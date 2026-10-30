"""Static handoff integrity and rollback without publishing or reading new results."""
import io
import json
import tarfile
from pathlib import Path

import pytest
from scripts.portfolio_artifact import BASE, digest, install, read_archive


def bundle(path, version='one', extra=None, retained=None):
    files = {name:b'{}' for name in ['CURRENT_DATA_NOTICE.txt', 'THIRD_PARTY_NOTICES.txt',
        'data/demo.json', 'data/current/latest.json', 'data/operations/latest.json',
        'data/research/latest.json', 'data/context/latest.json']}
    files['index.html'] = f'<script src="{BASE}assets/app.js"></script>'.encode()
    files['assets/app.js'] = version.encode()
    files.update(retained or {})
    receipt = dict(schema_version=1, application='fourth-down', base_path=BASE,
                   source_commit='a'*40, files={n:digest(b) for n,b in files.items()})
    files['release.json'] = json.dumps(receipt).encode()
    with tarfile.open(path, 'w:gz') as archive:
        for name, body in files.items():
            entry=tarfile.TarInfo(name);entry.size=len(body);archive.addfile(entry,io.BytesIO(body))
        if extra:
            entry=tarfile.TarInfo(extra[0]);entry.type=extra[1];entry.linkname='/tmp/unrelated'
            archive.addfile(entry,io.BytesIO(b''))
    return digest(path.read_bytes())


def portfolio(tmp_path):
    root=tmp_path/'site';root.mkdir();(root/'.git').mkdir()
    (root/'CNAME').write_text('thomashoward.dev')
    (root/'index.html').write_text('Existing portfolio')
    (root/'styles.css').write_text('Existing styles')
    return root


def test_import_upgrade_and_rollback_preserve_portfolio(tmp_path):
    root=portfolio(tmp_path);before={p.name:p.read_bytes() for p in root.iterdir() if p.is_file()}
    old=tmp_path/'old.tgz';old_sha=bundle(old)
    new=tmp_path/'new.tgz';new_sha=bundle(new,'two')
    for archive,sha,expected in [(old,old_sha,'one'),(new,new_sha,'two'),(old,old_sha,'one')]:
        install(archive,sha,root)
        assert (root/'fourth-down/assets/app.js').read_text()==expected
        assert {p.name:p.read_bytes() for p in root.iterdir() if p.is_file()}==before
        assert not list(root.glob('.fourth-down-import-*'))


@pytest.mark.parametrize('name,kind', [('../CNAME',tarfile.REGTYPE),('/index.html',tarfile.REGTYPE),
    ('assets/link',tarfile.SYMTYPE),('assets/hardlink',tarfile.LNKTYPE),('index.html',tarfile.REGTYPE),
    ('CNAME',tarfile.REGTYPE),('assets/../../styles.css',tarfile.REGTYPE)])
def test_unsafe_archive_never_changes_website(tmp_path,name,kind):
    root=portfolio(tmp_path);archive=tmp_path/'bad.tgz';sha=bundle(archive,extra=(name,kind))
    with pytest.raises(ValueError):install(archive,sha,root)
    assert not (root/'fourth-down').exists()
    assert (root/'CNAME').read_text()=='thomashoward.dev'


def test_bad_digest_wrong_domain_and_local_edits_fail_closed(tmp_path):
    root=portfolio(tmp_path);archive=tmp_path/'good.tgz';sha=bundle(archive)
    with pytest.raises(ValueError,match='checksum'):read_archive(archive,'0'*64)
    (root/'CNAME').write_text('different.example')
    with pytest.raises(ValueError,match='existing'):install(archive,sha,root)
    (root/'CNAME').write_text('thomashoward.dev');install(archive,sha,root)
    (root/'fourth-down/assets/app.js').write_text('Local edit')
    with pytest.raises(ValueError,match='checksum'):install(archive,sha,root)
    assert (root/'fourth-down/assets/app.js').read_text()=='Local edit'


def test_result_publication_can_cross_30mb_without_pruning_history(tmp_path):
    # Reproduce the production boundary: old immutable versions fit, but adding
    # the next result snapshot must not strand a verified final before install.
    retained = {f'data/operations/operations-{i}.json': b' ' * 4_000_000 for i in range(7)}
    root = portfolio(tmp_path)
    old = tmp_path/'before.tgz'
    install(old, bundle(old, retained=retained), root)
    retained['data/operations/operations-final.json'] = b' ' * 4_000_000
    new = tmp_path/'final.tgz'
    checksum = bundle(new, retained=retained)
    files, _ = read_archive(new, checksum)
    assert sum(map(len, files.values())) > 30_000_000
    install(new, checksum, root)
    assert all((root/'fourth-down'/name).read_bytes() == body for name, body in retained.items())
    assert (root/'index.html').read_text() == 'Existing portfolio'


def test_compressed_archive_still_obeys_expanded_budget_before_install(tmp_path, monkeypatch):
    from scripts import portfolio_artifact
    root = portfolio(tmp_path)
    archive = tmp_path/'oversized.tgz'
    checksum = bundle(archive, retained={'data/operations/large.json': b' ' * 100_000})
    monkeypatch.setattr(portfolio_artifact, 'MAX_BYTES', 50_000)
    assert archive.stat().st_size < portfolio_artifact.MAX_BYTES
    with pytest.raises(ValueError, match='Archive exceeds the portfolio size budget'):
        install(archive, checksum, root)
    assert not (root/'fourth-down').exists()
    assert (root/'index.html').read_text() == 'Existing portfolio'


def test_static_budget_failure_reports_actual_and_allowed_sizes(tmp_path, monkeypatch):
    from scripts import portfolio_artifact
    archive = tmp_path/'checked.tgz'
    files, receipt = read_archive(archive, bundle(archive))
    total = sum(map(len, files.values()))
    monkeypatch.setattr(portfolio_artifact, 'MAX_BYTES', total - 1)
    with pytest.raises(ValueError, match=rf'{total} > {total - 1} bytes'):
        portfolio_artifact.validate(files, receipt)
