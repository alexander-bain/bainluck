"""Candidate selection for the Discover / Sports feed's game-event pool.

WHY THIS EXISTS (#2065)
-----------------------
``_score_events`` selected its candidates with ONE ``ORDER BY`` and ONE
``LIMIT 500`` spanning all three status tiers.  The ordering (live → recently
finished → scheduled, then ``commence_time DESC``) was added so that thousands
of scheduled events could not crowd out live ones.  It does the opposite at full
strength: **any single tier that overflows the cap starves the other two
entirely, and any single sport that overflows it starves every other sport.**

Measured on production ``a13239f1``, 2026-08-21, before a line of this was
written:

=========================================================  ==========
events matching the window predicate                           25,610
…carrying any ``win_probability_sources``                         170
rows admitted by the ``LIMIT 500`` cap                            500
…that are ``live``                                         500 (100%)
…that are ``esports``                                             488
…carrying any probability source                                    8
scheduled events admitted (73 with data exist)                      0
completed/closed admitted (72 with data exist)                      0
=========================================================  ==========

The 500 admitted rows spanned a *fifteen minute* ``commence_time`` band, and the
feed served one real game — rendered twice, as two cards.

TWO GUARDS, BECAUSE THE TWO FAULTS ARE INDEPENDENT
--------------------------------------------------
1. **Exact-duplicate collapse.**  2,911 live ``esports`` rows resolved to *ten*
   distinct matchups: mean 291 copies each, max 364, **zero singletons**.  Rows
   sharing ``(sport, home, away, commence_time)`` are byte-identical restatements
   of one fixture, so we keep the richest one.

   This is a DISPLAY-layer collapse of identical rows and nothing more.  It is
   **not** a matching fix and must not be described as one: near-miss aliases
   (#1986's ``"tampa bay"`` vs ``"tampa bay rays"``) are out of scope *by
   construction* and remain the registry's under ruling 048.

2. **Per-tier quotas.**  The collapse alone fixes today and not the class.  With
   zero duplicates a legitimate flood re-creates the starvation — 2,703
   *distinct* esports matchups were created in the seven days to 2026-08-21 — so
   each tier gets a floor that no sibling can take.

Measured effect of the collapse alone on that same pool: **25,610 → 279**
candidates (live 2,941→39, recent 19,900→144, scheduled 2,769→96).  The cap
stops binding, and every tier is admitted.

PROVING THIS
------------
The feed's integration harness mocks ``db.execute``, so no test in this repo
ever runs this SQL.  Two things close that gap and both are load-bearing:
``tests/test_feed_event_candidates.py`` compiles the statement against the real
PostgreSQL dialect and asserts its shape, and the queue's production evidence
runs the compiled SQL against the live database.  A window query that satisfies
SQLAlchemy but not Postgres would otherwise pass every gate.
"""

from __future__ import annotations

from sqlalchemy import Numeric, Select, String, and_, case, func, or_, select
from sqlalchemy.ext.compiler import compiles
from sqlalchemy.sql.functions import FunctionElement

from app.models import Event, Sport

# Status tiers, in the priority order the feed has always used.
TIER_LIVE = 0
TIER_RECENT = 1
TIER_SCHEDULED = 2

RECENT_STATUSES = ("completed", "closed")

#: Total rows the candidate pass may return.  Deliberately UNCHANGED from the
#: single ``LIMIT 500`` this replaces — the fix is how the budget is *divided*,
#: not how big it is, so no latency claim rides on it.
EVENT_CANDIDATE_BUDGET = 500

#: Per-tier hard caps.  They sum to :data:`EVENT_CANDIDATE_BUDGET`, and each one
#: sits above the deduplicated tier size measured on production 2026-08-21
#: (live 39, recent 144, scheduled 96) — so on a real slate nothing is cut and
#: the quotas are inert.  They bind only under a flood, which is the whole point.
TIER_QUOTAS = {
    TIER_LIVE: 200,
    TIER_RECENT: 150,
    TIER_SCHEDULED: 150,
}

