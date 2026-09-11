"""#3879 — the fourth price rail: the served Polymarket long tail.

WHAT IS BEING GUARDED, AND WHY IT NEEDS GUARDING AT BIRTH.

A stale futures ladder renders exactly like a fresh one. There is no blank
state, no error and no missing card — the numbers simply age, wearing whatever
freshness word the gates award them. Measured on production 2026-09-07: 56,721
of 76,006 served Polymarket futures legs had not been re-read in 24 hours, and
nothing anywhere said so. #3868 is what it looks like when someone finally reads
one aloud on a page.

So this rail's tests are mostly about the states in which it achieves nothing,
because those are the states its own surface cannot show:

* the selector could not run (which is NOT "there is nothing to do"),
* nothing was stale (honest, and still never GREEN),
* everything stale was already attempted this window (the opposite state, and it
  gets its own reason rather than sharing that silence),
* Gamma refused every batch,
* markets came back and not one price landed.

Plus the three properties the ship itself turns on: the unit of work is the
whole MARKET, a batch that fails cannot wipe the run's other batches, and a
market that could not be written is marked ATTEMPTED so it cannot sit at the
head of a stalest-first ordering forever and starve the tail behind it.
"""

import app.tasks.polymarket_condition_refresh as rail
import app.tasks.tournament_price_refresh as tournament_rail
from app.utils.task_verdict import ENFORCED_TASKS, verdict_for


class _Market:
    """The one attribute the rail reads off a Gamma market before writing."""

    def __init__(self, condition_id: str):
        self.condition_id = condition_id


class _Service:
    def __init__(self, markets=None, raises: Exception | None = None, per_call=None):
        self._markets = markets or []
        self._raises = raises
        #: One entry per call: a list of markets, or an Exception to raise.
        self._per_call = list(per_call) if per_call is not None else None
        self.calls: list[list[str]] = []
        self.asked_include_closed: bool | None = None

    async def get_markets_by_conditions(
        self, conditions, batch_size=None, include_closed=False
    ):
        self.calls.append(list(conditions))
        self.asked_include_closed = include_closed
        if self._per_call is not None:
            step = self._per_call[len(self.calls) - 1]
            if isinstance(step, Exception):
                raise step
            return step
        if self._raises is not None:
            raise self._raises
        return self._markets


def _arm(
    monkeypatch,
    *,
    candidates=None,
    stale=0,
    served=0,
    selector_raises: Exception | None = None,
    service=None,
    writer=None,
    skips=None,
    marked=None,
    imminent=None,
    names=None,
):
    """Point the rail at scripted collaborators. No DB, no network, no Redis.

    ``names`` maps a market id to its ``(name, external_id)`` as the producer
    wrote them. The headline/ladder split is then computed by calling the REAL
    :func:`_is_headline_market` (#4983 repair, CERT-2564) rather than by handing
    the rail an answer — a test that injects the partition it is checking proves
    only that a set was plumbed through, and the first cut of this ship failed
    for exactly that reason.

    A market with no entry gets a bare-matchup name, which classifies as a
    headline. That is the right default for the ~10,600 non-kickoff rows the
    #3879 tests are about: they never reach the kickoff phases, so the split is
    not what those tests are asserting.
    """
    import app.services.polymarket_api as poly

    def _identity(mid):
        return (names or {}).get(mid, (f"Home {mid} vs. Away {mid}", f"0x{mid:04x}"))

    async def _select(*, stale_hours, limit):
        if selector_raises is not None:
            raise selector_raises
        rows = list(candidates or [])
        return (
            rows,
            stale,
            served,
            set(imminent or ()),
            {mid for mid, _ in rows if rail._is_headline_market(*_identity(mid))},
        )

    monkeypatch.setattr(rail, "_select_stale_conditions", _select)
    monkeypatch.setattr(poly, "PolymarketAPIService", lambda *a, **k: service or _Service())
    monkeypatch.setattr(rail, "_load_attempt_skips", lambda ids: set(skips or ()))
    # `marked is not None`, never `marked or []`: an empty list is falsy, and the
    # `or` form would quietly extend a throwaway list and report no marks at all.
    sink = marked if marked is not None else []
    # #4896: the real `_mark_attempted` takes the imminent set as a second
    # argument so it can pick a TTL per market. The double records the ids the
    # rail marked; which TTL each got is asserted directly against the real
    # function in `TestAnImminentGameReentersEachBeat`.
    monkeypatch.setattr(
        rail, "_mark_attempted", lambda ids, imminent_ids=frozenset(): sink.extend(ids)
    )
    if writer is not None:
        monkeypatch.setattr(tournament_rail, "_write_refreshed_prices", writer)


async def _writes(markets, stats, *, now):
    stats["outcomes_updated"] += 2 * len(markets)
    stats["snapshots_written"] += 2 * len(markets)


