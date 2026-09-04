"""#2908 — a soccer match that reaches full time stops being LIVE.

WHAT A USER SAW. Page one of `/sports` at phone width, 2026-09-03 ~22:35Z. The
**Live Now** rail said 8, and two of its cards were finished matches wearing a
full-time clock:

    FT 90'+5'  ·  FRANCE LIGUE ONE  ·  Lille 1 — Toulouse 0
    FT 90'+5'  ·  SPAIN LA LIGA     ·  Celta Vigo 0 — Real Sociedad 0

One row, two claims: `status = "live"` for the rail, `period = "FT"` on the card,
200 px apart.

WHICH FIELD WAS WRONG (the #2841 rule, answered before anything was repaired).
`period` was RIGHT. ESPN's own payload for that exact fixture, re-fetched
2026-09-04:

    soccer/fra.1  LILL @ TOU
    status.type = {"name": "STATUS_FULL_TIME", "state": "post",
                   "completed": true, "detail": "FT", "shortDetail": "FT"}
    status.displayClock = "90'+5'"

The authority says the match is over, in three separate fields. It was `status`
that had not caught up — and the reason it had not is one line in
`ESPNAPIService._parse_event`, which derived its `pre`/`in`/`post` from
`status.type.name` and knew exactly one terminal name, `STATUS_FINAL`. Surveyed
across every ESPN-mapped league on 2026-09-02/03:

    baseball/mlb               STATUS_FINAL       state=post  completed=True
    football/college-football  STATUS_FINAL       state=post  completed=True
    tennis/atp                 STATUS_FINAL       state=post  completed=True
    soccer/fra.1               STATUS_FULL_TIME   state=post  completed=True
    soccer/esp.1               STATUS_FULL_TIME   state=post  completed=True

**Soccer is the only mapped sport that does not say FINAL**, so every finished
soccer match fell through to the raw name, `update_event_fields_from_espn`'s
settle branch never fired, and nothing else was allowed to end it — live/048
correctly stopped the silence-based fallback from ending matches, so the row
went to `suspended` and stayed there. Measured 2026-09-04: **574 soccer rows**
sat `live` or `suspended` more than four hours past their own kickoff.

The repair reads the field ESPN publishes for this — `status.type.state`, with
`completed` — which `_parse_header_scores` has already read since #980/#981.
"""

from datetime import datetime, timedelta, timezone

import pytest

from app.services.espn_api import ESPNAPIService, espn_terminal_state
from app.utils.espn_helpers import update_event_fields_from_espn

NOW = datetime(2026, 9, 3, 22, 35, tzinfo=timezone.utc)
KICKOFF = NOW - timedelta(hours=2)


# ---------------------------------------------------------------------------
# The production payloads
# ---------------------------------------------------------------------------

#: `soccer/fra.1` scoreboard, Lille at Toulouse, re-fetched 2026-09-04. The exact
#: fixture from the bug report, trimmed to the keys the parser reads.
LILLE_TOULOUSE_FULL_TIME = {
    "id": "704946",
    "name": "Lille at Toulouse",
    "shortName": "LILL @ TOU",
    "date": "2026-09-03T19:00Z",
    "status": {
        "clock": 5400.0,
        "displayClock": "90'+5'",
        "period": 2,
        "type": {
            "id": "28", "name": "STATUS_FULL_TIME", "state": "post",
            "completed": True, "description": "Full Time",
            "detail": "FT", "shortDetail": "FT",
        },
    },
    "competitions": [{
        "competitors": [
            {"homeAway": "home", "score": "0", "team": {"id": "1", "name": "Toulouse"}},
            {"homeAway": "away", "score": "1", "team": {"id": "2", "name": "Lille"}},
        ],
    }],
}

