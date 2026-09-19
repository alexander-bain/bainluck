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
// #7058 asked for the repair in two parts: serve `settled_at` on the detail
// payload, then print it here. THE SECOND PART IS WRONG, AND THIS IS THE
// MEASUREMENT THAT SAYS SO — written down because the issue, the route and this
// file all read as if the only thing missing were the field.
//
// `settled_at` is documented in `models.py` as "WHEN status became 'resolved'".
// It records when WE SAW the transition, not when the market resolved, and the
// sweeps that write it stamp their own clock. Measured on production
// 2026-09-19 over the exact population the issue names — resolved markets whose
// `resolution_date` is in the future and whose `settled_at` is set (9,347 rows,
// 9,345 of them carrying a `commence_time`):
//
//     settled_at more than 24h after the game started   4,765  (51%)
//     … more than 7 days after                          1,611  (17%)
//     … more than 30 days after                         1,256  (13%)
//
// Second method, independent of `commence_time` and of any assumption about
// when a game ends: the stamps are SHARED. One `settled_at` value, identical to
// the microsecond, is carried by 137 different markets; the next four cover 118,
// 99, 95 and 91. A timestamp that 137 unrelated games share to the microsecond
// is a sweep's clock and cannot be an observation of any one of them.
//
// The issue's own five specimens are the case in miniature: `60755454` and its
// four siblings are baseball games that started 2026-09-11 13:00Z, and all five
// carry `settled_at = 2026-09-18 22:55:08.995192Z` — the #6919 drain's clock,
// seven days after the games were played. Printing that field would have
// answered "Resolved 9/25/2026" with "Resolved 9/18/2026" on a game finished on
// the 11th: a second false date, on half the population, in the reader's first
// line. `app/utils/settlement_stamp.py` reached the same verdict from the chart
// side (#6360) and ranks `settled_at` LAST of four witnesses for this reason.
//
// So this module states no date, and serving the field would not change that.
// It does NOT carry a `settled_at` branch: the honest render with no trustworthy
// evidence is silence (notice 34), and an unreachable branch is a guess about a
// field's shape that no test can kill.
//
// IF A DATE IS EVER WANTED HERE, the witness is the one the chart already
// trusts — `settlement_stamp.py`'s arm 1 (a PAST `resolution_date`) or arm 2
// (the market's last real observation, where the journey ends) — never arm 3.
// That needs a server-side decision on the detail route, because the page's
// history fetch is window-scoped and would make the date appear and disappear
// with a chart toggle. Nobody has asked for it; the banner is complete without
// one.
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
