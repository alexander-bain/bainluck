"""Resolution authority ladder for is_winner / resolution_source writes (#845).

`is_winner` writes were governed by ~30 ad-hoc phases with scattered NOT-IN
guard lists. Nothing structurally prevented a heuristic guess from overwriting an
authoritative settlement — the root cause of the 71,896 guess-resolved outcomes
in #754.

This module is the SINGLE SOURCE OF TRUTH for:
  1. the authority ORDERING (`authority_tier` / `is_downgrade`) — used by the CI
     guard test to fail any change that would let a lower-authority source
     overwrite a higher one, or introduce a new guess-family write; and
  2. the canonical source SETS + SQL fragments the backfill phases interpolate,
     so the guess-family / overwritable lists live in ONE place instead of being
     copy-pasted (and silently drifting) across phases.

Pure module: no DB, no network, no imports from app code — safe to import from
tasks and tests alike (mirrors the sport_keys.py "pure shared data" pattern).

NOTE (2026-07-01 external comment on #845, MarkovianProtocol): the idea of
defining the top rung by *recomputability from cited public data* rather than a
source name is noted but NOT adopted here — it needs its own evaluation and would
require storing canonical inputs alongside every write. This module keeps the
name-based ladder the issue scopes; recomputability can layer on later.
"""

from __future__ import annotations

# ---------------------------------------------------------------------------
# Authority tiers (higher tier = more authoritative). A write must never lower
# the tier of an already-resolved outcome (see is_downgrade).
# ---------------------------------------------------------------------------

# Tier 3 — external settlement: the venue's OWN settled result (API/CLOB). The
# strongest authority; nothing may overwrite these.
AUTHORITATIVE_SOURCES: frozenset[str] = frozenset({
    "api_settlement",
    "clob_authoritative",
    "clob_ordinal",
    "datagolf_settlement",
    "settlement_sync",
    "poly_total_score",
})

# Tier 2 — deterministic from cited public data (box score / game score / final
# leaderboard). Recomputes to the same winner; overwrites only guesses/soft.
DETERMINISTIC_SOURCES: frozenset[str] = frozenset({
    "box_score",
    "box_score_bound",
    "scoring_plays",
    "game_score",
    "leaderboard",
    "datagolf_matchup",
    "datagolf_played_lost",
})

# Tier 1 — terminal/soft: structural losers/voids (deterministic, no winner) and
# the soft "clean" close-probability resolution. Overwritable by a hard result.
#
# `date_passed` grades an open "by <past-date>?" Polymarket binary whose deadline
# has lapsed and whose No side sits near-certain (>= 0.95): the event provably did
# NOT happen by the stated date, so No wins. It is deterministic-from-the-clock but
# NOT the venue's own settlement, so it lives in the terminal tier — a later
# authoritative Gamma/CLOB settlement (tier 3) may overwrite it.
TERMINAL_SOURCES: frozenset[str] = frozenset({
    "clean_resolution",
    "pass2_loser",
    "all_losers",
    "did_not_play",
    "withdrew",
    "no_pregame_trading",
    "date_passed",
})

# Tier 0 — guess-family: heuristic inferences with no cited authority. These are
# the poison class (#754). They must NEVER overwrite a higher tier, and adding a
# new one must be a deliberate, test-visible act.
GUESS_FAMILY_SOURCES: frozenset[str] = frozenset({
    "pass2_guess",
    "binary_higher_wins",
    "multi_max_prob",
    "pass3_threshold",
})

_TIERS: tuple[tuple[int, frozenset[str]], ...] = (
    (3, AUTHORITATIVE_SOURCES),
    (2, DETERMINISTIC_SOURCES),
    (1, TERMINAL_SOURCES),
    (0, GUESS_FAMILY_SOURCES),
)

# Every resolution_source the codebase writes must be classified above so the
# guard can reason about it (the completeness test enforces this).
KNOWN_SOURCES: frozenset[str] = (
    AUTHORITATIVE_SOURCES | DETERMINISTIC_SOURCES | TERMINAL_SOURCES | GUESS_FAMILY_SOURCES
)

# Sentinel tier for an unclassified source: below everything, so an unknown write
# can never be treated as authoritative (fail-safe; the completeness test should
# catch it long before prod).
_UNKNOWN_TIER = -1


def authority_tier(source: str | None) -> int:
    """Return the authority tier of a resolution_source (higher = stronger).

    None/empty → -1 (treated as unresolved, below all real sources). An
    unclassified non-empty source also → -1 (fail-safe)."""
    if not source:
        return _UNKNOWN_TIER
    for tier, members in _TIERS:
        if source in members:
            return tier
    return _UNKNOWN_TIER


