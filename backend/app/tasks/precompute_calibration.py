"""Precompute heavy calibration queries and cache results in Redis.

These queries time out during Heroku's 30-second request window on production
data volumes (500K+ snapshot rows). Running them as background Celery tasks
with results cached in Redis lets the API endpoints serve instantly.
"""

import contextlib
import json
import logging
import math
import random
import re
import time
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import text

from app.utils.resolution_authority import (
    CALIBRATION_TRUTH_ELIGIBLE_SOURCES_SQL,
    CALIBRATION_TRUTH_INELIGIBLE_SOURCES_SQL,
    PRICE_DERIVED_SOURCES_SQL,
)

logger = logging.getLogger(__name__)

# Redis cache TTL: 24 hours (results don't change quickly)
_CACHE_TTL = 86400

# Main calibration cache TTL: 2 hours (refreshed every 1h by beat)
_MAIN_CACHE_TTL = 7200

# Queue #262: canonical calibration-population fingerprint. Surfaced on every
# population-derived surface (horizon diagnostics, /calibration/examples,
# bucket-debug, snapshot-health) so a future population change is VISIBLE across
# all consumers. Bump when _calibration_population_ctes changes materially.
CALIBRATION_POPULATION_VERSION = "q263"

# L2-73 (#999 §E): the corrections log — "what we found and fixed" — served in the
# payload so web + native render the same trust panel. Static seed from the #997
# record; each entry is a real, dated data-quality fix. When a new class is fixed,
# add a row here (single source of truth for the panel).
CALIBRATION_CORRECTIONS = [
    {
        "date": "2026-07-09",
        "title": "Polymarket hockey sign-flip",
        "rows": 36207,
        "description": "Player-threshold props stored the OVER probability against "
                       "the Under/No side (gotcha #17). Re-graded the Polymarket half "
                       "(poly MCE 4.68 → 4.01).",
    },
    {
        "date": "2026-07-08",
        "title": "Premature golf resolutions",
        "rows": 230,
        "description": "Golf markets resolved at cp=1.0 with future dates were "
                       "un-resolved so they grade against the real result.",
    },
    {
        "date": "2026-07-09",
        "title": "DataGolf survivorship exclusion",
        "rows": None,
        "description": "Symmetric exclusion of did-not-play / withdrew outcomes so the "
                       "golf curve isn't inflated by non-participants.",
    },
    {
        "date": "2026-07-09",
        "title": "Polymarket no-bid placeholder exclusion",
        "rows": None,  # live count in payload.poly_placeholder_filter.excluded
        "description": "Illiquid poly props stamped a no-signal ~0.50 midpoint "
                       "(Gamma synthetic prices, gotcha #19). #151's census proved "
                       "no-bid near-0.50 outcomes resolve at 0.10–0.28 (placeholders) "
                       "vs 0.43–0.55 for has-bid coin-flips. Now excluded from the "
                       "curve by bid presence — read-side only, no regrade.",
    },
    {
        "date": "2026-07-09",
        "title": "Malformed-binary exclusion",
        "rows": None,  # live count in payload.malformed_binary_filter
        "description": "Resolved 2-outcome mutually-exclusive markets must have "
                       "exactly one winner. Zero-winner (void) and two-winner "
                       "(impossible) markets are data artifacts, not scoreable "
                       "outcomes — now excluded from the curve. Census: ~43K "
                       "both-false + ~1.5K both-winner across all categories. "
                       "Read-side only, no regrade.",
    },
    {
        "date": "2026-07-09",
        "title": "Golf FIELD one-sided-ask placeholder exclusion",
        "rows": None,  # live count in payload.golf_placeholder_filter.excluded
        "description": "Golf winner/round-leader outcomes priced >=0.80 in a "
                       "mutually-exclusive market with >=2 such outcomes are "
                       "Kalshi one-sided-ask placeholders (mex probs can't have "
                       "two 80%+ outcomes; 98.6% lose). Excluded; genuine single "
                       "leaders (82% win) stay in. Read-side only, no regrade.",
    },
    {
        "date": "2026-07-10",
        "title": "Multi-candidate probability normalization",
        "rows": None,  # live count in payload.mex_normalization.normalized_outcomes
        "description": "Mutually-exclusive markets with >=3 outcomes are one "
                       "question and must sum to ~1.0, but sources stamp each "
                       "candidate at its one-sided ask so the sum inflated to "
                       "2.4-5.3 (census 2026-07-09). Now each such market's "
                       "probabilities are divided by the per-market sum. Only "
                       "genuine single-winner partitions are touched; multi-winner "
                       "ladders/independent binaries and voids are excluded. "
                       "Read-side only, no regrade.",
    },
    {
        "date": "2026-07-11",
        "title": "Soccer 2-way (draw-omission) historical exclusion",
        "rows": None,  # live count in payload.soccer_2way_filter.excluded
        "description": "Soccer game-odds were captured 2-way (home/away only) — "
                       "no draw column — so every soccer moneyline row summed to "
                       "~1.0 and structurally dropped the ~25% draw mass (#1011), "
                       "in BOTH the events aggregate and the per-bookmaker curve. "
                       "That over-predicted home/away uniformly across all ~20 "
                       "leagues (EPL 17.6pp, Switzerland 15.0pp, Turkey 7.6pp). "
                       "The draw was never stored so these rows can't be "
                       "reconstructed — historical soccer moneyline is excluded "
                       "from the curve (league-scoped by the soccer_* key); soccer "
                       "spreads/totals are kept. Forward fix = 3-way capture "
                       "(#1011 draw column). Read-side only, no regrade.",
    },
    {
        "date": "2026-07-12",
        "title": "Esports match-bundle exclusion",
        "rows": None,  # live count in payload.esports_multi_bundle_filter.excluded
        "description": "Polymarket packs a whole esports match (cumulative "
                       "Total-Kills Over/Under ladders per game, per-game winners, "
                       "first-blood props) into one non-partition market with >=3 "
                       "outcomes. Cumulative Over rungs legitimately resolve many "
                       "YES at once (gotcha #17), so the market has >=2 winners and "
                       "its prices neither sum to ~1.0 (can't be normalized) nor "
                       "bucket as a clean prediction — the counter-class #157 "
                       "refuses to normalize (OPS-557: 93,629 outcomes over-predict "
                       "+9.2pp, avg cp-sum 17.9). The >=3-outcome sibling of the "
                       "malformed-binary filter; excluded from the curve, never "
                       "re-graded (the many-YES grading is correct). Read-side "
                       "only, no regrade.",
    },
    {
        "date": "2026-07-13",
        "title": "Kalshi player-prop threshold exclusion — corrected discriminator (Queue #186)",
        "rows": None,  # live count in payload.kalshi_prop_threshold_filter.excluded
        "description": "Kalshi player-prop 'Player: N+' OVER markets (points/"
                       "assists/goals/total-bases/hits/HR/strikeouts/rebounds/"
                       "blocks) capture a settled post-game quote as the closing "
                       "line (Kalshi commence_time ≈ resolution time, gotcha #14) "
                       "— '6+ total bases' at 0.96, impossible as a real OVER. "
                       "Queue #186 (2026-07-13) corrects the Queue #167 filter: a "
                       "snapshot-level verify over the Calibration Sentinel's "
                       "flagged series (#1069–#1073) disproved #167's 'keep the "
                       "real-bid rows' rule — real-bid rows are corrupt too (a "
                       "scorer and a non-scorer in one market both carry cp 0.995 "
                       "with a live 0.99 bid). The honest discriminator is the "
                       "CURVE PRICE, not the bid. Now excluded: (A) rows in the "
                       "degenerate settlement-collapse band (curve price >= 0.90, "
                       "which resolves 0.11–0.48 across every series), and (B) the "
                       "whole NHL goal-family (category='hockey'), corrupt at every "
                       "band (opening 0.82→winrate 0.05) though its resolution is "
                       "verified sane (5.24 scorers/game) — an illiquid degenerate "
                       "capture, not a sign-flip. Below the band the liquid NBA/MLB "
                       "series are an honest diagonal and are KEPT, bringing their "
                       "high-band actual within ~10pp of predicted (NBAPTS -2pp, "
                       "MLBKS -2pp). No regrade: the sign-flip premise is disproven "
                       "and no honest price exists to recover (gotcha #21). "
                       "Read-side only.",
    },
]

# Horizons: (label, days_before_resolution)
_HORIZONS = [
    ("T-30", 30),
    ("T-7", 7),
    ("T-1", 1),
    ("T-0", 0),
]

_MIN_OUTCOMES_PER_HORIZON = 50

# Item 1 (Queue #220/221): the time-horizon task ran all 4 horizons in one
# process and blew the 600s soft limit (0/27 successes over 3 days; last success
# 2026-07-18, then 12 consecutive SoftTimeLimitExceeded at 600.9s). Each horizon
# is a LATERAL last-snapshot probe over ~539K eligible resolved non-event
# outcomes against the largest table — ~150s each, so 4 in one run overrun the
# limit. Fix = bound + chunk + resumable cursor:
#   * per-horizon statement_timeout bounds any single query (never runs away);
#   * completed horizons are persisted to a WIP accumulator keyed by label, so a
#     later horizon's slowness never discards an already-computed one;
#   * an internal wall-clock deadline (well under the 600s soft limit, sized so a
#     freshly-started horizon can run its full statement_timeout and still finish
#     before the limit) stops the run cleanly and resumes the remaining horizons
#     on the next beat. The full 4-horizon payload assembles across 1-2 runs and
#     is only published (and the WIP cleared) once every horizon is present.
# Runs every 6h; a full refresh lands within ~12h, comfortably inside the 24h TTL.
_TIME_HORIZON_WIP_KEY = "bainluck:calibration:time_horizon:wip"
# Per-horizon statement_timeout (seconds). Bounds a single LATERAL probe.
_HORIZON_STMT_TIMEOUT_S = 300
# Internal deadline (seconds). A horizon is only started if it can run its full
# statement_timeout and still finish before this deadline, which itself sits far
# enough under the 600s soft limit that the run always returns cleanly.
_HORIZON_DEADLINE_S = 560

# #997 App Store ship-gate: a per-category / per-sport reliability chart below
# this many resolved outcomes is statistical noise (a handful of resolutions
# swings MCE by tens of points), not a calibration signal. The gate is enforced
# server-side so web AND future native both inherit it — the published
# by_category / by_sport lists are pre-filtered, and the threshold itself is
# shipped in the payload so clients don't hardcode their own bar. Tunable at
# runtime via the Redis key ``calibration:min_category_outcomes`` (no deploy).
_DEFAULT_MIN_CATEGORY_OUTCOMES = 1000


def _get_min_category_outcomes(rc) -> int:
    """Redis-tunable minimum resolved-outcome count for a chartable sub-category.

    Falls back to _DEFAULT_MIN_CATEGORY_OUTCOMES on any miss/parse error so the
    gate can never silently disable itself (a malformed key must not open the
    thin-sample floodgates)."""
    try:
        raw = rc.get("calibration:min_category_outcomes") if rc is not None else None
        if raw is None:
            return _DEFAULT_MIN_CATEGORY_OUTCOMES
        val = int(raw)
        return val if val >= 0 else _DEFAULT_MIN_CATEGORY_OUTCOMES
    except Exception:
        return _DEFAULT_MIN_CATEGORY_OUTCOMES


# ---------------------------------------------------------------------------
# #940 phase-1: published-calibration liquidity filter (Kalshi-first).
#
# A resolved outcome counts toward the PUBLISHED calibration numbers only if at
# least one snapshot ever showed a real bid (yes_bid > 0) OR a trade
# (last_price > 0). A pure one-sided, never-traded placeholder price (no bid and
# no trade, ever) is a price we never actually discovered, so it is excluded
# from the calibration denominator. This is a READ-SIDE filter only — it never
# mutates is_winner or calibration_probability (gotcha #21).
#
# Kalshi-only for now: Polymarket's per-outcome volume backfill is still sparse
# (phase-2, deferred + Alex-gated). The /calibration page surfaces the
# included/excluded counts + this rule so the filter is transparent, never silent.
#
# KALSHI_LIQUIDITY_EXISTS is the production SQL form (embedded in the main
# calibration query, where ``fo`` is futures_outcomes and ``vm`` carries source).
# outcome_is_calibration_liquid() is the canonical, unit-tested Python definition
# of the same predicate — keep the two in sync.
# ---------------------------------------------------------------------------
KALSHI_LIQUIDITY_EXISTS = (
    "(vm.source <> 'kalshi' OR EXISTS (\n"
    "        SELECT 1 FROM futures_odds_snapshots fos\n"
    "        WHERE fos.outcome_id = fo.id\n"
    "          AND (fos.yes_bid > 0 OR fos.last_price > 0)))"
)

KALSHI_LIQUIDITY_RULE_TEXT = (
    "Excludes outcomes that never showed a real bid (yes_bid > 0) or trade "
    "(last_price > 0) in any snapshot — pure one-sided, never-traded placeholder "
    "prices. Applied to Kalshi only; never mutates resolutions."
)

# L2-76 (#151/#997): curve-side exclusion of the Polymarket no-bid PLACEHOLDER
# class. Gamma stamps synthetic `outcomePrices` at ~0.50 with no orderbook, so an
# illiquid poly outcome sits near 0.50 but is not a real 50/50. #151's census
# proved the discriminator is BID PRESENCE: near-0.50 poly outcomes that NEVER
# showed a bid/trade resolve at 0.10–0.28 (placeholders), while has-bid ones
# resolve at 0.43–0.55 (genuine coin-flips — MUST stay in). So exclude poly
# outcomes in the [0.45, 0.55] band with NO snapshot bid/trade evidence at all.
# Read-side only (gotcha #21) — never mutates is_winner / calibration_probability.
# The bid check uses SNAPSHOT provenance (evidence captured over the outcome's
# life), not the current bid — live bids can clear on resolution.
POLY_PLACEHOLDER_EXCLUDE = (
    "(vm.source = 'polymarket'\n"
    "     AND COALESCE(fo.calibration_probability, fo.opening_probability) >= 0.45\n"
    "     AND COALESCE(fo.calibration_probability, fo.opening_probability) <= 0.55\n"
    "     AND NOT EXISTS (\n"
    "        SELECT 1 FROM futures_odds_snapshots fos\n"
    "        WHERE fos.outcome_id = fo.id\n"
    "          AND (fos.yes_bid > 0 OR fos.last_price > 0)))"
)

POLY_PLACEHOLDER_RULE_TEXT = (
    "Excludes Polymarket outcomes near 0.50 (cp in [0.45, 0.55]) that never showed "
    "a real bid or trade in any snapshot — Gamma synthetic placeholder prices, not "
    "genuine coin-flips (#151 census: no-bid near-0.50 resolve at 0.10–0.28 vs "
    "has-bid at 0.43–0.55). Read-side only; never mutates resolutions."
)

# Queue #220/221 Item 3 — the EXCLUSION-SYMMETRY census.
#
# The never-traded liquidity filter is ASYMMETRIC across sources: Kalshi excludes
# EVERY never-bid/never-traded outcome (all price bands, KALSHI_LIQUIDITY_EXISTS),
# but Polymarket only excludes never-traded outcomes in the near-0.50 placeholder
# band (POLY_PLACEHOLDER_EXCLUDE). A Polymarket outcome that NEVER traded but sits
# outside [0.45, 0.55] (e.g. a 0.10 or 0.92 Gamma synthetic) is therefore still
# counted in the published curve — an asymmetry that Kalshi does not have.
#
# This queue MEASURES that asymmetry (it does not change curve behavior — closing
# the asymmetry by excluding all poly never-traded is a separate, Alex-gated
# decision; gotcha #21 keeps everything read-side). POLY_NEVER_TRADED is the
# all-bands never-traded predicate; the census counts the cohort still IN the
# curve (never traded AND outside the placeholder band).
POLY_NEVER_TRADED = (
    "(vm.source = 'polymarket'\n"
    "     AND NOT EXISTS (\n"
    "        SELECT 1 FROM futures_odds_snapshots fos\n"
    "        WHERE fos.outcome_id = fo.id\n"
    "          AND (fos.yes_bid > 0 OR fos.last_price > 0)))"
)

# Per-source liquidity/never-traded exclusion policy — the parameterization the
# queue asked for. Declaring each source's policy in one structure (instead of
# two ad-hoc SQL fragments) makes the asymmetry explicit, surfaces it in the
# /calibration payload, and turns "close the asymmetry" into a one-field change.
SOURCE_LIQUIDITY_EXCLUSIONS: dict[str, dict[str, Any]] = {
    "kalshi": {
        "never_traded_excluded": "all_bands",
        "rule": KALSHI_LIQUIDITY_RULE_TEXT,
    },
    "polymarket": {
        "never_traded_excluded": "placeholder_band_0.45_0.55",
        "rule": POLY_PLACEHOLDER_RULE_TEXT,
        "asymmetry_note": (
            "Unlike Kalshi (all-bands), Polymarket only excludes never-traded "
            "outcomes in the near-0.50 placeholder band; never-traded outcomes "
            "outside that band are still counted (see poly_never_traded_in_curve)."
        ),
    },
}

# L2-79 Item 1 (#997/#1010): curve-side exclusion of MALFORMED BINARIES. A
# resolved, mutually-exclusive 2-outcome market must have exactly ONE winner.
# Zero winners (both-false = a void/malformed resolution) or two winners
# (both-winner = impossible / double-graded) is a data artifact, not a real
# outcome to score — leaving it in either drags the curve down (both-false
# losers) or fakes a perfect winner (both-winner). The census (2026-07-09) found
# ~43K both-false + ~1.5K both-winner such markets across every category
# (tennis 17.4K, soccer 8.2K, esports 8.1K the largest). Standalone both-false
# markets are already dropped by the clean_vms has_winner>=1 gate; this catches
# the GROUPED both-false losers that leak in via a group/event virtual-market
# AND every both-winner market (which clean_vms keeps, has_winner>=1). Read-side
# only (gotcha #21) — never mutates is_winner / calibration_probability.
MALFORMED_BINARY_RULE_TEXT = (
    "Excludes resolved 2-outcome mutually-exclusive markets whose winner count is "
    "not exactly 1 — zero winners (void/malformed resolution) or two winners "
    "(impossible / double-graded). These are data artifacts, not scoreable "
    "outcomes. Read-side only; never mutates resolutions."
)

# L2-79 Item 2 (#940/#762): curve-side exclusion of golf FIELD/winner ONE-SIDED-
# ASK PLACEHOLDERS. In a mutually-exclusive golf winner/round-leader market, at
# most ONE outcome can legitimately price >=0.80 (mex probabilities must sum to
# ~1). Kalshi stamps illiquid player-winner outcomes at the high ASK (~0.88–0.99)
# with no real two-sided book, so many outcomes in the same market cluster at
# >=0.80 and ~98.6% resolve as losers. The census (2026-07-09) confirmed the
# discriminator: markets with >=2 outcomes in the >=0.80 band produce 954 losers
# vs 14 winners (98.6% loss @ cp 0.93 — placeholder), while markets with exactly
# ONE outcome >=0.80 (a genuine leader/heavy favorite) produce 304 winners vs 65
# losers (82% win @ cp 0.88 — well-calibrated, MUST stay in). So exclude the
# high band ONLY in over-subscribed markets; the low-priced field and genuine
# single leaders are untouched. Read-side only (gotcha #21).
GOLF_PLACEHOLDER_HIGH_BAND = 0.80

GOLF_PLACEHOLDER_RULE_TEXT = (
    "Excludes golf winner/round-leader outcomes priced >=0.80 in mutually-exclusive "
    "markets that have >=2 outcomes in that band — one-sided-ask placeholder prices "
    "(mex probabilities can't have two 80%+ outcomes; ~98.6% resolve as losers). "
    "Genuine single-leader markets (one outcome >=0.80, 82% win) stay in. "
    "Read-side only; never mutates resolutions."
)

# Queue #157 (#1012): curve-side MULTI-CANDIDATE NORMALIZATION.
#
# A resolved, mutually-exclusive market with >=3 outcomes is a partition of ONE
# question — its outcome probabilities MUST sum to ~1.0. But Kalshi/Polymarket
# stamp each candidate at its one-sided ASK, so the per-market cp sum inflates
# well past 1 (census 2026-07-09, mex >=3 markets, cp = COALESCE(cal_prob,
# opening): economics avg 2.37, entertainment 3.09, tech 2.23, football 4.63,
# cricket 1.50, esports 1.91). Leaving the raw over-confident prices in drags ECE
# hard (isolated per-category sim, raw->normalized: football 17.98->10.50,
# entertainment 11.80->4.73, cricket 10.62->6.31, tech 6.91->5.00, economics
# 3.28->2.64 — no category got worse). The fix: divide each eligible outcome's cp
# by the per-market cp sum when that sum exceeds MEX_NORMALIZE_THRESHOLD, so the
# market sums to 1. Markets already ~1.0 (sum <= threshold) are left untouched.
#
# COUNTER-CLASS GUARD (the critical safety): a genuine mex partition resolves with
# EXACTLY ONE winner. Cumulative-threshold ladders ("Over 3.5 maps" + "Over 4.5
# maps") and independent binaries mislabeled mutually_exclusive resolve with 2+
# winners — their probabilities legitimately sum >1 and must NOT be normalized
# (#155 pass3 ladder lesson; gotcha #23's own caveat). The census confirmed the
# discriminator at scale: of the >1.15-sum mex >=3 markets, 6,892 have EXACTLY one
# winner (normalize) vs ~391 multi-winner (ladders/independent — untouched) and
# 336 zero-winner (voids — already excluded). Winner count is taken over ALL
# outcomes, mirroring the malformed_binaries CTE's structure test. Read-side only
# (gotcha #21) — never mutates is_winner / calibration_probability. Writer-side
# durable normalization (stamp at capture) is follow-up scope on #1012.
MEX_NORMALIZE_THRESHOLD = 1.15

