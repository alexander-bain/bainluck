"""#5697 — the live pass asks about the board day its own game is filed under.

WHAT A READER SAW. `/events/15304203` (Purdue v Wake Forest) and ten other
college football games, production, Saturday 2026-09-12, photographed at 390 px
by ux/1219 and ux/1220: the card reads **LIVE**, `live · 1m ago`, `⟳ 20s`, a
populated win-probability chart, `↓ -21% Boilermakers since open`, and
`Projected final: 23 – 31` — and **no score anywhere on it**. Every freshness
signal is green and correct, which is the worst possible shape: nothing tells
the reader the number is missing rather than 0–0. Eleven of the fifteen live
NCAAF games on the board were in that state, seven of them 3 h 26 m past their
own kickoff, i.e. games that had finished.

── WHY, MEASURED AGAINST ESPN'S OWN API (standing notice 26) ─────────────────

    2026-09-12 22:25Z
    GET football/college-football/scoreboard                     24 events
    GET football/college-football/scoreboard?limit=200           24 events
    GET football/college-football/scoreboard?dates=20260912      80 events

The undated board is not a page of the day's slate, it is a **curated subset**
— `?limit=200` does not widen it, and only `?dates=` does. `_sync_espn_live_
events` fetched `get_scoreboard(key)` with no date, so the live pass could only
ever see those 24 games.

The separation is total. Of the eleven NCAAF games that carried no score
through their whole duration, **eleven of eleven were absent from the 24 and
present in the 80**; every game that tracked live was in the 24. The same pass,
read from `/api/admin/task-metrics?task=espn_sync` at 22:28Z, reported:

    sports_with_live 37 · events_synced 5 · events_unmatched 23

Five matched events across thirty-seven live sports. The games then got exactly
ONE `ScoreSnapshot`, at +240 minutes, when a dated path finally settled them —
which is why this reads as "the score was late" rather than as a bug.

This is the second half of #4652's root cause. That ship found that the undated
board answers about *today*, so a match ending after Eastern midnight is filed
under a board nobody asks for; it built `_settle_authority_stragglers` for the
rows whose board day has **rolled**, and skips any row whose day has not, on the
grounds that it is "already reachable by the ordinary pass". That comment is
what this suite falsifies: the ordinary pass reaches 24 of 80.

── THE SAFETY CASE, AND WHY IT IS TWO GUARDS ─────────────────────────────────

#4652's own safety paragraph is the hazard to beat: "LAFC" on the 9/9 board and
"LAFC" on the 9/10 board are the same string, so merging another day's board
into the shared pool would let a finished score and a Final land on a fixture
that has not kicked off (gotcha #32 / CERT-752's class).

Guard 1 — the widened pool is built for ONE event from the board day of THAT
event's own `commence_time`, and is never appended to the shared board. So a
second event in the same sport cannot see it, and `create_events_from_unmatched_
espn` still receives exactly the board it received before this change.
`test_a_widened_board_never_reaches_the_event_creator` and
`test_the_pool_is_per_event_not_merged_into_the_shared_board` are those arms.

Guard 2 — the matcher's own time authorization, which is MEASURED here rather
than assumed: since #2049 the name arm runs through `select_authorized_espn_
candidate`, which refuses any candidate more than `NAME_ONLY_SAME_GAME_SECONDS`
(3 h, asserted below so a future loosening reds this file) from our own
`commence_time`. #4652's prose says the name arm has no time guard; that
predates #2049 and is no longer true.

── THE CONTROL ───────────────────────────────────────────────────────────────

`test_THE_CONTROL_without_the_fetcher_the_game_stays_scoreless` runs the exact
same specimen with `dated_board_fetcher=None` and asserts the game is NOT
matched and keeps no score. It is the production behaviour of 22:25Z and it must
stay red-able: if it ever passes *with* a score, this suite has stopped
measuring anything.

Every ESPN row below is CAPTURED from the two responses quoted above.
"""
from datetime import datetime, timedelta, timezone

import pytest

from app.services.espn_api import ESPNEvent, ESPNTeam
from app.tasks.espn_sync import (
    MAX_DATED_BOARDS_PER_SPORT,
    _process_live_sport,
    espn_team_matches,
)
from app.utils.espn_candidate_selection import NAME_ONLY_SAME_GAME_SECONDS
from app.utils.espn_helpers import match_event_to_espn
from app.utils.event_completion import espn_board_date

SPORT = "americanfootball_ncaaf"

# CAPTURED: every one of these games kicks off 2026-09-12T16:00Z. Eastern is
# UTC-4 in September, so 16:00Z is noon ET and the board day is the 12th.
KICKOFF = datetime(2026, 9, 12, 16, 0, tzinfo=timezone.utc)
BOARD_DAY = "20260912"

