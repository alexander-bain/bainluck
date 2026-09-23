"""#6280 — an anchored row past the 48h settle window is stranded for good.

WHAT A USER SAW, production 2026-09-15 02:0xZ at 390 px (LOOKs saved at
`artifacts/live-252/`), on two marquee college-football pages:

    /events/15175988  Michigan State @ Michigan
        "No result reported" · "Sep 4, 2026 · 3:30 PM PDT" · hero "No price"
        over "Opened 87% - 13%", a "Next update: 108" ticker implying it is
        live, and — worst — a Win Probability chart drawing a FLAT 87% line
        across a full hour, with Projected Point Margin flat at +18 over the
        same hour. An hour of in-game history for a game that does not kick
        off until November 7.

    /events/14595362  SMU @ Florida State, six days after the final
        hero serves a live-shaped 6% - 94%, score 17-24, caption "No result
        reported · last score 17-24", chart ending at "11:00 - 4th Quarter" —
        while Additional Markets on the SAME page print "SMU Won" twice. The
        props are graded and the game is not. The true final was SMU 27-24, so
        the score on the page is also wrong.

Alex's 2026-09-14 16:14 PT directive names this class exactly: "Top-tier (e.g.
NFL) unknown upcoming/live/completed is a defect", and "confine in-game
win-probability/score-differential charts to actual game duration". The chart
defect here is reached THROUGH the state defect, which is what this ship fixes.

── THE MECHANISM ─────────────────────────────────────────────────────────────

`_settle_authority_stragglers` (#4652) asks about the right board day, but only
for rows inside `AUTHORITY_STRAGGLER_LOOKBACK` (48h). The other drain,
`suspended` -> `retired`, is keyed on the row being UNREACHABLE — no provider id
at all (`suspended_row_is_unreachable`). An anchored row past 48h is therefore
too anchored to retire and too old to settle, and NOTHING else selects it.

MEASURED on production 2026-09-15 02:2xZ (`sql_fingerprint` 0c6d56326c5650d4):
the entire stranded population is SEVEN rows in five (sport, board day) groups,
all 7-30 days old. There is no ancient tail, and no `live` rows in it at all.

── CAPTURED FROM ESPN, per specimen, by id (standing notice 26) ──────────────

Every board below is the real response to
`site.api.espn.com/.../scoreboard?dates=<the day our row carries>` — the exact
URL shape `ESPNAPIService.get_scoreboard` builds — read 2026-09-15 02:3xZ:

    football/college-football/20260903  401858424  post completed=True Final
                                                   ILL 42 - UAB 23
    football/college-football/20260907  401858212  post completed=True Final
                                                   FSU 24 - SMU 27
    soccer/usa.1/20260905               761783     post completed=True FT
                                                   POR 5 - MIN 4
    soccer/usa.1/20260905               761784     post completed=True FT
                                                   VAN 1 - STL 3

    football/college-football/20260904  401858511  NOT ON BOARD (8 events)
    football/college-football/20260905  401856719  NOT ON BOARD (68 events)
    soccer/usa.1/20260905               761773     NOT ON BOARD (13 events)

The split IS the design. Four settle. The other three — Michigan State @
Michigan (ESPN files it under 11/7), Auburn @ Georgia (10/17) and the FC
Cincinnati postponement (10/21) — are ABSENT from the board for the day our row
carries, so the pass is a no-op on precisely the rows that must not be settled.
They are refused a step before the settle door, by absence rather than by
judgement. `test_the_three_that_must_not_settle_come_out_untouched` is that arm
and it must stay red-able: it is what fails if anyone ever reaches for a name
match here (gotcha #32, CERT-752's class).

── AND WHY THE ARM NEEDS A CLOCK OF ITS OWN ──────────────────────────────────

Those same three requalify on EVERY pass and can never resolve. On a 60s beat a
naively widened window re-asks five boards forever (~7,200 extra ESPN requests a
day, against a task whose p95 already overruns its period at 111.5s) for a stock
that will never move; and a stalest-first queue ordered on `commence_time` parks
them at the head of it forever, starving the settleable rows behind them. So the
sort key is one THE WORK ADVANCES — when we last ASKED — written whether or not
the ask settled anything, including when the board came back dark.
`test_the_three_that_can_never_settle_do_not_starve_the_queue` is that arm.
"""
from datetime import datetime, timedelta, timezone

import pytest

