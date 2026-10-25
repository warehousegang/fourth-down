"""Separate immutable V2 research storage; no V1/public scorecard integration."""
import json
import os
import tempfile
from pathlib import Path

from ml.current_source import canonical, sha, timestamp
from ml.data import ROOT
from ml.v2_prospective import MODEL_SHA, RESULT_SHA, probability, require_activation

DIRECTORY = ROOT / "data/research-v2/prospective"


def validate(record):
    synthetic = record.get("mode") == "v2-shadow-simulation" and record.get("prospective") is False
    if not synthetic:
        require_activation()
        if record.get("mode") != "v2-shadow-forecast" or record.get("prospective") is not True:
            raise ValueError("Unsupported shadow record mode")
    if (record.get("model_sha256") != MODEL_SHA or record.get("result_sha256") != RESULT_SHA
            or record.get("season") != 2026 or record.get("schema_version") != 1
            or not timestamp(record["cutoff"]) <= timestamp(record["generated_at"]) < timestamp(record["kickoff"])):
        raise ValueError("Invalid shadow model/season/pregame timing")
    if record.get("status") == "available":
        p = probability(record["features"])
        if record["home_probability"] != p or record["away_probability"] != 1-p:
            raise ValueError("Shadow probability does not match frozen model")
    elif (record.get("status") != "unavailable" or not record.get("unavailable_reason")
          or record.get("home_probability") is not None or record.get("away_probability") is not None):
        raise ValueError("Unavailable shadow record cannot contain predictions")
    return synthetic


def _directory(path):
    path = Path(path).absolute()
    if any(p.is_symlink() for p in [path, *path.parents]):
        raise ValueError("No symlink ledger paths")
    path = path.resolve()
    if not (path == DIRECTORY.resolve() or DIRECTORY.resolve() in path.parents
            or (Path(tempfile.gettempdir()).resolve() in path.parents and ROOT.resolve() not in path.parents)):
        raise ValueError("V2 shadow storage must stay in its isolated research directory")
    return path


def write(record, directory=DIRECTORY):
    synthetic = validate(record)
    directory = _directory(directory) / ("simulations" if synthetic else "forecasts")
    # One immutable decision per game/scheduled kickoff, not one new entry per retry.
    identity = {k: record[k] for k in ("mode", "season", "game_id", "kickoff", "cutoff")}
    key, body = sha(canonical(identity)), canonical(record)
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / f"{key}.json"
    with tempfile.NamedTemporaryFile(dir=directory, prefix=".pending-", delete=False) as handle:
        temporary = Path(handle.name)
        handle.write(body); handle.flush(); os.fsync(handle.fileno())
    try:
        try:
            os.link(temporary, path, follow_symlinks=False)  # Complete file, atomic no-overwrite.
            fd = os.open(directory, os.O_RDONLY)
            try: os.fsync(fd)
            finally: os.close(fd)
        except FileExistsError:
            if path.is_symlink() or path.read_bytes() != body:
                raise ValueError("Immutable decision conflict; preserve the first record and investigate")
    finally:
        temporary.unlink(missing_ok=True)
    return {"file": str(path), "sha256": sha(body), "decision_id": key, "prospective": not synthetic}


def read(receipt):
    path = Path(receipt["file"])
    if path.is_symlink():
        raise ValueError("No symlink shadow records")
    body = path.read_bytes()
    if sha(body) != receipt["sha256"] or path.name != receipt["decision_id"] + ".json":
        raise ValueError("Shadow record checksum/identity mismatch")
    record = json.loads(body)
    validate(record)
    identity = {k: record[k] for k in ("mode", "season", "game_id", "kickoff", "cutoff")}
    if sha(canonical(identity)) != receipt["decision_id"]:
        raise ValueError("Shadow decision identity mismatch")
    return record


def existing(identity, directory=DIRECTORY):
    """Find an immutable decision before a retry tries to regenerate its timestamp."""
    require_activation()
    key = sha(canonical(identity))
    path = _directory(directory) / "forecasts" / f"{key}.json"
    if not path.exists():
        return None
    receipt = dict(file=str(path), sha256=sha(path.read_bytes()), decision_id=key, prospective=True)
    read(receipt)
    return receipt