#: How far two rows' ``commence_time`` may disagree and still be the SAME
#: fixture for display purposes.
#:
#: WHY THIS IS NOT ZERO (#2057).  The original collapse partitioned on
#: ``commence_time`` **exactly**, because every duplicate it was built for
#: shared one: #2065's esports rows were byte-identical restatements, and
#: #2213's Red Sox pair was measured as "identical ``sport_id``,
#: ``home_team_name``, ``away_team_name`` and ``commence_time``".  That stopped
#: being true.  Measured on production 2026-08-31, over every duplicate group in
#: a five-day window:
#:
#: =====================  ============
#: gap between the rows   groups
#: =====================  ============
#: 0s                                3
#: **60s**                      **12**  ← the whole MLB slate
#: 1,784s                            1
#: ≥17,098s (4.7h+)                 39
#: =====================  ============
#:
#: Twelve MLB games — the entire slate — carry a StatPal row and an Odds-API row
#: exactly **one minute** apart, so the exact-equality key was inert against all
#: of them while catching only three groups all week.  Discover was serving four
#: of those pairs as eight cards at the moment this was written.
#:
#: WHY 300 SECONDS, AND WHY NOT LARGER.  This is deliberately the SMALLEST
#: number that covers the measured fault, not the largest that could be
#: defended.  It is 5× the 60s skew it exists for, ~6× below the nearest
#: non-60s group in the same census (1,784s, a lone ``soccer_other`` pair that
#: therefore stays uncollapsed), and ~36× below
#: ``espn_candidate_selection.MAX_SAME_GAME_SECONDS`` (3h), the repository's
#: measured *identity* bound.  A doubleheader is hours apart and cannot come
#: near it.
#:
#: THE ASYMMETRY THAT PICKS THE DIRECTION.  Failing to collapse shows a visible
#: duplicate — today's behaviour, no regression.  Over-collapsing HIDES a real
#: game, which is both worse and invisible.  So every judgement call here is
#: resolved toward the smaller number, and every edge case below fails toward
#: leaving two cards rather than one.
#:
#: This does not touch ruling 048.  It is still a DISPLAY collapse of two rows
#: into one CARD, mutating nothing and leaving both rows addressable at
#: ``/api/events/{id}``; absorption still needs an id-anchored correspondence.
#: Measurement says none exists for these pairs either — the StatPal row carries
#: only ``statpal_fixture_id`` and the Odds-API row only ``external_id`` /
#: ``espn_id``, so no provider id is shared and the registry correctly declines
#: to merge them.  That merge stays behind the anchor channel (#1946).
SAME_FIXTURE_SECONDS = 300


class _EpochSeconds(FunctionElement):
    """``commence_time`` as seconds, on both dialects this code runs against.

    There is no dialect-portable spelling of "seconds since the epoch" in
    SQLAlchemy, and the tolerance comparison below needs one: production is
    PostgreSQL, while the executing tests in
    ``tests/test_feed_event_candidates.py`` run on in-memory SQLite so that the
    collapse is proven by *running* it and not only by compiling it.  A
    PostgreSQL-only ``EXTRACT(EPOCH ...)`` would silently downgrade every one of
    those tests to a shape assertion.

    The test module already carries the same pattern for ``JSONB`` and ``ARRAY``
    DDL; this is that shim moved next to the expression that needs it, so there
    is one definition rather than one per caller.
    """

    type = Numeric()
    inherit_cache = True


@compiles(_EpochSeconds)
def _epoch_seconds_default(element, compiler, **kw):  # pragma: no cover - PG path
    (inner,) = element.clauses
    return "EXTRACT(EPOCH FROM %s)" % compiler.process(inner, **kw)


@compiles(_EpochSeconds, "sqlite")
def _epoch_seconds_sqlite(element, compiler, **kw):
    (inner,) = element.clauses
    return "CAST(strftime('%%s', %s) AS REAL)" % compiler.process(inner, **kw)


def status_tier_expr():
    """SQL tier of an event row — live (0) → recent (1) → scheduled (2)."""
    return case(
        (Event.status == "live", TIER_LIVE),
        (Event.status.in_(RECENT_STATUSES), TIER_RECENT),
        else_=TIER_SCHEDULED,
    )


