"""#7086 — a placement never files a fixture on a TOURNAMENT that has finished.

THE READER'S COMPLAINT. Four Davis Cup ties playing on 2026-09-19 headed their
pages **"US Open 2026"**. `/events/15314722` — Auger-Aliassime v Rinderknech —
rendered the breadcrumb "‹ US Open 2026" and served
`sport: "tennis_atp_us_open"`, six days after the 2026 US Open final
(Zverev–Shelton, 2026-09-13 18:13:40).

WHY #6392's GUARD PASSED THEM. `KXDAVISCUPMATCH-*` is unmapped, so the row lands
on the honest catch-all `tennis_other`; #5576's placer then re-reads it and asks
which tennis league both players share. A tennis player belongs to every
tournament they have ever entered, permanently, so the two sets intersect at
exactly one league — the most recent Slam they both played — and refusal 2 is
satisfied. #6392's season guard is the one that should stop it, and it did not:
130 schedule-born US Open fixtures sit after its floor, every one of them
played before the tournament ended.

WHY THE CONSTANT COULD NOT JUST BE TIGHTENED, WHICH IS THE WHOLE FINDING.
#6392's own control is `baseball_npb`, whose kickoff sits **7.0 days** past the
last fixture we have loaded, because our schedule horizon ends there while
Polymarket lists further ahead. The four Davis Cup ties sit **5.29–6.16 days**
past the US Open's last fixture. The correct case and the wrong one OVERLAP in
days, so no threshold separates them and a second dimension is required: NPB
runs for 176 days and the draw runs for 14.

EVERY FIXTURE BELOW IS A PRODUCTION ROW, read by db-query on 2026-09-19 ~08:4xZ.
The tournament's own draw is here in full from 09-08, because the controls are
the point: the same guard that refuses the Davis Cup tie must still place the
US Open's own semi-final, whose kickoff is 1.77 days from the final.
"""
from datetime import datetime, timedelta, timezone

import pytest

from app.tasks.prediction_market_matching import (
    MARKET_BORN_COMMENCE_SOURCES,
    _PLACEMENT_BLOCK_GAP_DAYS,
    _PLACEMENT_SEASON_BLOCK_DAYS,
    _PLACEMENT_SEASON_WINDOW_DAYS,
    _PLACEMENT_TOURNAMENT_WINDOW_DAYS,
    league_is_running_at,
    longest_block_days,
)
from tests.lib_placement_predicate import PredicateSession, ScheduleRow


def _utc(text: str) -> datetime:
    return datetime.fromisoformat(text).replace(tzinfo=timezone.utc)


# ── The 2026 US Open, as `events` carries it ─────────────────────────────────
# The draw opened 2026-08-30 15:00 and ran 130 schedule-born fixtures to the
# final. From 09-08 every row is here; the two gaps of 1.80 and 1.77 days are
# the widest inside the draw and they are what sets the tournament window.
US_OPEN_FIRST = _utc("2026-08-30 15:00:00")
US_OPEN_DRAW = [
    US_OPEN_FIRST,
    _utc("2026-09-08 01:12:29"),
    _utc("2026-09-08 18:22:56"),
    _utc("2026-09-09 03:00:23"),
    _utc("2026-09-09 21:02:27"),
    _utc("2026-09-09 23:58:34"),
    _utc("2026-09-11 19:12:43"),
    _utc("2026-09-11 23:38:16"),
    _utc("2026-09-13 18:13:40"),  # Zverev v Shelton — the final
]
US_OPEN_FINAL = US_OPEN_DRAW[-1]

# ── The season competitions ──────────────────────────────────────────────────
# A first-and-last pair cannot express what this guard reads (CERT-3120). The
# season arm asks how long a competition's longest continuous BLOCK of play is,
# which is a question about density: three points 145 days apart describe a
# league that plays three times a year, not one that plays all summer. So each
# competition is carried at the cadence production actually has.


