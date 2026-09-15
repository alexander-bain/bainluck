"""A showcase card points at the market we hold, or says nothing (#6249).

`/sport/football` printed "Super Bowl · Date TBD · Odds available closer to the
event" while `/futures/86832` served 32 priced teams repriced that hour. The
card had three branches and none of them could ask whether we held the market,
so the dead card was reached BY CONSTRUCTION for every sport but tennis.

The fix is an allowlist of provider ids, so the tests that matter are the ones
that pin what each declared pattern REFUSES. Every external id quoted here was
read off production on 2026-09-14; they are real siblings that a looser rule
(a name pattern, a tier, a canonical key) admits today.
"""

from datetime import datetime, timezone

import pytest

from app.utils.showcase_futures import (
    MIN_PRICED_OUTCOMES,
    _loggable,
    SHOWCASE_MARKET_IDENTITIES,
    ShowcaseCandidate,
    attach_showcase_markets,
    choose_candidate,
    identity_matches,
    unanchored_identities,
)
from app.utils.sport_keys import SPORT_HIERARCHY

NOW = datetime(2026, 9, 15, 0, 0, tzinfo=timezone.utc)


def patterns_for(sport_slug: str, event_name: str) -> list[str]:
    return [
        identity.external_id_pattern
        for identity in SHOWCASE_MARKET_IDENTITIES[(sport_slug, event_name)]
    ]


def matches_any(sport_slug: str, event_name: str, external_id: str) -> bool:
    return any(
        identity_matches(pattern, external_id)
        for pattern in patterns_for(sport_slug, event_name)
    )


class TestDeclaredIdentitiesAdmitTheRightMarket:
    """Each entry matches the market it was written for."""

    @pytest.mark.parametrize(
        "sport_slug,event_name,external_id",
        [
            ("football", "Super Bowl", "americanfootball_nfl_super_bowl_winner"),
            ("football", "College Football Playoff", "KXNCAAF-27"),
            (
                "football",
                "College Football Playoff",
                "americanfootball_ncaaf_championship_winner",
            ),
            ("basketball", "March Madness (Men's)", "basketball_ncaab_championship_winner"),
            ("hockey", "Stanley Cup", "KXNHL-27"),
            ("hockey", "Stanley Cup", "icehockey_nhl_championship_winner"),
            ("baseball", "World Series", "KXMLB-26"),
            ("baseball", "World Series", "baseball_mlb_world_series_winner"),
            ("soccer", "Champions League", "KXUCL-27"),
            ("soccer", "FIFA World Cup", "KXWC-30"),
        ],
    )
    def test_matches(self, sport_slug, event_name, external_id):
        assert matches_any(sport_slug, event_name, external_id)

    def test_a_kalshi_series_follows_its_competition_into_next_season(self):
        """The season suffix is why these are patterns and not literals."""
        for season in ("26", "27", "28", "31"):
            assert matches_any("soccer", "Champions League", f"KXUCL-{season}")


class TestDeclaredIdentitiesRefuseTheirSiblings:
    """The negative half — every id here is a real open market, and wrong."""

    @pytest.mark.parametrize(
        "sport_slug,event_name,external_id,why",
        [
            # Gender. #6250 is this defect live one surface over: the men's and
            # women's Champions League blended into one cell.
            ("soccer", "FIFA World Cup", "KXWCW-27", "the women's World Cup"),
            # A different stage of the same competition.
            ("soccer", "Champions League", "KXUCLLEAGUE-27", "the league phase"),
            ("football", "College Football Playoff", "KXNCAAFFINALIST-27", "making the final"),
            # A different division.
            ("football", "College Football Playoff", "KXNCAAFFCS-27", "FCS, not FBS"),
            # A prefix collision: every MLB award series starts KXMLB.
            ("baseball", "World Series", "KXMLBAL-26", "the AL pennant"),
            ("baseball", "World Series", "KXMLBALCY-26", "the AL Cy Young"),
            ("baseball", "World Series", "KXMLBALMOTY-26", "AL Manager of the Year"),
            ("baseball", "World Series", "KXMLBBESTRECORD-26", "best regular-season record"),
            # The NBA in-season cup collides with the NBA's own prefix; the
            # same shape would collide here if a KXNHL-flavoured cup appeared.
            ("hockey", "Stanley Cup", "KXNHLCUP-27", "a different competition"),
        ],
    )
    def test_refuses(self, sport_slug, event_name, external_id, why):
        assert not matches_any(sport_slug, event_name, external_id), why

    def test_fifa_world_cup_refuses_the_frozen_odds_api_row(self):
        """`soccer_fifa_world_cup_winner` is the FINISHED 2026 tournament.

        It is still `status='open'`, frozen at 2026-07-19 with Spain 58.7%.
        Declaring it would have pointed the card at a tournament that ended
        two months ago — this assertion is why only Kalshi is declared here.
        """
        assert not matches_any("soccer", "FIFA World Cup", "soccer_fifa_world_cup_winner")

    def test_every_pattern_is_anchored_at_both_ends(self):
        assert unanchored_identities() == []


