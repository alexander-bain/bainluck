"""#837 / #5661 — the top-up's window turns on WHERE IT STOPPED, not on the clock.

WHY THIS FILE EXISTS.  #6634 made FILLED outcomes leave the ask, and that was
correct and insufficient: measured on the release that carried it, 324 of 333
condition ids were identical between consecutive recycles and 2 were newly
mapped per pass.  Nothing makes UNFILLABLE outcomes leave.  Most legs of a live
game's parent row are unfillable for good — a CLOSED sub-market answers HTTP 200
``[]`` on this read (indistinguishable from "never existed", gotcha #53), and an
open spread/total is returned but our single leg named "Spread -1.5" cannot be
attributed to Gamma's two teams.  They keep their lexicographic seats forever,
so a game-winner line that sorts above the 300th seat is never asked at all,
though it maps on the first try when asked directly.

WHY NOT THE OBVIOUS REPAIR.  Turning the window by wall clock —
``(now // 600) * size % len`` — was executed before it was built and STARVES:

    900 stable ids, cap 300, one pass every 900 s.  Clock buckets land on
    0, 1, 3, 4, 6, 7…, so the starts are 0 and 300 for ever and the last 300
    ids are never asked.  600 ids at cap 300 on a 1,200 s cadence starves half.

That is not "a skipped window costs one cycle"; it is permanent, and it needs
only the call cadence to resonate with the window quantum.  A runner that
restarts inside the dyno and whose recycles drift cannot carry a cadence
assumption.  So the selector below has no clock in it at all, and the tests that
matter most in this file are the two that replay those exact counterexamples.

THE CLASSES PINNED HERE: the counterexample cadences; the coverage bound at a
sweep of shapes; clock-independence by construction; a runner restart; slate
churn in both directions; the per-call cap; dead legs that must never map
however often they are asked; the correct-side mapping that must not move; a
Redis outage on read and on write; and a Gamma failure, which must no longer
unsubscribe the legs whose tokens we already hold.
"""

import math

import pytest
from sqlalchemy.sql.dml import Update

import app.tasks.polymarket_token_topup as topup_mod
from app.tasks.polymarket_token_topup import (
    OUTCOME_TOKEN_METADATA_KEY,
    select_ask_window,
    topup_outcome_clob_tokens,
)


def _ids(n: int, prefix: str = "0x") -> list[str]:
    """``n`` sorted, distinct condition-id-shaped strings."""
    return sorted(f"{prefix}{i:06d}" for i in range(n))


def _sweep(ordered: list[str], size: int, passes: int) -> list[list[str]]:
    """``passes`` consecutive selections over a STABLE slate, cursor carried."""
    cursor = None
    out = []
    for _ in range(passes):
        kept, cursor = select_ask_window(ordered, size, cursor)
        out.append(kept)
    return out


# ───────────────────────── the refuted design's own counterexamples ──────────


class TestTheCounterexamplesThatKilledTheClock:
    """Replayed verbatim.  These are the reason this is a cursor and not a clock."""

    def test_900_ids_cap_300_every_900_seconds_reaches_all_900(self):
        ordered = _ids(900)
        # The clock form visits buckets 0, 1, 3, 4, 6, 7… here, so its starts are
        # 0 and 300 for ever and ids[600:900] are never asked.  Three passes of a
        # resuming window is the whole slate, and the interval does not appear in
        # the computation at all.
        asked = _sweep(ordered, 300, 3)
        assert {c for p in asked for c in p} == set(ordered)
        assert [len(p) for p in asked] == [300, 300, 300]
        assert asked[0][0] == ordered[0] and asked[2][-1] == ordered[-1]

    def test_600_ids_cap_300_every_1200_seconds_reaches_all_600(self):
        ordered = _ids(600)
        asked = _sweep(ordered, 300, 2)
        assert {c for p in asked for c in p} == set(ordered)
        assert set(asked[0]).isdisjoint(asked[1]), (
            "consecutive passes must ask disjoint slices; overlap is the wasted "
            "budget the clock form spent"
        )

    def test_a_repeated_or_skipped_window_cannot_starve_anything(self):
        """Passes at wildly irregular, repeated and skipped intervals.

        The selector takes no time argument, so 'when' cannot enter the answer —
        this test states that as behaviour rather than leaving it to inspection.
        """
        ordered = _ids(1000)
        cursor = None
        seen: set[str] = set()
        # 4 passes is ceil(1000/300) = 4, whatever the spacing between them.
        for _ in range(4):
            kept, cursor = select_ask_window(ordered, 300, cursor)
            seen |= set(kept)
        assert seen == set(ordered)

    def test_the_selection_does_not_move_when_the_wall_clock_does(self, monkeypatch):
        import time

        ordered = _ids(900)
        first, cursor = select_ask_window(ordered, 300, None)
        for fake in (0, 600, 1200, 123456789, 1_789_000_000):
            monkeypatch.setattr(time, "time", lambda v=fake: float(v))
            again, again_cursor = select_ask_window(ordered, 300, None)
            assert again == first and again_cursor == cursor


