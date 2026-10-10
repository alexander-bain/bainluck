"""#10022 — an open Kalshi contract the socket sees finalize is graded from the socket, per leg.

The ship: on 2026-10-01 Kalshi finalized all seven CHC–SD Wild Card series
contracts at 05:11Z, and 80 minutes later the finished series still printed
``SD wins 2-1 12%`` and ``Over 2.5 total games 38%`` — the #9484 open-contract
connections streamed those contracts' prices to the close and subscribed
``ticker`` alone, so their result waited for the REST sweep (``CHC20`` took
23 h). These tests drive the real consumer with a recording socket and assert:

1. the venue's declaration is read through the shared three-state judgment
   (``yes``/``no`` on a result-carrying state; ``scalar``/``""``/``closed``
   grade nothing), from ``status`` or the v2 channel's ``event_type``;
2. an open contract's frame reaches the PER-LEG grader with that one leg, from
   either connection, and never the two-sided handler;
3. an open-contract connection never acts on a linked-slate frame — the game
   socket owns those, exactly once;
4. what the grader changed is what is counted and announced: a re-delivered
   frame (one per connection) counts once, and a board announces ``terminal``
   only when the grader says it resolved.

The SQL — one leg written, no sibling crowned, the board resolved only when no
leg is left without a venue grade — is asserted against real Postgres in
``tests/integration/test_open_contract_leg_grade_pg_10022.py``.
"""

import json

import pytest

import app.tasks.kalshi_ws as kalshi_task
from app.tasks import ws_open_contracts as oc
from tests.test_ws_open_contract_prices_9484 import (
    LINKED_TICKER,
    OPEN_TICKER,
    _run,
    _settle,
)


SD20 = "KXMLBSERIESSCORE-26CHCSDWC-SD20"
SD21 = "KXMLBSERIESSCORE-26CHCSDWC-SD21"


def _v2(ticker, event_type="determined", result="no"):
    """The v2 lifecycle channel names the transition in ``event_type``."""
    return json.dumps({"type": "market_lifecycle_v2", "msg": {
        "market_ticker": ticker, "event_type": event_type, "result": result,
    }})


# ------------------------------------------------------------ the verdict ----


class TestTheVerdictIsTheSharedThreeStateJudgment:
    @pytest.mark.parametrize("key", ["status", "event_type"])
    @pytest.mark.parametrize("state", ["determined", "finalized"])
    @pytest.mark.parametrize("result,won", [("yes", True), ("no", False)])
    def test_a_declared_side_grades(self, key, state, result, won):
        msg = {"market_ticker": SD21.lower(), key: state, "result": result}
        assert oc.lifecycle_verdict(msg) == (SD21, won)

    @pytest.mark.parametrize("msg", [
        {"market_ticker": SD21, "status": "finalized", "result": "scalar"},
        {"market_ticker": SD21, "status": "finalized", "result": ""},
        {"market_ticker": SD21, "status": "determined", "result": None},
        # `closed` is terminal but carries no result (#1818): never evidence.
        {"market_ticker": SD21, "status": "closed", "result": "no"},
        {"market_ticker": SD21, "event_type": "deactivated", "result": "no"},
        {"market_ticker": SD21, "event_type": "close_date_updated"},
        {"market_ticker": "", "status": "finalized", "result": "yes"},
        {"status": "finalized", "result": "yes"},
    ])
    def test_no_declared_side_grades_nothing(self, msg):
        assert oc.lifecycle_verdict(msg) is None

    def test_not_a_mapping_is_nothing(self):
        assert oc.lifecycle_verdict(None) is None
        assert oc.lifecycle_verdict("finalized") is None


# ------------------------------------------------------------ the routing ----


def _recording_grader(monkeypatch, answers=None):
    """Replaces the SQL grader; answers each call from ``answers`` (default:
    graded, not resolved)."""
    calls = []
    answers = list(answers or [])

    class _Row:
        def __init__(self, **kw):
            self.__dict__.update(kw)

    async def _grade(_session, *, market_id, outcome_id, state, result):
        from app.utils.kalshi_market_status import gradeable_winner

        calls.append((market_id, outcome_id, gradeable_winner(state, result)))
        if answers:
            graded, resolved = answers.pop(0)
        else:
            graded, resolved = True, False
        return (
            _Row(id=outcome_id, last_updated="2026-10-01T05:11:20+00:00")
            if graded else None,
            _Row(id=market_id, settled_at="2026-10-01T05:11:21+00:00")
            if resolved else None,
        )

    monkeypatch.setattr(oc, "grade_open_contract_leg", _grade)
    return calls


def _recording_changes(monkeypatch):
    changes = []

    def _queue(_session, **kw):
        changes.append(kw)

    monkeypatch.setattr(kalshi_task, "queue_market_change", _queue)
    return changes


