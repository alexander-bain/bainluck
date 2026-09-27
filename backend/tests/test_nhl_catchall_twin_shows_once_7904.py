"""Guard: an NHL game with a Polymarket `icehockey_other` twin shows once — #7904.

THE PAGE THIS EXISTS FOR. `bainluck.com/search?q=oilers` at 390px (authority/1281,
2026-09-26 23:5xZ) and `?q=hurricane` (latency/1166, 2026-09-27 04:5xZ). One game,
two cards, next to each other:

    OTHER HOCKEY · Oct 3 4:00 PM · Oilers 55% / Kraken 45%        <- 15306594
    NHL          · Oct 3 4:00 PM · Edmonton Oilers / Seattle Kraken <- 15319587

The first is a row Polymarket's ingest minted on the `icehockey_other` catch-all
with bare nicknames and no id of any kind. The second is StatPal's NHL row. Each
card holds one venue, so neither shows the blend.

Two things kept the catch-all pass (#5576) from folding them, and both are
fixed here:

* it needed ONE club spelled identically by both rows, and the Polymarket row
  shortens both ("Kraken" / "Seattle Kraken", "Oilers" / "Edmonton Oilers");
* it needed the league row to carry an `espn_id` or `external_id`, and the NHL
  rows for Oct 2–4 are StatPal rows that carry only `statpal_fixture_id`.

Production drive, 461 rows (hockey/basketball/baseball, -2d..+30d), 2026-09-27
08:1xZ: OFF 37 dropped, ON 46, NEW = the nine same-orientation NHL pairs, LOST 0.

WHAT EACH ARM DEFENDS:

* the StatPal specimen folds, onto the NHL row, and the card keeps both venues;
* an ESPN-anchored NHL row folds its twin the same way;
* 🔴 a REVERSED orientation stays two cards — the fold unions venue prices by
  home/away, so pairing reversed rows would print the other club's number;
* each side must pass the name rule on its own;
* 🔴 college keys still refuse (West Georgia / Georgia is a college shape);
* the league row must still carry an id, and the catch-all row must carry none;
* a live game still stays two cards (the existing live refusal).
"""

from datetime import datetime, timedelta, timezone

from app.utils.event_twin_fold import fold_twin_events

PUCK_DROP = datetime(2026, 10, 3, 23, 0, tzinfo=timezone.utc)


class _Sport:
    def __init__(self, id, key):
        self.id = id
        self.key = key


_SPORT_IDS = {"icehockey_nhl": 41, "icehockey_other": 42, "baseball_ncaa": 43,
              "baseball_other": 44}


class _Row:
    """The subset of `Event` the fold reads — not a MagicMock, because an
    auto-attribute mock makes every id column truthy and that truthiness is the
    licence's input."""

    def __init__(
        self,
        id,
        *,
        away,
        home,
        sport_key,
        commence_time=PUCK_DROP,
        external_id=None,
        espn_id=None,
        statpal_fixture_id=None,
        sources=None,
        status="scheduled",
    ):
        self.id = id
        self.sport_id = _SPORT_IDS[sport_key]
        self.sport = _Sport(self.sport_id, sport_key)
        self.away_team_name = away
        self.home_team_name = home
        self.commence_time = commence_time
        self.external_id = external_id
        self.espn_id = espn_id
        self.statpal_fixture_id = statpal_fixture_id
        self.win_probability_sources = sources
        self.status = status
        self.home_score = None
        self.away_score = None
        self.opening_home_probability = None
        self.opening_away_probability = None


def _statpal_nhl_row(**overrides):
    """Production `15319587`: StatPal fixture 652905, Kalshi 0.56, no espn/external id."""
    fields = dict(
        away="Seattle Kraken",
        home="Edmonton Oilers",
        sport_key="icehockey_nhl",
        statpal_fixture_id="652905",
        sources={"kalshi": 0.56},
    )
    fields.update(overrides)
    return _Row(15319587, **fields)


def _polymarket_shadow(**overrides):
    """Production `15306594`: `icehockey_other`, `polymarket_venue`, no id at all."""
    fields = dict(
        away="Kraken",
        home="Oilers",
        sport_key="icehockey_other",
        sources={"polymarket": 0.55},
    )
    fields.update(overrides)
    return _Row(15306594, **fields)


def _survivors(*rows):
    result = fold_twin_events(list(rows))
    return [row.id for row in result.events], result


def test_the_statpal_specimen_is_one_card_carrying_both_venues():
    nhl, shadow = _statpal_nhl_row(), _polymarket_shadow()

    ids, result = _survivors(shadow, nhl)

    assert ids == [15319587]
    assert result.survivor_of == {15306594: 15319587}
    assert set(result.merged_sources[15319587]) == {"kalshi", "polymarket"}


