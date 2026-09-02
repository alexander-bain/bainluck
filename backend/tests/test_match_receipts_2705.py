"""#2705 — every matching attempt leaves a receipt, and the reason is countable.

WHAT THESE TESTS ARE FOR. Before receipts, an unattached market was one bit:
``futures_markets.event_id IS NULL``. That bit cannot distinguish "no event
exists", "an event exists and the matcher refused it", and "the scan never
reached this row" — and the third is what actually happened to the 8/28
Polymarket US Open wave (ARTIFACT-M-20260902-N: three groups at zero links, all
ingested 8/28, while every 8/31–9/01 group linked, with nothing about the names,
candidates or shapes separating them). INVARIANTS-2026-09-02 query (c) counts
996 markets that are parseable, have an exact-name candidate in an agreeing
state, are unlinked, and have no written reason.

So the tests below hold three lines:

1. **A receipt is written for every attempt, and it always carries a reason.**
   A path that returns without one is the old NULL wearing a new table.
2. **The reason is a CLOSED enum.** A free-text reason would turn 996 markets
   into 996 strings and query (c) would stay uncountable. ``reject()`` raises on
   an unknown value, in the caller's own stack.
3. **Receipts change nothing about matching.** ``_score_candidates`` must return
   the identical decision with and without a receipt attached — proved by
   running both arms over the same candidates, not by reading the code.

And one line about the pass that the receipts exist to make measurable: the
backlog scan's SELECT is COMPILED AND RUN over planted rows in stdlib sqlite3,
because a fake session returns whatever rows it was handed no matter what the
predicate says. If never-attempted stops being selected first, that test goes
red; if the predicate starts selecting linked markets too, it also goes red.
"""

import asyncio
import inspect
import re
import sqlite3
from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy.dialects import sqlite as sqlite_dialect

from app.tasks import prediction_market_matching as pmm
from app.utils import match_receipts as mr
from app.utils.match_receipts import (
    MAX_TRACE_CANDIDATES,
    CandidateTrace,
    MatchReceipt,
)

NOW = datetime(2026, 9, 2, 20, 0, tzinfo=timezone.utc)


# =============================================================================
# Part 1 — the closed enum. The reason has to be countable or (c) stays a census.
# =============================================================================


def _receipt(**kw) -> MatchReceipt:
    base = dict(
        market_id=1, source="polymarket", external_id="59669077",
        market_name="Ann Li vs Donna Vekic", phase=mr.PHASE_PASS2_GENERAL,
        attempted_at=NOW,
    )
    base.update(kw)
    return MatchReceipt(**base)


def test_reject_refuses_a_reason_that_is_not_in_the_enum():
    """A typo'd reason is a silently uncountable row — it must raise instead."""
    with pytest.raises(ValueError, match="unknown match reject reason"):
        _receipt().reject("no_candidates")  # the real value is singular


def test_every_reject_constant_is_in_the_registry():
    """A constant that is not in REJECT_REASONS cannot be used at all.

    ``reject()`` validates against the frozenset, so a module-level constant
    added without registering it would raise the first time it fired — in
    production, on the matcher's own path. Caught here instead.
    """
    constants = {
        v for k, v in vars(mr).items()
        if k.startswith("REJECT_") and isinstance(v, str)
    }
    assert constants == set(mr.REJECT_REASONS), (
        f"drifted: {constants ^ set(mr.REJECT_REASONS)}"
    )


def test_the_three_states_the_null_conflated_are_separate_reasons():
    """The distinction the whole table exists to draw."""
    assert mr.REJECT_NO_CANDIDATE != mr.REJECT_OUTSIDE_TIME_WINDOW
    assert mr.REJECT_OUTSIDE_TIME_WINDOW != mr.REJECT_STATE_DISAGREES
    # And "never attempted" is not a reject reason at all — it is the ABSENCE
    # of a row. Making it a reason would let the matcher claim it looked.
    assert "never_attempted" not in mr.REJECT_REASONS


def test_reject_reasons_fit_the_column_the_migration_creates():
    """A reason longer than the column is a write that fails in production."""
    from app.models.models import MarketMatchReceipt

    width = MarketMatchReceipt.__table__.c.reject_reason.type.length
    longest = max(mr.REJECT_REASONS, key=len)
    assert len(longest) <= width, f"{longest!r} exceeds VARCHAR({width})"