# ───────────────────────────── the guarantee, swept ──────────────────────────


class TestTheCoverageBound:
    @pytest.mark.parametrize(
        "total,size",
        [(1706, 300), (333, 300), (301, 300), (900, 300), (7, 3), (10, 1), (300, 300)],
    )
    def test_every_id_is_asked_within_ceil_total_over_size_passes(self, total, size):
        ordered = _ids(total)
        bound = math.ceil(total / size)
        seen = {c for p in _sweep(ordered, size, bound) for c in p}
        assert seen == set(ordered), (
            f"{len(set(ordered) - seen)} of {total} ids unasked after the "
            f"claimed bound of {bound} passes"
        )

    @pytest.mark.parametrize("total,size", [(1706, 300), (5, 2), (1, 1)])
    def test_no_pass_ever_exceeds_the_cap(self, total, size):
        for kept in _sweep(_ids(total), size, 12):
            assert len(kept) <= size

    def test_a_slate_under_the_cap_is_asked_whole_and_spends_no_write(self):
        ordered = _ids(12)
        kept, cursor = select_ask_window(ordered, 300, None)
        assert kept == ordered
        assert cursor is None, (
            "None means 'leave the stored position alone' — a pass that asked "
            "everything has nothing to defer and must not spend a Redis write"
        )

    def test_a_restart_resumes_where_the_last_pass_stopped(self):
        """The position is durable, so there is no module state to lose.

        A pass counter would restart at 0 and re-select the head for ever, which
        is the defect this replaces.  Here the only input is the stored cursor.
        """
        ordered = _ids(900)
        first, cursor = select_ask_window(ordered, 300, None)
        # ── process dies here; nothing in memory survives, the cursor does ──
        second, _ = select_ask_window(ordered, 300, cursor)
        assert set(first).isdisjoint(second)
        assert second[0] == ordered[300]


class TestSlateChurn:
    def test_an_id_entering_above_the_cursor_is_asked_this_cycle(self):
        ordered = _ids(900)
        _first, cursor = select_ask_window(ordered, 300, None)
        arrival = "0x000400_new"  # sorts inside the next slice
        grown = sorted(ordered + [arrival])
        second, _ = select_ask_window(grown, 300, cursor)
        assert arrival in second

    def test_removing_the_cursors_own_id_skips_nobody(self):
        """The cursor is an id, not an index: its departure must not shift turns."""
        ordered = _ids(900)
        first, cursor = select_ask_window(ordered, 300, None)
        assert cursor == first[-1]
        shrunk = [c for c in ordered if c != cursor]
        second, _ = select_ask_window(shrunk, 300, cursor)
        assert second[0] == ordered[300], (
            "the pass after the cursor's id was removed must resume at the id "
            "that followed it, not restart or jump"
        )

    def test_a_cursor_past_the_end_of_a_shrunken_slate_wraps_to_the_front(self):
        kept, _ = select_ask_window(_ids(10), 3, "0xzzzzzz")
        assert kept == _ids(10)[:3]


# ───────────────────── the same thing through the real function ──────────────

# One live MLB parent row's shape, trimmed to the classes that matter: five legs
# that can never be filled and sort BELOW the hero, and the hero above them.
# The ids are ordered so that the hero is unreachable under a fixed head at
# cap 2 — that is the whole defect, so the fixture asserts it below.
DEAD_CLOSED_A = "0x00038b26_closed_first_five_spread"
DEAD_CLOSED_B = "0x23ea4ae8_closed_nrfi"
DEAD_SPREAD = "0x4115c976_spread_minus_1_5"
DEAD_TOTAL = "0x119a1073_ou_7_5"
DEAD_UNKNOWN = "0x00000001_never_existed"
HERO = "0x86700037_atl_chc_moneyline"

