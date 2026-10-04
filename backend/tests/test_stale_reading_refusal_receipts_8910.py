"""#8910 — a refused stale reading leaves one receipt naming its event.

## why the receipt exists

The poll and the 15-minute matcher both refuse a reading whose rows were seen
EARLIER than the stored entry's writer saw them (the pre-goal price put back
over the socket's post-goal one). Until now the only trace of a refusal was the
aggregate `stale_readings_refused`, which neither writer logged, and which on
the WebSocket lane also counts a row deleted mid-batch. Codex's review of
live/659 accepted the guard but could not accept "an older reading was refused
on THIS game" from a count. The held-page acceptance needs exactly that: one
line, written at the refusal, naming the writer, event, source and both
OBSERVATION clocks of the row that regressed.

## the arms

* matcher refusal: the real `_phase2_persist_group_reading` refuses, writes no
  hero and no chart point, commits once, and logs one attributed receipt;
* precision: a two-row (devigged) reading where only ONE row regressed names
  that row alone, with the lag of that row (not of its fresher sibling);
* matcher healthy control: a newer reading writes, and logs no receipt;
* receipt failure, both writers: a receipt that raises cannot skip the commit
  that releases the row lock, and the refusal still stands.
"""

from __future__ import annotations

import logging
from datetime import timedelta

import pytest

from app.tasks import prediction_market_matching as pmm
from app.utils.aggregation import stamp_source_reading

from tests.test_phase2_writer_group_reading_cert767 import (
    NOW,
    _EventRow,
    _FakeSession,
    _Outcome,
    _cert759_group,
)
from tests.test_live_poll_refuses_a_reading_older_than_the_stored_stamp_8910 import (
    _beat,
    _now,
    _receipts,
    _fields,
    _stored_at,
    _written,
)

_LOGGER = "app.tasks.prediction_market_matching"
EVENT_ID = 15299603
HOME_ROW, AWAY_ROW = "9001", "9002"


class _SeenOutcome(_Outcome):
    """cert767's outcome, plus the id and `last_updated` an observation basis keys on."""

    def __init__(self, outcome_id, market_id, rank, name, probability, last_seen):
        super().__init__(market_id, rank, name, probability)
        self.id = outcome_id
        self.last_updated = last_seen


def _outcomes(*, home_seen, away_seen):
    return [
        _SeenOutcome(int(HOME_ROW), 9, 1, "Brandon Nakashima", 0.62, home_seen),
        _SeenOutcome(int(AWAY_ROW), 9, 2, "Alex Michelsen", 0.38, away_seen),
    ]


def _stored(basis: dict, value=0.40) -> dict:
    return stamp_source_reading(
        None, "polymarket", value, now=NOW, observed_basis=basis,
    )


def _stats() -> dict:
    return {"snapshots_written": 0, "snapshots_deduped": 0, "errors": []}


async def _persist(outcomes, stored):
    session = _FakeSession(outcomes, _EventRow(EVENT_ID, wps=stored))
    stats = _stats()
    spoke = await pmm._phase2_persist_group_reading(session, _cert759_group(), stats)
    return session, stats, spoke


def _matcher_reading_basis():
    """The two rows the matcher's reading is derived from, and when it saw them."""
    home_seen = NOW - timedelta(seconds=300)
    away_seen = NOW - timedelta(seconds=300)
    return home_seen, away_seen