def is_guess_family(source: str | None) -> bool:
    """True if the source is a heuristic guess (tier 0, the poison class)."""
    return source in GUESS_FAMILY_SOURCES


def is_authoritative(source: str | None) -> bool:
    """True if the source is an external settlement (tier 3)."""
    return source in AUTHORITATIVE_SOURCES


def can_write_winner(market_status: str | None, source: str | None) -> bool:
    """True if `source` is allowed to assert is_winner on a market in this status.

    The invariant (#845 status-awareness): a winner may only stand on a market
    that has actually settled (`resolved`/`closed`) OR — regardless of market
    status — when written by an authoritative external settlement (tier 3), which
    is self-justifying (the venue said so). Every other write on a still-open
    market is premature and must be cleared (`_clear_premature_open_winners`).

    Fail-safe on unknown status: only an authoritative source may write when the
    market status is anything other than resolved/closed."""
    return (market_status in {"resolved", "closed"}) or is_authoritative(source)


def is_downgrade(existing: str | None, new: str | None) -> bool:
    """True if writing `new` over an already-resolved `existing` lowers authority.

    Writing over an unresolved outcome (existing None/empty) is never a downgrade.
    A same-tier rewrite is allowed (e.g. re-running api_settlement)."""
    if not existing:
        return False
    return authority_tier(new) < authority_tier(existing)


# ---------------------------------------------------------------------------
# Canonical SQL SETS + fragments — the backfill phases interpolate these so the
# "which sources are overwritable / are guesses" decision lives in ONE place.
# ---------------------------------------------------------------------------

# The set treated as "NOT an authoritative winner" in the re-resolution HAVING
# guards (a market may be re-resolved when its only winners come from these). It
# is the guess-family PLUS the soft/terminal winner-bearing sources that a hard
# result may supersede. Kept byte-for-byte equal to the tuple that was duplicated
# across the phases (the drift-scan test pins this).
OVERWRITABLE_WINNER_SOURCES: tuple[str, ...] = (
    "pass2_guess",
    "binary_higher_wins",
    "multi_max_prob",
    "clean_resolution",
    "pass2_loser",
    "pass3_threshold",
)


def _sql_in_list(sources: tuple[str, ...] | frozenset[str]) -> str:
    """Render a SQL IN-list fragment: ('a', 'b', ...) from a source set."""
    ordered = sources if isinstance(sources, tuple) else tuple(sorted(sources))
    return "(" + ", ".join(f"'{s}'" for s in ordered) + ")"


# SQL fragment (no surrounding IN/NOT IN keyword) for the overwritable set.
OVERWRITABLE_WINNER_SOURCES_SQL: str = _sql_in_list(OVERWRITABLE_WINNER_SOURCES)

# SQL fragment for the strict guess-family set (for guards that must protect ANY
# non-guess resolution, including deterministic/soft ones).
GUESS_FAMILY_SOURCES_SQL: str = _sql_in_list(GUESS_FAMILY_SOURCES)


# ---------------------------------------------------------------------------
# Calibration-truth eligibility (Queue #261) — ORTHOGONAL to overwrite authority.
#
# The tier ladder above answers "may this source's write STAND over another's?"
# (overwrite authority). Calibration-truth eligibility answers a DIFFERENT
# question: "may this source's resolved winner GRADE a published calibration
# forecast?". The two axes deliberately diverge:
#
#   * settlement_sync is tier-3 AUTHORITATIVE (its write may stand) yet is
#     price-derived (is_winner = current_probability >= 0.95), so it must NOT
#     grade a forecast — a terminal price that both defines the winner AND
#     grades the earlier/current price is self-grading leakage (C20/C21).
#   * clean_resolution is tier-1 TERMINAL and likewise price-derived.
#
# A source is calibration-truth-eligible iff its winner is established
# INDEPENDENTLY of the market's own price: external venue/API settlement, or
# deterministic recomputation from cited public data (box score / game score /
# leaderboard / clock). Guess-family (no cited authority), structural
# no-winner/void (no real prediction to grade), and price-derived truth are all
# ineligible. Unknown sources FAIL CLOSED (ineligible) — the completeness test
# forces every classified source into exactly one bucket before it can ship.
# ---------------------------------------------------------------------------

# Price-derived resolution: the winner is inferred from the market's OWN
# terminal/close price, not an independent authority. Operationally useful, but
# never independent of the forecast it would grade — ineligible regardless of
# overwrite tier (settlement_sync is tier 3; clean_resolution is tier 1).
PRICE_DERIVED_SOURCES: frozenset[str] = frozenset({
    "clean_resolution",
    "settlement_sync",
})

