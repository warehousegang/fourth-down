"""Synthetic result fixtures; never publish these outcomes or fit a model."""
import copy
import io
import json
from datetime import timedelta
from urllib.error import URLError

import numpy as np
import pytest
rdata = pytest.importorskip('rdata', reason='Outcome-reader checks require requirements-results.txt')

from ml.current_source import EASTERN, canonical, sha, timestamp
from ml import result_source
from ml.results import reconcile
from test_lifecycle import snapshot, forecast, operation, BEFORE, AFTER


def detail(game, phase='FINAL', home=24, away=17):
    return {'id':np.array(['synthetic-event']), 'homeTeam':{'abbreviation':np.array([game['home']])},
            'visitorTeam':{'abbreviation':np.array([game['away']])},
            'startTime':np.array([timestamp(game['kickoff']).astimezone(EASTERN).strftime('%m/%d/%y, %H:%M:%S')]),
            'phase':np.array([phase]),'homePointsTotal':np.array([home]),'visitorPointsTotal':np.array([away])}


def raw_fixture(tmp_path, game, **kwargs):
    path=tmp_path/'synthetic.rds'
    rdata.write_rds(path,{'data':{'viewer':{'gameDetail':detail(game,**kwargs)}}})
    return path.read_bytes()


def provider(raw, game, updated=AFTER):
    asset={'name':result_source.provider_id(game)+'.rds','browser_download_url':result_source.source_url(game),
           'size':len(raw),'digest':'sha256:'+sha(raw),'updated_at':updated}
    calls=[]
    def fetch(url,maximum):
        calls.append(url)
        if url.startswith('https://api.github.com/'):
            return canonical({'tag_name':'raw_pbp_2026','assets':[asset]})
        assert url==result_source.source_url(game)
        return raw
    return fetch,calls


def base():
    s=snapshot();f=forecast(s)
    return operation([f],[s],generated=AFTER)


def observation(tmp_path, operations, **kwargs):
    game=operations['schedule'][0]
    raw=raw_fixture(tmp_path,game,**kwargs)
    fetch,calls=provider(raw,game)
    result_source.collect([game],2026,root=tmp_path,fetch=fetch,now=timestamp(AFTER))
    return result_source.load_observations(2026,tmp_path,AFTER),raw,calls


def test_real_format_roundtrip_and_duplicate_check_preserve_first_observation(tmp_path):
    ops=base(); observations,raw,calls=observation(tmp_path,ops)
    assert observations[0]['game']['status']=='completed'
    assert observations[0]['game']['home_score']==24
    before={p.name:p.read_bytes() for p in (tmp_path/'data/results/2026').iterdir()}
    fetch,calls=provider(raw,ops['schedule'][0])
    receipt=result_source.collect(ops['schedule'],2026,root=tmp_path,fetch=fetch,now=timestamp(AFTER)+timedelta(minutes=15))
    assert receipt=={'changed':False,'captured':0,'missing':[],'requests':1}
    assert len(calls)==1
    assert before=={p.name:p.read_bytes() for p in (tmp_path/'data/results/2026').iterdir()}


def test_final_scores_existing_designation_without_modifying_forecast(tmp_path):
    ops=base(); original=canonical(ops)
    captures,_,_=observation(tmp_path,ops)
    result=reconcile(ops,captures,AFTER)
    assert canonical(ops)==original
    assert result['catalog']==ops['catalog']
    assert result['games'][0]['final_forecast_id']==ops['games'][0]['final_forecast_id']
    assert result['metrics']['primary']['count']==1
    assert result['games'][0]['result']['source_url']==captures[0]['source_url']
    assert reconcile(result,captures,'2026-09-14T04:00:00Z')==result


