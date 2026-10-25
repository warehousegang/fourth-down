"""Shared Python/React policy vectors and synthetic stale-to-postgame lifecycle."""
import copy
import json
import math
from pathlib import Path

import pytest

from ml.current import generate
from ml.current_source import canonical, timestamp
from ml.freshness import select_display_forecast
from ml.lifecycle import build_operations
from test_lifecycle import snapshot, bundle

VECTORS = json.loads((Path(__file__).parent/'fixtures/freshness-policy.json').read_text())


@pytest.mark.parametrize('case', VECTORS['cases'], ids=lambda c: c['name'])
def test_shared_python_react_display_policy(case):
    values = copy.deepcopy(VECTORS['base'])
    for path, value in case['changes']:
        keys = [int(k) if k.isdigit() else k for k in path.split('.')]
        target = values
        for key in keys[:-1]: target = target[key]
        target[keys[-1]] = value
    before = canonical(values)
    result = select_display_forecast(**values, now=timestamp(case['now']))
    assert result['state'] == case['expected']
    assert result['forecast_id'] == (VECTORS['base']['operations']['catalog'][0]['id'] if case['expected'] != 'unavailable' else None)
    assert canonical(values) == before


def test_expired_source_cannot_mint_new_probability_but_verified_original_survives_to_scoring():
    first = snapshot(observed='2026-09-11T12:00:00Z')
    original = generate(first, [], '2026-09-11T13:00:00Z', '2026-09-11T13:00:00Z')
    saved = canonical(original)
    later = copy.deepcopy(first)
    later['retrieved_at'] = '2026-09-13T13:00:00Z'
    current = generate(later, [first], '2026-09-13T13:01:00Z', '2026-09-13T13:01:00Z')
    assert current['games'][0]['home_probability'] is None
    ops = build_operations([bundle(original), bundle(current)], [first, later], current['generated_at'])
    choice = select_display_forecast(current, current['games'][0], ops, timestamp(current['generated_at']))
    assert choice['state'] == 'older'
    record = next(f for f in ops['catalog'] if f['id'] == choice['forecast_id'])
    assert record['generated_at'] == original['generated_at']
    final = copy.deepcopy(later)
    final['retrieved_at'] = final['source_updated_at'] = '2026-09-13T22:00:00Z'
    final['games'][0].update(phase='FINAL', validated=True, home_score=24, away_score=17)
    postgame = build_operations([bundle(original), bundle(current)], [first, later, final], '2026-09-13T22:01:00Z')
    assert select_display_forecast(current, current['games'][0], postgame, timestamp(postgame['generated_at']))['state'] == 'archived'
    game = postgame['games'][0]
    assert game['final_forecast_id'] == record['id']
    assert len(game['evaluations']) == 1
    p = original['games'][0]['home_probability']
    metrics = postgame['metrics']['primary']
    assert metrics['count'] == 1 and metrics['brier'] == pytest.approx((p-1)**2)
    assert metrics['log_loss'] == pytest.approx(-math.log(p))
    assert metrics['accuracy'] == float(p >= .5)
    assert canonical(original) == saved


def test_changed_source_never_falls_back_to_obsolete_probability():
    first = snapshot(observed='2026-09-11T12:00:00Z')
    original = generate(first, [], '2026-09-11T13:00:00Z', '2026-09-11T13:00:00Z')
    changed = copy.deepcopy(first)
    changed.update(raw_sha256='b'*64, retrieved_at='2026-09-13T13:00:00Z')
    current = generate(changed, [first], '2026-09-13T13:01:00Z', '2026-09-13T13:01:00Z')
    ops = build_operations([bundle(original), bundle(current)], [first, changed], current['generated_at'])
    assert select_display_forecast(current, current['games'][0], ops, timestamp(current['generated_at']))['state'] == 'unavailable'


def test_display_full_lifecycle_preserves_designated_snapshot_and_immutable_versions(monkeypatch):
    first = snapshot(observed='2026-09-12T12:00:00Z')
    original = generate(first, [], '2026-09-12T13:00:00Z', '2026-09-12T13:00:00Z')
    latest = generate(first, [], '2026-09-12T14:00:00Z', '2026-09-12T14:00:00Z')
    archives = [bundle(original), bundle(latest)]
    saved = canonical(archives)
    game = latest['games'][0]
    pre = build_operations(archives, [first], latest['generated_at'])
    expected = select_display_forecast(latest, game, pre, timestamp(latest['generated_at']))['forecast_id']
    assert expected != pre['games'][0]['original_forecast_id']

    def forbidden_score(*args, **kwargs):
        raise AssertionError('Post-kickoff refresh must never score a new pregame forecast')

    monkeypatch.setattr('ml.current.score', forbidden_score)
    history = [first]
    versions = []
    for phase, verified, scores in [('IN_PROGRESS', False, (7, 3)), ('FINAL', False, (24, 17)),
                                     ('FINAL', True, (24, 17)), ('FINAL', True, (17, 24)),
                                     ('FINAL', True, (24, 24))]:
        observation = copy.deepcopy(first)
        hour = 18 + len(history)
        now = f'2026-09-13T{hour:02}:00:00Z'
        observation.update(retrieved_at=now, source_updated_at=now, raw_sha256=str(len(history))*64)
        observation['games'][0].update(phase=phase, validated=verified, home_score=scores[0], away_score=scores[1])
        current = generate(observation, history, now, now)
        assert current['games'] == []
        history.append(observation)
        ops = build_operations(archives, history, now)
        row = ops['games'][0]
        assert row['final_forecast_id'] == expected
        choice = select_display_forecast(current, ops['schedule'][0], ops, timestamp(now))
        assert choice['state'] == 'archived' and choice['forecast_id'] == expected
        if not verified:
            assert row['result'] is None and row['evaluations'] == []
        elif scores[0] == scores[1]:
            assert row['result']['tie'] and not row['evaluations']
        else:
            evaluation = next(e for e in row['evaluations'] if e['primary'])
            y = int(scores[0] > scores[1])
            p = game['home_probability']
            assert evaluation['forecast_id'] == expected
            assert evaluation['brier'] == pytest.approx((p-y)**2)
            assert evaluation['log_loss'] == pytest.approx(-math.log(p if y else 1-p))
        versions.append((ops, canonical(ops)))
    assert len({o['games'][0]['result']['version'] for o, _ in versions if o['games'][0]['result']}) == 3
    assert canonical(archives) == saved
    assert all(canonical(ops) == body for ops, body in versions)


def test_archived_display_honors_designation_instead_of_selecting_a_better_result():
    first = snapshot()
    original = generate(first, [], '2026-09-12T13:00:00Z', '2026-09-12T13:00:00Z')
    later = generate(first, [], '2026-09-12T14:00:00Z', '2026-09-12T14:00:00Z')
    ops = build_operations([bundle(original), bundle(later)], [first], '2026-09-13T18:00:00Z')
    designated = ops['catalog'][0]['id']
    ops['games'][0]['final_forecast_id'] = designated
    assert select_display_forecast(later, later['games'][0], ops, timestamp(ops['generated_at']))['forecast_id'] == designated