def test_phase_names_fit_their_column_too():
    from app.models.models import MarketMatchReceipt

    width = MarketMatchReceipt.__table__.c.phase.type.length
    assert len(max(mr.PHASES, key=len)) <= width


def test_link_clears_a_previously_written_reject_reason():
    """A receipt cannot say both "linked" and "here is why it did not"."""
    r = _receipt()
    r.reject(mr.REJECT_NO_CANDIDATE)
    r.link(15299723)
    assert r.outcome == mr.OUTCOME_LINKED
    assert r.reject_reason is None
    assert r.linked_event_id == 15299723


def test_reject_clears_a_previously_written_event_id():
    r = _receipt()
    r.link(15299648)
    r.reject(mr.REJECT_EVENT_DATE_CONFLICT)
    assert r.linked_event_id is None


# =============================================================================
# Part 2 — the stored trace. Bounded, and the decision survives the bound.
# =============================================================================


def test_candidate_payload_keeps_the_chosen_row_even_past_the_cap():
    """Truncation must never drop the candidate that explains the outcome."""
    r = _receipt()
    for i in range(MAX_TRACE_CANDIDATES + 5):
        r.trace(CandidateTrace(event_id=1000 + i, score=float(i), verdict="lower_score"))
    r.trace(CandidateTrace(event_id=9999, score=0.5, verdict="chosen"))

    payload = r.candidate_payload()
    assert len(payload) == MAX_TRACE_CANDIDATES
    assert payload[0]["event_id"] == 9999, "the chosen candidate was truncated away"


def test_candidate_payload_orders_by_score_so_the_near_misses_survive():
    r = _receipt()
    for eid, score in [(1, 3.0), (2, 30.0), (3, 12.0)]:
        r.trace(CandidateTrace(event_id=eid, score=score, verdict="lower_score"))
    assert [c["event_id"] for c in r.candidate_payload()] == [2, 3, 1]


def test_unscored_candidates_sort_after_scored_ones():
    """A name-gate rejection has no score; it must not outrank a near miss."""
    r = _receipt()
    r.trace(CandidateTrace(event_id=1, verdict=mr.REJECT_NAME_MISMATCH))
    r.trace(CandidateTrace(event_id=2, score=18.0, verdict="lower_score"))
    assert [c["event_id"] for c in r.candidate_payload()] == [2, 1]


def test_to_row_serializes_datetimes_in_detail_so_jsonb_can_hold_them():
    """The detail carries the searched window; a raw datetime is not JSON."""
    r = _receipt()
    r.detail.update({"window_start": NOW, "nested": {"ticker_game_date": NOW}})
    r.reject(mr.REJECT_OUTSIDE_TIME_WINDOW)
    row = r.to_row()
    assert row["detail"]["window_start"] == NOW.isoformat()
    assert row["detail"]["nested"]["ticker_game_date"] == NOW.isoformat()
    import json

    json.dumps(row["detail"])  # raises if anything is still a datetime


def test_to_row_truncates_to_the_column_widths():
    r = _receipt(external_id="x" * 400, market_name="y" * 900)
    row = r.to_row()
    assert len(row["external_id"]) == 200
    assert len(row["market_name"]) == 300


# =============================================================================
# Part 3 — receipts are write-only. The matcher decides the same thing either way.
# =============================================================================


class _Sport:
    def __init__(self, key):
        self.key = key


class _Event:
    def __init__(self, id, home, away, commence, status="scheduled",
                 sport_key="tennis_atp", external_id="odds-api-1"):
        self.id = id
        self.home_team_name = home
        self.away_team_name = away
        self.commence_time = commence
        self.status = status
        self.sport = _Sport(sport_key) if sport_key else None
        self.sport_id = 7
        self.external_id = external_id


def _Matchup(team_a, team_b, format_type="bare_matchup"):
    """The REAL MatchupInfo — a stand-in would drift from what the scorer reads."""
    from app.utils.prediction_market_matching import MatchupInfo

    return MatchupInfo(team_a, team_b, yes_team=team_a, format_type=format_type)


