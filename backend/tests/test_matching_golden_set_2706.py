"""#2706 — the 709-pair golden set, as a CI regression gate.

WHAT THE GOLDEN SET IS. 709 pairs adjudicated against production on 2026-09-02
(``ARTIFACT-M-20260902-A``, ``.claude/handoff/MATCHING-GOLDEN-2026-09-02.json``):
159 say *"this market belongs on this event"* and 550 say *"this market belongs
on no event"*. Only 39 of the 709 are ``attached-correct`` today — the rest are
the audit's failure classes. **So this file is a RATCHET, not a bar.** It does
not assert that all 709 pass; it asserts that no pair which passes today stops
passing tomorrow, and that any pair which starts passing is recorded.

WHY THE FIXTURE CARRIES CANDIDATES. The pairs were adjudicated against the
production database and CI has no production database, so the honest test has to
carry the INPUTS: the market row and the events the matcher's own search would
have surfaced. ``scripts/capture_matching_golden_fixture.py`` builds those with
the matcher's own parser and its own term expansion. Without them the test is
vacuous twice: a positive pair with one candidate proves nothing about a chooser,
and a negative pair with no candidates proves nothing about restraint. The
captured set averages 6.2 candidates per pair, and the first pair in the file is
a BYU–Utah Tech twin one day apart — picking the right instance is the whole job.

WHY THE REPLAY COMPILES REAL SQL. The window arithmetic IS failure class (c). A
test that reimplemented the window would agree with itself forever and drift from
the matcher, which is exactly how ``/prediction-markets/match-trace`` came to hold
a stale copy of it. So the replay below takes the statements
``_find_matching_event`` REALLY issues, compiles them, runs them over the planted
fixture rows in stdlib sqlite3, and hands the survivors to the real
``_score_candidates``. Change the window, the status filter, the term expansion or
the scoring and this file moves.
"""

from __future__ import annotations

import asyncio
import json
import re
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

import pytest
from sqlalchemy.dialects import sqlite as sqlite_dialect

from app.tasks.prediction_market_matching import (
    _find_matching_event,
    _score_candidates,
)
from app.utils.prediction_market_matching import (
    extract_game_date_from_ticker,
    extract_matchup_with_ticker_fallback,
)

FIXTURES = Path(__file__).parent / "fixtures"
INPUTS_PATH = FIXTURES / "matching_golden_inputs.json"
BASELINE_PATH = FIXTURES / "matching_golden_baseline.json"


# =============================================================================
# The replay harness
# =============================================================================


class _Sport:
    __slots__ = ("id", "key")

    def __init__(self, id, key):
        self.id = id
        self.key = key


class _Event:
    """The attributes the scorer reads. Built from a fixture row."""

    __slots__ = (
        "id", "home_team_name", "away_team_name", "commence_time", "status",
        "external_id", "sport_id", "sport",
    )

    def __init__(self, row: dict, now: datetime):
        self.id = row["id"]
        self.home_team_name = row["home_team_name"]
        self.away_team_name = row["away_team_name"]
        self.commence_time = _parse_dt(row["commence_time"])
        # Derived, not captured — see status_at().
        self.status = status_at(row["commence_time"], now)
        self.external_id = row["external_id"]
        self.sport_id = row["sport_id"]
        self.sport = _Sport(row["sport_id"], row["sport"]) if row["sport"] else None


class _Market:
    """The attributes the matcher reads off a FuturesMarket."""

    __slots__ = (
        "id", "source", "external_id", "name", "category", "llm_sport_category",
        "commence_time", "group_type", "group_id", "status", "event_id",
    )

    def __init__(self, row: dict):
        self.id = row["id"]
        self.source = row["source"]
        self.external_id = row["external_id"]
        self.name = row["name"]
        self.category = row["category"]
        self.llm_sport_category = row["llm_sport_category"]
        self.commence_time = _parse_dt(row["commence_time"])
        self.group_type = row["group_type"]
        self.group_id = row["group_id"]
        self.status = row["status"]
        self.event_id = None


def _parse_dt(value):
    if value is None:
        return None
    if isinstance(value, datetime):
        dt = value
    else:
        dt = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


def _sqlite_stamp(dt) -> str | None:
    """The exact literal form SQLAlchemy's sqlite dialect renders a datetime as.

    The compiled WHERE compares ``events.commence_time`` against literals in
    ``YYYY-MM-DD HH:MM:SS.ffffff``. Planting any other format would make every
    window comparison a string mismatch and every pair look unmatched — a
    uniformly-green ratchet that proves nothing.
    """
    if dt is None:
        return None
    return _parse_dt(dt).replace(tzinfo=None).strftime("%Y-%m-%d %H:%M:%S.%f")


