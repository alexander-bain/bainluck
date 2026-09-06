"""#3397 — a postponed match must not render as live.

THE ROW. Production 2026-09-05, event ``15291065``, D.C. United @ FC Cincinnati,
MLS, scheduled ``2026-09-06 01:31Z``::

    status      live
    period      Postponed
    game_clock  0'
    scores      0 / 0
    espn_snapshots  0 rows

The native app drew a ``Postponed 0'`` pill directly beneath a ``Win Probability
● Live`` header and counted the match in its ``13 live`` badge; the web MLS
league page drew the same row first in ``Live Now 3`` with a green dot. The other
two cards in that rail were genuinely live and read correctly — the rail was
right about two of its three members, so nothing global was broken. One row was
saying two things.

WHY NOTHING CAUGHT IT. `espn_terminal_state` (#2908) reads ESPN's own
``state``/``completed`` pair and returns ``"post"`` only when a competition is
over AND somebody finished it, which correctly refuses to settle a postponement.
But its ``None`` arrives at `update_event_fields_from_espn` as *no opinion*, and
that helper's if/elif chain tests ``ee.status in ("post", "final")`` and
``ee.status == "in"``. ``STATUS_POSTPONED`` is neither, so the chain fell
through, the status column was never written, and the row kept the ``live`` the
clock promotion in `transition_event_statuses` had given it when kickoff passed.
ESPN's word for the stoppage was recorded — in ``period`` — and its meaning was
not.

THE SHAPE OF THE FIX, WHICH IS THE POINT OF THIS FILE. The obvious guard is the
stoppage words, and the repo already has one: `schedule_sentinel._ESPN_POSTPONED`
lists POSTPONED, CANCELED, CANCELLED, SUSPENDED and ABANDONED — five entries,
one of them a British spelling somebody added after being bitten. That is a
denylist on a status column, and a denylist admits every state nobody
anticipated. `espn_stopped_without_result` instead reads ``state == "post"`` with
``completed`` not True: ESPN's ``pre``/``in``/``post`` is a closed three-value
vocabulary published on every competition, and ``completed`` is the boolean that
splits ``post`` into "finished" and "stopped". `test_a_name_espn_has_not_invented
_yet_is_still_caught` is the assertion that separates the two designs, and it
carries its own control — the same payload IS missed by the name list.

MEASURED BLAST RADIUS (production 2026-09-05, all sports)::

    period          live rows
    (null)                 58
    In Progress             5
    7:53 - 3rd Quarter      1
    End 8th                 1
    49'                     1
    Postponed               1     <- the defect
    Top 9th                 1
    54'                     1

One row, hence p3. The 58 ``period IS NULL`` rows are also why the fix may not
fail closed on a missing period: those events have no ESPN opinion at all, and a
guard that demoted them would empty the rail. Reading ``state`` rather than
``period`` never reaches them — no ESPN status block, no demotion.
"""

from datetime import datetime, timedelta, timezone

import pytest

from app.services.espn_api import ESPNAPIService, espn_stopped_without_result
from app.utils.event_completion import EVENT_SUSPENDED
from app.utils.espn_helpers import update_event_fields_from_espn

from tests.test_espn_api_parsing import LIVE_EVENT
from tests.test_espn_soccer_full_time_2908 import (
    BRAGA_GIL_VICENTE_POSTPONED,
    LILLE_TOULOUSE_FULL_TIME,
    NANTES_TOULOUSE_ABANDONED,
    NON_SETTLING_PAYLOADS,
    SETTLING_PAYLOADS,
    SOCCER_SECOND_HALF,
)


#: The two captured stoppages are imported, not re-typed. `test_espn_soccer_
#: full_time_2908` fetched them from ESPN (`soccer/por.1` event 401885480 and
#: `soccer/fra.1` event 746714) and checks its own fixture set against the
#: census table, so importing keeps ONE copy of the evidence: if that module
#: re-captures or renames a payload this file fails loudly rather than drifting
#: onto a stale private copy.
CAPTURED_STOPPAGES = NON_SETTLING_PAYLOADS


def _rename(payload: dict, name: str, **type_overrides) -> dict:
    """A copy of a CAPTURED payload with its status type edited.

    Derived from a real capture rather than hand-built so that the only
    difference between the fixture and production data is the field under test.
    """
    out = {**payload, "status": {**payload["status"]}}
    out["status"]["type"] = {**payload["status"]["type"], "name": name,
                             **type_overrides}
    return out


