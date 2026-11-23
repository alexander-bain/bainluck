import React from "react";
import { renderToStaticMarkup } from "react-dom/server";
import FactoryFloor from "@/app/factory/FactoryFloor";
import { beltFlowing, readerBehind, stopText } from "@/app/factory/activity";
import type { FactoryData, Stop } from "@/app/factory/types";
import morning from "../../../scripts/factory/tests/fixtures/morning-nov18.json";

jest.mock("next/navigation", () => ({
  useRouter: () => ({ refresh: jest.fn() }),
}));
jest.mock("@/hooks/usePageTracking", () => ({ usePageTracking: jest.fn() }));
jest.mock("@/hooks/useScrollDepth", () => ({ useScrollDepth: jest.fn() }));
jest.mock("@/hooks/useEngagementTime", () => ({
  useEngagementTime: jest.fn(),
}));

const data = {
  schema_version: 1,
  generated_at: morning.provenance.snapshot_generated_at,
  observed_since: morning.observed_since,
  changes: morning.changes,
  stops: morning.expected_stops,
  jams: [],
  signals: morning.master,
  coverage: [],
} as FactoryData;

it("shows real bay states while keeping a quiet floor motionless", () => {
  const renderedAt = "2026-11-18T17:50:00Z";
  const html = renderToStaticMarkup(
    <FactoryFloor
      data={data}
      lastGoodAt={data.generated_at}
      renderedAt={renderedAt}
      activity={{
        checkedAt: renderedAt,
        masterAt: data.generated_at,
        ciAt: data.generated_at,
        collector: { at: data.generated_at, failed: false },
      }}
    />,
  );
  expect(html).toContain('data-reader="current"');
  expect(html).toContain('data-motion="paused"');
  expect(html).toContain('data-reading-state="quiet"');
  expect(html).toContain("Last published 1 hr 51 min ago.");
  expect(html).toContain('title="Long wait"');
  expect(html).toContain('title="Idle"');
  expect(html).not.toContain('title="Paused"');
  expect(html).not.toContain("Updates have stopped.");
  expect(html).toContain('data-factory-row="Server"');
  expect(html).not.toContain("The floor can&#x27;t be read right now");
});

it("names the server release and failed test gate in the 3:36 PM replay", () => {
  const now = "2026-11-22T23:36:58.642342Z";
  const held: FactoryData = {
    ...data,
    generated_at: now,
    changes: [],
    stops: [{
      kind: "master", line: "Server", station: "Ship", number: 13444,
      since: "2026-11-22T23:35:42Z", count: 1, level: "amber",
    }],
    signals: { tests: "failing", testflight: "success" },
  };
  const text = "The server release for #13444 is on hold because a server test failed.";
  const html = renderToStaticMarkup(<FactoryFloor data={held} lastGoodAt={now} renderedAt={now} />);
  expect(html).toContain(text);
  expect(html).not.toContain("Checks, Server: the shared tests failed");
  expect(html).not.toContain("All clear.");
});

it("says the next reading is waiting for a machine and reserves Paused for a stopped or unconfirmed read", () => {
  const now = "2026-11-18T17:50:00Z";
  const props = { data, lastGoodAt: data.generated_at, renderedAt: now };
  const activity = {
    checkedAt: now,
    masterAt: "2026-11-18T17:27:00Z",
    ciAt: data.generated_at,
    collectorQueuedAt: "2026-11-18T17:30:00Z",
    collector: { at: data.generated_at, failed: false },
  };
  const waiting = renderToStaticMarkup(<FactoryFloor {...props} activity={activity} />);
  expect(waiting).toContain('data-reading-state="waiting"');
  expect(waiting).toContain("The next reading is waiting for a machine.");
  expect(waiting).not.toContain("Updates have stopped.");
  expect(waiting).not.toContain('title="Paused"');

  const failure = { ...activity, collector: { at: "2026-11-18T17:49:00Z", failed: true } };
  const failed = renderToStaticMarkup(<FactoryFloor {...props} activity={failure} />);
  expect(failed).toContain('data-reading-state="failed"');
  expect(failed).toContain("Updates have stopped.");
  expect(failed).toContain('title="Paused"');

  const lastKnown = renderToStaticMarkup(<FactoryFloor {...props} />);
  expect(lastKnown).toContain("Showing the last published floor.");
  expect(lastKnown).toContain('title="Paused"');
});

it("prints both observed November 18 stoppages at 10 AM Pacific", () => {
  const messages = (data.stops as Stop[]).map((s) =>
    stopText(s, "2026-11-18T18:00:00Z"),
  );
  expect(messages).toContain("Server loading dock is waiting for a merge.");
  expect(messages).toContain("Server announced a merge at 8:47 AM PT.");
});