class TestThisRailCannotAchieveNothingQuietly:
    """Five ways to refresh no prices. None of them may read GREEN."""

    def test_the_rail_is_enrolled_so_its_terminal_is_authoritative(self):
        # Enrolment WITHOUT a terminal is a no-op, and a terminal WITHOUT
        # enrolment is ignored. Both halves, or neither is worth anything.
        assert "polymarket_condition_refresh" in ENFORCED_TASKS

    async def test_a_selector_that_could_not_run_is_failed_not_no_work(
        self, monkeypatch
    ):
        """"I could not look" and "there is nothing to do" must never read the same."""
        _arm(monkeypatch, selector_raises=RuntimeError("statement timeout"))
        stats = await rail._refresh_stale_polymarket_conditions()

        assert stats["terminal"] == "failed"
        assert stats["reason"] == "selector_failed"
        assert any("statement timeout" in e for e in stats["errors"])
        assert verdict_for("polymarket_condition_refresh", stats).is_green is False

    async def test_nothing_stale_is_no_work_and_still_never_green(self, monkeypatch):
        _arm(monkeypatch, candidates=[], stale=0, served=22_034)
        stats = await rail._refresh_stale_polymarket_conditions()

        assert stats["terminal"] == "no_work"
        assert stats["reason"] == "nothing_stale"
        verdict = verdict_for("polymarket_condition_refresh", stats)
        assert verdict.is_green is False
        # Authoritative, so it BLOCKS the success counter rather than being
        # waved through as a legacy return.
        assert verdict.authoritative is True
        assert verdict.blocks_success is True

    async def test_everything_stale_already_attempted_gets_its_own_reason(
        self, monkeypatch
    ):
        """The opposite state from the one above. One shared silence would hide
        a rail whose whole budget is being eaten by markets it cannot write."""
        _arm(
            monkeypatch,
            candidates=[(1, ["0xaaa"]), (2, ["0xbbb"])],
            stale=2,
            served=10,
            skips={1, 2},
        )
        stats = await rail._refresh_stale_polymarket_conditions()

        assert stats["terminal"] == "no_work"
        assert stats["reason"] == "all_recently_attempted"
        assert stats["skipped_recent_attempt"] == 2
        assert verdict_for("polymarket_condition_refresh", stats).is_green is False

    async def test_a_zero_budget_says_so_instead_of_borrowing_that_reason(
        self, monkeypatch
    ):
        """Both leave `due` empty and they mean opposite things: this one
        refreshed nothing BY INSTRUCTION, the one above could not."""
        _arm(
            monkeypatch,
            candidates=[(1, ["0xaaa"]), (2, ["0xbbb"])],
            stale=2,
            served=10,
        )
        stats = await rail._refresh_stale_polymarket_conditions(budget=0)

        assert stats["terminal"] == "no_work"
        assert stats["reason"] == "no_budget"
        assert stats["skipped_recent_attempt"] == 0
        assert verdict_for("polymarket_condition_refresh", stats).is_green is False

    async def test_every_batch_refused_by_gamma_is_failed_and_names_the_cause(
        self, monkeypatch
    ):
        _arm(
            monkeypatch,
            candidates=[(1, ["0xaaa"])],
            stale=1,
            served=10,
            service=_Service(raises=RuntimeError("gamma 429")),
        )
        stats = await rail._refresh_stale_polymarket_conditions()

        assert stats["terminal"] == "failed"
        assert stats["reason"] == "fetch_failed"
        assert any("gamma 429" in e for e in stats["errors"])
        assert verdict_for("polymarket_condition_refresh", stats).is_green is False

    async def test_markets_returned_but_no_price_written_is_failed(self, monkeypatch):
        """The zero-yield mutant. Everything 'worked' and nothing landed."""

        async def _writes_nothing(markets, stats, *, now):
            stats["unpriced"] += len(markets)

        _arm(
            monkeypatch,
            candidates=[(1, ["0xaaa"])],
            stale=1,
            served=10,
            service=_Service(markets=[_Market("0xaaa")]),
            writer=_writes_nothing,
        )
        stats = await rail._refresh_stale_polymarket_conditions()

        assert stats["terminal"] == "failed"
        assert stats["reason"] == "no_prices_written"
        assert stats["snapshots_written"] == 0
        assert verdict_for("polymarket_condition_refresh", stats).is_green is False

    async def test_a_run_that_wrote_prices_is_the_only_green(self, monkeypatch):
        _arm(
            monkeypatch,
            candidates=[(1, ["0xaaa"])],
            stale=1,
            served=10,
            service=_Service(markets=[_Market("0xaaa")]),
            writer=_writes,
        )
        stats = await rail._refresh_stale_polymarket_conditions()

        assert stats["terminal"] == "complete"
        assert stats["reason"] == "prices_written"
        assert verdict_for("polymarket_condition_refresh", stats).is_green is True


class TestOneBadBatchCannotWipeTheRun:
    """Gotcha #42, and it is sharper here than in a feed loop: the batches are
    independent markets, so a single Gamma hiccup must cost those forty rows and
    nothing else."""

    async def test_a_failed_fetch_leaves_the_other_batch_written(self, monkeypatch):
        conditions = [(i, [f"0x{i:03x}"]) for i in range(rail.BATCH_SIZE + 1)]
        service = _Service(
            per_call=[RuntimeError("gamma 502"), [_Market("0xfff")]]
        )
        _arm(
            monkeypatch,
            candidates=conditions,
            stale=len(conditions),
            served=1_000,
            service=service,
            writer=_writes,
        )
        stats = await rail._refresh_stale_polymarket_conditions()

        assert stats["batches"] == 2
        assert stats["snapshots_written"] > 0
        assert any("gamma 502" in e for e in stats["errors"])
        # It wrote, so it is not `failed` — and it carries an error, so the
        # contract downgrades it to PARTIAL rather than letting a half-run pass
        # as healthy.
        assert stats["terminal"] == "complete"
        assert verdict_for("polymarket_condition_refresh", stats).is_green is False

    async def test_a_write_that_raises_is_caught_per_batch(self, monkeypatch):
        """The quietest failure this rail has: fetched fine, wrote nothing."""
        calls = {"n": 0}

        async def _second_batch_only(markets, stats, *, now):
            calls["n"] += 1
            if calls["n"] == 1:
                raise RuntimeError("deadlock detected")
            await _writes(markets, stats, now=now)

        conditions = [(i, [f"0x{i:03x}"]) for i in range(rail.BATCH_SIZE + 1)]
        _arm(
            monkeypatch,
            candidates=conditions,
            stale=len(conditions),
            served=1_000,
            service=_Service(markets=[_Market("0xaaa")]),
            writer=_second_batch_only,
        )
        stats = await rail._refresh_stale_polymarket_conditions()

        assert any("deadlock detected" in e for e in stats["errors"])
        assert stats["snapshots_written"] > 0
        assert verdict_for("polymarket_condition_refresh", stats).is_green is False