#: 🔴 A name ESPN has not invented. `state`/`completed` are the captured
#: postponement's, untouched — only the name is new, which is exactly the
#: variable a denylist keys on and this fix does not.
INVENTED_STOPPAGE = _rename(
    BRAGA_GIL_VICENTE_POSTPONED,
    "STATUS_CALLED_OFF_WATERLOGGED_PITCH",
    detail="Called Off",
)

#: 🔴 DELIBERATELY OUT OF SCOPE, and pinned so the scope is a decision rather
#: than an oversight. ESPN publishes a delay as ``state="in"`` — the authority
#: claiming the competition IS in progress. `espn_terminal_state` measured this
#: and declined to translate ``in`` for the same reason. Catching a delay needs
#: the NAME, which is the rotting test this fix exists to avoid, over a
#: population this change has not measured.
DELAYED_IS_STILL_IN_PLAY = _rename(
    SOCCER_SECOND_HALF, "STATUS_DELAYED", state="in", detail="Delayed",
)


KICKOFF = datetime.now(timezone.utc) - timedelta(hours=1)


class _Event:
    """The columns `update_event_fields_from_espn` reads and writes."""

    def __init__(self, status="live"):
        self.id = 15291065
        self.status = status
        self.home_team_name = "FC Cincinnati"
        self.away_team_name = "D.C. United"
        self.commence_time = KICKOFF
        self.commence_time_source = "espn"
        self.completed_at = None
        self.game_clock = None
        self.period = None
        self.home_score = None
        self.away_score = None
        self.broadcast_info = None
        self.llm_importance = None


class _Session:
    def __init__(self):
        self.statements = []
        self.added = []

    async def execute(self, statement):
        self.statements.append(statement)
        return None

    def add(self, obj):
        self.added.append(obj)


async def _sync(client, payload, *, row_status="live"):
    ee = client._parse_event(payload)
    event = _Event(status=row_status)
    session = _Session()
    stats: dict = {}
    await update_event_fields_from_espn(session, event, ee, set(), stats)
    return event, stats, session


def _written(session) -> dict:
    """The columns actually sent to Postgres, merged across statements."""
    values: dict = {}
    for statement in session.statements:
        values.update(statement.compile().params)
    return values


@pytest.fixture
def client():
    return ESPNAPIService()


# ---------------------------------------------------------------------------
# The predicate: an allowlist on `state`, not a denylist on the name
# ---------------------------------------------------------------------------


