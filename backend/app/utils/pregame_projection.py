"""The projected final a finished game was forecast to end on, read from before play (#11296).

PILLARS: TRUTH / FORMATTING. SHIP: a final card or page can set the actual score
beside the score the sportsbooks projected BEFORE the game, in the same units and
the same team order, or say exactly why it cannot.

── WHY ``current_odds`` CANNOT ANSWER THIS ─────────────────────────────────────

``current_odds.projected_*`` is each book's LATEST row, and on a finished game
the latest row is in-play. UX read eight NFL finals on ``/api/events/search``
(2026-10-19 22:24Z) and all eight served an in-game pair: event 15328569,
kick-off 17:00Z, pair captured 20:25Z at 31.2 / 23.8 beside a 31–38 final.
Printing that as "projected" invents a forecast nobody made before the game.

``Event.opening_home_spread`` / ``opening_over_under`` are not an answer either.
They are the last pregame MEDIANS (``_maybe_set_opening_odds`` rewrites them on
every scheduled poll), but nothing records WHEN they were last written, so the
comparison could not say when its forecast was taken. ``closing_*`` is filled by
``backfill_winners`` from the single newest row across ALL books, with spread and
total chosen independently, so its two halves can come from different books at
different times. Neither is used.

── WHAT THIS READS INSTEAD ─────────────────────────────────────────────────────

Each book's own newest ``odds_snapshots`` row captured STRICTLY BEFORE the
boundary below, aggregated exactly the way ``current_odds`` aggregates the
latest rows of a scheduled game. That is the consensus membership the page uses
before play: every book's latest row, with no freshness cutoff (the stale-book
filter runs only once a game has started). In other words, the projected pair
the scheduled page served at the last moment before the listed start. Rules,
each with a test:

* **Latest means latest.** One row per book: its newest row before the boundary,
  ties broken by the higher id. If that row carries no projected pair (say the
  book had pulled its spread), the book contributes nothing. It never falls back
  to an OLDER pair from the same book, because then a "latest" claim would mix
  readings from different times.
* **A pair is one book's pair.** A row counts only when both projected values
  are present, finite and non-negative, AND they solve that row's own spread and
  total (``project_scores``). That makes it provable that the two numbers were
  observed together and are not two halves from different rows.
* **The existing refusals still apply.** Books whose home/away are reversed
  (``detect_reversed_bookmakers``, run over this same pregame set) and books
  whose projected leader is their own moneyline underdog (#8231) are excluded.
  The underdog is read from both stored legs, so a three-way soccer board is
  judged correctly (``_crowns_its_own_underdog``).
* **The stamps are a range.** Each book contributes its own last reading, so
  no single instant is when "the forecast" was taken. The payload carries
  ``earliest_captured_at`` and ``latest_captured_at`` over the contributing
  rows, so a consensus that leans on a book which stopped quoting early says so
  rather than hiding behind its freshest member. Rows the pre-#11286 odds
  collapse deleted are simply absent: every surviving row keeps its own values,
  so what is read is a real reading at its own stamp. The poller stamps a row
  AFTER the venue response arrives (``_create_or_update_snapshot``), so the stamp
  is an upper bound on the read, and ``captured_at < boundary`` means the read
  happened before it.

── THE BOUNDARY, AND WHAT IT DOES NOT CLAIM ───────────────────────────────────

No column records when a game actually began, so this reads no observed
kick-off. The boundary is the row's stored ``commence_time``, admitted only when
it is the start a SCHEDULE published (``start_is_from_schedule``: ESPN, StatPal
or The Odds API) and is not a placeholder instant either provider has marked
(``start_placeholder``). A market close, a ticker date or a listing stamp
(gotcha #14) is refused rather than used. The payload says so twice:
``boundary: "scheduled_start"`` and ``kind: "last_before_scheduled_start"``.

What a scheduled boundary cannot prove, both directions (see
``KIND_LAST_BEFORE_SCHEDULED_START``): a game that began EARLY would admit an
in-play row, and a game that began LATE excludes pregame readings taken after
the listing. The repo's observed-start evidence (the ``observed_transition_markers``
Q1 bracket) lives only inside the per-event ``/history`` read, so a bounded
batched observed-start read for list surfaces is #11296's named remaining
dependency.

This is the same cutoff the settled probability prior uses
(``PREMATCH_PRIOR_SQL``: the row's current ``commence_time``), made stricter:
``<`` rather than ``<=``, plus the two provenance gates. A rescheduled start moves
it, because the current column is read at serve time.

── UNITS ───────────────────────────────────────────────────────────────────────

Only where the pair is a scoreline: the spread moves with the matchup and both
lines are in the unit the scoreboard counts. That is football and basketball
(``points``, ``full_game``) and soccer (``goals``, ``regulation``: its sportsbook
lines settle on 90 minutes). Hockey's puck line and baseball's run line are
pinned at ±1.5 (#8617), tennis is projected in games under a sets scoreboard,
and a fight has no points (#9006). Those and any undeclared sport serve
``format_unsupported``. The table is the web's ``PROJECTED_FINAL_FORMATS``, so
producer and card admit the same sports.

── WHAT THE ACTUAL SCORE COVERS (soccer) ───────────────────────────────────────

A forecast settles on a period, and so does a scoreboard. Football and
basketball are simple: the final is ``full_game``, overtime included, which is
what their lines settle on. A soccer final is not: a knockout level after 90
minutes goes to extra time and maybe penalties, and the stored score is then
NOT the 90-minute score the forecast is about. The forecast's own ``period`` is
no evidence of what the scoreboard covers.

So a settled soccer row also carries ``final_score_period: "regulation"`` when,
and only when, its own stored ``period`` says the match ENDED at full time. That
is the contract the three-way accuracy curve already grades on
(``soccer_three_way.regulation_finish_proven``, CERT-4066): the ESPN sync writes
``status.type.detail`` into ``period``, ``"FT"`` on a full-time finish, and the
extra-time and shootout finishes carry other details, refused by exact
equality. A period left at a live token, an absent period, ``AET`` or a shootout
detail serves NO key, so the comparison is withheld rather than set against an
extra-time total or a shootout tally. Nothing is inferred from the score, the
clock, the competition or the forecast.

The box-score status the curve also accepts is not used here: list routes do not
load ``box_score_data``, so using it would let the event page compare a game its
own card refuses. The key is a sibling of the forecast and is set whether or
not a forecast was found: it is a fact about the score, not about the reading.
Football and basketball rows serve no key; their callers pass ``full_game``.

── LIVE DETAIL ─────────────────────────────────────────────────────────────────

The event page of a game being played may ask the same question, so its
headline can set the current in-play projection beside the one retained from
before the scheduled start (``read_pregame_projections(..., live_detail=True)``).
Only the event page passes it, and only a row that PRINTS ``"live"`` is added;
every list, search and feed caller stays settled-only. Nothing else changes:
the same boundary and its provenance gates, the same statement and selection,
the same format table and refusals, the same object.

* **The baseline is not the in-play reading.** The in-play pair
  (``card_projected_pair._live_projection``) admits only rows at or after this
  same ``commence_time``; this reads only rows strictly before it. No row can be
  both, so the first in-play reading can never become the baseline. A live row
  whose published start is still ahead is not asked at all.
* **Soccer's period is the forecast's, not the scoreboard's.** The baseline
  carries ``period: "regulation"`` because its lines settle on 90 minutes. A
  live row never serves ``final_score_period`` (there is no final yet), and the
  baseline is not withheld for want of one. Whether the CURRENT pair may be set
  beside it is the in-play pair's own gate (it is withheld outside regulation
  play), so a client compares only when both objects name the same ``unit`` and
  ``period``.

── PROVENANCE IS ITS OWN ───────────────────────────────────────────────────────

``prematch_odds.source`` names the VENUE of the settled probability prior
(Kalshi → Polymarket → sportsbooks). This forecast is a different reading, so it
is served as its own object (``pregame_projection``) with its own source,
basis, time and kind, and never inherits that field.
"""

