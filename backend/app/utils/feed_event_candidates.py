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
from app.utils.proven_duplicates import not_a_proven_duplicate

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
    return [has_sources.desc(), has_score.desc(), Event.id.asc()]


def event_candidate_ids(where_clauses) -> Select:
    """A SELECT of event ids: duplicates collapsed, then quota'd per tier.

    Returns a ``Select`` of ids for use as a subquery, so the caller keeps its
    single round trip and its existing ORM loader options.

    ``where_clauses`` must already carry the full candidate predicate — time
    window, sport filter, tag containment.  They are applied *inside* the window
    pass on purpose: quotas computed over an unfiltered pool would hand a
    filtered request the wrong slice.

    #2263: proven duplicates are dropped here too, and that is a DIFFERENT guard
    from the collapse below rather than a widening of it.  The collapse fuses
    rows that are byte-identical on ``(sport, home, away, commence_time)``; the
    twins #2263 found differ by ONE MINUTE and by ``"St.Louis"`` vs
    ``"St. Louis"``, so the partition never groups them and the flagship surface
    printed both.  Near-miss aliases remain out of scope for the collapse exactly
    as this module's header says — the difference is that a proven duplicate is
    not a near-miss guess.  It was established at the write side, by ESPN's own
    fixture resolving onto two of our rows, and this reads the finding rather
    than re-deriving it.
    """
    where_clauses = [*where_clauses, not_a_proven_duplicate()]
    dedup_partition = [
        Event.sport_id,
        Event.home_team_name,
        Event.away_team_name,
        Event.commence_time,
        case((identity_incomplete_expr(), Event.id), else_=None),
    ]

    collapsed = (
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
        .subquery("feed_event_candidates_collapsed")
    )

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
