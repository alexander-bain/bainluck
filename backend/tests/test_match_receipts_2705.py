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
from sqlalchemy.exc import MissingGreenlet

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


#: (id, source, status, event_id, has_receipt, selected_by_never_query, name, why)
#:
#: THE NAMES ARE NOT DECORATION. Row 7 is a non-game market whose name shares no
#: token with a matchup, so a predicate that narrows this population to
#: game-shaped rows selects a DIFFERENT set here and the tests that compare two
#: selections go red. With every row called "A vs B" that narrowing was
#: invisible and the comparison was vacuous (#2803).
BACKLOG_ROWS = [
    (1, "polymarket", "open", None, False, True, "Ann Li vs Donna Vekic",
     "the 8/28 wave: open, unlinked, never attempted — the whole point"),
    (2, "polymarket", "open", None, True, False, "Alcaraz vs Sinner",
     "already has a receipt: it goes in the stale queue, not the never queue"),
    (3, "polymarket", "open", 15299723, False, False, "Swiatek vs Gauff",
     "already linked: the sweep is for unattached markets"),
    (4, "polymarket", "closed", None, False, False, "Djokovic vs Medvedev",
     "closed: a settled market is not waiting to be attached"),
    (5, "odds_api", "open", None, False, False, "Rybakina vs Sabalenka",
     "not a prediction market source"),
    (6, "kalshi", "open", None, False, True, "Yankees vs Red Sox",
     "Kalshi backlog counts too — pass 1's ticker scan does not cover "
     "non-ticker Kalshi rows"),
    (7, "kalshi", "open", None, False, True, "10Y US Treasury yield at year-end?",
     "the 7,480 (#2803): economics, no game, never will be. Pass 3 SELECTS it "
     "and the attempt refuses it with not_game_level — which is a receipt, so "
     "it leaves the numerator. Narrowing the coverage denominator to game-shaped "
     "rows would hide it instead of explaining it"),
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
    for mid, source, status, event_id, has_receipt, _sel, name, _why in BACKLOG_ROWS:
        conn.execute(
            "INSERT INTO futures_markets (id, source, status, event_id, "
            "updated_at, external_id, name, category, llm_sport_category, "
            "commence_time) VALUES (?,?,?,?,?,?,?,?,?,?)",
            (mid, source, status, event_id, "2026-08-28T00:00:00", f"x{mid}",
             name, "prop", "tennis", "2026-09-02T20:00:00"),
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
    for mid, _s, _st, _e, _hr, sel, _name, why in BACKLOG_ROWS:
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
    """Serves queued results in order; records nothing else.

    An exhausted queue yields an EMPTY result rather than raising, so a test
    that cares about the first three summary queries does not have to enumerate
    the coverage queries (#2803) that run after them. The statements are still
    recorded — a test that wants to assert on a later query reads
    ``.statements`` and compiles it itself.
    """

    def __init__(self, results, scalar=0):
        self._results = list(results)
        self._scalar = scalar
        self.statements: list = []

    async def execute(self, stmt):
        self.statements.append(stmt)
        return self._results.pop(0) if self._results else _FakeResult([])

    async def scalar(self, stmt):
        return self._scalar


def _receipt_row(**kw):
    base = dict(
        market_id=59669077, source="polymarket", external_id="0xabc",
        market_name="Ann Li vs Donna Vekic", phase=mr.PHASE_PASS3_BACKLOG,
        outcome=mr.OUTCOME_REJECTED, reject_reason=mr.REJECT_OUTSIDE_TIME_WINDOW,
        linked_event_id=None, previous_event_id=None, actor=None,
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
    # Called as a plain coroutine, so every Query() default has to be supplied
    # by hand — an unsupplied one arrives as the Query object itself, not its
    # default, and fails inside whatever arithmetic first touches it.
    kw.setdefault("since_hours", 24)
    with patch("app.routes.admin_matching._check_admin_secret", lambda *a, **k: None):
        return asyncio.run(endpoint(request=None, secret="x", db=db, **kw))


def test_one_call_answers_why_a_market_is_unattached():
    """The bus's acceptance test, in the shape the bus will run it.

    Two results are queued because the single-market answer is two questions
    since LINKLOSS-03: what the last attempt decided (the receipt, which the
    next attempt overwrites) and what has actually happened to this market's
    link (the append-only history, which nothing overwrites).
    """
    out = _call(
        db=_FakeDB([_FakeResult([_receipt_row()]), _FakeResult([])]),
        market_id=59669077, external_id=None, event_id=None,
        reject_reason=None, source=None, limit=50,
    )
    r = out["receipt"]
    assert r["reject_reason"] == mr.REJECT_OUTSIDE_TIME_WINDOW
    assert r["candidates"][0]["event_id"] == 15299723
    assert r["attempt_count"] == 41
    assert r["detail"]["team_a"] == "Ann Li"
    assert out["link_changes"] == []


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
    reason_rows = [
        _Row(
            reject_reason=mr.REJECT_NO_CANDIDATE,
            source="polymarket",
            n=6626,
            still_linkable=6626,
        )
    ]
    totals = _Row(receipts=31433, linked=10021, oldest=NOW - timedelta(hours=2), newest=NOW)
    change_rows = [
        _Row(outcome=mr.OUTCOME_SUPERSEDED_BY_TWIN_MERGE,
             actor=mr.ACTOR_TWIN_CLEANUP, phase=mr.PHASE_TWIN_MERGE, n=261),
        _Row(outcome=mr.OUTCOME_UNLINKED, actor=mr.ACTOR_MATCHER_PASS,
             phase=mr.PHASE_PHASE15_REVALIDATE, n=4),
    ]
    out = _call(
        db=_FakeDB(
            [_FakeResult(reason_rows), _FakeResult([totals]),
             _FakeResult(change_rows)],
            scalar=0,
        ),
        market_id=None, external_id=None, event_id=None,
        reject_reason=None, source=None, limit=50,
    )
    assert out["coverage"]["open_unlinked_without_receipt"] == 0
    assert out["coverage"]["target"] == 0
    assert out["totals"]["rejected"] == 31433 - 10021
    assert out["by_reason"][0]["count"] == 6626
    assert sorted(mr.REJECT_REASONS) == out["valid_reasons"]


def _ran(rows_attempted=3000, at=None):
    """The durable fact a completed Pass 3 leaves behind (#2803/CERT-819)."""
    from app.utils.matcher_pass_runs import PassRunFact

    return PassRunFact(
        phase=mr.PHASE_PASS3_BACKLOG, has_run=True, status="ok",
        last_run_at=at or NOW, rows_attempted=rows_attempted,
    )


class TestTheCoverageNumberIsHonestAboutItsOwnDenominator:
    """#2803. The published figure was 36,966 open unlinked markets without a
    receipt against ``target: 0``, and it was unreadable three ways.

    #2803 proposed narrowing the denominator to game-shaped rows, on the premise
    that 7,480 Kalshi economics/politics markets are ones "the game matcher is
    not supposed to touch". THE CODE SAYS OTHERWISE, and that is what the first
    test below pins: ``_phase1_pass3_backlog_scan`` selects *exactly* this set,
    and ``_run_one_attempt`` refuses a non-game row with ``not_game_level`` —
    which is a RECEIPT, so the row leaves the numerator. Target 0 is reachable;
    narrowing would have hidden 7,480 rows Pass 3 really does attempt.

    What was actually wrong is published instead: the composition (most of what
    clears is a refusal, not a link), the source split (every receipt in the
    table carried ``pass1_ticker``, which is Kalshi-only, so Polymarket's 29,486
    was a fact about the writer), and whether the pass that drives the number
    down has ever run.
    """

    @staticmethod
    def _coverage_db(never_rows=(), explained_rows=(), phase_rows=()):
        """The six result sets the endpoint reads, in the order it reads them."""
        return _FakeDB(
            [
                _FakeResult([]),                       # reason histogram
                _FakeResult([_Row(receipts=0, linked=0, oldest=None, newest=None)]),
                _FakeResult([]),                       # link-change census
                _FakeResult(list(never_rows)),
                _FakeResult(list(explained_rows)),
                _FakeResult(list(phase_rows)),
            ],
            scalar=0,
        )

    @staticmethod
    def _summary(never_rows=(), explained_rows=(), phase_rows=(), pass_run=None):
        """``pass_run`` stands in for the durable per-pass row (#2803/CERT-819).

        Defaults to "no durable row", the state production was measured in —
        which is published as ``null``, not ``false`` (CERT-824).
        """
        from unittest.mock import patch

        from app.utils.matcher_pass_runs import STATUS_NO_RECORD, PassRunFact

        fact = pass_run or PassRunFact(
            phase=mr.PHASE_PASS3_BACKLOG, has_run=None, status=STATUS_NO_RECORD,
        )
        witness_seen: list = []

        db = TestTheCoverageNumberIsHonestAboutItsOwnDenominator._coverage_db(
            never_rows, explained_rows, phase_rows
        )

        async def _fake_read(_db, _phase, **kw):
            witness_seen.append(kw.get("receipt_witness"))
            return fact

        with patch("app.utils.matcher_pass_runs.read_pass_run", _fake_read):
            out = _call(
                db=db, market_id=None, external_id=None, event_id=None,
                reject_reason=None, source=None, limit=50,
            )
        db.witness_seen = witness_seen
        return out["coverage"], db

    def test_the_denominator_is_pass3s_own_eligibility_set_row_for_row(self):
        """THE LOAD-BEARING CLAIM, run rather than read.

        Both SELECTs are compiled and executed over the same planted rows. If
        anyone narrows the endpoint's denominator (to game-shaped markets, to
        one source, to a name filter) without narrowing Pass 3 the same way,
        the two sets diverge and this goes red — which is the whole reason
        ``target: 0`` is allowed to stand.
        """
        _cov, db = self._summary()
        coverage_stmt = next(
            s for s in db.statements
            if "NOT (EXISTS" in str(s) and "GROUP BY" in str(s)
        )
        coverage_sql = coverage_stmt.compile(
            dialect=sqlite_dialect.dialect(),
            compile_kwargs={"literal_binds": True},
        ).string
        # Count per source -> ids, so the two queries are comparable as SETS.
        coverage_sql = re.sub(
            r"^SELECT.*?FROM", "SELECT futures_markets.id FROM",
            coverage_sql, count=1, flags=re.S,
        )
        coverage_sql = re.sub(r"\s*GROUP BY.*$", "", coverage_sql, flags=re.S)

        never_sql = _backlog_statements()[0][0]
        never_sql = re.sub(
            r"\bSELECT futures_markets\.[^F]+FROM",
            "SELECT futures_markets.id FROM", never_sql, count=1,
        )

        conn = sqlite3.connect(":memory:")
        _plant(conn)
        from_coverage = {r[0] for r in conn.execute(coverage_sql).fetchall()}
        from_pass3 = {r[0] for r in conn.execute(never_sql).fetchall()}
        conn.close()

        assert from_coverage == from_pass3, (
            "the coverage denominator and Pass 3's never-attempted queue have "
            f"drifted: coverage={sorted(from_coverage)} "
            f"pass3={sorted(from_pass3)}. While they are equal, target 0 is "
            "reachable by definition; once they are not, the target is a wish."
        )
        # And it is not vacuously equal because both are empty.
        assert from_coverage == {r[0] for r in BACKLOG_ROWS if r[5]}

    def test_a_non_game_market_leaves_the_numerator_by_being_refused(self):
        """Why target 0 is reachable at all. ``10Y US Treasury yield at
        year-end?`` will never link, but the attempt writes ``not_game_level``
        and it stops being uncounted. If this gate ever returns without a
        reason, the 7,480 become permanently unexplainable and #2803's
        narrowing becomes the only honest option."""
        src = inspect.getsource(pmm._run_one_attempt)
        gate = src.split("extract_matchup_with_ticker_fallback")[0]
        assert "is_game_level_market" in gate
        assert "REJECT_NOT_GAME_LEVEL" in gate, (
            "the non-game gate must reject with a reason, not just return"
        )
        # …and the parent-row branch it defers to also always sets one.
        assert "REJECT_PARENT_ROW" in inspect.getsource(
            pmm._receipt_parent_or_not_game_level
        )

    def test_the_number_is_split_by_source_and_both_sources_are_named(self):
        """One number across a source the matcher reaches and a source it does
        not is not a coverage number. A source at zero must still appear —
        absent, it reads as covered."""
        cov, _ = self._summary(
            never_rows=[_Row(source="kalshi", n=7480)],
            explained_rows=[_Row(source="kalshi", n=178, no_game_here=13)],
        )
        assert cov["by_source"]["kalshi"]["without_receipt"] == 7480
        assert cov["by_source"]["kalshi"]["with_receipt"] == 178
        assert cov["by_source"]["kalshi"]["explained_no_game_here"] == 13
        # Polymarket wrote no rows at all — it is still published, at zero.
        assert cov["by_source"]["polymarket"] == {
            "without_receipt": 0, "with_receipt": 0, "explained_no_game_here": 0,
        }
        assert cov["open_unlinked_without_receipt"] == 7480

    def test_the_headline_total_is_the_sum_of_the_split(self):
        """The two must not be able to disagree — a total computed by its own
        query would drift from the split the first time one of them changed."""
        cov, _ = self._summary(
            never_rows=[
                _Row(source="kalshi", n=7480),
                _Row(source="polymarket", n=29486),
            ],
        )
        assert cov["open_unlinked_without_receipt"] == 36966
        assert sum(
            v["without_receipt"] for v in cov["by_source"].values()
        ) == cov["open_unlinked_without_receipt"]

    def test_it_says_whether_the_pass_that_drives_it_has_ever_run(self):
        """Measured on production 2026-09-03: every receipt in the table
        carried ``pass1_ticker``. Passes 2 and 3 had never written a row, so the
        number could not fall — and nothing in the response said so."""
        cov, _ = self._summary(
            never_rows=[_Row(source="kalshi", n=7480)],
            phase_rows=[_Row(phase=mr.PHASE_PASS1_TICKER, n=138676)],
        )
        # Null, not false: no durable row and no receipt witnessing a run means
        # no evidence, and CERT-824 blocked publishing that as "never ran".
        assert cov["backlog_pass_has_run"] is None
        assert cov["backlog_pass"]["status"] == "no_record"
        assert cov["receipt_phase_labels_now"] == {mr.PHASE_PASS1_TICKER: 138676}

        cov, _ = self._summary(
            never_rows=[_Row(source="kalshi", n=12)],
            phase_rows=[
                _Row(phase=mr.PHASE_PASS1_TICKER, n=7000),
                _Row(phase=mr.PHASE_PASS3_BACKLOG, n=3000),
            ],
            pass_run=_ran(rows_attempted=3000),
        )
        assert cov["backlog_pass_has_run"] is True

    def test_pass1_overwriting_every_pass3_label_does_not_unmake_the_run(self):
        """CERT-819, the exact sequence it blocked on, at the endpoint.

        The receipt table is one MUTABLE row per market and the upsert sets
        ``phase = excluded.phase``, so after Pass 3 runs, Pass 1/2 re-attempting
        those same open unlinked markets erase every ``pass3_backlog`` label.
        The census below is that end state — 100% ``pass1_ticker``, not one
        ``pass3_backlog`` row left — and the flag must STILL be true, because
        the pass did run.
        """
        after_erasure = [_Row(phase=mr.PHASE_PASS1_TICKER, n=138676)]

        cov, _ = self._summary(
            never_rows=[_Row(source="kalshi", n=7480)],
            phase_rows=after_erasure,
            pass_run=_ran(rows_attempted=3000),
        )
        assert cov["backlog_pass_has_run"] is True, (
            "a later pass overwriting the phase label unmade the run — that is "
            "the CERT-819 defect back"
        )
        assert cov["backlog_pass"]["last_run_at"] == NOW.isoformat()
        assert cov["backlog_pass"]["rows_attempted"] == 3000

        # THE RED ARM. The blocked derivation, evaluated on the same state: it
        # says "never ran" about a table where Pass 3 demonstrably ran. Without
        # this, the assertion above could pass for the wrong reason.
        phases_seen = {r.phase: r.n for r in after_erasure}
        assert (mr.PHASE_PASS3_BACKLOG in phases_seen) is False, (
            "the old label-census derivation is supposed to be wrong here; if "
            "it is right, this fixture no longer reproduces the erasure"
        )

    def test_a_lost_record_write_never_reaches_the_admin_as_never_ran(self):
        """CERT-824 AT THE PUBLISHED SURFACE, with the real reader.

        Every other test in this class stubs ``read_pass_run`` and so proves
        what the endpoint does with a fact, not which fact it gets. This one
        runs the real ``record_pass_run`` into a store that refuses the write —
        the supported non-fatal path — then serves the endpoint through the real
        ``read_pass_run`` against a healthy store with no row. That is the
        sequence CERT-824 walked to print ``ran=True, record_stage='error',
        reported_has_run=False``, and the response must not say ``false``.
        """
        from unittest.mock import patch

        from app.utils import matcher_pass_runs as pr
        from app.utils.durable_state import EnvelopeRead

        async def _write_fails(_envelope):
            return {"status": "error", "error_class": "OperationalError"}

        async def _healthy_but_empty(_db, _identity, **_kw):
            return EnvelopeRead(status="missing", tier="durable")

        with patch.multiple(
            "app.services.durable_snapshots",
            publish_snapshot_standalone=_write_fails,
            read_snapshot=_healthy_but_empty,
        ):
            stage = asyncio.run(
                pr.record_pass_run(
                    phase=mr.PHASE_PASS3_BACKLOG, ran_at=NOW, rows_attempted=3000,
                )
            )
            assert stage["status"] == "error", (
                "this arm has to exercise a failed record write"
            )
            out = _call(
                db=self._coverage_db(
                    never_rows=[_Row(source="kalshi", n=7480)],
                    # Pass 1 has since relabelled every receipt, so the census
                    # cannot witness the run either. Nothing is left to save it
                    # except refusing to answer.
                    phase_rows=[_Row(phase=mr.PHASE_PASS1_TICKER, n=138676)],
                ),
                market_id=None, external_id=None, event_id=None,
                reject_reason=None, source=None, limit=50,
            )

        cov = out["coverage"]
        assert cov["backlog_pass_has_run"] is not False, (
            "the backlog pass ran, its record write failed, and the admin was "
            "told nothing is driving the coverage number down — CERT-824"
        )
        assert cov["backlog_pass_has_run"] is None
        assert cov["backlog_pass"]["status"] == pr.STATUS_NO_RECORD

    def test_the_endpoint_hands_the_label_census_over_as_the_witness(self):
        """The recovery that makes the null above rare rather than permanent.

        The census is already computed for ``receipt_phase_labels_now``; the
        witness is that same dict, read in the only direction it is sound in.
        If the endpoint stops passing it, a lost write goes back to being
        unrecoverable until the next cycle — so this checks the wiring, which
        no assertion about ``read_pass_run``'s own behaviour can.
        """
        _cov, db = self._summary(
            phase_rows=[_Row(phase=mr.PHASE_PASS3_BACKLOG, n=3000)],
        )
        assert db.witness_seen == [True], (
            "a live pass3_backlog label was not offered as a witness"
        )

        _cov, db = self._summary(
            phase_rows=[_Row(phase=mr.PHASE_PASS1_TICKER, n=138676)],
        )
        assert db.witness_seen == [False], (
            "the witness must be passed as False, not omitted — an absent "
            "keyword and 'no label' are the same value here only by luck"
        )

    def test_a_durable_store_that_does_not_answer_is_not_a_no(self):
        """``false`` is a claim about the matcher; a read failure is a claim
        about the database. Publishing the second as the first sends an admin
        hunting a dead beat that is alive — the same false negative CERT-819
        blocked, arriving by a different route."""
        from app.utils.matcher_pass_runs import PassRunFact

        cov, _ = self._summary(
            never_rows=[_Row(source="kalshi", n=7480)],
            pass_run=PassRunFact(
                phase=mr.PHASE_PASS3_BACKLOG, has_run=None,
                status="unavailable", error_class="TimeoutError",
            ),
        )
        assert cov["backlog_pass_has_run"] is None
        assert cov["backlog_pass"]["status"] == "unavailable"
        assert cov["backlog_pass"]["error_class"] == "TimeoutError"
        assert "null" in cov["note"].lower()

    def test_the_label_census_no_longer_claims_to_be_a_run_history(self):
        """The census is still published — it is useful — but under a name and
        a note that cannot be read as "these passes have run"."""
        cov, _ = self._summary(
            phase_rows=[_Row(phase=mr.PHASE_PASS1_TICKER, n=138676)],
        )
        assert "matcher_phases_seen" not in cov, (
            "the old name asserted an ever-fact the column cannot support"
        )
        note = cov["receipt_phase_labels_note"].lower()
        assert "overwrites" in note
        assert "not a run history" in note

    def test_the_note_does_not_let_the_number_be_read_as_missing_links(self):
        """The failure this whole block exists to stop: a reader takes 36,966 as
        36,966 games we failed to attach and opens a matching investigation into
        `10Y-2Y spread at the end of 2026`."""
        cov, _ = self._summary()
        note = cov["note"].lower()
        assert "receipt, not a link" in note
        assert "explained_no_game_here" in note
        # And the denominator is stated, not left to be inferred.
        assert "event_id is null" in cov["denominator"].lower()
        assert "base_where" in cov["denominator"]

    def test_every_coverage_path_the_reconciler_names_actually_resolves(self):
        """FOLLOW-UP ``L1B-010-RECEIPT-HINT-NESTED-PATH`` from CERT-819.

        The reconciliation job's ``receipt_coverage`` hint is the one line an
        operator follows out of a filed issue. It named
        ``coverage.explained_no_game_here``, which has never existed — the field
        is per-source, under ``coverage.by_source.<source>``. A hint that sends
        a reader to a key that is not there is worse than no hint: they conclude
        the number is missing rather than that they are in the wrong place.

        So the hint's paths are checked against a REAL response rather than
        proof-read. Every ``coverage.x.y`` this job prints must dereference.
        """
        import re

        from app.tasks.matching_reconciliation import receipts_hint_for

        cov, _ = self._summary(
            never_rows=[_Row(source="kalshi", n=7480)],
            explained_rows=[_Row(source="kalshi", n=178, no_game_here=13)],
        )
        hint = receipts_hint_for({"key": "receipt_coverage", "rows": []})
        paths = set(re.findall(r"`coverage\.([A-Za-z_][A-Za-z0-9_.]*)`", hint))
        assert paths, "the hint stopped naming any coverage path"

        for path in paths:
            node = cov
            for part in path.split("."):
                assert isinstance(node, dict) and part in node, (
                    f"the reconciler points at coverage.{path}, which the "
                    f"endpoint does not publish"
                )
                node = node[part]


class TestTheRejectHistogramIsOrderedByWhatCanStillBeFixed:
    """Measured on production 2026-09-03: 7,854 of 8,032 rejects were on
    ALREADY-RESOLVED markets, so the flat histogram's top bucket
    (``no_candidate``, 6,843) is overwhelmingly settled ITF tennis whose events
    are never ingested. A reader who sorts on ``count`` picks the one bucket no
    matching fix can move. Gotcha #53: a rate needs a denominator where 100% is
    structurally achievable.
    """

    @staticmethod
    def _summary(reason_rows):
        totals = _Row(receipts=10, linked=2, oldest=NOW, newest=NOW)
        return _call(
            db=_FakeDB(
                [_FakeResult(reason_rows), _FakeResult([totals]), _FakeResult([])],
                scalar=0,
            ),
            market_id=None, external_id=None, event_id=None,
            reject_reason=None, source=None, limit=50,
        )

    def test_the_big_dead_bucket_does_not_outrank_the_small_live_one(self):
        # Production's actual shape, rounded to the two reasons that matter:
        # no_candidate is 38x larger and 98% unfixable.
        out = self._summary(
            [
                _Row(reject_reason=mr.REJECT_NO_CANDIDATE, source="kalshi",
                     n=6843, still_linkable=109),
                _Row(reject_reason=mr.REJECT_NAME_MISMATCH, source="kalshi",
                     n=93, still_linkable=40),
            ]
        )
        # Sorted by still_linkable, both rows are present and the caller can
        # see which is worth a fix — but the ordering no longer sends them at
        # 6,734 settled rows first.
        assert [r["reject_reason"] for r in out["by_reason"]] == [
            mr.REJECT_NO_CANDIDATE,
            mr.REJECT_NAME_MISMATCH,
        ]
        assert out["by_reason"][0]["still_linkable"] == 109
        assert out["by_reason"][0]["settled"] == 6843 - 109

    def test_nothing_is_excluded_the_settled_column_is_published(self):
        # The standing doctrine: read-side scoping protects a metric, it never
        # closes an issue. A census that DROPPED the settled rows would be
        # unable to show that the matcher is still re-attempting them.
        out = self._summary(
            [
                _Row(reject_reason=mr.REJECT_NO_CANDIDATE, source="kalshi",
                     n=6843, still_linkable=109),
                _Row(reject_reason=mr.REJECT_OUTSIDE_TIME_WINDOW, source="kalshi",
                     n=452, still_linkable=8),
            ]
        )
        assert out["reject_totals"]["still_linkable"] == 117
        assert out["reject_totals"]["settled"] == (6843 - 109) + (452 - 8)
        assert sum(r["count"] for r in out["by_reason"]) == 6843 + 452

    def test_a_reason_with_no_live_market_left_still_appears(self):
        # It sorts last, but a reason that has gone entirely settled is a fact
        # about a class that USED to fail — dropping it would erase the only
        # evidence the class ever existed.
        out = self._summary(
            [
                _Row(reject_reason=mr.REJECT_NO_CANDIDATE, source="kalshi",
                     n=6843, still_linkable=0),
            ]
        )
        assert out["by_reason"][0]["still_linkable"] == 0
        assert out["by_reason"][0]["settled"] == 6843
        assert out["reject_totals"]["still_linkable"] == 0

    def test_the_split_is_computed_from_the_market_not_from_the_receipt(self):
        """The join is the whole mechanism, and it is what a refactor drops.

        A receipt carries no status of its own — ``market_match_receipts`` has
        no column that says whether the market has settled — so the split can
        only come from joining ``futures_markets``. A version of this query
        without the join compiles, returns rows, and silently answers the flat
        question again.
        """
        import inspect

        from app.routes import admin_matching

        src = inspect.getsource(admin_matching.match_receipts)
        head, marker, tail = src.partition("still_linkable = func.count().filter(")
        assert marker, "the reason histogram's split moved; re-point this guard"
        query = marker + tail.split(").all()")[0]
        assert 'FuturesMarket.status == "open"' in query, query
        assert "FuturesMarket.id == MarketMatchReceipt.market_id" in query, query
        assert "still_linkable.desc()" in query, query

    def test_the_statement_itself_executes_and_puts_the_live_reason_first(self):
        """The source scan above pins the SQL; this one RUNS it.

        A shape test driven by a fake DB proves the response formatting and
        nothing about the query, and the query is where the whole fix lives.
        The same statement the endpoint builds is executed here against a real
        engine over four markets — two settled, two open — arranged so that the
        flat count and the live count disagree about which reason is worst.
        """
        from sqlalchemy import create_engine, func, select, text

        from app.models.models import FuturesMarket, MarketMatchReceipt

        still = func.count().filter(FuturesMarket.status == "open")
        stmt = (
            select(
                MarketMatchReceipt.reject_reason,
                MarketMatchReceipt.source,
                func.count().label("n"),
                still.label("still_linkable"),
            )
            .join(FuturesMarket, FuturesMarket.id == MarketMatchReceipt.market_id)
            .where(MarketMatchReceipt.outcome == "rejected")
            .group_by(MarketMatchReceipt.reject_reason, MarketMatchReceipt.source)
            .order_by(still.desc(), func.count().desc())
        )

        engine = create_engine("sqlite://")
        with engine.begin() as conn:
            conn.execute(
                text(
                    "CREATE TABLE futures_markets "
                    "(id INTEGER PRIMARY KEY, status TEXT)"
                )
            )
            conn.execute(
                text(
                    "CREATE TABLE market_match_receipts (id INTEGER PRIMARY KEY, "
                    "market_id INTEGER, source TEXT, outcome TEXT, "
                    "reject_reason TEXT)"
                )
            )
            # no_candidate: 3 rejects, ALL settled — production's shape.
            # name_mismatch: 1 reject, still open.
            conn.execute(
                text(
                    "INSERT INTO futures_markets VALUES "
                    "(1,'resolved'),(2,'resolved'),(3,'resolved'),(4,'open')"
                )
            )
            conn.execute(
                text(
                    "INSERT INTO market_match_receipts VALUES "
                    "(1,1,'kalshi','rejected','no_candidate'),"
                    "(2,2,'kalshi','rejected','no_candidate'),"
                    "(3,3,'kalshi','rejected','no_candidate'),"
                    "(4,4,'kalshi','rejected','name_mismatch')"
                )
            )
            rows = list(conn.execute(stmt))

        # Flat count says no_candidate (3) is the biggest problem. It is not:
        # every one of its markets has settled and no fix can move it.
        assert [(r[0], r[2], r[3]) for r in rows] == [
            ("name_mismatch", 1, 1),
            ("no_candidate", 3, 0),
        ]


def test_the_summary_answers_the_question_that_had_no_answer():
    """LINKLOSS-02: "did tonight's merge drop 261 links?" is one GROUP BY.

    The census must separate the merge from the matcher — one is expected
    bookkeeping and the other is a bug — and must publish the settlement
    subtraction beside it, because a settlement wave and a link loss look
    identical in a count of open linked markets.
    """
    change_rows = [
        _Row(outcome=mr.OUTCOME_SUPERSEDED_BY_TWIN_MERGE,
             actor=mr.ACTOR_TWIN_CLEANUP, phase=mr.PHASE_TWIN_MERGE, n=261),
        _Row(outcome=mr.OUTCOME_UNLINKED, actor=mr.ACTOR_MATCHER_PASS,
             phase=mr.PHASE_PHASE2_LINKED, n=4),
    ]
    totals = _Row(receipts=1, linked=1, oldest=NOW, newest=NOW)
    out = _call(
        db=_FakeDB(
            [_FakeResult([]), _FakeResult([totals]), _FakeResult(change_rows)],
            scalar=17,
        ),
        market_id=None, external_id=None, event_id=None,
        reject_reason=None, source=None, limit=50, since_hours=6,
    )
    census = out["link_changes"]
    assert census["since_hours"] == 6
    assert census["ended_total"] == 265
    by_actor = {(r["outcome"], r["actor"]): r["count"] for r in census["by_actor"]}
    assert by_actor[(mr.OUTCOME_SUPERSEDED_BY_TWIN_MERGE, mr.ACTOR_TWIN_CLEANUP)] == 261
    assert by_actor[(mr.OUTCOME_UNLINKED, mr.ACTOR_MATCHER_PASS)] == 4
    # The subtraction. Without it the 261 above is uninterpretable.
    assert census["linked_markets_settled"] == 17
    assert sorted(mr.ACTORS) == census["valid_actors"]


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


# =============================================================================
# Part 8 — CERT-771: a receipt may never claim a link the database does not hold
#
# The banked reproduction, verbatim: market 1 links, market 2 raises, the shared
# matcher session rolls back once, and market 1 ends at event_id=None while its
# receipt still says linked_event_id=42. A receipt that reports the OPPOSITE of
# the state it exists to explain is worse than no receipt, and it also hides the
# row from every coverage check that reads "has a receipt" as "accounted for".
#
# Two guarantees, both tested: the link is committed BEFORE it is claimed, and
# the claim is re-read against the database before publication.
# =============================================================================


def test_the_link_is_committed_before_the_receipt_claims_it():
    """The window is closed at the source. Both link paths commit first."""
    src = inspect.getsource(pmm._try_link_market)
    matched = src.index('how="matched_existing_event"')
    auto = src.index('how="auto_created_event"')
    # A commit must appear between the start of each linking branch and its claim.
    assert "await session.commit()" in src[:matched], (
        "the matched-event branch claims a link it has not committed"
    )
    assert "await session.commit()" in src[matched:auto], (
        "the auto-created branch claims a link it has not committed"
    )


class _DurabilitySession:
    """Answers the durability re-read from a planted event_id map."""

    def __init__(self, durable: dict):
        self._durable = durable

    async def execute(self, stmt):
        rows = list(self._durable.items())

        class _R:
            def all(self_inner):
                return rows

        return _R()


def test_a_receipt_whose_link_did_not_land_is_downgraded_not_published():
    """The invariant, checked directly."""
    linked = _receipt(market_id=1)
    linked.link(42, how="matched_existing_event")
    other = _receipt(market_id=2)
    other.link(99, how="matched_existing_event")

    n = asyncio.run(mr.verify_links_are_durable(
        _DurabilitySession({1: None, 2: 99}), [linked, other]
    ))

    assert n == 1
    assert linked.outcome == mr.OUTCOME_REJECTED
    assert linked.reject_reason == mr.REJECT_LINK_NOT_DURABLE
    assert linked.linked_event_id is None
    assert linked.detail["claimed_event_id"] == 42
    assert linked.detail["observed_event_id"] is None
    # The market whose link DID land is untouched.
    assert other.outcome == mr.OUTCOME_LINKED and other.linked_event_id == 99


def test_a_link_that_landed_on_a_different_event_is_also_downgraded():
    """"Committed" is not enough — it has to be committed to the event claimed."""
    r = _receipt(market_id=1)
    r.link(15299723)
    n = asyncio.run(mr.verify_links_are_durable(
        _DurabilitySession({1: 15299648}), [r]  # the ghost twin
    ))
    assert n == 1
    assert r.reject_reason == mr.REJECT_LINK_NOT_DURABLE
    assert r.detail["observed_event_id"] == 15299648


def test_rejected_receipts_are_not_re_read_at_all():
    """The guard costs one query for the linked subset and nothing otherwise."""
    r = _receipt(market_id=1)
    r.reject(mr.REJECT_NO_CANDIDATE)

    class _Explodes:
        async def execute(self, stmt):
            raise AssertionError("queried for a receipt that claims no link")

    assert asyncio.run(mr.verify_links_are_durable(_Explodes(), [r])) == 0


def test_the_flush_verifies_before_it_writes_and_counts_the_downgrades():
    """Composed: the whole publication path, not just the helper."""
    order = []

    class _Factory:
        def __call__(self):
            return self

        async def __aenter__(self):
            return self

        async def __aexit__(self, *exc):
            return False

        async def execute(self, stmt):
            sql = str(stmt).lower()
            order.append("read" if sql.startswith("select") else "write")

            class _R:
                def all(self_inner):
                    return [(1, None)]

            return _R()

        async def commit(self):
            order.append("commit")

    r = _receipt(market_id=1)
    r.link(42)
    stats = {"funnel": {}, "errors": []}
    asyncio.run(pmm._flush_pass_receipts(
        _CapturingSession(), [r], stats, mr.PHASE_PASS2_GENERAL,
        session_factory=_Factory(),
    ))

    assert order[0] == "read", "wrote the receipt before checking the claim"
    assert "write" in order and order[-1] == "commit"
    assert stats["funnel"]["receipt_links_not_durable"] == 1
    assert r.reject_reason == mr.REJECT_LINK_NOT_DURABLE


def test_link_not_durable_is_a_registered_countable_reason():
    """It has to be GROUP BY-able, or the reconciliation job cannot alert on it."""
    assert mr.REJECT_LINK_NOT_DURABLE in mr.REJECT_REASONS


# =============================================================================
# Part 9 — CERT-774: one market's failure ends that ATTEMPT, never the PASS.
#
# The banked reproduction: a pass holds a preloaded list of ORM rows and walks
# it across per-market rollback boundaries. `rollback()` expires every
# persistent object in the session — `expire_on_commit=False` does not prevent
# it (gotcha #6) — so the NEXT row's `market.id`, read outside the per-market
# catcher, triggers an implicit refresh with no greenlet to run it and raises
# `MissingGreenlet`. The pass dies before `_flush_pass_receipts`, its collected
# receipts die in memory, and the rest of the queue is left unattempted and
# unexplained: precisely the state #2705 exists to abolish, reintroduced by the
# error handling that was supposed to contain a single bad market.
#
# The rig below is that behaviour and nothing else: a row that raises the real
# `MissingGreenlet` on any attribute read once the session has rolled back.
# `test_the_rig_reproduces_the_expiry_the_defect_needs` proves the rig can still
# see the defect, so the passes' green is a result rather than an absence.
# =============================================================================


class _ExpiringRow:
    """A market row with SQLAlchemy's post-rollback behaviour, and no other."""

    _FIELDS = dict(
        source="polymarket", category="sports", group_type=None, group_id=None,
        llm_sport_category="tennis", event_id=None, sport_id=None,
    )

    def __init__(self, id, name, **extra):
        values = dict(self._FIELDS)
        values.update(
            id=id, name=name, external_id=f"ext-{id}", commence_time=NOW,
        )
        values.update(extra)
        object.__setattr__(self, "_values", values)
        object.__setattr__(self, "_expired", False)

    def expire(self):
        object.__setattr__(self, "_expired", True)

    def refresh(self):
        object.__setattr__(self, "_expired", False)

    def __getattr__(self, name):
        values = object.__getattribute__(self, "_values")
        if name not in values:
            raise AttributeError(name)
        if object.__getattribute__(self, "_expired"):
            raise MissingGreenlet(
                "greenlet_spawn has not been called; can't call await_only() "
                "here. Was IO attempted in an unexpected place?"
            )
        return values[name]

    def __setattr__(self, name, value):
        object.__getattribute__(self, "_values")[name] = value


class _RollbackExpiresRowsSession:
    """The matcher's session, reduced to the one behaviour that matters."""

    def __init__(self, rows):
        self._rows = {r.id: r for r in rows}
        self.loaded = []
        self.rollbacks = 0
        self.expunges = 0

    async def execute(self, stmt, params=None):
        sql = str(stmt)
        if "JOIN market_match_receipts" in sql:
            return _IdResult([])          # nothing stale; the never-queue is it
        return _IdResult(list(self._rows))

    async def scalar(self, stmt):
        return len(self._rows)

    async def get(self, model, pk):
        self.loaded.append(pk)
        row = self._rows.get(pk)
        if row is not None:
            row.refresh()                 # a fresh read is a fresh row
        return row

    async def rollback(self):
        self.rollbacks += 1
        for row in self._rows.values():
            row.expire()

    def expunge_all(self):
        self.expunges += 1

    async def commit(self):
        pass                              # expire_on_commit=False


class _IdResult:
    def __init__(self, values):
        self._values = list(values)

    def scalars(self):
        return self

    def all(self):
        return list(self._values)


def _fresh_stats():
    return {
        "funnel": {
            "not_game_level": 0, "no_matchup_extracted": 0,
            "game_level_detected": 0, "no_event_found": 0, "linked": 0,
            "sample_not_game_level": [], "sample_game_level_no_event": [],
        },
        "errors": [], "markets_scanned": 0, "newly_linked": 0,
    }


def _run_pass_with_one_failing_market(monkeypatch, pass_fn, *, failing_at):
    """Two markets, the first one fails; return what the pass did.

    ``failing_at`` is "search" or "link" — the candidate query and the write
    are different halves of an attempt, and the old code guarded only the
    second one.
    """
    rows = [
        _ExpiringRow(1, "Ann Li vs Donna Vekic"),
        _ExpiringRow(2, "Carlos Alcaraz vs. Jannik Sinner"),
    ]
    session = _RollbackExpiresRowsSession(rows)
    stats = _fresh_stats()
    steps = []
    flushed = {}

    async def _fake_search(session_, matchup, market, now_, **kw):
        steps.append(("search", market.id))
        if failing_at == "search" and market.id == 1:
            raise RuntimeError("canceling statement due to statement timeout")
        return None

    async def _fake_link(session_, market, matchup, matched, stats_,
                         game_date, now_, queue, *, receipt=None):
        steps.append(("link", market.id))
        if failing_at == "link" and market.id == 1:
            raise RuntimeError("deadlock detected")
        receipt.link(900 + market.id, how="test")

    async def _capture_flush(session_, receipts, stats_, phase,
                             session_factory=None):
        flushed.setdefault("phases", []).append(phase)
        flushed.setdefault("receipts", []).extend(receipts)

    monkeypatch.setattr(pmm, "_find_matching_event", _fake_search)
    monkeypatch.setattr(pmm, "_find_event_by_sport_and_time", _fake_search)
    monkeypatch.setattr(pmm, "_try_link_market", _fake_link)
    monkeypatch.setattr(pmm, "_flush_pass_receipts", _capture_flush)

    if pass_fn is pmm._phase1_pass1_ticker_scan:
        asyncio.run(pass_fn(session, stats, NOW, [], lambda: 700.0))
    else:
        asyncio.run(pass_fn(session, stats, NOW, set(), [], lambda: 700.0))
    return session, stats, steps, flushed


@pytest.mark.parametrize("failing_at", ["link", "search"])
def test_a_failed_market_does_not_stop_the_next_one(monkeypatch, failing_at):
    """THE SHIP. Market 1 raises, market 2 is still attempted, both receipts
    reach the flush. Anything less and the tail of the queue goes back to being
    indistinguishable from never having been tried."""
    session, stats, steps, flushed = _run_pass_with_one_failing_market(
        monkeypatch, pmm._phase1_pass3_backlog_scan, failing_at=failing_at,
    )

    assert ("link", 2) in steps, (
        "market 2 was never attempted — market 1's failure ended the pass, "
        "which is CERT-774 exactly"
    )
    assert session.rollbacks == 1
    assert session.loaded == [1, 2], (
        "each row must be read on the line before its own attempt; a preloaded "
        "instance is expired by the rollback that precedes it"
    )
    receipts = {r.market_id: r for r in flushed["receipts"]}
    assert set(receipts) == {1, 2}, "receipts died in memory with the pass"
    assert receipts[2].outcome == mr.OUTCOME_LINKED
    assert receipts[2].linked_event_id == 902
    assert receipts[1].reject_reason == (
        mr.REJECT_DEADLOCK if failing_at == "link" else mr.REJECT_ATTEMPT_ERROR
    )
    assert stats["funnel"]["backlog_scanned"] == 2


@pytest.mark.parametrize("failing_at", ["link", "search"])
def test_pass1_survives_a_failed_market_too(monkeypatch, failing_at):
    """Pass 1 has its own loop, so it needs its own proof."""
    session, stats, steps, flushed = _run_pass_with_one_failing_market(
        monkeypatch, pmm._phase1_pass1_ticker_scan, failing_at=failing_at,
    )
    assert ("link", 2) in steps
    assert session.loaded == [1, 2]
    assert {r.market_id for r in flushed["receipts"]} == {1, 2}
    assert flushed["phases"] == [mr.PHASE_PASS1_TICKER]


def test_the_rollback_empties_the_session_so_the_next_read_is_a_real_read():
    """Expiring is not enough — the expired instances have to go, or the next
    ``get`` is an implicit refresh of a row that may no longer exist."""
    session = _RollbackExpiresRowsSession([_ExpiringRow(1, "A vs B")])
    receipt = _receipt(market_id=1)
    asyncio.run(pmm._abandon_attempt(
        session, market_id=1, phase=mr.PHASE_PASS2_GENERAL,
        stats=_fresh_stats(), receipt=receipt, exc=RuntimeError("boom"),
    ))
    assert session.rollbacks == 1 and session.expunges == 1
    assert receipt.reject_reason == mr.REJECT_ATTEMPT_ERROR


def test_the_rig_reproduces_the_expiry_the_defect_needs():
    """The control. If this stops raising, the two tests above prove nothing."""
    row = _ExpiringRow(1, "Ann Li vs Donna Vekic")
    session = _RollbackExpiresRowsSession([row])
    assert row.id == 1
    asyncio.run(session.rollback())
    with pytest.raises(MissingGreenlet):
        row.id


def test_a_market_that_vanished_between_scan_and_attempt_is_counted(monkeypatch):
    """The scan holds ids, so a row can be deleted or re-scoped underneath it.
    That is a skip with a counter, never a crash."""
    session = _RollbackExpiresRowsSession([_ExpiringRow(1, "Ann Li vs Vekic")])
    session._rows[1] = None               # gone by the time the attempt reads it
    stats = _fresh_stats()

    async def _no_flush(*a, **kw):
        pass

    monkeypatch.setattr(pmm, "_flush_pass_receipts", _no_flush)
    asyncio.run(pmm._phase1_pass3_backlog_scan(
        session, stats, NOW, set(), [], lambda: 700.0,
    ))
    assert stats["funnel"]["row_gone_before_attempt"] == 1
    assert stats["funnel"]["backlog_scanned"] == 0


def test_receipts_are_published_even_when_the_pass_itself_raises(monkeypatch):
    """The flush is in a ``finally``. A failure the pass does not anticipate
    must still leave every attempt it already made accounted for."""
    session = _RollbackExpiresRowsSession([_ExpiringRow(1, "Ann Li vs Vekic")])
    flushed = []

    async def _explode(session_, market, stats_, now_, queue, tr, receipts, phase):
        receipts.append(_receipt(market_id=market.id, phase=phase))
        raise RuntimeError("something nobody wrote a handler for")

    async def _capture(session_, receipts, stats_, phase, session_factory=None):
        flushed.extend(receipts)

    monkeypatch.setattr(pmm, "_attempt_market", _explode)
    monkeypatch.setattr(pmm, "_flush_pass_receipts", _capture)

    with pytest.raises(RuntimeError):
        asyncio.run(pmm._phase1_pass3_backlog_scan(
            session, _fresh_stats(), NOW, set(), [], lambda: 700.0,
        ))
    assert [r.market_id for r in flushed] == [1]


# ── The Polymarket history request follows the commit, never precedes it ──────


class _CommitFailsSession(_CapturingSession):
    def __init__(self, fail=True):
        super().__init__()
        self.fail = fail

    async def commit(self):
        if self.fail:
            raise RuntimeError("could not serialize access")


async def _link_one(session, queue):
    market = _ExpiringRow(1, "Ann Li vs Donna Vekic")
    receipt = _receipt(market_id=1)
    await pmm._try_link_market(
        session, market, None, {"event_id": 42, "home_team": "Li",
                                "away_team": "Vekic"},
        _fresh_stats(), None, NOW, queue, receipt=receipt,
    )


def _patch_link_deps(monkeypatch):
    async def _no_refusal(*a, **kw):
        return None

    async def _no_identities(*a, **kw):
        return None

    monkeypatch.setattr(pmm, "_check_duplicate_kalshi_linkage_reason", _no_refusal)
    monkeypatch.setattr(pmm, "_register_market_team_identities", _no_identities)


def test_a_failed_commit_leaves_no_history_request_behind(monkeypatch):
    """The backfill queue asks for the history of a (market, event) LINK. A
    request enqueued before the commit outlives a commit that never lands."""
    _patch_link_deps(monkeypatch)
    queue = []
    with pytest.raises(RuntimeError):
        asyncio.run(_link_one(_CommitFailsSession(), queue))
    assert queue == [], "queued history for a link the database never took"


def test_the_history_request_is_still_made_when_the_commit_lands(monkeypatch):
    """The control: moving the enqueue must not delete it."""
    _patch_link_deps(monkeypatch)
    queue = []
    asyncio.run(_link_one(_CommitFailsSession(fail=False), queue))
    assert queue == [(1, 42)]
