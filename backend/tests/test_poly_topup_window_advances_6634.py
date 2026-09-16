"""#6634 / #837 — the outcome top-up's cap is a bound on WORK, not a permanent frontier.

WHY THIS FILE EXISTS.  #6617 taught ``topup_outcome_clob_tokens`` to read a
two-way head-to-head, and it works — where it is reached.  It was reached for
300 of 1,706 addressable outcomes, and the same 300 every recycle.

``topup_outcome_clob_tokens`` caps its ask at ``MAX_TOPUP_MARKETS`` with
``kept = sorted(addressable)[:max_outcomes]`` and logs the remainder as
"deferred to the next recycle".  Nothing deferred it.  The caller
(``polymarket_ws``) drops a market from ``outcomes`` only when it carries the
MARKET-level ``clob_token_ids``; its ``tokens_by_market`` never reads
``OUTCOME_TOKEN_METADATA_KEY``, which is the key this top-up writes.  So the
fill was invisible to the filter, the ask never shrank, ``sorted`` re-selected
the same lexicographic head, and everything above the boundary was starved
permanently.  A livelock: the queue's sort key was not one the work advanced.

MEASURED ON PRODUCTION, 2026-09-16 22:39-22:47Z, with #6617 live on v4645+.
The live+6h slate held **1,706 addressable condition ids against a cap of 300**
— the constant is commented as "~4x headroom" for a slate an order of magnitude
smaller — and the 300th, the last one kept, was ``0x2b8f76c0…``.  Of nine live
MLB events carrying a Polymarket hero leg::

    event                outcome            condition id   vs 0x2b8f…   tokens
    15313146 Rangers     Boston Red Sox     0x0614…        below        1
    15313140 Pirates     Milwaukee Brewers  0x6fe6…        above        0
    15313138 Rays        Athletics          0xa40f…        above        0

Three for three with the boundary.  Gamma answered all three with the shape
#6617 handles — ``outcomes`` the contenders themselves, two ``clobTokenIds`` —
and our outcome names matched verbatim, so the matcher was never the
difference; the cap was the whole of it.

WHAT THE READER SAW.  At 22:40:58Z, **six** of those hero legs shared the
identical stamp ``22:40:58.322131`` and two more shared ``22:38:58.321518`` —
120 s apart, the poll sawtooth, one writer per transaction.  The single leg
below the boundary sat off-beat at ``22:42:06.181160``.  That row is the
positive control: the fast lane was correct and simply was not reaching the
other eight.

THE FIX reads what is already stored and excludes it from the ask, so the set
shrinks monotonically and the window advances.  Stored tokens are SEEDED INTO
THE RETURN rather than merely skipped, because the return value is the socket's
subscription list — dropping a known outcome would unsubscribe the very legs
this module exists to keep streaming.

The tests below pin, in order: a stored token is returned without being
re-asked; the ask advances to the outcome that was starved (the defect itself);
an all-stored pass asks Gamma nothing and still answers in full; a stored
outcome is never rewritten; and a failed bookkeeping read degrades to the
previous behaviour rather than taking the socket's token pass down.
"""

import pytest
from sqlalchemy.sql.dml import Update

from app.tasks.polymarket_token_topup import (
    OUTCOME_TOKEN_METADATA_KEY,
    topup_outcome_clob_tokens,
)

pytestmark = pytest.mark.asyncio

# Tonight's three specimens, kept verbatim so the fixture cannot drift into a
# friendlier one. LOW sorts below the measured boundary 0x2b8f76c0…; HIGH sorts
# above it, which is the only reason it was starved.
LOW_CONDITION = "0x06146cca6d8e1906e6fa1e80c1cab9cf4c5582b2c63f23b5786ea25f854fe267"
LOW_MARKET_ID = 60683974
LOW_OUTCOME_ID = 228928588
LOW_OUTCOME_NAME = "Boston Red Sox"
LOW_OUTCOMES = ["Boston Red Sox", "Texas Rangers"]
LOW_TOKEN = "11111111111111111111111111111111111111111111111111111111111111111111111111111"

HIGH_CONDITION = "0x6fe65ea3a60632c75216bd3739a73cb5e8725fef9847e5a1e2f5302584a7fe7a"
HIGH_MARKET_ID = 60683985
HIGH_OUTCOME_ID = 228919342
HIGH_OUTCOME_NAME = "Milwaukee Brewers"
HIGH_OUTCOMES = ["Milwaukee Brewers", "Pittsburgh Pirates"]
HIGH_TOKEN = "22222222222222222222222222222222222222222222222222222222222222222222222222222"