def _every(start: datetime, end: datetime, days: float) -> list[datetime]:
    """Fixtures every ``days`` from ``start`` through ``end``, inclusive."""
    fixtures, when = [], start
    while when <= end:
        fixtures.append(when)
        when += timedelta(days=days)
    return fixtures


# `basketball_nbl` is the CERT-3120 specimen and is carried by its real days:
# a 67-day block last season, a 167-day off-season, then a two-day opening.
# Production holds 46 fixtures on these 30 distinct days (measured 2026-09-19).
NBL_LAST_SEASON = [
    _utc(f"2026-{month_day} 08:30:00")
    for month_day in (
        "01-28", "01-29", "01-30", "01-31", "02-01",
        "02-05", "02-06", "02-07", "02-08",
        "02-12", "02-13", "02-14", "02-15",
        "02-18", "02-19", "02-20", "02-22",
        "03-04", "03-05", "03-07", "03-10", "03-11", "03-14", "03-17",
        "03-21", "03-27", "04-01", "04-05",
    )
]
NBL_THIS_SEASON = [
    _utc("2026-09-19 09:36:00"), _utc("2026-09-19 11:36:00"),
    _utc("2026-09-20 05:06:00"), _utc("2026-09-20 07:06:00"),
]

# The Nations League plays in international WINDOWS — no block of its own is
# longer than a draw, so it is not season-shaped and never will be. It is here
# because it is the competition that proves the "still playing" arm carries its
# own weight: nothing but a fixture AFTER the kickoff rescues it.
#
# EXACTLY AS PRODUCTION CARRIES IT, which is load-bearing and was got wrong
# once. A first draft of this fixture invented June and early-September windows
# and started the last one ON the 09-17 kickoff. That made the tournament arm
# admit the row — there was a fixture 0 days away — so deleting the
# still-playing arm altogether left every test green, and the arm that recovers
# three of CERT-3120's five was untested. Measured 2026-09-19 for a 09-17
# kickoff: 2 fixtures before it, the nearest 174.88 days back, and 30 after it,
# the nearest 7.08 days on. Nothing sits within a week either side.
NATIONS_LEAGUE_WINDOWS = [
    _utc("2026-03-26 17:00:00"),
    _utc("2026-03-29 17:00:00"),
] + _every(_utc("2026-09-24 16:00:00"), _utc("2026-09-29 18:45:00"), 0.2)

SEASONS = {
    "baseball_npb": _every(
        _utc("2026-03-27 09:00:00"), _utc("2026-09-15 09:01:14"), 3
    ),
    "basketball_nbl": NBL_LAST_SEASON + NBL_THIS_SEASON,
    "soccer_uefa_nations_league": NATIONS_LEAGUE_WINDOWS,
    "soccer_conmebol_copa_sudamericana": _every(
        _utc("2026-03-03 15:00:00"), _utc("2026-09-18 00:30:00"), 7
    ),
    "soccer_conmebol_copa_libertadores": _every(
        _utc("2026-02-04 00:31:00"), _utc("2026-09-18 00:30:00"), 7
    ),
    "soccer_switzerland_superleague": _every(
        _utc("2026-02-07 17:00:00"), _utc("2026-09-20 14:30:00"), 7
    ),
    # One matchday every three weeks from February, then the next one 13 days
    # after the Roma v Barcelona kickoff CERT-3120 named. Production holds 964
    # fixtures before that kickoff and 18 after it.
    "soccer_uefa_champs_league": _every(
        _utc("2026-02-17 20:00:00"), _utc("2026-09-10 20:00:00"), 21
    ) + [_utc("2026-10-13 20:00:00"), _utc("2026-10-14 20:00:00")],
}

# The competitions whose longest block really is a season. The Nations League is
# deliberately NOT in here: its windows are shorter than a draw.
CONTINUOUS_SEASONS = {
    league: fixtures
    for league, fixtures in SEASONS.items()
    if league != "soccer_uefa_nations_league"
}

