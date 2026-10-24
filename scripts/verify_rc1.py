"""Read-only release verification; only RC1 reports/bundles and temp restores are written."""
import contextlib
import hashlib
import io
import json
import re
import runpy
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from tempfile import TemporaryDirectory

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from ml.current_source import timestamp
from ml.evidence_bundle import collect_payload, export_bundle, import_bundle, validate_payload

sha = lambda body: hashlib.sha256(body).hexdigest()


def main():
    now = datetime.now(timezone.utc)
    baseline = json.loads((ROOT/'docs/RC1_BASELINE.json').read_bytes())
    verified = {}
    for group in ('file_sha256', 'local_dataset_sha256'):
        for name, digest in baseline[group].items():
            actual = sha((ROOT/name).read_bytes())
            if actual != digest: raise ValueError('RC1 protected evidence changed: '+name)
            verified[name] = actual
    original = Path.home()/'Documents/ChatGPT/AI/nfl-predictor'
    legacy = {}
    for path in sorted((ROOT/'legacy').glob('*.py')):
        assert sha(path.read_bytes()) == sha((original/path.name).read_bytes())
        legacy[path.name] = sha(path.read_bytes())
    # The independent oracle reads only the current 2026 raw capture and frozen JSON.
    capture = io.StringIO()
    with contextlib.redirect_stdout(capture):
        runpy.run_path(str(ROOT/'scripts/verify_current.py'), run_name='rc1_independent_oracle')
    independent = json.loads(capture.getvalue())
    scope = runpy.run_path(str(ROOT/'scripts/replay_current.py'), run_name='rc1_replay')
    directory = ROOT/'web/public/data/current'
    pointer = json.loads((directory/'latest.json').read_bytes())
    artifact = json.loads((directory/pointer['file']).read_bytes())
    replay = scope['replay'](directory/pointer['file'])
    payload = collect_payload(2026)
    proofs = validate_payload(payload, 2026, now.isoformat())
    output = ROOT/'artifacts/rc1'; output.mkdir(parents=True, exist_ok=True)
    bundle = export_bundle(2026, output/'real-evidence-bundle', created_at=now.isoformat())
    with TemporaryDirectory(prefix='fourth-down-rc1-real-restore-') as temp:
        restored = import_bundle(bundle['bundle'], 2026, bundle['sha256'], root=temp,
                                 expected_manifest_sha256=bundle['manifest_sha256'])
        assert collect_payload(2026, temp) == payload
        repeated = import_bundle(bundle['bundle'], 2026, bundle['sha256'], root=temp)
        assert repeated['restored'] == 0
        assert not (Path(temp)/'web/public/data/current/latest.json').exists()
    tracked = subprocess.check_output(['git','ls-files','-z'],cwd=ROOT).decode().split('\0')
    untracked = subprocess.check_output(['git','ls-files','--others','--exclude-standard','-z'],cwd=ROOT).decode().split('\0')
    files = {ROOT/name for name in tracked+untracked if name}
    files.update(p for p in (ROOT/'web/dist').rglob('*') if p.is_file())
    patterns = {'private_key':rb'-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----',
                'github_token':rb'(?:gh[pousr]_[A-Za-z0-9]{30,}|github_pat_[A-Za-z0-9_]{50,})',
                'aws_access_key':rb'AKIA[0-9A-Z]{16}',
                'openai_key':rb'sk-(?:proj-)?[A-Za-z0-9_-]{40,}'}
    findings = []
    for path in sorted(files):
        if not path.is_file(): continue
        body = path.read_bytes()
        for kind, pattern in patterns.items():
            if re.search(pattern,body): findings.append({'file':str(path.relative_to(ROOT)), 'kind':kind})
    assert not findings, 'Potential embedded credentials; review paths without printing secret contents'
    result = {'schema_version':1, 'checked_at':now.isoformat(), 'source_commit':baseline['source_commit'],
        'protected_files_verified':len(baseline['file_sha256']), 'local_datasets_verified':len(baseline['local_dataset_sha256']),
        'sha256':verified, 'legacy_original_matches':legacy, 'independent_current':independent,
        'byte_replay':replay, 'current_schedule_forecast_operations_proofs':proofs,
        'source_proof_scope':'Current schedule, forecast and operations bundle only; excludes context and research',
        'freshness':{'as_of':artifact['as_of'], 'generated_at':artifact['generated_at'],
            'source_updated_at':artifact['source']['source_updated_at'], 'valid_until':artifact['valid_until'],
            'source_age_hours':(now-timestamp(artifact['source']['source_updated_at'])).total_seconds()/3600,
            'expired_at_review':now>=timestamp(artifact['valid_until']),
            'future_kickoff_count_at_review':sum(timestamp(g['kickoff'])>now for g in artifact['games'] if g['kickoff']),
            'availability_limit':'Saved source only; no live source reacquisition or schedule-change assertion'},
        'real_bundle':bundle, 'restore':restored, 'idempotent_repeat_restored':repeated['restored'],
        'credential_scan':{'files':len(files), 'patterns':list(patterns), 'findings':findings,
            'scope':'Tracked and nonignored candidate source plus dist; finite patterns, not comprehensive secret detection'},
        'prohibited_actions_executed':[],
        'boundary_evidence_level':'Code-path review and artifact hashes; this field is not an instrumented runtime audit'}
    (output/'integrity-current-recovery.json').write_text(json.dumps(result,indent=2)+'\n')
    print(json.dumps({k:v for k,v in result.items() if k!='sha256'},indent=2))


if __name__ == '__main__': main()