# The moment ux photographed the card: 206 minutes after kickoff.
NOW = KICKOFF + timedelta(minutes=206)


def _team(name, short):
    return ESPNTeam(
        espn_id="t-" + short.lower().replace(" ", ""),
        name=name,
        abbreviation=short[:4].upper(),
        display_name=name,
        short_name=short,
        nickname=None,
        primary_color=None,
        secondary_color=None,
        logo_url=None,
        logo_url_dark=None,
        record=None,
    )


def _espn_event(espn_id, home, home_short, away, away_short, hs, aws, when=KICKOFF):
    return ESPNEvent(
        espn_id=espn_id,
        name=f"{away} at {home}",
        short_name=f"{away_short} @ {home_short}",
        date=when,
        status="post",
        status_detail="Final",
        period=4,
        clock="0:00",
        home_team=_team(home, home_short),
        away_team=_team(away, away_short),
        home_score=hs,
        away_score=aws,
        venue=None,
        broadcasts=[],
        home_win_probability=None,
    )


# CAPTURED from `?dates=20260912`, absent from the undated board.
PURDUE_WAKE = _espn_event(
    "401858224", "Purdue Boilermakers", "Purdue",
    "Wake Forest Demon Deacons", "Wake Forest", 36, 38,
)
ECU_APP = _espn_event(
    "401864571", "East Carolina Pirates", "East Carolina",
    "App State Mountaineers", "App State", 24, 27,
)
# CAPTURED from the undated board — one of the 24 that tracked live all day.
MICH_OU = _espn_event(
    "401856679", "Michigan Wolverines", "Michigan",
    "Oklahoma Sooners", "Oklahoma", 17, 10,
)

UNDATED_BOARD = [MICH_OU]
DATED_BOARD = [MICH_OU, PURDUE_WAKE, ECU_APP]


class _FakeSport:
    def __init__(self, key):
        self.key = key
        self.id = 1


class _FakeEvent:
    """Only the columns the live pass and the field writer actually read."""

    _next_id = 15304203

    def __init__(self, home, away, *, espn_id=None, commence=KICKOFF, status="live"):
        self.id = _FakeEvent._next_id
        _FakeEvent._next_id += 1
        self.sport = _FakeSport(SPORT)
        self.sport_id = 1
        self.home_team_name = home
        self.away_team_name = away
        self.home_team_normalized = None
        self.away_team_normalized = None
        self.home_team_alt_names = None
        self.away_team_alt_names = None
        self.home_team_id = None
        self.away_team_id = None
        self.espn_id = espn_id
        self.commence_time = commence
        self.commence_time_source = None
        self.status = status
        self.home_score = None
        self.away_score = None
        self.period = None
        self.broadcast_info = None
        self.completed_at = None
        self.llm_importance = None


class _Result:
    def __init__(self, rows):
        self._rows = rows

    def scalars(self):
        return self

    def all(self):
        return self._rows


class _FakeSession:
    """Serves the two queries `_process_live_sport` issues, in order."""

    def __init__(self, events):
        self._queued = [_Result(events), _Result([])]
        self.added = []

    async def execute(self, *_a, **_k):
        if self._queued:
            return self._queued.pop(0)
        return _Result([])

    def add(self, obj):
        self.added.append(obj)

    async def flush(self):
        return None


class _Recorder:
    """Captures which board entry reached each downstream writer."""

    def __init__(self):
        self.updated = []
        self.created_against = []
        self.fetch_calls = []

    async def upsert_team(self, session, name, espn_team, sport_id, cache, stats):
        return None

    async def register_identities(self, *a, **k):
        return None

    async def update_fields(self, session, event, ee, claimed, stats):
        # The two lines of the real writer this suite makes a claim about;
        # everything else it does is covered by `test_espn_sync_helpers`.
        self.updated.append((event.id, ee.espn_id))
        event.home_score = ee.home_score
        event.away_score = ee.away_score
        return True

    async def write_win_prob(self, *a, **k):
        return False

    async def compute_stat_model(self, *a, **k):
        return False

    async def create_unmatched(self, session, our_events, espn_events, sport_key, stats):
        self.created_against.append(list(espn_events))


def _run(events, *, fetcher, board=UNDATED_BOARD):
    """Drive one live pass. Returns (recorder, stats)."""
    import asyncio

    rec = _Recorder()
    stats = {"events_synced": 0, "events_updated": 0, "errors": []}
    session = _FakeSession(events)
    asyncio.get_event_loop_policy().new_event_loop()
    asyncio.run(
        _process_live_sport(
            session, SPORT, board, stats,
            NOW - timedelta(hours=6), NOW - timedelta(hours=5),
            espn_team_matches, rec.upsert_team, rec.register_identities,
            match_event_to_espn, rec.update_fields, rec.write_win_prob,
            rec.compute_stat_model, rec.create_unmatched,
            dated_board_fetcher=fetcher,
        )
    )
    return rec, stats