SCHEDULE_ROWS = [
    ScheduleRow("tennis_atp_us_open", when, "odds_api") for when in US_OPEN_DRAW
] + [
    ScheduleRow(league, when, "odds_api")
    for league, fixtures in SEASONS.items()
    for when in fixtures
]

# The four ties, with the kickoff each actually carries.
DAVIS_CUP_TIES = [
    (15314352, _utc("2026-09-19 01:10:00"), "Auger-Aliassime v Halys"),
    (15314583, _utc("2026-09-19 15:10:00"), "Virtanen v Vacherot"),
    (15314613, _utc("2026-09-19 19:00:00"), "Tabilo v Merida"),
    (15314722, _utc("2026-09-19 22:10:00"), "Auger-Aliassime v Rinderknech"),
]


def _six_three_nine_two_admits(rows, league, kickoff) -> bool:
    """#6392's predicate, written out — the guard as it shipped before this.

    Spelled here rather than imported so the control cannot drift into agreeing
    with the code it is the control FOR: if the season arm is silently widened,
    this stays the behaviour that was actually on production on 2026-09-19.
    """
    floor = kickoff - timedelta(days=_PLACEMENT_SEASON_WINDOW_DAYS)
    return any(
        row.league == league
        and row.commence_time >= floor
        and (row.source is None or row.source not in MARKET_BORN_COMMENCE_SOURCES)
        for row in rows
    )


class TestTheFourDavisCupTies:
    @pytest.mark.asyncio
    @pytest.mark.parametrize("event_id,kickoff,label", DAVIS_CUP_TIES)
    async def test_a_finished_tournament_does_not_admit_a_new_fixture(
        self, event_id, kickoff, label
    ):
        session = PredicateSession(SCHEDULE_ROWS)
        assert await league_is_running_at(
            session, "tennis_atp_us_open", kickoff
        ) is False, (
            f"/events/{event_id} — {label} — would head its page 'US Open 2026' "
            f"{(kickoff - US_OPEN_FINAL).days} days after the final"
        )

    @pytest.mark.asyncio
    @pytest.mark.parametrize("event_id,kickoff,label", DAVIS_CUP_TIES)
    async def test_the_shipped_guard_admitted_every_one_of_them(
        self, event_id, kickoff, label
    ):
        """The red-first control, kept.

        Without this the refusals above could pass for any reason at all — a
        typo in the league key would satisfy them. This asserts the guard that
        was ON PRODUCTION said yes to all four, so the new step is what is
        doing the work.
        """
        assert _six_three_nine_two_admits(
            SCHEDULE_ROWS, "tennis_atp_us_open", kickoff
        ) is True, f"{label} was not admitted by #6392 — the specimen is stale"


class TestTheTournamentStillPlacesItsOwn:
    """A guard that only tightens would re-break #5576. Both arms, as asked."""

    @pytest.mark.asyncio
    @pytest.mark.parametrize(
        "kickoff,label",
        [
            (_utc("2026-08-30 15:00:00"), "first ball of the draw"),
            (_utc("2026-09-09 03:00:23"), "Shelton v Alcaraz, round of 16"),
            (_utc("2026-09-11 19:12:43"), "Zverev v Khachanov, semi-final"),
            (_utc("2026-09-13 18:13:40"), "the final itself"),
        ],
    )
    async def test_the_draw_admits_its_own_fixtures(self, kickoff, label):
        session = PredicateSession(SCHEDULE_ROWS)
        assert await league_is_running_at(
            session, "tennis_atp_us_open", kickoff
        ) is True, f"{label} is a US Open fixture and must still be placed there"

    @pytest.mark.asyncio
    async def test_a_later_round_places_while_the_schedule_lags_behind_it(self):
        """The case the window is sized for.

        A Slam's later rounds are not in `events` until the draw resolves, so a
        market can name a semi-final we have not loaded. The widest gap inside
        the real draw is 1.80 days, so a kickoff up to 3 days past the last
        known fixture is still inside the tournament.
        """
        session = PredicateSession(
            [
                ScheduleRow("tennis_atp_us_open", when, "odds_api")
                for when in US_OPEN_DRAW[:-1]  # the final not yet scheduled
            ]
        )
        assert await league_is_running_at(
            session, "tennis_atp_us_open", US_OPEN_FINAL
        ) is True


