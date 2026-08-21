"""#1798 / ruling 048 — the drain the acceptance assumed, and its honest zero.

The property under test is NOT "the drain drains". Measured against production on
2026-08-17 it drains nothing, because 499 of the 500 unanchored rows were created by
Polymarket and ``events`` has no Polymarket id column — the id the bounding clause
waits for has nowhere to land.

So the property under test is that the zero **says so**. A drain reporting success
over a population it structurally cannot touch is #683's ten green weeks again:
500 scanned, 0 reconciled, recorded as SUCCESS, while the thing it was built to
bound grows. The dispositions exist to make those two zeros different objects.
"""

import pytest

from app.tasks.reconcile_unanchored_events import (
    DISPOSITION_ANCHORED_NO_DUPLICATE,
    DISPOSITION_ANCHORED_TWIN_UNSEEN,
    DISPOSITION_AWAITING,
    DISPOSITION_DRAINABLE,
    DISPOSITION_NO_CHANNEL,
    UNANCHORED_TAG,
    classify_row,
    reconcile,
    summarize_for_operator,
)
from app.utils.event_merge_invariant import PROVIDER_ID_COLUMNS


class _Row:
    def __init__(self, **kw):
        defaults = {
            "id": 1, "sport_id": 53232, "commence_time": None, "status": "closed",
            "home_team_name": "Home FC", "away_team_name": "Away FC",
            "event_tags": [UNANCHORED_TAG], "external_id": None, "espn_id": None,
            "statpal_fixture_id": None, "twin_count": 0,
        }
        defaults.update(kw)
        for k, v in defaults.items():
            setattr(self, k, v)

    def get(self, key):
        return getattr(self, key, None)


# ── the dispositions ───────────────────────────────────────────────────────


class TestTheZeroIsNotOneZero:
    def test_a_polymarket_row_is_no_channel_not_awaiting(self):
        """The finding, as an assertion.

        ``AWAITING_ANCHOR`` means "an id may yet arrive" and licenses waiting.
        For a Polymarket-created row it never can: there is no column. Reporting
        it as awaiting is the census telling an operator to be patient about
        something that will not happen.
        """
        row = _Row(event_tags=[UNANCHORED_TAG, "provenance:source:polymarket"])
        assert classify_row(row) == DISPOSITION_NO_CHANNEL

    def test_a_kalshi_row_is_also_no_channel(self):
        row = _Row(event_tags=[UNANCHORED_TAG, "provenance:source:kalshi"])
        assert classify_row(row) == DISPOSITION_NO_CHANNEL

    def test_an_odds_api_row_with_no_id_yet_is_awaiting(self):
        """Odds API HAS a column, so waiting is a real state for this row."""
        row = _Row(event_tags=[UNANCHORED_TAG, "provenance:source:odds_api"])
        assert classify_row(row) == DISPOSITION_AWAITING

    def test_a_row_with_no_source_tag_is_awaiting_not_no_channel(self):
        """Fail toward the reading that keeps the row in view.

        An untagged row is one we cannot classify. Calling it NO_ANCHOR_CHANNEL
        would quietly retire it from the population that gets looked at, which is
        the more expensive mistake.
        """
        assert classify_row(_Row(event_tags=[UNANCHORED_TAG])) == DISPOSITION_AWAITING

    def test_a_row_touched_by_both_a_channel_and_a_channel_less_source_awaits(self):
        row = _Row(event_tags=[
            UNANCHORED_TAG, "provenance:source:polymarket", "provenance:source:espn",
        ])
        assert classify_row(row) == DISPOSITION_AWAITING

    def test_an_arrived_id_with_no_duplicate_at_all_is_the_only_success(self):
        """Reconciliation succeeding and a duplicate existing are separate facts."""
        row = _Row(espn_id="401816407", twin_count=0, shadow_twin_count=0)
        assert classify_row(row) == DISPOSITION_ANCHORED_NO_DUPLICATE

    def test_a_duplicate_the_id_key_CANNOT_SEE_is_not_a_success(self):
        """Queue 387's split, and the whole reason for it.

        ``twin_count`` is strictly id-keyed. A row whose duplicate shares no
        provider id therefore reports ``twin_count = 0`` — and under the old
        single bucket that rendered identically to "there is no duplicate".
        It is the opposite: it is ruling 048's accepted cost, outstanding, in
        the one shape this rail is constitutionally unable to drain.
        """
        row = _Row(espn_id="401816407", twin_count=0, shadow_twin_count=1)
        assert classify_row(row) == DISPOSITION_ANCHORED_TWIN_UNSEEN
        assert classify_row(row) != DISPOSITION_ANCHORED_NO_DUPLICATE

    def test_a_visible_twin_still_wins_over_an_invisible_one(self):
        """An id-keyed twin is DRAINABLE regardless of the shadow count — the
        meter must never divert a row away from the arm that can actually act."""
        row = _Row(espn_id="401816407", twin_count=1, shadow_twin_count=3)
        assert classify_row(row) == DISPOSITION_DRAINABLE

    def test_the_shadow_count_never_reaches_the_drain(self):
        """The meter is a meter. Ruling 048 deleted name-and-time absorption;
        counting it is safe only while nothing consumes the count to write."""
        import inspect

        import app.tasks.reconcile_unanchored_events as mod

        src = inspect.getsource(mod.reconcile)
        # `drainable` — the list the apply path iterates — is built from the
        # id-keyed disposition alone. If shadow_twin_count ever appears in this
        # function, someone has wired the meter into the rail.
        assert "shadow_twin_count" not in src, (
            "the shadow (name-and-time) count has reached reconcile() — that is "
            "ruling 048's deleted absorption path being rebuilt via the meter"
        )

    def test_an_arrived_id_that_another_row_shares_is_drainable(self):
        row = _Row(espn_id="401816407", twin_count=1)
        assert classify_row(row) == DISPOSITION_DRAINABLE

    def test_every_provider_column_can_anchor(self):
        """A column added to the invariant must not leave this classifier behind."""
        for col in PROVIDER_ID_COLUMNS:
            assert classify_row(_Row(**{col: "an-id"})) != DISPOSITION_NO_CHANNEL
            assert classify_row(_Row(**{col: "an-id"})) != DISPOSITION_AWAITING