from __future__ import annotations

import math
from datetime import datetime, timezone
from typing import Any, Iterable, Mapping, Optional, Sequence

from app.utils.odds_math import (
    aggregate_bookmaker_odds,
    detect_reversed_bookmakers,
    project_scores,
    projection_contradicts_moneyline,
)
from app.utils.prematch_reading import SETTLED_STATUSES
from app.utils.scheduled_start import loaded_commence_time_source, start_is_from_schedule
from app.utils.soccer_three_way import is_soccer_key, regulation_finish_proven
from app.utils.start_placeholder import (
    espn_start_placeholder_tag,
    espn_start_placeholder_tags,
    start_placeholder_tag,
    start_placeholder_tags,
)

#: The served object's key and its refusal's key. Siblings of ``prematch_odds``.
PROJECTION_KEY = "pregame_projection"
UNAVAILABLE_KEY = "pregame_projection_unavailable"
#: What a settled row's ACTUAL score covers, when its own row proves it. A
#: sibling of the forecast, never inside it (see "WHAT THE ACTUAL SCORE COVERS").
SCORE_PERIOD_KEY = "final_score_period"
#: The one value served: a soccer match that ended at full time.
SCORE_PERIOD_REGULATION = "regulation"

#: The one non-settled status the event page may ask about (``live_detail``).
#: Exact: ``suspended``, ``scheduled`` and anything unrecognised are not asked.
LIVE_DETAIL_STATUS = "live"

