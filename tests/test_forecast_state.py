"""Fresh-runner handoff and partial-publication protection, without network or model fit."""
import json
from pathlib import Path
from unittest.mock import patch

import pytest
from ml import current_source
from ml.current_source import timestamp
from ml.rc1_operations import synthetic_source
from ml.refresh import refresh
from scripts.forecast_state import restore, save


def test_fresh_runner_roundtrip_and_idempotency(tmp_path):
    working = tmp_path/'working'
    source, _ = synthetic_source(working)
    with patch.object(current_source, 'ROOT', working):
        refresh(source, now=timestamp('2026-09-05T13:00:00Z'),
                current_directory=working/'web/public/data/current', operations_directory=working/'web/public/data/operations')
    receipt = save(2026, working, timestamp('2026-09-05T14:00:00Z'))
    fresh = tmp_path/'fresh'; (fresh/'ops').mkdir(parents=True)
    for path in (working/'ops').iterdir(): (fresh/'ops'/path.name).write_bytes(path.read_bytes())
    first = restore(2026, fresh); second = restore(2026, fresh)
    assert first['restored'] == receipt['files'] and second['restored'] == 0
    assert not (fresh/'web/public/data/current/latest.json').exists()
    corrupt = fresh/'ops'/receipt['file']; corrupt.write_bytes(corrupt.read_bytes()+b'bad')
    with pytest.raises(ValueError, match='checksum'): restore(2026, fresh)


def test_missing_retained_evidence_is_not_backfilled(tmp_path):
    directory=tmp_path/'web/public/data/current'; directory.mkdir(parents=True)
    (directory/'forecast-2026-existing.json').write_text('{}')
    with pytest.raises(ValueError, match='original evidence'):restore(2026,tmp_path)
    assert restore(2027,tmp_path)['new_season']
    with pytest.raises(ValueError, match='Protected'):restore(2025,tmp_path)


def test_partial_publication_cannot_seal_state(tmp_path):
    from ml import refresh as runner
    source,_=synthetic_source(tmp_path)
    kwargs={'current_directory':tmp_path/'web/public/data/current','operations_directory':tmp_path/'web/public/data/operations'}
    with patch.object(current_source,'ROOT',tmp_path):
        refresh(source,now=timestamp('2026-09-05T13:00:00Z'),**kwargs)
        save(2026,tmp_path,timestamp('2026-09-05T13:01:00Z'))
        before={p.name:p.read_bytes() for p in (tmp_path/'ops').iterdir()}
        with patch.object(runner,'publish_operations',side_effect=OSError('Interrupted runner')):
            with pytest.raises(OSError):refresh(source,now=timestamp('2026-09-05T13:02:00Z'),**kwargs)
        with pytest.raises(ValueError,match='Mixed'):save(2026,tmp_path,timestamp('2026-09-05T13:03:00Z'))
        assert before=={p.name:p.read_bytes() for p in (tmp_path/'ops').iterdir()}
