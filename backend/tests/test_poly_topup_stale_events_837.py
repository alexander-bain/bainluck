"""#837 — a finished game's legs leave the ask, so a live game's line is reached.

THE SHIP. A live fixture's Polymarket winner line gets a CLOB token — and so
streams, instead of sitting on the 120 s poll sawtooth — within two socket
recycles instead of seven.

THE DEFECT, measured on production 2026-09-17 07:0xZ. The caller's slate is
``Event.status = 'live' OR (status = 'scheduled' AND commence_time <= NOW() +
6h)``. That window has no LOWER bound, so an event stuck at 'scheduled' whose
game kicked off weeks ago satisfies it for ever. Of 4,148 slate outcomes, 3,050
sat on markets whose event had commenced up to fifteen weeks earlier (2,996 of
them more than 12 h ago) — Sivasspor vs. Mardin 1969 Spor from September 2 was
still being asked about on September 17. The ask was 73% dead. Every capped pass
read ``1011 outcomes needed tokens, capped at 300`` and then ``300 asked, 0
returned by Gamma`` on a 200 OK, because ``/markets?condition_ids=`` defaults to
open-only and answers a settled id with an empty 200 (gotcha #53).

Distinct condition ids the ask carries, by lower bound, same hour:

    no bound  1,803        12 h  581        24 h  581
       48 h    581          7 d  589

Bimodal — today's fixtures, then corpses — so ``STALE_EVENT_HOURS`` sits on a
flat plateau and is not a tuned constant. 1,803 -> 581 takes the cycle from
ceil(1803/300) = 7 passes to ceil(581/300) = 2.

WHY NOT A SETTLEMENT COLUMN, which is the trap this file exists to keep shut.
``FuturesMarket.status = 'resolved'`` is the obvious predicate and it is WRONG:
measured the same hour, the four live ITF tennis legs #837 is about (W35 Kyoto,
Phan Thiet 4 — events 15313682 / 15313516 / 15313625) were themselves
``status = 'resolved'`` WHILE STILL IN PLAY, carrying ``is_winner = False`` on
both contenders, which is the column's default rather than a settlement.
Filtering on it would have dropped exactly the legs the ship is for. Polymarket
settlement is only ever written by the WebSocket ``market_resolved`` handler, so
a leg that never had a token was never subscribed and can never have been
marked settled by it — the signal is circular on precisely the population that
matters. ``settled_at`` is no better: NULL on 66 of 576 sampled corpses, and the
model says it is never backfilled.

``test_a_live_market_marked_resolved_is_still_asked`` is that case, pinned.

AND AGE ALONE MAY NOT DROP A LEG EITHER, which is the other half of the
predicate and the reason ``TestAgeAloneMayNotDropALeg`` exists. The caller's
slate admits an event on either of two statuses, and an event that reached
``'live'`` is the event graph saying the game is happening NOW. Aging that out
on a clock would drop exactly the live winner line this ship is for — a
multi-day competition, a fixture whose row is advanced late, any event whose
start time is wrong in the stale direction. So the drop requires BOTH a known
old start AND an event still sitting at ``STALE_EVENT_STATUS``; every unknown
keeps its leg.

The guard is free. Measured on production 2026-09-17 07:5xZ: of the slate legs
past the bound, 2,996 of 2,996 are ``'scheduled'`` and NO live event of that age
exists anywhere in the table — the newest dropped leg starts 2026-09-06, nine
days clear of the 48 h line. Deleting the status clause turns this module back
into the age-alone version and reddens the four ``TestAgeAloneMayNotDropALeg``
cases and NOTHING else: the fourteen tests above still pass, which is the proof
that the clause guards a class of wrong drop without costing the repair a leg.
"""

from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy.sql.dml import Update

from app.tasks.polymarket_token_topup import (
    OUTCOME_TOKEN_METADATA_KEY,
    STALE_EVENT_HOURS,
    STALE_EVENT_STATUS,
    topup_outcome_clob_tokens,
)

SCHEDULED = STALE_EVENT_STATUS
LIVE_STATUS = "live"

assert LIVE_STATUS != STALE_EVENT_STATUS, (
    "the live-exemption tests below are vacuous if the two statuses collide"
)

NOW = datetime.now(timezone.utc)
FRESH = NOW - timedelta(hours=1)
STALE = NOW - timedelta(days=14)