@pytest.mark.asyncio
class TestTheMatcherRefusalLeavesAnAttributedReceipt:
    async def test_a_refused_matcher_reading_names_its_event_and_row(self, caplog):
        home_seen, away_seen = _matcher_reading_basis()
        stored_seen = NOW - timedelta(seconds=20)
        stored = _stored({
            HOME_ROW: stored_seen.timestamp(), AWAY_ROW: stored_seen.timestamp(),
        })
        with caplog.at_level(logging.INFO, logger=_LOGGER):
            session, stats, spoke = await _persist(
                _outcomes(home_seen=home_seen, away_seen=away_seen), stored,
            )

        # The refusal itself, unchanged.
        assert spoke is None
        assert stats["stale_readings_refused"] == 1, stats
        assert session.updates == [], "the stale reading was stamped"
        assert session.added == [], "the stale reading got a chart point"
        assert session.commits == 1, "the refusal must release the row lock"

        lines = _receipts(caplog)
        assert len(lines) == 1, lines
        got = _fields(lines[0])
        assert got["writer"] == "matcher", got
        assert got["event"] == str(EVENT_ID), got
        assert got["source"] == "polymarket", got
        assert got["stored_value"] == "0.4", got
        # The group speaks from its home row; the stored writer's basis has both.
        assert got["regressed_rows"] == HOME_ROW, got
        assert got["rejected_observed"] == f"{HOME_ROW}@{home_seen.isoformat()}", got
        assert got["stored_observed"] == (
            f"{HOME_ROW}@{stored_seen.isoformat()},{AWAY_ROW}@{stored_seen.isoformat()}"
        ), got
        assert got["max_observation_lag_s"] == "280.000", got
        # The value it WOULD have stamped is the oriented home probability.
        assert 0.0 < float(got["value"]) < 1.0, got

    async def test_a_devigged_reading_names_only_the_row_that_regressed(
        self, caplog
    ):
        """A devig averages two separately-fetched rows. Here this reading saw
        the away row LATER than the stored writer did and the home row EARLIER:
        the guard refuses (any shared row older), and the receipt must name the
        home row alone, with the home row's lag — not the fresher sibling's.

        The fake group above speaks from one row, so this arm drives the
        receipt with the two-row basis the devig builds, after confirming the
        guard itself refuses that exact pair."""
        from app.utils.aggregation import reading_regresses_stored_observation

        basis = {
            HOME_ROW: (NOW - timedelta(seconds=300)).timestamp(),
            AWAY_ROW: (NOW - timedelta(seconds=10)).timestamp(),
        }
        stored = _stored({
            HOME_ROW: (NOW - timedelta(seconds=60)).timestamp(),
            AWAY_ROW: (NOW - timedelta(seconds=120)).timestamp(),
        })
        assert reading_regresses_stored_observation(stored, "polymarket", basis)
        with caplog.at_level(logging.INFO, logger=_LOGGER):
            pmm._log_stale_reading_refusal(
                "matcher", EVENT_ID, "polymarket",
                value=0.6, basis=basis, stored_sources=stored,
            )
        got = _fields(_receipts(caplog)[0])
        assert got["regressed_rows"] == HOME_ROW, got
        assert got["max_observation_lag_s"] == "240.000", got
        assert got["rejected_observed"].count("@") == 2, got

    async def test_control_a_newer_matcher_reading_writes_and_logs_nothing(
        self, caplog
    ):
        home_seen, away_seen = NOW - timedelta(seconds=20), NOW - timedelta(seconds=20)
        stored_seen = NOW - timedelta(seconds=300)
        stored = _stored({
            HOME_ROW: stored_seen.timestamp(), AWAY_ROW: stored_seen.timestamp(),
        })
        with caplog.at_level(logging.INFO, logger=_LOGGER):
            session, stats, spoke = await _persist(
                _outcomes(home_seen=home_seen, away_seen=away_seen), stored,
            )
        assert spoke == 9, "control: the healthy reading never spoke"
        assert stats.get("stale_readings_refused", 0) == 0, stats
        assert session.stamped_sources() is not None, "control: nothing stamped"
        assert len(session.added) == 1 and session.commits == 1
        assert _receipts(caplog) == [], "a write logged a refusal receipt"


@pytest.mark.asyncio
class TestAReceiptThatFailsCannotBreakTheRefusal:
    async def test_matcher_still_commits_and_refuses(self, monkeypatch, caplog):
        def _boom(_basis):
            raise ValueError("render failed")

        monkeypatch.setattr(pmm, "_render_observation_basis", _boom)
        home_seen, away_seen = _matcher_reading_basis()
        stored_seen = NOW - timedelta(seconds=20)
        stored = _stored({
            HOME_ROW: stored_seen.timestamp(), AWAY_ROW: stored_seen.timestamp(),
        })
        with caplog.at_level(logging.INFO, logger=_LOGGER):
            session, stats, spoke = await _persist(
                _outcomes(home_seen=home_seen, away_seen=away_seen), stored,
            )
        assert spoke is None and stats["stale_readings_refused"] == 1, stats
        assert session.updates == [] and session.added == []
        assert session.commits == 1, "a failed receipt skipped the lock release"
        warned = [
            r.getMessage() for r in caplog.records
            if r.levelno == logging.WARNING and "receipt failed" in r.getMessage()
        ]
        assert len(warned) == 1 and f"event={EVENT_ID}" in warned[0], warned

    async def test_poll_still_commits_before_anything_else(self, monkeypatch, caplog):
        def _boom(_basis):
            raise ValueError("render failed")

        monkeypatch.setattr(pmm, "_render_observation_basis", _boom)
        now = _now()
        with caplog.at_level(logging.INFO, logger=_LOGGER):
            stamped, points, stats = await _written(
                monkeypatch,
                _beat(last_seen=now - timedelta(seconds=150)),
                _stored_at(now - timedelta(seconds=15)),
            )
        assert stats["stale_readings_refused"] == 1 and stamped == [] and points == []
        journal = _written.last_session.journal
        read_at = journal.index(("execute", "select:win_probability_sources"))
        assert journal[read_at + 1] == ("commit", None), journal[read_at : read_at + 3]
        warned = [
            r.getMessage() for r in caplog.records
            if r.levelno == logging.WARNING and "receipt failed" in r.getMessage()
        ]
        assert len(warned) == 1 and "writer=poll event=101" in warned[0], warned
