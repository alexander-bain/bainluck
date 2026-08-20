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

# --- discover_first_page floor (UX-P089 / #1936) -----------------------------
# The alarm Alex's "the live feed shows TWO cards" field test proves we lacked.
#
# It has TWO limbs, and the second one is the whole reason this exists. When that
# report came in, `GET /api/feed` was returning FIFTY renderable cards for Alex's
# own session id — a card-counting alarm would have been green throughout. What
# he could not get was DELIVERY: a cold build for an identified principal was
# measured at 4.3s / 4.3s / 11.7s, against a native client whose entire
# initial-load budget is 6s and whose deadline error is non-retryable. A feed
# that is built correctly and arrives after the reader has given up is starved.
#
# So: count the cards a client could render, AND time the build against the
# client's real budget. A flow that measured only what the server produced would
# have watched this whole incident go by.
DISCOVER_FIRST_PAGE_FLOOR = 12  # flow:sentinel_discover_first_page_floor
# Limb 3 — DARK CLASS (#1948). The floor and the budget together still could not
# see a whole CARD TYPE go dark, and that is not hypothetical: on the #1948 run
# this alarm reported `renderable_cards: 41` against `items_returned: 50` with
# `type_concept: 9`. 41 = 50 - 9. Every concept card on the page was
# unrenderable, the entire tier was invisible to both surfaces, and the alarm
# PASSED — because 41 clears a floor of 12. It photographed the incident and
# called it healthy.
#
# A class is dark when the server built cards of that type and a client can
# render NONE of them. That is categorically different from "we have no
# concepts today", which produces no items of the type at all and is not
# flagged.
#
# The minimum class size keeps this a floor alarm rather than a per-card judge
# (the `feed_renderable_card_count` docstring's own rule: a noisy floor alarm
# gets muted, and then you have no alarm). One unrenderable card of a type is a
# card bug and belongs to the empty-envelope work; two or more with not a single
# survivor is a mechanism.
DISCOVER_DARK_CLASS_MIN = 2  # flow:sentinel_discover_dark_class_min
# `DiscoverViewModel.retryBudget` — the client's TOTAL initial-load budget, not a
# per-attempt timeout. Kept as its own constant so the day someone changes it in
# Swift, the mismatch is one grep away.
DISCOVER_CLIENT_LOAD_BUDGET_S = 6.0  # flow:sentinel_discover_client_budget_s
# The iOS first-page request shape, verbatim (`DiscoverViewModel.firstPageLimit`
# = 50, `eventPct` = 0.15). Probing a different shape probes a different feed.
DISCOVER_FIRST_PAGE_PARAMS = {"limit": "50", "offset": "0", "event_pct": "0.15"}
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
    "discover_first_page": "area:discover-ranking",
    "participation_family": "area:event-details",
    "matured_linkage": "area:event-details",  # covers matching/linkage per label desc
    "unlinked_held": "area:event-details",  # matcher missed a link we could have made
    "season_aggregate_linkage": "area:event-details",  # season market on a game event (#1220)
    "frozen_final_scores": "area:calibration",  # settled score is not the final (CAL-P002)
    "winner_field_coherence": "area:calibration",  # mex market w/ >1 winner or >1 certain leg (CAL-P006)
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
    "discover_first_page": "Discover first page starved, or built too slowly for the client to receive",
    "participation_family": "non-ME prop family (make-cut/top-N) squashed to sum-100%",
    "matured_linkage": "imminent event has a phantom blend source (in blend, no linked market)",
    "unlinked_held": "imminent event has an unlinked winner market we already hold (matcher miss)",
    "season_aggregate_linkage": "season-aggregate market mislinked to a single game event",
    "frozen_final_scores": "settled event stores a non-final (frozen mid-game) score",
    "winner_field_coherence": "single-winner market crowned twice, or a field of near-certain legs",
    "team_identity_dupes": "unmerged team-identity dupes remain or adjudication backlog is climbing",
}