# Sources whose winner is established INDEPENDENTLY of the market's own price:
# venue/API settlement (minus the price-derived settlement_sync) + deterministic
# public-data resolution + date_passed (deterministic-from-the-clock, real
# winner). These — and only these — may grade a published calibration forecast.
CALIBRATION_TRUTH_ELIGIBLE_SOURCES: frozenset[str] = (
    (AUTHORITATIVE_SOURCES - PRICE_DERIVED_SOURCES)
    | DETERMINISTIC_SOURCES
    | frozenset({"date_passed"})
)

# The complement over KNOWN_SOURCES: guess-family, structural no-winner/void,
# and price-derived truth. Ineligible to grade a published forecast.
CALIBRATION_TRUTH_INELIGIBLE_SOURCES: frozenset[str] = (
    KNOWN_SOURCES - CALIBRATION_TRUTH_ELIGIBLE_SOURCES
)


def is_calibration_truth_eligible(source: str | None) -> bool:
    """True iff `source` may grade a published calibration forecast.

    Fail-closed: None/empty and any unclassified source return False (an unknown
    winner-writer can never leak into the published curve). Orthogonal to
    authority_tier — a tier-3 price-derived source (settlement_sync) is False."""
    return source in CALIBRATION_TRUTH_ELIGIBLE_SOURCES


def calibration_truth_class(source: str | None) -> str:
    """Classify a resolution_source for calibration-truth reporting.

    One of: ``authoritative_independent`` (venue/API settlement, non-price),
    ``deterministic_independent`` (score/leaderboard/clock), ``price_derived``
    (self-grading — ineligible), ``structural_void`` (no-winner/void),
    ``guess`` (heuristic), ``missing`` (None/empty), or ``unknown``
    (a non-empty source not in KNOWN_SOURCES — fail-closed, and the completeness
    test fails)."""
    if source is None or str(source).strip() == "":
        return "missing"
    if source in PRICE_DERIVED_SOURCES:
        return "price_derived"
    if source in GUESS_FAMILY_SOURCES:
        return "guess"
    if source in (AUTHORITATIVE_SOURCES - PRICE_DERIVED_SOURCES):
        return "authoritative_independent"
    if source in DETERMINISTIC_SOURCES or source == "date_passed":
        return "deterministic_independent"
    if source in TERMINAL_SOURCES:  # remaining terminal = structural no-winner/void
        return "structural_void"
    return "unknown"


# SQL fragments (rendered from the frozensets above, sorted → deterministic).
CALIBRATION_TRUTH_ELIGIBLE_SOURCES_SQL: str = _sql_in_list(
    CALIBRATION_TRUTH_ELIGIBLE_SOURCES
)
CALIBRATION_TRUTH_INELIGIBLE_SOURCES_SQL: str = _sql_in_list(
    CALIBRATION_TRUTH_INELIGIBLE_SOURCES
)
PRICE_DERIVED_SOURCES_SQL: str = _sql_in_list(PRICE_DERIVED_SOURCES)

# SQL fragment for the AUTHORITATIVE (tier-3) set. #845 batch 2: the phases that
# write api_settlement previously guarded only `!= 'api_settlement'`, so they
# could clobber a sibling authoritative source (clob_authoritative,
# datagolf_settlement, …). Routing those guards through this set protects the
# whole tier — strictly more conservative (an UPDATE skips MORE rows, never
# resolves more), so it can only prevent a downgrade, never cause one.
AUTHORITATIVE_SOURCES_SQL: str = _sql_in_list(AUTHORITATIVE_SOURCES)

# Guess-family sources that assert a SINGLE winner in a mutually-exclusive
# market (moneyline / set-winner / head-to-head). This is GUESS_FAMILY_SOURCES
# MINUS pass3_threshold: pass3_threshold grades cumulative-threshold ladders
# ("Over 3.5 maps" AND "Over 4.5 maps"), where multiple YES outcomes are
# LEGITIMATELY co-winners — flipping one there would corrupt a correct result.
# The both-winner correction (#997) flips ONLY these when a strictly-higher
# authority sibling already won; pass3_threshold is deliberately excluded so
# legit ladders are never touched. Kept in the ladder module so the drift-scan
# test (which forbids the inline 3-tuple literal in backfill_winners.py) stays
# the single source of truth for guess-family membership.
SINGLE_WINNER_GUESS_SOURCES: tuple[str, ...] = (
    "pass2_guess",
    "binary_higher_wins",
    "multi_max_prob",
)
SINGLE_WINNER_GUESS_SOURCES_SQL: str = _sql_in_list(SINGLE_WINNER_GUESS_SOURCES)
