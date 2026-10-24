"""Resume current-season forecasting from the portfolio's Git-retained evidence.

prepare changes only the disposable source checkout. stage is called after tests
and the production build pass. Neither command pushes, deploys, or fits a model.
"""
import argparse
import json
import shutil
import subprocess
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from urllib.error import HTTPError, URLError

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from ml.current_source import SCHEDULED, canonical, current_season, iso, load_snapshot, sha, timestamp
from ml.evidence_bundle import collect_payload, destination, validate_payload
from ml.refresh import acquire_bounded, refresh, refresh_lock
from scripts import forecast_state, portfolio_artifact

STATE = '.fourth-down-state'


def read_release(portfolio):
    root = Path(portfolio).resolve()
    if not (root/'.git').exists() or (root/'CNAME').read_bytes() != b'thomashoward.dev':
        raise ValueError('Expected the existing portfolio checkout and unchanged CNAME')
    files = {}
    for path in (root/'fourth-down').rglob('*'):
        if path.is_symlink():
            raise ValueError('Symlink in published application')
        if path.is_file():
            files[path.relative_to(root/'fourth-down').as_posix()] = path.read_bytes()
    receipt = json.loads(files.pop('release.json'))
    portfolio_artifact.validate(files, receipt)
    return files, receipt


def hydrate(portfolio, season, root=ROOT):
    """Keep original bytes; only latest pointers and the evidence ZIP may advance."""
    portfolio, root = Path(portfolio), Path(root)
    files, release = read_release(portfolio)
    state_path = destination(portfolio, f'{STATE}/automation.json')
    state = json.loads(state_path.read_bytes()) if state_path.exists() else {}
    pointer = json.loads(files['data/current/latest.json'])
    if state and (state.get('schema_version') != 1 or state.get('forecast_sha256') != pointer['sha256']):
        raise ValueError('Retained state and published forecast do not match')
    # Bootstrap from the source repository's verified original bundle only once.
    # Subsequent runs must use portfolio Git state, never an expiring Actions cache.
    if state:
        for suffix in ('json', 'zip'):
            name = f'forecast-evidence-{season}.{suffix}'
            saved = destination(portfolio, f'{STATE}/{name}')
            if saved.exists():
                target = destination(root, f'ops/{name}')
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_bytes(saved.read_bytes())
            elif state['season'] == season:
                raise ValueError('Retained observation bundle missing')
        if state['season'] == season:
            receipt = json.loads((root/'ops'/f'forecast-evidence-{season}.json').read_bytes())
            if receipt['sha256'] != state.get('evidence_sha256'):
                raise ValueError('Retained state and evidence receipt do not match')
    forecast_state.restore(season, root=root)
    for name, body in files.items():
        if not name.startswith(('data/current/', 'data/operations/', 'data/context/')):
            continue
        target = destination(root, 'web/public/'+name)
        if target.exists() and target.name != 'latest.json' and target.read_bytes() != body:
            raise ValueError('Immutable publication conflict: '+name)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(body)
    if pointer['season'] == season:
        forecast_state.checked_pair(root, season)
        validate_payload(collect_payload(season, root), season, iso(datetime.now(timezone.utc)))
    current = json.loads(files['data/current/'+pointer['file']])
    return current, state, release


def refresh_reasons(snapshot, previous, state, revision, now):
    """Actual kickoff timestamps cover every weekday, international games and DST."""
    reasons = []
    if not state or state.get('source_commit') != revision:
        reasons.append('initialization_or_source_revision')
    if previous['season'] != snapshot['season']:
        return reasons+['new_season']
    generated = timestamp(previous['generated_at'])
    if now < generated or timestamp(snapshot['retrieved_at']) > now:
        raise ValueError('Clock precedes retained forecast or source observation')
    old = previous['source']
    if (old['raw_sha256'], timestamp(old['source_updated_at'])) != (
            snapshot['raw_sha256'], timestamp(snapshot['source_updated_at'])):
        reasons.append('source_changed')
    # Only renew a still-fresh source; polling an old source must not make it new.
    if now-timestamp(snapshot['source_updated_at']) <= timedelta(hours=48) and now-generated >= timedelta(hours=12):
        reasons.append('freshness_renewal')
    if generated < timestamp(previous['valid_until']) <= now:
        reasons.append('source_expired')
    for game in snapshot['games']:
        if not game['kickoff']:
            continue
        kick = timestamp(game['kickoff'])
        if generated < kick <= now:
            reasons.append('kickoff_crossed')
        if game['phase'] in SCHEDULED and generated < kick-timedelta(hours=2) <= now < kick:
            reasons.append('pregame_window')
    return sorted(set(reasons))


