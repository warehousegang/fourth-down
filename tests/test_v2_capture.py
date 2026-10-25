"""Synthetic event-time/ledger tests and real-shaped archived-V1 verification; no fitting."""
import copy
import json
from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta

import pytest

from ml.current_source import canonical, iso, normalize, sha, timestamp
from ml.v2_capture import (Ledger, config, coverage, cutoff, decision_record, finalize, identity,
                           infer, key, phase, require_activation, schedule_changes, select_v1, stage)
from test_evidence_bundle import payload, archive
from test_v2_prospective import fixture, csv_bytes, schedule_rows


@pytest.fixture
def archived(payload):
    raw,r=archive(payload)
    r.update(repository='warehousegang/thomashowarddev',commit='a'*40,
             commit_at='2026-09-05T14:01:00Z',retrieved_at='2026-11-01T15:35:00Z',
             path='.fourth-down-state/forecast-evidence-2026.zip')
    return raw,r


def inputs():
    c=fixture()
    rows=schedule_rows(c)
    rows[-1]['game_time']='2026-11-01T17:00:00Z'
    c['schedule']=(csv_bytes(rows),dict(c['schedule'][1]))
    for kind,(raw,r) in c.items():
        r.update(raw_sha256=sha(raw),retrieved_at='2026-11-01T15:35:00Z')
    g=normalize(c['schedule'][0],2026,full_coverage=False)[-1]
    return c,g


@pytest.mark.parametrize('kickoff',[
    '2026-10-30T00:15:00Z', # Thursday evening EDT
    '2026-11-01T14:30:00Z', # International Sunday, DST changed
    '2026-11-01T18:00:00Z','2026-11-01T21:05:00Z','2026-11-02T01:20:00Z',
    '2026-11-03T01:15:00Z', # Monday
    '2026-11-04T22:37:00Z', # Wednesday odd-minute kickoff
    '2026-12-26T18:00:00Z' # Saturday
])
def test_every_kickoff_drives_utc_windows(kickoff):
    _,g=inputs();g.update(kickoff=kickoff)
    t=cutoff(g)
    assert phase(g,t-timedelta(minutes=31))=='pending'
    assert phase(g,t-timedelta(minutes=30))=='stage'
    assert phase(g,t-timedelta(microseconds=1))=='stage'
    assert phase(g,t)=='finalize'
    assert phase(g,t+timedelta(minutes=15))=='finalize'
    assert phase(g,t+timedelta(minutes=15,microseconds=1))=='missed_cutoff'


def test_gate_and_rehearsal_exclusion(monkeypatch):
    import ml.v2_capture as capture
    disabled=dict(config(),enabled=False,activation_approved=False)
    monkeypatch.setattr(capture,'config',lambda:disabled)
    assert not capture.config()['enabled'] and not capture.config()['activation_approved']
    with pytest.raises(PermissionError): require_activation()
    _,g=inputs();g['kickoff']=iso(timestamp(config()['activation_at'])+timedelta(hours=1))
    assert phase(g,timestamp(config()['activation_at']))=='before_activation'


def test_sealed_cutoff_delayed_and_idempotent(tmp_path,archived):
    c,g=inputs();ledger=Ledger(tmp_path)
    s=stage(ledger,c,*archived,g,timestamp('2026-11-01T15:36:00Z'),synthetic=True)
    r=finalize(ledger,g,timestamp('2026-11-01T16:04:00Z'),synthetic=True,schedule_observed_at='2026-11-01T16:03:00Z')
    assert r['v2'] and r['v1'] is None and r['pair_category']=='v2_only'
    assert r['finalization_delay_seconds']==240 and r['cutoff']=='2026-11-01T16:00:00+00:00'
    assert not r['scorecard_eligible']
    before={str(p):p.read_bytes() for p in tmp_path.rglob('*') if p.is_file()}
    assert finalize(ledger,g,timestamp('2026-11-01T18:00:00Z'),synthetic=True)==r
    assert {str(p):p.read_bytes() for p in tmp_path.rglob('*') if p.is_file()}==before
    assert ledger.read(s['sources']['pbp']['object'])==c['pbp'][0]


@pytest.mark.parametrize('minute,expected',[(0,'no_sealed_pre_cutoff_capture'),(16,'missed_cutoff'),(60,'missed_cutoff')])
def test_missed_or_delayed_capture_no_backfill(tmp_path,minute,expected):
    _,g=inputs();r=finalize(Ledger(tmp_path),g,cutoff(g)+timedelta(minutes=minute),synthetic=True,schedule_observed_at=iso(cutoff(g)))
    assert r['exclusion']==expected and r['v2'] is None


