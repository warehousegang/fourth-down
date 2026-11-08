"""Report a failed provider check after preserving/publishing verified evidence.

Run after the existing publisher, including no-change runs. This command reads
only the refresh receipt; it never collects, modifies, publishes or sends alerts.
GitHub Actions retains its existing failed-run notification mechanism.
"""
import argparse
import json
from datetime import datetime, timezone
from pathlib import Path


def check(receipt, now=None):
    if not isinstance(receipt, dict) or receipt.get('schema_version') != 1:
        raise ValueError('Missing or invalid refresh receipt; collection health is unknown')
    results = receipt.get('results')
    if not isinstance(results, dict):
        raise ValueError('Missing result collection receipt; collection health is unknown')
    if 'error' in results:
        # Never echo provider exception text, URLs, headers or credentials.
        raise ValueError('Result provider check failed. Previously verified evidence is retained; inspect the refresh decision and the next scheduled run.')
    captured, requests, missing = (results.get(k) for k in ('captured', 'requests', 'missing'))
    if (type(results.get('changed')) is not bool or type(captured) is not int or captured < 0
            or type(requests) is not int or requests < 0 or not isinstance(missing, list)):
        raise ValueError('Incomplete result collection receipt; collection health is unknown')
    try:
        started = datetime.fromisoformat(receipt['started_at'].replace('Z','+00:00'))
        elapsed = ((now or datetime.now(timezone.utc))-started).total_seconds()
        if started.tzinfo is None or elapsed < 0:
            raise ValueError()
    except (KeyError, AttributeError, TypeError, ValueError):
        raise ValueError('Missing or invalid refresh start time; collection health is unknown') from None
    return {'healthy': True, 'captured': captured, 'provider_files_not_yet_available': len(missing),
            'elapsed_seconds': round(elapsed,3), 'duration_maintenance_required': elapsed >= 12*60}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--receipt', required=True)
    args = parser.parse_args()
    try:
        result = check(json.loads(Path(args.receipt).read_bytes()))
    except (OSError, ValueError):
        # CLI output is deliberately static even if an invalid file contains secrets.
        print('::error title=Fourth Down result collection::The provider check did not complete successfully. Retained scores are preserved. Inspect the refresh decision receipt and next scheduled execution.')
        return 1
    if result['duration_maintenance_required']:
        print('::warning title=Fourth Down refresh duration::Refresh exceeded 12 minutes. Review restoration and publication duration before it overlaps the 15-minute collection cadence.')
    print(json.dumps(result, indent=2))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