assert LOW_CONDITION < HIGH_CONDITION, (
    "the whole defect is lexicographic: if these two ever sort the other way "
    "the cap tests below prove nothing"
)


class _FakeMarket:
    def __init__(self, condition_id, clob_token_ids, outcomes):
        self.condition_id = condition_id
        self.clob_token_ids = list(clob_token_ids)
        self.outcomes = list(outcomes)


class _FakeService:
    def __init__(self, markets):
        self._markets = markets
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


class _Session:
    """Answers the two SELECTs this function makes, in the order it makes them.

    The stored-metadata read comes first, the outcome-name read second. They are
    both Selects, so a stub that answered them alike — as the #6617 fixture does —
    would hand market metadata to the name parser and hide the very thing these
    tests pin.
    """

    def __init__(self, stored_rows=(), name_rows=(), *, stored_raises=None):
        self.updates: list = []
        self.selects: list = []
        self._queue = [
            ("stored", list(stored_rows)),
            ("names", list(name_rows)),
        ]
        self._stored_raises = stored_raises

    async def execute(self, stmt):
        if isinstance(stmt, Update):
            self.updates.append(stmt)
            return _Rows([])
        self.selects.append(stmt)
        kind, rows = self._queue.pop(0) if self._queue else ("names", [])
        if kind == "stored" and self._stored_raises:
            raise self._stored_raises
        return _Rows(rows)


def _both_markets():
    return [
        _FakeMarket(LOW_CONDITION, [LOW_TOKEN, "9" * 20], LOW_OUTCOMES),
        _FakeMarket(HIGH_CONDITION, [HIGH_TOKEN, "8" * 20], HIGH_OUTCOMES),
    ]


def _both_targets():
    return [
        (LOW_MARKET_ID, LOW_OUTCOME_ID, LOW_CONDITION),
        (HIGH_MARKET_ID, HIGH_OUTCOME_ID, HIGH_CONDITION),
    ]


