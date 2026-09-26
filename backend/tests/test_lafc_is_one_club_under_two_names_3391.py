"""Guard: `LAFC` and `Los Angeles FC` are one club, to the registry and to the fold (#3391).

THE PAGE. `bainluck.com/search?q=lafc` at 390px, 2026-09-26 ~22:40Z, two hours
before FC Dallas v LAFC: one card, `FC Dallas · No price yet · LAFC`. The game
had Kalshi, Polymarket and sportsbook prices — on a SECOND row. Production:

    15314003  FC Dallas / Los Angeles FC  odds_api   96 markets  kalshi, betting, polymarket
    15318170  FC Dallas / LAFC            espn 761835  0 markets  (no sources)

`/api/events/search?q=los angeles fc` and `?q=lafc` return the same seven LAFC
fixtures back to 2026-08-29, once under each name — every LAFC game this season
is two rows.

THE GENERATOR. The Odds API lists the fixture ~10 days out as `Los Angeles FC`
and creates the row. ESPN lists it ~4 days out as `LAFC`; its claim is
schedule-derived (ruling 048 arm B), so it reaches the structured match — and
`names_match('LAFC', 'Los Angeles FC')` was False (one token, nothing to
overlap, nothing to contain), so it CREATED. Nothing downstream could fold the
pair either: the serve-time soccer pass asks `soccer_team_matches`, which also
said False.

THE FIX is one whole-name alias in each of those two predicates — the
`_NATION_NAME_ALIASES` shape (#8675) and the `CLUB_NAME_ALIASES` shape (#6022).
Whole-name, so neither can reach LA Galaxy, the other club in the same city.
"""

from datetime import datetime, timezone

import pytest

from app.models import Event
from app.services.event_registry import EventClaim, _find_by_structured_match
from app.utils.event_twin_fold import fold_twin_events
from app.utils.name_normalization import names_match
from app.utils.soccer_team_matching import soccer_pair_matches, soccer_team_matches
from tests.test_event_registry import _FakeRegistrySession

KICKOFF = datetime(2026, 9, 27, 0, 30, tzinfo=timezone.utc)
MLS_SPORT_ID = 40


class _Sport:
    def __init__(self, key):
        self.key = key


class _Row:
    """The subset of `Event` the fold reads. Not a MagicMock: an auto-attribute
    mock makes every `espn_id` truthy and every `sport.key` anything at all."""

    def __init__(self, id, home, away, *, espn_id=None, external_id=None, sources=None,
                 commence_time_source="espn", sport_key="soccer_usa_mls"):
        self.id = id
        self.sport_id = MLS_SPORT_ID
        self.sport = _Sport(sport_key)
        self.home_team_name = home
        self.away_team_name = away
        self.commence_time = KICKOFF
        self.home_score = None
        self.away_score = None
        self.espn_id = espn_id
        self.external_id = external_id
        self.commence_time_source = commence_time_source
        self.win_probability_sources = sources


def _tonights_pair():
    """The production pair, read 2026-09-26 23:0xZ."""
    priced = _Row(
        15314003, "FC Dallas", "Los Angeles FC",
        external_id="1939426b2b", commence_time_source="odds_api",
        sources={
            "kalshi": {"value": 0.40},
            "betting": {"value": 0.41},
            "polymarket": {"value": 0.39},
        },
    )
    espn = _Row(15318170, "FC Dallas", "LAFC", espn_id="761835")
    return priced, espn


