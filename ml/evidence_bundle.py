"""Bounded local source/forecast evidence handoff; no network or pointer restoration."""
import argparse
import io
import json
import os
import re
import stat
import tempfile
import zipfile
from datetime import datetime, timezone
from pathlib import Path

from ml.data import ROOT
from ml.current import frozen_model
from ml.current_source import DOWNLOAD, canonical, check_season, iso, normalize, sha, timestamp
from ml.lifecycle import input_verification, validate_snapshot, verify_forecast

MAX_FILES = 4096
MAX_ENTRY_BYTES = 5_000_000
MAX_TOTAL_BYTES = 128 * 1024 * 1024
MAX_ARCHIVE_BYTES = 64 * 1024 * 1024
MAX_RATIO = 200
HEX = r"[0-9a-f]{64}"


def strict_json(body):
    def pairs(values):
        result = {}
        for key, value in values:
            if key in result:
                raise ValueError("Duplicate JSON key")
            result[key] = value
        return result
    def invalid(value):
        raise ValueError("Nonfinite JSON value: " + value)
    return json.loads(body, object_pairs_hook=pairs, parse_constant=invalid)


def allowed_path(name, season):
    check_season(season)
    if not isinstance(name, str) or not name or name != name.strip():
        raise ValueError("Invalid evidence path")
    patterns = (rf"data/current/{season}/raw-({HEX})\.csv", rf"data/current/{season}/snapshot-({HEX})\.json",
                rf"web/public/data/current/forecast-{season}-({HEX})\.json", rf"web/public/data/operations/operations-({HEX})\.json",
                rf"data/results/{season}/raw-({HEX})\.rds", rf"data/results/{season}/observation-({HEX})\.json")
    for pattern in patterns:
        matched = re.fullmatch(pattern, name)
        if matched:
            return matched.group(1)
    raise ValueError("Unsafe, protected-season or unsupported evidence path: " + name)


def destination(root, name):
    """Reject any existing symlink or non-directory ancestor inside the chosen root."""
    root = Path(root).absolute()
    if root.is_symlink():
        raise ValueError("Evidence root cannot be a symlink")
    target = root
    for part in Path(name).parts:
        target = target / part
        if target.is_symlink():
            raise ValueError("Symlink destination is forbidden")
        if target != root / name and target.exists() and not target.is_dir():
            raise ValueError("Non-directory evidence ancestor")
    return target


