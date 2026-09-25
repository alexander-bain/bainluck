"""#6280, second half — the stranded row that was never LATE, only MISDATED.

WHAT A USER SEES, production 2026-09-15 04:2xZ at 390 px (LOOK saved at
`artifacts/live-255/msu-michigan-before.png`), on `/events/15175988`:

    "Sep 4, 2026 - 3:30 PM PDT" · "No result reported" · hero "No price" over
    "Opened 87% - 13%", and under it a **Win Probability chart on its "Since
    Start" tab** drawing a FLAT 87% line from 3:30 PM to 5:08 PM, with
    Projected Point Margin flat at +18 across the same fake hour.

Michigan State @ Michigan kicks off on **November 7**. The page renders an hour
of in-game history for a game that has not been played.

── WHY THE FIRST HALF OF #6280 COULD NOT REACH IT ───────────────────────────

`_settle_deep_authority_stragglers` (shipped `1afd9e694`) reaches the stranded
population by asking the BOARD DAY our row carries. For these rows the board day
IS the defect: ESPN files them under their real dates, so the September board we
fetch does not contain their id and the settle pass is a deliberate no-op. That
arm's own docstring names all three and says so.

── CAPTURED FROM ESPN BY ID, 2026-09-15 04:3xZ (standing notice 26) ─────────

`site.api.espn.com/.../summary?event=<id>` — the URL shape `get_event` builds.
All three answer `STATUS_SCHEDULED`, `state=pre`, `completed=false`, both
competitor scores absent, team names matching our row exactly:

    football/college-football  401858511  2026-11-07T05:00Z  we store 09-04
                               Michigan Wolverines / Michigan State Spartans
    football/college-football  401856719  2026-10-17T04:00Z  we store 09-05
                               Georgia Bulldogs / Auburn Tigers
    soccer/usa.1               761773     2026-10-21T23:00Z  we store 09-06
                               FC Cincinnati / D.C. United

── WHY THE ARM WRITES THE STATE AND NOT ONLY THE CLOCK ──────────────────────

`reconcile_anchor_schedule` writes `commence_time` alone, and for its population
that is right. Here it would invent a state with no precedent: production
carries ZERO `suspended` rows with a future kickoff (measured 2026-09-15
04:4xZ), so a clock-only move would leave these three as the only ones — still
"No result reported", still charted as a game that started, because the web
chart cuts on `commence_time` and `suspended` is what selects the "Since Start"
tab. The authority's answer is one consistent fact and the row is made to say
it, or nothing.

`test_a_past_authority_start_is_refused` is the arm that must stay red-able: it
is what fails if anyone ever drops the future-start gate, which is the only
thing standing between this rail and moving a PLAYED game's clock forward.
"""
from datetime import datetime, timedelta, timezone

import pytest

from app.services.espn_api import ESPNEvent, ESPNTeam
from app.tasks.espn_sync import (
    AUTHORITY_STRAGGLER_LOOKBACK,
    AUTHORITY_UNSTARTED_REASK,
    MAX_UNSTARTED_RECOVERY_ASKS_PER_PASS,
    UNSTARTED_RECOVERY_ASKED_KEY,
    _recover_unstarted_authority_fixtures,
    _unstarted_recovery_asked_at,
)

#: The instant the population above was measured.
NOW = datetime(2026, 9, 15, 4, 30, tzinfo=timezone.utc)

