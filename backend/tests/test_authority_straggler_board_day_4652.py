"""#4652 — a match that ends after Eastern midnight is still asked about.

WHAT A USER SAW. `/sports/soccer_usa_mls` at 390 px, 2026-09-10 08:20Z. The
first thing on the page, above Upcoming:

    Live & Paused  2
      No result reported · last score 1-0    LAFC — Red Bull New York
      No result reported · last score 2-3    San Diego FC — San Jose Earthquakes

Both matches had finished roughly four hours earlier. Thirteen MLS games that
finished in the same window were correctly filed below under **Finished 13**
with their scores. And the first card's "last score" is not merely stale, it is
WRONG as a result: ESPN records LAFC 2-0, so the page printed a frozen mid-game
score as the nearest thing it had to a final.

WHY THE ROWS WERE STUCK, measured the same morning against ESPN's own API
(standing notice 26 — the venue, not our mirror):

    GET soccer/usa.1/scoreboard              (undated, asked at 08:20Z)
        12 events, every one state=pre       ← the 9/10 matchday
        761795 absent · 761797 absent

    GET soccer/usa.1/scoreboard?dates=20260909
        14 events, every one state=post completed=True detail=FT
        761795 LAFC 2 - RBNY 0 · 761797 San Diego 2 - San Jose 3

Both fixtures kick off at `2026-09-10T02:30Z` — 10:30 pm ET on the 9th. ESPN
files them under the **9/9** board, where they live for good. They finish around
04:30Z; Eastern midnight is 04:00Z. So by full time the undated board our sync
asks for has already rolled to the 10th and no longer contains the game that
just ended. `_sync_espn_live_events` passed no date, ever, so the only board it
could see was today's and the authority's FT was never read.

Nothing downstream recovers: live/048 correctly forbids ending a match on
silence, so the wall-clock net turns the row `suspended` and leaves it. Census
at 08:20Z — 11 rows `suspended` WITH an `espn_id`, the oldest **151 hours** old
(Illinois 42-23 UAB), four of them MLS with real scorelines.

── WHY THE OBVIOUS FIX IS INERT, WHICH IS THE TRAP THIS SUITE PINS ───────────

`suspended` is missing from both ESPN candidate queries — `_find_sport_keys_to_
sync` (arms: live / completed+closed / scheduled) and `_process_live_sport` (the
same three). It is genuinely missing and it genuinely matters. But adding it
alone changes NOTHING a reader sees: the board those rows would then be matched
against still does not contain them, so they are fetched, unmatched, and left
exactly as they were. `test_the_control__todays_board_settles_nothing` is that
arm, and it must stay red-able — it is the whole reason this ship is a date fix
and not a status fix.

── THE SAFETY CASE ───────────────────────────────────────────────────────────

The straggler pass matches on `espn_id` ONLY, never by name. `match_event_to_
espn` name-matches with no time guard, and "LAFC" on the 9/9 board and "LAFC" on
the 9/10 board are the same string — merging yesterday's finished board into the
live pass would let a finished score and a Final land on a fixture that has not
kicked off (gotcha #32 / CERT-752's class). Every fixture below is CAPTURED from
the two responses quoted above; the postponed one is event 15291065, FC
Cincinnati v D.C. United, which is really in this candidate set at 0-0 and must
come out of it unsettled.
"""
from datetime import datetime, timedelta, timezone

import pytest

from app.services.espn_api import ESPNEvent
from app.tasks.espn_sync import _settle_authority_stragglers
from app.utils.espn_helpers import update_event_fields_from_espn
from app.utils.event_completion import (
    authority_board_day_has_rolled,
    espn_board_date,
)

# The instant every clock in this module is read from: 2026-09-10 08:20Z, the
# moment the page above was photographed. 04:20 ET on the 10th, so the undated
# board is the 10th's and the matches below are filed under the 9th's.
NOW = datetime(2026, 9, 10, 8, 20, tzinfo=timezone.utc)

# CAPTURED. Both kickoffs are ESPN's own `date` for these fixtures.
KICKOFF = datetime(2026, 9, 10, 2, 30, tzinfo=timezone.utc)


class _FakeSport:
    def __init__(self, key):
        self.key = key