def test_outage_cannot_reuse_without_current_schedule_check(tmp_path,archived):
    c,g=inputs();l=Ledger(tmp_path)
    stage(l,c,*archived,g,timestamp('2026-11-01T15:36:00Z'),synthetic=True)
    assert finalize(l,g,cutoff(g),synthetic=True)['exclusion']=='schedule_not_rechecked_at_finalization'


@pytest.mark.parametrize('kind',['schedule','pbp','prior'])
def test_at_cutoff_data_rejected(tmp_path,archived,kind):
    c,g=inputs();c[kind][1]['retrieved_at']=iso(cutoff(g))
    with pytest.raises(ValueError): stage(Ledger(tmp_path),c,*archived,g,cutoff(g)-timedelta(seconds=1),synthetic=True)


def test_missing_efficiency_is_v2_exclusion(archived):
    c,g=inputs();rows=schedule_rows(c);rows[0]['phase']='SCHEDULED';rows[0]['home_score']='';rows[0]['visitor_score']=''
    raw=csv_bytes(rows);c['schedule']=(raw,dict(c['schedule'][1],raw_sha256=sha(raw)))
    r=decision_record(g,cutoff(g),cutoff(g),c,*archived,synthetic=True)
    assert r['v2'] is None and 'Missing required' in r['v2_exclusions'][0]


def test_schedule_change_voids_without_overwriting(tmp_path,archived):
    c,g=inputs();l=Ledger(tmp_path)
    stage(l,c,*archived,g,timestamp('2026-11-01T15:36:00Z'),synthetic=True)
    r=finalize(l,g,cutoff(g),synthetic=True,schedule_observed_at=iso(cutoff(g)))
    moved=dict(g,kickoff='2026-11-02T17:00:00Z',day='2026-11-02')
    before=(tmp_path/'decisions'/f'{key(g)}.json').read_bytes()
    v=schedule_changes(l,[moved],timestamp('2026-11-01T16:10:00Z'))
    assert v and v[0]['invalidated_identity']==key(g)
    assert (tmp_path/'decisions'/f'{key(g)}.json').read_bytes()==before
    assert schedule_changes(l,[moved],timestamp('2026-11-01T16:11:00Z'))==v
    assert key(moved)!=key(g) and phase(moved,timestamp('2026-11-01T16:10:00Z'))=='pending'
    assert coverage([g],cutoff(g),[r],v)['state_counts']=={'void_schedule_change':1}


def test_unconfirmed_postponed_and_coverage():
    _,g=inputs();unknown=dict(g,kickoff=None);postponed=dict(g,phase='POSTPONED',id='ngs-2026-103')
    report=coverage([unknown,postponed],cutoff(g))
    assert report['total_games']==2
    assert report['state_counts']=={'unconfirmed_kickoff':1,'not_scheduled':1}


def test_immutable_concurrent_object_and_collision(tmp_path):
    l=Ledger(tmp_path)
    with ThreadPoolExecutor(max_workers=4) as pool: result=list(pool.map(l.blob,[b'fixed']*8))
    assert len(set(result))==1
    with pytest.raises(ValueError,match='collision'): l.put(result[0],b'different')
    (tmp_path/result[0]).write_bytes(b'corrupt')
    with pytest.raises(ValueError,match='Corrupt'): l.read(result[0])


def test_actual_v1_selected_from_existing_bytes_only(archived,payload,monkeypatch):
    raw,r=archived;r=dict(r,retrieved_at='2026-09-05T14:02:00Z')
    source=json.loads(next(b for n,b in payload.items() if '/snapshot-' in n))
    target=source['games'][0]
    # Fail if pairing tries to generate a V1 forecast or publish anything.
    import ml.current
    monkeypatch.setattr(ml.current,'generate',lambda *a,**k:pytest.fail('V1 regeneration'))
    selected,errors=select_v1(raw,r,target,timestamp('2026-09-06T16:00:00Z'))
    assert not errors and selected
    original=json.loads(next(b for n,b in payload.items() if '/current/forecast-' in n))
    g=next(g for g in original['games'] if g['id']==target['id'])
    assert selected['generated_at']==g['generated_at'] and selected['home_probability']==g['home_probability']
    assert selected['evaluation_cutoff']=='2026-09-06T16:00:00+00:00'
    assert select_v1(raw,dict(r,retrieved_at='2026-09-06T16:00:00Z'),target,timestamp('2026-09-06T16:00:00Z'))[0] is None
    assert select_v1(raw,r,dict(target,home=target['away'],away=target['home']),timestamp('2026-09-06T16:00:00Z'))[0] is None
    with pytest.raises(ValueError): select_v1(raw+b'x',r,target,timestamp('2026-09-06T16:00:00Z'))


