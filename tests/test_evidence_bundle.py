"""Bounded bundle roundtrip and hostile-archive tests; synthetic 2026 data only."""
import copy
import csv
import io
import json
import stat
import zipfile
from pathlib import Path

import pytest

from ml.current import generate
from ml.current_source import DOWNLOAD, TEAMS, canonical, normalize, sha
from ml.evidence_bundle import (allowed_path, decode_bundle, encode_bundle, export_bundle,
                                import_bundle, validate_payload)
from ml.lifecycle import build_operations

CREATED = "2026-09-05T14:00:00+00:00"


@pytest.fixture
def payload():
    # 32-team circle schedule, 17 rounds, 272 games. No real or protected outcomes.
    teams = sorted(TEAMS)
    fields = ["season", "season_type", "week", "game_key", "game_id", "game_time", "game_date", "phase", "home_team_abbr", "visitor_team_abbr", "home_score", "visitor_score", "validated", "site_full_name"]
    stream = io.StringIO(); writer = csv.DictWriter(stream, fieldnames=fields); writer.writeheader()
    from datetime import date, timedelta
    for week in range(1, 18):
        day = date(2026, 9, 6) + timedelta(days=(week-1)*7)
        for i in range(16):
            identifier = str((week-1)*16+i+1)
            writer.writerow({"season": 2026, "season_type": "REG", "week": week, "game_key": identifier,
                "game_id": "synthetic-"+identifier, "game_time": f"{day}T17:00:00Z", "game_date": day.strftime("%m/%d/%Y"),
                "phase": "", "home_team_abbr": teams[i], "visitor_team_abbr": teams[31-i],
                "home_score": "", "visitor_score": "", "validated": "false", "site_full_name": "Synthetic venue"})
        teams = [teams[0], teams[-1], *teams[1:-1]]
    raw = stream.getvalue().encode()
    source = {"schema_version": 1, "season": 2026, "retrieved_at": "2026-09-05T12:00:00+00:00",
              "source_updated_at": "2026-09-05T11:00:00+00:00", "source_url": f"{DOWNLOAD}/ngs_schedule_2026.csv",
              "raw_sha256": sha(raw), "asset_id": 1, "license_url": "https://example.test/license", "source_name": "Synthetic",
              "games": normalize(raw, 2026)}
    forecast = generate(source, [], "2026-09-05T13:00:00+00:00", "2026-09-05T13:00:00+00:00")
    fb = canonical(forecast)
    bundle = {"file": f"forecast-2026-{sha(fb)}.json", "sha256": sha(fb), "artifact": forecast}
    operations = build_operations([bundle], [source], CREATED)
    sb, ob = canonical(source), canonical(operations)
    return {f"data/current/2026/raw-{sha(raw)}.csv": raw,
            f"data/current/2026/snapshot-{sha(sb)}.json": sb,
            f"web/public/data/current/{bundle['file']}": fb,
            f"web/public/data/operations/operations-{sha(ob)}.json": ob}


def archive(payload):
    return encode_bundle(payload, 2026, CREATED)


def rewrite(content, transform):
    with zipfile.ZipFile(io.BytesIO(content)) as source:
        members = [(item, source.read(item.filename)) for item in source.infolist()]
    members = transform(members)
    target = io.BytesIO()
    with zipfile.ZipFile(target, "w", compression=zipfile.ZIP_DEFLATED) as output:
        for info, body in members:
            output.writestr(info, body)
    return target.getvalue()


def import_bytes(content, root, tmp_path, expected=None):
    path = tmp_path / "bundle.zip"; path.write_bytes(content)
    return import_bundle(path, 2026, expected or sha(content), root=root)


def test_roundtrip_exact_bytes_no_pointers_and_reproducible_export(payload, tmp_path):
    content, receipt = archive(payload)
    assert archive(payload)[0] == content
    recovered, summary = decode_bundle(content, 2026, receipt["sha256"], receipt["manifest_sha256"])
    assert recovered == payload and summary["source_snapshots"] == summary["forecast_versions"] == summary["operations_versions"] == 1
    target = tmp_path / "restored"
    result = import_bytes(content, target, tmp_path)
    assert result["restored"] == 4 and not result["pointers_restored"]
    assert all((target/name).read_bytes() == body for name, body in payload.items())
    assert not list(target.rglob("latest.json"))
    repeated = import_bytes(content, target, tmp_path)
    assert repeated["restored"] == 0 and repeated["identical_existing"] == 4
    emitted = export_bundle(2026, tmp_path / "exports", root=target, created_at=CREATED)
    assert emitted["sha256"] == receipt["sha256"]


