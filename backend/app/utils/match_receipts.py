"""Matching receipts — the record of what the matcher actually did (#2705).

WHY THIS EXISTS. Before receipts, ``futures_markets.event_id IS NULL`` was the
only thing the system could say about an unattached market, and that one bit
conflates three completely different states:

* **no candidate exists** — upstream has the market, we have no event for it;
* **a candidate exists and was refused** — a real matcher decision, with a
  reason;
* **the market was never looked at** — the scan never reached it.

The third is the one that cost days. Measured 2026-09-02 (ARTIFACT-M-20260902-N):
all three zero-link US Open Polymarket groups were ingested 8/28 and stayed at
zero links while every 8/31–9/01 group linked, with nothing about the names, the
candidate event, or the market shape separating them. The separator was the
scan: Pass 2 orders by ``updated_at DESC`` and takes the top ``limit`` rows, so
an older ingest wave sitting behind 21,412 unlinked rows is never *attempted*.
``link-rate`` cannot see that, because a never-tried market and a
correctly-refused market are the same NULL. ARTIFACT-M-20260902-O says it
outright: *"the 'never attempted' hole is NOT measurable from prod rows today"*.

WHAT A ROW MEANS. Exactly one thing: *the last time the matcher looked at this
market, here is what it saw and what it decided.* It is a record, not a
constraint and not a claim of correctness. Deliberately ONE row per market,
upserted — not an append-only attempt log. 21k open unlinked markets × 96 cycles
a day is 2M rows a day of mostly-identical text; the question the bus actually
asks ("why is PM 59669077 unattached") is answered by the latest attempt, and
``attempt_count`` + ``first_attempted_at`` preserve the history that matters.

WHY THE REASON IS A CLOSED ENUM. ``INVARIANTS-2026-09-02.md`` query (c) counts
996 markets that are parseable, have an exact-name candidate in an agreeing
state, are unlinked, and have *no written reason*. A free-text reason column
would turn that 996 into 996 different strings and the invariant would stay
uncountable. Every reject reason here is a value the reconciliation job (#2706)
can GROUP BY.

NOT A SIMULATION. ``/api/admin/prediction-markets/match-trace`` re-runs the
matching logic *now*, against today's events, with a partial copy of the window
arithmetic. It answers "what would happen if we tried". It cannot answer "what
happened", it drifts from the matcher every time the matcher changes, and it
says nothing at all about a market the scan never reached. Receipts are written
by the matcher itself, on the path that made the decision.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Optional

from sqlalchemy import func

# ── Outcomes ────────────────────────────────────────────────────────────────
OUTCOME_LINKED = "linked"
OUTCOME_REJECTED = "rejected"

# ── The closed reject enum ──────────────────────────────────────────────────
# Add a value here and to REJECT_REASONS in the same edit, or the guard test
# fails. The reconciliation job (#2706) groups by these, so a reason that only
# exists as a string in a log line does not count as "written".

#: The row is a container/parent, not a game market. Polymarket
#: ``polymarket_event``/``negrisk`` and Kalshi ``kalshi_event`` rows describe a
#: group of sub-markets; the sub-markets are what attach to an event.
REJECT_PARENT_ROW = "parent_row"

#: ``is_game_level_market`` said no — a futures/award/prop market that is not
#: about one game between two named sides.
REJECT_NOT_GAME_LEVEL = "not_game_level"

#: No matchup could be parsed from the name or the ticker, so there is nothing
#: to search events with.
REJECT_NO_MATCHUP = "no_matchup_extracted"

#: Searched, and no event anywhere carries these team names — including with
#: the time window and the status filter removed. This is the honest
#: "upstream has it, we do not" bucket.
REJECT_NO_CANDIDATE = "no_candidate"

#: Events with these names exist, but every one of them sits outside the
#: matcher's time window. The classic Kalshi resolution-date-vs-game-date shape
#: (gotcha #14) and the stale-tournament-segment shape (Q504-b) both land here.
REJECT_OUTSIDE_TIME_WINDOW = "outside_time_window"

#: Events with these names exist inside the window, but their ``status``
#: excluded them (completed/closed and older than the past cutoff).
REJECT_STATE_DISAGREES = "state_disagrees"

#: Candidates came back, but none passed the team-name gate — the ILIKE found
#: them on one token and the fuzzy match refused the pair.
REJECT_NAME_MISMATCH = "name_mismatch"

#: Candidates came back and were refused because their sport disagrees with the
#: market's ticker-derived or LLM-assigned sport.
REJECT_WRONG_SPORT = "wrong_sport"

#: A best candidate was found but scored below the confidence floor the matcher
#: requires when it has no sport prefix to validate against.
REJECT_NAME_SCORE_BELOW = "name_score_below"

#: The duplicate-linkage guard refused: a sibling ticker for the same game is
#: already on that event.
REJECT_ALREADY_LINKED_ELSEWHERE = "already_linked_elsewhere"

#: The duplicate-linkage guard refused on the widened ticker-date-vs-event-date
#: arm (``_REFUSAL_EVENT_DATE``).
REJECT_EVENT_DATE_CONFLICT = "event_date_conflict"

#: No event matched and auto-creation was attempted and declined (self-refuting
#: commence time, missing second side, creation freeze).
REJECT_AUTO_CREATE_DECLINED = "auto_create_declined"

#: The attempt raised. Recorded rather than swallowed, because "it errored" and
#: "it was refused" are different answers to the bus's question.
REJECT_ATTEMPT_ERROR = "attempt_error"

#: The attempt hit a Postgres deadlock against the live-price poller. Expected
#: at low rates (gotcha #13); a spike is its own signal.
REJECT_DEADLOCK = "deadlock"

REJECT_REASONS: frozenset[str] = frozenset({
    REJECT_PARENT_ROW,
    REJECT_NOT_GAME_LEVEL,
    REJECT_NO_MATCHUP,
    REJECT_NO_CANDIDATE,
    REJECT_OUTSIDE_TIME_WINDOW,
    REJECT_STATE_DISAGREES,
    REJECT_NAME_MISMATCH,
    REJECT_WRONG_SPORT,
    REJECT_NAME_SCORE_BELOW,
    REJECT_ALREADY_LINKED_ELSEWHERE,
    REJECT_EVENT_DATE_CONFLICT,
    REJECT_AUTO_CREATE_DECLINED,
    REJECT_ATTEMPT_ERROR,
    REJECT_DEADLOCK,
})

# ── Phases ──────────────────────────────────────────────────────────────────
#: Kalshi ticker-pattern scan (Phase 1 Pass 1) — unbounded except by time.
PHASE_PASS1_TICKER = "pass1_ticker"
#: Name-shaped scan (Phase 1 Pass 2) — ``updated_at DESC``, top ``limit``.
PHASE_PASS2_GENERAL = "pass2_general"
#: Receipt-staleness backlog sweep (Phase 1 Pass 3) — the pass that makes
#: "never attempted" impossible. Ordered by oldest receipt first, so no market
#: can sit behind a newer wave forever.
PHASE_PASS3_BACKLOG = "pass3_backlog"

PHASES: frozenset[str] = frozenset({
    PHASE_PASS1_TICKER, PHASE_PASS2_GENERAL, PHASE_PASS3_BACKLOG,
})

#: Cap on the candidate trace stored per receipt. The scoring queries take 20
#: rows; storing all 20 for 21k markets is JSONB nobody reads. The trace is
#: sorted best-score-first before truncation, so the rows that explain the
#: decision are the rows that survive it.
MAX_TRACE_CANDIDATES = 8


@dataclass
class CandidateTrace:
    """One event the matcher considered, and what it did with it."""

    event_id: int
    home_team: Optional[str] = None
    away_team: Optional[str] = None
    commence_time: Optional[datetime] = None
    status: Optional[str] = None
    sport_key: Optional[str] = None
    #: The computed score, or ``None`` when the candidate was rejected before
    #: scoring (name gate, sport gate).
    score: Optional[float] = None
    #: Why this individual candidate lost: ``name_mismatch``, ``wrong_sport``,
    #: ``outside_time_window``, ``state_disagrees``, ``lower_score``, or
    #: ``chosen``.
    verdict: str = "considered"

    def to_dict(self) -> dict[str, Any]:
        return {
            "event_id": self.event_id,
            "home_team": self.home_team,
            "away_team": self.away_team,
            "commence_time": (
                self.commence_time.isoformat() if self.commence_time else None
            ),
            "status": self.status,
            "sport_key": self.sport_key,
            "score": round(self.score, 3) if self.score is not None else None,
            "verdict": self.verdict,
        }


@dataclass
class MatchReceipt:
    """What one matching attempt saw and decided, for one market."""

    market_id: int
    source: str
    external_id: Optional[str]
    market_name: Optional[str]
    phase: str
    attempted_at: datetime
    outcome: str = OUTCOME_REJECTED
    reject_reason: Optional[str] = None
    linked_event_id: Optional[int] = None
    candidates: list[CandidateTrace] = field(default_factory=list)
    detail: dict[str, Any] = field(default_factory=dict)

    def reject(self, reason: str, **detail: Any) -> "MatchReceipt":
        """Mark this attempt rejected. Unknown reasons raise, by design.

        A typo'd reason string is a silently uncountable row, which is the
        exact failure this table was built to end — so it fails loudly here,
        in the caller's own stack, rather than becoming the 997th unexplained
        market.
        """
        if reason not in REJECT_REASONS:
            raise ValueError(
                f"unknown match reject reason {reason!r} — add it to "
                f"app/utils/match_receipts.REJECT_REASONS"
            )
        self.outcome = OUTCOME_REJECTED
        self.reject_reason = reason
        self.linked_event_id = None
        if detail:
            self.detail.update(detail)
        return self

    def link(self, event_id: int, **detail: Any) -> "MatchReceipt":
        """Mark this attempt linked to ``event_id``."""
        self.outcome = OUTCOME_LINKED
        self.reject_reason = None
        self.linked_event_id = event_id
        if detail:
            self.detail.update(detail)
        return self

    def trace(self, candidate: CandidateTrace) -> None:
        self.candidates.append(candidate)

    def candidate_payload(self) -> list[dict[str, Any]]:
        """The stored trace: best-scoring first, capped, chosen never dropped."""
        chosen = [c for c in self.candidates if c.verdict == "chosen"]
        rest = [c for c in self.candidates if c.verdict != "chosen"]
        rest.sort(key=lambda c: (c.score is None, -(c.score or 0.0)))
        ordered = chosen + rest
        return [c.to_dict() for c in ordered[:MAX_TRACE_CANDIDATES]]

    def to_row(self) -> dict[str, Any]:
        """The upsert payload — one dict per market, keyed on ``market_id``."""
        return {
            "market_id": self.market_id,
            "source": (self.source or "")[:50],
            "external_id": (self.external_id or "")[:200] or None,
            "market_name": (self.market_name or "")[:300] or None,
            "phase": self.phase,
            "outcome": self.outcome,
            "reject_reason": self.reject_reason,
            "linked_event_id": self.linked_event_id,
            "candidates": self.candidate_payload(),
            "detail": _jsonable(self.detail),
            "first_attempted_at": self.attempted_at,
            "last_attempted_at": self.attempted_at,
            "attempt_count": 1,
        }


def _jsonable(value: Any) -> Any:
    """Coerce datetimes (and containers of them) so JSONB can hold the detail."""
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, dict):
        return {k: _jsonable(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_jsonable(v) for v in value]
    return value


async def flush_receipts(session, receipts: list[MatchReceipt], chunk: int = 500) -> int:
    """Upsert receipts, newest attempt wins, ``attempt_count`` accumulates.

    One row per market: ``ON CONFLICT (market_id) DO UPDATE``. ``first_attempted_at``
    is kept (``LEAST`` of old and new, so a clock skew cannot move it forward)
    and ``attempt_count`` increments, which is what makes "attempted N times,
    still rejected for reason R" a question the bus can ask.

    Batched because the backlog pass writes thousands per cycle and a per-market
    round trip would spend the matcher's whole time budget on bookkeeping.
    Deduplicated within the batch first: Postgres refuses an ``ON CONFLICT``
    statement that hits the same key twice in one command ("cannot affect row a
    second time"), and one market CAN be seen by two passes in one run.
    """
    if not receipts:
        return 0

    from sqlalchemy.dialects.postgresql import insert as pg_insert

    from app.models.models import MarketMatchReceipt

    # Last write wins within a batch — the later pass saw the later state.
    deduped: dict[int, MatchReceipt] = {}
    for receipt in receipts:
        deduped[receipt.market_id] = receipt
    rows = [r.to_row() for r in deduped.values()]

    written = 0
    for start in range(0, len(rows), chunk):
        batch = rows[start:start + chunk]
        stmt = pg_insert(MarketMatchReceipt).values(batch)
        stmt = stmt.on_conflict_do_update(
            index_elements=[MarketMatchReceipt.market_id],
            set_={
                "source": stmt.excluded.source,
                "external_id": stmt.excluded.external_id,
                "market_name": stmt.excluded.market_name,
                "phase": stmt.excluded.phase,
                "outcome": stmt.excluded.outcome,
                "reject_reason": stmt.excluded.reject_reason,
                "linked_event_id": stmt.excluded.linked_event_id,
                "candidates": stmt.excluded.candidates,
                "detail": stmt.excluded.detail,
                "last_attempted_at": stmt.excluded.last_attempted_at,
                "first_attempted_at": func.least(
                    MarketMatchReceipt.first_attempted_at,
                    stmt.excluded.first_attempted_at,
                ),
                "attempt_count": MarketMatchReceipt.attempt_count + 1,
            },
        )
        await session.execute(stmt)
        written += len(batch)
    return written
