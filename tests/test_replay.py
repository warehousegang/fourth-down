"""RC1 independent replay adversarial tests. No training or data acquisition."""
import copy
import csv
import io
import json
import urllib.request
from pathlib import Path

import pytest

from ml.replay import (FEATURES, ROOT, block_intervals, canonical, compare_saved, frozen_evidence,
                       parse_rows, read_approved_source, reconstruct, reliability, replay, scores,
                       verify_saved_challenger, write_evidence)


def source_fixture():
    return [
        dict(game_id='prior-season',season='2022',week='18',game_type='REG',gameday='2023-01-08',gametime='13:00',home_team='A',away_team='B',home_score='50',away_score='0'),
        dict(game_id='first',season='2023',week='1',game_type='REG',gameday='2023-09-07',gametime='13:00',home_team='A',away_team='B',home_score='20',away_score='10'),
        dict(game_id='same-day',season='2023',week='1',game_type='REG',gameday='2023-09-07',gametime='20:00',home_team='A',away_team='C',home_score='7',away_score='7'),
        dict(game_id='target',season='2023',week='2',game_type='REG',gameday='2023-09-14',gametime='13:00',home_team='B',away_team='A',home_score='35',away_score='7'),
        dict(game_id='later',season='2023',week='4',game_type='REG',gameday='2023-10-01',gametime='13:00',home_team='A',away_team='C',home_score='10',away_score='24')]


def raw(rows):
    stream=io.StringIO();writer=csv.DictWriter(stream,fieldnames=list(rows[0]));writer.writeheader();writer.writerows(rows)
    return stream.getvalue().encode()


def target(rows,identity):
    return next(row for row in rows if row['game_id']==identity)


def fake_saved(result):
    return {**{key:result[key] for key in ('id','season','week','home','away','model_id','cutoff','kickoff','factors','home_probability')},
            'status':'available','history_games':{side:len(result['history'][side]) for side in ('home','away')}}


def test_target_same_date_and_future_outcomes_cannot_change_features():
    model,_,_=frozen_evidence();fixture=source_fixture();before=parse_rows(raw(fixture))
    first=reconstruct(before,target(before,'same-day'),model)
    assert first['features']==dict.fromkeys(FEATURES,0)
    assert first['history']=={'home':[],'away':[]}
    for row in fixture:
        if row['gameday']>='2023-09-14':row['home_score'],row['away_score']='99','0'
    after=parse_rows(raw(fixture))
    original=reconstruct(before,target(before,'target'),model)
    altered=reconstruct(after,target(after,'target'),model)
    assert canonical(original)==canonical(altered)
    assert original['features']['smooth_win_diff']==pytest.approx((0+2)/(1+4)-(1.5+2)/(2+4))
    assert all(item['gameday']<original['gameday'] for history in original['history'].values() for item in history)
    assert original['historical_publication_availability_proven'] is False


def test_ties_missing_games_rest_cap_and_ordering_match_frozen_definition():
    model,_,_=frozen_evidence();fixture=source_fixture();rows=parse_rows(raw(fixture))
    result=reconstruct(rows,target(rows,'later'),model)
    assert result['factors'][-1]['home']==14 and result['factors'][-1]['away']==14
    fixture[1]['home_score']=''
    changed=parse_rows(raw(fixture));later=reconstruct(changed,target(changed,'target'),model)
    assert [r['id'] for r in later['history']['away']]==['same-day']
    assert later['factors'][0]['away']==.5  # a single tie plus symmetric fixed prior
    assert reconstruct(list(reversed(rows)),target(rows,'later'),model)==result


@pytest.mark.parametrize('season',['2024','2025','2026','2023.0'])
def test_locked_or_unsupported_season_rejected_before_score_parsing(season):
    rows=source_fixture();rows[-1]['season']=season;rows[-1]['home_score']='NEVER_PARSE_PROTECTED_SCORE'
    with pytest.raises(ValueError,match='Protected or unsupported'):
        parse_rows(raw(rows))


def test_direct_reconstruction_rejects_protected_rows():
    model,_,_=frozen_evidence();rows=parse_rows(raw(source_fixture()));rows[-1]['season']=2025
    with pytest.raises(ValueError,match='Protected or unsupported'):
        reconstruct(rows,rows[-2],model)


@pytest.mark.parametrize('change,match',[(('home_score','NaN'),'score'),(('home_score','-1'),'score'),
    (('week','0'),'week'),(('game_id','first'),'duplicate'),(('gameday','2026-10-01'),'Date'),(('away_team','A'),'team')])
def test_malformed_source_inputs_fail_closed(change,match):
    rows=source_fixture();rows[-1][change[0]]=change[1]
    with pytest.raises(ValueError,match=match):parse_rows(raw(rows))


