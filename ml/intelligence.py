"""Timestamped enrichment eligibility only. No network, fitting or probability changes."""
import json
import re
from datetime import datetime, timedelta, timezone
from urllib.parse import urlparse

EXTERNAL_DOMAINS = {"efficiency", "quarterback", "injuries", "weather", "developments", "travel"}
MAX_AGE_HOURS = {"efficiency": 192, "quarterback": 24, "injuries": 24, "weather": 12,
                 "developments": 168, "travel": 168}


def timestamp(value):
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        raise ValueError("Evidence timestamps must include a time zone")
    return parsed.astimezone(timezone.utc)


def eligible_evidence(records, *, game_id, team, season, cutoff, kickoff, approved_hosts=()):
    """Fail closed. Caller supplies reviewed hosts; empty approvals make all evidence unavailable.

    Metadata is an ingestion contract, not independent proof that a web claim is true. Retain
    source bytes/checksum in the reviewed snapshot. This function cannot fetch or trust a URL.
    """
    if season in (2024, 2025) or season < 2010:
        raise ValueError("Protected or unsupported evidence season")
    end, start = timestamp(cutoff), timestamp(kickoff)
    if end >= start:
        raise ValueError("Pregame cutoff must precede kickoff")
    if not isinstance(records, list) or len(records) > 100:
        raise ValueError("Evidence batch must be a bounded list of at most100records")
    accepted, rejected = [], []
    for record in records:
        reason = None
        if not isinstance(record, dict):
            rejected.append({"domain": "unknown", "reason": "Evidence must be an object"})
            continue
        try:
            if len(json.dumps(record, allow_nan=False)) > 16384:
                raise ValueError("Evidence record exceeds the size bound")
            domain = record["domain"]
            if domain not in EXTERNAL_DOMAINS:
                raise ValueError("Unknown enrichment domain")
            if record["game_id"] != game_id or record["team"] != team or record["season"] != season:
                raise ValueError("Evidence identity mismatch")
            url = urlparse(record["source_url"])
            if url.scheme != "https" or url.hostname not in approved_hosts or url.username or url.password:
                raise ValueError("Source is not approved")
            if record["license_reviewed"] is not True or record["verification"] != "verified":
                raise ValueError("Unverified evidence or source rights")
            if not re.fullmatch(r"[0-9a-f]{64}", record["source_sha256"]):
                raise ValueError("Missing source integrity")
            published, observed, retrieved, valid = [timestamp(record[k]) for k in
                ("published_at", "observed_at", "retrieved_at", "valid_until")]
            if not (published <= observed <= retrieved <= end and observed < end < valid):
                raise ValueError("Future, unordered, or expired evidence")
            if end - published > timedelta(hours=MAX_AGE_HOURS[domain]):
                raise ValueError("Stale evidence")
            if record["phase"] != "pregame":
                raise ValueError("Postgame evidence cannot enter pregame intelligence")
            value = record["value"]
            if not isinstance(value, dict) or not value:
                raise ValueError("Missing structured evidence")
            if domain == "quarterback" and (value.get("status") != "starter_confirmed" or not value.get("player_id")):
                raise ValueError("Starting quarterback is not confirmed")
            if domain == "injuries" and (value.get("availability") not in {"out", "doubtful", "questionable", "active"}
                                        or not value.get("player_id")):
                raise ValueError("Unknown injury availability")
            if domain == "weather" and (value.get("kind") != "forecast" or timestamp(value["valid_for"]) != start):
                raise ValueError("Weather must be a pregame forecast for the scheduled kickoff")
            if domain == "developments" and value.get("category") not in {"roster_transaction", "coaching_announcement", "schedule_change"}:
                raise ValueError("Unsupported news category; private-state inference is prohibited")
            accepted.append(dict(record, affects_probability=False))
        except (KeyError, TypeError, ValueError, AttributeError) as error:
            reason = str(error)
        if reason:
            rejected.append({"domain": record.get("domain", "unknown"), "reason": reason})
    # Conflicting source assertions remain unavailable, including conflicting starter reports.
    groups = {}
    for record in accepted:
        identity = (record["domain"], record["value"].get("player_id") if record["domain"] == "injuries" else None)
        groups.setdefault(identity, []).append(record)
    clean = []
    for (domain, _), group in groups.items():
        values = {json.dumps(row["value"], sort_keys=True, allow_nan=False) for row in group}
        if len(values) > 1:
            rejected.append({"domain": domain, "reason": "Conflicting verified source assertions"})
        else:
            clean.append(max(group, key=lambda row: timestamp(row["observed_at"])))
    return {"status": "available" if clean else "unavailable", "evidence": clean, "rejected": rejected,
            "probability_adjustment": None, "model_feature_enabled": False}
