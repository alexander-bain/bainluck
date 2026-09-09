"""#4242 — a resolved 2024 market minting a new game every seven hours.

`_create_event_from_prediction_market` replaced a market `commence_time` that
disagreed with `now` by more than 30 days with `now` itself, commented "the
market is probably live". For a market whose own start time is two years old
that is not a guess, it is a fabrication — and the row it writes carries no
`events.external_id`, so neither the registry's exact-source-id step nor its
structured match (which keys on time) can ever find it again. The next poll
creates a SECOND row, at a new `now`. Go to 1.

Measured on production 2026-09-09: **1,912 phantom rows across 100 matchups**,
growing ~15/day. Worst single matchup 70 rows. `/api/events/search?q=Whittaker`
returned 25 results of which **24 were the same resolved 2024 fight**, one of
them flagged `live`, burying the one real Whittaker bout on the card.

This is the shape #2020 already named — not ruling 048's bounded duplicate cost
but a generator no drain can outrun — and it is the Polymarket half of it:
`auto_create_self_refutes` closes the identical loop but returns False for
anything that is not Kalshi, because it refuses on a TICKER date and Polymarket
has no ticker at all.

Both directions are asserted throughout: the generator terminates AND a market
that reports a real start still creates its event. The call-site tests are
behavioural with `session=None`, so a refusal that landed after
`find_or_create_event` (i.e. after the bogus row was already written) fails.
"""

from datetime import datetime, timedelta, timezone

import pytest

from app.tasks.prediction_market_matching import (
    AUTO_CREATE_STALE_MARKET_DAYS,
    auto_create_self_refutes,
    auto_create_time_is_invented,
)
from app.utils.prediction_market_matching import (
    extract_matchup,
    is_derivative_market_name,
)

# The clock every test in this file runs against. Fixed, never derived from the
# real one (gotcha #44): offsets are taken FROM this, so no assertion here can
# branch on the day it is run.
NOW = datetime(2026, 9, 9, 8, 20, tzinfo=timezone.utc)


class _Matchup:
    def __init__(self, team_a, team_b):
        self.team_a = team_a
        self.team_b = team_b


class _Market:
    """The fields `_create_event_from_prediction_market` reads, and no others."""

    def __init__(
        self,
        name,
        commence_time,
        source="polymarket",
        external_id="0xb1a8121ceb5610846bca219b13c75a9ef41f9eb2",
        llm_sport_category="mma",
    ):
        self.name = name
        self.commence_time = commence_time
        self.source = source
        self.external_id = external_id
        self.llm_sport_category = llm_sport_category


# The three production specimens, read live 2026-09-09 08:1xZ. Every one of them
# is `status='resolved'` at the venue and was still minting rows that morning.
SPECIMENS = [
    # (market name, market's own commence_time, rows it had already minted)
    ("Whittaker vs. Chimaev",
     datetime(2024, 10, 22, 21, 27, 25, tzinfo=timezone.utc), 61),
    ("Galatasaray vs. AZ Alkmaar",
     datetime(2025, 2, 11, 20, 56, 53, tzinfo=timezone.utc), 62),
    ("Mets vs. Dodgers - Game 4",
     datetime(2024, 10, 17, 1, 10, 57, tzinfo=timezone.utc), 70),
]


# ---------------------------------------------------------------------------
# The premise, asserted rather than assumed
# ---------------------------------------------------------------------------
class TestThePremise:
    """If these stop holding, the rest of the file guards a story, not a defect."""

    @pytest.mark.parametrize("name,commence,_rows", SPECIMENS)
    def test_the_specimen_is_far_enough_past_to_be_a_fabrication(
        self, name, commence, _rows
    ):
        age_days = (NOW - commence).total_seconds() / 86400
        assert age_days > 365, (
            f"{name} was measured 1.5-2 years stale; it is now {age_days:.0f}d"
        )

    @pytest.mark.parametrize("name,commence,_rows", SPECIMENS)
    def test_the_old_thirty_day_rule_would_have_stamped_now(
        self, name, commence, _rows
    ):
        """The line this fix replaces: >30d disagreement => `commence_time = now`.

        This is the fabrication itself. Asserting it keeps the fix honest about
        what it changed.
        """
        assert abs((commence - NOW).total_seconds()) > 86400 * 30

    @pytest.mark.parametrize("name,commence,_rows", SPECIMENS)
    def test_2020s_guard_cannot_see_this(self, name, commence, _rows):
        """Why a new predicate exists at all.

        `auto_create_self_refutes` is the same termination check and it is
        Kalshi-only by construction. For a Polymarket market it is False no
        matter how absurd the row would be, so the loop it closes stayed open
        on this side.
        """
        assert auto_create_self_refutes(_Market(name, commence), NOW) is False