def validate_payload(payload, season, created_at):
    """All bytes and dependencies validated before any destination write."""
    check_season(season)
    now = timestamp(created_at)
    if not payload or len(payload) > MAX_FILES:
        raise ValueError("Evidence bundle must contain 1–4096 files")
    if sum(len(body) for body in payload.values()) > MAX_TOTAL_BYTES:
        raise ValueError("Evidence exceeds total size budget")
    objects, snapshots, forecasts, operations, results = {}, {}, {}, [], {}
    for name, body in sorted(payload.items()):
        expected = allowed_path(name, season)
        if not isinstance(body, bytes) or len(body) > MAX_ENTRY_BYTES or sha(body) != expected:
            raise ValueError("Evidence content address or size mismatch: " + name)
        if name.endswith(".csv"):
            normalize(body, season)  # Checks every row's season before reading scores.
            continue
        if name.endswith('.rds'):
            continue  # Reparsed and matched through its observation below.
        data = strict_json(body)
        if not isinstance(data, dict) or data.get("season") != season or data.get("schema_version") != 1:
            raise ValueError("Mixed/protected season or unsupported evidence schema")
        objects[name] = data
        if '/results/' in name:
            from ml.result_source import validate_observation
            raw_name = f"data/results/{season}/raw-{data['raw_sha256']}.rds"
            allowed_path(raw_name,season)
            if raw_name not in payload:
                raise ValueError('Missing raw result evidence')
            results[sha(body)] = validate_observation(data,payload[raw_name],season,created_at)
        elif "/snapshot-" in name:
            validate_snapshot(data, now)
            if data.get("source_url") != f"{DOWNLOAD}/ngs_schedule_{season}.csv":
                raise ValueError("Unexpected source provenance URL")
            raw_name = f"data/current/{season}/raw-{data['raw_sha256']}.csv"
            allowed_path(raw_name, season)
            if raw_name not in payload or normalize(payload[raw_name], season) != data["games"]:
                raise ValueError("Missing raw source or normalized snapshot mismatch")
            snapshots[sha(body)] = data
        elif "/current/forecast-" in name:
            bundle = {"file": Path(name).name, "sha256": sha(body), "artifact": data}
            verify_forecast(bundle, season, now)
            forecasts[sha(body)] = bundle
        else:
            if data.get("mode") != "forecast-operations" or data.get("model_id") != frozen_model()["id"]:
                raise ValueError("Unsupported operations artifact")
            if timestamp(data["generated_at"]) > now:
                raise ValueError("Operations artifact created after bundle receipt")
            operations.append(data)
    if not snapshots:
        raise ValueError("Bundle requires original source evidence")
    for bundle in forecasts.values():
        artifact = bundle["artifact"]
        if artifact["snapshot_sha256"] not in snapshots:
            raise ValueError("Forecast original snapshot missing")
        for game in artifact["games"]:
            errors = input_verification(game, artifact, list(snapshots.values()))
            if errors:
                raise ValueError("Forecast source proof failed: " + "; ".join(errors))
    for artifact in operations:
        source = snapshots.get(artifact["source"]["snapshot_sha256"])
        if source is None or any(artifact["source"][key] != source[key] for key in ("retrieved_at", "source_updated_at", "source_url", "raw_sha256")):
            raise ValueError("Operations source proof missing or inconsistent")
        for row in artifact["schedule"]:
            if row["season"] != season or not row["id"].startswith(f"ngs-{season}-"):
                raise ValueError("Mixed season in operations schedule")
        for row in artifact["catalog"]:
            bundle = forecasts.get(row["artifact_sha256"])
            if bundle is None or row["artifact_file"] != bundle["file"] or row["season"] != season:
                raise ValueError("Operations forecast receipt dependency missing")
            game = next((g for g in bundle["artifact"]["games"] if g["id"] == row["game_id"]), None)
            if game is None or row["id"] != sha(canonical({"artifact_sha256": bundle["sha256"], "game_id": game["id"]})):
                raise ValueError("Operations forecast identity mismatch")
            for key in ("home", "away", "generated_at", "cutoff", "kickoff", "features", "factors", "history", "home_probability", "away_probability"):
                if row[key] != game[key]:
                    raise ValueError("Operations forecast receipt differs from original")
        for game in artifact["games"]:
            if game.get("season") != season or not game["id"].startswith(f"ngs-{season}-"):
                raise ValueError("Mixed season in operations game")
            if any(e.get("season") != season for e in game["evaluations"]):
                raise ValueError("Mixed season in outcome evaluations")
            if game.get('result_evidence'):
                observation = results.get(game['result_evidence'])
                if not observation or any(observation['game'][k] != game[k] for k in ('id','home','away','week','kickoff','status')):
                    raise ValueError('Supplemental outcome observation missing or mismatched')
            if game["result"] and game["result"]["snapshot_sha256"] in results:
                observed = results[game['result']['snapshot_sha256']]
                if (observed['game']['status'] != 'completed' or
                        any(game['result'][k] != observed['game'][k] for k in ('home_score','away_score')) or
                        game.get('result_evidence') != game['result']['snapshot_sha256'] or
                        game['result'].get('provider') != 'nflverse' or
                        any(game['result'].get(k) != observed[k] for k in ('raw_sha256','source_updated_at')) or
                        game['result']['observed_at'] != observed['observed_at'] or
                        game['result']['source_url'] != observed['source_url']):
                    raise ValueError('Final result differs from retained evidence')
            elif game["result"] and game["result"]["snapshot_sha256"] not in snapshots:
                raise ValueError("Result observation source is missing")
    return {"source_snapshots": len(snapshots), "forecast_versions": len(forecasts), "operations_versions": len(operations)}


def collect_payload(season, root=ROOT):
    check_season(season)
    root = Path(root).absolute()
    candidates = []
    for directory, pattern in ((f"data/current/{season}", "raw-*.csv"), (f"data/current/{season}", "snapshot-*.json"),
                               ("web/public/data/current", f"forecast-{season}-*.json"), ("web/public/data/operations", "operations-*.json"),
                               (f"data/results/{season}","raw-*.rds"), (f"data/results/{season}","observation-*.json")):
        folder = destination(root, directory)
        if folder.is_symlink():
            raise ValueError("Symlink evidence folder")
        candidates.extend(folder.glob(pattern))
    payload = {}
    for file in sorted(set(candidates)):
        name = file.relative_to(root).as_posix()
        allowed_path(name, season)
        path = destination(root, name)
        if not path.is_file() or path.stat().st_size > MAX_ENTRY_BYTES:
            raise ValueError("Evidence file type or size is invalid")
        body = path.read_bytes()
        if "/operations/" in name:
            recorded_season = strict_json(body).get("season")
            check_season(recorded_season)
            if recorded_season != season:
                continue  # Other allowed seasons are separate bundles.
        payload[name] = body
        if len(payload) > MAX_FILES or sum(map(len, payload.values())) > MAX_TOTAL_BYTES:
            raise ValueError("Evidence export exceeds bundle budget")
    return payload