class _Market:
    def __init__(self, external_id=None, source="polymarket",
                 llm_sport_category="tennis", name="Ann Li vs Donna Vekic"):
        self.id = 1
        self.source = source
        self.external_id = external_id
        self.name = name
        self.llm_sport_category = llm_sport_category
        self.commence_time = NOW


def _tennis_candidates():
    return [
        _Event(15299723, "Ann Li", "Donna Vekic", NOW + timedelta(minutes=40)),
        _Event(15299648, "Ann Li", "Donna Vekic", NOW + timedelta(hours=20)),
    ]


def test_score_candidates_returns_the_same_decision_with_and_without_a_receipt():
    """The load-bearing contract: a receipt observes, it does not steer.

    Run BOTH arms over the same candidates and compare the returned dict. A
    test that only checked the receipt's contents would pass just as happily on
    a version that had started matching differently while being watched.
    """
    matchup = _Matchup("Ann Li", "Donna Vekic")
    market = _Market()

    without = pmm._score_candidates(_tennis_candidates(), matchup, market, NOW, NOW)
    receipt = _receipt()
    with_ = pmm._score_candidates(
        _tennis_candidates(), matchup, market, NOW, NOW, receipt=receipt
    )

    assert without == with_
    assert with_ is not None and with_["event_id"] == 15299723
    assert receipt.candidates, "the receipt recorded nothing"


def test_the_chosen_candidate_is_marked_chosen_and_the_rest_lower_score():
    matchup = _Matchup("Ann Li", "Donna Vekic")
    receipt = _receipt()
    pmm._score_candidates(
        _tennis_candidates(), matchup, _Market(), NOW, NOW, receipt=receipt
    )
    verdicts = {c.event_id: c.verdict for c in receipt.candidates}
    assert verdicts[15299723] == "chosen"
    assert verdicts[15299648] == "lower_score"


def test_a_wrong_sport_candidate_is_traced_as_wrong_sport_not_as_a_name_problem():
    """The sport gate fires AFTER the name gate, so the names DID match.

    Reporting it as a name mismatch sends the next reader to the name
    normalizer when the bug is in the sport filing — which is exactly the wrong
    place for the 463 US Open rows filed as ``table_tennis``.
    """
    matchup = _Matchup("Ann Li", "Donna Vekic")
    market = _Market(external_id=None, llm_sport_category="tennis")
    candidates = [
        _Event(1, "Ann Li", "Donna Vekic", NOW, sport_key="tabletennis_wtt"),
    ]
    receipt = _receipt()
    result = pmm._score_candidates(
        candidates, matchup, market, NOW, NOW, receipt=receipt
    )
    assert result is None
    assert [c.verdict for c in receipt.candidates] == [mr.REJECT_WRONG_SPORT]
    assert pmm._reason_from_traces(receipt.candidates) == mr.REJECT_WRONG_SPORT


def test_a_name_gate_rejection_is_traced_as_a_name_mismatch():
    matchup = _Matchup("Ann Li", "Donna Vekic")
    candidates = [_Event(1, "Ann Li", "Iga Swiatek", NOW)]
    receipt = _receipt()
    result = pmm._score_candidates(
        candidates, matchup, _Market(), NOW, NOW, receipt=receipt
    )
    assert result is None
    assert [c.verdict for c in receipt.candidates] == [mr.REJECT_NAME_MISMATCH]


def test_wrong_sport_outranks_name_mismatch_in_the_reason():
    """Most specific wins: a candidate that reached the sport gate had already
    passed the name gate, so the name is not the story."""
    traces = [
        CandidateTrace(event_id=1, verdict=mr.REJECT_NAME_MISMATCH),
        CandidateTrace(event_id=2, verdict=mr.REJECT_WRONG_SPORT),
    ]
    assert pmm._reason_from_traces(traces) == mr.REJECT_WRONG_SPORT


def test_score_below_outranks_everything():
    traces = [
        CandidateTrace(event_id=1, verdict=mr.REJECT_WRONG_SPORT),
        CandidateTrace(event_id=2, verdict=mr.REJECT_NAME_SCORE_BELOW),
    ]
    assert pmm._reason_from_traces(traces) == mr.REJECT_NAME_SCORE_BELOW


def test_no_traces_means_no_reason_so_the_caller_must_probe():
    """An empty trace is not "name mismatch" — nothing was even considered."""
    assert pmm._reason_from_traces([]) is None


