"""One authorized local rehearsal. No fitting, network, activation or public writes.

Real captures are pinned to the approved exposure. These ad hoc decisions are
explicitly excluded from the separately disabled T-60 prospective cohort.
"""
import argparse
import csv
import io
import json
import os
import tempfile
from collections import Counter, defaultdict
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pyarrow.parquet as pq

from ml.current_source import DOWNLOAD, EASTERN, FINAL, SCHEDULED, canonical, iso, normalize, sha, timestamp
from ml.data import ROOT
from ml.v2_prospective import (MODEL_SHA, RESULT_SHA, PLAN, PBP_URL, PBP_LICENSE,
    SCHEDULE_LICENSE, _pbp_totals, _prior_scores, feature_state, frozen_v2, plan, probability)

AUTH = ROOT / 'docs/holdout-amendments/001-2026-10-25-v2-prior-authorization.json'
EXPOSURE = AUTH.with_name('002-2026-10-25-v2-prior-exposure.json')
AUTH_SHA = '0cf4d3328446aeebada7c2a9d3f487b5ef74130ddcb14e7e836dc1ec3d86c254'
EXPOSURE_SHA = 'e6ee766d7496f75f2b475d468ab218b0e3f63b94408762355e2f98691496b3fc'
MANIFEST_SHA = 'e4e647c093e97a4aca67e0497821be635d35dd527b4a374ec07a9b54247fa69a'
INPUT = ROOT / 'data/research-v2/limited-rehearsal-2026-10-25/inputs/manifest.json'
OUTPUT = ROOT / 'data/research-v2/prospective/limited-rehearsal-2026-10-25'


def authorized():
    if sha(AUTH.read_bytes()) != AUTH_SHA or sha(EXPOSURE.read_bytes()) != EXPOSURE_SHA:
        raise PermissionError('Limited rehearsal authorization/exposure changed')
    exposure = json.loads(EXPOSURE.read_bytes())
    if exposure['previous_amendment_sha256'] != AUTH_SHA:
        raise PermissionError('Invalid append-only amendment chain')
    auth = json.loads(AUTH.read_bytes())
    freeze = ROOT/'docs/HOLDOUT_PROTOCOL_FREEZE.json'
    if sha(freeze.read_bytes()) != auth['original_holdout_freeze_sha256']:
        raise PermissionError('Original holdout freeze changed')
    for name, digest in json.loads(freeze.read_bytes())['file_sha256'].items():
        if sha((ROOT/name).read_bytes()) != digest:
            raise PermissionError('Original holdout boundary changed')
    p = plan()
    if not p['prior_2025_use_approved'] or p['enabled'] or p['activation_approved'] or p['activation_at']:
        raise PermissionError('Only the approved disabled local-rehearsal scope is supported')
    frozen_v2()


def check_capture(raw, receipt, kind, cutoff):
    season = 2025 if kind == 'prior' else 2026
    url = PBP_URL if kind == 'pbp' else f'{DOWNLOAD}/ngs_schedule_{season}.csv'
    license_url = PBP_LICENSE if kind == 'pbp' else SCHEDULE_LICENSE
    if (receipt.get('kind') != kind or receipt.get('season') != season
            or receipt.get('synthetic') is not False or receipt.get('url') != url
            or receipt.get('license_url') != license_url or receipt.get('raw_sha256') != sha(raw)
            or receipt.get('upstream_digest') != 'sha256:' + sha(raw)):
        raise ValueError('Unverified or out-of-scope rehearsal capture')
    updated, retrieved = timestamp(receipt['source_updated_at']), timestamp(receipt['retrieved_at'])
    if not updated <= retrieved < cutoff:
        raise ValueError('Capture must precede the actual decision cutoff')
    if kind != 'prior' and cutoff - retrieved > timedelta(hours=plan()['maximum_capture_age_hours']):
        raise ValueError('Current capture exceeds six-hour observation limit')


