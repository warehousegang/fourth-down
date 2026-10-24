"""Package Fourth Down and import only its static directory into the portfolio."""
import argparse
import gzip
import hashlib
import io
import json
import os
import re
import subprocess
import tarfile
import tempfile
from pathlib import Path, PurePosixPath

ROOT = Path(__file__).resolve().parents[1]
BASE = '/fourth-down/'
MAX_BYTES = 30_000_000


def digest(body):
    return hashlib.sha256(body).hexdigest()


def allowed(name):
    path = PurePosixPath(name)
    return (not path.is_absolute() and '\\' not in name and str(path) == name
            and all(part not in ('..', '.') and not part.startswith('.') for part in path.parts)
            and (name in {'index.html', 'CURRENT_DATA_NOTICE.txt', 'THIRD_PARTY_NOTICES.txt'}
                 or path.parts[0] in {'assets', 'data'}))


def validate(files, receipt):
    if (receipt.get('schema_version') != 1 or receipt.get('application') != 'fourth-down'
            or receipt.get('base_path') != BASE
            or not re.fullmatch('[0-9a-f]{40}', receipt.get('source_commit', ''))):
        raise ValueError('Invalid Fourth Down release receipt')
    hashes = receipt.get('files', {})
    if not hashes or set(files) != set(hashes) or any(not allowed(name) for name in files):
        raise ValueError('Unexpected or missing static files')
    if sum(map(len, files.values())) > MAX_BYTES:
        raise ValueError('Static artifact exceeds the portfolio size budget')
    if any(digest(body) != hashes[name] for name, body in files.items()):
        raise ValueError('Static file checksum mismatch')
    for name in ['index.html', 'CURRENT_DATA_NOTICE.txt', 'THIRD_PARTY_NOTICES.txt',
                 'data/demo.json', 'data/current/latest.json', 'data/operations/latest.json',
                 'data/research/latest.json', 'data/context/latest.json']:
        if name not in files:
            raise ValueError(f'Required static file missing: {name}')
    links = re.findall(r'(?:src|href)="([^"]+)"', files['index.html'].decode())
    if not links or any(not link.startswith(BASE) or link[len(BASE):] not in files for link in links):
        raise ValueError('Build must use /fourth-down/ with local static assets')


def pack(output):
    # The source commit plus per-file checksums identify the exported build.
    dirty = subprocess.check_output(['git', 'status', '--porcelain', '--untracked-files=normal'], cwd=ROOT)
    if dirty:
        raise ValueError('Commit the reviewed source before packaging')
    env = {**os.environ, 'VITE_BASE_PATH': BASE}
    for script in ['check-release.mjs', 'check-dist.mjs']:
        subprocess.run(['node', str(ROOT/'web/scripts'/script)], cwd=ROOT, env=env, check=True)
    files = {}
    for path in (ROOT/'web/dist').rglob('*'):
        if path.is_symlink():
            raise ValueError('Symlinks are not static release assets')
        if path.is_file():
            files[path.relative_to(ROOT/'web/dist').as_posix()] = path.read_bytes()
    receipt = dict(schema_version=1, application='fourth-down', base_path=BASE,
                   source_commit=subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=ROOT).decode().strip(),
                   files={name:digest(body) for name,body in sorted(files.items())})
    validate(files, receipt)
    files['release.json'] = (json.dumps(receipt, indent=2, sort_keys=True)+'\n').encode()
    output = Path(output); output.parent.mkdir(parents=True, exist_ok=True)
    with output.open('wb') as raw, gzip.GzipFile(fileobj=raw, mode='wb', filename='', mtime=0) as zipped:
        with tarfile.open(fileobj=zipped, mode='w') as archive:
            for name, body in sorted(files.items()):
                member = tarfile.TarInfo(name); member.size = len(body); member.mode = 0o644
                archive.addfile(member, io.BytesIO(body))
    checksum = digest(output.read_bytes())
    Path(str(output)+'.sha256').write_text(f'{checksum}  {output.name}\n')
    return dict(archive=str(output), sha256=checksum, source_commit=receipt['source_commit'], files=len(files))


def read_archive(path, expected):
    path = Path(path)
    if path.stat().st_size > MAX_BYTES or not re.fullmatch('[0-9a-f]{64}', expected):
        raise ValueError('Invalid archive size or SHA256')
    if digest(path.read_bytes()) != expected:
        raise ValueError('Archive checksum mismatch')
    files = {}; total = 0
    with tarfile.open(path, 'r:gz') as archive:
        for member in archive:
            if (not member.isfile() or member.name in files
                    or (member.name != 'release.json' and not allowed(member.name))):
                raise ValueError('Unsafe or duplicate archive member')
            total += member.size
            if total > MAX_BYTES or len(files) >= 2000:
                raise ValueError('Archive exceeds the portfolio size budget')
            files[member.name] = archive.extractfile(member).read()
    receipt = json.loads(files.pop('release.json'))
    validate(files, receipt)
    return files, receipt


def install(archive, expected, portfolio):
    files, receipt = read_archive(archive, expected)
    root = Path(portfolio).resolve()
    if not (root/'.git').exists() or (root/'CNAME').read_text().strip() != 'thomashoward.dev':
        raise ValueError('Target must be the existing thomashoward.dev Git checkout')
    target = root/'fourth-down'
    if target.is_symlink():
        raise ValueError('Refusing a symlink destination')
    if target.exists():
        prior = {}
        for path in target.rglob('*'):
            if path.is_symlink():
                raise ValueError('Refusing existing symlink content')
            if path.is_file(): prior[path.relative_to(target).as_posix()] = path.read_bytes()
        # Do not erase unowned files or local edits inside the application directory.
        previous_receipt = json.loads(prior.pop('release.json'))
        validate(prior, previous_receipt)
    with tempfile.TemporaryDirectory(prefix='.fourth-down-import-', dir=root) as temporary:
        stage = Path(temporary)/'new'; stage.mkdir()
        for name, body in files.items():
            destination = stage/name; destination.parent.mkdir(parents=True, exist_ok=True)
            destination.write_bytes(body)
        (stage/'release.json').write_text(json.dumps(receipt, indent=2, sort_keys=True)+'\n')
        backup = Path(temporary)/'previous'
        if target.exists(): target.rename(backup)
        try:
            stage.rename(target)
        except BaseException:
            if backup.exists(): backup.rename(target)
            raise
    return dict(directory=str(target), source_commit=receipt['source_commit'], files=len(files),
                publication='Local import only; review and approved Git push are separate')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest='command', required=True)
    package = sub.add_parser('pack'); package.add_argument('--output', required=True)
    importer = sub.add_parser('install')
    importer.add_argument('--archive', required=True); importer.add_argument('--sha256', required=True)
    importer.add_argument('--portfolio', required=True)
    args = parser.parse_args()
    print(json.dumps(pack(args.output) if args.command == 'pack' else
                     install(args.archive, args.sha256, args.portfolio), indent=2))
