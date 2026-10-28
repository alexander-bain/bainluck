// #10090 — the chart transform's timestamp→ms reuse returns exactly what the
// plain parse returns, holds at most 1,024 strings, and never evicts one it holds.
import * as dateFns from "date-fns";

import { CHART_TIMESTAMP_MS_MAX_ENTRIES, createChartTimestampMs } from "@/lib/chartTimestampMs";

jest.mock("date-fns", () => {
  const actual = jest.requireActual("date-fns");
  return { ...actual, parseISO: jest.fn(actual.parseISO) };
});

const { parseISO: realParseISO } = jest.requireActual<typeof import("date-fns")>("date-fns");
const parseCalls = () => (dateFns.parseISO as jest.Mock).mock.calls.length;
const plain = (s: string) => realParseISO(s).getTime();
const minute = (i: number) => new Date(Date.UTC(2026, 8, 20) + i * 60_000).toISOString();

beforeEach(() => (dateFns.parseISO as jest.Mock).mockClear());

describe("#10090 createChartTimestampMs", () => {
  const inputs = [
    "2026-09-20T04:46:00Z",
    "2026-09-20T04:46:00.000Z",
    "2026-09-20T04:46:30.123456Z",
    "2026-09-20T04:46:30.123456789Z",
    "2026-09-26T23:04:41.429489+00:00",
    "2026-09-20T01:38:00-07:00",
    "2026-09-20T04:46:00", // no zone: plain path
    "2026-09-20", // date only: plain path
    "2026-09-20T04:46Z", // no seconds: plain path
    "2026-13-40T25:61:61Z", // explicit-zone shape, invalid value: NaN, never held
    "not a time",
    "",
  ];

  test("every input returns the plain parse, on the first and the repeated read", () => {
    const ms = createChartTimestampMs();
    for (const s of inputs) {
      expect(Object.is(ms(s), plain(s))).toBe(true);
      expect(Object.is(ms(s), plain(s))).toBe(true);
    }
    expect(Number.isNaN(ms("2026-13-40T25:61:61Z"))).toBe(true);
  });

  test("an absent timestamp fails exactly as the plain parse fails", () => {
    const ms = createChartTimestampMs();
    for (const absent of [undefined, null]) {
      let plainError: unknown;
      try {
        plain(absent as unknown as string);
      } catch (e) {
        plainError = e;
      }
      let cachedError: unknown;
      try {
        ms(absent as unknown as string);
      } catch (e) {
        cachedError = e;
      }
      expect(String(cachedError)).toBe(String(plainError));
    }
  });

  test("a repeated explicit-zone string is parsed once; other strings every time", () => {
    const ms = createChartTimestampMs();
    for (let i = 0; i < 5; i++) ms("2026-09-20T04:46:00Z");
    expect(parseCalls()).toBe(1);
    for (let i = 0; i < 3; i++) ms("2026-09-20T04:46:00");
    for (let i = 0; i < 3; i++) ms("2026-13-40T25:61:61Z");
    expect(parseCalls()).toBe(1 + 3 + 3);
  });

  test("the map holds at most 1,024 strings and keeps the first ones past the cap", () => {
    expect(CHART_TIMESTAMP_MS_MAX_ENTRIES).toBe(1024);
    const ms = createChartTimestampMs();
    for (let i = 0; i < CHART_TIMESTAMP_MS_MAX_ENTRIES; i++) ms(minute(i));
    expect(parseCalls()).toBe(CHART_TIMESTAMP_MS_MAX_ENTRIES);
    // Over the cap: correct every time, held never.
    const over = minute(CHART_TIMESTAMP_MS_MAX_ENTRIES);
    expect(ms(over)).toBe(plain(over));
    expect(ms(over)).toBe(plain(over));
    expect(parseCalls()).toBe(CHART_TIMESTAMP_MS_MAX_ENTRIES + 2);
    // No eviction: every string held before the cap is still answered from the map.
    (dateFns.parseISO as jest.Mock).mockClear();
    for (let i = 0; i < CHART_TIMESTAMP_MS_MAX_ENTRIES; i++) expect(ms(minute(i))).toBe(plain(minute(i)));
    expect(parseCalls()).toBe(0);
  });

  test("each transform starts with its own empty map", () => {
    const first = createChartTimestampMs();
    const second = createChartTimestampMs();
    first("2026-09-20T04:46:00Z");
    second("2026-09-20T04:46:00Z");
    expect(parseCalls()).toBe(2);
  });
});