from app.services.espn_api import ESPNEvent
from app.tasks.espn_sync import (
    AUTHORITY_DEEP_STRAGGLER_REASK,
    AUTHORITY_STRAGGLER_LOOKBACK,
    DEEP_STRAGGLER_ASKED_KEY,
    MAX_DEEP_STRAGGLER_BOARDS_PER_PASS,
    _deep_straggler_asked_at,
    _settle_deep_authority_stragglers,
)
from app.utils.espn_helpers import update_event_fields_from_espn

#: The instant the population above was measured.
NOW = datetime(2026, 9, 15, 2, 30, tzinfo=timezone.utc)


class _FakeSport:
    def __init__(self, key):
        self.key = key


class _FakeEvent:
    """Only the columns the deep arm and the settle door actually read."""

    def __init__(
        self, id, espn_id, home, away, commence_time, *,
        status="suspended", home_score=None, away_score=None,
        sport_key="americanfootball_ncaaf", asked_at=None, period=None,
    ):
        self.id = id
        self.espn_id = espn_id
        self.home_team_name = home
        self.away_team_name = away
        self.status = status
        self.commence_time = commence_time
        self.completed_at = None
        self.home_score = home_score
        self.away_score = away_score
        self.sport = _FakeSport(sport_key)
        self.win_probability_sources = (
            {DEEP_STRAGGLER_ASKED_KEY: asked_at} if asked_at else {}
        )
        # Fields the settle door touches but this suite does not assert on.
        self.period = period
        self.game_clock = None
        self.broadcast = None
        self.llm_importance = None
        self.espn_win_prob_home = None


class _FakeScalars:
    def __init__(self, rows):
        self._rows = rows

    def all(self):
        return self._rows


class _FakeResult:
    #: #6056 / CERT-2829: the live-state compare-and-write reads `rowcount` off
    #: its result, and its ABSENCE is not a loud failure — the per-row
    #: try/except of gotcha #42 swallows the AttributeError and the row simply
    #: stays `suspended`, which reads as a behavioural regression rather than as
    #: a broken rail.
    rowcount = 1

    def __init__(self, rows):
        self._rows = rows

    def scalars(self):
        return _FakeScalars(self._rows)


class _FakeSession:
    """Absorbs the arm's one SELECT and records every Core UPDATE it sends."""

    def __init__(self, rows):
        self._rows = rows
        self.updates = []
        self.selects = []

    async def execute(self, stmt, *args, **kwargs):
        text = str(stmt)
        if text.lstrip().upper().startswith("SELECT"):
            self.selects.append((text, stmt.compile().params))
            return _FakeResult(self._rows)
        self.updates.append((text, stmt.compile().params))
        return _FakeResult([])

    async def flush(self):
        pass

    def add(self, obj):
        pass

    def stamped_sources(self):
        """Every `win_probability_sources` value written by a Core UPDATE."""
        return [
            params["win_probability_sources"]
            for text, params in self.updates
            if "win_probability_sources" in params
        ]


class _FakeESPN:
    """Serves a board per (sport, date). Records exactly what was asked for."""

    def __init__(self, boards, dark=False):
        self._boards = boards
        self._dark = dark
        self.asked = []

    async def get_scoreboard(self, sport_key, date=None):
        self.asked.append((sport_key, date))
        if self._dark:
            return None
        return self._boards.get((sport_key, date), [])

    async def close(self):
        return None


