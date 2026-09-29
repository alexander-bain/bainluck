"""#9609 — `_is_finished_club_word`, the pure half of the finished-club-word arm.

The route wiring and the SQL are proven against real Postgres in
`tests/integration/test_search_finished_club_word_outcome_arm_pg_9609.py`; this
file pins the rule's boundaries without a database.
"""

from types import SimpleNamespace

from app.routes.events import _is_finished_club_word


def _row(name, sport_key="baseball_mlb"):
    return SimpleNamespace(name=name, sport_key=sport_key)


def test_a_whole_club_word_is_finished():
    assert _is_finished_club_word("rays", [_row("Tampa Bay Rays"), _row("Rayo Vallecano", "soccer_spain_la_liga")])
    assert _is_finished_club_word("METS", [_row("New York Mets")])


def test_a_club_word_the_term_only_starts_means_the_reader_may_still_be_typing():
    assert not _is_finished_club_word(
        "heat", [_row("Miami Heat", "basketball_nba"), _row("Flackwell Heath FC", "soccer_fa_cup")]
    )
    # ...whichever order the teams read returned them in.
    assert not _is_finished_club_word(
        "red", [_row("California Redwoods", "lacrosse_pll"), _row("Boston Red Sox")]
    )
    assert not _is_finished_club_word(
        "red", [_row("Boston Red Sox"), _row("California Redwoods", "lacrosse_pll")]
    )


def test_a_partial_word_is_not_finished():
    assert not _is_finished_club_word("yank", [_row("New York Yankees")])


def test_a_mid_word_hit_is_not_a_club_word():
    assert not _is_finished_club_word("hawks", [_row("Seattle Seahawks", "americanfootball_nfl")])


def test_an_individual_sport_row_is_not_a_club():
    assert not _is_finished_club_word("ray", [_row("Ray Stevens", "tennis_atp_us_open")])
    # ...nor can it veto one.
    assert _is_finished_club_word(
        "rays", [_row("Tampa Bay Rays"), _row("Rayshawn Jenkins", "mma_mixed_martial_arts")]
    )


def test_a_row_with_no_sport_is_ignored():
    assert not _is_finished_club_word("rays", [_row("Tampa Bay Rays", None)])


def test_no_team_rows_changes_nothing():
    assert not _is_finished_club_word("rays", [])
    assert not _is_finished_club_word("rays", None)
