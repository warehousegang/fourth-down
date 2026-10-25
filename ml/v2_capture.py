"""T-60 shadow capture, immutable pairing and coverage. No fitting or V1 writes.

The only shipped real-data entry point is an explicitly unscored dry run.
The prospective gate requires a separately reviewed activation revision.
"""
import json
import os
import re
import tempfile
from collections import Counter
from functools import lru_cache
from datetime import datetime, timedelta, timezone
from pathlib import Path

from ml.current_source import FINAL, SCHEDULED, canonical, iso, normalize, sha, timestamp
from ml.data import ROOT
from ml.evidence_bundle import decode_bundle
from ml.lifecycle import IN_PROGRESS, eligibility, input_verification
from ml.v2_prospective import (MODEL_SHA, RESULT_SHA, _pbp_totals, _prior_scores,
                               feature_state, frozen_v2, probability, verify_capture)
from ml.v2_rehearsal import authorized, check_capture

CONFIG = ROOT / 'research/v2/shadow/ACTIVATION.json'
IDENTITY_KEYS = ('id', 'season', 'week', 'home', 'away', 'day', 'kickoff')


def config():
    p = json.loads(CONFIG.read_bytes())
    if p['model_sha256'] != MODEL_SHA or p['season'] != 2026:
        raise ValueError('Frozen model/season mismatch')
    return p


def require_activation():
    p = config()
    if not (p['enabled'] and p['activation_approved'] and p.get('approval_reference')):
        raise PermissionError('Recurring/prospective V2 remains disabled pending owner approval')
    if p['public_publication'] or p['automatic_promotion']:
        raise PermissionError('Shadow activation cannot publish or promote a model')
    authorized()


def identity(game):
    if game.get('season') != 2026 or not re.fullmatch(r'ngs-2026-\d+', game.get('id', '')):
        raise ValueError('Only 2026 game identities allowed')
    return {k: game[k] for k in IDENTITY_KEYS}


def key(game):
    return sha(canonical(identity(game)))


def cutoff(game):
    return timestamp(game['kickoff']) - timedelta(minutes=config()['decision_minutes_before_kickoff'])


def phase(game, now):
    """UTC event-time scheduling; no weekday assumptions or local DST arithmetic."""
    identity(game)
    p = config()
    if not game['kickoff']:
        return 'unconfirmed_kickoff'
    due = cutoff(game)
    if due <= timestamp(p['activation_at']):
        return 'before_activation'
    if game.get('phase') not in SCHEDULED:
        if game.get('phase') in FINAL | IN_PROGRESS and now > due + timedelta(minutes=p['maximum_finalization_delay_minutes']):
            return 'missed_cutoff'
        return 'not_scheduled'
    if now < due - timedelta(minutes=p['stage_minutes_before_cutoff']):
        return 'pending'
    if now < due:
        return 'stage'
    if now < timestamp(game['kickoff']) and now <= due + timedelta(minutes=p['maximum_finalization_delay_minutes']):
        return 'finalize'
    return 'missed_cutoff'


class Ledger:
    """Content-addressed objects and exclusive decision slots; no mutable latest pointer."""
    def __init__(self, directory):
        self.root = Path(directory).absolute()
        allowed = (ROOT / 'data/research-v2/prospective').resolve()
        temp = Path(tempfile.gettempdir()).resolve()
        roots = [allowed, temp]
        if os.environ.get('GITHUB_ACTIONS') == 'true' and os.environ.get('RUNNER_TEMP'):
            runner = Path(os.environ['RUNNER_TEMP']).resolve()
            if not runner.is_relative_to(ROOT.resolve()):
                roots.append(runner)
        if not any(self.root.resolve().is_relative_to(p) for p in roots):
            raise ValueError('Shadow ledger must be isolated from public/V1 files')
        for p in (self.root, *self.root.parents):
            if p.is_symlink():
                raise ValueError('Symlink ledger forbidden')
        self.root.mkdir(parents=True, exist_ok=True)

    def put(self, name, body):
        path = self.root / name
        if Path(name).is_absolute() or '..' in Path(name).parts:
            raise ValueError('Unsafe ledger path')
        for parent in (path, *path.parents):
            if parent.is_symlink():
                raise ValueError('Symlink ledger forbidden')
        path.parent.mkdir(parents=True, exist_ok=True)
        temporary = None
        try:
            with tempfile.NamedTemporaryFile(dir=path.parent, delete=False) as stream:
                temporary = Path(stream.name)
                stream.write(body); stream.flush(); os.fsync(stream.fileno())
            try:
                os.link(temporary, path, follow_symlinks=False)
            except FileExistsError:
                if path.read_bytes() != body:
                    raise ValueError('Immutable capture collision: ' + name)
        finally:
            if temporary is not None:
                temporary.unlink(missing_ok=True)
        return name

    def blob(self, body):
        return self.put('objects/' + sha(body), body)

    def read(self, name):
        if not re.fullmatch(r'objects/[0-9a-f]{64}', name):
            raise ValueError('Invalid object reference')
        body = (self.root / name).read_bytes()
        if sha(body) != name.split('/')[-1]:
            raise ValueError('Corrupt ledger object')
        return body

    def receipt(self, group, record, slot=None):
        body = canonical(record)
        if group not in ('stages', 'decisions', 'voids', 'coverage', 'dry-runs'):
            raise ValueError('Invalid receipt namespace')
        if slot is not None and not re.fullmatch(r'[0-9a-f]{64}', slot):
            raise ValueError('Invalid receipt identity')
        return self.put(f'{group}/{slot or sha(body)}.json', body)


