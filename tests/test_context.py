"""Current-context tests use synthetic data and committed artifacts; never live services."""
import copy
import csv
import io
import json
from datetime import timedelta

import pyarrow as pa
import pyarrow.parquet as pq
import pytest

from ml.context import (LICENSE, LICENSE_URL, ROOT, SOURCES, acquire, decode, generate, injuries_for,
                        load_receipt, performance_for, publish, quarterback_for, source_available)
from ml.current_source import canonical, iso, sha, timestamp

CUTOFF = "2026-10-24T14:00:00Z"
GENERATED = "2026-10-24T14:01:00Z"


def source(identity):
    tag, pattern = SOURCES[identity]
    return {"id": identity, "url": f"https://github.com/nflverse/nflverse-data/releases/download/{tag}/{pattern.format(season=2026)}",
            "source_updated_at": "2026-10-24T12:00:00Z", "retrieved_at": "2026-10-24T13:00:00Z",
            "sha256": "a"*64, "file": "raw", "license": LICENSE, "license_url": LICENSE_URL, "asset_id": 1}


def game(identity="ngs-2026-2", week=7, kickoff="2026-10-25T17:00:00Z", phase=""):
    return {"id": identity, "season": 2026, "week": week, "home": "DET", "away": "GB", "kickoff": kickoff,
            "day": kickoff[:10], "phase": phase, "validated": phase == "FINAL", "home_score": 21 if phase == "FINAL" else None,
            "away_score": 14 if phase == "FINAL" else None}


def schedule():
    return {"season": 2026, "source_updated_at": "2026-10-24T12:00:00Z", "retrieved_at": "2026-10-24T13:00:00Z",
            "source_url": "https://example.test/synthetic-2026.csv", "raw_sha256": "b"*64,
            "games": [game("ngs-2026-1", 6, "2026-10-18T17:00:00Z", "FINAL"), game()]}


def stats():
    return [{"season": "2026", "season_type": "REG", "week": 6, "game_id": "2026_06_GB_DET", "team": team,
             "opponent_team": "GB" if team == "DET" else "DET", "completions": "20", "attempts": "30",
             "passing_yards": "240", "carries": "20", "rushing_yards": "80", "passing_epa": "FUTURE_TRAINING_VINTAGE_NOT_USED"} for team in ("DET", "GB")]


def injury():
    return {"season": "2026", "season_type": "REG", "week": 7, "team": "DET", "gsis_id": "synthetic-player",
            "full_name": "Synthetic Player", "position": "QB", "report_status": "Questionable", "practice_status": "Limited",
            "report_primary_injury": "Synthetic test status"}


def depth():
    return {"dt": "2026-10-24T11:00:00Z", "team": "DET", "player_name": "Synthetic Player",
            "gsis_id": "synthetic-player", "espn_id": "test-1", "pos_abb": "QB", "pos_rank": 1}


def raw_csv(rows):
    output = io.StringIO()
    writer = csv.DictWriter(output, fieldnames=list(rows[0]))
    writer.writeheader(); writer.writerows(rows)
    return output.getvalue().encode()


def raw_depth(rows):
    output = io.BytesIO(); pq.write_table(pa.Table.from_pylist(rows), output)
    return output.getvalue()


def verified_source(identity, body):
    item = source(identity); item["sha256"] = sha(body)
    item["file"] = item["sha256"] + "-" + SOURCES[identity][1].format(season=2026)
    return item


def bundle():
    return {"schema_version": 1, "season": 2026, "sources": [source(i) for i in SOURCES]}, {
        "injuries": [injury()], "depth_charts": [depth()], "stats_team": stats()}


def test_context_generation_real_ratios_and_no_model_claim():
    receipt, decoded = bundle()
    artifact = generate(schedule(), receipt, decoded, CUTOFF, GENERATED)
    assert artifact["affects_probability"] is False
    assert "model" not in artifact and "probability" not in artifact["games"][0]
    side = artifact["games"][0]["teams"]["home"]
    assert side["injuries"]["status"] == "observed"
    assert side["injuries"]["report_published_at"] is None
    assert side["quarterback"]["confirmed_starter"] is None
    assert side["performance"]["metrics"]["offense"] == {"completion_rate": 20/30, "passing_yards_per_attempt": 8, "rushing_yards_per_attempt": 4}
    assert side["performance"]["completed_game_ids"] == ["ngs-2026-1"]
    assert "passing_epa" not in json.dumps(side)


@pytest.mark.parametrize("year", [2024,2025])
def test_protected_context_acquisition_rejected_before_network(monkeypatch, year):
    called = []
    monkeypatch.setattr("ml.context.download", lambda url: called.append(url))
    with pytest.raises(ValueError): acquire(year)
    assert not called