# ---------------------------------------------------------------------------
# The predicate
# ---------------------------------------------------------------------------
class TestAutoCreateTimeIsInvented:
    @pytest.mark.parametrize("name,commence,_rows", SPECIMENS)
    def test_every_production_specimen_is_refused(self, name, commence, _rows):
        assert auto_create_time_is_invented(_Market(name, commence), NOW) is True

    def test_a_market_reporting_a_real_start_is_untouched(self):
        """The direction that matters most: today's fixtures still get created."""
        market = _Market("Sporting Lisbon vs. Galatasaray", NOW + timedelta(hours=11))
        assert auto_create_time_is_invented(market, NOW) is False

    def test_a_game_that_started_an_hour_ago_is_untouched(self):
        market = _Market("Mets vs. Dodgers", NOW - timedelta(hours=1))
        assert auto_create_time_is_invented(market, NOW) is False

    def test_a_market_with_no_time_of_its_own_is_a_different_population(self):
        """Deliberately NOT refused.

        `commence_time IS NULL` holds 376 unlinked Polymarket markets and takes
        a different branch of the caller. Widening this predicate to cover them
        would refuse a population this fix never measured.
        """
        assert auto_create_time_is_invented(_Market("A vs. B", None), NOW) is False

    def test_the_cut_is_where_the_measurement_put_it(self):
        assert AUTO_CREATE_STALE_MARKET_DAYS == 180

    def test_one_day_inside_the_cut_is_kept_and_one_day_outside_is_refused(self):
        """Both sides of the boundary, so a re-tuning cannot pass by accident."""
        inside = _Market(
            "A vs. B", NOW - timedelta(days=AUTO_CREATE_STALE_MARKET_DAYS - 1)
        )
        outside = _Market(
            "A vs. B", NOW - timedelta(days=AUTO_CREATE_STALE_MARKET_DAYS + 1)
        )
        assert auto_create_time_is_invented(inside, NOW) is False
        assert auto_create_time_is_invented(outside, NOW) is True

    def test_a_naive_market_time_is_read_as_utc_not_crashed_on(self):
        """Production stores tz-aware, but the ORM hands back naive on some paths."""
        naive = datetime(2024, 10, 22, 21, 27, 25)
        assert auto_create_time_is_invented(_Market("A vs. B", naive), NOW) is True

    def test_a_ticker_that_reports_a_start_exempts_a_stale_kalshi_market(self):
        """The clause that keeps this cut off Kalshi's back.

        A Kalshi market whose own `commence_time` is two years past but whose
        TICKER parses to a date is not inventing anything — #2020 already gives
        that row a reported start. Refusing it here would delete a real fixture.
        """
        market = _Market(
            "LoL: GAM vs. TSW",
            datetime(2024, 8, 21, tzinfo=timezone.utc),
            source="kalshi",
            external_id="KXLOLGAME-26AUG210500GAMTSW",
        )
        assert auto_create_time_is_invented(market, NOW) is False


# ---------------------------------------------------------------------------
# The call site — reachability, not just a pure function
# ---------------------------------------------------------------------------
class TestTheRefusalIsReachedBeforeAnythingIsWritten:
    """BEHAVIOURAL, with `session=None` as the assertion.

    A pure predicate proves nothing about whether the caller consults it. These
    run the real writer: the refusal must land BEFORE `find_or_create_event`, so
    a None session can never be dereferenced. A refusal that fired afterwards
    would already have written the phantom row.
    """

    @pytest.mark.asyncio
    @pytest.mark.parametrize("name,commence,_rows", SPECIMENS)
    async def test_the_specimen_mints_nothing(self, name, commence, _rows):
        from app.tasks.prediction_market_matching import (
            _create_event_from_prediction_market,
        )

        matchup = extract_matchup(name)
        assert matchup is not None, "the parse changed — this test is now vacuous"

        result = await _create_event_from_prediction_market(
            None, matchup, _Market(name, commence), NOW,
        )
        assert result is None

    @pytest.mark.asyncio
    async def test_a_market_with_a_real_start_runs_past_the_refusal(self):
        """The control that makes the test above mean something.

        The SAME call for a fixture whose market reports a start today must run
        PAST the new refusal and only then fail on the None session. Without
        this, a writer that returned None unconditionally would pass every
        assertion in the class above — and every sport The Odds API does not
        cover would silently stop being created.
        """
        from app.tasks.prediction_market_matching import (
            _create_event_from_prediction_market,
        )

        with pytest.raises(AttributeError):
            await _create_event_from_prediction_market(
                None,
                _Matchup("Whittaker", "Chimaev"),
                _Market("Whittaker vs. Chimaev", NOW + timedelta(hours=6)),
                NOW,
            )


# ---------------------------------------------------------------------------
# The rider: the one derivative label #2871 could not reach
# ---------------------------------------------------------------------------
class TestHighestScoringQuarterIsADerivative:
    """`Patriots vs. Seahawks - Highest Scoring Quarter` named an away team on
    production 2026-09-05, twice, five days after #2871 shipped.

    #2871's alternation is `segment x market-type`, which reads a LEADING period
    ("1st Half First Team to Score"). Here the period word is the market type's
    own tail, so no combination of those two halves reaches it.
    """

    @pytest.mark.parametrize(
        "title",
        [
            "Patriots vs. Seahawks - Highest Scoring Quarter",
            "49ers vs. Rams - Highest Scoring Quarter",
            "Arsenal vs. Chelsea - Highest Scoring Half",
            "Bruins vs. Rangers - Highest Scoring Period",
            "Mets vs. Dodgers - Highest Scoring Inning",
        ],
    )
    def test_the_label_is_refused(self, title):
        assert is_derivative_market_name(title) is True

    @pytest.mark.parametrize(
        "title",
        [
            # A distinct real game in a series — stripping it would MERGE
            # Games 1-5 into one event, the opposite of this fix (#2871's note).
            "Mets vs. Dodgers - Game 4",
            # The game's own container market still creates the fixture.
            "CF Estrela da Amadora vs. FC Porto - More Markets",
            # A hyphen inside a club name is not a suffix.
            "FC Thun vs. Lausanne-Sport",
        ],
    )
    def test_the_shapes_2871_deliberately_keeps_are_still_kept(self, title):
        assert is_derivative_market_name(title) is False