@pytest.mark.parametrize('phase',['FINAL','FINAL_OVERTIME'])
def test_correction_is_new_evidence_and_changes_score_once(tmp_path,phase):
    ops=base(); captures,raw,_=observation(tmp_path,ops,phase=phase)
    first=reconcile(ops,captures,AFTER)
    game=ops['schedule'][0]
    corrected=raw_fixture(tmp_path,game,phase=phase,home=17,away=24)
    fetch,_=provider(corrected,game,'2026-09-14T04:00:00Z')
    result_source.collect([game],2026,root=tmp_path,fetch=fetch,now=timestamp('2026-09-14T04:01:00Z'))
    all_captures=result_source.load_observations(2026,tmp_path,'2026-09-14T04:01:00Z')
    assert len(all_captures)==2
    assert (tmp_path/f'data/results/2026/raw-{sha(raw)}.rds').read_bytes()==raw
    latest=reconcile(first,all_captures,'2026-09-14T04:01:00Z')
    assert latest['metrics']['primary']['count']==1
    assert latest['games'][0]['evaluations'][0]['correct']!=first['games'][0]['evaluations'][0]['correct']
    assert latest['games'][0]['final_forecast_id']==first['games'][0]['final_forecast_id']
    assert latest['catalog']==first['catalog']


@pytest.mark.parametrize('phase,status',[('IN_PROGRESS','in_progress'),('OVERTIME','in_progress'),('FINAL_UNKNOWN','unknown'),('POSTPONED','postponed'),('CANCELED','canceled')])
def test_nonfinal_observations_are_never_scored(tmp_path,phase,status):
    ops=base();captures,_,_=observation(tmp_path,ops,phase=phase)
    result=reconcile(ops,captures,AFTER)
    assert result['games'][0]['status']==(ops['games'][0]['status'] if status=='unknown' else status)
    assert result['games'][0]['result'] is None
    assert not result['games'][0]['evaluations']
    assert result['metrics']['primary']['count']==0
    assert result['catalog']==ops['catalog']


def test_tie_is_preserved_and_excluded(tmp_path):
    ops=base(); captures,_,_=observation(tmp_path,ops,home=24,away=24)
    result=reconcile(ops,captures,AFTER)
    assert result['games'][0]['result']['tie']
    assert result['metrics']['primary']['count']==0
    assert result['metrics']['primary']['ties_excluded']==1
    assert result['metrics']['primary']['accuracy'] is None


def test_missing_publication_and_outage_leave_original_outcomes_intact(tmp_path):
    ops=base()
    missing=lambda *args,**kwargs:canonical({'tag_name':'raw_pbp_2026','assets':[]})
    receipt=result_source.collect(ops['schedule'],2026,root=tmp_path,fetch=missing,now=timestamp(AFTER))
    assert not receipt['changed'] and receipt['missing']==[ops['games'][0]['id']]
    assert reconcile(ops,[],AFTER)==ops
    captures,_,_=observation(tmp_path,ops)
    saved=reconcile(ops,captures,AFTER)
    def outage(*args,**kwargs):raise URLError('synthetic outage')
    with pytest.raises(URLError):result_source.collect(ops['schedule'],2026,root=tmp_path,fetch=outage,now=timestamp(AFTER))
    assert reconcile(saved,result_source.load_observations(2026,tmp_path,AFTER),AFTER)==saved


@pytest.mark.parametrize('change',[{'home':'KC'},{'away':'BUF'},{'kickoff':'2026-09-14T17:00:00Z'}])
def test_ambiguous_or_rescheduled_match_fails_closed(tmp_path,change):
    ops=base();g=ops['schedule'][0];raw=raw_fixture(tmp_path,g)
    with pytest.raises(ValueError):result_source.normalize(raw,{**g,**change},AFTER)


@pytest.mark.parametrize('season',[2024,2025])
def test_protected_seasons_rejected_before_any_network(season,tmp_path):
    def forbidden(*args,**kwargs):raise AssertionError('Network must not run')
    with pytest.raises(ValueError,match='Protected'):
        result_source.collect([],season,root=tmp_path,fetch=forbidden,now=timestamp(AFTER))


