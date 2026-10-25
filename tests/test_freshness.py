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
    assert select_display_forecast(current, current['games'][0], postgame, timestamp(postgame['generated_at']))['state'] == 'unavailable'
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
