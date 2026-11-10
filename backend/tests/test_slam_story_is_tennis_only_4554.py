"""#4554 — searching "wimbledon" stops filing AFC Wimbledon's football under tennis.

WHAT A READER SAW. `/search?q=wimbledon` at 390 px, Nov 7: the ANSWERS card was
headed "GRAND SLAM TENNIS" and held four EFL League One markets for AFC Wimbledon
vs. Blackpool FC (`68595881` and its O/U lines), above the two Wimbledon singles
winner markets. `_story_key` read the bare word "wimbledon" and returned
`story:grand_slam_tennis` whatever sport the market was.

THE GATE. A Slam's name is tennis only when the market's sport category is tennis.
That is the gate the "US Open" rule beside it has always had. Measured over 400
days (read-only, `109604098a09e9c3`), every real Slam market carries "tennis"
(2,332 rows, none null). Every other match was a mis-filing: AFC Wimbledon's
football (590 rows), golf's "career Grand Slam", a baseball grand slam and
esports' "ESL Grand Slam".

  A  the specimen: AFC Wimbledon's markets are not a tennis story, under any of the
     categories they have been filed with;
  B  every real Slam market keeps its story;
  C  another sport's "grand slam" is not tennis, and the US Open rule is unchanged;
  D  the search families composer, as the route calls it: the singles winners form
     the Grand Slam Tennis card and AFC Wimbledon's rows are not in it.
"""

from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

from app.routes.events import _compose_futures_families
from app.utils.feed_market_quality import _story_key

SLAM = "story:grand_slam_tennis"

#: The four markets the live card held (names verbatim from the search payload).
AFC_WIMBLEDON = [
    (69573903, "AFC Wimbledon vs. Blackpool FC: AFC Wimbledon O/U 3.5"),
    (68595881, "AFC Wimbledon vs. Blackpool FC"),
    (69422585, "AFC Wimbledon vs. Blackpool FC: O/U 1.5"),
    (69422589, "AFC Wimbledon vs. Blackpool FC: 1st Half O/U 1.5"),
]
SINGLES = [
    (61082280, "Wimbledon Men's Singles Winner"),
    (61082279, "Wimbledon Women's Singles Winner"),
]


class TestTheSpecimenIsNotTennis:
    def test_the_four_markets_on_the_card_are_not_a_tennis_story(self):
        for _, name in AFC_WIMBLEDON:
            assert _story_key(name, "soccer") != SLAM, name

    def test_nor_under_the_other_categories_these_fixtures_have_been_filed_with(self):
        """Resolved AFC Wimbledon rows carry `basketball`, `baseball` and `football`
        too (the same 400-day read). None of those is tennis either."""
        for category in ("basketball", "baseball", "football", "other", ""):
            assert _story_key("Wigan vs Wimbledon", category) != SLAM, category


class TestEveryRealSlamKeepsItsStory:
    def test_the_production_slam_markets_still_key_as_the_slam(self):
        for name in (
            "Wimbledon Men's Singles Winner",
            "Wimbledon Women's Singles Winner",
            "Australian Open Exacta",
            "Women's French Open: Semifinals Qualifiers",
            "2022 French Open: Who will win Kecmanovic vs. Medvedev?",
            "Roland Garros Men's Singles Winner",
            "Will Jannik Sinner win a Grand Slam this season?",
        ):
            assert _story_key(name, "tennis") == SLAM, name


class TestOtherSportsAndTheUsOpen:
    def test_another_sports_grand_slam_is_not_tennis(self):
        assert _story_key("Will Jordan Spieth complete the career Grand Slam in 2027?", "golf") != SLAM
        assert _story_key("Pro Baseball: 2+ Grand Slam Game", "baseball") != SLAM
        assert _story_key("Will Vitality win the ESL Grand Slam at IEM Rio?", "esports") != SLAM

    def test_the_us_open_rule_is_unchanged(self):
        assert _story_key("US Open Men's Singles Winner", "tennis") == SLAM
        assert _story_key("US Open Winner", "golf") != SLAM


def _market(mid, name, category):
    """A candidate row as the route hands it to the composer (fields it reads)."""
    now = datetime.now(timezone.utc)
    leg = SimpleNamespace(
        id=mid * 10, name="Yes", external_id=f"leg-{mid}", current_probability=0.5,
        current_odds=None, current_american_odds=None, current_yes_bid=0.48,
        current_yes_ask=0.52, previous_probability=None, is_winner=None, rank=None,
        team_id=None,
    )
    return SimpleNamespace(
        id=mid, name=name, external_id=f"PM-{mid}", llm_sport_category=category,
        category="game_prop", market_tier=5, market_type="prop", sport=None,
        sport_id=None, source="polymarket", volume=0.0, status="open",
        mutually_exclusive=False, resolution_date=(now + timedelta(days=30)).date(),
        updated_at=now, canonical_market_key=None, image_url=None,
        hook_description=None, group_id=None, event_id=None, outcomes=[leg],
    )


def _families():
    """The served candidate order: AFC Wimbledon's rows first, as on the live card."""
    markets = [_market(i, n, "soccer") for i, n in AFC_WIMBLEDON]
    markets += [_market(i, n, "tennis") for i, n in SINGLES]
    return _compose_futures_families(
        markets, [("wimbledon", None)], lambda m: {"id": m.id, "name": m.name},
        {m.id for m in markets},
    )


def _ids(family):
    return [family["headline"]["id"]] + [m["id"] for m in family["members"]]


class TestTheSearchCard:
    def test_the_grand_slam_tennis_card_holds_the_singles_winners_only(self):
        slam = [f for f in _families() if f["family_key"] == SLAM]
        assert len(slam) == 1
        assert sorted(_ids(slam[0])) == sorted(i for i, _ in SINGLES)

    def test_no_afc_wimbledon_row_is_under_a_tennis_heading(self):
        afc = {i for i, _ in AFC_WIMBLEDON}
        for family in _families():
            if family["family_key"] == SLAM:
                assert not afc & set(_ids(family))
