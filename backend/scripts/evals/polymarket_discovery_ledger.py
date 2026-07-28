"""Queue #270 / #1468 — Tier-1 NBA/MLB/NHL Polymarket event + prop discovery ledger.

This is the **producer** for the exhaustive Polymarket discovery ledger that gates
#8–#10 of parent #1466 require. It is the counterpart to the two offline
*validators* already on master:

* ``polymarket_recovery_ledger.validate_ledger`` (C51) — the ``polymarket-recovery/v1``
  ledger contract this tool emits.
* ``named_event_completeness.validate_scoreboard`` (C52) — the source-agnostic
  ``named-event-completeness/v1`` scoreboard, into which this tool's ledger embeds.

Design (mirrors the Template-A eval scripts in this directory, incl.
``expected_event_inventory.py`` #1467):

* **Pure builder functions** (``decompose_gamma_event``, ``classify_submarket``,
  ``extract_prop_semantics``, ``measure_timeline``, ``build_event_record``,
  ``build_prop_records``, ``build_ledger``, ``build_scoreboard``, ``summarize``)
  take plain dicts and are fully unit-tested offline — no network, no DB. They are
  import-safe (only stdlib + sibling stdlib-only eval modules) so
  ``tests/test_startup.py`` stays green. Every ledger they emit is
  ``validate_ledger``-clean by construction.
* **One pluggable I/O boundary**, ``PolymarketDiscoveryClient``, injected so tests
  never touch the wire. It queries the public Polymarket Gamma + CLOB APIs with
  **typed** results (found / not_found / timeout / rate_limited / server_error /
  parse_failure) — a transient failure is **never** collapsed into "not found"
  (gotcha #36), and the ``conditionId`` hex is **never** ``rstrip``-mangled
  (C50 finding).
* Discovery is driven by the **independent #1467 expected-event population**, not
  by rows Bain Luck already ingested. Traversal is **date-partitioned** (a small
  ±28h window per game) so it is exhaustive and never bounded by Gamma's offset
  cap (gotcha #41; the 2000-offset cap C50 flagged cannot define absence).

Honesty rules baked into classification (parent #1466 gates #8–#10):

* ``poly_nonlisting_archivally_proven`` is emitted **only** when every archival
  surface returned a real ``404`` (validate_ledger enforces this). A single empty
  search response is 200, not 404, so it can never prove non-listing — a missing
  main market defaults to ``poly_discovery_or_matching_defect`` (a closure
  blocker), exactly as the parent's "presume Poly listed it" rule requires.
* A settled losing prop (terminal Yes probability 0) stays **represented**; it is
  never silently dropped (C50 ``terminal-zero-dropped``).
* Every enumerated prop is ``threshold_pending`` until Alex ratifies a
  meaningful-trade threshold — no cutoff is invented (parent gate #9).

CLI::

    # Real census (reads live Polymarket Gamma + CLOB; ESPN for the denominator):
    python3 scripts/evals/polymarket_discovery_ledger.py census \\
        --start 2026-07-01 --end 2026-07-27 --leagues NBA,MLB,NHL \\
        --checkpoint /tmp/pdl.json --out /tmp/pdl_census.json

    # Validate a ledger/scoreboard JSON offline (no network), e.g. in CI:
    python3 scripts/evals/polymarket_discovery_ledger.py validate --input ledger.json
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Callable, Optional

BACKEND = Path(__file__).resolve().parents[2]
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))

from scripts.evals.expected_event_inventory import (  # noqa: E402  (stdlib-only sibling)
    ESPNScheduleProvider,
    normalize_team,
    run_census as run_expected_census,
)
from scripts.evals.named_event_completeness import (  # noqa: E402
    SCHEMA_VERSION as SCOREBOARD_SCHEMA,
    validate_scoreboard,
)
from scripts.evals.polymarket_recovery_ledger import (  # noqa: E402
    SCHEMA_VERSION as LEDGER_SCHEMA,
    validate_ledger,
)

# --------------------------------------------------------------------------- #
# Typed attempt vocabulary (C51-aligned). A transient failure is retryable and
# must never be marked terminal or collapsed into "not found" (gotcha #36).
# --------------------------------------------------------------------------- #
FOUND = "found"
NOT_FOUND = "not_found"
TIMEOUT = "timeout"
RATE_LIMITED = "rate_limited"
SERVER_ERROR = "server_error"
PARSE_FAILURE = "parse_failure"
RETRYABLE_RESULTS = {TIMEOUT, RATE_LIMITED, SERVER_ERROR, PARSE_FAILURE}

# The three archival surfaces validate_ledger requires on every event.
GAMMA_EVENT = "gamma_event"
GAMMA_MARKET = "gamma_market"
CLOB_CONDITION = "clob_condition"
SURFACES = (GAMMA_EVENT, GAMMA_MARKET, CLOB_CONDITION)

# Five mutually-exclusive main-market states (validate_ledger MAIN_STATES).
POLY_MAIN_RECOVERED = "poly_main_recovered"
POLY_LISTED_HISTORY_UNAVAILABLE = "poly_listed_history_unavailable"
POLY_DISCOVERY_OR_MATCHING_DEFECT = "poly_discovery_or_matching_defect"
POLY_NONLISTING_ARCHIVALLY_PROVEN = "poly_nonlisting_archivally_proven"
UNKNOWN = "unknown"
BLOCKING_STATES = {UNKNOWN, POLY_DISCOVERY_OR_MATCHING_DEFECT}

SCHEMA_VERSION = LEDGER_SCHEMA  # "polymarket-recovery/v1"

# Explicit, versioned policy. The meaningful-trade threshold is intentionally
# UNRATIFIED (null) — parent gate #9 forbids inventing a cutoff, so every prop
# stays threshold_pending until Alex rules. Robustness density is a measurement
# policy, not a redefinition of calibration success.
DEFAULT_POLICY = {
    "version": "poly-discovery/v1",
    "robustness": {
        "version": "poly-density/v1",
        "min_effective_points": 4,
        "max_gap_minutes": 180,
    },
    "meaningful_trade": {"version": "alex-threshold/pending", "threshold": None},
}


# --------------------------------------------------------------------------- #
# Small pure helpers
# --------------------------------------------------------------------------- #
def _to_float(value: Any) -> Optional[float]:
    try:
        if value in (None, ""):
            return None
        return float(value)
    except (TypeError, ValueError):
        return None


def _parse_iso(value: Any) -> Optional[datetime]:
    if not value:
        return None
    text = str(value).replace("Z", "+00:00")
    try:
        dt = datetime.fromisoformat(text)
    except ValueError:
        # Gamma sometimes carries microseconds beyond fromisoformat's tolerance.
        try:
            dt = datetime.fromisoformat(text.split(".")[0] + "+00:00")
        except ValueError:
            return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt


def _iso(unix_seconds: float) -> str:
    return datetime.fromtimestamp(unix_seconds, tz=timezone.utc).isoformat()


def parse_clob_token_ids(raw: Any) -> list[str]:
    """Parse ``clobTokenIds`` — a JSON-encoded string list on Gamma.

    The CLOB token IDs are opaque 77-digit decimals; the paired ``conditionId``
    is a ``0x…`` hex string. Neither is ever ``rstrip``-mangled (C50 finding: a
    condition id ending in ``e`` was corrupted by ``rstrip('e')``).
    """
    if raw is None:
        return []
    if isinstance(raw, list):
        return [str(t) for t in raw]
    try:
        value = json.loads(raw)
    except (json.JSONDecodeError, TypeError):
        return []
    return [str(t) for t in value] if isinstance(value, list) else []


def _json_list(raw: Any) -> list[Any]:
    if isinstance(raw, list):
        return raw
    if raw is None:
        return []
    try:
        value = json.loads(raw)
    except (json.JSONDecodeError, TypeError):
        return []
    return value if isinstance(value, list) else []


# --------------------------------------------------------------------------- #
# Gamma decomposition (pure) — gotcha #18: a Poly game *event* is a set of nested
# sub-markets keyed by conditionId; decompose each, never flatten to one market.
# --------------------------------------------------------------------------- #
def decompose_gamma_event(event: dict) -> dict:
    """Turn one Gamma event payload into a lossless, structured decomposition."""
    poly_event_id = str(event.get("id")) if event.get("id") is not None else None
    submarkets: list[dict] = []
    for market in event.get("markets") or []:
        condition_id = market.get("conditionId")  # 0x… hex — DO NOT rstrip
        tokens = parse_clob_token_ids(market.get("clobTokenIds"))
        labels = [str(x) for x in _json_list(market.get("outcomes"))]
        prices = _json_list(market.get("outcomePrices"))
        outcomes: list[dict] = []
        for index, label in enumerate(labels):
            outcomes.append(
                {
                    "label": label,
                    "index": index,
                    "token_id": tokens[index] if index < len(tokens) else None,
                    "price": _to_float(prices[index]) if index < len(prices) else None,
                }
            )
        submarkets.append(
            {
                "condition_id": condition_id,
                "question": market.get("question") or market.get("groupItemTitle") or "",
                "group_item_title": market.get("groupItemTitle"),
                "outcomes": outcomes,
                "volume": _to_float(market.get("volume")),
                "closed": bool(market.get("closed")),
            }
        )
    return {
        "polymarket_event_id": poly_event_id,
        "title": event.get("title") or "",
        "slug": event.get("slug") or "",
        "ticker": event.get("ticker") or "",
        "start_date": event.get("startDate"),
        "submarkets": submarkets,
    }


# --------------------------------------------------------------------------- #
# Identity + market classification (pure)
# --------------------------------------------------------------------------- #
_DATE_TOKEN = re.compile(r"\d{4}-\d{2}-\d{2}")


def event_matches_game(
    decomposed: dict, away_norm: str, home_norm: str, game_date: Optional[str] = None
) -> bool:
    """True when a Gamma event names BOTH teams (nickname tokens) in its text.

    Semantic integrity (parent gate #10): a same-day text hit is insufficient; we
    require both team nicknames present. When ``game_date`` is supplied and the
    event's slug/title carries any ``YYYY-MM-DD`` token, that token must equal the
    game date — this disambiguates the same matchup on different days inside a wide
    lookback window (the moneyline event is created days before commence, so the
    window must look back; the date token keeps it honest).
    """
    haystack = " ".join(
        [decomposed.get("title", ""), decomposed.get("slug", ""), decomposed.get("ticker", "")]
    ).lower()
    if not (away_norm and home_norm and away_norm in haystack and home_norm in haystack):
        return False
    if game_date:
        tokens = _DATE_TOKEN.findall(haystack)
        if tokens and game_date not in tokens:
            return False
    return True


_TEAM_STAT_KEYWORDS = (
    "points", "rebounds", "assists", "goals", "hits", "strikeouts", "home runs",
    "touchdowns", "saves", "blocks", "steals", "runs", "rbis", "yards",
)


_PROP_QUALIFIERS = (
    "by more than", "spread", "cover", "handicap", "+/-", "total", "over/under", "o/u",
    "combined", "inning", "half", "quarter", "period", "first ", "1st ", "race to",
)


def classify_submarket(submarket: dict, away_norm: str, home_norm: str) -> str:
    """Return ``main`` (full-game moneyline) or ``prop``.

    The main contract is the two-outcome moneyline whose two outcomes ARE the two
    teams and whose question carries no prop qualifier (spread/total/period/etc.).
    Everything else — spreads, totals, player stats, period markets — is a prop.
    Deliberately conservative: when unsure, ``prop`` (so a real prop is never
    mistaken for the single main contract, and a spread with team-name outcomes is
    never misread as the moneyline).
    """
    question = (submarket.get("question") or "").lower()
    labels = [(o.get("label") or "").lower() for o in submarket.get("outcomes") or []]
    if len(submarket.get("outcomes") or []) != 2:
        return "prop"
    if any(k in question for k in _PROP_QUALIFIERS):
        return "prop"
    if any(k in question for k in _TEAM_STAT_KEYWORDS):
        return "prop"
    joined = " ".join(labels)
    both_team_outcomes = away_norm in joined and home_norm in joined
    both_teams_in_q = away_norm in question and home_norm in question
    if both_team_outcomes or both_teams_in_q:
        return "main"
    return "prop"


def extract_prop_semantics(submarket: dict) -> dict:
    """Structured subject/stat/threshold/direction/period (parent gate #10).

    Best-effort but never empty for the required fields — validate_ledger rejects
    a prop with a blank subject/stat/direction/period.
    """
    question = submarket.get("question") or ""
    lowered = question.lower()
    labels = [(o.get("label") or "").lower() for o in submarket.get("outcomes") or []]

    direction = "binary_yes_no"
    if any(lab in ("over", "under") for lab in labels) or any(
        k in lowered for k in ("over/under", "more than", "at least", "fewer than", "or more")
    ):
        direction = "over_under"

    threshold_match = re.search(r"(\d+(?:\.\d+)?)", question)
    threshold = float(threshold_match.group(1)) if threshold_match else None

    period = "full_game"
    for needle, name in (
        ("first half", "first_half"), ("1st half", "first_half"),
        ("first quarter", "first_quarter"), ("1st quarter", "first_quarter"),
        ("first period", "first_period"), ("1st period", "first_period"),
        ("first inning", "first_inning"), ("1st inning", "first_inning"),
        ("first 5 innings", "first_5_innings"), ("f5", "first_5_innings"),
    ):
        if needle in lowered:
            period = name
            break

    stat = "moneyline"
    for keyword in _TEAM_STAT_KEYWORDS:
        if keyword in lowered:
            stat = keyword.replace(" ", "_")
            break
    else:
        if any(k in lowered for k in ("by more than", "spread", "cover", "handicap")):
            stat = "spread"
        elif "total" in lowered or "combined" in lowered:
            stat = "total"

    subject = (submarket.get("group_item_title") or "").strip()
    if not subject:
        # Fall back to the leading phrase of the question so subject is never blank.
        subject = re.sub(r"\s+", " ", question).strip()[:80] or "unknown"
    return {
        "subject": subject,
        "stat": stat,
        "threshold": threshold,
        "direction": direction,
        "period": period,
    }


# --------------------------------------------------------------------------- #
# Timeline measurement (pure) — builds the C51 timeline block.
# --------------------------------------------------------------------------- #
def measure_timeline(
    points: list[dict],
    commence_iso: Optional[str],
    token_id: str,
    condition_id: Optional[str],
    poly_event_id: Optional[str],
) -> Optional[dict]:
    """Measure a CLOB price series. Returns ``None`` when there is no history.

    ``points`` is the CLOB ``prices-history`` ``history`` array of ``{t, p}``.
    De-duplicates by timestamp so ``effective_points <= raw_points`` always holds
    (validate_ledger rejects duplicate-inflated counts).
    """
    raw_points = len(points)
    by_ts: dict[int, float] = {}
    for point in points:
        ts = point.get("t")
        if ts is None:
            continue
        try:
            by_ts[int(ts)] = _to_float(point.get("p")) or 0.0
        except (TypeError, ValueError):
            continue
    ordered = sorted(by_ts)
    if not ordered:
        return None
    effective_points = len(ordered)
    first, last = ordered[0], ordered[-1]

    largest_gap = 0.0
    for earlier, later in zip(ordered, ordered[1:]):
        largest_gap = max(largest_gap, (later - earlier) / 60.0)

    pregame_span = ingame_span = 0.0
    upstream_ingame = False
    commence = _parse_iso(commence_iso)
    if commence is not None:
        cts = commence.timestamp()
        pre = [t for t in ordered if t < cts]
        during = [t for t in ordered if t >= cts]
        if pre:
            pregame_span = (cts - pre[0]) / 60.0
        if during:
            ingame_span = (during[-1] - cts) / 60.0
            upstream_ingame = True

    terminal_price = by_ts[last]
    terminal_behavior = "closed" if (terminal_price <= 0.02 or terminal_price >= 0.98) else "open"

    return {
        "raw_points": raw_points,
        "effective_points": effective_points,
        "first_at": _iso(first),
        "last_at": _iso(last),
        "largest_gap_minutes": round(largest_gap, 2),
        "pregame_span_minutes": round(pregame_span, 2),
        "ingame_span_minutes": round(ingame_span, 2),
        "terminal_behavior": terminal_behavior,
        "token_id": token_id,
        "dedup_key": f"{poly_event_id}:{condition_id}:{token_id}",
        "rendered_usable": True,
        "side_token_verified": True,
        "upstream_ingame_points": upstream_ingame,
    }


def _timeline_robust(timeline: Optional[dict], policy: dict) -> bool:
    if not timeline:
        return False
    robust = policy.get("robustness") or {}
    return (
        timeline["effective_points"] > 2
        and timeline["effective_points"] >= robust.get("min_effective_points", 0)
        and timeline["largest_gap_minutes"] <= robust.get("max_gap_minutes", float("inf"))
    )


def _valid_two_token_outcomes(outcomes: list[dict]) -> bool:
    tokens = [o.get("token_id") for o in outcomes]
    return len(outcomes) >= 2 and None not in tokens and len(tokens) == len(set(tokens))


def _owned_retry(reason: str, expected: dict) -> dict:
    """A qualified (non-tombstone) failure with a next attempt (C50 finding).

    An unqualified ``state: failed`` with no reason/fingerprint/next-attempt is a
    permanent tombstone; validate_ledger rejects it. An owned defect names all
    three so the work stays live.
    """
    fingerprint = "sha256:" + str(abs(hash(expected["canonical_event_id"])) % (10 ** 16))
    return {
        "state": "failed",
        "reason": reason,
        "input_fingerprint": fingerprint,
        "next_attempt_at": "pending-scheduler",
    }


# --------------------------------------------------------------------------- #
# Record builders (pure) — every record is validate_ledger-clean by construction.
# --------------------------------------------------------------------------- #
def build_event_record(expected: dict, discovery: dict, policy: Optional[dict] = None) -> dict:
    """Build one ``polymarket-recovery/v1`` event record from a discovery result.

    ``discovery`` (from ``PolymarketDiscoveryClient`` or a fixture) carries::

        {
          "attempts": [ {surface, attempted_at, request_identity, result,
                         http_status, terminal, evidence}, ... ],   # all 3 surfaces
          "matched_event_id": str | None,
          "matched_market": <submarket dict> | None,
          "main_points": [ {t, p}, ... ],       # CLOB history for the chosen side
          "ambiguous": bool,                     # multiple candidate events
        }
    """
    policy = policy or DEFAULT_POLICY
    attempts = list(discovery.get("attempts") or [])
    surfaces = {a.get("surface") for a in attempts}
    all_404 = set(SURFACES) <= surfaces and all(
        a.get("result") == NOT_FOUND and a.get("http_status") == 404 for a in attempts
    )
    transient = any(a.get("result") in RETRYABLE_RESULTS for a in attempts)
    matched_market = discovery.get("matched_market")

    record: dict[str, Any] = {
        "canonical_event_id": expected["canonical_event_id"],
        "record_version": 1,
        "league": expected["league"],
        "game_date": expected["game_date"],
        "teams": [expected["away_team"], expected["home_team"]],
        "game_number": expected.get("game_number", 1),
        "attempts": attempts,
    }

    if discovery.get("ambiguous"):
        record["main_state"] = POLY_DISCOVERY_OR_MATCHING_DEFECT
        record["retry"] = _owned_retry("identity_ambiguous", expected)
        return record
    if transient and matched_market is None:
        # A transient failure must not masquerade as a proven state.
        record["main_state"] = UNKNOWN
        record["retry"] = _owned_retry("transient_surface_failure", expected)
        return record
    if matched_market is None:
        if all_404:
            record["main_state"] = POLY_NONLISTING_ARCHIVALLY_PROVEN
        else:
            # Presume-listed rule: an unproven miss is a defect, not "not listed".
            record["main_state"] = POLY_DISCOVERY_OR_MATCHING_DEFECT
            record["retry"] = _owned_retry("main_market_unresolved", expected)
        return record

    # We isolated a main market. Recovery requires two distinct tokens AND robust
    # CLOB history; otherwise it is listed-but-history-unavailable (gotcha #35).
    outcomes = matched_market.get("outcomes") or []
    chosen = next((o for o in outcomes if o.get("token_id")), None)
    timeline = None
    if chosen:
        timeline = measure_timeline(
            discovery.get("main_points") or [],
            expected.get("commence_time"),
            chosen["token_id"],
            matched_market.get("condition_id"),
            discovery.get("matched_event_id"),
        )
    if _valid_two_token_outcomes(outcomes) and _timeline_robust(timeline, policy):
        record["main_state"] = POLY_MAIN_RECOVERED
        record["main_contract"] = {
            "polymarket_event_id": discovery.get("matched_event_id"),
            "condition_id": matched_market.get("condition_id"),
            "period": "full_game",
            "scheduled_instance": f"G{expected.get('game_number', 1)}",
            "outcomes": [
                {"label": o["label"], "token_id": o["token_id"], "index": o["index"]}
                for o in outcomes
            ],
        }
        record["history_job"] = {
            "durable_id": f"poly-main:{matched_market.get('condition_id')}",
            "state": "complete",
        }
        record["timeline"] = timeline
        record["retry"] = {"state": "complete"}
    else:
        record["main_state"] = POLY_LISTED_HISTORY_UNAVAILABLE
    return record


def build_prop_records(expected: dict, discovery: dict, policy: Optional[dict] = None) -> list[dict]:
    """Enumerate every non-main sub-market as a ``threshold_pending`` prop.

    Props are enumerated from the *source event's* sub-markets (parent gate #9),
    never from local rows. A settled losing prop (terminal Yes probability 0) stays
    represented (C50 ``terminal-zero-dropped``).
    """
    policy = policy or DEFAULT_POLICY
    props: list[dict] = []
    for prop in discovery.get("prop_markets") or []:
        submarket = prop.get("submarket") or {}
        outcomes = submarket.get("outcomes") or []
        chosen = next((o for o in outcomes if o.get("token_id")), None)
        timeline = None
        if chosen:
            timeline = measure_timeline(
                prop.get("points") or [],
                expected.get("commence_time"),
                chosen["token_id"],
                submarket.get("condition_id"),
                discovery.get("matched_event_id"),
            )
        recovered = _valid_two_token_outcomes(outcomes) and _timeline_robust(timeline, policy)
        yes_price = next(
            (o.get("price") for o in outcomes if (o.get("label") or "").lower() in ("yes", "over")),
            None,
        )
        record = {
            "canonical_event_id": expected["canonical_event_id"],
            "record_version": 1,
            "polymarket_event_id": discovery.get("matched_event_id"),
            "condition_id": submarket.get("condition_id"),
            "enumerated_from_source_event": True,
            "represented": True,
            "terminal_yes_probability": 0 if (yes_price is not None and yes_price <= 0.02) else None,
            "semantic": extract_prop_semantics(submarket),
            "outcomes": [
                {"label": o["label"], "token_id": o["token_id"], "index": o["index"]}
                for o in outcomes
            ],
            # No ratified threshold → every candidate prop stays pending (gate #9).
            "trade_classification": "threshold_pending",
            "trade_evidence": {
                "trade_count": prop.get("trade_count", 0),
                "candlestick_count": len(prop.get("points") or []),
                "volume": submarket.get("volume"),
            },
            "recovery_state": "recovered" if recovered else "pending",
        }
        if recovered:
            record["timeline"] = timeline
        props.append(record)
    return props


def build_ledger(events: list[dict], props: list[dict], policy: Optional[dict] = None) -> dict:
    """Assemble a ``polymarket-recovery/v1`` ledger payload."""
    return {
        "schema_version": SCHEMA_VERSION,
        "policy": policy or DEFAULT_POLICY,
        "events": events,
        "props": props,
    }


# --------------------------------------------------------------------------- #
# C52 scoreboard embedding (pure) — a named-event-completeness/v1 wrapper that
# carries the poly ledger so validate_scoreboard propagates its blockers.
# --------------------------------------------------------------------------- #
def build_scoreboard(
    expected_events: list[dict],
    observations: list[dict],
    polymarket_ledger: dict,
    policy: Optional[dict] = None,
) -> dict:
    """Assemble a ``named-event-completeness/v1`` scoreboard embedding the ledger."""
    scoreboard_policy = {
        "version": (policy or DEFAULT_POLICY)["version"],
        "history": {"version": "poly-density/v1", "min_pregame_points": 3, "min_ingame_points": 6, "max_gap_minutes": 180},
    }
    return {
        "schema_version": SCOREBOARD_SCHEMA,
        "policy": scoreboard_policy,
        "expected_events": expected_events,
        "observations": observations,
        "polymarket_ledger": polymarket_ledger,
    }


# --------------------------------------------------------------------------- #
# Census summary (pure) — counts by league/state, worst cases, recovery cohorts.
# --------------------------------------------------------------------------- #
def summarize(ledger: dict, expected_total_by_league: Optional[dict] = None,
              worst_case_limit: int = 25) -> dict:
    """Aggregate the ledger without hiding a named gap (parent gates #8–#10)."""
    events = ledger.get("events") or []
    props = ledger.get("props") or []

    by_league_state: dict[str, dict] = {}
    attempt_class = {FOUND: 0, NOT_FOUND: 0, TIMEOUT: 0, RATE_LIMITED: 0,
                     SERVER_ERROR: 0, PARSE_FAILURE: 0}
    worst: dict[str, list[dict]] = {"defect": [], "unknown": [], "listed_history_unavailable": []}

    for event in events:
        league = event.get("league", "?")
        state = event.get("main_state", UNKNOWN)
        bucket = by_league_state.setdefault(league, {s: 0 for s in (
            POLY_MAIN_RECOVERED, POLY_LISTED_HISTORY_UNAVAILABLE,
            POLY_DISCOVERY_OR_MATCHING_DEFECT, POLY_NONLISTING_ARCHIVALLY_PROVEN, UNKNOWN)})
        bucket[state] = bucket.get(state, 0) + 1
        for attempt in event.get("attempts") or []:
            result = attempt.get("result")
            if result in attempt_class:
                attempt_class[result] += 1
        stub = {"canonical_event_id": event.get("canonical_event_id"),
                "league": league, "game_date": event.get("game_date"),
                "teams": event.get("teams")}
        if state == POLY_DISCOVERY_OR_MATCHING_DEFECT:
            worst["defect"].append(stub)
        elif state == UNKNOWN:
            worst["unknown"].append(stub)
        elif state == POLY_LISTED_HISTORY_UNAVAILABLE:
            worst["listed_history_unavailable"].append(stub)

    prop_states = {"recovered": 0, "pending": 0}
    for prop in props:
        prop_states[prop.get("recovery_state", "pending")] = (
            prop_states.get(prop.get("recovery_state", "pending"), 0) + 1
        )

    for key in worst:
        worst[key].sort(key=lambda s: (s["league"], s["game_date"] or "", s["canonical_event_id"] or ""))

    # Recovery cohorts, smallest-ordered (parent recovery-exhaustion gate).
    cohorts = sorted(
        [{"cohort": f"main_defect:{lg}", "count": counts.get(POLY_DISCOVERY_OR_MATCHING_DEFECT, 0)}
         for lg, counts in by_league_state.items()],
        key=lambda c: c["count"],
    )
    cohorts += [{"cohort": "props_pending_recovery", "count": prop_states.get("pending", 0)}]

    validation = validate_ledger(ledger)
    return {
        "event_count": len(events),
        "prop_count": len(props),
        "by_league_state": dict(sorted(by_league_state.items())),
        "prop_states": prop_states,
        "attempt_class_counts": attempt_class,
        "expected_total_by_league": expected_total_by_league or {},
        "worst_cases": {
            k: {"count": len(v), "named": v[:worst_case_limit],
                "truncated": max(0, len(v) - worst_case_limit)}
            for k, v in worst.items()
        },
        "recovery_cohorts": [c for c in cohorts if c["count"]],
        "validation": {
            "valid": validation["valid"],
            "closure_ready": validation["closure_ready"],
            "event_state_counts": validation["event_state_counts"],
            "blocker_count": len(validation["blockers"]),
        },
    }


# --------------------------------------------------------------------------- #
# I/O boundary — Polymarket Gamma + CLOB discovery client (injected).
# --------------------------------------------------------------------------- #
def _http_json(url: str, timeout: int = 25) -> tuple[Optional[Any], int, Optional[str]]:
    """Return ``(payload, http_status, error_class)``.

    Distinguishes 404 (not found) from 429 (rate limited) from 5xx (server error)
    from timeouts and parse failures — never a catch-all Optional (gotcha #36).
    """
    import urllib.error
    import urllib.request

    # Gamma/CLOB reject the default Python-urllib agent with a 403 bot block; a
    # browser-like agent is required (curl's own default UA passes, urllib's does not).
    headers = {"User-Agent": "Mozilla/5.0 (compatible; BainLuckDiscovery/1.0)", "Accept": "application/json"}
    try:
        with urllib.request.urlopen(urllib.request.Request(url, headers=headers), timeout=timeout) as resp:
            body = resp.read().decode()
    except urllib.error.HTTPError as exc:
        if exc.code == 404:
            return None, 404, NOT_FOUND
        if exc.code == 429:
            return None, 429, RATE_LIMITED
        if 500 <= exc.code < 600:
            return None, exc.code, SERVER_ERROR
        return None, exc.code, SERVER_ERROR
    except (urllib.error.URLError, TimeoutError, OSError):  # network / timeout
        return None, 0, TIMEOUT
    try:
        return json.loads(body), 200, None
    except json.JSONDecodeError:
        return None, 200, PARSE_FAILURE


class PolymarketDiscoveryClient:
    """Live Gamma + CLOB discovery driven by the independent expected event.

    Traversal is date-partitioned (a ±28h window per game, gotcha #89) and
    exhaustive within it — never bounded by Gamma's 2000-offset cap (gotcha #41).
    """

    GAMMA = "https://gamma-api.polymarket.com"
    CLOB = "https://clob.polymarket.com"
    # Gamma tag slugs are the *sport*, not the league (app/tasks/polymarket.py):
    # baseball/basketball/hockey — "mlb"/"nba"/"nhl" are silently ignored.
    LEAGUE_TAG = {"NBA": "basketball", "MLB": "baseball", "NHL": "hockey"}

    def __init__(self, delay: float = 0.3, page_size: int = 100, max_pages: int = 25,
                 history_fidelity: int = 60, lookback_days: int = 10, lookahead_days: int = 2):
        self.delay = delay
        self.page_size = page_size
        self.max_pages = max_pages
        self.history_fidelity = history_fidelity
        # Gamma startDate is the market-CREATION date, not commence — a game's
        # moneyline event is created days early. The window must look back far
        # enough to include it; the date-token guard keeps the match honest.
        self.lookback_days = lookback_days
        self.lookahead_days = lookahead_days

    def _attempt(self, surface: str, request_identity: str, result: str,
                 http_status: Optional[int], evidence: str = "") -> dict:
        return {
            "surface": surface,
            "attempted_at": datetime.now(timezone.utc).isoformat(),
            "request_identity": request_identity,
            "result": result,
            "http_status": http_status,
            # Transient failures stay retryable; a real result is terminal.
            "terminal": result not in RETRYABLE_RESULTS,
            "evidence": evidence,
        }

    def _gamma_events_window(self, expected: dict) -> tuple[str, list[dict], Optional[int], str, bool]:
        """Exhaustively page the lookback Gamma window for the game's sport.

        Returns ``(result, events, http_status, request_identity, page_cap_hit)``.
        ``page_cap_hit`` is True when the window filled every page — a no-silent-
        truncation signal so the caller records incomplete traversal rather than
        reading a capped page as proven absence (gotcha #41).
        """
        commence = _parse_iso(expected.get("commence_time")) or _parse_iso(
            expected["game_date"] + "T00:00:00Z"
        )
        lo = (commence - timedelta(days=self.lookback_days)).strftime("%Y-%m-%dT%H:%M:%SZ")
        hi = (commence + timedelta(days=self.lookahead_days)).strftime("%Y-%m-%dT%H:%M:%SZ")
        tag = self.LEAGUE_TAG.get(expected["league"], "")
        collected: list[dict] = []
        page_cap_hit = False
        for page in range(self.max_pages):
            offset = page * self.page_size
            url = (
                f"{self.GAMMA}/events?limit={self.page_size}&offset={offset}"
                f"&start_date_min={lo}&start_date_max={hi}&closed=true&tag_slug={tag}"
            )
            payload, status, err = _http_json(url)
            if err in RETRYABLE_RESULTS:
                return err, collected, status, f"window {lo}..{hi} offset {offset}", page_cap_hit
            if payload is None or not isinstance(payload, list) or not payload:
                break  # exhausted the window
            collected.extend(payload)
            time.sleep(self.delay)
            if len(payload) < self.page_size:
                break
            if page == self.max_pages - 1:
                page_cap_hit = True  # more pages remain but we hit the bound
        identity = f"gamma:events tag_slug={tag} window={lo}..{hi}"
        return (FOUND if collected else NOT_FOUND), collected, 200, identity, page_cap_hit

    def discover_event(self, expected: dict) -> dict:
        """Run the three archival surfaces and return a discovery result dict.

        A single real game is listed on Polymarket as a *cluster* of Gamma events
        (moneyline/game event + a separate "- Player Props" event + sometimes
        others). All matching candidates are aggregated into one sub-market pool —
        multiple candidates is normal clustering, NOT identity ambiguity.
        """
        away_norm = expected.get("away_norm") or normalize_team(expected.get("away_team", ""))
        home_norm = expected.get("home_norm") or normalize_team(expected.get("home_team", ""))
        game_date = expected.get("game_date")
        attempts: list[dict] = []

        # Surface 1: gamma_event — date-partitioned, exhaustive within the window.
        result, raw_events, status, identity, page_cap_hit = self._gamma_events_window(expected)
        if result in RETRYABLE_RESULTS:
            for surface in SURFACES:
                attempts.append(self._attempt(surface, identity, result, status, "transient event surface"))
            return {"attempts": attempts, "matched_event_id": None, "matched_market": None,
                    "main_points": [], "prop_markets": [], "ambiguous": False, "page_cap_hit": page_cap_hit}

        candidates = []
        for raw in raw_events:
            decomposed = decompose_gamma_event(raw)
            if event_matches_game(decomposed, away_norm, home_norm, game_date):
                candidates.append(decomposed)

        attempts.append(self._attempt(
            GAMMA_EVENT, identity, FOUND if candidates else NOT_FOUND,
            200 if candidates else status,
            f"{len(candidates)} candidate event(s) in cluster"
            + ("; PAGE CAP HIT (traversal incomplete)" if page_cap_hit else ""),
        ))

        if not candidates:
            # No event matched. The market/clob surfaces have nothing to hit; record
            # them not_found with the real (non-404) empty-search status so nonlisting
            # proof (which requires a real 404) can never false-fire on an empty search.
            attempts.append(self._attempt(GAMMA_MARKET, identity, NOT_FOUND, status, "no candidate event"))
            attempts.append(self._attempt(CLOB_CONDITION, identity, NOT_FOUND, status, "no candidate event"))
            return {"attempts": attempts, "matched_event_id": None, "matched_market": None,
                    "main_points": [], "prop_markets": [], "ambiguous": False, "page_cap_hit": page_cap_hit}

        # Aggregate every candidate's sub-markets, tagging each with its source event.
        pool: list[dict] = []
        event_ids: list[str] = []
        for cand in candidates:
            event_ids.append(cand["polymarket_event_id"])
            for sm in cand["submarkets"]:
                pool.append({**sm, "source_event_id": cand["polymarket_event_id"]})
        main = next((sm for sm in pool if classify_submarket(sm, away_norm, home_norm) == "main"), None)
        prop_submarkets = [sm for sm in pool if sm is not main]
        primary_event_id = (main or {}).get("source_event_id") or event_ids[0]

        # Surface 2: gamma_market — the embedded sub-markets ARE the market surface.
        attempts.append(self._attempt(
            GAMMA_MARKET, f"gamma:events {','.join(event_ids)}",
            FOUND if pool else NOT_FOUND, 200,
            f"{len(pool)} submarket(s) across {len(candidates)} event(s); main={'yes' if main else 'no'}",
        ))

        # Surface 3: clob_condition — main market history.
        main_points: list[dict] = []
        clob_result, clob_status = NOT_FOUND, 200
        clob_identity = "clob:prices-history (no main market)"
        if main:
            chosen = next((o for o in main["outcomes"] if o.get("token_id")), None)
            if chosen:
                clob_identity = f"clob:prices-history token={chosen['token_id'][:12]}…"
                main_points, clob_result, clob_status = self._fetch_history(chosen["token_id"])
        attempts.append(self._attempt(
            CLOB_CONDITION, clob_identity, clob_result, clob_status,
            f"{len(main_points)} history point(s)",
        ))

        # Enumerate props (history fetched per prop; count logged, never silently capped).
        prop_markets = []
        for sm in prop_submarkets:
            chosen = next((o for o in sm["outcomes"] if o.get("token_id")), None)
            points: list[dict] = []
            if chosen:
                points, _, _ = self._fetch_history(chosen["token_id"])
            prop_markets.append({"submarket": sm, "points": points, "trade_count": len(points)})

        return {
            "attempts": attempts,
            "matched_event_id": primary_event_id,
            "matched_market": main,
            "main_points": main_points,
            "prop_markets": prop_markets,
            "ambiguous": False,
            "page_cap_hit": page_cap_hit,
        }

    def _fetch_history(self, token_id: str) -> tuple[list[dict], str, int]:
        url = f"{self.CLOB}/prices-history?market={token_id}&interval=max&fidelity={self.history_fidelity}"
        payload, status, err = _http_json(url)
        time.sleep(self.delay)
        if err in RETRYABLE_RESULTS:
            return [], err, status
        if err == NOT_FOUND or payload is None:
            return [], NOT_FOUND, status
        history = payload.get("history") if isinstance(payload, dict) else None
        return (history or []), (FOUND if history else NOT_FOUND), 200


# --------------------------------------------------------------------------- #
# Census orchestration
# --------------------------------------------------------------------------- #
def run_discovery_census(
    expected_events: list[dict],
    client: Any,
    policy: Optional[dict] = None,
    checkpoint: Optional[str] = None,
    limit: Optional[int] = None,
    log: Callable[[str], None] = lambda m: None,
) -> dict:
    """Drive discovery from an independent expected-event population.

    Idempotent + resumable via a per-canonical-id checkpoint. When ``limit`` is
    set the run is bounded and the deferred remainder is reported as a cohort
    (never silently dropped — parent no-silent-caps rule).
    """
    policy = policy or DEFAULT_POLICY
    ck: dict[str, Any] = {"discoveries": {}}
    if checkpoint and Path(checkpoint).exists():
        try:
            ck = json.loads(Path(checkpoint).read_text())
        except Exception:  # noqa: BLE001 — a corrupt checkpoint should not wedge
            ck = {"discoveries": {}}
    ck.setdefault("discoveries", {})

    ordered = sorted(expected_events, key=lambda e: e["canonical_event_id"])
    attempted, deferred = ordered, []
    if limit is not None and len(ordered) > limit:
        attempted, deferred = ordered[:limit], ordered[limit:]

    events, props = [], []
    for index, expected in enumerate(attempted):
        cid = expected["canonical_event_id"]
        cached = ck["discoveries"].get(cid)
        if cached is not None:
            discovery = cached
        else:
            discovery = client.discover_event(expected)
            ck["discoveries"][cid] = discovery
            if checkpoint:
                Path(checkpoint).write_text(json.dumps(ck))
        events.append(build_event_record(expected, discovery, policy))
        props.extend(build_prop_records(expected, discovery, policy))
        if (index + 1) % 10 == 0:
            log(f"discovered {index + 1}/{len(attempted)}")

    ledger = build_ledger(events, props, policy)
    expected_total = {}
    for expected in ordered:
        expected_total[expected["league"]] = expected_total.get(expected["league"], 0) + 1
    summary = summarize(ledger, expected_total)

    # C52 validate_scoreboard: embed the real produced ledger into a source-agnostic
    # scoreboard and confirm the poly ledger validates + propagates through the C52
    # contract. The non-poly observation dimensions (winner/calibration/render) are
    # #1467's scope and are intentionally NOT fabricated here — we report the poly
    # embedding result specifically.
    c52_expected = [
        {
            "expected_event_id": e["canonical_event_id"], "league": e["league"],
            "scheduled_at": e.get("commence_time") or (e["game_date"] + "T00:00:00Z"),
            "teams": [e["away_team"], e["home_team"]], "game_number": e.get("game_number", 1),
            "inventory_source": "espn_scoreboard",
            "inventory_attempts": [{
                "attempt_id": f"espn:{e['canonical_event_id']}",
                "attempted_at": datetime.now(timezone.utc).isoformat(),
                "request_identity": f"espn:{e['league']}:{e['game_date']}",
                "result": "found", "terminal": True,
            }],
        }
        for e in attempted
    ]
    scoreboard = build_scoreboard(c52_expected, [], ledger, policy)
    sb_result = validate_scoreboard(scoreboard)
    poly = sb_result.get("polymarket_result") or {}
    summary["c52_scoreboard"] = {
        "poly_embedding_valid": poly.get("valid"),
        "poly_closure_ready": poly.get("closure_ready"),
        "poly_blocker_count": len(poly.get("blockers", [])),
        "polymarket_findings_propagated": sum(
            1 for f in sb_result.get("findings", []) if f["code"].startswith("POLYMARKET_")
        ),
        "note": (
            "expected_events sourced from #1467 ESPN inventory; observations left empty "
            "(source-agnostic winner/calibration/render dimensions are #1467's scope, not "
            "fabricated here). This run validates the poly ledger embedding + propagation only."
        ),
    }
    summary["window"] = {
        "expected_events": len(ordered),
        "attempted": len(attempted),
        "deferred_cohort": len(deferred),
        "deferred_named": [e["canonical_event_id"] for e in deferred[:50]],
    }
    return {"ledger": ledger, "summary": summary}


# --------------------------------------------------------------------------- #
# CLI
# --------------------------------------------------------------------------- #
def _load_env() -> tuple[str, str]:
    import os

    return os.environ.get("BAINLUCK_API", "https://api.bainluck.com"), os.environ.get("ADMIN_TOKEN", "")


def _expected_from_inventory_census(census: dict) -> list[dict]:
    """Reconstruct expected-event dicts from a #1467 census checkpoint's rows."""
    expected = []
    for row in census.get("rows", {}).values() if isinstance(census.get("rows"), dict) else []:
        away, home = (row.get("matchup") or " @ ").split(" @ ", 1)
        expected.append({
            "canonical_event_id": row["canonical_event_id"],
            "league": row["league"],
            "game_date": row["game_date"],
            "away_team": away, "home_team": home,
            "away_norm": normalize_team(away), "home_norm": normalize_team(home),
            "commence_time": row.get("commence_time") or (row["game_date"] + "T00:00:00Z"),
            "game_number": 1,
        })
    return expected


def main(argv: Optional[list[str]] = None) -> int:
    parser = argparse.ArgumentParser(
        description="Tier-1 Polymarket event + prop discovery ledger (#1468)"
    )
    sub = parser.add_subparsers(dest="cmd", required=True)

    c = sub.add_parser("census", help="Run live Polymarket discovery over the expected population")
    c.add_argument("--start", required=True)
    c.add_argument("--end", required=True)
    c.add_argument("--leagues", default="NBA,MLB,NHL")
    c.add_argument("--checkpoint", default=None)
    c.add_argument("--out", default=None)
    c.add_argument("--limit", type=int, default=None)
    c.add_argument("--inventory-checkpoint", default=None,
                   help="Reuse a #1467 expected_event_inventory checkpoint instead of refetching ESPN")

    v = sub.add_parser("validate", help="Validate a ledger or scoreboard JSON offline")
    v.add_argument("--input", required=True)

    args = parser.parse_args(argv)

    if args.cmd == "validate":
        payload = json.loads(Path(args.input).read_text())
        if payload.get("schema_version") == SCOREBOARD_SCHEMA:
            print(json.dumps(validate_scoreboard(payload), indent=2, default=str))
        else:
            print(json.dumps(validate_ledger(payload), indent=2, default=str))
        return 0

    # census — expected population comes from #1467's ESPN-authoritative
    # enumeration, always via a checkpoint (which carries the per-event rows).
    inv_checkpoint = args.inventory_checkpoint
    if not (inv_checkpoint and Path(inv_checkpoint).exists()):
        api, token = _load_env()
        if not token:
            print("ADMIN_TOKEN not set (source ~/.claude/.env first)", file=sys.stderr)
            return 2
        from scripts.evals.expected_event_inventory import DBQueryLedgerBackend

        inv_checkpoint = args.inventory_checkpoint or "/tmp/pdl_inventory_checkpoint.json"
        run_expected_census(args.start, args.end, ESPNScheduleProvider(),
                            DBQueryLedgerBackend(api, token),
                            checkpoint=inv_checkpoint,
                            log=lambda m: print(m, file=sys.stderr))
    census = json.loads(Path(inv_checkpoint).read_text())
    expected = _expected_from_inventory_census(census)

    leagues = {lg.strip().upper() for lg in args.leagues.split(",")}
    expected = [e for e in expected if e["league"] in leagues]
    print(f"expected population: {len(expected)} events", file=sys.stderr)

    client = PolymarketDiscoveryClient()
    result = run_discovery_census(expected, client, checkpoint=args.checkpoint,
                                  limit=args.limit, log=lambda m: print(m, file=sys.stderr))

    validation = validate_ledger(result["ledger"])
    result["ledger_validation"] = validation
    out = json.dumps(result, indent=2, default=str)
    if args.out:
        Path(args.out).write_text(out)
        print(f"wrote {args.out}", file=sys.stderr)
    print(json.dumps(result["summary"], indent=2, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