class TestTheMeasuredMargins:
    def test_the_tournament_window_separates_the_measured_population(self):
        """Assert the MARGIN, not the number — #6392's own discipline.

        Widest gap between consecutive fixtures INSIDE the draw is 1.80 days
        (the ATP and WTA draws both; the French Open's is 2.02). Smallest gap of
        the four wrong placements is 5.29 days. Every value in 2.1..5.2 gives
        the same verdict, and 3 sits inside it.
        """
        widest_inside_the_draw = max(
            (later - earlier).total_seconds() / 86400
            for earlier, later in zip(US_OPEN_DRAW[1:], US_OPEN_DRAW[2:])
        )
        smallest_wrong = min(
            (kickoff - US_OPEN_FINAL).total_seconds() / 86400
            for _, kickoff, _ in DAVIS_CUP_TIES
        )
        assert 1.79 < widest_inside_the_draw < 1.81
        assert 5.28 < smallest_wrong < 5.30
        assert (
            widest_inside_the_draw
            < _PLACEMENT_TOURNAMENT_WINDOW_DAYS
            < smallest_wrong
        )

    def test_the_block_separates_seasons_from_tournaments(self):
        """14 days of play against 176, either side of a 30-day block."""
        draw_block = longest_block_days(US_OPEN_DRAW, _PLACEMENT_BLOCK_GAP_DAYS)
        season_blocks = [
            longest_block_days(fixtures, _PLACEMENT_BLOCK_GAP_DAYS)
            for fixtures in CONTINUOUS_SEASONS.values()
        ]
        assert 14 < draw_block < 15
        assert min(season_blocks) > 60  # NBL's 67, the shortest of the six
        assert draw_block < _PLACEMENT_SEASON_BLOCK_DAYS < min(season_blocks)

    def test_the_block_tolerance_separates_a_lull_from_an_off_season(self):
        """30 days sits between NBL's longest in-season lull and its off-season.

        The two numbers CERT-3120 turned up, measured 2026-09-19: the largest
        gap inside ``basketball_nbl``'s season is 10.0 days (02-22 → 03-04) and
        the break between its seasons is 167 (04-05 → 09-19). A tolerance below
        the first shatters a season into fragments and the league reads as a
        tournament — which is the defect. Above the second, two seasons fuse and
        a finished competition looks eternal. Every value in 11..166 answers the
        same, so assert the margin rather than the number.
        """
        longest_lull = max(
            (later - earlier).total_seconds() / 86400
            for earlier, later in zip(NBL_LAST_SEASON, NBL_LAST_SEASON[1:])
        )
        off_season = (NBL_THIS_SEASON[0] - NBL_LAST_SEASON[-1]).total_seconds() / 86400
        assert 9.9 < longest_lull < 10.1
        assert 166 < off_season < 168
        assert longest_lull < _PLACEMENT_BLOCK_GAP_DAYS < off_season


