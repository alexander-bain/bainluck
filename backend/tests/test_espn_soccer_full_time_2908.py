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

── PROVENANCE (`LIVE-060-EVIDENCE-PROVENANCE`, CERT-904 follow-up) ────────────

CERT-904 granted this ship's token and named one evidence defect: the trimmed
Lille–Toulouse fixture below carried the id `704946`, which is not that match's
ESPN id, under a comment claiming it was "the exact fixture from the bug
report". It is now the real one, `401876468`, with ESPN's real team ids and its
real kickoff instant; every literal in it came out of the response, not out of a
keyboard. Each fixture below now says in its own comment whether it was CAPTURED
or CONSTRUCTED, because a fixture that claims a provenance it does not have is
evidence you cannot re-derive.

Fixing that turned up a second prose defect, in the same family. Both this
module and `espn_terminal_state`'s docstring named **`STATUS_CANCELED`** as the
`state="post" / completed=False` case the fix must refuse. That name was never
measured. A census of **5,672 soccer fixtures** across 34 ESPN leagues,
2026-02-01 → 2026-09-04, returns it **zero** times, and returns four names the
original evidence did not mention:

    STATUS_FULL_TIME    5,572   post  completed=True    "FT"
    STATUS_FINAL_PEN       57   post  completed=True    "FT-Pens"
    STATUS_FINAL_AET        7   post  completed=True    "AET"
    STATUS_SCHEDULED       28   pre   completed=False   (kickoff time)
    STATUS_POSTPONED        7   post  completed=False   "Postponed"
    STATUS_ABANDONED        1   post  completed=False   "Abandoned"
    STATUS_CANCELED         0   —     —                 (never observed)

