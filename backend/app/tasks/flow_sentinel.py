"""Flow Sentinel — scripted user-flow acceptance sentinel against production (#1078).

Alex-directed (Opus-era plan, docs/execution-plan-2026-07-13.md §1 six failure
classes, §2 P3 reliability/design program, §0 rule 5 "sentinels over Alex's
eyeball"). This is the *measurement* the "fast and natural" reliability program
is scored by: it continuously drives real user flows against PRODUCTION, asserts
a concrete correctness condition per flow (not just HTTP 200), and files ONE
deduped, evidence-packed GitHub issue per failing flow. Alex exits the DETECTION
loop; his eyeball stays the SHIP gate, never the smoke detector.

Modeled on the Calibration Sentinel (#1054, app/tasks/calibration_sentinel.py):
same mine → evidence-pack → auto-file rails, same fingerprint dedup, same
GITHUB_TOKEN filing path (bug_report_github). Read-only against production — the
sentinel files work, it never writes data.

Six flows == Alex's six failure classes (plan §1):
  1. search_gold_set       — search finds each frozen gold-set entity (search miss)
  2. duplicate_events      — no real-world event appears twice (unmerged duplicate)
  3. event_completeness    — live Tier-1 events render game markets (missing markets)
  4. resolved_state        — settled events never render live, live ones do (state)
  5. chart_density         — user-visible charts clear the 1pt/open-hour bar (#180)
  6. category_discover     — category pages + Discover first page non-empty & quality

Design intent — regression-first, not re-file-the-backlog. Where a failure class
is already a tracked program (search findability is #993's Instant Answers work;
chart density is #180), the sentinel encodes the FROZEN baseline / a tunable bar
so a healthy run is GREEN and only a genuine REGRESSION (a flow that WORKED now
broken) files — mirroring the calibration sentinel's suppress-known discipline.
The scorecard always reports the current numbers so the trend stays visible.
"""

import hashlib
import logging
import os
import re
import time as _time
from typing import Any

import httpx

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Config (Redis-tunable, no-deploy — mirrors the calibration sentinel pattern)
# ---------------------------------------------------------------------------
FLOW_SENTINEL_API = os.environ.get("FLOW_SENTINEL_API", "https://api.bainluck.com")
HTTP_TIMEOUT = 30.0
SEARCH_CONCURRENCY = 4  # bounded fan-out so we don't hammer prod search

# chart_density: overall_below_bar_pct above this fails. The TRUE SLA target is
# 0% (every user-visible chart >= 1pt/open-hour) and is tracked by #180; this
# high default catches a density COLLAPSE (charts going dark) without re-filing
# #180's known backlog every run. Tune down as #180 hill-climbs.
CHART_DENSITY_MAX_BELOW_BAR_PCT = 95.0  # flow:sentinel_chart_density_max_below_bar
# event_completeness / resolved_state / duplicate sampling sizes.
EVENT_SAMPLE_SIZE = 10          # flow:sentinel_event_sample_size
# resolved_state: a status='live' event whose game started more than this many
# hours ago is stuck rendering live long after it settled (resolved-shown-as-live).
STALE_LIVE_HOURS = 12.0         # flow:sentinel_stale_live_hours
# Feed-quality @20 targets (CLAUDE.md production audit target).
FEED_QUALITY_TOP_N = 20
# participation_family (#199): how many golf prop markets to detail-probe per run.
PARTICIPATION_SAMPLE_SIZE = 8

# Tier-1 leagues (CLAUDE.md quota-guard tiers): a live game here with zero
# markets is a real completeness bug, not an upstream coverage gap.
TIER1_SPORTS = (
    "basketball_nba",
    "icehockey_nhl",
    "baseball_mlb",
    "americanfootball_nfl",
    "basketball_ncaab",
)

# ---------------------------------------------------------------------------
# Instant Answers gold set (FROZEN 2026-07-06, .claude/handoff/
# instant_answers_benchmark_v1.md). Each row: (natural query, expected_found).
# expected_found == True for baseline OK + UNREADABLE (search returned a top
# result); False for UNFINDABLE + MISSING (baseline search miss). A regression =
# an expected-found entity that now returns nothing. A recovery = an expected-miss
# entity that now returns something (surfaced as good news, never filed).
# Do NOT edit the query set — it is the frozen benchmark. Append rounds only.
# ---------------------------------------------------------------------------
GOLD_SET: tuple[tuple[str, bool], ...] = (
    ("lebron james", False),            # Q01 UNFINDABLE
    ("aaron rodgers", False),           # Q02 UNFINDABLE
    ("next coach fired", False),        # Q03 UNFINDABLE
    ("nba mvp", False),                 # Q04 UNFINDABLE (wrong-league)
    ("nba champion", True),             # Q05 OK
    ("nfl mvp", False),                 # Q06 UNFINDABLE
    ("super bowl champion", False),     # Q07 UNFINDABLE
    ("world series", True),             # Q08 OK
    ("stanley cup", True),              # Q09 OK
    ("premier league winner", True),    # Q10 OK
    ("champions league winner", True),  # Q11 OK
    ("ballon d'or", True),              # Q12 UNREADABLE (found)
    ("heisman", True),                  # Q13 OK
    ("fed rate decision", False),       # Q14 UNFINDABLE
    ("fed chair", True),                # Q15 UNREADABLE (found)
    ("2028 democratic nominee", True),  # Q16 UNREADABLE (found)
    ("2028 republican nominee", True),  # Q17 UNREADABLE (found)
    ("us recession 2026", True),        # Q18 OK
    ("best picture oscar", True),       # Q19 OK
    ("highest grossing movie", True),   # Q20 UNREADABLE (found)
    ("person of the year", True),       # Q21 OK
    ("bitcoin price 2026", False),      # Q22 UNFINDABLE
    ("masters winner", False),          # Q23 MISSING
    ("nba rookie of the year", False),  # Q24 UNFINDABLE
    ("trump approval", False),          # Q25 UNFINDABLE
)

# A synthetic entity that MUST NOT exist — the canary. In canary mode it is
# appended to the gold set as expected_found=True, so it is guaranteed to
# "regress", proving the detect → evidence-pack → file path end-to-end.
CANARY_QUERY = "zzqx nonexistent sentinel canary entity 99"

# ---------------------------------------------------------------------------
# TOP-1 CORRECTNESS gold set (#1206 / Queue #246 Item 1) — the metric #244 proved
# we now need: #244 killed zero-results (findability), so the bar moves from "did
# ANYTHING surface" to "is the RIGHT surface top-1". Each entry asserts the LEADING
# item of a given kind is the expected surface. Distinct from GOLD_SET (findability)
# — this is additive and only holds family-phrased queries with an UNAMBIGUOUS
# correct top-1 (concept hubs + the curated team aliases). The full ~50-query set is
# needs-user (#1213 — Alex's 20 + Fable's 30); append rows as that lands.
#   (query, expected_kind, marker) — kind ∈ {"concept", "team"}; marker is a
#   case-insensitive substring the leading item of that kind must contain.
GOLD_SET_TOP1: tuple[tuple[str, str, str], ...] = (
    ("grammys", "concept", "event:awards:grammys"),
    ("oscars", "concept", "event:awards:oscars"),
    ("emmys", "concept", "event:awards:emmys"),
    ("masters winner", "concept", "event:golf:"),
    ("world cup", "concept", "event:soccer:world-cup"),
    ("pats", "team", "patriots"),
    ("revs", "team", "revolution"),
    ("niners", "team", "49ers"),
)

