"""Synthetic verification of the limited real-input rehearsal; no real 2025 reads."""
import copy
import json
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pytest

from ml.current_source import canonical, normalize, sha, timestamp
from ml import v2_rehearsal as rehearsal
from ml.v2_prospective import _prior_scores, require_activation, simulate
from ml.v2_shadow_store import read, write
from test_v2_prospective import fixture, csv_bytes, game, schedule_rows, GENERATED


def record():
    synthetic=simulate(fixture(),'ngs-2026-102',GENERATED)
    for source in synthetic['sources']:source['synthetic']=False  # unit fixture for the real-mode validator
    return dict(synthetic,mode='v2-shadow-rehearsal',prospective=False,scorecard_eligible=False,
        authorization_sha256=rehearsal.AUTH_SHA,exposure_sha256=rehearsal.EXPOSURE_SHA,
        input_manifest_sha256=rehearsal.MANIFEST_SHA)


def test_authorization_grants_only_rehearsal_and_preserves_holdout():
    rehearsal.authorized()
    with pytest.raises(PermissionError,match='disabled'):require_activation()
    auth=json.loads(rehearsal.AUTH.read_bytes());exposure=json.loads(rehearsal.EXPOSURE.read_bytes())
    assert not auth['activation_approved'] and exposure['evaluation_authorized'] is False
    assert exposure['fitting_calibration_selection_authorized'] is False
    assert exposure['source']['season']==2025


def test_unapproved_manifest_rejected_before_capture_read(tmp_path):
    path=tmp_path/'manifest.json';path.write_text('{"prior":{"file":"2024-forbidden.csv"}}')
    with pytest.raises(ValueError,match='sealed approved'):rehearsal.load_captures(path)


@pytest.mark.parametrize('field,value',[('season',2024),('url','https://example.com/scores.csv'),
    ('synthetic',True),('raw_sha256','0'*64),('upstream_digest','sha256:'+'0'*64),
    ('retrieved_at','2026-09-27T16:00:00Z'),('source_updated_at','2026-09-28T00:00:00Z')])
def test_capture_scope_hashes_and_strict_cutoff(field,value):
    raw,receipt=fixture()['prior'];receipt=dict(receipt,synthetic=False,upstream_digest='sha256:'+sha(raw))
    receipt[field]=value
    with pytest.raises(ValueError):rehearsal.check_capture(raw,receipt,'prior',timestamp('2026-09-27T16:00:00Z'))


def test_current_capture_age_and_static_prior_are_distinct():
    for kind,(raw,r) in fixture().items():
        r=dict(r,synthetic=False,upstream_digest='sha256:'+sha(raw),retrieved_at='2026-09-21T05:00:00Z',source_updated_at='2026-09-21T04:00:00Z')
        if kind=='prior':rehearsal.check_capture(raw,r,kind,timestamp(GENERATED))
        else:
            with pytest.raises(ValueError,match='six-hour'):rehearsal.check_capture(raw,r,kind,timestamp(GENERATED))


def test_non_regular_scores_ignored_before_interpretation():
    rows=schedule_rows(fixture(),'prior');expected=_prior_scores(csv_bytes(rows),full_coverage=False)
    for kind in ['PRE','POST']:
        other=dict(rows[0],season_type=kind,home_score='MUST NOT READ',visitor_score='MUST NOT READ',game_key='bad',phase='bad')
        rows.append(other)
    assert _prior_scores(csv_bytes(rows),full_coverage=False)==expected
    rows[-1]['season']='2024'
    with pytest.raises(ValueError,match='only 2025'):_prior_scores(csv_bytes(rows),full_coverage=False)


def test_atomic_rehearsal_storage_and_retry_preserve_original(tmp_path):
    first=record()
    with ThreadPoolExecutor(max_workers=4) as pool:
        receipts=list(pool.map(lambda _:write(first,tmp_path),range(8)))
    assert all(r==receipts[0] for r in receipts)
    assert '/rehearsals/' in receipts[0]['file'] and receipts[0]['prospective'] is False
    assert read(receipts[0])==first and len(list(tmp_path.rglob('*.json')))==1
    with pytest.raises(ValueError,match='Immutable'):
        write(dict(first,generated_at='2026-09-27T16:06:00Z'),tmp_path)
    assert read(receipts[0])['generated_at']==GENERATED


@pytest.mark.parametrize('mutation',['scorecard','prospective','hash','probability','future-history','future-opponent','postkickoff'])
def test_rehearsal_cannot_be_promoted_tampered_or_leaky(tmp_path,mutation):
    r=record()
    if mutation=='scorecard':r['scorecard_eligible']=True
    elif mutation=='prospective':r['prospective']=True
    elif mutation=='hash':r['authorization_sha256']='0'*64
    elif mutation=='probability':r['home_probability']=.99
    elif mutation=='future-history':r['history']['home']['dates'].append('2026-09-27')
    elif mutation=='future-opponent':r['history']['home']['efficiency'][0]['opponent_history_dates'].append('2026-09-27')
    else:r['generated_at']=r['kickoff']
    with pytest.raises((PermissionError,ValueError)):write(r,tmp_path)


def test_run_uses_actual_clock_and_sealed_batch_is_idempotent(tmp_path,monkeypatch):
    captures=fixture()
    for raw,receipt in captures.values():receipt.update(synthetic=False,upstream_digest='sha256:'+sha(raw))
    games=normalize(captures['schedule'][0],2026,full_coverage=False)
    target=games[-1]
    # Fixed fixture clock is test-only; production run has no date/clock parameter.
    class Clock:
        @classmethod
        def now(cls,*_):return timestamp(GENERATED)
    monkeypatch.setattr(rehearsal,'datetime',Clock)
    monkeypatch.setattr(rehearsal,'OUTPUT',tmp_path)
    monkeypatch.setattr(rehearsal,'load_captures',lambda:captures)
    monkeypatch.setattr(rehearsal,'normalize',lambda *_:copy.deepcopy(games))
    monkeypatch.setattr(rehearsal,'prior_coverage',lambda *_:{'test_only':True})
    calls=[]
    def produce(*args):calls.append(args);return record()
    monkeypatch.setattr(rehearsal,'_record',produce)
    before=rehearsal.run();original=(tmp_path/'batch.json').read_bytes()
    again=rehearsal.run()
    assert before==again and (tmp_path/'batch.json').read_bytes()==original and len(calls)==1
    assert len(before['records'])==1 and len(before['exclusions'])==2


def test_rehearsal_public_writes_and_interruption_rejected(tmp_path,monkeypatch):
    with pytest.raises(ValueError,match='isolated'):write(record(),rehearsal.ROOT/'web/public/data/v2')
    import ml.v2_shadow_store as storage
    def fail(*_args,**_kwargs):raise OSError('interrupted')
    monkeypatch.setattr(storage.os,'link',fail)
    with pytest.raises(OSError):write(record(),tmp_path)
    assert not list(tmp_path.rglob('*.json')) and not list(tmp_path.rglob('.pending-*'))
