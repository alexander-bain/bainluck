// #1541 — a market the provider WITHDREW is "no longer offered", never final.
//
// The review blocker on PR #10938: the first backend cut wrote `status:
// "resolved"` for an Odds API championship the provider stopped listing, and
// this page titles its table "Final Results" and draws its settled hero off
// exactly that status. A FUTURE championship dropped for eight days met the
// same rule. A listing gap proves the market is unavailable, not that the
// competition ended, so the backend now writes `status: "withdrawn"` and the
// detail route withholds every price on it
// (`backend/tests/test_a_withdrawn_championship_is_never_served_final_1541.py`).
//
// Two arms, as in #7060's file: the DECISION in `lib/settlementBanner.ts` (the
// page is a client component behind SWR, so the words live where a test can
// reach them), and the CALL SITES read as source.

import { readFileSync } from "fs";
import { join } from "path";

import { WITHDRAWN_BANNER, settlementBannerText } from "@/lib/settlementBanner";

const PAGE = join(__dirname, "..", "app", "futures", "[id]", "page.tsx");

/** Words that would claim the competition is over or decided. */
const SETTLEMENT_WORDS = /settled|final|result|ended|over\b|won|winner|resolved|closed/i;

describe("#1541 the withdrawn banner says unavailable, never final", () => {
  it("prints the withdrawn sentence for a withdrawn market", () => {
    expect(settlementBannerText({ status: "withdrawn" })).toBe(WITHDRAWN_BANNER);
    expect(WITHDRAWN_BANNER).toBe("This market is no longer offered.");
  });

  it("carries no settlement claim", () => {
    expect(WITHDRAWN_BANNER).not.toMatch(SETTLEMENT_WORDS);
  });

  it("would catch a settlement claim (control for the arm above)", () => {
    expect(settlementBannerText({ status: "resolved" })).toMatch(SETTLEMENT_WORDS);
  });

  it("is not the settled sentence", () => {
    expect(settlementBannerText({ status: "withdrawn" })).not.toBe(
      settlementBannerText({ status: "resolved" }),
    );
  });

  it("leaves an open market silent", () => {
    expect(settlementBannerText({ status: "open" })).toBeNull();
  });
});

describe("#1541 the page never reads withdrawn as resolved", () => {
  const source = readFileSync(PAGE, "utf8");

  it("reads the page (anti-vacuity)", () => {
    expect(source).toContain("<FuturesHero");
  });

  it("keys its settled view on `resolved` alone", () => {
    // "Final Results", the settled hero and the verdict column all hang off
    // `isResolved`. Withdrawn must never be folded into it.
    expect(source).toContain('const isResolved = market.status === "resolved";');
    expect(source).not.toMatch(/isResolved\s*=[^;\n]*withdrawn/);
  });

  it("stands down the live furniture on a withdrawn market", () => {
    expect(source).toContain('const isWithdrawn = market.status === "withdrawn";');
    // The "Games This Week" strip of unrelated fixtures, and the resolve date.
    expect(source).toMatch(/marketResolved=\{isResolved \|\| isWithdrawn\}/);
    expect(source).toMatch(/resolveDate=\{isResolved \|\| isWithdrawn \?/);
  });
});
