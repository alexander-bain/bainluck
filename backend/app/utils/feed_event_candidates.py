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
from app.utils.event_completion import EVENT_SUSPENDED
from app.utils.proven_duplicates import not_a_proven_duplicate

# Status tiers.  These integers are PARTITION LABELS and quota keys, not a
# display order — the caller applies its own `ORDER BY` after this pass — which
# is why `TIER_SUSPENDED` can be appended at 3 without claiming that a suspended
# match is less interesting than a scheduled one.
TIER_LIVE = 0
TIER_RECENT = 1
TIER_SCHEDULED = 2
#: live/048 + CERT-786 — see :data:`TIER_QUOTAS` for why this is its own tier
#: rather than a fourth member of :data:`RECENT_STATUSES`.
TIER_SUSPENDED = 3

RECENT_STATUSES = ("completed", "closed")

#: Total rows the candidate pass may return.  Deliberately UNCHANGED from the
#: single ``LIMIT 500`` this replaces — the fix is how the budget is *divided*,
#: not how big it is, so no latency claim rides on it.  Still unchanged through
#: live/048: the suspended tier is funded by re-dividing, not by growing.
EVENT_CANDIDATE_BUDGET = 500

#: Per-tier hard caps.  They sum to :data:`EVENT_CANDIDATE_BUDGET`, and each one
#: sits above the deduplicated tier size measured on production 2026-08-21
#: (live 39, recent 144, scheduled 96) — so on a real slate nothing is cut and
#: the quotas are inert.  They bind only under a flood, which is the whole point.
#:
#: ── WHY `suspended` GOT ITS OWN FLOOR (live/048, CERT-786) ──
#:
#: The obvious move was to add it to :data:`RECENT_STATUSES`, and that would
#: have reintroduced #2065 in miniature.  A suspended row IS recent, but its
#: measured population is a flood with a flood's shape — ~500 rows/day, 89% of
#: them esports fixtures whose only source went dark — while the recent tier's
#: deduplicated size on a real slate is 144 against a quota of 150.  Six slots
#: of slack is not a floor.  A quiet night of esports outages would have taken
#: "Just Happened" away from real finished games, which is precisely the
#: starvation this module exists to prevent, arriving through the door the
#: module left open.
#:
#: So it gets a tier, and the module's own rule applies unchanged: *each tier
#: gets a floor that no sibling can take.*
#:
#: THE 50 IS FUNDED FROM `TIER_LIVE`, 200 → 150, and that is the safest of the
#: three places it could have come from.  Measured deduplicated tier sizes leave
#: live with 161 slots of headroom, recent with 6 and scheduled with 54, so live
#: is the only tier that can pay without moving its floor near its measurement —
#: 150 is still 3.8× the 39 rows live actually carries.  It is also the tier a
#: suspended row COMES FROM: a live match going into a rain delay moves between
#: exactly these two tiers, so the budget follows the row.
TIER_QUOTAS = {
    TIER_LIVE: 150,
    TIER_RECENT: 150,
    TIER_SCHEDULED: 150,
    TIER_SUSPENDED: 50,
}


def candidate_window_conditions(
    *,
    now,
    live_start_cutoff,
    upcoming_cutoff,
    recent_cutoff,
):
    """The status × time window the game-event candidate pass selects on.

    ONE DEFINITION, AND IT IS NEW (live/048, CERT-786).  This predicate used to
    live inline in ``_score_events`` with a hand-written copy of it in
    ``tests/test_feed_event_candidates.py`` — a copy whose docstring said "the
    exact predicate ``_score_events`` accumulates", which was true when it was
    written and is exactly the kind of claim that stops being true silently.
    When ``suspended`` was added to the vocabulary the route was one of the
    places that had to learn the word and did not; a test holding its own copy
    of the predicate could not have caught that, because the copy would have
    been just as wrong and just as green.  So the copy is gone: the route calls
    this, the executing test calls this, and there is nothing left to diverge.

    The windows are passed in rather than computed here because the caller
    widens them for ``my_teams_only`` (72h back / 7d forward instead of 24h /
    12h), and that choice belongs to the request, not to the predicate.

    Arms, in order:

    * ``live`` — no lower bound; a long game is still a game.  The upper bound
      is a small clock-drift buffer against rows stuck ``live`` with a future
      start (see :func:`app.utils.lifecycle.served_event_status`).
    * ``scheduled`` — ahead of us, inside the upcoming window.
    * ``completed`` / ``closed`` — recently finished.
    * ``suspended`` — recently *not* finished, on the same window as the Final
      it replaced.  See the route-side comment for why it shares that window
      rather than the live arm's open floor.
    """
    return [
        or_(
            and_(
                Event.status == "live",
                Event.commence_time <= live_start_cutoff,
            ),
            and_(
                Event.status == "scheduled",
                Event.commence_time >= now,
                Event.commence_time <= upcoming_cutoff,
            ),
            and_(
                Event.status.in_(RECENT_STATUSES),
                Event.commence_time >= recent_cutoff,
            ),
            and_(
                Event.status == EVENT_SUSPENDED,
                Event.commence_time >= recent_cutoff,
            ),
        )
    ]