class _CapturingSession:
    """Records the SELECTs ``_find_matching_event`` issues and answers none.

    Returning nothing is deliberate: it drives the function through BOTH of its
    passes in one call, so the replay gets the windowed statement and the broad
    fallback statement together and can apply them in the same order the matcher
    would.
    """

    def __init__(self):
        self.statements = []

    async def execute(self, stmt):
        self.statements.append(stmt)
        return _EmptyResult()


class _EmptyResult:
    def scalars(self):
        return self

    def unique(self):
        return self

    def all(self):
        return []


_PROJECT_RE = re.compile(r"^SELECT\b.*?\nFROM events\b", re.DOTALL)


def _project_to_ids(sql: str) -> str:
    """Rewrite ``SELECT <every column> FROM events …`` to ``SELECT events.id …``.

    Only the column LIST is replaced. The FROM, the JOIN, the WHERE, the ORDER
    BY and the LIMIT — everything that decides which rows come back — is the
    matcher's own, untouched.
    """
    projected, n = _PROJECT_RE.subn("SELECT events.id \nFROM events", sql, count=1)
    assert n == 1, f"could not project the candidate query:\n{sql[:400]}"
    return projected


#: How long after commence an event is treated as ``live`` by the replay.
_LIVE_WINDOW_SECONDS = 3.5 * 3600


def status_at(commence, now: datetime) -> str:
    """The status an event held at ``now``, derived from its start time.

    THE FIXTURE IS OTHERWISE INTERNALLY INCONSISTENT, and that inconsistency is
    not cosmetic. Every event's ``status`` was captured on 2026-09-02, but each
    pair is replayed at the clock its own decision was live at — often days
    earlier. Feeding a *past* clock a *present* status asks the matcher to
    decide about a game that has not started yet and is already marked
    ``closed``.

    Measured: with the captured statuses, ZERO of the 709 pairs were decided by
    the broad fallback pass, because that pass requires ``status IN
    ('scheduled','live')`` and almost every captured row reads ``closed``. An
    entire matching path was invisible to the gate — deleting it outright left
    the suite green. Deriving the status from the replay clock closes that hole.

    Deterministic and clock-free: both inputs come out of the fixture.
    """
    ct = _parse_dt(commence)
    if ct is None:
        return "scheduled"
    delta = (now - ct).total_seconds()
    if delta < 0:
        return "scheduled"
    if delta <= _LIVE_WINDOW_SECONDS:
        return "live"
    return "completed"


def _plant(conn: sqlite3.Connection, events: list[dict], now: datetime) -> None:
    conn.execute(
        "CREATE TABLE events (id INTEGER PRIMARY KEY, home_team_name TEXT, "
        "away_team_name TEXT, commence_time TEXT, status TEXT, "
        "external_id TEXT, sport_id INTEGER)"
    )
    conn.execute("CREATE TABLE sports (id INTEGER PRIMARY KEY, key TEXT)")
    sports = {}
    for e in events:
        conn.execute(
            "INSERT OR REPLACE INTO events VALUES (?,?,?,?,?,?,?)",
            (e["id"], e["home_team_name"], e["away_team_name"],
             _sqlite_stamp(e["commence_time"]),
             status_at(e["commence_time"], now), e["external_id"],
             e["sport_id"]),
        )
        if e["sport_id"] is not None and e["sport"]:
            sports[e["sport_id"]] = e["sport"]
    for sid, key in sports.items():
        conn.execute("INSERT OR REPLACE INTO sports VALUES (?,?)", (sid, key))
    conn.commit()