# Lexicographically ORDERED so the cap tests below mean something: under the
# defect the corpses sort first and take every seat.
CORPSE_A = "0x1111111111111111111111111111111111111111111111111111111111111111"
CORPSE_B = "0x2222222222222222222222222222222222222222222222222222222222222222"
LIVE = "0x9999999999999999999999999999999999999999999999999999999999999999"

assert CORPSE_A < CORPSE_B < LIVE, (
    "the defect is lexicographic — if the live leg ever sorts first, the cap "
    "tests here pass for the wrong reason"
)

CORPSE_A_MARKET, CORPSE_A_OUTCOME = 101, 9001
CORPSE_B_MARKET, CORPSE_B_OUTCOME = 102, 9002
LIVE_MARKET, LIVE_OUTCOME = 103, 9003
LIVE_NAME = "Boston Red Sox"
LIVE_TOKEN = "7" * 77


class _FakeMarket:
    def __init__(self, condition_id, clob_token_ids, outcomes):
        self.condition_id = condition_id
        self.clob_token_ids = list(clob_token_ids)
        self.outcomes = list(outcomes)


class _FakeService:
    """Gamma. Answers only the live market — a closed id is an empty 200."""

    def __init__(self, markets=None):
        self._markets = list(
            markets
            if markets is not None
            else [_FakeMarket(LIVE, [LIVE_TOKEN, "8" * 77], [LIVE_NAME, "Texas Rangers"])]
        )
        self.asked: list[list[str]] = []
        self.closed = False

    async def get_markets_by_conditions(self, condition_ids, **_kw):
        self.asked.append(list(condition_ids))
        wanted = set(condition_ids)
        return [m for m in self._markets if m.condition_id in wanted]

    async def close(self):
        self.closed = True


class _Rows:
    def __init__(self, rows):
        self._rows = list(rows)

    def all(self):
        return list(self._rows)


class _HalfDeadRows:
    """``.all()`` yields real rows and then raises, as a severed cursor does."""

    def __init__(self, rows):
        self._rows = list(rows)

    def all(self):
        for row in self._rows:
            yield row
        raise RuntimeError("connection lost mid-cursor")


class _Session:
    """Answers the market read (metadata + event start time + status), then names.

    ``commence_by_market`` is the whole point: a market absent from it answers
    with ``None``, which is "start time unknown" and must NOT be treated as
    stale.

    Its value is either a bare start time — read as an event still sitting at
    ``'scheduled'``, which is the corpse shape — or an explicit
    ``(commence_time, status)`` pair when a test needs to say otherwise.
    """

    def __init__(self, commence_by_market, names, *, stored=None, raises=None):
        self.commence_by_market = commence_by_market
        self.names = names
        self.stored = stored or {}
        self.updates: list = []
        self._raises = raises
        self._n = 0

    @staticmethod
    def _split(value):
        if isinstance(value, tuple):
            return value
        return value, SCHEDULED

    async def execute(self, stmt):
        if isinstance(stmt, Update):
            self.updates.append(stmt)
            return _Rows([])
        self._n += 1
        if self._n == 1:
            if self._raises:
                raise self._raises
            return _Rows(
                [
                    (
                        mid,
                        {OUTCOME_TOKEN_METADATA_KEY: self.stored[mid]}
                        if mid in self.stored
                        else None,
                        *self._split(value),
                    )
                    for mid, value in self.commence_by_market.items()
                ]
            )
        return _Rows(list(self.names.items()))


def _targets(*legs):
    return list(legs)


CORPSE_A_LEG = (CORPSE_A_MARKET, CORPSE_A_OUTCOME, CORPSE_A)
CORPSE_B_LEG = (CORPSE_B_MARKET, CORPSE_B_OUTCOME, CORPSE_B)
LIVE_LEG = (LIVE_MARKET, LIVE_OUTCOME, LIVE)

ALL_THREE = _targets(CORPSE_A_LEG, CORPSE_B_LEG, LIVE_LEG)
NAMES = {CORPSE_A_OUTCOME: "x", CORPSE_B_OUTCOME: "y", LIVE_OUTCOME: LIVE_NAME}


def _session(commence, **kw):
    return _Session(commence, dict(NAMES), **kw)


BOTH_CORPSES_STALE = {
    CORPSE_A_MARKET: STALE,
    CORPSE_B_MARKET: STALE,
    LIVE_MARKET: FRESH,
}


