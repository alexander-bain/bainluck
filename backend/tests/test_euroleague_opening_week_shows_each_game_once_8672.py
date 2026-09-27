"""Guard: EuroLeague's opening week shows each game once — #8672.

THE PAGE THIS EXISTS FOR. `bainluck.com/sports/basketball_euroleague`, 390px,
2026-09-27 07:3xZ, two days before the season opens. Three games drawn twice,
each pair one Odds-API row (`external_id` set) beside one id-less Polymarket
row, at the same minute:

    Sep 29 10:00 AM   Žalgiris 44% / Olympiacos 56%
    Sep 29 10:00 AM   Zalgiris Kaunas 44% / Olympiacos B.C. 56%
    Sep 29 11:30 AM   Pallacanestro Olimpia Milano 70% / Virtus Segafredo Bologna 30%
    Sep 29 11:30 AM   Olimpia Milano 73% / Virtus Bologna 27%
    Oct 1  11:30 AM   (Virtus Segafredo Bologna v Olympiacos, twice)

Frame: `artifacts-lane1-el/BEFORE-euroleague-390.png`. Every other
opening-week pair (Paris–Partizan, Fenerbahce–Bayern, …) already folds because
one club is spelled identically by both providers. On these three NEITHER club
is, and #8100's name pass refuses a both-sides pair everywhere because of
`West Georgia v North Florida` / `Georgia v Florida` (college baseball).

WHAT EACH ARM DEFENDS:

* the three games fold, and the one card keeps both venues;
* a DIFFERENT game at the same minute in the same league (Anadolu Efes v Real
  Madrid, 17:00Z, in the Žalgiris bucket) is never pulled in;
* 🔴 college keys still refuse the both-sides case — the West Georgia specimen;
* catch-all keys and individual sports still refuse it;
* each side must pass the name rule on its own — one matching side is not enough;
* the symmetric, live and two-scoreline refusals still hold on the new arm.
"""

from datetime import datetime, timedelta, timezone

from app.utils.event_twin_fold import _both_sides_may_differ, fold_twin_events

TIP_OFF = datetime(2026, 9, 29, 17, 0, tzinfo=timezone.utc)

EUROLEAGUE = "basketball_euroleague"


class _Sport:
    def __init__(self, id, key):
        self.id = id
        self.key = key


class _Row:
    """The subset of `Event` the fold reads — not a MagicMock, because an
    auto-attribute mock makes every `external_id` truthy and that truthiness is
    the licence's input."""

    def __init__(
        self,
        id,
        *,
        away,
        home,
        sport_key=EUROLEAGUE,
        commence_time=TIP_OFF,
        external_id=None,
        espn_id=None,
        sources=None,
        status="scheduled",
        home_score=None,
        away_score=None,
    ):
        self.id = id
        self.sport_id = abs(hash(sport_key)) % 10**6
        self.sport = _Sport(self.sport_id, sport_key)
        self.away_team_name = away
        self.home_team_name = home
        self.commence_time = commence_time
        self.external_id = external_id
        self.espn_id = espn_id
        self.win_probability_sources = sources
        self.status = status
        self.home_score = home_score
        self.away_score = away_score
        self.opening_home_probability = None
        self.opening_away_probability = None


def _zalgiris_pair(**overrides):
    """Production `15318708` (Odds API) and `15317900` (Polymarket), 2026-09-29 17:00Z."""
    anchored = _Row(
        15318708,
        away="Olympiacos",
        home="Žalgiris",
        external_id="f81c0fafff6aa898b2461179c72d4abd",
        sources={"betting": 0.44},
        **overrides,
    )
    claim = _Row(
        15317900,
        away="Olympiacos B.C.",
        home="Zalgiris Kaunas",
        sources={"polymarket": 0.445},
        **overrides,
    )
    return anchored, claim


def _milano_pair():
    """Production `15318799` (Odds API) and `15317901` (Polymarket), 18:30Z."""
    at = TIP_OFF + timedelta(minutes=90)
    anchored = _Row(
        15318799,
        away="Virtus Segafredo Bologna",
        home="Pallacanestro Olimpia Milano",
        commence_time=at,
        external_id="08d0ddedce84664b3bbb9e4f5137c8fb",
        sources={"betting": 0.70, "kalshi": 0.71},
    )
    claim = _Row(
        15317901,
        away="Virtus Bologna",
        home="Olimpia Milano",
        commence_time=at,
        sources={"polymarket": 0.73},
    )
    return anchored, claim


def _bologna_pair():
    """Production `15319319` (Odds API) and `15318705` (Polymarket), Oct 1 18:30Z."""
    at = datetime(2026, 10, 1, 18, 30, tzinfo=timezone.utc)
    anchored = _Row(
        15319319,
        away="Olympiacos",
        home="Virtus Segafredo Bologna",
        commence_time=at,
        external_id="b317d475532739fa45af483e4a6b017f",
    )
    claim = _Row(
        15318705,
        away="Olympiacos B.C.",
        home="Virtus Bologna",
        commence_time=at,
        sources={"polymarket": 0.40},
    )
    return anchored, claim


def _efes_madrid():
    """Production `15318707`: a DIFFERENT game in the Žalgiris pair's minute."""
    return _Row(
        15318707,
        away="Real Madrid",
        home="Anadolu Efes",
        external_id="670c71e1c104910cc5edf679ee8a65fc",
        sources={"betting": 0.51},
    )


# ── the ship ──────────────────────────────────────────────────────────────────


def test_zalgiris_v_olympiacos_is_one_card():
    anchored, claim = _zalgiris_pair()

    result = fold_twin_events([anchored, claim])

    assert [e.id for e in result.events] == [15318708]
    assert result.dropped_ids == [15317900]