def replay(pair: dict, now: datetime):
    """What the matcher would choose for this pair. Returns an event id or None.

    Uses the matcher's real statements for the candidate set and the matcher's
    real scorer for the choice. The only thing this harness supplies is the
    database.
    """
    market = _Market(pair["market"])
    matchup = extract_matchup_with_ticker_fallback(
        market.name, external_id=market.external_id
    )
    if not matchup:
        return None, "no_matchup"

    game_date = (
        extract_game_date_from_ticker(market.external_id)
        if market.source == "kalshi" else None
    )

    session = _CapturingSession()
    asyncio.run(
        _find_matching_event(
            session, matchup, market, now, game_date_override=game_date
        )
    )
    if not session.statements:
        return None, "no_query"

    by_id = {e["id"]: e for e in pair["events"]}
    conn = sqlite3.connect(":memory:")
    try:
        _plant(conn, pair["events"], now)
        for stmt in session.statements:
            sql = stmt.compile(
                dialect=sqlite_dialect.dialect(),
                compile_kwargs={"literal_binds": True},
            ).string
            ids = [r[0] for r in conn.execute(_project_to_ids(sql)).fetchall()]
            survivors = [_Event(by_id[i], now) for i in ids if i in by_id]
            # The scorer needs the same reference instant the matcher uses.
            from app.tasks.prediction_market_matching import ticker_start_utc

            scoring_ref = (
                ticker_start_utc(game_date) if game_date and market.source == "kalshi"
                else None
            ) or game_date
            result = _score_candidates(
                survivors, matchup, market, now, scoring_ref
            )
            if result:
                return result["event_id"], "matched"
        return None, "no_match"
    finally:
        conn.close()


#: The instant the golden set was adjudicated at. Used only for pairs with
#: nothing to anchor on. Pinned, never ``now()`` (gotcha #44).
GOLDEN_AS_OF = datetime(2026, 9, 2, 20, 0, tzinfo=timezone.utc)

#: How far before the decisive game the replay clock sits.
_LEAD = 3600


def pair_as_of(pair: dict) -> datetime:
    """The clock this pair's decision was live at. Derived, deterministic.

    ONE PINNED INSTANT DOES NOT WORK, and the reason is a finding, not a
    convenience. The matcher deliberately refuses events that finished more than
    ``MAX_PAST_GAME_DELTA`` ago, so replaying a market that attached on 8/30 at a
    9/2 clock asks the matcher to do something it is CORRECT to refuse. Measured:
    32 of the 39 ``attached-correct`` pairs — markets production has attached
    right now — "failed" that way, which would have made the positive arm of
    this ratchet a monument to a clock bug.

    So each pair is replayed at the moment its own decision was live:

    * **positive pair** — one hour before the event the golden set names. That
      is when the matcher really had to choose.
    * **negative pair with candidates** — one hour before the candidate closest
      to the market's own commence time, i.e. the moment the most tempting
      wrong answer is on the board. Anchoring a negative anywhere else would let
      the time window do the refusing and the test would prove nothing.
    * **negative pair with no candidates** — the adjudication instant; there is
      nothing to be tempted by, and the pair asserts only that the matcher does
      not invent a link.

    Still deterministic and still clock-free: every anchor is read out of the
    fixture, so this file's verdict does not move with the calendar.
    """
    from datetime import timedelta

    by_id = {e["id"]: e for e in pair["events"]}
    correct = by_id.get(pair["correct_event_id"])
    if correct is not None:
        return _parse_dt(correct["commence_time"]) - timedelta(seconds=_LEAD)

    times = [
        _parse_dt(e["commence_time"]) for e in pair["events"]
        if e["commence_time"]
    ]
    if not times:
        return GOLDEN_AS_OF
    market_time = _parse_dt(pair["market"].get("commence_time")) or GOLDEN_AS_OF
    nearest = min(times, key=lambda t: abs((t - market_time).total_seconds()))
    return nearest - timedelta(seconds=_LEAD)


def load_inputs() -> dict:
    return json.loads(INPUTS_PATH.read_text())


def evaluate_all() -> dict[str, bool]:
    """Replay every pair at its own decision clock. ``{market_id: passes}``."""
    data = load_inputs()
    out = {}
    for pair in data["pairs"]:
        chosen, _why = replay(pair, pair_as_of(pair))
        out[str(pair["market_id"])] = chosen == pair["correct_event_id"]
    return out


# =============================================================================
# The fixture itself has to be trustworthy before the ratchet means anything
# =============================================================================


def test_the_fixture_covers_the_whole_golden_set():
    data = load_inputs()
    assert data["captured_pairs"] == data["golden_pairs"] == 709
    assert data["dropped"] == {"event_gone": 0, "market_gone": 0}
    assert data["positive_pairs"] == 159
    assert data["negative_pairs"] == 550