#: The only kind produced, named for the boundary it actually used: each book's
#: last reading before the PUBLISHED start. It is not ``"latest_before_play"``:
#: if play began late, readings between the listed start and the first ball were
#: still pregame and are excluded, and nothing here observed the first ball.
#: Two kinds stay reserved and are deliberately NOT produced:
#:
#: * ``"latest_before_play"`` needs an observed start. The repo has one, the
#:   ``observed_transition_markers`` Q1 bracket (football and basketball, from the
#:   win-prob game-state stream), but it is computed only inside the per-event
#:   ``/history`` read. Using it on cards needs a bounded batched observed-start
#:   read, which does not exist (#11296's named remaining dependency).
#: * ``"opening"``: our first stored row is the first price we happened to see,
#:   not the market's opening (see ``prematch_reading``'s note on
#:   ``futures_outcomes.opening_probability``).
KIND_LAST_BEFORE_SCHEDULED_START = "last_before_scheduled_start"

BOUNDARY_SCHEDULED_START = "scheduled_start"
SOURCE_SPORTSBOOKS = "sportsbooks"
BASIS_CONSENSUS_SPREAD_TOTAL = "consensus_spread_total"

# Refusal reasons, first failing wins. A settled row with no positive carries one.
REASON_NO_START = "no_start"
REASON_START_NOT_FROM_SCHEDULE = "start_not_from_schedule"
REASON_START_IS_PLACEHOLDER = "start_is_placeholder"
REASON_FORMAT_UNSUPPORTED = "format_unsupported"
REASON_NO_PREGAME_READING = "no_pregame_reading"
REASON_READ_FAILED = "read_failed"

#: Sport-key prefixes whose sportsbook pair is a scoreline: the spread moves with
#: the matchup AND both lines are in the unit the scoreboard counts. With the
#: unit and the period the lines settle on. The SAME table as the web's
#: ``PROJECTED_FINAL_FORMATS`` (``frontend/lib/projectedFinalPair.ts``, #2920),
#: so a producer positive is never a card the consumer refuses. Hockey is out
#: like baseball: its puck line is pinned at ±1.5 (NHL 15333056 and 15332424 both
#: −1.5 → "4 – 3"; AHL 15327140 1.5 / 1.5 → 0.0 – 1.5). A sport joins by name;
#: nothing gets in by default.
_PROJECTION_FORMAT_BY_PREFIX: tuple[tuple[str, str, str], ...] = (
    ("americanfootball_", "points", "full_game"),
    ("basketball_", "points", "full_game"),
    ("soccer_", "goals", "regulation"),
)

#: How far a stored pair may miss ``project_scores(spread, total)`` and still be
#: that row's own pair. The writer rounds each side to 0.1 and the columns hold
#: one decimal, so two independent half-step roundings bound the error at 0.1.
_PAIR_LINE_TOLERANCE = 0.11