def test_context_sources_validate_year_before_football_values():
    rows = stats(); rows[0]["season"] = "2025"; rows[0]["attempts"] = "NEVER_PARSE"
    body = raw_csv(rows)
    with pytest.raises(ValueError, match="Mixed/protected"):
        decode(body, verified_source("stats_team", body), 2026)
    row = depth(); row["dt"] = "2026-01-04T11:00:00Z"
    body = raw_depth([row])
    with pytest.raises(ValueError, match="Mixed/protected"):
        decode(body, verified_source("depth_charts", body), 2026)


def test_depth_chart_filters_positions_after_year_validation():
    row = depth(); row["pos_abb"] = "WR"
    body = raw_depth([row, depth()])
    parsed = decode(body, verified_source("depth_charts", body), 2026)
    assert len(parsed) == 1 and parsed[0]["pos_abb"] == "QB"


def test_missing_or_duplicate_injury_reports_do_not_mean_healthy():
    result = injuries_for([], source("injuries"), game(), "DET", timestamp(CUTOFF))
    assert result["status"] == "unavailable" and not result["players"]
    result = injuries_for([injury(),injury()], source("injuries"), game(), "DET", timestamp(CUTOFF))
    assert result["status"] == "unavailable" and not result["players"]
    row = injury(); row["report_status"] = ""
    result = injuries_for([row], source("injuries"), game(), "DET", timestamp(CUTOFF))
    assert result["players"][0]["report_status"] == "Not supplied"


def test_unknown_starter_and_future_depth_report_not_inferred():
    row = depth(); row["dt"] = "2026-10-24T15:00:00Z"
    result = quarterback_for([row], source("depth_charts"), "DET", timestamp(CUTOFF))
    assert result["status"] == "unavailable" and result["confirmed_starter"] is None
    result = quarterback_for([depth()], source("depth_charts"), "DET", timestamp(CUTOFF))
    assert result["status"] == "observed" and result["confirmed_starter"] is None


def test_future_and_target_stats_cannot_enter_current_context():
    rows = stats()
    future = dict(rows[0], week=7, game_id="2026_07_GB_DET", passing_yards="99999", attempts="NEVER_PARSE")
    result = performance_for(rows+[future], source("stats_team"), schedule(), game(), "DET", timestamp(CUTOFF))
    assert result["status"] == "observed" and result["totals"]["offense"]["passing_yards"] == 240
    changed = schedule(); changed["games"][0]["kickoff"] = "2026-10-24T15:00:00Z"
    assert performance_for(rows, source("stats_team"), changed, game(), "DET", timestamp(CUTOFF))["status"] == "unavailable"


def test_missing_ambiguous_or_invalid_completed_statistics_fail_closed():
    for rows in [stats()[:1], stats()+stats()[:1], [dict(stats()[0], completions="31"),stats()[1]],
                 [dict(stats()[0], passing_yards="NaN"),stats()[1]]]:
        result = performance_for(rows, source("stats_team"), schedule(), game(), "DET", timestamp(CUTOFF))
        assert result["status"] == "unavailable" and result["metrics"] is None


def test_source_time_staleness_and_postkickoff_generation_boundaries():
    receipt, decoded = bundle()
    receipt["sources"][0]["retrieved_at"] = CUTOFF
    with pytest.raises(ValueError, match="before cutoff"):
        generate(schedule(), receipt, decoded, CUTOFF, GENERATED)
    receipt, decoded = bundle()
    assert generate(schedule(),receipt,decoded,CUTOFF,"2026-10-25T17:00:00Z")["games"] == []
    stale = source("injuries"); stale["source_updated_at"] = "2026-10-20T12:00:00Z"
    assert not source_available(stale,timestamp(CUTOFF))
    assert injuries_for([injury()],stale,game(),"DET",timestamp(CUTOFF))["status"] == "unavailable"
    mixed = schedule(); mixed["games"][0]["season"] = 2025
    with pytest.raises(ValueError,match="Mixed/protected"):
        generate(mixed,*bundle(),CUTOFF,GENERATED)


