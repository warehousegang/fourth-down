"""One read-only hosted rehearsal; captures real inputs, never enters prospective scoring."""
import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from urllib.request import Request, urlopen

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from ml.current_source import DOWNLOAD, SCHEDULED, canonical, iso, normalize, sha, timestamp
from ml.v2_prospective import PBP_URL, PBP_LICENSE, SCHEDULE_LICENSE
from ml.v2_rehearsal import authorized
from ml.v2_capture import (Ledger, config, coverage, decision_record, infer, select_v1,
                           validate_archive)


def now():
    return datetime.now(timezone.utc)


def fetch(url, limit):
    if not url.startswith(('https://api.github.com/', 'https://github.com/', 'https://raw.githubusercontent.com/')):
        raise ValueError('Unexpected source host')
    with urlopen(Request(url,headers={'User-Agent':'FourthDown-V2-shadow-dry-run','Cache-Control':'no-cache'}),timeout=60) as response:
        body=response.read(limit+1)
    if not 0<len(body)<=limit: raise ValueError('Source size limit')
    return body


def acquire():
    authorized()
    captures={}
    for kind,season,repo,tag,url,license_url,limit in (
        ('prior',2025,'sportsdataverse/sportsdataverse-data','nfl_ngs_schedules',f'{DOWNLOAD}/ngs_schedule_2025.csv',SCHEDULE_LICENSE,2_000_000),
        ('schedule',2026,'sportsdataverse/sportsdataverse-data','nfl_ngs_schedules',f'{DOWNLOAD}/ngs_schedule_2026.csv',SCHEDULE_LICENSE,2_000_000),
        ('pbp',2026,'nflverse/nflverse-data','pbp',PBP_URL,PBP_LICENSE,128_000_000)):
        metadata=json.loads(fetch(f'https://api.github.com/repos/{repo}/releases/tags/{tag}',8_000_000))
        asset=next(a for a in metadata['assets'] if a['browser_download_url']==url)
        # Reject a new prior vintage BEFORE downloading or interpreting it.
        if kind=='prior' and asset.get('digest')!='sha256:'+config()['prior_sha256']:
            raise ValueError('2025 source changed: new vintage requires review')
        if not 0<asset['size']<=limit: raise ValueError('Unbounded source')
        started=iso(now());raw=fetch(url,limit);retrieved=iso(now())
        if asset.get('digest')!='sha256:'+sha(raw) or len(raw)!=asset['size']:
            raise ValueError('Upstream digest mismatch')
        captures[kind]=(raw,dict(kind=kind,season=season,synthetic=False,url=url,license_url=license_url,
            asset_id=asset['id'],raw_sha256=sha(raw),upstream_digest=asset['digest'],size=len(raw),
            source_updated_at=asset['updated_at'],retrieval_started_at=started,retrieved_at=retrieved))
    repo='warehousegang/thomashowarddev'
    commit=json.loads(fetch(f'https://api.github.com/repos/{repo}/commits/main',4_000_000))
    prefix=f'https://raw.githubusercontent.com/{repo}/{commit["sha"]}/.fourth-down-state/'
    receipt=json.loads(fetch(prefix+'forecast-evidence-2026.json',100_000))
    body=fetch(prefix+'forecast-evidence-2026.zip',64*1024*1024)
    receipt.update(repository=repo,commit=commit['sha'],commit_at=commit['commit']['committer']['date'],
                   path='.fourth-down-state/forecast-evidence-2026.zip',retrieved_at=iso(now()))
    validate_archive(body,receipt)
    return captures,body,receipt


def verify(directory):
    ledger=Ledger(directory)
    report=json.loads((ledger.root/'dry-run.json').read_bytes())
    manifest=report['inputs']
    captures={k:(ledger.read(v['object']),v['receipt']) for k,v in manifest['sources'].items()}
    archive=ledger.read(manifest['v1_archive']['object']); receipt=manifest['v1_archive']['receipt']
    validate_archive(archive,receipt)
    count=0
    for item in report['predictions']:
        body=(ledger.root/item['file']).read_bytes()
        if sha(body)!=item['sha256']: raise ValueError('Prediction checksum mismatch')
        record=json.loads(body)
        if record['prospective'] or record['scorecard_eligible']: raise ValueError('Dry run entered prospective cohort')
        target=dict(record['target'],phase='')
        decision=timestamp(record['cutoff'])
        try:
            replay=infer(captures,target,decision)
            errors=[]
        except (ValueError, KeyError) as error:
            replay=None;errors=[str(error)]
        if record['v2']!=replay or record['v2_exclusions']!=errors: raise ValueError('V2 replay differs')
        v1,reasons=select_v1(archive,receipt,target,decision)
        if v1!=record['v1'] or reasons!=record['v1_exclusions']: raise ValueError('V1 original pairing differs')
        count+=1
    return dict(verified_predictions=count, exact_v2_reproduction=True, original_v1_pairs_verified=True,
                prospective_scorecard_entries=0, v1_generation_or_writes=False)


def run(directory):
    ledger=Ledger(directory)
    if (ledger.root/'dry-run.json').exists():
        return verify(directory)  # No fetch, replacement or newer timestamps on retry.
    captures,archive,receipt=acquire()
    inputs=dict(sources={k:dict(object=ledger.blob(raw),receipt=r) for k,(raw,r) in captures.items()},
                v1_archive=dict(object=ledger.blob(archive),receipt=receipt))
    decision=now()
    games=normalize(captures['schedule'][0],2026)
    selected=[g for g in games if g['kickoff'] and g['phase'] in SCHEDULED and
              decision<timestamp(g['kickoff']) and (timestamp(g['kickoff'])-decision).total_seconds()<=7*86400]
    predictions=[]
    for target in selected:
        record=decision_record(target,decision,now(),captures,archive,receipt)
        record['cutoff_policy']='Ad hoc real-clock hosted dry run; NOT a T-60 prospective capture'
        record['inputs']=inputs
        file=ledger.receipt('dry-runs',record)
        predictions.append(dict(file=file,sha256=sha(canonical(record)),game_id=target['id'],
            away=target['away'],home=target['home'],kickoff=target['kickoff'],pair_category=record['pair_category'],
            v1_home_probability=record['v1']['home_probability'] if record['v1'] else None,
            v2_home_probability=record['v2']['home_probability'] if record['v2'] else None,
            exclusions=record['v1_exclusions']+record['v2_exclusions']))
    report=dict(schema_version=1,mode='hosted-shadow-dry-run',prospective=False,scorecard_eligible=False,
        decision_at=iso(decision),generated_at=iso(now()),inputs=inputs,predictions=predictions,
        coverage=coverage(games,decision),selection_window_days=7,
        activation=config(),source_commit=__import__('os').environ.get('GITHUB_SHA'),
        github_run_id=__import__('os').environ.get('GITHUB_RUN_ID'))
    ledger.put('dry-run.json',canonical(report))
    return verify(directory)


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--output',required=True);parser.add_argument('--verify',action='store_true')
    args=parser.parse_args()
    print(json.dumps(verify(args.output) if args.verify else run(args.output),sort_keys=True))