def projection_format(sport_key: Optional[str]) -> Optional[tuple[str, str]]:
    """``(unit, period)`` for a supported sport, or ``None`` if its pair is no scoreline."""
    key = str(sport_key or "").lower()
    for prefix, unit, period in _PROJECTION_FORMAT_BY_PREFIX:
        if key.startswith(prefix):
            return unit, period
    return None


def _utc(value: Any) -> Optional[datetime]:
    if not isinstance(value, datetime):
        return None
    return value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value


def _loaded(event: Any, name: str) -> Any:
    """A column already in memory, never a lazy load (gotcha #42 / #1698)."""
    state = getattr(event, "__dict__", None)
    if isinstance(state, dict) and name in state:
        return state[name]
    inner = state.get("_event") if isinstance(state, dict) else None
    if inner is not None:
        return _loaded(inner, name)
    return None


def pregame_boundary(event: Any) -> tuple[Optional[datetime], Optional[str]]:
    """``(boundary_at, None)`` when the row's start may bound a pregame read, else ``(None, reason)``.

    Not a status check: callers decide which rows are asked (settled, plus a
    live row on the event page: see "LIVE DETAIL").
    """
    commence = _utc(_loaded(event, "commence_time"))
    if commence is None:
        return None, REASON_NO_START
    if not start_is_from_schedule(loaded_commence_time_source(event)):
        return None, REASON_START_NOT_FROM_SCHEDULE
    tags = _loaded(event, "event_tags")
    if start_placeholder_tag(commence) in start_placeholder_tags(
        tags
    ) or espn_start_placeholder_tag(commence) in espn_start_placeholder_tags(tags):
        return None, REASON_START_IS_PLACEHOLDER
    return commence, None


def _finite(value: Any) -> Optional[float]:
    if value is None:
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) else None


def _get(row: Any, key: str) -> Any:
    return row.get(key) if isinstance(row, Mapping) else getattr(row, key, None)


def _own_pair(row: Any) -> Optional[tuple[float, float]]:
    """The row's projected pair when it is provably that row's own, else ``None``."""
    home = _finite(_get(row, "projected_home_score"))
    away = _finite(_get(row, "projected_away_score"))
    if home is None or away is None or home < 0 or away < 0:
        return None
    spread = _finite(_get(row, "home_spread"))
    total = _finite(_get(row, "over_under"))
    if spread is None or total is None:
        return None
    line_home, line_away = project_scores(spread, total)
    if (
        abs(line_home - home) > _PAIR_LINE_TOLERANCE
        or abs(line_away - away) > _PAIR_LINE_TOLERANCE
    ):
        return None
    if _crowns_its_own_underdog(row, home, away):
        return None
    return home, away


def _crowns_its_own_underdog(row: Any, home: float, away: float) -> bool:
    """#8231's refusal, with the moneyline leader read from BOTH legs when stored.

    ``projection_contradicts_moneyline`` judges the leader as ``home > 0.5``,
    which is the same question only on a two-way board. A soccer book stores the
    three-way legs (``h2h_pair_on_the_full_board`` leaves them summing to ~0.74),
    so a 0.45 home favourite over a 0.29 away would read as the underdog and its
    honest projection would be refused. Comparing the two stored legs asks who
    the book's moneyline favours on every board, and is ``home > 0.5`` exactly
    when the legs are complements.
    """
    home_p = _finite(_get(row, "home_win_probability"))
    away_p = _finite(_get(row, "away_win_probability"))
    if home_p is not None and away_p is not None:
        # Re-centre so the shared rule judges "home leads the moneyline".
        return projection_contradicts_moneyline(0.5 + (home_p - away_p) / 2, home, away)
    return projection_contradicts_moneyline(home_p, home, away)


