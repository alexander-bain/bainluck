/**
 * #10955 (360) — EVOLUTION READS A SETTLEMENT POINT AS A RESULT, NOT A LATEST CHANCE.
 *
 * `/api/futures/{id}/history` ends a graded leg with one `bookmaker: "settlement"`
 * point whose VALUE is the grade (1 won, 0 lost) and whose timestamp is never a
 * market time (`lib/chartSettlementPoints.ts`). The chart already draws it as a
 * result mark. EvolutionView and its sidebar did not: both took the raw last
 * history value, so
 *
 *   - the default selection and the color ranking sorted a loser's 0 and a
 *     winner's 1 as if they were prices (an evidenced loser with a real 45%
 *     dropped out of the default set behind a 12% leg; a 0.5 "recorded" grade
 *     outranked every real contender),
 *   - the sidebar printed "100.0%" / "0.0%" as the leg's current chance, and an
 *     empty history printed "0.0%",
 *   - the time-range window filtered the settlement point by its timestamp, so the
 *     chart's result mark vanished on short ranges while the sidebar still read
 *     the full history.
 *
 * Synthetic field (no production settlement specimen exists — the served
 * histories carried zero settlement points in the retained reader sample), so
 * this pays the component contract only, never served-reader acceptance.
 */

import "../helpers/minimalDom";
import React, { act } from "react";
import { createRoot } from "react-dom/client";
import type { FuturesHistoryPoint, FuturesOutcomeHistory } from "@/lib/types";
import { EvolutionView } from "@/components/EvolutionView";
import { SERIES_COLORS } from "@/lib/seriesColors";

const NOW = Date.parse("2026-10-20T12:00:00Z");
const iso = (ms: number) => new Date(ms).toISOString();
const H = 3_600_000;

function real(prob: number, agoMs: number): FuturesHistoryPoint {
  return { timestamp: iso(NOW - agoMs), probability: prob, bookmaker: "kalshi" } as FuturesHistoryPoint;
}
/** A settlement point stamped 30 days ago — an old scheduled close, far outside
 *  any short range, and earlier than the leg's real readings. */
function settlement(prob: number): FuturesHistoryPoint {
  return { timestamp: iso(NOW - 30 * 24 * H), probability: prob, bookmaker: "settlement" } as FuturesHistoryPoint;
}
function leg(id: number, name: string, history: FuturesHistoryPoint[], extra: Partial<FuturesOutcomeHistory> = {}): FuturesOutcomeHistory {
  return { outcome_id: id, name, history, ...extra } as FuturesOutcomeHistory;
}

/** Served order deliberately puts the winner first so the old raw sort, which
 *  tied the winner's settlement 1 with Echo's observed 1, kept it first too. */
function field(): FuturesOutcomeHistory[] {
  return [
    leg(1, "Alpha Upset", [real(0.05, 5 * H), real(0.08, 2 * H), settlement(1)]),
    leg(2, "Bravo Favorite", [real(0.4, 5 * H), real(0.45, 2 * H), settlement(0)]),
    leg(3, "Charlie Contender", [real(0.3, 5 * H), real(0.25, 2 * H), settlement(0)]),
    leg(4, "Delta Live", [real(0.2, 5 * H), real(0.22, 2 * H)]),
    leg(5, "Echo Observed", [real(0.9, 5 * H), real(1, 2 * H)]),
    leg(6, "Foxtrot Zero", [real(0.1, 5 * H), real(0, 2 * H)]),
    leg(7, "Golf Recorded", [real(0.1, 5 * H), real(0.12, 2 * H), settlement(0.5)]),
    leg(8, "Hotel Empty", []),
    leg(9, "India Low", [real(0.02, 5 * H), real(0.01, 2 * H), settlement(0)]),
  ];
}

let history: { outcomes: FuturesOutcomeHistory[] };
let detail: { id: number; outcomes: { id: number; probability: number | null }[] } | undefined;
jest.mock("swr", () => ({
  __esModule: true,
  default: (key: unknown) =>
    Array.isArray(key)
      ? { data: detail, error: undefined, isLoading: false }
      : { data: history, error: undefined, isLoading: false },
}));

