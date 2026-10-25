"""Regression for the retained 2026 NYG–HOU overtime provider observation."""
import copy
import json
import math
from pathlib import Path

import pytest
pytest.importorskip('rdata')

from ml import result_source
from ml.current_source import canonical, sha, timestamp
from ml.results import reconcile
from test_results import base, detail, provider

FIXTURES = Path(__file__).parent/'fixtures/results'
NOW = '2026-10-25T21:24:51+00:00'


def retained():
    return (json.loads((FIXTURES/'2026_07_NYG_HOU.legacy.json').read_bytes()),
            (FIXTURES/'2026_07_NYG_HOU.rds').read_bytes())


def test_actual_overtime_header_and_legacy_receipt_reproduce():
    observation, raw = retained()
    before = canonical(observation)
    assert sha(raw) == '78afae9d13511b1ba4b3cbb8fdf26afb29281f88b7d5d114efba85a02521089d'
    parsed = result_source.normalize(raw, observation['game'], observation['observed_at'])
    assert parsed['phase'] == 'FINAL_OVERTIME'
    assert parsed['status'] == 'completed' and parsed['validated']
    assert (parsed['away'],parsed['away_score'],parsed['home'],parsed['home_score']) == ('NYG',27,'HOU',21)
    assert result_source.validate_observation(observation,raw,2026,NOW) == observation
    assert result_source.effective_game(observation) == parsed
    assert canonical(observation) == before


def test_cached_overtime_final_recovers_once_without_rewriting_evidence(tmp_path):
    observation, raw = retained()
    directory = tmp_path/'data/results/2026'; directory.mkdir(parents=True)
    body = canonical(observation)
    (directory/f'observation-{sha(body)}.json').write_bytes(body)
    (directory/f'raw-{sha(raw)}.rds').write_bytes(raw)
    before = {p.name:p.read_bytes() for p in directory.iterdir()}
    game = observation['game']
    fetch,calls = provider(raw,game,observation['source_updated_at'])
    receipt = result_source.collect([game],2026,root=tmp_path,fetch=fetch,now=timestamp(NOW))
    assert receipt == {'changed':False,'captured':0,'missing':[],'requests':1}
    assert len(calls) == 1
    captures = result_source.load_observations(2026,tmp_path,NOW)
    # A synthetic ledger scaffold isolates reconciliation. Production replay is
    # performed separately against the complete retained, hash-verified ledger.
    ops = base()
    identity = {k:game[k] for k in ('id','season','week','home','away','kickoff','day')}
    ops['schedule'][0].update(identity)
    ops['games'][0].update({k:v for k,v in identity.items() if k!='day'},status='unknown')
    forecast = ops['catalog'][0]
    forecast.update(game_id=game['id'],home='HOU',away='NYG',home_probability=.5571244457483405,
                    away_probability=.4428755542516595,generated_at='2026-10-25T00:22:38.161263+00:00')
    original = canonical(ops)
    result = reconcile(ops,captures,NOW)
    row = result['games'][0]
    assert row['result']['away_score']==27 and row['result']['home_score']==21
    assert row['result']['snapshot_sha256']==sha(body)
    assert row['result']['observed_at']==observation['observed_at']
    score = next(e for e in row['evaluations'] if e['primary'])
    assert not score['correct'] and score['outcome_home']==0
    assert score['brier']==pytest.approx(.5571244457483405**2)
    assert score['log_loss']==pytest.approx(-math.log(.4428755542516595))
    assert result['catalog']==ops['catalog'] and canonical(ops)==original
    assert result['generated_at']==NOW
    assert result['metrics']['primary']['count']==1
    assert reconcile(result,captures,'2026-10-25T22:00:00Z')==result
    assert before=={p.name:p.read_bytes() for p in directory.iterdir()}


def test_delayed_overtime_publication_is_collected_and_scored_once(tmp_path):
    observation,raw = retained();game=observation['game']
    missing=lambda *a,**kw:canonical({'tag_name':'raw_pbp_2026','assets':[]})
    first=result_source.collect([game],2026,root=tmp_path,fetch=missing,now=timestamp('2026-10-25T20:17:00Z'))
    assert first['missing']==[game['id']] and first['captured']==0
    fetch,_=provider(raw,game,observation['source_updated_at'])
    second=result_source.collect([game],2026,root=tmp_path,fetch=fetch,now=timestamp(NOW))
    assert second['captured']==1
    assert result_source.load_observations(2026,tmp_path,NOW)[0]['game']['status']=='completed'
    assert result_source.collect([game],2026,root=tmp_path,fetch=fetch,now=timestamp(NOW))['captured']==0


@pytest.mark.parametrize('change',[{'away_score':28},{'validated':True},{'status':'completed'}])
def test_legacy_compatibility_does_not_accept_changed_receipt_fields(change):
    observation,raw=retained();observation['game'].update(change)
    with pytest.raises(ValueError,match='does not reproduce'):
        result_source.validate_observation(observation,raw,2026,NOW)


def test_overtime_final_requires_scores_and_publication_after_actual_start():
    observation,raw=retained();observation['source_updated_at']='2026-10-25T17:00:00Z'
    with pytest.raises(ValueError,match='publication must follow'):
        result_source.validate_observation(observation,raw,2026,NOW)
    game=observation['game'];value=detail(game,phase='FINAL_OVERTIME');value['homePointsTotal']=None
    with pytest.raises(ValueError,match='valid scores'):
        result_source.normalize_detail(value,game,NOW)
