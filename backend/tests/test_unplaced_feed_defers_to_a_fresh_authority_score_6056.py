"""#6056, 2026-10-21: a feed that cannot say where the game is may not take a
point off a score ESPN read moments ago.

THE SPECIMEN (Spurs at Thunder, event 15195695), from ux's saved reader at
390 px — `served-responses.json` under
`artifacts/discovery-containers-release-plan/event-page-design-20261011/
live-card-projected-final-next-source-20261020/reader-15195695-0235Z/`:

    02:33:43 / :45 / :47  price cards  31-44  `8:08 - 2nd Quarter`  espn     02:33:35Z
    02:33:49              price cards  30-42  `8:08 - 2nd Quarter`  statpal  02:33:48Z

30-42 had been StatPal's own reading since 02:33:02Z. The row's period and
clock did not move with StatPal's write, which on this writer happens only when
its reading carries no position `live_progress_position` can place — and an
unplaceable incoming position made the guard answer "no evidence", so the
lagging score landed over ESPN's.

The controls carry as much weight as the refusal: the rule must not become the
monotonic clamp `game_state`'s module note rejects. Each one below is a case
where a lower or different score must still land.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import pytest

from app.utils.game_state import (
    UNPLACED_SECONDARY_DEFERS_TO_AUTHORITY_SECONDS,
    live_write_would_revert,
)
from app.utils.score_observation import authority_score_age_seconds
from tests.test_live_state_does_not_run_backwards_6056 import (
    _Fixture,
    _LiveFixture,
    _run_livescores,
    _run_schedules,
    _ScheduleFixture,
)

ROW = ("8:08 - 2nd Quarter", "8:08")
#: Spurs (home) 31, Thunder (away) 44 -> StatPal's 30-42.
SPECIMEN = dict(
    stored_home_score=31,
    stored_away_score=44,
    incoming_home_score=30,
    incoming_away_score=42,
)
#: 02:33:48.14Z - 02:33:35.36Z.
SPECIMEN_AGE = 12.8


class TestTheGuardOnTheSpecimen:
    def test_the_specimen_is_refused(self):
        assert live_write_would_revert(
            *ROW, None, None, stored_authority_score_age_seconds=SPECIMEN_AGE, **SPECIMEN
        )

    @pytest.mark.parametrize(
        "incoming_period, incoming_clock",
        [
            (None, None),  # a bare `live` status
            ("2nd Quarter", None),  # a period name with no clock
            ("8:16 - Q2", "8:16"),  # a label the ladder cannot read
        ],
    )
    def test_every_unplaceable_shape_is_covered(self, incoming_period, incoming_clock):
        assert live_write_would_revert(
            *ROW,
            incoming_period,
            incoming_clock,
            stored_authority_score_age_seconds=SPECIMEN_AGE,
            **SPECIMEN,
        )

    def test_without_the_age_the_verdict_is_what_it_was(self):
        """A caller that does not pass the age, or a row whose score is not
        ESPN's, gets the old answer: no evidence, accepted."""
        assert not live_write_would_revert(*ROW, None, None, **SPECIMEN)

    def test_a_stored_side_that_cannot_be_placed_is_covered_too(self):
        """Soccer's `Half` is deliberately unplaceable on both writers. The
        rule asks the same question: nothing says the lower reading is later."""
        assert live_write_would_revert(
            "2nd Half",
            None,
            "2nd Half",
            None,
            stored_authority_score_age_seconds=30.0,
            stored_home_score=2,
            stored_away_score=1,
            incoming_home_score=1,
            incoming_away_score=1,
        )

    def test_a_placeable_reading_over_an_unplaceable_row_is_covered(self):
        """Only the STORED side unplaceable: the incoming clock is readable but
        there is nothing to compare it with, so it proves nothing is later."""
        stored = ("2nd Quarter", None)
        incoming = ("7:59 - 2nd Quarter", "7:59")
        assert live_write_would_revert(
            *stored, *incoming, stored_authority_score_age_seconds=SPECIMEN_AGE, **SPECIMEN
        )
        assert not live_write_would_revert(*stored, *incoming, **SPECIMEN)

    def test_an_authority_read_after_this_board_is_fresh(self):
        assert live_write_would_revert(
            *ROW, None, None, stored_authority_score_age_seconds=-4.0, **SPECIMEN
        )