# Flow → GitHub area label routing.
_FLOW_AREA_LABELS = {
    "search_gold_set": "area:search",
    "search_gold_top1": "area:search",
    "duplicate_events": "area:event-details",
    "event_completeness": "area:event-details",
    "resolved_state": "area:calibration",
    "chart_density": "area:event-details",
    "category_discover": "area:discover-ranking",
    "participation_family": "area:event-details",
    "matured_linkage": "area:event-details",  # covers matching/linkage per label desc
    "unlinked_held": "area:event-details",  # matcher missed a link we could have made
    "season_aggregate_linkage": "area:event-details",  # season market on a game event (#1220)
    "team_identity_dupes": "area:event-details",  # unmerged team-identity dupes / adjudication backlog
}
_FLOW_TITLES = {
    "search_gold_set": "search misses gold-set entities",
    "search_gold_top1": "search returns wrong top-1 for gold-set family queries",
    "duplicate_events": "duplicate unmerged events in results",
    "event_completeness": "live Tier-1 events missing game markets",
    "resolved_state": "settled/live event state incorrect",
    "chart_density": "user-visible charts below the density bar",
    "category_discover": "category / Discover first page empty or low-quality",
    "participation_family": "non-ME prop family (make-cut/top-N) squashed to sum-100%",
    "matured_linkage": "imminent event has a phantom blend source (in blend, no linked market)",
    "unlinked_held": "imminent event has an unlinked winner market we already hold (matcher miss)",
    "season_aggregate_linkage": "season-aggregate market mislinked to a single game event",
    "team_identity_dupes": "unmerged team-identity dupes remain or adjudication backlog is climbing",
}


# ---------------------------------------------------------------------------
# Runtime threshold overrides (Redis, no-deploy tuning)
# ---------------------------------------------------------------------------
def _load_overrides() -> None:
    global CHART_DENSITY_MAX_BELOW_BAR_PCT, EVENT_SAMPLE_SIZE, STALE_LIVE_HOURS
    try:
        from app.tasks.redis_state import get_redis_client

        r = get_redis_client()
        for key, name, cast in (
            ("flow:sentinel_chart_density_max_below_bar", "CHART_DENSITY_MAX_BELOW_BAR_PCT", float),
            ("flow:sentinel_event_sample_size", "EVENT_SAMPLE_SIZE", int),
            ("flow:sentinel_stale_live_hours", "STALE_LIVE_HOURS", float),
        ):
            v = r.get(key)
            if v is not None:
                globals()[name] = cast(v.decode() if isinstance(v, bytes) else v)
    except Exception as exc:
        logger.info("Flow sentinel overrides not loaded (using defaults): %s", exc)


# ---------------------------------------------------------------------------
# Pure helpers (unit-tested — no network)
# ---------------------------------------------------------------------------
def search_found(payload: dict) -> bool:
    """A gold-set entity is FOUND if the search payload surfaces it anywhere the
    UI would render an answer: an event concept, a game result, a futures market,
    or a futures family. Empty across all == a search miss (failure class #1)."""
    if not isinstance(payload, dict):
        return False
    for key in ("event_concepts", "results", "futures", "futures_families"):
        if payload.get(key):
            return True
    return False


def search_concept_first(payload: dict) -> bool:
    """Readability signal (soft): did a concept/event page or a futures market
    lead the results, rather than only a tangential team/typeahead hit? Surfaced
    in the scorecard, not a hard fail (v1 keeps findability as the bar)."""
    if not isinstance(payload, dict):
        return False
    return bool(payload.get("event_concepts") or payload.get("futures") or payload.get("results"))


def search_top1_matches(payload: dict, kind: str, marker: str) -> bool:
    """Does the LEADING item of ``kind`` in the search payload contain ``marker``?

    kind="concept" → the first ``event_concepts`` entry's ``key`` (concept hubs are
    prepended by the query-concept detectors, so index 0 is the detected surface).
    kind="team"    → the first ``teams`` entry's ``name``.
    Case-insensitive substring. Pure (unit-tested — no network)."""
    if not isinstance(payload, dict):
        return False
    marker = (marker or "").lower()
    if kind == "concept":
        concepts = payload.get("event_concepts") or []
        if not concepts:
            return False
        return marker in str((concepts[0] or {}).get("key", "")).lower()
    if kind == "team":
        teams = payload.get("teams") or []
        if not teams:
            return False
        return marker in str((teams[0] or {}).get("name", "")).lower()
    return False


def gold_top1_misses(results: list[dict]) -> list[dict]:
    """Top-1 entries whose expected leading surface is NOT top-1 — the fileable
    failures for the top-1 correctness flow."""
    return [r for r in results if not r["top1_ok"]]


def gold_set_regressions(results: list[dict]) -> list[dict]:
    """From per-entity results, the regressions: expected-found entities that now
    return nothing. These are the fileable failures — a search that WORKED broke."""
    return [r for r in results if r["expected_found"] and not r["found"]]


def gold_set_recoveries(results: list[dict]) -> list[dict]:
    """Expected-miss entities that now return something — good news, surfaced but
    never filed (the frozen baseline can be tightened once they stick)."""
    return [r for r in results if not r["expected_found"] and r["found"]]


def event_dup_key(event: dict) -> str | None:
    """Stable real-world-event key: sport + normalized team pair + commence day.
    Two events sharing this key are the same game ingested twice (unmerged
    duplicate — failure class #2). Returns None when the row lacks the fields to
    judge (skip, don't false-positive)."""
    sport = (event.get("sport") or "").strip().lower()
    home = (event.get("home_team") or "").strip().lower()
    away = (event.get("away_team") or "").strip().lower()
    # Minute granularity (YYYY-MM-DDTHH:MM), NOT day: a true unmerged duplicate
    # shares the exact commence_time (same ingestion), while a legitimate
    # doubleheader / best-of series has DIFFERENT start times — day granularity
    # would false-positive those, minute granularity does not.
    commence = (event.get("commence_time") or "")[:16]
    if not (sport and home and away and len(commence) >= 16):
        return None
    pair = "|".join(sorted((home, away)))  # order-independent (home/away swaps)
    return f"{sport}::{pair}::{commence}"


def find_duplicate_events(events: list[dict]) -> list[dict]:
    """Group events by real-world key; return one record per key seen >1 time."""
    seen: dict[str, list[int]] = {}
    meta: dict[str, dict] = {}
    for e in events:
        k = event_dup_key(e)
        if not k:
            continue
        seen.setdefault(k, []).append(e.get("id"))
        meta.setdefault(k, e)
    dups = []
    for k, ids in seen.items():
        if len(ids) > 1:
            e = meta[k]
            dups.append({
                "key": k,
                "event_ids": ids,
                "home_team": e.get("home_team"),
                "away_team": e.get("away_team"),
                "sport": e.get("sport"),
            })
    return dups


def _parse_commence(ct: str | None):
    """Parse an ISO commence_time to an aware datetime, or None if unparseable."""
    if not ct:
        return None
    from datetime import datetime

    try:
        return datetime.fromisoformat(ct.replace("Z", "+00:00"))
    except (ValueError, TypeError):
        return None


def stale_live_events(events: list[dict], now, max_age_hours: float) -> list[dict]:
    """status='live' events whose game started > max_age_hours ago — stuck
    rendering live long after they settled (resolved-shown-as-live, failure #4).
    ``now`` is injected for testability."""
    out = []
    for e in events:
        if e.get("status") != "live":
            continue
        t = _parse_commence(e.get("commence_time"))
        if t is None:
            continue
        age_h = (now - t).total_seconds() / 3600.0
        if age_h > max_age_hours:
            out.append({"event_id": e.get("id"), "sport": e.get("sport"),
                        "home_team": e.get("home_team"), "away_team": e.get("away_team"),
                        "age_hours": round(age_h, 1)})
    return out


