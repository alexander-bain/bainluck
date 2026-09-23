"""#8070 — a served payload never carries two different records for one team.

`_format_team_data` served the team's season twice, from two columns, and never
compared them:

    record     <- teams.current_record        (stamped when a game completes)
    standings  <- public_standings(...)       (the once-daily StatPal board,
                                               whose wins/losses every client
                                               composes into a record itself)

Measured on production `/api/feed?limit=120`, `cache.status: miss`,
2026-09-22 19:44Z. Two of the eight MLB teams on the page contradicted
themselves, and the two were the two sides of ONE game — Baltimore had beaten
Toronto, `current_record` knew it and the board did not:

    BAL   record 76-81   standings 75-81      (one more WIN in `record`)
    TOR   record 77-80   standings 77-79      (one more LOSS in `record`)
    PHI   record 86-70   standings 86-70      \\
    MIL   record 98-58   standings 98-58       |  the six that agreed, and the
    BOS   record 84-72   standings 84-72       |  control on the sizing: the
    CLE   record 81-75   standings 81-75       |  skew fires on exactly the
    LAD   record 96-60   standings 96-60       |  teams whose last game just
    SD    record 87-69   standings 87-69      /   completed.

A reader sees both: the event-page hero prints `record`, and the team card one
scroll down composes `${standings.wins}-${standings.losses}`. Neither is
labelled as coming from a different rail.

WHAT THESE GUARDS PIN, AND WHY THEY ARE SHAPED THIS WAY

The acceptance asks for a guard that fails on the DISAGREEMENT, not on the
specimen — so the load-bearing test is `test_no_served_payload_carries_two
_records`, a sweep of the invariant over every row in `ROWS`, and BAL and TOR
are two rows in that table rather than the subject of their own assertions. A
new league, a new draw spelling or a new stale direction is caught by adding a
row, not by writing a test.

A sweep like that is worthless if nothing in the table exercises the repair —
an implementation that returned the blob untouched would pass an all-agreeing
table happily. `test_the_sweep_is_not_vacuous` is the control: it asserts the
table actually contains rows the alignment MOVED, and that it contains rows it
LEFT ALONE, so the invariant can distinguish a fix from a no-op.

Every case that asserts the fresh column wins has a sibling asserting it does
not, for the reason #5520's suite gives: a guard that only ever asserted
"prefer `current_record`" would pass against a change that ignored the board
entirely, which blanks the record on rows that have no `current_record` and on
the NHL rollover and NBA post-season rows where `current_record` is the stale
half. Those two directions are `NHL_ROLLOVER` and `NBA_FINISHED` below.
"""

from copy import deepcopy
from types import SimpleNamespace

import pytest

from app.routes.events import _format_team_data
from app.utils.standings_shape import reconciled_record_and_standings


def _team(current_record, standings, **overrides):
    """A row carrying only what `_format_team_data` reads."""
    fields = {
        "id": 4242,
        "slug": "some-team",
        "primary_color": "#111111",
        "secondary_color": "#222222",
        "logo_url_small": None,
        "logo_url_large": None,
        "abbreviation": "XYZ",
        "current_record": current_record,
        "standings_data": standings,
        "season_stats": None,
    }
    fields.update(overrides)
    return SimpleNamespace(**fields)


def _composed(standings):
    """The record string a client builds out of the served blob.

    Deliberately a transcription of what the clients actually do —
    `RelatedFutures.tsx`'s `StandingsCard` and both two-column team cards —
    rather than a call into our own helper, so the guard cannot agree with the
    server by sharing its bug.
    """
    if not isinstance(standings, dict):
        return None
    if standings.get("wins") is None or standings.get("losses") is None:
        return None
    record = f"{standings['wins']}-{standings['losses']}"
    draws = standings.get("draws") or standings.get("ties")
    if draws:
        record += f"-{draws}"
    return record


