/**
 * #683 (Root ruling B) — "FULL" ASKS THE SERVER FOR THE QUESTION'S WHOLE HISTORY.
 *
 * Root's control: a 189-day-old archive specimen served its points at
 * `hours=4800` and NONE at `hours=4320`, which is exactly what EvolutionView's
 * "Full" sent. The fix is not a bigger constant. The whole-history rung adds
 * `range=full` and keeps `hours` as the floor an older server serves.
 *
 * Pinned by calling the REAL fetchers against a recording `fetch`, so the URL a
 * phone sends is the thing asserted. Three arms:
 *
 *  SHIP     — the whole-history rung (EvolutionView "full", /futures "all")
 *             sends `range=full`, on the multi-market route, on the single-id
 *             delegation, and on the detail stream's fresh re-read.
 *  CONTROL  — every shorter rung's URL is byte-identical to the URL it sent
 *             before this change (strings written out, not rebuilt).
 *  DECODER  — the response block is read only when the server says it served
 *             a full read, and missing coverage is "unknown", never "complete".
 */

import fs from "fs";
import path from "path";

import { API_URL, fetchFuturesHistory, fetchMultiMarketHistory } from "@/lib/api";
import {
  historyRangeDataAttributes,
  historyRangeOption,
  readHistoryRange,
  servedFullRange,
} from "@/lib/historyRange";
import type { FuturesHistoryResponse } from "@/lib/types";

const ROOT = path.resolve(__dirname, "..", "..");

function readSource(relative: string): string {
  const source = fs.readFileSync(path.join(ROOT, relative), "utf8");
  if (source.trim().length === 0) throw new Error(`source scan target is empty: ${relative}`);
  return source;
}

const EMPTY: FuturesHistoryResponse = { market_id: 0, market_name: "", hours: 0, outcomes: [] };

let urls: string[] = [];

beforeEach(() => {
  urls = [];
  jest.spyOn(globalThis, "fetch").mockImplementation(async (input: RequestInfo | URL) => {
    urls.push(String(input));
    return {
      ok: true,
      status: 200,
      headers: { get: () => null },
      json: async () => EMPTY,
    } as unknown as Response;
  });
});

afterEach(() => jest.restoreAllMocks());

function sent(): string {
  expect(urls).toHaveLength(1);
  expect(urls[0].startsWith(API_URL)).toBe(true);
  return urls[0].slice(API_URL.length);
}

describe("#683 SHIP — the whole-history rung sends range=full", () => {
  it("EvolutionView 'full' on the combined chart: /multi-history keeps hours as the floor and adds range=full", async () => {
    await fetchMultiMarketHistory([683001, 683002], 4320, 50, historyRangeOption("full"));
    expect(sent()).toBe("/api/futures/multi-history?market_ids=683001%2C683002&hours=4320&top_n=50&range=full");
  });

  it("EvolutionView 'full' with one market: the single-id delegation carries range=full too", async () => {
    await fetchMultiMarketHistory([683003], 4320, 50, historyRangeOption("full"));
    expect(sent()).toBe("/api/futures/683003/history?hours=4320&top_n=50&range=full");
  });

  it("/futures 'all': the created_at-derived hours stay, and range=full is added", async () => {
    await fetchFuturesHistory(683004, 4560, undefined, undefined, undefined, historyRangeOption("all"));
    expect(sent()).toBe("/api/futures/683004/history?hours=4560&range=full");
  });

  it("the detail stream's fresh re-read asks for the same range, so it cannot replace a full chart with an hours-only one", async () => {
    await fetchFuturesHistory(683005, 4560, undefined, undefined, undefined, { fresh: true, range: "full" });
    expect(sent()).toBe("/api/futures/683005/history?hours=4560&range=full&fresh=true");
  });

  it("both EvolutionView fetchers and both /futures readers pass the rung's range (source pin on the call sites)", () => {
    const evo = readSource("components/EvolutionView.tsx");
    expect(evo).toContain("const fullRange = historyRangeOption(timeRange);");
    expect(evo).toContain("fetchMultiMarketHistory(activeMarketIds, fetchHours, 50, fullRange)");
    expect(evo).toContain("fetchFuturesHistory(activeMarketId, fetchHours, undefined, 50, undefined, fullRange)");

    const page = readSource("app/futures/[id]/page.tsx");
    expect(page).toContain("const historyRange = historyRangeOption(effectiveRange)?.range;");
    expect(page).toContain('["futures-history", marketId, historyHours, historyRange ?? ""]');
    expect(page).toContain("historyRange ? { range: historyRange } : undefined");
    expect(page).toContain("history: historyData, historyHours, historyRange,");

    const stream = readSource("hooks/useFuturesDetailStream.ts");
    expect(stream).toContain("{ fresh: true, signal, range }");
    expect(stream).toContain("callbacks.current.historyRange !== range");
  });
});