def test_no_pregame_result_request_or_unverified_final(tmp_path):
    g=base()['schedule'][0]
    def forbidden(*args,**kwargs):raise AssertionError('No request before kickoff')
    assert result_source.collect([g],2026,root=tmp_path,fetch=forbidden,now=timestamp(BEFORE))['requests']==0
    with pytest.raises(ValueError):result_source.normalize(raw_fixture(tmp_path,g),g,BEFORE)
    invalid=detail(g);invalid['homePointsTotal']=np.array([True])
    with pytest.raises(ValueError,match='score'):result_source.normalize_detail(invalid,g,AFTER)


def test_checksum_and_future_publication_rejected(tmp_path):
    ops=base();g=ops['schedule'][0];raw=raw_fixture(tmp_path,g)
    fetch,_=provider(raw,g,'2026-09-15T00:00:00Z')
    with pytest.raises(ValueError,match='provenance'):
        result_source.collect([g],2026,root=tmp_path,fetch=fetch,now=timestamp(AFTER))
    assert not list((tmp_path/'data/results/2026').glob('*'))


def test_result_asset_request_budget_is_bounded(tmp_path):
    assert result_source.MAX_RAW==2_000_000
    assert result_source.MAX_EXPANDED==5_000_000
    with pytest.raises(ValueError,match='oversized'):
        result_source.normalize(b'x'*(result_source.MAX_RAW+1),base()['schedule'][0],AFTER)


def test_newer_schedule_without_scores_cannot_erase_verified_final(tmp_path):
    ops=base(); captures,_,_=observation(tmp_path,ops)
    ops['source']['source_updated_at']='2026-09-14T04:00:00Z'
    result=reconcile(ops,captures,'2026-09-14T04:01:00Z')
    assert result['games'][0]['result']['home_score']==24
    assert result['metrics']['primary']['count']==1


def test_newer_verified_primary_correction_takes_precedence(tmp_path):
    ops=base();captures,_,_=observation(tmp_path,ops)
    ops['source']['source_updated_at']='2026-09-14T04:00:00Z'
    ops['games'][0]['result']={'home_score':17,'away_score':24,'provider':'ngs'}
    assert reconcile(ops,captures,'2026-09-14T04:01:00Z')==ops