class TestAnImminentGameReentersEachBeat:
    """CERT-2546's required repair: an ordering key alone does not set a cadence.

    #4896's first cut led the queue with imminent games and stopped there. But
    leading only decides who goes first among rows that are ELIGIBLE, and both
    eligibility gates were sized for the 12-hour producer window — the selector's
    `stalest <` test and the attempt marker, which `_ATTEMPT_TTL_SECONDS` pins to
    the same 12 hours. A game reached once therefore vanished for eleven of the
    next twelve hourly beats and could be 12 hours stale at kickoff, against an
    acceptance of under an hour.

    Both halves are guarded here. The SQL half — a warm imminent row re-entering
    while a warm ordinary row does not — is executed against real Postgres in
    `tests/integration/test_polymarket_kickoff_ordering_pg.py`, because a CASE in
    a WHERE clause is not something a string assertion can evaluate.
    """

    def test_imminent_game_reenters_on_the_next_hourly_beat(self):
        """The eligibility window for a kickoff row is under the beat interval.

        Asserted as the inequality rather than against the literal 45, because
        the property that matters is "strictly less than an hour" — a bound set
        to exactly 60 makes whether the next beat sees the row depend on which
        of the two fires first.
        """
        assert rail.KICKOFF_STALE_MINUTES < 60, (
            "a kickoff row must become eligible again INSIDE the hourly beat "
            "interval, or leading the queue buys it one refresh and no cadence"
        )
        # And the marker cannot outlive that window, or the marker IS the
        # window and the shorter one is decoration.
        assert rail._KICKOFF_ATTEMPT_TTL_SECONDS <= rail.KICKOFF_STALE_MINUTES * 60
        assert rail._KICKOFF_ATTEMPT_TTL_SECONDS < rail._ATTEMPT_TTL_SECONDS

    def test_the_marker_ttl_is_chosen_per_market_not_per_call(self):
        """A batch legitimately mixes the two classes — `_pack_batches` groups on
        id count, not on urgency — so one TTL for the call would give whichever
        class lost the coin toss the wrong cadence."""
        seen: dict[int, int] = {}

        class _Pipe:
            def setex(self, key, ttl, _val):
                seen[int(key.rsplit(":", 1)[1])] = ttl

            def execute(self):
                return None

        class _RC:
            def pipeline(self):
                return _Pipe()

        import app.tasks.redis_state as redis_state

        original = redis_state.get_redis_client
        redis_state.get_redis_client = lambda **kw: _RC()
        try:
            rail._mark_attempted([11, 22, 33], {22})
        finally:
            redis_state.get_redis_client = original

        assert seen[22] == rail._KICKOFF_ATTEMPT_TTL_SECONDS, (
            "the imminent market in a mixed batch did not get the short TTL"
        )
        assert seen[11] == rail._ATTEMPT_TTL_SECONDS
        assert seen[33] == rail._ATTEMPT_TTL_SECONDS

    def test_the_selector_gates_staleness_on_the_kickoff_class(self):
        sql = " ".join(rail._CANDIDATE_SQL.split())
        assert (
            f"WHEN p.kickoff IS NOT NULL THEN make_interval(mins => "
            f"{rail.KICKOFF_STALE_MINUTES})" in sql
        ), "the staleness gate does not branch on the kickoff class"
        assert "ELSE make_interval(hours => :stale_hours)" in sql, (
            "the ordinary class must keep the 12-hour producer window"
        )

    def test_the_imminent_set_travels_to_the_marker(self):
        """The flag is selected and carried, not recomputed downstream — two
        answers to "is this row imminent" is how they come to disagree."""
        sql = " ".join(rail._CANDIDATE_SQL.split())
        assert "(p.kickoff IS NOT NULL) AS imminent" in sql

        import inspect

        source = inspect.getsource(rail._refresh_stale_polymarket_conditions)
        assert "_mark_attempted([mid for mid, _ in batch], imminent_ids)" in source


class TestTheOrderingCannotStarveItsOwnTail:
    """A stalest-first ordering over a population it cannot always write is a
    fixed point waiting to happen: the rows that fail come back to the head of
    the queue on every run, forever, and the tail behind them is never reached.
    The ATTEMPT marker is what breaks it, so it is written on the attempt and
    not on the success."""

    async def test_a_batch_that_failed_is_still_marked_attempted(self, monkeypatch):
        marked: list[int] = []
        _arm(
            monkeypatch,
            candidates=[(7, ["0xaaa"])],
            stale=1,
            served=10,
            service=_Service(raises=RuntimeError("gamma 429")),
            marked=marked,
        )
        await rail._refresh_stale_polymarket_conditions()

        assert marked == [7]

    async def test_a_market_gamma_never_returns_is_still_marked(self, monkeypatch):
        """`not_returned` is the shape that would otherwise loop forever: the id
        is valid, the venue simply has nothing to say about it today."""
        marked: list[int] = []
        _arm(
            monkeypatch,
            candidates=[(7, ["0xaaa"]), (8, ["0xbbb"])],
            stale=2,
            served=10,
            service=_Service(markets=[_Market("0xaaa")]),
            writer=_writes,
            marked=marked,
        )
        stats = await rail._refresh_stale_polymarket_conditions()

        assert stats["not_returned"] == 1
        assert sorted(marked) == [7, 8]

    async def test_the_marker_expires_inside_the_staleness_window(self):
        """A marker that outlived the window would retire the row instead of
        rotating it — the same silence, one level down."""
        assert rail._ATTEMPT_TTL_SECONDS == rail.SERVED_STALE_HOURS * 3600

    def test_the_producer_window_is_below_the_bar_it_must_not_breach(self):
        """#3879's acceptance is 24h on tier 1-2. A producer window EQUAL to the
        bar makes the sweep permanently one cycle behind the breach it exists to
        prevent (`futures_price_refresh.REGISTERED_REFRESH_MINUTES`'s lesson)."""
        assert rail.SERVED_STALE_HOURS < 24


