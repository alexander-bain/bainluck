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

from datetime import datetime
from typing import Any, Iterable, Mapping, Optional, Sequence

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


def _pair(home: Any, away: Any) -> Optional[tuple[float, float]]:
    """``(home, away)`` as a coherent pair, anchored on home."""
    home_prob = _as_probability(home)
    if home_prob is None:
        return None
    away_prob = _as_probability(away)
    if away_prob is None or abs(home_prob + away_prob - 1.0) > _COMPLEMENT_TOLERANCE:
        away_prob = round(1.0 - home_prob, 6)
    return home_prob, away_prob


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
) -> Optional[dict]:
    """The first rung of the ladder that has a coherent pre-match pair.

    ``by_source`` maps a prediction-market source id to ``(home, away)`` — the
    last snapshot at or before ``commence_time`` for that source. The books rung
    is passed separately because it lives on the event row rather than in the
    snapshot table.

    Returns ``{"home_probability", "away_probability", "source"}``, or ``None``
    when no rung has a reading. ``None`` means "we hold nothing", which is the
    only case where a settled card is allowed to print no pre-match number.
    """
    readings = dict(by_source or {})
    for source in ladder:
        if source == BOOKS_SOURCE:
            pair = _pair(books_home, books_away)
        else:
            served = readings.get(source)
            if served is None:
                continue
            if isinstance(served, Mapping):
                pair = _pair(served.get("home"), served.get("away"))
            else:
                home, away = (list(served) + [None, None])[:2]
                pair = _pair(home, away)
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
PREMATCH_PRIOR_SQL = """
    SELECT x.event_id, x.source,
           x.home_win_probability, x.away_win_probability
    FROM unnest(cast(:ids as integer[]), cast(:cutoffs as timestamptz[]))
         AS t(event_id, cutoff)
    CROSS JOIN LATERAL (
        SELECT DISTINCT ON (s.source)
               s.event_id, s.source,
               s.home_win_probability, s.away_win_probability
        FROM win_prob_snapshots s
        WHERE s.event_id = t.event_id
          AND s.source = ANY(:sources)
          AND s.home_win_probability IS NOT NULL
          AND s.captured_at <= t.cutoff
        ORDER BY s.source, s.captured_at DESC
    ) x
"""

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
