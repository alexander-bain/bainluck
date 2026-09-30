"""#9873: a name that ends in the initial "V" must keep it, and the second side
must not start with "vs".

Kalshi calls Tokyo Verdy "Tokyo V" and writes the doubles player V. Prashanth as
"Prashanth V". Both matchup patterns match case-insensitively and read their
first side lazily, so the split used to land on that initial:

    "Tokyo V vs Kobe"                            -> ("Tokyo", "vs Kobe")
    "Geerts / Prashanth V vs Donski / Pieczonka" -> ("Geerts / Prashanth", "vs Donski / Pieczonka")

and an unlinked Kalshi market minted a row with those names (production event
15321903, and 13 Tokyo Verdy home games since March).

The other direction matters just as much. #3026 refuses a question by reading the
lazy parse ("Announcers at Duke vs Virginia" -> "Announcers" / "Duke vs Virginia"),
and a club whose real name starts with "V" ("V Varen") must not lose that letter.
"""

import pytest

from app.utils.prediction_market_matching import (
    _fuzzy_team_match,
    extract_matchup,
    question_refusal_reason,
)


@pytest.mark.parametrize(
    "name, team_a, team_b, format_type",
    [
        # The production specimens.
        ("Tokyo V vs Kobe", "Tokyo V", "Kobe", "bare_matchup"),
        ("Tokyo V vs United Chiba", "Tokyo V", "United Chiba", "bare_matchup"),
        (
            "Geerts / Prashanth V vs Donski / Pieczonka",
            "Geerts / Prashanth V", "Donski / Pieczonka", "bare_matchup",
        ),
        # The derby, both ways round.
        ("Tokyo V vs Tokyo", "Tokyo V", "Tokyo", "bare_matchup"),
        ("Tokyo vs Tokyo V", "Tokyo", "Tokyo V", "bare_matchup"),
        # The other strong separators, and the dotted forms.
        ("Tokyo V at Kobe", "Tokyo V", "Kobe", "bare_matchup"),
        ("Cioclea Igor V vs. Uzun Ilia", "Cioclea Igor V", "Uzun Ilia", "bare_matchup"),
        # A game prop goes through the other pattern, which had the same split.
        ("Tokyo V vs Kobe: Total Goals", "Tokyo V", "Kobe", "game_prop"),
    ],
)
def test_the_initial_v_stays_on_the_first_name(name, team_a, team_b, format_type):
    m = extract_matchup(name)
    assert m is not None
    assert (m.team_a, m.team_b, m.format_type) == (team_a, team_b, format_type)
    assert m.yes_team == team_a
    assert not m.team_b.lower().startswith(("vs ", "vs. ", "v ", "at ", "@ "))


@pytest.mark.parametrize(
    "name, team_a, team_b",
    [
        # A real name that starts with "V" after a strong split keeps its letter.
        ("Tokyo vs V Varen", "Tokyo", "V Varen"),
        ("Tokyo V vs V Varen", "Tokyo V", "V Varen"),
        # A plain weak split is unchanged.
        ("Arsenal v Chelsea", "Arsenal", "Chelsea"),
        ("Liverpool v. Everton", "Liverpool", "Everton"),
        ("Urawa vs Tokyo V", "Urawa", "Tokyo V"),
        # #3026's embedded matchup reads exactly as master reads it: its second
        # side carries a separator INSIDE it, never at its start.
        ("Announcers at Duke vs Virginia", "Announcers", "Duke vs Virginia"),
        ("University at Albany vs Buffalo", "University", "Albany vs Buffalo"),
    ],
)
def test_parses_the_fix_must_not_move(name, team_a, team_b):
    m = extract_matchup(name)
    assert m is not None
    assert (m.team_a, m.team_b) == (team_a, team_b)


def test_3026_still_refuses_the_embedded_matchup_at_the_mint():
    m = extract_matchup("Announcers at Duke vs Virginia")
    assert question_refusal_reason(m.team_a, m.team_b) is not None


def test_the_restored_name_binds_tokyo_verdy_and_not_fc_tokyo():
    """What the fix buys at link time: the bare "Tokyo" bound either club."""
    m = extract_matchup("Tokyo V vs Kobe")
    assert _fuzzy_team_match(m.team_a, "Tokyo Verdy")
    assert not _fuzzy_team_match(m.team_a, "FC Tokyo")
    assert _fuzzy_team_match(m.team_b, "Vissel Kobe")
    # The strawman: master's parse binds FC Tokyo too.
    assert _fuzzy_team_match("Tokyo", "FC Tokyo")