it("shows an off-floor lane's fresh report in its card and speech until it expires", () => {
  const now = "2026-11-22T19:55:00Z";
  const phrase = "retaking the iPad screenshots from build 5852";
  const fallback = "There is no recent activity for this lane.";
  const reading: FactoryData = {
    ...data,
    generated_at: now,
    stops: [],
    changes: [],
    speech: { F: { text: fallback, mood: "asleep", source: "facts" } },
    lane_updates: { F: { at: "2026-11-22T16:55:00Z", text: phrase } },
  };
  const rendered = (clock: string, changes = reading.changes) => renderToStaticMarkup(
    <FactoryFloor data={{ ...reading, changes }} lastGoodAt={now} renderedAt={clock} />,
  );
  const html = rendered(now);
  expect(html).toMatch(/data-floor-speech="F"[^]*?data-source="lane"[^]*?retaking the iPad screenshots from build 5852/);
  expect(html).toMatch(/data-crew="F"[^]*?Posted at 8:55 AM PT[^]*?retaking the iPad screenshots from build 5852/);
  expect(html).not.toContain(fallback);
  const expired = rendered("2026-11-22T19:55:00.001Z");
  expect(expired).toContain(fallback);
  expect(expired).not.toContain(phrase);
  expect(rendered(now, [{ ...data.changes[0], builder: "F", station: "Write", merged_at: null,
    parked: false, side_track: false, held_for_108: false, bot_update: false }])).not.toContain(phrase);
});

it("describes the completed checks for #13424 as waiting for a merge despite legacy job totals", () => {
  const now = "2026-11-22T19:37:00Z";
  const stop = {
    kind: "line-stalled", line: "Server", station: "Merge line", level: "amber",
    number: 13424, count: 1, since: "2026-11-22T18:55:00Z", waiting_since: "2026-11-22T19:03:00Z",
    machines: { running: 15, waiting: 17 },
  } as const;
  const reading: FactoryData = {
    ...data,
    generated_at: now,
    stops: [stop],
    changes: [],
    signals: {
      tests: "passing", testflight: "success",
      checks_queue: { machines: 40, running: 3, waiting: 0, machines_busy: 15,
        longest_wait_minutes: null, queued_without_jobs: 0 },
    },
  };
  const html = renderToStaticMarkup(<FactoryFloor data={reading} lastGoodAt={now} renderedAt={now} />);
  expect(html).toContain("Loading dock, Server: #13424 is waiting for a merge.");
  expect(html).not.toContain("17 waiting");
  expect(html).toContain("<dt>Runs waiting</dt><dd>0</dd>");
  expect(html).toContain("Runs waiting counts runs with a job queued for a machine and none running.");
});

it("runs only recently crossed belts and stops them for an old read or a blocking station", () => {
  const flowing: FactoryData = {
    ...data,
    generated_at: "2026-11-18T18:00:00Z",
    stops: [],
    transitions: [
      {
        number: 12971,
        line: "Server",
        from: "Review",
        to: "Ship",
        at: "2026-11-18T18:00:00Z",
      },
    ],
  };
  expect(beltFlowing(flowing, "Server", 2, "2026-11-18T18:01:00Z")).toBe(true);
  expect(beltFlowing(flowing, "Server", 0, "2026-11-18T18:01:00Z")).toBe(false);
  expect(beltFlowing(flowing, "Website", 2, "2026-11-18T18:01:00Z")).toBe(
    false,
  );
  expect(beltFlowing(flowing, "Server", 2, "2026-11-18T18:16:00Z")).toBe(false);
  flowing.stops = [
    {
      kind: "hold",
      line: "Server",
      station: "Merge line",
      since: flowing.generated_at,
      count: 1,
      level: "red",
      source: { id: 6994962892, author: "Builder B" },
    },
  ];
  expect(beltFlowing(flowing, "Server", 2, "2026-11-18T18:01:00Z")).toBe(false);
  expect(readerBehind(flowing, "2026-11-18T18:15:00Z")).toBe(false);
});

it("pairs each factory station with its engineering name", () => {
  const html = renderToStaticMarkup(
    <FactoryFloor data={data} lastGoodAt={data.generated_at} renderedAt={data.generated_at} />,
  );
  for (const [name, term] of [
    ["Bench", "writing"],
    ["Checks", "automated tests"],
    ["Inspection", "review"],
    ["Loading dock", "merge queue"],
    ["Truck", "deploying"],
    ["Live", "in readers’ hands"],
  ]) {
    expect(html).toContain(`<strong>${name}</strong><span>${term}</span>`);
  }
  expect(html).toContain("A crate is one change.");
});

