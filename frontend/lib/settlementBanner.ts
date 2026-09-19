// #7060 / #7058 — whether `/futures/[id]` may announce that a market is over,
// and in what words.
//
// ── WHAT THE PAGE SAID BEFORE THIS ───────────────────────────────────────────
//
// One expression in `app/futures/[id]/page.tsx` carried two settlement claims,
// and both were derived from `resolution_date`:
//
//     {(isResolved || (market.resolution_date && new Date(market.resolution_date) < new Date())) && (
//       … isResolved
//         ? `This market has been settled.${… ` Resolved ${…resolution_date…}.`}`
//         : `This market resolved on ${…resolution_date…}. Showing final probabilities.`
//
// `resolution_date` is the SCHEDULED resolution. It is not evidence that
// anything resolved, and it is not the date on which anything did. Line 726 of
// that same file had already written this rule down and line 735 already acted
// on it for the hero; the banner was left behind.
//
// Read on production 2026-09-18 23:43Z, `/futures/61317401` at 390px — "Detroit
// Tigers vs. Chicago White Sox · 1st Inning Winner", `status: "open"`, three
// legs quoting 53 / 26 / 21, venue trading:
//
//     This market resolved on 9/18/2026. Showing final probabilities.
//     53%  ↑ 4.0 pts · last move Sep 18
//
// The banner and the hero, three lines apart, in the same component, disagreed
// about whether the game had happened. 937 open markets carried a passed
// `resolution_date` in that minute (authority/480 measured 648 at 23:1xZ — the
// population BREATHES, because every Polymarket in-game market crosses its
// scheduled date while it is still trading, so the marquee games are the most
// affected, not the least).
//
// ── THE RULE ─────────────────────────────────────────────────────────────────
//
// `status` is the only settlement evidence the payload carries, and it is
// exhaustive: production holds exactly two values, `resolved` (1,026,367) and
// `open` (42,839), measured the same minute. So the gate is `status`, alone.
//
// ── WHY NO DATE AT ALL, RATHER THAN A BETTER ONE (#7058) ─────────────────────
//
// A settled market's banner used to append " Resolved <resolution_date>." —
// the schedule again, printed as history. On 9,993 resolved markets that date
// is in the FUTURE, so the page said "Resolved 9/25/2026" on a market settled
// today (authority/479 has the screenshot: `/futures/60755454`).
//
// The true field is `settled_at`, and `GET /api/futures/{id}` does not serve it
// (checked by key on 61317401: absent). So this module states no date. It does
// NOT carry a `settled_at` branch waiting for the backend half — an unreachable
// branch is a guess about a field's shape that no test can kill, and the honest
// render with no evidence is silence (notice 34). #7058 stays open for the
// backend field plus the branch that prints it.
//
// ── SCOPE: THE OTHER PAST-DATE DERIVATION IN THAT FILE IS LEFT ALONE ─────────
//
// `page.tsx:141` derives the same "is this over?" from the same date, for the
// chart's history WINDOW. It is not a claim to the reader (it widens a fetch),
// and on this population it changes nothing: these markets were created days
// ago, so the window floors at 168h either way. Named here so the next reader
// knows it was measured, not missed.

/** The fields this decision reads. A subset of `FuturesMarket`, so the page can pass the market. */
export interface SettlementBannerSubject {
  status?: string | null;
}

/**
 * The sentence `/futures/[id]` prints above a settled market, or `null` when it
 * must print nothing.
 *
 * A scheduled date — passed, future or absent — never reaches this decision.
 */
export function settlementBannerText(
  market: SettlementBannerSubject | null | undefined,
): string | null {
  if (!market) return null;
  return market.status === "resolved" ? "This market has been settled." : null;
}
