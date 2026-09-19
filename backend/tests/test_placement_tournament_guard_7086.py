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
    _PLACEMENT_SEASON_SPREAD_DAYS,
    _PLACEMENT_SEASON_WINDOW_DAYS,
    _PLACEMENT_TOURNAMENT_WINDOW_DAYS,
    league_is_running_at,
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
# First fixture, a fixture in the 30-to-60-day SHOULDER before the kickoffs
# these leagues are tested at, and the last fixture. The shoulder row is not
# decoration: it is the evidence the season arm actually reads, and a
# first-and-last pair cannot express it — production carries 75 NPB fixtures in
# 07-25..08-20, 19 Sudamericana, 15 Libertadores and 18 Swiss.
#
# `basketball_nbl` and `soccer_uefa_nations_league` have NONE, because one
# opened its season on 09-19 and the other only plays in international windows.
# They are here with the rows production actually has, and they place on the
# tournament arm instead — which is the honest reading of a competition whose
# fixtures really are one short burst.
SEASONS = {
    "baseball_npb": (
        _utc("2026-03-27 09:00:00"),
        _utc("2026-08-19 09:00:00"),
        _utc("2026-09-15 09:01:14"),
    ),
    "basketball_nbl": (
        _utc("2026-01-28 08:30:00"), None, _utc("2026-09-20 07:06:00"),
    ),
    "soccer_uefa_nations_league": (
        _utc("2026-03-26 17:00:00"), None, _utc("2026-09-29 18:45:00"),
    ),
    "soccer_conmebol_copa_sudamericana": (
        _utc("2026-03-03 15:00:00"),
        _utc("2026-08-19 22:00:00"),
        _utc("2026-09-18 00:30:00"),
    ),
    "soccer_conmebol_copa_libertadores": (
        _utc("2026-02-04 00:31:00"),
        _utc("2026-08-19 22:00:00"),
        _utc("2026-09-18 00:30:00"),
    ),
    "soccer_switzerland_superleague": (
        _utc("2026-02-07 17:00:00"),
        _utc("2026-08-09 14:30:00"),
        _utc("2026-09-20 14:30:00"),
    ),
}

SCHEDULE_ROWS = [
    ScheduleRow("tennis_atp_us_open", when, "odds_api") for when in US_OPEN_DRAW
] + [
    ScheduleRow(league, when, "odds_api")
    for league, bounds in SEASONS.items()
    for when in bounds
    if when is not None
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

    def test_the_spread_separates_seasons_from_tournaments(self):
        """14 days end to end against 176, either side of a 60-day band."""
        draw_span = (US_OPEN_FINAL - US_OPEN_FIRST).total_seconds() / 86400
        season_spans = [
            (bounds[-1] - bounds[0]).total_seconds() / 86400
            for bounds in SEASONS.values()
        ]
        assert 14 < draw_span < 15
        assert min(season_spans) > 170  # NPB, the shortest of the six
        assert draw_span < _PLACEMENT_SEASON_SPREAD_DAYS < min(season_spans)


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


class TestTheStatedCost:
    """What this ship gives up, asserted rather than left in a PR comment.

    MEASURED, exactly and per event, over every market-born event on a real
    league between 09-01 and 10-20, each judged at its OWN kickoff: of the 147
    the shipped predicate admits today, **5 are newly refused**. (1,729 more sit
    in leagues carrying no schedule-born fixture at all; step 1 already refuses
    those and the new steps never run.)

        basketball_nbl              15313951  09-23  Cairns v Tasmania
        basketball_nbl              15314490  09-24  Perth v Adelaide
        soccer_uefa_champs_league   15313706  09-30  AS Roma v FC Barcelona
        soccer_uefa_nations_league  15314829  09-17  Serbia v Belgium
        soccer_uefa_nations_league  15314830  09-20  Finland v Greece

    ONE MECHANISM, NOT THREE: a competition whose fixtures we hold only in a
    narrow burst reads as a tournament, because on our own data it IS one. NBL
    opened its season on 09-19 behind a horizon 1.1 days wide; we hold one
    Champions League matchday and none of its August qualifiers, so 09-30 is 13
    days from anything; the Nations League plays in windows. All five keep their
    `<sport>_other` catch-all instead of being placed.

    That is the fail-closed direction the catch-all exists for — a vague label
    rather than a wrong one — and every one self-heals as the schedule loads
    forward. It is still a real cost, and Roma v Barcelona is a marquee fixture,
    so it is named rather than summarised. The NBL pair is pinned below as the
    exemplar because its population is small enough to state exactly; widening
    the window to recover any of the five would have to clear the 5.29-day
    defect gap, which is what makes this a trade and not an oversight.
    """

    @pytest.mark.asyncio
    @pytest.mark.parametrize(
        "kickoff,label",
        [
            (_utc("2026-09-23 09:30:00"), "Cairns Taipans v Tasmania JackJumpers"),
            (_utc("2026-09-24 11:30:00"), "Perth Wildcats v Adelaide 36ers"),
        ],
    )
    async def test_a_season_opening_horizon_reads_as_a_tournament(
        self, kickoff, label
    ):
        season_opening = [
            ScheduleRow("basketball_nbl", when, "odds_api")
            for when in (
                _utc("2026-09-19 09:36:00"), _utc("2026-09-19 11:36:00"),
                _utc("2026-09-20 05:06:00"), _utc("2026-09-20 07:06:00"),
            )
        ]
        session = PredicateSession(season_opening)
        assert await league_is_running_at(
            session, "basketball_nbl", kickoff
        ) is False, f"{label}"

    @pytest.mark.asyncio
    async def test_it_is_the_empty_shoulder_and_nothing_else(self):
        """Name the mechanism, so the cost above is not mistaken for a bug.

        NBL's real January fixture does NOT rescue these rows — it is 8 months
        back, far outside the shoulder, exactly like a tournament's previous
        edition. What would rescue them is the league having played in the 30-to
        -60 days before the kickoff, which NBL genuinely had not: its season
        opened four days earlier. The August row below is CONSTRUCTED to show
        the mechanism; production has no such fixture.
        """
        kickoff = _utc("2026-09-23 09:30:00")
        season_opening = [
            ScheduleRow("basketball_nbl", _utc("2026-09-20 07:06:00"), "odds_api")
        ]
        january = ScheduleRow(
            "basketball_nbl", _utc("2026-01-28 08:30:00"), "odds_api"
        )
        constructed_shoulder = ScheduleRow(
            "basketball_nbl", _utc("2026-08-19 09:00:00"), "odds_api"
        )
        assert await league_is_running_at(
            PredicateSession(season_opening + [january]), "basketball_nbl", kickoff
        ) is False
        assert await league_is_running_at(
            PredicateSession(season_opening + [constructed_shoulder]),
            "basketball_nbl",
            kickoff,
        ) is True
