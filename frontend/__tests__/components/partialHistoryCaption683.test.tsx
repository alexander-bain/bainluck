/**
 * #683 — A FULL CHART SAYS WHEN PART OF ITS RECOVERED HISTORY COULD NOT BE SHOWN.
 *
 * Calibration's server half (PR #11083 @ 616d0c0a6b): on a `range=full` read
 * whose older live captures were thinned, an archive interval whose overlap
 * with our own captures could not be decided inside the read budget is LEFT
 * OUT and disclosed as `history_range.served_history: "partial"`, instead of
 * being silently counted as covered. Without a word the hole reads as a quiet
 * market.
 *
 * The reader rule, all of it:
 *  - `partial` ⇒ ONE short plain caption under the chart. No counts, no method.
 *  - every served point is drawn exactly as before (no drop, grey or re-scale).
 *  - `complete`, absent, or a read that was not full ⇒ no caption, no change.
 *
 * Arms: DECODER (the flag fires only on the server's own word), RENDER (one
 * caption; the rest of the chart byte-identical with and without it), and
 * WIRING (every chart that asks for the full range passes the flag — derived
 * from the import graph, so a sixth full-range chart cannot ship silent).
 */

import "../helpers/minimalDom";
import fs from "fs";
import path from "path";
import React from "react";
import { renderToStaticMarkup } from "react-dom/server";

import { FuturesChart } from "@/components/FuturesChart";
import {
  PARTIAL_HISTORY_CAPTION,
  historyRangeDataAttributes,
  servedPartialHistory,
} from "@/lib/historyRange";
import type { FuturesHistoryPoint, FuturesHistoryResponse, FuturesOutcomeHistory } from "@/lib/types";

const ROOT = path.resolve(__dirname, "..", "..");
const HOUR = 60 * 60 * 1000;
const START = Date.UTC(2026, 2, 2, 0, 0, 0);
const NOW = Date.UTC(2026, 9, 15, 20, 0, 0);

beforeAll(() => {
  jest.useFakeTimers({ doNotFake: ["performance"] });
  jest.setSystemTime(NOW);
});
afterAll(() => jest.useRealTimers());

type Block = FuturesHistoryResponse["history_range"];
const response = (history_range: Block): Pick<FuturesHistoryResponse, "history_range"> => ({ history_range });
const fullBlock = (extra: Partial<NonNullable<Block>> = {}): Block => ({
  requested: "full",
  window_start: "2026-03-02T00:00:00Z",
  window_start_basis: "archive_first_interval",
  archive_coverage: "complete",
  thinned_outcomes: [1],
  ...extra,
});

describe("#683 decoder: the caption fires only on the server's own word", () => {
  it("a full read that says partial is partial", () => {
    expect(
      servedPartialHistory(
        response(fullBlock({ served_history: "partial", unresolved_withheld: { archive_intervals: 3, venue_points: 0 } })),
      ),
    ).toBe(true);
  });

  it.each([
    ["complete", fullBlock({ served_history: "complete" })],
    ["absent (older server)", fullBlock()],
    ["null", fullBlock({ served_history: null })],
    ["an unknown word", fullBlock({ served_history: "PARTIAL" })],
    ["a block that did not answer as full", { requested: "hours", served_history: "partial" } as Block],
    ["no block", undefined],
  ])("%s is not partial", (_label, block) => {
    expect(servedPartialHistory(response(block))).toBe(false);
  });

  it("null and undefined responses are not partial", () => {
    expect(servedPartialHistory(null)).toBe(false);
    expect(servedPartialHistory(undefined)).toBe(false);
  });

  it("probes read the word from the card; absent is written as complete", () => {
    expect(historyRangeDataAttributes(response(fullBlock({ served_history: "partial" })))["data-history-served"]).toBe(
      "partial",
    );
    expect(historyRangeDataAttributes(response(fullBlock()))["data-history-served"]).toBe("complete");
    expect(historyRangeDataAttributes(response(undefined))).toEqual({});
  });
});

describe("#683 the caption itself", () => {
  it("is one short plain sentence with no counts, no machine keys and no venue", () => {
    expect(PARTIAL_HISTORY_CAPTION).toBe("Some older prices aren't shown.");
    expect(PARTIAL_HISTORY_CAPTION).not.toMatch(/\d/);
    expect(PARTIAL_HISTORY_CAPTION).not.toMatch(/_|overlap|budget|archive|kalshi|polymarket|book/i);
    expect(PARTIAL_HISTORY_CAPTION.split(/[.!?]\s/).length).toBe(1);
  });
});

