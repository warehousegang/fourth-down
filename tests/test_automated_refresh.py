"""Hosted orchestration tests; synthetic data only, no network, fitting or holdout."""
import subprocess
from datetime import timedelta

import pytest

from ml.current_source import timestamp
from scripts.automated_refresh import refresh_reasons, publication_deadline, stage
from scripts import portfolio_artifact
from scripts.publish_forecasts import permitted_changes, verify_settings, publish


def inputs():
    source = {'raw_sha256':'a'*64, 'source_updated_at':'2026-10-24T10:00:00Z'}
    previous = {'season':2026, 'generated_at':'2026-10-24T12:00:00Z',
                'valid_until':'2026-10-25T12:00:00Z', 'source':source}
    snapshot = {'season':2026, 'retrieved_at':'2026-10-24T12:05:00Z', **source, 'games':[]}
    state = {'source_commit':'b'*40}
    return snapshot, previous, state, 'b'*40


def test_unchanged_check_is_a_noop_and_does_not_stage_anything(tmp_path):
    assert refresh_reasons(*inputs(), timestamp('2026-10-24T12:06:00Z')) == []
    assert stage(tmp_path, {'changed':False}, None) == {'changed':False}
    assert not list(tmp_path.iterdir())


def test_changed_results_and_rescheduling_trigger_regeneration():
    args = list(inputs()); args[0]['raw_sha256'] = 'c'*64
    assert refresh_reasons(*args, timestamp('2026-10-24T12:06:00Z')) == ['source_changed']


@pytest.mark.parametrize('kickoff', [
    '2026-10-25T13:30:00Z', '2026-10-25T17:00:00Z', '2026-10-25T20:25:00Z',
    '2026-10-30T00:15:00Z', '2026-10-27T00:15:00Z', '2026-12-25T18:00:00Z',
    '2026-11-08T18:00:00Z',  # After US daylight saving changes.
])
def test_all_kickoff_windows_use_timestamps_not_weekday_assumptions(kickoff):
    args = list(inputs()); kick = timestamp(kickoff)
    generated = kick-timedelta(hours=4)
    args[1]['generated_at'] = generated.isoformat()
    args[1]['valid_until'] = (kick+timedelta(hours=20)).isoformat()
    for obj in (args[1]['source'], args[0]): obj['source_updated_at'] = generated.isoformat()
    args[0]['retrieved_at'] = (kick-timedelta(hours=1)).isoformat()
    args[0]['games'] = [{'kickoff':kickoff, 'phase':'SCHEDULED'}]
    now = kick-timedelta(hours=1)
    assert refresh_reasons(*args, now) == ['pregame_window']
    args[1]['generated_at'] = now.isoformat()
    assert refresh_reasons(*args, now+timedelta(minutes=1)) == []
    assert refresh_reasons(*args, kick) == ['kickoff_crossed']


def test_missing_or_postponed_kickoff_does_not_invent_pregame_window():
    args = list(inputs())
    args[0]['games'] = [{'kickoff':None,'phase':''}, {'kickoff':'2026-10-24T13:00:00Z','phase':'POSTPONED'}]
    assert refresh_reasons(*args, timestamp('2026-10-24T12:06:00Z')) == []


def test_stale_source_is_published_expired_once_not_relabelled_as_fresh():
    args = list(inputs())
    now = timestamp('2026-10-27T12:00:00Z')
    assert refresh_reasons(*args, now) == ['source_expired']
    args[1]['generated_at'] = now.isoformat()
    assert refresh_reasons(*args, now+timedelta(hours=13)) == []


def test_fresh_source_renews_after_twelve_hours():
    assert refresh_reasons(*inputs(), timestamp('2026-10-25T00:01:00Z')) == ['freshness_renewal']


def test_late_publication_cannot_create_a_backdated_pregame_archive():
    forecast = {'games':[{'status':'available', 'kickoff':'2026-10-25T17:00:00Z'}]}
    publication_deadline(forecast, timestamp('2026-10-25T16:57:00Z'))
    for now in ('2026-10-25T16:59:00Z','2026-10-25T17:01:00Z'):
        with pytest.raises(ValueError, match='kickoff'):
            publication_deadline(forecast, timestamp(now))