def future_settled_events(events: list[dict], now) -> list[dict]:
    """status in (completed/closed) events whose commence_time is in the FUTURE —
    settled before they started (a resolved-state data bug). ``now`` injected."""
    out = []
    for e in events:
        if e.get("status") not in ("completed", "closed"):
            continue
        t = _parse_commence(e.get("commence_time"))
        if t is None or t <= now:
            continue
        out.append({"event_id": e.get("id"), "sport": e.get("sport"),
                    "home_team": e.get("home_team"), "away_team": e.get("away_team"),
                    "commence_time": e.get("commence_time")})
    return out


def inverted_completed_events(events: list[dict]) -> list[dict]:
    """completed/closed events whose ``completed_at`` PRECEDES their
    ``commence_time`` — a game recorded as finishing before it started. This is
    the #190/#189 cross-merged-events class (gotcha #32): ESPN's finished-game
    handling folded an earlier same-matchup game's terminal state onto a later
    sibling. Root cause of empty settled charts + impossible My-Stuff dates. With
    the write-side guards deployed this should be 0 going forward, so any new hit
    is a genuine regression the sentinel files."""
    out = []
    for e in events:
        if e.get("status") not in ("completed", "closed"):
            continue
        commence = _parse_commence(e.get("commence_time"))
        completed = _parse_commence(e.get("completed_at"))
        if commence is None or completed is None:
            continue
        if completed < commence:
            out.append({
                "event_id": e.get("id"), "sport": e.get("sport"),
                "home_team": e.get("home_team"), "away_team": e.get("away_team"),
                "commence_time": e.get("commence_time"),
                "completed_at": e.get("completed_at"),
                "inversion_hours": round((commence - completed).total_seconds() / 3600.0, 1),
            })
    return out


def game_markets_empty(gm: dict) -> bool:
    """True when a game-markets payload has no real markets in ANY section — a
    live Tier-1 event with this is a completeness failure (#3)."""
    if not isinstance(gm, dict):
        return True
    sections = ("totals", "player_props", "team_totals", "spreads",
                "period_markets", "matchups", "other")
    return not any(gm.get(s) for s in sections)


def feed_event_card_count(feed_items: Any) -> int:
    """Number of game/event cards in a /api/feed items list. The Sports tab is
    built from these — zero of them while live games exist is the #1091 empty-tab
    regression."""
    if not isinstance(feed_items, list):
        return 0
    return sum(1 for i in feed_items if isinstance(i, dict) and i.get("type") == "event")


def overnormalized_participation_family(
    detail: dict, min_outcomes: int = 5, sum_lo: float = 0.9, sum_hi: float = 1.1
) -> bool:
    """True when a NON-mutually-exclusive futures family has been squashed to sum
    ~100% on its detail rail (#199, The Open marquee-rail bug).

    Golf make-cut / top-5 / top-N are ``mutually_exclusive=False`` — MANY outcomes
    are simultaneously true, so an honest displayed distribution sums to several
    multiples of 100% (make-cut ~7800%, top-5 ~500%). If the #23 normalizer wrongly
    runs on such a family, the whole set is divided down to sum ~1.0, turning an
    honest 87% make-cut into ~1%. A displayed sum of ~100% on an ME=False family
    with n>=5 priced outcomes is that regression. (ME=True fields are supposed to
    sum ~100%, so they are never flagged.)"""
    if detail.get("mutually_exclusive") is not False:
        return False
    outs = [
        o for o in (detail.get("outcomes") or [])
        if isinstance(o, dict) and o.get("probability")
    ]
    if len(outs) < min_outcomes:
        return False
    total = sum(float(o["probability"]) for o in outs)
    return sum_lo <= total <= sum_hi


def chart_density_tile_broken(tile) -> bool:
    """#1147: True when the chart_density tile is a BROKEN MEASUREMENT rather than a
    real reading — missing, or degraded to ``{"error": ...}`` / ``{"skipped": ...}``
    because the census SQL hit its statement_timeout with no prior good value. A
    broken measurement must be SKIPPED, never filed as a RED (cry-wolf); only a
    valid numeric below-bar reading is a real defect."""
    if tile is None:
        return True
    if not isinstance(tile, dict):
        return True
    if tile.get("error") or tile.get("skipped"):
        return True
    return tile.get("overall_below_bar_pct") is None


def chart_density_verdict(tile: dict, threshold: float) -> tuple[bool, dict]:
    """(passed, evidence) for the chart_density tile. Fails when the overall
    below-bar fraction exceeds the (tunable) threshold. Missing/errored tile is a
    fail with an explicit reason (the measurement itself is broken)."""
    if not isinstance(tile, dict) or tile.get("error") or tile.get("overall_below_bar_pct") is None:
        return False, {"reason": "chart_density tile missing or errored", "tile": tile}
    pct = float(tile["overall_below_bar_pct"])
    ev = {
        "overall_below_bar_pct": pct,
        "threshold": threshold,
        "bar_points_per_hour": tile.get("bar_points_per_hour"),
        "by_source": tile.get("by_source"),
    }
    return pct <= threshold, ev


_FEED_QUALITY_TARGETS = (
    ("boring_count", 0, "boring-rate@20"),
    ("ladder_count", 0, "ladder-rate@20"),
    ("duplicate_family_count", 0, "duplicate-family-rate@20"),
)


def feed_quality_failures(summary: dict, top_n: int = FEED_QUALITY_TOP_N) -> list[dict]:
    """Feed-quality @20 target misses (CLAUDE.md production targets): boring,
    ladder, duplicate-family must be 0; explanation-coverage must be top_n/top_n."""
    fails = []
    for key, target, label in _FEED_QUALITY_TARGETS:
        val = summary.get(key)
        if val is None:
            continue
        if val > target:
            fails.append({"metric": label, "value": val, "target": target})
    exp = summary.get("explanation_ok_count")
    if exp is not None and exp < top_n:
        fails.append({"metric": f"explanation-coverage@{top_n}", "value": exp, "target": top_n})
    return fails


def flow_fingerprint(flow_key: str) -> str:
    """Stable 12-char fingerprint per flow — one deduped issue per failing flow;
    re-runs comment on the open issue instead of filing a duplicate (design §4)."""
    return hashlib.sha1(f"flow:{flow_key}".encode("utf-8")).hexdigest()[:12]


def severity_for_flow(flow_key: str, failed_count: int, checked: int) -> str:
    """P1 when a flow is broadly broken (>=50% of checks fail or the whole flow
    is dark), else P2. Chart density (a tracked backlog) caps at P2."""
    if flow_key == "chart_density":
        return "P2"
    if checked and failed_count / checked >= 0.5:
        return "P1"
    return "P2"


# ---------------------------------------------------------------------------
# Live flow runners (HTTP against production)
# ---------------------------------------------------------------------------
async def _get_json(client: httpx.AsyncClient, path: str, params: dict | None = None) -> Any:
    resp = await client.get(path, params=params)
    resp.raise_for_status()
    return resp.json()


