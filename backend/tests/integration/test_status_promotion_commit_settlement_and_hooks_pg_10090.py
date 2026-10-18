"""What the status task's mid-pass commit must not cost. #10090, real Postgres.

The status task now commits a completed scheduled → live promotion before its
later arms read history, and drops the rows it loaded (``expunge_all``), so a
blend stamp can reach a game that has just started. That fix's own file,
``test_status_task_releases_started_rows_pg_10090.py``, proves the row is
released and that a later arm reads the committed row. These are CERT-4214's
two independent witnesses, banked as permanent guards for what the same change
could break next to it:

* A GENUINE SETTLEMENT IS KEPT: a second session settles the game (completed
  110-95, ``completed_at``, a new Kalshi source) while the later arms run. The
  pass must leave that result, its timestamp and its source exactly as written.
  It is not the bogus-final shape (0-0, no ``completed_at``) the repair arm
  exists for, so nothing may "repair" it back to live.
* THE PUBLICATION HOOKS SURVIVE THE COMMIT AND THE EXPUNGE: a non-venue frame
  queued with the promotion is recorded once at its commit and is ready to
  publish after it. After ``expunge_all`` and a fresh select, a second frame
  queued on the same session is recorded and kept beside the first, and an
  empty third commit records and readies nothing new.

Limit, stated so nobody quotes more than this proves: the hook case replaces
``record_committing_publications`` with a capture. It checks the hook
lifecycle on a real session and transaction, NOT that the publication table
holds those rows.

The seeded game, the real pass and the concurrent writer are the fix file's
own helpers, so both files exercise the same pass the same way.
"""

from __future__ import annotations

import os

import pytest

from tests.integration.test_status_task_releases_started_rows_pg_10090 import (  # noqa: F401 — ``seeded`` is a fixture
    WRITER_SOURCE,
    _concurrent_write,
    _run_pass,
    seeded,
)

#: The #7617 step's disposable database, as the fix file uses. Named here so
#: ``test_pg_gated_tests_are_named_in_ci`` sees this file as gated.
DB_URL = os.environ.get("DELAY_CONTRACT_DATABASE_URL")

pytestmark = [pytest.mark.asyncio]

needs_postgres = pytest.mark.skipif(
    not DB_URL,
    reason=(
        "set DELAY_CONTRACT_DATABASE_URL to run the real-Postgres status-task "
        "settlement and publication-hook contract (CI job `search-recall` "
        "provisions a disposable one)"
    ),
)


@needs_postgres
async def test_a_genuine_settlement_during_the_later_arms_is_kept(seeded):
    engine, maker, event_id = seeded
    from sqlalchemy import text

    outcomes = []

    async def _settle():
        outcomes.append(
            await _concurrent_write(
                engine,
                event_id,
                "status = 'completed', home_score = 110, away_score = 95, "
                "completed_at = now(), win_probability_sources = "
                "COALESCE(win_probability_sources, '{}'::jsonb) || CAST(:src AS jsonb)",
            )
        )

    stats = await _run_pass(maker, _settle)

    async with maker() as session:
        row = (
            await session.execute(
                text(
                    "SELECT status, home_score, away_score, completed_at, "
                    "commence_time, win_probability_sources FROM events WHERE id = :id"
                ),
                {"id": event_id},
            )
        ).one()

    assert stats["scheduled_to_live"] == 1
    assert outcomes == ["written"], (
        "the settlement under a 500 ms lock budget was refused while the pass "
        "ran its later arms"
    )
    assert (row.status, row.home_score, row.away_score) == ("completed", 110, 95), (
        "the pass overwrote a genuine settlement written while its later arms ran"
    )
    assert row.completed_at is not None
    assert row.completed_at >= row.commence_time
    assert row.win_probability_sources["kalshi"] == WRITER_SOURCE["kalshi"]
    assert row.win_probability_sources["espn"] == {"home_win_prob": 0.617}
    assert stats["repaired_bogus_completed"] == 0, (
        "the repair arm treated a genuine 110-95 final as a bogus one"
    )


@needs_postgres
async def test_publication_hooks_keep_committed_frames_across_expunge(
    seeded, monkeypatch
):
    _engine, maker, event_id = seeded
    from sqlalchemy import select

    from app.models.models import Event
    from app.utils import nonvenue_live_push as push
    from app.utils import probability_publication as publication

    records = []
    monkeypatch.setattr(publication, "recording_enabled", lambda: True)
    monkeypatch.setattr(
        publication,
        "record_committing_publications",
        lambda _session, entries: records.append(entries),
    )

    async with maker() as session:
        event = (
            await session.execute(select(Event).where(Event.id == event_id))
        ).scalar_one()
        event.status = "live"
        frame = {
            "event_id": event_id,
            "status": "live",
            "source_value": 0.6,
            "source": "espn",
            "p": 0.6,
        }
        push._queue(
            session, frame, event, dict(event.win_probability_sources), {"rev": 1}
        )
        await session.commit()
        session.expunge_all()

        # The promotion's commit recorded its frame once and readied it.
        assert push._PENDING not in session.info
        assert session.info[push._READY] == [frame]
        assert len(records) == 1

        # A fresh select after the expunge is a new object on the same session,
        # and the listeners the first frame installed still fire for it.
        event2 = (
            await session.execute(select(Event).where(Event.id == event_id))
        ).scalar_one()
        assert event2 is not event
        frame2 = {**frame, "p": 0.7, "source_value": 0.7}
        push._queue(
            session, frame2, event2, dict(event2.win_probability_sources), {"rev": 2}
        )
        await session.commit()
        assert push._PENDING not in session.info
        assert session.info[push._READY] == [frame, frame2], (
            "the second commit's frame replaced or lost the first committed frame"
        )
        assert len(records) == 2

        # An empty commit records and readies nothing new.
        await session.commit()
        assert len(records) == 2, "an empty commit called the recorder again"
        assert session.info[push._READY] == [frame, frame2]