def test_the_fixture_carries_real_candidate_sets_not_single_answers():
    """A positive pair with one candidate cannot test a chooser.

    If the capture ever degrades to "the correct event and nothing else", the
    positive half of this suite becomes unfalsifiable — so the shape of the
    candidate sets is itself asserted.
    """
    pairs = load_inputs()["pairs"]
    positives = [p for p in pairs if p["correct_event_id"] is not None]
    multi = [p for p in positives if len(p["events"]) > 1]
    assert len(multi) >= 100, (
        f"only {len(multi)}/{len(positives)} positive pairs have a real choice "
        "to make — re-run scripts/capture_matching_golden_fixture.py"
    )


def test_the_adjudicated_event_is_always_present_for_a_positive_pair():
    """A pair whose answer is missing from its own candidate list can never go
    green, so it would sit in the baseline as a permanent false negative."""
    for p in load_inputs()["pairs"]:
        if p["correct_event_id"] is None:
            continue
        ids = {e["id"] for e in p["events"]}
        assert p["correct_event_id"] in ids, f"market {p['market_id']}"


# =============================================================================
# The truncation proof (LANE1B-002-FIXTURE-CANDIDATE-PARITY)
#
# The 2026-09-02 capture is NOT production's candidate set. It differs in three
# measurable ways, and each one makes some green in this file mean less than it
# looks. A ratchet whose fixture is optimistic in ways nobody has written down
# is a ratchet that quietly stops guarding, so the three gaps are COMPUTED from
# the fixture here, PINNED, and allowed to move in one direction only.
#
#   1. THE CAP. `capture_matching_golden_fixture.py` keeps 10 candidates per
#      market; production's own candidate query takes `LIMIT 20`
#      (`_find_matching_event`). 327/709 pairs came back at the cap.
#   2. THE WIDENING. The capture widens the matcher's window by ±4 days so a
#      failure-class-(c) answer — one that sits OUTSIDE the window, which is
#      the whole point of that class — is in the file at all. But the cap is
#      applied as "earliest 10 in the WIDENED window", so for a market with
#      more than 10 rows in that span the eviction lands on the LATE end, which
#      overlaps the matcher's real window. 235 pairs are in that state: their
#      last captured candidate starts BEFORE the matcher's own window closes,
#      so real in-window rivals may be missing. Fewer rivals is an EASIER test
#      in both directions — a positive chooses against less competition, a
#      negative refuses less temptation.
#   3. THE APPENDED ANSWER. When the capture's own search did not surface the
#      adjudicated event, the capture appends it (`search_surfaced_the_answer`
#      is false for 88 pairs). Such a pair can still test the SCORER — does it
#      prefer the adjudicated event over the decoys it did see — but it says
#      nothing about whether production would ever put that event on the board.
#      60 of the 105 passing positives are in this bucket, so the positive arm
#      is asserted separately WITHOUT them below.
#
# THE FIX, when someone re-captures: use production's own window and its own
# `ORDER BY commence_time LIMIT 20` for the primary block, and keep the
# appended answer flagged. Every number below then falls, and these tests say
# so out loud rather than going quietly green.
# =============================================================================

#: Candidates kept per market by the capture that produced this fixture.
CAPTURE_CANDIDATE_CAP = 10

#: Measured 2026-09-02 on `matching_golden_inputs.json`. Each may only FALL.
POSITIVES_WITH_AN_APPENDED_ANSWER = 88
PAIRS_AT_THE_CAPTURE_CAP = 327
TRUNCATED_PAIRS_THE_WINDOW_OUTLASTS = 235

_WINDOW_RE = re.compile(r"commence_time BETWEEN '([^']+)' AND '([^']+)'")


def _searched_candidates(pair: dict) -> list[dict]:
    """The candidates the capture's SEARCH returned, without an appended answer."""
    if pair["search_surfaced_the_answer"]:
        return pair["events"]
    return [e for e in pair["events"] if e["id"] != pair["correct_event_id"]]


def _matcher_window_end(pair: dict, now: datetime):
    """When the matcher's OWN candidate window closes, read off its OWN SQL.

    Not recomputed here. Re-deriving the window arithmetic in a test is how
    ``match-trace`` came to explain a matcher it no longer agreed with; the
    bounds are parsed out of the statement ``_find_matching_event`` issued.
    """
    market = _Market(pair["market"])
    matchup = extract_matchup_with_ticker_fallback(
        market.name, external_id=market.external_id
    )
    if not matchup:
        return None
    game_date = (
        extract_game_date_from_ticker(market.external_id)
        if market.source == "kalshi" else None
    )
    session = _CapturingSession()
    asyncio.run(
        _find_matching_event(
            session, matchup, market, now, game_date_override=game_date
        )
    )
    if not session.statements:
        return None
    sql = session.statements[0].compile(
        dialect=sqlite_dialect.dialect(), compile_kwargs={"literal_binds": True}
    ).string
    found = _WINDOW_RE.search(sql)
    return _parse_dt(found.group(2)) if found else None