class TestTheCorpsesLeaveTheAsk:
    @pytest.mark.asyncio
    async def test_a_finished_games_legs_are_not_asked(self):
        service = _FakeService()
        await topup_outcome_clob_tokens(
            _session(BOTH_CORPSES_STALE), ALL_THREE, service=service
        )
        assert service.asked == [[LIVE]], (
            "only the live leg should reach Gamma; the two weeks-old ones are "
            f"corpses. Asked: {service.asked}"
        )

    @pytest.mark.asyncio
    async def test_the_live_leg_is_reached_in_the_same_pass_under_a_cap_of_one(self):
        """The money test: the cap used to be spent entirely on corpses.

        With ``max_outcomes=1`` and three legs, the pre-filter window takes the
        lexicographic head — ``CORPSE_A`` — and the live leg waits. Filtering
        first leaves one askable leg, so the cap stops binding at all.
        """
        service = _FakeService()
        filled = await topup_outcome_clob_tokens(
            _session(BOTH_CORPSES_STALE), ALL_THREE, service=service, max_outcomes=1
        )
        assert service.asked == [[LIVE]]
        assert filled == {LIVE_OUTCOME: (LIVE_MARKET, LIVE_TOKEN)}

    @pytest.mark.asyncio
    async def test_an_all_stale_slate_asks_gamma_nothing(self):
        service = _FakeService()
        filled = await topup_outcome_clob_tokens(
            _session({CORPSE_A_MARKET: STALE, CORPSE_B_MARKET: STALE}),
            _targets(CORPSE_A_LEG, CORPSE_B_LEG),
            service=service,
        )
        assert service.asked == []
        assert filled == {}


class TestUnknownIsNeverStale:
    """Only a POSITIVELY KNOWN old start time may drop a leg."""

    @pytest.mark.asyncio
    async def test_a_null_start_time_keeps_its_leg(self):
        service = _FakeService()
        await topup_outcome_clob_tokens(
            _session({CORPSE_A_MARKET: None, LIVE_MARKET: FRESH}),
            _targets(CORPSE_A_LEG, LIVE_LEG),
            service=service,
        )
        assert sorted(service.asked[0]) == sorted([CORPSE_A, LIVE])

    @pytest.mark.asyncio
    async def test_a_market_with_no_linked_event_keeps_its_leg(self):
        """The outer join yields no row at all for it — still asked."""
        service = _FakeService()
        await topup_outcome_clob_tokens(
            _session({LIVE_MARKET: FRESH}),
            _targets(CORPSE_A_LEG, LIVE_LEG),
            service=service,
        )
        assert sorted(service.asked[0]) == sorted([CORPSE_A, LIVE])

    @pytest.mark.asyncio
    async def test_a_failed_read_drops_nothing(self):
        """Fail OPEN. A bookkeeping outage must never shrink the ask."""
        service = _FakeService()
        await topup_outcome_clob_tokens(
            _session(BOTH_CORPSES_STALE, raises=RuntimeError("db gone")),
            ALL_THREE,
            service=service,
        )
        assert sorted(service.asked[0]) == sorted([CORPSE_A, CORPSE_B, LIVE])

    @pytest.mark.asyncio
    async def test_a_read_that_dies_PART_WAY_drops_nothing_either(self):
        """The case the previous test cannot see, found by mutation.

        A fake that raises on the first call leaves ``stale_market_ids`` empty
        anyway, so it passes whether or not the except branch resets it. A read
        that yields some rows and THEN dies leaves PARTIAL staleness — and
        acting on it would drop legs on the strength of an outage. Killing the
        reset must fail here.
        """

        class _DiesMidway(_Session):
            async def execute(self, stmt):
                if isinstance(stmt, Update):
                    return await super().execute(stmt)
                self._n += 1
                if self._n == 1:
                    return _HalfDeadRows(
                        [
                            (CORPSE_A_MARKET, None, STALE, SCHEDULED),
                            (CORPSE_B_MARKET, None, STALE, SCHEDULED),
                        ]
                    )
                return _Rows(list(self.names.items()))

        service = _FakeService()
        await topup_outcome_clob_tokens(
            _DiesMidway(BOTH_CORPSES_STALE, dict(NAMES)), ALL_THREE, service=service
        )
        assert sorted(service.asked[0]) == sorted([CORPSE_A, CORPSE_B, LIVE]), (
            "a half-read must drop nothing at all"
        )

    @pytest.mark.asyncio
    async def test_a_naive_datetime_is_read_as_utc_and_does_not_raise(self):
        service = _FakeService()
        naive = (NOW - timedelta(days=14)).replace(tzinfo=None)
        await topup_outcome_clob_tokens(
            _session({CORPSE_A_MARKET: naive, LIVE_MARKET: FRESH}),
            _targets(CORPSE_A_LEG, LIVE_LEG),
            service=service,
        )
        assert service.asked == [[LIVE]]


