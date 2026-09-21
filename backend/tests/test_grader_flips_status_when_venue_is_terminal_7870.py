"""#7870: the grade lands AND the page stops reading live — one venue read, two writes.

## the defect this guards

#7857 shipped the first half: band 4 selects a market the venue settled years
before its own end date, the grader reads `GET /events/{ticker}` and writes
`is_winner` on the legs. Verified on production 2026-09-21 — `/api/futures/112815`
("Next Fed rate hike?") returned all three rungs the venue reports as
`is_winner: true` / `resolution_source: api_settlement`.

**The page did not change.** The frontend gates every settled affordance on
`market.status`, never on the grade:

    // lib/futuresDetailDisplay.ts
    export function gradedWinner(outcomes, leader, status) {
      if (status !== "resolved") return null;
    // app/futures/[id]/page.tsx
    const isResolved = market.status === "resolved";

That gate is correct and is NOT loosened here — its own comment says a stray
`is_winner` must not let a live market claim a result. The repair is that the
status has to follow the grade, out of the same venue read.

## why the row was stranded

`futures_markets.status` is written to `'resolved'` by two rails and the
specimen escapes both:

* `_poll_kalshi_markets` derives it from `all_terminal(m.status for m in
  event.markets)` on every poll — but polling is keyed on the SERIES, and Kalshi
  RETIRED `FEDHIKE` into successor `KXFEDHIKE`. Read live 2026-09-21:
  `/markets?series_ticker=FEDHIKE` returns **0 markets in every status**, while
  `/markets?series_ticker=KXFEDHIKE` returns the three finalized rungs with their
  tickers unchanged. The poller went dark on a row the venue had answered
  (gotcha #33, one step on).
* the resolution-window sweep (CAL-P1019 / #2722) fires on `resolution_date`,
  which for this row is **2028-01-01**.

The grader's door was never shut: `GET /events/FEDHIKE` answers **200** with the
three `finalized` markets.

## so the rule is the POLLER'S rule, not a new one

This is the load-bearing design claim and
:class:`TestTheGateIsThePollersOwnHelperAndNotACopy` is what holds it: the grader
calls `kms.all_terminal`, the same helper `_poll_kalshi_markets` calls, imported
rather than retyped. Two hand-rolled copies of "is this event over" is exactly
the drift `app/utils/kalshi_market_status.py` was written to end (#1818, where
four modules each encoded Kalshi's status vocabulary from memory and the one that
mattered was inverted). It also means `closed`'s known false positive — terminal,
but no result yet — is inherited rather than re-introduced, and if #1818 ever
removes it from `TERMINAL_STATUSES` both call sites move together.

## measured at the venue before building (notice 26/27), 2026-09-21

"Flip `status` in bulk" is a serve-time change: `status` filters feed, search and
the category pages. 173 Kalshi events were read live, in three strata:

    stratum                                                  n     would flip
    ------------------------------------------------------------------------
    random, our open markets carrying >=1 venue-graded leg    52        0
    random, our open markets whose EVERY leg is graded        69        0
    census, our open markets already past resolution_date     13       12

The two random strata are the important half: **0 false flips**. Those markets
are genuinely mid-flight — a settled rung on a live ladder is the ordinary shape
(`KXYTVIEWSW-ARI26SEP20`: 4 `finalized` + 11 `active`), and `TestAMidFlightLadder`
is that specimen written down.

The census is the ship: **12 of 13** were fully `finalized` at the venue while
reading LIVE on the site — finished ITF tennis matches, Rainbow Six games, and
the day's gold/silver/copper/brent/natgas settlement ladders. The 13th
(`KXT20MATCH-26SEP211430BAHCYM`, 2 x `active`) was correctly held.

A gate that fires on 12 of 13 overdue rows and 0 of 121 mid-flight ones is
DISCRIMINATING, and that is the property under test here. The count is the
smaller half.

## known residual, named rather than papered over

An event the venue has otherwise finished whose last leg is `inactive` (listed,
never traded) is not all-terminal and does not flip — measured on
`KXPGATOP20-BICA26` and `KXPGATOP5-BICA26`, **133 `finalized` + 1 `inactive`**
each. `TestTheInactiveHoldoutIsAKnownResidual` pins it as a KNOWN MISS so a later
reader finds the measurement instead of rediscovering it. Admitting `inactive`
into `TERMINAL_STATUSES` is the wrong repair — it is the normal state of an
unstarted market, 622 of 2,000 in the #1818 probe — and needs its own census.

## why a recording session and not the existing `_LoopSession`

`tests/test_kalshi_settlement_recency_band_4057.py` answers any UPDATE with
`rowcount=1`, which proves a statement was issued and nothing about what it
targets. Delete the `source == "kalshi"` clause, or the `status != "resolved"`
clause, or point the UPDATE at `FuturesOutcome`, and that rig still passes. The
session here compiles every statement it is handed, so the arms below assert the
WHERE the production row actually depends on.
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

# NOT `from app.tasks import backfill_winners`: that resolves to the Celery task
# object the package re-exports, which has none of the module's private functions,
# so every `monkeypatch.setattr` below dies with AttributeError.
import app.tasks.backfill_winners as bw

from app.utils import kalshi_market_status as kms

BACKFILL_SOURCE = (
    Path(__file__).resolve().parents[1] / "app" / "tasks" / "backfill_winners.py"
)
POLL_SOURCE = Path(__file__).resolve().parents[1] / "app" / "tasks" / "kalshi.py"


# ---------------------------------------------------------------- the rig


class _Result:
    def __init__(self, rowcount: int = 1):
        self.rowcount = rowcount

    def all(self):
        return []


class _RecordingSession:
    """Answers like `_LoopSession` but KEEPS the compiled SQL of every statement."""

    def __init__(self):
        self.statements: list[str] = []
        self.commits = 0

    async def execute(self, stmt, params=None):
        try:
            sql = str(stmt.compile(compile_kwargs={"literal_binds": True}))
        except Exception:
            sql = str(stmt)
        self.statements.append(sql)
        return _Result(1 if "UPDATE" in sql.upper() else 0)

    async def commit(self):
        self.commits += 1

    async def rollback(self):
        return None

    # -- what the arms ask it --------------------------------------------

    def market_status_updates(self) -> list[str]:
        """Only the statements that write `futures_markets.status`."""
        return [
            s
            for s in self.statements
            if s.upper().startswith("UPDATE")
            and "futures_markets" in s
            and "status" in s
        ]


class _SessionCM:
    def __init__(self, session):
        self._session = session

    def __call__(self, *a, **k):
        return self

    async def __aenter__(self):
        return self._session

    async def __aexit__(self, *a):
        return False


class _FakeKalshi:
    def __init__(self, answers):
        self.asked: list[str] = []
        self._answers = answers

    async def get_event(self, ticker):
        self.asked.append(ticker)
        return self._answers.get(ticker)

    async def close(self):
        return None


class _FakeRedis:
    def __init__(self):
        self.store: dict[str, str] = {}

    def get(self, key):
        return self.store.get(key)

    def setex(self, key, ttl, value):
        self.store[key] = value

    def delete(self, key):
        self.store.pop(key, None)


def _event(*legs: tuple[str, str, str | None]) -> dict:
    """A venue event. Each leg is `(ticker, status, result)` — quoted from the
    probe, never invented: the statuses below are the five `kalshi_market_status`
    measured on 2026-08-13."""
    return {
        "markets": [
            {"ticker": t, "status": s, "result": r} for t, s, r in legs
        ]
    }


async def _drive(monkeypatch, *, ticker: str, event: dict | None, dry_run=False):
    """Run the REAL `_backfill_kalshi_winners` over one event, selection stubbed."""

    async def _fake_select(session, limit_, cursor_, *, include_tail=True):
        return [ticker], []

    async def _fake_early(session, limit_):
        return []

    async def _fake_longdated(session, limit_, cursor_):
        return []

    session = _RecordingSession()
    venue = _FakeKalshi({ticker: event})

    monkeypatch.setattr(bw, "_select_kalshi_settlement_tickers", _fake_select)
    monkeypatch.setattr(bw, "_select_kalshi_early_settled_tickers", _fake_early)
    monkeypatch.setattr(
        bw, "_select_kalshi_early_settled_longdated_tickers", _fake_longdated
    )
    monkeypatch.setattr(bw, "get_task_session", _SessionCM(session))
    monkeypatch.setattr(
        "app.tasks.redis_state.get_redis_client", lambda *a, **k: _FakeRedis()
    )
    monkeypatch.setattr(
        "app.services.kalshi_api.KalshiAPIService", lambda *a, **k: venue
    )

    stats = await bw._backfill_kalshi_winners(limit=100, dry_run=dry_run)
    return stats, session, venue


# ------------------------------------------------- the gate fires, and when


@pytest.mark.asyncio
class TestTheGateFiresOnAFullySettledEvent:
    """The #7857 specimen, reduced to its venue answer."""

    async def test_an_all_finalized_event_flips_the_market_to_resolved(
        self, monkeypatch
    ):
        # `/events/FEDHIKE` on 2026-09-21: three rungs, all finalized/yes.
        stats, session, _ = await _drive(
            monkeypatch,
            ticker="FEDHIKE",
            event=_event(
                ("FEDHIKE-26DEC31", "finalized", "yes"),
                ("FEDHIKE-27JUN30", "finalized", "yes"),
                ("FEDHIKE-27DEC31", "finalized", "yes"),
            ),
        )
        assert stats["status_resolved"] == 1
        assert len(session.market_status_updates()) == 1

    async def test_the_flip_is_scoped_to_this_kalshi_event_and_spares_resolved_rows(
        self, monkeypatch
    ):
        """The WHERE, asserted — the half `_LoopSession` cannot see.

        Every clause here is load-bearing. Without `source`, a Polymarket row
        sharing the external id is collateral; without `external_id`, the
        statement is a table-wide flip; without `status != 'resolved'` the
        `settled_at` COALESCE is the only thing between a re-resolve and a
        rewritten settlement stamp, and COALESCE is a second line of defence,
        not the first.
        """
        _, session, _ = await _drive(
            monkeypatch,
            ticker="FEDHIKE",
            event=_event(("FEDHIKE-26DEC31", "finalized", "yes")),
        )
        sql = session.market_status_updates()[0]
        assert "futures_markets.source = 'kalshi'" in sql
        assert "futures_markets.external_id = 'FEDHIKE'" in sql
        assert "futures_markets.status != 'resolved'" in sql

    async def test_the_settled_stamp_is_coalesced_and_not_overwritten(
        self, monkeypatch
    ):
        """A market resolved once, reopened by a poll and resolved again keeps
        its FIRST stamp. A bare `now()` would silently re-date every settlement
        this pass touches, and nothing downstream would look wrong."""
        _, session, _ = await _drive(
            monkeypatch,
            ticker="FEDHIKE",
            event=_event(("FEDHIKE-26DEC31", "finalized", "yes")),
        )
        sql = session.market_status_updates()[0].lower()
        assert "coalesce" in sql
        assert "settled_at" in sql