describe("#683 CONTROL — every shorter rung is byte-identical to before", () => {
  it.each(["7d", "24h", "today", "tournament", "1W", "1M", undefined, null, "FULL", "lifetime"])(
    "rung %p sends no range option",
    (rung) => {
      expect(historyRangeOption(rung as string | null | undefined)).toBeUndefined();
    },
  );

  it("EvolutionView's week fetch on the combined chart", async () => {
    await fetchMultiMarketHistory([683011, 683012], 168, 50, historyRangeOption("7d"));
    expect(sent()).toBe("/api/futures/multi-history?market_ids=683011%2C683012&hours=168&top_n=50");
  });

  it("EvolutionView's week fetch with one market", async () => {
    await fetchMultiMarketHistory([683013], 168, 50, historyRangeOption("7d"));
    expect(sent()).toBe("/api/futures/683013/history?hours=168&top_n=50");
  });

  it("/futures '1M' and its fresh re-read", async () => {
    await fetchFuturesHistory(683014, 720, undefined, undefined, undefined, historyRangeOption("1M"));
    expect(sent()).toBe("/api/futures/683014/history?hours=720");
    urls = [];
    await fetchFuturesHistory(683014, 720, undefined, undefined, undefined, { fresh: true, range: undefined });
    expect(sent()).toBe("/api/futures/683014/history?hours=720&fresh=true");
  });

  it("the fixed-window settled readers are untouched (champion + top_n, no range)", async () => {
    await fetchFuturesHistory(683015, 8760, undefined, 8, "Dodgers");
    expect(sent()).toBe("/api/futures/683015/history?hours=8760&top_n=8&champion=Dodgers");
  });
});

describe("#683 DECODER — the server's account, read only when it says it served full", () => {
  it("an older server (no block) reads as today's hours window", () => {
    expect(readHistoryRange(EMPTY)).toBeNull();
    expect(servedFullRange(EMPTY)).toBe(false);
    expect(historyRangeDataAttributes(EMPTY)).toEqual({});
    expect(servedFullRange(undefined)).toBe(false);
    expect(historyRangeDataAttributes(null)).toEqual({});
  });

  it("a block for some other requested range is not a full read", () => {
    const other = { ...EMPTY, history_range: { requested: "since_start" } };
    expect(servedFullRange(other)).toBe(false);
    expect(historyRangeDataAttributes(other)).toEqual({});
  });

  it("a partial archive says partial: the earliest drawn point is not the question's open", () => {
    const partial: FuturesHistoryResponse = {
      ...EMPTY,
      history_range: {
        requested: "full",
        window_start: "2026-04-09T00:00:00+00:00",
        window_start_basis: "archive_first_interval",
        archive_coverage: "partial",
        archive_venue_open: "2026-03-01T00:00:00+00:00",
        thinned_outcomes: [11, 12],
      },
    };
    expect(servedFullRange(partial)).toBe(true);
    expect(historyRangeDataAttributes(partial)).toEqual({
      "data-history-range": "full",
      "data-history-range-start": "2026-04-09T00:00:00+00:00",
      "data-history-range-basis": "archive_first_interval",
      "data-archive-coverage": "partial",
      "data-history-range-thinned": "2",
    });
  });

  it("a full read with no coverage word is 'unknown', never read as a whole lifetime", () => {
    const silent: FuturesHistoryResponse = {
      ...EMPTY,
      history_range: { requested: "full", window_start_basis: "market_created_at", archive_coverage: null },
    };
    const attrs = historyRangeDataAttributes(silent);
    expect(attrs["data-archive-coverage"]).toBe("unknown");
    expect(attrs["data-history-range-thinned"]).toBe("0");
    expect(attrs).not.toHaveProperty("data-history-range-start");
  });
});

describe("#683 — a full read is not the sparse-data widening note", () => {
  it("both /futures range-control call sites drop actual_hours when the server served full", () => {
    const page = readSource("app/futures/[id]/page.tsx");
    expect(page).toContain(
      "actualHours={servedFullRange(historyData) ? undefined : historyData.actual_hours}",
    );
    expect(page).toContain(
      "actualHours={servedFullRange(historyData) ? undefined : historyData?.actual_hours}",
    );
    expect(page).not.toMatch(/actualHours=\{historyData\??\.actual_hours\}/);
  });
});