class TestTheUnitOfWorkIsTheWholeMarket:
    """A ladder with some legs from today and some from August is worse than a
    wholly stale one: the reader cannot tell that two numbers beside each other
    were observed thirteen days apart, and every comparison between them is
    false."""

    def test_selection_is_per_market_on_its_stalest_leg(self):
        """A market is due when its STALEST ungraded leg is stale, so the whole
        row is re-priced together rather than leg by leg."""
        sql = " ".join(rail._CANDIDATE_SQL.split())
        assert "MIN(COALESCE(fo.last_updated" in sql
        assert "fo.is_winner IS NOT TRUE" in sql

    def test_the_writer_is_the_shared_one_not_a_fork(self):
        """Reuse is the correctness argument, not a convenience: a second writer
        would be a second answer to what a Gamma market means for these rows —
        including #3868's both-copies-of-the-condition lookup, which is the only
        reason the ladder legs a league page renders get written at all."""
        import inspect

        source = inspect.getsource(rail._refresh_stale_polymarket_conditions)
        assert (
            "from app.tasks.tournament_price_refresh import _write_refreshed_prices"
            in source
        )

    async def test_every_fetched_market_reaches_that_writer(self, monkeypatch):
        """And it reaches it whole: the markets Gamma returned are handed over
        as a batch, so every leg of each condition is written in one pass."""
        seen: list[str] = []

        async def _capture(markets, stats, *, now):
            seen.extend(m.condition_id for m in markets)
            await _writes(markets, stats, now=now)

        _arm(
            monkeypatch,
            candidates=[(1, ["0xaaa"]), (2, ["0xbbb"])],
            stale=2,
            served=10,
            service=_Service(markets=[_Market("0xaaa"), _Market("0xbbb")]),
            writer=_capture,
        )
        await rail._refresh_stale_polymarket_conditions()

        assert seen == ["0xaaa", "0xbbb"]

    async def test_the_wall_budget_stops_between_markets_never_inside_one(
        self, monkeypatch
    ):
        """A run that stopped mid-market would leave exactly the half-refreshed
        ladder this rail exists to prevent."""
        conditions = [(i, [f"0x{i:03x}"]) for i in range(rail.BATCH_SIZE * 3)]
        clock = {"t": 0.0}
        monkeypatch.setattr(
            rail.time, "monotonic", lambda: clock.__setitem__("t", clock["t"] + 100.0) or clock["t"]
        )
        _arm(
            monkeypatch,
            candidates=conditions,
            stale=len(conditions),
            served=1_000,
            service=_Service(markets=[_Market("0xaaa")]),
            writer=_writes,
        )
        stats = await rail._refresh_stale_polymarket_conditions()

        # The clock passes 200s during the loop, so it stops early — and on a
        # batch boundary, which is what `batches` being a whole number of
        # completed fetches records.
        assert stats["wall_exhausted"] is True
        assert stats["batches"] < 3
        # It wrote something, so it is PARTIAL and not `failed` — and never
        # green, because a run the CLOCK bounded is a run whose sizing has
        # stopped being true.
        assert stats["terminal"] == "partial"
        assert stats["reason"] == "wall_exhausted"
        assert verdict_for("polymarket_condition_refresh", stats).is_green is False


