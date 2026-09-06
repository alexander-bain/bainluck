"""#3488: a tennis match page shows the hour the match actually starts.

Measured against production 2026-09-06 12:30Z. **426 of 471** open Kalshi
tennis match markets were stored at a `00:00:00` midnight placeholder, and
**199 tennis events** rendered from them. The specimen a user could see:
`KXATPMATCH-26SEP07ZVEDAR` (Zverev vs Darderi, US Open) — the venue's own
`/markets` gives `occurrence_datetime = 2026-09-07T18:00:00Z`, our row said
`2026-09-07 00:00:00Z`, and `/events/15305789` read **"Sep 6, 2026 · 8:00 PM
EDT · Starts in 11h 27m"** for a match starting Sep 7 at 2:00 PM EDT. Eighteen
hours early, on the wrong day.

TWO defects produced that one number, and **either fix alone leaves the page
still wrong** — the controls at the bottom of this file assert exactly that:

1. **ITF never fetched the hour.** `_is_kalshi_game_ticker` is falsy for
   `KXITFMATCH` (we do not ingest ITF events, so it is deliberately absent
   from `_KALSHI_GAME_TICKERS`), so #3433's occurrence preference never opened
   and the row kept Kalshi's +14d settlement close.
2. **The fix-up threw the hour away for everyone else.** ATP/WTA *are* game
   tickers and *did* store `occurrence_datetime` — and then
   `_fix_tennis_commence_times` re-dated every open tennis match market to the
   ticker's midnight, because the ticker knows nothing finer than a day. That
   rewrite also poisoned the linked Event to midnight, and the fix-up's
   linked-event branch then read that midnight back as agreement: a loop that
   re-confirmed its own bad answer every poll.

The three "populations" #3488 was filed against (+14d backstop / midnight /
real clock) are one population in three stages of this pipeline, not three
bugs. The `real clock` rows were never a lever — they were backstop rows the
fix-up had not reached yet, sitting at Sep 20/21.

The first half is **not tennis-only**: `_TENNIS_MATCH_SERIES_RE` is a shape,
and 16 non-tennis per-match series wear it (rugby, cricket, squash, darts,
chess, volleyball, pickleball, …). They have the identical +14d bug — the
venue gives `KXRUGBYNRLMATCH-26SEP13PENSYD` occurrence 09-13T09:05Z against a
09-27T06:05Z close — so re-timing them is the point. That reach is measured
and pinned in `TestTheNonTennisReachIsADecisionNotAnAccident` so a 17th series
joining the shape is a test failure, not a silent re-timing. The second half
is scoped `llm_sport_category='tennis'` in SQL and never reaches them.
"""

from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import pytest

from app.tasks.kalshi import (
    _fix_tennis_commence_times,
    _is_dated_match_ticker,
    _is_kalshi_game_ticker,
    _kalshi_commence_time,
    _tennis_commence_target,
)

UTC = timezone.utc

# The production specimen, venue-measured 2026-09-06.
ZVEDAR = "KXATPMATCH-26SEP07ZVEDAR"
OCCURRENCE = datetime(2026, 9, 7, 18, 0, tzinfo=UTC)   # venue: when it happens
BACKSTOP = datetime(2026, 9, 21, 15, 0, tzinfo=UTC)    # venue: +14d settlement
TICKER_MIDNIGHT = datetime(2026, 9, 7, tzinfo=UTC)     # all the ticker knows


def _market(occ=OCCURRENCE, close=BACKSTOP):
    return SimpleNamespace(occurrence_datetime=occ, close_time=close)