def identity_incomplete_expr():
    """True when a row cannot be safely identified for duplicate collapse.

    ``PARTITION BY`` treats NULLs as EQUAL, so a row missing any part of its
    identity would be fused with every other such row in the same bucket.  Those
    rows partition on their own ``id`` instead and can therefore never be
    collapsed with anything.

    The live arm is the EMPTY STRING, not NULL: ``home_team_name``,
    ``away_team_name`` and ``commence_time`` are all NOT NULL in the schema, so
    the NULL arms are unreachable today and are kept for the column that loosens
    later.  Either way this is latent rather than live — production measured zero
    empty and zero NULL names across all 25,610 candidates on 2026-08-21 — which
    is exactly why it needs a test and not a comment.  Mutation M2 deleted this
    guard and the first version of that test still passed, because it varied the
    away name and so never made two rows share a key.
    """
    return or_(
        Event.home_team_name.is_(None),
        Event.away_team_name.is_(None),
        Event.commence_time.is_(None),
        Event.home_team_name == "",
        Event.away_team_name == "",
    )


def survivor_order():
    """Which copy of a duplicated fixture wins, most significant key first.

    ``has probability sources`` leads, because a copy that can render a
    probability is strictly more useful than one that renders a blank card — the
    MLB row on the 2026-08-21 feed served ``current_odds: null``.  Then ``has a
    score``.  Then the lowest ``id``: the original row that other tables link
    to, and the key that makes this choice deterministic rather than merely
    arbitrary.

    ``IS NOT NULL`` ALONE IS NOT THE PREDICATE, and the first draft of this used
    it.  SQLAlchemy's JSON type serialises Python ``None`` to the JSON text
    ``'null'`` rather than to SQL NULL, so an ORM-written source-less row reads
    as *having* sources and the blank copy wins the tiebreak.  Today's
    production rows are true SQL NULL (25,442 NULL / 167 real / **zero** empty
    ``{}`` across the 25,610 candidates), so this is latent there rather than
    live — but the executing test in ``test_feed_event_candidates.py`` caught it
    immediately, and a shape-only assertion never would have.  Compare the text
    form so all three spellings of "nothing" collapse to the same answer.

    Ranking finer than "has sources" — by the *number* of sources, say — was
    declined: counting JSONB keys needs a correlated subquery per row across the
    whole window, and no measurement showed a benefit worth that.

    ``has_opening`` WAS ADDED LATER (#2213), AND THE MEASUREMENT THAT WAS MISSING
    ABOVE NOW EXISTS.  On 2026-08-25 the Red Sox–Marlins duplicate pair reached
    the tiebreak with **both** rows carrying sources and **both** carrying a
    score, so the decision fell all the way through to ``Event.id.asc()`` — and
    the lowest id was the wrong row.  Ids are creation order, and the
    schedule-only pipeline creates six days early:

    ======================  =========================  =========================
    row                     ``15228865`` (StatPal)     ``15291666`` (ESPN/odds)
    ======================  =========================  =========================
    created                 2026-08-19 (wins on id)    2026-08-25
    sources                 ``mlb`` alone              espn + betting + stat_model
    opening probabilities   none                       0.4209 / 0.5791
    the card it renders     50%/50%, one signal bar    57%/43%, "Opened 58%/42%"
    ======================  =========================  =========================

    So "collapse to one card" would have kept the *worse* card — a coin-flip
    reading off a single source, replacing a real blend — and the duplicate bug
    would have been traded for a quality bug that is harder to see.  **Arriving
    first is not evidence of being better; for this pair it is evidence of the
    opposite**, because the pipeline that creates earliest is the one carrying
    least.

    ``opening_home_probability IS NOT NULL`` is a plain column test — no
    subquery, no JSONB traversal — and it separates "a betting source has priced
    this row" from "this row is a schedule entry".  It is deliberately a proxy
    for richness rather than a measure of it; true source-count ranking stays
    declined on the cost grounds above, which still hold for the 25,610-row
    Discover pool.

    WHERE IT SITS, AND WHY IT MOVED (CERT-407)
    ------------------------------------------
    The first version of this placed ``has_opening`` directly below
    ``has_sources`` and therefore ABOVE ``has_score``.  CERT-407 blocked on that
    ordering and the finding was right: it makes a row that has merely been
    PRICED outrank a row that has actually been PLAYED.  Driven on a real pair,
    it kept an opening-priced scoreless row and suppressed the only row carrying
    ``2–1`` — trading #2213's duplicate bug for a fresher one in which My Stuff
    shows a live card that does not know the score.

    The two keys answer different questions and the order between them is the
    whole content of the repair:

    ``has_score``    is direct evidence about the FIXTURE — this row knows what
                     is happening in the game.
    ``has_opening``  is evidence about the PIPELINE that wrote the row — some
                     betting source has priced it at least once.

    Direct evidence about the game wins, so ``has_score`` leads.  The #2213 pair
    is untouched by the swap because BOTH of its rows carry a score: the tie
    ``has_opening`` was added to break is still the tie it breaks, one key later.
    That non-obvious fact is why the repair keeps two separate tests — one for
    the key's POSITION, one for its PRESENCE — since a corpus that proves either
    alone will happily pass with the other broken.

    The key remains inert for every pre-existing test in
    ``test_feed_event_candidates.py`` (their fixtures set no opening odds), which
    is the check that it widens the order rather than reordering it.
    """
    return [signal.desc() for _, signal in _survivor_signals()] + [Event.id.asc()]