async def _run_search_gold_set(client: httpx.AsyncClient, canary: bool) -> dict:
    import asyncio

    gold = list(GOLD_SET)
    if canary:
        gold.append((CANARY_QUERY, True))  # guaranteed regression → proves filing

    sem = asyncio.Semaphore(SEARCH_CONCURRENCY)

    async def _one(query: str, expected: bool) -> dict:
        async with sem:
            try:
                payload = await _get_json(client, "/api/events/search", {"q": query})
                found = search_found(payload)
                return {
                    "query": query, "expected_found": expected, "found": found,
                    "concept_first": search_concept_first(payload),
                    "counts": {
                        k: len(payload.get(k, [])) if isinstance(payload.get(k), list) else 0
                        for k in ("event_concepts", "results", "futures", "futures_families")
                    },
                }
            except Exception as exc:
                return {"query": query, "expected_found": expected, "found": False,
                        "error": str(exc)[:150]}

    results = await asyncio.gather(*[_one(q, e) for q, e in gold])
    regressions = gold_set_regressions(results)
    recoveries = gold_set_recoveries(results)
    found_n = sum(1 for r in results if r["found"])
    return {
        "flow": "search_gold_set",
        "checked": len(results),
        "passed": len(regressions) == 0,
        "failures": [{"query": r["query"], "detail": "expected-found entity now returns nothing"}
                     for r in regressions],
        "evidence": {
            "found": found_n,
            "total": len(results),
            "regressions": [r["query"] for r in regressions],
            "recoveries": [r["query"] for r in recoveries],
            "per_entity": results,
        },
    }


async def _run_search_gold_top1(client: httpx.AsyncClient) -> dict:
    """#1206 / Queue #246 Item 1 — TOP-1 CORRECTNESS: for each unambiguous family
    query, the RIGHT surface (concept hub / curated-alias team) must LEAD, not just
    appear somewhere. Files each miss (the metric #244 proved we need now that
    findability is solved)."""
    import asyncio

    sem = asyncio.Semaphore(SEARCH_CONCURRENCY)

    async def _one(query: str, kind: str, marker: str) -> dict:
        async with sem:
            try:
                payload = await _get_json(client, "/api/events/search", {"q": query})
                return {
                    "query": query, "kind": kind, "marker": marker,
                    "top1_ok": search_top1_matches(payload, kind, marker),
                }
            except Exception as exc:
                return {"query": query, "kind": kind, "marker": marker,
                        "top1_ok": False, "error": str(exc)[:150]}

    results = await asyncio.gather(*[_one(q, k, m) for q, k, m in GOLD_SET_TOP1])
    misses = gold_top1_misses(results)
    ok_n = sum(1 for r in results if r["top1_ok"])
    return {
        "flow": "search_gold_top1",
        "checked": len(results),
        "passed": len(misses) == 0,
        "failures": [
            {"query": r["query"],
             "detail": f"'{r['query']}' expected top-1 {r['kind']} matching "
                       f"'{r['marker']}' — not the leading result"}
            for r in misses
        ],
        "evidence": {
            "top1_ok": ok_n,
            "total": len(results),
            "top1_rate": round(ok_n / len(results), 3) if results else 0,
            "misses": [r["query"] for r in misses],
            "per_entity": results,
        },
    }


async def _sample_events(client: httpx.AsyncClient, status: str, limit: int) -> list[dict]:
    try:
        data = await _get_json(client, "/api/events", {"status": status, "limit": limit})
        return data.get("events", []) if isinstance(data, dict) else (data or [])
    except Exception as exc:
        logger.warning("flow sentinel: event sample (%s) failed: %s", status, exc)
        return []


async def _run_duplicate_events(client: httpx.AsyncClient) -> dict:
    # A broad live+scheduled slate is where an unmerged duplicate would show.
    events = await _sample_events(client, "live", 200)
    events += await _sample_events(client, "scheduled", 200)
    dups = find_duplicate_events(events)
    return {
        "flow": "duplicate_events",
        "checked": len(events),
        "passed": len(dups) == 0,
        "failures": [{"detail": f"{d['sport']}: {d['home_team']} vs {d['away_team']} "
                                f"appears {len(d['event_ids'])}x (ids {d['event_ids']})"}
                     for d in dups],
        "evidence": {"sampled": len(events), "duplicates": dups},
    }


async def _run_event_completeness(client: httpx.AsyncClient) -> dict:
    # Live Tier-1 games MUST have markets. Scheduled-far games can legitimately be
    # empty (upstream), so we only hard-check LIVE Tier-1 events.
    live = await _sample_events(client, "live", 200)
    tier1_live = [e for e in live if (e.get("sport") in TIER1_SPORTS)][:EVENT_SAMPLE_SIZE]
    failures, checked = [], 0
    for e in tier1_live:
        eid = e.get("id")
        if eid is None:
            continue
        checked += 1
        try:
            gm = await _get_json(client, f"/api/events/{eid}/game-markets")
        except Exception as exc:
            failures.append({"event_id": eid, "detail": f"game-markets errored: {str(exc)[:120]}"})
            continue
        if game_markets_empty(gm):
            failures.append({
                "event_id": eid,
                "detail": f"live {e.get('sport')} game {e.get('home_team')} vs "
                          f"{e.get('away_team')} has zero markets in every section",
            })
    return {
        "flow": "event_completeness",
        "checked": checked,
        "passed": len(failures) == 0,
        "failures": failures,
        "evidence": {"live_tier1_sampled": checked, "no_live_tier1": checked == 0},
    }


async def _run_sports_feed_events(client: httpx.AsyncClient) -> dict:
    # The Sports tab (iOS FeedViewModel) backfills game cards from
    # /api/feed?include_futures=false and filters client-side to type=="event".
    # If live games exist but the feed returns ZERO event cards, the Sports tab is
    # empty — the #1091 regression, where one malformed event raised mid-loop and
    # wiped the entire event feed. This is the flow that would have caught it
    # (r189 recommendation). We only assert when there is a live slate to compare
    # against, so an upstream-quiet window is not a false failure.
    live = await _sample_events(client, "live", 200)
    live_count = len(live)
    if live_count == 0:
        return {
            "flow": "sports_feed_events",
            "checked": 0,
            "passed": True,
            "skipped": True,
            "failures": [],
            "evidence": {"live_sampled": 0, "reason": "no live games to assert against"},
        }
    try:
        feed = await _get_json(
            client, "/api/feed", {"limit": "200", "include_futures": "false"}
        )
        items = feed.get("items", []) if isinstance(feed, dict) else []
        event_cards = feed_event_card_count(items)
    except Exception as exc:
        return {
            "flow": "sports_feed_events",
            "checked": 1,
            "passed": False,
            "failures": [{"detail": f"/api/feed?include_futures=false errored: {str(exc)[:120]}"}],
            "evidence": {"live_sampled": live_count, "error": str(exc)[:200]},
        }
    passed = event_cards > 0
    failures = (
        []
        if passed
        else [{
            "detail": f"{live_count} live games exist but /api/feed?include_futures=false "
                      f"returned 0 event cards — the Sports tab is empty (#1091 regression)",
        }]
    )
    return {
        "flow": "sports_feed_events",
        "checked": 1,
        "passed": passed,
        "failures": failures,
        "evidence": {"live_sampled": live_count, "feed_event_cards": event_cards},
    }


async def _run_resolved_state(client: httpx.AsyncClient) -> dict:
    # Resolved-state correctness (failure class #4): a settled game must never
    # keep rendering as live, and a settled row must not predate its own game.
    # We assert on the AUTHORITATIVE list fields (status + commence_time) — the
    # detail endpoints' status/event_status fields are populated inconsistently
    # (empty for market-less / some live events), so they cannot back an auto-file.
    from datetime import datetime, timezone

    now = datetime.now(timezone.utc)
    live = await _sample_events(client, "live", 200)
    completed = await _sample_events(client, "completed", 200)
    stale = stale_live_events(live, now, STALE_LIVE_HOURS)
    future = future_settled_events(completed, now)
    inverted = inverted_completed_events(completed)
    failures = [
        {"detail": f"live {s['sport']} game {s['home_team']} vs {s['away_team']} "
                   f"started {s['age_hours']}h ago but still renders LIVE (id {s['event_id']})"}
        for s in stale
    ] + [
        {"detail": f"settled {f['sport']} event {f['home_team']} vs {f['away_team']} "
                   f"has a FUTURE commence_time {f['commence_time']} (id {f['event_id']})"}
        for f in future
    ] + [
        {"detail": f"settled {i['sport']} event {i['home_team']} vs {i['away_team']} "
                   f"has completed_at {i['completed_at']} BEFORE commence_time "
                   f"{i['commence_time']} ({i['inversion_hours']}h inverted, id "
                   f"{i['event_id']}) — cross-merged event (#190/gotcha #32)"}
        for i in inverted
    ]
    return {
        "flow": "resolved_state",
        "checked": len(live) + len(completed),
        "passed": len(failures) == 0,
        "failures": failures,
        "evidence": {
            "live_sampled": len(live), "completed_sampled": len(completed),
            "stale_live_hours": STALE_LIVE_HOURS,
            "stale_live": stale, "future_settled": future,
            "inverted_completed": inverted,
        },
    }