class TestTheWindowAdvances:
    async def test_the_starved_outcome_is_asked_once_the_low_one_is_stored(self):
        """THE DEFECT ITSELF.

        Pass two, with the low condition already stored from pass one and the
        cap still 1. Before this fix the ask was ``sorted(...)[:1]`` over the
        unchanged set, so it re-asked ``0x0614…`` forever and ``0x6fe6…`` was
        never reached. Tonight that was 1,406 of 1,706 outcomes.
        """
        service = _FakeService(_both_markets())
        session = _Session(
            stored_rows=[
                (LOW_MARKET_ID, {OUTCOME_TOKEN_METADATA_KEY: {str(LOW_OUTCOME_ID): LOW_TOKEN}})
            ],
            name_rows=[(HIGH_OUTCOME_ID, HIGH_OUTCOME_NAME)],
        )

        filled = await topup_outcome_clob_tokens(
            session, _both_targets(), service=service, max_outcomes=1
        )

        assert service.asked == [[HIGH_CONDITION]], (
            "the starved condition must be the one asked; re-asking the stored "
            "one is the livelock this file exists to prevent"
        )
        assert filled[HIGH_OUTCOME_ID] == (HIGH_MARKET_ID, HIGH_TOKEN)

    async def test_the_stored_leg_stays_subscribable(self):
        """The return value IS the socket's subscription list.

        Skipping a stored outcome without returning it would unsubscribe a leg
        that is streaming correctly — strictly worse than the starvation.
        """
        service = _FakeService(_both_markets())
        session = _Session(
            stored_rows=[
                (LOW_MARKET_ID, {OUTCOME_TOKEN_METADATA_KEY: {str(LOW_OUTCOME_ID): LOW_TOKEN}})
            ],
            name_rows=[(HIGH_OUTCOME_ID, HIGH_OUTCOME_NAME)],
        )

        filled = await topup_outcome_clob_tokens(
            session, _both_targets(), service=service, max_outcomes=1
        )

        assert filled[LOW_OUTCOME_ID] == (LOW_MARKET_ID, LOW_TOKEN)
        assert len(filled) == 2

    async def test_a_stored_outcome_is_never_rewritten(self):
        """A known token costs no write. Only the newly filled one is persisted."""
        service = _FakeService(_both_markets())
        session = _Session(
            stored_rows=[
                (LOW_MARKET_ID, {OUTCOME_TOKEN_METADATA_KEY: {str(LOW_OUTCOME_ID): LOW_TOKEN}})
            ],
            name_rows=[(HIGH_OUTCOME_ID, HIGH_OUTCOME_NAME)],
        )

        await topup_outcome_clob_tokens(
            session, _both_targets(), service=service, max_outcomes=1
        )

        assert len(session.updates) == 1
        assert str(HIGH_MARKET_ID) in str(
            session.updates[0].compile(compile_kwargs={"literal_binds": True})
        )

    async def test_an_all_stored_slate_asks_gamma_nothing_and_still_answers(self):
        service = _FakeService(_both_markets())
        session = _Session(
            stored_rows=[
                (
                    LOW_MARKET_ID,
                    {OUTCOME_TOKEN_METADATA_KEY: {str(LOW_OUTCOME_ID): LOW_TOKEN}},
                ),
                (
                    HIGH_MARKET_ID,
                    {OUTCOME_TOKEN_METADATA_KEY: {str(HIGH_OUTCOME_ID): HIGH_TOKEN}},
                ),
            ],
        )

        filled = await topup_outcome_clob_tokens(
            session, _both_targets(), service=service, max_outcomes=1
        )

        assert service.asked == [], "nothing was missing; Gamma must not be called"
        assert filled == {
            LOW_OUTCOME_ID: (LOW_MARKET_ID, LOW_TOKEN),
            HIGH_OUTCOME_ID: (HIGH_MARKET_ID, HIGH_TOKEN),
        }
        assert session.updates == []

    async def test_an_empty_stored_token_is_re_asked_not_trusted(self):
        """A key present with a falsy value is not a fill. It must be re-asked,
        never returned as a token the socket would subscribe to."""
        service = _FakeService(_both_markets())
        session = _Session(
            stored_rows=[
                (LOW_MARKET_ID, {OUTCOME_TOKEN_METADATA_KEY: {str(LOW_OUTCOME_ID): ""}})
            ],
            name_rows=[(LOW_OUTCOME_ID, LOW_OUTCOME_NAME)],
        )

        filled = await topup_outcome_clob_tokens(
            session, _both_targets(), service=service, max_outcomes=1
        )

        assert service.asked == [[LOW_CONDITION]]
        assert filled[LOW_OUTCOME_ID] == (LOW_MARKET_ID, LOW_TOKEN)

    async def test_an_unreadable_stored_key_does_not_crash_the_pass(self):
        service = _FakeService(_both_markets())
        session = _Session(
            stored_rows=[
                (LOW_MARKET_ID, {OUTCOME_TOKEN_METADATA_KEY: {"not-an-id": LOW_TOKEN}})
            ],
            name_rows=[(LOW_OUTCOME_ID, LOW_OUTCOME_NAME)],
        )

        filled = await topup_outcome_clob_tokens(
            session, _both_targets(), service=service, max_outcomes=1
        )

        assert service.asked == [[LOW_CONDITION]]
        assert filled[LOW_OUTCOME_ID] == (LOW_MARKET_ID, LOW_TOKEN)

    async def test_a_failed_stored_read_degrades_to_the_old_behaviour(self):
        """Never take the socket's token pass down for a bookkeeping read.

        Without the read every outcome is asked again — the behaviour that
        predates this fix, not a new failure.
        """
        service = _FakeService(_both_markets())
        session = _Session(
            name_rows=[(LOW_OUTCOME_ID, LOW_OUTCOME_NAME)],
            stored_raises=RuntimeError("metadata read exploded"),
        )

        filled = await topup_outcome_clob_tokens(
            session, _both_targets(), service=service, max_outcomes=1
        )

        assert service.asked == [[LOW_CONDITION]]
        assert filled[LOW_OUTCOME_ID] == (LOW_MARKET_ID, LOW_TOKEN)

    async def test_a_market_with_no_stored_key_is_asked_as_before(self):
        """The no-op case: sibling metadata present, our key absent."""
        service = _FakeService(_both_markets())
        session = _Session(
            stored_rows=[(LOW_MARKET_ID, {"polymarket_event_id": "917153"})],
            name_rows=[(LOW_OUTCOME_ID, LOW_OUTCOME_NAME)],
        )

        filled = await topup_outcome_clob_tokens(
            session, _both_targets(), service=service, max_outcomes=1
        )

        assert service.asked == [[LOW_CONDITION]]
        assert filled[LOW_OUTCOME_ID] == (LOW_MARKET_ID, LOW_TOKEN)