#: The three real specimens, as (event id, espn id, home, away, our clock,
#: ESPN's real start, sport key).
MSU_AT_MICHIGAN = (
    15175988, "401858511", "Michigan Wolverines", "Michigan State Spartans",
    datetime(2026, 9, 4, 22, 30, tzinfo=timezone.utc),
    datetime(2026, 11, 7, 5, 0, tzinfo=timezone.utc),
    "americanfootball_ncaaf",
)
AUBURN_AT_GEORGIA = (
    14870016, "401856719", "Georgia Bulldogs", "Auburn Tigers",
    datetime(2026, 9, 5, 19, 0, tzinfo=timezone.utc),
    datetime(2026, 10, 17, 4, 0, tzinfo=timezone.utc),
    "americanfootball_ncaaf",
)
DC_AT_CINCINNATI = (
    15291065, "761773", "FC Cincinnati", "D.C. United",
    datetime(2026, 9, 6, 1, 31, tzinfo=timezone.utc),
    datetime(2026, 10, 21, 23, 0, tzinfo=timezone.utc),
    "soccer_usa_mls",
)


class _FakeSport:
    def __init__(self, key):
        self.key = key


class _FakeEvent:
    """Only the columns this arm reads or writes."""

    def __init__(
        self, id, espn_id, home, away, commence_time, *,
        status="suspended", sport_key="americanfootball_ncaaf",
        asked_at=None, home_score=None, away_score=None, period=None,
        game_clock=None, commence_time_source="espn", sources=None,
    ):
        self.id = id
        self.espn_id = espn_id
        self.home_team_name = home
        self.away_team_name = away
        self.home_team_normalized = None
        self.away_team_normalized = None
        self.home_team_alt_names = None
        self.away_team_alt_names = None
        self.status = status
        self.commence_time = commence_time
        self.commence_time_source = commence_time_source
        self.completed_at = None
        self.home_score = home_score
        self.away_score = away_score
        self.period = period
        self.game_clock = game_clock
        self.sport = _FakeSport(sport_key)
        sources = dict(sources or {})
        if asked_at:
            sources[UNSTARTED_RECOVERY_ASKED_KEY] = asked_at
        self.win_probability_sources = sources


class _FakeScalars:
    def __init__(self, rows):
        self._rows = rows

    def all(self):
        return self._rows


class _FakeResult:
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

    async def execute(self, stmt, *args, **kwargs):
        text = str(stmt)
        if text.lstrip().upper().startswith("SELECT"):
            return _FakeResult(self._rows)
        self.updates.append((text, stmt.compile().params))
        return _FakeResult([])

    async def flush(self):
        pass

    def recoveries(self):
        """Every Core UPDATE that moved a clock — the repair write."""
        return [p for _t, p in self.updates if "commence_time" in p]

    def stamps(self):
        """Every Core UPDATE that wrote the queue stamp."""
        return [
            p for _t, p in self.updates if "win_probability_sources" in p
        ]


class _FakeESPN:
    """Answers `get_event` by (sport_key, espn_id). Records what was asked."""

    def __init__(self, answers, raises=False):
        self._answers = answers
        self._raises = raises
        self.asked = []

    async def get_event(self, sport_key, espn_id):
        self.asked.append((sport_key, espn_id))
        if self._raises:
            raise RuntimeError("ESPN blew up")
        return self._answers.get((sport_key, espn_id))

    async def close(self):
        return None


def _team(display_name):
    return ESPNTeam(
        espn_id="t", name=display_name, abbreviation=None,
        display_name=display_name, short_name=None, nickname=None,
        primary_color=None, secondary_color=None, logo_url=None,
        logo_url_dark=None, record=None,
    )


def _scheduled(espn_id, home, away, starts_at, *, home_score=None,
               away_score=None, status="scheduled"):
    """A CAPTURED `summary?event=` answer: unplayed, in the future."""
    return ESPNEvent(
        espn_id=espn_id,
        name=f"{away} at {home}",
        short_name=None,
        date=starts_at,
        status=status,
        status_detail="Scheduled",
        period=None,
        clock=None,
        home_team=_team(home),
        away_team=_team(away),
        home_score=home_score,
        away_score=away_score,
        venue=None,
        broadcasts=[],
        home_win_probability=None,
    )


def _row(spec, **kwargs):
    event_id, espn_id, home, away, our_clock, _real, sport_key = spec
    kwargs.setdefault("sport_key", sport_key)
    return _FakeEvent(event_id, espn_id, home, away, our_clock, **kwargs)


