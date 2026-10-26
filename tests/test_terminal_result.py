"""The real Week 7 stale header and synthetic, explicitly terminal game logs."""
import copy
import gzip
import json
import math
from pathlib import Path

import numpy as np
import pandas as pd
import pytest
rdata = pytest.importorskip('rdata')
from ml import result_source
from ml.current_source import canonical, sha, timestamp
from ml.results import reconcile
from test_results import base, detail, provider

FIXTURES = Path(__file__).parent/'fixtures/results'
NOW = '2026-10-26T00:25:00+00:00'


def retained():
    return (json.loads((FIXTURES/'2026_07_DEN_ARI.legacy.json').read_bytes()),
            (FIXTURES/'2026_07_DEN_ARI.rds').read_bytes())


def terminal_detail(game, quarter=4, clock='00:00', home=24, away=17):
    value=detail(game,phase='INGAME',home=home,away=away)
    value['period']=np.array([quarter])
    value['playReview']=np.array([False])
    value['plays']=pd.DataFrame([{'playType':'END_GAME','playDescription':'END GAME',
        'playDeleted':False,'orderSequence':2,'playId':2,'quarter':quarter,'clockTime':clock}])
    value['drives']=pd.DataFrame([{'endTransition':'END_GAME','playIdEnded':2,
        'playSeqEnded':2,'quarterEnd':quarter,'gameClockEnd':clock}])
    value['scoringSummaries']=pd.DataFrame([{'homeScore':home,'visitorScore':away}])
    return value


def test_actual_stale_header_has_explicit_terminal_evidence():
    observation,raw=retained();body=canonical(observation)
    assert sha(raw)=='a83eec0c2beb8aebda46dd2e5b35a6f736fdf64d8a979ea59346e50ea32f6480'
    value=rdata.conversion.convert(rdata.parser.parse_data(gzip.decompress(raw),extension='.rds'))['data']['viewer']['gameDetail']
    assert value['phase'][0]=='INGAME' and value['gameClock'][0]=='00:36'
    assert value['plays'].iloc[-1]['playType']=='END_GAME'
    verified=result_source.validate_observation(observation,raw,2026,NOW)
    game=result_source.effective_game(verified)
    assert game['phase']=='INGAME' and game['status']=='completed' and game['validated']
    assert (game['away_score'],game['home_score'])==(30,16)
    assert canonical(verified)==body and observation==verified
    # Serializing never turns a legacy observation into a rewritten receipt.
    assert json.loads(canonical(verified))['game']['status']=='unknown'
    assert result_source.effective_game(observation)['status']=='unknown'


@pytest.mark.parametrize('quarter,clock',[(4,'00:00'),(5,'07:25'),(5,'00:00')])
def test_explicit_terminal_play_and_drive_support_regulation_and_overtime(quarter,clock):
    game=base()['schedule'][0]
    value=terminal_detail(game,quarter,clock)
    parsed=result_source.normalize_detail(value,game,'2026-09-14T04:00:00Z')
    assert parsed['status']=='completed' and parsed['validated']


@pytest.mark.parametrize('mutation',[
    'no_plays','no_drives','no_summary','end_quarter','not_last','deleted',
    'mismatched_drive','mismatched_sequence','mismatched_quarter','mismatched_clock',
    'nonzero_regulation_clock','bad_summary','early_quarter','canceled','duplicate_sequence','pending_review','regulation_tie',
])
def test_incomplete_or_conflicting_evidence_never_becomes_a_final(mutation):
    game=base()['schedule'][0];value=terminal_detail(game)
    if mutation=='no_plays':value.pop('plays')
    if mutation=='no_drives':value.pop('drives')
    if mutation=='no_summary':value.pop('scoringSummaries')
    if mutation=='end_quarter':value['plays'].loc[0,'playType']='END_QUARTER'
    if mutation=='not_last':value['plays']=pd.concat([value['plays'],value['plays'].assign(playType='RUSH',orderSequence=3)],ignore_index=True)
    if mutation=='deleted':value['plays'].loc[0,'playDeleted']=True
    if mutation=='mismatched_drive':value['drives'].loc[0,'playIdEnded']=99
    if mutation=='mismatched_sequence':value['drives'].loc[0,'playSeqEnded']=99
    if mutation=='mismatched_quarter':value['drives'].loc[0,'quarterEnd']=3
    if mutation=='mismatched_clock':value['drives'].loc[0,'gameClockEnd']='00:01'
    if mutation=='nonzero_regulation_clock':value=terminal_detail(game,clock='00:36')
    if mutation=='bad_summary':value['scoringSummaries'].loc[0,'homeScore']=25
    if mutation=='early_quarter':value=terminal_detail(game,quarter=3)
    if mutation=='canceled':value['phase']=np.array(['CANCELED'])
    if mutation=='pending_review':value['playReview']=np.array([True])
    if mutation=='regulation_tie':value=terminal_detail(game,home=17,away=17)
    if mutation=='duplicate_sequence':value['plays']=pd.concat([value['plays'],value['plays']],ignore_index=True)
    parsed=result_source.normalize_detail(value,game,'2026-09-14T04:00:00Z')
    assert parsed['status']!='completed' and not parsed['validated']


