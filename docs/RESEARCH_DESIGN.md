# Bounded research enrichment — design only

No LLM/API calls, agent jobs, background polling, or scheduled research are implemented. The prediction pipeline is deterministic and independent of this optional layer.

An owner-triggered run would take game_id, forecast_cutoff, allowed source domains and a small explicit budget (at most 12 URLs, 2 model calls, 5 minutes). These are proposed future limits, not an activated workflow. Sources: official team/league injury reports and roster releases; official depth charts with explicit confirmation for starting quarterbacks; official coaching announcements; a named official weather provider for the stadium location; verified team reporting with direct citations. Source-specific license/access review precedes implementation.

Suggested structured output:
```json
{
  "schema_version": 1,
  "game_id": "SOURCE_GAME_ID",
  "forecast_cutoff": "ISO8601_WITH_OFFSET",
  "retrieved_at": "ISO8601_WITH_OFFSET",
  "facts": [{
    "category": "injury|quarterback|roster|coaching|weather|team_news",
    "claim": "Short, source-grounded statement",
    "source_url": "https://OFFICIAL_SOURCE",
    "published_at": "ISO8601_WITH_OFFSET",
    "retrieved_at": "ISO8601_WITH_OFFSET",
    "verification": "verified|conflicted|stale|unavailable",
    "supporting_excerpt": "Minimal necessary excerpt",
    "applies_to_game_id": "SOURCE_GAME_ID"
  }],
  "unresolved": [],
  "probability_adjustment": null
}
```

Reject unknown team/player attribution, missing source timestamps, publications after the cutoff, URLs outside the allowlist, or uncited claims. Keep publication and retrieval time distinct. A live page retrieved today cannot establish historical availability. Do not convert questionable/out designation into invented starter status. Weather is a timestamped forecast, not observed postgame weather. A stale report cannot silently overwrite a newer official one. Conflicting official reports remain conflicted; speculation is separately labeled and excluded from facts. Empty results are a valid unavailable response.

Treat retrieved text as untrusted data, not instructions. Bound fetch sizes; no tools capable of arbitrary writes, messaging, purchases or credentials. No automatic publication. The LLM summarizes verified material; it cannot change model probabilities. Future model features need a versioned dataset, feature definition, leakage tests and separately approved evaluation. Research annotations display with citations and never masquerade as learned predictive factors.
