"""#4571 / Sol a552 review — the Odds stamp is decided against the row AT the write.

`_poll_all_odds` loads the event, decides, and writes by primary key alone: its
UPDATE never re-asserts the score it loaded (its status must land even when its
score is refused). So another writer can commit a different WHOLE score between
the load and the write. Sol reproduced two arms on a552d55067, where the stamp
was judged against the loaded pair:

1. Odds loads 3-0 and reads 3-0 at T1; StatPal commits 7-1 at T2; Odds' 3-0
   lands and "unchanged" kept StatPal@T2 — a stamp taken for 7-1 — on 3-0.
2. Odds reads (3, None) over loaded 3-0; StatPal commits 7-1; Odds' home 3 lands
   on the away 1 and the row ended 3-1 under StatPal's 7-1 stamp, a tuple nobody
   ever read whole.

Every arm here drives the REAL `_poll_all_odds` through the #7147 harness (real
payload, real parser, real guards, real Core UPDATE on a real sqlite row) and
reads the row back through a fresh session. The concurrent writer is injected at
the only point the race exists: immediately before the Odds score UPDATE runs,
after the pass has loaded and decided.

The controls pin what the repair must NOT change: a healthy same-tuple
confirmation still advances, an older one never regresses a newer, a changed
half reading still clears, an unchanged half reading still keeps, and a refused
score leaves a held stamp exactly as it was.
"""

import asyncio
import importlib.util
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session


