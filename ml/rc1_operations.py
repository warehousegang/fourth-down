"""Offline RC1 operational fault injection; all publication is in temporary directories."""
import copy
import csv
import io
import json
import re
from datetime import date, timedelta
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch
from urllib.error import HTTPError, URLError

from ml import current_source, refresh as runner
from ml.current import publish_local
from ml.current_source import DOWNLOAD, TEAMS, canonical, normalize, sha, timestamp
from ml.data import ROOT
from ml.evidence_bundle import collect_payload, export_bundle, import_bundle, validate_payload


def synthetic_source(root):
    """Complete fictitious 272-game schedule; no real scores or source acquisition."""
    stream = io.StringIO()
    fields = ['season', 'season_type', 'week', 'game_key', 'game_id', 'game_time',
              'game_date', 'phase', 'home_team_abbr', 'visitor_team_abbr', 'home_score',
              'visitor_score', 'validated', 'site_full_name']
    writer = csv.DictWriter(stream, fieldnames=fields); writer.writeheader()
    teams = sorted(TEAMS)
    for week in range(1, 18):
        day = date(2026, 9, 6) + timedelta(days=(week-1)*7)
        for i in range(16):
            key = (week-1)*16+i+1
            writer.writerow(dict(season=2026, season_type='REG', week=week, game_key=key,
                game_id=f'synthetic-{key}', game_time=f'{day}T17:00:00Z', game_date=day.strftime('%m/%d/%Y'),
                phase='', home_team_abbr=teams[i], visitor_team_abbr=teams[31-i], home_score='',
                visitor_score='', validated='false', site_full_name='RC1 SYNTHETIC'))
        teams = [teams[0], teams[-1], *teams[1:-1]]
    raw = stream.getvalue().encode()
    snapshot = dict(schema_version=1, season=2026, retrieved_at='2026-09-05T12:00:00Z',
        source_updated_at='2026-09-05T11:00:00Z', source_url=f'{DOWNLOAD}/ngs_schedule_2026.csv',
        raw_sha256=sha(raw), asset_id=1, source_name='RC1 SYNTHETIC; no NFL observations',
        license_url='https://example.test/synthetic', games=normalize(raw, 2026))
    directory = root/'data/current/2026'; directory.mkdir(parents=True)
    (directory/f'raw-{sha(raw)}.csv').write_bytes(raw)
    path = directory/f'snapshot-{sha(canonical(snapshot))}.json'
    path.write_bytes(canonical(snapshot))
    return path, snapshot


def assert_manual_trigger(text, allow_daily=False):
    """Accept only this project's explicit block syntax; fail closed on flow/merge forms."""
    lines = text.splitlines()
    positions = [i for i, line in enumerate(lines) if re.match(r"^(?:on|'on'|\"on\")[ \t]*:", line)]
    assert len(positions) == 1 and lines[positions[0]] == 'on:'
    block = []
    for line in lines[positions[0]+1:]:
        if not line.strip() or line.lstrip().startswith('#'): continue
        if not line.startswith(' '): break
        block.append(line)
    assert block and block[0] == '  workflow_dispatch:'
    if allow_daily and '  schedule:' in block:
        schedule = block.index('  schedule:')
        assert block[schedule:] == ['  schedule:', "    - cron: '17 12 * * *'"]
        block = block[:schedule]
    assert all(line.startswith('    ') for line in block[1:])
    assert not re.search(r'^\s*<<:|[&*][A-Za-z_][A-Za-z0-9_-]*', text, re.M)


