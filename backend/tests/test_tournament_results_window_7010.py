"""#7010 — the tournament hub must not revert to its opening-day view.

MEASURED ON PRODUCTION 2026-09-18 18:23Z (latency/569), five days after the US
Open final.  `https://bainluck.com/tournaments/us-open` served:

* **`ROUND OF 128 · 47 matches`** as the CURRENT round, listing
  `SATURDAY, AUG 29 9:00 PM` fixtures — three weeks stale;
* **`FINISHED — No match has finished yet`**, on a completed 128-draw Slam.

Four reads across three distinct `generated_at` values were identical, so this
was the steady state and not #4567's 90-second regeneration window.

ONE CAUSE, BOTH HALVES.  `fetch_tournament_results` defaults to ESPN's CURRENT
day.  The tournament ended 13 September, so from the 14th on today's scoreboard
carries no US Open competition; `order_of_play` is empty; `DECIDED` is the
slate's only route out, so all 96 pinned main-draw fixtures print as the day's
card, and `build_results` has nothing finished to put under them.

WHY EVERY COUNTER STAYED GREEN.  `source_errors []`, `tours_fetched` full,
`state: "live"` — because **nothing failed**.  The request succeeded and
returned an empty day.  The gotcha-#53 defence in `fetch_tournament_results`'
own docstring is aimed at the TIMED-OUT read and is correct there; this is the
succeeded-but-out-of-window read, which wears the same empty shape.

THE VENUE STILL HAS IT, read venue-side before the fix was written (notice 26):
`dates=20260913` returns the event with 625 competitions on both tours,
`dates=20260918` returns no US Open at all.  A date inside the window returns
the WHOLE tournament rather than that day's slice.

What this file holds the fix to:

* the re-ask fires on the ONE empty that means "wrong days", and on neither of
  the other two (a damaged read, a board that named matches);
* it never fires before a tournament starts, because a silent board is then the
  honest answer;
* the zero-yield paths are LOUD — an unmapped slug and a venue silent on the
  tournament's own window both say so in `errors` rather than publishing an
  empty page behind green counters;
* and the reader-visible consequence: with the windowed map in hand the slate
  retires all 96 pinned fixtures as `DECIDED` instead of printing them.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone

import pytest

from app.services.espn_tennis import DECIDED_SLATE_STATE
from app.tasks.tournament_price_refresh import (
    RESULT_CALENDAR_SLUGS,
    _board_is_silent,
    _sync_tournament_results,
    _tournament_window_dates,
)
from app.utils.majors_calendar import load_calendar
from app.utils.tournament_register import TournamentRegister, load_register
from app.utils.tournament_slate import build_slate, espn_competition_id

#: The day the defect was measured: after the US Open's `end`, and the whole
#: point is that this is not a special day — every day after it reads the same.
AFTER_THE_FINAL = datetime(2026, 9, 18, 18, 23, tzinfo=timezone.utc)

#: Inside the ceremony window, so the pinned-fixture clock exemption is live and
#: the 96 rows are reachable. A `now` outside it would retire the draw by the
#: far-end clock and every assertion below would pass for the wrong reason.
DURING = datetime(2026, 9, 5, 20, 0, tzinfo=timezone.utc)

TARGET = [("us-open", "US Open")]


def _silent_board() -> dict:
    """What ESPN returns for a tournament that is not on today's board.

    Clean: both tours answered, nothing raised, no US Open competition in either
    payload. This is the production shape, not an invented one — `stats` is
    present and counts zero, which is exactly the distinction the fix keys on.
    """
    return {
        "draws": {},
        "order_of_play": {},
        "errors": [],
        "tours_fetched": 2,
        "order_of_play_complete": False,
        "stats": {"events": 0, "competitions": 0},
    }


def _full_board(order_of_play: dict | None = None) -> dict:
    """What ESPN returns under a date inside the tournament's own window."""
    return {
        "draws": {"mens-singles": {}},
        "order_of_play": order_of_play if order_of_play is not None else {"1": {}},
        "errors": [],
        "tours_fetched": 2,
        "order_of_play_complete": True,
        "stats": {"events": 2, "competitions": 625},
    }


class _Redis:
    def __init__(self):
        self.writes: list[tuple[str, int, str]] = []

    async def setex(self, key, ttl, value):
        self.writes.append((key, ttl, value))
        return True


