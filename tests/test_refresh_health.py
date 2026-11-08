"""Collection outages must not masquerade as successful no-change checks."""
import copy
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
import subprocess
import sys

import pytest

from scripts.check_refresh_health import check


def receipt(captured=0, missing=None):
    return {'schema_version':1, 'changed':bool(captured), 'started_at':datetime.now(timezone.utc).isoformat(),
            'results':{'changed':bool(captured), 'captured':captured, 'requests':captured+1,
                       'missing':missing or []}}


@pytest.mark.parametrize('captured', [0, 2])
def test_success_and_pending_provider_files_are_healthy_without_mutating_receipt(captured):
    data=receipt(captured, ['ngs-2026-60308']); before=copy.deepcopy(data)
    assert check(data,datetime.fromisoformat(data['started_at']))=={'healthy':True, 'captured':captured, 'provider_files_not_yet_available':1,
           'elapsed_seconds':0, 'duration_maintenance_required':False}
    assert data==before


@pytest.mark.parametrize('changed', [False, True])
def test_outage_is_unhealthy_even_when_safe_evidence_was_published(changed):
    data={'schema_version':1, 'changed':changed,
          'results':{'changed':False, 'error':'URLError', 'action':'retain verified outcomes'}}
    before=copy.deepcopy(data)
    with pytest.raises(ValueError, match='provider check failed'): check(data)
    assert data==before


@pytest.mark.parametrize('data', [{}, {'schema_version':1}, {'schema_version':1,'results':{}},
    {'schema_version':1,'results':{'changed':False,'captured':True,'requests':1,'missing':[]}}])
def test_missing_collection_evidence_cannot_pass(data):
    with pytest.raises(ValueError, match='unknown'): check(data)


def test_cli_fails_without_echoing_exception_details_or_changing_files(tmp_path):
    path=tmp_path/'refresh.json'; body=json.dumps({'schema_version':1,'results':{'error':'SECRET_TEST_TOKEN'}})
    path.write_text(body)
    command=[sys.executable,str(Path(__file__).resolve().parents[1]/'scripts/check_refresh_health.py'),'--receipt',str(path)]
    run=subprocess.run(command,capture_output=True,text=True)
    assert run.returncode==1 and '::error title=Fourth Down result collection::' in run.stdout
    assert 'SECRET_TEST_TOKEN' not in run.stdout+run.stderr
    assert path.read_text()==body
    path.write_text(json.dumps(receipt()))
    run=subprocess.run(command,capture_output=True,text=True)
    assert run.returncode==0 and json.loads(run.stdout)['healthy']


def test_health_gate_follows_publication_and_covers_no_change_runs():
    workflow=(Path(__file__).resolve().parents[1]/'ops/external-scheduler/fourth-down-refresh.yml.proposed').read_text()
    assert workflow.index('Publish checked files') < workflow.index('Report result collection health')
    step=workflow.split('name: Report result collection health',1)[1]
    assert "if: always() && steps.refresh.outcome == 'success'" in step
    assert 'scripts/check_refresh_health.py --receipt "$RUNNER_TEMP/refresh.json"' in step


@pytest.mark.parametrize('seconds,warning', [(719,False),(720,True),(901,True)])
def test_duration_warning_precedes_the_fifteen_minute_cadence(seconds,warning):
    data=receipt(); now=datetime.fromisoformat(data['started_at'])+timedelta(seconds=seconds)
    assert check(data,now)['duration_maintenance_required'] is warning


@pytest.mark.parametrize('start', [None,'invalid','2026-11-08T12:00:00','2099-01-01T00:00:00Z'])
def test_unknown_or_future_start_time_does_not_claim_healthy_collection(start):
    data=receipt();data['started_at']=start
    with pytest.raises(ValueError,match='start time'):check(data)