def test_the_low_confidence_floor_is_traced_as_a_score_refusal():
    """The no-sport-prefix score floor: a real refusal with a real number."""
    matchup = _Matchup("Royals", "Indians")
    # No ticker and no llm_sport_category ⇒ no sport prefix ⇒ the score floor
    # applies, and a far-future candidate cannot clear it.
    market = _Market(external_id=None, llm_sport_category=None)
    candidates = [
        _Event(1, "Royals", "Indians", NOW + timedelta(days=13), sport_key=None,
               external_id=None),
    ]
    receipt = _receipt()
    result = pmm._score_candidates(
        candidates, matchup, market, NOW, NOW, receipt=receipt
    )
    assert result is None
    assert pmm._reason_from_traces(receipt.candidates) == mr.REJECT_NAME_SCORE_BELOW
    assert receipt.detail["score_floor"] == 21


# =============================================================================
# Part 4 — the backlog pass's POPULATION. Compiled and executed, not asserted at.
#
# A fake session returns whatever rows it was handed, whatever the predicate
# says, so the only honest test of "which markets does the sweep pick up" is to
# take the statements the sweep really issues, compile them, and run them over
# planted rows.
# =============================================================================


class _CapturingSession:
    """Records statements, returns nothing, so the sweep's SQL can be read off."""

    def __init__(self):
        self.statements = []

    async def execute(self, stmt):
        self.statements.append(stmt)

        class _Empty:
            def all(self_inner):
                return []

            def scalars(self_inner):
                return self_inner

            def unique(self_inner):
                return self_inner

        return _Empty()

    async def scalar(self, stmt):
        self.statements.append(stmt)
        return 0

    async def commit(self):
        pass

    async def rollback(self):
        pass


def _backlog_statements():
    stats = {"funnel": {}, "errors": [], "markets_scanned": 0}
    session = _CapturingSession()
    asyncio.run(
        pmm._phase1_pass3_backlog_scan(
            session, stats, NOW, set(), [], lambda: 700.0,
        )
    )
    assert session.statements, "the backlog pass issued no query at all"
    return [
        s.compile(
            dialect=sqlite_dialect.dialect(), compile_kwargs={"literal_binds": True}
        ).string
        for s in session.statements
    ], stats


#: (id, source, status, event_id, has_receipt, selected_by_never_query, why)
BACKLOG_ROWS = [
    (1, "polymarket", "open", None, False, True,
     "the 8/28 wave: open, unlinked, never attempted — the whole point"),
    (2, "polymarket", "open", None, True, False,
     "already has a receipt: it goes in the stale queue, not the never queue"),
    (3, "polymarket", "open", 15299723, False, False,
     "already linked: the sweep is for unattached markets"),
    (4, "polymarket", "closed", None, False, False,
     "closed: a settled market is not waiting to be attached"),
    (5, "odds_api", "open", None, False, False,
     "not a prediction market source"),
    (6, "kalshi", "open", None, False, True,
     "Kalshi backlog counts too — pass 1's ticker scan does not cover "
     "non-ticker Kalshi rows"),
]


def _plant(conn):
    conn.execute(
        "CREATE TABLE futures_markets (id INTEGER PRIMARY KEY, source TEXT, "
        "status TEXT, event_id INTEGER, updated_at TEXT, external_id TEXT, "
        "name TEXT, category TEXT, llm_sport_category TEXT, commence_time TEXT)"
    )
    conn.execute(
        "CREATE TABLE market_match_receipts (id INTEGER PRIMARY KEY, "
        "market_id INTEGER, last_attempted_at TEXT)"
    )
    for mid, source, status, event_id, has_receipt, _sel, _why in BACKLOG_ROWS:
        conn.execute(
            "INSERT INTO futures_markets (id, source, status, event_id, "
            "updated_at, external_id, name, category, llm_sport_category, "
            "commence_time) VALUES (?,?,?,?,?,?,?,?,?,?)",
            (mid, source, status, event_id, "2026-08-28T00:00:00", f"x{mid}",
             "A vs B", "prop", "tennis", "2026-09-02T20:00:00"),
        )
        if has_receipt:
            conn.execute(
                "INSERT INTO market_match_receipts (market_id, last_attempted_at) "
                "VALUES (?,?)",
                (mid, "2026-08-20T00:00:00"),
            )
    conn.commit()