@pytest.mark.parametrize("name", ["../escape", "/tmp/escape", "C:/escape", "data/current/2026/../2025/a.json",
    "data/current/2025/raw-"+"a"*64+".csv", "web/public/data/current/latest.json", "web/public/data/operations/latest.json",
    "data\\current\\2026\\raw.csv", "data/current/2026/raw-unsafe.csv", "docs/FROZEN_MODEL.json"])
def test_unsafe_protected_and_pointer_paths_rejected_before_writes(payload, tmp_path, name):
    content, _ = archive(payload)
    malicious = rewrite(content, lambda members: [*members, (zipfile.ZipInfo(name), b"anything")])
    target = tmp_path / "restored"
    with pytest.raises(ValueError):
        import_bytes(malicious, target, tmp_path)
    assert not target.exists()


def test_duplicate_zip_member_rejected(payload, tmp_path):
    content, _ = archive(payload)
    with pytest.warns(UserWarning, match="Duplicate"):
        malicious = rewrite(content, lambda members: [*members, members[-1]])
    with pytest.raises(ValueError, match="Duplicate"):
        import_bytes(malicious, tmp_path / "restore", tmp_path)


def test_zip_symlink_rejected(payload, tmp_path):
    content, _ = archive(payload)
    def mutate(members):
        members[-1][0].create_system = 3
        members[-1][0].external_attr = (stat.S_IFLNK | 0o777) << 16
        return members
    with pytest.raises(ValueError, match="symlinks"):
        import_bytes(rewrite(content, mutate), tmp_path / "restore", tmp_path)


def test_archive_manifest_and_file_hashes_enforced(payload, tmp_path):
    content, receipt = archive(payload)
    with pytest.raises(ValueError, match="Bundle checksum"):
        decode_bundle(content, 2026, "0"*64)
    with pytest.raises(ValueError, match="Manifest checksum"):
        decode_bundle(content, 2026, receipt["sha256"], "0"*64)
    def alter(members):
        info, body = members[-1]
        members[-1] = (info, body.replace(b'"schema_version":1', b'"schema_version":2'))
        return members
    with pytest.raises(ValueError, match="checksum"):
        import_bytes(rewrite(content, alter), tmp_path / "restore", tmp_path)


def test_manifest_mixed_season_and_inventory_rejected(payload, tmp_path):
    content, _ = archive(payload)
    def alter(members):
        info, body = members[0]
        value = json.loads(body); value["season"] = 2025
        members[0] = (info, canonical(value)); return members
    target = tmp_path / "restore"
    with pytest.raises(ValueError, match="season"):
        import_bytes(rewrite(content, alter), target, tmp_path)
    assert not target.exists()
    def missing(members):
        return members[:-1]
    with pytest.raises(ValueError, match="inventory"):
        import_bytes(rewrite(content, missing), target, tmp_path)


def test_differing_destination_preflight_prevents_any_new_writes(payload, tmp_path):
    content, _ = archive(payload)
    target = tmp_path / "restore"
    last = target / sorted(payload)[-1]; last.parent.mkdir(parents=True); last.write_bytes(b"existing-different")
    with pytest.raises(ValueError, match="overwrite"):
        import_bytes(content, target, tmp_path)
    assert list(p for p in target.rglob("*") if p.is_file()) == [last]
    assert last.read_bytes() == b"existing-different"


def test_destination_symlinks_are_rejected_without_external_writes(payload, tmp_path):
    content, _ = archive(payload)
    target = tmp_path / "restore"; target.mkdir()
    outside = tmp_path / "outside"; outside.mkdir()
    (target/"data").symlink_to(outside, target_is_directory=True)
    with pytest.raises(ValueError, match="Symlink"):
        import_bytes(content, target, tmp_path)
    assert not list(outside.iterdir())


def test_source_export_symlink_rejected(payload, tmp_path):
    target = tmp_path / "source"; target.mkdir()
    outside = tmp_path / "outside"; outside.mkdir()
    (target/"data").symlink_to(outside, target_is_directory=True)
    with pytest.raises(ValueError, match="Symlink"):
        export_bundle(2026, tmp_path / "exports", root=target, created_at=CREATED)
    assert not (tmp_path/"exports").exists()