def test_the_one_card_carries_both_venues():
    """The Polymarket price lives on the row that loses, so it must be unioned
    onto the survivor — one card that has quietly dropped a venue is not the
    blend."""
    anchored, claim = _zalgiris_pair()

    result = fold_twin_events([anchored, claim])

    assert result.merged_sources[15318708] == {"betting": 0.44, "polymarket": 0.445}


def test_olimpia_milano_v_virtus_bologna_is_one_card():
    anchored, claim = _milano_pair()

    result = fold_twin_events([anchored, claim])

    assert [e.id for e in result.events] == [15318799]
    assert result.merged_sources[15318799] == {
        "betting": 0.70,
        "kalshi": 0.71,
        "polymarket": 0.73,
    }


def test_virtus_bologna_v_olympiacos_is_one_card():
    anchored, claim = _bologna_pair()

    result = fold_twin_events([anchored, claim])

    assert [e.id for e in result.events] == [15319319]


def test_the_opening_week_page_folds_exactly_the_three_twins():
    """The three pairs and a different game sharing the Žalgiris minute, in the
    order the league page hands them over. Seven rows in, four cards out, and
    Anadolu Efes v Real Madrid is untouched."""
    zal_a, zal_c = _zalgiris_pair()
    mil_a, mil_c = _milano_pair()
    bol_a, bol_c = _bologna_pair()
    efes = _efes_madrid()

    result = fold_twin_events([zal_a, zal_c, efes, mil_a, mil_c, bol_a, bol_c])

    assert sorted(result.dropped_ids) == [15317900, 15317901, 15318705]
    assert sorted(e.id for e in result.events) == [15318707, 15318708, 15318799, 15319319]
    assert 15318707 not in result.merged_sources, "a different game gains nothing"


# ── what must still refuse ────────────────────────────────────────────────────


def test_west_georgia_is_still_not_georgia():
    """🔴 The licence's one measured false fold, `baseball_ncaa` 2026-05-14 22:05Z.
    `baseball_` is an admitted family, so only the college refusal keeps these two
    real games apart."""
    at = datetime(2026, 5, 14, 22, 5, tzinfo=timezone.utc)
    georgia = _Row(14706238, sport_key="baseball_ncaa", away="Georgia", home="Florida", commence_time=at)
    west = _Row(
        14707767,
        sport_key="baseball_ncaa",
        away="West Georgia",
        home="North Florida",
        commence_time=at,
        external_id="ncaa-west-georgia",
    )

    assert len(fold_twin_events([georgia, west]).events) == 2


def test_a_college_basketball_key_refuses_too():
    """`basketball_ncaab` sits inside the `basketball_` family; `Kansas` and
    `Kansas State` are two schools."""
    kansas = _Row(1, sport_key="basketball_ncaab", away="Kansas", home="UCF")
    kstate = _Row(
        2,
        sport_key="basketball_ncaab",
        away="Kansas State Wildcats",
        home="UCF Knights",
        external_id="ncaab-kstate",
    )

    assert len(fold_twin_events([kansas, kstate]).events) == 2


def test_a_catchall_key_refuses():
    """`basketball_other` holds many leagues under one key — the college shape."""
    anchored, claim = _zalgiris_pair(sport_key="basketball_other")

    assert len(fold_twin_events([anchored, claim]).events) == 2


def test_an_individual_sport_refuses():
    """Tennis is not a team family: surnames are not club names."""
    full = _Row(1, sport_key="tennis_atp", away="Zhizhen Zhang", home="Jack Pinnington Jones", external_id="x")
    short = _Row(2, sport_key="tennis_atp", away="Zhang", home="Pinnington Jones")

    assert len(fold_twin_events([full, short]).events) == 2


def test_each_side_must_pass_the_name_rule_on_its_own():
    """`Olympiacos` ⊆ `Olympiacos B.C.` holds on the away side; `Panathinaikos`
    is not `Zalgiris Kaunas`. One related side is not a fixture."""
    anchored, _ = _zalgiris_pair()
    other = _Row(3, away="Olympiacos B.C.", home="Panathinaikos")

    assert len(fold_twin_events([anchored, other]).events) == 2


def test_the_home_side_alone_is_not_enough_either():
    anchored, _ = _zalgiris_pair()
    other = _Row(4, away="Real Madrid", home="Zalgiris Kaunas")

    assert len(fold_twin_events([anchored, other]).events) == 2


def test_two_id_less_rows_still_refuse():
    anchored, claim = _zalgiris_pair()
    anchored.external_id = None

    assert len(fold_twin_events([anchored, claim]).events) == 2


def test_a_live_pair_still_refuses():
    anchored, claim = _zalgiris_pair(status="live")

    assert len(fold_twin_events([anchored, claim]).events) == 2


def test_two_different_scorelines_still_refuse():
    anchored, claim = _zalgiris_pair(status="completed")
    anchored.home_score, anchored.away_score = 80, 75
    claim.home_score, claim.away_score = 70, 88

    assert len(fold_twin_events([anchored, claim]).events) == 2


# ── the admitted leagues ──────────────────────────────────────────────────────


def test_the_admitted_leagues_are_professional_team_leagues():
    for key in (
        "basketball_euroleague",
        "basketball_nba",
        "icehockey_liiga",
        "icehockey_nhl",
        "baseball_npb",
    ):
        assert _both_sides_may_differ(key), key
    for key in (
        "baseball_ncaa",
        "basketball_ncaab",
        "basketball_wncaab",
        "americanfootball_ncaaf",
        "lacrosse_ncaa",
        "basketball_other",
        "icehockey_other",
        "tennis_atp",
        "esports",
        "mma_mixed_martial_arts",
    ):
        assert not _both_sides_may_differ(key), key