#: The same shape a match IN PLAY carries. ESPN's second-half state word is not
#: `STATUS_IN_PROGRESS` either, which is why this is a fixture and not an
#: assumption.
SOCCER_SECOND_HALF = {
    "id": "704947",
    "name": "Celta Vigo at Real Sociedad",
    "shortName": "CEL @ RS",
    "date": "2026-09-03T21:00Z",
    "status": {
        "displayClock": "63'",
        "period": 2,
        "type": {
            "id": "3", "name": "STATUS_SECOND_HALF", "state": "in",
            "completed": False, "detail": "63'", "shortDetail": "63'",
        },
    },
    "competitions": [{
        "competitors": [
            {"homeAway": "home", "score": "0", "team": {"id": "3", "name": "Real Sociedad"}},
            {"homeAway": "away", "score": "0", "team": {"id": "4", "name": "Celta Vigo"}},
        ],
    }],
}

#: 🔴 The one that must NOT settle. A cancelled or postponed fixture is also
#: `state="post"` — with `completed=False`, because nothing was played.
SOCCER_CANCELLED = {
    "id": "704948",
    "name": "Nantes at Lens",
    "shortName": "NAN @ LEN",
    "date": "2026-09-03T19:00Z",
    "status": {
        "displayClock": "0'",
        "period": 0,
        "type": {
            "id": "5", "name": "STATUS_CANCELED", "state": "post",
            "completed": False, "detail": "Canceled", "shortDetail": "Canceled",
        },
    },
    "competitions": [{
        "competitors": [
            {"homeAway": "home", "score": None, "team": {"id": "5", "name": "Lens"}},
            {"homeAway": "away", "score": None, "team": {"id": "6", "name": "Nantes"}},
        ],
    }],
}


@pytest.fixture
def client():
    return ESPNAPIService()


# ---------------------------------------------------------------------------
# The parser
# ---------------------------------------------------------------------------


class TestTheParserReadsTheAuthoritysOwnState:
    def test_the_fixture_is_the_one_the_old_code_could_not_read(self, client):
        """🔴 The control. If ESPN ever renames this to STATUS_FINAL the bug is
        gone and every assertion below would pass for the wrong reason."""
        name = LILLE_TOULOUSE_FULL_TIME["status"]["type"]["name"]
        assert name == "STATUS_FULL_TIME"
        assert name.lower() not in ("status_final", "status_in_progress",
                                    "status_scheduled"), (
            "this fixture no longer exercises the fall-through branch"
        )

    def test_soccer_full_time_parses_as_post(self, client):
        event = client._parse_event(LILLE_TOULOUSE_FULL_TIME)
        assert event is not None
        assert event.status == "post", (
            "a match ESPN calls Full Time did not reach the settle branch"
        )
        assert event.status_detail == "FT"
        assert event.clock == "90'+5'"

    def test_a_cancelled_match_does_not_parse_as_post(self, client):
        """`state="post"` alone would stamp a Final and a 0-0 on a match nobody
        played — a false LIVE traded for a false FINAL (the CERT-752 class)."""
        event = client._parse_event(SOCCER_CANCELLED)
        assert event is not None
        assert event.status != "post"

    def test_an_in_play_match_is_not_settled(self, client):
        event = client._parse_event(SOCCER_SECOND_HALF)
        assert event is not None
        assert event.status != "post"

    @pytest.mark.parametrize("status_type,expected", [
        ({"state": "post", "completed": True}, "post"),
        ({"state": "post", "completed": False}, None),
        ({"state": "post"}, None),
        ({"state": "post", "completed": "true"}, None),   # the STRING is not True
        ({"state": "POST", "completed": True}, "post"),
        ({"state": "in", "completed": False}, None),
        ({"state": "pre", "completed": False}, None),
        ({}, None),
        (None, None),
    ])
    def test_terminal_state_needs_both_halves(self, status_type, expected):
        assert espn_terminal_state(status_type) == expected

    def test_the_sports_that_already_worked_still_work(self, client):
        """STATUS_FINAL never reaches the new branch; it is matched by name
        first. Asserted so the repair is provably additive."""
        from tests.test_espn_api_parsing import FINAL_EVENT, LIVE_EVENT, SCHEDULED_EVENT

        assert client._parse_event(FINAL_EVENT).status == "post"
        assert client._parse_event(LIVE_EVENT).status == "in"
        assert client._parse_event(SCHEDULED_EVENT).status == "scheduled"


