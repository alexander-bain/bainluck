"""The class on every `contains` edge. #2927 Phase 3, spec §4.

The classifier decides which SECTION a hub member appears in. It is pure, so it
is gradeable by a table of real examples — which is what this file is. The
strings below are taken from the US Open register
(`backend/data/tournament_registers/us-open-2026.json`), from Kalshi's eight
attached US Open props, and from the name shapes ARTIFACT-M-20260903-I
measured, rather than invented to fit the patterns.

TWO FAILURE MODES ARE GUARDED, NOT ONE. It is easy to write a classifier that
never returns `unclassified` — it just guesses — and easy to write one that
returns it constantly. Both are tested: every named class has a positive case,
`unclassified` has its own positive cases, and the doubles rules have negative
cases proving a singles member does NOT reach them.
"""

import pytest

from app.utils.container_class import MemberEvidence, classify_member, is_valid_class
from app.utils.container_graph import CLASS_UNCLASSIFIED, EDGE_CLASSES


def ev(**kwargs) -> MemberEvidence:
    kwargs.setdefault("node_type", "market")
    return MemberEvidence(**kwargs)


class TestItAlwaysReturnsARealClass:
    """The contract the DB CHECK relies on: never None, never a raise."""

    @pytest.mark.parametrize(
        "evidence",
        [
            ev(),
            ev(name=""),
            ev(name=None),
            ev(name="   "),
            ev(name="⚽️🎾"),
            ev(name="x" * 5000),
            ev(node_type="container", name=None),
            ev(register_kind="a-kind-nobody-defined"),
            ev(draw="a-draw-nobody-defined"),
            ev(market_shape="not-a-shape"),
        ],
    )
    def test_every_input_yields_a_class_in_the_vocabulary(self, evidence):
        result = classify_member(evidence)
        assert result in EDGE_CLASSES
        assert is_valid_class(result)

    def test_nothing_recognisable_is_unclassified_not_a_guess(self):
        """`unclassified` is the honest answer and is a real section.

        The tempting alternative — defaulting to `match_winner` because most
        members are fixtures — files every unknown under the wrong heading,
        where nobody looking at it can tell it was a guess.
        """
        assert classify_member(ev(name="Honey Deuce Sales")) == CLASS_UNCLASSIFIED


class TestDoublesOutranksEverything:
    """Doubles is a property of what the member IS, not of how it is worded."""

    def test_two_participants_on_a_side_is_doubles(self):
        """The structural signal, and the only one that cannot be wrong.

        This is why doubles waited on `event_participants` rather than on an
        ingest patch: before that table, this test was unstatable.
        """
        assert (
            classify_member(ev(node_type="event", max_side_size=2)) == "doubles"
        )

    def test_it_beats_the_fixture_pattern(self):
        """"Bopanna/Ebden vs Arevalo/Pavic" matches `X vs Y` too.

        If the fixture branch ran first, every doubles match would be filed as
        an ordinary `match_winner` — in a singles section, which is the exact
        wrong answer that looks like a right one.
        """
        assert (
            classify_member(
                ev(
                    node_type="event",
                    name="Bopanna/Ebden vs Arevalo/Pavic",
                    max_side_size=2,
                )
            )
            == "doubles"
        )

    @pytest.mark.parametrize(
        "draw", ["mens-doubles", "womens-doubles", "mixed-doubles"]
    )
    def test_the_authoritys_own_draw_slug_is_doubles(self, draw):
        assert classify_member(ev(node_type="event", draw=draw)) == "doubles"

    @pytest.mark.parametrize("draw", ["mens-singles", "womens-singles"])
    def test_a_singles_draw_is_not_doubles(self, draw):
        """The negative half, and the reason the slug set is matched WHOLE.

        `"doubles" in draw` is the sloppy version. It is right on these two
        only by luck — one slug like `mens-singles-doubles-qualifying` and it
        files a singles member under doubles forever.
        """
        assert classify_member(ev(node_type="event", draw=draw)) != "doubles"

    def test_two_slash_joined_pairs_in_a_name_is_doubles(self):
        """The name fallback — last, and only when structure said nothing.

        ARTIFACT-M-20260903-I measured 79 slash-teams that "never match 2-name
        rows".
        """
        assert (
            classify_member(ev(node_type="event", name="Bopanna/Ebden vs Arevalo/Pavic"))
            == "doubles"
        )

    def test_a_single_slash_is_not_a_doubles_pair(self):
        """One slash is not two pairs.

        A market named "Sinner vs Alcaraz W/L" has a slash and is singles.
        """
        assert (
            classify_member(ev(node_type="event", name="Sinner vs Alcaraz W/L"))
            != "doubles"
        )

    def test_a_singles_fixture_with_hyphenated_names_is_not_doubles(self):
        """Real name shapes from artifact I, none of them doubles."""
        for name in (
            "Bu Yunchaokete vs Coleman Wong",
            "B. Van De Zandschulp vs A. Davidovich Fokina",
            "Jean-Julien Rojer vs Marcelo Melo",
        ):
            assert classify_member(ev(node_type="event", name=name)) != "doubles", name

    def test_structure_wins_over_a_singles_looking_name(self):
        """Ordering constraint from spec §6: keys on structure, not names.

        A doubles fixture whose stored name lost its partners still classes as
        doubles when the participants say two-a-side.
        """
        assert (
            classify_member(
                ev(node_type="event", name="Bopanna vs Arevalo", max_side_size=2)
            )
            == "doubles"
        )