# --------------------------------------------- the gate HOLDS, and when


@pytest.mark.asyncio
class TestTheGateHoldsOnEverythingElse:
    """0 of 121 mid-flight events flipped in the venue probe. These are why."""

    async def test_a_mid_flight_ladder_with_settled_rungs_does_not_flip(
        self, monkeypatch
    ):
        """`KXYTVIEWSW-ARI26SEP20`, read live 2026-09-21: 4 `finalized` + 11
        `active`. This is the COMMON shape of our open-with-a-graded-leg
        population — 1,924 markets — and flipping it would take a live market
        off every surface that filters on status. The legs still grade; only the
        status is withheld."""
        stats, session, _ = await _drive(
            monkeypatch,
            ticker="KXYTVIEWSW-ARI26SEP20",
            event=_event(
                ("KXYTVIEWSW-ARI26SEP20-T1", "finalized", "yes"),
                ("KXYTVIEWSW-ARI26SEP20-T2", "finalized", "no"),
                ("KXYTVIEWSW-ARI26SEP20-T3", "active", ""),
            ),
        )
        assert stats["status_resolved"] == 0
        assert session.market_status_updates() == []
        # ...and the grading half is untouched: this is a withheld STATUS, not a
        # withheld grade. Two finalized legs were still written.
        assert stats["winners_set"] + stats["losers_set"] == 2

    async def test_an_event_with_no_markets_is_not_a_settlement(self, monkeypatch):
        """31 of the tickers probed answered 200 with an EMPTY market list.
        `all_terminal([])` is False on purpose: an absence is not a fact
        (gotcha #53), and "the venue listed nothing" is the single most
        available way to flip the whole table by accident."""
        stats, session, _ = await _drive(
            monkeypatch, ticker="KXDNCAUTOPSY-26", event={"markets": []}
        )
        assert stats["status_resolved"] == 0
        assert session.market_status_updates() == []

    async def test_a_missing_event_flips_nothing(self, monkeypatch):
        stats, session, _ = await _drive(
            monkeypatch, ticker="KXGONE-26", event=None
        )
        assert stats["status_resolved"] == 0
        assert session.market_status_updates() == []

    async def test_dry_run_writes_no_status(self, monkeypatch):
        stats, session, _ = await _drive(
            monkeypatch,
            ticker="FEDHIKE",
            event=_event(("FEDHIKE-26DEC31", "finalized", "yes")),
            dry_run=True,
        )
        assert stats["status_resolved"] == 0
        assert session.market_status_updates() == []