def _fixture(espn_id, home_score, away_score, detail="Final"):
    """One row of a CAPTURED ESPN board, finished."""
    return ESPNEvent(
        espn_id=espn_id,
        name=f"fixture {espn_id}",
        short_name=None,
        date=NOW - timedelta(days=8),
        status="post",
        status_detail=detail,
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


# ── THE SEVEN, exactly as production holds them ──────────────────────────────

def _illinois():
    return _FakeEvent(14793404, "401858424", "Illinois Fighting Illini",
                      "UAB Blazers", datetime(2026, 9, 4, 1, 0, tzinfo=timezone.utc),
                      home_score=42, away_score=23)


def _fsu_smu():
    """Our row: FSU 17 - SMU 24. The real final was FSU 24 - SMU 27."""
    return _FakeEvent(14595362, "401858212", "Florida State Seminoles",
                      "SMU Mustangs", datetime(2026, 9, 7, 23, 30, tzinfo=timezone.utc),
                      home_score=17, away_score=24, period="11:00 - 4th Quarter")


def _portland():
    return _FakeEvent(15291072, "761783", "Portland Timbers",
                      "Minnesota United FC",
                      datetime(2026, 9, 6, 2, 30, tzinfo=timezone.utc),
                      home_score=3, away_score=2, period="49'",
                      sport_key="soccer_usa_mls")


def _vancouver():
    return _FakeEvent(15291073, "761784", "Vancouver Whitecaps FC",
                      "St. Louis City SC",
                      datetime(2026, 9, 6, 2, 30, tzinfo=timezone.utc),
                      home_score=1, away_score=3, period="54'",
                      sport_key="soccer_usa_mls")


def _michigan():
    """Has NOT been played. ESPN files it under 11/7; our row says 9/4."""
    return _FakeEvent(15175988, "401858511", "Michigan Wolverines",
                      "Michigan State Spartans",
                      datetime(2026, 9, 4, 22, 30, tzinfo=timezone.utc))


def _georgia():
    """Has NOT been played. ESPN files it under 10/17; our row says 9/5."""
    return _FakeEvent(14870016, "401856719", "Georgia Bulldogs", "Auburn Tigers",
                      datetime(2026, 9, 5, 19, 0, tzinfo=timezone.utc))


def _cincinnati():
    """A genuine postponement, moved to an October board. Must stay unsettled."""
    return _FakeEvent(15291065, "761773", "FC Cincinnati", "D.C. United",
                      datetime(2026, 9, 6, 1, 31, tzinfo=timezone.utc),
                      home_score=0, away_score=0, period="Postponed",
                      sport_key="soccer_usa_mls")


#: CAPTURED. Keyed the way `get_scoreboard` is called: (sport_key, board day).
#: Note what is NOT here — 401858511, 401856719 and 761773 are absent from the
#: boards for the days our rows carry, exactly as ESPN served them.
BOARDS = {
    ("americanfootball_ncaaf", "20260903"): [_fixture("401858424", 42, 23)],
    ("americanfootball_ncaaf", "20260904"): [_fixture("401999001", 17, 10)],
    ("americanfootball_ncaaf", "20260905"): [_fixture("401999002", 31, 28)],
    ("americanfootball_ncaaf", "20260907"): [_fixture("401858212", 24, 27)],
    ("soccer_usa_mls", "20260905"): [
        _fixture("761783", 5, 4, detail="FT"),
        _fixture("761784", 1, 3, detail="FT"),
    ],
}


async def _run(rows, boards=BOARDS, dark=False, now=NOW):
    session = _FakeSession(rows)
    espn = _FakeESPN(boards, dark=dark)
    stats = {"authority_dark_sports": 0, "errors": []}
    await _settle_deep_authority_stragglers(
        session, espn, now, stats, update_event_fields_from_espn
    )
    return session, espn, stats


# ── THE SHIP ─────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_the_four_finals_past_the_window_are_settled():
    """The population nothing has selected since it aged out of 48h."""
    rows = [_illinois(), _fsu_smu(), _portland(), _vancouver()]
    _session, _espn, stats = await _run(rows)

    assert [e.status for e in rows] == ["completed"] * 4
    assert stats["deep_straggler_settled"] == 4
    # Reported beside the counter, so a 0 can be told from "nothing selected"
    # (gotcha #53).
    assert stats["deep_straggler_candidates"] == 4
    assert stats["deep_straggler_eligible"] == 4


@pytest.mark.asyncio
async def test_the_wrong_score_on_the_marquee_page_is_corrected_too():
    """The page printed 17-24 six days after a 24-27 final."""
    row = _fsu_smu()
    session, _espn, _stats = await _run([row])

    # Read off the statement: since #6056 / CERT-2829 the live-state columns are
    # SENT by a conditional UPDATE rather than assigned, and this suite drives
    # the pass against a recording session rather than a database.
    written = {}
    for _text, params in session.updates:
        written.update(params)
    assert written["home_score"] == 24, "17 on the card, 24 in reality"
    assert written["away_score"] == 27, "24 on the card, 27 in reality"


@pytest.mark.asyncio
async def test_the_three_that_must_not_settle_come_out_untouched():
    """THE CONTROL. Two unplayed marquee games and a real postponement.

    ESPN files all three under a LATER board day than our row carries, so the
    board this pass fetches does not contain their id. Nothing settles them —
    and nothing may, since two of the three have not been played at all. This is
    the arm that goes red if anyone ever reaches for a name match: "Michigan
    Wolverines" is on plenty of boards.
    """
    rows = [_michigan(), _georgia(), _cincinnati()]
    _session, espn, stats = await _run(rows)

    assert [e.status for e in rows] == ["suspended"] * 3
    assert stats["deep_straggler_settled"] == 0
    # It did ASK — the boards were fetched and answered. The rows simply were
    # not on them, which is the difference between "refused" and "not reached".
    assert stats["deep_straggler_boards_fetched"] == 3
    assert stats["deep_straggler_candidates"] == 3


@pytest.mark.asyncio
async def test_the_postponement_survives_even_when_it_is_on_its_own_board():
    """Belt and braces: absence is not the ONLY thing protecting 15291065.

    The row above is safe because ESPN moved it off the board. If ESPN ever
    serves it on the day we ask about, the settle door must still refuse it —
    `espn_terminal_state` requires completed=True, and a postponement is not.
    """
    row = _cincinnati()
    postponed = ESPNEvent(
        espn_id="761773", name="postponed", short_name=None,
        date=NOW - timedelta(days=9), status="STATUS_POSTPONED",
        status_detail="Postponed", period=None, clock=None,
        home_team=None, away_team=None, home_score=0, away_score=0,
        venue=None, broadcasts=[], home_win_probability=None,
        stopped_without_result=True,
    )
    _session, _espn, stats = await _run(
        [row], boards={("soccer_usa_mls", "20260905"): [postponed]}
    )

    assert row.status == "suspended"
    assert row.completed_at is None
    assert stats["deep_straggler_settled"] == 0


# ── DISJOINT FROM THE SHALLOW ARM ────────────────────────────────────────────

@pytest.mark.asyncio
async def test_this_arm_selects_the_exact_complement_of_the_shallow_window():
    """The two arms partition the population on one boundary; they never share.

    A row the 48h pass is already working must not be pulled into a six-hour
    cooldown by this one, and a board it has already fetched must not be fetched
    twice in the same pass.

    ⚠️ THIS IS ASSERTED ON THE STATEMENT, and it has to be. The boundary lives in
    the SELECT's WHERE clause, so the only component that can enforce it is the
    database — a recording session hands back whatever rows it was given no
    matter what it was asked. A test that fed this arm a fresh row and asserted
    "no board was fetched" would be asserting a filter the rig cannot apply, and
    would pass for the wrong reason the moment the clause was deleted.
    """
    session = _FakeSession([])
    await _settle_deep_authority_stragglers(
        session, _FakeESPN(BOARDS), NOW, {"authority_dark_sports": 0, "errors": []},
        update_event_fields_from_espn,
    )

    assert len(session.selects) == 1
    text, params = session.selects[0]
    # STRICTLY less-than the shallow arm's floor: its window is
    # `>= now - LOOKBACK`, so `< now - LOOKBACK` is the exact complement.
    assert "events.commence_time <" in text, (
        "the deep arm no longer excludes the shallow arm's window"
    )
    boundary = NOW - AUTHORITY_STRAGGLER_LOOKBACK
    assert boundary in params.values(), (
        f"the deep arm's floor is not the shallow arm's ceiling ({boundary})"
    )


# ── THE LIVELOCK, which is the reason the stamp exists ───────────────────────

@pytest.mark.asyncio
async def test_the_three_that_can_never_settle_do_not_starve_the_queue():
    """THE ANTI-LIVELOCK ARM.

    Ordered on `commence_time`, the three permanently-stuck rows are the three
    OLDEST in the pile, so an oldest-first queue with a per-pass budget of 4
    boards hands them three of its four slots on every pass, forever. Ordered on
    when we last ASKED, they are asked once, stamped, and fall behind everything
    that has not been asked yet.
    """
    stuck = [_michigan(), _georgia(), _cincinnati()]
    settleable = [_illinois(), _fsu_smu(), _portland(), _vancouver()]
    rows = stuck + settleable

    # Pass one: five groups, four slots. Which four does it spend them on?
    session, espn, stats = await _run(rows)
    assert stats["deep_straggler_groups"] == 5
    assert len(espn.asked) == MAX_DEEP_STRAGGLER_BOARDS_PER_PASS

    # Every row it asked about now carries a stamp — including the ones that
    # settled nothing. That is the queue advancing.
    assert stats["deep_straggler_asked"] > 0

    # Pass two, one minute later. The group that missed out must now be first,
    # and nothing that was already asked may take a slot from it.
    later = NOW + timedelta(minutes=1)
    unsettled = [e for e in rows if e.status == "suspended"]
    _s2, espn2, stats2 = await _run(unsettled, now=later)

    asked_twice = set(espn.asked) & set(espn2.asked)
    assert not asked_twice, (
        "a group already asked took a slot from one that has never been asked "
        f"— {asked_twice}"
    )
    # And by the end of pass two every settleable row is settled.
    assert all(e.status == "completed" for e in settleable), (
        "a settleable row was starved by rows that can never settle"
    )


@pytest.mark.asyncio
async def test_a_row_asked_recently_is_left_alone_until_the_cooldown_expires():
    """Steady state is zero requests, which is what makes the width affordable."""
    recent = _michigan()
    recent.win_probability_sources = {
        DEEP_STRAGGLER_ASKED_KEY: (NOW - timedelta(hours=1)).isoformat()
    }
    _session, espn, stats = await _run([recent])

    assert espn.asked == []
    assert stats["deep_straggler_candidates"] == 1, "it was selected"
    assert stats["deep_straggler_eligible"] == 0, "and then held by the cooldown"


@pytest.mark.asyncio
async def test_the_cooldown_expires_and_the_row_is_asked_again():
    """The complement of the test above — together they pin the boundary."""
    stale = _michigan()
    stale.win_probability_sources = {
        DEEP_STRAGGLER_ASKED_KEY: (
            NOW - AUTHORITY_DEEP_STRAGGLER_REASK - timedelta(minutes=1)
        ).isoformat()
    }
    _session, espn, stats = await _run([stale])

    assert espn.asked == [("americanfootball_ncaaf", "20260904")]
    assert stats["deep_straggler_eligible"] == 1


@pytest.mark.asyncio
async def test_a_never_asked_row_jumps_ahead_of_one_already_asked():
    """A freshly stranded row is the reader-visible one; it does not queue."""
    asked = _michigan()
    asked.win_probability_sources = {
        DEEP_STRAGGLER_ASKED_KEY: (NOW - timedelta(days=1)).isoformat()
    }
    never = _fsu_smu()
    _session, espn, _stats = await _run([asked, never])

    assert espn.asked[0] == ("americanfootball_ncaaf", "20260907"), (
        "the never-asked row did not go first"
    )


@pytest.mark.asyncio
async def test_a_dark_board_still_advances_the_queue():
    """Otherwise a persistently dark sport wedges the head of it forever.

    Nothing is settled on silence (#3473) — that is the point of the dark path —
    but the ASK still happened and the queue has to record it.
    """
    rows = [_michigan(), _fsu_smu()]
    session, espn, stats = await _run(rows, dark=True)

    assert stats["deep_straggler_settled"] == 0
    assert stats["deep_straggler_boards_fetched"] == 0
    assert stats["authority_dark_sports"] == 2
    assert len(espn.asked) == 2
    assert len(session.stamped_sources()) == 2, "a dark board froze the queue"


@pytest.mark.asyncio
async def test_the_stamp_merges_into_what_the_settle_door_just_wrote():
    """The stamp shares `win_probability_sources` with the door, so order binds.

    `update_event_fields_from_espn` writes that same JSONB at three sites and
    re-assigns the in-memory value after each Core UPDATE. If the stamp were
    taken BEFORE the row loop it would write back a dict the door had already
    moved on from, silently dropping the probability the door had just stored.
    Driven with a door that writes a key and leaves the row unsettled, which is
    the only shape in which both writes land on one row.
    """
    row = _michigan()

    async def _door_writes_a_probability(
        session, event, matched, claimed, stats, *, allow_unstarted=False
    ):
        merged = dict(event.win_probability_sources or {})
        merged["espn"] = 0.61
        event.win_probability_sources = merged  # what espn_helpers does

    session = _FakeSession([row])
    espn = _FakeESPN(
        {("americanfootball_ncaaf", "20260904"): [_fixture("401858511", 0, 0)]}
    )
    stats = {"authority_dark_sports": 0, "errors": []}
    await _settle_deep_authority_stragglers(
        session, espn, NOW, stats, _door_writes_a_probability
    )

    stamped = session.stamped_sources()
    assert len(stamped) == 1, "the unsettled row was not stamped"
    assert stamped[0][DEEP_STRAGGLER_ASKED_KEY] == NOW.isoformat()
    assert stamped[0]["espn"] == 0.61, (
        "the stamp clobbered the probability the settle door had just written"
    )


@pytest.mark.asyncio
async def test_a_settled_row_is_not_stamped():
    """It has left the candidate states, so a stamp on it is residue."""
    row = _fsu_smu()
    session, _espn, _stats = await _run([row])

    assert row.status == "completed"
    assert session.stamped_sources() == []


@pytest.mark.asyncio
async def test_the_stamp_is_written_by_a_core_update_not_an_attribute():
    """Gotcha #4 — an in-place JSONB assignment is silently dropped."""
    row = _michigan()
    session, _espn, _stats = await _run([row])

    stamped = session.stamped_sources()
    assert len(stamped) == 1
    assert stamped[0][DEEP_STRAGGLER_ASKED_KEY] == NOW.isoformat()
    # A NEW dict, not the row's own object mutated in place.
    update_texts = [t for t, p in session.updates if "win_probability_sources" in p]
    assert update_texts and update_texts[0].lstrip().upper().startswith("UPDATE")


# ── THE STAMP READER, whose defaults all point the same way ──────────────────

def test_an_absent_stamp_reads_as_never_asked():
    assert _deep_straggler_asked_at(_michigan(), NOW) is None


def test_a_garbled_stamp_reads_as_never_asked_rather_than_parking_the_row():
    row = _michigan()
    row.win_probability_sources = {DEEP_STRAGGLER_ASKED_KEY: "not a timestamp"}
    assert _deep_straggler_asked_at(row, NOW) is None


@pytest.mark.asyncio
async def test_a_future_stamp_does_not_hold_the_row_out_of_the_queue():
    """A clock that ran backwards must not cost a settleable row its place."""
    row = _michigan()
    row.win_probability_sources = {
        DEEP_STRAGGLER_ASKED_KEY: (NOW + timedelta(days=30)).isoformat()
    }
    _session, espn, stats = await _run([row])

    assert stats["deep_straggler_eligible"] == 1
    assert espn.asked == [("americanfootball_ncaaf", "20260904")]


def test_a_naive_stamp_is_read_as_utc_rather_than_crashing():
    row = _michigan()
    row.win_probability_sources = {
        DEEP_STRAGGLER_ASKED_KEY: "2026-09-15T01:00:00"
    }
    asked = _deep_straggler_asked_at(row, NOW)
    assert asked == datetime(2026, 9, 15, 1, 0, tzinfo=timezone.utc)


# ── THE BUDGET ───────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_the_budget_caps_the_boards_one_pass_may_fetch():
    """The task already overruns its own 60s period at p95 111.5s."""
    rows = [_illinois(), _fsu_smu(), _portland(), _vancouver(),
            _michigan(), _georgia(), _cincinnati()]
    _session, espn, stats = await _run(rows)

    assert stats["deep_straggler_groups"] == 5, "five board days in the pile"
    assert len(espn.asked) == MAX_DEEP_STRAGGLER_BOARDS_PER_PASS
    assert MAX_DEEP_STRAGGLER_BOARDS_PER_PASS < 5, (
        "this test is vacuous unless the budget actually bites"
    )


@pytest.mark.asyncio
async def test_an_unmapped_sport_is_never_asked_about():
    """`ESPN_SPORT_MAPPING` is the reach boundary; this arm does not widen it."""
    row = _fsu_smu()
    row.sport = _FakeSport("cricket_the_hundred")
    _session, espn, stats = await _run([row])

    assert espn.asked == []
    assert stats["deep_straggler_candidates"] == 1
    assert stats["deep_straggler_eligible"] == 0


# ── THE ARM CANNOT COST THE PASS ITS RUN ─────────────────────────────────────

@pytest.mark.asyncio
async def test_one_bad_row_does_not_wipe_the_pass(monkeypatch):
    """Gotcha #42, asserted in the direction that matters: siblings survive."""
    rows = [_illinois(), _fsu_smu()]
    calls = {"n": 0}

    # `allow_unstarted` is part of the door's contract (#5501), so a stand-in
    # takes it and hands it on. A double that omitted it would raise TypeError
    # into the per-row `except` and read as the bad row this test injects.
    async def _explode_once(
        session, event, matched, claimed, stats, *, allow_unstarted=False
    ):
        calls["n"] += 1
        if calls["n"] == 1:
            raise RuntimeError("boom")
        return await update_event_fields_from_espn(
            session, event, matched, claimed, stats,
            allow_unstarted=allow_unstarted,
        )

    session = _FakeSession(rows)
    espn = _FakeESPN(BOARDS)
    stats = {"authority_dark_sports": 0, "errors": []}
    await _settle_deep_authority_stragglers(
        session, espn, NOW, stats, _explode_once
    )

    assert stats["deep_straggler_settled"] == 1, "the healthy sibling settled"
    assert any("deep_straggler_update_" in e for e in stats["errors"])