def test_disabled_tick_does_not_touch_network_or_storage(tmp_path,monkeypatch):
    from scripts import v2_shadow_tick
    import ml.v2_capture as capture
    disabled=dict(config(),enabled=False,activation_approved=False)
    monkeypatch.setattr(capture,'config',lambda:disabled)
    monkeypatch.setattr(v2_shadow_tick,'acquire',lambda:pytest.fail('Network before approval'))
    with pytest.raises(PermissionError): v2_shadow_tick.tick(tmp_path/'absent')
    assert not (tmp_path/'absent').exists()


def test_git_state_persistence_is_add_only_and_rejects_stale_writer(tmp_path):
    import subprocess
    from scripts.v2_shadow_state import append_state
    def git(path,*args):
        return subprocess.check_output(['git','-C',str(path),*args],text=True,stderr=subprocess.DEVNULL).strip()
    remote=tmp_path/'remote.git';remote.mkdir();git(remote,'init','--bare')
    a=tmp_path/'a';a.mkdir();git(a,'init','-b','v2-shadow-state')
    git(a,'config','user.email','test@example.invalid');git(a,'config','user.name','Test')
    (a/'README').write_text('Synthetic isolated ledger')
    git(a,'add','.');git(a,'commit','-m','Initialize');git(a,'remote','add','origin',str(remote));git(a,'push','origin','HEAD')
    b=tmp_path/'b';subprocess.run(['git','clone','-q','-b','v2-shadow-state',str(remote),str(b)],check=True)
    git(b,'config','user.email','test@example.invalid');git(b,'config','user.name','Test')
    one=tmp_path/'one';l=Ledger(one);l.blob(b'one')
    assert append_state(a,one)['changed']
    assert not append_state(a,one)['changed']
    two=tmp_path/'two';Ledger(two).blob(b'two')
    with pytest.raises(subprocess.CalledProcessError): append_state(b,two)
    assert git(remote,'rev-parse','refs/heads/v2-shadow-state')==git(a,'rev-parse','HEAD')
    (one/'objects'/sha(b'one')).write_bytes(b'changed')
    with pytest.raises(ValueError,match='mutation'): append_state(a,one)


def test_real_runner_requires_stage_commit_before_cutoff(tmp_path,archived,monkeypatch):
    import ml.v2_capture as capture
    c,g=inputs();l=Ledger(tmp_path)
    s=stage(l,c,*archived,g,timestamp('2026-11-01T15:36:00Z'),synthetic=True)
    # Synthetic fixtures only: exercise the prospective persistence gate without acquisition.
    monkeypatch.setattr(capture,'require_activation',lambda:None)
    late={sha(canonical(s)):{'commit':'b'*40,'committed_at':iso(cutoff(g))}}
    r=finalize(l,g,cutoff(g),schedule_observed_at=iso(cutoff(g)),persisted_stages=late)
    assert r['exclusion']=='no_sealed_pre_cutoff_capture' and not r['scorecard_eligible']


def test_github_temp_is_accepted_only_for_hosted_isolated_root(tmp_path,monkeypatch):
    import ml.v2_capture as capture
    # ROOT-relative public assets stay forbidden even if a misconfigured runner points there.
    monkeypatch.setenv('GITHUB_ACTIONS','true')
    monkeypatch.setenv('RUNNER_TEMP',str(capture.ROOT/'web/public'))
    with pytest.raises(ValueError,match='isolated'): Ledger(capture.ROOT/'web/public/forbidden-shadow')


def test_missed_v2_capture_preserves_verified_v1_only_coverage(tmp_path,archived,monkeypatch):
    import ml.v2_capture as capture
    c,g=inputs();l=Ledger(tmp_path)
    stage(l,c,*archived,g,timestamp('2026-11-01T15:36:00Z'),synthetic=True)
    # Pair selection itself is separately tested against complete synthetic archive bytes.
    original={'game_id':g['id'],'home_probability':0.61,'generated_at':'2026-10-31T12:00:00Z'}
    monkeypatch.setattr(capture,'select_v1',lambda *a:(original,[]))
    r=finalize(l,g,cutoff(g)+timedelta(minutes=16),synthetic=True)
    assert r['exclusion']=='missed_cutoff' and r['v1']==original and r['v2'] is None
    assert r['pair_category']=='v1_only' and not r['scorecard_eligible']


@pytest.mark.parametrize('state',['FINAL','IN_PROGRESS'])
def test_daily_recovery_reports_missed_games_after_kickoff(state):
    _,g=inputs();g['phase']=state
    assert phase(g,timestamp(g['kickoff'])+timedelta(hours=4))=='missed_cutoff'