class TestTheItfTickerReachesItsStartTime:
    """Half one: the hour gets fetched."""

    @pytest.mark.parametrize(
        "ticker",
        [
            "KXITFMATCH-26SEP07OLIGRO",
            "KXITFWMATCH-26SEP06MORGAL",
            "KXITFDOUBLES-26SEP04CESMENAGUDEL",
            "KXITFWDOUBLES-26SEP04CESMENAGUDEL",
            # Not ITF, and the reason a map entry per series is the wrong fix:
            # KXATPEXACTMATCH is a game ticker and KXWTAEXACTMATCH is not.
            "KXWTAEXACTMATCH-26SEP06JOVGAU",
        ],
    )
    def test_a_non_game_tennis_match_ticker_prefers_the_venue_occurrence(self, ticker):
        # The control that makes this test mean something: these are NOT games
        # by the repo's own definition, which is precisely why #3433 missed
        # them. If someone "fixes" this by adding ITF to _KALSHI_GAME_TICKERS
        # this assertion fails and tells them why that is the wrong door.
        assert _is_kalshi_game_ticker(ticker) is None
        assert _is_dated_match_ticker(ticker) is True

        assert (
            _kalshi_commence_time(
                [_market()],
                is_game=False,
                is_dated_match=_is_dated_match_ticker(ticker),
            )
            == OCCURRENCE
        )

    def test_without_the_new_gate_it_keeps_the_plus_14d_backstop(self):
        """The bug, reproduced: this is what production stored for 138 rows."""
        assert (
            _kalshi_commence_time([_market()], is_game=False) == BACKSTOP
        )

    def test_the_gate_is_classification_only_and_never_renames(self):
        """CERT-2043's shape. `is_dated_match` must not become a game verdict:
        `_build_game_market_name` and auto-create both key off `is_game`, and
        a satellite-tour market must not be sent through the matchup renamer."""
        for ticker in ("KXITFMATCH-26SEP07OLIGRO", "KXITFWMATCH-26SEP06MORGAL"):
            assert _is_dated_match_ticker(ticker) is True
            assert _is_kalshi_game_ticker(ticker) is None

    def test_the_gate_covers_every_dated_match_series_game_or_not(self):
        """The whole point of gating on ticker SHAPE rather than a per-series
        map: the game/non-game split across tennis is not a tour boundary and
        does not follow a pattern anyone would guess. Measured 2026-09-06."""
        non_game = {
            "KXITFMATCH-26SEP07OLIGRO",
            "KXITFWMATCH-26SEP06MORGAL",
            "KXITFDOUBLES-26SEP04CESMENAGUDEL",
            "KXITFWDOUBLES-26SEP04CESMENAGUDEL",
            "KXWTAEXACTMATCH-26SEP06JOVGAU",
        }
        game = {
            "KXATPMATCH-26SEP07ZVEDAR",
            "KXWTAMATCH-26SEP07OSARYB",
            "KXATPCHALLENGERMATCH-26SEP06NAKLIU",
            "KXWTACHALLENGERMATCH-26SEP06ZAATSY",
            "KXATPDOUBLES-26SEP04KRAPUTFARWAL",
            "KXWTADOUBLES-26SEP03MUHSTOPARSHY",
            "KXATPEXACTMATCH-26SEP06SHETSI",
        }
        for ticker in non_game:
            assert _is_kalshi_game_ticker(ticker) is None, ticker
        for ticker in game:
            assert _is_kalshi_game_ticker(ticker) is not None, ticker
        # One predicate covers both halves of that split, so no tennis match
        # series can be left behind by an incomplete map again.
        for ticker in non_game | game:
            assert _is_dated_match_ticker(ticker) is True, ticker