function point(i: number): FuturesHistoryPoint {
  return {
    timestamp: new Date(START + i * HOUR).toISOString(),
    probability: 0.3 + (i % 7) * 0.03,
    american_odds: null,
    bookmaker: "consensus",
  };
}
const series: FuturesOutcomeHistory[] = [
  { outcome_id: 1, name: "Yes", history: Array.from({ length: 60 }, (_, i) => point(i)) },
  { outcome_id: 2, name: "No", history: Array.from({ length: 60 }, (_, i) => ({ ...point(i), probability: 1 - (point(i).probability ?? 0) })) },
];

const CAPTION_TAG = /<p class="[^"]*" data-testid="futures-chart-history-partial">[^<]*<\/p>/g;

describe("#683 render: one caption, every point drawn as before", () => {
  it("historyWithheld renders the caption exactly once", () => {
    const html = renderToStaticMarkup(<FuturesChart historyData={series} settled historyWithheld />);
    expect(html.match(CAPTION_TAG)).toHaveLength(1);
    expect(html).toContain(PARTIAL_HISTORY_CAPTION.replace(/'/g, "&#x27;"));
  });

  it("CONTROL: without the flag there is no caption", () => {
    const html = renderToStaticMarkup(<FuturesChart historyData={series} settled />);
    expect(html).not.toContain("futures-chart-history-partial");
    expect(html).not.toContain("older prices");
  });

  it("the chart around the caption is byte-identical — nothing dropped, greyed or re-scaled", () => {
    const withheld = renderToStaticMarkup(<FuturesChart historyData={series} settled historyWithheld />);
    const control = renderToStaticMarkup(<FuturesChart historyData={series} settled />);
    // Strawman: the comparison would fail if the caption were left in.
    expect(withheld).not.toBe(control);
    expect(withheld.replace(CAPTION_TAG, "")).toBe(control);
  });

  it("a mini chart (no axes, no room for a sentence) stays silent", () => {
    const html = renderToStaticMarkup(<FuturesChart historyData={series} mini historyWithheld />);
    expect(html).not.toContain("futures-chart-history-partial");
  });
});

/* WIRING — every component/page that asks for the full range passes the flag.
   The set is read off the import graph (`historyRangeOption` is the only way a
   chart sends `range=full`), so a new full-range chart that forgets the caption
   reddens here instead of shipping a silent hole. */
function walk(dir: string, out: string[] = []): string[] {
  for (const entry of fs.readdirSync(dir, { withFileTypes: true })) {
    const full = path.join(dir, entry.name);
    if (entry.isDirectory()) walk(full, out);
    else if (/\.tsx$/.test(entry.name)) out.push(full);
  }
  return out;
}

describe("#683 wiring: every full-range chart passes the flag", () => {
  const callers = [...walk(path.join(ROOT, "components")), ...walk(path.join(ROOT, "app"))]
    .filter((file) => /\bhistoryRangeOption\(/.test(fs.readFileSync(file, "utf8")))
    .map((file) => path.relative(ROOT, file))
    .sort();

  it("the census finds the five known full-range charts (a vacuous empty set cannot pass)", () => {
    expect(callers).toEqual([
      "app/futures/[id]/page.tsx",
      "components/EvolutionView.tsx",
      "components/event/SettledPathChart.tsx",
      "components/event/TwoSidedTimeline.tsx",
      "components/event/WinnerEvolutionChart.tsx",
    ]);
  });

  it.each([
    "app/futures/[id]/page.tsx",
    "components/EvolutionView.tsx",
    "components/event/SettledPathChart.tsx",
    "components/event/TwoSidedTimeline.tsx",
    "components/event/WinnerEvolutionChart.tsx",
  ])("%s hands its FuturesChart the server's partial word", (file) => {
    const source = fs.readFileSync(path.join(ROOT, file), "utf8");
    const charts = source.match(/<FuturesChart\b[\s\S]*?\/>/g) ?? [];
    const flagged = charts.filter((tag) => /historyWithheld=\{servedPartialHistory\(\w+\)\}/.test(tag));
    expect(flagged).toHaveLength(1);
  });
});