def encode_bundle(payload, season, created_at):
    summary = validate_payload(payload, season, created_at)
    manifest = {"schema_version": 1, "mode": "fourth-down-evidence-bundle", "season": season, "created_at": created_at,
                "pointer_policy": "immutable-versions-only-regenerate-latest-after-import",
                "files": [{"path": name, "sha256": sha(body), "size": len(body)} for name, body in sorted(payload.items())]}
    manifest_bytes = canonical(manifest)
    if len(manifest_bytes) + sum(map(len, payload.values())) > MAX_TOTAL_BYTES:
        raise ValueError("Manifest plus evidence exceeds uncompressed size budget")
    stream = io.BytesIO()
    with zipfile.ZipFile(stream, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=6) as archive:
        for name, body in [("manifest.json", manifest_bytes), *sorted(payload.items())]:
            entry = zipfile.ZipInfo(name, date_time=(1980, 1, 1, 0, 0, 0))
            entry.create_system = 3
            entry.external_attr = (stat.S_IFREG | 0o644) << 16
            entry.compress_type = zipfile.ZIP_DEFLATED
            archive.writestr(entry, body)
    content = stream.getvalue()
    if len(content) > MAX_ARCHIVE_BYTES:
        raise ValueError("Compressed bundle exceeds archive budget")
    return content, {"season": season, "sha256": sha(content), "manifest_sha256": sha(manifest_bytes),
                     "files": len(payload), "bytes": len(content), **summary}


def export_bundle(season, output_directory=None, *, root=ROOT, created_at=None):
    created_at = created_at or iso(datetime.now(timezone.utc))
    payload = collect_payload(season, root)
    content, receipt = encode_bundle(payload, season, created_at)
    directory = Path(output_directory or Path(root) / "artifacts/evidence-bundles")
    directory.mkdir(parents=True, exist_ok=True)
    target = directory / f"evidence-{season}-{receipt['sha256']}.zip"
    if target.is_symlink() or target.exists() and target.read_bytes() != content:
        raise ValueError("Bundle output collision or symlink")
    if not target.exists():
        with target.open("xb") as stream:
            stream.write(content)
    return dict(receipt, bundle=str(target), pointers_restored=False)


def decode_bundle(content, season, expected_sha256, expected_manifest_sha256=None):
    check_season(season)
    if not re.fullmatch(HEX, expected_sha256) or len(content) > MAX_ARCHIVE_BYTES or sha(content) != expected_sha256:
        raise ValueError("Bundle checksum or archive size mismatch")
    with zipfile.ZipFile(io.BytesIO(content)) as archive:
        entries = archive.infolist()
        names = [i.filename for i in entries]
        if not 2 <= len(entries) <= MAX_FILES+1 or len(set(names)) != len(names) or names.count("manifest.json") != 1:
            raise ValueError("Duplicate, missing or excessive ZIP entries")
        total = 0
        for entry in entries:
            if entry.filename != "manifest.json":
                allowed_path(entry.filename, season)  # Reject protected/traversal names before extracting any member.
            mode = entry.external_attr >> 16
            if entry.is_dir() or stat.S_ISLNK(mode) or stat.S_IFMT(mode) not in (0, stat.S_IFREG) or entry.flag_bits & 1:
                raise ValueError("ZIP symlinks, directories, special or encrypted members are forbidden")
            if entry.compress_type not in (zipfile.ZIP_STORED, zipfile.ZIP_DEFLATED):
                raise ValueError("Unsupported ZIP compression")
            if entry.file_size > MAX_ENTRY_BYTES or entry.file_size/max(1, entry.compress_size) > MAX_RATIO:
                raise ValueError("ZIP entry exceeds size or compression ratio budget")
            total += entry.file_size
        if total > MAX_TOTAL_BYTES:
            raise ValueError("ZIP exceeds uncompressed size budget")
        manifest_bytes = archive.read("manifest.json")
        if expected_manifest_sha256 is not None and sha(manifest_bytes) != expected_manifest_sha256:
            raise ValueError("Manifest checksum mismatch")
        manifest = strict_json(manifest_bytes)
        if (manifest.get("schema_version") != 1 or manifest.get("mode") != "fourth-down-evidence-bundle"
                or manifest.get("season") != season or manifest.get("pointer_policy") != "immutable-versions-only-regenerate-latest-after-import"):
            raise ValueError("Unsupported or mixed/protected-season bundle manifest")
        files = manifest["files"]
        if not isinstance(files, list) or len(files) != len(entries)-1 or len({f["path"] for f in files}) != len(files):
            raise ValueError("Invalid manifest file inventory")
        if set(names) != {"manifest.json", *(f["path"] for f in files)}:
            raise ValueError("Unlisted ZIP members or missing evidence")
        payload = {}
        for record in files:
            name = record["path"]
            allowed_path(name, season)
            if type(record["size"]) is not int or record["size"] < 0 or record["size"] != archive.getinfo(name).file_size:
                raise ValueError("Manifest size mismatch")
            body = archive.read(name)
            if len(body) != record["size"] or sha(body) != record["sha256"]:
                raise ValueError("Manifest evidence checksum mismatch")
            payload[name] = body
    summary = validate_payload(payload, season, manifest["created_at"])
    return payload, {"season": season, "sha256": expected_sha256, "manifest_sha256": sha(manifest_bytes),
                     "files": len(payload), "bytes": len(content), **summary}