def workflow_contract():
    """Check this repository's reviewed text contract, not a hosted Actions execution."""
    lock = json.loads((ROOT/'docs/ACTIONS_LOCK.json').read_bytes())['actions']
    records = []
    for path in sorted((ROOT/'.github/workflows').iterdir()):
        if not path.name.endswith(('.yml', '.yml.disabled')):
            continue
        text = path.read_text()
        active = path.suffix == '.yml'
        assert_manual_trigger(text, allow_daily='portfolio-artifact' in path.name)
        shadow = path.name == 'v2-shadow.yml'
        assert ('timeout-minutes: 12' if shadow else 'timeout-minutes: 10') in text and 'contents: read' in text
        uses = re.findall(r'uses:\s+([^\s#]+)', text)
        assert uses
        for use in uses:
            name, digest = use.split('@')
            assert digest == lock[name]['sha'] and re.fullmatch('[0-9a-f]{40}', digest)
        if shadow:
            assert 'group: v2-shadow-capture' in text and 'cancel-in-progress: false' in text
            assert 'ref: v2-shadow-state' in text and 'fetch-depth: 0' in text
            assert 'scripts/v2_shadow_tick.py' in text and 'scripts/v2_shadow_state.py' in text
            assert '  capture:\n    permissions:\n      contents: write' in text
            assert not any(v in text for v in ('deploy-pages@','pages: write','id-token: write','ml.refresh','portfolio_artifact.py'))
        elif 'portfolio-artifact' not in path.name:
            assert not re.search(r'^\s+\S+: write', text, re.M)
        else:
            assert 'deploy-pages@' not in text and 'pages: write' not in text and 'id-token: write' not in text
            assert 'cancel-in-progress: false' in text and 'retention-days: 7' in text
            assert 'forecast_state.py restore' in text and 'forecast_state.py save' in text
            assert 'portfolio_artifact.py pack' in text and 'VITE_BASE_PATH: /fourth-down/' in text
        records.append({'file':str(path.relative_to(ROOT)), 'sha256':sha(path.read_bytes()),
                        'active_manual_only':active, 'immutable_actions':len(uses)})
    assert len(records) == 3
    assert {Path(r['file']).name for r in records} <= {'ci.yml','portfolio-artifact.yml.disabled','portfolio-artifact.yml','v2-shadow.yml'}
    return records