@lru_cache(maxsize=2)
def _decoded_archive(raw, digest, manifest_digest):
    # Reuse only byte-identical, fully verified archives within this process.
    return decode_bundle(raw, 2026, digest, manifest_digest)[0]


def validate_archive(raw, receipt):
    if (receipt.get('repository') != 'warehousegang/thomashowarddev'
            or not re.fullmatch(r'[0-9a-f]{40}', receipt.get('commit', ''))
            or receipt.get('path') != '.fourth-down-state/forecast-evidence-2026.zip'
            or timestamp(receipt['commit_at']) > timestamp(receipt['retrieved_at'])):
        raise ValueError('Invalid V1 Git archive provenance')
    return _decoded_archive(raw, receipt['sha256'], receipt['manifest_sha256'])


def select_v1(raw, receipt, target, decision):
    """Select existing bytes only. Verification never issues a new V1 prediction."""
    if timestamp(receipt['retrieved_at']) >= decision:
        return None, ['v1_archive_not_observed_before_cutoff']
    payload = validate_archive(raw, receipt)
    snapshots = [json.loads(b) for n, b in payload.items() if '/snapshot-' in n]
    candidates, rejected = [], []
    for name, body in payload.items():
        if '/current/forecast-' not in name:
            continue
        artifact = json.loads(body)
        if timestamp(artifact['generated_at']) > decision:
            continue
        for g in artifact['games']:
            if g['id'] != target['id']:
                continue
            reasons = eligibility(g, artifact, target) + input_verification(g, artifact, snapshots)
            if reasons:
                rejected.extend(reasons)
                continue
            candidates.append(dict(game_id=g['id'], artifact_file=Path(name).name,
                artifact_sha256=sha(body), generated_at=g['generated_at'],
                feature_cutoff=g['cutoff'], evaluation_cutoff=iso(decision),
                home_probability=g['home_probability'], away_probability=g['away_probability'],
                age_hours=(decision-timestamp(g['generated_at'])).total_seconds()/3600,
                model_id=g['model_id'], provenance=receipt))
    if not candidates:
        return None, sorted(set(rejected)) or ['no_actual_eligible_archived_v1']
    return max(candidates, key=lambda v:(timestamp(v['generated_at']), v['artifact_sha256'])), []


def stage(ledger, captures, archive, archive_receipt, target, observed, *, synthetic=False):
    """Seal complete source bytes and actual V1 archive before the cutoff."""
    if not synthetic:
        authorized()  # limited score-only data permission; not prospective activation
    due = cutoff(target)
    if phase(target, observed) != 'stage':
        raise ValueError('Outside pre-cutoff stage window')
    for kind, (raw, receipt) in captures.items():
        if synthetic:
            verify_capture(raw, receipt, kind, due, simulation=True)
        else:
            check_capture(raw, receipt, kind, due)
        if timestamp(receipt['retrieved_at']) > observed:
            raise ValueError('Capture observed after stage receipt')
    if set(captures) != {'prior', 'schedule', 'pbp'}:
        raise ValueError('Missing required captures')
    if not synthetic and sha(captures['prior'][0]) != config()['prior_sha256']:
        raise ValueError('2025 prior differs from already authorized bytes')
    games = normalize(captures['schedule'][0], 2026, full_coverage=not synthetic)
    actual = next((g for g in games if g['id'] == target['id']), None)
    if actual is None or identity(actual) != identity(target) or actual['phase'] not in SCHEDULED:
        raise ValueError('Stage schedule identity mismatch')
    if timestamp(archive_receipt['retrieved_at']) > observed:
        raise ValueError('Archive observed after stage receipt')
    validate_archive(archive, archive_receipt)
    sources = {k:dict(object=ledger.blob(raw), receipt=r) for k,(raw,r) in captures.items()}
    record = dict(schema_version=1, mode='synthetic-stage' if synthetic else 'shadow-stage',
        target=identity(target), phase=target['phase'], observed_at=iso(observed), cutoff=iso(due),
        config_sha256=sha(CONFIG.read_bytes()), sources=sources,
        v1_archive=dict(object=ledger.blob(archive), receipt=archive_receipt),
        scorecard_eligible=False)
    ledger.receipt('stages', record)
    return record


