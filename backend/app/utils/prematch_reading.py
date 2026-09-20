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

from datetime import datetime, timezone
from typing import Any, Iterable, Mapping, Optional, Sequence

# #7514 — the same two predicates the served duel is withheld on (#6238), so the
# payload and the pre-match row cannot disagree about which away figures are a
# real price. `draw_priced_winner` imports only `graded_card`, which is stdlib
# only, so this adds no cycle.
from app.utils.draw_priced_winner import away_is_the_complement, sport_prices_a_draw

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
                pair = _pair(
                    served.get("home"),
                    served.get("away"),
                    served.get("draw"),
                    sport=sport,
                )
            else:
                # Padded to THREE so a two-element tuple — every caller before
                # #6277, and every two-way source after it — unpacks unchanged.
                home, away, draw = (list(served) + [None, None, None])[:3]
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
