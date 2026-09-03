/**
 * ux/1034 B7 — THE EVENT PAGE'S SOURCE LEGEND READS THE PAYLOAD.
 *
 * Alex asked for this one to be **verified, not built**:
 *
 *   > Sources legend on 15293830 shows BainLuck / Sportsbooks / Kalshi and no
 *   > Polymarket — correct today … when it attaches, the legend must pick it up
 *   > without a deploy. Verify, don't build.
 *
 * ## The verification failed, which is why there is code in this commit
 *
 * The footer strip was three chips, and the third was
 *
 *     Object.keys(win_prob_sources).some(k => k.includes('kalshi'))
 *       -> a hard-coded <span>Kalshi</span>, in violet
 *
 * — one venue, present or absent, with no branch for a second source at all.
 * **No attachment could ever have reached it.** Measured on the live page at
 * 2026-09-03T02:00Z, after lane1/056 attached the group: Polymarket had been on
 * this event since 20:26Z the previous evening — 145 points in
 * `win_prob_history`, a full entry in `win_prob_sources`, and the chart above
 * the strip was drawing its line — and the strip still read
 * `BainLuck · Sportsbooks · Kalshi`.
 *
 * The payload in `uxp1034_event_15293830_sources.json` is that read, verbatim.
 *
 * ## Two arms, because the strip has two failure modes
 *
 * The **library arm** proves the rule on the payload. The **source arm** proves
 * the page spends it — a pure function nothing renders is the classic way this
 * class of fix passes its own test and changes nothing on screen. `OddsChart`
 * is Recharts and server-renders to an empty box (see
 * `eventChartLabelling.test.tsx`, which established this constraint and the
 * discipline that goes with it), so the strip cannot be rendered here; the scan
 * therefore RAISES if it cannot find the block it is checking, because a source
 * guard that silently matches nothing is how a renamed variable turns this file
 * green by making it vacuous.
 */

import { readFileSync } from "fs";
import { join } from "path";

import { chartSourceChips } from "@/lib/chartSourceChips";
import { SOURCE_COLORS } from "@/lib/sourceColors";

import SERVED from "../fixtures/uxp1034_event_15293830_sources.json";

const PAYLOAD = SERVED as unknown as {
  win_prob_sources: Record<string, { display_name?: string }>;
  win_prob_history: Record<string, unknown[]>;
};

describe("ux/1034 B7 — the chips come from the payload", () => {
  it("picks up Polymarket on the served payload, with no code naming it", () => {
    const chips = chartSourceChips(PAYLOAD.win_prob_sources, PAYLOAD.win_prob_history);

    expect(chips.map((chip) => chip.key)).toEqual(["kalshi", "polymarket"]);
    expect(chips.map((chip) => chip.label)).toEqual(["Kalshi", "Polymarket"]);

    // The measurement that makes this a real attachment and not a fixture we
    // wrote: both series carry real points, from the live read.
    expect(PAYLOAD.win_prob_history.polymarket.length).toBe(145);
    expect(PAYLOAD.win_prob_history.kalshi.length).toBe(297);
  });

  /**
   * L2-155's law, which the violet chip broke: one source, one colour,
   * everywhere. The strip drew Kalshi violet while the plot six pixels above it
   * drew the same source `#22c55e`.
   */
  it("takes colour from the one registry the chart also reads", () => {
    const chips = chartSourceChips(PAYLOAD.win_prob_sources, PAYLOAD.win_prob_history);
    expect(chips.find((c) => c.key === "kalshi")!.color).toBe(SOURCE_COLORS.kalshi.hex);
    expect(chips.find((c) => c.key === "polymarket")!.color).toBe(
      SOURCE_COLORS.polymarket.hex
    );
    // Not the violet it used to be.
    expect(chips.every((chip) => chip.color !== "#a78bfa")).toBe(true);
  });

  /** A chip for a line the chart is not drawing is the same lie, facing the
   *  other way — so a source with no series is dropped. */
  it("drops a declared source with no series", () => {
    const chips = chartSourceChips(
      { kalshi: {}, polymarket: {}, stat_model: {} },
      { kalshi: [1, 2], polymarket: [], stat_model: undefined }
    );
    expect(chips.map((c) => c.key)).toEqual(["kalshi"]);
  });

  /** The sportsbook aggregate already has its own chip beside this list, under
   *  either of the two names the payloads use for it. */
  it("never doubles the sportsbook chip", () => {
    expect(
      chartSourceChips(
        { betting: {}, odds_api: {}, kalshi: {} },
        { betting: [1], odds_api: [1], kalshi: [1] }
      ).map((c) => c.key)
    ).toEqual(["kalshi"]);
  });

  it("survives an empty or absent payload", () => {
    expect(chartSourceChips(undefined, undefined)).toEqual([]);
    expect(chartSourceChips({}, {})).toEqual([]);
    expect(chartSourceChips({ kalshi: {} }, {})).toEqual([]);
  });

  /** A source nobody has declared still gets a chip rather than vanishing —
   *  the registry's neutral grey and the payload's own name. */
  it("names an unknown source from the payload rather than dropping it", () => {
    const chips = chartSourceChips(
      { pinnacle_model: { display_name: "Pinnacle Model" } },
      { pinnacle_model: [1, 2] }
    );
    expect(chips).toEqual([
      { key: "pinnacle_model", label: "Pinnacle Model", color: "#6b7280" },
    ]);
  });
});

describe("ux/1034 B7 — and the page spends it", () => {
  const SOURCE = readFileSync(
    join(__dirname, "../../app/events/[id]/page.tsx"),
    "utf8"
  );

  it("maps the chips into the chart footer", () => {
    // RAISE rather than pass if the block moved — see the file header.
    const footer = SOURCE.indexOf("{/* Chart footer: Legend + Sources toggle */}");
    if (footer < 0) {
      throw new Error(
        "chart footer block not found in the event page — this guard cannot " +
          "check what it cannot locate; find the block and re-anchor it."
      );
    }
    const block = SOURCE.slice(footer, footer + 4000);
    expect(block).toContain("{sourceChips.map((chip) => (");
    expect(block).toContain("backgroundColor: chip.color");
    expect(block).toContain("{chip.label}");
  });

  /** The defect itself, gone from the file — a hard-coded venue name in a
   *  legend is the whole bug and it must not come back beside the new list. */
  it("no longer hard-codes a venue into the legend", () => {
    expect(SOURCE).not.toContain("includes('kalshi')");
    expect(SOURCE).not.toContain('bg-violet-400');
  });
});
