"""Separate Git ledger persistence. Add-only fast-forward pushes, never force.

The reviewed workflow uses only warehousegang/fourth-down:v2-shadow-state.
No credentials in arguments; Git uses the caller's ephemeral Actions credential.
"""
import argparse
import json
import subprocess
import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from ml.v2_capture import Ledger, require_activation

BRANCH='v2-shadow-state'
REMOTE='https://github.com/warehousegang/fourth-down.git'


def git(directory,*args):
    return subprocess.check_output(['git','-C',str(directory),*args],text=True).strip()


def publish(checkout,ledger):
    require_activation()
    return append_state(checkout,ledger)


def append_state(checkout,ledger):
    """Pure local-copy/check operation plus configured Git push; test with a local bare remote."""
    checkout=Path(checkout);ledger=Path(ledger)
    if git(checkout,'branch','--show-current')!=BRANCH: raise ValueError('Wrong state branch')
    if git(checkout,'status','--porcelain'): raise ValueError('Dirty ledger checkout')
    expected=git(checkout,'rev-parse','HEAD')
    for source in sorted(ledger.rglob('*')):
        if source.is_symlink(): raise ValueError('Symlink state forbidden')
        if not source.is_file(): continue
        name=source.relative_to(ledger)
        if name.parts[0] not in ('objects','stages','decisions','voids','coverage'):
            raise ValueError('Only shadow ledger namespaces may persist')
        destination=checkout/'ledger'/name
        if any(p.is_symlink() for p in (destination,*destination.parents)): raise ValueError('Symlink destination')
        if destination.exists():
            if destination.read_bytes()!=source.read_bytes(): raise ValueError('Immutable state mutation rejected')
        else:
            destination.parent.mkdir(parents=True,exist_ok=True)
            with destination.open('xb') as output: output.write(source.read_bytes())
    git(checkout,'add','--','ledger')
    changes=git(checkout,'diff','--cached','--name-status').splitlines()
    if not changes: return {'changed':False,'commit':expected}
    if any(not row.startswith('A\tledger/') for row in changes): raise ValueError('Only appended shadow state allowed')
    git(checkout,'commit','-m','Append immutable V2 shadow capture evidence')
    # Ordinary fast-forward push rejects a concurrent writer; no force/reset/rebase.
    git(checkout,'push','origin',f'HEAD:refs/heads/{BRANCH}')
    return {'changed':True,'commit':git(checkout,'rev-parse','HEAD'),'parent':expected}


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--checkout',required=True);parser.add_argument('--ledger',required=True)
    args=parser.parse_args();require_activation()
    if git(args.checkout,'remote','get-url','origin')!=REMOTE: raise ValueError('Unexpected state remote')
    print(json.dumps(publish(args.checkout,args.ledger),sort_keys=True))
