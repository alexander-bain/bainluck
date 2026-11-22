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

it("keeps the old floor motionless without claiming updates stopped when no work finished", () => {
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
  expect(html).toContain('data-reader="behind"');
  expect(html).toContain('data-motion="paused"');
  expect(html).toContain('data-reading-state="quiet"');
  expect(html).toContain("Last published 1 hr 51 min ago.");
  expect(html).not.toContain("Updates have stopped.");
  expect(html).toContain('data-factory-row="Server"');
  expect(html).not.toContain("The floor can&#x27;t be read right now");
});

it("prints both observed November 18 stoppages at 10 AM Pacific", () => {
  const messages = (data.stops as Stop[]).map((s) =>
    stopText(s, "2026-11-18T18:00:00Z"),
  );
  expect(messages).toContain("Server loading dock has stalled.");
  expect(messages).toContain("Server announced a merge at 8:47 AM PT.");
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
