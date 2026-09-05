"""The stamper banks the ledger row, and the two disagree on purpose.

`stamp_nfl_statpal_fixtures` now returns an `agreement` block alongside its
stamping receipts. The two are answers to different questions and are expected
to differ:

  * the STAMPER asks *may I write an identity claim on this?* and requires both
    team names and a kickoff within ±1h, because a five-hour gap is not proof;
  * the AGREEMENT ROW asks *do both sides have this game?* and joins on the team
    pair alone, because a join keyed on kickoff cannot report a kickoff
    disagreement — it drops the row instead (spec rule 4).

The first production pass (2026-09-04 10:23Z) is what makes this concrete: it
reported 38 StatPal misses and 31 of our rows as misses, and most of those are
one game seen from both ends five hours apart. This file pins the coexistence,
because the cheap "fix" — widening the stamper's window until the two agree —
would write real identity claims on a guess.

## what each test can fail on

* the agreement row disappearing from a summary the bus reads daily;
* the denominator shrinking as the task succeeds, which makes today's row
  incomparable to yesterday's and the seven-day count meaningless;
* a row this pass just stamped being reported as unanchored;
* a failed read publishing a percentage;
* the stamper's ±1h window leaking into the measurement — including the way it
  leaked for real, as the bounds of the query that selects the population
  (CERT-962).
"""

from __future__ import annotations

from contextlib import asynccontextmanager
from datetime import datetime, timedelta, timezone
from importlib import import_module
from types import SimpleNamespace

import pytest

from app.services.anchor_channel import WROTE
from app.services.statpal_api import StatPalFixture
from app.utils.authority_agreement import READ_FAILED, READ_OK

#: `app/tasks/__init__.py` registers a task attribute that shadows the submodule
#: of the same name, so the dotted import hands back the task object and
#: `monkeypatch.setattr` fails on a name the module plainly has. `import_module`
#: reads `sys.modules` and is unambiguous.
task = import_module("app.tasks.stamp_nfl_statpal_fixtures")

NOW = datetime(2026, 9, 4, 10, 23, tzinfo=timezone.utc)
KICKOFF = datetime(2026, 9, 13, 20, 25, tzinfo=timezone.utc)


def _fixture(fixture_id, away, home, start, round_info="Regular Season / Week 1"):
    return StatPalFixture(
        fixture_id=fixture_id,
        home_team=home,
        away_team=away,
        start_time=start,
        status="scheduled",
        league="USA: NFL",
        round_info=round_info,
    )


def _candidate(event_id, away, home, start, held=None, status="scheduled"):
    """One CANDIDATES row, in the column order the task unpacks."""
    return (event_id, home, away, start, held, status)


class FakeResult:
    def __init__(self, rows=(), rowcount=0):
        self._rows = list(rows)
        self.rowcount = rowcount

    def fetchall(self):
        return self._rows


class RecordingSession:
    """Answers the task's two statements by EXACT text, and nothing else.

    An unrecognised statement raises. A fake that answers "no rows" to a query
    it does not know turns a real change in the task into a green test —
    gotcha #53 in test form.
    """

    def __init__(self, candidates, *, update_rowcount=1):
        self._candidates = candidates
        self._update_rowcount = update_rowcount
        self.commits = 0
        self.rollbacks = 0
        self.updates: list[dict] = []
        #: The bounds of every CANDIDATES read, in order. The task now makes two
        #: with DIFFERENT bounds — the narrow one it writes ids over and the wider
        #: one it measures the agreement row over — and a fake that handed both
        #: the same rows is what let CERT-962's defect pass a green suite.
        self.candidate_windows: list[tuple[datetime, datetime]] = []

    async def execute(self, statement, params=None):
        sql = str(statement)
        if sql == task.CANDIDATES:
            params = params or {}
            start, end = params["window_start"], params["window_end"]
            self.candidate_windows.append((start, end))
            # Honour the bounds, exactly as `WHERE commence_time BETWEEN` does.
            # A fake that ignores the window it was handed cannot tell a query
            # that reads our whole horizon from one that reads a slice of it.
            return FakeResult(
                [r for r in self._candidates if r[3] is not None and start <= r[3] <= end]
            )
        if sql == task.SET_FIXTURE_ID:
            self.updates.append(dict(params or {}))
            return FakeResult(rowcount=self._update_rowcount)
        raise AssertionError(
            "the task executed a statement this guard does not know:\n"
            f"{sql}\nAdd it here deliberately — do not let it return nothing."
        )

    async def commit(self):
        self.commits += 1

    async def rollback(self):
        self.rollbacks += 1