def test_the_never_attempted_query_selects_exactly_the_starved_rows():
    """Run the real SELECT. Planted rows, one expectation per row."""
    sql, _ = _backlog_statements()
    never_sql = sql[0]
    # sqlite has no ILIKE/tz types in play here; the predicate is plain.
    never_sql = re.sub(r"\bSELECT futures_markets\.[^F]+FROM", "SELECT futures_markets.id FROM", never_sql, count=1)

    conn = sqlite3.connect(":memory:")
    _plant(conn)
    got = {r[0] for r in conn.execute(never_sql).fetchall()}
    conn.close()

    expected = {r[0] for r in BACKLOG_ROWS if r[5]}
    for mid, _s, _st, _e, _hr, sel, why in BACKLOG_ROWS:
        assert (mid in got) is sel, f"market {mid} — {why}"
    assert got == expected


def test_the_stale_query_orders_oldest_receipt_first():
    """The ordering IS the fix: nothing can be overtaken by a newer wave."""
    sql, _ = _backlog_statements()
    stale_sql = next(s for s in sql if "JOIN market_match_receipts" in s)
    assert "last_attempted_at ASC" in stale_sql, (
        "the backlog pass must take the oldest receipt first; ordering it any "
        "other way rebuilds the recency starvation it exists to end"
    )


def test_pass2_still_orders_by_recency_so_fresh_ingest_is_not_delayed():
    """The sweep is additive. New markets must still be matched promptly."""
    src = inspect.getsource(pmm._phase1_pass2_general_scan)
    assert "updated_at.desc()" in src


def test_the_backlog_cap_is_reported_not_silent():
    """A cap nobody can see reads as "we attempted everything"."""
    _, stats = _backlog_statements()
    assert "backlog_dropped" in stats["funnel"]
    assert "backlog_eligible_total" in stats["funnel"]
    assert "backlog_scanned" in stats["funnel"]


def test_the_backlog_pass_stands_down_when_the_task_is_out_of_time():
    """It must never starve the price-snapshot phases it runs in front of."""
    stats = {"funnel": {}, "errors": [], "markets_scanned": 0}
    session = _CapturingSession()
    asyncio.run(
        pmm._phase1_pass3_backlog_scan(
            session, stats, NOW, set(), [],
            lambda: pmm._BACKLOG_MIN_SECONDS_REMAINING - 1,
        )
    )
    assert stats["funnel"]["backlog_skipped_budget"] is True
    assert session.statements == [], "it queried anyway"


def test_the_matcher_runs_the_backlog_pass():
    """A pass nobody calls is a pass that does not exist."""
    src = inspect.getsource(pmm._match_prediction_markets)
    assert "_phase1_pass3_backlog_scan" in src


def test_the_backlog_pass_uses_the_same_attempt_path_as_pass2():
    """Two matchers is two sets of answers. Both passes call _attempt_market."""
    assert "_attempt_market" in inspect.getsource(pmm._phase1_pass3_backlog_scan)
    assert "_attempt_market" in inspect.getsource(pmm._phase1_pass2_general_scan)


# =============================================================================
# Part 5 — no attempt escapes without a reason.
# =============================================================================


class _FakeMarket:
    """The attributes _attempt_market touches, and no others."""

    def __init__(self, id=1, name="Championship 2026", category="championship",
                 source="polymarket", external_id="abc", group_type=None,
                 group_id=None, llm_sport_category="tennis"):
        self.id = id
        self.name = name
        self.category = category
        self.source = source
        self.external_id = external_id
        self.group_type = group_type
        self.group_id = group_id
        self.llm_sport_category = llm_sport_category
        self.commence_time = NOW
        self.event_id = None


def _run_attempt(market):
    stats = {
        "funnel": {
            "not_game_level": 0, "no_matchup_extracted": 0,
            "game_level_detected": 0, "no_event_found": 0, "linked": 0,
            "sample_not_game_level": [], "sample_game_level_no_event": [],
        },
        "errors": [], "markets_scanned": 0, "newly_linked": 0,
    }
    receipts: list[MatchReceipt] = []
    asyncio.run(
        pmm._attempt_market(
            _CapturingSession(), market, stats, NOW, [], lambda: 700.0,
            receipts, mr.PHASE_PASS3_BACKLOG,
        )
    )
    assert len(receipts) == 1
    return receipts[0], stats


