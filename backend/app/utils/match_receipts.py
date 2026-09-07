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

A LINK THAT ENDS IS ALSO A THING THAT HAPPENED (LINKLOSS-02, added 2026-09-02).
The first version of this table could only describe an ATTEMPT to attach, which
left the reverse — a link that existed and stopped existing — with no record
anywhere in the system. The night the bus asked "did that merge drop 261
links?", the answer was not uncertain, it was unavailable: a lost link, a moved
link, and a market that had simply settled out of the open population all
looked identical from outside. ``unlinked`` and ``superseded_by_twin_merge``,
``previous_event_id``, ``actor``, and ``futures_markets.settled_at`` are the
four pieces that make that one question a ``GROUP BY``. The full argument for
each is at its definition below.

A LINK CHANGE IS HISTORY, NOT A COLUMN YOU OVERWRITE (LINKLOSS-03, the CERT-791
repair). The vocabulary above was written onto the one-row-per-market receipt,
and that row is an upsert: the *next* ordinary attempt on the same market
replaces ``outcome``, ``previous_event_id`` and ``actor`` with its own. An
unlinked market is by definition ``event_id IS NULL``, which is exactly the
population the scheduled matcher re-scans every 15 minutes — so the receipt
recording *why a price disappeared* was reliably destroyed by the next pass,
usually within the hour, and the 24h census under-counted by everything it had
already re-attempted. The receipt stays what it always was, "the last time the
matcher looked, here is what it decided"; every link change ALSO appends an
immutable row to ``market_link_changes`` (:class:`app.models.models.
MarketLinkChange`), and the census reads that table. One writer — every receipt
goes through :func:`flush_receipts` — so a change cannot be published without
its history row, and nothing later can rewrite one.

NOT A SIMULATION. ``/api/admin/prediction-markets/match-trace`` re-runs the
matching logic *now*, against today's events, with a partial copy of the window
arithmetic. It answers "what would happen if we tried". It cannot answer "what
happened", it drifts from the matcher every time the matcher changes, and it
says nothing at all about a market the scan never reached. Receipts are written
by the matcher itself, on the path that made the decision.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Optional

from sqlalchemy import func, select

from app.utils.name_normalization import normalize_name

# ── Outcomes ────────────────────────────────────────────────────────────────
#
# A LINK THAT ENDS IS AN EVENT, NOT AN ABSENCE. Until LINKLOSS-02 the receipt
# vocabulary was ``linked`` | ``rejected`` — both of them statements about an
# ATTEMPT to attach. Neither can say anything about a link that already existed
# and stopped existing, so a market that had a price on a game card yesterday
# and has none today produces the same evidence as a market that was never
# linked at all: the last receipt still reads ``linked``, and the row underneath
# it sits at NULL.
#
# The night of 2026-09-02 the bus asked "did a merge drop 261 links?" and the
# answer was unavailable — not uncertain, unavailable. There are four ways a
# ``futures_markets.event_id`` stops pointing where it pointed, and before this
# change exactly zero of them left a record:
#
# * the matcher's own re-validation unlinks a mislinked market;
# * the matcher relinks it to a better event;
# * a twin cleanup merges two events and repoints the market onto the survivor;
# * the market settles, leaves the open population, and the link stops being
#   maintained — which is not a loss at all, and is the one that has to be
#   subtractable before the other three can be counted.

OUTCOME_LINKED = "linked"
OUTCOME_REJECTED = "rejected"

#: The market WAS linked and now is not, and no replacement was chosen. The
#: previous event is on ``previous_event_id`` and ``actor`` says who did it.
#: This is the outcome that makes "we lost 261 links tonight" a countable claim
#: instead of a diff between two snapshots.
OUTCOME_UNLINKED = "unlinked"

#: The market's event was merged into another event and the row was repointed
#: onto the survivor. NOT a matching decision: nothing re-examined the market,
#: the ground moved under it. It is its own outcome rather than a ``linked``
#: with a different id because the two answer different questions — "the
#: matcher changed its mind" and "the event this was attached to stopped being
#: the canonical one" have different fixes, and a merge that repoints 261 rows
#: must not read as 261 matching decisions.
OUTCOME_SUPERSEDED_BY_TWIN_MERGE = "superseded_by_twin_merge"

OUTCOMES: frozenset[str] = frozenset({
    OUTCOME_LINKED,
    OUTCOME_REJECTED,
    OUTCOME_UNLINKED,
    OUTCOME_SUPERSEDED_BY_TWIN_MERGE,
})

# ── Actors ──────────────────────────────────────────────────────────────────
# WHO ended the link. Closed, for the same reason the reject enum is closed: the
# bus's question is a GROUP BY, and a free-text actor makes it uncountable.

#: One of the matcher's own passes decided it — Phase 1.5 re-validation or the
#: Phase 2 wrong-game/date sweeps. A bug lives here if the count is not ~0.
ACTOR_MATCHER_PASS = "matcher_pass"

#: An event merge repointed the row (``repoint_event_children``). Expected in
#: bulk: one merge moves every child of the loser at once.
ACTOR_TWIN_CLEANUP = "twin_cleanup"