def import_bundle(path, season, expected_sha256, *, root=ROOT, expected_manifest_sha256=None):
    source = Path(path)
    if source.is_symlink() or not source.is_file() or source.stat().st_size > MAX_ARCHIVE_BYTES:
        raise ValueError("Bundle input type or archive size is invalid")
    payload, receipt = decode_bundle(source.read_bytes(), season, expected_sha256, expected_manifest_sha256)
    root = Path(root).absolute()
    targets = {}
    for name, body in payload.items():
        target = destination(root, name)
        if target.exists() and (not target.is_file() or target.read_bytes() != body):
            raise ValueError("Import would overwrite different existing evidence: " + name)
        targets[name] = target
    # Full archive + destination preflight completed before any import directory/file is written.
    # Exclusive final creation cannot overwrite concurrent writers; an I/O failure can leave
    # a subset of identical immutable versions, safely resumable by rerunning this import.
    written = 0
    for name, body in sorted(payload.items()):
        target = destination(root, name)
        if target.exists():
            if not target.is_file() or target.read_bytes() != body:
                raise ValueError("Concurrent evidence collision")
            continue
        target.parent.mkdir(parents=True, exist_ok=True)
        destination(root, name)
        temporary = None
        try:
            with tempfile.NamedTemporaryFile(prefix=".evidence-import-", dir=target.parent, delete=False) as stream:
                temporary = Path(stream.name)
                stream.write(body)
                stream.flush()
                os.fsync(stream.fileno())
            destination(root, name)
            try:
                os.link(temporary, target, follow_symlinks=False)  # Atomic no-overwrite publication.
                written += 1
            except FileExistsError:
                if target.is_symlink() or not target.is_file() or target.read_bytes() != body:
                    raise ValueError("Concurrent evidence collision")
        finally:
            if temporary is not None:
                temporary.unlink(missing_ok=True)
    return dict(receipt, restored=written, identical_existing=len(payload)-written, pointers_restored=False)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    out = sub.add_parser("export")
    out.add_argument("--season", required=True, type=int)
    out.add_argument("--output-directory")
    out.add_argument("--root", default=str(ROOT), help="Local checkout/evidence root")
    incoming = sub.add_parser("import")
    incoming.add_argument("bundle")
    incoming.add_argument("--season", required=True, type=int)
    incoming.add_argument("--sha256", required=True, help="Bundle checksum from trusted export receipt")
    incoming.add_argument("--manifest-sha256")
    incoming.add_argument("--root", default=str(ROOT), help="Local checkout/evidence root")
    args = parser.parse_args()
    if args.command == "export":
        receipt = export_bundle(args.season, args.output_directory, root=args.root)
    else:
        receipt = import_bundle(args.bundle, args.season, args.sha256, root=args.root, expected_manifest_sha256=args.manifest_sha256)
    print(json.dumps(receipt, indent=2))


if __name__ == "__main__":
    main()
