/** @jest-environment jsdom */
/**
 * #883 — THE FIRST READER STOPS GETTING THE COLD CHART.
 *
 * The landing-page audit (FABLE-LANDING-PAGE-AUDIT-20261006) found 17 of 21
 * futures/props pages answering their first reader with a thin chart AND
 * `venue_history.fill: "requested"`; the fill landed 99–219 s later and the
 * page never asked again. These pin the bounded re-ask: it fires while the
 * server says a fill is in flight, stops on the first answer that says anything
 * else, stops when the schedule is spent, and never applies an answer after the
 * reader has moved to another range or left.
 */
import React from "react";
import { createRoot, type Root } from "react-dom/client";
import { act } from "react-dom/test-utils";
import { useFuturesHistoryFillRetry } from "@/hooks/useFuturesHistoryFillRetry";
import {
  HISTORY_FILL_RETRY_DELAYS_MS,
  historyFillPending,
  historyFillRetryDelay,
} from "@/lib/futuresHistoryFill";

type Body = { venue_history?: { fill?: string | null } | null; tag?: string };

let host: HTMLDivElement;
let root: Root;

beforeEach(() => {
  (globalThis as unknown as { IS_REACT_ACT_ENVIRONMENT: boolean }).IS_REACT_ACT_ENVIRONMENT = true;
  jest.useFakeTimers();
  host = document.createElement("div");
  root = createRoot(host);
});
afterEach(() => {
  act(() => root.unmount());
  jest.useRealTimers();
});

function Probe(props: {
  inFlight: boolean;
  rungKey: string;
  refetch: (signal: AbortSignal) => Promise<Body>;
  apply: (b: Body) => unknown;
}) {
  useFuturesHistoryFillRetry(props);
  return null;
}

async function advance(ms: number) {
  await act(async () => {
    jest.advanceTimersByTime(ms);
  });
  // Let the awaited refetch/apply chain settle.
  await act(async () => {
    await Promise.resolve();
    await Promise.resolve();
  });
}

const PENDING: Body = { venue_history: { fill: "requested" } };
const CLAIMED: Body = { venue_history: { fill: "already_claimed" } };
const FILLED: Body = { venue_history: { fill: "answered_recently" }, tag: "filled" };

describe("historyFillPending", () => {
  it("reads requested and already_claimed as in flight", () => {
    expect(historyFillPending(PENDING)).toBe(true);
    expect(historyFillPending(CLAIMED)).toBe(true);
  });
  it("reads every other answer, and absence, as not in flight", () => {
    for (const fill of ["answered_recently", "chart_not_thin", "hourly_cap", "error", "not_considered", null]) {
      expect(historyFillPending({ venue_history: { fill } })).toBe(false);
    }
    expect(historyFillPending({})).toBe(false);
    expect(historyFillPending(null)).toBe(false);
    expect(historyFillPending(undefined)).toBe(false);
  });
  it("spends a bounded schedule that covers the slowest observed fill (219 s)", () => {
    const total = HISTORY_FILL_RETRY_DELAYS_MS.reduce((a, b) => a + b, 0);
    expect(total).toBeGreaterThanOrEqual(219_000);
    expect(total).toBeLessThanOrEqual(5 * 60_000);
    expect(historyFillRetryDelay(HISTORY_FILL_RETRY_DELAYS_MS.length)).toBeNull();
    expect(historyFillRetryDelay(-1)).toBeNull();
  });
});

describe("useFuturesHistoryFillRetry", () => {
  it("re-asks while pending and applies the filled answer, then stops", async () => {
    const answers = [CLAIMED, FILLED];
    const refetch = jest.fn(async () => answers.shift() ?? FILLED);
    const apply = jest.fn();
    act(() => root.render(<Probe inFlight rungKey="1:168:" refetch={refetch} apply={apply} />));

    expect(refetch).not.toHaveBeenCalled();
    await advance(HISTORY_FILL_RETRY_DELAYS_MS[0]);
    expect(refetch).toHaveBeenCalledTimes(1);
    expect(apply).toHaveBeenLastCalledWith(CLAIMED);

    await advance(HISTORY_FILL_RETRY_DELAYS_MS[1]);
    expect(refetch).toHaveBeenCalledTimes(2);
    expect(apply).toHaveBeenLastCalledWith(FILLED);

    await advance(10 * 60_000);
    expect(refetch).toHaveBeenCalledTimes(2);
  });

  it("CONTROL: an answer that is not pending never starts a re-ask", async () => {
    const refetch = jest.fn(async () => FILLED);
    act(() => root.render(<Probe inFlight={false} rungKey="1:168:" refetch={refetch} apply={() => {}} />));
    await advance(10 * 60_000);
    expect(refetch).not.toHaveBeenCalled();
  });

  it("gives up after the schedule when the fill never lands", async () => {
    const refetch = jest.fn(async () => PENDING);
    act(() => root.render(<Probe inFlight rungKey="1:168:" refetch={refetch} apply={() => {}} />));
    for (const d of HISTORY_FILL_RETRY_DELAYS_MS) await advance(d);
    expect(refetch).toHaveBeenCalledTimes(HISTORY_FILL_RETRY_DELAYS_MS.length);
    await advance(10 * 60_000);
    expect(refetch).toHaveBeenCalledTimes(HISTORY_FILL_RETRY_DELAYS_MS.length);
  });

  it("a failed read spends one attempt and keeps going", async () => {
    const refetch = jest
      .fn<Promise<Body>, [AbortSignal]>()
      .mockRejectedValueOnce(new Error("network"))
      .mockResolvedValueOnce(FILLED);
    const apply = jest.fn();
    act(() => root.render(<Probe inFlight rungKey="1:168:" refetch={refetch} apply={apply} />));
    await advance(HISTORY_FILL_RETRY_DELAYS_MS[0]);
    expect(apply).not.toHaveBeenCalled();
    await advance(HISTORY_FILL_RETRY_DELAYS_MS[1]);
    expect(apply).toHaveBeenCalledWith(FILLED);
  });

  it("a range change aborts the in-flight read and never applies its late answer", async () => {
    let release: (b: Body) => void = () => {};
    let seenSignal: AbortSignal | null = null;
    const refetch = jest.fn(
      (signal: AbortSignal) =>
        new Promise<Body>((resolve) => {
          seenSignal = signal;
          release = resolve;
        }),
    );
    const apply = jest.fn();
    act(() => root.render(<Probe inFlight rungKey="1:168:" refetch={refetch} apply={apply} />));
    await advance(HISTORY_FILL_RETRY_DELAYS_MS[0]);
    expect(refetch).toHaveBeenCalledTimes(1);

    act(() => root.render(<Probe inFlight={false} rungKey="1:720:" refetch={refetch} apply={apply} />));
    expect(seenSignal!.aborted).toBe(true);
    await act(async () => {
      release(FILLED);
      await Promise.resolve();
    });
    expect(apply).not.toHaveBeenCalled();
  });

  it("unmount cancels the next scheduled read", async () => {
    const refetch = jest.fn(async () => PENDING);
    act(() => root.render(<Probe inFlight rungKey="1:168:" refetch={refetch} apply={() => {}} />));
    act(() => root.render(<></>));
    await advance(10 * 60_000);
    expect(refetch).not.toHaveBeenCalled();
  });
});