class TestTheRegistersOwnKindIsPassedThrough:
    """The register already parsed its rows; re-deriving loses a kind."""

    @pytest.mark.parametrize(
        "register_kind,expected",
        [
            ("matchup", "match_winner"),
            ("reach", "advancement"),
            ("prop", "side_question"),
        ],
    )
    def test_each_register_kind_maps(self, register_kind, expected):
        assert classify_member(ev(register_kind=register_kind)) == expected

    def test_an_unknown_register_kind_falls_through_rather_than_failing(self):
        """A register that grows a fifth list must not crash assembly.

        It falls through to the naming tests, and to `unclassified` if those
        say nothing — the member stays visible either way.
        """
        assert (
            classify_member(ev(register_kind="broadcast", name="ESPN2 coverage"))
            == CLASS_UNCLASSIFIED
        )

    def test_the_register_kind_does_not_beat_doubles(self):
        """A doubles matchup is `doubles`, not `match_winner`.

        The register pins singles today, but M4 makes it one edge source among
        several and nothing stops a future register carrying a doubles draw.
        """
        assert (
            classify_member(
                ev(node_type="event", register_kind="matchup", draw="mens-doubles")
            )
            == "doubles"
        )


class TestTheNamedClasses:
    """One positive case per class, from real strings."""

    @pytest.mark.parametrize(
        "name",
        [
            "Will Sinner actually play?",
            "Will Djokovic withdraw before the quarterfinals?",
            "Will Osaka compete in the US Open?",
        ],
    )
    def test_side_questions(self, name):
        assert classify_member(ev(name=name)) == "side_question"

    @pytest.mark.parametrize(
        "name",
        [
            "Exact Match Score: Sinner vs Alcaraz",
            "Total Games: Swiatek vs Zheng",
            "Game Spread: Alcaraz vs Fritz",
            "Set 1 Winner: Sinner vs Shelton",
        ],
    )
    def test_kalshis_eight_attached_props(self, name):
        """All four families of Kalshi's 8 US Open props.

        Each one also contains "X vs Y", so this is simultaneously the test
        that the prop branch runs BEFORE the fixture branch.
        """
        assert classify_member(ev(name=name)) == "prop"

    @pytest.mark.parametrize(
        "name",
        [
            "Winner of the US Open 2026",
            "Carlos Alcaraz to win the US Open",
            "US Open Men's Singles Champion",
        ],
    )
    def test_titles(self, name):
        assert classify_member(ev(name=name)) == "title"

    @pytest.mark.parametrize(
        "name",
        [
            "Will Alejandro Tabilo reach the R16?",
            "Coco Gauff to reach the semifinals",
            "Will Fritz advance to the quarterfinals?",
        ],
    )
    def test_advancement_ladders(self, name):
        assert classify_member(ev(name=name)) == "advancement"

    def test_a_title_is_not_read_as_an_advancement(self):
        """Both are ladder-shaped; only one is an outright.

        "to win the final" and "to reach the final" differ by one verb, and if
        advancement ran first the whole `title` section would be empty.
        """
        assert classify_member(ev(name="Alcaraz to win the final")) == "title"
        assert classify_member(ev(name="Alcaraz to reach the final")) == "advancement"

    @pytest.mark.parametrize(
        "name",
        [
            "Sinner vs Alcaraz",
            "Swiatek v Zheng",
            "Iga Swiatek vs. Qinwen Zheng",
        ],
    )
    def test_fixtures(self, name):
        assert classify_member(ev(node_type="event", name=name)) == "match_winner"

    def test_an_event_with_one_entity_a_side_is_a_fixture_without_a_vs(self):
        """A card titled "Sinner — Alcaraz" is still one fixture's winner."""
        assert (
            classify_member(
                ev(node_type="event", name="Sinner — Alcaraz", max_side_size=1)
            )
            == "match_winner"
        )

    def test_every_named_class_is_reachable(self):
        """No class is dead code.

        A class in the vocabulary that nothing can ever return is a section the
        hub will always draw empty — and nobody would notice.
        """
        produced = {
            classify_member(ev(node_type="event", max_side_size=2)),
            classify_member(ev(register_kind="matchup")),
            classify_member(ev(register_kind="reach")),
            classify_member(ev(register_kind="prop")),
            classify_member(ev(name="Total Games: Swiatek vs Zheng")),
            classify_member(ev(name="Winner of the US Open 2026")),
            classify_member(ev(name="Honey Deuce Sales")),
        }
        assert produced == EDGE_CLASSES