def _arm(monkeypatch, replies):
    """Serve `replies` in order and record the `dates` each call asked for."""
    import app.services.espn_tennis as espn
    import app.tasks.redis_state as redis_state

    asked: list[str | None] = []
    queue = list(replies)

    async def _fetch(event_name, *, dates=None):
        asked.append(dates)
        assert queue, f"one fetch too many; already served {len(replies)}"
        return queue.pop(0)

    client = _Redis()
    monkeypatch.setattr(espn, "fetch_tournament_results", _fetch)
    monkeypatch.setattr(redis_state, "get_async_redis_client", lambda: client)
    return asked, client


class TestWhichEmptyMeansAskForOtherDays:
    """Three empties wear one shape and only one of them is this defect."""

    def test_a_clean_board_that_counted_no_competition_is_silent(self):
        assert _board_is_silent(_silent_board()) is True

    def test_a_board_that_counted_competitions_is_not(self):
        assert _board_is_silent(_full_board()) is False

    def test_a_damaged_read_is_not_a_rolled_over_board(self):
        """A tour that FAILED leaves us not knowing what is on the board. Asking
        for other days would publish half a scoreboard as a whole one."""
        damaged = _silent_board()
        damaged["errors"] = ["wta: timeout"]
        damaged["tours_fetched"] = 1
        assert _board_is_silent(damaged) is False

    def test_a_payload_with_no_census_is_not_read_as_a_count_of_zero(self):
        """`parse_results` always writes `stats`, so this is not a production
        shape — and a missing count must not be invented into "we saw nothing"."""
        assert _board_is_silent({"errors": []}) is False


class TestTheWindowTheReAskUses:
    def test_it_is_a_range_over_the_tournaments_own_calendar_dates(self):
        assert (
            _tournament_window_dates("us-open", AFTER_THE_FINAL)
            == "20260824-20260913"
        )

    def test_a_tournament_that_has_not_started_is_never_re_asked(self):
        """Before the first ball a silent board is the honest answer, and a
        future window would put a draw on the hub before it is earned."""
        before = datetime(2026, 8, 1, 12, 0, tzinfo=timezone.utc)
        assert _tournament_window_dates("us-open", before) is None

    def test_the_final_day_is_still_inside_the_window(self):
        """The window runs to the `end` date inclusive, so the last day of the
        tournament is covered rather than falling into the gap this fixes."""
        assert _tournament_window_dates(
            "us-open", datetime(2026, 9, 13, 23, 0, tzinfo=timezone.utc)
        ) == "20260824-20260913"

    def test_an_unmapped_slug_has_no_window(self):
        assert _tournament_window_dates("wimbledon", AFTER_THE_FINAL) is None

    def test_every_mapped_slug_names_a_calendar_entry_that_exists(self):
        """A rename in `majors_calendar.yaml` must not orphan this map silently —
        an orphan reads as "no window", which is the defect wearing a shrug."""
        slugs = {str(e.get("slug")) for e in load_calendar()}
        missing = [v for v in RESULT_CALENDAR_SLUGS.values() if v not in slugs]
        assert not missing, f"no calendar entry for {missing}"


class TestTheSyncReAsksAndPublishesTheRecoveredBoard:
    async def test_a_rolled_over_board_is_re_asked_under_its_own_window(
        self, monkeypatch
    ):
        asked, client = _arm(monkeypatch, [_silent_board(), _full_board()])

        stats = await _sync_tournament_results(TARGET)

        assert asked == [None, "20260824-20260913"], "today first, then the window"
        assert stats["window_reads"] == 1
        assert stats["window_recovered"] == 1
        assert stats["terminal"] == "complete"

        # THE PUBLISHED BYTES ARE THE RECOVERED BOARD, not the empty one. The
        # route reads this key and nothing else, so a re-ask that fetched a full
        # scoreboard and then cached the silent one would be an inert fix.
        cached = json.loads(
            next(v for k, _, v in client.writes if k.endswith("us-open"))
        )
        assert cached["stats"]["competitions"] == 625

    async def test_a_board_that_names_matches_is_asked_once_and_for_today(
        self, monkeypatch
    ):
        """No behaviour change while a tournament is on — one request, no dates,
        which is what the default is right for."""
        asked, _ = _arm(monkeypatch, [_full_board()])

        stats = await _sync_tournament_results(TARGET)

        assert asked == [None]
        assert "window_reads" not in stats
        assert stats["errors"] == []

    async def test_a_damaged_read_is_not_re_asked(self, monkeypatch):
        damaged = _silent_board()
        damaged["errors"] = ["atp: 503"]
        asked, _ = _arm(monkeypatch, [damaged])

        stats = await _sync_tournament_results(TARGET)

        assert asked == [None]
        assert "window_reads" not in stats


