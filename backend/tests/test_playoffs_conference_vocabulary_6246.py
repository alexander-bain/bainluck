"""#6246 — the championship grid renders one block per conference, not one per spelling.

WHAT A READER SAW. `/playoffs/nfl` at 390px drew, in order: a card headed **AFC**
holding two teams (Chargers, Steelers), then a card headed **American Football
Conference** holding the other fourteen, then the same split again on the NFC
side. Nothing was missing and nothing said the two cards were one conference — a
reader looking for the Chargers in the AFC standings found a two-team league.

WHY. `grouped_teams` keys on the raw `conference` string. Two sources feed it:
`Team.standings_data` (live, StatPal) and `static_divisions` (the fallback for
rows with no standings label). They spoke different vocabularies — "American
Football Conference" against "AFC", and on the other field "Central" against
"AL Central" — so the page split whenever the population was MIXED. That mixed
state is not an edge case: it is the offseason → preseason → regular-season
transition the fallback map exists to cover, and MLB was sitting in it on the
division field when this was fixed (29 rows "Central", one "NL Central").

WHAT THESE TESTS GUARD, and it is deliberately the class rather than the two
literals that were wrong:

1. THE INVARIANT — every label the static map emits is already canonical. A
   future league added to the map with a fresh vocabulary fails here, at the
   table, instead of on the page.
2. THE FOLD — an abbreviation arriving from anywhere still lands in the one
   group, so fixing the table did not leave the page one bad upstream row away
   from splitting again.
3. THE SYMPTOM — a mixed population groups into exactly as many blocks as the
   league has conferences. This is the assertion that would have failed on the
   photographed page, and it is stated in the grouping's own terms (a count of
   distinct keys), not in terms of any particular string.
4. THE NON-TARGETS — NBA, NHL and the college grids keep byte-identical
   behaviour, including "SEC" never becoming "SEC Conference". The fix moved a
   rule into a shared helper; a normalizer that quietly widened while doing so
   would be a regression with no issue attached to it.
"""

import pytest

from app.utils.static_divisions import (
    _LEAGUE_MAPS,
    canonical_conference,
    canonical_division,
    grid_conference_key,
    lookup_division,
)


class TestVocabularyInvariant:
    """The fallback's labels ARE the live vocabulary — canonicalizing is a no-op."""

    def test_every_static_label_is_already_canonical(self):
        offenders = []
        for league, table in _LEAGUE_MAPS.items():
            for nickname, (conf, div) in table.items():
                if grid_conference_key(league, conf) != conf:
                    offenders.append((league, nickname, "conference", conf))
                if canonical_division(league, div) != div:
                    offenders.append((league, nickname, "division", div))
        assert offenders == [], (
            "the static map emits labels its own canonicalizer rewrites, which is "
            f"exactly the #6246 split: {offenders[:6]}"
        )

    def test_each_league_emits_one_label_per_conference(self):
        # Two conferences in MLB and two in the NFL — if the table ever holds a
        # second spelling of one of them, the grid grows a block.
        for league, expected in (("mlb", 2), ("nfl", 2)):
            labels = {conf for conf, _div in _LEAGUE_MAPS[league].values()}
            assert len(labels) == expected, f"{league}: {sorted(labels)}"

    def test_each_league_emits_one_label_per_division(self):
        for league, expected in (("mlb", 3), ("nfl", 8)):
            # MLB divisions are scoped by conference (East/Central/West appear in
            # both), the NFL's carry the conference in the name (AFC East, ...).
            labels = {div for _conf, div in _LEAGUE_MAPS[league].values()}
            assert len(labels) == expected, f"{league}: {sorted(labels)}"


class TestTheFold:
    """An abbreviation from any source lands in the canonical group."""

    @pytest.mark.parametrize(
        "league,incoming,expected",
        [
            ("nfl", "AFC", "American Football Conference"),
            ("nfl", "NFC", "National Football Conference"),
            ("nfl", "afc", "American Football Conference"),
            ("nfl", "  AFC  ", "American Football Conference"),
            ("americanfootball_nfl", "AFC", "American Football Conference"),
            ("mlb", "AL", "American League"),
            ("mlb", "NL", "National League"),
            ("mlb", "American", "American League"),
            ("baseball_mlb", "NL", "National League"),
        ],
    )
    def test_conference_aliases(self, league, incoming, expected):
        assert canonical_conference(league, incoming) == expected

    @pytest.mark.parametrize(
        "league,incoming,expected",
        [
            ("mlb", "AL Central", "Central"),
            ("mlb", "NL Central", "Central"),
            ("mlb", "NL West", "West"),
            ("baseball_mlb", "AL East", "East"),
            ("mlb", "Central", "Central"),
        ],
    )
    def test_division_aliases(self, league, incoming, expected):
        assert canonical_division(league, incoming) == expected

    def test_the_specimen_the_issue_photographed(self):
        # The Chargers and the Steelers, whichever source answers for them.
        for name in ("Los Angeles Chargers", "Pittsburgh Steelers"):
            conf, _div = lookup_division("nfl", name)
            assert conf == "American Football Conference"
        assert canonical_conference("nfl", "AFC") == "American Football Conference"

    def test_the_mlb_specimen_measured_on_production(self):
        # 29 rows served "Central" and the Cardinals' standings-less row served
        # "NL Central" on 2026-09-16.
        assert lookup_division("mlb", "St. Louis Cardinals")[1] == "Central"
        assert canonical_division("mlb", "NL Central") == "Central"


