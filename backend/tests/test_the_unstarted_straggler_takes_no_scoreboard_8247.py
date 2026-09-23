"""#8247 — `allow_unstarted` granted settling, and quietly granted the scoreboard too.

WHAT A USER SAW, production 2026-09-23, twelve minutes after the #5501 release
(v4972, 15:17Z), on `/events/15290171` — Chicago White Sox @ Toronto Blue Jays,
**played 2026-04-02**, read nearly six months later
(`artifacts-live-538/REGRESSION-15290171-0-0-hero-1532Z.png`):

    the hero prints a scoreboard of `0` — `0`, the caption reads
    "No result reported · last score 0-0", and the Score Differential chart
    has gained an orange "Actual Score Diff" point.

Before the release those two columns were NULL and none of it rendered. This is
strictly worse than the blank it replaced: a blank reads as "we do not know", a
`0-0` reads as a fact, and it is false.

── THE MECHANISM ────────────────────────────────────────────────────────────

#5501 widened `_settle_deep_authority_stragglers` to reach `scheduled` rows and
passes `allow_unstarted=True` into the settle door so their status MAY be moved
to a Final. But the door is `update_event_fields_from_espn`, and its own
docstring says what it does:

    Update clock, SCORES, broadcast, importance, and commence_time from ESPN.

Only the `status`/`completed_at` write was ever gated on `authority_may_settle`.
The four live-state values — `game_clock`, `period`, `home_score`, `away_score` —
sat OUTSIDE that permission and were written on their own terms. So a
`scheduled` row the widened SELECT now reaches, whose board does NOT report
`post`/`final` (a postponement, a cancellation, or a board answering with a
pre-game record), kept its status and still took ESPN's `0-0`.

A permission scoped to settling silently also granted score-writing, because the
two live in one function and only one of them was gated.

── WHY #5501's OWN GUARD DID NOT CATCH IT ───────────────────────────────────

`test_the_shared_door_still_refuses_a_scheduled_row_by_default` asserts exactly
one thing about the refused row:

    assert row.status == "scheduled"

It proved the status did not move and said nothing about the scoreboard, so the
half of the door that was not gated was also the half nothing looked at. These
tests assert on the UPDATE's own params, which is where the write actually is.

── MEASURED, production, on a FIXED banked set of 328 ids ───────────────────

    pre-merge 14:53Z   0 rows `scheduled` carrying a score
    15:22Z             0          (post-release, drain started)
    15:29Z             7
    15:33Z            12 site-wide, every one of them exactly `0-0`

Same query, same ids, before and after — which is why banking by id rather than
by count was what made the cause decisive instead of inferred.
"""

from datetime import datetime, timezone

import pytest

from app.services.espn_api import ESPNEvent
from app.utils.espn_helpers import update_event_fields_from_espn

from tests.test_the_anchored_straggler_past_the_window_6280 import (
    _FakeEvent,
    _FakeSession,
)

#: 2026-04-02 20:10Z — production row 15290171's own `commence_time`.
FIRST_PITCH = datetime(2026, 4, 2, 20, 10, tzinfo=timezone.utc)


def _board(status, home_score, away_score, *, clock=None, detail=None):
    """One row of an ESPN board, in whatever state the board reports."""
    return ESPNEvent(
        espn_id="401814780",
        name="fixture 401814780",
        short_name=None,
        date=FIRST_PITCH,
        status=status,
        status_detail=detail if detail is not None else (
            "Final" if status == "post" else "Scheduled"
        ),
        period=None,
        clock=clock,
        home_team=None,
        away_team=None,
        home_score=home_score,
        away_score=away_score,
        venue=None,
        broadcasts=[],
        home_win_probability=None,
        stopped_without_result=False,
    )


def _white_sox_at_blue_jays(**kw):
    """Production row 15290171, exactly as it sat before the regression."""
    return _FakeEvent(
        15290171, "401814780", "Toronto Blue Jays", "Chicago White Sox",
        FIRST_PITCH, status="scheduled", sport_key="baseball_mlb", **kw
    )