def capture_fidelity() -> dict[str, int]:
    """The three gaps, counted off the fixture and the matcher's own window."""
    pairs = load_inputs()["pairs"]
    ledger = {"appended_answers": 0, "at_cap": 0, "window_outlasts_capture": 0}
    for pair in pairs:
        if pair["correct_event_id"] is not None and not pair["search_surfaced_the_answer"]:
            ledger["appended_answers"] += 1
        searched = _searched_candidates(pair)
        if len(searched) < CAPTURE_CANDIDATE_CAP:
            continue                       # the search returned everything it had
        ledger["at_cap"] += 1
        end = _matcher_window_end(pair, pair_as_of(pair))
        if end is None:
            continue
        starts = [
            _parse_dt(e["commence_time"]) for e in searched if e["commence_time"]
        ]
        if starts and max(starts) < end:
            # The capture stopped before the matcher's window did, so rows the
            # matcher WOULD have scored may not be in the file.
            ledger["window_outlasts_capture"] += 1
    return ledger


def test_every_pair_records_whether_its_answer_was_searched_for_or_supplied():
    """Without this flag the two kinds of green are indistinguishable."""
    for p in load_inputs()["pairs"]:
        assert "search_surfaced_the_answer" in p, f"market {p['market_id']}"


def test_the_fixtures_known_truncation_is_banked_and_may_only_improve():
    """The proof itself. These are the ways this fixture is EASIER than
    production; a re-capture may lower them and may not raise them."""
    led = capture_fidelity()
    fix = (
        " — re-capture with production's own window and its own "
        "ORDER BY commence_time LIMIT 20 (LANE1B-002-FIXTURE-CANDIDATE-PARITY)"
    )
    assert led["appended_answers"] <= POSITIVES_WITH_AN_APPENDED_ANSWER, (
        f"{led['appended_answers']} positive pairs are handed an answer their "
        f"own search never surfaced, up from "
        f"{POSITIVES_WITH_AN_APPENDED_ANSWER}{fix}"
    )
    assert led["at_cap"] <= PAIRS_AT_THE_CAPTURE_CAP, (
        f"{led['at_cap']} pairs hit the {CAPTURE_CANDIDATE_CAP}-candidate "
        f"capture cap, up from {PAIRS_AT_THE_CAPTURE_CAP}{fix}"
    )
    assert led["window_outlasts_capture"] <= TRUNCATED_PAIRS_THE_WINDOW_OUTLASTS, (
        f"{led['window_outlasts_capture']} truncated pairs stop before the "
        f"matcher's window closes, up from "
        f"{TRUNCATED_PAIRS_THE_WINDOW_OUTLASTS}{fix}"
    )
    # And the other direction: an improvement has to be recorded, or the next
    # regression back to today's number passes unnoticed (gotcha #10).
    assert led == {
        "appended_answers": POSITIVES_WITH_AN_APPENDED_ANSWER,
        "at_cap": PAIRS_AT_THE_CAPTURE_CAP,
        "window_outlasts_capture": TRUNCATED_PAIRS_THE_WINDOW_OUTLASTS,
    }, f"the fixture's fidelity changed to {led} — update the pinned constants"


# =============================================================================
# The ratchet
# =============================================================================


def test_no_golden_pair_regresses():
    """THE GATE. A pair that passes in the baseline must still pass.

    Fail-on-new in both directions, the same semantics as the frontend
    typecheck ratchet (gotcha #10): a regression fails, and an IMPROVEMENT also
    fails until it is recorded, because an unrecorded improvement silently
    raises the floor and the next regression back to it goes unnoticed.

    To record: ``python3 scripts/matching_golden_baseline.py --write``
    """
    baseline = json.loads(BASELINE_PATH.read_text())
    expected = baseline["pairs"]
    actual = evaluate_all()

    assert set(expected) == set(actual), (
        "the fixture and the baseline disagree about which pairs exist — "
        "re-record with scripts/matching_golden_baseline.py --write"
    )

    by_market = {str(p["market_id"]): p for p in load_inputs()["pairs"]}

    def _describe(mid):
        p = by_market[mid]
        return (
            f"  market {mid} [{p['failure_class']}] {p['title']!r} "
            f"→ expected event {p['correct_event_id']}"
        )

    regressions = [m for m in expected if expected[m] and not actual[m]]
    improvements = [m for m in expected if not expected[m] and actual[m]]

    problems = []
    if regressions:
        problems.append(
            f"{len(regressions)} golden pair(s) REGRESSED:\n"
            + "\n".join(_describe(m) for m in regressions[:20])
        )
    if improvements:
        problems.append(
            f"{len(improvements)} golden pair(s) now PASS and the baseline does "
            "not say so. This is good news that must be recorded — run "
            "`python3 scripts/matching_golden_baseline.py --write`:\n"
            + "\n".join(_describe(m) for m in improvements[:20])
        )
    assert not problems, "\n\n".join(problems)