class TestTheRegistryJoinsTheEspnClaimToTheOddsRow:
    @pytest.mark.parametrize("a,b", [("LAFC", "Los Angeles FC"), ("Los Angeles FC", "LAFC")])
    def test_names_match_both_ways(self, a, b):
        assert names_match(a, b)

    def test_it_does_not_reach_the_other_club_in_the_city(self):
        assert not names_match("LAFC", "LA Galaxy")
        assert not names_match("LAFC", "Los Angeles Galaxy")

    @pytest.mark.asyncio
    async def test_espns_lafc_claim_finds_the_odds_row(self):
        """The join that was CREATING a second row every LAFC fixture.

        10/11 Vancouver v LAFC (15316577) exists today only as the Odds row; when
        ESPN lists it this is the call that decides one row or two.
        """
        odds_row = Event(
            id=15316577, sport_id=MLS_SPORT_ID,
            home_team_name="Los Angeles FC", away_team_name="Vancouver Whitecaps FC",
            commence_time=datetime(2026, 10, 11, 2, 30, tzinfo=timezone.utc),
            status="scheduled",
        )
        session = _FakeRegistrySession(structured_candidates=[odds_row], sport_id=MLS_SPORT_ID)
        found = await _find_by_structured_match(
            session, MLS_SPORT_ID, "LAFC", "Vancouver Whitecaps",
            datetime(2026, 10, 11, 2, 30, tzinfo=timezone.utc),
            claim=EventClaim("espn", "761900", schedule_derived=True),
        )
        assert found is odds_row

    @pytest.mark.asyncio
    async def test_a_galaxy_row_at_the_same_minute_is_not_found(self):
        """Control: the alias names LAFC, not Los Angeles."""
        galaxy_row = Event(
            id=1, sport_id=MLS_SPORT_ID,
            home_team_name="LA Galaxy", away_team_name="Vancouver Whitecaps FC",
            commence_time=datetime(2026, 10, 11, 2, 30, tzinfo=timezone.utc),
            status="scheduled",
        )
        session = _FakeRegistrySession(structured_candidates=[galaxy_row], sport_id=MLS_SPORT_ID)
        found = await _find_by_structured_match(
            session, MLS_SPORT_ID, "LAFC", "Vancouver Whitecaps",
            datetime(2026, 10, 11, 2, 30, tzinfo=timezone.utc),
            claim=EventClaim("espn", "761900", schedule_derived=True),
        )
        assert found is None


class TestTheFoldServesTonightsGameOnceWithItsPrice:
    def test_the_soccer_predicate_sees_one_club(self):
        assert soccer_team_matches("LAFC", "Los Angeles FC")
        assert soccer_team_matches("Los Angeles FC", "LAFC")
        assert soccer_pair_matches(("FC Dallas", "LAFC"), ("FC Dallas", "Los Angeles FC"))

    @pytest.mark.parametrize(
        "other,ours",
        [
            ("LA Galaxy", "LAFC"),
            ("Los Angeles Galaxy", "LAFC"),
            ("Los Angeles FC II", "LAFC"),
            ("LAFC 2", "Los Angeles FC"),
        ],
    )
    def test_it_reaches_neither_the_rival_nor_a_reserve_side(self, other, ours):
        assert not soccer_team_matches(other, ours)

    def test_the_pair_folds_and_the_card_keeps_the_price(self):
        priced, espn = _tonights_pair()
        fold = fold_twin_events([priced, espn])

        assert [e.id for e in fold.events] == [espn.id], "the ESPN-anchored row is served"
        assert fold.survivor_of == {priced.id: espn.id}
        # The reader's symptom was "No price yet": the served row must carry the
        # three venues the other row held.
        assert set(fold.merged_sources[espn.id]) == {"kalshi", "betting", "polymarket"}

    def test_before_the_alias_this_pair_did_not_fold(self, monkeypatch):
        """Non-vacuity: the fold above is the alias's doing, not a looser rule."""
        from app.utils import event_twin_fold as etf
        from app.utils import soccer_team_matching as stm

        # `_pair_matches` is memoised, so an answer cached by an earlier test
        # would survive the patch and this control could never fail.
        etf._pair_matches.cache_clear()
        without = {k: v for k, v in stm.CLUB_NAME_ALIASES.items() if v != ("lafc",)}
        monkeypatch.setattr(stm, "CLUB_NAME_ALIASES", without)
        try:
            priced, espn = _tonights_pair()
            fold = fold_twin_events([priced, espn])
            assert fold.dropped_ids == []
        finally:
            etf._pair_matches.cache_clear()

    def test_a_galaxy_fixture_at_the_same_minute_does_not_fold_into_lafcs(self):
        _, espn = _tonights_pair()
        galaxy = _Row(1, "FC Dallas", "LA Galaxy", external_id="x", commence_time_source="odds_api",
                      sources={"betting": {"value": 0.5}})
        fold = fold_twin_events([galaxy, espn])
        assert fold.dropped_ids == []