async def _door(row, board, *, allow_unstarted):
    session = _FakeSession([row])
    await update_event_fields_from_espn(
        session, row, board, {"401814780"},
        {"authority_dark_sports": 0, "errors": []},
        allow_unstarted=allow_unstarted,
    )
    return session


def _written(session, column):
    """Every value this session's Core UPDATEs tried to put in `column`.

    Read off `stmt.compile().params` rather than off the row, because the write
    is a Core UPDATE and a row attribute would not see it — and because the
    params are what the database would actually have received.
    """
    return [
        params[column]
        for _text, params in session.updates
        if column in params
    ]


# ── THE DEFECT ───────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_an_unstarted_row_whose_board_did_not_finish_takes_no_scoreboard():
    """The regression, at its specimen: a 2026-04-02 game must not take `0-0`."""
    row = _white_sox_at_blue_jays()

    session = await _door(row, _board("pre", 0, 0), allow_unstarted=True)

    assert _written(session, "home_score") == [], (
        "the board did not report this game finished, so its scoreboard is not "
        "a fact about it — /events/15290171 printed a 0-0 hero on a game played "
        "six months earlier"
    )
    assert _written(session, "away_score") == []
    assert row.status == "scheduled", "unsettled rows keep their status"


@pytest.mark.asyncio
async def test_the_refusal_covers_the_clock_and_the_period_too():
    """All four live-state columns describe a match IN PLAY. This row is not."""
    row = _white_sox_at_blue_jays()

    session = await _door(
        row, _board("pre", 0, 0, clock="0:00", detail="Top 1st"),
        allow_unstarted=True,
    )

    assert _written(session, "game_clock") == []
    assert _written(session, "period") == []


# ── THE POSITIVE CONTROL: the rig CAN express the write it is asked to refuse ─
#
# Without this arm the two tests above pass on a door that writes nothing at
# all, which is the vacuity that makes a "nothing was written" assertion worth
# nothing on its own.

@pytest.mark.asyncio
async def test_the_same_rig_writes_the_scoreboard_when_the_board_says_final():
    """#5501's actual ship, unbroken: a finished game still gets its score."""
    row = _white_sox_at_blue_jays()

    session = await _door(row, _board("post", 3, 5), allow_unstarted=True)

    assert _written(session, "home_score") == [3], (
        "the permission still has to settle a genuinely finished game — this is "
        "what #5501 exists to do"
    )
    assert _written(session, "away_score") == [5]


# ── THE CONFINEMENT: the fix must not reach any caller that did not opt in ───

@pytest.mark.asyncio
async def test_the_liveness_pass_still_scores_a_scheduled_row_as_its_game_starts():
    """The refusal keys on the FLAG, never on the status.

    A `scheduled` row taking a score from an in-progress board is the normal
    kickoff path — the liveness pass promotes and scores it in the same hop.
    Keying the refusal on `status == "scheduled"` instead of on the flag would
    silently break that, and it is the far larger population.
    """
    row = _white_sox_at_blue_jays()

    session = await _door(row, _board("in", 2, 1), allow_unstarted=False)

    assert _written(session, "home_score") == [2], (
        "a caller that never asked for the unstarted permission had its own "
        "score write taken away"
    )
    assert _written(session, "away_score") == [1]


@pytest.mark.asyncio
async def test_a_default_caller_is_bit_identical_to_before_the_fix():
    """`allow_unstarted` defaults False, so the refusal cannot fire by omission."""
    row = _white_sox_at_blue_jays()
    session = _FakeSession([row])

    await update_event_fields_from_espn(
        session, row, _board("in", 4, 0), {"401814780"},
        {"authority_dark_sports": 0, "errors": []},
    )

    assert _written(session, "home_score") == [4]