That census makes the ship BIGGER than it was certified as, and the extra part
is already shipped: `STATUS_FINAL_PEN` and `STATUS_FINAL_AET` are two more names
the old parser could not read, so 64 more finished matches were stuck on the
rail for the same reason. Both settle correctly under the `state`+`completed`
rule, and both are asserted below off their real payloads. The refusal side is
now asserted off the two `completed=False` terminals that actually occur —
a postponed fixture and an ABANDONED one, which is the harder of the two: it
has a real clock ("22'") and a real period, so only `completed` tells it from a
match that finished.
"""

from datetime import datetime, timedelta, timezone

import pytest

from app.services.espn_api import ESPNAPIService, espn_terminal_state
from app.utils.event_completion import EVENT_SUSPENDED
from app.utils.espn_helpers import update_event_fields_from_espn

NOW = datetime(2026, 9, 3, 22, 35, tzinfo=timezone.utc)
KICKOFF = NOW - timedelta(hours=2)


# ---------------------------------------------------------------------------
# The production payloads
# ---------------------------------------------------------------------------

#: CAPTURED — `soccer/fra.1?dates=20260903`, event `401876468`, fetched
#: 2026-09-04. The exact fixture from the bug report, trimmed to the keys the
#: parser reads; every value below is verbatim from that response, including
#: ESPN's own event id, team ids and kickoff instant.
LILLE_TOULOUSE_FULL_TIME = {
    "id": "401876468",
    "name": "Lille at Toulouse",
    "shortName": "LILL @ TOU",
    "date": "2026-09-03T18:45Z",
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
            {"homeAway": "home", "score": "0", "team": {"id": "179", "name": "Toulouse"}},
            {"homeAway": "away", "score": "1", "team": {"id": "166", "name": "Lille"}},
        ],
    }],
}

#: CAPTURED — `soccer/ned.1?dates=20260524`, event `401873227`, fetched
#: 2026-09-04. A cup tie decided on penalties: `STATUS_FINAL_PEN`, a SECOND
#: terminal name the old parser could not read. 57 of them in the census.
AJAX_UTRECHT_FINAL_PEN = {
    "id": "401873227",
    "name": "FC Utrecht at Ajax Amsterdam",
    "shortName": "UTR @ AJA",
    "date": "2026-05-24T10:15Z",
    "status": {
        "clock": 7200.0,
        "displayClock": "120'",
        "period": 5,
        "type": {
            "id": "47", "name": "STATUS_FINAL_PEN", "state": "post",
            "completed": True, "description": "Final Score - After Penalties",
            "detail": "FT-Pens", "shortDetail": "FT-Pens",
        },
    },
    "competitions": [{
        "competitors": [
            {"homeAway": "home", "score": "1", "team": {"id": "139", "name": "Ajax Amsterdam"}},
            {"homeAway": "away", "score": "1", "team": {"id": "153", "name": "FC Utrecht"}},
        ],
    }],
}

#: CAPTURED — `soccer/eng.2?dates=20260512`, event `401871356`, fetched
#: 2026-09-04. Decided in extra time: `STATUS_FINAL_AET`, the THIRD terminal
#: name. Its `detail` is "AET", a terminal period word, which is what makes it
#: the sharpest case for the no-terminal-word-on-a-live-row assertion below.
SOUTHAMPTON_MIDDLESBROUGH_FINAL_AET = {
    "id": "401871356",
    "name": "Middlesbrough at Southampton",
    "shortName": "MID @ SOU",
    "date": "2026-05-12T19:00Z",
    "status": {
        "clock": 7200.0,
        "displayClock": "120'+7'",
        "period": 4,
        "type": {
            "id": "45", "name": "STATUS_FINAL_AET", "state": "post",
            "completed": True, "description": "Final Score - After Extra Time",
            "detail": "AET", "shortDetail": "AET",
        },
    },
    "competitions": [{
        "competitors": [
            {"homeAway": "home", "score": "2", "team": {"id": "376", "name": "Southampton"}},
            {"homeAway": "away", "score": "1", "team": {"id": "369", "name": "Middlesbrough"}},
        ],
    }],
}

#: 🔴 CAPTURED — `soccer/por.1?dates=20260816`, event `401885480`, fetched
#: 2026-09-04. Must NOT settle. A postponed fixture is `state="post"` too —
#: with `completed=False`, because nothing was played.
BRAGA_GIL_VICENTE_POSTPONED = {
    "id": "401885480",
    "name": "Gil Vicente at Braga",
    "shortName": "GVFC @ SCB",
    "date": "2026-08-16T19:30Z",
    "status": {
        "clock": 0.0,
        "displayClock": "0'",
        "type": {
            "id": "6", "name": "STATUS_POSTPONED", "state": "post",
            "completed": False, "description": "Postponed",
            "detail": "Postponed", "shortDetail": "Postponed",
        },
    },
    "competitions": [{
        "competitors": [
            {"homeAway": "home", "score": "0", "team": {"id": "2994", "name": "Braga"}},
            {"homeAway": "away", "score": "0", "team": {"id": "3699", "name": "Gil Vicente"}},
        ],
    }],
}

#: 🔴 CAPTURED — `soccer/fra.1?dates=20260517`, event `746714`, fetched
#: 2026-09-04. THE HARD REFUSAL, and the reason `completed` is the load-bearing
#: half: this match was abandoned at 22', so unlike a postponement it carries a
#: real running clock and a real period. Nothing but `completed=False`
#: distinguishes it from a match that ran its course. (Its six-digit id is
#: genuine — ESPN still serves the old numbering for pre-2026-27 fra.1 rows.)
NANTES_TOULOUSE_ABANDONED = {
    "id": "746714",
    "name": "Toulouse at Nantes",
    "shortName": "TOU @ NAN",
    "date": "2026-05-17T19:00Z",
    "status": {
        "clock": 1320.0,
        "displayClock": "22'",
        "period": 1,
        "type": {
            "id": "27", "name": "STATUS_ABANDONED", "state": "post",
            "completed": False, "description": "Abandoned",
            "detail": "Abandoned", "shortDetail": "ABN",
        },
    },
    "competitions": [{
        "competitors": [
            {"homeAway": "home", "score": "0", "team": {"id": "165", "name": "Nantes"}},
            {"homeAway": "away", "score": "0", "team": {"id": "179", "name": "Toulouse"}},
        ],
    }],
}

#: CONSTRUCTED, and labelled so on purpose — this is the one fixture here that
#: is not a capture. A match IN PLAY cannot be re-fetched after the fact: the
#: census window holds no `state="in"` row, because every fixture in it has
#: since finished. The `status.type` block is ESPN's documented in-play shape
#: (`STATUS_SECOND_HALF`, id 3), and the identity is the bug report's second
#: stuck card, Celta Vigo at Real Sociedad. **Its ids are synthetic** and are
#: written in an obviously non-ESPN form so no later reader mistakes them for
#: captured values. What it is here to prove is one thing only, and that thing
#: does not depend on its identity: `state="in"` must never settle.
SOCCER_SECOND_HALF = {
    "id": "SYNTHETIC-IN-PLAY-1",
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
            {"homeAway": "home", "score": "0",
             "team": {"id": "SYNTHETIC-HOME", "name": "Real Sociedad"}},
            {"homeAway": "away", "score": "0",
             "team": {"id": "SYNTHETIC-AWAY", "name": "Celta Vigo"}},
        ],
    }],
}

#: Every terminal name the census observed, and how the fix must treat it. The
#: fixture set is checked against this table so a name cannot be added to one
#: without the other.
CENSUS_TERMINALS = {
    "STATUS_FULL_TIME": True,
    "STATUS_FINAL_PEN": True,
    "STATUS_FINAL_AET": True,
    "STATUS_POSTPONED": False,
    "STATUS_ABANDONED": False,
}

#: The three that settle, and the two that must not.
SETTLING_PAYLOADS = (
    LILLE_TOULOUSE_FULL_TIME,
    AJAX_UTRECHT_FINAL_PEN,
    SOUTHAMPTON_MIDDLESBROUGH_FINAL_AET,
)
NON_SETTLING_PAYLOADS = (
    BRAGA_GIL_VICENTE_POSTPONED,
    NANTES_TOULOUSE_ABANDONED,
)


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

    @pytest.mark.parametrize(
        "payload", SETTLING_PAYLOADS, ids=lambda p: p["status"]["type"]["name"]
    )
    def test_every_completed_terminal_name_soccer_uses_parses_as_post(
        self, client, payload
    ):
        """The census's three `completed=True` names, not just the one the bug
        report happened to land on. `STATUS_FINAL_PEN` and `STATUS_FINAL_AET`
        were equally unreadable to the old name-only parser — 64 more finished
        matches with no way off the rail — and neither was named in CERT-904's
        evidence."""
        event = client._parse_event(payload)
        assert event is not None
        assert event.status == "post", (
            f"{payload['status']['type']['name']} did not reach the settle branch"
        )

    @pytest.mark.parametrize(
        "payload", NON_SETTLING_PAYLOADS, ids=lambda p: p["status"]["type"]["name"]
    )
    def test_a_match_nobody_finished_does_not_parse_as_post(self, client, payload):
        """`state="post"` alone would stamp a Final and a 0-0 on a match nobody
        played — a false LIVE traded for a false FINAL (the CERT-752 class).

        Both real: a postponement never kicked off, and an ABANDONED match did —
        it stopped at 22' carrying a live clock and period 1, so `completed` is
        the only field that separates it from a result."""
        event = client._parse_event(payload)
        assert event is not None
        assert event.status != "post"

    def test_the_fixture_set_is_the_measured_vocabulary(self):
        """🔴 The provenance guard (`LIVE-060-EVIDENCE-PROVENANCE`). The
        original evidence asserted the refusal over `STATUS_CANCELED`, a name a
        5,672-fixture census across 34 leagues returns ZERO times. Tying the
        fixtures to the census means the next name can only be added to one by
        being added to both."""
        covered = {
            p["status"]["type"]["name"]: p["status"]["type"]["completed"]
            for p in SETTLING_PAYLOADS + NON_SETTLING_PAYLOADS
        }
        assert covered == CENSUS_TERMINALS
        assert "STATUS_CANCELED" not in covered, (
            "STATUS_CANCELED was never observed in the census — a fixture "
            "asserting over it is asserting over an invented payload"
        )

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

    @pytest.mark.parametrize(
        "payload", NON_SETTLING_PAYLOADS, ids=lambda p: p["status"]["type"]["name"]
    )
    async def test_a_match_nobody_finished_is_not_given_a_final(self, client, payload):
        """The subject is the FINAL, and that half is unchanged.

        ⚠️ **The expected status moved `live` → `suspended` (#3397), and the
        original assertion was pinning a defect.** This test's own name, message
        and second assertion are all about one thing: a match nobody played out
        must not be stamped with a result. `== "live"` was never that claim — it
        was shorthand for "the settle branch did not fire", true only because
        `live` happened to be the status `_sync` starts the row on and nothing
        in the helper then touched the column.

        Nothing touching it was the bug. Production 2026-09-05 carried event
        15291065 `status='live'` / `period='Postponed'`, drawn on the MLS page
        inside `Live Now` with a green dot; the row read live because this
        branch was open, exactly as asserted here. So the assertion is now
        written as what it means — not settled, and not live either — and the
        no-`completed_at` half below is untouched, which is what keeps the
        CERT-752 trade (a false LIVE swapped for a false FINAL) refused.
        """
        event, _stats, session = await _sync(client, payload)

        assert event.status != "completed", (
            f"{payload['shortName']} was settled — that stamps a Final and a "
            "blank score on a match nobody played out"
        )
        assert event.status == EVENT_SUSPENDED, (
            f"{payload['shortName']} reads {event.status!r} while ESPN says "
            f"{payload['status']['type']['name']} — a match that stopped "
            "without a result is being drawn in the Live Now rail (#3397)"
        )
        assert "completed_at" not in _written(session)

    @pytest.mark.parametrize(
        "payload", SETTLING_PAYLOADS, ids=lambda p: p["status"]["type"]["name"]
    )
    async def test_every_completed_terminal_closes_its_row(self, client, payload):
        """The rail loses the card for all three names, not only the one in the
        bug report — with a completion stamp in every case."""
        event, stats, session = await _sync(client, payload)

        assert event.status == "completed"
        written = _written(session)
        assert written.get("status") == "completed"
        assert written.get("completed_at") is not None
        assert stats.get("espn_completed") == 1

    async def test_no_terminal_period_word_survives_on_a_live_row(self, client):
        """The acceptance criterion as the reader states it: no card in the rail
        carries a terminal period word while its status says live.

        Stated over the payloads rather than over one of them, so a future ESPN
        vocabulary added to the fixtures above is covered without a new test.
        """
        terminal_words = {"ft", "final", "aet", "ft-pens", "full time"}
        for payload in (
            *SETTLING_PAYLOADS,
            *NON_SETTLING_PAYLOADS,
            SOCCER_SECOND_HALF,
        ):
            event, _stats, _session = await _sync(client, payload)
            period = (event.period or "").strip().lower()
            if period in terminal_words:
                assert event.status != "live", (
                    f"{payload['shortName']}: period={event.period!r} on a live row"
                )