async def _run_chart_density(client: httpx.AsyncClient) -> dict:
    admin_token = os.environ.get("ADMIN_TOKEN", "")
    tile = None
    err = None
    try:
        data = await _get_json(client, "/api/admin/backfill-progress",
                               {"secret": admin_token} if admin_token else None)
        census = data.get("census") if isinstance(data, dict) else None
        tile = census.get("chart_density") if isinstance(census, dict) else None
    except Exception as exc:
        err = str(exc)[:150]
    # #1147: a MISSING tile, or a DEGRADED one (the census tile query hit its
    # statement_timeout and _degrade returned {"error": ...} / {"skipped": ...} with
    # no prior good value), is a BROKEN MEASUREMENT — not evidence of a real density
    # collapse. Filing a RED on our own broken measurement is exactly the cry-wolf
    # #1147 flagged. Treat it as skipped; only a valid numeric below-bar reading fires.
    if chart_density_tile_broken(tile):
        reason = err or (
            (tile or {}).get("error")
            or (tile or {}).get("skipped")
            or "chart_density tile unavailable / degraded"
            if isinstance(tile, dict)
            else (err or "chart_density tile unavailable")
        )
        return {
            "flow": "chart_density", "checked": 0, "passed": True,
            "failures": [],
            "evidence": {"skipped": True, "reason": reason},
            "skipped": True,
        }
    passed, ev = chart_density_verdict(tile, CHART_DENSITY_MAX_BELOW_BAR_PCT)
    return {
        "flow": "chart_density",
        "checked": 1,
        "passed": passed,
        "failures": [] if passed else [{
            "detail": f"{ev.get('overall_below_bar_pct')}% of user-visible charts below "
                      f"the {ev.get('bar_points_per_hour')}pt/open-hour bar "
                      f"(threshold {ev.get('threshold')}%)"}],
        "evidence": ev,
    }


async def _run_category_discover(client: httpx.AsyncClient) -> dict:
    failures = []
    checked = 0

    # (a) Category pages non-empty.
    for path, empty_check in (
        ("/api/politics", lambda d: (d.get("total_markets") or 0) <= 0),
        ("/api/economics", lambda d: (d.get("total_markets") or 0) <= 0),
        ("/api/entertainment", lambda d: (d.get("total_markets") or 0) <= 0 or d.get("error")),
        ("/api/weather/featured", lambda d: not (d if isinstance(d, list) else [])),
    ):
        checked += 1
        try:
            data = await _get_json(client, path)
            if empty_check(data):
                failures.append({"detail": f"{path} returned empty content"})
        except Exception as exc:
            failures.append({"detail": f"{path} errored: {str(exc)[:120]}"})

    # (b) Discover first page non-empty + quality-capped (@20 targets).
    checked += 1
    try:
        feed = await _get_json(client, "/api/feed",
                               {"limit": "50", "include_events": "false", "include_futures": "true"})
        items = [i for i in feed.get("items", []) if i.get("type") == "futures"]
        if not items:
            failures.append({"detail": "/api/feed first page returned zero futures items"})
        else:
            from app.utils.feed_quality_debug import build_feed_quality_debug

            debug = build_feed_quality_debug(items, ground_truth_items=[], top_n=FEED_QUALITY_TOP_N)
            fq_fails = feed_quality_failures(debug["summary"])
            for f in fq_fails:
                failures.append({"detail": f"feed {f['metric']}={f['value']} (target {f['target']})"})
    except Exception as exc:
        failures.append({"detail": f"/api/feed quality check errored: {str(exc)[:120]}"})

    return {
        "flow": "category_discover",
        "checked": checked,
        "passed": len(failures) == 0,
        "failures": failures,
        "evidence": {"checks": checked},
    }


async def _run_participation_family(client: httpx.AsyncClient) -> dict:
    """#199: a non-mutually-exclusive prop family (golf make-cut / top-N) must NEVER
    render as a sum-to-1 distribution — that squashed an honest 87% make-cut to ~1%
    on The Open's detail/ladder rail. Sample golf prop markets whose names look like
    participation families, pull each detail, and assert none are over-normalized.
    This class files itself next time it recurs."""
    failures: list[dict] = []
    checked = 0
    prop_name_re = re.compile(
        r"\b(make\s+the?\s*cut|top\s*\d+|round\s*\d+\s*leader|to\s+finish)\b", re.I
    )
    try:
        faceted = await _get_json(
            client, "/api/futures/faceted", {"sport_category": "golf", "limit": "40"}
        )
        markets = faceted.get("markets", []) if isinstance(faceted, dict) else []
    except Exception as exc:
        return {
            "flow": "participation_family",
            "checked": 0,
            "passed": True,
            "skipped": True,
            "failures": [],
            "evidence": {"reason": f"faceted golf errored: {str(exc)[:100]}"},
        }

    candidates = [
        m for m in markets
        if isinstance(m, dict)
        and (m.get("outcome_count") or 0) >= 5
        and prop_name_re.search(m.get("name") or "")
    ][:PARTICIPATION_SAMPLE_SIZE]

    for m in candidates:
        mid = m.get("id")
        if mid is None:
            continue
        try:
            detail = await _get_json(client, f"/api/futures/{mid}")
        except Exception as exc:
            failures.append({"market_id": mid, "detail": f"detail errored: {str(exc)[:100]}"})
            continue
        # Only ME=False families are eligible; detector guards that internally.
        if detail.get("mutually_exclusive") is not False:
            continue
        checked += 1
        if overnormalized_participation_family(detail):
            outs = [o for o in (detail.get("outcomes") or []) if o.get("probability")]
            total = sum(float(o["probability"]) for o in outs)
            failures.append({
                "market_id": mid,
                "detail": f"non-ME family '{(detail.get('name') or '')[:50]}' "
                          f"({len(outs)} outcomes) displayed sum={total:.2f} ~100% — "
                          f"squashed by #23 normalizer (#199); should sum >>100%",
            })

    return {
        "flow": "participation_family",
        "checked": checked,
        "passed": len(failures) == 0,
        "skipped": checked == 0,
        "failures": failures,
        "evidence": {
            "golf_prop_markets_sampled": checked,
            "no_eligible_markets": checked == 0,
        },
    }