MEX_NORMALIZE_RULE_TEXT = (
    "Normalizes resolved mutually-exclusive markets with >=3 outcomes and exactly "
    "one winner whose per-market probability sum exceeds 1.15 — each outcome's "
    "probability is divided by the market sum so the partition sums to ~1.0 (fixes "
    "one-sided-ask over-confidence; census 2026-07-09 found sums of 2.4-5.3 in "
    "economics/entertainment/tech/football). Multi-winner ladders / independent "
    "binaries (2+ winners) and voids (0 winners) are the counter-class and left "
    "untouched, as are markets already summing to ~1.0. Read-side only; never "
    "mutates resolutions."
)


def market_needs_mex_normalization(
    n_eligible: int, n_winners: int, cp_sum: float | None
) -> bool:
    """True if a mutually-exclusive market's curve prices should be normalized (Queue #157).

    Canonical, unit-tested definition mirroring the ``mex_norm_markets`` CTE: a
    resolved mutually-exclusive market qualifies for per-market probability
    normalization iff it has >=3 eligible outcomes, EXACTLY one winner (a genuine
    single-winner partition — not a multi-winner ladder / independent-binary set,
    not a zero-winner void), and its eligible cp sum exceeds
    ``MEX_NORMALIZE_THRESHOLD`` (a sum already ~1.0 needs no correction). The
    caller must have already confirmed the market is a single-winner partition —
    ``mutually_exclusive=true`` OR ``market_type='field'`` (#254: 65K field
    markets carry the mutually_exclusive flag unset yet are definitionally one
    winner among >2 competitors). Read-side only (gotcha #21) — the divisor is
    the eligible cp sum; each outcome's normalized probability is ``cp / cp_sum``.
    """
    return (
        n_eligible >= 3
        and n_winners == 1
        and cp_sum is not None
        and cp_sum > MEX_NORMALIZE_THRESHOLD
    )


# Queue #257 Item 1 — the FIELD-COMPLETENESS invariant before normalization.
#
# market_needs_mex_normalization decides a market is a *candidate* for per-market
# normalization (>=3 eligible, one winner over ALL outcomes, over-confident sum).
# But normalizing divides each survivor's cp by the per-market cp sum so the
# published partition sums to ~1.0 — and that is only correct when the survivors
# ARE the whole field. If a published per-outcome exclusion (liquidity, poly
# placeholder, esports bundle, golf placeholder, Kalshi prop threshold, weather
# wide-spread) removed one or more members, the surviving cp sum is smaller than
# the true full-field sum, so dividing the survivors by it INFLATES them (the
# winner's true share is smaller than survivor_cp / survivor_sum). Worse, if the
# excluded member WAS the winner, normalizing the losers to sum 1.0 is pure
# fiction. Such a PARTIAL field must be EXCLUDED from the curve with a
# machine-readable reason, never "normalized over survivors".
#
# Completeness is proven STRUCTURALLY: there is no stored expected-member count
# (market_type='field' is a shape from app.utils.market_shape — ">2 competitors,
# one wins" — with no member cardinality), so the source-backed invariant is "no
# eligible member of this field was excluded" (survivor_n == eligible_n) AND "the
# winner survived" (survivor_win_n == 1) AND "still a partition" (survivor_n >= 3).
# When that holds, the survivor cp sum equals the divisor, so the bucketed field
# sums to ~1.0 by construction; otherwise the field is excluded. (This detects
# EXCLUSION-INDUCED partiality, which is what the curve controls; members that
# were never ingested at all are undetectable without an expected-member count —
# a documented forward limitation, not fabricated here.) Read-side only (gotcha
# #21) — never mutates is_winner / calibration_probability.
FIELD_COMPLETENESS_RULE_TEXT = (
    "A resolved mutually-exclusive / field market is normalized (each outcome's "
    "probability divided by the per-market sum) ONLY when its captured partition "
    "is COMPLETE — every eligible member survives every per-outcome exclusion and "
    "the winner is among the survivors — so the published field sums to ~1.0. If a "
    "published exclusion removed any member, the field is PARTIAL: normalizing the "
    "survivors would inflate them (their true combined share is < 1.0), so the "
    "whole market is excluded from the curve with a repair reason instead of being "
    "normalized over survivors. Completeness is structural (no stored expected-"
    "member count exists); exclusion-induced partiality is what is detected. "
    "Read-side only; never mutates resolutions."
)


def field_is_complete_for_normalization(
    eligible_n: int, survivor_n: int, survivor_win_n: int
) -> bool:
    """True if a normalization-candidate field is COMPLETE enough to normalize (Queue #257).

    Canonical, unit-tested mirror of the ``field_completeness`` CTE gate. Given a
    market already confirmed a normalization candidate by
    ``market_needs_mex_normalization`` (>=3 eligible, one winner over all
    outcomes, sum > threshold), it is normalized over its survivors ONLY when:

      * ``survivor_n == eligible_n`` — NO eligible member was removed by a
        published per-outcome exclusion (the survivor cp sum therefore equals the
        full-field divisor, so the normalized partition sums to ~1.0), AND
      * ``survivor_win_n == 1`` — the winner itself survived (normalizing losers
        to sum 1.0 when the winner was excluded would be fiction), AND
      * ``survivor_n >= 3`` — the survivor set is still a partition, not a
        collapsed 1-2 outcome remnant.

    When this is False for a candidate, the market is a PARTIAL field and its
    outcomes are EXCLUDED from the published curve (``is_field_incomplete``) with
    a machine-readable reason — never normalized over the survivors. Read-side
    only (gotcha #21).
    """
    return (
        survivor_n == eligible_n
        and survivor_win_n == 1
        and survivor_n >= 3
    )


# Queue #259 Item 1 — the sum-to-1 INVARIANT for a published normalized field.
#
# field_is_complete_for_normalization decides a candidate field is complete enough
# to normalize (cp / per-market sum). But the ``deduped`` CTE then applies two MORE
# filters to every ``is_multi`` row: an extreme-tail cut (adj > 0.005 AND adj < 0.98)
# and a mode-price cut (drop a price shared by > max(eligible*0.5, 2) members). A
# complete normalized field IS ``is_multi`` (>=3 eligible), so before this fix those
# filters ran AFTER normalization and could delete a member the completeness gate
# had already counted — publishing < 1.0 (C14's 0.99/0.20/0.001 -> tail dropped ->
# ~99.9%; a uniform field -> its modal price wipes every member). The tail/mode cuts
# are placeholder heuristics for the NON-partition multi pool, so the fix EXEMPTS
# ``is_mex_normalized`` rows: a complete field publishes ALL its members and the
# partition still sums to ~1.0. This is the executable mirror of that ``deduped``
# decision. Read-side only (gotcha #21).
def published_normalized_field_probabilities(
    raw_cps: list[float], *, apply_tail_mode_filters: bool = False
) -> list[float]:
    """Published normalized probabilities for a COMPLETE single-winner field (Queue #259).

    ``raw_cps`` are the raw curve prices of the field's members (already confirmed a
    complete normalization candidate by ``market_needs_mex_normalization`` +
    ``field_is_complete_for_normalization``). Returns each member's PUBLISHED
    probability = ``cp / sum(cp)``.

    With ``apply_tail_mode_filters=False`` (the shipped ``deduped`` behavior after the
    Queue #259 invariant fix) EVERY member is published, so the returned list sums to
    ~1.0. ``apply_tail_mode_filters=True`` reproduces the OLD pre-fix behavior — the
    extreme-tail (>0.005 AND <0.98) and mode-price cuts run after normalization and
    can drop members, so the sum falls below 1.0. Tests assert the fixed path holds
    the invariant and the old path violates it (the counterexamples).
    """
    cp_sum = sum(raw_cps)
    if cp_sum <= 0:
        return []
    normalized = [cp / cp_sum for cp in raw_cps]
    if not apply_tail_mode_filters:
        # Queue #259 invariant fix: a complete partition is published whole.
        return normalized
    # Legacy (buggy) behavior kept for contrast: drop extreme tails + modal prices.
    from collections import Counter

    counts = Counter(normalized)
    eligible = len(normalized)
    mode_threshold = max(eligible * 0.5, 2)
    mode_prices = {p for p, c in counts.items() if c > mode_threshold}
    return [
        p
        for p in normalized
        if 0.005 < p < 0.98 and p not in mode_prices
    ]


# #762: void-resolution filter (mostly DataGolf "Make the Cut" markets).
#
# A resolved outcome whose resolution_source is did_not_play / withdrew is a
# VOID — the player never teed off, so there was no cut outcome to score. These
# are all graded is_winner=False by the resolver, but counting them as
# "predicted X% and lost" dragged DataGolf's actual rate down across every bin
# (~49% of resolved DataGolf outcomes were did_not_play, inflating MCE to
# ~13.7pp). The main calibration query already drops these from the denominator
# (resolution_source NOT IN (...)); this surfaces the count + rule so the
# exclusion is transparent, never silent — the same contract as the #940
# liquidity_filter. Read-side only; never mutates is_winner (gotcha #21).
VOID_RESOLUTION_SOURCES = ("did_not_play", "withdrew")

VOID_FILTER_RULE_TEXT = (
    "Excludes resolved outcomes for players who never participated "
    "(did_not_play / withdrew) — VOIDs with no real outcome to score, not "
    "losses. Mostly DataGolf 'Make the Cut' markets; never mutates resolutions."
)


def outcome_is_calibration_void(resolution_source: str | None) -> bool:
    """True if an outcome is a VOID excluded from the published calibration set.

    Canonical, unit-tested definition of the #762 rule: an outcome whose
    ``resolution_source`` marks non-participation (did_not_play / withdrew) is a
    void — the underlying event never occurred for that player — so it is dropped
    from the calibration denominator. Read-side only (gotcha #21); the inverse of
    "counts toward calibration" for this dimension.
    """
    return resolution_source in VOID_RESOLUTION_SOURCES


# Queue #158 (#1011): curve-side exclusion of HISTORICAL SOCCER GAME-ODDS captured
# 2-way (draw omitted). The Odds API soccer h2h is 3-way (home/draw/away) but the
# events table has NO draw column, so every soccer game-odds row was stored as a
# 2-way home/away split summing to ~1.0 — structurally omitting the ~25% draw mass.
# That over-predicts home/away systematically (ops-lane census #1010/#1011: EPL
# predicted 0.573 home vs ACTUAL 0.397 = 17.6pp over; Switzerland 15.0pp; Turkey
# 7.6pp; uniform across all ~20 leagues = one mechanism, not model bias). The draw
# was never captured, so these historical rows cannot be reconstructed/re-graded —
# they are excluded from the published curve, league-scoped by the ``soccer_*``
# sport key. The forward fix (3-way capture into a new draw column) is #1011's
# separate schema+ingest step. Read-side only (gotcha #21) — never mutates
# scores or probabilities.
SOCCER_2WAY_EXCLUDE_PATTERN = "soccer_%"

SOCCER_2WAY_RULE_TEXT = (
    "Excludes historical soccer game-odds (moneyline) from the curve — BOTH the "
    "events aggregate (odds_api) and the per-bookmaker (odds_api_bookmaker) sources. "
    "Soccer h2h is 3-way (home/draw/away) but both stored only a 2-way home/away "
    "split summing to ~1.0, dropping the ~25% draw mass and over-predicting "
    "home/away by 7-18pp uniformly across ~20 leagues (#1011). The draw was never "
    "captured so these rows can't be re-graded; league-scoped by the soccer_* key. "
    "Soccer spreads/totals (genuinely 2-way) are kept. Forward fix = 3-way capture. "
    "Read-side only; never mutates resolutions."
)


def category_is_soccer_2way_excluded(category: str | None) -> bool:
    """True if an events-table category (sport key) is an excluded soccer league.

    Canonical, unit-tested definition of the Queue #158 (#1011) rule mirroring the
    ``s.key NOT LIKE 'soccer_%'`` events-curve filter: every soccer league game-odds
    row was captured 2-way (draw dropped at ingest), so it is excluded from the
    published moneyline curve. Read-side only (gotcha #21).
    """
    return bool(category) and category.startswith("soccer_")


# Queue #159 (#1010): esports malformed-MULTI "match bundle" curve exclusion.
#
# Polymarket packs a whole esports match into ONE non-partition market —
# cumulative "Total Kills Over/Under X.5 in Game N" ladders (Over 17.5, 18.5,
# ... 54.5), per-game winners, first-blood props, series totals — flattened into
# a single market with dozens of outcomes (market 128754: 73 outcomes). Because
# the Over rungs are CUMULATIVE, a high-kill game legitimately resolves many YES
# at once (gotcha #17), so the market resolves with >=2 winners. That makes it
# the exact counter-class #157's normalization deliberately REFUSES: the prices
# neither sum to ~1.0 (multiple partitions mashed together — can't be normalized
# by one per-market divisor) nor bucket as a clean single prediction. OPS-557
# census (2026-07-11): n=93,629 poly outcomes, winrate 0.395 vs cp 0.487
# (+9.2pp), avg per-market cp-sum 17.9; sub-bands <25%-win +23.7pp (longshot Over
# rungs that missed) / 25-50% +10.1pp / >50% -4.1pp (near-certain Over rungs that
# hit). The >=2-winner grading is CORRECT for cumulative ladders, so these rows
# are EXCLUDED from the curve, never re-graded — the >=3-outcome sibling of the
# malformed-binary filter. Read-side only (gotcha #21). esports-scoped: the same
# poly bundle shape is well-calibrated in basketball/tennis/hockey (~+1.5pp), so
# a blanket exclusion would drop good data; the general sweep is #160's sentinel.
ESPORTS_MULTI_BUNDLE_CATEGORY = "esports"

ESPORTS_MULTI_BUNDLE_RULE_TEXT = (
    "Excludes esports 'match bundle' markets — Polymarket packs a whole match "
    "(cumulative Total-Kills Over/Under ladders per game, per-game winners, "
    "first-blood props) into one non-partition market with >=3 outcomes that "
    "resolves with >=2 winners. Because the Over rungs are cumulative, many "
    "resolve YES at once (gotcha #17), so the prices neither sum to ~1.0 (can't "
    "be normalized — multiple partitions mashed) nor bucket as a clean prediction "
    "(OPS-557 census: 93,629 outcomes, winrate 0.395 vs cp 0.487 = +9.2pp, avg "
    "per-market cp-sum 17.9). The >=3-outcome sibling of the malformed-binary "
    "filter and the exclusion complement of #157's counter-class guard. The "
    "many-YES ladder grading is correct, so these are excluded from the curve, "
    "never re-graded. Read-side only; never mutates resolutions."
)


def market_is_esports_multi_bundle(
    category: str | None, n_outcomes: int, n_winners: int
) -> bool:
    """True if a resolved market is an esports match-bundle excluded from the curve (Queue #159).

    Canonical, unit-tested definition mirroring the ``esports_multi_bundles`` CTE:
    an esports market with >=3 outcomes that resolved with >=2 winners is a
    Polymarket match bundle (cumulative Total-Kills Over ladders + per-game
    winners + props mashed into one non-partition market; gotcha #17/#23). The
    >=2-winner test is the discriminator — a genuine single-winner partition
    resolves with EXACTLY one winner — the same signal #157's counter-class guard
    uses to REFUSE normalization, here used to EXCLUDE from the published curve.
    Outcome/winner counts are over ALL outcomes of the market, mirroring the
    malformed_binaries CTE. Read-side only (gotcha #21) — never mutates is_winner;
    the many-YES cumulative-ladder grading is correct, so the rows are dropped
    from the curve rather than re-graded.
    """
    return (
        category == ESPORTS_MULTI_BUNDLE_CATEGORY
        and n_outcomes >= 3
        and n_winners >= 2
    )


# Queue #186 (#941, corrects #167): Kalshi player-prop threshold curve exclusion.
#
# Kalshi player-prop markets are single-sided "Player: N+" OVER outcomes (points,
# assists, goals, total bases, hits, HR, strikeouts, rebounds, blocks, ...). A
# large slice of their captured calibration_probability is corrupt: these markets
# are polled near/after game time (Kalshi commence_time ≈ resolution time,
# gotcha #14), so a settled post-game quote (yes_ask≈1.00) gets stamped as the
# "closing line" — e.g. "6+ total bases" at 0.96, physically impossible as a real
# OVER. It is the settlement artifact, not a prediction.
#
# Queue #167 (2026-07-12) tried to keep the "real-bid" rows, believing only the
# no-live-bid rows were poison. The Queue #186 forensic verify (2026-07-13,
# snapshot-level trace over the exact series the Calibration Sentinel flagged in
# #1069–#1073) DISPROVED that: real-bid rows are corrupt too. In one market a
# scorer and a non-scorer BOTH carry cp 0.995 with a live 0.99 bid (Kapanen 1+ did
# not score / Caufield 1+ did — same stamped closing line). The live bid is a
# stale settlement quote, not price discovery. The honest discriminator is the
# CURVE PRICE, not the bid.
#
# The corrected diagnosis has two distinct sub-populations (verified by an
# opening-decile trace, prod 2026-07-13):
#   * DEGENERATE SETTLEMENT-COLLAPSE BAND (curve price >= 0.90): corrupt for EVERY
#       series — it resolves 0.11–0.48, never near 0.90 (NBA 0.983→0.445, NHL
#       0.979→0.117). Excluded. Below the band the liquid series are an honest
#       diagonal (NBAPTS 0.647→0.600, 0.749→0.734; MLBTB 0.639→0.791) and are
#       KEPT ("SAVE all possible", gotcha #21) — excluding only the band brings
#       their high-band actual within ~10pp of predicted (NBAPTS -2pp, MLBKS -2pp).
#   * NHL GOAL-FAMILY (llm_sport_category='hockey', KXNHLGOAL/PTS/AST): corrupt at
#       EVERY band (opening 0.69→0.21, 0.82→0.05) while its RESOLUTION is verified
#       SANE (5.24 scorers credited/game, min 1 max 25, 0 zero-scorer games; api
#       and box_score agree at ~0.09 winrate). So this is an illiquid degenerate
#       CAPTURE, not a resolution bug and NOT a sign-flip (low prices resolve low,
#       honestly — there is no side to flip). No honest price to recover → the
#       whole class is dropped.
#
# No regrade (the sign-flip premise from the Sentinel writeup is disproven; gotcha
# #21). Read-side only; never mutates is_winner or probabilities. Consistent with
# the writer-side guard in backfill_winners._compute_calibration_prices that
# refuses to stamp a no-bid snapshot as the closing line for these props.
#
# POSIX form for the SQL ``~`` operator ([+] is a literal plus in a bracket
# expression so no backslash escaping is needed inside the f-string).
KALSHI_PROP_THRESHOLD_NAME_RE = r"^.+:[[:space:]]*[0-9]+[+][[:space:]]*$"

# Python mirror of the SQL regex for the unit-tested helper.
_KALSHI_PROP_THRESHOLD_RE = re.compile(r"^.+:\s*\d+\+\s*$")

# Queue #186 (#941) DEGENERATE SETTLEMENT-COLLAPSE BAND. The corrected verify
# pass (2026-07-13, forensic snapshot trace) proved the #167 "keep the real-bid
# rows" discriminator was itself an artifact: real-bid rows are corrupt too. Per
# outcome, both a scorer and a non-scorer in the same market get the same
# post-settlement quote stamped as the closing line (e.g. Kapanen 1+ ybid 0.99
# cp 0.995 DID NOT score, next to Caufield 1+ ybid 0.99 cp 0.995 who DID). The
# honest discriminator is the CURVE PRICE, not the bid: an opening-decile trace
# shows opening_probability is a clean diagonal through decile 8 for the liquid
# series (NBA points/reb/ast/3pt, MLB TB/HIT/HR/KS: e.g. NBAPTS 0.647→0.600,
# 0.749→0.734) and ONLY the >=0.90 band is degenerate (0.983→0.445 for NBA,
# 0.979→0.117 for NHL — it never resolves anywhere near 0.90 for ANY series).
# Excluding that band brings every liquid series' high-band (0.6–0.9) actual to
# within ~10pp of predicted (NBAPTS -2pp, NBAAST -4pp, MLBKS -2pp, MLBHIT -6pp).
KALSHI_PROP_THRESHOLD_DEGENERATE_BAND = 0.90

# Queue #194 Item 3 (#1089) — NHL GOAL-FAMILY HONEST-BAND RECOVERY. The #941
# "corrupt at EVERY band" premise was an overstatement (it only sampled the high
# deciles). A fresh forensic (prod 2026-07-14, curve-price calibration of all
# resolved KXNHLGOAL/PTS/AST, n=26,436) shows the goal-family is corrupt only in
# the HIGH band and WELL-CALIBRATED in the low band — so the wholesale hockey drop
# needlessly discarded ~16.7K honest rows. Curve-price bands (pred → actual):
#     <0.30      n=13,285   0.127 → 0.096   gap  3.1pp   HONEST
#     0.30–0.40  n= 2,000   0.345 → 0.323   gap  2.2pp   HONEST
#     0.40–0.50  n= 1,411   0.445 → 0.405   gap  4.0pp   HONEST
#     0.50–0.70  n= 3,745   0.637 → 0.311   gap 32.6pp   DEGENERATE
#     0.70–0.90  n= 1,916   0.795 → 0.189   gap 60.6pp   DEGENERATE
#     >=0.90     n= 4,079   0.975 → 0.182   gap 79.3pp   DEGENERATE
# Calibration breaks hard at 0.50 (gap jumps 4pp → 33pp), so the honest cutoff is
# 0.50: RECOVER (include) hockey goal-family rows below 0.50 — 16,696 well-
# calibrated outcomes — and EXCLUDE the 9,740 at/above it permanently (the
# earliest snapshot is also degenerate there — an illiquid one-sided-ask capture,
# gotcha #14 — so there is genuinely no honest price to recover for that split;
# the issue's "re-stamp from the first snapshot" premise is disproven). Read-side
# only (gotcha #21) — never mutates is_winner or probabilities.
KALSHI_HOCKEY_HONEST_BAND_MAX = 0.50