class TestWhatStillLands:
    def test_once_the_authority_is_quiet_the_feed_writes_again(self):
        """THE ANTI-PIN. A dark ESPN must not freeze a real correction for
        longer than the window."""
        window = UNPLACED_SECONDARY_DEFERS_TO_AUTHORITY_SECONDS
        assert live_write_would_revert(
            *ROW, None, None, stored_authority_score_age_seconds=window, **SPECIMEN
        )
        assert not live_write_would_revert(
            *ROW, None, None, stored_authority_score_age_seconds=window + 0.1, **SPECIMEN
        )

    def test_the_window_outlasts_espns_measured_beat(self):
        """60 s beat, p95 ~112 s (`tasks/__init__.py` adherence table). A
        window shorter than that lets the specimen through between passes."""
        assert UNPLACED_SECONDARY_DEFERS_TO_AUTHORITY_SECONDS >= 112

    def test_the_authority_correcting_itself_lands(self):
        assert not live_write_would_revert(
            *ROW,
            None,
            None,
            incoming_is_authority=True,
            stored_authority_score_age_seconds=SPECIMEN_AGE,
            **SPECIMEN,
        )

    def test_a_lower_score_from_a_later_placeable_moment_lands(self):
        """A correction from a LATER moment is news (the module note)."""
        assert not live_write_would_revert(
            *ROW,
            "7:59 - 2nd Quarter",
            "7:59",
            stored_authority_score_age_seconds=SPECIMEN_AGE,
            **SPECIMEN,
        )

    @pytest.mark.parametrize("incoming", [(33, 44), (31, 44), (31, 46)])
    def test_an_unplaced_reading_that_lowers_nothing_lands(self, incoming):
        assert not live_write_would_revert(
            *ROW,
            None,
            None,
            stored_authority_score_age_seconds=SPECIMEN_AGE,
            stored_home_score=31,
            stored_away_score=44,
            incoming_home_score=incoming[0],
            incoming_away_score=incoming[1],
        )

    def test_one_missing_score_is_no_evidence(self):
        assert not live_write_would_revert(
            *ROW,
            None,
            None,
            stored_authority_score_age_seconds=SPECIMEN_AGE,
            stored_home_score=31,
            stored_away_score=44,
            incoming_home_score=None,
            incoming_away_score=42,
        )

    def test_the_strictly_earlier_rule_is_untouched(self):
        assert live_write_would_revert(
            *ROW,
            "8:16 - 2nd Quarter",
            "8:16",
            stored_authority_score_age_seconds=None,
            **SPECIMEN,
        )


class TestTheAge:
    AT = datetime(2026, 10, 21, 2, 33, 48, 141198, tzinfo=timezone.utc)
    ESPN_AT = datetime(2026, 10, 21, 2, 33, 35, 357742, tzinfo=timezone.utc)

    def test_espns_stamp_is_aged(self):
        age = authority_score_age_seconds("espn", self.ESPN_AT, at=self.AT)
        assert age == pytest.approx(12.783456)

    @pytest.mark.parametrize("source", ["statpal", "odds_api", None, ""])
    def test_another_feeds_stamp_gives_nothing_to_defer_to(self, source):
        assert authority_score_age_seconds(source, self.ESPN_AT, at=self.AT) is None

    def test_a_missing_clock_is_no_age(self):
        assert authority_score_age_seconds("espn", None, at=self.AT) is None
        assert authority_score_age_seconds("espn", self.ESPN_AT, at=None) is None

    def test_a_naive_clock_is_read_as_utc(self):
        naive = self.ESPN_AT.replace(tzinfo=None)
        assert authority_score_age_seconds("espn", naive, at=self.AT) == pytest.approx(
            12.783456
        )

    def test_an_expired_stamp_is_read_as_absent_not_lazy_loaded(self):
        """After the stamp's forward-only CASE the instance EXPIRES both stamp
        columns; an attribute read would lazy-load (MissingGreenlet in async).
        The writer reads the instance dict, so an expired stamp is no evidence."""
        from app.tasks.statpal_sync import loaded_authority_score_age

        class _Expired:
            @property
            def score_source(self):  # pragma: no cover - must not be read
                raise AssertionError("lazy-loaded an expired stamp")

            score_observed_at = score_source

        assert loaded_authority_score_age(_Expired(), at=self.AT) is None
        fresh = SimpleNamespace(score_source="espn", score_observed_at=self.ESPN_AT)
        assert loaded_authority_score_age(fresh, at=self.AT) == pytest.approx(12.783456)