class TestTheOrderingIsAcceptanceOneMadeMechanical:
    """#3879's acceptance 1 names tier 1 and 2 specifically, and a 1,200-market
    budget over a 13,746-market population only meets it if those rows are taken
    FIRST. The ordering is the whole guarantee; a budget without it is a
    lottery."""

    def test_tier_one_and_two_are_priority(self):
        sql = " ".join(rail._CANDIDATE_SQL.split())
        assert "fm.market_tier IN (1, 2)" in sql

    def test_an_imminent_market_is_priority_whatever_its_tier(self):
        """9,281 legs sit in the ≤2d bucket. An imminent question is the one a
        reader is most likely to be looking at."""
        sql = " ".join(rail._CANDIDATE_SQL.split())
        assert f"make_interval(days => {rail.IMMINENT_DAYS})" in sql
        assert rail.IMMINENT_DAYS == 2

    def test_priority_leads_and_the_stalest_of_a_class_is_next(self):
        """Within a class it is stalest-first, which is what stops a member of
        that class being passed over twice for the same reason.

        #4896 put one key in front of this and changed nothing else: the tail of
        the ORDER BY is asserted whole, so a change to either surviving key
        still fails here.
        """
        sql = " ".join(rail._CANDIDATE_SQL.split())
        assert "p.priority DESC, s.stalest ASC" in sql

    def test_a_game_about_to_be_played_leads_even_that(self):
        """#4896: staleness cannot express urgency.

        A 90-day-old election price is always "staler" than a game starting in
        two hours, so under a budget the game is a permanent loss. Measured
        2026-09-10 20:5xZ: `Pegula vs Sabalenka` (on court 23:00Z) ranked 7,947
        of 10,675 and `Rybakina vs Gauff` 10,667, both below `CANDIDATE_LIMIT`
        3,600 — unselectable, not merely starved, because a Polymarket game
        market carries tier 5 and a `resolution_date` a WEEK after the fixture
        so neither arm of `priority` fires.

        That the key SORTS correctly is proved against real Postgres in
        `tests/integration/test_polymarket_kickoff_ordering_pg.py`; this is the
        guard that stops it being deleted.
        """
        sql = " ".join(rail._CANDIDATE_SQL.split())
        assert (
            "ORDER BY p.kickoff ASC NULLS LAST, p.priority DESC, s.stalest ASC" in sql
        )

    def test_the_kickoff_key_reads_the_event_clock_not_the_market_one(self):
        """The whole point: `resolution_date` is a padded venue window for a
        game market, and the event row already knows when the game starts."""
        sql = " ".join(rail._CANDIDATE_SQL.split())
        assert " ".join(rail._KICKOFF_SQL.split()) in sql
        assert "e.commence_time" in sql
        assert "e.completed_at IS NULL" in sql
        assert f"make_interval(hours => {rail.KICKOFF_LEAD_HOURS})" in sql
        assert f"make_interval(hours => {rail.KICKOFF_TAIL_HOURS})" in sql

    def test_the_events_join_cannot_shrink_the_pool(self):
        """6,337 of the pool are futures with no event at all. An inner join
        would drop every one of them and the census would report the loss as a
        healthy smaller number."""
        sql = " ".join(rail._CANDIDATE_SQL.split())
        assert "LEFT JOIN events e ON e.id = fm.event_id" in sql

    def test_the_horizon_is_the_full_twenty_four_hours_the_issue_names(self):
        """CERT-2549's guard: the lead may not be narrowed to fit the budget.

        #4896's acceptance is "every event kicking off within 24h". A cut of
        this ship set 12 because the 24h class costs 656 ids a beat of a
        1,000-id `CONDITION_BUDGET` — which met the bar for the last half-day
        and quietly dropped games 12-24h out back onto the ordinary 12-hour
        window. Narrowing the horizon to fit the budget is amending the
        acceptance, not meeting it, so the floor is asserted here and the far
        edge is exercised behaviourally by
        `test_game_twenty_hours_from_kickoff_reenters_on_the_next_hourly_beat`.
        """
        assert rail.KICKOFF_LEAD_HOURS >= 24, (
            "#4896 requires every game inside 24h to hold the game cadence; a "
            "shorter lead leaves the 12-24h band on the ordinary window"
        )
        assert 0 < rail.KICKOFF_TAIL_HOURS <= rail.KICKOFF_LEAD_HOURS

    def test_the_kickoff_class_still_fits_inside_one_run(self):
        """The cost of that horizon, stated as a bound rather than buried.

        MEASURED on the live pool, production 2026-09-10 22:1xZ, per BEAT with
        `KICKOFF_STALE_MINUTES` in force:

             6h -> 130 markets / 341 ids   12h -> 137 / 348   24h -> 230 / 656

        656 of 1,000 is two thirds of every run, leaving ~344 for #4827's
        backlog rotation. That is the accepted trade — the rotation is a
        transient catch-up and the kickoff class is permanent — but it only
        holds while the class still FITS. The eligibility window is what sets
        the class's per-beat size, so it is the thing guarded: shortening it
        further multiplies the cost, and at some point the drain reaches zero
        and this rail does nothing but re-read tonight's games.
        """
        assert rail.KICKOFF_STALE_MINUTES >= 45, (
            "a shorter kickoff window re-admits the class more often than "
            "hourly and eats the backlog drain; 45 min already re-admits it "
            "on every beat, which is all the acceptance asks for"
        )
        assert rail.KICKOFF_STALE_MINUTES < 60

    def test_the_budget_still_leaves_the_backlog_drain_a_real_share(self):
        """The other half of the trade, and the half nothing else asserts.

        `test_the_kickoff_class_still_fits_inside_one_run` pins the window that
        sizes the class. It cannot see the other operand: `CONDITION_BUDGET` is
        what the class is spent AGAINST, and lowering it starves #4827's drain
        just as surely as widening the horizon does. At the measured 24h cost
        the two numbers are 656 and 1,000, and nothing in this file would fire
        if the budget were cut to 700 and the drain silently went to ~44 ids a
        beat over a ~54,000-id population — which is the rail doing nothing but
        re-reading tonight's games, the exact failure the blocked cut was
        blocked for.

        So the guard is on the DIFFERENCE, not on either constant alone.
        """
        # MEASURED, production 2026-09-10 22:1xZ, 24h lead, per beat. The upper
        # end of the observed 539-656 range, because a floor argued from the
        # cheap end of a range is not a floor.
        KICKOFF_CLASS_IDS_MEASURED = 656
        # What the drain needs to stay a drain rather than a rounding error.
        DRAIN_FLOOR_IDS = 300

        drain = rail.CONDITION_BUDGET - KICKOFF_CLASS_IDS_MEASURED
        assert drain >= DRAIN_FLOOR_IDS, (
            f"the kickoff class costs ~{KICKOFF_CLASS_IDS_MEASURED} ids a beat "
            f"and CONDITION_BUDGET is {rail.CONDITION_BUDGET}, leaving {drain} "
            f"for #4827's backlog rotation — below the {DRAIN_FLOOR_IDS} floor. "
            "Either raise the budget or re-measure the class; do NOT narrow "
            "KICKOFF_LEAD_HOURS, which is what CERT-2549 blocked."
        )

    def test_the_budget_and_the_window_are_one_sizing(self):
        """1,200 x 12 = 14,400 against the 13,746 served markets measured on
        production 2026-09-08. A budget that could not cover the population
        inside one staleness window would leave a permanent unreachable tail
        however the ordering was written."""
        assert rail.MARKET_BUDGET * rail.SERVED_STALE_HOURS >= 13_746

    def test_the_id_budget_is_sized_under_the_wall_and_not_at_it(self):
        """#4827: the cap that has to be true of a run is the CONDITION-ID one,
        and it is sized against measured throughput, not against the population.

        Production `task-metrics` 2026-09-10 16:09Z: 452 conditions, 1,311
        outcomes + 1,311 snapshots, 73.1 s. That is ~0.162 s per condition, so
        the id budget times that rate has to leave real room under
        `_TIME_BUDGET_S` — a budget sized AT the wall would make
        `wall_exhausted` the normal terminal, and `wall_exhausted` is reported as
        PARTIAL. An alarm that fires every run is not an alarm."""
        measured_seconds_per_condition = 73.1 / 452
        projected = rail.CONDITION_BUDGET * measured_seconds_per_condition
        assert projected < rail._TIME_BUDGET_S
        # Not merely under it: under it with a fifth of the wall to spare, so a
        # slow Gamma hour does not flip the terminal.
        assert projected < rail._TIME_BUDGET_S * 0.85