function descendants(node: HTMLElement): HTMLElement[] {
  return [node, ...Array.from(node.childNodes).flatMap((n) => descendants(n as HTMLElement))];
}
// eslint-disable-next-line @typescript-eslint/no-explicit-any
function props(node: HTMLElement): Record<string, any> {
  const key = Object.keys(node).find((k) => k.startsWith("__reactProps$"));
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  return key ? (node as any)[key] : {};
}

let host: HTMLElement;
let root: ReturnType<typeof createRoot>;
const MARKET = 4242;
function render(requireCurrentPrices = false) {
  act(() =>
    root.render(<EvolutionView marketId={MARKET} defaultTopN={5} requireCurrentPrices={requireCurrentPrices} />),
  );
}

/** Sidebar rows in drawn order: name, the value column, and the dot color. */
function rows() {
  return descendants(host)
    .filter((n) => n.tagName === "DIV" && props(n).onMouseEnter && String(props(n).className).includes("cursor-default"))
    .map((row) => {
      const spans = descendants(row).filter((n) => n.tagName === "SPAN");
      const dot = spans.find((s) => props(s).style?.backgroundColor);
      const name = spans.find((s) => String(props(s).className).includes("truncate"))!;
      const value = spans.find((s) => String(props(s).className).includes("tabular-nums"))!;
      return { name: name.textContent, value: value.textContent, color: props(dot!).style.backgroundColor as string };
    });
}
function openPicker() {
  const input = descendants(host).find((n) => n.tagName === "INPUT" && props(n).placeholder)!;
  act(() => props(input).onFocus());
}
/** Picker entries: name → value text. */
function pickerEntries(): Record<string, string> {
  const out: Record<string, string> = {};
  for (const b of descendants(host).filter((n) => n.tagName === "BUTTON" && String(props(n).className).includes("justify-between"))) {
    const [name, value] = Array.from(b.childNodes) as HTMLElement[];
    out[name.textContent] = value.textContent;
  }
  return out;
}
function clickRange(label: string) {
  const b = descendants(host).find((n) => n.tagName === "BUTTON" && n.textContent === label)!;
  expect(b).toBeDefined();
  act(() => props(b).onClick());
}
function resultMarks(): string[] {
  return descendants(host)
    .filter((n) => props(n)["data-testid"] === "futures-chart-result-mark")
    .map((n) => `${props(n)["data-outcome-id"]}:${props(n)["data-result"]}`)
    .sort();
}
function footerCount(): string {
  const m = host.textContent.match(/(\d+) of (\d+)/);
  return m ? m[0] : "";
}

beforeEach(() => {
  jest.spyOn(Date, "now").mockReturnValue(NOW);
  history = { outcomes: field() };
  detail = undefined;
  host = document.createElement("div");
  document.body.appendChild(host);
  root = createRoot(host);
});
afterEach(() => {
  act(() => root.unmount());
  document.body.removeChild(host);
  jest.restoreAllMocks();
});

describe("#10955 (360) EvolutionView default selection and sidebar order", () => {
  it("selects the winner first, then the strongest REAL readings — settlement 0/1 is not a price", () => {
    render();
    // Old raw-last order picked Alpha(1), Echo(1), Golf(0.5 settlement), Delta(.22),
    // Bravo(0) and dropped Charlie's real 25% behind a settlement value.
    expect(rows().map((r) => r.name)).toEqual([
      "Alpha Upset",
      "Echo Observed",
      "Bravo Favorite",
      "Charlie Contender",
      "Delta Live",
    ]);
    expect(footerCount()).toBe("5 of 9");
  });

  it("the winner takes the leader color, and every dot matches the order it is drawn in", () => {
    render();
    const r = rows();
    expect(r[0].name).toBe("Alpha Upset");
    expect(r.map((x) => x.color)).toEqual(SERIES_COLORS.slice(0, 5));
  });

  it("a winner the current market no longer quotes is still selected; a graded loser stays out by the old rule", () => {
    detail = {
      id: MARKET,
      outcomes: field().map((o) => ({
        id: o.outcome_id,
        probability: o.outcome_id === 1 || o.outcome_id === 2 ? null : 0.1,
      })),
    };
    render(true);
    const names = rows().map((r) => r.name);
    expect(names[0]).toBe("Alpha Upset");
    expect(names).not.toContain("Bravo Favorite");
    expect(rows()[0].value).toBe("Won");
    // The loser is unavailable now and graded: the picker names its result, and
    // it stays addable.
    openPicker();
    expect(pickerEntries()["Bravo Favorite"]).toBe("Lost");
  });
});