HERO_MARKET_ID = 60683956
HERO_OUTCOME_ID = 228928100
HERO_NAME = "Atlanta Braves"
HERO_GAMMA_OUTCOMES = ["Atlanta Braves", "Chicago Cubs"]
HERO_TOKEN = "71" * 30
CUBS_TOKEN = "72" * 30

DEAD_LEGS = [DEAD_CLOSED_A, DEAD_CLOSED_B, DEAD_SPREAD, DEAD_TOTAL, DEAD_UNKNOWN]

assert all(d < HERO for d in DEAD_LEGS), (
    "every dead leg must sort below the hero or this fixture proves nothing: "
    "the starvation IS the lexicographic order"
)


class _FakeMarket:
    def __init__(self, condition_id, clob_token_ids, outcomes):
        self.condition_id = condition_id
        self.clob_token_ids = list(clob_token_ids)
        self.outcomes = list(outcomes)


#: What Gamma answers.  The two CLOSED legs and the unknown id are ABSENT from
#: this map, which is how a closed market arrives on this read: an empty 200,
#: not an error.  The spread and the total ARE returned and are still
#: unmappable, because our leg's name is not one of Gamma's outcomes.
GAMMA_ANSWERS = {
    HERO: _FakeMarket(HERO, [HERO_TOKEN, CUBS_TOKEN], HERO_GAMMA_OUTCOMES),
    DEAD_SPREAD: _FakeMarket(DEAD_SPREAD, ["81" * 30, "82" * 30], ["Chicago Cubs", "Atlanta Braves"]),
    DEAD_TOTAL: _FakeMarket(DEAD_TOTAL, ["83" * 30, "84" * 30], ["Over", "Under"]),
}


class _FakeService:
    def __init__(self, *, raises=None):
        self.asked: list[list[str]] = []
        self.closed = False
        self._raises = raises

    async def get_markets_by_conditions(self, condition_ids, **_kw):
        self.asked.append(list(condition_ids))
        if self._raises:
            raise self._raises
        return [GAMMA_ANSWERS[c] for c in condition_ids if c in GAMMA_ANSWERS]

    async def close(self):
        self.closed = True


class _Rows:
    def __init__(self, rows):
        self._rows = list(rows)

    def all(self):
        return list(self._rows)


class _Session:
    """Answers the stored-metadata SELECT then the outcome-name SELECT.

    ``stored`` is the live ``{outcome_id: token}`` map the recycles write into,
    so a pass reads what the pass before it persisted — the round trip is what
    makes the ask shrink, and a stub that forgot it would hide that.
    """

    def __init__(self, stored: dict, names: dict, *, load_raises=None):
        self.stored = stored
        self.names = names
        self.updates: list = []
        self._load_raises = load_raises
        self._n = 0

    async def execute(self, stmt):
        if isinstance(stmt, Update):
            self.updates.append(stmt)
            return _Rows([])
        self._n += 1
        if self._n == 1:
            if self._load_raises:
                raise self._load_raises
            rows: dict = {}
            for oid, token in self.stored.items():
                rows.setdefault(HERO_MARKET_ID, {})[str(oid)] = token
            # Third and fourth elements are the parent event's start time and
            # status (#837). Both ``None`` — "unknown" — because the module
            # treats unknown as NOT stale on either, so these rotation tests
            # keep exercising the window rather than the staleness filter,
            # which has its own file.
            return _Rows(
                [
                    (mid, {OUTCOME_TOKEN_METADATA_KEY: m}, None, None)
                    for mid, m in rows.items()
                ]
            )
        return _Rows(list(self.names.items()))


def _targets() -> list[tuple[int, int, str]]:
    legs = [(HERO_MARKET_ID, HERO_OUTCOME_ID, HERO)]
    for i, cid in enumerate(DEAD_LEGS):
        legs.append((HERO_MARKET_ID, 900_000 + i, cid))
    return legs