class TestTheFetchCanSeeAResult:
    """#3868, inherited deliberately. `/markets?condition_ids=…` applies a
    `closed=false` filter the caller never asked for, so without
    `include_closed` a leg that settles stops coming back at all — it lands in
    `not_returned`, nothing is written, and the last LIVE price is frozen on the
    page for good."""

    async def test_the_rail_asks_for_closed_books_too(self, monkeypatch):
        service = _Service(markets=[_Market("0xaaa")])
        _arm(
            monkeypatch,
            candidates=[(1, ["0xaaa"])],
            stale=1,
            served=10,
            service=service,
            writer=_writes,
        )
        await rail._refresh_stale_polymarket_conditions()

        assert service.asked_include_closed is True


class TestTheCensusTravelsWithEveryRun:
    """#3879 acceptance 2: the staleness of the served population is readable
    from the rail's own terminal, not only from an ad-hoc query. A refresh rail
    that silently stops must not read as healthy — and this one's surface cannot
    show that it stopped, because the pages keep rendering."""

    async def test_a_working_run_reports_the_population_it_is_responsible_for(
        self, monkeypatch
    ):
        _arm(
            monkeypatch,
            candidates=[(1, ["0xaaa"])],
            stale=6_470,
            served=22_034,
            service=_Service(markets=[_Market("0xaaa")]),
            writer=_writes,
        )
        stats = await rail._refresh_stale_polymarket_conditions()

        assert stats["served_markets"] == 22_034
        assert stats["stale_markets"] == 6_470

    async def test_a_quiet_run_still_reports_it(self, monkeypatch):
        """"13,746 served, none stale" is a healthy quiet run; "0 served" is a
        broken selector wearing one. Without the census they are the same line."""
        _arm(monkeypatch, candidates=[], stale=0, served=22_034)
        stats = await rail._refresh_stale_polymarket_conditions()

        assert stats["served_markets"] == 22_034
        assert stats["stale_markets"] == 0

    def test_the_census_costs_no_second_scan_on_a_working_run(self):
        """Both numbers come off the selector the run already executed — a
        window count taken before the LIMIT, and the pool's own size."""
        sql = " ".join(rail._CANDIDATE_SQL.split())
        assert "COUNT(*) OVER () AS stale_markets" in sql
        assert "(SELECT COUNT(*) FROM pool) AS served_markets" in sql
        assert "MATERIALIZED" in sql

    async def test_the_budget_binding_is_reported_and_is_not_an_alarm(
        self, monkeypatch
    ):
        """A steady-state rotation over 22,034 markets has the budget binding on
        every run, forever. Reporting THAT as PARTIAL would be an alarm that can
        never clear; the census is what carries the growth signal instead."""
        conditions = [(i, [f"0x{i:03x}"]) for i in range(5)]
        _arm(
            monkeypatch,
            candidates=conditions,
            stale=6_470,
            served=22_034,
            service=_Service(markets=[_Market("0xaaa")]),
            writer=_writes,
        )
        stats = await rail._refresh_stale_polymarket_conditions(budget=2)

        assert stats["conditions_requested"] == 2
        assert stats["budget_exhausted"] is True
        assert stats["terminal"] == "complete"
        assert verdict_for("polymarket_condition_refresh", stats).is_green is True


class TestTheEighthPriceAskerAsksTheSharedQuestion:
    """CERT-452's finding, one rail later. That cert's census enumerated a fixed
    dictionary of six price askers, so it could not discover a seventh — and the
    seventh was `tournament_price_refresh`, running every ten minutes, filtering
    on no liveness signal at all. This is the eighth, and it composes the shared
    predicate rather than hand-copying a WHERE clause."""

    def test_the_selector_composes_the_shared_predicate(self):
        from app.utils import futures_liveness

        def _norm(s: str) -> str:
            return " ".join(s.split()).lower()

        assert _norm(futures_liveness.LIVE_MARKET_SQL) in _norm(rail._CANDIDATE_SQL)

    def test_the_census_fallback_composes_it_too(self):
        """The two must report on the SAME population or the census describes a
        set the rail does not sweep."""
        from app.utils import futures_liveness

        def _norm(s: str) -> str:
            return " ".join(s.split()).lower()

        assert _norm(futures_liveness.LIVE_MARKET_SQL) in _norm(rail._SERVED_COUNT_SQL)
        # #4827: and the ADDRESSABILITY half is shared the same way, from one
        # constant. A census counting a population the selector cannot address —
        # or refusing one it can — is the same defect this class is about, just
        # pointed the other way.
        assert _norm(rail._ADDRESSABLE_LEG_SQL) in _norm(rail._SERVED_COUNT_SQL)
        assert _norm(rail._ADDRESSABLE_LEG_SQL) in _norm(rail._CANDIDATE_SQL)

    def test_it_filters_before_the_venue_fetch(self):
        """A retired market must also stop costing a Gamma request."""
        import inspect

        source = inspect.getsource(rail._refresh_stale_polymarket_conditions)
        assert source.index("_select_stale_conditions(") < source.index(
            "get_markets_by_conditions("
        )

    def test_the_population_is_the_condition_addressable_one(self):
        """#4827 amends the claim this test used to make, and keeps its point.

        The old fence was `fm.external_id LIKE '0x%'` on the MARKET row, and its
        reason — "an event-keyed row addressed this way is a request that cannot
        return" — is still true and still honoured: no event id is ever sent to
        `/markets?condition_ids=…`. What was wrong was treating the market row as
        the only place a condition id can live. The fence is now the legs, which
        is where 7,608 live markets kept theirs."""
        sql = " ".join(rail._CANDIDATE_SQL.split())
        assert "fm.source = 'polymarket'" in sql
        assert "fo_a.external_id LIKE '0x%'" in sql
        # And the request ids come from a condition-shaped source on both arms —
        # the market's own id when it is one, the legs' otherwise.
        assert "WHEN p.external_id LIKE '0x%' THEN ARRAY[p.external_id]" in sql
        assert "regexp_replace(fo.external_id, '_(yes|no)$', '')" in sql