def test_legacy_evidence_reconciles_once_and_preserves_original_forecast(tmp_path):
    obs,raw=retained();game=obs['game'];directory=tmp_path/'data/results/2026';directory.mkdir(parents=True)
    body=canonical(obs);(directory/f'observation-{sha(body)}.json').write_bytes(body)
    (directory/f'raw-{sha(raw)}.rds').write_bytes(raw)
    before={p.name:p.read_bytes() for p in directory.iterdir()}
    fetch,calls=provider(raw,game,obs['source_updated_at'])
    assert result_source.collect([game],2026,root=tmp_path,fetch=fetch,now=timestamp(NOW))['captured']==0
    captures=result_source.load_observations(2026,tmp_path,NOW)
    ops=base();identity={k:game[k] for k in ('id','season','week','home','away','kickoff','day')}
    ops['schedule'][0].update(identity);ops['games'][0].update({k:v for k,v in identity.items() if k!='day'},status='unknown')
    forecast=ops['catalog'][0];forecast.update(game_id=game['id'],home='ARI',away='DEN',home_probability=.41,away_probability=.59)
    original=canonical(ops);result=reconcile(ops,captures,NOW);row=result['games'][0]
    assert (row['result']['away_score'],row['result']['home_score'])==(30,16)
    assert row['result']['observed_at']==obs['observed_at'] and row['result']['snapshot_sha256']==sha(body)
    score=next(e for e in row['evaluations'] if e['primary'])
    assert score['correct'] and score['brier']==pytest.approx(.41**2)
    assert score['log_loss']==pytest.approx(-math.log(.59))
    assert result['catalog']==ops['catalog'] and canonical(ops)==original
    assert result['metrics']['primary']['count']==1
    assert reconcile(result,captures,'2026-10-26T00:26:00Z')==result
    assert before=={p.name:p.read_bytes() for p in directory.iterdir()}


@pytest.mark.parametrize('change',[{'away_score':31},{'validated':True},{'status':'completed'}])
def test_legacy_receipt_tampering_is_rejected(change):
    obs,raw=retained();obs['game'].update(change)
    with pytest.raises(ValueError,match='does not reproduce'):
        result_source.validate_observation(obs,raw,2026,NOW)


def test_delayed_terminal_observation_after_incomplete_file_is_applied_once(tmp_path):
    game=base()['schedule'][0];value=terminal_detail(game);file=tmp_path/'synthetic.rds'
    incomplete=copy.deepcopy(value);incomplete['plays'].loc[0,'playType']='RUSH'
    for i,detail_value in enumerate((incomplete,value)):
        for frame in (detail_value['plays'],detail_value['drives']):
            for column in frame.columns:
                if pd.api.types.is_string_dtype(frame[column]):
                    frame[column]=frame[column].astype(pd.StringDtype(storage='python'))
        rdata.write_rds(file,{'data':{'viewer':{'gameDetail':detail_value}}});raw=file.read_bytes()
        time=f'2026-09-14T04:{i:02}:00Z';fetch,_=provider(raw,game,time)
        assert result_source.collect([game],2026,root=tmp_path,fetch=fetch,now=timestamp(time))['captured']==1
        ops=reconcile(base(),result_source.load_observations(2026,tmp_path,time),time)
        assert ops['metrics']['primary']['count']==i
    assert len(result_source.load_observations(2026,tmp_path,time))==2
    assert result_source.collect([game],2026,root=tmp_path,fetch=fetch,now=timestamp(time))['captured']==0


def test_changed_validated_receipt_cannot_reuse_its_interpretation():
    observation,raw=retained();verified=result_source.validate_observation(observation,raw,2026,NOW)
    verified['game']['away_score']=31
    with pytest.raises(ValueError,match='modified'):
        result_source.effective_game(verified)


def test_terminal_score_correction_replaces_one_game_without_replacing_forecasts(tmp_path):
    game=base()['schedule'][0];ops=base();catalog=copy.deepcopy(ops['catalog'])
    for i,(home,away) in enumerate([(24,17),(17,24)]):
        value=terminal_detail(game,home=home,away=away)
        for frame in (value['plays'],value['drives']):
            for column in frame.columns:
                if pd.api.types.is_string_dtype(frame[column]):
                    frame[column]=frame[column].astype(pd.StringDtype(storage='python'))
        path=tmp_path/'synthetic.rds';rdata.write_rds(path,{'data':{'viewer':{'gameDetail':value}}})
        time=f'2026-09-14T04:{i:02}:00Z';fetch,_=provider(path.read_bytes(),game,time)
        result_source.collect([game],2026,root=tmp_path,fetch=fetch,now=timestamp(time))
        captures=result_source.load_observations(2026,tmp_path,time)
        ops=reconcile(ops,captures,time)
        assert ops['catalog']==catalog and ops['metrics']['primary']['count']==1
        assert ops['games'][0]['result']['home_score']==home
    assert len(captures)==2
    assert reconcile(ops,captures,time)==ops