#: Label carried by each survivor signal into the collapse subquery, in the
#: certified order.  The outer window orders by these labels, so the ordering
#: and the columns it reads cannot drift into two different definitions.
SURVIVOR_SIGNAL_NAMES = ("has_sources", "has_score", "has_opening")


def _survivor_signals():
    """The survivor signals as ``(label, expression)``, most significant first.

    Split out of :func:`survivor_order` so the two-level collapse can carry the
    same three expressions through its inner subquery and order by them
    outside, without restating them.  The order of this tuple IS the certified
    order documented above, and ``test_the_survivor_keys_are_in_the_certified_order``
    still reads it through :func:`survivor_order`.
    """
    sources_text = func.cast(Event.win_probability_sources, String)
    has_sources = case(
        (
            and_(
                Event.win_probability_sources.isnot(None),
                sources_text.notin_(("null", "{}")),
            ),
            1,
        ),
        else_=0,
    )
    has_score = case(
        (or_(Event.home_score.isnot(None), Event.away_score.isnot(None)), 1),
        else_=0,
    )
    has_opening = case(
        (Event.opening_home_probability.isnot(None), 1),
        else_=0,
    )
    return tuple(zip(SURVIVOR_SIGNAL_NAMES, (has_sources, has_score, has_opening)))


def fixture_identity_partition():
    """The columns that say "these rows are claims about the same fixture".

    Everything except the clock.  ``commence_time`` used to sit here as an
    exact key; it is now applied as a bounded window
    (:data:`SAME_FIXTURE_SECONDS`) in :func:`_collapsed_subquery`, because two
    providers disagree about the minute a game starts (#2057).
    """
    return [
        Event.sport_id,
        Event.home_team_name,
        Event.away_team_name,
        case((identity_incomplete_expr(), Event.id), else_=None),
    ]


