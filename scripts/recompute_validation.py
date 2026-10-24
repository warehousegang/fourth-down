"""Read-only independent review. No project scoring/training functions or network calls."""
import csv
import hashlib
import json
import math
from datetime import date, datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
ORIGINAL = Path('/Users/thomas/Documents/ChatGPT/AI/nfl-predictor')
OUT = ROOT / 'artifacts/corrective'
OUT.mkdir(parents=True, exist_ok=True)

def read(path):
    return json.loads(path.read_text())

def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()

def close(a, b):
    assert abs(a-b) < 1e-12, (a, b)

frozen = read(ROOT/'docs/FROZEN_MODEL.json')
model = read(ROOT/'artifacts/model.json')
evaluation = read(ROOT/'artifacts/evaluation.json')
demo = read(ROOT/'web/public/data/demo.json')
manifest = read(ROOT/'data/manifest.json')
snapshot = ROOT/'data/schedules-2010-2023.csv'
assert sha(snapshot) == manifest['sha256'] == model['source_sha256'] == frozen['source_sha256']
frozen_checks = {p: sha(ROOT/p) == digest for p, digest in frozen['file_sha256'].items()}
assert all(frozen_checks.values())
assert frozen['model'] == model == demo['model']
assert evaluation == demo['evaluation'] == read(ROOT/'docs/VALIDATION_RESULTS.json')
assert sha(ROOT/'web/dist/data/demo.json') == sha(ROOT/'web/public/data/demo.json')
assert frozen['holdout_approval'] is None and frozen['holdout_evaluated'] is False
without_id = {k:v for k,v in model.items() if k != 'id'}
assert model['id'] == model['kind']+'-v1-'+hashlib.sha256(json.dumps(without_id, sort_keys=True).encode()).hexdigest()[:10]

# Validate only the season column before reading any score fields.
with snapshot.open() as source:
    seasons = {int(row['season']) for row in csv.DictReader(source)}
assert seasons == set(range(2010, 2024))
with snapshot.open() as source:
    raw = list(csv.DictReader(source))
assert len(raw) == manifest['rows']
assert all(row['game_type'] == 'REG' for row in raw)
for row in raw:
    row['season'] = int(row['season'])
    row['week'] = int(row['week'])
    row['day'] = date.fromisoformat(row['gameday'])
    for key in ('home_score', 'away_score'):
        row[key] = float(row[key]) if row[key] else None
complete = [r for r in raw if r['home_score'] is not None and r['away_score'] is not None]
training = [r for r in complete if r['season'] <= 2022 and r['home_score'] != r['away_score']]
validation = sorted([r for r in complete if r['season'] == 2023 and r['home_score'] != r['away_score']], key=lambda r:(r['day'],r['game_id']))
assert len(training) == 3347 and len(validation) == 272
lookup = {g['id']:g for g in demo['games']}
assert set(lookup) == {r['game_id'] for r in validation}
tz = ZoneInfo('America/New_York')
largest_factor_error = 0.0
largest_probability_error = 0.0
probs = []
early_games = 0

for row in validation:
    game = lookup[row['game_id']]
    assert game['status'] == 'available' and game['model_id'] == model['id']
    assert game['home'] == row['home_team'] and game['away'] == row['away_team']
    assert game['week'] == row['week'] and game['season'] == row['season']
    cutoff = datetime.fromisoformat(row['gameday']).replace(tzinfo=tz)
    kickoff = datetime.fromisoformat(row['gameday']+'T'+row['gametime']).replace(tzinfo=tz)
    assert datetime.fromisoformat(game['cutoff']) == cutoff < kickoff
    assert datetime.fromisoformat(game['kickoff']) == kickoff
    assert game['stadium'] == row['stadium']
    assert game['neutral_site'] == (row['location'] == 'Neutral')
    side_values = {}
    # Independent per-team queries, not the production batched state machine.
    for side in ('home', 'away'):
        team = row[side+'_team']
        history = sorted([r for r in complete if r['season'] == row['season'] and r['day'] < row['day'] and team in (r['home_team'],r['away_team'])], key=lambda r:(r['day'],r['game_id']))
        margins = [(r['home_score']-r['away_score'])*(1 if r['home_team']==team else -1) for r in history]
        wins = sum(1 if m > 0 else 0.5 if m == 0 else 0 for m in margins)
        n = len(history)
        side_values[side] = {
            'smooth_win_diff': (wins+2)/(n+4),
            'margin_diff': sum(margins)/(n+4),
            'recent_margin_diff': sum(margins[-5:])/(min(n,5)+2),
            'rest_diff': min(14,(row['day']-history[-1]['day']).days) if n else 7,
        }
        assert game['history_games'][side] == n
    early_games += int(min(game['history_games'].values()) == 0)
    z = model['intercept']
    for key, coefficient, factor in zip(model['features'], model['coefficients'], game['factors'], strict=True):
        home, away = side_values['home'][key], side_values['away'][key]
        difference = home-away
        contribution = difference*coefficient
        assert factor['key'] == key
        for actual, expected in [(factor['home'],home),(factor['away'],away),(factor['difference'],difference),(factor['coefficient'],coefficient),(factor['contribution'],contribution)]:
            close(actual, expected)
            largest_factor_error = max(largest_factor_error,abs(actual-expected))
        z += contribution
    p = 1/(1+math.exp(-z))
    close(p,game['home_probability'])
    largest_probability_error = max(largest_probability_error,abs(p-game['home_probability']))
    probs.append(p)

