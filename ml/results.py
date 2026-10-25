"""Add verified outcome evidence to the existing V1 ledger; never run inference."""
import copy
from datetime import datetime, timezone

from ml.current_source import canonical, iso, sha, timestamp
from ml.data import ROOT
from ml.lifecycle import HOME_RATE, binary_score, investigate, metric_set
from ml.result_source import LICENSE, REPOSITORY, effective_game


def reconcile(operations, observations, now=None):
    """Observations must have passed result_source.validate_observation first."""
    now = now or iso(datetime.now(timezone.utc))
    generated = timestamp(now)
    if generated < timestamp(operations['generated_at']):
        raise ValueError('Result reconciliation cannot move time backwards')
    result = copy.deepcopy(operations)
    latest = {}
    for observation in observations:
        game = observation['game']
        if observation['season'] != operations['season'] or timestamp(observation['observed_at']) > generated:
            raise ValueError('Mixed-season or future outcome observation')
        key = game['id']
        prior = latest.get(key)
        if prior and timestamp(prior['source_updated_at']) == timestamp(observation['source_updated_at']):
            if prior['game'] != game:
                raise ValueError('Conflicting result versions at the same publication time')
            # Repeated retrieval never moves first-observed timestamps forward.
            if timestamp(prior['observed_at']) <= timestamp(observation['observed_at']):
                continue
        elif prior and timestamp(prior['source_updated_at']) > timestamp(observation['source_updated_at']):
            continue
        latest[key] = observation
    schedule = {g['id']:g for g in result['schedule']}
    applied = []
    for row in result['games']:
        observation = latest.get(row['id'])
        if not observation:
            continue
        game = effective_game(observation); scheduled = schedule.get(row['id'])
        if not scheduled or any(game[k] != scheduled[k] for k in ('season','week','home','away','kickoff','day')):
            continue  # A confirmed reschedule cannot inherit another kickoff's result.
        if (timestamp(observation['source_updated_at']) < timestamp(result['source']['source_updated_at'])
                and (row['result'] and row['result'].get('provider') != 'nflverse'
                     or row['status'] in {'postponed','canceled'} and not row.get('result_evidence'))):
            continue  # Newer verified primary results or explicit cancellation win.
        # A newer schedule publication without a verified result is not a
        # retraction of an independently verified final.
        state = game['status']
        if state == 'unknown':
            continue
        digest = sha(canonical(observation))
        row['status'] = scheduled['status'] = state
        scheduled['source_phase'] = game['phase']
        row['result_evidence'] = digest
        row['result'] = None; row['evaluations'] = []; row['analysis'] = None
        records = [r for r in result['catalog'] if r['game_id'] == row['id'] and r['eligible']]
        # An existing designation is authoritative. A new one uses time/identity,
        # never which prediction would have been correct.
        if row['final_forecast_id'] is None and state in {'completed','in_progress'} and records:
            final = max(records, key=lambda r:(timestamp(r['generated_at']),r['id']))
            row['final_forecast_id'] = final['id']; final['selected_final'] = True
        if state == 'completed':
            row['result'] = {'version':sha(canonical({k:game[k] for k in ('id','home_score','away_score','phase')})),
                             'home_score':game['home_score'], 'away_score':game['away_score'],
                             'tie':game['home_score'] == game['away_score'],
                             'observed_at':observation['observed_at'], 'source_updated_at':observation['source_updated_at'],
                             'source_url':observation['source_url'], 'snapshot_sha256':digest,
                             'raw_sha256':observation['raw_sha256'], 'provider':'nflverse'}
            if not row['result']['tie']:
                y = int(game['home_score'] > game['away_score'])
                for forecast in records:
                    p = forecast['home_probability']
                    row['evaluations'].append({'forecast_id':forecast['id'], 'game_id':row['id'], 'season':result['season'],
                        'primary':forecast['id'] == row['final_forecast_id'], 'home_probability':p, 'outcome_home':y,
                        **binary_score(p,y), 'baseline':{'coin_flip':{'probability':.5, **binary_score(.5,y)},
                        'home_rate':{'probability':HOME_RATE, **binary_score(HOME_RATE,y)}}})
            row['analysis'] = investigate(game,row['result'],next((e for e in row['evaluations'] if e['primary']),None))
        applied.append(observation)
    if not applied:
        return operations
    scores = [e for game in result['games'] for e in game['evaluations']]
    tied = [g for g in result['games'] if g['result'] and g['result']['tie']]
    ties_primary = sum(g['final_forecast_id'] is not None for g in tied)
    ties_all = sum(sum(r['eligible'] and r['game_id'] == g['id'] for r in result['catalog']) for g in tied)
    result['metrics'] = {'primary':metric_set([e for e in scores if e['primary']],ties_primary),
                         'all_snapshots':metric_set(scores,ties_all)}
    from collections import Counter
    result['schedule_counts'] = dict(Counter(g['status'] for g in result['schedule']))
    result['result_feed'] = {'provider':'nflverse', 'source_url':REPOSITORY, 'license_url':LICENSE,
        'base_operations_sha256':operations.get('result_feed',{}).get('base_operations_sha256',sha(canonical(operations))),
        'last_observed_at':max(o['observed_at'] for o in applied),
        'source_updated_at':max(o['source_updated_at'] for o in applied)}
    no_scores = 'No eligible recorded forecasts have an observed non-tied final result; prospective metrics remain unavailable.'
    result['warnings'] = [w for w in result['warnings'] if w != no_scores]
    if not scores:
        result['warnings'].append(no_scores)
    # A duplicate check must not create a new artifact, receipt, or frontend build.
    if canonical(result) == canonical(operations):
        return operations
    result['generated_at'] = iso(generated)
    for path in ('ml/results.py','ml/result_source.py','requirements-results.txt'):
        result['pipeline_sha256'][path] = sha((ROOT/path).read_bytes())
    return result
