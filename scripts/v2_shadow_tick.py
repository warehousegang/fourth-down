"""Prepared prospective worker. Disabled at the first instruction until approval.

Caller restores the separate append-only ledger; must publish it with CAS after
success. This script never updates V1 or the portfolio and performs no scoring.
"""
import argparse
import json
import sys
import subprocess
from datetime import datetime, timezone
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from ml.current_source import iso, normalize, sha
from ml.v2_capture import (Ledger, coverage, finalize, phase, require_activation,
                           schedule_changes, stage)
from scripts.v2_shadow_dry_run import acquire


def persistence(checkout, ledger):
    witnesses={}
    for path in (ledger.root/'stages').glob('*.json'):
        name='ledger/stages/'+path.name
        source=Path(checkout)/name
        if not source.exists() or source.read_bytes()!=path.read_bytes():
            continue
        commit=subprocess.check_output(['git','-C',str(checkout),'log','-1','--format=%H','--',name],text=True).strip()
        if not commit: continue
        original=subprocess.check_output(['git','-C',str(checkout),'show',f'{commit}:{name}'])
        if original!=path.read_bytes(): raise ValueError('Committed stage differs from local copy')
        when=subprocess.check_output(['git','-C',str(checkout),'show','-s','--format=%cI',commit],text=True).strip()
        witnesses[sha(original)]={'commit':commit,'committed_at':when,'path':name}
    return witnesses


def tick(output,state_checkout=None):
    require_activation()  # before any network, ledger or input read
    if state_checkout is None: raise ValueError('Separate state checkout is required')
    ledger=Ledger(output)
    witnesses=persistence(state_checkout,ledger)
    try:
        captures,archive,receipt=acquire()
    except Exception as error:
        ledger.receipt('coverage',dict(generated_at=iso(datetime.now(timezone.utc)),
            status='source_unavailable',denominator_unknown=True,scorecard_eligible=False,
            reason=type(error).__name__))
        # A persisted outage receipt is not a successful capture. CLI exits nonzero below.
        return {'status':'source_unavailable'}
    games=normalize(captures['schedule'][0],2026)
    observed=datetime.now(timezone.utc)
    voids=schedule_changes(ledger,games,observed)
    for game in games:
        current=datetime.now(timezone.utc)
        state=phase(game,current)
        if state=='stage':
            stage(ledger,captures,archive,receipt,game,current)
        elif state in ('finalize','missed_cutoff'):
            finalize(ledger,game,current,schedule_observed_at=captures['schedule'][1]['retrieved_at'],persisted_stages=witnesses)
    decisions=[json.loads(p.read_bytes()) for p in (ledger.root/'decisions').glob('*.json')]
    all_voids=[json.loads(p.read_bytes()) for p in (ledger.root/'voids').glob('*.json')]
    report=coverage(games,datetime.now(timezone.utc),decisions,all_voids)
    ledger.receipt('coverage',report)
    return {'status':'success','coverage':report['state_counts'],'voids':len(voids)}


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--output',required=True);parser.add_argument('--state-checkout',required=True);args=parser.parse_args()
    result=tick(args.output,args.state_checkout);print(json.dumps(result,sort_keys=True))
    raise SystemExit(0 if result['status']=='success' else 1)