describe("#10955 (360) the sidebar prints results, real readings and absences honestly", () => {
  it("graded legs read Won / Lost, never the settlement value as a percent", () => {
    render();
    const byName = Object.fromEntries(rows().map((r) => [r.name, r.value]));
    expect(byName["Alpha Upset"]).toBe("Won");
    expect(byName["Bravo Favorite"]).toBe("Lost");
    expect(byName["Charlie Contender"]).toBe("Lost");
    for (const name of ["Alpha Upset", "Bravo Favorite", "Charlie Contender"]) {
      expect(byName[name]).not.toMatch(/%$/);
    }
  });

  it("a genuinely observed 100% and an ungraded leg keep their real readings", () => {
    render();
    const byName = Object.fromEntries(rows().map((r) => [r.name, r.value]));
    expect(byName["Echo Observed"]).toBe("100.0%");
    expect(byName["Delta Live"]).toBe("22.0%");
  });

  it("the picker: observed 0% stays a price, an unnamed grade says Settled, no history is a dash, a loser is addable", () => {
    render();
    openPicker();
    const p = pickerEntries();
    expect(p["Foxtrot Zero"]).toBe("0.0%");
    expect(p["Golf Recorded"]).toBe("Settled");
    expect(p["Hotel Empty"]).toBe("—");
    expect(p["India Low"]).toBe("Lost");
    // Ordered like the sidebar: graded/ungraded by last real reading, empty last.
    expect(Object.keys(p)).toEqual(["Golf Recorded", "India Low", "Foxtrot Zero", "Hotel Empty"]);
  });

  it("adding a graded loser from the picker draws it as Lost, not 0.0%", () => {
    render();
    openPicker();
    const b = descendants(host).find((n) => n.tagName === "BUTTON" && n.textContent.includes("India Low"))!;
    act(() => props(b).onClick());
    const india = rows().find((r) => r.name === "India Low");
    expect(india?.value).toBe("Lost");
    expect(footerCount()).toBe("6 of 9");
  });
});

describe("#10955 (360) a result survives the time range", () => {
  it("the chart keeps every selected result mark on a short range, and selection/colors do not move", () => {
    render();
    const before = rows();
    expect(resultMarks()).toEqual(["1:won", "2:lost", "3:lost"]);
    clickRange("24 Hours");
    // The settlement points are stamped 30 days back; filtering them by time took
    // the marks off the chart while the sidebar kept saying Won / Lost.
    expect(resultMarks()).toEqual(["1:won", "2:lost", "3:lost"]);
    expect(rows()).toEqual(before);
  });
});

describe("#10955 (360) controls", () => {
  it("a field with no settlement points keeps the plain last-value order and percents", () => {
    history = {
      outcomes: [
        leg(11, "Kilo One", [real(0.1, 3 * H), real(0.3, H)]),
        leg(12, "Lima Two", [real(0.6, 3 * H), real(0.5, H)]),
        leg(13, "Mike Three", [real(0.2, 3 * H), real(0.05, H)]),
      ],
    };
    render();
    expect(rows().map((r) => [r.name, r.value])).toEqual([
      ["Lima Two", "50.0%"],
      ["Kilo One", "30.0%"],
      ["Mike Three", "5.0%"],
    ]);
    expect(resultMarks()).toEqual([]);
  });

  it("does not rewrite the served history", () => {
    const before = JSON.stringify(history);
    render();
    clickRange("24 Hours");
    expect(JSON.stringify(history)).toBe(before);
  });
});