class _CursorStore:
    """Stands in for Redis.  Survives 'restarts' exactly as the real key does."""

    def __init__(self, value=None, *, load_raises=None, save_raises=None):
        self.value = value
        self.saves: list = []
        self.load_raises = load_raises
        self.save_raises = save_raises

    def install(self, monkeypatch):
        async def _load():
            if self.load_raises:
                # The real loader swallows and returns None; this store raises
                # so a test can prove the swallow happens in the module, not here.
                raise self.load_raises
            return self.value

        async def _save(cursor):
            self.saves.append(cursor)
            if self.save_raises:
                raise self.save_raises
            if cursor:
                self.value = cursor

        monkeypatch.setattr(topup_mod, "load_topup_cursor", _load)
        monkeypatch.setattr(topup_mod, "save_topup_cursor", _save)
        return self


async def _recycles(n: int, monkeypatch, *, cap=2, store=None, service=None):
    """``n`` consecutive socket recycles sharing one cursor and one stored map."""
    store = store or _CursorStore().install(monkeypatch)
    stored: dict = {}
    names = {HERO_OUTCOME_ID: HERO_NAME}
    for i, cid in enumerate(DEAD_LEGS):
        names[900_000 + i] = {
            DEAD_SPREAD: "Spread -1.5",
            DEAD_TOTAL: "O/U 7.5",
        }.get(cid, "Yes")
    svc = service or _FakeService()
    filled: dict = {}
    for _ in range(n):
        session = _Session(stored, names)
        filled = await topup_outcome_clob_tokens(
            session, _targets(), service=svc, max_outcomes=cap
        )
        for oid, (_mid, token) in filled.items():
            stored[oid] = token
    return filled, svc.asked, stored


class TestThroughTheRealFunction:
    pytestmark = pytest.mark.asyncio

    async def test_a_hero_above_a_window_of_dead_legs_is_reached(self, monkeypatch):
        """THE DEFECT.  Under the old fixed head the hero sorts last of six at
        cap 2 and is asked on no recycle, ever."""
        filled, asked, _ = await _recycles(3, monkeypatch)
        assert any(HERO in pass_ for pass_ in asked), (
            f"the hero leg was never asked in 3 recycles; the passes were {asked}"
        )
        assert filled[HERO_OUTCOME_ID] == (HERO_MARKET_ID, HERO_TOKEN)

    async def test_the_hero_gets_its_own_side_not_the_opponents(self, monkeypatch):
        """Mapping is untouched by this ship and must stay by-name (Q489).

        A token attributed to the wrong leg does not make a card stale, it makes
        it inverted, so this asserts the Braves token and NOT the Cubs one.
        """
        filled, _, _ = await _recycles(3, monkeypatch)
        assert filled[HERO_OUTCOME_ID][1] == HERO_TOKEN
        assert filled[HERO_OUTCOME_ID][1] != CUBS_TOKEN

    async def test_every_leg_is_asked_within_the_bound(self, monkeypatch):
        _filled, asked, _ = await _recycles(3, monkeypatch)
        assert {c for p in asked for c in p} == set(DEAD_LEGS + [HERO])

    async def test_dead_legs_never_map_however_often_they_are_asked(
        self, monkeypatch
    ):
        """Cause-agnostic is the point: the window does not need to know WHY a
        leg is dead, and it must not start inventing a token for one."""
        filled, _asked, _ = await _recycles(8, monkeypatch)
        assert set(filled) == {HERO_OUTCOME_ID}

    async def test_no_recycle_asks_more_than_the_cap(self, monkeypatch):
        _filled, asked, _ = await _recycles(8, monkeypatch, cap=2)
        assert asked and all(len(p) <= 2 for p in asked)

    async def test_a_stored_hero_is_never_re_asked_and_stays_subscribable(
        self, monkeypatch
    ):
        """#6634's property, re-pinned here because the window must not undo it:
        the return value IS the socket's subscription list."""
        _filled, asked, stored = await _recycles(6, monkeypatch)
        assert stored[HERO_OUTCOME_ID] == HERO_TOKEN
        after_first_fill = [p for p in asked if HERO in p]
        assert len(after_first_fill) == 1, (
            "a filled hero must leave the ask; re-asking it spends the budget "
            "the dead legs already waste"
        )

    async def test_the_window_survives_a_runner_restart(self, monkeypatch):
        """Two separate 'processes' sharing only the durable cursor."""
        store = _CursorStore().install(monkeypatch)
        await _recycles(1, monkeypatch, store=store)
        carried = store.value
        assert carried, "the first pass must persist where it stopped"

        # A fresh store seeded from Redis is what a restarted runner sees.
        restarted = _CursorStore(value=carried).install(monkeypatch)
        _filled, asked, _ = await _recycles(2, monkeypatch, store=restarted)
        assert asked[0][0] != sorted(DEAD_LEGS + [HERO])[0], (
            "a restarted runner that re-selects the head is the defect itself"
        )