#: The market settled. The link is not wrong and usually is not even removed —
#: the market simply leaves the open population that ``link-rate`` counts, which
#: is why a settlement wave looks exactly like a link loss until you can
#: subtract it. See ``futures_markets.settled_at``.
ACTOR_SETTLEMENT = "settlement"

#: A human ran an admin repair endpoint. Rare, deliberate, and the one class
#: that has no automated re-examination behind it — so an unexplained unlink
#: that turns out to be this is a different investigation entirely.
ACTOR_ADMIN_REPAIR = "admin_repair"

ACTORS: frozenset[str] = frozenset({
    ACTOR_MATCHER_PASS,
    ACTOR_TWIN_CLEANUP,
    ACTOR_SETTLEMENT,
    ACTOR_ADMIN_REPAIR,
})

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

#: The market has SETTLED, so the matcher will not attempt it again (#2798).
#:
#: NOT A REFUSAL OF A CANDIDATE — an INELIGIBILITY, and the distinction is the
#: whole reason it is a value here rather than an absence. Measured on
#: production 2026-09-03: every receipt the matcher wrote in an hour came from
#: Pass 1, and 7,464 of those 7,642 sat on ``status='resolved'`` markets, some
#: re-attempted 40 times. The event population for a past date is frozen, so
#: not one of those attempts could ever have produced a different answer — and
#: while they ran, Passes 2 and 3 never started at all (zero rows in the whole
#: receipts table carry their phase). The settled tail was eating the budget of
#: the backlog sweep built to end "never attempted".
#:
#: So the settled rows leave the scan, and this value is what keeps that from
#: re-creating the hole the table exists to abolish: a market that stops being
#: attempted must SAY why, once. Written by the settled sweep
#: (:data:`PHASE_SETTLED_SWEEP`) exactly one time per market — its own selection
#: excludes rows that already carry it — so the reject histogram stops being
#: dominated by dead rows whose timestamps keep looking fresh.
#:
#: It overwrites whatever the last live attempt decided, which is correct: the
#: receipt is current state ("the last time the matcher looked, here is what it
#: decided"), and a ``name_mismatch`` on a market that has since resolved
#: describes a question nobody can act on. The history it replaces is not lost —
#: every link CHANGE is immutable in ``market_link_changes``, and
#: ``attempt_count`` / ``first_attempted_at`` survive the upsert.
REJECT_SETTLED = "settled"

#: The receipt's claim about the link and the database disagree. The attempt
#: CHOSE an event and the row is not on it; or the attempt UNLINKED and the row
#: is still attached; or a merge claimed to repoint and the row did not move.
#: The matcher rolled back before the write became durable — a sibling market in
#: the same pass raised, or the commit itself failed.
#:
#: This value exists because the alternative is a receipt that LIES. Publishing
#: `linked_event_id=42` for a market sitting at NULL would make the one-query
#: answer report the opposite of the state it is meant to explain, and would
#: hide the row from every coverage check that treats "has a receipt" as
#: "accounted for". The unlink half is worse, not better: an ``unlinked`` row
#: that did not happen is a fabricated link loss, and link losses are exactly
#: what this vocabulary was added to count. A nonzero count here is itself the
#: finding. Target 0.
REJECT_LINK_NOT_DURABLE = "link_not_durable"

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
    REJECT_SETTLED,
    REJECT_LINK_NOT_DURABLE,
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
#: The settled sweep (#2798) — the one pass that writes a receipt WITHOUT
#: attempting anything. It stamps :data:`REJECT_SETTLED` on the markets that
#: have left the matcher's population by resolving, so "the scan stopped coming
#: here" is a recorded decision instead of a silence. Its own selection skips
#: rows that already carry the reason, which is what makes it once-per-market
#: rather than another every-pass re-touch.
PHASE_SETTLED_SWEEP = "settled_sweep"

# The phases below never attach a market that was unattached. They only END or
# MOVE a link that already existed, which is why they arrived with the
# ``unlinked`` / ``superseded_by_twin_merge`` outcomes and not before.

#: Phase 1.5 re-validation — the pass that re-reads every open linked market and
#: unlinks or relinks the ones whose event no longer agrees with them.
PHASE_PHASE15_REVALIDATE = "phase15_revalidate"
#: Phase 2's two wrong-game sweeps: the multi-game group unlink and the
#: ticker-date-vs-event-date unlink.
PHASE_PHASE2_LINKED = "phase2_linked"
#: ``_relink_collapsed_game_markets`` (#944) — the bulk SQL pass that moves a
#: game market off the last game's event onto its own date's event.
PHASE_RELINK_COLLAPSED = "relink_collapsed"
#: ``_reconcile_kalshi_match_segments`` (Q435) — converges every Kalshi market
#: of one tennis match onto one event.
PHASE_SEGMENT_RECONCILE = "segment_reconcile"
#: ``repoint_event_children`` — a merge moved the children of a losing twin.
PHASE_TWIN_MERGE = "twin_merge"
#: A human ran an admin repair. Named separately from the matcher's passes
#: because "a person did this on purpose" is the answer, not a detail of it.
PHASE_ADMIN_REPAIR = "admin_repair"