class TestTheNonTennisReachIsADecisionNotAnAccident:
    """`_TENNIS_MATCH_SERIES_RE` is a SHAPE, and its name is the misleading
    part. 16 non-tennis series wear that shape, none of them is a game ticker,
    and all 618 of their rows change behaviour under this fix. That is
    deliberate — they have the same bug — but it must never be discovered by
    someone reading a diff months later."""

    #: Measured on production 2026-09-06: every Kalshi series matching the
    #: shape whose main category is not tennis, with row counts.
    NON_TENNIS_SERIES = {
        "kxrugbynrlmatch": 204,
        "kxsquashmatch": 170,
        "kxrugbyeslmatch": 128,
        "kxpplmatch": 15,
        "kxvolleyballmatch": 14,
        "kxchessmatch": 13,
        "kxcricketodimatch": 12,
        "kxtglmatch": 11,
        "kxdartsmatch": 9,
        "kxcountychampmatch": 9,
        "kxsixnationsmatch": 9,
        "kxrugbymlrmatch": 9,
        "kxsshieldmatch": 8,
        "kxcrickettestmatch": 5,
        "kxpickleballmatch": 1,
        "kxwrestlingmatch": 1,
    }

    def test_the_non_tennis_series_are_reached_and_are_not_games(self):
        for series in self.NON_TENNIS_SERIES:
            ticker = f"{series.upper()}-26SEP07ABCDEF"
            assert _is_dated_match_ticker(ticker) is True, ticker
            # None of them is a game ticker, so for every one of these the
            # gate is what opens the occurrence preference — this is the real
            # behaviour change, not a no-op.
            assert _is_kalshi_game_ticker(ticker) is None, ticker

    def test_the_rugby_specimen_has_the_identical_plus_14d_bug(self):
        """Venue-read 2026-09-06 (notice 26): KXRUGBYNRLMATCH-26SEP13PENSYD
        has occurrence 2026-09-13T09:05Z against close 2026-09-27T06:05Z —
        the same +14d settlement backstop tennis has. Re-timing it is the
        point, not collateral damage."""
        occ = datetime(2026, 9, 13, 9, 5, tzinfo=UTC)
        close = datetime(2026, 9, 27, 6, 5, tzinfo=UTC)
        ticker = "KXRUGBYNRLMATCH-26SEP13PENSYD"

        assert _kalshi_commence_time(
            [_market(occ=occ, close=close)],
            is_game=bool(_is_kalshi_game_ticker(ticker)),
            is_dated_match=_is_dated_match_ticker(ticker),
        ) == occ

    def test_the_second_half_never_reaches_them(self):
        """`_fix_tennis_commence_times` is scoped `llm_sport_category='tennis'`
        in SQL, so only the FIRST half touches these series. Asserted against
        the query text so a future widening of that scope is caught here."""
        import inspect

        from app.tasks.kalshi import _fix_tennis_commence_times

        src = inspect.getsource(_fix_tennis_commence_times)
        assert "llm_sport_category = 'tennis'" in src


class TestTheGateRefusesWhatItShould:
    """An outright's occurrence is not a start time — #3433's own warning."""

    @pytest.mark.parametrize(
        "ticker",
        [
            "KXWTA-26USO",
            "KXATPADVANCE-26USOSEMI",
            "KXHONEYDEUCE-01JAN27",
            "KXATP1RANK-26DEC31",     # the day-backtracking trap
            "KXATPMATCH-26SEP6",      # one-digit day
            "",
            None,
        ],
    )
    def test_outrights_and_malformed_tickers_are_refused(self, ticker):
        assert _is_dated_match_ticker(ticker) is False

    def test_an_occurrence_after_its_own_close_is_still_refused(self):
        """The second bound survives the new gate: KXHONEYDEUCE-shaped data
        (occurrence AFTER close) is not an occurrence we understand."""
        m = _market(occ=datetime(2027, 1, 1, 15, 0, tzinfo=UTC),
                    close=datetime(2027, 1, 1, 4, 59, tzinfo=UTC))
        assert (
            _kalshi_commence_time([m], is_game=False, is_dated_match=True)
            == datetime(2027, 1, 1, 4, 59, tzinfo=UTC)
        )