class TestThePredicateReadsTheClosedVocabulary:
    @pytest.mark.parametrize(
        "payload", CAPTURED_STOPPAGES, ids=lambda p: p["status"]["type"]["name"]
    )
    def test_a_captured_stoppage_is_caught(self, payload):
        assert espn_stopped_without_result(payload["status"]["type"]) is True

    @pytest.mark.parametrize(
        "payload", SETTLING_PAYLOADS, ids=lambda p: p["status"]["type"]["name"]
    )
    def test_a_finished_match_is_not_a_stoppage(self, payload):
        """🔴 THE CONTROL. Without it the predicate passes by returning True for
        every terminal state, and a Final would be demoted out of its result."""
        assert espn_stopped_without_result(payload["status"]["type"]) is False

    def test_a_match_in_play_is_not_a_stoppage(self):
        assert espn_stopped_without_result(
            SOCCER_SECOND_HALF["status"]["type"]) is False

    def test_a_scheduled_match_is_not_a_stoppage(self):
        assert espn_stopped_without_result(
            {"name": "STATUS_SCHEDULED", "state": "pre", "completed": False}
        ) is False

    def test_a_missing_or_malformed_status_block_is_not_a_stoppage(self):
        """No ESPN opinion must never demote a row — the 58 `period IS NULL`
        live rows measured on 2026-09-05 are exactly this case."""
        for bad in (None, {}, [], "post", {"state": None}, {"completed": False}):
            assert espn_stopped_without_result(bad) is False

    def test_completed_is_load_bearing(self):
        """``state`` alone would settle two matches nobody finished, and
        ``completed`` alone would catch a scheduled fixture."""
        assert espn_stopped_without_result(
            {"state": "post", "completed": True}) is False
        assert espn_stopped_without_result(
            {"state": "post", "completed": False}) is True
        assert espn_stopped_without_result(
            {"state": "pre", "completed": False}) is False

    def test_a_name_espn_has_not_invented_yet_is_still_caught(self):
        """🔴 THE ASSERTION THAT SEPARATES ALLOWLIST FROM DENYLIST.

        The payload is the captured Braga postponement with one field changed:
        a name nobody has written down. The predicate catches it because it
        never reads the name.
        """
        assert espn_stopped_without_result(
            INVENTED_STOPPAGE["status"]["type"]) is True

    def test_the_name_denylist_would_miss_it(self):
        """🔴 ITS CONTROL — proof the mechanism was needed, not redundant.

        If `schedule_sentinel`'s hand-maintained set already covered this, the
        test above would pass under either design and prove nothing. It does
        not: the invented name is absent from the denylist, so a guard written
        that way admits the row while this one refuses it.
        """
        from app.tasks.schedule_sentinel import _ESPN_POSTPONED

        invented = INVENTED_STOPPAGE["status"]["type"]["name"]
        assert invented not in _ESPN_POSTPONED
        assert espn_stopped_without_result(INVENTED_STOPPAGE["status"]["type"])
        # And the denylist is genuinely a live alternative — it does catch the
        # captured name — so the difference above is the open vocabulary, not a
        # broken comparison.
        assert BRAGA_GIL_VICENTE_POSTPONED["status"]["type"]["name"] in _ESPN_POSTPONED

    def test_the_parser_carries_the_verdict_onto_the_event(self, client):
        """The predicate is only useful if `_parse_event` publishes it."""
        assert client._parse_event(
            BRAGA_GIL_VICENTE_POSTPONED).stopped_without_result is True
        assert client._parse_event(
            NANTES_TOULOUSE_ABANDONED).stopped_without_result is True
        assert client._parse_event(
            LILLE_TOULOUSE_FULL_TIME).stopped_without_result is False
        assert client._parse_event(
            SOCCER_SECOND_HALF).stopped_without_result is False

    def test_the_existing_status_values_are_unchanged(self, client):
        """Every reader of `ee.status` compares it against "in"/"post"/"final".
        The new field is additive precisely so none of them change meaning.

        Note what the third assertion pins, because it surprised this test on
        first run: an in-play SOCCER match does not parse as ``"in"``. Its name
        is ``STATUS_SECOND_HALF``, which matches none of the three branches in
        `_parse_event`, so it falls through to the lowercased raw name — the
        same fall-through #2908 fixed on the terminal side and
        `espn_terminal_state`'s docstring deliberately did NOT fix on the live
        side ("`state == "in"` is deliberately NOT translated here"). That is
        pre-existing and out of scope; it is asserted so this file records the
        real value rather than the assumed one.
        """
        assert client._parse_event(LILLE_TOULOUSE_FULL_TIME).status == "post"
        assert client._parse_event(LIVE_EVENT).status == "in"
        assert client._parse_event(SOCCER_SECOND_HALF).status == "status_second_half"


# ---------------------------------------------------------------------------
# The row: the Live Now rail stops carrying a match nobody kicked off
# ---------------------------------------------------------------------------