def _answer(spec, **kwargs):
    _id, espn_id, home, away, _our, real_start, sport_key = spec
    return {(sport_key, espn_id): _scheduled(
        espn_id, home, away, kwargs.pop("starts_at", real_start), **kwargs
    )}


async def _run(rows, answers, *, now=NOW, raises=False):
    session = _FakeSession(rows)
    espn = _FakeESPN(answers, raises=raises)
    stats = {"errors": []}
    await _recover_unstarted_authority_fixtures(session, espn, now, stats)
    return session, espn, stats


# ══ THE SHIP ═════════════════════════════════════════════════════════════════


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "spec", [MSU_AT_MICHIGAN, AUBURN_AT_GEORGIA, DC_AT_CINCINNATI],
    ids=["msu_at_michigan", "auburn_at_georgia", "dc_united_at_cincinnati"],
)
async def test_each_real_specimen_is_restored_to_its_true_kickoff(spec):
    """The user-visible ship, one specimen at a time, on captured ESPN data."""
    session, espn, stats = await _run([_row(spec)], _answer(spec))

    assert stats["unstarted_recovery_recovered"] == 1
    (written,) = session.recoveries()
    assert written["commence_time"] == spec[5]
    assert written["status"] == "scheduled"
    assert written["commence_time_source"] == "espn"
    assert espn.asked == [(spec[6], spec[1])]


@pytest.mark.asyncio
async def test_the_in_game_residue_is_cleared_with_the_clock():
    """The postponement carries 0-0 and `Postponed`; a future fixture has neither.

    Leaving them would trade one visible lie for another — a scheduled game
    showing a 0-0 scoreline.
    """
    row = _row(DC_AT_CINCINNATI, home_score=0, away_score=0, period="Postponed",
               game_clock="0'")
    session, _espn, _stats = await _run([row], _answer(DC_AT_CINCINNATI))

    (written,) = session.recoveries()
    assert written["home_score"] is None
    assert written["away_score"] is None
    assert written["period"] is None
    assert written["game_clock"] is None
    # The in-memory row is NOT asserted here: the write goes through
    # `write_row_if_unmoved`, whose statement is ORM-enabled, so SQLAlchemy's
    # `synchronize_session="auto"` updates the instance itself. A fake session
    # cannot do that, and hand-mirroring in the arm would be the double-write
    # `write_row_if_unmoved` documents against. The real behaviour is held up by
    # that helper's own suite, not by this fake.


@pytest.mark.asyncio
async def test_all_three_specimens_drain_in_one_pass():
    """The measured stock is three and the per-pass budget is four."""
    specs = [MSU_AT_MICHIGAN, AUBURN_AT_GEORGIA, DC_AT_CINCINNATI]
    answers = {}
    for spec in specs:
        answers.update(_answer(spec))
    session, _espn, stats = await _run([_row(s) for s in specs], answers)

    assert stats["unstarted_recovery_recovered"] == 3
    assert len(session.recoveries()) == 3


# ══ THE FOUR GATES ═══════════════════════════════════════════════════════════


@pytest.mark.asyncio
async def test_no_answer_writes_nothing_but_still_advances_the_queue():
    """Gate 1. `get_event` returns None for a 404 AND for a dark authority.

    Neither is evidence about the fixture (gotcha #53), so nothing is written —
    but the ask HAPPENED, so the queue must move or a dark night starves every
    row behind this one forever.
    """
    session, _espn, stats = await _run([_row(MSU_AT_MICHIGAN)], {})

    assert stats["unstarted_recovery_no_answer"] == 1
    assert stats["unstarted_recovery_recovered"] == 0
    assert session.recoveries() == []
    assert len(session.stamps()) == 1