KALSHI_PROP_THRESHOLD_RULE_TEXT = (
    "Excludes the corrupt slice of Kalshi player-prop threshold outcomes "
    "(single-sided 'Player: N+' OVER markets — points/assists/goals/total-bases/"
    "hits/HR/strikeouts/rebounds/blocks). Two exclusions: (A) the NHL goal-family "
    "(llm_sport_category='hockey') at/above 0.50, whose prices are degenerate in "
    "the high band (0.50–0.70 winrate 0.31, >=0.90 winrate 0.18) — an illiquid "
    "capture (gotcha #14), not a sign-flip or resolution bug — while its honest "
    "low band (<0.50, ~3pp calibrated) is RECOVERED (Queue #194/#1089, correcting "
    "#941's over-broad wholesale drop); and (B) any row whose curve price "
    "(closing line, else opening) sits in the degenerate settlement-collapse band "
    "(>= 0.90), which resolves 0.11–0.48 across every series — the settled "
    "post-game quote stamped as the line ('6+ total bases' at 0.96, physically "
    "impossible as a real OVER). Below that band the liquid series (NBA points/reb/"
    "ast/3pt, MLB TB/HIT/HR/KS) are an honest diagonal and are KEPT, bringing their "
    "high-band actual within ~10pp of predicted. Queue #186 (2026-07-13) corrects "
    "#167: its no-live-bid discriminator was itself an artifact — real-bid rows are "
    "corrupt too (a scorer and a non-scorer in one market both carry cp 0.995 with "
    "ybid 0.99), so the curve price, not the bid, is the honest discriminator. No "
    "regrade: the sign-flip premise is disproven (low prices resolve low, honestly) "
    "and there is no honest price to recover for the excluded rows (gotcha #21). "
    "Read-side only; never mutates resolutions or probabilities."
)


def kalshi_prop_threshold_exclude_sql(
    *,
    source: str,
    name: str,
    category: str,
    calibration_probability: str,
    opening_probability: str,
    curve_price: str | None = None,
) -> str:
    """Canonical SQL boolean for the Queue #186/#941 Kalshi prop-threshold exclusion.

    Single source of truth mirrored by ``outcome_is_kalshi_prop_threshold`` (the
    Python helper). Renders the exact ``is_kalshi_prop_threshold`` predicate used
    by the calibration curve so every SQL read-path honours the same rule and
    cannot silently diverge — the calibration precompute task, the
    ``/api/calibration`` cold-cache fallback serve, AND the source-intelligence
    fair-fight MCE (Queue #188 Item 3: ``source_intelligence.py`` was reading the
    corrupt NHL cal prices raw, unguarded). Callers pass the column expressions for
    their own table aliases; the regex and degenerate band come from the module
    constants so a hand-typed literal can never drift out of sync (the route used
    to hardcode ``0.90``).

    Excluded when source='kalshi', ``name`` matches the 'Player: N+' OVER pattern,
    and EITHER category='hockey' OR the price sits in the degenerate band.

    Queue #263 Item 1 (horizon-honest band classification): the band decision is a
    PRICE-STATE decision, so it must read the same price expression the surface is
    finalized on. ``curve_price`` overrides the price expression used for BOTH the
    hockey (>= 0.50) and general (>= 0.90) band comparisons; the headline path
    leaves it None and falls back to ``COALESCE(cp, opening)`` (identical to the
    old literal), while a horizon passes its snapshot price so each horizon
    classifies a threshold outcome on ITS OWN price, not the terminal probability.
    The hockey vs general split is preserved mechanically — only the price the two
    bands read changes. Read-side only (gotcha #21) — never mutates resolutions.
    """
    price_expr = (
        curve_price
        if curve_price is not None
        else f"COALESCE({calibration_probability}, {opening_probability})"
    )
    return (
        f"({source} = 'kalshi'\n"
        f"     AND {name} ~ '{KALSHI_PROP_THRESHOLD_NAME_RE}'\n"
        f"     AND (({category} = 'hockey'\n"
        f"            AND {price_expr}\n"
        f"                >= {KALSHI_HOCKEY_HONEST_BAND_MAX})\n"
        f"          OR {price_expr}\n"
        f"             >= {KALSHI_PROP_THRESHOLD_DEGENERATE_BAND}))"
    )

# Queue #183 Item 4 (#182 historical twin): curve-side exclusion of WEATHER
# WIDE-SPREAD FABRICATED MIDPOINTS. #182 proved a WIDE Kalshi book
# (yes_ask - yes_bid >= 0.50) with no trade has NO real price discovery at its
# midpoint — the captured cal_prob is a fabricated number, not a market line. #182
# fixed this FORWARD (_kalshi_yes_probability now skips wide/one-sided no-trade
# books, _KALSHI_TIGHT_SPREAD_MAX = 0.50); this is the read-side HISTORICAL twin
# for the rows captured before that guard shipped. WEATHER-GATED ONLY: #182's
# census confirmed weather's ~65 wide-spread rows are the disease, while tech's
# miscalibration is genuine (NOT wide-book noise, ~10pp is real), so tech is
# deliberately left in (its census is parked — do NOT extend this to tech). These
# rows carry a live bid (bid > 0), so the #940 liquidity filter KEEPS them — the
# SPREAD is the discriminator the liquidity filter misses. Read-side only (gotcha
# #21) — never mutates is_winner / calibration_probability.
WEATHER_WIDE_SPREAD_MIN = 0.50  # mirrors kalshi.py _KALSHI_TIGHT_SPREAD_MAX

WEATHER_WIDE_SPREAD_EXCLUDE = (
    "(vm.source = 'kalshi'\n"
    "     AND cv.category = 'weather'\n"
    "     AND fo.current_yes_bid IS NOT NULL AND fo.current_yes_ask IS NOT NULL\n"
    f"     AND (fo.current_yes_ask - fo.current_yes_bid) >= {WEATHER_WIDE_SPREAD_MIN}\n"
    "     AND NOT EXISTS (\n"
    "        SELECT 1 FROM futures_odds_snapshots fos\n"
    "        WHERE fos.outcome_id = fo.id AND fos.last_price > 0))"
)

WEATHER_WIDE_SPREAD_RULE_TEXT = (
    "Excludes Kalshi WEATHER outcomes whose captured price is a fabricated wide-book "
    "midpoint: a book with yes_ask - yes_bid >= 0.50 and NO trade in any snapshot has "
    "no real price discovery at its midpoint (#182). These rows carry a live bid so "
    "the #940 liquidity filter keeps them — the wide spread is the discriminator. "
    "WEATHER ONLY: #182's census showed tech's miscalibration is genuine, not "
    "wide-book noise, so tech is left in. Read-side only; never mutates resolutions."
)


def outcome_is_weather_wide_spread(
    source: str | None,
    category: str | None,
    current_yes_bid: float | None,
    current_yes_ask: float | None,
    ever_last_price: float | None = None,
) -> bool:
    """True if a Kalshi WEATHER outcome is a fabricated wide-book midpoint (Queue #183 Item 4).

    Canonical, unit-tested definition mirroring the ``WEATHER_WIDE_SPREAD_EXCLUDE``
    SQL flag. Excluded only when ALL hold:
      1. source == 'kalshi' AND category == 'weather' (weather-gated — tech's
         miscalibration is genuine per #182's census and is NOT excluded here)
      2. a two-sided book is present with a WIDE spread
         (yes_ask - yes_bid >= WEATHER_WIDE_SPREAD_MIN, i.e. 0.50)
      3. no trade evidence (``ever_last_price`` is None or 0) — a wide book that
         actually traded has real evidence and is KEPT (#182 uses last_price then)

    Read-side only (gotcha #21) — never mutates resolutions.
    """
    if source != "kalshi" or category != "weather":
        return False
    if current_yes_bid is None or current_yes_ask is None:
        return False
    # Bid/ask live in Numeric(5,4) columns, so Postgres computes the spread in
    # EXACT decimal arithmetic. Round to 4 dp here so the Python mirror agrees
    # with the SQL flag at the 0.50 boundary (binary float would make e.g.
    # 0.70 - 0.20 = 0.4999… and silently disagree with the DB).
    spread = round(float(current_yes_ask) - float(current_yes_bid), 4)
    if spread < WEATHER_WIDE_SPREAD_MIN:
        return False
    return (ever_last_price or 0) <= 0


def outcome_is_kalshi_prop_threshold(
    source: str | None,
    name: str | None,
    curve_price: float | None = None,
    category: str | None = None,
) -> bool:
    """True if a Kalshi player-prop threshold outcome is EXCLUDED from the curve (Queue #186/#941).

    Canonical, unit-tested definition mirroring the ``is_kalshi_prop_threshold``
    flag in the main outcome scan. A row is a "<subject>: N+" OVER threshold when
    source == 'kalshi' and the name matches the single-sided threshold pattern
    (points/assists/goals/total-bases/hits/HR/strikeouts/rebounds/... player
    props). Such a row is EXCLUDED when EITHER:

      A. ``category == 'hockey'`` AND ``curve_price`` >= 0.50 — the NHL goal-family
         (KXNHLGOAL/PTS/AST) is degenerate ONLY in the high band. Queue #194 (#1089)
         forensic (n=26,436) showed it is well-calibrated below 0.50 (<0.30 gap
         3.1pp, 0.30–0.40 2.2pp, 0.40–0.50 4.0pp) and breaks hard at/above it
         (0.50–0.70 gap 32.6pp, >=0.90 79.3pp). So the honest low band is RECOVERED
         (kept) and only the degenerate >=0.50 split is dropped (its earliest
         snapshot is also degenerate — an illiquid one-sided-ask capture, gotcha
         #14 — no honest price to recover). This corrects #941's over-broad
         wholesale hockey drop.
      B. ``curve_price`` (= COALESCE(calibration_probability, opening_probability))
         is in the DEGENERATE SETTLEMENT-COLLAPSE BAND (>= 0.90). Across every
         series this band resolves at 0.11–0.48, never near 0.90 — it is the
         settled post-game quote stamped as the closing line, not a prediction.
         Below the band the liquid series (NBA/MLB) are an honest diagonal and
         are KEPT ("SAVE all possible", gotcha #21).

    NOTE (Queue #186 correction): the earlier #167 discriminator keyed on live YES
    bid (keep rows with ``current_yes_bid`` > 0). The 2026-07-13 forensic verify
    disproved it — real-bid rows are corrupted too (a scorer and a non-scorer in
    the same market both carry cp 0.995 with ybid 0.99). The curve price, not the
    bid, is the honest discriminator. Read-side only — never mutates is_winner /
    calibration_probability (no regrade; the sign-flip premise is disproven).
    """
    if source != "kalshi" or not name:
        return False
    if not _KALSHI_PROP_THRESHOLD_RE.match(name):
        return False
    if curve_price is None:
        # Unknown price → conservatively excluded (the SQL path always has a
        # curve price via COALESCE, so this only affects defensive callers).
        return True
    if category == "hockey":
        # #1089 recovery: the goal-family is honest below 0.50 and degenerate
        # at/above it — exclude only the degenerate high band, recover the rest.
        return curve_price >= KALSHI_HOCKEY_HONEST_BAND_MAX
    return curve_price >= KALSHI_PROP_THRESHOLD_DEGENERATE_BAND


def outcome_is_calibration_liquid(
    ever_yes_bid: float | None, ever_last_price: float | None
) -> bool:
    """True if an outcome qualifies for the published calibration set.

    Canonical definition of the #940 phase-1 rule, mirroring
    ``KALSHI_LIQUIDITY_EXISTS``: an outcome is liquid (included) iff some
    snapshot ever showed a real bid (``yes_bid > 0``) OR a trade
    (``last_price > 0``). Never-bid AND never-traded -> excluded. Read-side
    only (gotcha #21). ``ever_yes_bid`` / ``ever_last_price`` are the max
    bid / max last_price observed across an outcome's snapshots (NULL if none).
    """
    return (ever_yes_bid or 0) > 0 or (ever_last_price or 0) > 0


def binary_is_malformed(n_outcomes: int, n_winners: int) -> bool:
    """True if a 2-outcome mutually-exclusive market is malformed (L2-79 Item 1).

    Canonical, unit-tested definition mirroring the ``malformed_binaries`` CTE: a
    resolved binary must have exactly one winner. Zero winners (void/malformed) or
    two winners (impossible / double-graded) is a data artifact excluded from the
    published curve. Only applies to 2-outcome markets; anything else is not a
    binary and returns False. Read-side only (gotcha #21).
    """
    return n_outcomes == 2 and n_winners != 1


def outcome_in_golf_high_band(cp: float | None) -> bool:
    """True if a golf outcome's price sits in the placeholder high band (L2-79 Item 2).

    The band-membership half of the ``golf_placeholder_markets`` rule: an outcome
    priced at/above GOLF_PLACEHOLDER_HIGH_BAND is a candidate one-sided-ask
    placeholder. The full exclusion additionally requires the market to be
    over-subscribed (>=2 outcomes in this band) — that market-level check lives in
    the SQL CTE. Read-side only (gotcha #21).
    """
    return cp is not None and cp >= GOLF_PLACEHOLDER_HIGH_BAND


def _wilson_ci(wins: int, total: int, z: float = 1.96) -> tuple[float, float]:
    if total == 0:
        return (0.0, 0.0)
    p = wins / total
    denom = 1 + z**2 / total
    center = (p + z**2 / (2 * total)) / denom
    spread = z * math.sqrt((p * (1 - p) + z**2 / (4 * total)) / total) / denom
    return (max(0.0, center - spread), min(1.0, center + spread))


def _bootstrap_mce_ci(
    bucket_list: list[dict],
    n_boot: int = 1000,
    seed: int = 42,
) -> tuple[float, float]:
    if not bucket_list:
        return (0.0, 0.0)
    rng = random.Random(seed)
    k = len(bucket_list)
    mce_samples: list[float] = []
    for _ in range(n_boot):
        sample = rng.choices(bucket_list, k=k)
        # n-weighted to match the #137 weighted point estimate.
        total_abs_err = 0.0
        total_w = 0.0
        for b in sample:
            actual = b["winners"] / b["n"] if b["n"] else 0.0
            w = b["n"]
            total_abs_err += abs(actual - b["avg_prob"]) * w
            total_w += w
        mce_samples.append(total_abs_err / total_w if total_w else 0.0)
    mce_samples.sort()
    lo = mce_samples[int(n_boot * 0.025)]
    hi = mce_samples[int(n_boot * 0.975)]
    return (lo, hi)


def _compute_horizon_mce(buckets: list[dict], weighted: bool = True) -> float | None:
    """Mean per-bucket calibration error, in percentage points.

    #137 Item 3: `weighted=True` (the default) weights each probability bucket's
    |actual - predicted| by the bucket's sample size (n). The old equal-weighted
    mean (weighted=False) let a tail bucket of n=2-13 dominate a category whose
    bulk (n=1000s) was well-calibrated — the r108 "mlb spreads 16.4pp" artifact
    class. n-weighting makes the number reflect the outcomes users actually see.
    Pass weighted=False to reproduce the legacy number (kept as `mce_unweighted`
    during the transition for comparison).
    """
    if not buckets:
        return None
    total_abs_err = 0.0
    total_w = 0.0
    for b in buckets:
        if b["n"] == 0:
            continue
        avg_prob = b["sum_prob"] / b["n"]
        actual = b["winners"] / b["n"]
        w = b["n"] if weighted else 1
        total_abs_err += abs(actual - avg_prob) * w
        total_w += w
    if total_w == 0:
        return None
    return round(total_abs_err / total_w * 100, 2)


