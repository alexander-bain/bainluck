// UX-P087 (#1860) — the browser rail's oracle must agree with the component it grades.
//
// ── THE DEFECT THIS TEST EXISTS TO CATCH ──
//
// `e2e/specs/league-cards.spec.ts` is ruling 047's acceptance on the league page.
// Its oracle deliberately RESTATES the partition rules instead of importing
// `lib/leagueCards`, because importing the implementation would make the rail
// compare production against the very function production reads and assert
// nothing (gotcha #121). That independence is correct and is kept.
//
// What was missing was the other half. On 2026-08-17 the first league-cards run
// that ever reached the page failed:
//
//     15 binary/ies must occupy at most 15 rows; 16 rows means the two-row
//     (Yes AND No) presentation is back.  Expected <= 15, Received 16
//
// and it was read, reasonably, as ruling 047 regressing. It was not. The page
// rendered SIXTEEN binaries as SIXTEEN rows — one row each. The sixteenth is
// "Shohei Ohtani: Cy Young and MVP Winner", a ONE-SIDED market carrying a single
// `Yes 1%` outcome. `binaryAnswer` counts it on purpose and documents why; the
// rail's restatement required exactly two outcomes and could not see it.
//
// An independent restatement is an instrument. An independent restatement nobody
// ever compares to the thing it measures is a second opinion with no referee —
// and the drift is invisible until it reds a correct page or, worse, greens a
// broken one. This test is the referee: both implementations, the SAME production
// payload, market by market.
//
// ── WHY THE FIXTURE IS PRODUCTION AND NOT INVENTED (#1886's standard) ──
//
// `leagueMlbProduction.json` is the verbatim body of `GET /api/leagues/baseball_mlb`.
// An invented fixture would have carried two-outcome binaries — the shape both
// implementations already agreed on — and agreed with the bug. The one-sided
// market is in the real payload and is asserted below BY NAME, so a future fixture
// refresh that happens to drop it cannot silently make this test vacuous.

import { binaryAnswer, dateLadder } from "../../lib/leagueCards";
import { isBinary, isDateLadder, leagueMarkets } from "../../e2e/helpers/leagueCardOracle";
import type { LeagueMarket } from "../../lib/api";
import production from "../fixtures/leagueMlbProduction.json";

const markets = leagueMarkets(production as never) as unknown as LeagueMarket[];

describe("league-card oracle ↔ component parity (production payload)", () => {
  it("reads a non-trivial number of markets — a vacuous parity check proves nothing", () => {
    expect(markets.length).toBeGreaterThan(20);
  });

  it("agrees with binaryAnswer on EVERY market", () => {
    const disagreements = markets
      .filter((m) => isBinary(m as never) !== (binaryAnswer(m) !== null))
      .map((m) => ({
        name: m.name,
        outcomes: (m.top_outcomes || []).map((o) => o.name),
        oracleSaysBinary: isBinary(m as never),
        componentSaysBinary: binaryAnswer(m) !== null,
      }));

    expect(disagreements).toEqual([]);
  });

  it("agrees with dateLadder on EVERY market", () => {
    const disagreements = markets
      .filter((m) => isDateLadder(m as never) !== (dateLadder(m) !== null))
      .map((m) => ({
        name: m.name,
        outcomes: (m.top_outcomes || []).map((o) => o.name),
        oracleSaysLadder: isDateLadder(m as never),
        componentSaysLadder: dateLadder(m) !== null,
      }));

    expect(disagreements).toEqual([]);
  });

  // The specimen that broke the rail, pinned by name. Without this, a fixture
  // refresh onto a slate with no one-sided market would leave the two parity
  // tests above passing while covering nothing that ever went wrong.
  it("still carries the ONE-SIDED market that broke the rail, and both sides count it", () => {
    const ohtani = markets.find((m) => (m.name || "").includes("Shohei Ohtani"));
    expect(ohtani).toBeDefined();
    expect((ohtani!.top_outcomes || []).map((o) => o.name)).toEqual(["Yes"]);

    // The whole defect in two lines: the component counts it, so the oracle must.
    expect(binaryAnswer(ohtani!)).not.toBeNull();
    expect(isBinary(ohtani! as never)).toBe(true);
  });

  // Both directions (gotcha #43): a rule that says "yes" to everything would pass
  // every assertion above. The oracle must also REFUSE the shapes that keep their
  // own cards — multi-outcome awards, and two-outcome markets that are two real
  // answers rather than a yes/no pair.
  it("refuses the shapes that are not binaries", () => {
    const multi = markets.filter((m) => (m.top_outcomes || []).length > 2);
    expect(multi.length).toBeGreaterThan(0);
    for (const m of multi) expect(isBinary(m as never)).toBe(false);

    const twoRealAnswers = {
      ...markets[0],
      name: "Dodgers or Padres?",
      top_outcomes: [
        { ...(markets[0].top_outcomes || [])[0], id: 1, name: "Dodgers" },
        { ...(markets[0].top_outcomes || [])[0], id: 2, name: "Padres" },
      ],
    } as LeagueMarket;
    expect(isBinary(twoRealAnswers as never)).toBe(false);
    expect(binaryAnswer(twoRealAnswers)).toBeNull();
  });

  // The counts the rail asserts as EXACT equalities, recorded here so a change to
  // either implementation shows up as a number a reader can check against a
  // screenshot rather than as a boolean.
  it("records the owed counts this payload implies", () => {
    expect(markets.filter((m) => isBinary(m as never)).length).toBe(22);
    expect(markets.filter((m) => isDateLadder(m as never)).length).toBe(6);
  });
});