@pytest.mark.asyncio
async def test_an_authority_answer_carrying_a_score_is_refused():
    """Gate 2. A fixture with a score has been played, whatever its status says."""
    answers = _answer(MSU_AT_MICHIGAN, home_score=21, away_score=17)
    session, _espn, stats = await _run([_row(MSU_AT_MICHIGAN)], answers)

    assert stats["unstarted_recovery_recovered"] == 0
    assert session.recoveries() == []


@pytest.mark.asyncio
async def test_a_past_authority_start_is_refused():
    """Gate 3 — THE SAFETY GATE. Drop it and this rail hides played games.

    If the anchor named a game that already kicked off, writing its start
    forward would take a row a reader can see and push it into the future.
    """
    answers = _answer(MSU_AT_MICHIGAN, starts_at=NOW - timedelta(hours=3))
    session, _espn, stats = await _run([_row(MSU_AT_MICHIGAN)], answers)

    assert stats["unstarted_recovery_recovered"] == 0
    assert session.recoveries() == []


@pytest.mark.asyncio
async def test_a_start_exactly_at_now_is_refused():
    """The boundary is strict. `now` is not the future, and a fixture starting
    this instant is the liveness path's business, not a misdating."""
    answers = _answer(MSU_AT_MICHIGAN, starts_at=NOW)
    session, _espn, _stats = await _run([_row(MSU_AT_MICHIGAN)], answers)

    assert session.recoveries() == []


@pytest.mark.asyncio
async def test_a_non_scheduled_authority_state_is_refused():
    """Gate 2, the other half: `post`/`in` belong to the settle arms."""
    for state in ("post", "in"):
        answers = _answer(MSU_AT_MICHIGAN, status=state)
        session, _espn, _stats = await _run([_row(MSU_AT_MICHIGAN)], answers)
        assert session.recoveries() == [], state


@pytest.mark.asyncio
async def test_teams_that_disagree_with_the_anchor_are_refused_and_counted():
    """Gate 4. A disagreement means the ID is wrong, not the clock — that is
    `repair_authority_id_collisions`' question and is never guessed at here."""
    answers = {
        (MSU_AT_MICHIGAN[6], MSU_AT_MICHIGAN[1]): _scheduled(
            MSU_AT_MICHIGAN[1], "Ohio State Buckeyes", "Penn State Nittany Lions",
            MSU_AT_MICHIGAN[5],
        )
    }
    session, _espn, stats = await _run([_row(MSU_AT_MICHIGAN)], answers)

    assert stats["unstarted_recovery_refused_teams"] == 1
    assert session.recoveries() == []


@pytest.mark.asyncio
async def test_a_statpal_clock_is_asked_about_and_recovered():
    """#8653: the registry ranks espn above statpal. A stale StatPal clock is
    the row that most needs ESPN's, so it is no longer skipped."""
    row = _row(MSU_AT_MICHIGAN, commence_time_source="statpal")
    session, espn, stats = await _run([row], _answer(MSU_AT_MICHIGAN))

    assert len(espn.asked) == 1
    assert stats["unstarted_recovery_eligible"] == 1
    assert len(session.recoveries()) == 1


@pytest.mark.asyncio
async def test_an_outranking_clock_is_never_even_asked_about():
    """Every ESPN start-time rail asks the registry ranking
    (`provider_may_set_start`), and two rails must not disagree: only
    `mlb_schedule_repair` outranks ESPN."""
    row = _row(MSU_AT_MICHIGAN, commence_time_source="mlb_schedule_repair")
    session, espn, stats = await _run([row], _answer(MSU_AT_MICHIGAN))

    assert espn.asked == []
    assert stats["unstarted_recovery_eligible"] == 0
    assert session.recoveries() == []


# ══ THE QUEUE ════════════════════════════════════════════════════════════════