class TestTheFixupStopsThrowingTheHourAway:
    """Half two: the hour survives the next poll."""

    def test_a_market_already_on_its_ticker_day_is_left_alone(self):
        assert (
            _tennis_commence_target(ZVEDAR, None, OCCURRENCE) is None
        ), "re-dating 18:00Z to 00:00Z can only lose the hour"

    def test_the_poisoned_event_loop_cannot_pull_it_back_to_midnight(self):
        """The live regression: Event 15305789 was itself re-dated to midnight
        by this fix-up, and the linked-event branch then read that midnight as
        agreement (|delta| = 0) and wrote it straight back onto the market."""
        assert (
            _tennis_commence_target(ZVEDAR, TICKER_MIDNIGHT, OCCURRENCE) is None
        )

    def test_the_backstop_is_still_re_dated(self):
        """#3403 must not regress: a market genuinely on the +14d backstop is
        still moved, and a linked kick-off still wins when it agrees."""
        assert _tennis_commence_target(ZVEDAR, None, BACKSTOP) == TICKER_MIDNIGHT

        kickoff = datetime(2026, 9, 7, 15, 0, tzinfo=UTC)
        assert _tennis_commence_target(ZVEDAR, kickoff, BACKSTOP) == kickoff

    def test_the_leave_alone_window_ends_where_the_agreement_window_does(self):
        inside = TICKER_MIDNIGHT + timedelta(hours=35)
        outside = TICKER_MIDNIGHT + timedelta(hours=37)
        assert _tennis_commence_target(ZVEDAR, None, inside) is None
        assert _tennis_commence_target(ZVEDAR, None, outside) == TICKER_MIDNIGHT

    @pytest.mark.asyncio
    async def test_the_driver_leaves_a_venue_timed_row_untouched(self, monkeypatch):
        """End to end through the real driver loop, against the two rows
        production actually holds: one already carrying the venue hour, one
        still on the backstop."""
        from tests.test_tennis_commence_times import _install_fake_session, _row

        rows = [
            _row(1, ZVEDAR, OCCURRENCE),                        # must not move
            _row(2, "KXITFMATCH-26SEP07OLIGRO", BACKSTOP),      # must move
        ]
        session = _install_fake_session(monkeypatch, rows)

        assert await _fix_tennis_commence_times() == 1
        assert session.updates == [(2, TICKER_MIDNIGHT)]


class TestEitherHalfAloneLeavesThePageWrong:
    """The reason both halves ship in one commit. Each control replays the
    pipeline — poll writes `commence_time`, next poll's fix-up may rewrite it —
    and asserts what the user would still see."""

    @staticmethod
    def _pipeline(ticker, *, gate_open: bool, fixup_guarded: bool):
        """Returns the commence_time a user would end up seeing."""
        stored = _kalshi_commence_time(
            [_market()],
            is_game=bool(_is_kalshi_game_ticker(ticker)),
            is_dated_match=gate_open and _is_dated_match_ticker(ticker),
        )
        target = _tennis_commence_target(
            ticker,
            TICKER_MIDNIGHT,                     # the poisoned linked event
            stored if fixup_guarded else None,
        )
        return target if target is not None else stored

    def test_half_one_alone_is_red_the_fixup_still_flattens_it(self):
        """Fetch the hour but leave the fix-up unguarded: it is overwritten."""
        got = self._pipeline(
            "KXITFMATCH-26SEP07OLIGRO", gate_open=True, fixup_guarded=False
        )
        assert got == TICKER_MIDNIGHT, "expected the midnight placeholder"

    def test_half_two_alone_is_red_there_is_no_hour_to_protect(self):
        """Guard the fix-up but never fetch the hour: ITF sits on the backstop,
        which is outside the window, so it is re-dated to midnight anyway."""
        got = self._pipeline(
            "KXITFMATCH-26SEP07OLIGRO", gate_open=False, fixup_guarded=True
        )
        assert got == TICKER_MIDNIGHT, "expected the midnight placeholder"

    def test_both_halves_together_show_the_real_start(self):
        got = self._pipeline(
            "KXITFMATCH-26SEP07OLIGRO", gate_open=True, fixup_guarded=True
        )
        assert got == OCCURRENCE

    def test_the_atp_specimen_needed_only_half_two_and_proves_it(self):
        """ATP is already a game ticker, so it always fetched the hour — the
        fix-up alone was destroying it. This is the row behind the screenshot."""
        assert _is_kalshi_game_ticker(ZVEDAR) == "ATP"
        assert (
            self._pipeline(ZVEDAR, gate_open=False, fixup_guarded=False)
            == TICKER_MIDNIGHT
        )
        assert (
            self._pipeline(ZVEDAR, gate_open=False, fixup_guarded=True)
            == OCCURRENCE
        )