# ── the verdict ────────────────────────────────────────────────────────────


class _Savepoint:
    """#2048: the drain contains each row's DB work in a savepoint.

    Modelled here because a fake without it makes the drain look broken; the
    containment itself is asserted in ``test_reconcile_unanchored_bind_2048.py``.
    """

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        return False


class _Session:
    """Answers the census, then the twin lookup. Records every write."""

    def __init__(self, census_rows, twin_rows=None, raise_on_census=False):
        self._census = census_rows
        self._twins = twin_rows or []
        self._raise = raise_on_census
        self.calls = 0
        self.writes: list = []
        self.committed = False

    def begin_nested(self):
        return _Savepoint()

    async def execute(self, stmt, params=None):
        self.calls += 1
        sql = str(stmt)
        if "DELETE FROM events" in sql or "UPDATE " in sql:
            self.writes.append((sql.strip().split("\n")[0], params))
            return _Result([])
        if self.calls == 1:
            if self._raise:
                raise RuntimeError("relation \"events\" does not exist")
            return _Result(self._census)
        return _Result(self._twins)

    async def commit(self):
        self.committed = True


class _Result:
    def __init__(self, rows):
        self._rows = rows

    def mappings(self):
        return self

    def all(self):
        return self._rows


class TestTheVerdict:
    @pytest.mark.asyncio
    async def test_the_production_shape_reports_no_work_and_names_the_reason(self):
        """500 rows, all Polymarket. Not `complete`, and the reason is the finding."""
        rows = [
            _Row(id=i, event_tags=[UNANCHORED_TAG, "provenance:source:polymarket"])
            for i in range(1, 51)
        ]
        out = await reconcile(_Session(rows), apply=False)

        assert out["measured"] is True
        assert out["terminal"] == "no_work"
        assert out["reconciled"] == 0
        assert out["unbounded"] == 50
        assert out["census"][DISPOSITION_NO_CHANNEL] == 50
        assert "no anchoring channel" in out["reason"]

    @pytest.mark.asyncio
    async def test_a_no_work_verdict_cannot_read_green(self):
        """The enrolment must not be decorative.

        ``ENFORCED_TASKS`` membership does nothing without a terminal the
        classifier recognises. This asserts the wiring end to end: the summary
        this task actually returns is graded NOT-GREEN by the shipping verdict
        module under the task's real registered name.
        """
        from app.utils.task_verdict import ENFORCED_TASKS, verdict_for

        assert "reconcile_unanchored_events" in ENFORCED_TASKS

        rows = [_Row(id=1, event_tags=[UNANCHORED_TAG, "provenance:source:polymarket"])]
        out = await reconcile(_Session(rows), apply=False)

        verdict = verdict_for("reconcile_unanchored_events", out)
        assert verdict.is_green is False
        assert verdict.authoritative is True

    @pytest.mark.asyncio
    async def test_a_census_that_could_not_run_is_not_a_census_that_found_nothing(self):
        """gotcha #53, on the rail whose whole job is measuring a declared cost."""
        out = await reconcile(_Session([], raise_on_census=True), apply=False)

        assert out["measured"] is False
        assert out["terminal"] == "failed"
        assert "census_failed" in out["reason"]
        assert "reconciled" not in out  # no number at all, rather than a zero
        assert summarize_for_operator(out).startswith("UNMEASURED")

    @pytest.mark.asyncio
    async def test_a_drainable_pair_is_reported_but_not_written_on_a_dry_run(self):
        rows = [_Row(id=11, espn_id="401816407", twin_count=1)]
        twins = [{
            "id": 22, "espn_id": "401816407", "external_id": None,
            "statpal_fixture_id": None, "home_team_name": "Home FC",
            "away_team_name": "Away FC", "commence_time": None,
        }]
        session = _Session(rows, twins)

        out = await reconcile(session, apply=False)

        assert out["reconciled"] == 1
        assert out["drained"][0]["applied"] is False
        assert out["drained"][0]["shared_on"] == ["espn_id"]
        assert session.writes == []

    @pytest.mark.asyncio
    async def test_a_twin_sharing_no_id_is_refused_by_the_invariant(self):
        """Belt and braces on a DELETE path.

        The census SQL is already id-keyed, so this pair should be unreachable.
        The point is that if it ever IS reached — a hand-edited query, a column
        added in one place — the refusal happens before the delete, not after.
        """
        rows = [_Row(id=11, espn_id="401816407", twin_count=1)]
        twins = [{
            "id": 22, "espn_id": None, "external_id": None,
            "statpal_fixture_id": None, "home_team_name": "Home FC",
            "away_team_name": "Away FC", "commence_time": None,
        }]
        session = _Session(rows, twins)

        out = await reconcile(session, apply=True)

        assert out["reconciled"] == 0
        assert len(out["refused"]) == 1
        assert "ruling 048" in out["refused"][0]["reason"].lower()
        assert session.writes == []

    @pytest.mark.asyncio
    async def test_the_scan_declares_its_own_truncation(self):
        """A bounded scan that does not say it was bounded is a wrong census."""
        rows = [
            _Row(id=i, event_tags=[UNANCHORED_TAG, "provenance:source:polymarket"])
            for i in range(1, 4)
        ]
        out = await reconcile(_Session(rows), apply=False, limit=3)
        assert out["truncated"] is True

        out = await reconcile(_Session(rows), apply=False, limit=100)
        assert out["truncated"] is False


class TestTheTagAgreesWithTheRegistry:
    def test_the_tag_string_is_the_one_the_create_path_writes(self):
        """Two copies of a string is two copies to keep honest.

        The drain looks for a tag the registry writes. If they ever disagree the
        drain silently scans an empty population and reports a contented zero —
        which is precisely the failure mode this whole task exists to prevent.
        """
        from app.services.event_registry import _TAG_UNANCHORED

        assert UNANCHORED_TAG == _TAG_UNANCHORED
