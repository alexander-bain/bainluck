"""#8072 arm B — the Athletics' page stops printing the Dodgers' Max Muncy's National League odds.

Two clubs carry a Max Muncy. The prop-families roster branch searches the A's
roster names, so it matched every open "Max Muncy" leg, and the Athletics' MVP
card printed "Max Muncy 1%" from Kalshi's "NL MVP Winner?" (``KXMLBNLMVP-26``,
outcome 1395), after the resolver had already cleared that leg's ``team_id``
(arm A). ``_withhold_other_side`` now also asks ``link_crosses_conference``, the
resolver's own rule, about every market.

The rows are production's shapes (open "Max Muncy" legs, read 2026-09-29): the
Kalshi markets carry no ``sport_id``, and the conference is in the ticker only.
"""

from types import SimpleNamespace

from tests.test_prop_families_side_9610 import _DB, _build, _entities, _reasons
from tests import test_prop_families_side_9610 as side

MLB_ID = 3


def _market(mid, name, external_id):
    return SimpleNamespace(
        id=mid, name=name, source="kalshi", external_id=external_id,
        sport_id=None, group_id=f"kalshi:{external_id}", status="open",
        resolution_date=None, market_metadata={}, llm_sport_category="baseball",
    )


def _pair(oid, player, market):
    outcome = SimpleNamespace(
        id=oid, name=player, current_probability=0.01,
        market_id=market.id, is_winner=False,
    )
    return (outcome, market)


NL_ROWS = [
    _pair(1395, "Max Muncy", _market(209, "NL MVP Winner?", "KXMLBNLMVP-26")),
    _pair(1458, "Max Muncy", _market(211, "NL Hank Aaron Award Winner?", "KXMLBNLHAARON-26")),
    _pair(198634611, "Max Muncy",
          _market(52755974, "Silver Slugger: NL Third Baseman", "KXMLBSS-26NL3B")),
    _pair(219813584, "Max Muncy (LAD)",
          _market(58728331, "National League MVP Finalists", "KXMLBAWARDFIN-26NLMVP")),
]
AL_ROWS = [
    _pair(1605, "Nick Kurtz", _market(216, "AL MVP Winner?", "KXMLBALMVP-26")),
    _pair(1608, "Jacob Wilson", _market(216, "AL MVP Winner?", "KXMLBALMVP-26")),
]
# The league's own board names no conference: nothing to refuse on either page.
LEAGUE_ROWS = [
    _pair(237492328, "Max Muncy (LAD)",
          _market(62952889, "Pro Baseball Championship Series MVP Winner", "KXMLBWSMVP-26")),
]


def _entity_set(rows):
    return {outcome.name for outcome, _ in rows}


def _club(name, *, sport_id=MLB_ID, tid=11494, slug="athletics"):
    return SimpleNamespace(id=tid, name=name, slug=slug, sport_id=sport_id, roster_players=[])


def _db(rows):
    return _DB(rows)


class TestTheConferenceScreen:
    def setup_method(self):
        self._keys = dict(side.SPORT_KEYS)
        side.SPORT_KEYS.clear()
        side.SPORT_KEYS.update({MLB_ID: "baseball_mlb"})

    def teardown_method(self):
        side.SPORT_KEYS.clear()
        side.SPORT_KEYS.update(self._keys)

    async def test_the_athletics_page_drops_every_national_league_leg(self):
        payload = await _build(_club("Athletics"), _db(NL_ROWS + AL_ROWS + LEAGUE_ROWS))
        rows = [row for fam in payload["families"] for row in fam["rows"]]
        assert not {row["outcome_id"] for row in rows} & {o.id for o, _ in NL_ROWS}
        assert _entities(payload) == _entity_set(AL_ROWS + LEAGUE_ROWS)
        assert _reasons(payload) == []

    async def test_the_dodgers_page_keeps_them_and_drops_the_american_league_legs(self):
        payload = await _build(
            _club("Los Angeles Dodgers", tid=10707, slug="los-angeles-dodgers"),
            _db(NL_ROWS + AL_ROWS + LEAGUE_ROWS),
        )
        assert _entities(payload) == _entity_set(NL_ROWS + LEAGUE_ROWS)

    async def test_strawman_an_unscreened_build_prints_the_national_league_muncy(self):
        # A team with no sport_id is not screened: the same fixture then prints
        # every leg, so the tests above are not passing on an empty build.
        # It prints the reader's specimen: "Max Muncy 1%" from the NL MVP board.
        # (The lone "NL MVP Finalists" leg is a one-entity family, never printed.)
        payload = await _build(_club("Athletics", sport_id=None), _db(NL_ROWS + AL_ROWS))
        rows = [row for fam in payload["families"] for row in fam["rows"]]
        assert 1395 in {row["outcome_id"] for row in rows}
        assert "Max Muncy" in _entities(payload)
