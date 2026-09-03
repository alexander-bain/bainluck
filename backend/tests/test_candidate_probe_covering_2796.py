"""#2796 — the candidate probe answers the question it is asked.

WHAT WAS WRONG. The probe exists to split one bucket in two: "upstream has a
market we have no event for" (``no_candidate``) versus "the game IS in our
events table and our window or status filter excluded it" (``outside_time_
window`` / ``state_disagrees``). Only the second is a matcher bug, and it is the
one nothing else can see.

It went at that with an OR over every pattern of every side, ordered by
``commence_time``, ``LIMIT 5``. The OR fires on ONE token — "Morehouse Maroon
Tigers vs Arkansas-Pine Bluff" retrieves Detroit Tigers and Hanshin Tigers — so
the five rows it returned were the five earliest coincidences in a 165-day
window, and ``covering_hits: 0`` meant only "none of those five was this game".
The CERT-810 grader measured 103 of 109 live NCAAF rejects coming back with
exactly 5 hits: saturated, every one of them, so the reason on those receipts
was chosen by a truncation rather than by a fact.

THE FIX IS RETRIEVAL, NOT A BIGGER LIMIT. A limit large enough to be safe today
is a limit that saturates on a busier weekend, and nothing in the receipt would
say which day you were reading. Both sides now go into the WHERE clause, so the
LIMIT cuts a list whose every member already carries the whole matchup — and
when the broad fallback arm is the one that ran and it fills up, the receipt
records ``saturated`` so no consumer reads a truncated zero as a measurement.

THESE TESTS RUN THE REAL SQL. A fake session returns whatever rows it was handed
no matter what the predicate says, which is exactly the property under test
here — so the statements the probe issues are compiled and executed over planted
events in stdlib sqlite3.
"""

import sqlite3
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Optional

import pytest
from sqlalchemy.dialects import sqlite as sqlite_dialect

from app.tasks import prediction_market_matching as pmm
from app.utils import match_receipts as mr

NOW = datetime(2026, 9, 3, 12, 0, tzinfo=timezone.utc)
WINDOW = (NOW - timedelta(hours=6), NOW + timedelta(hours=6))


@dataclass
class _Matchup:
    team_a: str
    team_b: Optional[str] = None


class _Row:
    """One projected event row, in the order the probe SELECTs its columns."""

    def __init__(self, raw):
        self.id, self.home_team_name, self.away_team_name, commence, self.status = raw
        self.commence_time = datetime.fromisoformat(commence) if commence else None


class _Result:
    def __init__(self, rows):
        self._rows = rows

    def all(self):
        return self._rows


class _SqliteSession:
    """Compiles each statement and RUNS it against planted rows."""

    def __init__(self, conn):
        self.conn = conn
        self.sql = []

    async def execute(self, stmt):
        compiled = stmt.compile(
            dialect=sqlite_dialect.dialect(), compile_kwargs={"literal_binds": True}
        ).string
        self.sql.append(compiled)
        return _Result([_Row(r) for r in self.conn.execute(compiled).fetchall()])


def _conn(events):
    conn = sqlite3.connect(":memory:")
    conn.execute(
        "CREATE TABLE events (id INTEGER PRIMARY KEY, home_team_name TEXT, "
        "away_team_name TEXT, commence_time TEXT, status TEXT)"
    )
    for eid, home, away, commence, status in events:
        conn.execute(
            "INSERT INTO events VALUES (?,?,?,?,?)",
            (eid, home, away, commence.strftime("%Y-%m-%d %H:%M:%S.%f"), status),
        )
    conn.commit()
    return conn


def _ilike_conditions(matchup):
    """The broad OR list the matcher builds and hands the probe."""
    conditions = []
    for team in [matchup.team_a] + ([matchup.team_b] if matchup.team_b else []):
        conditions.extend(pmm._side_ilike_conditions(team))
    return conditions


def _receipt(market_name):
    return mr.MatchReceipt(
        market_id=1, source="kalshi", external_id="KXNCAAFGAME-26SEP03MOREAPB",
        market_name=market_name, phase=mr.PHASE_PASS1_TICKER, attempted_at=NOW,
    )