PHASES: frozenset[str] = frozenset({
    PHASE_PASS1_TICKER, PHASE_PASS2_GENERAL, PHASE_PASS3_BACKLOG,
    PHASE_SETTLED_SWEEP,
    PHASE_PHASE15_REVALIDATE, PHASE_PHASE2_LINKED, PHASE_TWIN_MERGE,
    PHASE_ADMIN_REPAIR, PHASE_RELINK_COLLAPSED, PHASE_SEGMENT_RECONCILE,
})

#: Cap on the candidate trace stored per receipt. The scoring queries take 20
#: rows; storing all 20 for 21k markets is JSONB nobody reads. The trace is
#: sorted best-score-first before truncation, so the rows that explain the
#: decision are the rows that survive it.
MAX_TRACE_CANDIDATES = 8


# ── Coverage: is this retrieved row THIS GAME? ───────────────────────────────
#
# THE ORACLE MUST NOT BE THE PREDICATE UNDER DIAGNOSIS. A receipt says
# ``name_mismatch`` when the team-name gate refused a real candidate, and
# ``no_candidate`` when the retrieval ILIKE returned rows that are simply other
# games. Separating those two needs a second opinion on "is this row the game
# the market is about" — and it cannot be ``_fuzzy_team_match``, because that is
# the exact function whose refusal is being explained. Asking it produces a
# guaranteed answer: it already said no, so every real name-gate failure would
# be relabelled an upstream absence.
#
# Measured on production, 2026-09-03 (266 rejected receipts on open unlinked
# markets, 222 of them ``name_mismatch``): deriving coverage from
# ``_fuzzy_team_match`` calls **0** of the 222 covered, so all 222 would defer to
# the probe and 109 real name-gate failures would land in ``no_candidate``.
# CERT-783 blocked exactly that on the Browns-Jaguars case (market 60075060,
# "CLE Browns vs JAC Jaguars", event 14780144 "Jacksonville Jaguars" vs
# "Cleveland Browns", in-window and in the candidate list).
#
# So coverage is measured here, on anchor tokens, and the failure it is tuned
# for is the SILENT one: when in doubt, a row counts as covered and the receipt
# keeps saying ``name_mismatch`` — the label it had before receipts learned to
# measure coverage at all. A row is only handed to the probe when it can be
# positively ruled out as this game.

#: A shared token shorter than this is not evidence. Three characters keeps the
#: real anchors ("lsu", "smu", "byu", "usc") and drops the noise ("st", "fc",
#: "la", "at"). Tokens are compared by EQUALITY, never by prefix: a prefix rule
#: makes a one-letter token a wildcard that covers every name starting with that
#: letter (lane1 Q503 measured `Christopher O'Connell` == `Oleksandra
#: Oliynykova` that way).
COVERAGE_MIN_ANCHOR = 3

#: Separators that split a market name into two sides. ``vs``/``v``/``@`` are
#: tried before ``at``, because "University at Albany vs Buffalo" contains both
#: and only the ``vs`` split is the matchup.
_COVERAGE_VS_SPLIT = re.compile(r"\s+(?:vs\.?|v\.?|@)\s+", re.IGNORECASE)
_COVERAGE_AT_SPLIT = re.compile(r"\s+at\s+", re.IGNORECASE)

_COVERAGE_TOKEN = re.compile(r"[a-z0-9]+")


def coverage_anchors(name: Optional[str]) -> frozenset[str]:
    """The tokens of ``name`` long enough to anchor a coverage claim.

    Apostrophes are deleted rather than split on, so "Hawai'i" is one token
    ``hawaii`` and matches "Hawaii Rainbow Warriors". Splitting there would
    produce a one-character token, which is the wildcard this function's
    3-character floor exists to prevent.
    """
    if not name:
        return frozenset()
    base = normalize_name(name).replace("'", "")
    return frozenset(
        t for t in _COVERAGE_TOKEN.findall(base) if len(t) >= COVERAGE_MIN_ANCHOR
    )


def _anchors_touch(side: Optional[str], team: Optional[str]) -> bool:
    return bool(coverage_anchors(side) & coverage_anchors(team))


def sides_from_market_name(
    market_name: Optional[str],
) -> tuple[Optional[str], Optional[str]]:
    """The two sides a market's own NAME states, or ``(None, None)``.

    This is the second, independent reading of the matchup. The matcher's parsed
    ``team_a``/``team_b`` come from an extractor that can be wrong in a way no
    amount of team-name tolerance recovers from: on production, "Denver vs
    Kansas City" parsed to ``Nuggets``/``Chiefs`` — the NBA teams for those
    cities, for an NFL market — and 65 of 222 ``name_mismatch`` receipts were
    that shape. Reading the sides off the name catches those, because the row
    the ILIKE returned really is the game the name describes.

    A trailing ``": Spread"`` / ``": 1st Half Total"`` qualifier is dropped; a
    name that does not split into exactly two non-empty sides yields nothing.
    """
    head = (market_name or "").split(":")[0]
    for pattern in (_COVERAGE_VS_SPLIT, _COVERAGE_AT_SPLIT):
        parts = pattern.split(head)
        if len(parts) == 2 and parts[0].strip() and parts[1].strip():
            return parts[0].strip(), parts[1].strip()
    return None, None


