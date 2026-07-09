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
TERMINAL_SOURCES: frozenset[str] = frozenset({
    "clean_resolution",
    "pass2_loser",
    "all_losers",
    "did_not_play",
    "withdrew",
    "no_pregame_trading",
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