def test_hash_mismatch_prevents_parsing_and_never_acquires_data(tmp_path,monkeypatch):
    source=tmp_path/'source.csv';source.write_bytes(b'protected bytes never parsed')
    manifest=tmp_path/'manifest.json';manifest.write_text(json.dumps({'sha256':'bad'}))
    def forbidden(*a,**k):raise AssertionError('No parsing/network after integrity failure')
    monkeypatch.setattr('ml.replay.parse_rows',forbidden);monkeypatch.setattr(urllib.request,'urlopen',forbidden)
    with pytest.raises(ValueError,match='checksum'):read_approved_source(source,manifest)


@pytest.mark.parametrize('mutation',[lambda x:x.update(home_probability=.99),lambda x:x.update(home_probability=float('nan')),
    lambda x:x['factors'][0].update(contribution=float('nan')),lambda x:x.update(kickoff='2023-09-15T13:00:00-04:00'),
    lambda x:x['history_games'].update(home=99)])
def test_saved_artifact_discrepancies_are_detected(mutation):
    model,_,_=frozen_evidence();rows=parse_rows(raw(source_fixture()));result=reconstruct(rows,target(rows,'target'),model)
    saved=copy.deepcopy(fake_saved(result));assert compare_saved(result,saved)==[]
    mutation(saved);assert compare_saved(result,saved)


def test_scoring_calibration_and_complete_week_bootstrap_are_reproducible():
    y,p=[0,1,1,0],[.2,.8,.7,.4]
    result=scores(y,p);assert result['accuracy']==1 and result['brier']==pytest.approx(.0825)
    bins=reliability(y,p);assert sum(b['count'] for b in bins)==4
    blocks=[(2023,1),(2023,1),(2023,2),(2023,2)]
    first=block_intervals(y,p,.55,blocks)
    assert first==block_intervals(y,p,.55,blocks)
    assert first['unit']=='season-week' and first['blocks']==[[2023,1],[2023,2]]
    assert first['replicates']==2000 and first['seed']==42
    assert first['intervals']['brier']['estimate']==result['brier']


def test_saved_challenger_arithmetic_and_split_checks_do_not_fit(monkeypatch):
    from sklearn.linear_model import LogisticRegression
    from sklearn.preprocessing import StandardScaler
    from sklearn.pipeline import Pipeline
    def forbidden(*a,**k):raise AssertionError('RC1 replay must never fit or acquire')
    for cls in (LogisticRegression,StandardScaler,Pipeline):monkeypatch.setattr(cls,'fit',forbidden)
    monkeypatch.setattr(urllib.request,'urlopen',forbidden)
    result=verify_saved_challenger()
    assert result['predictions_checked']==1576 and result['chronological_splits_verified']
    assert result['largest_probability_error']<1e-12
    assert result['prospective_or_untouched_test'] is False


def test_evidence_writer_is_local_content_addressed_and_preserves_versions(tmp_path,monkeypatch):
    monkeypatch.setattr('ml.replay.ROOT',tmp_path)
    first=write_evidence({'synthetic_test':True},'2026-10-24T14:00:00Z');contents=first.read_bytes()
    second=write_evidence({'synthetic_test':True},'2026-10-24T14:00:01Z')
    assert first.parent==tmp_path/'artifacts/rc1/replay' and first!=second and first.read_bytes()==contents
    assert not (tmp_path/'web').exists()


@pytest.mark.skipif(not (ROOT/'data/schedules-2010-2023.csv').is_file() or not (ROOT/'data/manifest.json').is_file(),
                    reason='Requires separately preserved approved local2010–2023 snapshot; RC1 never downloads historical data in CI')
def test_real_historical_replay_is_independent_read_only_and_repeatable(monkeypatch):
    import ml.features,ml.forecast
    from sklearn.linear_model import LogisticRegression
    from sklearn.preprocessing import StandardScaler
    from sklearn.pipeline import Pipeline
    def forbidden(*a,**k):raise AssertionError('Independent replay cannot reuse production scoring, fit, or fetch')
    for cls in (LogisticRegression,StandardScaler,Pipeline):monkeypatch.setattr(cls,'fit',forbidden)
    monkeypatch.setattr(ml.features,'build_features',forbidden);monkeypatch.setattr(ml.forecast,'score',forbidden)
    monkeypatch.setattr(urllib.request,'urlopen',forbidden)
    protected=[ROOT/'docs/FROZEN_MODEL.json',ROOT/'docs/MODEL_REGISTRY.json',ROOT/'web/public/data/demo.json']
    protected+=list((ROOT/'web/public/data').glob('*/latest.json'))
    before={path:path.read_bytes() for path in protected}
    first=replay();second=replay()
    assert canonical(first)==canonical(second)
    assert all(path.read_bytes()==body for path,body in before.items())
    assert first['metrics']['incumbent']=={'n':272,'accuracy':0.5882352941176471,'brier':0.23704473172141693,'log_loss':0.6657815064516025}
    assert first['boundaries']['evaluated_seasons']==[2023]
    assert not first['prospective'] and not first['historical_publication_availability_proven']
    assert first['verification']['discrepancies']==[]