def infer(captures, target, decision, *, synthetic=False):
    for kind, (raw, r) in captures.items():
        if synthetic:
            verify_capture(raw, r, kind, decision, simulation=True)
        else:
            check_capture(raw, r, kind, decision)
    if not synthetic and sha(captures['prior'][0]) != config()['prior_sha256']:
        raise ValueError('Unapproved prior vintage')
    games = normalize(captures['schedule'][0], 2026, full_coverage=not synthetic)
    for g in games:
        g['observed_at'] = captures['schedule'][1]['retrieved_at']
    actual = next((g for g in games if g['id'] == target['id']), None)
    if actual is None or identity(actual) != identity(target):
        raise ValueError('Target does not match captured schedule')
    priors = _prior_scores(captures['prior'][0], full_coverage=not synthetic)
    totals, joins = _pbp_totals(captures['pbp'][0], games, target['day'])
    features, history = feature_state(actual, games, totals, priors, decision)
    p = probability(features)
    return dict(features=features, history=history, joins=joins, home_probability=p, away_probability=1-p)


def decision_record(target, decision, generated, captures, archive, archive_receipt, *, synthetic=False):
    if not decision <= generated < timestamp(target['kickoff']):
        raise ValueError('Decision must be pregame, with honest generation timestamp')
    v1, reasons = select_v1(archive, archive_receipt, target, decision)
    v2, errors = None, []
    try:
        v2 = infer(captures, target, decision, synthetic=synthetic)
    except (ValueError, KeyError) as error:
        errors = [str(error)]
    paired = 'both' if v1 and v2 else 'v1_only' if v1 else 'v2_only' if v2 else 'neither'
    return dict(schema_version=1, mode='shadow-dry-run' if not synthetic else 'synthetic-t60',
        prospective=False, scorecard_eligible=False, target=identity(target), cutoff=iso(decision),
        generated_at=iso(generated), model_id=frozen_v2()['id'], model_sha256=MODEL_SHA,
        result_sha256=RESULT_SHA, config_sha256=sha(CONFIG.read_bytes()),
        code_sha256={n:sha((ROOT/n).read_bytes()) for n in ('ml/v2_capture.py','ml/v2_prospective.py')},
        v1=v1, v2=v2, pair_category=paired, v1_exclusions=reasons, v2_exclusions=errors,
        sources=[r for _,r in captures.values()],
        limitations=['Not eligible for prospective scoring until separately approved activation',
                    'V1 is an actual earlier archived prediction, not a regenerated T-60 forecast',
                    'Source publication time is not retrieval time; no injury/news/weather/QB inputs'])