# ── The table. A row is (label, current_record, standings, expected_record) ──
#
# The eight MLB rows are production's own, verbatim; the rest are the other
# directions the rule has to survive, each measured on the same 137-row
# population #5520 and #6266 worked from.

BAL = {"wins": 75, "losses": 81, "div_rank": 5, "division": "AL East", "pct": ".481"}
TOR = {"wins": 77, "losses": 79, "div_rank": 3, "division": "AL East", "pct": ".494"}
PHI = {"wins": 86, "losses": 70, "div_rank": 1, "division": "NL East"}
MIL = {"wins": 98, "losses": 58, "div_rank": 1, "division": "NL Central"}
BOS = {"wins": 84, "losses": 72, "div_rank": 3, "division": "AL East"}
CLE = {"wins": 81, "losses": 75, "div_rank": 2, "division": "AL Central"}
LAD = {"wins": 96, "losses": 60, "div_rank": 1, "division": "NL West"}
SD = {"wins": 87, "losses": 69, "div_rank": 2, "division": "NL West"}

# NHL between seasons: the board has ROLLED OVER and `current_record` still
# holds last season's finished 82 games. The board is right and the fresh-looking
# column is the wrong one — #6266's defect, and the reason the preference is
# conditioned rather than blanket.
NHL_ROLLOVER = {"wins": 0, "losses": 0, "ties": 0, "division": "Pacific"}

# NBA after the season: the direction REVERSES. `current_record` is 77 games of
# a season the board has complete at 82.
NBA_FINISHED = {"wins": 20, "losses": 62, "div_rank": 5, "division": "Atlantic"}

# A soccer row, where the record has three parts and the row spells the third
# `draws` rather than `ties`.
SOCCER_LAGGING = {"wins": 12, "losses": 5, "draws": 3, "points": 39}

ROWS = [
    ("BAL, one win ahead of the board", "76-81", BAL, "76-81"),
    ("TOR, one loss ahead of the board", "77-80", TOR, "77-80"),
    ("PHI, agrees", "86-70", PHI, "86-70"),
    ("MIL, agrees", "98-58", MIL, "98-58"),
    ("BOS, agrees", "84-72", BOS, "84-72"),
    ("CLE, agrees", "81-75", CLE, "81-75"),
    ("LAD, agrees", "96-60", LAD, "96-60"),
    ("SD, agrees", "87-69", SD, "87-69"),
    ("NHL rollover — the BOARD wins", "43-33-6", NHL_ROLLOVER, "0-0"),
    ("NBA finished — the BOARD wins", "18-59", NBA_FINISHED, "20-62"),
    ("soccer, board lagging a draw", "12-5-4", SOCCER_LAGGING, "12-5-4"),
    ("no current_record at all", None, PHI, "86-70"),
    ("unparseable current_record", "N/A", CLE, "81-75"),
]


@pytest.mark.parametrize(
    "label,current_record,standings,expected",
    ROWS,
    ids=[row[0] for row in ROWS],
)
def test_no_served_payload_carries_two_records(
    label, current_record, standings, expected
):
    """THE INVARIANT. `record` and the client-composed W-L must be one answer.

    This is the guard the acceptance asks for: it fails on the disagreement
    itself, on any row, in either direction. It does not know which rail is
    supposed to win — only that the payload may not say both.
    """
    data = _format_team_data(_team(current_record, deepcopy(standings)))

    assert data["record"] == expected, f"{label}: wrong rail won"
    assert _composed(data["standings"]) == data["record"], (
        f"{label}: the payload carries two records — "
        f"`record` {data['record']!r} against a composed "
        f"{_composed(data['standings'])!r}"
    )