async def _probe(events, matchup, market_name):
    conn = _conn(events)
    session = _SqliteSession(conn)
    receipt = _receipt(market_name)
    try:
        await pmm._record_no_match_reason(
            session, receipt, _ilike_conditions(matchup), NOW,
            WINDOW[0], WINDOW[1], matchup=matchup, probe_allowed=True,
        )
    finally:
        conn.close()
    return receipt, session


#: Five one-token coincidences, all earlier than the real game, all of which the
#: old probe returned and none of which is the market's matchup. This is the
#: NCAAF shape: the ILIKE fires on "Tigers".
COINCIDENCES = [
    (1, "Detroit Tigers", "Minnesota Twins", NOW + timedelta(hours=1), "scheduled"),
    (2, "Hanshin Tigers", "Yomiuri Giants", NOW + timedelta(hours=2), "scheduled"),
    (3, "LSU Tigers", "Clemson Tigers", NOW + timedelta(hours=3), "scheduled"),
    (4, "Auburn Tigers", "Baylor Bears", NOW + timedelta(hours=4), "scheduled"),
    (5, "Missouri Tigers", "Kansas Jayhawks", NOW + timedelta(hours=5), "scheduled"),
]

#: The game the market is actually about, sitting behind all five of them.
REAL_GAME = (
    99, "Morehouse Maroon Tigers", "Arkansas-Pine Bluff Golden Lions",
    NOW + timedelta(days=9), "scheduled",
)

MATCHUP = _Matchup("Morehouse Maroon Tigers", "Arkansas-Pine Bluff Golden Lions")
MARKET_NAME = "Morehouse Maroon Tigers vs Arkansas-Pine Bluff Golden Lions"


@pytest.mark.asyncio
async def test_the_probe_finds_the_covering_game_behind_five_coincidences():
    """THE BUG. The old LIMIT 5 could not see event 99 and said `no_candidate`.

    Nothing about the game changed — it is in our events table, ninth day out,
    excluded by the matcher's ±6h window. That is a real matcher finding, and it
    was being filed as an upstream absence because five other teams called
    Tigers play sooner.
    """
    receipt, _ = await _probe(COINCIDENCES + [REAL_GAME], MATCHUP, MARKET_NAME)

    assert receipt.reject_reason == mr.REJECT_OUTSIDE_TIME_WINDOW
    assert receipt.detail["candidate_probe"]["covering_hits"] == 1
    assert receipt.detail["candidate_probe"]["arm"] == "covering"
    assert [c.event_id for c in receipt.candidates] == [99]


@pytest.mark.asyncio
async def test_the_covering_arm_retrieves_only_rows_carrying_both_sides():
    """The coincidences must not come back at all when a covering row exists.

    This is what makes the LIMIT harmless: it now cuts a list whose members are
    all answers to the question.
    """
    receipt, session = await _probe(COINCIDENCES + [REAL_GAME], MATCHUP, MARKET_NAME)
    assert receipt.detail["candidate_probe"]["hits"] == 1
    assert len(session.sql) == 1, "the broad arm ran even though covering hit"


@pytest.mark.asyncio
async def test_an_upstream_gap_is_still_an_upstream_gap():
    """Control. No covering row exists, so the honest answer is unchanged.

    Without this arm the change would read as "everything is a window bug now",
    which is the opposite lie from the one being fixed.
    """
    receipt, session = await _probe(COINCIDENCES, MATCHUP, MARKET_NAME)

    assert receipt.reject_reason == mr.REJECT_NO_CANDIDATE
    assert receipt.detail["candidate_probe"]["covering_hits"] == 0
    assert receipt.detail["candidate_probe"]["arm"] == "broad_after_covering_miss"
    assert len(session.sql) == 2, "the broad arm must run when nothing covers"


