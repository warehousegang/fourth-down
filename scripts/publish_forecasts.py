"""Commit one checked forecast/state tree and request the existing Pages build.

Uses the portfolio repository's GITHUB_TOKEN. Never updates Pages settings or
DNS. A failed build is recoverable by rerunning: unchanged data is not regenerated.
"""
import argparse
import concurrent.futures
import hashlib
import json
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from urllib.error import URLError
from urllib.parse import urljoin
from urllib.request import Request, urlopen

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from scripts.automated_refresh import publication_deadline, read_release

REPOSITORY = 'warehousegang/thomashowarddev'
ORIGIN = 'https://thomashoward.dev/'


def git(root, *args):
    return subprocess.check_output(['git', *args], cwd=root, text=True).strip()


def api(path, method='GET'):
    return json.loads(subprocess.check_output(['gh', 'api', '--method', method,
        '-H', 'Accept: application/vnd.github+json', f'repos/{REPOSITORY}/{path}'], text=True))


def permitted_changes(names):
    if any(not name.startswith(('fourth-down/', '.fourth-down-state/')) for name in names):
        raise ValueError('Publication attempted to change unrelated portfolio content')


def verify_settings(settings):
    if (settings['build_type'] != 'legacy' or settings['cname'] != 'thomashoward.dev'
            or settings['source'] != {'branch':'main', 'path':'/'}):
        raise ValueError('Pages configuration changed; refusing to change or replace it')


def fetch(path):
    request = Request(urljoin(ORIGIN, path), headers={
        'User-Agent':'FourthDown-publication-check/1.0', 'Cache-Control':'no-cache'})
    with urlopen(request, timeout=30) as response:
        return response.read(30_000_001)


def verify_live(root, full=True):
    files, receipt = read_release(root)
    if json.loads(fetch('fourth-down/release.json')) != receipt:
        raise ValueError('Live release receipt differs from checked Git tree')
    expected = {'fourth-down/'+name:body for name, body in files.items()}
    if not full:
        expected = {name:body for name,body in expected.items() if '/assets/' in name or name.endswith('latest.json')}
        for folder in ('current', 'operations', 'context'):
            pointer = json.loads(files[f'data/{folder}/latest.json'])
            name = f'data/{folder}/'+pointer['file']
            expected['fourth-down/'+name] = files[name]
    # Existing portfolio pages/assets must still match their unchanged Git bytes.
    for name in git(root, 'ls-files').splitlines():
        if not name.startswith(('fourth-down/', '.')) and name not in ('README.md', 'CNAME'):
            if full or name in ('index.html', 'projects/index.html', 'projects/nfl-predictor/index.html'):
                expected[name] = (Path(root)/name).read_bytes()
    def check(item):
        name, body = item
        path = name[:-10] if name.endswith('index.html') else name
        if hashlib.sha256(fetch(path)).digest() != hashlib.sha256(body).digest():
            raise ValueError('Live bytes differ: '+name)
    with concurrent.futures.ThreadPoolExecutor(max_workers=4) as pool:
        list(pool.map(check, expected.items()))
    pointer = json.loads(files['data/current/latest.json'])
    current = json.loads(files['data/current/'+pointer['file']])
    return dict(verified_files=len(expected), source_commit=receipt['source_commit'],
                forecast_sha256=pointer['sha256'], generated_at=current['generated_at'],
                source_updated_at=current['source']['source_updated_at'], valid_until=current['valid_until'])


def publish(root, pause=time.sleep):
    root = Path(root).resolve()
    verify_settings(api('pages'))
    original = git(root, 'rev-parse', 'HEAD')
    git(root, 'fetch', 'origin', 'main')
    if git(root, 'rev-parse', 'origin/main') != original:
        raise ValueError('Portfolio main moved during generation; rerun from its latest tree')
    names = set(git(root, 'diff', '--name-only', 'HEAD').splitlines())
    names.update(git(root, 'ls-files', '--others', '--exclude-standard').splitlines())
    permitted_changes(names)
    changed = bool(names)
    if changed:
        files, _ = read_release(root)
        pointer = json.loads(files['data/current/latest.json'])
        prior_pointer = json.loads(git(root,'show','HEAD:fourth-down/data/current/latest.json'))
        if pointer['sha256'] != prior_pointer['sha256']:
            publication_deadline(json.loads(files['data/current/'+pointer['file']]), datetime.now(timezone.utc))
        git(root, 'add', '--', 'fourth-down/', '.fourth-down-state/')
        permitted_changes(git(root, 'diff', '--cached', '--name-only').splitlines())
        git(root, 'config', 'user.name', 'github-actions[bot]')
        git(root, 'config', 'user.email', '41898282+github-actions[bot]@users.noreply.github.com')
        git(root, 'commit', '-m', 'Refresh Fourth Down forecasts and retained observations')
        # Never force-push or rebase across unreviewed website changes.
        git(root, 'push', 'origin', 'HEAD:main')
    revision = git(root, 'rev-parse', 'HEAD')
    latest = api('pages/builds/latest')
    build_requested = changed or latest.get('commit') != revision or latest.get('status') != 'built'
    if build_requested:
        # Token-authored pushes do not trigger Pages automatically. This requests
        # a build of the EXISTING branch publisher; it is not a settings update.
        api('pages/builds', 'POST')
        for attempt in range(36):
            latest = api('pages/builds/latest')
            if latest.get('commit') == revision and latest.get('status') == 'built':
                break
            if latest.get('commit') == revision and latest.get('status') == 'errored':
                raise RuntimeError('Pages build failed; rerun to retry the same retained tree')
            print('Waiting for existing Pages publisher...', flush=True)
            pause(10)
        else:
            raise RuntimeError('Pages did not confirm this commit within six minutes; retry manually')
    # CDN propagation can trail a successful Pages build. Bound retries; fail
    # visibly rather than accepting mismatched pointers or partial cached data.
    for attempt in range(12):
        try:
            verification = verify_live(root, full=changed)
            return dict(changed=changed, website_commit=revision, pages_build_requested=build_requested,
                        pages_status=latest['status'], **verification)
        except (ValueError, URLError, TimeoutError):
            if attempt == 11:
                raise
            print('Waiting for matching live assets...', flush=True)
            pause(10)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--portfolio', required=True)
    parser.add_argument('--receipt', required=True)
    args = parser.parse_args()
    result = publish(args.portfolio)
    Path(args.receipt).write_text(json.dumps(result, indent=2)+'\n')
    print(json.dumps(result, indent=2))
