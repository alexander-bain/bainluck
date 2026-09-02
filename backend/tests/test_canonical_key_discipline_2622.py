"""#2622 — the canonical key names WHICH question, not just which sport.

RED-FIRST. On master every test in `TestTheCardThatShippedAMan` fails, because
`compute_canonical_market_key` had no axis below sport/league/category/season and
the two US Open winner boards therefore carried one identical key. The controls
in `TestNothingElseMoved` are green on BOTH trees on purpose — they are what says
the axis is additive rather than a rewrite.

Every string in `TestTheCardThatShippedAMan` and `TestTheReplayFoundThis` is a
VERBATIM production market name, pulled from `futures_markets` on 2026-09-01,
apostrophes and all. The typographic apostrophe in "Women’s" is U+2019 and is the
reason a pattern written with a plain `'` would have matched nothing at all.
"""

import inspect

import pytest

from app.utils.futures_categorization import compute_canonical_market_key


def _sym(name):
    """Fetch a #2622 symbol, or FAIL BY ASSERTION naming what is missing.

    Imported lazily rather than at module scope so this file COLLECTS on a tree
    without the fix. A red-first run that dies at collection reports an error,
    not a count of failures, and an error cannot be told apart from a broken
    test file — which is the one thing a red-first proof has to rule out.
    """
    import app.utils.futures_categorization as fc

    fn = getattr(fc, name, None)
    assert fn is not None, (
        f"app.utils.futures_categorization.{name} does not exist on this tree — "
        "#2622's discipline axis is not applied"
    )
    return fn


def _key(name, sport="tennis", league=None, category="championship", season="2026"):
    assert "market_name" in inspect.signature(compute_canonical_market_key).parameters, (
        "compute_canonical_market_key takes no `market_name` on this tree — "
        "#2622's discipline axis is not applied"
    )
    return compute_canonical_market_key(sport, league, category, season, market_name=name)


def detect_gender_axis(name):
    return _sym("detect_gender_axis")(name)


def detect_competition_axis(name):
    return _sym("detect_competition_axis")(name)


def detect_matchup_axis(name):
    return _sym("detect_matchup_axis")(name)


def market_discipline_axis(name):
    return _sym("market_discipline_axis")(name)


class TestTheCardThatShippedAMan:
    """The /sports Top Markets card that put Alcaraz #1 in the women's draw."""

    MENS = "2026 Men’s US Open Winner (Tennis)"
    WOMENS = "2026 Women’s US Open Winner (Tennis)"

    def test_the_two_us_open_boards_no_longer_share_a_key(self):
        # Market 114159 and market 114160, both `tennis::championship:2026` in
        # production. One key, two questions, and the client grouped on it.
        assert _key(self.MENS) != _key(self.WOMENS)

    def test_each_board_names_its_own_draw_and_its_own_event(self):
        assert _key(self.MENS) == "tennis::championship:2026:mens-us-open"
        assert _key(self.WOMENS) == "tennis::championship:2026:womens-us-open"

    def test_the_typographic_apostrophe_is_the_one_production_actually_uses(self):
        # U+2019, not U+0027. Both rows carry it; a plain-apostrophe pattern
        # would have shipped green and changed nothing.
        assert "’" in self.WOMENS
        assert detect_gender_axis(self.WOMENS) == "womens"
        assert detect_gender_axis(self.MENS) == "mens"

    def test_womens_never_reads_as_mens(self):
        # "Women's" contains the letters m-e-n. The word boundary is what stops
        # it, and this is the assertion that keeps it there.
        for name in ("Women's Singles", "2026 Women’s US Open Winner", "WTA Finals"):
            assert detect_gender_axis(name) == "womens", name

    def test_a_plain_apostrophe_is_handled_too(self):
        assert detect_gender_axis("2026 Men's US Open Winner") == "mens"

    def test_the_season_is_still_segment_three_on_a_five_segment_key(self):
        # `routes/futures.py` reads the season out of the key by position. It
        # read `parts[-1]`, which was the season only while every key had four
        # segments; the sibling panel would have gone quietly empty here.
        assert _key(self.WOMENS).split(":")[3] == "2026"

    def test_the_first_four_segments_are_byte_identical_to_the_old_key(self):
        old = compute_canonical_market_key("tennis", None, "championship", "2026")
        assert _key(self.WOMENS).startswith(old + ":")