@pytest.mark.asyncio
async def test_a_recovered_row_is_not_stamped():
    """It became `scheduled`, so it has left the candidate set and can never be
    selected again — a stamp on it is residue."""
    session, _espn, _stats = await _run(
        [_row(MSU_AT_MICHIGAN)], _answer(MSU_AT_MICHIGAN)
    )

    assert len(session.recoveries()) == 1
    assert session.stamps() == []


@pytest.mark.asyncio
async def test_a_row_inside_the_cooldown_is_skipped():
    row = _row(
        MSU_AT_MICHIGAN,
        asked_at=(NOW - AUTHORITY_UNSTARTED_REASK + timedelta(hours=1)).isoformat(),
    )
    _session, espn, stats = await _run([row], _answer(MSU_AT_MICHIGAN))

    assert espn.asked == []
    assert stats["unstarted_recovery_eligible"] == 0


@pytest.mark.asyncio
async def test_a_row_past_the_cooldown_is_asked_again():
    row = _row(
        MSU_AT_MICHIGAN,
        asked_at=(NOW - AUTHORITY_UNSTARTED_REASK - timedelta(hours=1)).isoformat(),
    )
    _session, espn, stats = await _run([row], _answer(MSU_AT_MICHIGAN))

    assert espn.asked == [(MSU_AT_MICHIGAN[6], MSU_AT_MICHIGAN[1])]
    assert stats["unstarted_recovery_recovered"] == 1


@pytest.mark.asyncio
async def test_the_never_asked_row_goes_first():
    """The sort key is one the work ADVANCES (gotcha #41). A never-asked row
    outranks one asked eight hours ago, so a permanently-stuck row cannot camp
    at the head of the queue."""
    stale = _row(
        AUBURN_AT_GEORGIA,
        asked_at=(NOW - timedelta(hours=8)).isoformat(),
    )
    fresh = _row(MSU_AT_MICHIGAN)
    answers = {**_answer(MSU_AT_MICHIGAN), **_answer(AUBURN_AT_GEORGIA)}
    _session, espn, _stats = await _run([stale, fresh], answers)

    assert espn.asked[0] == (MSU_AT_MICHIGAN[6], MSU_AT_MICHIGAN[1])


@pytest.mark.asyncio
async def test_the_per_pass_budget_bounds_the_espn_calls():
    """One call PER ROW here, not per board — so the budget IS the wall clock."""
    rows, answers = [], {}
    for n in range(MAX_UNSTARTED_RECOVERY_ASKS_PER_PASS + 3):
        spec = (
            900000 + n, f"90000{n}", f"Home {n}", f"Away {n}",
            NOW - timedelta(days=9),
            NOW + timedelta(days=40), "americanfootball_ncaaf",
        )
        rows.append(_row(spec))
        answers.update(_answer(spec))
    _session, espn, _stats = await _run(rows, answers)

    assert len(espn.asked) == MAX_UNSTARTED_RECOVERY_ASKS_PER_PASS


@pytest.mark.asyncio
async def test_an_unparseable_stamp_is_treated_as_never_asked():
    """Forgetting costs one extra call; skipping costs a row that is never
    revisited at all."""
    row = _row(MSU_AT_MICHIGAN, asked_at="not-a-timestamp")
    _session, espn, _stats = await _run([row], _answer(MSU_AT_MICHIGAN))

    assert espn.asked == [(MSU_AT_MICHIGAN[6], MSU_AT_MICHIGAN[1])]


def test_a_naive_stamp_is_read_as_utc():
    """A stamp written without a timezone must not raise on comparison."""
    event = _FakeEvent(
        1, "x", "H", "A", NOW,
        asked_at=datetime(2026, 9, 15, 1, 0).isoformat(),
    )
    parsed = _unstarted_recovery_asked_at(event, NOW)
    assert parsed is not None and parsed.tzinfo is not None


# ══ THE STAMP MERGES, IT DOES NOT CLOBBER ════════════════════════════════════