class TestAnOpenContractFrameIsGradedPerLeg:
    async def test_on_its_own_connection(self, monkeypatch):
        calls = _recording_grader(monkeypatch)
        changes = _recording_changes(monkeypatch)
        stats, _record, state = await _run(
            monkeypatch,
            frames_for={SD21: [_v2(SD21, result="no")]},
            open_rows=[(SD20, 62713436, 236765872), (SD21, 62713436, 236765873)],
        )

        assert calls == [(62713436, 236765873, False)], "one leg, its own verdict"
        assert state["market_writes"] == [], "the two-sided handler never ran"
        assert stats["open_contract_settlements"] == 1
        assert stats["open_contract_markets_resolved"] == 0
        assert [c["terminal"] if "terminal" in c else False for c in changes] == [False]
        assert changes[0]["outcome_observed_at"] == {
            236765873: "2026-10-01T05:11:20+00:00"
        }

    async def test_the_board_announces_terminal_only_when_the_grader_resolved_it(
        self, monkeypatch,
    ):
        _recording_grader(monkeypatch, answers=[(True, True)])
        changes = _recording_changes(monkeypatch)
        stats, _record, _state = await _run(
            monkeypatch,
            frames_for={SD20: [_v2(SD20, result="yes")]},
            open_rows=[(SD20, 62713436, 236765872)],
        )

        assert stats["open_contract_markets_resolved"] == 1
        terminal = [c for c in changes if c.get("terminal")]
        assert terminal == [{
            "market_id": 62713436, "source": "kalshi", "outcome_observed_at": {},
            "terminal": True, "updated_at": "2026-10-01T05:11:21+00:00",
        }]

    async def test_a_redelivered_frame_counts_once(self, monkeypatch):
        """The frame is delivered twice; the second write changes nothing (the
        grader returns None) and is neither counted nor announced.

        ded5f8ed39: a frame for a ticker another connection owns is that
        connection's, so the game socket no longer supplies the second copy;
        the shard that owns the leg redelivers it instead."""
        calls = _recording_grader(monkeypatch, answers=[(True, False), (False, False)])
        changes = _recording_changes(monkeypatch)
        stats, _record, _state = await _run(
            monkeypatch,
            frames_for={
                OPEN_TICKER: [_settle(OPEN_TICKER), _settle(OPEN_TICKER)],
            },
            open_rows=[(OPEN_TICKER, 50, 501)],
        )

        assert calls == [(50, 501, False), (50, 501, False)]
        assert stats["open_contract_settlements"] == 1
        assert len(changes) == 1

    async def test_a_scalar_frame_grades_nothing_and_is_counted(self, monkeypatch):
        calls = _recording_grader(monkeypatch)
        stats, _record, _state = await _run(
            monkeypatch,
            frames_for={SD21: [_v2(SD21, event_type="settled", result="scalar")]},
            open_rows=[(SD21, 62713436, 236765873)],
        )

        assert calls == []
        assert stats["open_contract_lifecycle_unverdicted"] == 1
        assert stats["open_contract_settlements"] == 0

    async def test_a_grader_error_is_an_error_not_a_settlement(self, monkeypatch):
        async def _boom(*_a, **_kw):
            raise RuntimeError("deadlock")

        monkeypatch.setattr(oc, "grade_open_contract_leg", _boom)
        stats, _record, _state = await _run(
            monkeypatch,
            frames_for={SD21: [_v2(SD21)]},
            open_rows=[(SD21, 62713436, 236765873)],
        )

        assert stats["errors"] >= 1
        assert stats["open_contract_settlements"] == 0


class TestAnOpenContractConnectionLeavesTheGameSlateAlone:
    async def test_a_linked_frame_on_the_shard_does_nothing(self, monkeypatch):
        """Delivered on the OPEN-CONTRACT connection (it rides OPEN_TICKER's
        subscription): a linked-slate ticker is the game socket's to settle."""
        calls = _recording_grader(monkeypatch)
        stats, _record, state = await _run(
            monkeypatch,
            frames_for={OPEN_TICKER: [_settle(LINKED_TICKER, result="yes")]},
            open_rows=[(OPEN_TICKER, 50, 501)],
        )

        assert calls == []
        assert state["market_writes"] == []
        assert stats["settlements"] == 0

    async def test_the_settlement_undo_switch_never_grades(self, monkeypatch):
        """``WS_OPEN_CONTRACT_SETTLEMENT=0``: the shard subscribes ``ticker``
        alone, and a frame for its leg arriving on the GAME socket grades
        nothing either — the pre-#10022 behaviour, whole."""
        monkeypatch.setenv("WS_OPEN_CONTRACT_SETTLEMENT", "0")
        calls = _recording_grader(monkeypatch)
        stats, _record, state = await _run(
            monkeypatch,
            frames_for={LINKED_TICKER: [_settle(OPEN_TICKER)]},
            open_rows=[(OPEN_TICKER, 50, 501)],
        )

        assert oc.open_contract_channels() == ["ticker"]
        assert calls == []
        assert state["market_writes"] == []
        assert stats["open_contract_settlements"] == 0