class TestTheReplayFoundThis:
    """Defects caught by replaying the axis over the live population, not by me."""

    def test_club_suffixes_do_not_weld_unrelated_english_fixtures(self):
        # A last-token rule (which is what made Kalshi's `Fritz` meet
        # Polymarket's `Taylor Fritz`) collapsed 238 live soccer fixtures onto
        # `vs-afc-fc`. That is #2622 rebuilt inside its own fix.
        a = _key("Tranmere Rovers FC vs. Oldham Athletic AFC", sport="soccer")
        b = _key("Barrow AFC vs. Sutton United FC", sport="soccer")
        c = _key("Southend United FC vs. Yeovil Town FC", sport="soccer")
        assert len({a, b, c}) == 3
        assert "vs-afc-fc" not in a

    def test_stripping_the_suffix_MAKES_a_cross_source_pair_that_did_not_exist(self):
        # Kalshi writes bare club names, Polymarket writes them with FC and a
        # stat rider. Same fixture, and now the same key — the pairing this
        # axis is supposed to enable, not the one it costs.
        kalshi = _key("Ipswich Town vs Liverpool", sport="soccer")
        poly = _key("Ipswich Town FC vs. Liverpool FC - Total Corners", sport="soccer")
        assert kalshi == poly
        assert kalshi.endswith(":vs-ipswich-liverpool")

    def test_a_stat_rider_is_a_view_of_one_fixture_not_a_second_fixture(self):
        assert _key("Cagliari Calcio vs. Hellas Verona FC - Halftime Result", sport="soccer") == \
            _key("Cagliari Calcio vs. Hellas Verona FC - First Team to Score", sport="soccer")

    def test_a_venue_prefix_is_stripped_and_a_stat_suffix_is_stripped(self):
        assert detect_matchup_axis("M15 Trelew: Tomas Martinez vs Felipe De Dios") == \
            "vs-felipe-de-dios-tomas-martinez"
        assert detect_matchup_axis("Nikola Bartunkova vs Elise Mertens: Set 1 Winner") == \
            "vs-elise-mertens-nikola-bartunkova"

    def test_reaching_a_round_is_not_winning_the_tournament(self):
        # Both are tennis/championship/2026/mens-us-open, and their OUTCOME sets
        # overlap, so no disjointness check downstream can separate them.
        winner = _key("2026 Men’s US Open Winner (Tennis)")
        reach = _key("US Open Men Singles: Quarterfinals Qualifiers")
        assert winner != reach
        assert reach.endswith(":mens-us-open-reach")

    def test_a_bare_final_is_still_the_outright_question(self):
        assert "reach" not in (market_discipline_axis("Wimbledon Final Winner") or "")

    def test_prose_containing_at_is_not_a_matchup(self):
        assert detect_matchup_axis("What will Trump say at Davos?") is None
        assert detect_matchup_axis("Will the Fed cut rates at the September meeting?") is None

    def test_three_sided_names_are_refused_rather_than_guessed(self):
        assert detect_matchup_axis("A vs B vs C") is None

    def test_the_itf_level_code_is_the_only_gender_token_those_rows_have(self):
        assert detect_gender_axis("M15 Trelew: Tomas Martinez vs Felipe De Dios") == "mens"
        assert detect_gender_axis("W15 Luján: Ambar Corbalan Miranda vs Fernanda Labrana") == "womens"


class TestTheAxisItself:
    def test_competition_slugs_cover_the_tennis_majors(self):
        assert detect_competition_axis("2026 Wimbledon Winner") == "wimbledon"
        assert detect_competition_axis("Roland Garros 2026") == "french-open"
        assert detect_competition_axis("2026 French Open Winner") == "french-open"
        assert detect_competition_axis("Australian Open 2026 Winner") == "australian-open"
        assert detect_competition_axis("2026 U.S. Open Winner") == "us-open"

    def test_the_sport_segment_already_separates_golf_from_tennis(self):
        # Both events are called "US Open". They cannot collide, because the
        # sport is segment 0 — which is why the slug is not sport-scoped.
        golf = _key("2026 U.S. Open Winner", sport="golf", league="PGA")
        tennis = _key("2026 Men’s US Open Winner (Tennis)")
        assert golf != tennis
        assert golf.startswith("golf:PGA:")

    def test_the_discipline_is_bounded(self):
        long_name = "Some Extremely Long Competitor Name vs Another Very Long One"
        assert len(market_discipline_axis(long_name)) <= _sym("MAX_DISCIPLINE_LEN")

    def test_a_key_stays_inside_its_column(self):
        # `FuturesMarket.canonical_market_key` is String(200).
        key = _key("A Really Long Womens Wimbledon Quarterfinals Qualifiers Market")
        assert len(key) <= 200

    def test_no_axis_means_no_fifth_segment(self):
        assert _key("Massachusetts Governor Election Winner", sport="politics",
                    league="US") == "politics:US:championship:2026"


class TestNothingElseMoved:
    """Controls. Green on master AND on this branch — that is the point."""

    def test_the_key_without_a_name_is_exactly_the_pre_2622_key(self):
        assert compute_canonical_market_key("basketball", "NBA", "championship", "2025-26") == \
            "basketball:NBA:championship:2025-26"
        assert compute_canonical_market_key("football", "NFL", "mvp", "2025") == \
            "football:NFL:mvp:2025"

    def test_the_refusals_are_unchanged(self):
        assert compute_canonical_market_key(None, "NBA", "championship", "2025-26") is None
        assert compute_canonical_market_key("basketball", "NBA", None, "2025-26") is None
        assert compute_canonical_market_key("politics", None, "championship", "2026") is None

    def test_a_name_can_never_create_a_key_where_there_was_none(self):
        # The discipline is a REFINEMENT. If the four required axes do not form
        # a key, no name may conjure one.
        assert compute_canonical_market_key(
            "politics", None, "championship", "2026",
            market_name="2026 Women’s US Open Winner",
        ) is None

    @pytest.mark.parametrize("name", ["", None, "   "])
    def test_an_empty_name_is_the_pre_2622_key(self, name):
        assert compute_canonical_market_key("hockey", "NHL", "championship", "2025-26",
                                            market_name=name) == \
            "hockey:NHL:championship:2025-26"

    def test_the_axis_is_deterministic(self):
        name = "2026 Women’s US Open Winner (Tennis)"
        assert market_discipline_axis(name) == market_discipline_axis(name)