class TestALadderIsAddressedByItsLegs:
    """#4827. The pool's old fence read `fm.external_id LIKE '0x%'` on the MARKET
    row, and 7,608 live markets kept their condition ids one level down, on the
    legs — 35,244 of them, 35,244 of 35,244, 10,201 unread for 30 days. Nothing
    addressed those rows at all: not this rail, not `futures_price_refresh`'s
    volume arm, not the register. This class guards the two things that had to
    become true for a ladder to travel: the ids are a LIST, and the budget that
    binds a run counts IDS.
    """

    def test_a_market_is_never_split_across_two_gamma_requests(self):
        """The unit of work is the whole market and the wall check runs BETWEEN
        batches, so a ladder split across the boundary is exactly the
        half-refreshed row this rail exists to prevent. Slicing `due` by market
        count — what the code did when every market was one id — splits it."""
        due = [(1, [f"0xa{i}" for i in range(30)]), (2, [f"0xb{i}" for i in range(30)])]
        batches = rail._pack_batches(due)

        # Two batches, one market each — never 30 ids of market 1 plus 10 of
        # market 2 in the first request and market 2's remaining 20 in a second.
        assert [[mid for mid, _ in b] for b in batches] == [[1], [2]]
        # And every id travels exactly once, with its own market.
        assert [cid for b in batches for _, cids in b for cid in cids] == [
            cid for _, cids in due for cid in cids
        ]

    def test_small_markets_share_a_request_up_to_the_url_bound(self):
        """`BATCH_SIZE` is a property of the URL, not of our bookkeeping: a query
        string with hundreds of repeated parameters is a 414 in waiting."""
        due = [(i, [f"0x{i:03x}"]) for i in range(rail.BATCH_SIZE + 1)]
        batches = rail._pack_batches(due)

        assert len(batches) == 2
        assert sum(len(cids) for _, cids in batches[0]) == rail.BATCH_SIZE
        assert sum(len(cids) for _, cids in batches[1]) == 1

    def test_a_ladder_wider_than_the_url_bound_still_gets_a_request(self):
        """It goes alone and `get_markets_by_conditions` chunks it internally —
        the whole market still reaches the writer in one call. Dropping it would
        make the widest ladders (128 legs on the 2028 presidential field)
        permanently unreachable while sitting at the head of the ordering."""
        wide = [(1, [f"0x{i:03x}" for i in range(rail.BATCH_SIZE * 2)])]
        batches = rail._pack_batches(wide)

        assert len(batches) == 1
        assert len(batches[0][0][1]) == rail.BATCH_SIZE * 2

    async def test_every_id_the_selector_produced_is_asked_for(self, monkeypatch):
        """No event id is ever sent — the selector decides the ids and the loop
        forwards exactly those. That is the old test's claim, kept."""
        service = _Service(markets=[_Market("0xaaa")])
        _arm(
            monkeypatch,
            candidates=[(1, ["0xaaa", "0xbbb"]), (2, ["0xccc"])],
            stale=2,
            served=10,
            service=service,
            writer=_writes,
        )
        await rail._refresh_stale_polymarket_conditions()

        assert [cid for call in service.calls for cid in call] == [
            "0xaaa",
            "0xbbb",
            "0xccc",
        ]

    async def test_the_budget_that_binds_counts_ids_not_markets(self, monkeypatch):
        """A market cost one id when every pool row was a bare condition. A
        ladder costs one per leg and the pool's ladders average 6.5, so a market
        cap alone would let one run ask for thousands of ids on a wall measured
        at 452."""
        _arm(
            monkeypatch,
            candidates=[(i, [f"0x{i}{j}" for j in range(10)]) for i in range(9)],
            stale=9,
            served=100,
            service=_Service(markets=[_Market("0xaaa")]),
            writer=_writes,
        )
        stats = await rail._refresh_stale_polymarket_conditions(
            budget=1_000, condition_budget=25
        )

        # Whole markets only: two fit under 25 ids, the third would take it to 30.
        assert stats["markets_due"] == 2
        assert stats["conditions_requested"] == 20
        assert stats["budget_exhausted"] is True

    async def test_the_market_cap_still_binds_when_it_is_the_smaller_one(
        self, monkeypatch
    ):
        """Both caps are enforced. Keeping the market cap is what stops a run of
        one-id markets from issuing 1,000 write loops on a wall sized for 452."""
        _arm(
            monkeypatch,
            candidates=[(i, [f"0x{i:03x}"]) for i in range(50)],
            stale=50,
            served=100,
            service=_Service(markets=[_Market("0xaaa")]),
            writer=_writes,
        )
        stats = await rail._refresh_stale_polymarket_conditions(
            budget=3, condition_budget=1_000
        )

        assert stats["markets_due"] == 3
        assert stats["conditions_requested"] == 3

    async def test_a_ladder_wider_than_the_whole_id_budget_is_still_admitted(
        self, monkeypatch
    ):
        """Otherwise it is a fixed point: permanently unreachable AND permanently
        at the head of a stalest-first ordering, which is the starvation shape the
        attempt markers exist to break."""
        _arm(
            monkeypatch,
            candidates=[(1, [f"0x{i:03x}" for i in range(200)])],
            stale=1,
            served=10,
            service=_Service(markets=[_Market("0xaaa")]),
            writer=_writes,
        )
        stats = await rail._refresh_stale_polymarket_conditions(condition_budget=5)

        assert stats["markets_due"] == 1
        assert stats["conditions_requested"] == 200

    async def test_a_zero_id_budget_refreshes_nothing_and_says_which_cap_did_it(
        self, monkeypatch
    ):
        """The always-admit-the-first rule must not swallow an explicit
        instruction to do nothing — `no_budget` and `all_recently_attempted` are
        different states and this file has already argued that once."""
        _arm(
            monkeypatch,
            candidates=[(1, ["0xaaa"])],
            stale=1,
            served=10,
            service=_Service(markets=[_Market("0xaaa")]),
            writer=_writes,
        )
        stats = await rail._refresh_stale_polymarket_conditions(condition_budget=0)

        assert stats["markets_due"] == 0
        assert stats["terminal"] == "no_work"
        assert stats["reason"] == "no_budget"
        assert verdict_for("polymarket_condition_refresh", stats).is_green is False


