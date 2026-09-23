"""#5501 — a row stranded in `scheduled` is stranded the same way, and was invisible.

WHAT A USER SAW, production 2026-09-23 at 390 px (LOOK saved at
`artifacts-live-535/LOOK-5501-mlb-stuck-scheduled-390.png`), on
`/events/15290487` — Boston Red Sox @ Pittsburgh Pirates, played 2026-08-15,
read 39 days later:

    the header says "Settled · Boston Red Sox wins · Aug 15, 2026", and
    directly beneath it the Run margin map and the Runs map both carry a
    "PRE-GAME" badge, and NO final score appears anywhere on the page.

The page is telling the reader two incompatible things at once. The settled half
is read off the linked market legs, which resolved; the pre-game half and the
missing score are read off `events.status`, which still says `scheduled`. That
is Alex's "settled means settled" ruling failing on a top-tier fixture, and his
2026-09-14 directive names the class: "Top-tier (e.g. NFL) unknown
upcoming/live/completed is a defect".

── THE MECHANISM, AND WHY #6280's ARM DID NOT ALREADY COVER IT ───────────────

#6280 established that an anchored row past the 48h settle window is reachable
by nothing — too anchored to retire, too old to settle — and built
`_settle_deep_authority_stragglers` for exactly that gap. That arm selected
`live`/`suspended`. Its docstring reported the whole stranded population as
SEVEN rows.

That count was taken over the two states the arm's own filter named, so it could
not see a row stranded in the third. `Event.status` is
`mapped_column(default="scheduled")`, so `scheduled` is both "we looked and it
had not started" AND "nobody has ever looked at this row" — indistinguishable in
the column. A row that never received its `scheduled → live` promotion is
stranded by the identical mechanism and was invisible to the arm built for it.

MEASURED on production 2026-09-23 (`/api/admin/db-query`):

    820  rows  status='scheduled', commence_time > 7 days past
    448  of those were CREATED AFTER THEIR OWN KICKOFF
    328  MLB rows minted in ONE pass on 2026-08-20, for games played
         2026-04-02 .. 2026-08-16, every one carrying an `espn_id`
      0  of those 328 share that `espn_id` with any other event row

The last line is the safety case: settling them by id cannot mint a second row
for a game. (Same-day "twins" on team name exist and carry DIFFERENT espn_ids,
which is why this arm matches by id and never by name.)

── CAPTURED FROM ESPN, by id (standing notice 26) ────────────────────────────

`site.api.espn.com/apis/site/v2/sports/baseball/mlb/scoreboard?dates=20260815`
read 2026-09-23, HTTP 200, 15 events on the board — the real response to the
exact URL shape `ESPNAPIService.get_scoreboard` builds:

    401816534  post completed=True   PIT 0 - BOS 4   ("BOS @ PIT")
    401816532  post completed=True   ATL 3 - ARI 10
    401816544  post completed=True   LAA 1 - KC 0

ESPN still serves the terminal result 39 days later, so the repair is not
inert — and `401816534`'s winner (Boston) is the same winner the page's own
header already prints from the market legs.
"""

from datetime import datetime, timedelta, timezone

import pytest

from app.services.espn_api import ESPNEvent
from app.tasks.espn_sync import (
    DEEP_STRAGGLER_STATUSES,
    _settle_deep_authority_stragglers,
)
from app.utils.espn_helpers import update_event_fields_from_espn
from app.utils.event_completion import (
    SETTLEABLE_STATUSES,
    authority_may_settle,
)

# The rig the arm is already proven against (#6280). Imported rather than
# re-declared so these tests and that suite cannot drift into testing two
# different fakes of the same collaborators.
from tests.test_the_anchored_straggler_past_the_window_6280 import (
    _FakeESPN,
    _FakeEvent,
    _FakeSession,
)

#: Five and a half weeks after the specimen's first pitch.
NOW = datetime(2026, 9, 23, 12, 0, tzinfo=timezone.utc)

#: 2026-08-15 23:15Z — the row's own `commence_time` on production.
FIRST_PITCH = datetime(2026, 8, 15, 23, 15, tzinfo=timezone.utc)


def _board_row(espn_id, home_score, away_score, *, status="post"):
    """One row of the CAPTURED 2026-08-15 MLB board."""
    return ESPNEvent(
        espn_id=espn_id,
        name=f"fixture {espn_id}",
        short_name=None,
        date=FIRST_PITCH,
        status=status,
        status_detail="Final" if status == "post" else "Scheduled",
        period=None,
        clock=None,
        home_team=None,
        away_team=None,
        home_score=home_score,
        away_score=away_score,
        venue=None,
        broadcasts=[],
        home_win_probability=None,
        stopped_without_result=False,
    )