class TestALiveRowLeavesTheRailWhenEspnSaysItStopped:
    @pytest.mark.parametrize(
        "payload", CAPTURED_STOPPAGES, ids=lambda p: p["status"]["type"]["name"]
    )
    async def test_a_stopped_match_stops_reading_live(self, client, payload):
        event, stats, session = await _sync(client, payload)

        assert event.status == EVENT_SUSPENDED, (
            f"{payload['shortName']} still reads {event.status!r} while ESPN "
            f"says {payload['status']['type']['name']} — the green dot stays"
        )
        assert _written(session).get("status") == EVENT_SUSPENDED, (
            "the demotion was mirrored in memory but never sent to Postgres, "
            "so the next reader still sees live (gotcha #4/#5)"
        )
        assert stats.get("espn_stopped_without_result") == 1

    @pytest.mark.parametrize(
        "payload", CAPTURED_STOPPAGES, ids=lambda p: p["status"]["type"]["name"]
    )
    async def test_a_stoppage_is_never_given_a_result(self, client, payload):
        """🔴 THE CERT-752 RULE. A false LIVE must not be traded for a false
        FINAL — only one of the two grades, and the wrong one resolves the
        prediction-market blend off a score nobody played."""
        event, stats, session = await _sync(client, payload)
        written = _written(session)

        assert event.status not in ("completed", "closed")
        assert "completed_at" not in written, (
            f"{payload['shortName']} was stamped with a completion time"
        )
        assert event.completed_at is None
        assert stats.get("espn_completed") is None

    async def test_the_invented_name_demotes_the_row_too(self, client):
        """The predicate's open-vocabulary property, carried all the way to the
        column a reader sees."""
        event, _stats, _session = await _sync(client, INVENTED_STOPPAGE)
        assert event.status == EVENT_SUSPENDED

    async def test_a_match_still_being_played_stays_live(self, client):
        """🔴 THE CONTROL. Without it this guard passes by demoting the rail."""
        event, stats, session = await _sync(client, SOCCER_SECOND_HALF)

        assert event.status == "live", "a match at 63' was taken off the rail"
        assert stats.get("espn_stopped_without_result") is None
        assert event.period == "63'"

    async def test_a_delayed_match_is_left_alone(self, client):
        """Scope, pinned. ESPN reports a delay as ``state="in"``, so the
        authority is claiming play — this fix does not contradict it."""
        event, stats, _session = await _sync(client, DELAYED_IS_STILL_IN_PLAY)

        assert event.status == "live"
        assert stats.get("espn_stopped_without_result") is None

    @pytest.mark.parametrize(
        "payload", SETTLING_PAYLOADS, ids=lambda p: p["status"]["type"]["name"]
    )
    async def test_a_finished_match_still_settles(self, client, payload):
        """🔴 THE REGRESSION CONTROL for #2908. The new branch sits next to the
        settle branch; if it stole a finished match the rail would keep it and
        the result would never publish."""
        event, stats, session = await _sync(client, payload)

        assert event.status == "completed"
        assert _written(session).get("completed_at") is not None
        assert stats.get("espn_completed") == 1
        assert stats.get("espn_stopped_without_result") is None

    @pytest.mark.parametrize("settled", ["completed", "closed"])
    @pytest.mark.parametrize(
        "payload", CAPTURED_STOPPAGES, ids=lambda p: p["status"]["type"]["name"]
    )
    async def test_a_settled_row_is_never_un_settled_by_a_stoppage(
        self, client, payload, settled
    ):
        """A late-arriving stoppage on a row that already has a result must not
        revoke it. ESPN re-serves a postponed original after the replay is
        played; reverting there would erase a real Final.
        """
        event, stats, session = await _sync(client, payload, row_status=settled)

        assert event.status == settled
        assert stats.get("espn_stopped_without_result") is None
        assert "status" not in _written(session)

    async def test_a_scheduled_row_is_not_demoted(self, client):
        """Out of scope on purpose. A fixture that has not reached kickoff is
        correctly `scheduled` already, and moving it to `suspended` would take a
        re-dated match off the upcoming rail, which needs `scheduled`."""
        event, stats, _session = await _sync(
            client, BRAGA_GIL_VICENTE_POSTPONED, row_status="scheduled")

        assert event.status == "scheduled"
        assert stats.get("espn_stopped_without_result") is None


class TestTheRowComesBackByItselfWhenPlayStarts:
    async def test_espn_reporting_play_returns_a_suspended_row_to_live(self, client):
        """Self-healing, so a resumed match needs no second mechanism.

        `play_resumes` already admits `suspended`, which is the door the six
        suspended US Open matches came back through (CERT-752). Demoting into
        that state therefore costs nothing when the match is finally played.

        Driven with `LIVE_EVENT` rather than the soccer in-play fixture on
        purpose: only ``STATUS_IN_PROGRESS`` parses to ``ee.status == "in"``,
        which is the branch that reopens this door (see
        `test_the_existing_status_values_are_unchanged`).
        """
        event, _stats, session = await _sync(
            client, LIVE_EVENT, row_status=EVENT_SUSPENDED)

        assert event.status == "live"
        assert _written(session).get("status") == "live"

    async def test_a_demoted_row_is_not_clock_promoted_behind_espns_back(self):
        """The other half of self-healing: `suspended` is a state the promotion
        arm cannot see.

        `transition_event_statuses` promotes on the clock alone, and that is
        what made the row live in the first place. A promotion that admitted any
        non-terminal status would re-create the defect on the next beat, and the
        demotion above would then flap once a pass, forever.

        Read off the arm's own filter. The docstring is stripped first because
        it discusses `suspended` in prose, and the search is bounded to the text
        before the live→suspended marker so the later arms (which legitimately
        name both states) cannot satisfy it — a whole-source substring check
        here would pass on the wrong line.
        """
        import inspect

        from app.tasks.espn_sync import _transition_event_statuses_impl

        source = inspect.getsource(_transition_event_statuses_impl)
        body = source.split('"""')[2]  # drop signature + docstring
        promotion = body.split("# --- live → suspended")[0]

        assert 'Event.status == "scheduled"' in promotion, (
            "the scheduled→live promotion no longer filters on 'scheduled' — "
            "if it admits suspended, #3397's row is promoted straight back "
            "into the Live Now rail on the next beat"
        )
        assert "Event.status.in_" not in promotion, (
            "the promotion filter was widened to a set of statuses; check by "
            "hand that it still cannot see 'suspended' (#3397)"
        )