class TestOrderingIsNotAccidental:
    """Each of these pairs would collapse if two branches swapped."""

    def test_a_prop_naming_two_players_is_a_prop_not_a_fixture(self):
        assert (
            classify_member(ev(name="Total Games: Sinner vs Alcaraz")) == "prop"
        )

    def test_a_side_question_naming_a_round_is_not_an_advancement(self):
        assert (
            classify_member(ev(name="Will Djokovic withdraw before the quarterfinals?"))
            == "side_question"
        )

    def test_a_doubles_prop_is_doubles(self):
        """Doubles is first for a reason: the section is the draw, not the
        market's stat line."""
        assert (
            classify_member(
                ev(name="Total Games: Bopanna/Ebden vs Arevalo/Pavic", draw="mens-doubles")
            )
            == "doubles"
        )


class TestItStaysPure:
    """No DB, no clock, no network — so it is gradeable by a table."""

    def test_the_same_input_gives_the_same_answer(self):
        evidence = ev(name="Sinner vs Alcaraz", node_type="event")
        assert len({classify_member(evidence) for _ in range(20)}) == 1

    def test_the_module_imports_nothing_heavy(self):
        import ast
        import pathlib

        from app.utils import container_class

        tree = ast.parse(pathlib.Path(container_class.__file__).read_text())
        imported = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                imported.update(a.name for a in node.names)
            elif isinstance(node, ast.ImportFrom):
                imported.add(node.module or "")
        for module in imported:
            assert not module.startswith("app.services"), module
            assert not module.startswith("app.tasks"), module
            assert not module.startswith("app.routes"), module
            assert "sqlalchemy" not in module, module