def load_captures(manifest_path=INPUT):
    authorized()  # before reading any protected input
    manifest_path = Path(manifest_path)
    if manifest_path.is_symlink() or not 0 < manifest_path.stat().st_size < 100_000:
        raise ValueError('Invalid capture manifest')
    body = manifest_path.read_bytes()
    if sha(body) != MANIFEST_SHA:
        raise ValueError('Only the sealed approved rehearsal captures are permitted')
    manifest = json.loads(body)
    if set(manifest) != {'prior', 'schedule', 'pbp'}:
        raise ValueError('Exactly three scoped captures required')
    captures = {}
    for kind, item in manifest.items():
        name = item['file']
        if Path(name).name != name or name.startswith('.'):
            raise ValueError('Capture path must be a local filename')
        path = manifest_path.parent / name
        limit = 128_000_000 if kind == 'pbp' else 2_000_000
        if path.is_symlink() or not 0 < path.stat().st_size <= limit:
            raise ValueError('Invalid capture file')
        raw = path.read_bytes()
        if sha(raw) != item['receipt']['raw_sha256']:
            raise ValueError('Capture checksum mismatch')
        captures[kind] = raw, item['receipt']
    return captures


def prior_coverage(raw):
    games = _prior_scores(raw)  # checks 2025-only, complete 272 REG games, 17/team
    rows = list(csv.DictReader(io.StringIO(raw.decode('utf-8-sig'))))
    types = Counter(r['season_type'] for r in rows)  # Never interpret non-REG scores.
    margins, ids = defaultdict(list), defaultdict(list)
    for g in games:
        for own, margin in ((g['home'], g['home_score']-g['away_score']),
                            (g['away'], g['away_score']-g['home_score'])):
            margins[own].append(margin); ids[own].append(g['id'])
    return {'season':2025, 'raw_rows':len(rows), 'rows_by_type':dict(types),
        'regular_games':len(games), 'excluded_non_regular':len(rows)-len(games),
        'first_game_day':min(g['day'] for g in games), 'last_game_day':max(g['day'] for g in games),
        'teams':{t:{'games':len(v), 'scoring_margin_sum':sum(v),
                    'shrunk_prior_margin':sum(v)/(len(v)+4), 'game_ids':sorted(ids[t])}
                 for t,v in sorted(margins.items())}}


def _record(captures, target, cutoff, generated, games=None):
    authorized()
    if target['season'] != 2026 or not target['kickoff'] or target['phase'] not in SCHEDULED:
        raise ValueError('Only scheduled future 2026 games are eligible')
    if not cutoff <= generated < timestamp(target['kickoff']):
        raise ValueError('Rehearsal must be generated before kickoff, never backdated')
    for kind in ('schedule', 'pbp', 'prior'):
        check_capture(*captures[kind], kind, cutoff)
    games = normalize(captures['schedule'][0],2026) if games is None else games
    for game in games: game['observed_at'] = captures['schedule'][1]['retrieved_at']
    priors = _prior_scores(captures['prior'][0])
    totals, joins = _pbp_totals(captures['pbp'][0],games,target['day'])
    model = frozen_v2()
    record = dict(schema_version=1, mode='v2-shadow-rehearsal', prospective=False,
        scorecard_eligible=False, game_id=target['id'], season=2026, week=target['week'],
        home=target['home'], away=target['away'], kickoff=target['kickoff'],
        cutoff=iso(cutoff), generated_at=iso(generated),
        prospective_t60_cutoff=iso(timestamp(target['kickoff'])-timedelta(minutes=60)),
        cutoff_policy='Actual ad hoc rehearsal decision time; not the T-60 prospective cohort',
        model_id=model['id'], model_sha256=MODEL_SHA, result_sha256=RESULT_SHA,
        feature_version=model['feature_version'], threshold=model['threshold'],
        authorization_sha256=AUTH_SHA, exposure_sha256=EXPOSURE_SHA, input_manifest_sha256=MANIFEST_SHA,
        protocol_sha256=sha((PLAN.parent/'PROTOCOL.md').read_bytes()), configuration_sha256=sha(PLAN.read_bytes()),
        code_sha256={name:sha((ROOT/name).read_bytes()) for name in
                    ('ml/v2_rehearsal.py','ml/v2_prospective.py','ml/v2_shadow_store.py','ml/v2_features.py','ml/v2_data.py')},
        sources=[captures[k][1] for k in ('schedule','pbp','prior')], joins=joins,
        source_age_hours={k:(cutoff-timestamp(r['source_updated_at'])).total_seconds()/3600 for k,(_,r) in captures.items()},
        status='unavailable', home_probability=None, away_probability=None, features={}, history={},
        limitations=['Local real-input rehearsal; excluded from all prospective/V1 scorecards',
                     'Source publication times remain distinct from current retrieval times',
                     'No quarterback, injury, weather or news inputs; probabilities condition on non-ties',
                     'Earlier opponent states use the source vintage captured before this decision',
                     '2025 REG scores consumed only as prior-season features; holdout evaluation remains locked'])
    try:
        features, history = feature_state(target,games,totals,priors,cutoff)
    except ValueError as exc:
        return dict(record,unavailable_reason=str(exc))
    p = probability(features)
    return dict(record,status='available',unavailable_reason=None,features=features,history=history,
                home_probability=p,away_probability=1-p)