def sides_covered(
    side_a: Optional[str],
    side_b: Optional[str],
    home_team: Optional[str],
    away_team: Optional[str],
) -> int:
    """How many of the named sides this row's two teams cover, 0-2.

    The two sides must land on DIFFERENT team slots. Without that, "Morehouse
    Maroon Tigers vs Arkansas-Pine Bluff" would read as fully covered by a row
    whose home and away are both Tigers — the one-token retrieval coincidence
    the whole distinction exists to catch.
    """
    if not side_a and not side_b:
        return 0
    if not side_b:
        return 1 if (_anchors_touch(side_a, home_team)
                     or _anchors_touch(side_a, away_team)) else 0
    if (
        (_anchors_touch(side_a, home_team) and _anchors_touch(side_b, away_team))
        or (_anchors_touch(side_a, away_team) and _anchors_touch(side_b, home_team))
    ):
        return 2
    if any((
        _anchors_touch(side_a, home_team), _anchors_touch(side_a, away_team),
        _anchors_touch(side_b, home_team), _anchors_touch(side_b, away_team),
    )):
        return 1
    return 0


def row_coverage(
    market_name: Optional[str],
    team_a: Optional[str],
    team_b: Optional[str],
    home_team: Optional[str],
    away_team: Optional[str],
) -> tuple[int, int]:
    """``(sides_covered, sides_named)`` for one retrieved row.

    Both readings of the matchup get a vote and the better one wins, because a
    miss in either direction costs a true ``name_mismatch``: the parsed sides
    can be invented (``Nuggets`` for an NFL market) and the name can be
    unsplittable (a Polymarket "Player Props" container).
    """
    named = 2 if team_b else 1
    best = sides_covered(team_a, team_b, home_team, away_team)
    if best < named:
        name_a, name_b = sides_from_market_name(market_name)
        if name_a and name_b:
            best = max(
                best,
                min(sides_covered(name_a, name_b, home_team, away_team), named),
            )
    return best, named


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
    #: How many of the sides the MARKET named this candidate's two teams cover,
    #: out of ``sides_named``, per :func:`row_coverage`. This is the difference
    #: between a candidate and a coincidence: the retrieval ILIKE fires on ONE
    #: token, so "Morehouse Maroon Tigers vs Arkansas-Pine Bluff" retrieves
    #: Detroit Tigers (MLB) and Hanshin Tigers (NPB), and reporting those as a
    #: name-gate refusal blames OUR matcher for a game that is not in ``events``
    #: at all. ``None`` on a trace whose coverage was never computed.
    sides_matched: Optional[int] = None
    #: How many sides the market named: 2 for a normal matchup, 1 for the
    #: single-team ``will_win`` shape. Stored per trace so one exported row is
    #: readable without its market — the same reason ``source`` is denormalized
    #: onto the receipt.
    sides_named: Optional[int] = None

    @property
    def covers_matchup(self) -> bool:
        """True when this candidate's teams cover EVERY side the market named.

        A candidate that covers fewer is a retrieval coincidence, not a rejected
        candidate, and must not be reported as one.
        """
        if self.sides_matched is None or self.sides_named is None:
            return False
        return self.sides_matched >= self.sides_named

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
            "sides_matched": self.sides_matched,
            "sides_named": self.sides_named,
        }