def _calibration_population_ctes(
    *,
    curve_price: str = "COALESCE(fo.calibration_probability, fo.opening_probability)",
    curve_price_join: str = "",
    rn_order: str = "ABS(fo.opening_probability - 0.5)",
    market_info_extra: str = "",
    leading_ctes: str = "",
) -> str:
    """The ONE canonical eligible -> final-published-row CTE chain (Queue #259 Item 1/2).

    Queue #262 Item 1: the finalizer is PARAMETERIZED by the "curve price" so the
    time-horizon surface can reuse the SAME resolved-question identity, independent-
    truth allowlist, and artifact exclusions while finalizing on a horizon snapshot
    instead of the terminal price. The defaults reproduce the headline population
    semantically (curve_price = terminal ``calibration_probability`` fallback,
    no extra joins), so the serve/cohort-sweep row parity (#259) and partition-sum
    invariant are preserved; existing tests pin that behavior.

      * ``curve_price``      — SQL expression for the bucketed/normalized price.
                               Headline: terminal cp. Horizon: the snapshot value.
      * ``curve_price_join`` — extra INNER JOIN injected into the price-bearing CTEs
                               (``ranked_outcomes`` + ``mex_field_divisor``); for a
                               horizon this joins ``horizon_price`` so ONLY outcomes
                               with a snapshot at the horizon cutoff survive.
      * ``rn_order``         — representative-side ORDER BY for the single-market
                               binary branch (headline: opening; horizon: snapshot).
      * ``market_info_extra``— extra WHERE on ``market_info`` (horizon scopes to
                               non-event, resolution-date-bearing markets so the
                               whole chain runs on the small horizon universe).
      * ``leading_ctes``     — CTE(s) prepended to the WITH-body (the horizon-price
                               LATERAL lookup), WITH a trailing comma.

    NORMALIZATION / FIELD-COMPLETENESS ARE HORIZON-HONEST (Queue #262 + #263 Item 1):
    ROSTER IDENTITY is structural — a market is a partition field regardless of the
    horizon, so ``mex_field_candidates`` detects it on the TERMINAL structure (mex/
    field, single winner, >=3 eligible) and carries the full terminal-eligible member
    count. EVERY PRICE-STATE decision is evaluated on the price expression: the
    normalization divisor (``mex_field_divisor`` sum over ``{curve_price}``), the
    field-sum > threshold qualification (moved out of candidate detection into the
    ``normalized`` gate, keyed on ``mnm_cp_sum``), and the Kalshi prop-threshold band
    (``{curve_price}`` passed to ``kalshi_prop_threshold_exclude_sql``). A field is
    published only when EVERY terminal-eligible member is present at the horizon AND
    survives every exclusion (survivor_n == terminal_eligible_n) AND its price-sum
    clears the threshold, else it is dropped WHOLE. On the headline path present ==
    terminal and ``{curve_price}`` == terminal cp, so this reduces to the old single
    ``mex_norm_markets`` behavior exactly.

    Returns the WITH-body (``market_info`` ... ``deduped``, WITHOUT the leading
    ``WITH`` and WITHOUT a trailing comma) that BOTH serve/audit consumers build
    on, so their populations cannot silently drift (the C14 finding: the cohort
    sweep measured rows the curve drops because it re-implemented the population):

      * ``compute_calibration_payload`` appends ``liq_summary`` / ``published_summary``
        / ``bucketed`` and aggregates ``deduped`` into curve buckets, and
      * ``scripts/evals/cohort_sweep.load_from_session`` selects the ``deduped``
        rows verbatim (same outcome ids, probabilities, question ids, source).

    ``deduped`` IS the final published population: eligible -> per-outcome
    exclusions -> field-completeness normalization -> mode/tail dedup -> rn=1
    binary side. Queue #259 Item 1 fix: a COMPLETE normalized field
    (``is_mex_normalized``) is EXEMPT from the mode-price and extreme-tail
    (``>0.005 AND <0.98``) filters — those are placeholder heuristics for the
    NON-partition multi pool, and applying them after normalization would drop a
    member (a tiny normalized tail, or a uniform field's modal price) and break
    the sum-to-1 invariant the completeness gate guarantees. Read-side only
    (gotcha #21) — never mutates is_winner / calibration_probability.

    Carries every column both consumers need (``outcome_id`` / ``outcome_name`` /
    ``market_type`` / ``llm_league`` for the sweep's cohort keys; ``vm_id`` is the
    production virtual-question identity WITH the source + >=3 group/event size
    gate, so the sweep can no longer collapse unrelated same-event props or split
    a two-market group).
    """
    return f"""{leading_ctes}market_info AS (
                SELECT fm.id AS market_id, fm.source, fm.event_id, fm.group_id,
                    fm.commence_time,
                    COALESCE(fm.llm_sport_category, 'uncategorized') AS category,
                    fm.mutually_exclusive,
                    fm.market_type,
                    fm.llm_league
                FROM futures_markets fm
                WHERE fm.status = 'resolved'
                  {market_info_extra}
                  -- #994 symmetric exclusion: DataGolf markets whose full field
                  -- the historical API genuinely can't return (event not found)
                  -- are dropped ENTIRELY — winners AND losers — so participation
                  -- can never be one-sidedly assumed. Recovery flags these; the
                  -- residual is expected to be ~0 (golf history never ages out).
                  AND NOT COALESCE(
                      (fm.market_metadata->>'datagolf_recovery_residual')::boolean,
                      false)
            ),
            -- L2-79 Item 1: malformed 2-outcome mex binaries (winner count != 1).
            -- Counts ALL outcomes of the market to determine the binary shape and
            -- true winner count (not the eligibility-filtered subset).
            malformed_binaries AS (
                SELECT fo.market_id,
                    COUNT(*) FILTER (WHERE fo.is_winner = true) AS win_count
                FROM futures_outcomes fo
                JOIN market_info mi ON mi.market_id = fo.market_id
                WHERE mi.mutually_exclusive = true
                GROUP BY fo.market_id
                HAVING COUNT(*) = 2
                   AND COUNT(*) FILTER (WHERE fo.is_winner = true) <> 1
            ),
            -- Queue #159 (#1010): esports malformed-MULTI "match bundle" markets —
            -- the >=3-outcome sibling of malformed_binaries and the exclusion-side
            -- complement of #157's counter-class guard. Polymarket flattens a whole
            -- match (cumulative Total-Kills Over ladders per game, per-game winners,
            -- first-blood props) into one non-partition market; because the Over
            -- rungs are cumulative, a high-kill game legitimately resolves many YES
            -- (gotcha #17), so the market has >=2 winners and its prices neither
            -- sum to 1 (multiple partitions mashed — can't be normalized) nor
            -- bucket as a clean prediction (OPS-557: n=93,629, winrate 0.395 vs cp
            -- 0.487 = +9.2pp, avg per-market cp-sum 17.9). Counts ALL outcomes,
            -- mirroring malformed_binaries. Read-side only (gotcha #21) — the
            -- many-YES ladder grading is CORRECT, so exclude, never re-grade.
            esports_multi_bundles AS (
                SELECT fo.market_id
                FROM futures_outcomes fo
                JOIN market_info mi ON mi.market_id = fo.market_id
                WHERE mi.category = 'esports'
                GROUP BY fo.market_id
                HAVING COUNT(*) >= 3
                   AND COUNT(*) FILTER (WHERE fo.is_winner = true) >= 2
            ),
            -- L2-79 Item 2: golf FIELD/winner one-sided-ask placeholder markets —
            -- mutually-exclusive golf markets with >=2 outcomes in the >=0.80 band
            -- (structurally impossible for genuine mex probabilities). Same
            -- eligibility predicate as the main outcome scan so the band count
            -- reflects the published population.
            golf_placeholder_markets AS (
                SELECT fo.market_id
                FROM futures_outcomes fo
                JOIN market_info mi ON mi.market_id = fo.market_id
                WHERE mi.category = 'golf'
                  AND mi.mutually_exclusive = true
                  AND mi.event_id IS NULL
                  AND COALESCE(fo.calibration_probability, fo.opening_probability) >= {GOLF_PLACEHOLDER_HIGH_BAND}
                  AND fo.opening_probability IS NOT NULL
                  AND fo.opening_probability > 0 AND fo.opening_probability < 1
                  -- Queue #261 Item 1: calibration-truth eligibility (allowlist).
                  -- Only sources whose winner is established INDEPENDENTLY of the
                  -- market's own price may grade a published forecast; guess,
                  -- structural-void, price-derived (clean_resolution /
                  -- settlement_sync) and unknown sources fail closed. Single
                  -- source of truth = resolution_authority.
                  AND fo.resolution_source IN {CALIBRATION_TRUTH_ELIGIBLE_SOURCES_SQL}
                  AND COALESCE(fo.volume, -1) != 0
                GROUP BY fo.market_id
                HAVING COUNT(*) >= 2
            ),
            -- Queue #157 (#1012): multi-candidate normalization support.
            -- mex_win_counts: winner count over ALL outcomes of each mex market
            -- (the structure test — genuine partitions have exactly 1 winner;
            -- multi-winner = ladder/independent, zero-winner = void).
            -- #254: also trust market_type='field' (the shape classifier's
            -- ">2 outcomes, one winner" signal) — 65K field markets have the
            -- mutually_exclusive flag UNSET and were escaping this gate raw
            -- (sum ~4.56). The win_count=1 / >=3 / sum>1.15 guards below keep a
            -- mis-shaped or multi-winner field from being normalized anyway.
            mex_win_counts AS (
                SELECT fo.market_id,
                    COUNT(*) FILTER (WHERE fo.is_winner = true) AS win_count
                FROM futures_outcomes fo
                JOIN market_info mi ON mi.market_id = fo.market_id
                WHERE (mi.mutually_exclusive = true OR mi.market_type = 'field')
                GROUP BY fo.market_id
            ),
            -- Queue #262 Item 1: split the old single mex_norm_markets into a
            -- structural CANDIDATE detection (terminal price) + a price-expression
            -- DIVISOR, so a horizon can normalize on its snapshot yet still measure
            -- completeness against the FULL terminal field.
            --
            -- mex_field_candidates: markets that are genuine partition FIELDS — a
            -- STRUCTURAL roster identity independent of the horizon (mex/field,
            -- exactly one winner, >=3 terminal-eligible outcomes). Carries the full
            -- terminal-eligible member count so horizon completeness can require
            -- every member to be present.
            --
            -- Queue #263 Item 1: the cp-SUM > threshold gate is a PRICE-STATE
            -- decision, not a roster identity, so it MUST be evaluated on the price
            -- expression the surface finalizes on — NOT the terminal probability.
            -- It moved out of candidate detection and into ``normalized`` below,
            -- gated on ``mnm_cp_sum`` (the mex_field_divisor sum over {curve_price}).
            -- This makes field qualification horizon-honest: a terminal-low/horizon-
            -- high field qualifies at the horizon, a terminal-high/horizon-low field
            -- does not. On the headline path {curve_price} == terminal cp, so
            -- mnm_cp_sum == the old terminal SUM and the qualified set + count equal
            -- the old mex_norm_markets membership + COUNT exactly.
            mex_field_candidates AS (
                SELECT fo.market_id,
                    COUNT(*) AS terminal_eligible_n
                FROM futures_outcomes fo
                JOIN market_info mi ON mi.market_id = fo.market_id
                JOIN mex_win_counts mwc ON mwc.market_id = fo.market_id
                WHERE (mi.mutually_exclusive = true OR mi.market_type = 'field')
                  AND mwc.win_count = 1
                  AND fo.opening_probability IS NOT NULL
                  AND fo.opening_probability > 0 AND fo.opening_probability < 1
                  -- Queue #261 Item 1: calibration-truth eligibility (allowlist),
                  -- identical to the ranked_outcomes / golf-placeholder scans so
                  -- candidate detection matches the published population.
                  AND fo.resolution_source IN {CALIBRATION_TRUTH_ELIGIBLE_SOURCES_SQL}
                  AND COALESCE(fo.volume, -1) != 0
                GROUP BY fo.market_id
                HAVING COUNT(*) >= 3
            ),
            -- mex_field_divisor: per-market normalization divisor = sum of the
            -- CURVE PRICE over the eligible members PRESENT at this price
            -- expression (all terminal members on the headline; only members with
            -- a horizon snapshot when curve_price_join joins horizon_price). On the
            -- headline path cp_sum equals the old mex_norm_markets cp_sum exactly.
            mex_field_divisor AS (
                SELECT fo.market_id,
                    SUM({curve_price}) AS cp_sum,
                    COUNT(*) AS present_eligible_n
                FROM futures_outcomes fo
                JOIN mex_field_candidates mfc ON mfc.market_id = fo.market_id
                {curve_price_join}
                WHERE fo.opening_probability IS NOT NULL
                  AND fo.opening_probability > 0 AND fo.opening_probability < 1
                  AND fo.resolution_source IN {CALIBRATION_TRUTH_ELIGIBLE_SOURCES_SQL}
                  AND COALESCE(fo.volume, -1) != 0
                GROUP BY fo.market_id
            ),
            group_sizes AS (
                SELECT group_id, source, COUNT(*) AS group_size
                FROM market_info
                WHERE group_id IS NOT NULL
                GROUP BY group_id, source
            ),
            event_sizes AS (
                SELECT event_id, source, COUNT(*) AS event_size
                FROM market_info
                WHERE event_id IS NOT NULL
                GROUP BY event_id, source
            ),
            virtual_market AS (
                SELECT
                    mi.market_id, mi.source, mi.category, mi.event_id,
                    CASE WHEN gs.group_size >= 3
                         THEN 'g:' || mi.group_id
                         WHEN es.event_size >= 3
                         THEN 'e:' || mi.event_id::text
                         ELSE 'm:' || mi.market_id::text
                    END AS vm_id,
                    COALESCE(gs.group_size >= 3, false)
                      OR COALESCE(es.event_size >= 3, false) AS is_grouped,
                    mi.mutually_exclusive,
                    mi.market_type,
                    mi.llm_league
                FROM market_info mi
                LEFT JOIN group_sizes gs
                  ON gs.group_id = mi.group_id AND gs.source = mi.source
                LEFT JOIN event_sizes es
                  ON es.event_id = mi.event_id AND es.source = mi.source
            ),
            vm_stats AS (
                SELECT
                    vm.vm_id, vm.source, vm.category, vm.is_grouped,
                    vm.mutually_exclusive,
                    COUNT(DISTINCT vm.market_id) AS market_count,
                    COUNT(*) AS total_outcomes,
                    COUNT(*) FILTER (WHERE fo.is_winner = true) AS has_winner,
                    COUNT(*) FILTER (WHERE fo.opening_probability IS NOT NULL
                                      AND fo.opening_probability > 0
                                      AND fo.opening_probability < 1) AS eligible
                FROM virtual_market vm
                JOIN futures_outcomes fo ON fo.market_id = vm.market_id
                GROUP BY vm.vm_id, vm.source, vm.category, vm.is_grouped,
                         vm.mutually_exclusive
            ),
            clean_vms AS (
                SELECT * FROM vm_stats
                WHERE eligible >= 1
                  AND has_winner >= 1
            ),
            ranked_outcomes AS MATERIALIZED (
                SELECT
                    -- Queue #157 (#1012): raw curve price + the per-market
                    -- normalization divisor. The actual normalization (cp /
                    -- mnm.cp_sum) is DEFERRED to the ``normalized`` CTE below,
                    -- because it is gated on FIELD COMPLETENESS (Queue #257 Item
                    -- 1) which can only be aggregated once these per-outcome
                    -- exclusion flags exist. Carry market_id so completeness can
                    -- be computed per market.
                    {curve_price} AS raw_cp,
                    -- Queue #262 Item 1: candidate membership (structural, terminal)
                    -- vs divisor (price-expression). is_mex_normalized keys on the
                    -- candidate so an incomplete horizon field is dropped WHOLE even
                    -- when <3 members are present at the snapshot.
                    mfc.market_id AS candidate_market_id,
                    mfd.cp_sum AS mnm_cp_sum,
                    fo.market_id AS market_id,
                    -- Queue #259 Item 2: carry outcome identity + per-market shape
                    -- so the cohort sweep selects the SAME final rows (row identity)
                    -- with its cohort keys, instead of re-deriving the population.
                    fo.id AS outcome_id,
                    fo.name AS outcome_name,
                    vm.market_type AS market_type,
                    vm.llm_league AS llm_league,
                    fo.is_winner AS is_winner,
                    (fo.calibration_probability IS NOT NULL
                     AND fo.calibration_probability IS DISTINCT FROM fo.opening_probability) AS price_moved,
                    cv.vm_id, cv.source, cv.category,
                    cv.eligible, cv.is_grouped,
                    (cv.is_grouped OR cv.eligible >= 3) AS is_multi,
                    -- #940 phase-1: never-bid/never-traded Kalshi placeholders are
                    -- excluded from the published set (read-side only, gotcha #21).
                    {KALSHI_LIQUIDITY_EXISTS} AS is_liquid,
                    {POLY_PLACEHOLDER_EXCLUDE} AS is_poly_placeholder,
                    -- Queue #220/221 Item 3: all-bands poly never-traded flag (for
                    -- the exclusion-symmetry census; does NOT gate the curve).
                    {POLY_NEVER_TRADED} AS is_poly_never_traded,
                    -- L2-79 Item 1: malformed 2-outcome mex binary (winner count
                    -- 0 = void, or 2 = impossible). mb.win_count carries which.
                    (mb.market_id IS NOT NULL) AS is_malformed_binary,
                    mb.win_count AS malformed_win_count,
                    -- Queue #159 (#1010): esports match-bundle exclusion flag.
                    (emb.market_id IS NOT NULL) AS is_esports_bundle,
                    -- L2-79 Item 2: golf one-sided-ask placeholder — this outcome
                    -- sits in the >=0.80 band of an over-subscribed golf mex market.
                    (gpm.market_id IS NOT NULL
                     AND COALESCE(fo.calibration_probability, fo.opening_probability)
                         >= {GOLF_PLACEHOLDER_HIGH_BAND}) AS is_golf_placeholder,
                    -- Queue #186 (#941, corrects #167): Kalshi player-prop
                    -- threshold "<subject>: N+" OVER captures. EXCLUDED when
                    -- (A) category='hockey' (NHL goal-family is corrupt at every
                    -- price band — illiquid degenerate capture, resolution sane)
                    -- or (B) the curve price is in the degenerate settlement-
                    -- collapse band (>= 0.90), which resolves 0.11–0.48 across
                    -- every series (gotcha #14/#21). Queue #263 Item 1: the band
                    -- reads {curve_price} (terminal COALESCE(cp, opening) on the
                    -- headline, the horizon snapshot on a horizon) so each horizon
                    -- classifies on its OWN price, not the terminal probability.
                    -- The 2026-07-13 verify disproved #167's no-live-bid keep:
                    -- real-bid rows are corrupt too (scorer + non-scorer both cp
                    -- 0.995). Curve price, not bid, is the honest discriminator;
                    -- below-band liquid series stay (SAVE all possible). Read-side
                    -- only, no regrade (sign-flip premise disproven).
                    {kalshi_prop_threshold_exclude_sql(
                        source='cv.source',
                        name='fo.name',
                        category='cv.category',
                        calibration_probability='fo.calibration_probability',
                        opening_probability='fo.opening_probability',
                        curve_price=curve_price,
                    )} AS is_kalshi_prop_threshold,
                    -- Queue #183 Item 4 (#182 twin): weather wide-spread fabricated
                    -- midpoint. A wide Kalshi weather book (ask-bid >= 0.50) with no
                    -- trade has no real price discovery at its midpoint. Weather-gated
                    -- (tech miscalibration is genuine per #182 census — kept).
                    {WEATHER_WIDE_SPREAD_EXCLUDE} AS is_weather_wide_spread,
                    ROW_NUMBER() OVER (
                        PARTITION BY cv.vm_id
                        ORDER BY {rn_order}
                    ) AS rn
                FROM futures_outcomes fo
                JOIN virtual_market vm ON vm.market_id = fo.market_id
                JOIN clean_vms cv ON cv.vm_id = vm.vm_id AND cv.source = vm.source
                {curve_price_join}
                LEFT JOIN malformed_binaries mb ON mb.market_id = fo.market_id
                LEFT JOIN esports_multi_bundles emb ON emb.market_id = fo.market_id
                LEFT JOIN golf_placeholder_markets gpm ON gpm.market_id = fo.market_id
                LEFT JOIN mex_field_candidates mfc ON mfc.market_id = fo.market_id
                LEFT JOIN mex_field_divisor mfd ON mfd.market_id = fo.market_id
                WHERE fo.opening_probability IS NOT NULL
                  AND fo.opening_probability > 0 AND fo.opening_probability < 1
                  -- Queue #261 Item 1: calibration-truth eligibility (allowlist).
                  -- Replaces the scattered NOT-IN denylist with the single
                  -- resolution_authority contract: price-derived (clean_resolution
                  -- / settlement_sync) can no longer grade its own forecast, all
                  -- guess-family is excluded, and unknown sources fail closed.
                  AND fo.resolution_source IN {CALIBRATION_TRUTH_ELIGIBLE_SOURCES_SQL}
              AND COALESCE(fo.volume, -1) != 0
            ),
            -- Queue #257 Item 1: FIELD-COMPLETENESS aggregation. For each
            -- normalization CANDIDATE market (mex/field, single winner over all
            -- outcomes, >=3 eligible, sum > threshold), count eligible members,
            -- survivors (those passing EVERY per-outcome published exclusion), and
            -- whether the winner survived. Queue #262 Item 1: eligible_n is the FULL
            -- terminal-eligible member count (mfc.terminal_eligible_n), NOT the
            -- present-outcome COUNT — so a horizon field with a member missing at
            -- the snapshot (present < terminal) is INCOMPLETE and dropped whole. On
            -- the headline path present == terminal, so eligible_n equals the old
            -- COUNT(*) over ranked_outcomes exactly and behavior is unchanged.
            field_completeness AS (
                SELECT ro.market_id,
                    MAX(mfc.terminal_eligible_n) AS eligible_n,
                    COUNT(*) FILTER (
                        WHERE ro.is_liquid AND NOT ro.is_poly_placeholder
                          AND NOT ro.is_malformed_binary
                          AND NOT ro.is_esports_bundle
                          AND NOT ro.is_golf_placeholder
                          AND NOT ro.is_kalshi_prop_threshold
                          AND NOT ro.is_weather_wide_spread
                    ) AS survivor_n,
                    COUNT(*) FILTER (
                        WHERE ro.is_winner
                          AND ro.is_liquid AND NOT ro.is_poly_placeholder
                          AND NOT ro.is_malformed_binary
                          AND NOT ro.is_esports_bundle
                          AND NOT ro.is_golf_placeholder
                          AND NOT ro.is_kalshi_prop_threshold
                          AND NOT ro.is_weather_wide_spread
                    ) AS survivor_win_n
                FROM ranked_outcomes ro
                JOIN mex_field_candidates mfc ON mfc.market_id = ro.market_id
                GROUP BY ro.market_id
            ),
            -- Queue #257 Item 1: apply normalization ONLY to COMPLETE candidate
            -- fields (survivor_n = eligible_n AND winner survived AND >=3), so a
            -- published field sums to ~1.0 over its survivors. A candidate whose
            -- field is PARTIAL (a member was excluded) is flagged
            -- is_field_incomplete and dropped from the curve by ``deduped`` —
            -- never normalized over survivors. mnm.cp_sum equals the survivor sum
            -- exactly when complete, so cp / mnm_cp_sum normalizes to ~1.
            -- Queue #263 Item 1: a market is a genuine normalization FIELD when it
            -- is a structural partition candidate (mex_field_candidates) AND its
            -- curve-price sum clears the field threshold ON THE PRICE EXPRESSION
            -- (mnm_cp_sum = mex_field_divisor's SUM over {curve_price}: terminal cp
            -- on the headline, the horizon snapshot on a horizon). Moving the sum
            -- gate off terminal candidate detection makes qualification horizon-
            -- honest. On the headline mnm_cp_sum == the old terminal SUM, so
            -- ``is_field`` reduces to the old candidate membership exactly and a
            -- structural-but-below-threshold market keeps flowing to the multi pool
            -- (neither normalized nor dropped) exactly as before.
            normalized AS (
                SELECT ro.*,
                    (ro.candidate_market_id IS NOT NULL
                     AND ro.mnm_cp_sum > {MEX_NORMALIZE_THRESHOLD}
                     AND fc.survivor_n = fc.eligible_n
                     AND fc.survivor_win_n = 1
                     AND fc.survivor_n >= 3) AS is_mex_normalized,
                    (ro.candidate_market_id IS NOT NULL
                     AND ro.mnm_cp_sum > {MEX_NORMALIZE_THRESHOLD}
                     AND NOT (fc.survivor_n = fc.eligible_n
                              AND fc.survivor_win_n = 1
                              AND fc.survivor_n >= 3)) AS is_field_incomplete,
                    CASE WHEN ro.candidate_market_id IS NOT NULL
                              AND ro.mnm_cp_sum > {MEX_NORMALIZE_THRESHOLD}
                              AND fc.survivor_n = fc.eligible_n
                              AND fc.survivor_win_n = 1
                              AND fc.survivor_n >= 3
                         THEN ro.raw_cp / ro.mnm_cp_sum
                         ELSE ro.raw_cp
                    END AS adj_opening_probability
                FROM ranked_outcomes ro
                LEFT JOIN field_completeness fc ON fc.market_id = ro.market_id
            ),
            -- Queue #259 Item 1: mode-price detection is a PLACEHOLDER heuristic
            -- for the non-partition multi pool; a COMPLETE normalized field
            -- (is_mex_normalized) is a genuine partition summing to ~1.0, so its
            -- prices must NOT drive (nor be removed by) mode detection — else a
            -- uniform field (10 members @ 0.10) would be wiped. Incomplete fields
            -- are dropped anyway; exclude both so only publishable rows vote.
            mode_prices AS (
                SELECT vm_id, adj_opening_probability AS mode_price
                FROM normalized
                WHERE is_multi AND eligible >= 3 AND is_liquid
                  AND NOT is_mex_normalized AND NOT is_field_incomplete
                GROUP BY vm_id, adj_opening_probability, eligible
                HAVING COUNT(*) > GREATEST(eligible * 0.5, 2)
            ),
            deduped AS (
                SELECT ro.* FROM normalized ro
                LEFT JOIN mode_prices mp
                  ON mp.vm_id = ro.vm_id AND mp.mode_price = ro.adj_opening_probability
                WHERE ro.is_liquid AND NOT ro.is_poly_placeholder
                    AND NOT ro.is_malformed_binary
                    AND NOT ro.is_esports_bundle
                    AND NOT ro.is_golf_placeholder
                    AND NOT ro.is_kalshi_prop_threshold
                    AND NOT ro.is_weather_wide_spread
                    AND NOT ro.is_field_incomplete
                    AND
                    CASE
                        -- Queue #259 Item 1 INVARIANT FIX: a COMPLETE normalized
                        -- field is a partition that sums to ~1.0 over EXACTLY its
                        -- survivor members (field_completeness proved every eligible
                        -- member survived every per-outcome exclusion). The mode /
                        -- extreme-tail filters below are placeholder heuristics for
                        -- the NON-partition multi pool; applying them here would drop
                        -- a member (a 0.001-normalized tail, or a uniform field's
                        -- modal price) and publish <1.0 — the exact defect C14 found
                        -- (0.99/0.20/0.001 -> tail dropped -> ~99.9%). Publish every
                        -- member of a complete field so the partition still sums to 1.
                        WHEN ro.is_mex_normalized THEN true
                        WHEN ro.is_multi
                            THEN ro.adj_opening_probability > 0.005
                             AND ro.adj_opening_probability < 0.98
                             AND mp.vm_id IS NULL
                        ELSE ro.rn = 1
                    END
            )"""


