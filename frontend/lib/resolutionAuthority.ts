/**
 * Resolution AUTHORITY — the frontend mirror of the tier-3 set in
 * `backend/app/utils/resolution_authority.py`.
 *
 * ## Why a renderer needs this at all (#6082)
 *
 * `futures_markets.status` is a MARKET-level fact and `futures_outcomes.is_winner`
 * is a LEG-level one, and a threshold ladder is precisely the shape where the two
 * come apart: on `/futures/261` ("Boston pro baseball wins this season?") Kalshi
 * had already settled `80+ wins` and `75+ wins` YES while the market itself was
 * legitimately still `open`, because the parent question runs to Nov 8 and
 * `90+ wins` genuinely traded at 19%.
 *
 * Gating the leg's verdict on the market's status therefore printed a PRICE where
 * a RESULT belonged — `LATEST 99%` on a rung the venue had already called — and
 * because both numbers were pre-settlement relics rather than live prices, the
 * page drew `≥ 75  98%` directly above `≥ 80  99%`. P(≥75) cannot be below
 * P(≥80); a reader does not need to know what a threshold ladder is to see it.
 * Measured on production 2026-09-14: 2,428 legs on 797 still-open markets carry
 * `is_winner IS TRUE` + `resolution_source = 'api_settlement'`, 1,738 of them
 * priced under 99.5%.
 *
 * ## The rule is the backend's, not a fourth private one
 *
 * `can_write_winner` (#845) is the codebase's answer to "may a winner stand here?"
 * and it has exactly two arms: a market that has actually settled, OR — regardless
 * of market status — an AUTHORITATIVE (tier-3) external settlement, which is
 * self-justifying because the venue said so. `_outcome_is_settled` in
 * `routes/league_futures.py` already renders on that rule and names this very
 * case ("the Alcaraz child is `status='open'` with `api_settlement`, which is
 * tier 3 and self-justifying"). This file exists so the web renderer can ask the
 * same question instead of approximating it with a status flag.
 *
 * 🔴 TIER 3 ONLY, AND THAT IS THE WHOLE POINT OF THE SET. A non-empty source is
 * not a grade (CERT-2222 / CERT-2517). The tiers below 3 are exactly the ones
 * that must NOT crown a leg on a market that is still trading:
 *   - tier 1 `ungradeable_result` is a RETRACTION — refused first and
 *     unconditionally by `outcomeRowVerdict`, before this function is consulted;
 *   - tier 0 is the guess family (#754), heuristic inferences with no cited
 *     authority, which the backend actively CLEARS off open markets
 *     (`_clear_premature_open_winners`).
 * An unknown source is not in the set and so is refused — fail-safe, matching
 * `authority_tier`'s `_UNKNOWN_TIER` sentinel.
 *
 * Kept byte-identical to `AUTHORITATIVE_SOURCES` by
 * `__tests__/lib/resolutionAuthorityMirror6082.test.ts`, which parses the Python
 * frozenset and compares the two sets both directions — the same drift discipline
 * `RETRACTED_RESOLUTION_SOURCE` gets from
 * `backend/tests/test_futures_serves_resolution_source_4788.py`. A source added
 * to one side and missed on the other is how a renderer starts crowning legs the
 * backend would refuse, and nothing else would catch it.
 */

/**
 * Tier 3 — external settlement: the venue's OWN settled result (API/CLOB). The
 * strongest authority; nothing may overwrite these.
 *
 * Mirror of `AUTHORITATIVE_SOURCES` in `app/utils/resolution_authority.py`.
 */
export const AUTHORITATIVE_RESOLUTION_SOURCES: ReadonlySet<string> = new Set([
  "api_settlement",
  "clob_authoritative",
  "clob_field_repair",
  "clob_never_graded",
  "clob_ordinal",
  "datagolf_settlement",
  "settlement_sync",
]);

/**
 * Is this `resolution_source` an external venue settlement (tier 3)?
 *
 * `null`/`undefined`/unknown → `false`. Absence of a source is absence of a
 * grader, and an unclassified source is refused rather than trusted.
 */
export function isAuthoritativeResolution(
  source: string | null | undefined,
): boolean {
  return source != null && AUTHORITATIVE_RESOLUTION_SOURCES.has(source);
}