def test_a_container_row_is_filed_as_a_parent_not_as_not_game_level():
    """Parent rows are a ROW KIND, not a matching verdict.

    Letting them fall into ``not_game_level`` makes that bucket a mix of
    "futures market" and "group header", and the reconciliation job's counts
    stop being about matching.
    """
    receipt, _ = _run_attempt(
        _FakeMarket(name="US Open Winner", group_type="polymarket_event",
                    group_id="polymarket:924353")
    )
    assert receipt.reject_reason == mr.REJECT_PARENT_ROW
    assert receipt.detail["group_id"] == "polymarket:924353"


def test_a_futures_market_is_filed_as_not_game_level():
    receipt, stats = _run_attempt(_FakeMarket(name="Who wins the US Open?"))
    assert receipt.reject_reason == mr.REJECT_NOT_GAME_LEVEL
    assert stats["funnel"]["not_game_level"] == 1


def test_every_attempt_leaves_a_receipt_carrying_a_reason_or_a_link():
    """The invariant. A receipt with neither is the old NULL in a new table."""
    for market in [
        _FakeMarket(name="Who wins the US Open?"),
        _FakeMarket(name="Championship", group_type="kalshi_event"),
    ]:
        receipt, _ = _run_attempt(market)
        assert (receipt.reject_reason is not None) ^ (
            receipt.outcome == mr.OUTCOME_LINKED
        ), f"{market.name}: receipt explains nothing"
        assert receipt.reject_reason in mr.REJECT_REASONS or receipt.reject_reason is None


def test_the_receipt_records_which_pass_reached_the_market():
    """A market only ever seen by pass 3 is one the ordinary scans never get
    to — that is a finding about the scan, not noise."""
    receipt, _ = _run_attempt(_FakeMarket(name="Who wins the US Open?"))
    assert receipt.phase == mr.PHASE_PASS3_BACKLOG
    assert receipt.phase in mr.PHASES


# =============================================================================
# Part 6 — the write. Deduped, accumulating, and never fatal.
# =============================================================================


def test_flush_dedupes_within_a_batch():
    """Postgres refuses an ON CONFLICT that hits one key twice in one command
    ("cannot affect row a second time"), and one market CAN be seen by two
    passes in one run. The later attempt wins."""
    captured = {}

    class _Session:
        async def execute(self, stmt):
            captured["stmt"] = stmt
            captured["rows"] = stmt.compile().params
            return None

    first = _receipt(market_id=42, phase=mr.PHASE_PASS2_GENERAL)
    first.reject(mr.REJECT_NO_CANDIDATE)
    second = _receipt(market_id=42, phase=mr.PHASE_PASS3_BACKLOG)
    second.link(15299723)

    written = asyncio.run(mr.flush_receipts(_Session(), [first, second]))
    assert written == 1
    params = captured["rows"]
    assert params["outcome_m0"] == mr.OUTCOME_LINKED
    assert params["phase_m0"] == mr.PHASE_PASS3_BACKLOG


def test_flush_is_a_noop_on_an_empty_batch():
    class _Session:
        async def execute(self, stmt):  # pragma: no cover - must not be called
            raise AssertionError("issued a statement for zero receipts")

    assert asyncio.run(mr.flush_receipts(_Session(), [])) == 0


class _FailingSessionFactory:
    """A session whose every write raises, as an async context manager."""

    def __call__(self):
        return self

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return False

    async def execute(self, stmt):
        raise RuntimeError("relation \"market_match_receipts\" does not exist")

    async def commit(self):
        pass


def test_a_receipt_write_failure_does_not_fail_the_matcher():
    """Receipts are a record, not a constraint. Losing the log must not lose
    the links the pass already committed — but the failure IS counted, because
    a receipts table that quietly stops being written is worse than none."""
    stats = {"funnel": {}, "errors": []}
    r = _receipt()
    r.reject(mr.REJECT_NO_CANDIDATE)
    asyncio.run(
        pmm._flush_pass_receipts(
            _CapturingSession(), [r], stats, mr.PHASE_PASS2_GENERAL,
            session_factory=_FailingSessionFactory(),
        )
    )
    assert stats["funnel"]["receipt_write_failures"] == 1
    assert any("receipts_" in e for e in stats["errors"])