def validate_record(record):
    authorized()
    if (record.get('prospective') is not False or record.get('scorecard_eligible') is not False
            or record.get('authorization_sha256') != AUTH_SHA or record.get('exposure_sha256') != EXPOSURE_SHA
            or record.get('input_manifest_sha256') != MANIFEST_SHA):
        raise ValueError('Rehearsal cannot activate or enter a prospective scorecard')
    cutoff = timestamp(record['cutoff'])
    sources = record['sources']
    if len(sources)!=3 or {s['kind'] for s in sources} != {'schedule','pbp','prior'}:
        raise ValueError('Missing rehearsal provenance')
    for source in sources:
        season = 2025 if source['kind']=='prior' else 2026
        url = PBP_URL if source['kind']=='pbp' else f'{DOWNLOAD}/ngs_schedule_{season}.csv'
        if source.get('synthetic') is not False or source.get('season')!=season or source.get('url')!=url:
            raise ValueError('Rehearsal provenance must be real and season-isolated')
        if not timestamp(source['source_updated_at']) <= timestamp(source['retrieved_at']) < cutoff:
            raise ValueError('Rehearsal source timestamp violates cutoff')
    day = timestamp(record['kickoff']).astimezone(EASTERN).date().isoformat()
    for side in record['history'].values():
        if any(d>=day for d in side['dates']) or any(not i.startswith('ngs-2025-') for i in side['prior_ids']):
            raise ValueError('Invalid rehearsal history cutoff or prior season')
        for entry in side['efficiency']:
            if any(d>=entry['gameday'] for d in entry['opponent_history_dates']):
                raise ValueError('Opponent future-game leakage')


def _seal(path, item):
    path.parent.mkdir(parents=True,exist_ok=True)
    body=canonical(item)
    with tempfile.NamedTemporaryFile(dir=path.parent,prefix='.pending-',delete=False) as f:
        temp=Path(f.name);f.write(body);f.flush();os.fsync(f.fileno())
    try:
        try: os.link(temp,path,follow_symlinks=False)
        except FileExistsError:
            if path.is_symlink() or path.read_bytes()!=body: raise ValueError('Immutable rehearsal batch conflict')
        fd=os.open(path.parent,os.O_RDONLY)
        try: os.fsync(fd)
        finally: os.close(fd)
    finally: temp.unlink(missing_ok=True)


