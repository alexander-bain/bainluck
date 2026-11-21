/** @jest-environment jsdom */

import React, { act } from "react";
import { createRoot } from "react-dom/client";
import { useRouter } from "next/navigation";
import FactoryFloor from "@/app/factory/FactoryFloor";
import {
  beltFlowing,
  crewActivity,
  duration,
  stopText,
} from "@/app/factory/activity";
import type { Change, FactoryData, FloorEvent } from "@/app/factory/types";
import { useEventPlayer } from "@/app/factory/playback";
import { useDayReplay } from "@/app/factory/useDayReplay";
import { replayReading, useReplayJournal } from "@/app/factory/replayJournal";
import { builderOfDay, clipboard, hours, injuryHours } from "@/app/factory/signs";
import { factoryTabTitle, floorVerdict } from "@/app/factory/verdict";

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
      container.querySelector('[aria-label="Side shelves"]')?.textContent,
    ).toContain("Parked 1");
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

it("counts deliveries in each Live bay and keeps held changes and quiet drafts off the floor", async () => {
  watchMotion();
  const container = document.createElement("div");
  const root = createRoot(container);
  const showModal = Object.getOwnPropertyDescriptor(HTMLDialogElement.prototype, "showModal");
  Object.defineProperty(HTMLDialogElement.prototype, "showModal", {
    configurable: true,
    value(this: HTMLDialogElement) { this.open = true; },
  });
  const waiting: Change = { ...base, station: "Merge line" };
  const shipped = snapshot.changes[3];
  const changes: Change[] = [
    waiting,
    { ...waiting, line: "Website" },
    shipped,
    { ...shipped, line: "Website", testflight_build: undefined },
    { ...base, number: 13070, checks_running: true, held_for_108: true },
    { ...base, number: 12621, station: "Write", parked: true },
  ];
  try {
    await act(async () =>
      root.render(
        <FactoryFloor
          data={{ ...snapshot, changes, stops: [], notes: undefined }}
          lastGoodAt={now}
          renderedAt={now}
        />,
      ),
    );
    expect(container.textContent).not.toMatch(/Shipped today|On the floor now|Busiest station/);
    for (const line of ["Website", "Apps"]) {
      const row = container.querySelector(`[data-factory-row="${line}"]`)!;
      const live = row.querySelector('[data-bay="Live"]')!;
      expect(live.textContent).toContain("1 shipped");
      expect(live.querySelector(`[data-crate="${shipped.number}"]`)).not.toBeNull();
    }
    const shelf = container.querySelector('[aria-label="Side shelves"]')!;
    expect(shelf.textContent).toContain("Held for 1.0.8 1");
    expect(shelf.textContent).toContain("Parked 1");
    expect(container.querySelector('[data-factory-row] [data-crate="13070"]')).toBeNull();
    expect(container.querySelector('[data-factory-row] [data-crate="12621"]')).toBeNull();
    expect(beltFlowing({ ...snapshot, changes, transitions: [] }, "Server", 1, now)).toBe(false);
    const crate = container.querySelector<HTMLButtonElement>(`[data-crate="${shipped.number}"]`)!;
    await act(async () => { crate.click(); });
    expect(container.querySelector("dialog")?.textContent)
      .toContain("This change appears on the Website and Apps lines.");
  } finally {
    await act(async () => root.unmount());
    if (showModal) Object.defineProperty(HTMLDialogElement.prototype, "showModal", showModal);
    else Reflect.deleteProperty(HTMLDialogElement.prototype, "showModal");
  }
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

it("checks for a new floor every minute while the page is visible", async () => {
  watchMotion();
  const refresh = jest.mocked(useRouter().refresh);
  refresh.mockClear();
  const container = document.createElement("div");
  const root = createRoot(container);
  try {
    await act(async () =>
      root.render(<FactoryFloor data={snapshot} lastGoodAt={now} renderedAt={now} />),
    );
    await act(async () => { jest.advanceTimersByTime(59_999); });
    expect(refresh).toHaveBeenCalledTimes(0);
    await act(async () => { jest.advanceTimersByTime(1); });
    expect(refresh).toHaveBeenCalledTimes(1);
  } finally {
    await act(async () => root.unmount());
  }
});

it("plays one event at a time in order, pauses and preserves the remaining delay", async () => {
  const events: FloorEvent[] = ["commit", "bot"].map((kind, index) => ({
    id: String(index),
    kind: kind === "commit" ? "commit" : "bot",
    number: 12998,
    line: "Server",
    builder: "B",
    station: kind === "commit" ? "Write" : "Review",
    at: now,
    observed_at: now,
  }));
  function Sample({ running }: { running: boolean }) {
    const current = useEventPlayer(now, events, running);
    return <span>{current?.event.kind ?? "quiet"}</span>;
  }
  const container = document.createElement("div");
  const root = createRoot(container);
  const draw = (running: boolean) => act(async () => root.render(<Sample running={running} />));
  const advance = (ms: number) => act(async () => { jest.advanceTimersByTime(ms); });
  try {
    await draw(true);
    await advance(0);
    expect(container.textContent).toBe("commit");
    await advance(10_000);
    await draw(false);
    await advance(180_000);
    expect(container.textContent).toBe("commit");
    await draw(true);
    await advance(139_999);
    expect(container.textContent).toBe("commit");
    await advance(1);
    expect(container.textContent).toBe("bot");
    await advance(1200);
    expect(container.textContent).toBe("quiet");
  } finally {
    await act(async () => root.unmount());
  }
});

it("plays the recording for 60 visible seconds and leaves the clock at the final read", async () => {
  const first = "2026-11-18T17:50:00Z";
  const archive = {
    date: "2026-11-18",
    through: now,
    events: [{
      id: "one", kind: "move", number: 12998, line: "Server", builder: "B",
      station: "Test", from: "Write", at: first, observed_at: now,
    }] satisfies FloorEvent[],
  };
  function Sample({ visible }: { visible: boolean }) {
    const history = useDayReplay(visible);
    return <button onClick={() => history.open(archive)}>{history.clock ?? "Replay"}</button>;
  }
  const container = document.createElement("div");
  const root = createRoot(container);
  const render = (visible: boolean) => act(async () => root.render(<Sample visible={visible} />));
  const advance = (ms: number) => act(async () => { jest.advanceTimersByTime(ms); });
  try {
    await render(true);
    await act(async () => { container.querySelector("button")!.click(); });
    await advance(10_000);
    await render(false);
    await advance(75_000);
    expect(container.textContent).toBe(first);
    await render(true);
    await advance(49_999);
    expect(container.textContent).toBe(first);
    await advance(1);
    expect(container.textContent).toBe(now);
  } finally {
    await act(async () => root.unmount());
  }
});

it("uses only published station transfers within the current Pacific day", () => {
  const transfer = { number: 12998, line: "Server", from: "Write", to: "Test" } as const;
  const reading = replayReading({
    ...snapshot,
    generated_at: "2026-11-20T08:10:00Z",
    changes: [],
    transitions: [
      { ...transfer, number: 12997, at: "2026-11-20T07:59:00Z" },
      { ...transfer, at: "2026-11-20T08:01:00Z" },
      { ...transfer, number: 12999, at: "2026-11-20T08:12:00Z" },
    ],
  }, "2026-11-20");
  expect(reading?.events).toEqual([
    expect.objectContaining({ number: 12998, builder: undefined, from: "Write", station: "Test" }),
  ]);
});

it("keeps earlier reads across a reload, deduplicates overlaps, and resets at Pacific midnight", async () => {
  const first = { number: 12998, line: "Server", from: "Write", to: "Test", at: now } as const;
  const later = { ...first, number: 12999, at: "2026-11-18T18:01:00Z" };
  function Browser({ current, day }: { current: FactoryData; day: string }) {
    const journal = useReplayJournal(current, day);
    return <output>{journal?.events.map((event) => event.number).join(",")}</output>;
  }
  const container = document.createElement("div");
  let root = createRoot(container);
  const paint = (current: FactoryData, day = "2026-11-18") =>
    act(async () => root.render(<Browser current={current} day={day} />));
  const storageKey = "factory-today-transfers-v1";
  localStorage.removeItem(storageKey);
  try {
    await paint({ ...snapshot, transitions: [first] });
    expect(container.textContent).toBe("12998");
    await paint({ ...snapshot, generated_at: later.at, transitions: [later, first] });
    expect(container.textContent).toBe("12998,12999");
    await act(async () => root.unmount());
    root = createRoot(container);
    await paint({ ...snapshot, generated_at: "2026-11-18T18:30:00Z", transitions: [] });
    expect(container.textContent).toBe("12998,12999");
    await paint({ ...snapshot, generated_at: "2026-11-19T08:01:00Z", transitions: [] }, "2026-11-19");
    expect(container.textContent).toBe("");
  } finally {
    await act(async () => root.unmount());
    localStorage.removeItem(storageKey);
  }
});

it("puts the same sourced hold on the stack light, bay, note and tab", async () => {
  watchMotion();
  const container = document.createElement("div");
  const root = createRoot(container);
  try {
    await act(async () =>
      root.render(
        <FactoryFloor data={snapshot} lastGoodAt={now} renderedAt={now} />,
      ),
    );
    const text = "Loading dock, Server: on hold since 9:20 AM PT after test_floor failed.";
    expect(container.querySelector('[data-verdict="red"] strong')?.textContent).toBe(text);
    expect(container.querySelector('[aria-label="Foreman’s note"] p')?.textContent).toMatch(new RegExp(`^${text}`));
    expect(container.querySelector('[data-line="Server"][data-bay="Merge line"]')?.getAttribute("data-alert")).toBe("red");
    expect(container.querySelectorAll('[data-alert="red"]')).toHaveLength(1);
    expect(document.title).toBe(`${text} | The Factory`);
  } finally {
    await act(async () => root.unmount());
  }
});

it("uses amber for a missing reading or a stopped refresh and green only for a verified clear floor", () => {
  const clear = {
    ...snapshot,
    stops: [],
    signals: { tests: "passing", testflight: "success" },
  };
  expect(floorVerdict(clear, false, now)).toMatchObject({ level: "green", text: "All clear." });
  expect(floorVerdict(clear, true, now)).toMatchObject({ level: "amber", text: "Not updating." });
  expect(floorVerdict({ ...clear, stops: undefined }, false, now).level).toBe("amber");
  expect(floorVerdict({ ...clear, signals: { ...clear.signals, tests: "unknown" } }, false, now).level).toBe("amber");
  expect(floorVerdict(null, true, now).level).toBe("amber");
  expect(factoryTabTitle(floorVerdict(clear, false, now))).toBe("All clear. | The Factory");
});

it("marks a crowded bay after its recorded jam reaches 30 minutes", () => {
  const jam = {
    key: "crowd:Test",
    kind: "crowd",
    line: null,
    station: "Test",
    started_at: "2026-11-18T17:29:59Z",
    qualifies_at: "2026-11-18T17:59:59Z",
    ended_at: null,
    count: 11,
  } as const;
  const clear: FactoryData = {
    ...snapshot,
    changes: [
      ...Array.from({ length: 10 }, (_, index) => ({ ...base, number: base.number + index })),
      { ...base, line: "Website", number: base.number + 10 },
    ],
    stops: [],
    jams: [jam],
    signals: { tests: "passing", testflight: "success" },
  };
  expect(floorVerdict(clear, false, "2026-11-18T17:59:58Z").level).toBe("green");
  expect(floorVerdict(clear, false, now).bays).toEqual([
    { line: "Server", station: "Test", level: "amber", text: "Checks, Server: 10 changes are backed up here.", crowded: true },
  ]);
});

it("counts injury-free hours only over a complete reading", () => {
  const reading = {
    from: "2026-11-19T17:00:00Z",
    available: true,
    events: [
      { kind: "wrong-number" as const, number: 13112, at: "2026-11-19T19:00:00Z" },
      { kind: "switched-off" as const, number: 7024584672, at: "2026-11-19T22:00:00Z" },
    ],
  };
  expect(injuryHours(reading, "2026-11-19T23:30:00Z")).toEqual({
    current: 1, record: 3, last: reading.events[1],
  });
  expect(hours(1)).toBe("1 hour");
  expect(injuryHours({ ...reading, available: false }, now)).toBeNull();
});

it("times only complete Bench to Live trips and names the longest known wait", () => {
  const live: Change = { ...base, station: "Live", live_at: now };
  const complete = { ...live, bench_seen_at: "2026-11-18T17:45:00Z" };
  const waiting: Change = { ...base, station: "Review", station_since: "2026-11-18T17:50:00Z" };
  expect(clipboard(now, [live, complete], [waiting])).toEqual({
    benchMedian: 900, longest: { change: waiting, seconds: 600 },
  });
  expect(clipboard(now, [live], []).benchMedian).toBeNull();
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
    expect(container.textContent).not.toContain(snapshot.notes!.floor);
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

it("keeps lane speech, its pose and the daily count readable with motion off", async () => {
  const reduce = watchMotion();
  reduce();
  const container = document.createElement("div");
  const root = createRoot(container);
  const data: FactoryData = {
    ...snapshot,
    speech: { B: { text: "#12998 is in checks.", mood: "working", source: "model" } },
    model_usage: { day: "2026-11-18", calls: 3 },
  };
  try {
    await act(async () => root.render(<FactoryFloor data={data} lastGoodAt={now} renderedAt={now} />));
    const builder = container.querySelector('[data-crew="B"]');
    expect(builder?.getAttribute("data-pose")).toBe("working");
    expect(builder?.querySelector('p[data-source="model"]')?.textContent).toBe("#12998 is in checks.");
    expect(container.textContent).toContain("3 of 200 model calls made today.");
    expect(container.querySelector("[data-factory]")?.getAttribute("data-motion")).toBe("paused");
  } finally {
    await act(async () => root.unmount());
  }
});

it("rotates one visible floor bubble between workers and holds it under reduced motion", async () => {
  const reduce = watchMotion();
  const container = document.createElement("div");
  const root = createRoot(container);
  const data: FactoryData = {
    ...snapshot,
    speech: {
      B: { text: "The scoreboard gets a fresh coat. #12998 is in checks.", mood: "working", source: "model" },
      S: { text: "The labels get a polish. #12999 is at the loading dock.", mood: "waiting", source: "model" },
    },
  };
  const bubbles = () => Array.from(container.querySelectorAll("[data-floor-speech]"));
  try {
    await act(async () => root.render(<FactoryFloor data={data} lastGoodAt={now} renderedAt={now} />));
    expect(bubbles()).toHaveLength(1);
    expect(bubbles()[0].getAttribute("data-floor-speech")).toBe("S");
    expect(bubbles()[0].textContent).toContain("The labels get a polish.");

    await act(async () => { jest.advanceTimersByTime(8_000); });
    expect(bubbles()).toHaveLength(1);
    expect(bubbles()[0].getAttribute("data-floor-speech")).toBe("B");
    expect(bubbles()[0].textContent).toContain("The scoreboard gets a fresh coat.");

    await act(async () => reduce());
    await act(async () => { jest.advanceTimersByTime(16_000); });
    expect(bubbles()).toHaveLength(1);
    expect(bubbles()[0].getAttribute("data-floor-speech")).toBe("B");
  } finally {
    await act(async () => root.unmount());
  }
});

it("ranks named builders by distinct delivered changes and keeps ties", () => {
  const delivery = (builder: Change["builder"], number: number) => ({ ...base, builder, number });
  const first = delivery("B", 13021);
  expect(builderOfDay([
    first, { ...first, line: "Website" }, delivery("B", 13022),
    delivery("D", 13023), delivery("D", 13024), delivery("E", 13025),
    delivery("Other", 13026), delivery("Other", 13027), delivery("Other", 13028),
  ])).toEqual({ builders: ["B", "D"], count: 2 });
  expect(builderOfDay([delivery("Other", 13026)])).toBeNull();
});

it("only displays a daily leader for deliveries recorded today with complete coverage", async () => {
  watchMotion();
  const container = document.createElement("div");
  const root = createRoot(container);
  const live = snapshot.changes[3];
  const data = {
    ...snapshot,
    changes: [live, { ...live, line: "Website" as const }, {
      ...live, number: 13028, builder: "D" as const, live_at: "2026-11-18T07:59:00Z",
    }],
  };
  const sign = () => container.querySelector('[aria-label="Builder of the day"]')?.textContent;
  try {
    await act(async () => root.render(<FactoryFloor data={data} lastGoodAt={now} renderedAt={now} />));
    expect(sign()).toContain("Apple · 1 change live");
    const incomplete = { ...data, coverage: ["Server deployment could not be confirmed."] };
    await act(async () => root.render(<FactoryFloor data={incomplete} lastGoodAt={now} renderedAt={now} />));
    expect(sign()).toContain("Delivery records are incomplete");
  } finally {
    await act(async () => root.unmount());
  }
});

it("keeps a followed crate flagged after a reload and shows its observed station times", async () => {
  watchMotion()();
  const container = document.createElement("div");
  let root = createRoot(container);
  const stubbed = ["showModal", "close"] as const;
  const original = stubbed.map((name) => Object.getOwnPropertyDescriptor(HTMLDialogElement.prototype, name));
  stubbed.forEach((name) => Object.defineProperty(HTMLDialogElement.prototype, name, {
    configurable: true,
    value(this: HTMLDialogElement) { this.open = name === "showModal"; },
  }));
  const key = "factory-followed-crates-v1";
  localStorage.removeItem(key);
  const button = (label: string) => Array.from(container.querySelectorAll("button")).find(
    (el) => el.textContent?.trim() === label || el.getAttribute("aria-label") === label,
  )!;
  const crate = (parent: ParentNode = container) => parent.querySelector<HTMLButtonElement>('[data-crate="12998"]')!;
  try {
    await act(async () => root.render(<FactoryFloor data={snapshot} lastGoodAt={now} renderedAt={now} />));
    await act(async () => crate().click());
    expect(container.querySelector("dialog")?.textContent).toContain("Station times are missing for this line.");
    await act(async () => button("Follow this crate").click());
    expect(crate().dataset.followed).toBe("true");
    expect(localStorage.getItem(key)).toBe("[12998]");
    await act(async () => root.unmount());
    root = createRoot(container);

    const moved: FactoryData = {
      ...snapshot,
      changes: [{ ...base, station: "Review", journey: [
        { station: "Test", first_seen_at: "2026-11-18T17:50:00Z", last_seen_at: "2026-11-18T17:55:00Z" },
        { station: "Review", first_seen_at: now },
      ] }],
    };
    await act(async () => root.render(<FactoryFloor data={moved} lastGoodAt={now} renderedAt={now} />));
    expect(crate().closest('[data-bay="Review"]')).not.toBeNull();
    expect(crate().dataset.followed).toBe("true");
    await act(async () => button("Followed crates 1").click());
    const dialog = container.querySelector("dialog")!;
    await act(async () => crate(dialog).click());
    expect(dialog.textContent).toContain("5 min between reads");
    expect(dialog.textContent).toContain("Inspection");
    await act(async () => button("Stop following").click());
    expect(localStorage.getItem(key)).toBe("[]");
    expect(crate().dataset.followed).toBeUndefined();
  } finally {
    await act(async () => root.unmount());
    localStorage.removeItem(key);
    stubbed.forEach((name, index) => {
      const descriptor = original[index];
      if (descriptor) Object.defineProperty(HTMLDialogElement.prototype, name, descriptor);
      else Reflect.deleteProperty(HTMLDialogElement.prototype, name);
    });
  }
});

it("keeps one mascot by the stack light and rests it after a quiet read", async () => {
  const reduce = watchMotion();
  const container = document.createElement("div");
  const root = createRoot(container);
  const clear: FactoryData = { ...snapshot, stops: [], signals: { tests: "passing", testflight: "success" } };
  const mascot = (level: string) => {
    const figures = container.querySelectorAll<HTMLElement>("[data-mascot-pose]");
    expect(figures).toHaveLength(1);
    expect(figures[0].dataset.mascot).toBe(level);
    expect(figures[0].closest("[data-verdict]")?.getAttribute("data-verdict")).toBe(level);
    return figures[0].dataset;
  };
  try {
    await act(async () => root.render(<FactoryFloor data={snapshot} lastGoodAt={now} renderedAt={now} />));
    expect(mascot("red").mascotPose).toBe("standing");
    expect(mascot("red").mascotMotion).toBeUndefined();
    await act(async () => reduce());
    await act(async () => { jest.advanceTimersByTime(16_000); });
    expect(mascot("red").mascotMotion).toBeUndefined();
    await act(async () => root.render(<FactoryFloor data={snapshot} readFailed lastGoodAt={now} renderedAt={now} />));
    expect(mascot("amber").mascotMotion).toBeUndefined();
    const quiet = {
      ...clear,
      changes: clear.changes.map(change => ({ ...change, last_activity: "2026-11-18T17:40:00Z" })),
    };
    await act(async () => root.render(<FactoryFloor data={quiet} lastGoodAt={now} renderedAt={now} />));
    expect(mascot("green").mascotPose).toBe("asleep");
  } finally {
    await act(async () => root.unmount());
  }
});

it("starts a real transfer when an open page receives a newer read", async () => {
  watchMotion();
  const container = document.createElement("div");
  const root = createRoot(container);
  const next = "2026-11-18T18:00:10Z";
  const selector = '[data-event-id^="transfer:"]';
  try {
    const before: FactoryData = { ...snapshot, transitions: [], changes: [{ ...base, station: "Write" }] };
    await act(async () => root.render(<FactoryFloor data={before} lastGoodAt={now} renderedAt={now} />));
    expect(container.querySelector(selector)).toBeNull();
    const after: FactoryData = {
      ...snapshot, generated_at: next,
      transitions: [{ number: 12998, line: "Server", from: "Write", to: "Test", at: next, observed_at: next }],
    };
    await act(async () => root.render(<FactoryFloor data={after} lastGoodAt={next} renderedAt={next} />));
    await act(async () => { jest.advanceTimersByTime(1); });
    expect(container.querySelector(selector)?.textContent).toContain("#12998");
    expect(container.querySelector('[data-arriving="true"]')?.textContent).toContain("#12998");
    expect(container.querySelector('[data-mascot-action="pushing"]')?.textContent).toContain("#12998");
    expect(container.querySelectorAll("[data-mascot-pose]")).toHaveLength(1);
    await act(async () => { jest.advanceTimersByTime(1500); });
    expect(container.querySelector(selector)).toBeNull();
    expect(container.querySelector('[data-arriving="true"]')).toBeNull();
    expect(container.querySelector('[data-mascot-action="pushing"]')).toBeNull();
    await act(async () => root.render(<FactoryFloor data={after} lastGoodAt={next} renderedAt={next} />));
    await act(async () => { jest.advanceTimersByTime(1); });
    expect(container.querySelector(selector)).toBeNull();
  } finally {
    await act(async () => root.unmount());
  }
});