def test_changes_and_pages_settings_are_narrowly_scoped():
    permitted_changes(['fourth-down/index.html','.fourth-down-state/automation.json'])
    for name in ('CNAME','index.html','.github/workflows/other.yml','projects/nfl-predictor/index.html'):
        with pytest.raises(ValueError): permitted_changes([name])
    original = {'build_type':'legacy','cname':'thomashoward.dev','source':{'branch':'main','path':'/'}}
    verify_settings(original)
    for key,value in [('cname','example.com'),('build_type','workflow'),('source',{'branch':'main','path':'/docs'})]:
        with pytest.raises(ValueError): verify_settings({**original,key:value})


def test_pack_allows_generated_data_but_rejects_source_changes_and_deletions(tmp_path, monkeypatch):
    def git(*args): subprocess.run(['git',*args],cwd=tmp_path,check=True,capture_output=True)
    git('init'); git('config','user.name','Test'); git('config','user.email','test@example.com')
    file = tmp_path/'web/public/data/current/latest.json'; file.parent.mkdir(parents=True)
    file.write_text('{}'); (tmp_path/'model.py').write_text('original')
    git('add','.'); git('commit','-m','fixture')
    monkeypatch.setattr(portfolio_artifact,'ROOT',tmp_path)
    file.write_text('{"new":true}')
    assert len(portfolio_artifact.source_revision(True)) == 40
    with pytest.raises(ValueError): portfolio_artifact.source_revision()
    (tmp_path/'model.py').write_text('changed')
    with pytest.raises(ValueError): portfolio_artifact.source_revision(True)
    (tmp_path/'model.py').write_text('original'); file.unlink()
    with pytest.raises(ValueError): portfolio_artifact.source_revision(True)


def test_website_race_aborts_before_any_commit_or_build(tmp_path, monkeypatch):
    from scripts import publish_forecasts as module
    calls = []
    def fake_git(root,*args):
        calls.append(args)
        return 'a'*40 if args == ('rev-parse','HEAD') else 'b'*40
    monkeypatch.setattr(module,'git',fake_git)
    monkeypatch.setattr(module,'api',lambda *args:{'build_type':'legacy','cname':'thomashoward.dev','source':{'branch':'main','path':'/'}})
    with pytest.raises(ValueError,match='main moved'): publish(tmp_path)
    assert not any(args[0] in ('push','add','commit') for args in calls)


def test_unchanged_run_recovers_a_failed_pages_build_without_new_commit(tmp_path, monkeypatch):
    from scripts import publish_forecasts as module
    calls=[]; requests=[]; polls=[]
    def fake_git(root,*args):
        calls.append(args)
        return 'a'*40 if args[0] == 'rev-parse' else ''
    def fake_api(path, method='GET'):
        requests.append((path,method))
        if path == 'pages': return {'build_type':'legacy','cname':'thomashoward.dev','source':{'branch':'main','path':'/'}}
        if path == 'pages/builds': return {}
        polls.append(1)
        return {'commit':'a'*40,'status':'errored' if len(polls)==1 else 'built'}
    monkeypatch.setattr(module,'git',fake_git); monkeypatch.setattr(module,'api',fake_api)
    monkeypatch.setattr(module,'verify_live',lambda *args,**kwargs:{'verified_files':5})
    result=publish(tmp_path,pause=lambda _:None)
    assert not result['changed'] and result['pages_build_requested']
    assert ('pages/builds','POST') in requests
    assert not any(args[0] in ('push','add','commit') for args in calls)