async def _run_matured_linkage(client: httpx.AsyncClient) -> dict:
    """Queue #220/221 Item 2 — the matured-linkage flow. For imminent events
    (≤24h), a prediction-market source that is in the blend (win_probability_
    sources) but has NO linked winner market is a phantom source — a real defect
    (Alex: below-100 must MEAN something). Reads the precomputed metric from
    Redis (kept warm every 10 min by precompute_admin_matured_linkage) and files
    each miss as an (event, source) pair. Decoupled + read-only: the sentinel
    files work, it never writes data."""
    payload = None
    try:
        import json as _json

        from app.tasks.redis_state import get_redis_client

        cached = get_redis_client().get("bainluck:admin:matured_linkage")
        if cached:
            payload = _json.loads(cached)
    except Exception as exc:
        return {
            "flow": "matured_linkage",
            "checked": 0,
            "passed": True,
            "skipped": True,
            "failures": [],
            "evidence": {"reason": f"matured-linkage cache read failed: {str(exc)[:120]}"},
        }

    if not payload or payload.get("status") != "ok":
        return {
            "flow": "matured_linkage",
            "checked": 0,
            "passed": True,
            "skipped": True,
            "failures": [],
            "evidence": {
                "reason": (payload or {}).get("status", "cache cold — beat has not run"),
            },
        }

    misses = payload.get("misses") or []
    failures = [
        {
            "event_id": m.get("event_id"),
            "source": m.get("source"),
            "detail": f"imminent {m.get('sport')} event {m.get('matchup')} carries "
                      f"{m.get('source')} in its blend but has NO linked {m.get('source')} "
                      f"winner market (phantom blend source; event {m.get('event_id')})",
        }
        for m in misses
    ]
    return {
        "flow": "matured_linkage",
        "checked": payload.get("checkable_pairs", 0),
        "passed": len(failures) == 0,
        "failures": failures,
        "evidence": {
            "headline_pct": payload.get("headline_pct"),
            "checkable_pairs": payload.get("checkable_pairs"),
            "backed": payload.get("backed"),
            "phantom": payload.get("phantom"),
            "by_source": payload.get("by_source"),
            "events_checked": payload.get("events_checked"),
            "events_consistent": payload.get("events_consistent"),
            "window": payload.get("window"),
        },
    }


async def _run_unlinked_held(client: httpx.AsyncClient) -> dict:
    """Queue #223 Item 4 — the STRONGER linkage flow (Alex's ruling). Distinct from
    matured_linkage: that finds a blend source with no market; THIS finds a game-
    winner market we ALREADY HOLD (Kalshi/Poly, open, event_id NULL) whose both teams
    match an imminent event — the matcher missed a link it could have made. Reads the
    ``unlinked_held`` block of the precomputed matured-linkage metric from Redis (kept
    warm every 10 min) and files each miss. Read-only — the sentinel files work."""
    payload = None
    try:
        import json as _json

        from app.tasks.redis_state import get_redis_client

        cached = get_redis_client().get("bainluck:admin:matured_linkage")
        if cached:
            payload = (_json.loads(cached) or {}).get("unlinked_held")
    except Exception as exc:
        return {
            "flow": "unlinked_held",
            "checked": 0,
            "passed": True,
            "skipped": True,
            "failures": [],
            "evidence": {"reason": f"unlinked-held cache read failed: {str(exc)[:120]}"},
        }

    if not payload or payload.get("status") != "ok":
        return {
            "flow": "unlinked_held",
            "checked": 0,
            "passed": True,
            "skipped": True,
            "failures": [],
            "evidence": {"reason": (payload or {}).get("status", "cache cold — beat has not run")},
        }

    misses = payload.get("misses") or []
    failures = [
        {
            "event_id": m.get("event_id"),
            "source": m.get("source"),
            "detail": f"imminent {m.get('sport')} event {m.get('matchup')} — we hold "
                      f"unlinked {m.get('source')} market #{m.get('market_id')} "
                      f"'{m.get('market_name')}' whose both teams match this event, but "
                      f"event_id is NULL (matcher miss; event {m.get('event_id')})",
        }
        for m in misses
    ]
    return {
        "flow": "unlinked_held",
        "checked": payload.get("candidates_scanned", 0),
        "passed": len(failures) == 0,
        "failures": failures,
        "evidence": {
            "headline_unlinked_held": payload.get("headline_unlinked_held"),
            "events_checked": payload.get("events_checked"),
            "candidates_scanned": payload.get("candidates_scanned"),
            "by_source": payload.get("by_source"),
        },
    }


# The season-aggregate market families that must NEVER carry an event_id: a
# season-long two-team comparison is a FUTURES market, not one game. Mirrors the
# Queue #238 `_SEASON_AGGREGATE_KEYWORDS` guard (prevention) and the
# `repair_season_series_mislinks.py` predicate (repair). This is the standing
# REGRESSION guard #1220 asked for — if the guard ever regresses, a new mislink
# gets caught here and auto-filed.
_SEASON_AGG_LINKAGE_SQL = (
    "SELECT COUNT(*) AS n FROM futures_markets fm WHERE fm.event_id IS NOT NULL AND ("
    "fm.name ILIKE '%Head-to-Head Win Total%' "
    "OR fm.name ILIKE '%Season Series Winner%' "
    "OR fm.name ILIKE '%Season Win Total%' "
    "OR fm.name ILIKE '%make the playoffs%')"
)


async def _run_season_aggregate_linkage(client: httpx.AsyncClient) -> dict:
    """#1220 regression guard: a season-aggregate market (Head-to-Head Win Total,
    Season Series Winner, Season Win Total, make-the-playoffs) linked to a single
    game event is a matching bug — it surfaces the season market on the wrong event
    page and can fabricate a bogus `*_other` FINAL card. Prevention shipped in Queue
    #238 and the backlog was repaired; this asserts the census stays 0. Reads via
    the admin db-query (read-only). A missing/broken admin path is SKIPPED, never
    filed — filing on our own broken measurement is the cry-wolf #1147 flagged."""
    admin_token = os.environ.get("ADMIN_TOKEN", "")
    if not admin_token:
        return {
            "flow": "season_aggregate_linkage", "checked": 0, "passed": True,
            "skipped": True, "failures": [],
            "evidence": {"reason": "ADMIN_TOKEN unset — db-query unavailable"},
        }
    try:
        resp = await client.post(
            "/api/admin/db-query",
            params={"secret": admin_token},
            json={"sql": _SEASON_AGG_LINKAGE_SQL, "limit": 1},
        )
        resp.raise_for_status()
        data = resp.json()
        rows = data.get("rows") if isinstance(data, dict) else None
        linked = int(rows[0][0]) if rows and rows[0] else 0
    except Exception as exc:
        return {
            "flow": "season_aggregate_linkage", "checked": 0, "passed": True,
            "skipped": True, "failures": [],
            "evidence": {"reason": f"db-query failed: {str(exc)[:120]}"},
        }
    failures = (
        [{"detail": f"{linked} season-aggregate market(s) (Head-to-Head/Season "
                    f"Series/Win Total/make-the-playoffs) carry an event_id — a "
                    f"season-long comparison mislinked to one game (#1220; run "
                    f"scripts/repair_season_series_mislinks.py --apply)"}]
        if linked > 0 else []
    )
    return {
        "flow": "season_aggregate_linkage",
        "checked": 1,
        "passed": linked == 0,
        "failures": failures,
        "evidence": {"season_aggregate_linked_markets": linked},
    }


# Clusters awaiting HUMAN adjudication (L2-173) is a needs-user backlog, not an
# agent-fixable bug — a small standing queue is normal. It only alarms past a
# conservative backlog size so its CLIMB is visible without crying wolf on the
# handful that always await Alex's verdict.
_AWAITING_ADJUDICATION_ALARM = 25