@pytest.mark.asyncio
class TestTheInactiveHoldoutIsAKnownResidual:
    """A KNOWN MISS, pinned so it is found rather than rediscovered.

    `KXPGATOP20-BICA26` and `KXPGATOP5-BICA26`, read live 2026-09-21: **133
    `finalized` + 1 `inactive`** each. A golf top-20 market whose whole field has
    settled except one player who never traded stays `open`, so its page keeps
    reading live after the tournament.

    This test asserts the CURRENT behaviour, and it is not an endorsement. If a
    later change admits `inactive`, this arm goes red and its author reads the
    reason: `inactive` is the ordinary state of an unstarted market (622 of 2,000
    in the #1818 probe), so widening `TERMINAL_STATUSES` would flip live markets,
    and the repair needs its own census.
    """

    async def test_one_inactive_leg_holds_an_otherwise_finished_event_open(
        self, monkeypatch
    ):
        stats, session, _ = await _drive(
            monkeypatch,
            ticker="KXPGATOP20-BICA26",
            event=_event(
                ("KXPGATOP20-BICA26-A", "finalized", "yes"),
                ("KXPGATOP20-BICA26-B", "finalized", "no"),
                ("KXPGATOP20-BICA26-C", "inactive", ""),
            ),
        )
        assert stats["status_resolved"] == 0, (
            "behaviour changed: see this class's docstring before accepting it"
        )
        assert session.market_status_updates() == []