it.each(["Live", "Test"] as const)(
  "shows two crates and an overflow control at %s",
  (station) => {
  const live = data.changes.find((c) => c.station === "Live")!;
  const floor = {
    ...data,
    changes: Array.from({ length: 12 }, (_, i) => ({
      ...live,
      number: 30000 + i,
      line: "Server" as const,
      station,
      live_at: "2026-11-18T18:00:00Z",
    })),
    generated_at: "2026-11-18T18:00:00Z",
    stops: [],
  };
  const html = renderToStaticMarkup(
    <FactoryFloor
      data={floor}
      lastGoodAt={floor.generated_at}
      renderedAt={floor.generated_at}
    />,
  );
    expect((html.match(/data-crate=/g) ?? []).length).toBe(2);
    expect(html).toContain("+10 more");
    expect(html).toContain(station === "Live" ? "12 shipped" : "12 here");
  },
);

it("shows active workers even when their crates have not changed bays", () => {
  const now = "2026-11-18T18:00:00Z";
  const base = {
    ...data.changes[0],
    line: "Server" as const,
    side_track: false,
    merged_at: null,
  };
  const snapshot: FactoryData = {
    ...data,
    generated_at: now,
    stops: [],
    transitions: [],
    changes: [
      {
        ...base,
        number: 1,
        station: "Write",
        last_activity: "2026-11-18T17:45:00Z",
      },
      {
        ...base,
        number: 2,
        station: "Test",
        last_activity: "2026-11-18T17:44:59Z",
      },
    ],
  };
  const html = renderToStaticMarkup(
    <FactoryFloor data={snapshot} lastGoodAt={now} renderedAt={now} />,
  );
  expect(html).toContain(
    'data-bay="Write" data-waiting="1" data-worker-state="working"',
  );
  expect(html).toContain(
    'data-bay="Test" data-waiting="1" data-worker-state="asleep"',
  );
  expect(html).not.toContain('data-flowing="true"');
});

it("omits the question mark on a Ship crate awaiting live confirmation", () => {
  const now = "2026-11-18T18:00:00Z";
  const snapshot: FactoryData = {
    ...data,
    generated_at: now,
    changes: [
      {
        ...data.changes[0],
        station: "Ship",
        side_track: false,
        unsure: true,
        reasons: ["Waiting for deployment evidence on this line."],
      },
    ],
  };
  const html = renderToStaticMarkup(
    <FactoryFloor data={snapshot} lastGoodAt={now} renderedAt={now} />,
  );
  expect(html).toContain("data-crate=");
  expect(html).not.toContain(">?</span>");
});

it("shows red only for an attributed NOW hold and drops the unsupported legacy warning", () => {
  const now = "2026-11-18T18:00:00Z";
  const hold = {
    kind: "hold",
    line: "Server",
    station: "Merge line",
    since: "2026-11-18T17:50:00Z",
    count: 1,
    level: "red",
  } as const;
  const verified = { ...hold, source: { id: 6994962892, author: "Builder B" } };
  const snapshot: FactoryData = {
    ...data,
    generated_at: now,
    stops: [verified, { ...hold, line: "Website" }],
  };
  const html = renderToStaticMarkup(
    <FactoryFloor data={snapshot} lastGoodAt={now} renderedAt={now} />,
  );
  expect((html.match(/data-level="red"/g) ?? []).length).toBe(1);
  expect(html).toContain("#issuecomment-6994962892");
  expect(html).toContain("9:50 AM PT · Builder B");
  expect(html).not.toContain("Website on HOLD");
});

it("puts sent-back changes at Write and bot updates on a separate shelf", () => {
  const now = "2026-11-18T18:00:00Z";
  const base = { ...data.changes[0], merged_at: null, side_track: false };
  const snapshot: FactoryData = {
    ...data,
    generated_at: now,
    stops: [],
    changes: [
      {
        ...base,
        number: 12765,
        line: "Server",
        station: "Write",
        sent_back: true,
      },
      {
        ...base,
        number: 12211,
        line: "Server",
        station: "Review",
        bot_update: true,
      },
    ],
  };
  const html = renderToStaticMarkup(
    <FactoryFloor data={snapshot} lastGoodAt={now} renderedAt={now} />,
  );
  expect(html).toContain('data-crate="12765" data-station="Server/Write"');
  expect(html).toContain("Sent back");
  expect(html).not.toContain('data-crate="12211"');
  expect(html).toContain("Bot updates <strong>1</strong>");
});