async def _run_team_identity_dupes(client: httpx.AsyncClient) -> dict:
    """#247 Item 2 / #1204 — the team-identity dupe class files ITSELF. Two
    DB-derived signals, read-only:

      • ``unresolved`` SAFE auto-mergeable bare-location stub pairs — should be 0
        after a clean run of the merge rail. >0 means the auto-merge regressed or
        did not run (a REAL, agent-fixable failure: run the repair with apply).
      • ``awaiting`` clusters queued for HUMAN adjudication (L2-173) — surfaced
        always; alarms only past ``_AWAITING_ADJUDICATION_ALARM`` since clearing
        it needs Alex's verdicts, not an agent.

    Reads the repairs dry-run census (no writes) + the pending-clusters summary.
    A broken/absent admin path is SKIPPED, never filed — filing on our own broken
    measurement is the #1147 cry-wolf."""
    admin_token = os.environ.get("ADMIN_TOKEN", "")
    if not admin_token:
        return {
            "flow": "team_identity_dupes", "checked": 0, "passed": True,
            "skipped": True, "failures": [],
            "evidence": {"reason": "ADMIN_TOKEN unset — admin endpoints unavailable"},
        }
    try:
        # apply=false → dry-run census only, no writes.
        r1 = await client.post(
            "/api/admin/repairs/team-identity-merge",
            params={"secret": admin_token, "apply": "false"},
        )
        r1.raise_for_status()
        census = r1.json() or {}
        r2 = await client.get(
            "/api/admin/team-clusters/pending",
            params={"secret": admin_token, "summary": "true"},
        )
        r2.raise_for_status()
        awaiting = int((r2.json() or {}).get("awaiting", 0) or 0)
    except Exception as exc:
        return {
            "flow": "team_identity_dupes", "checked": 0, "passed": True,
            "skipped": True, "failures": [],
            "evidence": {"reason": f"admin endpoint failed: {str(exc)[:120]}"},
        }

    unresolved = int(census.get("pairs_remaining", census.get("pairs_planned", 0)) or 0)
    failures = []
    if unresolved > 0:
        failures.append({
            "detail": f"{unresolved} SAFE auto-mergeable team-identity dupe pair(s) "
                      f"remain (bare-location stub folds) — the merge rail did not "
                      f"run or regressed. Fix: POST /api/admin/repairs/"
                      f"team-identity-merge?apply=true until pairs_remaining=0 "
                      f"(#1204 / Queue #247).",
        })
    if awaiting >= _AWAITING_ADJUDICATION_ALARM:
        failures.append({
            "detail": f"{awaiting} team-identity clusters awaiting HUMAN adjudication "
                      f"(L2-173) — backlog exceeds {_AWAITING_ADJUDICATION_ALARM}. "
                      f"Needs Alex's verdicts at /admin (team-clusters), not an "
                      f"agent fix. (needs-user)",
        })
    return {
        "flow": "team_identity_dupes",
        "checked": 2,
        "passed": len(failures) == 0,
        "failures": failures,
        "evidence": {
            "unresolved_mergeable_pairs": unresolved,
            "awaiting_adjudication": awaiting,
            "awaiting_alarm_threshold": _AWAITING_ADJUDICATION_ALARM,
            "clusters_planned": census.get("clusters_planned"),
            "clusters_examined": census.get("clusters_examined"),
        },
    }


# ---------------------------------------------------------------------------
# Evidence-pack rendering (the GitHub issue body)
# ---------------------------------------------------------------------------
def build_flow_issue_title(flow_result: dict) -> str:
    flow = flow_result["flow"]
    n = len(flow_result["failures"])
    title = f"[Flow Sentinel] {_FLOW_TITLES.get(flow, flow)} ({n} failing, {flow_result['checked']} checked)"
    return title[:256]


def build_flow_issue_body(flow_result: dict) -> str:
    flow = flow_result["flow"]
    fp = flow_fingerprint(flow)
    parts = [
        "## Flow Sentinel finding",
        "",
        f"`flow-sentinel-fingerprint:{fp}`  (dedupe key — do not remove)",
        "",
        f"**Flow:** `{flow}` — {_FLOW_TITLES.get(flow, flow)}  ",
        f"**Checks run:** {flow_result['checked']}  ",
        f"**Failing:** {len(flow_result['failures'])}  ",
        f"**Run against:** {FLOW_SENTINEL_API}",
        "",
        "### Failures",
    ]
    for f in flow_result["failures"][:40]:
        parts.append(f"- {f.get('detail') or f}")
    if len(flow_result["failures"]) > 40:
        parts.append(f"- …and {len(flow_result['failures']) - 40} more")

    ev = flow_result.get("evidence") or {}
    if ev:
        import json as _json
        parts += [
            "",
            "### Evidence",
            "```json",
            _json.dumps(ev, default=str, indent=1)[:3500],
            "```",
        ]
    parts += [
        "",
        "---",
        "*Auto-filed by the Flow Sentinel (#1078) — the reliability/design "
        "program's measurement. Read-only detection; the sentinel files work, it "
        "never writes data. Reproduce with "
        "`POST /api/admin/flow-sentinel/run?inline=true&file_issues=false`.*",
    ]
    return "\n".join(parts)


# ---------------------------------------------------------------------------
# Filing + dedup (reuses the bug_report_github httpx client, per calibration
# sentinel — the GITHUB_TOKEN rail is live and proven)
# ---------------------------------------------------------------------------
def issue_matches_flow(issue: dict, flow: str, fingerprint: str) -> bool:
    """True when an OPEN issue is the sentinel's issue for this flow/fingerprint.

    Two match paths (pure, so both are unit-tested):
      * **body marker** — the ``flow-sentinel-fingerprint:{fp}`` dedupe key is in
        the body (the primary key; matched as a plain substring so backticks /
        the colon can't break it, unlike a GitHub quoted-phrase search).
      * **title** — ``[Flow Sentinel] {flow name} (`` prefix. This is the
        fingerprint-equivalent fallback (title name ↔ flow ↔ fingerprint are 1:1)
        that catches an issue whose body marker was edited away.
    """
    if not isinstance(issue, dict):
        return False
    body = issue.get("body") or ""
    if f"flow-sentinel-fingerprint:{fingerprint}" in body:
        return True
    title = issue.get("title") or ""
    name = _FLOW_TITLES.get(flow, flow)
    return title.startswith(f"[Flow Sentinel] {name} (")


def find_matching_open_issue(
    open_issues: list[dict], flow: str, fingerprint: str
) -> int | None:
    """Pure dedup lookup over a list of open issues → matching issue number.

    Returns the LOWEST matching issue number so a stable canonical issue wins
    when duplicates already exist (the r252 cleanup: comment the oldest, not a
    later dupe)."""
    matches = [
        i["number"]
        for i in (open_issues or [])
        if isinstance(i, dict)
        and i.get("number") is not None
        and issue_matches_flow(i, flow, fingerprint)
    ]
    return min(matches) if matches else None


def _list_open_sentinel_issues() -> list[dict]:
    """Fetch OPEN alert-intake issues via the REST list API (strongly consistent,
    unlike the eventually-consistent /search index that let 5 dupes through —
    r252). Returns [] on any error so filing degrades safely."""
    from app.tasks.bug_report_github import GITHUB_TOKEN, REPO

    if not GITHUB_TOKEN:
        return []
    issues: list[dict] = []
    headers = {
        "Authorization": f"Bearer {GITHUB_TOKEN}",
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
    }
    try:
        for page in range(1, 4):  # up to 300 open alert-intake issues — ample
            resp = httpx.get(
                f"https://api.github.com/repos/{REPO}/issues",
                headers=headers,
                params={
                    "state": "open",
                    "labels": "alert-intake",
                    "per_page": 100,
                    "page": page,
                },
                timeout=30,
            )
            resp.raise_for_status()
            batch = resp.json()
            if not isinstance(batch, list) or not batch:
                break
            # Drop PRs (the issues endpoint includes them).
            issues.extend(i for i in batch if "pull_request" not in i)
            if len(batch) < 100:
                break
    except Exception as exc:
        logger.warning("Flow sentinel open-issue list failed: %s", exc)
        return []
    return issues