class TestLongestBlockDays:
    """The shape arithmetic, tested directly rather than through a fake."""

    def test_a_single_fixture_is_not_a_stretch_of_play(self):
        assert longest_block_days([_utc("2026-09-19T00:00")], 30) == 0.0

    def test_no_fixtures_is_not_a_stretch_of_play(self):
        assert longest_block_days([], 30) == 0.0

    def test_it_returns_the_longest_block_not_the_last_or_the_first(self):
        """The 67-day block is found whether it comes first or last.

        A loop that only closes the block it is standing in when the list ends
        returns the LAST block (1 day for NBL, which reads as a tournament and
        reproduces the CERT-3120 defect exactly), and one that returns early
        gives the first. Both orders are asserted so neither passes.
        """
        assert 66 < longest_block_days(NBL_LAST_SEASON + NBL_THIS_SEASON, 30) < 68
        shifted = [when - timedelta(days=365) for when in NBL_THIS_SEASON]
        assert 66 < longest_block_days(shifted + NBL_LAST_SEASON, 30) < 68

    def test_it_holds_the_longest_across_three_blocks(self):
        """Two blocks cannot tell "longest" from "last" — NBL's are 67 and 1, so
        a reader that simply overwrites still ends on 67 and looks correct.

        Three can: the longest first, then a middle one, then a short last one.
        Anything that overwrites as it goes returns the middle block's 20 days.
        """
        first = _every(_utc("2026-01-01 12:00"), _utc("2026-03-09 12:00"), 2)
        middle = _every(_utc("2026-06-01 12:00"), _utc("2026-06-21 12:00"), 2)
        last = [_utc("2026-11-01 12:00"), _utc("2026-11-02 12:00")]
        assert longest_block_days(middle, 30) == 20.0  # the overwriting answer
        assert longest_block_days(first + middle + last, 30) == 66.0

    def test_duplicate_and_unsorted_times_do_not_change_the_answer(self):
        """The query does not promise an order, so the arithmetic may not need one."""
        ordered = longest_block_days(NBL_LAST_SEASON, 30)
        assert longest_block_days(list(reversed(NBL_LAST_SEASON)), 30) == ordered
        assert longest_block_days(NBL_LAST_SEASON * 2, 30) == ordered


class TestAPreviousEditionIsNotASeason:
    """The trap this predicate's SHAPE exists to avoid.

    "Does a fixture exist outside a ±60-day band" is the obvious way to ask
    whether a competition is spread out, and it is wrong: an annual tournament's
    PREVIOUS edition sits ~365 days away, which is outside any such band, so the
    finished draw would read as a season and this whole ship would be inert the
    moment `events` holds two editions. The question is therefore asked of the
    SHOULDER — 30 to 60 days either side — which a previous edition falls well
    outside of. Our `events` table happens to hold one edition today, so nothing
    would have caught this; it is a guard against a data change, not a code one.
    """

    @pytest.mark.asyncio
    async def test_last_years_draw_does_not_vouch_for_this_year(self):
        previous_edition = [
            ScheduleRow("tennis_atp_us_open", when - timedelta(days=364), "odds_api")
            for when in US_OPEN_DRAW
        ]
        session = PredicateSession(SCHEDULE_ROWS + previous_edition)
        assert await league_is_running_at(
            session, "tennis_atp_us_open", _utc("2026-09-19 22:10:00")
        ) is False

    @pytest.mark.asyncio
    async def test_next_years_draw_does_not_vouch_for_this_one_either(self):
        """The same hole on the other side, found by mutation rather than by
        thinking: with the tournament read's CEILING removed every test still
        passed, because nothing in the population sat beyond it. A draw loaded
        for next August would then have proved that this August's draw is still
        running — a finished tournament vouched for by one that has not started.
        """
        next_edition = [
            ScheduleRow("tennis_atp_us_open", when + timedelta(days=346), "odds_api")
            for when in US_OPEN_DRAW
        ]
        session = PredicateSession(SCHEDULE_ROWS + next_edition)
        assert await league_is_running_at(
            session, "tennis_atp_us_open", _utc("2026-09-19 22:10:00")
        ) is False