def test_receipts_are_written_on_their_own_session_not_the_matchers():
    """The matcher's session carries the pass's pending event_id assignments.

    Writing receipts on it would put the links inside the same transaction as
    the log, so one bad receipt row would roll back real matching work. Proved
    by handing in a matcher session that fails on any use at all.
    """

    class _Exploding:
        async def execute(self, stmt):
            raise AssertionError("receipts were written on the matcher's session")

        async def commit(self):
            raise AssertionError("receipts committed the matcher's transaction")

    captured = []

    class _Recording(_FailingSessionFactory):
        async def execute(self, stmt):
            captured.append(stmt)

    stats = {"funnel": {}, "errors": []}
    r = _receipt()
    r.reject(mr.REJECT_NO_CANDIDATE)
    asyncio.run(
        pmm._flush_pass_receipts(
            _Exploding(), [r], stats, mr.PHASE_PASS2_GENERAL,
            session_factory=_Recording(),
        )
    )
    assert stats["funnel"]["receipts_written"] == 1
    assert stats["funnel"].get("receipt_write_failures") is None
    assert len(captured) == 1


def test_the_upsert_accumulates_attempt_count_rather_than_resetting_it():
    """"Refused 340 times since 8/28" is a different finding from "refused"."""
    src = inspect.getsource(mr.flush_receipts)
    assert "attempt_count + 1" in src
    assert "func.least" in src, (
        "first_attempted_at must never move forward — LEAST(old, new)"
    )


# =============================================================================
# Part 7 — the endpoint. One call answers "why is market X unattached".
# =============================================================================


class _Row:
    def __init__(self, **kw):
        self.__dict__.update(kw)


class _FakeResult:
    def __init__(self, rows):
        self._rows = rows

    def scalars(self):
        return self

    def first(self):
        return self._rows[0] if self._rows else None

    def all(self):
        return self._rows

    def one(self):
        return self._rows[0]


class _FakeDB:
    """Serves queued results in order; records nothing else."""

    def __init__(self, results, scalar=0):
        self._results = list(results)
        self._scalar = scalar

    async def execute(self, stmt):
        return self._results.pop(0)

    async def scalar(self, stmt):
        return self._scalar


def _receipt_row(**kw):
    base = dict(
        market_id=59669077, source="polymarket", external_id="0xabc",
        market_name="Ann Li vs Donna Vekic", phase=mr.PHASE_PASS3_BACKLOG,
        outcome=mr.OUTCOME_REJECTED, reject_reason=mr.REJECT_OUTSIDE_TIME_WINDOW,
        linked_event_id=None,
        candidates=[{"event_id": 15299723, "verdict": "outside_time_window"}],
        detail={"team_a": "Ann Li", "team_b": "Donna Vekic"},
        attempt_count=41, first_attempted_at=NOW - timedelta(days=5),
        last_attempted_at=NOW,
    )
    base.update(kw)
    return _Row(**base)


def _call(**kw):
    from unittest.mock import patch

    from app.routes.admin_matching import match_receipts as endpoint

    db = kw.pop("db")
    with patch("app.routes.admin_matching._check_admin_secret", lambda *a, **k: None):
        return asyncio.run(endpoint(request=None, secret="x", db=db, **kw))


def test_one_call_answers_why_a_market_is_unattached():
    """The bus's acceptance test, in the shape the bus will run it."""
    out = _call(
        db=_FakeDB([_FakeResult([_receipt_row()])]),
        market_id=59669077, external_id=None, event_id=None,
        reject_reason=None, source=None, limit=50,
    )
    r = out["receipt"]
    assert r["reject_reason"] == mr.REJECT_OUTSIDE_TIME_WINDOW
    assert r["candidates"][0]["event_id"] == 15299723
    assert r["attempt_count"] == 41
    assert r["detail"]["team_a"] == "Ann Li"


