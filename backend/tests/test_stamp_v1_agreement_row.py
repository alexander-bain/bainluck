"""One NBA/NHL pass end to end: what it writes, and what it publishes. #2867 / D50 step 3.

`stamp_v1_statpal_fixtures` returns an `agreement` block alongside its stamping
receipts, and the two answer different questions on purpose:

  * the STAMPER asks *may I write an identity claim on this?* and requires both
    team names and a start within ±1h, because an eighteen-hour gap is not proof;
  * the AGREEMENT ROW asks *do both sides have this game?* and joins on the team
    pair alone, because a join keyed on the clock cannot report a clock
    disagreement — it drops the row instead (ledger spec rule 4).

For these two sports a third thing has to be true as well, and it is the reason
this file exists rather than being folded into the NFL's. **StatPal publishes a
whole season on day one and we ingest a rolling odds-driven slice** — 1206 NBA
games against our 41, 1404 NHL against our 32, measured 2026-09-04. Under one
undivided `statpal_only` count that reads as a 3% identity disagreement, when
what is being measured is how far ahead our ingestion reaches. So the row splits
the miss by where it falls against our own inventory, publishes
`ours_covered_pct` beside `pct`, and blends neither into the other.

## what each test can fail on

* the agreement row disappearing from a summary the bus reads daily;
* the horizon split being subtracted from `identity.pct` instead of reported
  beside it, which is how a bar quietly becomes reachable;
* a row whose column is already correct being skipped instead of anchored — the
  state 691 production rows are in today, with zero anchors between them;
* a column write surviving an anchor refusal, which would leave a row that says
  linked and resolves nothing;
* a failed read publishing a percentage;
* the agreement row's denominator being drawn from the stamper's write window,
  which silently subtracts every game of ours past the edge of a rolling
  schedule from the number that governs a flip (CERT-962).
"""

from __future__ import annotations

from contextlib import asynccontextmanager
from datetime import datetime, timedelta, timezone
from importlib import import_module
from types import SimpleNamespace

import pytest

from app.services.anchor_channel import CONFIRMED, STALE_INCUMBENT, WROTE
from app.services.statpal_api import StatPalFixture, StatPalUpstreamError
from app.utils.authority_agreement import READ_FAILED, READ_OK

#: `app/tasks/__init__.py` registers task attributes that shadow submodules of
#: the same name, so a dotted import can hand back the task object instead of
#: the module. `import_module` reads `sys.modules` and is unambiguous.
task = import_module("app.tasks.stamp_v1_statpal_fixtures")

NOW = datetime(2026, 9, 4, 12, 17, tzinfo=timezone.utc)
TIPOFF = datetime(2026, 10, 20, 19, 0, tzinfo=timezone.utc)