@pytest.mark.asyncio
async def test_the_stamp_preserves_what_the_deep_arm_wrote_this_pass():
    """Both arms run in one pass against the same ORM object (the session's
    identity map), and the deep arm mirrors its own stamp. Reading the attribute
    here therefore cannot lose it — this is the assertion that proves it."""
    row = _row(
        MSU_AT_MICHIGAN,
        sources={"deep_straggler_asked_at": "2026-09-15T04:29:00+00:00",
                 "kalshi": {"value": 0.5}},
    )
    session, _espn, _stats = await _run([row], {})  # no answer -> stamp only

    (stamp,) = session.stamps()
    written = stamp["win_probability_sources"]
    assert written["deep_straggler_asked_at"] == "2026-09-15T04:29:00+00:00"
    assert written["kalshi"] == {"value": 0.5}
    assert written[UNSTARTED_RECOVERY_ASKED_KEY] == NOW.isoformat()


# ══ DISJOINTNESS FROM THE SETTLE ARMS ════════════════════════════════════════


#: The real ESPN status vocabulary for this population, as censused in
#: `espn_terminal_state`'s own docstring (5,672 soccer fixtures across 34
#: leagues, plus the four-sport `STATUS_FINAL` table above it). `state` and
#: `completed` are the fields that decide — NOT `name`, which is the #2908 trap.
_AUTHORITY_STATES = [
    ("STATUS_SCHEDULED", "pre", False),
    ("STATUS_IN_PROGRESS", "in", False),
    ("STATUS_FINAL", "post", True),
    ("STATUS_FULL_TIME", "post", True),
    ("STATUS_FINAL_PEN", "post", True),
    ("STATUS_POSTPONED", "post", False),
    ("STATUS_ABANDONED", "post", False),
]


def _settle_door_open(state, completed):
    from app.services.espn_api import espn_terminal_state

    status_type = {"state": state, "completed": completed}
    return espn_terminal_state(status_type) == "post" and completed is True


def _this_arm_open(name):
    # What `_parse_event` derives, which is what this arm gates on.
    return name == "STATUS_SCHEDULED"


@pytest.mark.parametrize("name,state,completed", _AUTHORITY_STATES)
def test_no_authority_answer_can_satisfy_both_doors(name, state, completed):
    """The two arms share a candidate population, so their disjointness cannot
    live in a window — it has to live in the ANSWER, and it does.

    The settle door opens only on `state="post"` AND `completed=True`; this arm
    opens only on the parsed status `scheduled`. Over the whole real status
    vocabulary the two are never open at once.
    """
    assert not (_settle_door_open(state, completed) and _this_arm_open(name)), name


def test_the_disjointness_pair_is_not_vacuous():
    """Both halves of the test above must actually be reachable, or it proves
    nothing — a guard that can never see either door open is a tautology."""
    assert any(
        _settle_door_open(state, completed)
        for _n, state, completed in _AUTHORITY_STATES
    )
    assert any(_this_arm_open(n) for n, _s, _c in _AUTHORITY_STATES)


@pytest.mark.asyncio
async def test_the_candidate_floor_is_the_settle_windows_own_boundary():
    """A row the liveness path is still working is never selected by this rail.

    The fake session cannot enforce a WHERE, so this reads the PREDICATE the arm
    actually sent: the compiled SELECT must carry `now - 48h` as its clock
    bound, which is the settle arms' own lookback and therefore the exact
    complement of the population they own.
    """
    session = _FakeSession([])
    session.selects = []
    original = session.execute

    async def _spy(stmt, *args, **kwargs):
        text = str(stmt)
        if text.lstrip().upper().startswith("SELECT"):
            session.selects.append(stmt.compile().params)
        return await original(stmt, *args, **kwargs)

    session.execute = _spy
    await _recover_unstarted_authority_fixtures(
        session, _FakeESPN({}), NOW, {"errors": []}
    )

    (params,) = session.selects
    bounds = [v for v in params.values() if isinstance(v, datetime)]
    assert bounds == [NOW - AUTHORITY_STRAGGLER_LOOKBACK]
    # An expanding IN compiles to ONE parameter holding the list.
    statuses = [v for v in params.values() if isinstance(v, list)]
    assert statuses == [["live", "suspended"]]