BOARDS = {
    ("baseball_mlb", "20260815"): [
        _board_row("401816534", 0, 4),
        _board_row("401816532", 3, 10),
        _board_row("401816544", 1, 0),
    ],
}


def _red_sox_at_pirates(**kw):
    """Production row 15290487, exactly as it sits today."""
    return _FakeEvent(
        15290487, "401816534", "Pittsburgh Pirates", "Boston Red Sox",
        FIRST_PITCH, status="scheduled", sport_key="baseball_mlb", **kw
    )


async def _run(rows, boards=BOARDS, now=NOW):
    session = _FakeSession(rows)
    espn = _FakeESPN(boards)
    stats = {"authority_dark_sports": 0, "errors": []}
    await _settle_deep_authority_stragglers(
        session, espn, now, stats, update_event_fields_from_espn
    )
    return session, espn, stats


# ── THE SHIP ─────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_the_red_sox_game_is_settled_with_the_final_espn_still_serves():
    """The page stops saying "Settled ... Boston wins" over PRE-GAME and no score."""
    row = _red_sox_at_pirates()
    session, _espn, stats = await _run([row])

    assert row.status == "completed", (
        "the stranded `scheduled` row was not settled — the reader still gets "
        "a pre-game page for a game played five weeks ago"
    )
    assert stats["deep_straggler_settled"] == 1

    # Read off the statement, not the row: since #6056 / CERT-2829 the
    # live-state columns are SENT by a conditional UPDATE rather than assigned,
    # and this suite drives the pass against a recording session.
    written = {}
    for _text, params in session.updates:
        written.update(params)
    assert (written.get("home_score"), written.get("away_score")) == (0, 4), (
        "settled without ESPN's final: the page would print a result and no "
        "score, which is half of what the reader is complaining about"
    )
    assert written.get("status") == "completed"


@pytest.mark.asyncio
async def test_the_arm_asks_the_board_day_the_row_carries():
    """By id, on its own board day — never by name across days (gotcha #32)."""
    _session, espn, _stats = await _run([_red_sox_at_pirates()])

    assert espn.asked == [("baseball_mlb", "20260815")]


# ── THE MUTANT THE RECORDING RIG CANNOT CATCH ────────────────────────────────

@pytest.mark.asyncio
async def test_the_select_names_the_scheduled_state():
    """Asserted ON THE STATEMENT, because the rig cannot apply a WHERE clause.

    `_FakeSession` hands back whatever rows it was constructed with, whatever it
    was asked — so every test above would go on passing if `scheduled` were
    dropped from the SELECT and the population went unselected on production.
    The sibling suite makes the same point about the 48h boundary; this is the
    same hazard on the status filter, which is the clause this ship changes.
    """
    session = _FakeSession([])
    await _settle_deep_authority_stragglers(
        session, _FakeESPN(BOARDS), NOW,
        {"authority_dark_sports": 0, "errors": []},
        update_event_fields_from_espn,
    )

    assert len(session.selects) == 1
    _text, params = session.selects[0]
    # The IN clause binds as ONE list-valued param, so this reads inside it —
    # `"scheduled" in params.values()` is False even when the clause is right.
    selected = set(params["status_1"])
    assert "scheduled" in selected, (
        "the deep arm no longer selects `scheduled`; the 328 measured rows go "
        "back to being reachable by nothing"
    )
    # The states it already reached must not have been traded away for it.
    assert SETTLEABLE_STATUSES <= selected, (
        f"widening the arm to `scheduled` dropped {SETTLEABLE_STATUSES - selected}"
    )


def test_the_arm_reaches_the_settleable_states_plus_the_unstarted_one():
    """The set is derived, so it cannot fall out of step the way the bug did."""
    assert set(DEEP_STRAGGLER_STATUSES) == SETTLEABLE_STATUSES | {"scheduled"}


# ── THE PERMISSION IS THIS ARM'S ALONE ───────────────────────────────────────

def test_nobody_else_may_settle_a_scheduled_row():
    """`scheduled` must NOT be in the set every caller of the door shares.

    Moving it into `SETTLEABLE_STATUSES` would pass every test above and hand
    the same permission to the liveness pass, where "nobody has started it" is a
    real observation and the guard is still doing work.
    """
    assert "scheduled" not in SETTLEABLE_STATUSES
    assert authority_may_settle("scheduled") is False
    assert authority_may_settle("scheduled", allow_unstarted=True) is True
    # The flag widens one state and nothing else: a settled row stays settled.
    for terminal in ("completed", "closed"):
        assert authority_may_settle(terminal, allow_unstarted=True) is False