def test_the_baseline_is_not_vacuously_green():
    """A baseline of all-False would make the regression arm unfalsifiable."""
    baseline = json.loads(BASELINE_PATH.read_text())
    passing = sum(1 for v in baseline["pairs"].values() if v)
    assert passing >= 550, (
        f"only {passing} golden pairs pass in the baseline — the ratchet has "
        "nothing left to protect"
    )


def test_the_positive_arm_of_the_baseline_has_teeth():
    """550 of 709 pairs are NEGATIVE, and a matcher that linked nothing at all
    would satisfy every one of them.

    So the floor is asserted separately for the pairs that require the matcher
    to actually CHOOSE an event. Without this, a change that broke linking
    outright could keep the headline number healthy.
    """
    baseline = json.loads(BASELINE_PATH.read_text())["pairs"]
    positives = [
        p for p in load_inputs()["pairs"] if p["correct_event_id"] is not None
    ]
    passing = sum(1 for p in positives if baseline[str(p["market_id"])])
    assert passing >= 60, (
        f"only {passing}/{len(positives)} POSITIVE pairs pass — the arm that "
        "tests choosing (rather than refusing) has stopped guarding anything"
    )


#: Passing positives whose answer the capture's own SEARCH surfaced — the
#: subset where a green means the matcher both FOUND and CHOSE the adjudicated
#: event. Measured 2026-09-02: 45 of the 105 passing positives.
END_TO_END_POSITIVE_FLOOR = 45


def test_the_positive_floor_holds_without_the_pairs_that_were_handed_an_answer():
    """60 of the 105 passing positives were handed their answer by the capture
    (see the truncation proof above). Those greens test the SCORER only.

    So the floor is asserted a second time over the pairs where the matcher's
    own search really surfaced the event it then chose. Without this split, the
    end-to-end arm could rot to nothing while the headline positive count sat
    still, carried entirely by pairs whose answer the fixture supplied.
    """
    baseline = json.loads(BASELINE_PATH.read_text())["pairs"]
    end_to_end = [
        p for p in load_inputs()["pairs"]
        if p["correct_event_id"] is not None and p["search_surfaced_the_answer"]
    ]
    passing = sum(1 for p in end_to_end if baseline[str(p["market_id"])])
    assert passing >= END_TO_END_POSITIVE_FLOOR, (
        f"only {passing}/{len(end_to_end)} positive pairs pass on a candidate "
        f"set their own search produced (floor {END_TO_END_POSITIVE_FLOOR}) — "
        "the end-to-end half of the positive arm has regressed even if the "
        "headline positive count has not"
    )


def test_the_baseline_records_what_it_was_measured_against():
    """A baseline that cannot say which fixture and which clock rule produced it
    is a number without a population."""
    baseline = json.loads(BASELINE_PATH.read_text())
    assert baseline["source_file"] == load_inputs()["source_file"]
    assert baseline["fallback_as_of"] == GOLDEN_AS_OF.isoformat()
    assert baseline["anchor"] == "per-pair decision clock (see pair_as_of)"
    assert baseline["pair_count"] == len(baseline["pairs"])


@pytest.mark.parametrize("failure_class", ["attached-correct", "x-false-attach"])
def test_the_classes_that_should_be_green_today_are_named_in_the_baseline(failure_class):
    """Sanity on the two decided classes, so a silent all-red rewrite is loud."""
    baseline = json.loads(BASELINE_PATH.read_text())["pairs"]
    pairs = [
        p for p in load_inputs()["pairs"] if p["failure_class"] == failure_class
    ]
    assert pairs, f"no {failure_class} pairs in the fixture"
    assert all(str(p["market_id"]) in baseline for p in pairs)