class TestTheSeasonLeaguesAreUntouched:
    """#6392's correct placements, re-asserted through the new predicate."""

    @pytest.mark.asyncio
    @pytest.mark.parametrize(
        "league,kickoff,label",
        [
            ("baseball_npb", _utc("2026-09-22 09:00:00"), "7.0d past the horizon"),
            ("baseball_npb", _utc("2026-09-20 05:00:00"), "Yomiuri v Yakult"),
            ("basketball_nbl", _utc("2026-09-19 09:30:00"), "Melbourne v Adelaide"),
            ("basketball_nbl", _utc("2026-09-20 05:00:00"), "Breakers v Illawarra"),
            (
                "soccer_uefa_nations_league",
                _utc("2026-09-27 16:00:00"), "Gibraltar v Andorra",
            ),
            (
                "soccer_conmebol_copa_sudamericana",
                _utc("2026-09-16 23:30:00"), "Metropolitanos v Caracas",
            ),
            (
                "soccer_conmebol_copa_libertadores",
                _utc("2026-09-15 22:00:00"), "Carabobo v La Guaira",
            ),
            (
                "soccer_switzerland_superleague",
                _utc("2026-09-19 18:30:00"), "Sion v Zurich",
            ),
        ],
    )
    async def test_a_running_season_still_admits_its_fixture(
        self, league, kickoff, label
    ):
        session = PredicateSession(SCHEDULE_ROWS)
        assert await league_is_running_at(session, league, kickoff) is True, (
            f"{label} is a correct #5576 placement and #7086 must not take it "
            f"back"
        )

    @pytest.mark.asyncio
    async def test_the_new_step_can_only_ever_refuse_more(self):
        """The property that bounds this ship's blast radius.

        It is #6392's predicate AND another, so every row it admits was already
        admitted. Asserted over the whole population rather than claimed in a
        docstring — a future arm that ADMITS something new fails here.
        """
        kickoffs = [kickoff for _, kickoff, _ in DAVIS_CUP_TIES] + [
            _utc("2026-09-20 05:00:00"), _utc("2026-09-22 09:00:00"),
            _utc("2026-09-27 16:00:00"), _utc("2026-10-30 12:00:00"),
        ]
        leagues = ["tennis_atp_us_open", *SEASONS]
        for league in leagues:
            for kickoff in kickoffs:
                session = PredicateSession(SCHEDULE_ROWS)
                now = await league_is_running_at(session, league, kickoff)
                if now:
                    assert _six_three_nine_two_admits(
                        SCHEDULE_ROWS, league, kickoff
                    ), f"{league} at {kickoff} is NEWLY admitted — not allowed"


class TestPhantomsMayNotVouchOnTheTournamentRead:
    @pytest.mark.asyncio
    @pytest.mark.parametrize("source", MARKET_BORN_COMMENCE_SOURCES)
    async def test_a_market_born_row_inside_the_draw_is_not_a_tournament(
        self, source
    ):
        """The circularity, re-closed on the new arm.

        The source exclusion was load-bearing on #6392's single query; the
        tournament read is a THIRD query and would reopen the hole on its own if
        it forgot. Here the only row within 3 days of the kickoff is market-born
        — one phantom Davis Cup tie vouching for the next.
        """
        kickoff = _utc("2026-09-19 22:10:00")
        session = PredicateSession(
            SCHEDULE_ROWS
            + [ScheduleRow("tennis_atp_us_open", kickoff, source)]
        )
        assert await league_is_running_at(
            session, "tennis_atp_us_open", kickoff
        ) is False


