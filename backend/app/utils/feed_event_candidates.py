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

from sqlalchemy import Select, String, and_, case, func, or_, select

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
    Discover pool.  Placed BELOW ``has_sources`` and ABOVE ``has_score`` so it
    only ever breaks ties the existing keys leave open, and it is inert for every
    pre-existing test in ``test_feed_event_candidates.py`` (their fixtures set no
    opening odds) — which is the check that it widens the order rather than
    reorders it.
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
    has_opening = case(
        (Event.opening_home_probability.isnot(None), 1),
        else_=0,
    )
    has_score = case(
        (or_(Event.home_score.isnot(None), Event.away_score.isnot(None)), 1),
        else_=0,
    )
    return [
        has_sources.desc(),
        has_opening.desc(),
        has_score.desc(),
        Event.id.asc(),
    ]


def _collapsed_subquery(where_clauses, name: str):
    """The duplicate-collapse pass, shared by both callers.

    Factored out for :func:`deduplicated_event_ids` (My Stuff) so the two
    surfaces cannot drift into two different definitions of "the same fixture".
    A second, subtly different partition key is a second set of duplicates.
    """
    dedup_partition = [
        Event.sport_id,
        Event.home_team_name,
        Event.away_team_name,
        Event.commence_time,
        case((identity_incomplete_expr(), Event.id), else_=None),
    ]

    return (
        select(
            Event.id.label("id"),
            status_tier_expr().label("tier"),
            Event.commence_time.label("commence_time"),
            func.row_number()
            .over(partition_by=dedup_partition, order_by=survivor_order())
            .label("dup_rn"),
        )
        .select_from(Event)
        .join(Sport, Event.sport_id == Sport.id)
        .where(and_(*where_clauses))
        .subquery(name)
    )


def deduplicated_event_ids(where_clauses) -> Select:
    """A SELECT of event ids with duplicates collapsed and NO tier quotas.

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
    collapsed = _collapsed_subquery(where_clauses, "my_stuff_candidates_collapsed")
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
