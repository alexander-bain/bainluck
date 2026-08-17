"use strict";

/**
 * UX-P087 (#1860) — the league page's PARTITION, restated for the browser rail.
 *
 * ── WHY A RESTATEMENT AND NOT AN IMPORT ──
 *
 * `frontend/lib/leagueCards.ts` is the code under test. A rail that imported it
 * would be comparing production against the very function production reads and
 * asserting nothing — the constant-oracle family (gotcha #121). So the rules the
 * component uses to decide "is this market a binary / a date ladder" are stated
 * again here, independently, and `frontend/__tests__/lib/leagueCardOracleParity.test.ts`
 * runs both implementations over the SAME production payload and fails when they
 * disagree. Independence is what makes the rail an instrument; the parity test is
 * what keeps the independent copy honest.
 *
 * ── THE DEFECT THIS FILE EXISTS TO END (measured, run 32055873206) ──
 *
 * The first league-cards run that ever reached the page failed with:
 *
 *     15 binary/ies must occupy at most 15 rows; 16 rows means the two-row
 *     (Yes AND No) presentation is back.  Expected <= 15, Received 16
 *
 * It was read as a ruling-047 regression. It was not. Measured against
 * `GET /api/leagues/baseball_mlb` the same hour, the page rendered SIXTEEN
 * binaries as SIXTEEN rows — one row each, exactly as retrofit 3 requires. The
 * sixteenth is "Shohei Ohtani: Cy Young and MVP Winner", a ONE-SIDED market
 * carrying a single `Yes 1%` outcome. `binaryAnswer` counts it deliberately and
 * says so in its own docstring; the rail's restatement required `length === 2`
 * and did not.
 *
 * The old restatement justified that gap in its header:
 *
 *     "Both are intentionally stricter than the component's, so this oracle
 *      UNDER-counts rather than over-counts and the DOM assertions below stay
 *      floors."
 *
 * **That reasoning is sound for a floor and inverted for a ceiling.** Two of the
 * three assertions were `toBeGreaterThan` — an under-count only makes those
 * easier, which is the safe direction. The binary assertion was
 * `toBeLessThanOrEqual(owed.binaries)`, a CEILING, and an under-counting oracle
 * lowers a ceiling onto a correct page. One one-sided market was all it took to
 * red the rail and send a lane hunting a regression that did not exist.
 *
 * So the rule here is:
 *
 *   **An oracle is only "safely strict" in the direction of the assertion that
 *   consumes it. State the rule FAITHFULLY and let the assertion be exact.**
 *
 * A faithful restatement is also what lets the binary assertion become an
 * equality, which matters for a reason the ceiling could never cover: with
 * `rows <= owed`, a page that dropped every binary row rendered ZERO rows and
 * PASSED. The instrument could not see the shape disappearing at all.
 *
 * ── DELIBERATE LIMITS ──
 *
 * These read `top_outcomes`, which is the truncated, probability-sorted list the
 * envelope carries — the same list the component partitions on. They are a
 * statement about what the PAGE owes, not about the market's full outcome set.
 */

/** Ruling 047's yes/no shapes. Matched by NAME, never by rank. */
const YES = /^yes$/i;
const NO = /^no$/i;

/**
 * "Before Nov 1, 2029" / "By Aug 1, 2030" / "After May 1, 2028".
 *
 * All five direction words the component accepts. The previous restatement took
 * only `before`, which under-counted ladders — harmless while the ladder
 * assertion was a floor, and the same latent trap as the binary one.
 */
const LADDER_PREFIX = /^(before|by|on or before|after|on or after)\s+(.{4,})$/i;

/** A ladder needs rungs. Two dates are a pair of props, not a ladder. */
const MIN_LADDER_OUTCOMES = 3;

function names(market) {
  return (market.top_outcomes || []).map((o) => ((o && o.name) || "").trim());
}

/**
 * Is this market a single yes/no question?
 *
 * One or two outcomes, drawn from {Yes, No}; a two-outcome market must carry
 * BOTH (two outcomes that are not a Yes/No pair are two real answers — a playoff
 * series is "Dodgers or Padres" — and those keep both rows). A one-sided market
 * priced on only one side is still one question with one answer, and one row is
 * already the right number of rows for it.
 */
function isBinary(market) {
  const outs = names(market);
  if (outs.length === 0 || outs.length > 2) return false;
  const yes = outs.some((n) => YES.test(n));
  const no = outs.some((n) => NO.test(n));
  return outs.length === 2 ? yes && no : yes || no;
}

/**
 * Is this market one question asked at three or more dated thresholds?
 *
 * EVERY outcome must parse as a dated threshold. A market where three of five
 * rungs are dates and the rest are something else is not a ladder, and grading
 * it as one would assert an order over rows the oracle could not read.
 */
function isDateLadder(market) {
  const outs = names(market);
  if (outs.length < MIN_LADDER_OUTCOMES) return false;
  return outs.every((n) => {
    const m = LADDER_PREFIX.exec(n);
    return m ? Number.isFinite(Date.parse(m[2].trim())) : false;
  });
}

/**
 * Flatten a `/api/leagues/{key}` body to its market list.
 *
 * The server sends `sections` as a MAPPING — `{"awards": [...], "props": [...],
 * "more_markets": [...]}` — and no top-level `markets` key. A reader that merely
 * TOLERATED an unexpected shape would return `[]`, zero every count, and make
 * every downstream assertion vacuously true; #1860's first repair nearly shipped
 * exactly that. A shape this oracle cannot read is a fact about the oracle, and
 * it must say so out loud.
 */
function leagueMarkets(body) {
  if (body && Array.isArray(body.markets)) return body.markets;
  if (body && body.sections && typeof body.sections === "object" && !Array.isArray(body.sections)) {
    return Object.values(body.sections).flatMap((list) => (Array.isArray(list) ? list : []));
  }
  const keys = body && typeof body === "object" ? Object.keys(body).join(", ") : String(body);
  throw new Error(
    `league payload carries neither a 'markets' array nor a 'sections' mapping — ` +
      `top-level keys were [${keys}]. The oracle cannot grade the page against a ` +
      `payload it cannot read, and reading zero markets would make every ` +
      `assertion vacuously true.`,
  );
}

/**
 * What the page OWES for this payload: the exact number of each ruled shape.
 *
 * `games` stays a brief rather than an exact contract — the rails are paginated
 * (`upcoming_games_has_more`), so the payload's count is what is available, not
 * what must be on screen. The two market shapes are exact: the whole section is
 * serialised, so every binary and every ladder in it is owed a place.
 */
function leagueOwed(body) {
  const markets = leagueMarkets(body);
  return {
    binaries: markets.filter(isBinary).length,
    ladders: markets.filter(isDateLadder).length,
    games:
      ((body.upcoming_games && body.upcoming_games.length) || 0) +
      ((body.recent_results && body.recent_results.length) || 0),
  };
}

module.exports = { isBinary, isDateLadder, leagueMarkets, leagueOwed };