class _FakeEvent:
    """Only the columns the straggler pass and the settle door actually read."""

    def __init__(
        self, id, espn_id, home, away, status, commence_time,
        home_score=None, away_score=None, sport_key="soccer_usa_mls",
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
        # Fields the settle door touches but this suite does not assert on.
        self.period = None
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
    def __init__(self, rows):
        self._rows = rows

    def scalars(self):
        return _FakeScalars(self._rows)


class _FakeSession:
    """Absorbs the pass's one SELECT and the settle door's Core UPDATEs."""

    def __init__(self, rows):
        self._rows = rows
        self.selects = []
        self.updates = []
        self.added = []

    async def execute(self, stmt, *args, **kwargs):
        text = str(stmt)
        if text.lstrip().upper().startswith("SELECT"):
            self.selects.append(text)
            return _FakeResult(self._rows)
        self.updates.append(text)
        return _FakeResult([])

    def add(self, obj):
        self.added.append(obj)


class _FakeESPN:
    """Serves a board per requested date. Records what was asked for."""

    def __init__(self, boards, dark=False):
        self._boards = boards
        self._dark = dark
        self.asked = []

    async def get_scoreboard(self, sport_key, date=None):
        self.asked.append((sport_key, date))
        if self._dark:
            return None
        return self._boards.get(date, [])

    async def close(self):
        return None


def _fixture(espn_id, home_score, away_score, *, finished=True, postponed=False):
    """One row of a captured ESPN board."""
    if postponed:
        # `espn_terminal_state` returns None for state=post/completed=False, so
        # `_parse_event` falls through to the raw name. Carried exactly as the
        # parser would hand it on.
        status, detail, stopped = "STATUS_POSTPONED", "Postponed", True
    elif finished:
        status, detail, stopped = "post", "FT", False
    else:
        status, detail, stopped = "scheduled", None, False
    return ESPNEvent(
        espn_id=espn_id,
        name=f"fixture {espn_id}",
        short_name=None,
        date=KICKOFF,
        status=status,
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
        stopped_without_result=stopped,
    )


# CAPTURED 2026-09-10 from `?dates=20260909` — the day the matches are filed
# under. Every fixture on that board came back post/completed=True/FT.
BOARD_0909 = {
    "20260909": [
        _fixture("761795", 2, 0),   # LAFC 2 - Red Bull New York 0
        _fixture("761797", 2, 3),   # San Diego FC 2 - San Jose Earthquakes 3
        _fixture("761799", 1, 2),
        _fixture("761796", 0, 1),
    ]
}

# CAPTURED 2026-09-10 08:20Z from the UNDATED call — the 9/10 matchday. Note
# what is not here: neither match that had just ended.
BOARD_TODAY_UNDATED = {
    "20260910": [
        _fixture("761804", None, None, finished=False),
        _fixture("761806", None, None, finished=False),
        _fixture("761810", None, None, finished=False),
    ]
}


def _suspended_specimens():
    return [
        # Our row's 1-0 is the frozen mid-game score the page printed.
        _FakeEvent(15305754, "761795", "LAFC", "Red Bull New York",
                   "suspended", KICKOFF, home_score=1, away_score=0),
        _FakeEvent(15298476, "761797", "San Diego FC", "San Jose Earthquakes",
                   "suspended", KICKOFF, home_score=2, away_score=3),
    ]


async def _run(rows, boards, dark=False, now=NOW):
    session = _FakeSession(rows)
    espn = _FakeESPN(boards, dark=dark)
    stats = {"authority_dark_sports": 0, "errors": []}
    await _settle_authority_stragglers(
        session, espn, now, stats, update_event_fields_from_espn
    )
    return session, espn, stats


# ── The clock arithmetic ─────────────────────────────────────────────────────

def test_a_late_kickoff_is_filed_under_the_previous_eastern_day():
    """02:30Z on the 10th is 10:30 pm ET on the 9th — ESPN's 9/9 board."""
    assert espn_board_date(KICKOFF) == "20260909"


def test_the_board_has_rolled_by_the_time_the_match_ends():
    assert authority_board_day_has_rolled(KICKOFF, NOW) is True


def test_a_match_still_inside_its_own_board_day_has_not_rolled():
    """The ordinary pass already reaches these; the straggler pass must not."""
    afternoon = datetime(2026, 9, 10, 19, 0, tzinfo=timezone.utc)  # 3 pm ET
    later = afternoon + timedelta(hours=3)
    assert authority_board_day_has_rolled(afternoon, later) is False


# ── The ship ─────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_the_prior_day_board_ends_both_matches():
    rows = _suspended_specimens()
    session, espn, stats = await _run(rows, BOARD_0909)

    assert [e.status for e in rows] == ["completed", "completed"]
    assert stats["straggler_settled"] == 2
    assert stats["straggler_candidates"] == 2
    # It asked for the day the matches are filed under, once.
    assert espn.asked == [("soccer_usa_mls", "20260909")]


@pytest.mark.asyncio
async def test_the_wrong_score_on_the_page_is_corrected_by_the_same_pass():
    """LAFC really won 2-0; the card printed `last score 1-0`."""
    rows = _suspended_specimens()
    await _run(rows, BOARD_0909)

    lafc = rows[0]
    assert (lafc.home_score, lafc.away_score) == (2, 0)


@pytest.mark.asyncio
async def test_the_control__todays_board_settles_nothing():
    """THE CONTROL, and the reason this is a date fix and not a status fix.

    Same rows, same pass, same code — the only difference is that the board
    served is the undated one the old path could see. Nothing is matched and
    nothing is settled, which is precisely what widening the `suspended` filter
    on its own would have shipped.
    """
    rows = _suspended_specimens()
    session, espn, stats = await _run(rows, BOARD_TODAY_UNDATED)

    assert [e.status for e in rows] == ["suspended", "suspended"]
    assert stats["straggler_settled"] == 0
    assert session.updates == []


# ── The safety case ──────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_a_postponed_fixture_reaches_the_door_and_is_refused():
    """Event 15291065, FC Cincinnati v D.C. United — really in this set at 0-0.

    `state=post` with `completed=False`. The settle arm must not read it as a
    result, and a 0-0 Final is exactly the false-final CERT-752 was about.
    """
    row = _FakeEvent(15291065, "761773", "FC Cincinnati", "D.C. United",
                     "suspended", KICKOFF, home_score=0, away_score=0)
    boards = {"20260909": [_fixture("761773", 0, 0, postponed=True)]}

    session, espn, stats = await _run([row], boards)

    assert row.status == "suspended"
    assert stats["straggler_settled"] == 0


@pytest.mark.asyncio
async def test_a_row_is_never_matched_by_NAME_only_by_its_own_espn_id():
    """The hazard that rules out merging the boards.

    The board carries a fixture with the same two team names and a real FT
    score, under a DIFFERENT id — which is what tomorrow's LAFC fixture looks
    like next to yesterday's. Nothing may cross.
    """
    row = _FakeEvent(15305754, "761795", "LAFC", "Red Bull New York",
                     "suspended", KICKOFF, home_score=1, away_score=0)
    boards = {"20260909": [_fixture("999999", 4, 1)]}

    session, espn, stats = await _run([row], boards)

    assert row.status == "suspended"
    assert (row.home_score, row.away_score) == (1, 0)
    assert stats["straggler_settled"] == 0


@pytest.mark.asyncio
async def test_authority_dark_settles_nothing_and_is_counted():
    """A board nobody served is not an empty board (#3473, gotcha #53)."""
    rows = _suspended_specimens()
    session, espn, stats = await _run(rows, BOARD_0909, dark=True)

    assert [e.status for e in rows] == ["suspended", "suspended"]
    assert stats["straggler_settled"] == 0
    assert stats["authority_dark_sports"] == 1


@pytest.mark.asyncio
async def test_a_row_whose_board_day_is_still_today_is_never_asked_about():
    """No candidate ⇒ no request. The ordinary pass owns these rows."""
    afternoon = datetime(2026, 9, 10, 19, 0, tzinfo=timezone.utc)
    now = afternoon + timedelta(hours=3)
    row = _FakeEvent(15309999, "761850", "Austin FC", "Colorado Rapids",
                     "live", afternoon)

    session, espn, stats = await _run([row], BOARD_0909, now=now)

    assert espn.asked == []
    assert stats["straggler_candidates"] == 0
    assert row.status == "live"


@pytest.mark.asyncio
async def test_a_sport_espn_does_not_map_is_skipped_not_guessed_at():
    row = _FakeEvent(15309998, "abc", "antivalue", "Liquid",
                     "suspended", KICKOFF, sport_key="esports_other")

    session, espn, stats = await _run([row], BOARD_0909)

    assert espn.asked == []
    assert stats["straggler_candidates"] == 0


@pytest.mark.asyncio
async def test_one_bad_row_does_not_wipe_the_pass(monkeypatch):
    """Gotcha #42 — a healthy sibling still settles."""
    rows = _suspended_specimens()

    calls = {"n": 0}

    # Mirrors the real settle door's signature including `observed_at` (#4571).
    # It must: the pass's try/except turns a TypeError from a stale double into
    # a `straggler_update_` error and a skipped row, so a signature drift here
    # reads as "the row was bad", not as "the test double is wrong".
    async def _explode_once(session, event, ee, claimed, stats, *, observed_at=None):
        calls["n"] += 1
        if calls["n"] == 1:
            raise RuntimeError("boom")
        return await update_event_fields_from_espn(
            session, event, ee, claimed, stats, observed_at=observed_at
        )

    session = _FakeSession(rows)
    espn = _FakeESPN(BOARD_0909)
    stats = {"authority_dark_sports": 0, "errors": []}
    await _settle_authority_stragglers(session, espn, NOW, stats, _explode_once)

    assert [e.status for e in rows] == ["suspended", "completed"]
    assert stats["straggler_settled"] == 1
    assert any("straggler_update_" in e for e in stats["errors"])


# ── The candidate query itself ───────────────────────────────────────────────

@pytest.mark.asyncio
async def test_the_candidate_query_asks_only_for_rows_an_authority_may_end():
    """A settled row is never re-ended, and a row with no anchor is not guessed.

    Asserted on the emitted SQL because the fake session cannot enforce a WHERE
    clause: without this, the suite would pass on a query that selected every
    event in the table.
    """
    session, espn, stats = await _run(_suspended_specimens(), BOARD_0909)

    assert len(session.selects) == 1
    sql = " ".join(session.selects[0].split()).lower()
    assert "events.status in" in sql
    assert "events.espn_id is not null" in sql
    assert "events.commence_time >=" in sql
    assert "events.commence_time <=" in sql