# ---------------------------------------------------------------------------
# The row — the acceptance criterion, end to end
# ---------------------------------------------------------------------------


class _Event:
    def __init__(self, status="live"):
        self.id = 15297780
        self.status = status
        self.home_team_name = "Toulouse"
        self.away_team_name = "Lille"
        self.commence_time = KICKOFF
        self.commence_time_source = "odds_api"
        self.completed_at = None
        self.game_clock = None
        self.period = None
        self.home_score = None
        self.away_score = None
        self.broadcast_info = None
        self.llm_importance = None


class _Session:
    """Records the UPDATE statements the helper issues; adds nothing to a DB."""

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
    stats = {}
    await update_event_fields_from_espn(session, event, ee, set(), stats)
    return event, stats, session


def _written(session) -> dict:
    """The columns the helper actually sent to Postgres, merged.

    Read off the compiled statements rather than off the in-memory row on
    purpose: the settle branch writes through Core `update()` and mirrors only
    `status` back onto the ORM object, so `completed_at` lands in the database
    and is absent in memory (gotcha #5, and named as an observation below).
    Asserting the statement is asserting what a reader will actually see.
    """
    values: dict = {}
    for statement in session.statements:
        values.update(statement.compile().params)
    return values


class TestTheLiveNowRailStopsCarryingFinishedMatches:
    async def test_a_full_time_soccer_row_is_closed(self, client):
        """The bug report's own row: `status='live'`, ESPN says FT."""
        event, stats, session = await _sync(client, LILLE_TOULOUSE_FULL_TIME)

        assert event.status == "completed", (
            f"the row is still {event.status!r} while its own period says "
            f"{event.period!r} — the Live Now rail keeps the card"
        )
        written = _written(session)
        assert written.get("status") == "completed"
        assert written.get("completed_at") is not None, (
            "the row was closed without a completion stamp"
        )
        assert stats.get("espn_completed") == 1
        # The card's clock is unchanged. `period` was never the wrong field.
        assert event.period == "FT"
        assert event.game_clock == "90'+5'"

    async def test_a_suspended_row_settles_in_one_hop(self, client):
        """Where the 574 stuck rows actually live: the silence fallback moved
        them to `suspended` because nothing was allowed to end them."""
        event, _stats, _session = await _sync(
            client, LILLE_TOULOUSE_FULL_TIME, row_status="suspended"
        )
        assert event.status == "completed"

    async def test_a_match_still_being_played_stays_live(self, client):
        """🔴 THE CONTROL the acceptance criterion asks for by name: without it
        this guard passes by closing everything."""
        event, stats, session = await _sync(client, SOCCER_SECOND_HALF)

        assert event.status == "live", "a match at 63' was closed"
        assert "completed_at" not in _written(session)
        assert stats.get("espn_completed") is None
        assert event.period == "63'"

    async def test_a_cancelled_match_is_not_given_a_final(self, client):
        event, _stats, session = await _sync(client, SOCCER_CANCELLED)

        assert event.status == "live", (
            "a cancelled fixture was settled — that stamps a Final and a blank "
            "score on a match nobody played"
        )
        assert "completed_at" not in _written(session)

    async def test_no_terminal_period_word_survives_on_a_live_row(self, client):
        """The acceptance criterion as the reader states it: no card in the rail
        carries a terminal period word while its status says live.

        Stated over the payloads rather than over one of them, so a future ESPN
        vocabulary added to the fixtures above is covered without a new test.
        """
        terminal_words = {"ft", "final", "aet", "full time"}
        for payload in (LILLE_TOULOUSE_FULL_TIME, SOCCER_SECOND_HALF, SOCCER_CANCELLED):
            event, _stats, _session = await _sync(client, payload)
            period = (event.period or "").strip().lower()
            if period in terminal_words:
                assert event.status != "live", (
                    f"{payload['shortName']}: period={event.period!r} on a live row"
                )