class TestTheFiveRefusalsCert3120Named:
    """The five valid placements the first draft of this guard refused.

    CERT-3120 BLOCKed that draft, correctly, and the reason is worth keeping
    where the tests are. The draft classified these as tournaments and refused
    them, and its own commit message called the cost harmless because they
    "self-heal as the schedule loads". They do not.
    ``_create_event_from_prediction_market`` creates the event under
    ``<sport>_other`` and LINKS the market to it even when this predicate says
    no, and every ordinary matching scan selects only
    ``FuturesMarket.event_id IS NULL``. Nothing revisits a linked catch-all, so
    a wrong refusal is permanent — a marquee fixture stranded under "Other"
    forever, which is a worse defect than the one the ship set out to fix.

        basketball_nbl              15313951  09-23  Cairns v Tasmania
        basketball_nbl              15314490  09-24  Perth v Adelaide
        soccer_uefa_champs_league   15313706  09-30  AS Roma v FC Barcelona
        soccer_uefa_nations_league  15314829  09-17  Serbia v Belgium
        soccer_uefa_nations_league  15314830  09-20  Finland v Greece

    They are recovered by two arms rather than by widening a window, because
    they are not one mechanism (the draft said they were). Two of them are a
    league whose new season sits behind a 1.1-day horizon and whose evidence is
    LAST season; three are competitions that simply have not finished. Each arm
    is isolated below, so neither can quietly carry the other.
    """

    @pytest.mark.asyncio
    @pytest.mark.parametrize(
        "league,kickoff,label",
        [
            ("basketball_nbl", _utc("2026-09-23 09:30:00"), "Cairns v Tasmania"),
            ("basketball_nbl", _utc("2026-09-24 11:30:00"), "Perth v Adelaide"),
            (
                "soccer_uefa_champs_league",
                _utc("2026-09-30 16:45:00"),
                "AS Roma v FC Barcelona",
            ),
            (
                "soccer_uefa_nations_league",
                _utc("2026-09-17 14:00:00"),
                "Serbia v Belgium",
            ),
            (
                "soccer_uefa_nations_league",
                _utc("2026-09-20 14:00:00"),
                "Finland v Greece",
            ),
        ],
    )
    async def test_it_places_the_five_it_used_to_strand(self, league, kickoff, label):
        session = PredicateSession(SCHEDULE_ROWS)
        assert await league_is_running_at(session, league, kickoff) is True, label

    @pytest.mark.asyncio
    @pytest.mark.parametrize(
        "kickoff,label",
        [
            (_utc("2026-09-23 09:30:00"), "Cairns v Tasmania"),
            (_utc("2026-09-24 11:30:00"), "Perth v Adelaide"),
        ],
    )
    async def test_the_nbl_pair_is_carried_by_last_season_alone(self, kickoff, label):
        """Isolated: NBL has NOTHING after these kickoffs, so only the block arm
        can rescue it.

        This is the case the ±[30,60] shoulder got wrong. NBL's evidence is 8
        months back — outside any shoulder, exactly where a tournament's
        previous edition sits — and the shoulder therefore could not tell a
        league between seasons from a finished draw. Its LENGTH can: last season
        is a 67-day block and a previous edition is a 14-day one.
        """
        nbl_only = [
            ScheduleRow("basketball_nbl", when, "odds_api")
            for when in NBL_LAST_SEASON + NBL_THIS_SEASON
        ]
        assert not [when for when in NBL_THIS_SEASON if when > kickoff], (
            "premise: nothing is scheduled after this kickoff, so the still-playing "
            "arm cannot be what admits it"
        )
        assert await league_is_running_at(
            PredicateSession(nbl_only), "basketball_nbl", kickoff
        ) is True, label

    @pytest.mark.asyncio
    async def test_without_last_season_the_nbl_pair_is_still_refused(self):
        """The other half of the same claim: it is LAST SEASON doing the work.

        Drop the January-to-April block and the league really is a two-day burst
        with nothing after it — the honest reading is then a refusal, and the
        test that says so is what stops the block arm being mistaken for a
        blanket amnesty.
        """
        opening_only = [
            ScheduleRow("basketball_nbl", when, "odds_api")
            for when in NBL_THIS_SEASON
        ]
        assert await league_is_running_at(
            PredicateSession(opening_only),
            "basketball_nbl",
            _utc("2026-09-23 09:30:00"),
        ) is False

    @pytest.mark.asyncio
    @pytest.mark.parametrize(
        "kickoff,label",
        [
            (_utc("2026-09-17 14:00:00"), "Serbia v Belgium"),
            (_utc("2026-09-20 14:00:00"), "Finland v Greece"),
        ],
    )
    async def test_the_nations_league_is_carried_by_still_playing_alone(
        self, kickoff, label
    ):
        """Isolated: a competition that is not season-shaped and never will be.

        Its windows are each shorter than a Slam's draw, so the block arm says
        tournament and is right to. What makes these placements valid is only
        that the competition has not finished — there are fixtures after the
        kickoff — which is the arm the draft was missing entirely.
        """
        windows = [
            ScheduleRow("soccer_uefa_nations_league", when, "odds_api")
            for when in NATIONS_LEAGUE_WINDOWS
        ]
        assert longest_block_days(
            NATIONS_LEAGUE_WINDOWS, _PLACEMENT_BLOCK_GAP_DAYS
        ) < _PLACEMENT_SEASON_BLOCK_DAYS, (
            "premise: not season-shaped, so the block arm cannot be what admits it"
        )
        assert not [
            when
            for when in NATIONS_LEAGUE_WINDOWS
            if abs((when - kickoff).total_seconds()) / 86400
            <= _PLACEMENT_TOURNAMENT_WINDOW_DAYS
        ], (
            "premise: nothing within the tournament window either, so the "
            "near-fixture arm cannot be what admits it — without this the test "
            "stays green when the still-playing arm is deleted outright"
        )
        assert await league_is_running_at(
            PredicateSession(windows), "soccer_uefa_nations_league", kickoff
        ) is True, label

    @pytest.mark.asyncio
    async def test_the_still_playing_arm_is_bounded_at_the_season_window(self):
        """It may not reach a NEXT edition, which is the mutant that survived.

        Unbounded, "does it play after this kickoff" is satisfied by next year's
        draw and a finished tournament becomes permanently placeable — the exact
        failure the block arm exists to prevent, reintroduced by the arm beside
        it. A fixture 351 days out must not vouch; one 13 days out must.
        """
        finished_draw = [
            ScheduleRow("tennis_atp_us_open", when, "odds_api")
            for when in US_OPEN_DRAW
        ]
        next_edition = ScheduleRow(
            "tennis_atp_us_open", _utc("2027-08-30 15:00:00"), "odds_api"
        )
        kickoff = _utc("2026-09-19 22:10:00")
        assert await league_is_running_at(
            PredicateSession(finished_draw + [next_edition]),
            "tennis_atp_us_open",
            kickoff,
        ) is False
        within_the_window = ScheduleRow(
            "tennis_atp_us_open", _utc("2026-10-02 15:00:00"), "odds_api"
        )
        assert await league_is_running_at(
            PredicateSession(finished_draw + [within_the_window]),
            "tennis_atp_us_open",
            kickoff,
        ) is True

    @pytest.mark.asyncio
    async def test_a_market_born_row_cannot_vouch_on_either_new_arm(self):
        """The circularity, closed on both arms added here.

        A phantom placement must not become the evidence that admits the next
        one — neither by looking like a fixture after the kickoff, nor by
        padding the competition's block into a season.
        """
        kickoff = _utc("2026-09-19 22:10:00")
        for source in MARKET_BORN_COMMENCE_SOURCES:
            ahead = ScheduleRow(
                "tennis_atp_us_open", _utc("2026-10-02 15:00:00"), source
            )
            assert await league_is_running_at(
                PredicateSession(
                    [
                        ScheduleRow("tennis_atp_us_open", when, "odds_api")
                        for when in US_OPEN_DRAW
                    ]
                    + [ahead]
                ),
                "tennis_atp_us_open",
                kickoff,
            ) is False, source
            padding = [
                ScheduleRow("tennis_atp_us_open", when, source)
                for when in _every(
                    _utc("2026-06-01 12:00:00"), _utc("2026-08-29 12:00:00"), 2
                )
            ]
            assert await league_is_running_at(
                PredicateSession(
                    [
                        ScheduleRow("tennis_atp_us_open", when, "odds_api")
                        for when in US_OPEN_DRAW
                    ]
                    + padding
                ),
                "tennis_atp_us_open",
                kickoff,
            ) is False, source