class TestTheZeroYieldPathsAreLoud:
    """gotcha #53. Both of these end with an empty page; neither may end with a
    green counter, because a hub that reverted silently is how this ran for five
    days."""

    async def test_a_silent_board_with_no_window_says_so(self, monkeypatch):
        asked, _ = _arm(monkeypatch, [_silent_board()])

        stats = await _sync_tournament_results([("wimbledon", "Wimbledon")])

        assert asked == [None]
        assert any("no window to re-ask" in e for e in stats["errors"])

    async def test_a_venue_silent_on_the_tournaments_own_window_says_so(
        self, monkeypatch
    ):
        asked, _ = _arm(monkeypatch, [_silent_board(), _silent_board()])

        stats = await _sync_tournament_results(TARGET)

        assert asked == [None, "20260824-20260913"]
        assert stats["window_reads"] == 1
        assert "window_recovered" not in stats
        assert any("silent on its own window" in e for e in stats["errors"])

    async def test_a_raising_window_read_leaves_todays_answer_and_reports(
        self, monkeypatch
    ):
        import app.services.espn_tennis as espn
        import app.tasks.redis_state as redis_state

        async def _fetch(event_name, *, dates=None):
            if dates is None:
                return _silent_board()
            raise RuntimeError("espn 503")

        monkeypatch.setattr(espn, "fetch_tournament_results", _fetch)
        monkeypatch.setattr(redis_state, "get_async_redis_client", lambda: _Redis())

        stats = await _sync_tournament_results(TARGET)

        assert any("espn 503" in e for e in stats["errors"])
        assert "window_recovered" not in stats

    @pytest.mark.parametrize(
        "replies",
        [
            pytest.param([_silent_board()], id="no-window"),
            pytest.param([_silent_board(), _silent_board()], id="window-also-silent"),
        ],
    )
    async def test_a_finished_tournament_never_ends_clean_and_empty(
        self, monkeypatch, replies
    ):
        """THE INVARIANT THE ISSUE ASKED FOR, stated where it can be enforced: a
        run that publishes a board naming no match never also reports no error.
        `results.count == 0` with `source_errors == []` is the exact pair a
        reader saw for five days."""
        slug = "us-open" if len(replies) == 2 else "wimbledon"
        _arm(monkeypatch, replies)

        stats = await _sync_tournament_results([(slug, "US Open")])

        assert stats["errors"], "an empty board with a clean error list is the defect"


class TestWhatTheReaderStopsSeeing:
    """The mechanism end to end: the map the re-ask recovers is the one that
    retires the opening-day card."""

    @staticmethod
    def _pinned() -> tuple[dict, list[str]]:
        raw = load_register("us-open", "2026")
        assert raw, "the us-open 2026 register must load — the file needs it"
        ids = [espn_competition_id(m) for m in TournamentRegister(raw).matchups]
        return raw, [i for i in ids if i]

    def test_the_empty_map_is_what_printed_round_of_128(self):
        """Unchanged `build_slate` behaviour, asserted so the fix is measured
        against the defect rather than against nothing."""
        raw, ids = self._pinned()
        slate = build_slate(
            raw, prices={}, now=DURING, order_of_play={}, order_of_play_complete=False
        )

        assert slate["count"] == len(ids) == 96
        assert "DECIDED" not in slate["dropped"]

    def test_the_windowed_map_retires_every_one_of_them(self):
        raw, ids = self._pinned()
        listed = {i: {"state": DECIDED_SLATE_STATE} for i in ids}

        slate = build_slate(
            raw, prices={}, now=DURING, order_of_play=listed, order_of_play_complete=True
        )

        assert slate["dropped"]["DECIDED"] == 96
        assert slate["count"] == 0