# ---------------------------------------------------------------------------
# Runtime threshold overrides (Redis, no-deploy tuning)
# ---------------------------------------------------------------------------
def _load_overrides() -> None:
    global CHART_DENSITY_MAX_BELOW_BAR_PCT, EVENT_SAMPLE_SIZE, STALE_LIVE_HOURS
    global DISCOVER_FIRST_PAGE_FLOOR, DISCOVER_CLIENT_LOAD_BUDGET_S, DISCOVER_DARK_CLASS_MIN
    try:
        from app.tasks.redis_state import get_redis_client

        r = get_redis_client()
        for key, name, cast in (
            ("flow:sentinel_chart_density_max_below_bar", "CHART_DENSITY_MAX_BELOW_BAR_PCT", float),
            ("flow:sentinel_event_sample_size", "EVENT_SAMPLE_SIZE", int),
            ("flow:sentinel_stale_live_hours", "STALE_LIVE_HOURS", float),
            ("flow:sentinel_discover_first_page_floor", "DISCOVER_FIRST_PAGE_FLOOR", int),
            ("flow:sentinel_discover_client_budget_s", "DISCOVER_CLIENT_LOAD_BUDGET_S", float),
            ("flow:sentinel_discover_dark_class_min", "DISCOVER_DARK_CLASS_MIN", int),
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


def gold_set_transport_errors(results: list[dict]) -> list[dict]:
    """Gold-set queries that did not get an ANSWER at all (#1494 criterion 3).

    A 503/timeout/connection-abort is not a search result — it is the absence of
    one. The old scoring collapsed both into ``found: False``, so a transport
    error on an ``expected_found: False`` entry scored EXACTLY like a legitimate
    "correctly returns nothing". On 2026-07-31 the sentinel recorded three hard
    503s from ``/api/events/search`` and still reported ``passed: true`` — search
    was down and its own regression guard said green.

    Transport failure is now its own fileable class, on ANY gold entry
    regardless of its expectation.
    """
    return [r for r in results if r.get("error")]


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
    #
    # ⚠️ KNOWN BLIND SPOT, and the premise above is the reason (UX-P091,
    # 2026-08-17). "A true unmerged duplicate shares the exact commence_time"
    # was written BEFORE ruling 048. Post-048 an id-less claim never absorbs, it
    # CREATES — so the duplicates 048 generates come from a DIFFERENT provider
    # carrying that provider's OWN start time, and two providers disagreeing
    # about the clock is now the normal way a duplicate is born.
    #
    # Measured specimen: a new 10-digit StatPal fixture namespace (`1329…`,
    # first seen 2026-08-17T08:14:56Z) created MLB rows whose commence_time is
    # Eastern local stamped as UTC — **exactly −4h** on all four (15200759-62).
    # Four hours is not a minute, so this key cannot pair them with anything,
    # and `duplicate_events` reported ZERO team-pair duplicates that night while
    # at least four unmerged pairs sat inside its own 222-row sample.
    #
    # NOT widened here, deliberately: −4h is INSIDE a legitimate doubleheader
    # gap, so no time tolerance separates this class from a real second game.
    # The honest fix is id-anchored (ruling 048's own grammar), not time-keyed.
    # `test_flow_sentinel_dup_key_blind_spot.py` PINS this limitation with the
    # production specimen so it stays a known, asserted gap rather than folklore
    # — the class is currently caught by `resolved_state`'s live-before-commence
    # and inverted-completed_at limbs, which DID fire on the same rows.
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


def live_before_commence_events(events: list[dict], now) -> list[dict]:
    """status='live' events whose commence_time is in the FUTURE — labeled live
    before they started (Queue 283 lifecycle invariant: live => now >= start).

    This is the read-side monitor for the same rule the classifiers now enforce
    (``highlights.compute_highlight`` / ``app.utils.lifecycle``). ``now`` injected
    for testability."""
    out = []
    for e in events:
        if e.get("status") != "live":
            continue
        t = _parse_commence(e.get("commence_time"))
        if t is None or t <= now:
            continue
        out.append({"event_id": e.get("id"), "sport": e.get("sport"),
                    "home_team": e.get("home_team"), "away_team": e.get("away_team"),
                    "commence_time": e.get("commence_time"),
                    "starts_in_hours": round((t - now).total_seconds() / 3600.0, 1)})
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


def frozen_final_score_events(ledger: list[dict]) -> list[dict]:
    """Settled events whose stored score is NOT the game's final score (CAL-P002).

    A settled event's score must BE the final. A violation means the page shows a
    wrong final — we held ``BOS 3-1`` where the real final was ``6-3`` — and every
    score-derived grade under it stands on a mid-game number. Two producers, one
    symptom: the wall-clock staleness nets close an event on elapsed time and keep
    whatever score the last poll wrote (``espn_sync._transition_event_statuses_impl``,
    ``odds_polling.detect_and_close_stale_events``), and a same-series neighbour's
    final can land on the wrong sibling.

    Pure over the ledger returned by the ``event-final-scores`` repair's DRY-RUN, so
    the guard and the repair share ONE definition of the defect and cannot drift.
    Identity-blocked rows are deliberately excluded — those are an ``espn_id``
    linkage defect (a different repair), not a frozen score."""
    out = []
    for e in ledger or []:
        if e.get("action") != "fix_score":
            continue
        out.append({
            "event_id": e.get("event_id"), "sport": e.get("sport_key"),
            "matchup": e.get("matchup"), "status": e.get("status"),
            "stored_score": e.get("stored_score"), "espn_final": e.get("espn_final"),
            "winner_flip": bool(e.get("winner_flip")),
            "commence_time": e.get("commence_time"),
        })
    return out


def freshly_written_incoherent_fields(defects: list[dict]) -> list[dict]:
    """CAL-P006 (#1527): the winner-field violations a PRODUCER is still creating.

    A mutually-exclusive market is a single-winner partition, so >1 ``is_winner``
    or >1 near-certain leg is an impossible state. 214+ soccer 1X2 markets held
    Home, Away AND Draw at 1.00, all three crowned.

    Only ``written_recently`` rows fail. This is deliberate and it is the whole
    design of the guard:

    * The standing legacy population cannot be repaired by this queue — a bulk
      ``is_winner`` reset needs a source that can immediately re-resolve
      (gotcha #21). Alarming on it every night would make the flow permanently
      RED for something no agent is allowed to fix, which is precisely the
      cry-wolf the grid health score was retired for.
    * A defect row only stays "recently written" while a producer keeps stamping
      it. The two CAL-P006 producer fixes stop that, so these rows age out of the
      window on their own — the flow goes green exactly when, and only when, the
      producers actually stopped. That makes it a falsifiable check on the fix
      rather than a restatement of the backlog.

    Pure over the ``winner-field-coherence`` census's DRY-RUN output, so guard and
    census share ONE definition of the defect and cannot drift."""
    out = []
    for d in defects or []:
        if not d.get("written_recently"):
            continue
        out.append({
            "market_id": d.get("market_id"),
            "source": d.get("source"),
            "status": d.get("status"),
            "category": d.get("category"),
            "name": d.get("name"),
            "legs": d.get("legs"),
            "winners": d.get("winners"),
            "near_certain": d.get("near_certain"),
            "field_sum": d.get("field_sum"),
            "classes": d.get("classes") or [],
            "last_written": d.get("last_written"),
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


def feed_renderable_card_count(feed_items: Any) -> int:
    """Cards a CLIENT could actually render from a /api/feed page (UX-P089).

    Not `len(items)`. The native and web surfaces both drop empty predictive
    envelopes through the same rule (`DiscoverViewModel.suppressionReason`,
    `feedItemSuppressionReason`), so an alarm that counted raw items would call a
    page of fifty bare tiles a healthy feed. Mirrored here rather than imported
    because the authority lives in Swift and TypeScript; the mirror is pinned by
    `test_flow_sentinel.py` against a recorded production page.

    Deliberately the PERMISSIVE reading of each rule. This is a floor alarm: it
    should fire when the feed is genuinely starved, not litigate individual
    cards. Over-counting risks a missed alarm; under-counting guarantees a noisy
    one, and a noisy floor alarm gets muted, which is how you end up with no
    alarm at all.
    """
    if not isinstance(feed_items, list):
        return 0
    return sum(1 for i in feed_items if feed_item_is_renderable(i))


_FUTURES_SETTLED_STATUSES = frozenset(
    {"resolved", "settled", "closed", "complete", "completed", "finalized", "final"}
)


def _futures_is_settled(data: dict, now: Any = None) -> bool:
    """Web's `_futuresIsSettled`, arm for arm (`discover/utils.ts`).

    The `resolution_date` arm is the one this copy was missing. It matters in the
    STRICT direction — without it the sentinel calls a settled-by-date card
    unrenderable while both clients print it, i.e. the mirror under-counts a
    healthy page. Kept last because it is the weakest authority of the four:
    `resolution_date` is SCHEDULED, never a transition timestamp, so a past date
    means "should have resolved by now", not "did".
    """
    if data.get("resolved") is True:
        return True
    if (data.get("winner") or "").strip():
        return True
    if (data.get("status") or "").strip().lower() in _FUTURES_SETTLED_STATUSES:
        return True
    raw = data.get("resolution_date")
    if not raw:
        return False
    from datetime import datetime, timezone

    try:
        parsed = datetime.fromisoformat(str(raw).replace("Z", "+00:00"))
    except (TypeError, ValueError):
        return False
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed < (now or datetime.now(timezone.utc))


def _concept_leader_is_usable(leader: Any) -> bool:
    """Web's `_conceptLeaderIsUsable`, arm for arm.

    Native writes this as `leader != nil` and that is COMPLETE there, because
    `FeedConceptLeader` decodes `name`/`probability` as non-optional and a
    malformed leader throws during decode. Python, like TypeScript, has no such
    gate — a bare presence test admits `{}`. The range check is not padding: an
    independent-binary field can sum past 100% (gotcha #23), so a leader reading
    over 1.0 is corrupt rather than confident.
    """
    if not isinstance(leader, dict):
        return False
    name = leader.get("name")
    if not isinstance(name, str) or not name.strip():
        return False
    p = leader.get("probability")
    if isinstance(p, bool) or not isinstance(p, (int, float)):
        return False
    return 0.0 <= float(p) <= 1.0


def feed_item_is_renderable(item: Any, depth: int = 0, now: Any = None) -> bool:
    """One card's renderability, by the surfaces' shared suppression rule.

    Module-level rather than a closure inside `feed_renderable_card_count`
    because the dark-class limb needs the SAME predicate per card type. A second
    copy of this rule is exactly the drift #1948 is about — the whole incident
    was two enumerations of one population disagreeing.

    #1951 — AND THIS FUNCTION WAS THE THIRD COPY. It shipped in UX-P092 carrying
    the pre-#1935 rule on two arms, and the consequence is worse here than in a
    renderer, because the dark-class limb IS the #1935-family detector: it names
    card types the server builds and no client renders. Grading that with a
    predicate MORE PERMISSIVE than the clients' makes the exact family it hunts
    invisible to it. A first page whose seven tournaments are all
    golferless-but-`marquee_whathit` is 100% dark on both surfaces, and the old
    reading reported `tournament: 7 built, 7 renderable` — PASS. That is #1948's
    own failure mode (a fully green alarm over a dark tier) reproduced inside the
    fix for #1948.

    ON THE DOCSTRING ABOVE THIS ONE, which says the reading is "deliberately the
    PERMISSIVE" one: that argument was made for the FLOOR limb, where
    under-counting means a noisy alarm and a noisy alarm gets muted. It does not
    license being permissive against the CLIENTS — matching them exactly is not
    "strict", it is accurate, and a card the clients drop is genuinely not on the
    reader's page. Measured on the 327-card production sample this was written
    against, the corrected predicate changes the renderable count by ZERO (58/75
    both ways), because today's population has no specimen of any of the three
    drifts. The floor limb is unaffected; the dark-class limb gains its sight.

    The parity that matters is asserted in `conceptAdmissionParity.test.ts`,
    which now covers THREE surfaces rather than two.
    """
    if not isinstance(item, dict):
        return False
    kind = item.get("type")
    data = item.get("data")
    if not isinstance(data, dict):
        return False
    if kind == "event":
        # Unconditional on all three surfaces: an event card is a real matchup
        # plus a status/score, never a bare tile.
        return True
    if kind == "futures":
        if data.get("top_outcomes"):
            return True
        # Settled-but-open is the normal Kalshi shape (gotcha #33), and a
        # result-carrying card is renderable — "settled means settled".
        return _futures_is_settled(data, now)
    if kind == "tournament":
        # #1935 deleted the bare `marquee_whathit` arm from BOTH clients:
        # `TournamentCard`/`DiscoverTournamentCard` render their entire champion
        # hero inside `golfers.first`, so a golferless WHAT-HIT tournament is a
        # gradient, a chip and a title. Since the golfer arm already admits every
        # tournament that CAN render, the whathit arm only ever fired for the one
        # that cannot. This copy kept it for three cycles after both clients
        # dropped it.
        return bool(data.get("golfers"))
    if kind == "concept":
        # Settled arm FIRST, and the order is load-bearing on all three surfaces:
        # "settled means settled" — a card with a result leads with the result and
        # must not fall back to a probability that is now history.
        if data.get("marquee_whathit") is True:
            named = (data.get("winner") or "").strip()
            summary = (data.get("result_summary") or "").strip()
            return bool(named or summary)
        return _concept_leader_is_usable(data.get("leader"))
    if kind == "bundle":
        if depth > 3:
            return False
        return any(
            feed_item_is_renderable(c, depth + 1, now) for c in (data.get("items") or [])
        )
    return False


def feed_dark_card_classes(feed_items: Any, min_class_size: int | None = None) -> list[dict]:
    """Card types the server BUILT but no client can render any of (#1948).

    Returns one row per dark class: ``{"type", "built", "renderable": 0}``.
    A type absent from the page is not dark — it is absent, and those are
    different facts (gotcha #53). A type with even one renderable member is not
    dark either; this limb is about a whole tier going out at once.

    `min_class_size` resolves at call time (see `discover_first_page_failures`
    for why a default argument would silently ignore the Redis override).
    """
    if not isinstance(feed_items, list):
        return []
    min_class_size = DISCOVER_DARK_CLASS_MIN if min_class_size is None else min_class_size

    built: dict[str, int] = {}
    renderable: dict[str, int] = {}
    for item in feed_items:
        if not isinstance(item, dict):
            continue
        kind = item.get("type")
        if not isinstance(kind, str) or not kind:
            continue
        built[kind] = built.get(kind, 0) + 1
        if feed_item_is_renderable(item):
            renderable[kind] = renderable.get(kind, 0) + 1

    return [
        {"type": kind, "built": n, "renderable": 0}
        for kind, n in sorted(built.items())
        if n >= min_class_size and renderable.get(kind, 0) == 0
    ]


def discover_first_page_failures(
    *,
    renderable: int,
    elapsed_s: float,
    cache_status: str | None,
    items: Any = None,
    floor: int | None = None,
    budget_s: float | None = None,
    dark_class_min: int | None = None,
) -> list[dict]:
    """The three-limb verdict for the Discover first page (UX-P089 / #1936; #1948).

    Limb 1 — STARVED: fewer renderable cards than the floor.

    Limb 2 — UNDELIVERABLE: the build outran the client's total load budget. Only
    asserted on a genuine COLD build, and that condition is load-bearing rather
    than defensive. A cache hit says nothing about build cost (it is an 8ms read),
    so timing one and passing would be a vacuous green — the alarm would report
    healthy precisely because it measured nothing. A cold build is the only
    sample that carries the number, and it is also the exact request a returning
    reader makes: identified principals get their own cache key with a 5s fresh
    TTL and a 300s stale tier, so anyone away for five minutes is cold.

    Limb 3 — DARK CLASS (#1948): a whole card TYPE built and none of it
    renderable. Limbs 1 and 2 are both page-level aggregates, and #1948 walked
    straight between them — 41 renderable of 50 items with all 9 concepts dark
    clears a floor of 12 and says nothing about the build time. The alarm
    photographed the incident and passed. `items` is optional so an older caller
    still gets limbs 1 and 2, but the runner passes it.

    THE THRESHOLDS RESOLVE AT CALL TIME, and that is a fix, not a style choice.
    They were `floor: int = DISCOVER_FIRST_PAGE_FLOOR` — a default argument,
    which Python binds ONCE when the module is imported. `_load_overrides()`
    reassigns those globals from Redis at the start of every run, so the
    override never reached the verdict, while the evidence block (which reads
    the global at call time) reported the NEW number. An operator raising the
    floor would have seen their value echoed back and graded against the old
    one. Same trap would have swallowed `dark_class_min` on arrival.
    """
    floor = DISCOVER_FIRST_PAGE_FLOOR if floor is None else floor
    budget_s = DISCOVER_CLIENT_LOAD_BUDGET_S if budget_s is None else budget_s
    dark_class_min = DISCOVER_DARK_CLASS_MIN if dark_class_min is None else dark_class_min

    failures: list[dict] = []
    if renderable < floor:
        failures.append(
            {
                "limb": "starved",
                "detail": (
                    f"Discover first page returned {renderable} renderable cards "
                    f"(floor {floor}) — the reader sees a near-empty feed"
                ),
                "renderable": renderable,
                "floor": floor,
            }
        )
    if cache_status == "miss" and elapsed_s > budget_s:
        failures.append(
            {
                "limb": "undeliverable",
                "detail": (
                    f"cold Discover build took {elapsed_s:.2f}s against the native "
                    f"client's {budget_s:.0f}s total load budget — the fetch is "
                    f"cancelled and Discover settles to last-good or honest-empty, "
                    f"however many cards the server built"
                ),
                "elapsed_s": round(elapsed_s, 3),
                "budget_s": budget_s,
            }
        )
    for dark in feed_dark_card_classes(items, min_class_size=dark_class_min):
        failures.append(
            {
                "limb": "dark_class",
                "detail": (
                    f"every `{dark['type']}` card on the Discover first page is "
                    f"unrenderable ({dark['built']} built, 0 renderable) — the "
                    f"whole class is invisible on both surfaces while the page "
                    f"total still clears the floor"
                ),
                "card_type": dark["type"],
                "built": dark["built"],
                "renderable": 0,
            }
        )
    return failures


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
async def _get_json(
    client: httpx.AsyncClient,
    path: str,
    params: dict | None = None,
    headers: dict | None = None,
) -> Any:
    # `headers` is forwarded only when set: the unauthenticated public-endpoint
    # flows (search, feed, events) send no auth at all, so their call shape is
    # unchanged.
    kwargs: dict = {"params": params}
    if headers:
        kwargs["headers"] = headers
    resp = await client.get(path, **kwargs)
    resp.raise_for_status()
    return resp.json()


# ---------------------------------------------------------------------------
# Admin transport (#1494) — Bearer only, never a token in a URL
# ---------------------------------------------------------------------------
def _admin_headers() -> dict | None:
    """Canonical admin transport: ``Authorization: Bearer <ADMIN_TOKEN>``.

    Queue #252 Item 3 removed the ``?secret=`` query-parameter auth path (a
    secret in a URL leaks through access logs, Referer, and browser history).
    Three flows here were never migrated, so every admin call they made returned
    403 — and each of them mapped that 403 to ``{"checked": 0, "passed": True}``,
    which the scorecard counted as a PASS. Three checks reported clean for weeks
    while being structurally unable to verify anything.

    Returns ``None`` when ADMIN_TOKEN is unset, so the caller reports UNKNOWN
    rather than issuing a request that cannot possibly authenticate.
    """
    token = os.environ.get("ADMIN_TOKEN", "")
    if not token:
        return None
    return {"Authorization": f"Bearer {token}"}


def _redact(text: Any) -> str:
    """Scrub the admin token out of any string bound for evidence/logs/issues.

    Defence in depth: httpx embeds the request URL in its error messages, and
    evidence strings land verbatim in a PUBLIC GitHub issue body. Even though
    the token no longer travels in a URL, anything that could carry it is
    scrubbed before it can be written down.
    """
    out = str(text)
    token = os.environ.get("ADMIN_TOKEN", "")
    if token and len(token) >= 6:
        out = out.replace(token, "<redacted>")
    # Belt and braces: strip any surviving secret/token query parameter.
    out = re.sub(
        r"((?:secret|token|admin_token)=)[^&\s\"']+", r"\1<redacted>", out,
        flags=re.IGNORECASE,
    )
    return out


def _unknown_flow(flow: str, reason: str, **evidence: Any) -> dict:
    """An explicit UNKNOWN result: we could not measure, so we cannot judge.

    This is the #1494 fix in one shape. UNKNOWN is neither a pass nor a failure:

    * it is EXCLUDED from ``flows_passed`` (a check that could not run has not
      passed — the old code counted it as one), and
    * it never files an issue and never resolves one (filing on our own broken
      measurement is the #1147 cry-wolf; auto-closing on it is worse).

    ``passed`` stays ``True`` purely so the existing "failing → file" path is
    untouched; ``unknown`` is the field every count now keys on.
    """
    return {
        "flow": flow,
        "checked": 0,
        "passed": True,
        "unknown": True,
        "skipped": True,
        "failures": [],
        "evidence": {"unknown": True, "reason": _redact(reason), **evidence},
    }


def flow_outcome(result: dict) -> str:
    """Classify one flow result as ``pass`` / ``fail`` / ``unknown``.

    The load-bearing invariant (#1494 acceptance): **a flow with
    ``checked == 0`` can never be a pass.** Zero checks means zero evidence.
    """
    if result.get("unknown") or result.get("skipped"):
        return "unknown"
    if not result.get("passed"):
        return "fail"
    if not result.get("checked"):
        return "unknown"
    return "pass"


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
                        "error": _redact(exc)[:150]}

    results = await asyncio.gather(*[_one(q, e) for q, e in gold])
    regressions = gold_set_regressions(results)
    recoveries = gold_set_recoveries(results)
    transport = gold_set_transport_errors(results)
    # A transport error on an expected-found entity is already a regression;
    # don't file the same query twice.
    regression_queries = {r["query"] for r in regressions}
    transport_only = [r for r in transport if r["query"] not in regression_queries]
    found_n = sum(1 for r in results if r["found"])
    return {
        "flow": "search_gold_set",
        "checked": len(results),
        # #1494 criterion 3: search being DOWN must fail this flow, not pass it.
        "passed": len(regressions) == 0 and len(transport) == 0,
        "failures": [
            {"query": r["query"], "detail": "expected-found entity now returns nothing"}
            for r in regressions
        ] + [
            {"query": r["query"],
             "detail": f"search ERRORED for this query — no answer was returned "
                       f"(transport/5xx, not a legitimate miss): "
                       f"{_redact(r.get('error'))[:150]}"}
            for r in transport_only
        ],
        "evidence": {
            "found": found_n,
            "total": len(results),
            "transport_errors": [r["query"] for r in transport],
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
                        "top1_ok": False, "error": _redact(exc)[:150]}

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


#: Rows/hour of NEW unanchored events above which ruling 048's "bounded cost" is
#: not bounded. DERIVED from the #2020 incident rather than chosen to taste:
#:
#:   * healthy regime, measured — 2026-08-18 added **6 rows in a day** (0.25/h),
#:     and the tag's introduction day (08-17) burst to 500 rows over 7 hours
#:     (71/h) as it first populated;
#:   * incident regime, measured — 2026-08-19/20 sustained **900-2,400 rows/hour**
#:     for three days, 500 -> 51,673 total.
#:
#: 100/h sits in the empty band between them: 400x the healthy daily rate, above
#: the one legitimate onset burst on record, and 24x below the incident. A rate
#: this high has never been benign here.
UNANCHORED_GROWTH_PER_HOUR_CEILING = 100.0

#: Redis key holding the PRIOR provenance-meter reading, so the growth gate
#: compares against a value we actually took rather than one it inferred.
_PROVENANCE_METER_PRIOR_KEY = "bainluck:flow_sentinel:provenance_meter_prior"
#: 14 days — long enough that a few skipped nightly runs still leave a prior to
#: compare against, short enough that a months-old reading never becomes the
#: baseline for a rate.
_PROVENANCE_METER_PRIOR_TTL_S = 14 * 24 * 3600


def _utcnow():
    from datetime import datetime, timezone

    return datetime.now(timezone.utc)


def _load_prior_provenance_meter():
    """The previous run's reading, or None. Never raises."""
    try:
        import json

        from app.tasks.redis_state import get_redis_client

        raw = get_redis_client().get(_PROVENANCE_METER_PRIOR_KEY)
        if not raw:
            return None
        return json.loads(raw.decode() if isinstance(raw, bytes) else raw)
    except Exception as exc:
        logger.info("flow sentinel: no prior provenance meter (%s)", exc)
        return None


def _store_provenance_meter(meter: dict, now) -> None:
    """Persist this run's reading for the next run to compare against."""
    try:
        import json

        from app.tasks.redis_state import get_redis_client

        payload = json.dumps({
            "read_at": now.isoformat(),
            "created_unanchored": meter.get("created_unanchored"),
            "reconciled": meter.get("reconciled"),
            "unreconciled": meter.get("unreconciled"),
        })
        get_redis_client().setex(
            _PROVENANCE_METER_PRIOR_KEY, _PROVENANCE_METER_PRIOR_TTL_S, payload,
        )
    except Exception as exc:
        logger.info("flow sentinel: could not persist provenance meter (%s)", exc)


def provenance_growth(prior, meter: dict, now) -> dict:
    """Growth of the unanchored population between two REAL readings. Pure.

    Returns a dict that always carries ``measured``; ``rate_per_hour`` is None
    whenever a rate cannot honestly be computed (no prior, unparseable prior, a
    non-positive interval, or missing counts). **A rate of None never fails the
    gate** — an absent comparison is not evidence of health, and it must not be
    dressed up as one either (gotcha #53).

    ``reconciled_delta`` may be NEGATIVE and that is not a bug in the reader:
    the meter's `reconciled` was observed moving 180 -> 173 between two live
    reads during #2020, so it is not monotone and cannot be read as drain
    progress. It is reported for context and never used as a denominator.
    """
    from datetime import datetime, timezone

    out = {
        "measured": False,
        "rate_per_hour": None,
        "created_delta": None,
        "reconciled_delta": None,
        "hours": None,
        "prior_read_at": None,
    }
    created = meter.get("created_unanchored")
    if not isinstance(created, (int, float)):
        out["reason"] = "current reading has no created_unanchored"
        return out
    if not isinstance(prior, dict):
        out["reason"] = "no prior reading persisted yet — first run, or TTL expired"
        return out
    prior_created = prior.get("created_unanchored")
    if not isinstance(prior_created, (int, float)):
        out["reason"] = "prior reading has no created_unanchored"
        return out
    try:
        prior_at = datetime.fromisoformat(str(prior.get("read_at")))
    except (TypeError, ValueError):
        out["reason"] = "prior reading has an unparseable read_at"
        return out
    if prior_at.tzinfo is None:
        prior_at = prior_at.replace(tzinfo=timezone.utc)
    hours = (now - prior_at).total_seconds() / 3600.0
    out["prior_read_at"] = prior_at.isoformat()
    if hours <= 0:
        # A prior stamped in the FUTURE would make the rate negative and the gate
        # would fail OPEN forever — the ahead-drift failure the lane locks already
        # learned the hard way. Refuse to compute rather than compute a lie.
        out["reason"] = f"non-positive interval ({hours:.3f}h) — refusing to rate"
        return out
    prior_reconciled = prior.get("reconciled")
    reconciled = meter.get("reconciled")
    out.update({
        "measured": True,
        "hours": hours,
        "created_delta": int(created - prior_created),
        "reconciled_delta": (
            int(reconciled - prior_reconciled)
            if isinstance(reconciled, (int, float))
            and isinstance(prior_reconciled, (int, float))
            else None
        ),
        "rate_per_hour": (created - prior_created) / hours,
    })
    return out


async def _run_provenance_meter(client: httpx.AsyncClient) -> dict:
    """Ruling 048's declared cost, read as a number rather than assumed bounded.

    This does NOT gate the duplicate_events verdict — 048 says duplicates are the
    expected, accepted price of never eating a real game, so a non-zero count is
    not a failure. What would be a failure is the count being unknown, or the
    outstanding backlog growing while nothing drains.

    Reports ``measured: False`` rather than a comfortable zero when it cannot
    read — the 403-as-PASS history documented on ``_admin_headers`` is precisely
    the bug this shape avoids.
    """
    headers = _admin_headers()
    if not headers:
        return {"measured": False, "reason": "ADMIN_TOKEN unset"}
    try:
        data = await _get_json(client, "/api/admin/events/duplicates", None, headers)
    except Exception as exc:
        return {"measured": False, "reason": _redact(exc)[:200]}
    meter = (data or {}).get("provenance_meter")
    if not isinstance(meter, dict) or not meter.get("measured"):
        return {
            "measured": False,
            "reason": (meter or {}).get("reason") or "endpoint returned no meter",
        }
    return meter


async def _run_duplicate_events(client: httpx.AsyncClient) -> dict:
    # A broad live+scheduled slate is where an unmerged duplicate would show.
    events = await _sample_events(client, "live", 200)
    events += await _sample_events(client, "scheduled", 200)
    dups = find_duplicate_events(events)
    meter = await _run_provenance_meter(client)

    # R6 (#1801, codex C-CERT-1801-R5 P2): the meter's own docstring names two
    # failures — an unknown count, and a backlog growing while nothing drains —
    # and neither could reach `passed`, which read `len(dups) == 0` alone. A
    # meter that cannot fail a verdict is evidence, not a gate, and #1501 is the
    # whole lesson about an absence that renders as health.
    #
    # 048 still stands: a non-zero duplicate COUNT is the accepted price and is
    # not a failure. What fails is not being able to see the count at all.
    meter_failures = []
    if not meter.get("measured"):
        meter_failures.append({
            "detail": "provenance meter UNMEASURED — ruling 048's declared cost "
                      f"is unknown, so it cannot be called bounded: "
                      f"{meter.get('reason') or 'no reason given'}"
        })
    else:
        # What one read CAN establish: 048 accepts duplicates because id-keyed
        # reconciliation drains them. If rows were created unanchored and NOT
        # ONE has ever reconciled, the draining half of the bargain is absent,
        # and the accepted price has no bound.
        created = meter.get("created_unanchored")
        reconciled = meter.get("reconciled")
        unreconciled = meter.get("unreconciled")
        if isinstance(created, (int, float)) and isinstance(reconciled, (int, float)):
            if created > 0 and reconciled == 0:
                meter_failures.append({
                    "detail": f"{created} rows created unanchored and ZERO ever "
                              f"reconciled ({unreconciled} outstanding) — ruling "
                              "048's accepted cost is only bounded by the "
                              "reconciliation that is not happening"
                })

        # #2020: THE GROWTH GATE — and the reason it had to exist.
        #
        # The clause above was the whole meter check, and it PASSED throughout the
        # #2020 incident: `reconciled` had drifted to 173 by incidental means, so
        # `reconciled == 0` was false while the population grew 500 -> 51,673 in
        # three days at ~2,400 rows/hour. **A gate that passes while the thing it
        # guards grows 100x is the crying-wolf failure inverted** — and it is
        # worse than a noisy alarm, because it is quoted as evidence of health.
        #
        # The previous comment here said a trend comparison would be "dead code
        # wearing the costume of a gate ... if a trend is wanted later, persist
        # the prior reading first and compare that; do not infer one." That was
        # exactly right, and this is that: the prior reading is now PERSISTED, so
        # the comparison is against a value we actually took, never an inferred
        # one. When there is no prior reading we say so and gate nothing.
        prior = _load_prior_provenance_meter()
        growth = provenance_growth(prior, meter, _utcnow())
        meter["growth"] = growth
        if growth.get("rate_per_hour") is not None and growth["rate_per_hour"] > (
            UNANCHORED_GROWTH_PER_HOUR_CEILING
        ):
            meter_failures.append({
                "detail": (
                    f"unanchored population GROWING at {growth['rate_per_hour']:.0f} "
                    f"rows/hour (ceiling {UNANCHORED_GROWTH_PER_HOUR_CEILING:.0f}) — "
                    f"{growth['created_delta']:+d} created and "
                    f"{growth['reconciled_delta']} reconciled over "
                    f"{growth['hours']:.2f}h. Ruling 048's cost is bounded by "
                    "reconciliation draining it; at this rate nothing drains it"
                )
            })
        _store_provenance_meter(meter, _utcnow())

    return {
        "flow": "duplicate_events",
        "checked": len(events),
        "passed": len(dups) == 0 and not meter_failures,
        "failures": [{"detail": f"{d['sport']}: {d['home_team']} vs {d['away_team']} "
                                f"appears {len(d['event_ids'])}x (ids {d['event_ids']})"}
                     for d in dups] + meter_failures,
        "evidence": {
            "sampled": len(events),
            "duplicates": dups,
            # Ruling 048: the declared cost, carried alongside the verdict so the
            # trend is visible night over night.
            "provenance_meter": meter,
        },
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


async def _run_discover_first_page(client: httpx.AsyncClient) -> dict:
    """Discover's first page must be full AND deliverable (UX-P089 / #1936).

    Probes the iOS request shape under a UNIQUE session id, which is what makes
    the sample cold: `feed_response_cache_key` gives every identified principal
    its own key, so a fresh id is guaranteed to miss and therefore to carry a
    real build time. It also puts the probe on the identified code path — the one
    with the 5s fresh TTL that a returning reader actually walks — rather than
    the anonymous key the pre-warm beat keeps warm and nobody signed in reads.

    The probe writes one throwaway cache entry per run. Bounded and deliberate:
    that entry is the cost of measuring the number that matters.
    """
    import uuid as _uuid

    probe_session = f"flow-sentinel-{_uuid.uuid4()}"
    started = _time.monotonic()
    try:
        resp = await client.get(
            "/api/feed",
            params=DISCOVER_FIRST_PAGE_PARAMS,
            headers={"x-session-id": probe_session},
        )
        resp.raise_for_status()
        payload = resp.json()
    except Exception as exc:
        return _unknown_flow(
            "discover_first_page",
            f"/api/feed first-page probe errored: {str(exc)[:150]}",
            probe="identified cold key",
        )

    wall_s = _time.monotonic() - started
    items = payload.get("items", []) if isinstance(payload, dict) else []
    renderable = feed_renderable_card_count(items)
    cache_status = resp.headers.get("x-feed-cache")
    # Prefer the server's own stage clock over wall time — it excludes network
    # and TLS, so it is the number the client's budget is actually racing.
    try:
        elapsed_s = float(resp.headers["x-feed-elapsed-ms"]) / 1000.0
    except (KeyError, TypeError, ValueError):
        elapsed_s = wall_s

    failures = discover_first_page_failures(
        renderable=renderable,
        elapsed_s=elapsed_s,
        cache_status=cache_status,
        items=items,
    )
    # Per-class census in the evidence, always — not only when a class is dark.
    # The #1948 run's evidence carried `renderable_cards: 41` and
    # `items_returned: 50` and a reader had to do the subtraction and then guess
    # WHICH nine were missing. The breakdown is the reading that makes limb 3's
    # verdict checkable by hand.
    by_class: dict[str, dict] = {}
    if isinstance(items, list):
        for _item in items:
            if not isinstance(_item, dict):
                continue
            _kind = _item.get("type")
            if not isinstance(_kind, str) or not _kind:
                continue
            row = by_class.setdefault(_kind, {"built": 0, "renderable": 0})
            row["built"] += 1
            if feed_item_is_renderable(_item):
                row["renderable"] += 1
    return {
        "flow": "discover_first_page",
        "checked": 1,
        "passed": not failures,
        "failures": failures,
        "evidence": {
            "items_returned": len(items) if isinstance(items, list) else 0,
            "renderable_cards": renderable,
            "cards_by_class": by_class,
            "floor": DISCOVER_FIRST_PAGE_FLOOR,
            "server_elapsed_s": round(elapsed_s, 3),
            "wall_s": round(wall_s, 3),
            "client_load_budget_s": DISCOVER_CLIENT_LOAD_BUDGET_S,
            "cache_status": cache_status,
            "stages": resp.headers.get("x-feed-stages"),
            "counts": resp.headers.get("x-feed-counts"),
        },
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
    live_before = live_before_commence_events(live, now)
    failures = [
        {"detail": f"live {s['sport']} game {s['home_team']} vs {s['away_team']} "
                   f"started {s['age_hours']}h ago but still renders LIVE (id {s['event_id']})"}
        for s in stale
    ] + [
        {"detail": f"live {b['sport']} event {b['home_team']} vs {b['away_team']} "
                   f"renders LIVE but its commence_time {b['commence_time']} is "
                   f"{b['starts_in_hours']}h in the FUTURE (live before start, id "
                   f"{b['event_id']})"}
        for b in live_before
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
            "live_before_commence": live_before,
            "inverted_completed": inverted,
        },
    }


async def _run_chart_density(client: httpx.AsyncClient) -> dict:
    headers = _admin_headers()
    if headers is None:
        return _unknown_flow("chart_density", "ADMIN_TOKEN unset — cannot authenticate")
    tile = None
    err = None
    try:
        data = await _get_json(client, "/api/admin/backfill-progress", None, headers)
        census = data.get("census") if isinstance(data, dict) else None
        tile = census.get("chart_density") if isinstance(census, dict) else None
    except Exception as exc:
        # Transport / auth / 5xx / parse failure — we could not read the tile at
        # all. That is UNKNOWN, not a pass (#1494).
        return _unknown_flow(
            "chart_density", f"admin read failed: {str(exc)[:150]}"
        )
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
        return _unknown_flow("chart_density", reason, skipped=True)
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
    headers = _admin_headers()
    if headers is None:
        return _unknown_flow(
            "season_aggregate_linkage",
            "ADMIN_TOKEN unset — db-query unavailable",
        )
    try:
        resp = await client.post(
            "/api/admin/db-query",
            headers=headers,
            json={"sql": _SEASON_AGG_LINKAGE_SQL, "limit": 1},
        )
        resp.raise_for_status()
        data = resp.json()
        rows = data.get("rows") if isinstance(data, dict) else None
        linked = int(rows[0][0]) if rows and rows[0] else 0
    except Exception as exc:
        return _unknown_flow(
            "season_aggregate_linkage", f"db-query failed: {str(exc)[:120]}"
        )
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


# Scan budget for the frozen-score guard, in (sport, date) GROUPS — one ESPN
# scoreboard call each, newest first because fresh defects appear at the head.
# Small enough to stay well inside HTTP_TIMEOUT (the ESPN client sleeps 0.5s/req).
#
# DELIBERATELY HEAD-ONLY. This is a REGRESSION guard — "did we mint a new frozen
# score last night?" — not a backlog census. The old tail is the repair's job,
# walked with its ``offset`` cursor; expecting the nightly guard to also drain
# 955 groups is how a guard becomes a timeout (CAL-P002B: measured 2026-08-07,
# this exact call H12'd at 30.25s because the repair's `limit` bounded its ESPN
# calls but not its scan — the flow would have reported `unknown` every night,
# fail-soft and so never RED, without ever guarding anything).
_FROZEN_SCORE_GROUPS = 6


async def _run_frozen_final_scores(client: httpx.AsyncClient) -> dict:
    """CAL-P002 regression guard: a settled event's stored score MUST be the final.

    Measures by calling the ``event-final-scores`` repair in DRY-RUN (it writes
    nothing) over the most recent slates, so the guard and the repair can never
    drift on what counts as a defect. A broken/unauthenticated measurement is
    SKIPPED, never filed — filing on our own broken instrument is the cry-wolf the
    grid health score was retired for."""
    headers = _admin_headers()
    if headers is None:
        return _unknown_flow(
            "frozen_final_scores", "ADMIN_TOKEN unset — repair rail unavailable"
        )
    try:
        resp = await client.post(
            "/api/admin/repairs/event-final-scores",
            headers=headers,
            params={
                "apply": "false",
                "limit": _FROZEN_SCORE_GROUPS,
                "newest_first": "true",
            },
        )
        resp.raise_for_status()
        result = (resp.json() or {}).get("result") or {}
    except Exception as exc:
        return _unknown_flow(
            "frozen_final_scores", f"repair dry-run failed: {str(exc)[:120]}"
        )

    scanned = int(result.get("events_scanned") or 0)
    if scanned == 0:
        # checked == 0 can never be a pass (an empty slate is not evidence).
        return _unknown_flow(
            "frozen_final_scores",
            "no settled ESPN-mapped events in the scanned window",
            groups_scanned=result.get("groups_scanned"),
        )

    frozen = frozen_final_score_events(result.get("ledger") or [])
    failures = [
        {"detail": f"settled {f['sport']} event {f['matchup']} stores score "
                   f"{f['stored_score']} but ESPN's FINAL is {f['espn_final']} "
                   f"(id {f['event_id']}"
                   + (", WINNER FLIP" if f["winner_flip"] else "")
                   + ") — frozen/wrong final (CAL-P002; POST /api/admin/repairs/"
                     "event-final-scores?apply=true)"}
        for f in frozen
    ]
    return {
        "flow": "frozen_final_scores",
        "checked": scanned,
        "passed": len(failures) == 0,
        "failures": failures,
        "evidence": {
            "events_scanned": scanned,
            "groups_scanned": result.get("groups_scanned"),
            "groups_remaining": result.get("groups_remaining"),
            "identity_blocked": result.get("identity_blocked"),
            "winner_flips": result.get("winner_flips"),
            "frozen_scores": frozen,
        },
    }


# Markets walked per sentinel run. Newest-first, so this is "did anything in the
# most recent slice of the market table acquire an impossible field".
_WINNER_FIELD_SCAN = 20000


async def _run_winner_field_coherence(client: httpx.AsyncClient) -> dict:
    """CAL-P006 (#1527): a single-winner market must have exactly one winner.

    Measures via the ``winner-field-coherence`` census in DRY-RUN (it never
    writes), newest-first, so guard and census cannot drift on what the defect is.
    A broken or unauthenticated measurement is SKIPPED, never filed — filing on
    our own broken instrument is the cry-wolf the grid health score was retired
    for."""
    headers = _admin_headers()
    if headers is None:
        return _unknown_flow(
            "winner_field_coherence", "ADMIN_TOKEN unset — census rail unavailable"
        )
    try:
        resp = await client.post(
            "/api/admin/repairs/winner-field-coherence",
            headers=headers,
            params={
                "apply": "false",
                "limit": _WINNER_FIELD_SCAN,
                "newest_first": "true",
            },
        )
        resp.raise_for_status()
        result = (resp.json() or {}).get("result") or {}
    except Exception as exc:
        return _unknown_flow(
            "winner_field_coherence", f"census dry-run failed: {str(exc)[:120]}"
        )

    walked = int(result.get("markets_walked") or 0)
    if walked == 0:
        # checked == 0 can never be a pass (an empty window is not evidence).
        return _unknown_flow(
            "winner_field_coherence", "census walked no markets"
        )

    fresh = freshly_written_incoherent_fields(result.get("defects") or [])
    failures = [
        {"detail": f"{f['source']} {f['category'] or 'uncategorised'} market "
                   f"{f['market_id']} \"{f['name']}\" is mutually exclusive but has "
                   f"{f['winners']}/{f['legs']} winners and "
                   f"{f['near_certain']}/{f['legs']} near-certain legs "
                   f"(field sums to {f['field_sum']}) — written {f['last_written']}, "
                   f"so a producer is STILL creating this (#1527; census: POST "
                   f"/api/admin/repairs/winner-field-coherence)"}
        for f in fresh
    ]
    return {
        "flow": "winner_field_coherence",
        "checked": walked,
        "passed": len(failures) == 0,
        "failures": failures,
        "evidence": {
            "markets_walked": walked,
            "defect_markets": result.get("defect_markets"),
            "by_class": result.get("by_class"),
            "by_category": result.get("by_category"),
            "bogus_winner_outcomes": result.get("bogus_winner_outcomes"),
            # The standing backlog is reported, never failed on: repairing it is
            # an authority-gated write, not something this guard can demand.
            "standing_backlog_in_window": (result.get("defect_markets") or 0)
            - len(fresh),
            "written_recently": result.get("written_recently"),
            "fresh_write_hours": result.get("fresh_write_hours"),
            "next_offset": result.get("next_offset"),
            "exhausted": result.get("exhausted"),
            "fresh_defects": fresh[:10],
        },
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
    headers = _admin_headers()
    if headers is None:
        return _unknown_flow(
            "team_identity_dupes",
            "ADMIN_TOKEN unset — admin endpoints unavailable",
        )
    try:
        # apply=false → dry-run census only, no writes.
        r1 = await client.post(
            "/api/admin/repairs/team-identity-merge",
            params={"apply": "false"},
            headers=headers,
        )
        r1.raise_for_status()
        census = r1.json() or {}
        r2 = await client.get(
            "/api/admin/team-clusters/pending",
            params={"summary": "true"},
            headers=headers,
        )
        r2.raise_for_status()
        awaiting = int((r2.json() or {}).get("awaiting", 0) or 0)
    except Exception as exc:
        return _unknown_flow(
            "team_identity_dupes", f"admin endpoint failed: {str(exc)[:120]}"
        )

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


def render_failure_lines(failures: list[dict], cap: int = 40) -> list[str]:
    """Render failure dicts as markdown bullets, KEEPING every structured key.

    UX-P091. ``build_flow_issue_body`` used to render ``f.get('detail')`` alone,
    which silently discarded every other key on the dict. ``event_completeness``
    is the specimen: it puts the id in ``{"event_id": eid, "detail": ...}`` and
    writes no id into the prose, so **#1942 was filed naming two teams and
    nothing else**. Reproducing it meant reading a SIBLING issue's evidence JSON
    (#1941) to recover the id — for a finding this rail had already measured.

    A limb should not have to remember to repeat its ids inside a sentence for
    them to survive filing. Rendering the whole dict makes losing one
    unrepresentable rather than merely discouraged, which is why this is a shared
    helper and not a fix to the one limb that happened to get caught.
    """
    lines: list[str] = []
    for f in failures[:cap]:
        if not isinstance(f, dict):
            lines.append(f"- {f}")
            continue
        detail = f.get("detail")
        extras = " ".join(
            f"`{k}={v}`" for k, v in f.items() if k != "detail" and v is not None
        )
        if detail and extras:
            lines.append(f"- {detail}  ({extras})")
        elif detail:
            lines.append(f"- {detail}")
        else:
            lines.append(f"- {extras or f}")
    if len(failures) > cap:
        lines.append(f"- …and {len(failures) - cap} more")
    return lines


def build_flow_redetect_comment(flow_result: dict) -> str:
    """The comment posted when a flow fails again on an ALREADY-OPEN issue.

    UX-P091. ``reconcile_issue``'s dedupe path is comment-only by design — "no
    duplicate, no label edit" — so the issue BODY is frozen at whatever the first
    run saw, forever. This comment was therefore the only channel carrying
    current state, and it carried **two integers**.

    The cost, measured: **#1483** was filed 2026-07-29 with 2 failures and has
    been re-observed for nineteen days. On 2026-08-17 the same flow was carrying
    a NEW class — four MLB games rendering LIVE 40–46h before their own
    commence_time, plus a `completed_at` inverted by 68.2h (gotcha #32's
    cross-merge invariant) — and a reader of #1483 could see none of it. The body
    said 2 failures about other games; the newest comment said "8 failing of 49
    checked. Still open."

    **A count that moves is not a finding.** A flow getting qualitatively worse
    rendered identically to one standing still, which is the same shape as gotcha
    #53: the emptier reading and the real one produced the same text. So the
    re-detect comment now carries the failures themselves.
    """
    fp = flow_fingerprint(flow_result["flow"])
    n = len(flow_result["failures"])
    parts = [
        f"Flow Sentinel re-observed this failure: **{n} failing** of "
        f"{flow_result['checked']} checked (fingerprint `{fp}`). Still open.",
        "",
        "**Current failures** (this run — the issue body above is frozen at "
        "first-file and does NOT reflect them):",
    ]
    parts += render_failure_lines(flow_result["failures"], cap=20)
    return "\n".join(parts)


def build_flow_issue_body(flow_result: dict, *, refreshed: bool = False) -> str:
    """The issue body. Used BOTH to file a new issue and, since UX-P092, to
    refresh an already-open one on re-detection.

    `refreshed=True` labels the body as a live re-observation rather than a
    first-file record. UX-P091 made the re-detect COMMENT carry the current
    failures, which fixed the channel but not the artefact: the body is what a
    reader sees first, and #1483's said "2 failures" for nineteen days while the
    flow was failing eight, one of them a new p1 class. A body that is rewritten
    must say so — a reader who cannot tell a refreshed body from the original
    cannot tell how old the finding is either.
    """
    flow = flow_result["flow"]
    fp = flow_fingerprint(flow)
    parts = [
        "## Flow Sentinel finding",
        "",
        f"`flow-sentinel-fingerprint:{fp}`  (dedupe key — do not remove)",
        "",
    ]
    if refreshed:
        from datetime import datetime as _now_dt, timezone as _now_tz

        parts += [
            f"> 🔄 **This body was refreshed by a later run** "
            f"({_now_dt.now(_now_tz.utc).isoformat(timespec='seconds')}). "
            f"It shows the CURRENT failures, not the ones this issue was filed "
            f"for. The comment thread below is the history.",
            "",
        ]
    parts += [
        f"**Flow:** `{flow}` — {_FLOW_TITLES.get(flow, flow)}  ",
        f"**Checks run:** {flow_result['checked']}  ",
        f"**Failing:** {len(flow_result['failures'])}  ",
        f"**Run against:** {FLOW_SENTINEL_API}",
        "",
        "### Failures",
    ]
    parts += render_failure_lines(flow_result["failures"])

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
_FLOW_MARKER = "flow-sentinel-fingerprint"


def _flow_title_prefix(flow: str) -> str:
    """The title-prefix fallback for this flow's dedup — 1:1 with the fingerprint
    (flow name ↔ flow ↔ fingerprint), so it still de-dups an issue whose body
    marker was edited away."""
    return f"[Flow Sentinel] {_FLOW_TITLES.get(flow, flow)} ("


def issue_matches_flow(issue: dict, flow: str, fingerprint: str) -> bool:
    """True when an OPEN issue is the sentinel's issue for this flow/fingerprint.
    Thin wrapper over the shared rail (Queue #258) so all sentinels share one
    matcher — body marker (primary) or ``[Flow Sentinel] {name} (`` title prefix
    (fallback). Pure (unit-tested)."""
    from app.tasks.sentinel_filing import issue_matches

    return issue_matches(issue, fingerprint, _FLOW_MARKER, title_prefix=_flow_title_prefix(flow))


def find_matching_open_issue(
    open_issues: list[dict], flow: str, fingerprint: str
) -> int | None:
    """Pure dedup lookup over a list of open issues → the LOWEST matching issue
    number (stable canonical wins). Thin wrapper over the shared rail."""
    from app.tasks.sentinel_filing import find_matching_issue

    return find_matching_issue(
        open_issues, fingerprint, _FLOW_MARKER, title_prefix=_flow_title_prefix(flow)
    )


def file_flow_issue(flow_result: dict, open_issues: list[dict] | None = None) -> dict:
    """File OR comment ONE issue for a failing flow's fingerprint, via the shared
    rail (Queue #258). ``open_issues`` may be injected so a whole run reuses one
    strongly-consistent REST-list snapshot."""
    from app.tasks.sentinel_filing import reconcile_issue

    flow = flow_result["flow"]
    fp = flow_fingerprint(flow)
    severity = severity_for_flow(flow, len(flow_result["failures"]), flow_result["checked"])
    labels = [
        "alert-intake",
        "needs-agent",
        _FLOW_AREA_LABELS.get(flow, "area:infra"),
        f"priority:{severity.lower()}",
    ]
    res = reconcile_issue(
        red=True,
        fingerprint=fp,
        marker_key=_FLOW_MARKER,
        labels=labels,
        title=build_flow_issue_title(flow_result),
        body=build_flow_issue_body(flow_result),
        title_prefix=_flow_title_prefix(flow),
        red_comment=build_flow_redetect_comment(flow_result),
        # UX-P092: on a dedupe, rewrite the BODY too, not just the comment.
        # UX-P091 fixed the channel; this fixes the artefact. #1483 read "2
        # failures" for nineteen days while the flow was failing eight.
        red_body=build_flow_issue_body(flow_result, refreshed=True),
        open_issues=open_issues,
    )
    res["flow"] = flow
    if res.get("action") == "filed":
        res["severity"] = severity
    return res


def resolve_flow_issue(flow_result: dict, open_issues: list[dict] | None = None) -> dict:
    """RED→GREEN: when a flow re-checks GREEN, close its canonical open issue with
    a recovery comment (Queue #258). A GREEN flow with no open issue is a no-op.
    SKIPPED flows must never resolve (a skip means we couldn't measure, not that
    the failure is fixed) — the caller filters those out before calling here."""
    from app.tasks.sentinel_filing import reconcile_issue

    flow = flow_result["flow"]
    fp = flow_fingerprint(flow)
    res = reconcile_issue(
        red=False,
        fingerprint=fp,
        marker_key=_FLOW_MARKER,
        green_comment=(
            f"Flow Sentinel re-checked GREEN — `{flow}` now passes "
            f"({flow_result['checked']} checked, 0 failing; fingerprint `{fp}`). "
            f"Auto-closing; a future recurrence opens a fresh episode."
        ),
        open_issues=open_issues,
    )
    res["flow"] = flow
    return res


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
        ("discover_first_page", _run_discover_first_page),
        ("resolved_state", _run_resolved_state),
        ("chart_density", _run_chart_density),
        ("category_discover", _run_category_discover),
        ("participation_family", _run_participation_family),
        ("matured_linkage", _run_matured_linkage),
        ("unlinked_held", _run_unlinked_held),
        ("season_aggregate_linkage", _run_season_aggregate_linkage),
        ("frozen_final_scores", _run_frozen_final_scores),
        ("winner_field_coherence", _run_winner_field_coherence),
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
    # #1494: three outcomes, not two. An UNKNOWN flow (auth/transport/5xx/parse
    # failure, or ADMIN_TOKEN unset) could not measure anything, so it is
    # excluded from `flows_passed` instead of silently inflating it — the bug
    # that let three admin flows report clean for weeks while every one of their
    # requests was 403ing. `flows_verified` is the honest denominator: the
    # headline "N/M passed" is only meaningful against the flows that ran.
    outcomes = [flow_outcome(f) for f in stats["flows"]]
    failing = [f for f, o in zip(stats["flows"], outcomes) if o == "fail"]
    unknown = [f for f, o in zip(stats["flows"], outcomes) if o == "unknown"]
    passed = [f for f, o in zip(stats["flows"], outcomes) if o == "pass"]
    stats["scorecard"] = {
        "flows_total": len(stats["flows"]),
        "flows_verified": len(passed) + len(failing),
        "flows_passed": len(passed),
        "flows_failed": len(failing),
        "flows_unknown": len(unknown),
        "unknown_flows": [f["flow"] for f in unknown],
        "per_flow": [
            {"flow": f["flow"], "outcome": o, "passed": o == "pass",
             "checked": f["checked"], "failing": len(f["failures"]),
             "unknown": o == "unknown",
             "skipped": f.get("skipped", False)}
            for f, o in zip(stats["flows"], outcomes)
        ],
    }

    # --- Filing + recovery (one deduped issue per failing flow; close-on-green
    # for a flow that now passes). One strongly-consistent REST-list snapshot is
    # reused for the whole run so dedup/close never race the flaky search index
    # (Queue #258). A SKIPPED flow is neither filed nor resolved — a skip means we
    # could not measure, not that the failure is fixed. ---
    if file_issues:
        from app.tasks.sentinel_filing import list_open_alert_issues

        open_issues = list_open_alert_issues()
        for f in failing:
            stats["filed"].append(file_flow_issue(f, open_issues=open_issues))
        recovered = [
            f for f, o in zip(stats["flows"], outcomes) if o == "pass"
        ]
        stats["resolved"] = [
            r
            for r in (resolve_flow_issue(f, open_issues=open_issues) for f in recovered)
            if r.get("action") in ("resolved", "close_failed")
        ]

    stats["duration_seconds"] = round(_time.monotonic() - start, 1)
    # #232: L2-153's cockpit card needs a wall-clock stamp to render precise
    # staleness (a cached verdict without one reads as SILENT). TTL is 14d — far
    # more than 2× the daily run interval — so a completed run is never evicted
    # before the next one refreshes it.
    from datetime import datetime as _dt, timezone as _tz
    stats["generated_at"] = _dt.now(_tz.utc).isoformat()

    # Persist the run so the cockpit / ops read path can tile it without
    # re-running. Queue 298 (#1512): durable row FIRST, Redis as the accelerator.
    # This used to be a bare SETEX whose failure was logged and swallowed, so an
    # evicted or unwritten scorecard still reported a healthy run.
    from app.services.durable_snapshots import publish_sentinel_evidence
    from app.utils.durable_state import evaluate_publication

    stages = await publish_sentinel_evidence(
        identity="sentinel:flow",
        redis_key="bainluck:flow_sentinel:last",
        stats=stats,
        source="flow_sentinel",
    )
    stats["persistence"] = stages
    evaluate_publication(
        compute_complete=True,
        durable_write="ok" if stages["durable"] in ("ok", "superseded") else "error",
        volatile_write=stages.get("volatile", "not_attempted"),
        stages=stages,
    ).raise_if_failed("flow sentinel evidence")

    logger.info(
        "Flow sentinel (%s%s): %d/%d verified flows passed (%d UNKNOWN of %d "
        "total), %d issues filed in %.1fs",
        stats["mode"],
        " +canary" if canary else "",
        stats["scorecard"]["flows_passed"],
        stats["scorecard"]["flows_verified"],
        stats["scorecard"]["flows_unknown"],
        stats["scorecard"]["flows_total"],
        len(stats["filed"]),
        stats["duration_seconds"],
    )
    return stats