def _collapsed_subquery(where_clauses, name: str):
    """The duplicate-collapse pass, shared by both callers.

    Factored out for :func:`deduplicated_event_ids` (My Stuff) so the two
    surfaces cannot drift into two different definitions of "the same fixture".
    A second, subtly different partition key is a second set of duplicates.

    TWO LEVELS, BECAUSE THE FIXTURE KEY IS NO LONGER A COLUMN (#2057)
    -----------------------------------------------------------------
    A window function cannot be nested inside another window function's
    ``PARTITION BY``, and the fixture key is now itself a windowed value: each
    row looks at the previous row for the same teams and adopts its start time
    when the two are within :data:`SAME_FIXTURE_SECONDS`.  So the scan computes
    ``prev_commence_time`` with ``lag()``, and the collapse partitions on the
    derived ``fixture_start`` one level up.

    WHY ``lag()`` AND NOT A BUCKET.  Rounding ``commence_time`` to a grid is one
    expression instead of two, and it was rejected: every bucket has an edge,
    and a pair straddling one silently stops collapsing.  Today's data would
    survive a 10-minute floor only because MLB start times happen to sit on a
    5-minute grid — a property of this season's schedule, not of the fault.
    ``lag()`` compares the rows to *each other*, so there is no edge to straddle.

    THE CHAIN CASE, STATED.  Three rows each 4 minutes apart collapse as
    ``{1,2}`` and ``{3}`` rather than as one group, because row 3 adopts row 2's
    time and not row 1's.  That is the fail-safe direction (an extra card, never
    a hidden game) and no such chain exists in the measured data — every
    duplicate group in the census is exactly two rows.
    """
    fixture_partition = fixture_identity_partition()

    scanned = (
        select(
            Event.id.label("id"),
            status_tier_expr().label("tier"),
            Event.commence_time.label("commence_time"),
            # Carried so a caller can ORDER the collapsed pool without a second
            # visit to ``events`` (#2057, LANE1-Q475).  It is a passenger: no
            # partition, no survivor key and no filter reads it here.
            Event.status.label("status"),
            Event.sport_id.label("sport_id"),
            Event.home_team_name.label("home_team_name"),
            Event.away_team_name.label("away_team_name"),
            case((identity_incomplete_expr(), Event.id), else_=None).label(
                "identity_key"
            ),
            func.lag(Event.commence_time)
            .over(partition_by=fixture_partition, order_by=Event.commence_time.asc())
            .label("prev_commence_time"),
            *(signal.label(label) for label, signal in _survivor_signals()),
        )
        .select_from(Event)
        .join(Sport, Event.sport_id == Sport.id)
        .where(and_(*where_clauses))
        .subquery(f"{name}_scanned")
    )

    # The previous row's start time when it is close enough to be the same
    # fixture, this row's own otherwise — so both halves of a pair carry one
    # value and a doubleheader's second leg starts a new group.
    fixture_start = case(
        (
            and_(
                scanned.c.prev_commence_time.isnot(None),
                (
                    _EpochSeconds(scanned.c.commence_time)
                    - _EpochSeconds(scanned.c.prev_commence_time)
                )
                <= SAME_FIXTURE_SECONDS,
            ),
            scanned.c.prev_commence_time,
        ),
        else_=scanned.c.commence_time,
    )

    return (
        select(
            scanned.c.id,
            scanned.c.tier,
            scanned.c.commence_time,
            scanned.c.status,
            func.row_number()
            .over(
                partition_by=[
                    scanned.c.sport_id,
                    scanned.c.home_team_name,
                    scanned.c.away_team_name,
                    scanned.c.identity_key,
                    fixture_start,
                ],
                order_by=[scanned.c[label].desc() for label in SURVIVOR_SIGNAL_NAMES]
                + [scanned.c.id.asc()],
            )
            .label("dup_rn"),
        )
        .select_from(scanned)
        .subquery(name)
    )


def deduplicated_events(where_clauses, name: str):
    """The collapsed pool as a SUBQUERY — ``id``, ``tier``, ``commence_time``,
    ``status``, ``dup_rn`` — for a caller that must ORDER and CAP it.

    WHY A SECOND ENTRY POINT (#2057, LANE1-Q475), AND WHY IT IS NOT A LUXURY
    -----------------------------------------------------------------------
    :func:`deduplicated_event_ids` hands back a bare ``SELECT id``, which a
    caller can only consume as ``Event.id.IN (…)``.  That shape was fine for My
    Stuff, whose pool is already bounded to one user's teams, and it is the
    wrong shape for a rail that shows the EIGHT most imminent games out of
    hundreds.  Measured on production 2026-08-31 with ``EXPLAIN (ANALYZE,
    BUFFERS)`` over the exact statement the results rail compiles, the semi-join
    form cost ``tennis_atp`` **1,946 -> 7,199 blocks** and the eight leagues in
    ``recent_results_query``'s table **10,572 -> 69,575** — because PostgreSQL
    drove the plan FROM the subquery and paid an ``events_pkey`` lookup plus a
    ``sports_pkey`` lookup for every one of 968 survivors, to return nine rows.

    The collapse itself was never the expense: that same plan attributes **402
    blocks** to the whole two-window scan.  What cost was hydrating every
    survivor before the ``LIMIT``.  Exposing the subquery lets the caller order
    and cap the collapsed pool FIRST and hydrate only the nine rows it will
    render.

    The ``dup_rn == 1`` filter is deliberately left to the caller.  Applying it
    here would make this a different function with the same body as
    :func:`deduplicated_event_ids`, and the point of exposing the subquery is
    that the caller composes.
    """
    return _collapsed_subquery(where_clauses, f"{name}_collapsed")