def finalize(ledger, target, now, *, synthetic=False, schedule_observed_at=None, persisted_stages=None):
    """Testable T-60 execution. Real prospective writes are disabled before any I/O."""
    if not synthetic:
        require_activation()
    slot = key(target)
    path = ledger.root / 'decisions' / (slot+'.json')
    if path.exists():
        return json.loads(path.read_bytes())
    due = cutoff(target)
    state = phase(target, now)
    if state in ('pending', 'stage'):
        raise ValueError('Decision is not due')
    base = dict(schema_version=1, target=identity(target), cutoff=iso(due), generated_at=iso(now),
                mode='synthetic-t60' if synthetic else 'v2-prospective-shadow', prospective=not synthetic, scorecard_eligible=False,
                pair_category='neither', v1=None, v2=None)
    invalidated = {json.loads(p.read_bytes())['invalidated_identity'] for p in (ledger.root/'voids').glob('*.json')}
    if slot in invalidated:
        record = dict(base, exclusion='schedule_identity_voided')
    elif state != 'finalize':
        record = dict(base, exclusion=state)
    elif schedule_observed_at is None or not due <= timestamp(schedule_observed_at) <= now:
        record = dict(base, exclusion='schedule_not_rechecked_at_finalization')
    else:
        stages = [json.loads(p.read_bytes()) for p in (ledger.root/'stages').glob('*.json')]
        persisted_stages = persisted_stages or {}
        candidates = [s for s in stages if (synthetic or
                      (sha(canonical(s)) in persisted_stages and
                       timestamp(s['observed_at']) <= timestamp(persisted_stages[sha(canonical(s))]['committed_at']) < due))
                      and s['target'] == identity(target)
                      and s['config_sha256'] == sha(CONFIG.read_bytes())
                      and due-timedelta(minutes=config()['stage_minutes_before_cutoff']) <= timestamp(s['observed_at']) < due]
        if not candidates:
            record = dict(base, exclusion='no_sealed_pre_cutoff_capture')
        else:
            s = max(candidates, key=lambda s:(timestamp(s['observed_at']),sha(canonical(s))))
            captures = {k:(ledger.read(v['object']),v['receipt']) for k,v in s['sources'].items()}
            record = decision_record(target,due,now,captures,ledger.read(s['v1_archive']['object']),
                                     s['v1_archive']['receipt'],synthetic=synthetic)
            record['stage_sha256'] = sha(canonical(s))
            record['stage_persistence'] = persisted_stages.get(record['stage_sha256'])
            record['finalization_delay_seconds'] = (now-due).total_seconds()
            if not synthetic:
                finished = datetime.now(timezone.utc)
                if phase(target,finished) != 'finalize':
                    record = dict(base,generated_at=iso(finished),exclusion='missed_cutoff_during_inference')
                else:
                    record.update(generated_at=iso(finished),finalization_delay_seconds=(finished-due).total_seconds())
                    record.update(mode='v2-prospective-shadow',prospective=True,
                              scorecard_eligible=record['pair_category']=='both',
                              activation_at=config()['activation_at'],approval_reference=config()['approval_reference'])
    if record.get('exclusion') in ('missed_cutoff', 'missed_cutoff_during_inference', 'schedule_not_rechecked_at_finalization'):
        # Missing V2 capture must not erase an already sealed V1-only observation.
        witnesses = persisted_stages or {}
        saved = [json.loads(p.read_bytes()) for p in (ledger.root/'stages').glob('*.json')]
        saved = [s for s in saved if s['target'] == identity(target)
                 and s['config_sha256'] == sha(CONFIG.read_bytes())
                 and timestamp(s['observed_at']) < due
                 and (synthetic or (sha(canonical(s)) in witnesses and
                     timestamp(s['observed_at']) <= timestamp(witnesses[sha(canonical(s))]['committed_at']) < due))]
        if saved:
            s = max(saved,key=lambda s:(timestamp(s['observed_at']),sha(canonical(s))))
            v1,reasons = select_v1(ledger.read(s['v1_archive']['object']),s['v1_archive']['receipt'],target,due)
            record.update(v1=v1,v1_exclusions=reasons,pair_category='v1_only' if v1 else 'neither',
                          stage_sha256=sha(canonical(s)))
    ledger.receipt('decisions',record,slot)
    return record


def schedule_changes(ledger, games, observed):
    """Append-only void notices; never overwrite forecasts after a schedule change."""
    current = {g['id']:g for g in games}
    voids = []
    for group in ('stages','decisions'):
        for path in (ledger.root/group).glob('*.json'):
            r = json.loads(path.read_bytes()); old = r['target']; new = current.get(old['id'])
            if new is None or identity(new) != old or new['phase'] not in SCHEDULED:
                # A normal final/in-progress phase is not itself evidence of rescheduling.
                if new and identity(new) == old and new['phase'] not in ('POSTPONED','CANCELLED','CANCELED','DELAYED','SUSPENDED'):
                    continue
                event = dict(game_id=old['id'], invalidated_identity=sha(canonical(old)),
                             replacement=identity(new) if new else None, reason='schedule_changed_or_unconfirmed',
                             observed_at=iso(observed), original_receipt_sha256=sha(path.read_bytes()))
                slot = sha(canonical({'identity':event['invalidated_identity'],'replacement':event['replacement']}))
                existing = ledger.root/'voids'/f'{slot}.json'
                if not existing.exists(): ledger.receipt('voids',event,slot)
                voids.append(json.loads(existing.read_bytes()))
    return voids


def coverage(games, now, decisions=(), voids=()):
    indexed = {key(r['target']):r for r in decisions}
    invalid = {v['invalidated_identity'] for v in voids}
    rows = []
    for game in games:
        row = dict(target=identity(game), state=phase(game,now), pair_category=None, exclusions=[])
        record = indexed.get(key(game))
        if key(game) in invalid:
            row.update(state='void_schedule_change',exclusions=['schedule_changed'])
        elif record:
            row.update(state='recorded',pair_category=record['pair_category'],
                       exclusions=[record['exclusion']] if 'exclusion' in record else record.get('v1_exclusions',[])+record.get('v2_exclusions',[]))
        elif row['state'] not in ('pending','stage','finalize'):
            row['exclusions']=[row['state']]
        rows.append(row)
    return dict(schema_version=1, generated_at=iso(now), activation_at=config()['activation_at'],
        scorecard_eligible=False, total_games=len(rows), state_counts=dict(Counter(r['state'] for r in rows)),
        pair_counts=dict(Counter(r['pair_category'] for r in rows if r['pair_category'])), games=rows)
