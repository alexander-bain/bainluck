"""#12577 — Server-side paired-metric register & venue probability blending.

Moves equivalent-venue blending for paired-metric sets (such as Kalshi #5165726 +
Polymarket #27988771 for Best Picture Nominee) onto the server via
``compute_aggregate_probability`` in ``app.utils.aggregation``, so the client
never computes its own unweighted two-venue average that could drift from
``SOURCE_WEIGHTS`` or the two-source divergence gate.

Unbending rules (#12577):
1. Stage 1 (e.g. Nominated / Make Playoffs) and Stage 2 (e.g. Wins / Win Title)
   are distinct propositions and are NEVER blended with each other.
2. Equivalent venue legs for the SAME stage (e.g. Kalshi + Polymarket for Stage 1)
   are blended on the server via ``compute_aggregate_probability``.
"""

from __future__ import annotations

import copy
import json
import math
from pathlib import Path
from types import SimpleNamespace
from typing import Any, Mapping

from app.utils.aggregation import compute_aggregate_probability

PAIRED_METRIC_REGISTER_PATH = (
    Path(__file__).resolve().parents[2]
    / "data"
    / "groupings"
    / "paired_metric_register.json"
)

SERVER_BLEND_AUTHORITY = "server:compute_aggregate_probability"
SINGLE_VENUE_AUTHORITY = "single_venue"


def _valid_prob(value: Any) -> float | None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    fval = float(value)
    if not math.isfinite(fval) or fval < 0.0 or fval > 1.0:
        return None
    return fval


def compute_server_venue_blend(
    kalshi_prob: float | None,
    polymarket_prob: float | None,
    *,
    kalshi_updated_at: str | None = None,
    polymarket_updated_at: str | None = None,
) -> tuple[float | None, str | None]:
    """Compute the server-side blend for a single stage across Kalshi and Polymarket.

    Delegates directly to :func:`app.utils.aggregation.compute_aggregate_probability`
    on a pre-game (`scheduled`) synthetic event container so ``SOURCE_WEIGHTS``,
    ``cap_weight_shares``, ``assess_divergence`` and ``_weighted_median`` govern
    the result with zero duplicate formula.
    """
    k_val = _valid_prob(kalshi_prob)
    p_val = _valid_prob(polymarket_prob)

    sources: dict[str, Any] = {}
    if k_val is not None:
        sources["kalshi"] = (
            {"value": k_val, "updated_at": kalshi_updated_at}
            if kalshi_updated_at
            else k_val
        )
    if p_val is not None:
        sources["polymarket"] = (
            {"value": p_val, "updated_at": polymarket_updated_at}
            if polymarket_updated_at
            else p_val
        )

    if not sources:
        return None, None

    synthetic_event = SimpleNamespace(
        win_probability_sources=sources,
        status="scheduled",
        espn_win_prob_home=None,
        opening_home_probability=None,
    )
    blended = compute_aggregate_probability(synthetic_event, event_status="scheduled")
    authority = (
        SERVER_BLEND_AUTHORITY
        if (k_val is not None and p_val is not None)
        else SINGLE_VENUE_AUTHORITY
    )
    return blended, authority


def hydrate_paired_metric_entry(raw_entry: Mapping[str, Any]) -> dict[str, Any]:
    """Hydrate a single paired-metric entry with server-blended stage probabilities."""
    entry = copy.deepcopy(dict(raw_entry))

    s1_k = _valid_prob(entry.get("stage_1_kalshi_probability"))
    s1_p = _valid_prob(entry.get("stage_1_polymarket_probability"))
    if s1_k is not None or s1_p is not None:
        blended_s1, auth_s1 = compute_server_venue_blend(
            s1_k,
            s1_p,
            kalshi_updated_at=entry.get("stage_1_kalshi_updated_at"),
            polymarket_updated_at=entry.get("stage_1_polymarket_updated_at"),
        )
        entry["stage_1_probability"] = blended_s1
        entry["stage_1_blend_authority"] = auth_s1
    elif _valid_prob(entry.get("stage_1_probability")) is not None:
        entry["stage_1_blend_authority"] = SINGLE_VENUE_AUTHORITY
    else:
        entry["stage_1_blend_authority"] = None

    s2_k = _valid_prob(entry.get("stage_2_kalshi_probability"))
    s2_p = _valid_prob(entry.get("stage_2_polymarket_probability"))
    if s2_k is not None or s2_p is not None:
        blended_s2, auth_s2 = compute_server_venue_blend(
            s2_k,
            s2_p,
            kalshi_updated_at=entry.get("stage_2_kalshi_updated_at"),
            polymarket_updated_at=entry.get("stage_2_polymarket_updated_at"),
        )
        entry["stage_2_probability"] = blended_s2
        entry["stage_2_blend_authority"] = auth_s2
    elif _valid_prob(entry.get("stage_2_probability")) is not None:
        entry["stage_2_blend_authority"] = SINGLE_VENUE_AUTHORITY
    else:
        entry["stage_2_blend_authority"] = None

    return entry


def hydrate_paired_metric_set(raw_set: Mapping[str, Any]) -> dict[str, Any]:
    """Hydrate a paired-metric set's entries with server-computed probabilities."""
    hydrated = copy.deepcopy(dict(raw_set))
    entries = [
        hydrate_paired_metric_entry(e)
        for e in (raw_set.get("entries") or [])
        if isinstance(e, Mapping)
    ]
    hydrated["entries"] = entries
    hydrated["blend_authority"] = SERVER_BLEND_AUTHORITY
    return hydrated


def load_paired_metric_register(
    register_path: Path | None = None,
) -> dict[str, Any]:
    """Load `paired_metric_register.json` and hydrate every set on the server."""
    target = register_path or PAIRED_METRIC_REGISTER_PATH
    raw = json.loads(target.read_text(encoding="utf-8"))
    out = copy.deepcopy(raw)
    out.setdefault("rules", {})["blend_authority"] = SERVER_BLEND_AUTHORITY
    raw_sets = raw.get("sets") or {}
    out["sets"] = {
        set_id: hydrate_paired_metric_set(set_data)
        for set_id, set_data in raw_sets.items()
        if isinstance(set_data, Mapping)
    }
    return out