def deduplicated_event_ids(where_clauses, name: str = "my_stuff_candidates") -> Select:
    """A SELECT of event ids with duplicates collapsed and NO tier quotas.

    ``name`` labels the emitted subquery and nothing else — it does not change a
    row.  It exists because more than one surface calls this now, and a plan
    read off production that says ``my_stuff_candidates_collapsed`` names the
    wrong surface to the next person debugging it.  The default is the original
    string, so My Stuff's alias is unchanged.

    ⚠️ **My Stuff's emitted SQL is NOT byte-identical, and the difference is one
    projected column.**  ``status`` was added to the scan for the league rails
    (#2057, LANE1-Q475).  Diffed statement against statement, that column and
    its restatement one level up are the ONLY changes: no partition key, no
    survivor key, no filter, no row.  Measured on the real Discover-shaped pool
    on production 2026-08-31, warm best of three: **1,568 root blocks and 357
    rows on both trees, identical.**  Stated rather than asserted, because "a
    projection is free" is a belief until someone runs it.

    A caller that must ORDER or CAP the collapsed pool wants
    :func:`deduplicated_events` instead — see the cost measured there.

    WHY THIS EXISTS SEPARATELY (#2213)
    ----------------------------------
    ``event_candidate_ids`` does two things — collapse duplicates, then divide a
    500-row budget across three status tiers — and only the Discover/Sports pool
    ever called it.  **My Stuff took the other branch of the same ``if`` and got
    neither guard**, so the collapse that has protected Discover since #2065 was
    never applied to the surface Alex actually opens.

    The bill arrived on 2026-08-25: My Stuff rendered "Live Now (2)" for ONE
    game, Boston Red Sox @ Miami Marlins, as two cards disagreeing about it —
    57%/43% on the ESPN/odds row and 50%/50% on the StatPal row.  Both rows carry
    identical ``sport_id``, ``home_team_name``, ``away_team_name`` and
    ``commence_time``, so the existing partition key would have collapsed them
    unchanged.  Nothing new had to be invented; the guard simply was not wired to
    this branch.

    The quotas are deliberately NOT carried over.  They exist to stop one status
    tier starving another out of a shared 500-row budget, and My Stuff's pool is
    a different shape: it is already bounded to one user's teams, capped at 200,
    and restricted to tier-1/2 sports.  Imposing a 200/150/150 split on a pool
    that rarely exceeds 40 rows would add a cut that never binds — and if it ever
    did bind, it would silently drop one of Alex's own games, which is worse than
    the flood it would be guarding against.

    Ruling 048 is untouched, and the distinction matters enough to restate: this
    collapses two rows into one **CARD**, not into one **ROW**.  It mutates
    nothing, is reversible by deleting the ``where``, and both rows remain fully
    addressable at ``/api/events/{id}``.  Absorbing them into a single event row
    would need an id-anchored correspondence, which measurement says does not
    exist — 0 of 41 duplicate MLB pairs share any provider id (#2213).  That
    merge stays the registry's, behind the anchor channel.
    """
    collapsed = deduplicated_events(where_clauses, name)
    return select(collapsed.c.id).where(collapsed.c.dup_rn == 1)


def event_candidate_ids(where_clauses) -> Select:
    """A SELECT of event ids: duplicates collapsed, then quota'd per tier.

    Returns a ``Select`` of ids for use as a subquery, so the caller keeps its
    single round trip and its existing ORM loader options.

    ``where_clauses`` must already carry the full candidate predicate — time
    window, sport filter, tag containment.  They are applied *inside* the window
    pass on purpose: quotas computed over an unfiltered pool would hand a
    filtered request the wrong slice.
    """
    collapsed = _collapsed_subquery(where_clauses, "feed_event_candidates_collapsed")

    ranked = (
        select(
            collapsed.c.id.label("id"),
            collapsed.c.tier.label("tier"),
            func.row_number()
            .over(
                partition_by=collapsed.c.tier,
                order_by=collapsed.c.commence_time.desc(),
            )
            .label("tier_rn"),
        )
        .where(collapsed.c.dup_rn == 1)
        .subquery("feed_event_candidates_ranked")
    )

    quota_expr = case(
        (ranked.c.tier == TIER_LIVE, TIER_QUOTAS[TIER_LIVE]),
        (ranked.c.tier == TIER_RECENT, TIER_QUOTAS[TIER_RECENT]),
        else_=TIER_QUOTAS[TIER_SCHEDULED],
    )

    return select(ranked.c.id).where(ranked.c.tier_rn <= quota_expr)