def _fixture(fixture_id, away, home, start, stats_id=None, status="Not Started"):
    return StatPalFixture(
        fixture_id=fixture_id,
        home_team=home,
        away_team=away,
        start_time=start,
        status=status,
        league="NBA",
        season="2026/2027",
        stats_id=stats_id,
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

    An unrecognised statement raises. A fake that answers "no rows" to a query it
    does not know turns a real change in the task into a green test — gotcha #53
    in test form.
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
    """Run one pass over the given fixtures and rows. Returns `(summary, session, anchors)`."""

    async def _drive(
        fixtures,
        candidates,
        *,
        spec=None,
        outcome=WROTE,
        schedule_error=None,
        update_rowcount=1,
    ):
        spec = spec or task.NBA
        session = RecordingSession(candidates, update_rowcount=update_rowcount)
        anchors: list[dict] = []

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

        async def _record_anchor(_session_arg, *, event_id, key, claim_context=None):
            anchors.append(
                {"event_id": event_id, "key": key, "claim_context": claim_context}
            )
            return SimpleNamespace(outcome=outcome)

        monkeypatch.setattr(task, "record_anchor", _record_anchor)

        summary = await task._run_stamp_v1_statpal_fixtures(spec, now=NOW)
        return summary, session, anchors

    return _drive


# ---------------------------------------------------------------------------
# The horizon split. This is the file's reason to exist.
# ---------------------------------------------------------------------------


async def test_a_season_we_have_not_ingested_yet_is_not_an_identity_disagreement(drive):
    """Production's shape in miniature: we hold one game, StatPal holds four.

    `identity.pct` is 1-in-5 and stays 1-in-5 — nothing is subtracted from it.
    What the row adds is WHERE the three StatPal-only games fall: one before our
    first, one inside the span we cover (the only one that is an ingestion
    finding), one past our last. And `ours_covered_pct` answers the different
    question — of the games we hold, how many does StatPal have.
    """
    ours_at = TIPOFF
    fixtures = [
        _fixture("1050110", "Boston Celtics", "Detroit Pistons", ours_at),
        _fixture(
            "1043639", "Miami Heat", "Toronto Raptors", ours_at - timedelta(days=17)
        ),
        _fixture(
            "1050112", "Philadelphia 76ers", "New York Knicks", ours_at + timedelta(hours=4)
        ),
        _fixture(
            "1051930",
            "Oklahoma City Thunder",
            "Portland Trail Blazers",
            ours_at + timedelta(days=22),
        ),
    ]
    rows = [
        _candidate(1, "Boston Celtics", "Detroit Pistons", ours_at),
        # A second row of ours, so "our span" is a span and not a point.
        _candidate(
            2, "Milwaukee Bucks", "Washington Wizards", ours_at + timedelta(hours=8)
        ),
    ]
    summary, _session, _anchors = await drive(fixtures, rows)

    identity = summary["agreement"]["identity"]
    assert identity["both"] == 1
    assert identity["statpal_only"] == 3
    assert identity["ours_only"] == 1
    assert identity["pct"] == 20.0
    assert identity["governs"] is True
    assert identity["statpal_only_by_horizon"] == {
        "before_our_first": 1,
        "inside_our_span": 1,
        "beyond_our_last": 1,
        "unplaceable": 0,
    }
    # Of the two games we hold, StatPal has one — the different question.
    assert identity["ours_covered_pct"] == 50.0
    # D63 = A (Alex, 2026-09-04) reversed which of the two decides for this
    # sport, and this assertion is the reversal. NBA is scored on
    # `ours_covered_pct` ALONE: `identity.pct` is 20.0 here and 3.40 in
    # production, not because either side disagrees about a game but because
    # StatPal publishes a season on day one and we ingest a rolling odds-driven
    # slice. Scoring NBA on it would put the flip permanently out of reach for a
    # reason that is not a disagreement — the unreachable-by-design failure that
    # spec rule 5 exists to prevent.
    #
    # So the union number is still PUBLISHED (the gap between the two is the
    # finding) and it does not appear in `numbers`, which is what "published,
    # not governing" has to mean if it means anything.
    governing = identity["governing"]
    assert governing["numbers"] == ["ours_covered_pct"]
    assert governing["values"] == {"ours_covered_pct": 50.0}
    # 50.0 is below the bar, so this day resets the streak — and it is BELOW
    # rather than the catastrophic-looking 20.0 that a `pct`-scored NBA would
    # have reported.
    assert governing["gate"] == "BELOW"


async def test_the_split_is_reported_beside_the_percentage_and_never_inside_it(drive):
    """A horizon bucket that moved `pct` would be an exclusion nobody declared,
    which is the failure mode ledger spec rule 5 exists to prevent."""
    fixtures = [
        _fixture("1050110", "Boston Celtics", "Detroit Pistons", TIPOFF),
        _fixture(
            "1051930",
            "Oklahoma City Thunder",
            "Portland Trail Blazers",
            TIPOFF + timedelta(days=22),
        ),
    ]
    rows = [_candidate(1, "Boston Celtics", "Detroit Pistons", TIPOFF)]
    summary, _s, _a = await drive(fixtures, rows)

    identity = summary["agreement"]["identity"]
    assert identity["statpal_only_by_horizon"]["beyond_our_last"] == 1
    # 1 of 2, exactly as if the split did not exist.
    assert identity["pct"] == 50.0
    assert identity["ours_covered_pct"] == 100.0


# ---------------------------------------------------------------------------
# What one pass writes
# ---------------------------------------------------------------------------


async def test_a_clean_stamp_writes_the_column_and_the_anchor_and_commits(drive):
    fixtures = [_fixture("1050110", "Boston Celtics", "Detroit Pistons", TIPOFF)]
    rows = [_candidate(1, "Boston Celtics", "Detroit Pistons", TIPOFF)]
    summary, session, anchors = await drive(fixtures, rows)

    assert summary["stamped"] == 1
    assert session.updates == [{"event_id": 1, "fixture_id": "1050110"}]
    assert session.commits == 1
    assert session.rollbacks == 0
    (anchor,) = anchors
    assert anchor["event_id"] == 1
    assert anchor["key"].source_id == "basketball_nba:1050110"
    # A row this pass just stamped must not be published as unanchored: the
    # agreement row reads the column AFTER the write, not the value it had when
    # the candidate query ran.
    assert summary["agreement"]["anchors"] == {
        "anchored": 1,
        "unanchored": 0,
        "mismatch": 0,
        "polluted_column": 0,
        "pct_of_both": 100.0,
        "governs": False,
        "note": (
            "the id join the shadow stamper wrote, over the games both sides "
            "have. Not the agreement number."
        ),
    }


async def test_a_column_that_is_already_right_gets_the_anchor_and_no_column_write(drive):
    """The 691-rows-zero-anchors case, which is the majority state for these two
    sports. Nothing is written to the column — it is already correct — and the
    anchor that was missing is written."""
    fixtures = [_fixture("1050110", "Boston Celtics", "Detroit Pistons", TIPOFF)]
    rows = [_candidate(1, "Boston Celtics", "Detroit Pistons", TIPOFF, held="1050110")]
    summary, session, anchors = await drive(fixtures, rows)

    assert summary["anchored_only"] == 1
    assert summary["stamped"] == 0
    assert session.updates == []          # the column was never touched
    assert session.commits == 1
    assert len(anchors) == 1
    assert anchors[0]["claim_context"]["column_was_already_set"] is True


async def test_an_anchor_that_already_names_the_event_is_not_counted_as_new_work(drive):
    """CONFIRMED means the pair was already complete. Counting it as an anchor
    written would make "the backfill is done" unreadable."""
    fixtures = [_fixture("1050110", "Boston Celtics", "Detroit Pistons", TIPOFF)]
    rows = [_candidate(1, "Boston Celtics", "Detroit Pistons", TIPOFF, held="1050110")]
    summary, _session, _anchors = await drive(fixtures, rows, outcome=CONFIRMED)

    assert summary["anchored_only"] == 0
    assert summary["already_linked"] == 1


async def test_an_anchor_refusal_takes_the_column_write_with_it(drive):
    """Both shapes or neither. A committed column with no anchor reads as STALE
    on every lookup — it resolves nothing while looking like a link."""
    fixtures = [_fixture("1050110", "Boston Celtics", "Detroit Pistons", TIPOFF)]
    rows = [_candidate(1, "Boston Celtics", "Detroit Pistons", TIPOFF)]
    summary, session, _anchors = await drive(
        fixtures, rows, outcome=STALE_INCUMBENT
    )

    assert summary["stamped"] == 0
    assert session.commits == 0
    assert session.rollbacks == 1
    (refusal,) = summary["write_refusal_receipts"]
    assert refusal["outcome"] == STALE_INCUMBENT
    assert refusal["event_id"] == 1


async def test_a_column_holding_another_contest_is_receipted_and_left_alone(drive):
    """CONTRADICTION requires evidence that the column names a DIFFERENT GAME.

    So the pass has to have read that other game. `1050112` is in this read, our
    row holds it, and a different contest matched the row — which is the two
    matching rules disagreeing, and neither is overruled here.
    """
    fixtures = [
        _fixture("1050110", "Boston Celtics", "Detroit Pistons", TIPOFF),
        _fixture("1050112", "Miami Heat", "Toronto Raptors", TIPOFF),
    ]
    rows = [_candidate(1, "Boston Celtics", "Detroit Pistons", TIPOFF, held="1050112")]
    summary, session, anchors = await drive(fixtures, rows)

    assert summary["contradictions"] == 1
    assert summary["foreign_id_space"] == 0
    assert session.updates == []
    assert anchors == []
    (receipt,) = summary["contradiction_receipts"]
    assert receipt["column_holds"] == "1050112"
    assert receipt["statpal_id"] == "1050110"


async def test_a_column_the_endpoint_cannot_resolve_is_not_called_a_contradiction(drive):
    """The MLB case, in miniature and in the NBA's own vocabulary.

    `999999` is a well-formed digit id and this endpoint has never published it.
    Calling that a contradiction claims the ingestion path picked a different
    GAME; measured on production MLB, what it actually did was pick the right
    game and write its id from the other ENDPOINT — 92 of 222 distinct column
    values resolve to nothing `season-schedule` serves.

    The two are different bugs with different owners, so they get different
    buckets. Neither is written, and neither is overwritten.
    """
    fixtures = [_fixture("1050110", "Boston Celtics", "Detroit Pistons", TIPOFF)]
    rows = [_candidate(1, "Boston Celtics", "Detroit Pistons", TIPOFF, held="999999")]
    summary, session, anchors = await drive(fixtures, rows)

    assert summary["foreign_id_space"] == 1
    assert summary["contradictions"] == 0
    assert session.updates == []
    assert anchors == []
    (receipt,) = summary["foreign_id_space_receipts"]
    assert receipt["column_holds"] == "999999"
    assert receipt["statpal_id"] == "1050110"
    # The repair is knowable — that is what makes it a namespace bug rather than
    # a mystery — and it is still not applied here.
    assert receipt["anchor_should_be"] == "1050110"


async def test_the_nhl_second_id_rides_in_the_claim_context_and_never_in_the_key(drive):
    """`stats_id` is real for the NHL and is NOT unique per contest — three
    values are each shared by two different games — so anchoring on it would
    merge two real fixtures. Carried where it stays visible; keyed on `id`."""
    puck_drop = datetime(2026, 9, 19, 23, 0, tzinfo=timezone.utc)
    fixtures = [
        _fixture(
            "649053",
            "Montreal Canadiens",
            "Toronto Maple Leafs",
            puck_drop,
            stats_id="68933",
        )
    ]
    rows = [_candidate(1, "Montréal Canadiens", "Toronto Maple Leafs", puck_drop)]
    summary, _session, anchors = await drive(fixtures, rows, spec=task.NHL)

    assert summary["stamped"] == 1
    (anchor,) = anchors
    assert anchor["key"].source_id == "icehockey_nhl:649053"
    assert anchor["claim_context"]["statpal_stats_id"] == "68933"
    assert summary["stats_id"] == {
        "present": 1,
        "absent": 0,
        "expected": "on every fixture",
        "measured_when_set": "1404/1404 season-schedule games, 2026-09-04",
        "as_expected": True,
    }


async def test_our_row_and_their_contest_both_get_a_receipt_when_the_clock_disagrees(
    drive,
):
    """The five 04:00Z rows, in miniature: the stamper refuses to write and the
    agreement row still calls it one game, off by hours.

    TWO games, not one, and the second is not decoration. The disagreeing row is
    20 hours from its contest, so it is only a stamping candidate at all if the
    write window is wider than 20 hours — which in production it always is (1404
    NHL fixtures spanning September to April) and in a one-fixture miniature it
    never is. A single-fixture version of this test passes the row to the
    agreement row and never to the stamper, and would therefore go green on a
    stamper that had stopped receipting entirely.
    """
    puck_drop = datetime(2026, 10, 2, 0, 0, tzinfo=timezone.utc)
    ours_at = datetime(2026, 10, 1, 4, 0, tzinfo=timezone.utc)  # midnight Eastern
    opener = datetime(2026, 9, 30, 23, 0, tzinfo=timezone.utc)
    fixtures = [
        _fixture("652870", "Boston Bruins", "Buffalo Sabres", opener, stats_id="68970"),
        _fixture(
            "652878", "Minnesota Wild", "Nashville Predators", puck_drop, stats_id="68976"
        ),
    ]
    rows = [
        _candidate(15168040, "Boston Bruins", "Buffalo Sabres", opener),
        _candidate(15168041, "Minnesota Wild", "Nashville Predators", ours_at),
    ]
    summary, session, anchors = await drive(fixtures, rows, spec=task.NHL)

    # The opener stamps; the 04:00Z row does not, and says so from both ends.
    assert summary["stamped"] == 1
    assert [u["event_id"] for u in session.updates] == [15168040]
    assert [a["event_id"] for a in anchors] == [15168040]
    assert summary["unmatched_fixture_receipts"][0]["statpal_id"] == "652878"
    assert summary["unmatched_row_receipts"][0]["event_id"] == 15168041

    # The agreement row calls it one game with a clock disagreement, which is the
    # whole of spec rule 4.
    agreement = summary["agreement"]
    assert agreement["identity"]["both"] == 2
    assert agreement["identity"]["pct"] == 100.0
    assert agreement["schedule"]["within"] == 1
    assert agreement["schedule"]["off_by_hours"] == 1
    assert agreement["schedule"]["governs"] is False


# ---------------------------------------------------------------------------
# Zero yield is a row, not a skip
# ---------------------------------------------------------------------------


async def test_a_failed_read_publishes_no_percentage_at_all(drive):
    summary, session, _anchors = await drive(
        [], [], schedule_error=StatPalUpstreamError("nba/season-schedule: HTTP 500")
    )

    agreement = summary["agreement"]
    assert agreement["read"] == READ_FAILED
    assert "identity" not in agreement
    assert agreement["read_failures"]
    # A READ-FAILED row pauses the seven-day streak; a 0% row would reset it.
    assert "pauses the streak" in agreement["note"]


async def test_an_empty_season_is_a_read_ok_row_and_not_a_failure(drive):
    """Distinguishable from the test above, which is the whole of gotcha #53."""
    summary, _session, _anchors = await drive([], [])

    agreement = summary["agreement"]
    assert agreement["read"] == READ_OK
    assert agreement["read_failures"] == []
    assert agreement["identity"]["both"] == 0
    assert summary["sport_key"] == "basketball_nba"


async def test_the_summary_the_endpoint_publishes_names_its_own_sport(drive):
    """`SHADOW_STAMPERS` maps three sports to three task names now, and the
    endpoint reads each task's banked summary. A summary that did not say which
    sport it measured could be published under the wrong one."""
    fixtures = [_fixture("1050110", "Boston Celtics", "Detroit Pistons", TIPOFF)]
    rows = [_candidate(1, "Boston Celtics", "Detroit Pistons", TIPOFF)]

    nba, _s, _a = await drive(fixtures, rows)
    assert nba["sport_key"] == "basketball_nba"
    assert nba["agreement"]["sport_key"] == "basketball_nba"

    nhl, _s, _a = await drive(fixtures, rows, spec=task.NHL)
    assert nhl["sport_key"] == "icehockey_nhl"
    assert nhl["agreement"]["sport_key"] == "icehockey_nhl"


# ---------------------------------------------------------------------------
# The seven-day count rides on the row the endpoint publishes (authority/021)
# ---------------------------------------------------------------------------


async def test_the_pass_folds_its_own_day_into_the_durable_ledger(drive, monkeypatch):
    """The chain, not the two ends.

    `authority_streak` is proved pure in `test_authority_streak.py` and the
    durable substrate is proved in Queue 298's own guards — and both being green
    says nothing about whether a real pass ever calls either. The seven-day count
    D50 gates on only exists if THIS function attaches it to THIS row, because
    the endpoint publishes the banked `agreement` block verbatim.
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

    fixtures = [_fixture("1050110", "Boston Celtics", "Detroit Pistons", TIPOFF)]
    rows = [_candidate(1, "Boston Celtics", "Detroit Pistons", TIPOFF)]
    summary, _s, _a = await drive(fixtures, rows)

    streak = summary["agreement"]["streak"]
    assert streak["days"] == 1
    assert streak["recorded"] is True
    assert streak["meets_flip_gate"] is False
    assert len(published) == 1
    assert published[0].identity == "authority-agreement-ledger:basketball_nba"
    assert published[0].payload["days"][0]["state"] == "MEETS"


async def test_a_ledger_that_cannot_be_written_never_reads_as_a_streak_of_zero(drive):
    """No durable substrate is stubbed here, so the read fails.

    The pass must still succeed — a stamper that read both StatPal endpoints and
    wrote its anchors has done its job — and the row must say the day was not
    recorded rather than publishing a count that looks like a measurement.
    """
    fixtures = [_fixture("1050110", "Boston Celtics", "Detroit Pistons", TIPOFF)]
    rows = [_candidate(1, "Boston Celtics", "Detroit Pistons", TIPOFF)]
    summary, _s, _a = await drive(fixtures, rows)

    streak = summary["agreement"]["streak"]
    assert streak["state"] == "UNRECORDED"
    assert "days" not in streak
    assert summary["agreement"]["identity"]["governing"]["gate"] == "MEETS"


# ---------------------------------------------------------------------------
# The measurement population. CERT-962: the write window is not the denominator.
# ---------------------------------------------------------------------------


async def test_an_october_row_beyond_a_rolling_schedule_stays_in_the_denominator(drive):
    """MLB's real shape, in miniature, and the defect CERT-962 named.

    StatPal's MLB `season-schedule` is a rolling ~17-day window, not a season —
    measured 2026-08-31T21:05Z to 2026-09-17T00:40Z on production. Our own
    inventory runs past the end of it. The question the governing number asks is
    "of the games WE list, does StatPal have them?", and the pass used to read
    our rows with `commence_time BETWEEN` StatPal's own first and last fixture
    ±1h before asking it — so a game of ours in October was removed by SQL and
    could be neither counted as missing nor placed by the horizon split. The
    denominator was horizon-subtracted at selection while the row published
    `ours_covered_pct` as though it were not.

    Three things this pins, and the first is the one that was wrong:

      * the October row is IN the denominator: 1 of 2, not 1 of 1;
      * it is placed in `beyond_statpal_last`, so a reader can tell "past the
        edge of what StatPal publishes" from a real disagreement;
      * the STAMPER never saw it. Its write window is unchanged and narrow, which
        is correct — there is no fixture out there to match it against, and a
        wider write window is how a stamper writes an identity claim on a guess.
    """
    #: StatPal's rolling window, anchored so it ends well before our October row.
    first = datetime(2026, 8, 31, 21, 5, tzinfo=timezone.utc)
    last = first + timedelta(days=17)
    october = datetime(2026, 10, 7, 0, 5, tzinfo=timezone.utc)
    assert october > last, "the row must be past StatPal's last fixture to be the case"

    fixtures = [
        _fixture("2001", "Boston Red Sox", "New York Yankees", first),
        _fixture("2002", "Chicago Cubs", "St. Louis Cardinals", last),
    ]
    rows = [
        _candidate(9001, "Boston Red Sox", "New York Yankees", first),
        # Our postseason row. StatPal's rolling schedule cannot reach it.
        _candidate(9002, "Los Angeles Dodgers", "San Diego Padres", october),
    ]
    summary, session, _anchors = await drive(fixtures, rows, spec=task.MLB)

    identity = summary["agreement"]["identity"]
    # 1 of 2. Before this repair it read 1 of 1 == 100%, and the missing game was
    # not "excluded" anywhere on the row — it was never selected.
    assert identity["ours_only"] == 1
    assert identity["ours_covered_pct"] == 50.0
    assert identity["ours_only_by_horizon"] == {
        "before_statpal_first": 0,
        "inside_statpal_span": 0,
        "beyond_statpal_last": 1,
        "unplaceable": 0,
    }

    # The write window is unchanged: StatPal's span ±1h, and the October row is
    # outside it. The measurement window is wider and holds both.
    write_window, measurement_window = session.candidate_windows
    assert write_window == (first - task.CANDIDATE_SLACK, last + task.CANDIDATE_SLACK)
    assert measurement_window[0] <= first and measurement_window[1] >= october
    assert summary["rows_in_window"] == 1
    assert summary["rows_measured"] == 2

    # And the stamper wrote only the game it had a fixture for.
    assert [u["event_id"] for u in session.updates] == [9001]


async def test_the_two_populations_are_read_as_two_queries_with_different_bounds(drive):
    """The call-site guard. The repair is a separate read, not a wider one.

    A single widened query would also put the October row in the denominator —
    and would hand the stamper candidates it has no fixture to match, which is
    how `MATCH_WINDOW` stops being the thing that decides a write. This asserts
    the shape: two reads, the write one strictly inside the measurement one.
    """
    first = datetime(2026, 8, 31, 21, 5, tzinfo=timezone.utc)
    fixtures = [_fixture("2001", "Boston Red Sox", "New York Yankees", first)]
    rows = [_candidate(9001, "Boston Red Sox", "New York Yankees", first)]
    _summary, session, _anchors = await drive(fixtures, rows, spec=task.MLB)

    assert len(session.candidate_windows) == 2
    (write_start, write_end), (measure_start, measure_end) = session.candidate_windows
    assert measure_start <= write_start
    assert measure_end >= write_end
    assert (measure_start, measure_end) != (write_start, write_end)


async def test_a_sport_whose_inventory_sits_inside_statpals_span_is_unmoved(drive):
    """The blast radius, pinned. NBA/NHL/NFL numbers must not move.

    `measurement_bounds` unions rather than replaces, so a sport whose local rows
    already sit inside StatPal's span reads exactly the population it read before
    this existed. Measured on production 2026-09-05: NFL 322 rows in both, NBA
    41, NHL 32 — only MLB moved, 222 to 729. Three seven-day clocks were already
    running when this landed, and a repair that redefined their denominators
    underneath them would have reset all three without saying so.
    """
    fixtures = [
        _fixture("1050110", "Boston Celtics", "Detroit Pistons", TIPOFF),
        _fixture("1050112", "Miami Heat", "Toronto Raptors", TIPOFF + timedelta(days=3)),
    ]
    rows = [
        _candidate(1, "Boston Celtics", "Detroit Pistons", TIPOFF),
        _candidate(2, "Miami Heat", "Toronto Raptors", TIPOFF + timedelta(days=3)),
    ]
    summary, _session, _anchors = await drive(fixtures, rows)

    assert summary["rows_in_window"] == summary["rows_measured"] == 2
    assert summary["agreement"]["identity"]["ours_covered_pct"] == 100.0
    assert summary["agreement"]["identity"]["ours_only"] == 0