def _harness():
    """The #7147 e2e rail, loaded by PATH (tests/ is not a package), as a fresh
    module so patching its shim here cannot leak into that file's own run."""
    path = Path(__file__).with_name(
        "test_a_settled_final_survives_the_writer_7147_e2e.py"
    )
    spec = importlib.util.spec_from_file_location("_odds_rail_4571", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


T_HELD = datetime.now(timezone.utc) - timedelta(hours=2)


def _run(*, specimen, home, away, completed=False, interloper=None):
    """Run the real pass; `interloper` = (home, away, source, at) is committed
    to the specimen row immediately before the Odds score UPDATE executes.

    Returns (result, row, read_window, interloper_fired).
    """
    h = _harness()
    fired = []

    class _RacingShim(h._AsyncShim):
        async def execute(self, statement, params=None):
            is_score_write = (
                interloper is not None
                and not fired
                and getattr(statement, "is_update", False)
                and statement.table.name == "events"
                and "score_source" in str(statement.compile())
            )
            if is_score_write:
                from app.models.models import Event

                i_home, i_away, i_source, i_at = interloper
                self._s.execute(
                    Event.__table__.update()
                    .where(Event.external_id == specimen["external_id"])
                    .values(
                        home_score=i_home, away_score=i_away,
                        score_source=i_source, score_observed_at=i_at,
                    )
                )
                fired.append(True)
            return await super().execute(statement, params)

    h._AsyncShim = _RacingShim
    before = datetime.now(timezone.utc)
    result, engine, event_id, service = asyncio.run(h._run_pass(
        specimen=specimen,
        payload=h._payload_for(specimen, home=home, away=away, completed=completed),
    ))
    after = datetime.now(timezone.utc)
    service.get_scores.assert_awaited_once()

    from app.models.models import Event

    with Session(engine) as fresh:
        row = fresh.execute(
            select(
                Event.home_score, Event.away_score, Event.status,
                Event.score_source, Event.score_observed_at,
            ).where(Event.id == event_id)
        ).one()
    return result, row, (before, after), bool(fired)


def _live_specimen(h_score=3, a_score=0, **overrides):
    """An unanchored live row — no #6056 deferral, no #7147 refusal applies."""
    now = datetime.now(timezone.utc)
    base = dict(
        external_id="odds-api-specimen",
        espn_id=None,
        home_team_name="Red Sox",
        away_team_name="Yankees",
        commence_time=now - timedelta(hours=1),
        status="live",
        home_score=h_score,
        away_score=a_score,
        score_source="espn",
        score_observed_at=T_HELD,
    )
    base.update(overrides)
    return base


def _stamped_in(row, window):
    before, after = window
    return row.score_source == "odds_api" and before <= row.score_observed_at <= after


# ── the two arms Sol reproduced ──────────────────────────────────────────────


def test_full_unchanged_reading_never_keeps_a_stamp_for_the_concurrent_score():
    t2 = datetime.now(timezone.utc) + timedelta(minutes=5)
    _result, row, window, fired = _run(
        specimen=_live_specimen(3, 0), home=3, away=0,
        interloper=(7, 1, "statpal", t2),
    )
    assert fired, "the concurrent writer never ran — the race was not exercised"
    assert (row.home_score, row.away_score) == (3, 0)
    assert (row.score_source, row.score_observed_at) != ("statpal", t2), (
        "3-0 is served under StatPal's stamp, which confirmed 7-1"
    )
    assert _stamped_in(row, window), (
        "3-0 is the tuple Odds read whole at its scores read; that read dates it"
    )


def test_partial_unchanged_reading_never_keeps_a_stamp_for_the_concurrent_score():
    t2 = datetime.now(timezone.utc) + timedelta(minutes=5)
    _result, row, _window, fired = _run(
        specimen=_live_specimen(3, 0), home=3, away=None,
        interloper=(7, 1, "statpal", t2),
    )
    assert fired, "the concurrent writer never ran — the race was not exercised"
    assert (row.home_score, row.away_score) == (3, 1)
    assert (row.score_source, row.score_observed_at) == (None, None), (
        "3-1 was never read whole by anyone; no stamp may date it"
    )


# ── controls: what the repair must not change ────────────────────────────────


def test_healthy_same_tuple_confirmation_still_advances():
    _result, row, window, _ = _run(specimen=_live_specimen(3, 0), home=3, away=0)
    assert (row.home_score, row.away_score) == (3, 0)
    assert _stamped_in(row, window)


def test_an_older_confirmation_never_regresses_a_newer_one_on_the_same_tuple():
    t2 = datetime.now(timezone.utc) + timedelta(minutes=5)
    _result, row, _window, fired = _run(
        specimen=_live_specimen(3, 0), home=3, away=0,
        interloper=(3, 0, "statpal", t2),
    )
    assert fired
    assert (row.home_score, row.away_score, row.score_source) == (3, 0, "statpal")
    assert row.score_observed_at == t2


def test_a_changed_full_reading_takes_its_own_clock():
    _result, row, window, _ = _run(specimen=_live_specimen(3, 0), home=4, away=0)
    assert (row.home_score, row.away_score) == (4, 0)
    assert _stamped_in(row, window)


def test_a_changed_half_reading_still_clears():
    _result, row, _window, _ = _run(specimen=_live_specimen(3, 0), home=7, away=None)
    assert (row.home_score, row.away_score) == (7, 0)
    assert (row.score_source, row.score_observed_at) == (None, None)


def test_an_unchanged_half_reading_still_keeps_the_held_stamp():
    _result, row, _window, _ = _run(specimen=_live_specimen(3, 0), home=3, away=None)
    assert (row.home_score, row.away_score) == (3, 0)
    assert (row.score_source, row.score_observed_at) == ("espn", T_HELD)


@pytest.mark.parametrize("home, away", [(7, 2), (None, 2)])
def test_a_refused_score_leaves_the_held_stamp_and_the_status_alone(home, away):
    """#7147's refusal: a settled ESPN-anchored final the feed disagrees with
    (whole, or one side landing on the stored other half). The score is
    declined, the status is not touched, and the stamp is neither refreshed
    nor cleared — the refused write carries no stamp column at all, which the
    armed interloper (it fires only on an UPDATE carrying `score_source`)
    proves by never firing."""
    now = datetime.now(timezone.utc)
    specimen = _live_specimen(
        7, 3, espn_id="401-espn-specimen", status="completed",
        commence_time=now - timedelta(hours=3), completed_at=now - timedelta(hours=1),
    )
    result, row, _window, fired = _run(
        specimen=specimen, home=home, away=away, completed=True,
        interloper=(8, 3, "espn", now + timedelta(minutes=5)),
    )
    assert result["scores_refused_settled_repoison"] == 1
    assert not fired, "a refused Odds write still sent stamp columns"
    assert (row.home_score, row.away_score, row.status) == (7, 3, "completed")
    assert (row.score_source, row.score_observed_at) == ("espn", T_HELD)