def _validated_actor(actor: Optional[str]) -> str:
    """The actor, or a loud failure. Same contract as the reject enum.

    An unknown actor string is worse than an unknown reject reason: the reject
    enum's consumers at least see a row they can eyeball, while the link-loss
    census is a ``GROUP BY actor`` whose whole output is the enum. One typo and
    a class of losses becomes its own silent bucket.
    """
    if actor not in ACTORS:
        raise ValueError(
            f"unknown link-change actor {actor!r} — add it to "
            f"app/utils/match_receipts.ACTORS"
        )
    return actor


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
    #: Where the link pointed BEFORE this attempt, when this attempt changed or
    #: ended it. NULL on an ordinary attach and on every reject. Reading it
    #: together with ``linked_event_id`` is the whole point: ``(42, None)`` is a
    #: loss, ``(42, 91)`` is a move, ``(None, 91)`` is an attach.
    previous_event_id: Optional[int] = None
    #: One of :data:`ACTORS` — who ended or moved the link. NULL when nothing
    #: was ended or moved.
    actor: Optional[str] = None
    candidates: list[CandidateTrace] = field(default_factory=list)
    detail: dict[str, Any] = field(default_factory=dict)

    def reject(self, reason: str, **detail: Any) -> "MatchReceipt":
        """Mark this attempt rejected. Unknown reasons raise, by design.

        A typo'd reason string is a silently uncountable row, which is the
        exact failure this table was built to end — so it fails loudly here,
        in the caller's own stack, rather than becoming the 997th unexplained
        market.

        A REJECT CARRIES NO LINK CHANGE. ``previous_event_id`` and ``actor``
        are cleared, not merely left behind, so that a row carrying them is
        always a change that really happened. The path that makes this
        load-bearing is :func:`verify_links_are_durable`: it downgrades an
        unlink whose row is still attached, and if the downgraded receipt kept
        its ``previous_event_id`` the "what came off this event" lookup would
        still report a departure that never occurred. The claimed ids survive
        in ``detail``, where they are evidence rather than assertion.
        """
        if reason not in REJECT_REASONS:
            raise ValueError(
                f"unknown match reject reason {reason!r} — add it to "
                f"app/utils/match_receipts.REJECT_REASONS"
            )
        self.outcome = OUTCOME_REJECTED
        self.reject_reason = reason
        self.linked_event_id = None
        self.previous_event_id = None
        self.actor = None
        if detail:
            self.detail.update(detail)
        return self

    def link(
        self,
        event_id: int,
        *,
        previous_event_id: Optional[int] = None,
        actor: Optional[str] = None,
        **detail: Any,
    ) -> "MatchReceipt":
        """Mark this attempt linked to ``event_id``.

        A RELINK is still a link, and passing ``previous_event_id`` is what
        makes it one that can be counted. Phase 1.5 moving a market from event
        42 to event 91 leaves the link count unchanged and event 42's card one
        source poorer; without the previous id the receipt reads identically to
        a market attaching for the first time, and the card that went quiet has
        no explanation anywhere in the system.
        """
        self.outcome = OUTCOME_LINKED
        self.reject_reason = None
        self.linked_event_id = event_id
        if previous_event_id is not None and previous_event_id != event_id:
            self.previous_event_id = previous_event_id
            self.actor = _validated_actor(actor or ACTOR_MATCHER_PASS)
        if detail:
            self.detail.update(detail)
        return self

    def unlink(
        self, previous_event_id: int, actor: str = ACTOR_MATCHER_PASS, **detail: Any
    ) -> "MatchReceipt":
        """Mark a link that existed and now does not.

        ``previous_event_id`` is required and not optional-with-a-default: an
        unlink receipt that cannot name what it detached from answers none of
        the questions it exists for. "261 links went away" is a number; "261
        links went away from these 12 events" is a diagnosis.
        """
        self.outcome = OUTCOME_UNLINKED
        self.reject_reason = None
        self.linked_event_id = None
        self.previous_event_id = previous_event_id
        self.actor = _validated_actor(actor)
        if detail:
            self.detail.update(detail)
        return self

    def supersede(
        self,
        previous_event_id: int,
        new_event_id: int,
        actor: str = ACTOR_TWIN_CLEANUP,
        **detail: Any,
    ) -> "MatchReceipt":
        """Mark a link the ground moved under — an event merge repointed it."""
        self.outcome = OUTCOME_SUPERSEDED_BY_TWIN_MERGE
        self.reject_reason = None
        self.linked_event_id = new_event_id
        self.previous_event_id = previous_event_id
        self.actor = _validated_actor(actor)
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
            "previous_event_id": self.previous_event_id,
            "actor": self.actor,
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


#: Every outcome that asserts something about ``futures_markets.event_id`` and
#: therefore has to be checked against it before publication. ``rejected`` is
#: absent by design: it asserts nothing about the column, only about an attempt.
_STATEFUL_OUTCOMES: frozenset[str] = frozenset({
    OUTCOME_LINKED, OUTCOME_UNLINKED, OUTCOME_SUPERSEDED_BY_TWIN_MERGE,
})


async def verify_links_are_durable(session, receipts: list[MatchReceipt]) -> int:
    """Downgrade any receipt whose claim the database does not hold (CERT-771).

    THE INVARIANT: a receipt never asserts a link state that is not committed.
    The matcher now commits each link before claiming it, so in the normal path
    this finds nothing — but the guarantee must not rest on that, because the
    failure it prevents is the worst one this table can have. A receipt reading
    ``linked_event_id=42`` for a market sitting at NULL does not merely lose
    information: it reports the OPPOSITE of the state it exists to explain, and
    it hides the row from every coverage check that treats "has a receipt" as
    "accounted for".

    ALL THREE STATEFUL CLAIMS ARE CHECKED, not just the attach. ``unlinked``
    asserts the column is NULL and ``superseded_by_twin_merge`` asserts it moved
    to a named survivor, and both are read by the link-loss census — so a
    rolled-back unlink republished as fact would *invent* the very link loss the
    census exists to find, which is a worse failure than the one CERT-771
    caught. Every stateful outcome is one comparison against the same row, so
    covering them costs nothing beyond the comparison.

    The claim is checked in the receipt session, right before publication. One
    indexed primary-key read per flush. Returns the number downgraded — nonzero
    means the matcher's writes are not landing, which is a finding in its own
    right and is counted as ``link_not_durable``.
    """
    from sqlalchemy import select

    from app.models.models import FuturesMarket

    claimed = {
        r.market_id: r for r in receipts if r.outcome in _STATEFUL_OUTCOMES
    }
    if not claimed:
        return 0

    rows = (await session.execute(
        select(FuturesMarket.id, FuturesMarket.event_id)
        .where(FuturesMarket.id.in_(list(claimed)))
    )).all()
    durable = {int(mid): eid for mid, eid in rows}

    downgraded = 0
    for market_id, receipt in claimed.items():
        observed = durable.get(market_id)
        # For every stateful outcome the assertion is the same shape: after this
        # attempt the row sits on ``linked_event_id`` (NULL for an unlink).
        if observed == receipt.linked_event_id:
            continue
        receipt.reject(
            REJECT_LINK_NOT_DURABLE,
            claimed_outcome=receipt.outcome,
            claimed_event_id=receipt.linked_event_id,
            previous_event_id=receipt.previous_event_id,
            observed_event_id=observed,
        )
        downgraded += 1
    return downgraded


