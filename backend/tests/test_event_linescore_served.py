"""live/073 — the games line reaches the match page, and only where it exists.

`_format_event` feeds the event detail response the match page reads.  The line
the tennis authority stores in `box_score_data["tennis"]` is served from here in
OUR home/away order, PRESENT-ONLY: a `"linescore": null` on every row of every
list this formatter feeds would be bytes on the wire for the ~99.9% of events
that will never have one.

The absence arms outnumber the presence arm on purpose.  The thing that would
make this a regression rather than a ship is a key appearing on an NFL card, or
an empty one appearing on a tennis match nobody has played yet.
"""

from datetime import datetime, timezone

import pytest

from app.models import Event, Sport
from app.routes.events import _format_event


def _event(**kwargs):
    sport = Sport(id=1, key=kwargs.pop("sport_key", "tennis_atp_us_open"), name="ATP")
    return Event(
        id=15301243,
        sport_id=1,
        sport=sport,
        home_team_name="Wu Yibing",
        away_team_name="Carlos Alcaraz",
        commence_time=datetime(2026, 9, 4, 18, 16, tzinfo=timezone.utc),
        status="completed",
        home_score=0,
        away_score=3,
        **kwargs,
    )


#: What `games_line_write` stores for event 15301243 — Alcaraz d. Wu 6-3, 6-4,
#: 6-1, in our order, which has Wu home.
WU_ALCARAZ_LINE = {
    "sets": [[3, 6], [4, 6], [1, 6]],
    "home_games": 8,
    "away_games": 18,
    "source": "espn",
}


def test_the_settled_match_serves_its_line():
    data = _format_event(_event(box_score_data={"tennis": WU_ALCARAZ_LINE}))

    assert data["linescore"]["sets"] == [[3, 6], [4, 6], [1, 6]]
    assert data["linescore"]["home_games"] == 8
    assert data["linescore"]["away_games"] == 18


def test_the_line_is_in_the_same_order_as_the_score_beside_it():
    """`home_score` 0 / `away_score` 3 and a line whose HOME side lost every
    set.  A response carrying the two in different orders is worse than one
    carrying neither."""
    data = _format_event(_event(box_score_data={"tennis": WU_ALCARAZ_LINE}))

    assert data["home_score"] == 0 and data["away_score"] == 3
    assert sum(s[0] for s in data["linescore"]["sets"]) == data["linescore"]["home_games"]
    assert data["linescore"]["home_games"] < data["linescore"]["away_games"]


def test_an_event_with_no_box_score_carries_no_key_at_all():
    assert "linescore" not in _format_event(_event(box_score_data=None))


def test_a_box_score_with_no_tennis_key_carries_no_key_at_all():
    """Every football and baseball row with a box score goes through here."""
    data = _format_event(_event(
        sport_key="americanfootball_nfl",
        box_score_data={"players": {"home": []}, "scoring_plays": [{"period": 1}]},
    ))

    assert "linescore" not in data


@pytest.mark.parametrize("stored", [
    {},
    {"sets": []},
    {"home_games": 8, "away_games": 18},
    None,
    "6-3, 6-4, 6-1",
    [[3, 6]],
])
def test_a_line_with_no_sets_in_it_is_not_served(stored):
    """An empty line is an absence, and an absence is served as one.  A
    `linescore` key holding `{"sets": []}` would make the page render a strip
    with nothing in it — the empty-card class ruling 2215 exists about."""
    assert "linescore" not in _format_event(_event(box_score_data={"tennis": stored}))


def test_the_response_holds_a_copy_and_not_the_row():
    """The formatter must not hand a caller the ORM instance's own dict: a
    mutation downstream would be an unflushed write to `box_score_data`
    (gotcha #4) that only shows up as a page telling a different story from the
    database."""
    stored = {"tennis": dict(WU_ALCARAZ_LINE)}
    event = _event(box_score_data=stored)

    data = _format_event(event)
    data["linescore"]["sets"].append([9, 9])

    assert stored["tennis"]["sets"] == [[3, 6], [4, 6], [1, 6]]