# ══ THE COMPARE-AND-WRITE (#6056) ════════════════════════════════════════════


@pytest.mark.asyncio
async def test_the_write_is_predicated_on_what_the_decision_consumed():
    """It writes four live-state columns, so it may not write unconditionally.

    The predicate is `status` + `commence_time` — the two facts that made the
    row a candidate — and NOT position, which this arm never reads and which is
    NULL on these rows, so a position predicate could never refuse.
    """
    session, _espn, _stats = await _run(
        [_row(MSU_AT_MICHIGAN)], _answer(MSU_AT_MICHIGAN)
    )

    (text, _params) = [u for u in session.updates if "commence_time" in u[1]][0]
    where = text.split("WHERE", 1)[1]
    assert "status" in where and "commence_time" in where
    assert "period" not in where and "game_clock" not in where


@pytest.mark.asyncio
async def test_a_row_that_moved_under_us_is_not_counted_as_recovered():
    """If a settle arm finished the row between the SELECT and the write, the
    CAS refuses — and the arm must report that as a refusal, not a repair."""

    class _RefusingSession(_FakeSession):
        async def execute(self, stmt, *args, **kwargs):
            result = await super().execute(stmt, *args, **kwargs)
            text = str(stmt)
            if "commence_time" in text and not text.lstrip().upper().startswith(
                "SELECT"
            ):
                class _Refused:
                    rowcount = 0
                return _Refused()
            return result

    session = _RefusingSession([_row(MSU_AT_MICHIGAN)])
    stats = {"errors": []}
    await _recover_unstarted_authority_fixtures(
        session, _FakeESPN(_answer(MSU_AT_MICHIGAN)), NOW, stats
    )

    assert stats["unstarted_recovery_recovered"] == 0
    assert stats["unstarted_recovery_row_moved"] == 1
    # It was NOT recovered, so it keeps its queue place and is asked again.
    assert len(session.stamps()) == 1


# ══ THE PARSER THIS ARM STANDS ON ════════════════════════════════════════════
#
# The arm above was written, fully tested and GREEN against hand-built
# `ESPNEvent`s while being a guaranteed no-op in production, because
# `_parse_event` read `status` and `date` from the top level of the payload and
# the `summary?event=` answer puts BOTH inside `competitions[0]`. Teams and
# scores parsed correctly, so the failure was silent and shaped exactly like
# "ESPN says nothing is scheduled". A fake that constructs the dataclass cannot
# see it; only the real payload shape can. Hence these.

#: The REAL shape of `header` from
#: `football/college-football/summary?event=401858511`, read 2026-09-15 06:1xZ.
#: Note what is NOT here: no `date`, no `status`.
_REAL_SUMMARY_HEADER = {
    "id": "401858511",
    "season": {"year": 2026, "type": 2},
    "competitions": [{
        "id": "401858511",
        "date": "2026-11-07T05:00Z",
        "status": {"type": {
            "id": "1", "name": "STATUS_SCHEDULED", "state": "pre",
            "completed": False, "description": "Scheduled",
            "detail": "11/7 - TBD", "shortDetail": "TBD",
        }},
        "competitors": [
            {"homeAway": "home", "score": None,
             "team": {"id": "130", "displayName": "Michigan Wolverines",
                      "name": "Wolverines", "location": "Michigan"}},
            {"homeAway": "away", "score": None,
             "team": {"id": "127", "displayName": "Michigan State Spartans",
                      "name": "Spartans", "location": "Michigan State"}},
        ],
    }],
}