def run():
    checks = []
    def record(name, **details):
        checks.append({'name':name, 'passed':True, **details})
    with TemporaryDirectory(prefix='fourth-down-rc1-operations-') as tmp:
        root = Path(tmp)
        source, snapshot = synthetic_source(root)
        current = root/'web/public/data/current'; operations = root/'web/public/data/operations'
        when = timestamp('2026-09-05T13:00:00Z')
        with patch.object(current_source, 'ROOT', root):
            kwargs = dict(now=when, current_directory=current, operations_directory=operations)
            first = runner.refresh(source, **kwargs)
            old_current = (current/'latest.json').read_bytes()
            old_ops = (operations/'latest.json').read_bytes()
            original_versions = {p:p.read_bytes() for folder in (current, operations) for p in folder.glob('*.json')}
            assert first['available_forecasts'] == 16
            assert first == runner.refresh(source, **kwargs)
            record('duplicate_refresh_is_byte_identical', available_forecasts=16)

            # Raise exactly before atomic pointer replacement. The new immutable file may exist.
            original_replace = Path.replace
            observations = []
            def fail_replace(path, target):
                if path == current/'.latest.tmp':
                    observations.append((current/'latest.json').read_bytes())
                    raise OSError('RC1 injected failure before pointer replacement')
                return original_replace(path, target)
            kwargs['now'] = when+timedelta(minutes=1)
            with patch.object(Path, 'replace', fail_replace):
                try: runner.refresh(source, **kwargs)
                except OSError: pass
                else: raise AssertionError('Failure injection did not execute')
            assert observations == [old_current]
            assert (current/'latest.json').read_bytes() == old_current
            assert (operations/'latest.json').read_bytes() == old_ops
            record('failure_before_pointer_replace_preserves_both_pointers')

            observed_after = []
            def observe_replace(path, target):
                before = Path(target).read_bytes() if Path(target).exists() else None
                result = original_replace(path, target)
                if path == current/'.latest.tmp':
                    pointer = json.loads(Path(target).read_bytes())
                    assert sha((current/pointer['file']).read_bytes()) == pointer['sha256']
                    observed_after.append({'before_sha256':sha(before), 'after_sha256':sha(Path(target).read_bytes())})
                return result
            with patch.object(Path, 'replace', observe_replace):
                runner.refresh(source, **kwargs)
            assert len(observed_after) == 1
            record('individual_pointer_replacement_has_complete_target', observations=observed_after,
                   limitation='Filesystem replace boundary checked; not power-loss durability or distributed atomicity')

            before_ops = (operations/'latest.json').read_bytes()
            kwargs['now'] = when+timedelta(minutes=2)
            with patch.object(runner, 'publish_operations', side_effect=OSError('RC1 second-publication failure')):
                try: runner.refresh(source, **kwargs)
                except OSError: pass
                else: raise AssertionError('Failure injection did not execute')
            assert (operations/'latest.json').read_bytes() == before_ops
            assert json.loads((current/'latest.json').read_bytes())['generated_at'] != json.loads(before_ops)['generated_at']
            runner.refresh(source, **kwargs)
            assert json.loads((current/'latest.json').read_bytes())['generated_at'] == json.loads((operations/'latest.json').read_bytes())['generated_at']
            record('partial_pair_publication_detected_and_same_input_rerun_recovers', cross_file_atomic=False)

            # Rollback only after validating every immutable payload against sources/model.
            payload = collect_payload(2026, root)
            validate_payload(payload, 2026, '2026-09-05T14:00:00Z')
            for folder, body in ((current, old_current), (operations, old_ops)):
                pointer = json.loads(body)
                assert sha((folder/pointer['file']).read_bytes()) == pointer['sha256']
                pending = folder/'.rc1-rollback.tmp'; pending.write_bytes(body); pending.replace(folder/'latest.json')
            assert all(p.read_bytes() == body for p, body in original_versions.items())
            rolled = json.loads((current/json.loads(old_current)['file']).read_bytes())
            assert timestamp(rolled['valid_until']) < timestamp('2026-09-08T00:00:00Z')
            record('rollback_restores_verified_pair_without_rewriting_time_or_versions', expiry_preserved=True,
                   original_valid_until=rolled['valid_until'], stale_review_at='2026-09-08T00:00:00Z',
                   expired_at_simulated_review=True,
                   limitation='Manual two-pointer rollback in isolated directory; production transaction not implemented')

            bundle = export_bundle(2026, root/'bundle', root=root, created_at='2026-09-05T14:00:00Z')
            restored = root/'restore'
            receipt = import_bundle(bundle['bundle'], 2026, bundle['sha256'], root=restored)
            again = import_bundle(bundle['bundle'], 2026, bundle['sha256'], root=restored)
            assert receipt['restored'] == len(payload) and again['restored'] == 0
            assert collect_payload(2026, restored) == payload
            assert not (restored/'web/public/data/current/latest.json').exists()
            record('portable_bundle_validates_restores_and_is_idempotent', files=len(payload),
                   pointers_restored=False, archive_sha256=bundle['sha256'])
            corrupted = root/'corrupt.zip'; corrupted.write_bytes(Path(bundle['bundle']).read_bytes()+b'corrupt')
            try: import_bundle(corrupted, 2026, bundle['sha256'], root=root/'bad-restore')
            except ValueError: pass
            else: raise AssertionError('Corrupt bundle accepted')
            assert not (root/'bad-restore').exists()
            record('corrupt_bundle_rejected_before_destination_creation')

            # Immutable version creation itself uses a direct write. Truncation blocks rerun;
            # record the limitation rather than silently deleting corrupted evidence.
            candidate = copy.deepcopy(rolled)
            candidate['generated_at'] = '2026-09-05T13:03:00Z'
            damaged = current/f"forecast-2026-{sha(canonical(candidate))}.json"
            damaged.write_bytes(b'{')
            before = (current/'latest.json').read_bytes()
            try: publish_local(candidate, current)
            except ValueError: pass
            else: raise AssertionError('Truncated immutable version accepted')
            assert (current/'latest.json').read_bytes() == before and damaged.read_bytes() == b'{'
            record('truncated_version_fails_closed_and_preserves_pointer',
                   automatic_repair=False, limitation='Production version writes are not crash-atomic; verified recovery required')

            # Budget failure is evaluated before writes; neither latest pointer moves.
            with patch.object(runner, 'MAX_UI_ARTIFACT_BYTES', 10):
                # Remove only our intentionally corrupt test file, then retry the ordinary path.
                damaged.unlink()
                before = [(d/'latest.json').read_bytes() for d in (current, operations)]
                try: runner.refresh(source, **kwargs)
                except ValueError as error: assert 'budget' in str(error)
                else: raise AssertionError('Oversize publication accepted')
                assert before == [(d/'latest.json').read_bytes() for d in (current, operations)]
            record('size_budget_failure_preserves_pointers')

        with runner.refresh_lock(root/'locks'):
            try:
                with runner.refresh_lock(root/'locks'): pass
            except RuntimeError: pass
            else: raise AssertionError('Duplicate lock accepted')
        with runner.refresh_lock(root/'locks'): pass
        record('duplicate_process_lock_blocks_then_releases')

    schedule = copy.deepcopy(snapshot)
    schedule['retrieved_at'] = '2026-10-20T12:00:00Z'
    schedule['source_updated_at'] = '2026-10-20T11:00:00Z'
    times = ['2026-10-23T00:15:00Z', '2026-10-24T20:00:00Z', '2026-10-25T13:30:00Z', '2026-10-27T00:15:00Z']
    schedule['games'] = schedule['games'][:4]
    for game, kickoff in zip(schedule['games'], times): game.update(kickoff=kickoff, week=7)
    plan = runner.plan_refresh(schedule, '2026-10-20T12:01:00Z')
    pre = [event for event in plan['events'] if event['kind'] == 'pregame']
    assert len(pre) == 4
    assert all(timestamp(event['latest_safe_start'])-timestamp(event['due_at']) == timedelta(minutes=90) for event in pre)
    assert {'early_week', 'saturday_evening'} <= {event['kind'] for event in plan['events']}
    missed = runner.plan_refresh(schedule, '2026-10-22T23:00:00Z')
    assert missed['missed_pregame_opportunities']
    late = runner.plan_refresh(schedule, '2026-10-23T00:16:00Z')
    assert not any(schedule['games'][0]['id'] in e['game_ids'] for e in late['events'] if e['kind'] == 'pregame')
    record('thursday_saturday_international_monday_and_missed_pregame_plan', events=len(plan['events']), enabled=plan['enabled'],
           schedule_policy='Tuesday09:00ET + Saturday18:00ET and every confirmed kickoff minus90min, including Thursday')
    dst = copy.deepcopy(schedule)
    dst['retrieved_at'] = '2026-10-30T12:00:00Z'
    dst['games'] = []
    dst_plan = runner.plan_refresh(dst, '2026-10-30T12:01:00Z')
    assert next(e['due_at'] for e in dst_plan['events'] if e['kind'] == 'saturday_evening') == '2026-10-31T22:00:00+00:00'
    assert next(e['due_at'] for e in dst_plan['events'] if e['kind'] == 'early_week') == '2026-11-03T14:00:00+00:00'
    record('eastern_dst_transition_preserves_local_schedule_hours')
    for kind, expected in [('outage',2), ('rate_limit',1)]:
        calls = []; pauses = []
        def failed(season):
            calls.append(season)
            if kind == 'outage': raise URLError('RC1 synthetic outage')
            raise HTTPError('https://example.test',429,'RC1 synthetic quota',{},io.BytesIO())
        try: runner.acquire_bounded(2026, failed, pauses.append)
        except (URLError, HTTPError): pass
        assert len(calls) == expected and len(pauses) == expected-1
        record(kind+'_bounded', attempts=len(calls), network_requests=0)
    records = workflow_contract()
    record('workflow_permissions_pins_no_cron_timeout_retention', workflows=records)
    return {'schema_version':1, 'mode':'RC1 SYNTHETIC OPERATIONAL DRY RUN', 'passed_checks':len(checks),
            'checks':checks, 'real_source_requests':0, 'real_publication_writes':0, 'scheduled_execution_enabled':False,
            'release_limitations':['Current and operations pointers are not a single transaction.',
                'Version file creation is not crash-atomic; collision fails closed and requires verified recovery.',
                'Trusted hosted bundle restoration and durable retention are not wired.',
                'Local dry runs do not prove hosted Actions runtime, billing quotas or Pages environment protection.']}


def main():
    result = run()
    directory = ROOT/'artifacts/rc1/operations'; directory.mkdir(parents=True, exist_ok=True)
    output = directory/f"dry-run-{sha(canonical(result))}.json"
    if output.exists() and output.read_bytes() != canonical(result): raise ValueError('Output collision')
    output.write_bytes(canonical(result))
    print(json.dumps({'report':str(output), **result}, indent=2))


if __name__ == '__main__': main()