# ------------------------------------------------------- the class guard


class TestTheGateIsThePollersOwnHelperAndNotACopy:
    """The design claim, guarded: ONE rule for "this event is over".

    A behavioural test cannot see this. Replace `kms.all_terminal(...)` in the
    grader with an inline `all(s in {"closed", "settled", "determined",
    "finalized"} for s in ...)` and every arm above stays green — while the two
    call sites are now free to drift, which is the #1818 defect exactly (four
    modules encoded Kalshi's status vocabulary from memory; the one that wrote
    `futures_markets.status` on every poll was inverted, and reverted every
    settlement fix the backfill made for weeks).
    """

    def test_the_poller_still_derives_status_from_all_terminal(self):
        """The premise. A guard that asserts parity with a call site that has
        moved is asserting nothing, so the premise is checked, not assumed."""
        source = POLL_SOURCE.read_text()
        assert "all_terminal(" in source, (
            "_poll_kalshi_markets no longer calls all_terminal — the grader's "
            "gate was built to match it; re-derive the parity before editing "
            "this guard away"
        )

    def test_the_grader_calls_the_shared_helper(self):
        source = BACKFILL_SOURCE.read_text()
        tree = ast.parse(source)
        calls = {
            node.func.attr
            for node in ast.walk(tree)
            if isinstance(node, ast.Call)
            and isinstance(node.func, ast.Attribute)
        }
        assert "all_terminal" in calls, (
            "the #7870 status gate must call kalshi_market_status.all_terminal, "
            "not re-encode Kalshi's terminal statuses (#1818)"
        )

    def test_no_hand_rolled_terminal_status_set_in_the_grader(self):
        """The mutation this file exists to catch, as source text."""
        source = BACKFILL_SOURCE.read_text()
        for spelling in ('"determined"', "'determined'"):
            assert spelling not in source, (
                f"{spelling} is spelled in backfill_winners.py — Kalshi's status "
                "vocabulary belongs to app/utils/kalshi_market_status.py alone"
            )

    def test_the_helper_still_refuses_an_empty_event(self):
        """`all_terminal([])` is False, and the grader leans on it for the
        empty-market-list case rather than testing `nested` a second time. If
        the helper ever returns True for empty, the grader flips every event the
        venue answers with nothing."""
        assert kms.all_terminal([]) is False
        assert kms.all_terminal(["finalized"]) is True
        assert kms.all_terminal(["finalized", "active"]) is False