@pytest.fixture
def drive(monkeypatch):
    """Run one pass over the given fixtures and rows. Returns `(summary, session)`."""

    async def _drive(
        fixtures,
        candidates,
        *,
        outcome=WROTE,
        schedule_error=None,
        update_rowcount=1,
    ):
        session = RecordingSession(candidates, update_rowcount=update_rowcount)

        @asynccontextmanager
        async def _session():
            yield session

        import app.tasks.base as task_base

        monkeypatch.setattr(task_base, "get_task_session", _session)

        async def _schedule(sport):
            if schedule_error is not None:
                raise schedule_error
            return list(fixtures)

        async def _live(sport):
            return []

        async def _close():
            return None

        monkeypatch.setattr(
            task,
            "get_statpal_service",
            lambda: SimpleNamespace(
                get_schedule_fixtures=_schedule,
                get_live_fixtures=_live,
                close=_close,
            ),
        )

        async def _record_anchor(*args, **kwargs):
            return SimpleNamespace(outcome=outcome)

        monkeypatch.setattr(task, "record_anchor", _record_anchor)

        summary = await task._run_stamp_nfl_statpal_fixtures(now=NOW)
        return summary, session

    return _drive


# ---------------------------------------------------------------------------
# The coexistence. This is the file's reason to exist.
# ---------------------------------------------------------------------------


async def test_a_five_hour_gap_is_a_stamper_miss_and_a_ledger_agreement(drive):
    """The production Week-16 case: one game, two honest and opposite answers.

    TWO games, and the second is not decoration. Our kickoff is five hours from
    StatPal's, so the disagreeing row is a stamping candidate at all only if the
    write window is wider than five hours — which in production it always is (322
    fixtures spanning August to February) and in a one-fixture miniature it never
    is. A single-fixture version reaches the agreement row and never the stamper,
    so it would stay green on a stamper that had stopped receipting entirely.
    """
    statpal_kickoff = datetime(2026, 12, 27, 0, 0, tzinfo=timezone.utc)
    our_kickoff = datetime(2026, 12, 27, 5, 0, tzinfo=timezone.utc)
    week17 = datetime(2026, 12, 28, 18, 0, tzinfo=timezone.utc)

    summary, session = await drive(
        [
            _fixture(
                "280760",
                "Chicago Bears",
                "Green Bay Packers",
                week17,
                "Regular Season / Week 17",
            ),
            _fixture(
                "280750",
                "Tampa Bay Buccaneers",
                "Atlanta Falcons",
                statpal_kickoff,
                "Regular Season / Week 16",
            ),
        ],
        [
            _candidate(15184670, "Chicago Bears", "Green Bay Packers", week17),
            _candidate(
                15184664, "Tampa Bay Buccaneers", "Atlanta Falcons", our_kickoff
            ),
        ],
    )

    # The stamper takes Week 17 and refuses Week 16 in both directions.
    assert summary["stamped"] == 1
    assert summary["unmatched_fixtures"] == 1
    assert summary["unmatched_rows"] == 1
    assert [u["event_id"] for u in session.updates] == [15184670]

    # The ledger row calls it what it is.
    agreement = summary["agreement"]
    assert agreement["identity"]["both"] == 2
    assert agreement["identity"]["statpal_only"] == 0
    assert agreement["identity"]["ours_only"] == 0
    assert agreement["identity"]["pct"] == 100.0
    assert agreement["schedule"]["off_by_hours"] == 1
    assert agreement["anchors"]["unanchored"] == 1


# ---------------------------------------------------------------------------
# The row is there, and it is about this pass
# ---------------------------------------------------------------------------


async def test_every_pass_banks_a_row_the_bus_can_read(drive):
    summary, _session = await drive(
        [_fixture("280445", "Arizona Cardinals", "Los Angeles Chargers", KICKOFF)],
        [
            _candidate(
                14781141, "Arizona Cardinals", "Los Angeles Chargers", KICKOFF
            )
        ],
    )
    agreement = summary["agreement"]
    assert agreement["sport_key"] == task.NFL_SPORT_KEY
    assert agreement["read"] == READ_OK
    assert agreement["identity"]["governs"] is True
    assert agreement["schedule"]["governs"] is False
    assert agreement["anchors"]["governs"] is False
    assert len(agreement["window"]) == 2


async def test_a_row_this_pass_stamped_is_anchored_not_missing(drive):
    """The pass's own success must not read as an unanchored game."""
    summary, session = await drive(
        [_fixture("280445", "Arizona Cardinals", "Los Angeles Chargers", KICKOFF)],
        [
            _candidate(
                14781141, "Arizona Cardinals", "Los Angeles Chargers", KICKOFF
            )
        ],
    )
    assert summary["stamped"] == 1
    assert session.commits == 1
    anchors = summary["agreement"]["anchors"]
    assert anchors["anchored"] == 1
    assert anchors["unanchored"] == 0
    assert anchors["pct_of_both"] == 100.0