y = np.array([int(r['home_score'] > r['away_score']) for r in validation])
p = np.array(probs)
home_rate = sum(r['home_score'] > r['away_score'] for r in training)/len(training)
close(home_rate, evaluation['home_win_rate'])
def metrics(predictions):
    return {'n':len(y), 'accuracy':float(np.mean((predictions >= .5)==y)), 'brier':float(np.mean((predictions-y)**2)), 'log_loss':float(-np.mean(y*np.log(predictions)+(1-y)*np.log(1-predictions)))}
recomputed = {key:metrics(pred) for key,pred in [('coin',np.full(len(y),.5)),('home',np.full(len(y),home_rate)),('schedule',p)]}
for key, values in recomputed.items():
    reported = next(r for r in evaluation['models'] if r['id'] == key)
    for metric,value in values.items(): close(value,reported[metric])
weeks = np.array([r['week'] for r in validation])
delta = (p-y)**2-(home_rate-y)**2
groups = [delta[weeks == week] for week in sorted(set(weeks))]
rng = np.random.default_rng(42)
replicates = [np.concatenate([groups[i] for i in rng.integers(0,len(groups),len(groups))]).mean() for _ in range(2000)]
interval = {'mean':float(delta.mean()),'low':float(np.quantile(replicates,.025)),'high':float(np.quantile(replicates,.975)),'unit':'week','replicates':2000}
for key in ('mean','low','high'): close(interval[key],evaluation['brier_difference'][key])
bins = np.minimum(np.floor(p*10).astype(int),9)
calibration = [{'bin':int(i),'count':int((bins==i).sum()),'predicted':float(p[bins==i].mean()),'observed':float(y[bins==i].mean())} for i in sorted(set(bins))]
for actual, reported in zip(calibration,evaluation['calibration'],strict=True):
    for key in actual: close(actual[key],reported[key])
originals = {name:{'manifest_matches_original':sha(ORIGINAL/name)==value,'manifest_matches_legacy':sha(ROOT/'legacy'/name)==value} for name,value in read(ROOT/'legacy/SHA256.json').items()}
assert all(all(checks.values()) for checks in originals.values())
assert not (ROOT/'web/public/teams').exists()
assert not (ROOT/'web/dist/teams').exists()
timestamp_order = [manifest['retrieved_at'],evaluation['generated_at'],demo['generated_at']]
assert sorted(map(datetime.fromisoformat,timestamp_order)) == list(map(datetime.fromisoformat,timestamp_order))
report = {
    'review_method':'Independent CSV history queries and saved-coefficient scoring; no fitting, tuning, network acquisition, or holdout reads',
    'source_sha256':sha(snapshot),'freeze_sha256':sha(ROOT/'docs/FROZEN_MODEL.json'),'demo_sha256':sha(ROOT/'web/public/data/demo.json'),
    'frozen_file_checks':frozen_checks,'model_and_reports_match':True,'built_demo_matches':True,'candidate_holdout_evaluation_locked':True,'holdout_exposure_status':read(ROOT/'docs/HOLDOUT_EXPOSURE.json')['status'],
    'source_rows':len(raw),'source_seasons':[min(seasons),max(seasons)],'ties':sum(r['home_score']==r['away_score'] for r in complete),'incomplete':len(raw)-len(complete),
    'train_n':len(training),'validation_n':len(validation),'training_home_rate':home_rate,'recomputed':recomputed,'brier_difference':interval,'calibration':calibration,
    'all_272_forecasts_and_1088_factors_match':True,'largest_factor_error':largest_factor_error,'largest_probability_error':largest_probability_error,
    'all_272_cutoffs_kickoffs_venues_match_source':True,'games_with_zero_prior_season_history':early_games,
    'timestamps_source_evaluation_forecast':timestamp_order,'original_script_checks':originals,'unlicensed_logos_absent':True,
    'not_reproduced_without_refitting':['original logistic metrics','four ablation fits','five expanding-window fitted model metrics'],
}
(OUT/'evidence.json').write_text(json.dumps(report,indent=2)+'\n')
print(json.dumps(report,indent=2))