def test_limits_apply_before_restore(payload, tmp_path, monkeypatch):
    from ml import evidence_bundle as module
    content, _ = archive(payload)
    target = tmp_path / "restore"
    monkeypatch.setattr(module, "MAX_FILES", 2)
    with pytest.raises(ValueError, match="excessive"):
        import_bytes(content, target, tmp_path)
    assert not target.exists()
    monkeypatch.setattr(module, "MAX_FILES", 4096)
    monkeypatch.setattr(module, "MAX_TOTAL_BYTES", 100)
    with pytest.raises(ValueError, match="uncompressed"):
        import_bytes(content, target, tmp_path)
    assert not target.exists()


def test_high_compression_and_oversized_member_are_rejected(payload, tmp_path, monkeypatch):
    from ml import evidence_bundle as module
    content, _ = archive(payload)
    monkeypatch.setattr(module, "MAX_RATIO", 1)
    with pytest.raises(ValueError, match="compression ratio"):
        import_bytes(content, tmp_path / "restore", tmp_path)
    monkeypatch.setattr(module, "MAX_RATIO", 200)
    monkeypatch.setattr(module, "MAX_ENTRY_BYTES", 100)
    with pytest.raises(ValueError, match="size"):
        import_bytes(content, tmp_path / "restore", tmp_path)


def test_missing_raw_or_snapshot_dependencies_rejected(payload):
    missing_raw = {k: v for k,v in payload.items() if not k.endswith(".csv")}
    with pytest.raises(ValueError, match="raw source"):
        archive(missing_raw)
    missing_snapshot = {k: v for k,v in payload.items() if "/snapshot-" not in k}
    with pytest.raises(ValueError, match="source evidence"):
        archive(missing_snapshot)
    missing_forecast = {k: v for k,v in payload.items() if "/current/forecast-" not in k}
    with pytest.raises(ValueError, match="receipt dependency"):
        archive(missing_forecast)


def test_raw_source_mixed_season_is_rejected_before_score_normalization(payload):
    raw_name = next(k for k in payload if k.endswith(".csv"))
    raw = payload.pop(raw_name).replace(b"2026,REG", b"2025,REG", 1)
    payload[f"data/current/2026/raw-{sha(raw)}.csv"] = raw
    with pytest.raises(ValueError, match="Mixed, protected"):
        archive(payload)


def test_normalized_source_cannot_diverge_from_raw_capture(payload):
    path = next(k for k in payload if "/snapshot-" in k)
    value = json.loads(payload.pop(path)); value["games"][0]["home_score"] = 31
    body = canonical(value)
    payload[f"data/current/2026/snapshot-{sha(body)}.json"] = body
    with pytest.raises(ValueError, match="normalized snapshot mismatch"):
        archive(payload)


@pytest.mark.parametrize("season", [2023,2024,2025])
def test_protected_seasons_rejected_without_reading_bundle(tmp_path, season):
    with pytest.raises(ValueError, match="Protected"):
        decode_bundle(b"not a ZIP", season, "0"*64)


def test_existing_latest_pointers_never_restored_or_regressed(payload, tmp_path):
    content, _ = archive(payload)
    root = tmp_path/"restore"
    for folder in ("current", "operations"):
        directory=root/"web/public/data"/folder; directory.mkdir(parents=True)
        (directory/"latest.json").write_bytes(b"existing pointer")
    import_bytes(content,root,tmp_path)
    assert all((root/"web/public/data"/folder/"latest.json").read_bytes()==b"existing pointer" for folder in ("current","operations"))


def test_duplicate_manifest_json_key_is_rejected(payload, tmp_path):
    content, _ = archive(payload)
    def alter(members):
        info, body = members[0]
        members[0] = (info, body.replace(b'"season":2026', b'"season":2026,"season":2026'))
        return members
    with pytest.raises(ValueError, match="Duplicate JSON"):
        import_bytes(rewrite(content, alter), tmp_path/"restore", tmp_path)


def test_operations_receipt_cannot_change_forecast_probability(payload):
    path = next(k for k in payload if "/operations/" in k)
    value = json.loads(payload.pop(path))
    value["catalog"][0]["home_probability"] = .99
    body = canonical(value)
    payload[f"web/public/data/operations/operations-{sha(body)}.json"] = body
    with pytest.raises(ValueError, match="differs from original"):
        archive(payload)