def _fetcher(board, *, log=None, dark=False, empty=False):
    async def fetch(sport_key, board_day):
        if log is not None:
            log.append((sport_key, board_day))
        if dark:
            return None
        if empty:
            return []
        return board

    return fetch


# ── The defect ───────────────────────────────────────────────────────────────


def test_the_game_absent_from_the_undated_board_gets_its_score():
    """Purdue v Wake Forest, 206 minutes in, is matched and carries 36-38."""
    ev = _FakeEvent("Purdue Boilermakers", "Wake Forest Demon Deacons")
    rec, stats = _run([ev], fetcher=_fetcher(DATED_BOARD))

    assert rec.updated == [(ev.id, "401858224")]
    assert (ev.home_score, ev.away_score) == (36, 38)
    assert stats["events_matched_on_dated_board"] == 1
    assert stats["dated_board_fetches"] == 1


def test_THE_CONTROL_without_the_fetcher_the_game_stays_scoreless():
    """Production, 2026-09-12 22:25Z. This is the bug, and it must stay red-able.

    Same specimen, same undated board, no second question. If this ever reports
    a score, the suite above has stopped proving that the widening is what
    found the game.
    """
    ev = _FakeEvent("Purdue Boilermakers", "Wake Forest Demon Deacons")
    rec, stats = _run([ev], fetcher=None)

    assert rec.updated == []
    assert (ev.home_score, ev.away_score) == (None, None)
    assert stats["events_synced"] == 0
    assert stats.get("events_matched_on_dated_board", 0) == 0


def test_the_board_day_asked_about_is_the_events_own():
    """Not "today" — the day THIS fixture is filed under (#4652's lesson)."""
    log = []
    ev = _FakeEvent("Purdue Boilermakers", "Wake Forest Demon Deacons")
    _run([ev], fetcher=_fetcher(DATED_BOARD, log=log))

    assert log == [(SPORT, BOARD_DAY)]
    assert log[0][1] == espn_board_date(ev.commence_time)


def test_the_board_day_is_eastern_and_is_not_the_utc_date():
    """The #4652 rollover shape, as the arm that cannot pass by coincidence.

    A 10:30 pm ET kickoff on the 12th has a UTC timestamp on the **13th**, and
    ESPN files it under the 12th's board for good. Asking "today" or asking the
    naive UTC date both give the wrong day here, and neither can be right by
    accident on some other day of the year — the two candidates differ from the
    answer in opposite directions.
    """
    late = _FakeEvent(
        "Purdue Boilermakers", "Wake Forest Demon Deacons",
        commence=datetime(2026, 9, 13, 2, 30, tzinfo=timezone.utc),
    )
    log = []
    _run([late], fetcher=_fetcher([], log=log))

    assert late.commence_time.strftime("%Y%m%d") == "20260913"
    assert log == [(SPORT, "20260912")]


# ── Guard 1: the widened pool is per-event and never shared ──────────────────


def test_a_widened_board_never_reaches_the_event_creator():
    """`create_events_from_unmatched_espn` sees the undated board, unchanged.

    Otherwise this ship would quietly start manufacturing events off a board it
    fetched for a different purpose — matching work, which is lane1's (D35).
    """
    ev = _FakeEvent("Purdue Boilermakers", "Wake Forest Demon Deacons")
    rec, _ = _run([ev], fetcher=_fetcher(DATED_BOARD))

    assert len(rec.created_against) == 1
    assert [e.espn_id for e in rec.created_against[0]] == ["401856679"]


def test_the_pool_is_per_event_not_merged_into_the_shared_board():
    """A second event cannot be matched off the board fetched for the first.

    The widened pool is rebuilt from `espn_events` each time, so an event whose
    own board day was never asked about sees only the undated board — even
    after a sibling has pulled a bigger one down.
    """
    found = _FakeEvent("Purdue Boilermakers", "Wake Forest Demon Deacons")
    # Filed under a different board day, and 24 h from anything on the 12th.
    other = _FakeEvent(
        "East Carolina Pirates", "App State Mountaineers",
        commence=KICKOFF + timedelta(days=1),
    )

    log = []

    async def fetch(sport_key, board_day):
        log.append((sport_key, board_day))
        # Only the 12th has a board; the 13th has not been played.
        return DATED_BOARD if board_day == BOARD_DAY else []

    rec, _ = _run([found, other], fetcher=fetch)

    assert (found.home_score, found.away_score) == (36, 38)
    # ECU/App State IS on the board the first event pulled down, and the names
    # match exactly — it stays unmatched only because that pool was never
    # shared and its own day is empty.
    assert (other.home_score, other.away_score) == (None, None)
    assert log == [(SPORT, BOARD_DAY), (SPORT, "20260913")]


