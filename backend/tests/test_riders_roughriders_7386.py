"""TYPING RIDERS FINDS THE SASKATCHEWAN ROUGHRIDERS. #7386.

A nickname spelled INSIDE a longer token of the official name (Rough*riders*)
cannot be separated from noise by a WHERE clause — `nets` inside "Hornets" is the
same construction (#7381) — so the fix is a curated alias, not a looser predicate.

Production 2026-09-30 ~11:50Z, `/api/events/search`:

    riders       teams Kolkata Knight Riders, Trinbago Knight Riders, Rider Broncs; 0 games
    roughriders  teams Saskatchewan Roughriders; games led by Stampeders @ Roughriders (Oct 3)

`Roughriders` names exactly one americanfootball_cfl club over 120 days of
events. The Knight Riders and the RailRiders keep the word — it is in their own
names — and the arm is CFL-scoped, so it cannot reach them.
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

KEY = ("americanfootball_cfl", "Saskatchewan Roughriders")


def _sql(clause) -> str:
    return str(clause.compile(compile_kwargs={"literal_binds": True}))


def _row(id_, name, sport_key, aliases):
    return SimpleNamespace(
        id=id_, name=name, slug=None, abbreviation=None, logo_url_small=None,
        current_record=None, sport_key=sport_key, alternate_names=aliases,
        team_rank=0.0, standings_updated_at=None,
    )


# The `riders` window on production 2026-09-30: the three rows full text finds
# today, plus the CFL row the curated arm recalls (stored names as read).
WINDOW = [
    _row(9385, "Kolkata Knight Riders", "cricket_ipl", None),
    _row(17638, "Trinbago Knight Riders", "cricket_caribbean_premier_league", None),
    _row(2652, "Rider Broncs", "basketball_ncaab", None),
    _row(15495, "Saskatchewan Roughriders", "americanfootball_cfl", None),
]


def _card_names(rows, q) -> list[str]:
    return [card["name"] for _key, card in _team_card_keyed(rows, q)]


def test_riders_is_curated_for_the_roughriders_with_one_claimant() -> None:
    assert CURATED_TEAM_ALIASES[KEY] == ["riders"]
    assert _alias_claim_counts()["riders"] == 1


def test_the_refused_glued_nicknames_stay_out_of_the_map() -> None:
    """`9ers`, `blue jays`, `oil` each already answer another club (San Francisco,
    Toronto, Edmonton). `9ers` must keep exactly one claimant, or it goes
    contested and the 49ers lose their game arm."""
    assert _alias_claim_counts()["9ers"] == 1
    for refused in ("blue jays", "oil"):
        assert refused not in _alias_claim_counts()
    assert team_nickname_event_expansions()["9ers"] == ("49ers", "americanfootball_nfl")


def test_the_teams_card_arm_names_exactly_that_row() -> None:
    assert team_nickname_team_rows()["riders"] == KEY
    arms = _team_nickname_team_arms(["riders"])
    assert len(arms) == 1
    sql = _sql(arms[0])
    assert "'americanfootball_cfl'" in sql and "'Saskatchewan Roughriders'" in sql
    assert _team_nickname_team_order(arms), "the named row must be ordered into the window"


def test_the_games_arm_is_roughriders_scoped_to_the_cfl() -> None:
    assert team_nickname_event_expansions()["riders"] == ("Roughriders", "americanfootball_cfl")
    arms = _team_nickname_event_arms(["riders"])
    assert len(arms) == 1
    sql = _sql(arms[0])
    assert "americanfootball_cfl" in sql and "Roughriders" in sql


def test_there_is_no_futures_arm_because_riders_is_inside_its_token() -> None:
    assert "riders" not in team_nickname_search_expansions()
    assert _team_nickname_futures_arms(["riders"]) == []


def test_riders_names_the_roughriders_game_and_no_cricket_side() -> None:
    admissions = _team_nickname_event_admissions(["riders"])
    assert _nickname_names_participant(
        admissions, "americanfootball_cfl", ["Saskatchewan Roughriders", "Calgary Stampeders"]
    )
    assert not _nickname_names_participant(
        admissions, "cricket_ipl", ["Kolkata Knight Riders", "Mumbai Indians"]
    )


def test_riders_cards_the_roughriders_and_keeps_the_knight_riders() -> None:
    names = _card_names(WINDOW, "riders")
    assert names[0] == "Saskatchewan Roughriders", names
    assert "Kolkata Knight Riders" in names and "Trinbago Knight Riders" in names, names


def test_without_the_curated_evidence_a_knight_riders_row_would_lead(monkeypatch) -> None:
    """The control: strip the injected alias and the same window does not lead with
    the Roughriders — so the test above measures the map entry, not the fixture."""
    monkeypatch.setattr(ev, "curated_team_aliases", lambda *_: ())
    assert _card_names(WINDOW, "riders")[0] != "Saskatchewan Roughriders"


def test_the_literal_names_still_lead_with_their_own_row() -> None:
    assert _card_names(WINDOW, "roughriders")[0] == "Saskatchewan Roughriders"
    assert _card_names(WINDOW, "knight riders")[0] in (
        "Kolkata Knight Riders", "Trinbago Knight Riders",
    )