def test_the_sweep_is_not_vacuous():
    """The control: the table must contain rows the repair actually MOVED.

    Without this, a `_format_team_data` that returned the board untouched
    would pass the sweep above on an all-agreeing table, and the suite would
    certify a no-op. It also pins the other half — that rows which already
    agreed are left alone — so "align everything to `current_record` always"
    is not a passing implementation either.
    """
    moved, untouched = [], []
    for label, current_record, standings, _expected in ROWS:
        served = _format_team_data(_team(current_record, deepcopy(standings)))
        if served["standings"] != standings:
            moved.append(label)
        else:
            untouched.append(label)

    assert moved, "no row in ROWS exercises the alignment — the sweep is vacuous"
    assert untouched, "every row was rewritten — the rule discriminates nothing"
    # The two production specimens are the rows that must move, and the six
    # that agreed are the rows that must not.
    assert "BAL, one win ahead of the board" in moved
    assert "TOR, one loss ahead of the board" in moved
    assert "PHI, agrees" in untouched
    assert "MIL, agrees" in untouched


def test_the_board_keeps_every_fact_that_is_not_the_record():
    """Only the three composable keys move; rank and vintage stay the board's.

    #5520's ruled shape — a fresher record beside a board-vintage rank is
    strictly less wrong than a stale record beside it — and the reason `pct`
    is deliberately NOT recomputed: nothing renders it, and our formula is not
    StatPal's `percentage`.
    """
    served = _format_team_data(_team("76-81", deepcopy(BAL)))
    standings = served["standings"]

    assert standings["wins"] == 76 and standings["losses"] == 81
    assert standings["div_rank"] == 5
    assert standings["division"] == "AL East"
    assert standings["pct"] == ".481", "pct was recomputed; it must keep the board's"


def test_a_record_with_no_draw_component_withholds_the_draw_key():
    """Absent, never a fabricated zero (notice 34).

    A two-part record chosen over a board that carries draws cannot say the
    draws are zero — the rail it came from never mentioned them. Removing the
    key composes the same string and claims nothing.
    """
    board = {"wins": 12, "losses": 5, "draws": 3, "points": 39}
    record, standings = reconciled_record_and_standings("20-5", board)

    assert record == "20-5"
    assert "draws" not in standings and "ties" not in standings
    assert _composed(standings) == "20-5"
    assert standings["points"] == 39, "an unrelated board fact was dropped"


def test_the_draw_key_is_written_through_the_spelling_the_row_uses():
    """A row that says `ties` keeps saying `ties`; a client reading it must not
    start reading a `draws` we invented."""
    _record, ties_row = reconciled_record_and_standings(
        "43-33-6", {"wins": 40, "losses": 33, "ties": 5}
    )
    assert ties_row["ties"] == 6 and "draws" not in ties_row

    _record, draws_row = reconciled_record_and_standings(
        "12-5-4", {"wins": 12, "losses": 5, "draws": 3}
    )
    assert draws_row["draws"] == 4 and "ties" not in draws_row


def test_the_live_jsonb_value_is_never_mutated():
    """Gotcha #4. `teams.py` hands this helper a live SQLAlchemy JSONB value,
    and an in-place edit there is the silent write that never raises."""
    board = {"wins": 75, "losses": 81, "div_rank": 5}
    before = deepcopy(board)

    record, standings = reconciled_record_and_standings("76-81", board)

    assert record == "76-81"
    assert standings is not board
    assert board == before, "the caller's dict was edited in place"


def test_an_unreadable_row_keeps_the_record_it_was_already_serving():
    """The non-regression. A row the rule cannot measure must not LOSE its
    record: there is no board behind it, so there is no contradiction to
    remove, and blanking it would be a worse bug than the one being fixed."""
    served = _format_team_data(_team("see website", None))

    assert served["record"] == "see website"
    assert "standings" not in served


def test_a_team_with_no_board_still_serves_its_record():
    """The other half of the same non-regression: the overwhelming majority of
    rows carry `current_record` and no `standings_data` at all."""
    served = _format_team_data(_team("9-3", None))

    assert served["record"] == "9-3"
    assert "standings" not in served
