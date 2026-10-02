"""TYPING MILAN ALSO FINDS OLIMPIA MILANO AND ITS EUROLEAGUE GAMES. #1757.

Production 2026-10-02 03:3xZ, `/api/events/search`:

    milan    teams AC Milan · Inter Milan · Internazionale · AC Milan U20 · U23;
             13 games, every one football; 0 Olimpia Milano
    milano   teams Club Milano · Pallacanestro Olimpia Milano;
             Saski Baskonia vs Pallacanestro Olimpia Milano (Euroleague, Oct 2)

The games rail's whole-word test (LAT-P034) cannot fold `milan` onto `Milano`:
the English stemmer keeps `milano` whole, and a prefix rule is refused because
it re-admits `fed` -> Federico. So the Euroleague club gets a curated,
sport-scoped alias. `Milano` names exactly one basketball_euroleague club (team
row 967). Additive like `avs` (#9263): AC Milan holds `Milan` in its stored
names and Inter Milan in its own name, so both keep the word, and the tests
below pin that AC Milan still leads the card.
"""

from __future__ import annotations

from types import SimpleNamespace

from app.config.team_aliases import (
    CURATED_TEAM_ALIASES,
    _alias_claim_counts,
    team_nickname_event_expansions,
    team_nickname_search_expansions,
    team_nickname_team_rows,
)
from app.routes import events as ev
from app.routes.events import (
    _nickname_names_participant,
    _team_card_keyed,
    _team_nickname_event_admissions,
    _team_nickname_event_arms,
    _team_nickname_futures_arms,
    _team_nickname_team_arms,
)

KEY = ("basketball_euroleague", "Pallacanestro Olimpia Milano")


def _sql(clause) -> str:
    return str(clause.compile(compile_kwargs={"literal_binds": True}))


def _row(id_, name, sport_key, aliases):
    return SimpleNamespace(
        id=id_, name=name, slug=None, abbreviation=None, logo_url_small=None,
        current_record=None, sport_key=sport_key, alternate_names=aliases,
        team_rank=0.0, standings_updated_at=None,
    )


# The `milan` window on production 2026-10-02 (stored names as read), plus the
# Euroleague row the curated arm now recalls.
WINDOW = [
    _row(2052, "AC Milan", "soccer_italy_serie_a", ["Milan"]),
    _row(2055, "Inter Milan", "soccer_italy_serie_a", ["Internazionale"]),
    _row(2295, "Inter Milan", "soccer_uefa_champs_league", ["Internazionale"]),
    _row(4990, "AC Milan U20", "soccer_other", None),
    _row(5219, "AC Milan U23", "soccer_other", None),
    _row(18901, "AC Milan", "soccer_uefa_europa_league", None),
    _row(967, "Pallacanestro Olimpia Milano", "basketball_euroleague", None),
]


def _card_names(rows, q) -> list[str]:
    return [card["name"] for _key, card in _team_card_keyed(rows, q)]


def test_milan_is_curated_for_olimpia_with_one_claimant() -> None:
    assert CURATED_TEAM_ALIASES[KEY] == ["milan"]
    assert _alias_claim_counts()["milan"] == 1


def test_the_teams_card_arm_names_exactly_that_row() -> None:
    assert team_nickname_team_rows()["milan"] == KEY
    arms = _team_nickname_team_arms(["milan"])
    assert len(arms) == 1
    sql = _sql(arms[0])
    assert "'basketball_euroleague'" in sql and "'Pallacanestro Olimpia Milano'" in sql


def test_ac_and_inter_qualify_the_word_so_the_arm_stays_off() -> None:
    """`ac milan` / `inter milan` name a football club; the word before `milan`
    is not Olimpia's, so `_nickname_is_qualified` keeps the basketball row out."""
    assert _team_nickname_team_arms(["ac", "milan"]) == []
    assert _team_nickname_team_arms(["inter", "milan"]) == []
    # The games arm keeps the surrounding word (`ac Milano`), so it names no
    # Euroleague game either.
    for words in (["ac", "milan"], ["inter", "milan"]):
        assert not _nickname_names_participant(
            _team_nickname_event_admissions(words),
            "basketball_euroleague",
            ["Saski Baskonia", "Pallacanestro Olimpia Milano"],
        ), words


def test_the_games_arm_is_milano_scoped_to_the_euroleague() -> None:
    assert team_nickname_event_expansions()["milan"] == ("Milano", "basketball_euroleague")
    arms = _team_nickname_event_arms(["milan"])
    assert len(arms) == 1
    sql = _sql(arms[0])
    assert "milano" in sql.lower() and "basketball_euroleague" in sql


def test_no_futures_arm_because_milan_is_spelled_inside_milano() -> None:
    """The futures rail is a plain ILIKE, so `%milan%` already reaches `Milano`."""
    assert "milan" not in team_nickname_search_expansions()
    assert _team_nickname_futures_arms(["milan"]) == []


def test_milan_names_olimpias_games_under_both_spellings() -> None:
    admissions = _team_nickname_event_admissions(["milan"])
    # Both spellings the Euroleague rows carry on production 2026-10-02.
    assert _nickname_names_participant(
        admissions, "basketball_euroleague", ["Saski Baskonia", "Pallacanestro Olimpia Milano"]
    )
    assert _nickname_names_participant(
        admissions, "basketball_euroleague", ["Olimpia Milano", "Virtus Bologna"]
    )


def test_milan_does_not_name_a_football_row_through_the_basketball_scope() -> None:
    admissions = _team_nickname_event_admissions(["milan"])
    assert not _nickname_names_participant(
        admissions, "soccer_other", ["FC Internazionale Milano", "Parma Calcio 1913"]
    )
    assert not _nickname_names_participant(
        admissions, "soccer_other", ["Alcione Milano", "Union Brescia"]
    )


def test_milan_keeps_ac_milan_first_and_cards_olimpia_ahead_of_the_youth_sides() -> None:
    names = _card_names(WINDOW, "milan")
    assert names[0] == "AC Milan", names
    assert "Inter Milan" in names, names
    assert names.index("Pallacanestro Olimpia Milano") < names.index("AC Milan U20"), names


def test_without_the_curated_evidence_olimpia_falls_behind_the_youth_sides(monkeypatch) -> None:
    """The control: strip the injected alias and the same window ranks Olimpia
    last — so the test above measures the map entry, not the fixture. (On
    production it is not even recalled: full text `milan` never matches the
    lexeme `milano`, which is what the card arm's (sport, name) key adds.)"""
    monkeypatch.setattr(ev, "curated_team_aliases", lambda *_: ())
    names = _card_names(WINDOW, "milan")
    assert names.index("Pallacanestro Olimpia Milano") > names.index("AC Milan U20"), names


def test_the_literal_names_still_lead_with_their_own_row() -> None:
    assert _card_names(WINDOW, "milano")[0] == "Pallacanestro Olimpia Milano"
    assert _card_names(WINDOW, "olimpia milano")[0] == "Pallacanestro Olimpia Milano"
    assert _card_names(WINDOW, "inter milan")[0] == "Inter Milan"
    assert _card_names(WINDOW, "ac milan")[0] == "AC Milan"