def select_pregame_projection(
    rows: Sequence[Any], *, boundary_at: datetime, unit: str, period: str
) -> tuple[Optional[dict], Optional[str]]:
    """``(projection, None)`` from one event's per-book latest pregame rows, else ``(None, reason)``.

    ``rows`` is :data:`PREGAME_PROJECTION_SQL`'s output for ONE event: at most one
    row per book. The boundary is re-applied here so a caller that hands in an
    unbounded row (a test, a future reuse) still cannot admit one from in-play.
    """
    boundary = _utc(boundary_at)
    if boundary is None:
        return None, REASON_NO_START
    pregame: list[Any] = []
    seen_books: set = set()
    for row in sorted(
        rows,
        key=lambda r: (_utc(_get(r, "captured_at")) or boundary, _get(r, "id") or 0),
        reverse=True,
    ):
        captured = _utc(_get(row, "captured_at"))
        if captured is None or captured >= boundary:
            continue
        book = _get(row, "bookmaker")
        if book in seen_books:
            continue  # latest per book only, if the caller handed more than one
        seen_books.add(book)
        pregame.append(row)

    reversed_books = detect_reversed_bookmakers(pregame)
    contributors: list[tuple[Any, tuple[float, float]]] = []
    for row in pregame:
        if _get(row, "bookmaker") in reversed_books:
            continue
        pair = _own_pair(row)
        if pair is not None:
            contributors.append((row, pair))
    if not contributors:
        return None, REASON_NO_PREGAME_READING

    # The same consensus `current_odds` prints, over pair-complete rows only, so
    # both means are taken over exactly the same books.
    # #8231 has already been applied above, from both legs, so no probability is
    # passed: `aggregate_bookmaker_odds` would re-judge from the home leg alone.
    aggregated = aggregate_bookmaker_odds(
        [
            {"projected_home_score": home, "projected_away_score": away}
            for _, (home, away) in contributors
        ]
    )
    home = aggregated["projected_home_score"]
    away = aggregated["projected_away_score"]
    if home is None or away is None:
        return None, REASON_NO_PREGAME_READING
    stamps = [_utc(_get(row, "captured_at")) for row, _ in contributors]
    return (
        {
            "projected_home_score": home,
            "projected_away_score": away,
            "kind": KIND_LAST_BEFORE_SCHEDULED_START,
            # A RANGE, not one stamp: each book contributes its own last reading,
            # so no single time is when "the forecast" was taken.
            "earliest_captured_at": min(stamps).isoformat(),
            "latest_captured_at": max(stamps).isoformat(),
            "boundary": BOUNDARY_SCHEDULED_START,
            "boundary_at": boundary.isoformat(),
            "source": SOURCE_SPORTSBOOKS,
            "basis": BASIS_CONSENSUS_SPREAD_TOTAL,
            "bookmaker_count": len(contributors),
            "unit": unit,
            "period": period,
        },
        None,
    )


# ── THE READ ─────────────────────────────────────────────────────────────────
#
# Each book's newest row strictly before its event's boundary, for a page of
# events in ONE statement. Same access path as `latest_odds_per_bookmaker_query`
# (LAT-P030/#1494): a loose index scan enumerates each event's books on
# `ix_odds_snapshots_bookmaker_closing (event_id, bookmaker, captured_at DESC)`,
# then a top-1 per (event, book) walks the same index from the boundary down.
# Rows read are O(books), not O(snapshot depth), so a deep in-play history
# costs nothing here.
#
# `ids` and `cutoffs` are POSITIONAL (`unnest` pairs by index), so they are built
# by one pass in `pregame_projection_binds`, never at a call site.
PREGAME_PROJECTION_SQL = """
    WITH RECURSIVE bounds AS (
        SELECT u.event_id, u.cutoff
        FROM unnest(cast(:ids as integer[]), cast(:cutoffs as timestamptz[]))
             AS u(event_id, cutoff)
    ), books AS (
        SELECT b.event_id, b.cutoff,
               (SELECT min(s.bookmaker) FROM odds_snapshots s
                 WHERE s.event_id = b.event_id) AS bookmaker
        FROM bounds b
        UNION ALL
        SELECT p.event_id, p.cutoff,
               (SELECT min(s.bookmaker) FROM odds_snapshots s
                 WHERE s.event_id = p.event_id AND s.bookmaker > p.bookmaker)
        FROM books p
        WHERE p.bookmaker IS NOT NULL
    )
    SELECT x.id, x.event_id, x.bookmaker, x.captured_at,
           x.home_win_probability, x.away_win_probability,
           x.home_spread, x.over_under,
           x.projected_home_score, x.projected_away_score
    FROM books k
    CROSS JOIN LATERAL (
        SELECT s.id, s.event_id, s.bookmaker, s.captured_at,
               s.home_win_probability, s.away_win_probability,
               s.home_spread, s.over_under,
               s.projected_home_score, s.projected_away_score
        FROM odds_snapshots s
        WHERE s.event_id = k.event_id
          AND s.bookmaker = k.bookmaker
          AND s.captured_at < k.cutoff
        ORDER BY s.captured_at DESC, s.id DESC
        LIMIT 1
    ) x
    WHERE k.bookmaker IS NOT NULL
"""