def status_tier_expr():
    """SQL tier of an event row — live (0), recent (1), scheduled (2), suspended (3).

    The suspended arm sits ABOVE the ``else_`` deliberately.  Before live/048
    the ``else_`` meant "scheduled", and it was right, because the four states
    it dispatched over were exhaustive.  A fifth state made the ``else_`` a
    catch-all that silently filed an already-played match into the tier for
    matches that have not started — sorted by ``commence_time DESC`` within a
    tier whose other rows are all in the FUTURE, so the suspended rows landed at
    the bottom and were the first thing the quota cut.
    """
    return case(
        (Event.status == "live", TIER_LIVE),
        (Event.status.in_(RECENT_STATUSES), TIER_RECENT),
        (Event.status == EVENT_SUSPENDED, TIER_SUSPENDED),
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
        has_score.desc(),
        has_opening.desc(),
        Event.id.asc(),
    ]


def _collapsed_subquery(where_clauses, name: str):
    """The duplicate-collapse pass, shared by both callers.

    Factored out for :func:`deduplicated_event_ids` (My Stuff) so the two
    surfaces cannot drift into two different definitions of "the same fixture".
    A second, subtly different partition key is a second set of duplicates.

    #2263: the proven-duplicate predicate is applied HERE, in the shared pass,
    for that same reason — and it is a DIFFERENT guard from the collapse below
    rather than a widening of it.  The collapse fuses rows that are identical on
    ``(sport, home, away, commence_time)``; the twins #2263 found differ by ONE
    MINUTE and by ``"St.Louis"`` vs ``"St. Louis"``, so the partition never
    groups them and both surfaces printed both rows.  Near-miss aliases stay out
    of scope for the collapse exactly as this module's header says — the
    difference is that a proven duplicate is not a near-miss guess.  It was
    established at the write side, by ESPN's own fixture resolving onto two of
    our rows, and this reads that finding rather than re-deriving it.

    It is deliberately not in the two callers.  #2213 exists because My Stuff
    took the other branch of an ``if`` and missed a guard Discover had; putting
    this in ``event_candidate_ids`` alone would rebuild that asymmetry, and
    #2213 does not already cover it — its twins were identical on the partition
    key, and #2263's are not.  In the shared pass a third caller cannot miss it.
    """
    dedup_partition = [
        Event.sport_id,
        Event.home_team_name,
        Event.away_team_name,
        Event.commence_time,
        case((identity_incomplete_expr(), Event.id), else_=None),
    ]

    where_clauses = [*where_clauses, not_a_proven_duplicate()]

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

    #2263 widened this: My Stuff also drops rows the registry has *proven* to
    duplicate another, which the partition key above cannot catch because those
    twins differ by a minute and a punctuation mark.  It arrives through the
    shared collapse pass, so this surface can never again be the one that missed
    a guard Discover had.
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

    #2263: proven duplicates are dropped as well, by the shared collapse pass —
    see :func:`_collapsed_subquery` for why it lives there and not here.
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
        # live/048 — named, not left to the `else_`. The `else_` is the
        # scheduled quota, and a new tier inheriting another tier's number is
        # how a floor gets shared by accident.
        (ranked.c.tier == TIER_SUSPENDED, TIER_QUOTAS[TIER_SUSPENDED]),
        else_=TIER_QUOTAS[TIER_SCHEDULED],
    )

    return select(ranked.c.id).where(ranked.c.tier_rn <= quota_expr)