def _group_keys(league: str, conferences: list[str]) -> set[str]:
    """What `grouped_teams` would key on for this population."""
    return {grid_conference_key(league, c) for c in conferences if c}


class TestTheSymptom:
    """A MIXED population is one block per conference — the page's own question."""

    def test_nfl_mixed_population_is_two_blocks_not_four(self):
        # 14 rows standings-backed, 2 rows falling back — the exact shape of the
        # photographed page.
        population = ["American Football Conference"] * 14 + ["AFC"] * 2
        population += ["National Football Conference"] * 15 + ["NFC"]
        assert _group_keys("nfl", population) == {
            "American Football Conference",
            "National Football Conference",
        }

    def test_mlb_mixed_population_is_two_blocks(self):
        population = ["American League"] * 15 + ["National League"] * 14 + ["NL"]
        assert _group_keys("mlb", population) == {"American League", "National League"}

    def test_mlb_mixed_divisions_are_six_not_seven(self):
        # The state MLB was actually in: one standings-less row against 29 others.
        population = [
            canonical_division("mlb", d)
            for d in (["East", "Central", "West"] * 9 + ["NL Central"])
        ]
        assert set(population) == {"East", "Central", "West"}

    def test_every_team_lands_in_its_real_conference(self):
        # Not just "two blocks" — the right two, with the right members. A
        # canonicalizer that mapped everything to one string would pass a bare
        # count and fail here.
        for league, table in (
            ("mlb", _LEAGUE_MAPS["mlb"]),
            ("nfl", _LEAGUE_MAPS["nfl"]),
        ):
            for nickname, (conf, _div) in table.items():
                assert grid_conference_key(league, conf) == conf, nickname


class TestNonTargets:
    """Leagues with no alias table are untouched, including the suffix rule."""

    @pytest.mark.parametrize(
        "league,incoming,expected",
        [
            # The directional/league suffix rule, preserved verbatim from the
            # block that used to live inline in playoffs.py.
            ("nba", "Eastern", "Eastern Conference"),
            ("nba", "Western", "Western Conference"),
            ("nhl", "Eastern Conference", "Eastern Conference"),
            # Named conferences must never be suffixed.
            ("ncaa-basketball", "SEC", "SEC"),
            ("ncaa-basketball", "Big Ten", "Big Ten"),
            ("ncaa-football", "ACC", "ACC"),
            # An unmapped label passes through: this normalizes spelling, it
            # never invents membership.
            ("nfl", "Practice Squad", "Practice Squad"),
        ],
    )
    def test_grid_key_passthrough(self, league, incoming, expected):
        assert grid_conference_key(league, incoming) == expected

    @pytest.mark.parametrize(
        "league,incoming",
        [
            # The directional suffix belongs to the grid key alone. Applying it
            # at the metadata site would have rewritten the event page's
            # Championship Path for two leagues with no defect filed against
            # them — `test_get_team_metadata_uses_standings_conference` is the
            # test that caught that, and it is the reason these are two calls.
            ("nba", "Eastern"),
            ("nba", "Western"),
            ("nhl", "Atlantic"),
        ],
    )
    def test_metadata_fold_leaves_directional_names_alone(self, league, incoming):
        assert canonical_conference(league, incoming) == incoming

    @pytest.mark.parametrize(
        "league,incoming",
        [
            ("nhl", "Atlantic Division"),
            ("nhl", "Metropolitan Division"),
            ("nba", "Atlantic"),
            ("nba", "Southeast"),
            ("ncaa-basketball", "East"),
        ],
    )
    def test_division_passthrough(self, league, incoming):
        # NHL says "Atlantic Division" and NBA says "Atlantic"; each is internally
        # consistent within its own league, so neither is rewritten. Scoping the
        # alias table by league is what keeps this fix off their rows.
        assert canonical_division(league, incoming) == incoming

    @pytest.mark.parametrize("value", [None, "", "   "])
    def test_empty_values_survive_unchanged(self, value):
        assert canonical_conference("nfl", value) == value
        assert grid_conference_key("nfl", value) == value
        assert canonical_division("mlb", value) == value

    def test_unknown_league_is_a_passthrough_not_a_crash(self):
        assert canonical_conference(None, "AFC") == "AFC"
        assert grid_conference_key(None, "AFC") == "AFC"
        assert canonical_division("", "AL Central") == "AL Central"