def _find_open_issue_by_fingerprint(fingerprint: str, flow: str) -> int | None:
    """Reliable dedup: match the fingerprint against the REST-listed OPEN
    alert-intake issues (body marker or title). Falls back to the /search index
    only if the REST list came back empty (e.g. transient error)."""
    open_issues = _list_open_sentinel_issues()
    match = find_matching_open_issue(open_issues, flow, fingerprint)
    if match is not None:
        return match
    if open_issues:
        # REST list succeeded and genuinely has no match → do not file a phantom
        # dupe via the flaky search index; there is no open issue for this flow.
        return None

    # REST list failed (empty) — last-resort search index (kept for safety).
    from app.tasks.bug_report_github import GITHUB_TOKEN, REPO

    if not GITHUB_TOKEN:
        return None
    q = f'repo:{REPO} in:body "flow-sentinel-fingerprint:{fingerprint}" state:open'
    try:
        resp = httpx.get(
            "https://api.github.com/search/issues",
            headers={
                "Authorization": f"Bearer {GITHUB_TOKEN}",
                "Accept": "application/vnd.github+json",
                "X-GitHub-Api-Version": "2022-11-28",
            },
            params={"q": q},
            timeout=30,
        )
        resp.raise_for_status()
        items = resp.json().get("items", [])
        return items[0]["number"] if items else None
    except Exception as exc:
        logger.warning("Flow sentinel dedup search failed for %s: %s", fingerprint, exc)
        return None


def file_flow_issue(flow_result: dict) -> dict:
    """File OR update one issue for a failing flow's fingerprint."""
    from app.tasks.bug_report_github import (
        GITHUB_TOKEN,
        add_to_project_board,
        comment_on_issue,
        create_github_issue,
    )

    flow = flow_result["flow"]
    fp = flow_fingerprint(flow)
    if not GITHUB_TOKEN:
        return {"flow": flow, "fingerprint": fp, "action": "skipped_no_token"}

    existing = _find_open_issue_by_fingerprint(fp, flow)
    if existing:
        try:
            comment_on_issue(
                existing,
                f"Flow Sentinel re-observed this failure: {len(flow_result['failures'])} "
                f"failing of {flow_result['checked']} checked (fingerprint `{fp}`). Still open.",
            )
        except Exception as exc:
            logger.warning("Flow sentinel comment failed on #%d: %s", existing, exc)
        return {"flow": flow, "fingerprint": fp, "action": "commented", "issue": existing}

    severity = severity_for_flow(flow, len(flow_result["failures"]), flow_result["checked"])
    labels = [
        "alert-intake",
        "needs-agent",
        _FLOW_AREA_LABELS.get(flow, "area:infra"),
        f"priority:{severity.lower()}",
    ]
    title = build_flow_issue_title(flow_result)
    body = build_flow_issue_body(flow_result)
    try:
        number, node_id = create_github_issue(title, body, labels)
    except Exception as exc:
        logger.error("Flow sentinel issue creation failed (%s): %s", fp, exc)
        return {"flow": flow, "fingerprint": fp, "action": "error", "error": str(exc)[:200]}
    try:
        add_to_project_board(node_id)
    except Exception:
        logger.warning("Flow sentinel: add issue #%d to board failed (non-fatal)", number, exc_info=True)
    return {"flow": flow, "fingerprint": fp, "action": "filed", "issue": number, "severity": severity}


# ---------------------------------------------------------------------------
# Main entry
# ---------------------------------------------------------------------------
async def _run_flow_sentinel(
    file_issues: bool = True,
    canary: bool = False,
    deadline_seconds: float = 540.0,
) -> dict[str, Any]:
    """Run the seven flows against production, build a scorecard, and (in a live
    run) file ONE deduped issue per failing flow.

    * canary=True appends a synthetic missing gold-set entity so the search flow
      is guaranteed to "regress" — the end-to-end proof that failures file.
    """
    _load_overrides()
    start = _time.monotonic()

    stats: dict[str, Any] = {
        "mode": "live" if file_issues else "detect_only",
        "canary": canary,
        "api": FLOW_SENTINEL_API,
        "config": {
            "chart_density_max_below_bar_pct": CHART_DENSITY_MAX_BELOW_BAR_PCT,
            "event_sample_size": EVENT_SAMPLE_SIZE,
        },
        "flows": [],
        "filed": [],
        "errors": [],
    }

    runners = (
        ("search_gold_set", lambda c: _run_search_gold_set(c, canary)),
        ("search_gold_top1", _run_search_gold_top1),
        ("duplicate_events", _run_duplicate_events),
        ("event_completeness", _run_event_completeness),
        ("sports_feed_events", _run_sports_feed_events),
        ("resolved_state", _run_resolved_state),
        ("chart_density", _run_chart_density),
        ("category_discover", _run_category_discover),
        ("participation_family", _run_participation_family),
        ("matured_linkage", _run_matured_linkage),
        ("unlinked_held", _run_unlinked_held),
        ("season_aggregate_linkage", _run_season_aggregate_linkage),
        ("team_identity_dupes", _run_team_identity_dupes),
    )

    async with httpx.AsyncClient(base_url=FLOW_SENTINEL_API, timeout=HTTP_TIMEOUT,
                                 follow_redirects=True) as client:
        for name, runner in runners:
            if _time.monotonic() - start > deadline_seconds:
                stats["errors"].append({"deadline": f"stopped before {name}"})
                break
            try:
                result = await runner(client)
            except Exception as exc:
                logger.error("Flow sentinel flow %s crashed: %s", name, exc)
                result = {"flow": name, "checked": 0, "passed": False,
                          "failures": [{"detail": f"flow crashed: {str(exc)[:150]}"}],
                          "evidence": {"crash": str(exc)[:200]}}
            stats["flows"].append(result)

    # --- Scorecard ---
    failing = [f for f in stats["flows"] if not f["passed"]]
    stats["scorecard"] = {
        "flows_total": len(stats["flows"]),
        "flows_passed": len(stats["flows"]) - len(failing),
        "flows_failed": len(failing),
        "per_flow": [
            {"flow": f["flow"], "passed": f["passed"], "checked": f["checked"],
             "failing": len(f["failures"]), "skipped": f.get("skipped", False)}
            for f in stats["flows"]
        ],
    }

    # --- Filing (one deduped issue per failing flow) ---
    if file_issues:
        for f in failing:
            stats["filed"].append(file_flow_issue(f))

    stats["duration_seconds"] = round(_time.monotonic() - start, 1)
    # #232: L2-153's cockpit card needs a wall-clock stamp to render precise
    # staleness (a cached verdict without one reads as SILENT). TTL is 14d — far
    # more than 2× the daily run interval — so a completed run is never evicted
    # before the next one refreshes it.
    from datetime import datetime as _dt, timezone as _tz
    stats["generated_at"] = _dt.now(_tz.utc).isoformat()

    # Cache the run so the cockpit / ops read path can tile it without re-running.
    try:
        import json as _json

        from app.tasks.redis_state import get_redis_client

        get_redis_client().setex(
            "bainluck:flow_sentinel:last", 14 * 86400, _json.dumps(stats, default=str)
        )
    except Exception as exc:
        logger.warning("Flow sentinel result cache write failed: %s", exc)

    logger.info(
        "Flow sentinel (%s%s): %d/%d flows passed, %d issues filed in %.1fs",
        stats["mode"],
        " +canary" if canary else "",
        stats["scorecard"]["flows_passed"],
        stats["scorecard"]["flows_total"],
        len(stats["filed"]),
        stats["duration_seconds"],
    )
    return stats