class TestNotDeclaringIsAnAnswer:
    """An event with no entry keeps the card that says we have nothing."""

    @pytest.mark.parametrize(
        "sport_slug,event_name",
        [
            # Its only market (polymarket 69996) resolved in April, and no open
            # market has been shown to be the women's tournament rather than
            # the men's: both carry llm_league NCAAB and a null llm_gender.
            ("basketball", "March Madness (Women's)"),
            # "World Series" matches the professional market too.
            ("baseball", "College World Series"),
            # Golf majors have their own card branch and an off-season field.
            ("golf", "The Masters"),
            # Wimbledon in September is what the fallback card is FOR.
            ("tennis", "Wimbledon"),
        ],
    )
    def test_no_identity_declared(self, sport_slug, event_name):
        assert (sport_slug, event_name) not in SHOWCASE_MARKET_IDENTITIES

    def test_every_declared_key_names_a_real_showcase_event(self):
        """A renamed showcase event must fail here, not silently go dead.

        The map is keyed on the event's own `name`, which is the string the
        hierarchy serves and the card prints; rename it upstream and every
        declared card falls back to "odds available closer to the event" with
        nothing red.
        """
        declared = set(SHOWCASE_MARKET_IDENTITIES)
        real = {
            (sport["slug"], event["name"])
            for sport in SPORT_HIERARCHY.values()
            for event in sport.get("showcase_events", [])
        }
        assert declared - real == set()


class TestChoosingAmongOpenMarkets:
    """Two seasons of one competition can be open at once."""

    def test_the_soonest_title_wins(self):
        """Measured: KXUCL-26 (last season, resolution date two years out) sat
        open beside KXUCL-27. The card wants the one decided next."""
        last_season = ShowcaseCandidate(392, 36, datetime(2028, 5, 29, tzinfo=timezone.utc))
        this_season = ShowcaseCandidate(
            31834253, 36, datetime(2027, 6, 5, tzinfo=timezone.utc)
        )
        assert choose_candidate([last_season, this_season], now=NOW) is this_season
        assert choose_candidate([this_season, last_season], now=NOW) is this_season

    def test_a_market_past_its_resolution_date_is_out(self):
        stale = ShowcaseCandidate(112911, 60, datetime(2026, 5, 31, tzinfo=timezone.utc))
        assert choose_candidate([stale], now=NOW) is None

    def test_a_dated_market_outranks_an_undated_one(self):
        """Odds API never dates a futures row, so it cannot outrank a row that
        says when it settles."""
        undated = ShowcaseCandidate(8, 32, None)
        dated = ShowcaseCandidate(52755659, 32, datetime(2027, 7, 1, tzinfo=timezone.utc))
        assert choose_candidate([undated, dated], now=NOW) is dated

    def test_an_undated_market_still_wins_when_it_is_the_only_one(self):
        undated = ShowcaseCandidate(86832, 32, None)
        assert choose_candidate([undated], now=NOW) is undated

    def test_a_shell_with_too_few_prices_is_not_a_market(self):
        """"UEFA Women's Champions League 2026-27 Winner" prices exactly one
        team. A card pointing at it shows a field of one."""
        shell = ShowcaseCandidate(60607654, MIN_PRICED_OUTCOMES - 1, None)
        assert choose_candidate([shell], now=NOW) is None

    def test_nothing_open_means_nothing_to_point_at(self):
        assert choose_candidate([], now=NOW) is None

    def test_ties_are_broken_deterministically(self):
        same_date = datetime(2027, 1, 26, tzinfo=timezone.utc)
        a = ShowcaseCandidate(9962834, 50, same_date)
        b = ShowcaseCandidate(181, 50, same_date)
        assert choose_candidate([a, b], now=NOW).market_id == 181
        assert choose_candidate([b, a], now=NOW).market_id == 181

    def test_the_bigger_field_wins_on_the_same_date(self):
        same_date = datetime(2027, 1, 26, tzinfo=timezone.utc)
        small = ShowcaseCandidate(181, 50, same_date)
        big = ShowcaseCandidate(9962834, 109, same_date)
        assert choose_candidate([small, big], now=NOW) is big


