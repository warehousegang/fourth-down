"""Retain verified observations in Git so a fresh Actions runner can resume forecasting."""
import argparse
import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from ml.current_source import canonical, check_season, current_season, sha
from ml.evidence_bundle import collect_payload, encode_bundle, import_bundle


def checked_pair(root, season):
    artifacts = []
    for folder, prefix in [('current', f'forecast-{season}'), ('operations', 'operations')]:
        directory = Path(root)/'web/public/data'/folder
        pointer = json.loads((directory/'latest.json').read_bytes())
        if not re.fullmatch(prefix+r'-[0-9a-f]{64}\.json', pointer['file']):
            raise ValueError('Unexpected publication pointer')
        body = (directory/pointer['file']).read_bytes()
        if sha(body) != pointer['sha256']:
            raise ValueError('Publication checksum mismatch')
        artifact = json.loads(body)
        if artifact['season'] != season or pointer['generated_at'] != artifact['generated_at']:
            raise ValueError('Publication season/time mismatch')
        artifacts.append(artifact)
    forecast, operations = artifacts
    if (forecast['generated_at'] != operations['generated_at'] or
            forecast['snapshot_sha256'] != operations['source']['snapshot_sha256']):
        raise ValueError('Mixed forecast/operations generations; no deployable state saved')


def save(season, root=ROOT, now=None):
    check_season(season)
    root = Path(root)
    checked_pair(root, season)
    content, receipt = encode_bundle(collect_payload(season, root), season,
        (now or datetime.now(timezone.utc)).isoformat())
    directory = root/'ops'; directory.mkdir(parents=True, exist_ok=True)
    filename = f'forecast-evidence-{season}.zip'
    receipt.update(schema_version=1, file=filename,
                   purpose='Git-retained current-season observations; not a public web asset')
    # The workflow commits this pair and the public JSON in one Git tree only after
    # all tests/builds pass. An interrupted runner cannot change the live Pages site.
    for name, body in [(filename, content), (f'forecast-evidence-{season}.json', canonical(receipt))]:
        temporary = directory/(name+'.tmp'); temporary.write_bytes(body); temporary.replace(directory/name)
    return receipt


def restore(season, root=ROOT):
    check_season(season)
    root = Path(root)
    receipt_path = root/'ops'/f'forecast-evidence-{season}.json'
    if not receipt_path.exists():
        if list((root/'web/public/data/current').glob(f'forecast-{season}-*.json')):
            raise ValueError('Retained forecasts require their original evidence; state bundle missing')
        return {'season':season, 'new_season':True, 'restored':0}
    receipt = json.loads(receipt_path.read_bytes())
    if receipt.get('schema_version') != 1 or receipt.get('season') != season or receipt.get('file') != f'forecast-evidence-{season}.zip':
        raise ValueError('Invalid retained evidence receipt')
    return import_bundle(root/'ops'/receipt['file'], season, receipt['sha256'], root=root,
                         expected_manifest_sha256=receipt['manifest_sha256'])


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('command', choices=['restore','save'])
    parser.add_argument('--season', type=int, default=current_season(datetime.now(timezone.utc)))
    args = parser.parse_args()
    print(json.dumps((restore if args.command == 'restore' else save)(args.season), indent=2))