def prepare(portfolio):
    season = current_season(datetime.now(timezone.utc))
    previous, state, _ = hydrate(portfolio, season)
    revision = subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=ROOT, text=True).strip()
    with refresh_lock():
        path = acquire_bounded(season)
        snapshot = load_snapshot(path, season)
        reasons = refresh_reasons(snapshot, previous, state, revision, datetime.now(timezone.utc))
        result = dict(schema_version=1, changed=bool(reasons), reasons=reasons, season=season,
                      source_commit=revision, source_updated_at=snapshot['source_updated_at'],
                      source_raw_sha256=snapshot['raw_sha256'], checked_at=iso(datetime.now(timezone.utc)))
        if reasons:
            result['refresh'] = refresh(path)
            # These cards are separate annotations, never probability inputs. A
            # network outage retains their original timestamps/expiry indicators.
            from ml.context import refresh_context
            try:
                refresh_context(snapshot)
                result['context'] = 'refreshed; does not affect probabilities'
            except (HTTPError, URLError, TimeoutError) as error:
                result['context'] = 'retained previous dated context: '+type(error).__name__
            result['evidence'] = forecast_state.save(season)
        return result


def publication_deadline(forecast, now):
    for game in forecast['games']:
        if game['status'] == 'available' and timestamp(game['kickoff']) <= now+timedelta(minutes=2):
            raise ValueError('Too close to kickoff to archive a new forecast safely; rerun after kickoff')


def stage(portfolio, result, output):
    if not result['changed']:
        return {'changed':False}
    root = Path(portfolio)
    old, _ = read_release(root)
    archive = portfolio_artifact.pack(output, generated_only=True)
    files, _ = portfolio_artifact.read_archive(output, archive['sha256'])
    for name, body in old.items():
        if name.startswith(('data/current/', 'data/operations/', 'data/context/')) and not name.endswith('/latest.json'):
            if files.get(name) != body:
                raise ValueError('Previously published history would be lost or rewritten')
    pointer = json.loads(files['data/current/latest.json'])
    current = json.loads(files['data/current/'+pointer['file']])
    publication_deadline(current, datetime.now(timezone.utc))
    portfolio_artifact.install(output, archive['sha256'], root)
    for suffix in ('json', 'zip'):
        name = f"forecast-evidence-{result['season']}.{suffix}"
        target = destination(root, f'{STATE}/{name}')
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(ROOT/'ops'/name, target)
    state = dict(schema_version=1, season=result['season'], source_commit=result['source_commit'],
                 forecast_sha256=pointer['sha256'], generated_at=pointer['generated_at'],
                 evidence_sha256=result['evidence']['sha256'])
    destination(root, f'{STATE}/automation.json').write_bytes(canonical(state))
    return {'changed':True, 'archive':archive, 'state':state}


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('command', choices=['prepare', 'stage'])
    parser.add_argument('--portfolio', required=True)
    parser.add_argument('--receipt', required=True)
    parser.add_argument('--archive')
    args = parser.parse_args()
    if args.command == 'prepare':
        result = prepare(args.portfolio)
        Path(args.receipt).write_bytes(canonical(result))
    else:
        result = stage(args.portfolio, json.loads(Path(args.receipt).read_bytes()), args.archive)
    print(json.dumps(result, indent=2))
