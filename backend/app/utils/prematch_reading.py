"""The pre-match reading a settled card prints, and WHICH VENUE said it.

── WHY A SETTLED CARD NEEDS THIS AT ALL (ux/1036 Tier A) ────────────────────────

Alex, on /sports "Just Happened" at phone width, 2026-09-02: *"How come none of
these show pre-event probability?"* He was reading a column of FINAL cards where
every pre-match number had been collapsed into one grey footnote — ``Opened
40/60`` — which does not say which team is the 40. A live card on the same page
gives each team its own number.

That footnote is also the wrong SHAPE for the question. Two figures in fixed
positions with a slash between them is a duel a reader has to decode against the
name order printed elsewhere on the card; UX-P166 already had to fix it summing
to 101. A number belongs beside the name it is about.

── THE LADDER, AND WHY IT IS ORDERED RATHER THAN MERGED ─────────────────────────

Alex's rule, given for the tennis hub on the same day (#2747) and reused here
verbatim: **Kalshi → Polymarket → sportsbook blend, labelled by source, never
blank when any pre-match reading exists.**

Ordered, not blended. A blend of "what Kalshi thought" and "what the books
thought" is a number no venue ever quoted, and the whole point of a settled card
is to show a reader the forecast that was actually on offer before the match. The
blend is the product for a LIVE question (standing ruling: one number per
question); a settled pre-match reading is history, and history has an author.

Prediction markets come first because they are the product's subject. Sportsbooks
are the fallback, and a fallback that is a different KIND of claim has to say so
— hence :func:`needs_source_label`. "The market opened them at 40%" and "the
books opened them at 40%" are not the same sentence, and printing the second as
the first is the class of defect ux/1034 A3 removed from the hub's footnote.

── WHAT COUNTS AS A PRE-MATCH READING ───────────────────────────────────────────

For the two prediction-market rungs, the last ``win_prob_snapshots`` row captured
at or before ``commence_time``. Not ``futures_outcomes.opening_probability``:
measured on production 2026-09-02, that column is "the first price we happened to
see", and on the linked game markets sampled it was captured AFTER the first ball
— e.g. event 15301117 (Hull City v Aston Villa, 14:34Z) carries an opening
captured at 16:15Z. A number stamped after kickoff is not a prior, and it looks
exactly like one.

For the books rung, ``Event.opening_*``, which ``_maybe_set_opening_odds`` keeps
refreshing until the game starts and then freezes — a genuine last-pregame
consensus by construction.

── AWAY IS ACCEPTED, NOT ASSUMED ────────────────────────────────────────────────

Both writers store the pair, and both store complements. The served away side is
therefore used when it IS a complement of the home side and derived otherwise —
rather than derived unconditionally, which would silently discard a real reading
whenever a source stopped agreeing with itself, and rather than trusted
unconditionally, which is how a card prints two numbers that do not answer one
question. The rounding of the pair is not decided here; it is
``rendered_duel_percents``' job at serialization, once, for the same reason
UX-P114 gave.
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import os
import threading
import time
from collections import OrderedDict
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any, Iterable, Mapping, NamedTuple, Optional, Sequence

# #7514 — the same two predicates the served duel is withheld on (#6238), so the
# payload and the pre-match row cannot disagree about which away figures are a
# real price. `draw_priced_winner` imports only `graded_card`, which is stdlib
# only, so this adds no cycle.
from app.utils.draw_priced_winner import away_is_the_complement, sport_prices_a_draw

logger = logging.getLogger(__name__)

# The two prediction-market rungs, in Alex's order. Source ids as the payload and
# `win_prob_snapshots.source` spell them — never a display name; those are the
# renderer's business and ruling 141 keeps venue names out of narrative copy.
PREDICTION_MARKET_SOURCES: tuple[str, ...] = ("kalshi", "polymarket")

# The sportsbook consensus rung. Deliberately generic: `Event.opening_*` is a
# MEDIAN across whichever books were still quoting (#1841), so there is no one
# venue to name and naming one would be false.
BOOKS_SOURCE = "books"

PREMATCH_LADDER: tuple[str, ...] = PREDICTION_MARKET_SOURCES + (BOOKS_SOURCE,)

# How far a served pair may miss 1.0 and still be treated as the two sides of one
# question. Wide enough for the 4-dp rounding both writers store, tight enough
# that two unrelated numbers never pass.
_COMPLEMENT_TOLERANCE = 0.01

# How far a THREE-WAY reading's three members may miss 1.0 and still be read as
# one partition (#6277).
#
# THIS IS THE READ SIDE OF `prediction_market_matching._THREE_WAY_SUM_BAND` AND
# IT IS DELIBERATELY NO NARROWER. A reader tighter than its writer accepts the
# row into the table and then throws it away at serve time — the number changes
# in the database, every test passes, and the card does not move: exactly the
# inertness `_pair` already caused once here, one gate further along. The two are
# pinned to each other by a test rather than by sitting near each other.
#
# The band itself is measured (see that constant): 380 of 381 live three-way
# boards on production sum within 0.10 of one. Wider than `_COMPLEMENT_TOLERANCE`
# because a venue quoting three legs spreads its vig across three rather than
# two, and still far tighter than the mass it must distinguish itself from — the
# draw this exists to account for runs 22-30 points.
#
# STRICTLY wider than the writer's 0.10 rather than equal to it, and the extra
# point is not slack in the rule — it is slack in the ARITHMETIC. The writer's
# band is inclusive at 1.10 and `1.10 - 1.0` is 0.1000000000000000888 in binary
# floating point, so an equal tolerance rejects the writer's own endpoint. The
# pinning test found that on its first run, which is the argument for having
# written it. Nothing reaches the extra point: this gate only fires on a stored
# draw, and only the writer stores one.
_PARTITION_TOLERANCE = 0.11


def _as_probability(value: Any) -> Optional[float]:
    """A usable probability, or ``None``.

    Rejects the endpoints as well as the out-of-range: a pre-match reading of
    exactly 0 or 1 is a settled price that leaked backwards past the clock
    filter, and it would render as "the market called it impossible" — the
    strongest claim on the card, made by an artefact.
    """
    if value is None or isinstance(value, bool):
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    if number != number or number in (float("inf"), float("-inf")):
        return None
    if not 0.0 < number < 1.0:
        return None
    return number


def _pair(
    home: Any, away: Any, draw: Any = None, sport: Any = None
) -> Optional[tuple[float, float]]:
    """``(home, away)`` as a coherent pair, anchored on home.

    ── WHY A THREE-WAY READING IS NOT RE-COMPLEMENTED (#6277) ──────────────────
    The fallback below is a coherence guard: two numbers that do not sum to one
    are not the two sides of one question, so the away slot is rebuilt from the
    side we trust. That is right for the case it was written for — a stale or
    unrelated value — and it is exactly wrong for a soccer game winner, where the
    two named sides are MEANT to fall short of one because a draw holds the rest.

    So the guard became the defect's last line. Fixing the writers alone is
    completely inert: with the venue's true prices in the row
    (Villarreal .495 / Real Betis .245) this function returned .495/.505 — the
    same fabricated complement, rebuilt at serve time, and the card would not
    have moved by a pixel. Measured before the writer was touched, by calling it.

    ``draw`` is what tells the two cases apart, and it is evidence rather than a
    flag: a third member that closes the partition to 1.0 proves the shortfall is
    accounted for, and no stale or unrelated pair can produce one. Absent (every
    two-way source, and every row written before #6277 shipped) the old rule
    applies unchanged — which is the whole reason this is safe to land while the
    table is still almost entirely two-way.

    ── AND WHEN THERE IS NO DRAW TO OFFER AS EVIDENCE (#7514) ──────────────────
    #6277 closed the arm above for the rungs that CAN carry a draw, and named the
    one that cannot as out of scope: "the books rung … never carries one:
    ``Event.opening_*`` has no draw column, which is #1011 and is not this fix"
    (:func:`resolve_prematch_reading`). On a draw-priced sport that made the
    fall-through unconditional, so the books rung re-complemented every time and
    #6277's repair was inert on exactly the rung that answers in production.

    Measured on production 2026-09-20 14:00Z, ``GET /api/feed?mode=sports``, the
    eight finished soccer cards carrying a usable pair — the answering rung is
    the whole variable:

        kalshi (carries a draw)   5 cards   worst gap  1.3pt
        books  (no draw column)   3 cards   worst gap 26.0pt

    FC Seoul's own de-vigged pre-match price was .545 and the card rendered 81%;
    St. Pauli .455 rendered 70%; Gwangju .129 rendered 33%.

    So ``sport`` is the SECOND kind of evidence, used only where the first is
    structurally unavailable. It is not a wider licence: it is the existing,
    already-measured :func:`away_is_the_complement`, which is the same predicate
    the served duel is withheld on (#6238), so the payload and this row now agree
    about which away figures are real. Three properties make it safe:

    * It is checked AFTER the ``draw`` arm, so a rung that offers real evidence
      still wins and the five kalshi cards above never reach it.
    * ``away_is_the_complement`` answers False for every two-way sport by its own
      first line, so ``sport_prices_a_draw`` is tested explicitly here. Without
      that gate this arm would keep a stale MLB away and delete the coherence
      guard outright — the single most important line in this function.
    * An away that IS the complement still falls through and is rebuilt, which is
      a no-op on the value and keeps the withholding story of #6238 intact.

    ``sport`` absent (the default, and every caller that has not been wired) is
    byte-identical to the behaviour before this change.
    """
    home_prob = _as_probability(home)
    if home_prob is None:
        return None
    away_prob = _as_probability(away)
    if away_prob is None:
        return home_prob, round(1.0 - home_prob, 6)
    if abs(home_prob + away_prob - 1.0) <= _COMPLEMENT_TOLERANCE:
        return home_prob, away_prob
    draw_prob = _as_probability(draw)
    if (
        draw_prob is not None
        and abs(home_prob + away_prob + draw_prob - 1.0) <= _PARTITION_TOLERANCE
    ):
        return home_prob, away_prob
    # #7514 — the draw-priced arm, reached only when no draw was offered above.
    # The `sport_prices_a_draw` gate is load-bearing: `away_is_the_complement`
    # returns False for every two-way sport, so without it this would keep a
    # stale two-way away and the guard below would never run again.
    if sport_prices_a_draw(sport) and not away_is_the_complement(
        away_prob, home_prob, sport
    ):
        return home_prob, away_prob
    return home_prob, round(1.0 - home_prob, 6)


def _is_a_two_way_reading_of_a_three_way_game(
    home: Any, away: Any, draw: Any, sport: Any
) -> bool:
    """May this PREDICTION-MARKET rung not answer at all? (#9130)

    On a draw-priced sport a venue reading with no draw beside it, whose away is
    ``1 − home`` (or absent), is a two-way re-normalization of a three-way game.
    It proves nothing about either side:

    * written off the HOME leg, its away is P(away) + P(draw);
    * written off the AWAY leg, its HOME is ``1 − P(away)`` = P(home) + P(draw).

    The row cannot say which, so neither number is a pre-match price. Measured
    2026-09-27 on ``/events/15314006`` (LA Galaxy 3–2 Colorado): every Kalshi row
    before kickoff was the chart backfill reading Colorado's leg, so the hero
    printed "WON · 71% pregame" from 1 − 0.295 while Galaxy's own leg and the
    books both said ~45%. ``_pair`` cannot refuse it — the pair is coherent by
    construction — so the rung is skipped here and the ladder falls through to
    the next venue or the books, whose draw-priced arm #7514 already handles.

    A reading that carries a draw (every live Kalshi partition since #6277) never
    reaches the second clause, and ``away_is_the_complement`` answers False for
    every two-way sport by its own first line, so neither is touched.
    """
    if _as_probability(draw) is not None:
        return False
    home_prob = _as_probability(home)
    if home_prob is None:
        return False
    return away_is_the_complement(_as_probability(away), home_prob, sport)


def opening_consensus_has_frozen(
    commence_time: Any, status: Any, now: datetime
) -> bool:
    """May ``Event.opening_*`` be published as an OPENING yet? (#3922)

    ``Event.opening_home_probability`` is not the price a market opened at. It is
    the LAST PREGAME consensus: :func:`app.tasks.odds_polling._maybe_set_opening_odds`
    rewrites it on **every** poll while the fixture is still scheduled, and stops
    the moment it starts. The module docstring above already said so — "keeps
    refreshing until the game starts and then freezes" — but three read paths
    published it under the word "Opened" regardless.

    Before the freeze that word is false twice over:

    * **The number never happened.** Measured 2026-09-08 against the eight US
      Open quarter-finals, the column disagreed with the books' own first-sight
      median (earliest ``odds_snapshots`` capture, all 1-2 days pre-match) on
      **8 of 8** rows — mean 2.6pp, worst 5.1pp. The hub said "Frances Tiafoe
      opened at 58%" (he opened at 56.9%) over an event page saying Shelton
      "Opened 24%" (26.99%) with "−2% since open" against a true −5pp.
    * **The reference point moves while you watch.** Two reads of
      ``/api/tournaments/us-open`` five minutes apart: three of eight matches
      changed their *opening* (Sabalenka .6986→.7012, Andreeva .3783→.3819,
      Zheng .2934→.2909) while their current did not move at all. An arrow whose
      baseline drifts is not measuring the market.

    And what it measures instead is the one thing Alex's standing ruling forbids
    a surface to show. Before the freeze the column tracks the books' price NOW,
    so ``blend − opening`` is not movement over time at all: it is
    ``blend_now − books_now``, a source-disagreement gauge wearing a time label.
    Where the blend is books-only it is structurally 0.0 — Zverev printed a flat
    arrow on a day his book ran 84.7 → 85.9.

    So this returns True on exactly the states in which the writer has STOPPED
    writing, and it is written as the writer's own two guards inverted rather
    than as an independent reading of them. A reader that decided freshness for
    itself would be a second copy of that rule, free to drift; the whole defect
    here is a column meaning one thing to its writer and another to its readers.

    A missing ``commence_time`` and a missing ``status`` both leave the writer
    free to overwrite, so both answer False — an unknown is never promoted to a
    freeze, because the cost of publishing early is a false sentence and the
    cost of withholding is silence.

    The naive/aware coercion is not tidying. ``events.commence_time`` is
    ``DateTime(timezone=True)`` so production always compares aware to aware, but
    this predicate now sits on the event page's render path, where the bare
    ``<=`` the writer can afford inside a task's error handling would be a
    ``TypeError`` — i.e. a 500 on the hero — the first time any caller hands it a
    naive stamp. Naive is read as UTC, which is what the column stores.
    """
    if isinstance(commence_time, datetime):
        if commence_time.tzinfo is None:
            commence_time = commence_time.replace(tzinfo=timezone.utc)
        reference = now if now.tzinfo is not None else now.replace(tzinfo=timezone.utc)
        if commence_time <= reference:
            return True
    return bool(status) and status != "scheduled"


def prematch_source_rank(source: Any) -> int:
    """Where this source sits on the ladder — lower wins.

    Exported so a surface that has to CHOOSE between two readings it already
    holds (the tennis hub picks between the venues pinned on one matchup) sorts
    by the same order the feed resolves by, rather than growing a second copy of
    Alex's ordering that can drift out of step with this one. An unknown source
    sorts last: it is still usable, it is simply never preferred over a rung we
    have a reason to trust.
    """
    try:
        return PREMATCH_LADDER.index(source)
    except ValueError:
        return len(PREMATCH_LADDER)


def is_prediction_market_source(source: Any) -> bool:
    """Is this rung a prediction market — i.e. does the number need no caveat?"""
    return source in PREDICTION_MARKET_SOURCES


def needs_source_label(source: Any) -> bool:
    """Must the card say where this number came from?

    Alex: *"labelled when not a prediction market."* A prediction-market opening
    is the thing this product is about and reads as itself; anything else is a
    different claim wearing the same shape, so it carries its source.
    """
    return source is not None and not is_prediction_market_source(source)


def resolve_prematch_reading(
    *,
    by_source: Optional[Mapping[str, Any]] = None,
    books_home: Any = None,
    books_away: Any = None,
    ladder: Iterable[str] = PREMATCH_LADDER,
    sport: Any = None,
) -> Optional[dict]:
    """The first rung of the ladder that has a coherent pre-match pair.

    ``by_source`` maps a prediction-market source id to ``(home, away)`` — the
    last snapshot at or before ``commence_time`` for that source — or, on a
    three-way game, to ``(home, away, draw)`` (#6277). The third member is
    optional at every call site and is only ever the EVIDENCE that the first two
    are a genuine sub-unit pair; see :func:`_pair`. The books rung is passed
    separately because it lives on the event row rather than in the snapshot
    table, and it never carries one: ``Event.opening_*`` has no draw column,
    which is #1011.

    ``sport`` is how the books rung is answered anyway (#7514). Because it can
    never carry a draw, the sentence above used to end "and is not this fix", and
    the consequence was that #6277's repair never reached the rung that actually
    answers in production: all three wrong finished soccer cards measured
    2026-09-20 14:00Z were ``source: "books"``, each overstating the away side by
    20–26 points, while all five ``kalshi`` cards in the same read were correct
    inside 1.3pt. The sport is evidence of last resort, applied only where the
    draw is structurally unavailable; :func:`_pair` carries the argument and the
    gate that keeps every two-way sport untouched. Absent, every caller behaves
    exactly as it did before.

    Returns ``{"home_probability", "away_probability", "source"}``, or ``None``
    when no rung has a reading. ``None`` means "we hold nothing", which is the
    only case where a settled card is allowed to print no pre-match number.
    """
    readings = dict(by_source or {})
    for source in ladder:
        if source == BOOKS_SOURCE:
            pair = _pair(books_home, books_away, sport=sport)
        else:
            served = readings.get(source)
            if served is None:
                continue
            if isinstance(served, Mapping):
                home, away, draw = (
                    served.get("home"),
                    served.get("away"),
                    served.get("draw"),
                )
            else:
                # Padded to THREE so a two-element tuple — every caller before
                # #6277, and every two-way source after it — unpacks unchanged.
                home, away, draw = (list(served) + [None, None, None])[:3]
            if _is_a_two_way_reading_of_a_three_way_game(home, away, draw, sport):
                continue
            pair = _pair(home, away, draw, sport=sport)
        if pair is None:
            continue
        return {
            "home_probability": pair[0],
            "away_probability": pair[1],
            "source": source,
        }
    return None


# ── READING IT OUT OF THE SNAPSHOT TABLE (LAT-P222) ──────────────────────────
#
# The statement below is the ux/1036 read, and for its first two days it was
# written the obvious way: join `win_prob_snapshots` back to `events` and
# compare `s.captured_at <= e.commence_time`. That comparison is the reason a
# cold Discover build spent most of a second here.
#
# Postgres cannot evaluate a bound it has to fetch. With `commence_time` living
# on the other table, the planner drives from the SNAPSHOT side and probes
# `events_pkey` once per candidate snapshot row. Measured on a production dyno
# 2026-09-04 with the app's own binds (`ARTIFACT-LAT-P222-prematch-mechanism-*`):
# **loops=24528, 753,087 buffer hits, 53 rows returned** — 99.2% of those hits
# are the inner probe. The stage profile put this ONE query at **86.0% of the
# whole `events` stage** (935.9 ms of 1,088.2 ms).
#
# The fix is not an index and not a rewrite of the ranking: it is noticing that
# `_score_events` already HOLDS every cutoff it is asking the database to go and
# find. `commence_time` is on each hydrated `Event` ten lines above the call. So
# the caller supplies the cutoffs and the statement stops reading `events` at
# all — `unnest` of two aligned arrays, one `DISTINCT ON` per event through
# `ix_winprob_event_source`. Proven on production over the same id list, in one
# probe, four reps each: **set-identical 53 rows** at 98.8 ms / 19,747 buffers
# against the join's 878.8–1,278.5 ms (`ARTIFACT-LAT-P222-prematch-ceiling-*`).
#
# 🔴 The semantics that must survive any future edit here, because none of them
# is visible in a latency number:
#
#   * "the LAST reading at or before kickoff, per source" — `DISTINCT ON
#     (s.source)` ordered `s.source, s.captured_at DESC` inside the lateral is
#     the same selection the outer `DISTINCT ON (s.event_id, s.source)` made,
#     one event at a time.
#   * a settled market prices the winner at ~100%, and the same table holds the
#     in-play and post-settlement readings. Drop the cutoff and every finished
#     card renders its own result back as a forecast. That is the defect this
#     bound exists to prevent and it is why the gate for it executes rows
#     (`tests/integration/test_prematch_prior_lateral_equivalence_pg.py`).
#   * the two arrays are POSITIONAL. `unnest(a, b)` pairs by index, so a filter
#     applied to one and not the other silently attributes one game's kickoff to
#     another game's prices — a wrong answer no latency measurement would
#     notice. They are therefore built by ONE pass, in
#     `settled_prematch_cutoffs`, and never assembled at the call site.
#   * `draw_probability` (#6277) rides the SAME row and adds no join, no filter
#     and no ordering term: it is a column of the row already being selected.
#     It is deliberately NOT in the `IS NOT NULL` guard — it is NULL on every
#     two-way source and on every row written before that fix, and requiring it
#     would silently empty this read of almost everything it serves.
PREMATCH_PRIOR_SQL = """
    SELECT x.event_id, x.source,
           x.home_win_probability, x.away_win_probability, x.draw_probability
    FROM unnest(cast(:ids as integer[]), cast(:cutoffs as timestamptz[]))
         AS t(event_id, cutoff)
    CROSS JOIN LATERAL (
        SELECT DISTINCT ON (s.source)
               s.event_id, s.source,
               s.home_win_probability, s.away_win_probability,
               s.draw_probability
        FROM win_prob_snapshots s
        WHERE s.event_id = t.event_id
          AND s.source = ANY(:sources)
          AND s.home_win_probability IS NOT NULL
          AND s.captured_at <= t.cutoff
        ORDER BY s.source, s.captured_at DESC
    ) x
"""

# ── #10090: ONE INDEX SEEK PER (GAME, SOURCE) INSTEAD OF A WALK ──────────────
#
# Measured on production 2026-10-31 19:16–19:51Z (pg_stat_statements diff): the
# statement above still ran 71 times at a MEAN OF 9.5 s on a cache miss, 8.1% of
# every block the database read. The lateral's `DISTINCT ON (s.source)` has to
# read EVERY eligible snapshot of the game for every requested source, and check
# each one on the heap for `home_win_probability IS NOT NULL`, before it can
# keep the newest. A live game holds thousands of snapshots.
#
# This form asks the same question one source at a time, `ORDER BY captured_at
# DESC LIMIT 1`, so Postgres seeks `ix_winprob_event_source_captured
# (event_id, source, captured_at)` backward from the cutoff and stops at the
# first row with a home probability. Local PG17, 40 settled games × 3,000
# snapshots per source with that index: 84,452 buffers / 85 ms → 422 buffers /
# 0.47 ms, same 80 rows (about 5 buffers per game and source, against ~1,056).
#
# Same rows, held by `tests/integration/test_prematch_prior_lateral_equivalence_pg.py`:
#
#   * `:sources` is membership, as `ANY` was — NULLs dropped, duplicates
#     collapsed by `DISTINCT`, so a duplicated source cannot double a row;
#   * `home_win_probability IS NOT NULL` and the inclusive `captured_at <=
#     cutoff` are INSIDE the top-1, so a NULL-home row newer than the last real
#     reading is skipped, not returned as "no reading", and nothing after kickoff
#     can be the answer;
#   * home, away and draw come from the ONE row, as before;
#   * output order is position, then source — the order the old plan produced
#     and the order `fetch_prematch_prior_rows` re-emits per game.
#
# TIES: two rows for one game and source with the same `captured_at` are a real
# shape (one transaction's writes share `now()`). `DISTINCT ON` above keeps an
# arbitrary one of them. This form says which: `s.id DESC`, the later-inserted
# row wins. The old statement is left byte-for-byte as it runs today, because it
# is the rollback, so the two forms can disagree ONLY on such a tie.
#
# `PREMATCH_PRIOR_TOP1=0` executes the statement above instead, unchanged. The
# cache keys still digest `PREMATCH_PRIOR_SQL`: they name the answer, which both
# forms give, so flipping the switch does not empty the shared cache.
PREMATCH_PRIOR_TOP1_SQL = """
    SELECT x.event_id, x.source,
           x.home_win_probability, x.away_win_probability, x.draw_probability
    FROM unnest(cast(:ids as integer[]), cast(:cutoffs as timestamptz[]))
         WITH ORDINALITY AS t(event_id, cutoff, ord)
    CROSS JOIN (
        SELECT DISTINCT u.src
        FROM unnest(cast(:sources as text[])) AS u(src)
        WHERE u.src IS NOT NULL
    ) w
    CROSS JOIN LATERAL (
        SELECT s.event_id, s.source,
               s.home_win_probability, s.away_win_probability,
               s.draw_probability
        FROM win_prob_snapshots s
        WHERE s.event_id = t.event_id
          AND s.source = w.src
          AND s.home_win_probability IS NOT NULL
          AND s.captured_at <= t.cutoff
        ORDER BY s.captured_at DESC, s.id DESC
        LIMIT 1
    ) x
    ORDER BY t.ord, x.source
"""

PREMATCH_PRIOR_TOP1_ENV = "PREMATCH_PRIOR_TOP1"


def prematch_prior_top1_enabled() -> bool:
    """The rollback to the `DISTINCT ON` walk without a deploy. Defaults ON."""
    raw = os.environ.get(PREMATCH_PRIOR_TOP1_ENV, "1").strip().lower()
    return raw not in {"0", "false", "no", "off"}


def prematch_prior_sql() -> str:
    """The statement a pre-match read executes now: top-1, or the walk when off."""
    if prematch_prior_top1_enabled():
        return PREMATCH_PRIOR_TOP1_SQL
    return PREMATCH_PRIOR_SQL


def prematch_row_to_reading(row: Any) -> tuple:
    """One ``PREMATCH_PRIOR_SQL`` row as the ``(home, away, draw)`` the ladder eats.

    Lives here, beside the statement that produces it, because it is the SHAPE
    CONTRACT between them and a shape contract with two authors drifts. It was
    written inline in `_score_events`, which made it the one link in this chain
    no unit test could reach: a fix that stored an honest draw and then dropped
    it on the way out of the cursor would pass every test in the suite and change
    nothing on the card. That is the same inertness `_pair` caused (#6277), one
    gate further along, and this is the guard for it.

    Floats, not Decimals: the column is ``Numeric(5,4)`` and psycopg hands back
    ``Decimal``, which `_as_probability` would take but which compares badly with
    the float arithmetic every consumer downstream does.
    """
    return (
        float(row.home_win_probability),
        (
            float(row.away_win_probability)
            if row.away_win_probability is not None
            else None
        ),
        # The third member of a three-way game, and the only thing that stops
        # `_pair` rebuilding the away slot as `1 - home`. NULL on every two-way
        # source, which is every source but a soccer or cricket game winner.
        float(row.draw_probability) if row.draw_probability is not None else None,
    )


#: The statuses whose cards print a pre-match reading. A scheduled or live card
#: does not, so its snapshots are never fetched. Held here rather than inlined
#: at the call site so the gate and the caller cannot disagree about what
#: "settled" means.
SETTLED_STATUSES: frozenset[str] = frozenset({"completed", "closed"})


def settled_prematch_cutoffs(
    events: Iterable[Any],
) -> tuple[list[int], list[datetime]]:
    """The `(ids, cutoffs)` binds for :data:`PREMATCH_PRIOR_SQL`.

    ONE pass over the hydrated events, appending to both lists together, so the
    two arrays are index-aligned *by construction* rather than by two
    comprehensions agreeing. `unnest(a, b)` pairs positionally: a future edit
    that filters one list and not the other would hand one game's kickoff time
    to another game's prices, and the response would still be well-formed.

    Two rows are dropped, both deliberately:

    * anything not settled — those cards print no pre-match reading;
    * anything with no ``commence_time``. The join this replaced compared
      ``s.captured_at <= e.commence_time``, and ``x <= NULL`` is NULL, so such
      an event contributed no rows there either. Excluding it here keeps that
      exactly, and does it where a reader can see it instead of leaving it to
      three-valued logic to agree by accident.
    """
    ids: list[int] = []
    cutoffs: list[datetime] = []
    for event in events:
        if getattr(event, "status", None) not in SETTLED_STATUSES:
            continue
        cutoff = getattr(event, "commence_time", None)
        if cutoff is None:
            continue
        ids.append(event.id)
        cutoffs.append(cutoff)
    return ids, cutoffs


def prematch_prior_binds(
    events: Iterable[Any],
    sources: Sequence[str] = PREDICTION_MARKET_SOURCES,
) -> Optional[dict]:
    """Every bind :data:`PREMATCH_PRIOR_SQL` takes, or ``None`` to skip the read.

    ``None`` when no candidate is settled — the read is not merely empty then,
    it is unnecessary, and a round trip that can only return zero rows is one
    the cold build should not pay for.
    """
    ids, cutoffs = settled_prematch_cutoffs(events)
    if not ids:
        return None
    return {"ids": ids, "cutoffs": cutoffs, "sources": list(sources)}


# ── #1480: ONE ANSWER FOR EVERY READER OF THE SAME SETTLED SLATE ──────────────
#
# The read above depends only on its binds, and `prematch_prior_binds` builds
# them from the candidate events alone — no reader, no clock. So `/api/feed`
# reuses one answer per bind set through `principal_independent_cache` instead
# of each Sports/Discover miss re-reading it.

#: The shared-artifact namespace the answer is reused under.
PREMATCH_PRIOR_SHARED_NAMESPACE = "event_prematch_prior"


def prematch_prior_share_key(binds: Mapping[str, Any]) -> tuple:
    """The shared-cache key for one :data:`PREMATCH_PRIOR_SQL` bind set.

    Built from the binds the statement receives, so the key and the read cannot
    disagree. Each cutoff is in the key next to its id: a rescheduled kickoff
    moves the cutoff, and a reading cut at the old kickoff must not be reused.
    The statement's own digest rotates the key if the SQL changes; ``"v1"`` is
    the answer's shape.
    """
    from app.utils.principal_independent_cache import digest_of

    return (
        "v1",
        digest_of([PREMATCH_PRIOR_SQL]),
        tuple(sorted(binds["sources"])),
        digest_of(
            f"{event_id}|{cutoff.isoformat()}"
            for event_id, cutoff in zip(binds["ids"], binds["cutoffs"])
        ),
    )


# ── #10090: A KICKED-OFF GAME'S PRE-MATCH READING DOES NOT CHANGE ────────────
#
# Measured on production 2026-10-31 16:41–17:24Z (pg_stat_statements diff): this
# statement ran 117 times for 1,088 s of execution and 899,585 blocks read —
# 8.9% of every block the database read in that window, on a disk-saturated
# Saturday, while Alex's signed-in feed requests were hitting the router's 25 s
# limit. Every bind it is given is a SETTLED game's kickoff, and the answer for
# a kickoff that has passed is the last row at or before it: the table can only
# add to it by a late write stamped before kickoff. So each game's rows are kept
# per `(event_id, cutoff, sources)` for a bounded TTL — long enough that the
# feed, the event page, the hub and the team page stop re-reading the same
# finished games, short enough that a late backfill row still lands — and only
# the games not held are sent to the database.
#
# What it never does, each tested:
#
#   * hold a cutoff that has not passed (a rescheduled or future kickoff reads
#     every time);
#   * hold anything but the statement's own output rows, keyed by exactly the
#     inputs that produced them — the 🔴 semantics above are the statement's,
#     and the statement is unchanged;
#   * split the positional arrays: the misses are re-bound in ONE pass over the
#     caller's aligned pair, and a bind set that repeats an event id with two
#     different cutoffs, or whose arrays differ in length, bypasses the cache
#     and reads exactly as before.
#
# Process-local first: an L1 hit costs no round trip.
#
# ── WHY THERE IS A SECOND TIER (#10090, 2026-10-31 afternoon) ────────────────
#
# Live from 17:51Z, the process-local cache cut NOTHING: 18:15–19:16Z the
# statement ran 3.4 calls/min at ~10.9k blocks a call, against 2.7 calls/min at
# ~7.8k before it. The callers are not one warm process. `web` runs
# `WEB_CONCURRENCY=2`, and the feed is also built by Celery prefork children
# (`prewarm_live_feed_shapes` every 30 s on `realtime`, the hourly category
# warmer and the tag-count measurer on `background`) — four and two children,
# each with its own empty dict, each recycled by `--max-memory-per-child` after
# a feed build. A game held in one process was read again by the next. So the
# held rows also go to Redis, one key per `(event_id, cutoff, sources)`, read
# with ONE `MGET` only for the positions the process missed, under a hard 250 ms
# deadline. The sync client runs in a thread on purpose: a Celery task runs on
# a fresh event loop each time, and a process-shared asyncio client is bound to
# the first one. Every L2 failure — a stall, a connection error, a malformed or
# non-matching envelope — is a miss, never an error to the page.
#
# A repeated event id used to bypass both tiers. Positions that repeat the same
# `(id, cutoff)` now read once and each position gets the rows the statement
# would have given it; only an id repeated with two DIFFERENT cutoffs still
# reads exactly as before (its rows carry no cutoff, so they cannot be told
# apart).
#
# Once a minute each process logs one `prematch reading cache:` line — calls,
# L1/L2 hits, misses, bypasses by reason, keys held — so the hit rate is read
# from production rather than inferred from `pg_stat_statements`.
#
# `PREMATCH_READING_CACHE=0` turns both tiers off; every call then reads exactly
# as before this existed. `PREMATCH_READING_CACHE_SHARED=0` turns off the Redis
# tier alone.

PREMATCH_READING_CACHE_ENV = "PREMATCH_READING_CACHE"
PREMATCH_READING_CACHE_SHARED_ENV = "PREMATCH_READING_CACHE_SHARED"
PREMATCH_READING_CACHE_TTL_S = 600.0
PREMATCH_READING_CACHE_MAX_KEYS = 20_000
PREMATCH_READING_CACHE_L2_DEADLINE_S = 0.25
PREMATCH_READING_CACHE_STATS_INTERVAL_S = 60.0
_L2_PREFIX = "bl:prematch_prior:v1"


class PrematchPriorRow(NamedTuple):
    """One :data:`PREMATCH_PRIOR_SQL` row, held as plain data (gotcha #6)."""

    event_id: int
    source: str
    home_win_probability: Any
    away_win_probability: Any
    draw_probability: Any


_prematch_cache: "OrderedDict[tuple, tuple[float, tuple[PrematchPriorRow, ...]]]" = (
    OrderedDict()
)
_prematch_cache_lock = threading.Lock()

_STAT_NAMES = (
    "calls",
    "db_reads",
    "positions",
    "l1_hits",
    "l2_hits",
    "misses",
    "not_kicked_off",
    "deduped",
    "bypass_off",
    "bypass_misaligned",
    "bypass_conflicting_cutoff",
    "l2_errors",
    "l2_published",
)
_stats: dict[str, int] = dict.fromkeys(_STAT_NAMES, 0)
_stats_since: list[Optional[float]] = [None]


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _monotonic() -> float:
    return time.monotonic()


def _wall() -> float:
    return time.time()


def _reset_prematch_cache_for_tests() -> None:
    with _prematch_cache_lock:
        _prematch_cache.clear()
        for name in _STAT_NAMES:
            _stats[name] = 0
        _stats_since[0] = None


def prematch_reading_cache_enabled() -> bool:
    """The rollback without a deploy. Defaults ON."""
    raw = os.environ.get(PREMATCH_READING_CACHE_ENV, "1").strip().lower()
    return raw not in {"0", "false", "no", "off"}


def prematch_reading_cache_shared_enabled() -> bool:
    """The Redis tier's own rollback. Defaults ON."""
    raw = os.environ.get(PREMATCH_READING_CACHE_SHARED_ENV, "1").strip().lower()
    return raw not in {"0", "false", "no", "off"}


def _as_utc(cutoff: datetime) -> datetime:
    # Aware datetimes for one instant already compare and hash equal whatever
    # their offset; only a naive one needs a zone to be compared at all.
    if cutoff.tzinfo is None:
        return cutoff.replace(tzinfo=timezone.utc)
    return cutoff


def _prematch_cache_key(
    event_id: Any, cutoff: Any, sources_key: tuple, now: datetime
) -> Optional[tuple]:
    """The key one position is held under, or ``None`` if it must be read."""
    if not isinstance(cutoff, datetime):
        return None
    cutoff = _as_utc(cutoff)
    if cutoff >= now:
        return None
    return (event_id, cutoff, sources_key)


def _plain_row(row: Any) -> PrematchPriorRow:
    return PrematchPriorRow(
        row.event_id,
        row.source,
        row.home_win_probability,
        row.away_win_probability,
        row.draw_probability,
    )


# ── the Redis tier ──────────────────────────────────────────────────────────

_SQL_DIGEST = hashlib.sha256(PREMATCH_PRIOR_SQL.encode()).hexdigest()[:12]


def _l2_key(key: tuple) -> str:
    event_id, cutoff, sources_key = key
    stamp = cutoff.astimezone(timezone.utc).isoformat()
    return f"{_L2_PREFIX}:{_SQL_DIGEST}:{','.join(sources_key)}:{event_id}:{stamp}"


def _encode_number(value: Any) -> Any:
    # Exactly invertible or refused: a Decimal comes back a Decimal, a float a
    # float. Anything else raises, and the key is simply not published.
    if value is None:
        return None
    if isinstance(value, Decimal):
        return ["D", str(value)]
    if isinstance(value, float):
        return ["F", repr(value)]
    raise TypeError(f"unpublishable probability {type(value).__name__}")


def _decode_number(value: Any) -> Any:
    if value is None:
        return None
    tag, text = value
    if tag == "D":
        return Decimal(text)
    if tag == "F":
        return float(text)
    raise ValueError(f"unknown tag {tag!r}")


def _encode_entry(key: tuple, rows: tuple, stored_wall: float) -> str:
    return json.dumps(
        {
            "k": _l2_key(key),
            "w": stored_wall,
            "r": [
                [
                    r.source,
                    _encode_number(r.home_win_probability),
                    _encode_number(r.away_win_probability),
                    _encode_number(r.draw_probability),
                ]
                for r in rows
            ],
        },
        separators=(",", ":"),
    )


def _decode_entry(
    key: tuple, blob: Any, now_wall: float
) -> Optional[tuple[float, tuple[PrematchPriorRow, ...]]]:
    """``(age_s, rows)`` or ``None``: anything unexpected is a miss."""
    try:
        if isinstance(blob, bytes):
            blob = blob.decode()
        doc = json.loads(blob)
        if doc["k"] != _l2_key(key):
            return None
        age = now_wall - float(doc["w"])
        if not 0 <= age < PREMATCH_READING_CACHE_TTL_S:
            return None
        event_id = key[0]
        rows = tuple(
            PrematchPriorRow(
                event_id,
                str(source),
                _decode_number(home),
                _decode_number(away),
                _decode_number(draw),
            )
            for source, home, away, draw in doc["r"]
        )
        return age, rows
    except Exception:  # noqa: BLE001 — a bad envelope is a miss, never the page
        return None


def _shared_client() -> Any:
    """The process's sync Redis client (the latency middleware's signature).

    Per-pid cached by ``get_redis_client``, so a prefork child never inherits
    its parent's sockets and no new pool parameter set is added to the plan's
    connection budget.
    """
    from app.tasks.redis_state import get_redis_client

    return get_redis_client(socket_timeout=0.5, fast_fail=True)


async def _l2_call(fn: Any) -> Any:
    """Run one sync Redis op in a thread under the hard deadline; raise on failure."""
    return await asyncio.wait_for(
        asyncio.to_thread(fn), timeout=PREMATCH_READING_CACHE_L2_DEADLINE_S
    )


async def _l2_read(keys: list[tuple]) -> Optional[list]:
    """The raw blobs for ``keys`` in order, or ``None`` if Redis did not answer."""
    try:
        client = _shared_client()
        redis_keys = [_l2_key(k) for k in keys]
        blobs = await _l2_call(lambda: client.mget(redis_keys))
        if not isinstance(blobs, (list, tuple)) or len(blobs) != len(keys):
            return None
        return list(blobs)
    except asyncio.CancelledError:
        raise
    except Exception:  # noqa: BLE001 — the read falls back to the database
        logger.debug("prematch reading cache: L2 read failed", exc_info=True)
        return None


async def _l2_publish(entries: list[tuple[tuple, tuple]]) -> int:
    """Publish ``(key, rows)`` pairs; the count published (0 on any failure)."""
    stored_wall = _wall()
    blobs = []
    for key, rows in entries:
        try:
            blobs.append((_l2_key(key), _encode_entry(key, rows, stored_wall)))
        except Exception:  # noqa: BLE001 — an unpublishable key is just not shared
            continue
    if not blobs:
        return 0
    expire_s = int(PREMATCH_READING_CACHE_TTL_S) + 1

    def _write() -> None:
        pipe = client.pipeline(transaction=False)
        for redis_key, blob in blobs:
            pipe.set(redis_key, blob, ex=expire_s)
        pipe.execute()

    try:
        client = _shared_client()
        await _l2_call(_write)
        return len(blobs)
    except asyncio.CancelledError:
        raise
    except Exception:  # noqa: BLE001 — not sharing costs a later read, nothing more
        logger.debug("prematch reading cache: L2 publish failed", exc_info=True)
        return -1


# ── the once-a-minute line ──────────────────────────────────────────────────


def _record(counts: Mapping[str, int]) -> Optional[str]:
    """Add one call's counts; return the stats line if one is due, and reset."""
    now = _monotonic()
    with _prematch_cache_lock:
        for name, value in counts.items():
            _stats[name] += value
        if _stats_since[0] is None:
            _stats_since[0] = now
            return None
        interval = now - _stats_since[0]
        if interval < PREMATCH_READING_CACHE_STATS_INTERVAL_S:
            return None
        snapshot = dict(_stats)
        keys_held = len(_prematch_cache)
        for name in _STAT_NAMES:
            _stats[name] = 0
        _stats_since[0] = now
    looked_up = snapshot["l1_hits"] + snapshot["l2_hits"] + snapshot["misses"]
    hit_pct = (
        100.0 * (snapshot["l1_hits"] + snapshot["l2_hits"]) / looked_up
        if looked_up
        else 0.0
    )
    fields = " ".join(f"{name}={snapshot[name]}" for name in _STAT_NAMES)
    return (
        f"prematch reading cache: dyno={os.environ.get('DYNO', '-')} "
        f"pid={os.getpid()} interval_s={interval:.0f} {fields} "
        f"keys_held={keys_held} hit_pct={hit_pct:.1f}"
    )


def _finish(counts: Mapping[str, int]) -> None:
    line = _record(counts)
    if line is not None:
        logger.info(line)


async def fetch_prematch_prior_rows(db: Any, binds: Mapping[str, Any]) -> list:
    """Every :data:`PREMATCH_PRIOR_SQL` row for one bind set, kicked-off games cached.

    The one place the statement executes, so every surface that prints a
    settled game's pre-match reading reads it through the same cache. Off, it is
    exactly the read each caller ran inline. Nothing is caught from the database.
    """
    from sqlalchemy import text

    ids = list(binds["ids"])
    cutoffs = list(binds["cutoffs"])
    counts: dict[str, int] = {"calls": 1}

    async def _read_as_before(reason: str) -> list:
        counts[reason] = 1
        counts["db_reads"] = 1
        rows = list((await db.execute(text(prematch_prior_sql()), dict(binds))).all())
        _finish(counts)
        return rows

    if not prematch_reading_cache_enabled():
        return await _read_as_before("bypass_off")
    if len(ids) != len(cutoffs):
        return await _read_as_before("bypass_misaligned")

    # One cutoff per id. A position that repeats its id's (id, cutoff) is read
    # once; an id with two different cutoffs cannot be attributed and reads as
    # before.
    cutoff_of: dict[Any, Any] = {}
    seen: dict[Any, Any] = {}
    for event_id, cutoff in zip(ids, cutoffs):
        same = _as_utc(cutoff) if isinstance(cutoff, datetime) else cutoff
        if event_id in seen:
            if seen[event_id] != same:
                return await _read_as_before("bypass_conflicting_cutoff")
            continue
        seen[event_id] = same
        cutoff_of[event_id] = cutoff
    unique_ids = list(cutoff_of)
    counts["positions"] = len(ids)
    counts["deduped"] = len(ids) - len(unique_ids)

    sources_key = tuple(sorted(set(binds["sources"])))
    now = _utcnow()
    keys = {
        event_id: _prematch_cache_key(event_id, cutoff_of[event_id], sources_key, now)
        for event_id in unique_ids
    }
    counts["not_kicked_off"] = sum(1 for k in keys.values() if k is None)

    held: dict[Any, tuple[PrematchPriorRow, ...]] = {}
    clock = _monotonic()
    with _prematch_cache_lock:
        for event_id in unique_ids:
            key = keys[event_id]
            if key is None:
                continue
            entry = _prematch_cache.get(key)
            if entry is None:
                continue
            if entry[0] <= clock:
                del _prematch_cache[key]
                continue
            _prematch_cache.move_to_end(key)
            held[event_id] = entry[1]
    counts["l1_hits"] = len(held)

    shared = prematch_reading_cache_shared_enabled()
    want = [e for e in unique_ids if keys[e] is not None and e not in held]
    if shared and want:
        blobs = await _l2_read([keys[e] for e in want])
        if blobs is None:
            counts["l2_errors"] = 1
        else:
            now_wall = _wall()
            clock = _monotonic()
            with _prematch_cache_lock:
                for event_id, blob in zip(want, blobs):
                    if blob is None:
                        continue
                    decoded = _decode_entry(keys[event_id], blob, now_wall)
                    if decoded is None:
                        continue
                    age, rows = decoded
                    held[event_id] = rows
                    _prematch_cache[keys[event_id]] = (
                        clock + PREMATCH_READING_CACHE_TTL_S - age,
                        rows,
                    )
                    _prematch_cache.move_to_end(keys[event_id])
                    counts["l2_hits"] = counts.get("l2_hits", 0) + 1
                while len(_prematch_cache) > PREMATCH_READING_CACHE_MAX_KEYS:
                    _prematch_cache.popitem(last=False)

    # ONE pass over the caller's aligned pair, so the re-bound arrays stay
    # index-aligned by construction (the 🔴 positional rule above).
    miss_ids = [e for e in unique_ids if e not in held]
    miss_cutoffs = [cutoff_of[e] for e in miss_ids]
    counts["misses"] = sum(1 for e in miss_ids if keys[e] is not None)

    fetched: dict[Any, list[PrematchPriorRow]] = {}
    if miss_ids:
        counts["db_reads"] = 1
        miss_binds = {**dict(binds), "ids": miss_ids, "cutoffs": miss_cutoffs}
        for row in (await db.execute(text(prematch_prior_sql()), miss_binds)).all():
            fetched.setdefault(row.event_id, []).append(_plain_row(row))
        expires = _monotonic() + PREMATCH_READING_CACHE_TTL_S
        to_publish: list[tuple[tuple, tuple]] = []
        with _prematch_cache_lock:
            for event_id in miss_ids:
                key = keys[event_id]
                if key is None:
                    continue
                rows = tuple(fetched.get(event_id, ()))
                _prematch_cache[key] = (expires, rows)
                _prematch_cache.move_to_end(key)
                to_publish.append((key, rows))
            while len(_prematch_cache) > PREMATCH_READING_CACHE_MAX_KEYS:
                _prematch_cache.popitem(last=False)
        if shared and to_publish:
            published = await _l2_publish(to_publish)
            if published < 0:
                counts["l2_errors"] = counts.get("l2_errors", 0) + 1
            else:
                counts["l2_published"] = published

    rows: list = []
    for event_id in ids:
        if event_id in held:
            rows.extend(held[event_id])
        else:
            rows.extend(fetched.get(event_id, ()))
    for event_id, leftover in fetched.items():
        if event_id not in cutoff_of:
            rows.extend(leftover)
    _finish(counts)
    return rows


async def read_prematch_priors(
    db: Any, binds: Mapping[str, Any]
) -> dict[int, dict[str, tuple]]:
    """``{event_id: {source: (home, away, draw)}}`` for one bind set.

    The read `_score_events` ran inline, moved here unchanged so the direct
    path and the shared builder are the same code. Nothing is caught.
    """
    prematch_by_event: dict[int, dict[str, tuple]] = {}
    for row in await fetch_prematch_prior_rows(db, binds):
        # #6277 — the row's shape is defined once, beside the statement that
        # produced it, so a member cannot be dropped here without a test
        # noticing.
        prematch_by_event.setdefault(row.event_id, {})[
            row.source
        ] = prematch_row_to_reading(row)
    return prematch_by_event