class TestAgeAloneMayNotDropALeg:
    """The event's STATUS is the second half of the predicate, and the guard.

    The caller's slate admits an event on either of two statuses — ``'live'``,
    or ``'scheduled'`` starting within 6 h. Aging out a leg whose event reached
    ``'live'`` would be this module overruling the event graph on a clock and
    dropping exactly the live winner line #837 exists to reach: a multi-day
    competition, a fixture whose row is advanced late, or any event whose start
    time is wrong in the stale direction.

    Measured on production 2026-09-17 07:5xZ, which is why this costs nothing:
    of the slate legs past the bound, 2,996 of 2,996 are ``'scheduled'`` and no
    live event of that age exists anywhere in the table. The clause removes a
    class of wrong drop without changing a leg of the repair — and the two
    ``TestTheCorpsesLeaveTheAsk`` cases above still pass, which is the proof.
    """

    @pytest.mark.asyncio
    async def test_a_live_event_is_never_aged_out_however_old_its_start_time(self):
        service = _FakeService(
            [
                _FakeMarket(CORPSE_A, ["a" * 77, "b" * 77], ["x", "z"]),
                _FakeMarket(LIVE, [LIVE_TOKEN, "8" * 77], [LIVE_NAME, "Texas Rangers"]),
            ]
        )
        await topup_outcome_clob_tokens(
            _session(
                {
                    CORPSE_A_MARKET: (NOW - timedelta(days=90), LIVE_STATUS),
                    LIVE_MARKET: FRESH,
                }
            ),
            _targets(CORPSE_A_LEG, LIVE_LEG),
            service=service,
        )
        assert sorted(service.asked[0]) == sorted([CORPSE_A, LIVE]), (
            "an event the graph calls 'live' must keep its leg no matter how "
            f"old its start time reads. Asked: {service.asked}"
        )

    @pytest.mark.asyncio
    async def test_a_live_event_keeps_its_seat_even_when_the_cap_binds(self):
        """Not merely kept in the dict — it must survive to the ask under a cap.

        Without this, a version that keeps the live leg in ``addressable`` but
        lets the corpse-sorted head spend the cap would still pass the test
        above.
        """
        service = _FakeService(
            [_FakeMarket(CORPSE_A, ["a" * 77, "b" * 77], ["x", "z"])]
        )
        await topup_outcome_clob_tokens(
            _session(
                {
                    CORPSE_A_MARKET: (NOW - timedelta(days=90), LIVE_STATUS),
                    CORPSE_B_MARKET: STALE,
                    LIVE_MARKET: (NOW - timedelta(days=90), LIVE_STATUS),
                }
            ),
            ALL_THREE,
            service=service,
            max_outcomes=2,
        )
        assert sorted(service.asked[0]) == sorted([CORPSE_A, LIVE]), (
            "both live-status legs are askable and the cap is 2, so the "
            f"'scheduled' corpse is the one that must give up its seat. Asked: "
            f"{service.asked}"
        )

    @pytest.mark.asyncio
    async def test_an_unknown_status_keeps_its_leg(self):
        """Unknown is not stale — an unlinked market answers NULL for both."""
        service = _FakeService(
            [
                _FakeMarket(CORPSE_A, ["a" * 77, "b" * 77], ["x", "z"]),
                _FakeMarket(LIVE, [LIVE_TOKEN, "8" * 77], [LIVE_NAME, "Texas Rangers"]),
            ]
        )
        await topup_outcome_clob_tokens(
            _session({CORPSE_A_MARKET: (STALE, None), LIVE_MARKET: FRESH}),
            _targets(CORPSE_A_LEG, LIVE_LEG),
            service=service,
        )
        assert sorted(service.asked[0]) == sorted([CORPSE_A, LIVE])

    @pytest.mark.asyncio
    async def test_a_status_we_do_not_recognise_keeps_its_leg(self):
        """Anything that is not the corpse status is out of scope, not stale.

        'suspended', 'voided', 'completed' and 'merged' all exist on the events
        table. None of them reaches the slate today, and if one ever does this
        module is not the place that decides what it means.
        """
        service = _FakeService(
            [
                _FakeMarket(CORPSE_A, ["a" * 77, "b" * 77], ["x", "z"]),
                _FakeMarket(LIVE, [LIVE_TOKEN, "8" * 77], [LIVE_NAME, "Texas Rangers"]),
            ]
        )
        await topup_outcome_clob_tokens(
            _session({CORPSE_A_MARKET: (STALE, "suspended"), LIVE_MARKET: FRESH}),
            _targets(CORPSE_A_LEG, LIVE_LEG),
            service=service,
        )
        assert sorted(service.asked[0]) == sorted([CORPSE_A, LIVE])