def test_an_espn_anchored_nhl_row_folds_its_twin_the_same_way():
    """Production `15169787` (ESPN 401891820) and shadow `15310325`, Oct 8 23:00Z."""
    at = datetime(2026, 10, 8, 23, 0, tzinfo=timezone.utc)
    nhl = _Row(
        15169787, away="Philadelphia Flyers", home="Ottawa Senators",
        sport_key="icehockey_nhl", commence_time=at, espn_id="401891820",
        external_id="9f6db651fe2d7363616cc72625c4972d",
    )
    shadow = _Row(
        15310325, away="Flyers", home="Senators", sport_key="icehockey_other",
        commence_time=at, sources={"polymarket": 0.47},
    )

    ids, result = _survivors(nhl, shadow)

    assert ids == [15169787]
    assert "polymarket" in result.merged_sources[15169787]


def test_a_reversed_orientation_stays_two_cards():
    """Production `15310317` (Blues @ Sharks) beside `15169788` (Sharks @ Blues).

    The clubs are right and the minute is right, but home and away are swapped.
    The fold unions the catch-all's prices onto the survivor BY SIDE, so one card
    would print the other club's percentage.
    """
    at = datetime(2026, 10, 9, 0, 0, tzinfo=timezone.utc)
    nhl = _Row(
        15169788, away="San Jose Sharks", home="St Louis Blues",
        sport_key="icehockey_nhl", commence_time=at, espn_id="401891825",
    )
    shadow = _Row(
        15310317, away="Blues", home="Sharks", sport_key="icehockey_other",
        commence_time=at, sources={"polymarket": 0.52},
    )

    ids, _ = _survivors(nhl, shadow)

    assert sorted(ids) == [15169788, 15310317]


def test_the_home_side_must_name_the_same_club():
    ids, _ = _survivors(
        _statpal_nhl_row(), _polymarket_shadow(home="Canucks"),
    )
    assert sorted(ids) == [15306594, 15319587]


def test_the_away_side_must_name_the_same_club():
    ids, _ = _survivors(
        _statpal_nhl_row(), _polymarket_shadow(away="Flames"),
    )
    assert sorted(ids) == [15306594, 15319587]


def test_a_college_league_still_refuses_both_sides_differing():
    """The licence's measured false fold, rebuilt across the catch-all.

    `Georgia` ⊆ `West Georgia` and `Florida` ⊆ `North Florida`, same minute, the
    claim id-less and the league row anchored — every other clause holds, and it
    is two real games.
    """
    league = _Row(
        14707767, away="West Georgia", home="North Florida",
        sport_key="baseball_ncaa", external_id="odds-west-georgia",
    )
    claim = _Row(
        14706238, away="Georgia", home="Florida", sport_key="baseball_other",
        sources={"polymarket": 0.5},
    )

    ids, _ = _survivors(league, claim)

    assert sorted(ids) == [14706238, 14707767]


def test_the_league_row_must_still_carry_some_id():
    ids, _ = _survivors(
        _statpal_nhl_row(statpal_fixture_id=None), _polymarket_shadow(),
    )
    assert sorted(ids) == [15306594, 15319587]


def test_a_catchall_row_carrying_a_statpal_id_is_not_folded_on_its_spelling():
    """A StatPal id makes the catch-all row somebody's scheduled fixture."""
    ids, _ = _survivors(
        _statpal_nhl_row(), _polymarket_shadow(statpal_fixture_id="999001"),
    )
    assert sorted(ids) == [15306594, 15319587]


def test_a_live_game_still_stays_two_cards():
    ids, _ = _survivors(
        _statpal_nhl_row(status="live"), _polymarket_shadow(status="live"),
    )
    assert sorted(ids) == [15306594, 15319587]


def test_a_different_game_at_the_same_minute_is_never_pulled_in():
    """Oct 3 23:00Z also has Hurricanes @ Flyers; it must not join Kraken @ Oilers."""
    other_nhl = _Row(
        15319588, away="Carolina Hurricanes", home="Philadelphia Flyers",
        sport_key="icehockey_nhl", statpal_fixture_id="652906",
        sources={"kalshi": 0.51},
    )

    ids, result = _survivors(_statpal_nhl_row(), _polymarket_shadow(), other_nhl)

    assert sorted(ids) == [15319587, 15319588]
    assert result.survivor_of == {15306594: 15319587}


def test_the_minute_must_agree():
    ids, _ = _survivors(
        _statpal_nhl_row(),
        _polymarket_shadow(commence_time=PUCK_DROP + timedelta(hours=1)),
    )
    assert sorted(ids) == [15306594, 15319587]