async def test_the_denominator_does_not_shrink_as_the_task_succeeds(drive):
    """Today's row has to be comparable to yesterday's, or the streak is noise.

    The stamping loop prunes each stamped row out of its candidate pool so two
    contests cannot both claim one row. Measuring over the pruned pool would
    report a denominator that falls every time the task works.
    """
    second = KICKOFF + timedelta(days=7)
    summary, _session = await drive(
        [
            _fixture("280445", "Arizona Cardinals", "Los Angeles Chargers", KICKOFF),
            _fixture("280446", "Denver Broncos", "Kansas City Chiefs", second),
        ],
        [
            _candidate(1, "Arizona Cardinals", "Los Angeles Chargers", KICKOFF),
            _candidate(2, "Denver Broncos", "Kansas City Chiefs", second),
        ],
    )
    assert summary["stamped"] == 2
    agreement = summary["agreement"]
    assert agreement["denominator"] == 2
    assert agreement["identity"]["both"] == 2
    assert agreement["anchors"]["anchored"] == 2


async def test_a_phantom_row_is_ours_only_in_the_row_and_a_miss_in_the_receipts(drive):
    """The Los Angeles phantom, reported by both instruments."""
    summary, _session = await drive(
        [_fixture("280445", "Arizona Cardinals", "Los Angeles Chargers", KICKOFF)],
        [
            _candidate(1, "Arizona Cardinals", "Los Angeles Chargers", KICKOFF),
            _candidate(2, "Arizona Cardinals", "Los Angeles Rams", KICKOFF),
        ],
    )
    assert summary["unmatched_rows"] == 1
    agreement = summary["agreement"]
    assert agreement["identity"]["ours_only"] == 1
    assert agreement["identity"]["both"] == 1
    assert agreement["denominator"] == 2
    assert agreement["receipts"]["ours_only"][0]["event_id"] == "2"


async def test_a_fabricated_column_reaches_the_row_as_its_own_bucket(drive):
    """#2963 rows are neither anchored nor a gap, in the ledger as in the task."""
    summary, session = await drive(
        [_fixture("280494", "Detroit Lions", "Cincinnati Bengals", KICKOFF)],
        [
            _candidate(
                15196977,
                "Detroit Lions",
                "Cincinnati Bengals",
                KICKOFF,
                held="statpal_live_Cincinnati Bengals_Detroit Lions",
            )
        ],
    )
    assert summary["polluted_column"] == 1
    assert session.updates == []
    anchors = summary["agreement"]["anchors"]
    assert anchors["polluted_column"] == 1
    assert anchors["anchored"] == 0
    assert anchors["unanchored"] == 0


# ---------------------------------------------------------------------------
# A read that failed is not a disagreement
# ---------------------------------------------------------------------------


async def test_a_refused_endpoint_banks_a_read_failed_row_with_no_percentage(drive):
    from app.services.statpal_api import StatPalUpstreamError

    summary, _session = await drive(
        [],
        [],
        schedule_error=StatPalUpstreamError("season-schedule HTTP 503"),
    )
    agreement = summary["agreement"]
    assert agreement["read"] == READ_FAILED
    assert "identity" not in agreement
    assert agreement["read_failures"]


async def test_a_genuinely_empty_slate_is_a_row_and_not_zero_percent(drive):
    """June. StatPal serves no NFL, nothing failed, and that is a real answer."""
    summary, _session = await drive([], [])
    agreement = summary["agreement"]
    assert agreement["read"] == READ_OK
    assert agreement["read_failures"] == []
    assert agreement["denominator"] == 0
    assert agreement["identity"]["pct"] is None


async def test_the_nfl_pass_folds_its_own_day_into_the_durable_ledger(drive, monkeypatch):
    """NFL's own chain link.

    NFL runs a different stamper module from NBA/NHL/MLB, so its call to the
    ledger is a second, independent wire. It is also the sport closest to the
    gate — the first to read `MEETS` on production — which makes it the worst
    one to discover was never recording its days.
    """
    import app.services.durable_snapshots as ds

    published = []

    async def _read(identity, **kwargs):
        return SimpleNamespace(
            status="missing", missing=True, ok=False, envelope=None, error=None
        )

    async def _publish(envelope, *, expected_generation=None):
        published.append(envelope)
        return {"status": "ok"}

    monkeypatch.setattr(ds, "read_snapshot_standalone", _read)
    monkeypatch.setattr(ds, "publish_cas_snapshot_standalone", _publish)

    # TWO games. A single-fixture population scores `TOO-FEW-TO-SCORE` — 100% of
    # one game is arithmetic, not agreement — and this test is about whether the
    # pass FOLDS its day into the ledger, not about whether the day clears.
    summary, _session = await drive(
        [
            _fixture("280445", "Arizona Cardinals", "Los Angeles Chargers", KICKOFF),
            _fixture("280446", "Chicago Bears", "Green Bay Packers", KICKOFF),
        ],
        [
            _candidate(1, "Arizona Cardinals", "Los Angeles Chargers", KICKOFF),
            _candidate(2, "Chicago Bears", "Green Bay Packers", KICKOFF),
        ],
    )

    streak = summary["agreement"]["streak"]
    assert streak["days"] == 1
    assert streak["recorded"] is True
    assert published[0].identity == (
        "authority-agreement-ledger:americanfootball_nfl"
    )
    assert published[0].payload["days"][0]["day"] == "2026-09-04"