async def compute_calibration_payload(db) -> dict:
    """The single canonical /api/calibration payload computation (Queue #257 Item 1).

    ONE eligible population + ONE normalization divisor, shared by BOTH serve
    paths so a cold-cache fallback can never diverge from the precomputed serve:
      * the scheduled ``precompute_calibration_main`` task (writes Redis), and
      * ``routes/calibration.public_calibration``'s in-request fallback.

    Previously each site carried its own copy of the CTE chain + Python
    post-processing and they had drifted in ~11 material ways — the route's
    cold-cache path was missing the liquidity / poly-placeholder / malformed-
    binary / golf-placeholder exclusions and the DataGolf-residual guard, used a
    looser resolution-source filter (kept ``pass2_loser`` / ``all_losers`` and
    NULL-source rows), and computed equal-weighted MCE where the task used
    n-weighted — so a cold serve showed a materially different curve. This
    function is that ONE population, imported by both.

    ``db`` is a live session supplied by the caller (task session or request
    session); all reads run on it and the response dict is returned WITHOUT
    writing Redis (the caching wrapper does that). Read-side only — never mutates
    is_winner / calibration_probability (gotcha #21).
    """
    from sqlalchemy import func, select

    from app.models import FuturesMarket
    from app.tasks.redis_state import get_redis_client

    # nullcontext preserves the historical block structure (the queries below
    # keep their original indentation) while running on the caller-provided
    # session instead of opening its own — so both serve paths share one body.
    with contextlib.nullcontext():
        # -----------------------------------------------------------
        # Query 1: Main futures calibration buckets
        # -----------------------------------------------------------
        main_sql = text(
            "WITH "
            + _calibration_population_ctes()
            # deduped is the LAST shared population CTE; liq_summary /
            # published_summary / bucketed + the bucket aggregation are
            # payload-only (the sweep selects deduped rows verbatim).
            + """,
            -- #940 phase-1 transparency: how many Kalshi outcomes the liquidity
            -- filter keeps vs drops (computed once from the materialized CTE).
            liq_summary AS (
                SELECT
                    COUNT(*) FILTER (WHERE source = 'kalshi' AND is_liquid) AS kalshi_included,
                    COUNT(*) FILTER (WHERE source = 'kalshi' AND NOT is_liquid) AS kalshi_excluded,
                    COUNT(*) FILTER (WHERE source = 'polymarket' AND is_poly_placeholder) AS poly_placeholder_excluded,
                    COUNT(*) FILTER (WHERE source = 'polymarket' AND NOT is_poly_placeholder) AS poly_included,
                    -- Queue #220/221 Item 3: exclusion-symmetry census. Poly
                    -- never-traded across ALL bands, and the asymmetry cohort
                    -- (never traded but outside the placeholder band, so still
                    -- IN the curve — the thing Kalshi excludes but poly does not).
                    COUNT(*) FILTER (WHERE source = 'polymarket' AND is_poly_never_traded) AS poly_never_traded_total,
                    COUNT(*) FILTER (WHERE source = 'polymarket' AND is_poly_never_traded AND NOT is_poly_placeholder) AS poly_never_traded_in_curve,
                    -- L2-79 Item 1: malformed-binary exclusion counts (eligible
                    -- outcomes flagged in ranked_outcomes, split by winner count).
                    COUNT(*) FILTER (WHERE is_malformed_binary AND malformed_win_count = 0) AS both_false_excluded,
                    COUNT(*) FILTER (WHERE is_malformed_binary AND malformed_win_count = 2) AS both_winner_excluded,
                    -- L2-79 Item 2: golf one-sided-ask placeholder exclusion count.
                    COUNT(*) FILTER (WHERE is_golf_placeholder) AS golf_placeholder_excluded,
                    -- Queue #157: multi-candidate normalization transparency —
                    -- how many curve outcomes had their probability normalized.
                    COUNT(*) FILTER (WHERE is_mex_normalized) AS mex_normalized_outcomes,
                    -- Queue #257 Item 1: field-completeness transparency. A
                    -- normalization CANDIDATE is a mex/field market that hit the
                    -- >=3 / one-winner / sum>threshold gate; it is PUBLISHED
                    -- (normalized) only if its field is complete, else EXCLUDED as
                    -- a partial field. Report the candidate vs published split so
                    -- the population change is honest, never silent.
                    COUNT(DISTINCT market_id) FILTER (
                        WHERE is_mex_normalized OR is_field_incomplete
                    ) AS mex_candidate_markets,
                    COUNT(DISTINCT market_id) FILTER (WHERE is_mex_normalized) AS mex_normalized_markets,
                    COUNT(DISTINCT market_id) FILTER (WHERE is_field_incomplete) AS field_incomplete_markets,
                    COUNT(*) FILTER (WHERE is_field_incomplete) AS field_incomplete_outcomes,
                    -- Queue #159: esports match-bundle exclusion count (eligible
                    -- outcomes flagged in ranked_outcomes that the filter drops).
                    COUNT(*) FILTER (WHERE is_esports_bundle) AS esports_bundle_excluded,
                    -- Queue #167 (#941/#1054): Kalshi player-prop threshold count.
                    COUNT(*) FILTER (WHERE is_kalshi_prop_threshold) AS kalshi_prop_threshold_excluded,
                    -- Queue #183 Item 4: weather wide-spread exclusion count.
                    COUNT(*) FILTER (WHERE is_weather_wide_spread) AS weather_wide_spread_excluded
                FROM normalized
            ),
            -- Queue #259 Item 1 (C14 P2): PUBLISHED counts from ``deduped`` (the
            -- rows that actually reach the curve), distinct from ``liq_summary``'s
            -- CANDIDATE counts over ``normalized`` (pre-dedup). Before the invariant
            -- fix a normalized field could be counted as published in liq_summary
            -- yet lose a member in deduped; reporting both makes the population
            -- change honest. With the fix these two normalized-market counts are
            -- equal (every complete field publishes intact) — a regression guard.
            published_summary AS (
                SELECT
                    COUNT(DISTINCT market_id) FILTER (WHERE is_mex_normalized) AS mex_published_markets,
                    COUNT(*) FILTER (WHERE is_mex_normalized) AS mex_published_outcomes,
                    COUNT(*) AS published_outcomes,
                    COUNT(DISTINCT vm_id) AS published_questions
                FROM deduped
            ),
            bucketed AS (
                SELECT *, LEAST(FLOOR(adj_opening_probability * 10)::int, 9) AS bucket_idx
                FROM deduped
            )
            SELECT bucket_idx, source, category, price_moved,
                COUNT(*) AS n,
                SUM(CASE WHEN is_winner THEN 1 ELSE 0 END) AS winners,
                AVG(adj_opening_probability) AS avg_prob,
                SUM(adj_opening_probability::float) AS sum_prob,
                SUM((adj_opening_probability::float - CASE WHEN is_winner THEN 1.0 ELSE 0.0 END)^2) AS sum_sq_err,
                MAX(ls.kalshi_included) AS kalshi_included,
                MAX(ls.kalshi_excluded) AS kalshi_excluded,
                MAX(ls.poly_placeholder_excluded) AS poly_placeholder_excluded,
                MAX(ls.poly_included) AS poly_included,
                MAX(ls.poly_never_traded_total) AS poly_never_traded_total,
                MAX(ls.poly_never_traded_in_curve) AS poly_never_traded_in_curve,
                MAX(ls.both_false_excluded) AS both_false_excluded,
                MAX(ls.both_winner_excluded) AS both_winner_excluded,
                MAX(ls.golf_placeholder_excluded) AS golf_placeholder_excluded,
                MAX(ls.mex_normalized_outcomes) AS mex_normalized_outcomes,
                MAX(ls.mex_candidate_markets) AS mex_candidate_markets,
                MAX(ls.mex_normalized_markets) AS mex_normalized_markets,
                MAX(ls.field_incomplete_markets) AS field_incomplete_markets,
                MAX(ls.field_incomplete_outcomes) AS field_incomplete_outcomes,
                MAX(ls.esports_bundle_excluded) AS esports_bundle_excluded,
                MAX(ls.kalshi_prop_threshold_excluded) AS kalshi_prop_threshold_excluded,
                MAX(ls.weather_wide_spread_excluded) AS weather_wide_spread_excluded,
                -- Queue #259 Item 1 (C14 P2): published (post-dedup) counts.
                MAX(ps.mex_published_markets) AS mex_published_markets,
                MAX(ps.mex_published_outcomes) AS mex_published_outcomes,
                MAX(ps.published_outcomes) AS published_outcomes,
                MAX(ps.published_questions) AS published_questions
            FROM bucketed
            CROSS JOIN liq_summary ls
            CROSS JOIN published_summary ps
            GROUP BY bucket_idx, source, category, price_moved
            ORDER BY bucket_idx, source, category, price_moved
        """)
        result = await db.execute(main_sql)
        rows = result.all()

        # #940 phase-1 transparency: included/excluded counts are constant across
        # every returned row (CROSS JOIN to the 1-row liq_summary).
        kalshi_included = (
            int(rows[0].kalshi_included)
            if rows and rows[0].kalshi_included is not None
            else 0
        )
        kalshi_excluded = (
            int(rows[0].kalshi_excluded)
            if rows and rows[0].kalshi_excluded is not None
            else 0
        )
        # L2-76: Polymarket no-bid placeholder exclusion transparency counts.
        poly_placeholder_excluded = (
            int(rows[0].poly_placeholder_excluded)
            if rows and rows[0].poly_placeholder_excluded is not None
            else 0
        )
        poly_included = (
            int(rows[0].poly_included)
            if rows and rows[0].poly_included is not None
            else 0
        )
        # Queue #220/221 Item 3: exclusion-symmetry census counts.
        poly_never_traded_total = (
            int(rows[0].poly_never_traded_total)
            if rows and rows[0].poly_never_traded_total is not None
            else 0
        )
        poly_never_traded_in_curve = (
            int(rows[0].poly_never_traded_in_curve)
            if rows and rows[0].poly_never_traded_in_curve is not None
            else 0
        )
        # L2-79 Item 1: malformed-binary exclusion transparency counts.
        both_false_excluded = (
            int(rows[0].both_false_excluded)
            if rows and rows[0].both_false_excluded is not None
            else 0
        )
        both_winner_excluded = (
            int(rows[0].both_winner_excluded)
            if rows and rows[0].both_winner_excluded is not None
            else 0
        )
        # L2-79 Item 2: golf one-sided-ask placeholder exclusion count.
        golf_placeholder_excluded = (
            int(rows[0].golf_placeholder_excluded)
            if rows and rows[0].golf_placeholder_excluded is not None
            else 0
        )
        # Queue #157: multi-candidate normalization transparency count.
        mex_normalized_outcomes = (
            int(rows[0].mex_normalized_outcomes)
            if rows and rows[0].mex_normalized_outcomes is not None
            else 0
        )

        # Queue #257 Item 1: field-completeness candidate/published split. A
        # candidate is a mex/field market that hit the normalization gate; it is
        # PUBLISHED (normalized) only if complete, else excluded as a partial
        # field. Reported separately so the population change is truthful.
        def _int0(attr):
            return (
                int(getattr(rows[0], attr))
                if rows and getattr(rows[0], attr, None) is not None
                else 0
            )

        mex_candidate_markets = _int0("mex_candidate_markets")
        mex_normalized_markets = _int0("mex_normalized_markets")
        field_incomplete_markets = _int0("field_incomplete_markets")
        field_incomplete_outcomes = _int0("field_incomplete_outcomes")
        # Queue #259 Item 1 (C14 P2): PUBLISHED (post-dedup) normalized markets —
        # the ones that actually reach the curve, vs the candidate/normalized
        # counts above which are computed pre-dedup over ``normalized``. With the
        # invariant fix these equal mex_normalized_markets (a complete field
        # publishes intact); a divergence means a post-normalization filter is
        # silently dropping members again.
        mex_published_markets = _int0("mex_published_markets")
        mex_published_outcomes = _int0("mex_published_outcomes")
        published_outcomes = _int0("published_outcomes")
        published_questions = _int0("published_questions")

        # Queue #159 (#1010): esports match-bundle exclusion transparency count.
        esports_bundle_excluded = (
            int(rows[0].esports_bundle_excluded)
            if rows and rows[0].esports_bundle_excluded is not None
            else 0
        )
        # Queue #167 (#941/#1054): Kalshi player-prop threshold exclusion count.
        kalshi_prop_threshold_excluded = (
            int(rows[0].kalshi_prop_threshold_excluded)
            if rows and rows[0].kalshi_prop_threshold_excluded is not None
            else 0
        )
        # Queue #183 Item 4 (#182 twin): weather wide-spread exclusion count.
        weather_wide_spread_excluded = (
            int(rows[0].weather_wide_spread_excluded)
            if rows and rows[0].weather_wide_spread_excluded is not None
            else 0
        )

        # -----------------------------------------------------------
        # Query 2: Ground-truth sports calibration from events table
        # -----------------------------------------------------------
        events_sql = text("""
            SELECT
                LEAST(FLOOR(prob * 10)::int, 9) AS bucket_idx,
                'odds_api' AS source,
                s.key AS category,
                COUNT(*) AS n,
                SUM(CASE WHEN won THEN 1 ELSE 0 END) AS winners,
                AVG(prob) AS avg_prob,
                SUM(prob::float) AS sum_prob,
                SUM((prob::float - CASE WHEN won THEN 1.0 ELSE 0.0 END)^2) AS sum_sq_err
            FROM (
                SELECT COALESCE(closing_home_probability, opening_home_probability) AS prob,
                       (home_score > away_score) AS won, sport_id
                FROM events
                WHERE status IN ('completed', 'closed')
                  AND COALESCE(closing_home_probability, opening_home_probability) IS NOT NULL
                  AND COALESCE(closing_home_probability, opening_home_probability) > 0
                  AND COALESCE(closing_home_probability, opening_home_probability) < 1
                  AND home_score IS NOT NULL AND away_score IS NOT NULL
                  AND home_score != away_score
                UNION ALL
                SELECT COALESCE(closing_away_probability, opening_away_probability) AS prob,
                       (away_score > home_score) AS won, sport_id
                FROM events
                WHERE status IN ('completed', 'closed')
                  AND COALESCE(closing_away_probability, opening_away_probability) IS NOT NULL
                  AND COALESCE(closing_away_probability, opening_away_probability) > 0
                  AND COALESCE(closing_away_probability, opening_away_probability) < 1
                  AND home_score IS NOT NULL AND away_score IS NOT NULL
                  AND home_score != away_score
            ) outcomes
            JOIN sports s ON s.id = outcomes.sport_id
            -- Queue #158 (#1011): soccer game-odds were captured 2-way (draw
            -- dropped at ingest — no draw column) so every soccer moneyline row
            -- sums to ~1.0 and over-predicts home/away by 7-18pp. Excluded from
            -- the published curve, league-scoped by the soccer_* key. Read-side
            -- only (gotcha #21); forward fix = 3-way capture (#1011).
            WHERE s.key NOT LIKE 'soccer_%'
            GROUP BY bucket_idx, s.key
            ORDER BY bucket_idx, s.key
        """)
        events_result = await db.execute(events_sql)
        events_rows = events_result.all()

        # -----------------------------------------------------------
        # Query 3: Spread calibration
        # -----------------------------------------------------------
        spreads_sql = text("""
            SELECT
                LEAST(FLOOR(prob * 10)::int, 9) AS bucket_idx,
                'odds_api_spreads' AS source,
                s.key AS category,
                COUNT(*) AS n,
                SUM(CASE WHEN won THEN 1 ELSE 0 END) AS winners,
                AVG(prob) AS avg_prob,
                SUM(prob::float) AS sum_prob,
                SUM((prob::float - CASE WHEN won THEN 1.0 ELSE 0.0 END)^2) AS sum_sq_err
            FROM (
                SELECT
                    (CASE WHEN closing_home_spread_odds < 0
                          THEN ABS(closing_home_spread_odds)::numeric / (ABS(closing_home_spread_odds) + 100.0)
                          ELSE 100.0 / (closing_home_spread_odds + 100.0) END)
                    /
                    ((CASE WHEN closing_home_spread_odds < 0
                           THEN ABS(closing_home_spread_odds)::numeric / (ABS(closing_home_spread_odds) + 100.0)
                           ELSE 100.0 / (closing_home_spread_odds + 100.0) END)
                     +
                     (CASE WHEN closing_away_spread_odds < 0
                           THEN ABS(closing_away_spread_odds)::numeric / (ABS(closing_away_spread_odds) + 100.0)
                           ELSE 100.0 / (closing_away_spread_odds + 100.0) END))
                    AS prob,
                    ((home_score - away_score) + closing_home_spread > 0) AS won,
                    sport_id
                FROM events
                WHERE status IN ('completed', 'closed')
                  AND closing_home_spread IS NOT NULL
                  AND closing_home_spread_odds IS NOT NULL
                  AND closing_away_spread_odds IS NOT NULL
                  AND home_score IS NOT NULL AND away_score IS NOT NULL
                  AND (home_score - away_score) + closing_home_spread != 0
            ) outcomes
            JOIN sports s ON s.id = outcomes.sport_id
            WHERE prob > 0 AND prob < 1
            GROUP BY bucket_idx, s.key
            ORDER BY bucket_idx, s.key
        """)
        spreads_result = await db.execute(spreads_sql)
        spreads_rows = spreads_result.all()

        # -----------------------------------------------------------
        # Query 4: Totals calibration
        # -----------------------------------------------------------
        totals_sql = text("""
            SELECT
                LEAST(FLOOR(prob * 10)::int, 9) AS bucket_idx,
                'odds_api_totals' AS source,
                s.key AS category,
                COUNT(*) AS n,
                SUM(CASE WHEN won THEN 1 ELSE 0 END) AS winners,
                AVG(prob) AS avg_prob,
                SUM(prob::float) AS sum_prob,
                SUM((prob::float - CASE WHEN won THEN 1.0 ELSE 0.0 END)^2) AS sum_sq_err
            FROM (
                SELECT
                    (CASE WHEN closing_over_odds < 0
                          THEN ABS(closing_over_odds)::numeric / (ABS(closing_over_odds) + 100.0)
                          ELSE 100.0 / (closing_over_odds + 100.0) END)
                    /
                    ((CASE WHEN closing_over_odds < 0
                           THEN ABS(closing_over_odds)::numeric / (ABS(closing_over_odds) + 100.0)
                           ELSE 100.0 / (closing_over_odds + 100.0) END)
                     +
                     (CASE WHEN closing_under_odds < 0
                           THEN ABS(closing_under_odds)::numeric / (ABS(closing_under_odds) + 100.0)
                           ELSE 100.0 / (closing_under_odds + 100.0) END))
                    AS prob,
                    ((home_score + away_score) > closing_over_under) AS won,
                    sport_id
                FROM events
                WHERE status IN ('completed', 'closed')
                  AND closing_over_under IS NOT NULL
                  AND closing_over_odds IS NOT NULL
                  AND closing_under_odds IS NOT NULL
                  AND home_score IS NOT NULL AND away_score IS NOT NULL
                  AND (home_score + away_score) != closing_over_under
            ) outcomes
            JOIN sports s ON s.id = outcomes.sport_id
            WHERE prob > 0 AND prob < 1
            GROUP BY bucket_idx, s.key
            ORDER BY bucket_idx, s.key
        """)
        totals_result = await db.execute(totals_sql)
        totals_rows = totals_result.all()

        # -----------------------------------------------------------
        # Query 5: Per-bookmaker calibration from Redis
        # -----------------------------------------------------------
        bookmaker_rows = []
        # Queue #158 (#1011): the per-bookmaker calibration (odds_api_bookmaker)
        # devigs soccer moneyline as home_prob/(home_prob+away_prob) — the SAME
        # 2-way draw-omission bug as the events curve (_precompute_bookmaker_
        # calibration in backfill_winners.py has no draw term). Left in, it
        # dominates the soccer_* by_category lines (~40K draw-inflated outcomes).
        # Drop the soccer_* bookmaker buckets here (read-side, consumption-side)
        # so the exclusion is robust even though the 6h source keeps writing them.
        bookmaker_soccer_excluded = 0
        try:
            from types import SimpleNamespace as _NS
            rc = get_redis_client()
            _cached = rc.get("bainluck:bookmaker_calibration")
            if _cached:
                for row in json.loads(_cached):
                    if category_is_soccer_2way_excluded(row.get("category")):
                        bookmaker_soccer_excluded += int(row.get("n") or 0)
                        continue
                    bookmaker_rows.append(_NS(**row))
        except Exception:
            pass

        # -----------------------------------------------------------
        # Query 6: Total resolved markets count
        # -----------------------------------------------------------
        total_markets_result = await db.execute(
            select(func.count()).select_from(FuturesMarket).where(
                FuturesMarket.status == "resolved"
            )
        )
        total_markets = total_markets_result.scalar()

        # -----------------------------------------------------------
        # Query 7: Closing line coverage
        # -----------------------------------------------------------
        closing_sql = text("""
            SELECT
                COUNT(*) FILTER (WHERE closing_home_probability IS NOT NULL) AS has_closing,
                COUNT(*) FILTER (WHERE closing_home_probability IS NULL
                                 AND commence_time IS NOT NULL) AS needs_closing,
                COUNT(*) AS total_completed
            FROM events
            WHERE status IN ('completed', 'closed')
              AND home_score IS NOT NULL AND away_score IS NOT NULL
        """)
        closing_result = await db.execute(closing_sql)
        closing_row = closing_result.one()

        # -----------------------------------------------------------
        # Query 8: #762 void-filter transparency — how many eligible resolved
        # outcomes the void rule (did_not_play / withdrew) drops from the
        # published denominator. Mirrors the #940 liquidity_filter count so the
        # exclusion is surfaced, never silent. Same eligibility predicate as the
        # main query (resolved + opening_probability in (0,1)).
        # -----------------------------------------------------------
        void_sql = text("""
            SELECT COUNT(*) AS excluded
            FROM futures_outcomes fo
            JOIN futures_markets fm ON fm.id = fo.market_id
            WHERE fm.status = 'resolved'
              AND fo.resolution_source IN ('did_not_play', 'withdrew')
              AND fo.opening_probability IS NOT NULL
              AND fo.opening_probability > 0 AND fo.opening_probability < 1
        """)
        void_result = await db.execute(void_sql)
        void_excluded = int(void_result.scalar() or 0)

        # -----------------------------------------------------------
        # Query 9: #754-curve heuristic-exclusion transparency — how many
        # eligible resolved outcomes the heuristic rule (pass2_loser /
        # all_losers, alongside the long-standing pass2_guess) drops from the
        # published curve. Lane-2 L2-30 measured poly pass2_loser = 41,069
        # outcomes @ 0.0% winrate (23,240 priced 0.5-0.9 — statistically
        # impossible if correct); leaving them in dragged poly MCE to ~10.84pp.
        # Read-side exclusion only — markets stay resolved, never re-graded
        # (gotcha #21). 97% lack a polymarket_event_id so Gamma/CLOB re-resolution
        # is infeasible by construction; exclusion is the correct durable fix.
        # Surfaced here so the exclusion is transparent, never silent.
        heur_sql = text("""
            SELECT fm.source, COUNT(*) AS excluded
            FROM futures_outcomes fo
            JOIN futures_markets fm ON fm.id = fo.market_id
            WHERE fm.status = 'resolved'
              AND fo.resolution_source IN ('pass2_loser', 'all_losers')
              AND fo.opening_probability IS NOT NULL
              AND fo.opening_probability > 0 AND fo.opening_probability < 1
            GROUP BY fm.source
        """)
        heur_result = await db.execute(heur_sql)
        heuristic_excluded = {r.source: int(r.excluded) for r in heur_result.all()}

        # -----------------------------------------------------------
        # Query 10: Queue #158 (#1011) soccer 2-way exclusion transparency —
        # how many events-table soccer moneyline outcomes the draw-omission rule
        # drops from the published curve. Mirrors the events_sql population
        # (same eligibility, both home + away outcomes) so the count is honest,
        # never silent — the same contract as the #762 void_filter count.
        # -----------------------------------------------------------
        soccer_2way_sql = text("""
            SELECT COUNT(*) AS excluded
            FROM (
                SELECT sport_id
                FROM events
                WHERE status IN ('completed', 'closed')
                  AND COALESCE(closing_home_probability, opening_home_probability) IS NOT NULL
                  AND COALESCE(closing_home_probability, opening_home_probability) > 0
                  AND COALESCE(closing_home_probability, opening_home_probability) < 1
                  AND home_score IS NOT NULL AND away_score IS NOT NULL
                  AND home_score != away_score
                UNION ALL
                SELECT sport_id
                FROM events
                WHERE status IN ('completed', 'closed')
                  AND COALESCE(closing_away_probability, opening_away_probability) IS NOT NULL
                  AND COALESCE(closing_away_probability, opening_away_probability) > 0
                  AND COALESCE(closing_away_probability, opening_away_probability) < 1
                  AND home_score IS NOT NULL AND away_score IS NOT NULL
                  AND home_score != away_score
            ) outcomes
            JOIN sports s ON s.id = outcomes.sport_id
            WHERE s.key LIKE 'soccer_%'
        """)
        soccer_2way_result = await db.execute(soccer_2way_sql)
        soccer_2way_excluded = int(soccer_2way_result.scalar() or 0)

        # -----------------------------------------------------------
        # Query 11: Queue #261 Item 3 — truth-evidence census. Over the SAME
        # resolved + opening-in-(0,1) eligibility shape the population scans,
        # classify every futures outcome by calibration-truth class so the
        # population change (Item 1) is visible, never silent: how many rows are
        # eligible (independent authority grades the forecast), how many are
        # price-derived (now excluded — the leakage containment), and — the hard
        # contract violation — how many carry an UNKNOWN source (must be 0).
        # No source-bias interpretation; just the counts + the two RED invariants.
        # -----------------------------------------------------------
        truth_sql = text(f"""
            SELECT
                CASE
                    WHEN fo.resolution_source IS NULL THEN 'missing'
                    WHEN fo.resolution_source IN {CALIBRATION_TRUTH_ELIGIBLE_SOURCES_SQL} THEN 'eligible'
                    WHEN fo.resolution_source IN {PRICE_DERIVED_SOURCES_SQL} THEN 'price_derived'
                    WHEN fo.resolution_source IN {CALIBRATION_TRUTH_INELIGIBLE_SOURCES_SQL} THEN 'ineligible_other'
                    ELSE 'unknown'
                END AS truth_class,
                COUNT(*) AS outcomes,
                COUNT(DISTINCT fo.market_id) AS markets
            FROM futures_outcomes fo
            JOIN futures_markets fm ON fm.id = fo.market_id
            WHERE fm.status = 'resolved'
              AND fo.opening_probability IS NOT NULL
              AND fo.opening_probability > 0 AND fo.opening_probability < 1
              AND COALESCE(fo.volume, -1) != 0
            GROUP BY 1
        """)
        truth_result = await db.execute(truth_sql)
        truth_by_class = {
            r.truth_class: {"outcomes": int(r.outcomes), "markets": int(r.markets)}
            for r in truth_result.all()
        }

    # -----------------------------------------------------------
    # Post-processing (runs outside the DB session)
    # -----------------------------------------------------------
    all_rows = list(rows) + list(events_rows) + list(spreads_rows) + list(totals_rows) + list(bookmaker_rows)
    total_outcomes = sum(r.n for r in all_rows)
    total_winners = sum(r.winners for r in all_rows)

    # Build bucket dicts with Wilson CIs
    bucket_dicts = []
    for r in all_rows:
        ci_lo, ci_hi = _wilson_ci(r.winners, r.n)
        bucket_dicts.append({
            "bucket_idx": r.bucket_idx, "source": r.source, "category": r.category,
            "price_moved": getattr(r, "price_moved", None),
            "n": r.n, "winners": r.winners,
            "avg_prob": round(float(r.avg_prob), 4),
            "sum_prob": round(float(r.sum_prob), 4),
            "sum_sq_err": round(float(r.sum_sq_err), 4),
            "ci_lower": round(ci_lo, 4),
            "ci_upper": round(ci_hi, 4),
        })

    # Aggregate buckets for MCE bootstrap CI
    agg: dict[int, dict] = {}
    for b in bucket_dicts:
        idx = b["bucket_idx"]
        if idx not in agg:
            agg[idx] = {"n": 0, "winners": 0, "sum_prob": 0.0}
        agg[idx]["n"] += b["n"]
        agg[idx]["winners"] += b["winners"]
        agg[idx]["sum_prob"] += b["sum_prob"]
    agg_list = [
        {"n": v["n"], "winners": v["winners"], "avg_prob": v["sum_prob"] / v["n"]}
        for v in agg.values()
        if v["n"] > 0
    ]
    mce_ci_lo, mce_ci_hi = _bootstrap_mce_ci(agg_list)

    # Cohort-level MCE: closing line vs opening price
    def _cohort_mce(buckets: list[dict], pred: object) -> float | None:
        cohort_agg: dict[int, dict] = {}
        for b in buckets:
            if b.get("price_moved") != pred:
                continue
            idx = b["bucket_idx"]
            if idx not in cohort_agg:
                cohort_agg[idx] = {"n": 0, "winners": 0, "sum_prob": 0.0}
            cohort_agg[idx]["n"] += b["n"]
            cohort_agg[idx]["winners"] += b["winners"]
            cohort_agg[idx]["sum_prob"] += b["sum_prob"]
        if not cohort_agg:
            return None
        total_abs_err = 0.0
        for v in cohort_agg.values():
            if v["n"] == 0:
                continue
            avg_prob = v["sum_prob"] / v["n"]
            actual = v["winners"] / v["n"]
            total_abs_err += abs(actual - avg_prob)
        return round(total_abs_err / len(cohort_agg) * 100, 2)

    mce_closing_line = _cohort_mce(bucket_dicts, True)
    mce_opening_price = _cohort_mce(bucket_dicts, False)

    # Per-category MCE breakdown
    cat_agg: dict[str, dict[int, dict]] = {}
    cat_outcomes: dict[str, int] = {}
    for b in bucket_dicts:
        cat = b["category"]
        idx = b["bucket_idx"]
        if cat not in cat_agg:
            cat_agg[cat] = {}
            cat_outcomes[cat] = 0
        if idx not in cat_agg[cat]:
            cat_agg[cat][idx] = {"n": 0, "winners": 0, "sum_prob": 0.0}
        cat_agg[cat][idx]["n"] += b["n"]
        cat_agg[cat][idx]["winners"] += b["winners"]
        cat_agg[cat][idx]["sum_prob"] += b["sum_prob"]
        cat_outcomes[cat] += b["n"]

    # #997: minimum-sample gate — a sub-category chart below this many resolved
    # outcomes is noise. Enforced here (server-side) so web + native inherit it.
    _min_cat_outcomes = _get_min_category_outcomes(get_redis_client())

    by_category = []
    small_sample_categories = []
    for cat, buckets_by_idx in sorted(cat_agg.items()):
        total_n = cat_outcomes[cat]
        if total_n == 0:
            continue
        if total_n < _min_cat_outcomes:
            # Below the bar: excluded from the published chart list, but
            # recorded (with its count) so the exclusion is transparent, never
            # silent. It still counts toward the overall/per-source curves.
            small_sample_categories.append({"category": cat, "outcomes": total_n})
            continue
        _cat_buckets = [
            {"n": v["n"], "winners": v["winners"], "sum_prob": v["sum_prob"]}
            for v in buckets_by_idx.values()
        ]
        cat_mce = _compute_horizon_mce(_cat_buckets)
        cat_mce_unweighted = _compute_horizon_mce(_cat_buckets, weighted=False)
        by_category.append({
            "category": cat,
            "mce": cat_mce,
            "mce_unweighted": cat_mce_unweighted,
            "outcomes": total_n,
            # L2-73 payload v2 (#999 §F): explicit display semantics so web +
            # native render the same story. ece = n-weighted (headline);
            # mce (worst-bucket) = the equal-weighted number, for the secondary col.
            "ece": cat_mce,
            "mce_worst": cat_mce_unweighted,
            "n": total_n,
            "gated": False,  # published entries are already above the sample floor
        })
    by_category.sort(key=lambda x: x["outcomes"], reverse=True)
    small_sample_categories.sort(key=lambda x: x["outcomes"], reverse=True)

    # Per-source MCE breakdown
    src_agg: dict[str, dict[int, dict]] = {}
    src_outcomes: dict[str, int] = {}
    for b in bucket_dicts:
        src = b["source"]
        idx = b["bucket_idx"]
        if src not in src_agg:
            src_agg[src] = {}
            src_outcomes[src] = 0
        if idx not in src_agg[src]:
            src_agg[src][idx] = {"n": 0, "winners": 0, "sum_prob": 0.0}
        src_agg[src][idx]["n"] += b["n"]
        src_agg[src][idx]["winners"] += b["winners"]
        src_agg[src][idx]["sum_prob"] += b["sum_prob"]
        src_outcomes[src] += b["n"]

    by_source = []
    for src, buckets_by_idx in sorted(src_agg.items()):
        total_n = src_outcomes[src]
        if total_n == 0:
            continue
        _src_buckets = [
            {"n": v["n"], "winners": v["winners"], "sum_prob": v["sum_prob"]}
            for v in buckets_by_idx.values()
        ]
        src_mce = _compute_horizon_mce(_src_buckets)
        src_mce_unweighted = _compute_horizon_mce(_src_buckets, weighted=False)
        by_source.append({
            "source": src,
            "mce": src_mce,
            "mce_unweighted": src_mce_unweighted,
            "outcomes": total_n,
            # L2-73 payload v2 (#999 §F): explicit ECE (n-weighted headline) +
            # worst-bucket MCE + n for native/web parity.
            "ece": src_mce,
            "mce_worst": src_mce_unweighted,
            "n": total_n,
            "gated": False,
        })
    by_source.sort(key=lambda x: x["outcomes"], reverse=True)

    # Spread / Total summaries
    def _source_summary(source_key: str) -> dict:
        sport_agg: dict[str, dict[int, dict]] = {}
        sport_outcomes: dict[str, int] = {}
        total_n = 0
        total_w = 0
        for b in bucket_dicts:
            if b["source"] != source_key:
                continue
            sport = b["category"]
            idx = b["bucket_idx"]
            if sport not in sport_agg:
                sport_agg[sport] = {}
                sport_outcomes[sport] = 0
            if idx not in sport_agg[sport]:
                sport_agg[sport][idx] = {"n": 0, "winners": 0, "sum_prob": 0.0}
            sport_agg[sport][idx]["n"] += b["n"]
            sport_agg[sport][idx]["winners"] += b["winners"]
            sport_agg[sport][idx]["sum_prob"] += b["sum_prob"]
            sport_outcomes[sport] += b["n"]
            total_n += b["n"]
            total_w += b["winners"]

        by_sport = []
        for sport, buckets_by_idx in sorted(sport_agg.items()):
            sn = sport_outcomes[sport]
            if sn == 0:
                continue
            # #997: same minimum-sample gate as by_category — a per-sport
            # spread/total chart below the bar is thin-sample noise.
            if sn < _min_cat_outcomes:
                continue
            sport_mce = _compute_horizon_mce([
                {"n": v["n"], "winners": v["winners"], "sum_prob": v["sum_prob"]}
                for v in buckets_by_idx.values()
            ])
            by_sport.append({"sport": sport, "mce": sport_mce, "outcomes": sn})
        by_sport.sort(key=lambda x: x["outcomes"], reverse=True)

        all_agg: dict[int, dict] = {}
        for b in bucket_dicts:
            if b["source"] != source_key:
                continue
            idx = b["bucket_idx"]
            if idx not in all_agg:
                all_agg[idx] = {"n": 0, "winners": 0, "sum_prob": 0.0}
            all_agg[idx]["n"] += b["n"]
            all_agg[idx]["winners"] += b["winners"]
            all_agg[idx]["sum_prob"] += b["sum_prob"]
        overall_mce = _compute_horizon_mce([
            {"n": v["n"], "winners": v["winners"], "sum_prob": v["sum_prob"]}
            for v in all_agg.values()
        ])

        return {
            "mce": overall_mce,
            "outcomes": total_n,
            "winners": total_w,
            "by_sport": by_sport,
        }

    spreads_summary = _source_summary("odds_api_spreads")
    totals_summary = _source_summary("odds_api_totals")

    # L2-78 Item 0 (flagged since L2-73): the true resolved-data span for the
    # calibration hero. Cheap MIN/MAX over resolved futures resolution_date (the
    # Kalshi/Polymarket bulk of the curve), but BOUNDED to a sane window so
    # data-quality artifacts can't define the hero: a resolved market must have
    # resolved in the past (resolution_date <= NOW() — a future date on a
    # 'resolved' row is a bad date) and within the last 5 years (these sources
    # are all recent; a 2011 date is a parse artifact, seen live). Without the
    # bound the raw MIN/MAX read Jul-2011–Jul-2029. None-safe; the hero falls
    # back to generated_at when absent.
    date_range = None
    try:
        dr = (
            await db.execute(
                text(
                    "SELECT MIN(resolution_date) AS lo, MAX(resolution_date) AS hi "
                    "FROM futures_markets "
                    "WHERE status = 'resolved' AND resolution_date IS NOT NULL "
                    "AND resolution_date <= NOW() "
                    "AND resolution_date >= NOW() - INTERVAL '5 years'"
                )
            )
        ).one()
        if dr.lo and dr.hi:
            date_range = {"start": dr.lo.isoformat(), "end": dr.hi.isoformat()}
    except Exception:
        logger.warning("calibration date_range aggregate failed", exc_info=True)

    response = {
        "closing_line_coverage": {
            "has_closing": closing_row.has_closing,
            "needs_closing": closing_row.needs_closing,
            "total": closing_row.total_completed,
        },
        "buckets": bucket_dicts,
        "by_category": by_category,
        "by_source": by_source,
        "date_range": date_range,  # L2-78 Item 0: resolved-data span for the hero
        "corrections": CALIBRATION_CORRECTIONS,  # L2-73 §E trust panel
        # #997 App Store ship-gate: the minimum resolved-outcome count for a
        # chartable sub-category. Shipped so web + native gate on the SAME bar
        # instead of hardcoding their own; by_category / by_sport above are
        # already filtered to it. small_sample_categories lists what was gated
        # out (with counts) so the exclusion is transparent.
        "min_category_outcomes": _min_cat_outcomes,
        "small_sample_categories": small_sample_categories,
        "spreads_summary": spreads_summary,
        "totals_summary": totals_summary,
        "total_markets": total_markets,
        "total_outcomes": total_outcomes,
        "total_winners": total_winners,
        "mce_ci_lower": round(mce_ci_lo * 100, 2),
        "mce_ci_upper": round(mce_ci_hi * 100, 2),
        "mce_closing_line": mce_closing_line,
        "mce_opening_price": mce_opening_price,
        "liquidity_filter": {
            "applies_to": "kalshi",
            "rule": KALSHI_LIQUIDITY_RULE_TEXT,
            "kalshi_included": kalshi_included,
            "kalshi_excluded": kalshi_excluded,
        },
        "poly_placeholder_filter": {  # L2-76 (#151/#997)
            "applies_to": "polymarket",
            "rule": POLY_PLACEHOLDER_RULE_TEXT,
            "included": poly_included,
            "excluded": poly_placeholder_excluded,
        },
        "exclusion_symmetry": {  # Queue #220/221 Item 3
            "note": (
                "The never-traded liquidity filter is asymmetric across sources. "
                "Kalshi excludes every never-traded outcome (all price bands); "
                "Polymarket only excludes never-traded outcomes in the near-0.50 "
                "placeholder band. poly_never_traded_in_curve is the cohort that "
                "never traded but sits outside that band, so it is STILL counted "
                "in the curve — the residual asymmetry. Measurement only; closing "
                "it (excluding all poly never-traded) is a separate Alex-gated "
                "decision (gotcha #21 keeps this read-side)."
            ),
            "per_source": SOURCE_LIQUIDITY_EXCLUSIONS,
            "poly_never_traded_total": poly_never_traded_total,
            "poly_never_traded_in_curve": poly_never_traded_in_curve,
            "poly_never_traded_excluded_by_band": max(
                poly_never_traded_total - poly_never_traded_in_curve, 0
            ),
        },
        "malformed_binary_filter": {  # L2-79 Item 1 (#997/#1010)
            "applies_to": "all",
            "rule": MALFORMED_BINARY_RULE_TEXT,
            "both_false_excluded": both_false_excluded,
            "both_winner_excluded": both_winner_excluded,
            "excluded": both_false_excluded + both_winner_excluded,
        },
        "golf_placeholder_filter": {  # L2-79 Item 2 (#940/#762)
            "applies_to": "golf",
            "rule": GOLF_PLACEHOLDER_RULE_TEXT,
            "excluded": golf_placeholder_excluded,
        },
        "mex_normalization": {  # Queue #157 (#1012) + Queue #257 Item 1
            "applies_to": "all",
            "rule": MEX_NORMALIZE_RULE_TEXT,
            "threshold": MEX_NORMALIZE_THRESHOLD,
            "normalized_outcomes": mex_normalized_outcomes,
            # Queue #257 Item 1: the field-completeness invariant. candidate =
            # markets that hit the normalization gate; published = those complete
            # enough to normalize (each sums ~1.0 over its survivors); the rest
            # are partial fields excluded from the curve with a repair reason,
            # never normalized over survivors.
            "field_completeness": {
                "rule": FIELD_COMPLETENESS_RULE_TEXT,
                "candidate_markets": mex_candidate_markets,
                # Queue #257 pre-dedup normalized-candidate count (over ``normalized``).
                "published_normalized_markets": mex_normalized_markets,
                # Queue #259 Item 1 (C14 P2): the counts computed over ``deduped`` —
                # markets/outcomes that actually reach the published curve. Equal to
                # the normalized-candidate count above once the sum-to-1 invariant
                # holds (a complete field publishes every member); reported so the
                # candidate -> published split is never silent.
                "published_normalized_markets_post_dedup": mex_published_markets,
                "published_normalized_outcomes_post_dedup": mex_published_outcomes,
                "field_incomplete_excluded_markets": field_incomplete_markets,
                "field_incomplete_excluded_outcomes": field_incomplete_outcomes,
            },
        },
        "esports_multi_bundle_filter": {  # Queue #159 (#1010)
            "applies_to": "esports",
            "rule": ESPORTS_MULTI_BUNDLE_RULE_TEXT,
            "excluded": esports_bundle_excluded,
        },
        "kalshi_prop_threshold_filter": {  # Queue #186 (#941, corrects #167)
            "applies_to": "kalshi",
            "rule": KALSHI_PROP_THRESHOLD_RULE_TEXT,
            "excluded": kalshi_prop_threshold_excluded,
        },
        "weather_wide_spread_filter": {  # Queue #183 Item 4 (#182 twin)
            "applies_to": "kalshi (weather only)",
            "rule": WEATHER_WIDE_SPREAD_RULE_TEXT,
            "excluded": weather_wide_spread_excluded,
        },
        "void_filter": {
            "applies_to": "datagolf",
            "rule": VOID_FILTER_RULE_TEXT,
            "excluded": void_excluded,
        },
        "soccer_2way_filter": {  # Queue #158 (#1011)
            "applies_to": "odds_api, odds_api_bookmaker",
            "rule": SOCCER_2WAY_RULE_TEXT,
            "excluded": soccer_2way_excluded + bookmaker_soccer_excluded,
            "events_excluded": soccer_2way_excluded,
            "bookmaker_excluded": bookmaker_soccer_excluded,
        },
        "heuristic_filter": {
            "applies_to": "polymarket",
            "rule": (
                "Outcomes resolved by legacy heuristic passes (pass2_guess, "
                "pass2_loser, all_losers) are excluded from the published curve: "
                "they were guessed, not authoritatively settled (Lane-2 #754 "
                "measured pass2_loser at 0.0% winrate even at 0.5-0.9 prices), and "
                "97% lack a polymarket_event_id so authoritative re-resolution is "
                "infeasible. Read-side exclusion only; markets stay resolved, "
                "never re-graded (gotcha #21)."
            ),
            "excluded_by_source": heuristic_excluded,
        },
        "truth_evidence": _build_truth_evidence(
            truth_by_class,
            mex_normalized_markets=mex_normalized_markets,
            mex_published_markets=mex_published_markets,
            published_outcomes=published_outcomes,
            published_questions=published_questions,
        ),
        "generated_at": datetime.now(timezone.utc).isoformat(),
    }

    return response