class TestItDegradesRatherThanFailing:
    pytestmark = pytest.mark.asyncio

    async def test_a_redis_read_fault_asks_from_the_front_and_does_not_raise(
        self, monkeypatch
    ):
        # The module's own loader is what must swallow, so this test drives the
        # real `load_topup_cursor` with a broken client underneath it.
        def _boom():
            raise RuntimeError("redis down")

        monkeypatch.setattr(topup_mod, "_read_cursor_sync", _boom)
        assert await topup_mod.load_topup_cursor() is None

    async def test_a_redis_write_fault_does_not_raise(self, monkeypatch):
        def _boom(_cursor):
            raise RuntimeError("redis down")

        monkeypatch.setattr(topup_mod, "_write_cursor_sync", _boom)
        await topup_mod.save_topup_cursor("0xdeadbeef")  # must not raise

    async def test_nothing_is_written_when_there_is_nothing_to_defer(
        self, monkeypatch
    ):
        writes: list = []
        monkeypatch.setattr(topup_mod, "_write_cursor_sync", writes.append)
        await topup_mod.save_topup_cursor(None)
        assert writes == []

    async def test_a_gamma_failure_keeps_the_already_stored_legs_subscribed(
        self, monkeypatch
    ):
        """The caller answers an exception with ``outcome_yes_token = {}``.

        So a provider outage used to unsubscribe every moneyline leg whose token
        we already held and had no need to ask about.  A failed ASK now returns
        what is already KNOWN.
        """
        _CursorStore().install(monkeypatch)
        stored = {HERO_OUTCOME_ID: HERO_TOKEN}
        session = _Session(stored, {HERO_OUTCOME_ID: HERO_NAME})
        service = _FakeService(raises=RuntimeError("gamma 503"))

        filled = await topup_outcome_clob_tokens(
            session, _targets(), service=service, max_outcomes=2
        )

        assert filled == {HERO_OUTCOME_ID: (HERO_MARKET_ID, HERO_TOKEN)}
        assert service.asked, "the outage must happen on a real ask, not before it"
        assert session.updates == [], "a failed pass writes nothing"

    async def test_a_gamma_failure_with_nothing_stored_still_re_raises(
        self, monkeypatch
    ):
        """The boundary of the arm above, and it is gotcha #36's line.

        With nothing stored there is nothing to protect, and answering ``{}``
        would say "these outcomes have no tokens" — the false negative that hid
        this gap for the market-level path. The swallow is licensed by HAVING AN
        ANSWER, never by the provider having failed, so this case re-raises
        exactly as it did before this ship (pinned independently by
        ``test_poly_moneyline_leg_streams_q500``, which must stay green).
        """
        _CursorStore().install(monkeypatch)
        session = _Session({}, {HERO_OUTCOME_ID: HERO_NAME})
        service = _FakeService(raises=RuntimeError("gamma 503"))

        with pytest.raises(RuntimeError):
            await topup_outcome_clob_tokens(
                session, _targets(), service=service, max_outcomes=2
            )

    async def test_a_gamma_failure_still_advances_the_window(self, monkeypatch):
        """Otherwise an outage holds the same slice until Gamma recovers — the
        same livelock with a different cause."""
        store = _CursorStore().install(monkeypatch)
        service = _FakeService(raises=RuntimeError("gamma 503"))
        session = _Session({}, {HERO_OUTCOME_ID: HERO_NAME})
        with pytest.raises(RuntimeError):
            await topup_outcome_clob_tokens(
                session, _targets(), service=service, max_outcomes=2
            )
        assert store.value, "the position must move even when the ask fails"