#: The BOARD shape, which carries both at the top level. This is the arm of the
#: test that stops the fix being a regression for `get_scoreboard`.
_REAL_BOARD_EVENT = {
    "id": "401858424",
    "date": "2026-09-03T23:00Z",
    "status": {"type": {"name": "STATUS_FINAL", "state": "post",
                        "completed": True, "detail": "Final"}},
    "competitions": [{
        "id": "401858424",
        "date": "2026-09-03T23:00Z",
        "status": {"type": {"name": "STATUS_FINAL", "state": "post",
                            "completed": True, "detail": "Final"}},
        "competitors": [
            {"homeAway": "home", "score": "42",
             "team": {"id": "356", "displayName": "Illinois Fighting Illini"}},
            {"homeAway": "away", "score": "23",
             "team": {"id": "5", "displayName": "UAB Blazers"}},
        ],
    }],
}


def _parse(payload):
    from app.services.espn_api import ESPNAPIService

    service = ESPNAPIService.__new__(ESPNAPIService)
    return ESPNAPIService._parse_event(service, payload)


def test_a_summary_payload_yields_its_status_and_date():
    """The bug that made the whole arm inert. `get_event` hands the parser
    `{"competitions": [competition], **header}`, and the summary's `header` has
    neither key — so both must be read from the competition."""
    merged = {"competitions": _REAL_SUMMARY_HEADER["competitions"],
              **{k: v for k, v in _REAL_SUMMARY_HEADER.items()
                 if k != "competitions"}}
    parsed = _parse(merged)

    assert parsed is not None
    assert parsed.status == "scheduled"
    assert parsed.date == datetime(2026, 11, 7, 5, 0, tzinfo=timezone.utc)
    assert parsed.home_score is None and parsed.away_score is None
    assert parsed.home_team.display_name == "Michigan Wolverines"


def test_the_board_payload_still_parses_from_the_top_level():
    """The fallback must not become the primary. A board event carries both
    keys at the top level and that is where they must still be read."""
    parsed = _parse(_REAL_BOARD_EVENT)

    assert parsed is not None
    assert parsed.status == "post"
    assert parsed.date == datetime(2026, 9, 3, 23, 0, tzinfo=timezone.utc)
    assert parsed.home_score == 42 and parsed.away_score == 23


def test_a_board_event_whose_competition_disagrees_prefers_the_top_level():
    """Precedence is explicit, not incidental: the top level wins when present,
    so the fallback can never silently reinterpret a board we already read."""
    event = {
        **_REAL_BOARD_EVENT,
        "date": "2026-09-03T23:00Z",
        "competitions": [{
            **_REAL_BOARD_EVENT["competitions"][0],
            "date": "2011-01-01T00:00Z",
            "status": {"type": {"name": "STATUS_SCHEDULED", "state": "pre",
                                "completed": False}},
        }],
    }
    parsed = _parse(event)

    assert parsed.date == datetime(2026, 9, 3, 23, 0, tzinfo=timezone.utc)
    assert parsed.status == "post"


# ══ FAILURE CONTAINMENT ══════════════════════════════════════════════════════


@pytest.mark.asyncio
async def test_one_espn_failure_does_not_cost_the_other_rows(caplog):
    """Gotcha #42: one bad item must never wipe the pass."""
    specs = [MSU_AT_MICHIGAN, AUBURN_AT_GEORGIA]
    answers = {}
    for spec in specs:
        answers.update(_answer(spec))

    class _OneBadESPN(_FakeESPN):
        async def get_event(self, sport_key, espn_id):
            self.asked.append((sport_key, espn_id))
            if espn_id == MSU_AT_MICHIGAN[1]:
                raise RuntimeError("timeout")
            return self._answers.get((sport_key, espn_id))

    session = _FakeSession([_row(s) for s in specs])
    espn = _OneBadESPN(answers)
    stats = {"errors": []}
    await _recover_unstarted_authority_fixtures(session, espn, NOW, stats)

    assert stats["unstarted_recovery_recovered"] == 1
    assert any("unstarted_recovery_" in e for e in stats["errors"])