def _build_truth_evidence(
    truth_by_class: dict,
    *,
    mex_normalized_markets: int,
    mex_published_markets: int,
    published_outcomes: int,
    published_questions: int,
) -> dict:
    """Queue #261 Item 3: the calibration-truth regression-visibility artifact.

    Reports the truth-evidence census (outcomes/markets by class over the
    resolved eligibility shape), the price-derived rows now excluded (the
    leakage containment), any unknown-source rows, and the two contract
    invariants. ``contract_ok`` goes RED ONLY on a real contract violation —
    an unknown resolution_source in the resolved population, or the Queue #259
    candidate==published partition breaking — never on a source-mix ratio.
    """
    unknown = truth_by_class.get("unknown", {"outcomes": 0, "markets": 0})
    price_derived = truth_by_class.get("price_derived", {"outcomes": 0, "markets": 0})
    partition_ok = mex_normalized_markets == mex_published_markets
    violations = []
    if unknown["outcomes"] > 0:
        violations.append(
            f"unknown resolution_source in {unknown['outcomes']} resolved outcomes "
            f"(fail-closed: excluded from the curve, but classify them in "
            f"resolution_authority)"
        )
    if not partition_ok:
        violations.append(
            f"Queue #259 partition invariant broken: normalized "
            f"{mex_normalized_markets} != published {mex_published_markets} markets "
            f"(a post-normalization filter is dropping field members)"
        )
    return {
        "rule": (
            "A source may grade a published forecast only if its winner is "
            "established INDEPENDENTLY of the market's own price (venue/API "
            "settlement or deterministic public-data). Price-derived truth "
            "(clean_resolution / settlement_sync) is excluded — Queue #261."
        ),
        "by_class": truth_by_class,
        "price_derived_excluded": price_derived,
        "unknown_sources": unknown,
        "published_outcomes": published_outcomes,
        "published_questions": published_questions,
        "partition_invariant": {
            "normalized_markets": mex_normalized_markets,
            "published_markets": mex_published_markets,
            "ok": partition_ok,
        },
        "contract_ok": not violations,
        "contract_violations": violations,
    }


