"""Static handoff integrity and rollback without publishing or reading new results."""
import io
import json
import tarfile
from pathlib import Path

import pytest
from scripts.portfolio_artifact import BASE, digest, install, read_archive


def bundle(path, version='one', extra=None):
    files = {name:b'{}' for name in ['CURRENT_DATA_NOTICE.txt', 'THIRD_PARTY_NOTICES.txt',
        'data/demo.json', 'data/current/latest.json', 'data/operations/latest.json',
        'data/research/latest.json', 'data/context/latest.json']}
    files['index.html'] = f'<script src="{BASE}assets/app.js"></script>'.encode()
    files['assets/app.js'] = version.encode()
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