async def record_link_change_receipts(
    market_rows,
    *,
    previous_event_id: int,
    new_event_id: Optional[int],
    actor: str,
    phase: str,
    now: Optional[datetime] = None,
    session_factory=None,
) -> int:
    """Receipt a link change made OUTSIDE the matcher. Returns rows written.

    For the merge rails and the admin repairs — the writers that end or move a
    link without running a matching pass, and so have no receipt list of their
    own to flush.

    CALL AFTER THE CHANGE HAS COMMITTED. :func:`verify_links_are_durable`
    re-reads each market on a fresh session, so a claim published before the
    commit would be read against the pre-change row and downgraded as
    un-durable — the receipt would then report a link the merge really did move
    as one it failed to move, which is a worse answer than none.

    NEVER RAISES. A merge that has already deleted the losing event must not
    then fail because its explanation could not be written; the failure is
    logged and reported as ``0``, and the caller counts what it got back. Same
    contract as ``_flush_pass_receipts`` in the matcher, for the same reason:
    the record must never be able to cost the thing it records.

    ``market_rows`` is a list of dicts carrying ``id``/``source``/
    ``external_id``/``name`` — the shape ``repoint_event_children`` returns
    under ``markets``, read before its update because the previous event id does
    not survive it.
    """
    if not market_rows:
        return 0

    import logging

    from app.tasks.base import get_task_session

    logger = logging.getLogger(__name__)
    attempted_at = now or datetime.now(timezone.utc)

    def _build(row) -> MatchReceipt:
        receipt = MatchReceipt(
            market_id=row["id"],
            source=row.get("source") or "",
            external_id=row.get("external_id"),
            market_name=row.get("name"),
            phase=phase,
            attempted_at=attempted_at,
        )
        if new_event_id is None:
            return receipt.unlink(previous_event_id, actor)
        # THE OUTCOME FOLLOWS FROM THE ACTOR, and only for this one actor.
        # ``superseded_by_twin_merge`` means the market did not move — its event
        # stopped existing under it. Every other actor moving a link made a
        # decision about the market, which is a ``linked`` carrying where it
        # came from. Collapsing the two would make a merge read as hundreds of
        # matching decisions, which is the misreading the outcome exists to
        # prevent.
        if actor == ACTOR_TWIN_CLEANUP:
            return receipt.supersede(previous_event_id, new_event_id, actor)
        return receipt.link(
            new_event_id, previous_event_id=previous_event_id, actor=actor,
        )

    receipts = [_build(row) for row in market_rows]

    factory = session_factory or get_task_session
    try:
        async with factory() as session:
            await verify_links_are_durable(session, receipts)
            written = await flush_receipts(session, receipts)
            await session.commit()
        return written
    except Exception as exc:  # pragma: no cover - defensive, see docstring
        logger.warning(
            "Link-change receipts failed for %d market(s) moved %s -> %s "
            "(%s/%s): %s",
            len(receipts), previous_event_id, new_event_id, actor, phase,
            str(exc)[:200],
        )
        return 0