@pytest.mark.parametrize('legacy_overtime',[False,True,'terminal'])
def test_outcome_bundle_roundtrip_and_tampering_rejected(tmp_path,legacy_overtime):
    from unittest.mock import patch
    from ml import current_source
    from ml.rc1_operations import synthetic_source
    from ml.refresh import refresh
    from ml.lifecycle import publish_operations
    from scripts.forecast_state import checked_pair,save,restore
    from ml.evidence_bundle import collect_payload,validate_payload
    working=tmp_path/'working'
    source,_=synthetic_source(working)
    with patch.object(current_source,'ROOT',working):
        refresh(source,now=timestamp('2026-09-05T13:00:00Z'),
            current_directory=working/'web/public/data/current',operations_directory=working/'web/public/data/operations')
    directory=working/'web/public/data/operations'
    ops=json.loads((directory/json.loads((directory/'latest.json').read_bytes())['file']).read_bytes())
    game=ops['schedule'][0]
    if legacy_overtime == 'terminal':
        from test_terminal_result import terminal_detail
        import pandas as pd
        value=terminal_detail(game)
        for frame in (value['plays'],value['drives']):
            for column in frame.columns:
                if pd.api.types.is_string_dtype(frame[column]):
                    frame[column]=frame[column].astype(pd.StringDtype(storage='python'))
        path=tmp_path/'terminal.rds';rdata.write_rds(path,{'data':{'viewer':{'gameDetail':value}}});raw=path.read_bytes()
    else:
        raw=raw_fixture(tmp_path,game,phase='FINAL_OVERTIME' if legacy_overtime else 'FINAL')
    fetch,_=provider(raw,game)
    result_source.collect([game],2026,root=working,fetch=fetch,now=timestamp(AFTER))
    if legacy_overtime:
        # Construct the exact receipt written by the old parser, then restore it
        # unchanged before deriving the new operations version.
        path=next((working/'data/results/2026').glob('observation-*.json'))
        legacy=json.loads(path.read_bytes());legacy['game'].update(validated=False,status='unknown')
        path.unlink();body=canonical(legacy)
        (path.parent/f'observation-{sha(body)}.json').write_bytes(body)
        forecast_state_receipt=save(2026,working,timestamp(AFTER))
        assert forecast_state_receipt['result_evidence']['files']>0
    result=reconcile(ops,result_source.load_observations(2026,working,AFTER),AFTER)
    publish_operations(result,directory)
    checked_pair(working,2026)
    receipt=save(2026,working,timestamp(AFTER))
    fresh=tmp_path/'fresh';(fresh/'ops').mkdir(parents=True)
    for p in (working/'ops').iterdir():(fresh/'ops'/p.name).write_bytes(p.read_bytes())
    assert restore(2026,fresh)['restored']==receipt['files']
    assert not list((fresh/'data/results').glob('**/*'))
    assert restore(2026,fresh,kind='result')['restored']>0
    assert len(result_source.load_observations(2026,fresh,AFTER))==1
    if legacy_overtime:
        restored=result_source.load_observations(2026,fresh,AFTER)[0]
        assert restored==legacy
        assert reconcile(result,[restored],AFTER)==result
    payload=collect_payload(2026,working)
    bad=copy.deepcopy(result);bad['games'][0]['result']['home_score']=99
    body=canonical(bad);payload[f'web/public/data/operations/operations-{sha(body)}.json']=body
    with pytest.raises(ValueError,match='differs from retained evidence'):
        validate_payload(payload,2026,AFTER)


def test_conflicting_publication_versions_rejected(tmp_path):
    ops=base();captures,_,_=observation(tmp_path,ops)
    bad=copy.deepcopy(captures[0]);bad['game']['home_score']=99
    with pytest.raises(ValueError,match='Conflicting result versions'):
        reconcile(ops,[*captures,bad],AFTER)


def test_delayed_actual_kickoff_on_same_date_matches_the_exact_event():
    game=base()['schedule'][0];value=detail(game)
    delayed=timestamp(game['kickoff'])+timedelta(hours=2)
    value['startTime']=np.array([delayed.astimezone(EASTERN).strftime('%m/%d/%y, %H:%M:%S')])
    assert result_source.normalize_detail(value,game,AFTER)['status']=='completed'


def test_bootstrap_downloads_at_most_sixteen_changed_game_files(tmp_path):
    original=base()['schedule'][0];games=[];bodies={};assets=[]
    for week in range(1,18):
        game={**original,'id':f'ngs-2026-{week}','week':week};games.append(game)
        raw=raw_fixture(tmp_path,game)
        url=result_source.source_url(game);bodies[url]=raw
        assets.append({'name':result_source.provider_id(game)+'.rds','browser_download_url':url,
            'size':len(raw),'digest':'sha256:'+sha(raw),'updated_at':AFTER})
    calls=[]
    def fetch(url,maximum):
        calls.append(url)
        return canonical({'tag_name':'raw_pbp_2026','assets':assets}) if 'api.github.com' in url else bodies[url]
    receipt=result_source.collect(games,2026,root=tmp_path,fetch=fetch,now=timestamp(AFTER))
    assert receipt['captured']==16 and receipt['requests']==len(calls)==17
    assert len(receipt['missing'])==1
    receipt=result_source.collect(games,2026,root=tmp_path,fetch=fetch,now=timestamp(AFTER))
    assert receipt['captured']==1 and receipt['requests']==2
