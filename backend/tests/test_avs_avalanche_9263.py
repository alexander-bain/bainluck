"""TYPING AVS CARDS THE COLORADO AVALANCHE FIRST, AND AVS FUTEBOL STAYS. #9263.

Production 2026-09-30 ~10:20Z, `/api/events/search`:

    avs        teams AVS Futebol SAD; futures 1 (Taça de Portugal Champion)
    avalanche  teams Colorado Avalanche; futures 9 (Stanley Cup, COL Total Points, ...)

The games list already led with Avalanche games (the event rail reaches them by
prefix); the TEAMS card and the markets list never did.

Measured before adding: all 37 open `hockey` futures markets naming `Avalanche`
are Colorado's (the 30 without "Colorado" in the title pair it with an NHL club),
and `Avalanche` names exactly one icehockey_nhl club over 120 days of events.

`avs` had been refused under the two-franchise rule (#8685). That rule protects a
club that would LOSE the word; AVS Futebol cannot, because `avs` is its name. The
tests below pin both halves: the Avalanche leads, and AVS Futebol is still carded.
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
    _team_nickname_team_order,
)

KEY = ("icehockey_nhl", "Colorado Avalanche")


def _sql(clause) -> str:
    return str(clause.compile(compile_kwargs={"literal_binds": True}))


def _row(id_, name, sport_key, aliases):
    return SimpleNamespace(
        id=id_, name=name, slug=None, abbreviation=None, logo_url_small=None,
        current_record=None, sport_key=sport_key, alternate_names=aliases,
        team_rank=0.0, standings_updated_at=None,
    )


# The `avs` window on production 2026-09-30: AVS Futebol, found by full text on its
# own name, and the NHL row the curated arm recalls (its stored names as read).
WINDOW = [
    _row(2167, "AVS Futebol SAD", "soccer_portugal_primeira_liga", None),
    _row(119, "Colorado Avalanche", "icehockey_nhl", ["Colorado", "Avalanche", "Colorado Avalanche"]),
]


def _card_names(rows, q) -> list[str]:
    return [card["name"] for _key, card in _team_card_keyed(rows, q)]


def test_avs_is_curated_for_the_avalanche_with_one_claimant() -> None:
    assert CURATED_TEAM_ALIASES[KEY] == ["avs"]
    assert _alias_claim_counts()["avs"] == 1


def test_the_teams_card_arm_names_exactly_that_row() -> None:
    assert team_nickname_team_rows()["avs"] == KEY
    arms = _team_nickname_team_arms(["avs"])
    assert len(arms) == 1
    sql = _sql(arms[0])
    assert "'icehockey_nhl'" in sql and "'Colorado Avalanche'" in sql
    assert _team_nickname_team_order(arms), "the named row must be ordered into the window"


def test_the_markets_arm_is_avalanche_scoped_to_hockey() -> None:
    assert team_nickname_search_expansions()["avs"] == ("Avalanche", "hockey")
    arms = _team_nickname_futures_arms(["avs"])
    assert len(arms) == 1
    sql = _sql(arms[0]).lower()
    assert "avalanche" in sql and "'hockey'" in sql


def test_the_games_arm_is_avalanche_scoped_to_the_nhl() -> None:
    assert team_nickname_event_expansions()["avs"] == ("Avalanche", "icehockey_nhl")
    arms = _team_nickname_event_arms(["avs"])
    assert len(arms) == 1
    assert "icehockey_nhl" in _sql(arms[0])


def test_avs_names_the_avalanches_game_and_no_other_sports_avalanche() -> None:
    admissions = _team_nickname_event_admissions(["avs"])
    assert _nickname_names_participant(
        admissions, "icehockey_nhl", ["Colorado Avalanche", "Los Angeles Kings"]
    )
    # Bare "Avalanche" rows sit in icehockey_ahl / soccer_other on production;
    # the NHL scope keeps the alias off them.
    assert not _nickname_names_participant(admissions, "icehockey_ahl", ["Avalanche", "Rochester Americans"])


def test_avs_cards_the_avalanche_first_and_keeps_avs_futebol() -> None:
    names = _card_names(WINDOW, "avs")
    assert names[0] == "Colorado Avalanche", names
    assert "AVS Futebol SAD" in names, names


def test_without_the_curated_evidence_avs_futebol_would_lead(monkeypatch) -> None:
    """The control: strip the injected alias and the same window leads with AVS
    Futebol — so the test above measures the map entry, not the fixture."""
    monkeypatch.setattr(ev, "curated_team_aliases", lambda *_: ())
    assert _card_names(WINDOW, "avs")[0] == "AVS Futebol SAD"


def test_the_literal_club_names_still_lead_with_their_own_row() -> None:
    assert _card_names(WINDOW, "avs futebol")[0] == "AVS Futebol SAD"
    assert _card_names(WINDOW, "avalanche")[0] == "Colorado Avalanche"