async def record_out_of_band_attempt(
    market_row,
    *,
    phase: str,
    linked_event_id: Optional[int] = None,
    reject_reason: Optional[str] = None,
    detail: Optional[dict[str, Any]] = None,
    now: Optional[datetime] = None,
    session_factory=None,
) -> int:
    """Receipt ONE matching attempt made outside the matcher's own passes.

    :func:`record_link_change_receipts` covers the writers that END or MOVE a
    link, and requires a ``previous_event_id`` to say what changed. A hand-run
    attach has no previous id — the market was unlinked and now is not — so it
    fits none of those signatures and, until #3755, was written by nobody. The
    result was that the admin tool recorded its rejections nowhere and its
    SUCCESSES nowhere either: a correct link with no phase, no candidate list
    and no score, invisible to ``/api/admin/match-receipts`` and to the
    link-change history, and indistinguishable afterwards from a market the
    matcher never reached.

    Exactly one of ``linked_event_id`` / ``reject_reason`` must be given; both
    or neither is a caller bug and raises, because "an attempt happened and we
    are not saying what it decided" is the row this table exists to prevent.

    NO ACTOR IS SET ON AN ATTACH, deliberately, and this is not an oversight to
    be fixed later. ``actor`` in this module means *who ended or moved a link*
    — :func:`link_change_row` keys the append-only history off exactly that,
    and :meth:`MatchReceipt.reject` clears it so that a row carrying one is
    always a change that really happened. A fresh attach changed nothing, so
    stamping it with an actor would put a phantom row in the link-change
    history and make an attach read as a departure from somewhere. The
    provenance a reader wants — *a human did this by hand* — is carried by
    ``phase`` (``admin_repair``), which is what the two existing admin call
    sites already use.

    CALL AFTER THE CHANGE HAS COMMITTED and NEVER RAISES, both for the reasons
    spelled out on :func:`record_link_change_receipts`: the claim is re-read on
    a fresh session by :func:`verify_links_are_durable`, and the record must
    never be able to cost the thing it records. Returns rows written — 0 means
    the explanation failed, never that the link did.
    """
    if (linked_event_id is None) == (reject_reason is None):
        raise ValueError(
            "record_out_of_band_attempt needs exactly one of linked_event_id / "
            f"reject_reason (got {linked_event_id!r} / {reject_reason!r})"
        )

    import logging

    from app.tasks.base import get_task_session

    logger = logging.getLogger(__name__)

    receipt = MatchReceipt(
        market_id=market_row["id"],
        source=market_row.get("source") or "",
        external_id=market_row.get("external_id"),
        market_name=market_row.get("name"),
        phase=phase,
        attempted_at=now or datetime.now(timezone.utc),
    )
    if linked_event_id is not None:
        receipt.link(linked_event_id, **(detail or {}))
    else:
        # An unknown reason raises inside ``reject`` — on purpose, and left to
        # propagate rather than swallowed by the guard below, because a typo'd
        # reason is a caller bug that must surface in tests, not a runtime
        # failure of the recording path.
        receipt.reject(reject_reason, **(detail or {}))

    factory = session_factory or get_task_session
    try:
        async with factory() as session:
            await verify_links_are_durable(session, [receipt])
            written = await flush_receipts(session, [receipt])
            await session.commit()
        return written
    except Exception as exc:  # pragma: no cover - defensive, see docstring
        logger.warning(
            "Out-of-band match receipt failed for market %s (%s, %s): %s",
            market_row.get("id"), phase,
            linked_event_id if linked_event_id is not None else reject_reason,
            str(exc)[:200],
        )
        return 0


async def record_twin_merge_receipts(
    market_rows,
    *,
    previous_event_id: int,
    new_event_id: int,
    now: Optional[datetime] = None,
    session_factory=None,
) -> int:
    """Receipt every market an event merge repointed. Returns rows written.

    The merge rails' spelling of :func:`record_link_change_receipts`, so a call
    site cannot get the actor/phase pair wrong for the one case there are three
    callers of.
    """
    return await record_link_change_receipts(
        market_rows,
        previous_event_id=previous_event_id,
        new_event_id=new_event_id,
        actor=ACTOR_TWIN_CLEANUP,
        phase=PHASE_TWIN_MERGE,
        now=now,
        session_factory=session_factory,
    )


def link_change_row(receipt: MatchReceipt) -> Optional[dict[str, Any]]:
    """The append-only history row for a receipt that ENDED or MOVED a link.

    ``None`` for everything else, and the two conditions are separate on
    purpose:

    * the outcome must be one that asserts something about
      ``futures_markets.event_id`` — a ``rejected`` receipt never appends,
      including one :func:`verify_links_are_durable` downgraded, which is what
      keeps a rolled-back unlink out of the permanent record;
    * ``previous_event_id`` must be set — an ordinary first attach is not a
      change to any link that existed, and counting it as one would inflate the
      census with losses that never happened.
    """
    if receipt.outcome not in _STATEFUL_OUTCOMES:
        return None
    if receipt.previous_event_id is None:
        return None
    return {
        "market_id": receipt.market_id,
        "source": (receipt.source or "")[:50],
        "external_id": (receipt.external_id or "")[:200] or None,
        "market_name": (receipt.market_name or "")[:300] or None,
        "phase": receipt.phase,
        "outcome": receipt.outcome,
        "actor": _validated_actor(receipt.actor),
        "previous_event_id": receipt.previous_event_id,
        "new_event_id": receipt.linked_event_id,
        "detail": _jsonable(receipt.detail),
        "changed_at": receipt.attempted_at,
    }


async def append_link_changes(
    session, receipts: list[MatchReceipt], chunk: int = 500
) -> int:
    """Append one immutable row per link change. Returns rows written.

    Plain ``INSERT``: no key to conflict on, nothing to update, nothing that
    can overwrite an earlier change. That is the entire difference from the
    receipt upsert beside it, and it is the difference CERT-791 blocked on —
    an unlinked market is ``event_id IS NULL``, which is the population the
    matcher re-scans every 15 minutes, so the receipt explaining a lost price
    was routinely replaced by an ordinary ``rejected`` attempt before anyone
    read it.

    Called from :func:`flush_receipts` on the same session and therefore inside
    the same transaction as the receipt it accompanies: a change is recorded
    once, in both places, or in neither.
    """
    rows = [row for row in map(link_change_row, receipts) if row is not None]
    if not rows:
        return 0

    from sqlalchemy import insert as sa_insert

    from app.models.models import MarketLinkChange

    written = 0
    for start in range(0, len(rows), chunk):
        batch = rows[start:start + chunk]
        await session.execute(sa_insert(MarketLinkChange).values(batch))
        written += len(batch)
    return written