def test_a_market_with_no_receipt_is_reported_as_never_attempted_not_as_empty():
    """Gotcha #53: an empty 200 is a response shape, not an absence.

    "Never attempted" and "attempted and refused" are the two answers this whole
    table exists to separate, so the endpoint must not collapse them into a
    missing key the caller reads as "nothing to report".
    """
    market_row = _Row(
        id=59669077, external_id="0xabc", name="Ann Li vs Donna Vekic",
        source="polymarket", status="open", event_id=None,
        created_at=NOW - timedelta(days=5),
    )
    out = _call(
        db=_FakeDB([_FakeResult([]), _FakeResult([market_row])]),
        market_id=59669077, external_id=None, event_id=None,
        reject_reason=None, source=None, limit=50,
    )
    assert out["receipt"] is None
    assert out["state"] == "never_attempted"
    assert out["market"]["id"] == 59669077


def test_an_unknown_market_is_a_404_not_a_never_attempted_claim():
    """"We never looked at it" is a claim about the matcher. Do not make it
    about a market that does not exist."""
    from fastapi import HTTPException

    with pytest.raises(HTTPException) as exc:
        _call(
            db=_FakeDB([_FakeResult([]), _FakeResult([])]),
            market_id=1, external_id=None, event_id=None,
            reject_reason=None, source=None, limit=50,
        )
    assert exc.value.status_code == 404


def test_an_unknown_reject_reason_filter_is_refused_by_name():
    """Silently returning zero rows for a typo'd filter reads as "none of those
    exist" — the same lie the whole table is here to stop telling."""
    from fastapi import HTTPException

    with pytest.raises(HTTPException) as exc:
        _call(
            db=_FakeDB([]), market_id=None, external_id=None, event_id=None,
            reject_reason="no_candidates", source=None, limit=50,
        )
    assert exc.value.status_code == 400
    assert "no_candidates" in str(exc.value.detail)


def test_the_summary_reports_the_coverage_number_the_bus_could_not_measure():
    """open unlinked markets with NO receipt — ARTIFACT-M-20260902-O's hole."""
    reason_rows = [_Row(reject_reason=mr.REJECT_NO_CANDIDATE, source="polymarket", n=6626)]
    totals = _Row(receipts=31433, linked=10021, oldest=NOW - timedelta(hours=2), newest=NOW)
    out = _call(
        db=_FakeDB([_FakeResult(reason_rows), _FakeResult([totals])], scalar=0),
        market_id=None, external_id=None, event_id=None,
        reject_reason=None, source=None, limit=50,
    )
    assert out["coverage"]["open_unlinked_without_receipt"] == 0
    assert out["coverage"]["target"] == 0
    assert out["totals"]["rejected"] == 31433 - 10021
    assert out["by_reason"][0]["count"] == 6626
    assert sorted(mr.REJECT_REASONS) == out["valid_reasons"]


def test_the_backlog_pass_holds_a_reserve_for_the_snapshot_phase():
    """Pass 3 runs in FRONT of Phase 2, which writes the chart line.

    Measured task cost is 337s p50 / 699s p95 against an 840s soft limit, so a
    sweep that spent the slack would set `phase2_skipped_budget` and take the
    live charts down to buy a diagnosis. The reserve must be larger than the
    other passes' 120s floor, or it is not a reserve.
    """
    assert pmm._BACKLOG_DOWNSTREAM_RESERVE_SECONDS >= 400
    assert (
        pmm._BACKLOG_MIN_SECONDS_REMAINING
        > pmm._BACKLOG_DOWNSTREAM_RESERVE_SECONDS
    ), "starting below the reserve means the pass stops on its first check"
    src = inspect.getsource(pmm._phase1_pass3_backlog_scan)
    assert "_BACKLOG_DOWNSTREAM_RESERVE_SECONDS" in src


def test_the_backlog_pass_stops_at_the_reserve_rather_than_running_to_the_floor():
    """Hand it a clock that is past the reserve but above the other passes'
    120s floor: it must stand down, not keep going."""
    stats = {"funnel": {}, "errors": [], "markets_scanned": 0}
    session = _CapturingSession()
    asyncio.run(
        pmm._phase1_pass3_backlog_scan(
            session, stats, NOW, set(), [],
            lambda: pmm._BACKLOG_DOWNSTREAM_RESERVE_SECONDS + 1,
        )
    )
    assert stats["funnel"]["backlog_skipped_budget"] is True