# ── Guard 2: the matcher's own time authorization, measured ──────────────────


def test_the_name_arm_still_refuses_a_candidate_outside_three_hours():
    """#2049's bound is what stops a wider board folding the wrong game in.

    Asserted as a NUMBER so that loosening it reds this file: the widening
    above is only safe because the matcher will not take a same-named game
    more than this far from our own kickoff.
    """
    assert NAME_ONLY_SAME_GAME_SECONDS == 3 * 60 * 60

    # Same two clubs, our row a day later than the board's game.
    stale = _FakeEvent(
        "Purdue Boilermakers", "Wake Forest Demon Deacons",
        commence=KICKOFF + timedelta(days=1),
    )
    rec, _ = _run([stale], fetcher=_fetcher(DATED_BOARD))

    assert rec.updated == []
    assert (stale.home_score, stale.away_score) == (None, None)


# ── The cost ceiling ─────────────────────────────────────────────────────────


def test_a_board_day_is_asked_about_once_however_many_games_need_it():
    """Eleven unmatched NCAAF games cost ONE extra request, not eleven."""
    log = []
    games = [
        _FakeEvent("Purdue Boilermakers", "Wake Forest Demon Deacons"),
        _FakeEvent("East Carolina Pirates", "App State Mountaineers"),
    ]
    rec, stats = _run(games, fetcher=_fetcher(DATED_BOARD, log=log))

    assert log == [(SPORT, BOARD_DAY)]
    assert stats["dated_board_fetches"] == 1
    assert stats["events_matched_on_dated_board"] == 2


def test_a_sport_cannot_ask_about_more_days_than_the_ceiling():
    """The pass already overruns its 60 s period; the ceiling is load-bearing."""
    assert MAX_DATED_BOARDS_PER_SPORT == 2

    log = []
    games = [
        _FakeEvent("A United", "B City", commence=KICKOFF + timedelta(days=d))
        for d in range(MAX_DATED_BOARDS_PER_SPORT + 2)
    ]
    _, stats = _run(games, fetcher=_fetcher([], log=log))

    assert len(log) == MAX_DATED_BOARDS_PER_SPORT
    assert stats["dated_board_days_skipped"] == 2


def test_an_event_matched_on_the_undated_board_asks_nothing_extra():
    """Michigan v Oklahoma is one of the 24 — it must cost no second request."""
    log = []
    ev = _FakeEvent("Michigan Wolverines", "Oklahoma Sooners")
    rec, stats = _run([ev], fetcher=_fetcher(DATED_BOARD, log=log))

    assert rec.updated == [(ev.id, "401856679")]
    assert log == []
    assert stats.get("dated_board_fetches", 0) == 0


# ── Authority dark ───────────────────────────────────────────────────────────


def test_a_dark_dated_board_changes_nothing_and_is_counted():
    """`None` is not an empty slate (#3473). It adds no candidate and no claim."""
    ev = _FakeEvent("Purdue Boilermakers", "Wake Forest Demon Deacons")
    rec, stats = _run([ev], fetcher=_fetcher(None, dark=True))

    assert rec.updated == []
    assert (ev.home_score, ev.away_score) == (None, None)
    assert stats["dated_board_dark"] == 1
    assert stats.get("dated_board_fetches", 0) == 0


def test_a_dark_board_is_not_re_asked_for_every_game_on_it():
    """One dark answer per day, not one per unmatched row."""
    log = []
    games = [
        _FakeEvent("Purdue Boilermakers", "Wake Forest Demon Deacons"),
        _FakeEvent("East Carolina Pirates", "App State Mountaineers"),
    ]
    _run(games, fetcher=_fetcher(None, dark=True, log=log))

    assert log == [(SPORT, BOARD_DAY)]


def test_a_raising_fetcher_does_not_wipe_the_sports_pass():
    """gotcha #42 — one bad board must not cost the healthy siblings."""

    async def boom(sport_key, board_day):
        raise RuntimeError("ESPN connection reset")

    found = _FakeEvent("Michigan Wolverines", "Oklahoma Sooners")
    lost = _FakeEvent("Purdue Boilermakers", "Wake Forest Demon Deacons")
    rec, stats = _run([lost, found], fetcher=boom)

    assert (found.home_score, found.away_score) == (17, 10)
    assert (lost.home_score, lost.away_score) == (None, None)
    assert any("dated_board_" in e for e in stats["errors"])


def test_an_event_with_no_commence_time_asks_nothing():
    """There is no board day to ask about, and `espn_board_date` would raise."""
    log = []
    ev = _FakeEvent("Purdue Boilermakers", "Wake Forest Demon Deacons")
    ev.commence_time = None
    rec, _ = _run([ev], fetcher=_fetcher(DATED_BOARD, log=log))

    assert log == []
    assert rec.updated == []