def link_change_census_query(since: datetime):
    """``GROUP BY outcome, actor, phase`` over the changes in a window.

    The one query the bus asks on the night of a merge, and it reads HISTORY.
    Asking the receipt table instead answers a different question — "link
    changes whose market has not been attempted since" — which is smaller,
    shrinks the longer you wait, and looks exactly like a quiet night.
    """
    from app.models.models import MarketLinkChange

    return (
        select(
            MarketLinkChange.outcome,
            MarketLinkChange.actor,
            MarketLinkChange.phase,
            func.count().label("n"),
        )
        .where(MarketLinkChange.changed_at >= since)
        .group_by(
            MarketLinkChange.outcome,
            MarketLinkChange.actor,
            MarketLinkChange.phase,
        )
        .order_by(func.count().desc())
    )


def link_changes_off_event_query(event_id: int, limit: int):
    """What came OFF this event, newest first — the card that went quiet."""
    from app.models.models import MarketLinkChange

    return (
        select(MarketLinkChange)
        .where(MarketLinkChange.previous_event_id == event_id)
        .order_by(MarketLinkChange.changed_at.desc())
        .limit(limit)
    )


def link_changes_for_market_query(market_id: int, limit: int):
    """Every link this market has lost or moved, newest first.

    The single-market half of the ship: "this market had a price yesterday and
    none today" is answered here even after the matcher has attempted it a
    hundred more times, because nothing in this table is ever updated.
    """
    from app.models.models import MarketLinkChange

    return (
        select(MarketLinkChange)
        .where(MarketLinkChange.market_id == market_id)
        .order_by(MarketLinkChange.changed_at.desc())
        .limit(limit)
    )


def link_loss_rows(result) -> list[dict[str, Any]]:
    """The pre-change market rows :func:`record_link_losses` needs, off a result.

    The SELECT that feeds it must run BEFORE the unlink — ``event_id`` is the
    thing about to be destroyed — and it raises rather than shrugging if the
    result cannot supply a column, because at that point nothing has been
    changed yet and a repair that cannot describe itself should not run. That
    is the opposite posture from ``event_child_repoint._rows``, which reads its
    rows mid-merge where a raise would cost the merge.
    """
    return [
        {
            "id": r.id, "source": r.source, "external_id": r.external_id,
            "name": r.name, "event_id": r.event_id,
        }
        for r in result.all()
    ]


async def record_link_losses(
    market_rows,
    *,
    actor: str,
    phase: str,
    now: Optional[datetime] = None,
    session_factory=None,
) -> int:
    """Receipt an unlink of markets that came off DIFFERENT events. Rows written.

    :func:`record_link_change_receipts` takes ONE ``previous_event_id``, because
    a merge moves the children of one loser. The admin repairs do not have that
    shape: ``delete-duplicates`` takes a list of event ids, and the
    date-mismatch sweep unlinks markets scattered across hundreds of events. A
    caller that flattened them onto a single id would name the wrong event as
    the loser on every row but one, and "which event lost its price" is the
    whole question — so the grouping happens here, once, instead of in three
    endpoints.

    ``market_rows`` carry their own pre-change ``event_id``; a row without one
    is skipped rather than guessed at. CALL AFTER THE COMMIT, for the reason in
    :func:`record_link_change_receipts`.
    """
    by_previous: dict[int, list] = {}
    for row in market_rows:
        previous = row.get("event_id", row.get("previous_event_id"))
        if previous is None:
            continue
        by_previous.setdefault(int(previous), []).append(row)

    written = 0
    for previous_event_id, rows in by_previous.items():
        written += await record_link_change_receipts(
            rows,
            previous_event_id=previous_event_id,
            new_event_id=None,
            actor=actor,
            phase=phase,
            now=now,
            session_factory=session_factory,
        )
    return written


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

    AND EVERY LINK CHANGE IS ALSO APPENDED, here, because this is the one
    function every receipt in the system passes through — the matcher's passes,
    the bulk moves, the merge rails and the admin repairs all end up on this
    line. A writer therefore cannot publish a link change and forget its
    history; there is no second path to forget it on. The append runs on the
    same session, from the same deduplicated list the upsert uses, so the two
    tables cannot disagree and neither can outlive a rollback of the other.
    """
    if not receipts:
        return 0

    from sqlalchemy.dialects.postgresql import insert as pg_insert

    from app.models.models import MarketMatchReceipt

    # Last write wins within a batch — the later pass saw the later state.
    # The history append reads the SAME deduplicated list rather than the raw
    # one: ``verify_links_are_durable`` also keeps the last receipt per market,
    # so an earlier same-market receipt in one batch was never checked against
    # the database, and an unverified claim is exactly what must not become
    # permanent.
    deduped: dict[int, MatchReceipt] = {}
    for receipt in receipts:
        deduped[receipt.market_id] = receipt
    ordered = list(deduped.values())
    rows = [r.to_row() for r in ordered]

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
                "previous_event_id": stmt.excluded.previous_event_id,
                "actor": stmt.excluded.actor,
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

    await append_link_changes(session, ordered, chunk=chunk)
    return written