@pytest.mark.asyncio
async def test_a_truncated_broad_arm_says_it_was_truncated():
    """`covering_hits: 0` off a full page is not a measurement — gotcha #53.

    The five coincidences fill the limit exactly, which is the state 103 of the
    109 NCAAF receipts were in. The reason stays `no_candidate` (there is still
    no evidence of a covering row) but the receipt now carries the caveat, so a
    census can separate "we looked and found nothing" from "we stopped looking".
    """
    receipt, _ = await _probe(COINCIDENCES, MATCHUP, MARKET_NAME)
    probe = receipt.detail["candidate_probe"]
    assert probe["hits"] == probe["limit"] == pmm._PROBE_LIMIT
    assert probe["saturated"] is True


@pytest.mark.asyncio
async def test_an_unsaturated_broad_arm_is_not_flagged():
    """The flag has to mean something, so it must not be always-on."""
    receipt, _ = await _probe(COINCIDENCES[:2], MATCHUP, MARKET_NAME)
    assert receipt.detail["candidate_probe"]["saturated"] is False
    assert receipt.detail["candidate_probe"]["hits"] == 2


@pytest.mark.asyncio
async def test_the_market_name_is_read_when_the_parsed_sides_are_invented():
    """"Denver vs Kansas City" parses to the NBA Nuggets/Chiefs for an NFL market.

    65 of 222 ``name_mismatch`` receipts were that shape. The covering arm gets
    both readings for the same reason ``row_coverage`` does: retrieving on the
    parse alone would rebuild the parse bug inside the instrument meant to
    detect it.
    """
    game = (
        7, "Kansas City Chiefs", "Denver Broncos", NOW + timedelta(days=9),
        "scheduled",
    )
    receipt, _ = await _probe(
        [game],
        _Matchup("Nuggets", "Chiefs"),          # the invented NBA parse
        "Denver Broncos vs Kansas City Chiefs",  # the name, which is right
    )
    assert receipt.reject_reason == mr.REJECT_OUTSIDE_TIME_WINDOW
    assert receipt.detail["candidate_probe"]["covering_hits"] == 1


@pytest.mark.asyncio
async def test_a_single_sided_market_skips_the_covering_arm():
    """One named side means one hit already covers it — the broad arm IS covering.

    Running a second identical query for these would double the probe's cost on
    the matcher's hottest path and buy nothing.
    """
    matchup = _Matchup("Merrimack Warriors")
    receipt, session = await _probe(
        [(99, "Merrimack Warriors", "Maine Black Bears", NOW + timedelta(days=9),
          "scheduled")],
        matchup,
        "Will Merrimack Warriors win the conference?",
    )
    assert pmm._covering_probe_condition(receipt.market_name, matchup) is None
    assert len(session.sql) == 1
    assert receipt.detail["candidate_probe"]["arm"] == "broad"
    assert receipt.reject_reason == mr.REJECT_OUTSIDE_TIME_WINDOW


@pytest.mark.asyncio
async def test_a_covering_row_inside_the_window_is_still_a_state_bug():
    """The other classification arm survives the retrieval change."""
    receipt, _ = await _probe(
        [(99, "Morehouse Maroon Tigers", "Arkansas-Pine Bluff Golden Lions",
          NOW, "completed")],
        MATCHUP, MARKET_NAME,
    )
    assert receipt.reject_reason == mr.REJECT_STATE_DISAGREES


@pytest.mark.asyncio
async def test_an_empty_events_table_is_an_upstream_gap_with_both_arms_run():
    receipt, session = await _probe([], MATCHUP, MARKET_NAME)
    assert receipt.reject_reason == mr.REJECT_NO_CANDIDATE
    assert receipt.detail["candidate_probe"]["hits"] == 0
    assert receipt.detail["candidate_probe"]["saturated"] is False
    assert len(session.sql) == 2


@pytest.mark.asyncio
async def test_the_probe_still_respects_its_date_bracket():
    """The bracket is what keeps the probe on an index. It must not have been
    dropped along with the OR — a covering row from last season is not evidence
    about this market."""
    receipt, _ = await _probe(
        [(99, "Morehouse Maroon Tigers", "Arkansas-Pine Bluff Golden Lions",
          NOW - timedelta(days=300), "completed")],
        MATCHUP, MARKET_NAME,
    )
    assert receipt.reject_reason == mr.REJECT_NO_CANDIDATE
    assert receipt.detail["candidate_probe"]["hits"] == 0