@pytest.mark.parametrize('source_changed,schedule_outage,outcomes_changed',[(False,False,True),(False,True,True),(True,True,True),(False,False,False)])
@pytest.mark.parametrize('new_observations',[False,True])
def test_score_only_prepare_never_runs_inference_and_selects_build_correctly(tmp_path,monkeypatch,source_changed,schedule_outage,outcomes_changed,new_observations):
    import json
    from contextlib import nullcontext
    from urllib.error import URLError
    from scripts import automated_refresh as runner
    from ml import result_source,results,lifecycle
    snapshot,previous,state,revision=inputs()
    if source_changed:state['source_commit']='c'*40
    directory=tmp_path/'web/public/data/operations';directory.mkdir(parents=True)
    operations={'games':[],'schedule':[]}
    (directory/'latest.json').write_text(json.dumps({'file':'fixture.json'}))
    (directory/'fixture.json').write_text(json.dumps(operations))
    monkeypatch.setattr(runner,'ROOT',tmp_path)
    monkeypatch.setattr(runner,'hydrate',lambda *_:(previous,state,{}))
    monkeypatch.setattr(runner.subprocess,'check_output',lambda *a,**kw:revision)
    monkeypatch.setattr(runner,'refresh_lock',nullcontext)
    def acquire(*_):
        if schedule_outage:raise URLError('synthetic outage')
        return 'fixture'
    monkeypatch.setattr(runner,'acquire_bounded',acquire)
    monkeypatch.setattr(runner,'load_snapshot',lambda *_:snapshot)
    monkeypatch.setattr(runner,'refresh_reasons',lambda *_:[])
    def forbidden(*_):raise AssertionError('Inference must not run on a score-only check')
    monkeypatch.setattr(runner,'refresh',forbidden)
    # Reinterpreting retained evidence must publish even when duplicate
    # suppression correctly reports no newly downloaded observation.
    monkeypatch.setattr(result_source,'collect',lambda *_:{'changed':new_observations})
    monkeypatch.setattr(result_source,'load_observations',lambda *_:[])
    monkeypatch.setattr(results,'reconcile',lambda *_:{**operations,'verified_outcome':'synthetic'} if outcomes_changed else operations)
    published=[];monkeypatch.setattr(lifecycle,'publish_operations',lambda value:published.append(value))
    monkeypatch.setattr(runner.forecast_state,'save',lambda *_:{'sha256':'d'*64})
    decision=runner.prepare('disposable')
    assert decision['changed']==(outcomes_changed or source_changed)
    assert decision['data_only']==(outcomes_changed and not source_changed)
    assert decision['reasons']==(['verified_outcome_changed'] if outcomes_changed else [])
    assert len(published)==int(outcomes_changed)


def test_score_only_stage_keeps_compiled_assets_and_forecast_bytes(tmp_path,monkeypatch):
    import json
    from ml.current_source import canonical
    from scripts import automated_refresh as runner
    source=tmp_path/'source';portfolio=tmp_path/'portfolio';portfolio.mkdir()
    directory=source/'web/public/data/operations';directory.mkdir(parents=True)
    (directory/'latest.json').write_bytes(b'new operations pointer')
    (directory/'operations-new.json').write_bytes(b'new verified outcome')
    ops=source/'ops';ops.mkdir()
    for kind in ('forecast','result'):
        for suffix in ('json','zip'):(ops/f'{kind}-evidence-2026.{suffix}').write_bytes(b'checked evidence')
    old={'assets/app.js':b'unchanged compiled application','data/game-day.json':b'old hint',
         'data/current/latest.json':canonical({'file':'forecast-old.json','sha256':'a'*64,'generated_at':'2026-09-05T13:00:00Z'}),
         'data/current/forecast-old.json':canonical({'games':[{'status':'available','kickoff':'2026-09-06T17:00:00Z'}]}),
         'data/operations/operations-old.json':b'original outcome evidence'}
    monkeypatch.setattr(runner,'ROOT',source)
    monkeypatch.setattr(runner,'read_release',lambda _: (old,{'source_commit':'b'*40}))
    def plan(*args,**kwargs):(source/'web/public/data/game-day.json').write_bytes(b'new bounded hint')
    monkeypatch.setattr(runner.subprocess,'run',plan)
    packed={}
    def pack(*args,**kwargs):
        packed.update({p.relative_to(source/'web/dist').as_posix():p.read_bytes() for p in (source/'web/dist').rglob('*') if p.is_file()})
        return {'source_commit':'b'*40,'sha256':'c'*64}
    monkeypatch.setattr(runner.portfolio_artifact,'pack',pack)
    monkeypatch.setattr(runner.portfolio_artifact,'read_archive',lambda *_:(packed,{}))
    monkeypatch.setattr(runner.portfolio_artifact,'install',lambda *_:None)
    def forbidden(*_):raise AssertionError('An unchanged archived forecast has no new publication deadline')
    monkeypatch.setattr(runner,'publication_deadline',forbidden)
    decision={'changed':True,'data_only':True,'source_commit':'b'*40,'season':2026,
        'evidence':{'sha256':'d'*64,'result_evidence':{'sha256':'e'*64}}}
    result=runner.stage(portfolio,decision,'fixture.tar.gz')
    for name,body in old.items():
        if name!='data/game-day.json':assert packed[name]==body
    assert packed['data/game-day.json']==b'new bounded hint'
    assert packed['data/operations/operations-new.json']==b'new verified outcome'
    assert result['state']['result_evidence_sha256']=='e'*64
    assert (portfolio/'.fourth-down-state/result-evidence-2026.zip').exists()
    with pytest.raises(ValueError,match='frontend build'):
        runner.stage(portfolio,{**decision,'source_commit':'f'*40},'fixture.tar.gz')