async def _precompute_calibration_main():
    """Precompute the main /api/calibration payload and cache it in Redis.

    Thin caching wrapper over the shared ``compute_calibration_payload`` (Queue
    #257 Item 1): opens a task session, computes the ONE canonical payload, and
    stores it under ``bainluck:calibration:main`` so the HTTP endpoint serves it
    instantly instead of running the heavy queries in-request.
    """
    from app.tasks.base import get_task_session
    from app.tasks.redis_state import get_redis_client

    async with get_task_session() as db:
        response = await compute_calibration_payload(db)

    rc = get_redis_client()
    rc.set("bainluck:calibration:main", json.dumps(response), ex=_MAIN_CACHE_TTL)
    logger.info(
        "Cached main calibration in Redis (%d buckets, %d outcomes)",
        len(response["buckets"]), response["total_outcomes"],
    )
    return {
        "status": "ok",
        "buckets": len(response["buckets"]),
        "outcomes": response["total_outcomes"],
    }


def _time_horizon_payload(horizons_result: dict) -> dict:
    """Assemble the served time-horizon payload from whatever horizons are computed.

    Additive over the historical shape (``horizons`` + ``description`` +
    ``generated_at``): also carries ``complete`` and ``missing`` so the endpoint can
    serve a PARTIAL result (e.g. 3/4 horizons) instead of the "computing" placeholder
    when one horizon is slow/poison — the #1171 fix (never publish nothing)."""
    missing = [label for label, _ in _HORIZONS if label not in horizons_result]
    return {
        "horizons": horizons_result,
        "complete": not missing,
        "missing": missing,
        "description": (
            "Calibration at multiple time horizons for non-event markets "
            "(elections, economics, entertainment, etc.). Each horizon shows "
            "prediction accuracy using the last available snapshot N days "
            "before market resolution."
        ),
        "generated_at": datetime.now(timezone.utc).isoformat(),
    }


def _publish_time_horizon(rc, horizons_result: dict) -> None:
    """Publish the currently-computed horizons to the served main key. Safe to call
    after every horizon: an OOM SIGKILL or statement_timeout on a LATER horizon can
    then never strand the endpoint on "computing" — it serves the horizons done so
    far (#1171: the main key was previously written ONLY after all 4 completed, so a
    single poison horizon blocked the whole payload forever)."""
    if not horizons_result:
        return
    try:
        rc.set(
            "bainluck:calibration:time_horizon",
            json.dumps(_time_horizon_payload(horizons_result)),
            ex=_CACHE_TTL,
        )
    except Exception as exc:  # noqa: BLE001 — publish is best-effort, never fatal
        logger.warning("time-horizon: main-key publish failed: %s", exc)


def _load_time_horizon_wip(rc) -> dict:
    """Load the resumable horizon WIP accumulator, rejecting stale populations.

    Queue #263 Item 2: the WIP is version-wrapped
    (``{"population_version": <v>, "horizons": {...}}``). A resume MUST discard:
      * a LEGACY unwrapped accumulator (a bare ``{label: data}`` dict with no
        wrapper — the pre-#263 shape),
      * corrupt JSON, and
      * any wrapper whose ``population_version`` != the current version,
    so a horizon computed under an older population is never resumed (skipping its
    recompute) nor republished under the new version. Returns ``{label: data}`` for
    ONLY the current-version horizons, so the caller recomputes everything else.
    """
    wip_raw = rc.get(_TIME_HORIZON_WIP_KEY)
    if not wip_raw:
        return {}
    try:
        parsed = json.loads(wip_raw)
    except (ValueError, TypeError):
        return {}
    if (
        not isinstance(parsed, dict)
        or parsed.get("population_version") != CALIBRATION_POPULATION_VERSION
    ):
        # Legacy unwrapped or version-mismatched accumulator — recompute from scratch.
        return {}
    horizons = parsed.get("horizons")
    if not isinstance(horizons, dict):
        return {}
    valid_labels = {label for label, _ in _HORIZONS}
    # Defense in depth: keep only current-version horizon entries. A mixed-version
    # wrapper should be impossible (writes always stamp the current version on both
    # the wrapper and every horizon's diag), but a stale horizon must never resume.
    return {
        k: v
        for k, v in horizons.items()
        if k in valid_labels
        and isinstance(v, dict)
        and v.get("population_version") == CALIBRATION_POPULATION_VERSION
    }


def _save_time_horizon_wip(rc, horizons_result: dict) -> None:
    """Persist the horizon WIP accumulator wrapped with the current population
    version (Queue #263 Item 2), so a later run can only resume horizons computed
    under the SAME population. Best-effort, mirroring the publish helper."""
    try:
        rc.set(
            _TIME_HORIZON_WIP_KEY,
            json.dumps({
                "population_version": CALIBRATION_POPULATION_VERSION,
                "horizons": horizons_result,
            }),
            ex=_CACHE_TTL,
        )
    except Exception as exc:  # noqa: BLE001 — WIP persistence is best-effort
        logger.warning("time-horizon: WIP persist failed: %s", exc)


def _build_time_horizon_sql(days: int) -> tuple[str, dict]:
    """Build the horizon calibration SQL for one horizon (Queue #262 Item 1).

    Pure string builder (no DB) so it is unit-testable. The horizon population
    REUSES the canonical ``_calibration_population_ctes`` resolved-question
    identity + independent-truth allowlist + artifact exclusions, finalized on the
    horizon SNAPSHOT as the curve price — NOT the terminal ``deduped`` scalar.
    Normalization, field completeness, mode/tail, and bucket assignment are all
    evaluated on this horizon's price. ``market_info`` is scoped to the non-event,
    resolution-date universe so the whole chain runs on the small horizon set;
    ``horizon_price`` is a leading LATERAL selecting each outcome's last snapshot
    at/under the cutoff, INNER-joined into the price-bearing CTEs so ONLY outcomes
    actually priced at this horizon survive. Returns ``(sql, params)``.
    """
    cutoff_expr = (
        "fm.resolution_date"
        if days == 0
        else "fm.resolution_date - make_interval(days => :days)"
    )
    horizon_price_cte = f"""horizon_price AS (
                    SELECT fo.id AS outcome_id, horizon.probability AS horizon_prob
                    FROM futures_outcomes fo
                    JOIN futures_markets fm ON fm.id = fo.market_id
                    LEFT JOIN LATERAL (
                        SELECT fos.probability
                        FROM futures_odds_snapshots fos
                        WHERE fos.outcome_id = fo.id
                          AND fos.captured_at <= {cutoff_expr}
                          AND fos.probability > 0 AND fos.probability < 1
                        ORDER BY fos.captured_at DESC
                        LIMIT 1
                    ) horizon ON true
                    WHERE fm.status = 'resolved'
                      AND fm.event_id IS NULL
                      AND fm.resolution_date IS NOT NULL
                      AND horizon.probability IS NOT NULL
                ),
            """
    population = _calibration_population_ctes(
        curve_price="hp.horizon_prob",
        curve_price_join="JOIN horizon_price hp ON hp.outcome_id = fo.id",
        rn_order="ABS(hp.horizon_prob - 0.5)",
        market_info_extra=(
            "AND fm.event_id IS NULL AND fm.resolution_date IS NOT NULL"
        ),
        leading_ctes=horizon_price_cte,
    )
    sql = (
        "WITH " + population + """,
                h_diag AS (
                    SELECT
                        (SELECT COUNT(*) FROM ranked_outcomes) AS candidate_n,
                        (SELECT COUNT(*) FROM deduped) AS final_n,
                        (SELECT COUNT(DISTINCT vm_id) FROM deduped) AS distinct_questions,
                        (SELECT COUNT(*) FROM ranked_outcomes WHERE NOT is_liquid) AS excl_illiquid,
                        (SELECT COUNT(*) FROM ranked_outcomes WHERE is_poly_placeholder) AS excl_poly_placeholder,
                        (SELECT COUNT(*) FROM ranked_outcomes WHERE is_malformed_binary) AS excl_malformed_binary,
                        (SELECT COUNT(*) FROM ranked_outcomes WHERE is_esports_bundle) AS excl_esports_bundle,
                        (SELECT COUNT(*) FROM ranked_outcomes WHERE is_golf_placeholder) AS excl_golf_placeholder,
                        (SELECT COUNT(*) FROM ranked_outcomes WHERE is_kalshi_prop_threshold) AS excl_kalshi_prop_threshold,
                        (SELECT COUNT(*) FROM ranked_outcomes WHERE is_weather_wide_spread) AS excl_weather_wide_spread,
                        (SELECT COUNT(*) FROM normalized WHERE is_field_incomplete) AS excl_field_incomplete
                ),
                h_buckets AS (
                    SELECT
                        LEAST(FLOOR(adj_opening_probability * 10)::int, 9) AS bucket_idx,
                        source, category,
                        COUNT(*) AS n,
                        SUM(CASE WHEN is_winner THEN 1 ELSE 0 END) AS winners,
                        AVG(adj_opening_probability) AS avg_prob,
                        SUM(adj_opening_probability::float) AS sum_prob,
                        SUM((adj_opening_probability::float - CASE WHEN is_winner THEN 1.0 ELSE 0.0 END)^2) AS sum_sq_err
                    FROM deduped
                    GROUP BY 1, 2, 3
                )
                SELECT b.bucket_idx, b.source, b.category, b.n, b.winners,
                    b.avg_prob, b.sum_prob, b.sum_sq_err,
                    d.candidate_n, d.final_n, d.distinct_questions,
                    d.excl_illiquid, d.excl_poly_placeholder, d.excl_malformed_binary,
                    d.excl_esports_bundle, d.excl_golf_placeholder,
                    d.excl_kalshi_prop_threshold, d.excl_weather_wide_spread,
                    d.excl_field_incomplete
                FROM h_diag d
                LEFT JOIN h_buckets b ON true
                ORDER BY b.bucket_idx, b.source, b.category
            """
    )
    params: dict = {"days": days} if days > 0 else {}
    return sql, params


async def _compute_time_horizon_calibration():
    """Compute time-horizon calibration and store in Redis.

    Bounded + chunked + resumable (Item 1, Queue #220/221): each horizon runs
    under a per-query statement_timeout, completed horizons are persisted to a
    WIP accumulator, and an internal deadline stops the run cleanly (resuming the
    remaining horizons next beat) so it never hits the 600s soft limit again.

    #1171 (Queue #228): each horizon is ISOLATED (a statement_timeout / OOM-adjacent
    DB error on one horizon rolls back and continues — one poison horizon never
    kills the task, gotcha #42), and the served main key is published after EVERY
    completed horizon (partial-first) so the endpoint serves 3/4 horizons instead of
    "computing" forever when one horizon is persistently slow. The WIP cursor is
    only cleared once all four are present."""
    from app.tasks.base import get_task_session
    from app.tasks.redis_state import get_redis_client

    rc = get_redis_client()
    start = time.monotonic()

    # Resume from any WIP accumulator left by a prior (deadline-truncated) run.
    # Queue #263 Item 2: the loader rejects legacy-unwrapped / corrupt / version-
    # mismatched accumulators, so a horizon computed under an older population is
    # recomputed rather than resumed or republished under the current version.
    horizons_result: dict = _load_time_horizon_wip(rc)

    async with get_task_session() as db:
        for label, days in _HORIZONS:
            if label in horizons_result:
                continue  # already computed in an earlier run — resumable cursor

            # Deadline guard: only start a horizon if it can run its full
            # statement_timeout and still finish before the internal deadline.
            # Bounds the longest single uninterrupted op (not just loop
            # boundaries — the budget-guard lesson), so the run always returns
            # cleanly under the 600s soft limit.
            elapsed = time.monotonic() - start
            if elapsed + _HORIZON_STMT_TIMEOUT_S > _HORIZON_DEADLINE_S:
                _save_time_horizon_wip(rc, horizons_result)
                _publish_time_horizon(rc, horizons_result)  # serve partial now (#1171)
                logger.info(
                    "time-horizon: deadline at %.0fs, %d/%d horizons done — "
                    "persisted WIP + published partial, resuming next run",
                    elapsed, len(horizons_result), len(_HORIZONS),
                )
                return {
                    "status": "partial",
                    "horizons_done": len(horizons_result),
                    "total": len(_HORIZONS),
                }

            # Fresh bounded transaction per horizon (mirror _begin_census): roll
            # back any aborted state, then arm the per-query statement_timeout.
            try:
                await db.rollback()
            except Exception:
                pass
            try:
                await db.execute(
                    text(f"SET LOCAL statement_timeout = '{_HORIZON_STMT_TIMEOUT_S}s'")
                )
            except Exception:
                pass

            horizon_sql_str, params = _build_time_horizon_sql(days)
            horizon_sql = text(horizon_sql_str)

            # ISOLATE the one risky op (#1171): the LATERAL probe is what hits the
            # per-horizon statement_timeout — a QueryCanceledError here was
            # previously UNCAUGHT and killed the whole task, so one persistently
            # slow horizon (the poison T-0) blocked all four from ever publishing.
            # Catch, roll back, and DEFER this horizon to the next run; the horizons
            # already computed stay in WIP and are served (gotcha #42: one bad item
            # must never wipe the whole pass).
            try:
                result = await db.execute(horizon_sql, params)
                rows = result.all()
            except Exception as exc:  # noqa: BLE001 — statement_timeout / transient DB
                logger.warning(
                    "time-horizon: horizon %s failed (%s) — rolled back, deferring "
                    "to next run; %d/%d horizons already computed are unaffected",
                    label, type(exc).__name__, len(horizons_result), len(_HORIZONS),
                )
                try:
                    await db.rollback()
                except Exception:
                    pass
                continue

            # Queue #262 Item 1: every row carries the same horizon diagnostics
            # (candidate/final/distinct-question counts + per-reason exclusion
            # counts) via a CROSS-shaped LEFT JOIN, and a diag-only row (bucket_idx
            # NULL) is always present even when no rows survive to a bucket.
            bucket_dicts = []
            diag: dict = {}
            for r in rows:
                if not diag:
                    diag = {
                        "population_version": CALIBRATION_POPULATION_VERSION,
                        "candidate_outcomes": int(r.candidate_n or 0),
                        "final_outcomes": int(r.final_n or 0),
                        "distinct_questions": int(r.distinct_questions or 0),
                        "excluded": {
                            "illiquid": int(r.excl_illiquid or 0),
                            "poly_placeholder": int(r.excl_poly_placeholder or 0),
                            "malformed_binary": int(r.excl_malformed_binary or 0),
                            "esports_bundle": int(r.excl_esports_bundle or 0),
                            "golf_placeholder": int(r.excl_golf_placeholder or 0),
                            "kalshi_prop_threshold": int(r.excl_kalshi_prop_threshold or 0),
                            "weather_wide_spread": int(r.excl_weather_wide_spread or 0),
                            "field_incomplete": int(r.excl_field_incomplete or 0),
                        },
                    }
                if r.bucket_idx is None:
                    continue  # diag-only row — no surviving buckets this horizon
                ci_lo, ci_hi = _wilson_ci(r.winners, r.n)
                bucket_dicts.append({
                    "bucket_idx": r.bucket_idx,
                    "source": r.source,
                    "category": r.category,
                    "n": r.n,
                    "winners": r.winners,
                    "avg_prob": round(float(r.avg_prob), 4),
                    "sum_prob": round(float(r.sum_prob), 4),
                    "sum_sq_err": round(float(r.sum_sq_err), 4),
                    "ci_lower": round(ci_lo, 4),
                    "ci_upper": round(ci_hi, 4),
                })

            total_n = sum(b["n"] for b in bucket_dicts)
            total_winners = sum(b["winners"] for b in bucket_dicts)

            if total_n < _MIN_OUTCOMES_PER_HORIZON:
                horizons_result[label] = {
                    "buckets": bucket_dicts,
                    "total_outcomes": total_n,
                    "total_winners": total_winners,
                    "mce": None,
                    "mce_ci_lower": None,
                    "mce_ci_upper": None,
                    "skipped": True,
                    "skip_reason": f"Only {total_n} outcomes (minimum {_MIN_OUTCOMES_PER_HORIZON})",
                    **diag,
                }
                _save_time_horizon_wip(rc, horizons_result)
                _publish_time_horizon(rc, horizons_result)  # serve partial (#1171)
                continue

            # Aggregate for MCE
            agg: dict[int, dict] = {}
            for b in bucket_dicts:
                idx = b["bucket_idx"]
                if idx not in agg:
                    agg[idx] = {"n": 0, "winners": 0, "sum_prob": 0.0}
                agg[idx]["n"] += b["n"]
                agg[idx]["winners"] += b["winners"]
                agg[idx]["sum_prob"] += b["sum_prob"]

            mce = _compute_horizon_mce([
                {"n": v["n"], "winners": v["winners"], "sum_prob": v["sum_prob"]}
                for v in agg.values()
            ])

            # Bootstrap CI
            agg_list = [
                {"n": v["n"], "winners": v["winners"],
                 "avg_prob": v["sum_prob"] / v["n"]}
                for v in agg.values() if v["n"] > 0
            ]
            mce_ci_lo, mce_ci_hi = _bootstrap_mce_ci(agg_list)

            # Per-source MCE
            by_source: dict[str, dict[int, dict]] = {}
            for b in bucket_dicts:
                src = b["source"]
                idx = b["bucket_idx"]
                if src not in by_source:
                    by_source[src] = {}
                if idx not in by_source[src]:
                    by_source[src][idx] = {"n": 0, "winners": 0, "sum_prob": 0.0}
                by_source[src][idx]["n"] += b["n"]
                by_source[src][idx]["winners"] += b["winners"]
                by_source[src][idx]["sum_prob"] += b["sum_prob"]
            mce_by_source = {}
            for src, src_agg in by_source.items():
                src_total = sum(v["n"] for v in src_agg.values())
                if src_total >= _MIN_OUTCOMES_PER_HORIZON:
                    mce_by_source[src] = _compute_horizon_mce([
                        {"n": v["n"], "winners": v["winners"], "sum_prob": v["sum_prob"]}
                        for v in src_agg.values()
                    ])

            # Per-category MCE
            by_cat: dict[str, dict[int, dict]] = {}
            for b in bucket_dicts:
                cat = b["category"]
                idx = b["bucket_idx"]
                if cat not in by_cat:
                    by_cat[cat] = {}
                if idx not in by_cat[cat]:
                    by_cat[cat][idx] = {"n": 0, "winners": 0, "sum_prob": 0.0}
                by_cat[cat][idx]["n"] += b["n"]
                by_cat[cat][idx]["winners"] += b["winners"]
                by_cat[cat][idx]["sum_prob"] += b["sum_prob"]
            mce_by_category = {}
            for cat, cat_agg in by_cat.items():
                cat_total = sum(v["n"] for v in cat_agg.values())
                if cat_total >= _MIN_OUTCOMES_PER_HORIZON:
                    mce_by_category[cat] = _compute_horizon_mce([
                        {"n": v["n"], "winners": v["winners"], "sum_prob": v["sum_prob"]}
                        for v in cat_agg.values()
                    ])

            horizons_result[label] = {
                "buckets": bucket_dicts,
                "total_outcomes": total_n,
                "total_winners": total_winners,
                "mce": mce,
                "mce_ci_lower": round(mce_ci_lo * 100, 2),
                "mce_ci_upper": round(mce_ci_hi * 100, 2),
                "mce_by_source": mce_by_source,
                "mce_by_category": mce_by_category,
                **diag,
            }
            # Persist immediately so a later horizon's slowness (or the deadline
            # guard firing next iteration) can never discard this one — and publish
            # the served main key NOW so the endpoint reflects each horizon as it
            # lands, never stranded on "computing" if a later horizon dies (#1171).
            _save_time_horizon_wip(rc, horizons_result)
            _publish_time_horizon(rc, horizons_result)

    # Publish whatever is computed. When all four are present this is the full
    # payload and the WIP cursor is cleared; otherwise it is an honest PARTIAL
    # (``complete: false``, ``missing: [...]``) that the endpoint still serves —
    # the missing horizon(s) retry next run (#1171: never publish nothing).
    _publish_time_horizon(rc, horizons_result)
    # Queue #263 Item 2: complete requires all four named horizons AND every one to
    # carry the current population version — so a run that somehow still holds a
    # stale-version horizon is reported partial (and its WIP is NOT cleared) rather
    # than declared done. In practice the loader already drops off-version horizons,
    # so this is a belt-and-braces invariant on the exit path.
    complete = len(horizons_result) == len(_HORIZONS) and all(
        isinstance(horizons_result.get(label), dict)
        and horizons_result[label].get("population_version")
        == CALIBRATION_POPULATION_VERSION
        for label, _ in _HORIZONS
    )
    if complete:
        rc.delete(_TIME_HORIZON_WIP_KEY)
    logger.info(
        "time-horizon: published %d/%d horizons (%s)",
        len(horizons_result), len(_HORIZONS), "complete" if complete else "partial",
    )
    return {
        "status": "ok" if complete else "partial",
        "horizons": len(horizons_result),
        "total": len(_HORIZONS),
    }