class TestTheBoundary:
    @pytest.mark.asyncio
    @pytest.mark.parametrize(
        "age_hours,expect_asked",
        [(STALE_EVENT_HOURS - 1, True), (STALE_EVENT_HOURS + 1, False)],
    )
    async def test_the_cutoff_is_where_it_says_it_is(self, age_hours, expect_asked):
        service = _FakeService()
        await topup_outcome_clob_tokens(
            _session(
                {
                    CORPSE_A_MARKET: NOW - timedelta(hours=age_hours),
                    LIVE_MARKET: FRESH,
                }
            ),
            _targets(CORPSE_A_LEG, LIVE_LEG),
            service=service,
        )
        assert (CORPSE_A in service.asked[0]) is expect_asked


class TestWhatMustNotChange:
    @pytest.mark.asyncio
    async def test_a_live_market_marked_resolved_is_still_asked(self):
        """The refuted predicate, pinned so nobody re-adopts it.

        Production carried live ITF tennis legs whose markets read
        ``status = 'resolved'`` while the matches were in play. This function
        must not consult that column, and the proof is that nothing in its
        inputs can express it: the only settlement-shaped signal reaching here
        is the event's start time, and a fresh one is asked about.
        """
        service = _FakeService()
        await topup_outcome_clob_tokens(
            _session({LIVE_MARKET: FRESH}), _targets(LIVE_LEG), service=service
        )
        assert service.asked == [[LIVE]]

    @pytest.mark.asyncio
    async def test_a_stored_leg_on_a_stale_event_stays_subscribed(self):
        """Dropping from the ASK must never unsubscribe a leg we already hold.

        The return value IS the socket's subscription list, so a stale-but-known
        leg has to come back even though it is never asked about again.
        """
        service = _FakeService()
        session = _session(
            {CORPSE_A_MARKET: STALE, LIVE_MARKET: FRESH},
            stored={CORPSE_A_MARKET: {str(CORPSE_A_OUTCOME): "storedtok"}},
        )
        filled = await topup_outcome_clob_tokens(
            session, _targets(CORPSE_A_LEG, LIVE_LEG), service=service
        )
        assert service.asked == [[LIVE]], "a stored leg is never re-asked"
        assert filled[CORPSE_A_OUTCOME] == (CORPSE_A_MARKET, "storedtok"), (
            "the stored leg must stay in the subscription list"
        )
        assert filled[LIVE_OUTCOME] == (LIVE_MARKET, LIVE_TOKEN)

    @pytest.mark.asyncio
    async def test_an_all_stale_slate_still_returns_its_stored_legs(self):
        service = _FakeService()
        session = _session(
            {CORPSE_A_MARKET: STALE, CORPSE_B_MARKET: STALE},
            stored={CORPSE_A_MARKET: {str(CORPSE_A_OUTCOME): "storedtok"}},
        )
        filled = await topup_outcome_clob_tokens(
            session, _targets(CORPSE_A_LEG, CORPSE_B_LEG), service=service
        )
        assert service.asked == []
        assert filled == {CORPSE_A_OUTCOME: (CORPSE_A_MARKET, "storedtok")}

    @pytest.mark.asyncio
    async def test_nothing_is_written_for_a_leg_that_is_no_longer_asked(self):
        service = _FakeService()
        session = _session(BOTH_CORPSES_STALE)
        await topup_outcome_clob_tokens(session, ALL_THREE, service=service)
        assert len(session.updates) == 1, (
            "only the live market's tokens should be persisted"
        )