@pytest.mark.asyncio
async def test_the_arm_hands_the_permission_to_the_door_it_was_given():
    """The forward is asserted, because its absence FAILS SILENTLY.

    The permission travels from the arm to an injected collaborator. If it stops
    being forwarded, every test that drives the real door still passes through
    `authority_may_settle`'s default and simply settles nothing — and if a door
    is handed the keyword it does not accept, the `TypeError` lands in the
    per-row `except` of gotcha #42 and reads as a bad row. Neither failure is
    loud, so the contract is pinned here.
    """
    seen = []

    async def _recording_door(
        session, event, matched, claimed, stats, *, allow_unstarted=False
    ):
        seen.append(allow_unstarted)

    from app.tasks.espn_sync import _settle_deep_authority_stragglers as arm

    await arm(
        _FakeSession([_red_sox_at_pirates()]), _FakeESPN(BOARDS), NOW,
        {"authority_dark_sports": 0, "errors": []}, _recording_door,
    )

    assert seen == [True], (
        "the deep arm no longer tells the door the row is an unstarted one"
    )


def test_exactly_one_call_site_grants_the_permission():
    """Inside 48h a `scheduled` row may still be a game about to start.

    The shallow arm shares BOTH the door and the board helper with the deep one,
    so the grant has to stop at the arm rather than at the helper. Asserted
    statically: driving the shallow arm to its door needs a row that satisfies
    preconditions this ship does not touch, and a behavioural test that silently
    stopped reaching the door would assert nothing while still passing.
    """
    import inspect as _inspect

    from app.tasks import espn_sync

    src = _inspect.getsource(espn_sync)
    assert src.count("allow_unstarted=True") == 1, (
        "more than one arm now grants the unstarted-settle permission"
    )
    # …and the helper everyone else shares still defaults to refusing.
    default = _inspect.signature(
        espn_sync._ask_boards_by_espn_id
    ).parameters["allow_unstarted"].default
    assert default is False


@pytest.mark.asyncio
async def test_the_shared_door_still_refuses_a_scheduled_row_by_default():
    """The default path — the liveness pass — is unchanged by this ship."""
    row = _red_sox_at_pirates()
    session = _FakeSession([row])

    await update_event_fields_from_espn(
        session, row, _board_row("401816534", 0, 4), {"401816534"},
        {"authority_dark_sports": 0, "errors": []},
    )

    assert row.status == "scheduled", (
        "a caller that did not ask for the permission was granted it anyway"
    )


# ── THE LIVELOCK, which is why the stamp predicate had to move too ───────────

@pytest.mark.asyncio
async def test_a_scheduled_row_the_board_did_not_settle_is_still_stamped():
    """Otherwise it re-asks its board every pass, forever.

    `_stamp_asked` used to skip any row `authority_may_settle` refused. Once
    `scheduled` rows are candidates, that predicate reads a row the board did
    not settle as "already left the candidate states" and never stamps it — so
    it never enters its cooldown. The stamp has to follow the ARM's candidate
    set, not the door's.
    """
    absent = _FakeEvent(
        15290999, "401816999", "Chicago Cubs", "St. Louis Cardinals",
        FIRST_PITCH, status="scheduled", sport_key="baseball_mlb",
    )
    session, espn, stats = await _run([absent])

    assert absent.status == "scheduled", "a row absent from its board was settled"
    assert espn.asked == [("baseball_mlb", "20260815")]
    assert stats["deep_straggler_asked"] == 1, (
        "the unsettled `scheduled` row went unstamped — it will re-ask this "
        "board on every pass and starve the queue behind it"
    )
    assert session.stamped_sources(), "no cooldown stamp was written"


@pytest.mark.asyncio
async def test_a_stamped_scheduled_row_is_left_alone_inside_its_cooldown():
    """The stamp it now receives is one the queue actually reads back."""
    recent = (NOW - timedelta(hours=1)).isoformat()
    row = _red_sox_at_pirates(asked_at=recent)
    _session, espn, _stats = await _run([row])

    assert espn.asked == [], "the cooldown did not hold the row back"
    assert row.status == "scheduled"


# ── SAFETY: the flag never turns a fixture that has not been played into a Final

@pytest.mark.asyncio
async def test_a_row_whose_board_says_it_has_not_finished_is_left_alone():
    """The door still requires ESPN's own `post`, flag or no flag.

    This is the case the refusal's original wording was protecting — a row we
    hold as `scheduled` that really has not been played. It is refused here by
    the authority's answer, not by our own status.
    """
    row = _red_sox_at_pirates()
    boards = {
        ("baseball_mlb", "20260815"): [
            _board_row("401816534", None, None, status="scheduled"),
        ],
    }
    _session, _espn, stats = await _run([row], boards=boards)

    assert row.status == "scheduled"
    assert stats["deep_straggler_settled"] == 0