def test_receipt_integrity_paths_reproducibility_and_history_immutability(tmp_path):
    receipt, _ = bundle()
    bodies = {"injuries":raw_csv([injury()]),"depth_charts":raw_depth([depth()]),"stats_team":raw_csv(stats())}
    receipt["sources"] = [verified_source(identity,body) for identity,body in bodies.items()]
    for item in receipt["sources"]: (tmp_path/item["file"]).write_bytes(bodies[item["id"]])
    path = tmp_path/("receipt-"+sha(canonical(receipt))+".json");path.write_bytes(canonical(receipt))
    captured, decoded = load_receipt(path,2026)
    first = generate(schedule(),captured,decoded,CUTOFF,GENERATED)
    assert canonical(first) == canonical(generate(schedule(),captured,decoded,CUTOFF,GENERATED))
    target = publish(first,tmp_path/"public");original = target.read_bytes()
    later = dict(first,generated_at="2026-10-24T14:02:00Z")
    second = publish(later,tmp_path/"public")
    assert target != second and target.read_bytes() == original
    (tmp_path/receipt["sources"][0]["file"]).write_bytes(b"changed")
    with pytest.raises(ValueError,match="Unverified"):
        load_receipt(path,2026)


def test_acquisition_is_bounded_and_uses_exact_three_season_assets(monkeypatch,tmp_path):
    rows = {"injuries": raw_csv([injury()]), "depth_charts": raw_depth([depth()]), "stats_team": raw_csv(stats())}
    calls = []
    def fetch(url):
        calls.append(url)
        identity = next(key for key in SOURCES if "/"+key in url)
        if "api.github.com" in url:
            return canonical({"assets":[{"name":SOURCES[identity][1].format(season=2026), "size":len(rows[identity]),
                      "digest":"sha256:"+sha(rows[identity]),"browser_download_url":source(identity)["url"],
                      "updated_at":"2026-10-24T12:00:00Z","id":1}]})
        assert url == source(identity)["url"]
        return rows[identity]
    monkeypatch.setattr("ml.context.download",fetch)
    monkeypatch.setattr("ml.context.current_season", lambda now: 2026)
    path=acquire(2026,tmp_path)
    assert len(calls)==6 and path.is_file()
    assert load_receipt(path,2026)[0]["season"]==2026


def test_committed_context_has_temporal_provenance_and_no_probabilities():
    root=ROOT/"web/public/data/context"
    pointer=json.loads((root/"latest.json").read_text());raw=(root/pointer["file"]).read_bytes()
    assert sha(raw)==pointer["sha256"] and pointer["file"]=="context-"+sha(raw)+".json"
    artifact=json.loads(raw)
    assert artifact["affects_probability"] is False
    for item in artifact["sources"]:
        assert timestamp(item["source_updated_at"])<=timestamp(item["retrieved_at"])<timestamp(artifact["as_of"])
    for target in artifact["games"]:
        assert timestamp(artifact["as_of"])<=timestamp(artifact["generated_at"])<timestamp(target["kickoff"])
        for side in target["teams"].values():
            assert side["quarterback"]["confirmed_starter"] is None
            assert side["injuries"]["report_published_at"] is None
            assert all(identifier.startswith('ngs-2026-') and identifier!=target['id'] for identifier in side['performance']['completed_game_ids'])
            if side['performance']['metrics']:
                for group, values in side['performance']['totals'].items():
                    assert side['performance']['metrics'][group]['completion_rate']==values['completions']/values['attempts']


def test_receipt_cannot_coerce_season_or_escape_raw_directory(tmp_path):
    receipt, _ = bundle()
    receipt['season'] = 2026.0
    def write(value):
        body=canonical(value);path=tmp_path/('receipt-'+sha(body)+'.json');path.write_bytes(body);return path
    with pytest.raises(ValueError,match='season'):
        load_receipt(write(receipt),2026)
    receipt,_=bundle();receipt['sources'][0]['sha256']='../escape'
    with pytest.raises(ValueError,match='digest'):
        load_receipt(write(receipt),2026)


def test_depth_snapshot_timestamp_is_not_original_publication_proof():
    result=quarterback_for([depth()],source('depth_charts'),'DET',timestamp(CUTOFF))
    assert result['report_published_at'] is None
    assert result['source_recorded_at']==iso(timestamp(depth()['dt']))


def test_source_outage_preserves_published_context(monkeypatch):
    from ml.context import refresh_context
    pointer=ROOT/'web/public/data/context/latest.json';before=pointer.read_bytes()
    def unavailable(*args,**kwargs):raise OSError('Synthetic source outage')
    monkeypatch.setattr('ml.context.acquire',unavailable)
    with pytest.raises(OSError,match='outage'):
        refresh_context(schedule())
    assert pointer.read_bytes()==before


def test_provider_record_cannot_postdate_published_source_bytes():
    row=depth();row['dt']='2026-10-24T12:30:00Z'  # before retrieval, after asset publication
    result=quarterback_for([row],source('depth_charts'),'DET',timestamp(CUTOFF))
    assert result['status']=='unavailable' and not result['depth_chart']
    assert result['source_recorded_at'] is None
