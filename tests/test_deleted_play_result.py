"""A real final rejected because deleted provider plays repeat sequence zero."""
import copy
import gzip
import json
import math
from pathlib import Path

import pandas as pd
import pytest
rdata = pytest.importorskip('rdata')
from ml import result_source
from ml.current_source import canonical, sha, timestamp
from ml.results import reconcile
from test_results import base, provider
from test_terminal_result import terminal_detail

FIXTURES = Path(__file__).parent/'fixtures/results'
NOW = '2026-11-09T04:43:12+00:00'


def retained():
    return (json.loads((FIXTURES/'2026_09_GB_NE.legacy.json').read_bytes()),
            (FIXTURES/'2026_09_GB_NE.rds').read_bytes())


def test_actual_final_ignores_deleted_sequence_placeholders():
    observation, raw = retained()
    assert sha(raw) == '2cd407019b15fb5a1467740527a396fa2901ee137e24dd7097d2cadf2170bd2c'
    detail = rdata.conversion.convert(rdata.parser.parse_data(gzip.decompress(raw), extension='.rds'))['data']['viewer']['gameDetail']
    assert detail['plays'].iloc[:2]['orderSequence'].tolist() == [0, 0]
    assert detail['plays'].iloc[:2]['playDeleted'].tolist() == [True, True]
    assert detail['phase'][0] == 'INGAME'
    verified = result_source.validate_observation(observation, raw, 2026, NOW)
    game = result_source.effective_game(verified)
    assert game['status'] == 'completed' and game['validated']
    assert (game['away_score'], game['home_score']) == (45, 27)
    assert canonical(verified) == canonical(observation)
    assert verified['game']['status'] == 'unknown'


@pytest.mark.parametrize('quarter,clock', [(4, '00:00'), (5, '07:25')])
@pytest.mark.parametrize('deleted', [True, False, None])
def test_only_explicitly_deleted_duplicate_rows_can_be_ignored(quarter, clock, deleted):
    game = base()['schedule'][0]
    detail = terminal_detail(game, quarter, clock)
    placeholder = detail['plays'].assign(orderSequence=0, playType='UNSPECIFIED', playDeleted=deleted)
    detail['plays'] = pd.concat([placeholder, placeholder, detail['plays']], ignore_index=True)
    parsed = result_source.normalize_detail(detail, game, '2026-09-14T04:00:00Z')
    assert (parsed['status'] == 'completed') is (deleted is True)


def test_retained_deleted_play_final_reconciles_once_without_rewriting_evidence(tmp_path):
    observation, raw = retained(); game = observation['game']
    directory = tmp_path/'data/results/2026'; directory.mkdir(parents=True)
    body = canonical(observation)
    (directory/f'observation-{sha(body)}.json').write_bytes(body)
    (directory/f"raw-{observation['raw_sha256']}.rds").write_bytes(raw)
    before = {p.name:p.read_bytes() for p in directory.iterdir()}
    fetch, _ = provider(raw, game, observation['source_updated_at'])
    assert result_source.collect([game], 2026, root=tmp_path, fetch=fetch, now=timestamp(NOW))['captured'] == 0
    observations = result_source.load_observations(2026, tmp_path, NOW)
    ops = base()
    identity = {k:game[k] for k in ('id','season','week','home','away','kickoff','day')}
    ops['schedule'][0].update(identity)
    ops['games'][0].update({k:v for k,v in identity.items() if k != 'day'}, status='unknown')
    ops['catalog'][0].update(game_id=game['id'],home='NE',away='GB',home_probability=.58,away_probability=.42)
    original = copy.deepcopy(ops)
    result = reconcile(ops, observations, NOW); row = result['games'][0]
    assert (row['result']['away_score'],row['result']['home_score']) == (45,27)
    assert row['result']['observed_at'] == observation['observed_at']
    assert row['result']['snapshot_sha256'] == sha(body)
    score = next(e for e in row['evaluations'] if e['primary'])
    assert score['correct'] is False
    assert score['brier'] == pytest.approx(.58**2)
    assert score['log_loss'] == pytest.approx(-math.log(.42))
    assert result['catalog'] == ops['catalog'] and ops == original
    assert result['metrics']['primary']['count'] == 1
    assert reconcile(result, observations, NOW) == result
    assert before == {p.name:p.read_bytes() for p in directory.iterdir()}