def final_score_period(event: Any, sport_key: Optional[str], status: Any) -> Optional[str]:
    """``"regulation"`` when a settled soccer row's own ``period`` proves a full-time finish, else ``None``.

    ``status`` is the status the card prints. Only the loaded column is read
    (``_loaded``): a row that did not load ``period`` refuses, it never lazy-loads.
    """
    if status not in SETTLED_STATUSES or not is_soccer_key(sport_key):
        return None
    if not regulation_finish_proven(_loaded(event, "period")):
        return None
    return SCORE_PERIOD_REGULATION


def plan_pregame_projections(
    events: Iterable[Any],
    sport_key_of,
    status_of=None,
    *,
    live_detail: bool = False,
    now: Optional[datetime] = None,
) -> tuple[Optional[dict], dict[int, dict]]:
    """Decide every asked row's question in one pass: ``(binds, answers)``.

    ``answers`` already holds each asked row that is refused before any read
    (``{UNAVAILABLE_KEY: reason}``); ``binds`` covers the rest, or is ``None``
    when nothing needs reading. Rows that are not asked are absent from both.
    ``sport_key_of(event)`` must not emit IO.

    By default only SETTLED rows are asked. ``live_detail=True`` also asks a
    row that prints exactly ``"live"`` (see "LIVE DETAIL" below); only the
    event page passes it, so every list and feed caller keeps settled-only
    cost and output.

    ``status_of(event)`` is the status the CARD PRINTS, when the caller has
    one. Routes pass it so "settled" means what the reader sees: #11295's
    current-pair attach keys on the same served status, so a card can carry
    at most one of the two pairs (Discover's clearance condition 1). The
    stored column is the fallback.
    """
    ids: list[int] = []
    cutoffs: list[datetime] = []
    formats: dict[int, tuple[str, str]] = {}
    answers: dict[int, dict] = {}
    for event in events:
        status = status_of(event) if status_of is not None else _loaded(event, "status")
        live = live_detail and status == LIVE_DETAIL_STATUS
        if status not in SETTLED_STATUSES and not live:
            continue
        event_id = _loaded(event, "id")
        if event_id is None:
            continue
        fmt = projection_format(sport_key_of(event))
        if fmt is None:
            answers[event_id] = {UNAVAILABLE_KEY: REASON_FORMAT_UNSUPPORTED}
            continue
        boundary, reason = pregame_boundary(event)
        if boundary is None:
            answers[event_id] = {UNAVAILABLE_KEY: reason}
            continue
        if live and boundary > (_utc(now) or datetime.now(timezone.utc)):
            # A live row whose published start is still ahead: every row before
            # that start may already be in-play, so it has no pregame side yet.
            # Served statuses cannot reach this (`served_event_status` downgrades
            # a live claim before its start); a stored-status caller can.
            continue
        ids.append(event_id)
        cutoffs.append(boundary)
        formats[event_id] = fmt
    if not ids:
        return None, answers
    return {"ids": ids, "cutoffs": cutoffs, "formats": formats}, answers


def answers_from_rows(plan: Mapping[str, Any], rows: Iterable[Any]) -> dict[int, dict]:
    """Each planned row's answer from the statement's rows."""
    by_event: dict[int, list] = {event_id: [] for event_id in plan["ids"]}
    for row in rows:
        by_event.setdefault(_get(row, "event_id"), []).append(row)
    answers: dict[int, dict] = {}
    for event_id, cutoff in zip(plan["ids"], plan["cutoffs"]):
        unit, period = plan["formats"][event_id]
        projection, reason = select_pregame_projection(
            by_event.get(event_id, []), boundary_at=cutoff, unit=unit, period=period
        )
        answers[event_id] = (
            {PROJECTION_KEY: projection} if projection is not None
            else {UNAVAILABLE_KEY: reason}
        )
    return answers