class TestTheSelectorAndTheWriterRefuseTheSameLeg:
    """#4840. `futures_liveness` exists because "fix and guard cannot disagree
    about what they cover", and it settled that argument for the MARKET bound.
    The same disagreement then ran one level down, on the LEG:

    * the writer refused `is_winner IS NOT TRUE` AND `resolution_source <>
      'api_settlement'`;
    * this selector refused only the first.

    A leg with `is_winner = false` and `resolution_source = 'api_settlement'` was
    therefore selectable and unwritable. Its `last_updated` can never advance, so
    it is permanently the stalest thing in its class, and the ordering is
    `stalest ASC` — it pinned its market to the head of the queue forever while
    markets below the LIMIT were never reached.

    Measured on production 2026-09-10, first 3,600 candidates: 365 carried such a
    leg and **155 had no writable leg at all**. With the shared refusal composed
    here, run from this module's own `_CANDIDATE_SQL`: fully-unwritable
    **155 → 0** (19:13Z), and the statement got faster, 3,984 ms → 709 ms.

    🔴 REACH, not just purity — the question a narrowing always has to answer is
    what it dropped that it should have kept. Production 19:17Z, old probe AND
    NOT new probe, over `LIVE_MARKET_SQL` × polymarket: **781 markets leave the
    pool, and 0 of them have an ungraded, non-`api_settlement`, `0x`-keyed leg.**
    Every row removed is one this rail could select and could never write.

    These are COMPOSITION guards — they prove the two sites cannot state the
    refusal differently, which is the drift that caused the defect. The
    behavioural before/after is the production measurement above, recorded on
    #4840; there is no local Postgres in this suite to re-run it against.
    """

    @staticmethod
    def _norm(s: str) -> str:
        return " ".join(s.split()).lower()

    def test_both_leg_refusals_come_from_the_one_shared_definition(self):
        """Acceptance 1: the selector's per-leg refusal and the writer's are the
        same text, from one place."""
        import inspect

        from app.tasks import tournament_price_refresh
        from app.utils.futures_liveness import writable_leg_sql

        # The selector composes it — rendered, so a renamed helper that stopped
        # being called would fail here rather than pass on the import alone.
        assert self._norm(writable_leg_sql("fo")) in self._norm(rail._CANDIDATE_SQL)
        assert self._norm(writable_leg_sql("fo_a")) in self._norm(
            rail._ADDRESSABLE_LEG_SQL
        )

        # And so does the writer, at its own call site rather than anywhere in
        # the module.
        writer_source = inspect.getsource(
            tournament_price_refresh._write_refreshed_prices
        )
        assert 'writable_leg_sql("fo")' in writer_source

    def test_the_refusal_names_both_clauses(self):
        """RED CONTROL. Narrowing the shared definition back to `is_winner`
        alone — the exact regression #4840 describes — fails here, and fails at
        every call site at once because they all render this one function."""
        from app.utils.futures_liveness import writable_leg_sql

        rendered = self._norm(writable_leg_sql("fo"))
        assert "fo.is_winner is not true" in rendered
        assert "coalesce(fo.resolution_source, '') <> 'api_settlement'" in rendered

    def test_it_coalesces_because_resolution_source_is_nullable(self):
        """`resolution_source` is NULL for the overwhelming majority of ungraded
        legs. A bare `<> 'api_settlement'` is NULL for those rows — not TRUE —
        so it would refuse every leg in the database and the rail would write
        nothing. The COALESCE is the whole predicate's load-bearing half."""
        from app.utils.futures_liveness import writable_leg_sql

        rendered = self._norm(writable_leg_sql("fo"))
        assert "coalesce(fo.resolution_source" in rendered
        assert "fo.resolution_source <>" not in rendered

    def test_the_alias_is_honoured_on_every_binding(self):
        """Three call sites bind three aliases to `futures_outcomes`. A constant
        that hard-coded `fo.` would have been hand-copied for `fo_a`, which is
        how the fourth copy — and the next drift — gets typed."""
        from app.utils.futures_liveness import writable_leg_sql

        for alias in ("fo", "fo_a", "fo_w"):
            rendered = writable_leg_sql(alias)
            assert f"{alias}.is_winner" in rendered
            assert f"{alias}.resolution_source" in rendered

    def test_the_census_and_the_selector_still_agree(self):
        """#4827's invariant, re-asserted because #4840 moves the shared
        addressability probe: the census must not count a population the
        selector refuses. Both compose `_ADDRESSABLE_LEG_SQL`, so the leg
        refusal lands in both — production, 19:13Z, `served_markets` 16,755 →
        15,954 in step."""
        assert self._norm(rail._ADDRESSABLE_LEG_SQL) in self._norm(
            rail._SERVED_COUNT_SQL
        )
        assert self._norm(rail._ADDRESSABLE_LEG_SQL) in self._norm(rail._CANDIDATE_SQL)


def test_the_module_never_creates_a_market_or_an_outcome():
    """Stated as a test because it is the boundary between this rail and the
    discovery scan: it re-prices rows that exist and nothing else."""
    import inspect

    source = inspect.getsource(rail)
    assert "INSERT INTO futures_markets" not in source
    assert "find_or_create" not in source


def test_the_wall_budget_leaves_room_under_the_soft_limit():
    """The task's soft limit is 300s. A loop budget at or above it would be
    enforced by SIGTERM instead of by the check between batches — mid-market."""
    from app.tasks import celery_app

    task = celery_app.tasks["app.tasks.refresh_stale_polymarket_conditions"]
    assert rail._TIME_BUDGET_S < task.soft_time_limit
