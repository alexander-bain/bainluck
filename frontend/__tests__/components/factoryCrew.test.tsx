/** @jest-environment jsdom */

import React, { act } from "react";
import { createRoot } from "react-dom/client";
import FactoryFloor from "@/app/factory/FactoryFloor";
import {
  beltFlowing,
  crewActivity,
  duration,
  stopText,
} from "@/app/factory/activity";
import type { Change, FactoryData } from "@/app/factory/types";

jest.mock("next/navigation", () => {
  const router = { refresh: jest.fn() };
  return { useRouter: () => router };
});
jest.mock("@/hooks/usePageTracking", () => ({ usePageTracking: jest.fn() }));
jest.mock("@/hooks/useScrollDepth", () => ({ useScrollDepth: jest.fn() }));
jest.mock("@/hooks/useEngagementTime", () => ({
  useEngagementTime: jest.fn(),
}));

const now = "2026-11-18T18:00:00Z";
const base: Change = {
  number: 12998,
  title: "A short example change",
  builder: "B",
  line: "Server",
  station: "Test",
  unsure: false,
  reasons: [],
  side_track: false,
  last_activity: "2026-11-18T17:58:00Z",
  merged_at: null,
  live_at: null,
  timing: null,
};

const snapshot: FactoryData = {
  schema_version: 1,
  generated_at: now,
  observed_since: "2026-11-18T04:00:00Z",
  changes: [
    { ...base, checks_running: true },
    {
      ...base,
      number: 12999,
      builder: "S",
      station: "Merge line",
      station_since: "2026-11-18T17:20:00Z",
    },
    {
      ...base,
      number: 13000,
      builder: "C",
      station: "Merge line",
      parked: true,
    },
    {
      ...base,
      number: 13001,
      builder: "F",
      line: "Apps",
      station: "Live",
      merged_at: "2026-11-18T17:50:00Z",
      live_at: now,
      live_posted_at: now,
      timing: "reported",
      testflight_build: 5801,
    },
  ],
  transitions: [
    {
      number: 12998,
      line: "Server",
      from: "Write",
      to: "Test",
      at: now,
      observed_at: now,
    },
  ],
  stops: [
    {
      kind: "hold",
      line: "Server",
      station: "Merge line",
      since: "2026-11-18T17:20:00Z",
      count: 1,
      level: "red",
      number: 12999,
      waiting_since: "2026-11-18T17:20:00Z",
      test: "test_floor",
      source: { id: 6994962892, author: "Builder B" },
    },
    {
      kind: "line-stalled",
      line: "Website",
      station: "Merge line",
      since: "2026-11-18T17:19:00Z",
      count: 1,
      level: "amber",
      number: 12997,
      waiting_since: "2026-11-18T17:21:00Z",
      machines: { running: 40, waiting: 95 },
    },
  ],
  jams: [],
  signals: { tests: "failing", testflight: "success" },
  coverage: [],
  notes: {
    snapshot_at: now,
    source: "model",
    floor: "The server dock is on hold.",
    stations: {
      Checks: "1 crate in checks.",
      Live: "TestFlight build 5801 is posted.",
    },
  },
};

beforeEach(() => {
  Object.assign(globalThis, { IS_REACT_ACT_ENVIRONMENT: true });
  jest.useFakeTimers().setSystemTime(new Date(now));
});
afterEach(() => jest.useRealTimers());

function watchMotion() {
  let reduced = false;
  const listeners = new Set<() => void>();
  Object.defineProperty(window, "matchMedia", {
    configurable: true,
    value: jest.fn(() => ({
      get matches() {
        return reduced;
      },
      addEventListener: (_event: string, listener: () => void) =>
        listeners.add(listener),
      removeEventListener: (_event: string, listener: () => void) =>
        listeners.delete(listener),
    })),
  });
  return () => {
    reduced = true;
    listeners.forEach((listener) => listener());
  };
}

it("keeps the same crate, hold, machine queue, build and caption information under reduced motion", async () => {
  const reduce = watchMotion();
  const container = document.createElement("div");
  const root = createRoot(container);
  try {
    await act(async () =>
      root.render(
        <FactoryFloor data={snapshot} lastGoodAt={now} renderedAt={now} />,
      ),
    );
    const floor = container.querySelector("[data-factory]")!;
    expect(floor.getAttribute("data-motion")).toBe("running");
    const text = floor.textContent;
    expect(text).toContain("test_floor");
    expect(text).toContain(
      "#12999 has waited 40 minutes for a turn at the loading dock.",
    );
    expect(text).toContain("40 jobs running, 95 waiting");
    expect(text).toContain("TestFlight build 5801 is posted.");
    expect(text).toContain("Written by a model from the counts on this page");
    expect(
      container.querySelector(
        '[aria-labelledby="parked-heading"] [data-crate="13000"]',
      ),
    ).not.toBeNull();
    await act(async () => reduce());
    expect(floor.getAttribute("data-motion")).toBe("paused");
    expect(floor.textContent).toBe(text);
  } finally {
    await act(async () => root.unmount());
  }
});

it("shows carrying, standing in line, working and sleeping from snapshot evidence", () => {
  expect(crewActivity(snapshot, now, [snapshot.changes[0]]).pose).toBe(
    "carrying",
  );
  expect(crewActivity(snapshot, now, [snapshot.changes[1]]).pose).toBe(
    "waiting",
  );
  expect(crewActivity(snapshot, now, []).pose).toBe("asleep");
  expect(
    crewActivity({ ...snapshot, transitions: [] }, now, [snapshot.changes[0]])
      .pose,
  ).toBe("working");
});

it("moves the checks conveyor while CI runs and pauses it on an old read", () => {
  const running = { ...snapshot, transitions: [] };
  expect(beltFlowing(running, "Server", 1, now)).toBe(true);
  expect(beltFlowing(running, "Apps", 1, now)).toBe(false);
  expect(beltFlowing(running, "Server", 1, "2026-11-18T18:16:00Z")).toBe(false);
  expect(beltFlowing({ ...running, changes: [] }, "Server", 1, now)).toBe(
    false,
  );
});

it("names the change waiting for inspection and uses a singular day", () => {
  expect(duration(24 * 60 * 60)).toBe("1 day");
  expect(
    stopText(
      {
        kind: "review-waiting",
        line: "Website",
        station: "Review",
        since: "2026-11-18T17:20:00Z",
        count: 1,
        level: "amber",
        number: 12998,
        waiting_since: "2026-11-18T17:20:00Z",
      },
      now,
    ),
  ).toBe("#12998 has waited 40 minutes for inspection.");
});

it("leaves the previous snapshot's notes off the current floor", async () => {
  watchMotion();
  const container = document.createElement("div");
  const root = createRoot(container);
  const mismatched = {
    ...snapshot,
    notes: { ...snapshot.notes!, snapshot_at: base.last_activity },
  };
  try {
    await act(async () =>
      root.render(
        <FactoryFloor data={mismatched} lastGoodAt={now} renderedAt={now} />,
      ),
    );
    expect(container.textContent).not.toContain("Foreman’s note");
    expect(container.querySelector('[data-crate="12998"]')).not.toBeNull();
    await act(async () =>
      root.render(
        <FactoryFloor data={snapshot} lastGoodAt={now} renderedAt={now} />,
      ),
    );
    expect(container.textContent).toContain("Foreman’s note");
  } finally {
    await act(async () => root.unmount());
  }
});