# ---------------------------------------------------------------------------
# Fair-fight comparison precomputation
# ---------------------------------------------------------------------------

# Minimum shared markets to report a pair
_MIN_SHARED = 100


def _compute_mce(probs: list[float], outcomes: list[bool]) -> float | None:
    if not probs:
        return None
    bucket_n: dict[int, int] = {}
    bucket_sum_prob: dict[int, float] = {}
    bucket_winners: dict[int, int] = {}
    for p, won in zip(probs, outcomes):
        idx = min(int(p * 10), 9)
        bucket_n[idx] = bucket_n.get(idx, 0) + 1
        bucket_sum_prob[idx] = bucket_sum_prob.get(idx, 0.0) + p
        bucket_winners[idx] = bucket_winners.get(idx, 0) + (1 if won else 0)
    if not bucket_n:
        return None
    total_abs_err = 0.0
    k = 0
    for idx in bucket_n:
        n = bucket_n[idx]
        avg_prob = bucket_sum_prob[idx] / n
        actual = bucket_winners[idx] / n
        total_abs_err += abs(actual - avg_prob)
        k += 1
    return round(total_abs_err / k * 100, 2) if k > 0 else None


# Kalshi prop filter — same as source_intelligence.py
_KALSHI_PROP_FILTER = """
    AND NOT (
        wp.source = 'kalshi'
        AND wp.game_state->>'market_name' IS NOT NULL
        AND (
            wp.game_state->>'market_name' ILIKE '%spread%'
            OR wp.game_state->>'market_name' ILIKE '%total%'
            OR wp.game_state->>'market_name' ILIKE '%overtime%'
            OR wp.game_state->>'market_name' ILIKE '%half winner%'
            OR wp.game_state->>'market_name' ILIKE '%half total%'
            OR wp.game_state->>'market_name' ILIKE '%half spread%'
            OR wp.game_state->>'market_name' ILIKE '% points%'
            OR wp.game_state->>'market_name' ILIKE '% rebounds%'
            OR wp.game_state->>'market_name' ILIKE '% assists%'
            OR wp.game_state->>'market_name' ILIKE '% steals%'
            OR wp.game_state->>'market_name' ILIKE '% blocks%'
            OR wp.game_state->>'market_name' ILIKE '%three pointer%'
            OR wp.game_state->>'market_name' ILIKE '%double double%'
            OR wp.game_state->>'market_name' ILIKE '%triple double%'
            OR wp.game_state->>'market_name' ILIKE '%leader%'
            OR wp.game_state->>'market_name' ILIKE '%strikeout%'
            OR wp.game_state->>'market_name' ILIKE '%home run%'
        )
    )
"""


async def _query_futures_fair_fight_impl(db):
    """Paired MCE comparison for Kalshi vs Polymarket on futures markets.

    Rewrite (#197 fair-fight profile): the previous version built a 432K-row
    ``source_questions`` CTE, then SELF-JOINED it three ways (group_pairs,
    key_pairs, and a correlated NOT EXISTS). Because the CTE is referenced
    multiple times, Postgres MATERIALIZES it — so those self-joins run over an
    UN-INDEXED 432K-row spool and blow the soft limit (0 successes / 12 consec
    timeouts). Prod profiling (2026-07-14) proved two things:

      1. The ``group_id`` arm matches NOTHING and never can: kalshi group_ids are
         prefixed ``kalshi:...`` and polymarket ``polymarket:<event_id>`` — the
         namespaces are structurally disjoint (0 cross-source matches). The arm
         (and the NOT EXISTS that references it) was pure dead weight.
      2. The composite index the pairing wants already exists
         (``ix_fm_canonical_source_count (canonical_market_key, source) WHERE
         canonical_market_key IS NOT NULL``).

    So we drop the dead group arm and discover shared canonical keys with a
    single index-driven GROUP BY on the base table (measured ~0.3s vs the old
    self-join blowup). Output is identical to the old key arm (the group arm
    contributed nothing). Pair-discovery is now sub-second; the join to
    futures_outcomes is the only remaining cost.

    NOTE for maintainers: shared canonical keys are dominated by GENERIC bucket
    keys (e.g. ``basketball::championship:2026`` is shared by ~47K markets), so
    this pairs broad category buckets, not one-question-to-one-question. That is
    a pre-existing pairing-granularity concern for the fair-fight surface, not
    something this perf rewrite changes.
    """
    sql = text("""
        WITH key_pairs AS (
            -- Shared canonical keys covered by BOTH sources. Index-driven
            -- aggregation on the base table (ix_fm_canonical_source_count),
            -- replacing the materialized-CTE self-join. Category is taken from
            -- the kalshi side, matching the old sq1.category semantics.
            SELECT
                fm.canonical_market_key AS match_key,
                MIN(COALESCE(fm.llm_sport_category, 'uncategorized'))
                    FILTER (WHERE fm.source = 'kalshi') AS category
            FROM futures_markets fm
            WHERE fm.status = 'resolved'
              AND fm.source IN ('kalshi', 'polymarket')
              AND fm.canonical_market_key IS NOT NULL
            GROUP BY fm.canonical_market_key
            HAVING COUNT(*) FILTER (WHERE fm.source = 'kalshi') > 0
               AND COUNT(*) FILTER (WHERE fm.source = 'polymarket') > 0
        ),
        matched_outcomes AS (
            SELECT
                kp.category,
                fm.source,
                COALESCE(fo.calibration_probability, fo.opening_probability) AS prob,
                fo.is_winner
            FROM key_pairs kp
            JOIN futures_markets fm ON fm.canonical_market_key = kp.match_key
            JOIN futures_outcomes fo ON fo.market_id = fm.id
            WHERE fm.status = 'resolved'
              AND fm.source IN ('kalshi', 'polymarket')
              AND fo.opening_probability IS NOT NULL
              AND fo.opening_probability > 0 AND fo.opening_probability < 1
              -- Queue #262 Item 3: replace the legacy NOT-IN denylist with the
              -- single independent-truth allowlist (resolution_authority) so a
              -- price-derived (clean_resolution / settlement_sync), guess, void, or
              -- unknown winner can never grade a fair-fight row either. Read-side
              -- only (gotcha #21).
              AND fo.resolution_source IN """ + CALIBRATION_TRUTH_ELIGIBLE_SOURCES_SQL + """
              AND COALESCE(fo.volume, -1) != 0
        )
        SELECT source, category, prob, is_winner
        FROM matched_outcomes
        WHERE prob IS NOT NULL AND prob > 0 AND prob < 1
        ORDER BY source, category
    """)
    result = await db.execute(sql)
    rows = result.all()

    by_cat: dict[str, dict[str, tuple[list[float], list[bool]]]] = {}
    for r in rows:
        cat = r.category
        src = r.source
        if cat not in by_cat:
            by_cat[cat] = {}
        if src not in by_cat[cat]:
            by_cat[cat][src] = ([], [])
        by_cat[cat][src][0].append(float(r.prob))
        by_cat[cat][src][1].append(bool(r.is_winner))

    all_kalshi_probs: list[float] = []
    all_kalshi_outcomes: list[bool] = []
    all_poly_probs: list[float] = []
    all_poly_outcomes: list[bool] = []
    by_category: list[dict] = []

    for cat, sources in sorted(by_cat.items()):
        k_data = sources.get("kalshi")
        p_data = sources.get("polymarket")
        if not k_data or not p_data:
            continue
        k_probs, k_wins = k_data
        p_probs, p_wins = p_data
        shared_n = min(len(k_probs), len(p_probs))
        if shared_n < 10:
            continue
        all_kalshi_probs.extend(k_probs)
        all_kalshi_outcomes.extend(k_wins)
        all_poly_probs.extend(p_probs)
        all_poly_outcomes.extend(p_wins)
        k_mce = _compute_mce(k_probs, k_wins)
        p_mce = _compute_mce(p_probs, p_wins)
        if k_mce is not None and p_mce is not None:
            by_category.append({
                "category": cat,
                "kalshi_n": len(k_probs),
                "polymarket_n": len(p_probs),
                "mce_kalshi": k_mce,
                "mce_polymarket": p_mce,
            })

    pairs = []
    # Queue #262 Item 3: min(row counts) is NOT a matched-market count, and the
    # canonical keys are dominated by generic category buckets (not one-question-
    # to-one-question), so NO winner/advantage is emitted — that claim would reflect
    # population + weighting, not source skill. The per-source MCEs stay as clearly-
    # labeled diagnostics with an explicit unavailable reason. min-count still gates
    # whether there is enough data to bother reporting the diagnostic.
    total_pooled = min(len(all_kalshi_probs), len(all_poly_probs))
    if total_pooled >= _MIN_SHARED:
        mce_k = _compute_mce(all_kalshi_probs, all_kalshi_outcomes)
        mce_p = _compute_mce(all_poly_probs, all_poly_outcomes)
        if mce_k is not None and mce_p is not None:
            pairs.append({
                "source_a": "kalshi",
                "source_b": "polymarket",
                "comparison_available": False,
                "reason": (
                    "canonical keys are generic category buckets, not "
                    "one-question-to-one-question matches; winner withheld"
                ),
                # honest per-source pooled counts — NOT a matched-market count.
                "kalshi_rows": len(all_kalshi_probs),
                "polymarket_rows": len(all_poly_probs),
                "mce_a": mce_k,
                "mce_b": mce_p,
                "by_category": [c for c in by_category if c["kalshi_n"] >= 20],
            })
    return pairs


async def _query_sports_fair_fight_impl(db):
    """Paired MCE comparison for prediction markets vs Odds API on sports events."""
    sql = text(f"""
        WITH wp_closing AS (
            SELECT DISTINCT ON (wp.event_id, wp.source)
                wp.event_id, wp.source, wp.home_win_probability
            FROM win_prob_snapshots wp
            JOIN events e ON e.id = wp.event_id
            WHERE e.status IN ('completed', 'closed')
              AND e.home_score IS NOT NULL AND e.away_score IS NOT NULL
              AND e.home_score != e.away_score
              AND wp.source IN ('kalshi', 'polymarket')
              AND wp.home_win_probability IS NOT NULL
              AND wp.home_win_probability > 0
              AND wp.home_win_probability < 1
              {_KALSHI_PROP_FILTER}
            ORDER BY wp.event_id, wp.source, wp.captured_at DESC
        )
        SELECT
            wc.event_id, wc.source AS pm_source,
            wc.home_win_probability AS pm_prob,
            COALESCE(e.closing_home_probability, e.opening_home_probability) AS odds_prob,
            (e.home_score > e.away_score) AS home_won,
            s.key AS sport
        FROM wp_closing wc
        JOIN events e ON e.id = wc.event_id
        JOIN sports s ON s.id = e.sport_id
        WHERE COALESCE(e.closing_home_probability, e.opening_home_probability) IS NOT NULL
          AND COALESCE(e.closing_home_probability, e.opening_home_probability) > 0
          AND COALESCE(e.closing_home_probability, e.opening_home_probability) < 1
        ORDER BY wc.source, s.key
    """)
    result = await db.execute(sql)
    rows = result.all()

    by_src: dict[str, dict[str, dict]] = {}
    for r in rows:
        src = r.pm_source
        sport = r.sport
        if src not in by_src:
            by_src[src] = {}
        if sport not in by_src[src]:
            by_src[src][sport] = {
                "pm_probs": [], "pm_outcomes": [],
                "odds_probs": [], "odds_outcomes": [],
            }
        won = bool(r.home_won)
        by_src[src][sport]["pm_probs"].append(float(r.pm_prob))
        by_src[src][sport]["pm_outcomes"].append(won)
        by_src[src][sport]["odds_probs"].append(float(r.odds_prob))
        by_src[src][sport]["odds_outcomes"].append(won)

    pairs = []
    for pm_source, sports_data in sorted(by_src.items()):
        all_pm_probs: list[float] = []
        all_pm_outcomes: list[bool] = []
        all_odds_probs: list[float] = []
        all_odds_outcomes: list[bool] = []
        by_sport: list[dict] = []

        for sport, data in sorted(sports_data.items()):
            n = len(data["pm_probs"])
            if n < 10:
                continue
            all_pm_probs.extend(data["pm_probs"])
            all_pm_outcomes.extend(data["pm_outcomes"])
            all_odds_probs.extend(data["odds_probs"])
            all_odds_outcomes.extend(data["odds_outcomes"])
            mce_pm = _compute_mce(data["pm_probs"], data["pm_outcomes"])
            mce_odds = _compute_mce(data["odds_probs"], data["odds_outcomes"])
            if mce_pm is not None and mce_odds is not None:
                by_sport.append({
                    "category": sport,
                    f"{pm_source}_n": n,
                    "odds_api_n": n,
                    f"mce_{pm_source}": mce_pm,
                    "mce_odds_api": mce_odds,
                })

        total = len(all_pm_probs)
        if total >= _MIN_SHARED:
            mce_pm = _compute_mce(all_pm_probs, all_pm_outcomes)
            mce_odds = _compute_mce(all_odds_probs, all_odds_outcomes)
            if mce_pm is not None and mce_odds is not None:
                # Queue #262 Item 3: these ARE per-event matched questions (same
                # game), so matched_questions is honest — but the MCE here is
                # equal-per-bucket, NOT the outcome-weighted headline metric, so a
                # winner would use a metric different from the headline definition.
                # Winner withheld until the comparison reuses the headline metric
                # (deliberately NOT rebuilt in this containment queue).
                pairs.append({
                    "source_a": pm_source,
                    "source_b": "odds_api",
                    "comparison_available": False,
                    "reason": (
                        "MCE is equal-per-bucket, not the outcome-weighted headline "
                        "metric; winner withheld"
                    ),
                    "matched_questions": total,
                    "mce_a": mce_pm,
                    "mce_b": mce_odds,
                    "by_category": [s for s in by_sport if s.get(f"{pm_source}_n", 0) >= 20],
                })
    return pairs


async def _compute_fair_fight_comparison():
    """Compute fair-fight comparison and store in Redis."""
    from app.tasks.base import get_task_session
    from app.tasks.redis_state import get_redis_client

    # Each MCE query runs in its OWN session with a per-statement timeout. The
    # task was tripping its 600s soft limit (SoftTimeLimitExceeded, consec 12):
    # the heavy paired-coverage scans ran away, and a shared session meant one
    # aborted transaction poisoned the other query's commit-on-exit. Own-session
    # + 240s statement_timeout bounds each scan well under the soft limit and
    # isolates failures so a slow half degrades to [] instead of failing the
    # whole task (advisory Redis surface — partial > red).
    async def _run_bounded(impl, label):
        try:
            async with get_task_session() as db:
                await db.execute(text("SET LOCAL statement_timeout = '240s'"))
                return await impl(db)
        except Exception:
            logger.exception("fair-fight precompute: %s query failed", label)
            return []

    futures_pairs = await _run_bounded(_query_futures_fair_fight_impl, "futures")
    sports_pairs = await _run_bounded(_query_sports_fair_fight_impl, "sports")

    response = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        # Queue #262 Item 3: the winner claim is CONTAINED. A source winner is only
        # meaningful when both sources are scored on the SAME one-question-to-one-
        # question set with the headline metric. The futures pairing is generic
        # canonical-key buckets (not question-paired) and both paths use a
        # non-headline equal-per-bucket MCE, so no winner/advantage is emitted —
        # only clearly-labeled diagnostic MCEs. Callers must treat this surface as
        # comparison-unavailable until an exact matched-question rebuild lands.
        "comparison_available": False,
        "unavailable_reason": (
            "Source winner withheld: fair-fight is not yet one-question-to-one-"
            "question with the headline metric (Queue #262 Item 3 containment)."
        ),
        "population_version": CALIBRATION_POPULATION_VERSION,
        "methodology": (
            "Diagnostic per-source MCE only. Winner/advantage are intentionally "
            "absent: the futures pairing groups generic canonical-key buckets (not "
            "matched questions), and the MCE is equal-per-bucket, not the outcome-"
            "weighted headline metric. Do not present these numbers as a source "
            "ranking."
        ),
        "min_shared_threshold": _MIN_SHARED,
        "pairs": futures_pairs + sports_pairs,
    }

    rc = get_redis_client()
    rc.set("bainluck:calibration:fair_fight", json.dumps(response), ex=_CACHE_TTL)
    logger.info("Cached fair-fight comparison in Redis")
    return {"status": "ok", "pairs": len(futures_pairs) + len(sports_pairs)}


async def _snapshot_coverage_metrics():
    """Daily snapshot of coverage metrics for tracking progress over time.

    Stores one row per day in a Redis sorted set keyed by date. Each row
    captures opening_probability, is_winner, and calibration_probability
    coverage per source and time window. This lets us answer "is coverage
    improving?" without re-running heavy queries.
    """
    from app.tasks.base import get_task_session
    from app.tasks.redis_state import get_redis_client

    stats = {"snapshots": 0, "errors": []}

    try:
        async with get_task_session() as session:
            result = await session.execute(
                text("""
                    SELECT
                        fm.source,
                        CASE
                            WHEN fm.resolution_date >= NOW() - INTERVAL '7 days' THEN '7d'
                            WHEN fm.resolution_date >= NOW() - INTERVAL '30 days' THEN '30d'
                            ELSE '90d+'
                        END AS age_bucket,
                        s.key AS league,
                        COUNT(*) AS total_resolved,
                        COUNT(fo.opening_probability) AS has_opening,
                        COUNT(fo.calibration_probability) AS has_cal_prob,
                        COUNT(CASE WHEN fo.is_winner IS NOT NULL THEN 1 END) AS has_winner,
                        AVG(CASE WHEN snap_counts.cnt IS NOT NULL THEN snap_counts.cnt ELSE 0 END)::int AS avg_snapshots
                    FROM futures_outcomes fo
                    JOIN futures_markets fm ON fo.market_id = fm.id
                    LEFT JOIN sports s ON s.id = fm.sport_id
                    LEFT JOIN LATERAL (
                        SELECT COUNT(*) AS cnt
                        FROM futures_odds_snapshots fos
                        WHERE fos.outcome_id = fo.id
                    ) snap_counts ON true
                    WHERE fm.status = 'resolved'
                      AND fm.resolution_date IS NOT NULL
                    GROUP BY fm.source, age_bucket, s.key
                    ORDER BY fm.source, age_bucket, total_resolved DESC
                """)
            )
            rows = result.fetchall()

            snapshot = {
                "date": datetime.now(timezone.utc).strftime("%Y-%m-%d"),
                "computed_at": datetime.now(timezone.utc).isoformat(),
                "by_source_age_league": [
                    {
                        "source": r.source,
                        "age": r.age_bucket,
                        "league": r.league or "unknown",
                        "total": r.total_resolved,
                        "has_opening": r.has_opening,
                        "has_cal_prob": r.has_cal_prob,
                        "has_winner": r.has_winner,
                        "avg_snapshots": r.avg_snapshots,
                    }
                    for r in rows
                ],
                "totals": {},
            }

            from collections import defaultdict
            by_source = defaultdict(lambda: {"total": 0, "opening": 0, "cal_prob": 0, "winner": 0})
            for r in rows:
                by_source[r.source]["total"] += r.total_resolved
                by_source[r.source]["opening"] += r.has_opening
                by_source[r.source]["cal_prob"] += r.has_cal_prob
                by_source[r.source]["winner"] += r.has_winner

            snapshot["totals"] = {
                src: {
                    "total": s["total"],
                    "opening_pct": round(100 * s["opening"] / max(s["total"], 1), 1),
                    "cal_prob_pct": round(100 * s["cal_prob"] / max(s["total"], 1), 1),
                    "winner_pct": round(100 * s["winner"] / max(s["total"], 1), 1),
                }
                for src, s in by_source.items()
            }

            rc = get_redis_client()
            date_key = snapshot["date"]
            rc.hset("bainluck:coverage_snapshots", date_key, json.dumps(snapshot))
            rc.expire("bainluck:coverage_snapshots", 90 * 86400)

            stats["snapshots"] = len(rows)
            logger.info(
                "Coverage snapshot: %s — %s",
                date_key,
                {src: f'{s["cal_prob_pct"]}% cal_prob' for src, s in snapshot["totals"].items()},
            )

            # NOTE (#1199): the backfill-winners/status cache (key
            # `bainluck:backfill_winners_status`) used to be piggybacked here as a
            # second heavy `market_status` CTE. That inline block was removed — the
            # dedicated `precompute_backfill_winners_status` task now owns that key,
            # runs HOURLY at :35 with a 2h TTL (always fresh), and writes the exact
            # same shape. Running the CTE again here was pure duplicate compute and
            # was the second heavy query occasionally pushing this daily snapshot
            # over its 600s soft_time_limit (~1/24h SoftTimeLimitExceeded). With it
            # gone the task runs a single LATERAL scan and completes well under the
            # limit. Do NOT re-add it here.

    except Exception as e:
        stats["errors"].append(str(e)[:200])
        logger.error("Coverage snapshot error: %s", e)

    return stats