# ---------------------------------------------------------------------------
# End to end, on the real writers.
# ---------------------------------------------------------------------------


def _specimen_row(stamp):
    return ("San Antonio Spurs", "Oklahoma City Thunder", "8:08", "8:08 - 2nd Quarter", (31, 44), stamp)


def _bare_live_fixture(now, scores=(30, 42)):
    return _Fixture(
        now - timedelta(hours=1),
        "San Antonio Spurs",
        "Oklahoma City Thunder",
        raw_status="live",
        game_clock=None,
        scores=scores,
    )


@pytest.mark.asyncio
async def test_the_30_second_writer_refuses_the_specimen(monkeypatch):
    now = datetime.now(timezone.utc)
    rows, snaps, result = await _run_livescores(
        monkeypatch,
        fixtures=[_bare_live_fixture(now)],
        events=[_specimen_row(("espn", now - timedelta(seconds=13)))],
        sport_key="basketball_nba",
    )

    assert (rows[0].home_score, rows[0].away_score) == (31, 44), (
        "ESPN's 31-44 must not step back to StatPal's 30-42"
    )
    assert rows[0].period == "8:08 - 2nd Quarter"
    assert rows[0].score_source == "espn"
    assert snaps == []
    assert result["reverting_live_skipped"] == 1


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "stamp_source, stamp_age",
    [
        ("espn", timedelta(minutes=10)),  # ESPN went quiet
        ("statpal", timedelta(seconds=13)),  # the row's score is not ESPN's
    ],
)
async def test_the_30_second_writer_still_lands_it_without_a_fresh_authority(
    monkeypatch, stamp_source, stamp_age
):
    now = datetime.now(timezone.utc)
    rows, _snaps, result = await _run_livescores(
        monkeypatch,
        fixtures=[_bare_live_fixture(now)],
        events=[_specimen_row((stamp_source, now - stamp_age))],
        sport_key="basketball_nba",
    )

    assert (rows[0].home_score, rows[0].away_score) == (30, 42)
    assert result["reverting_live_skipped"] == 0


@pytest.mark.asyncio
async def test_the_30_second_writer_still_lands_a_basket_without_a_position(monkeypatch):
    now = datetime.now(timezone.utc)
    rows, _snaps, result = await _run_livescores(
        monkeypatch,
        fixtures=[_bare_live_fixture(now, scores=(33, 44))],
        events=[_specimen_row(("espn", now - timedelta(seconds=13)))],
        sport_key="basketball_nba",
    )

    assert (rows[0].home_score, rows[0].away_score) == (33, 44)
    assert result["reverting_live_skipped"] == 0


@pytest.mark.asyncio
async def test_the_hourly_writer_refuses_the_same_shape(monkeypatch):
    """The second writer on the same columns (CERT-2824) asks the same
    question. The rig is the NFL one; the shape is sport-independent."""
    now = datetime.now(timezone.utc)
    rows, result = await _run_schedules(
        monkeypatch,
        schedule=[
            _ScheduleFixture(
                now - timedelta(hours=3), "New York Giants", "Dallas Cowboys", fixture_id="280459"
            )
        ],
        live=[
            _LiveFixture(
                now - timedelta(hours=3),
                "New York Giants",
                "Dallas Cowboys",
                raw_status="live",
                game_clock=None,
                scores=(28, 14),
            )
        ],
        events=[
            (
                "New York Giants",
                "Dallas Cowboys",
                "5:21",
                "5:21 - 4th Quarter",
                (28, 20),
                "280459",
                ("espn", now - timedelta(seconds=20)),
            )
        ],
    )

    assert (rows[0].home_score, rows[0].away_score) == (28, 20)
    assert result["schedule_reverting_live_skipped"] == 1