async def read_pregame_projections(
    db: Any,
    events: Iterable[Any],
    sport_key_of,
    status_of=None,
    *,
    timeout_ms: Optional[int] = None,
    live_detail: bool = False,
) -> dict[int, dict]:
    """``{event_id: {PROJECTION_KEY: …} | {UNAVAILABLE_KEY: reason}}`` for the asked rows.

    At most one statement, inside a SAVEPOINT so a failure (a statement
    timeout on a bounded route) cannot poison the caller's transaction. A
    failed read answers ``read_failed`` for every row it was asked about;
    nothing raises except a cancellation, which propagates as itself.

    ``timeout_ms`` gives the read its own server-side bound, for a caller whose
    rows are already built and whose stage deadline must not be spent here
    (`/api/feed`, #11295's C1): ``SET LOCAL statement_timeout`` inside the
    savepoint. The savepoint is always ROLLED BACK, never released: the read
    writes nothing, and the rollback reverts the SET LOCAL so the bound cannot
    leak into a later stage on the same session. ``timeout_ms`` of zero or less
    means no budget is left: no round trip, and ``read_failed``.

    ``live_detail`` is :func:`plan_pregame_projections`' opt-in, for the event
    page only. It adds no statement: the live row joins the same one.
    """
    import logging

    from sqlalchemy import text

    events = list(events)
    plan, answers = plan_pregame_projections(
        events, sport_key_of, status_of, live_detail=live_detail
    )
    # What each settled row's actual score covers: decided from the row alone,
    # so it is served whatever the read below answers.
    score_periods: dict[int, str] = {}
    for event in events:
        status = status_of(event) if status_of is not None else _loaded(event, "status")
        event_id = _loaded(event, "id")
        period = final_score_period(event, sport_key_of(event), status)
        if event_id is not None and period is not None:
            score_periods[event_id] = period

    def _answered() -> dict[int, dict]:
        for event_id, period in score_periods.items():
            answers.setdefault(event_id, {})[SCORE_PERIOD_KEY] = period
        return answers

    if plan is None:
        return _answered()
    failed = {event_id: {UNAVAILABLE_KEY: REASON_READ_FAILED} for event_id in plan["ids"]}
    if timeout_ms is not None and timeout_ms <= 0:
        answers.update(failed)
        return _answered()
    try:
        nested = await db.begin_nested()
        try:
            if timeout_ms is not None:
                await db.execute(
                    text(f"SET LOCAL statement_timeout = '{int(timeout_ms)}ms'")
                )
            rows = (
                await db.execute(
                    text(PREGAME_PROJECTION_SQL),
                    {"ids": plan["ids"], "cutoffs": plan["cutoffs"]},
                )
            ).all()
        finally:
            try:
                await nested.rollback()
            except Exception:  # noqa: BLE001 — the read's own error wins
                pass
    except Exception:  # noqa: BLE001 — one optional key, never the page
        logging.getLogger(__name__).warning(
            "pregame projection read failed for %d event(s)",
            len(plan["ids"]),
            exc_info=True,
        )
        answers.update(failed)
        return _answered()
    answers.update(answers_from_rows(plan, rows))
    return _answered()


def attach_pregame_projection(payload: dict, answer: Optional[Mapping[str, Any]]) -> None:
    """Put one row's answer on its served dict: one of the two forecast keys, or
    neither, plus the actual score's period when the row proved one."""
    if not answer:
        return
    if answer.get(PROJECTION_KEY) is not None:
        payload[PROJECTION_KEY] = dict(answer[PROJECTION_KEY])
    elif answer.get(UNAVAILABLE_KEY):
        payload[UNAVAILABLE_KEY] = answer[UNAVAILABLE_KEY]
    if answer.get(SCORE_PERIOD_KEY) == SCORE_PERIOD_REGULATION:
        payload[SCORE_PERIOD_KEY] = SCORE_PERIOD_REGULATION