class TestTheFailureLogCannotBeForged:
    """`sport_slug` comes off the URL path (CodeQL `py/log-injection`)."""

    def test_a_newline_cannot_write_a_second_log_line(self):
        forged = "soccer\nWARNING:root:transfer approved"
        assert "\n" not in _loggable(forged)
        assert _loggable(forged).startswith("soccer")

    def test_a_real_slug_survives_intact(self):
        for slug in ("soccer", "american-football", "march_madness"):
            assert _loggable(slug) == slug

    def test_a_flood_is_truncated_and_an_empty_one_still_prints(self):
        assert len(_loggable("x" * 4000)) == 40
        assert _loggable("\r\n\r\n") == "(unprintable)"


class FakeResult:
    def __init__(self, rows):
        self._rows = rows

    def all(self):
        return self._rows


class FakeDb:
    """Returns one canned result per `execute`, in order."""

    def __init__(self, *results):
        self._results = list(results)
        self.calls = 0

    async def execute(self, _stmt):
        self.calls += 1
        if not self._results:
            return FakeResult([])
        return self._results.pop(0)


class RaisingDb:
    async def execute(self, _stmt):
        raise RuntimeError("database is down")


class TestAttachingTheMarketToTheEvents:
    async def test_declared_event_carries_its_market(self):
        events = [{"name": "Super Bowl", "type": "championship"}]
        db = FakeDb(FakeResult([(86832, None, 32)]))
        out = await attach_showcase_markets("football", events, db, now=NOW)
        assert out[0]["futures_market_id"] == 86832
        assert out[0]["futures_priced_outcomes"] == 32
        assert out[0]["name"] == "Super Bowl"
        assert out[0]["type"] == "championship"

    async def test_undeclared_event_carries_the_keys_as_null(self):
        """Absent-key and null must not be two ways of saying "no market"."""
        events = [{"name": "March Madness (Women's)", "type": "tournament"}]
        db = FakeDb()
        out = await attach_showcase_markets("basketball", events, db, now=NOW)
        assert out[0]["futures_market_id"] is None
        assert out[0]["futures_priced_outcomes"] is None
        assert db.calls == 0, "an undeclared event must not cost a query"

    async def test_a_declared_event_with_nothing_open_stays_null(self):
        events = [{"name": "Super Bowl", "type": "championship"}]
        db = FakeDb(FakeResult([]))
        out = await attach_showcase_markets("football", events, db, now=NOW)
        assert out[0]["futures_market_id"] is None

    async def test_a_declared_event_whose_only_market_has_settled_stays_null(self):
        events = [{"name": "Champions League", "type": "championship"}]
        db = FakeDb(
            FakeResult([(112911, datetime(2026, 5, 31, tzinfo=timezone.utc), 60)])
        )
        out = await attach_showcase_markets("soccer", events, db, now=NOW)
        assert out[0]["futures_market_id"] is None

    async def test_the_sport_scopes_the_lookup(self):
        """"U.S. Open" is a golf major; the tennis map must not reach it, and
        neither may the championship map reach across sports."""
        events = [{"name": "Super Bowl", "type": "championship"}]
        db = FakeDb(FakeResult([(86832, None, 32)]))
        out = await attach_showcase_markets("soccer", events, db, now=NOW)
        assert out[0]["futures_market_id"] is None
        assert db.calls == 0

    async def test_a_failing_lookup_leaves_the_page_standing(self):
        events = [
            {"name": "Super Bowl", "type": "championship"},
            {"name": "College Football Playoff", "type": "championship"},
        ]
        out = await attach_showcase_markets("football", events, RaisingDb(), now=NOW)
        assert [event["name"] for event in out] == [
            "Super Bowl",
            "College Football Playoff",
        ]
        assert all(event["futures_market_id"] is None for event in out)

    async def test_the_hierarchy_constant_is_never_mutated(self):
        """`SPORT_HIERARCHY` is a module-level dict served to every request."""
        events = SPORT_HIERARCHY["football"]["showcase_events"]
        before = [dict(event) for event in events]
        db = FakeDb(FakeResult([(86832, None, 32)]), FakeResult([(181, None, 50)]))
        await attach_showcase_markets("football", events, db, now=NOW)
        assert [dict(event) for event in events] == before
        assert all("futures_market_id" not in event for event in events)