def run():
    from ml.v2_shadow_store import _directory, read, write
    authorized(); _directory(OUTPUT)
    captures=load_captures()
    report_path=OUTPUT/'batch.json'
    if report_path.exists():
        report=json.loads(report_path.read_bytes())
        for receipt in report['records']: read(receipt)
        return report
    games=normalize(captures['schedule'][0],2026)
    session_path=OUTPUT/'session.json'
    if session_path.exists():
        session=json.loads(session_path.read_bytes());cutoff=timestamp(session['cutoff'])
    else:
        cutoff=datetime.now(timezone.utc)
        future=[g for g in games if g['phase'] in SCHEDULED and g['kickoff'] and timestamp(g['kickoff'])>cutoff]
        week=min(future,key=lambda g:timestamp(g['kickoff']))['week'] if future else None
        session={'cutoff':iso(cutoff),'week':week,'manifest_sha256':MANIFEST_SHA,'authorization_sha256':AUTH_SHA}
        _seal(session_path,session)
    if session['manifest_sha256']!=MANIFEST_SHA or session['authorization_sha256']!=AUTH_SHA:
        raise ValueError('Session authorization/capture mismatch')
    for kind in captures: check_capture(*captures[kind],kind,cutoff)
    coverage=prior_coverage(captures['prior'][0]);records=[];excluded=[]
    for g in games:
        if not g['kickoff']: reason='unconfirmed kickoff'
        elif timestamp(g['kickoff'])<=cutoff: reason='kickoff at/before actual rehearsal cutoff'
        elif g['phase'] not in SCHEDULED: reason='not confirmed scheduled'
        elif g['week']!=session['week']: reason='outside earliest upcoming week selected before scoring'
        else: reason=None
        if reason:
            excluded.append({'game_id':g['id'],'week':g['week'],'kickoff':g['kickoff'],'reason':reason});continue
        identity=dict(mode='v2-shadow-rehearsal',season=2026,game_id=g['id'],kickoff=g['kickoff'],cutoff=iso(cutoff))
        key=sha(canonical(identity));path=OUTPUT/'rehearsals'/f'{key}.json'
        if path.exists():
            receipt=dict(file=str(path),sha256=sha(path.read_bytes()),decision_id=key,prospective=False);read(receipt)
        elif datetime.now(timezone.utc)>=timestamp(g['kickoff']):
            excluded.append({'game_id':g['id'],'reason':'kickoff passed during rehearsal; no backdating'});continue
        else:
            record=_record(captures,g,cutoff,datetime.now(timezone.utc),games)
            # Record the actual completion clock, after feature derivation and inference.
            record['generated_at']=iso(datetime.now(timezone.utc))
            receipt=write(record,OUTPUT)
        records.append(receipt)
    report=dict(schema_version=1,mode='v2-shadow-rehearsal',prospective=False,scorecard_eligible=False,
        session=session,records=records,exclusions=excluded,prior_coverage=coverage,
        current_schedule_games=len(games),current_completed_games=sum(g['phase'] in FINAL for g in games),
        current_pbp_rows=pq.ParquetFile(io.BytesIO(captures['pbp'][0])).metadata.num_rows,
        sources=[captures[k][1] for k in ('prior','schedule','pbp')],
        attribution='SportsDataverse / NFL NGS schedule (MIT source attribution retained); nflverse/nflfastR PBP (CC BY 4.0). Team priors, efficiency totals and predictions are derived modifications.',
        recurring_enabled=False,holdout_evaluation_authorized=False)
    _seal(report_path,report)
    return report


def reproduce():
    """Replay saved inputs and timestamps, never mint a new or backdated forecast."""
    from ml.v2_shadow_store import read
    report=run();captures=load_captures();games=normalize(captures['schedule'][0],2026)
    for receipt in report['records']:
        saved=read(receipt);target=next(g for g in games if g['id']==saved['game_id'])
        expected=_record(captures,target,timestamp(saved['cutoff']),timestamp(saved['generated_at']),games)
        if canonical(saved)!=canonical(expected): raise ValueError('Rehearsal does not reproduce byte-for-byte')
    return {'records_reproduced':len(report['records']),'byte_identical':True,'new_forecasts_created':False}


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--reproduce',action='store_true')
    args=parser.parse_args()
    print(json.dumps(reproduce() if args.reproduce else run(),indent=2))
