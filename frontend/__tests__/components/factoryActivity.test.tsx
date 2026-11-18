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

it("draws an old valid floor, dimmed and motionless, with its age", () => {
  const html = renderToStaticMarkup(
    <FactoryFloor
      data={data}
      lastGoodAt={data.generated_at}
      renderedAt="2026-11-18T17:50:00Z"
    />,
  );
  expect(html).toContain('data-reader="behind"');
  expect(html).toContain('data-motion="paused"');
  expect(html).toContain(
    "Last read 7:58 AM PT, 1 hr 51 min ago. The reader is behind.",
  );
  expect(html).toContain("On the floor now");
  expect(html).not.toContain("The floor can&#x27;t be read right now");
});

it("prints both observed November 18 stoppages at 10 AM Pacific", () => {
  const messages = (data.stops as Stop[]).map((s) =>
    stopText(s, "2026-11-18T18:00:00Z"),
  );
  expect(messages).toContain(
    "Server: nothing merged for 3 hr 50 min, 14 waiting.",
  );
  expect(messages).toContain("Announced at 8:47 AM, not merged.");
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
    },
  ];
  expect(beltFlowing(flowing, "Server", 2, "2026-11-18T18:01:00Z")).toBe(false);
  expect(readerBehind(flowing, "2026-11-18T18:15:00Z")).toBe(false);
});

it("limits a Live bay to eight crates while retaining its full count", () => {
  const live = data.changes.find((c) => c.station === "Live")!;
  const floor = {
    ...data,
    changes: Array.from({ length: 12 }, (_, i) => ({
      ...live,
      number: 30000 + i,
      line: "Server" as const,
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
  expect((html.match(/data-crate=/g) ?? []).length).toBe(8);
  expect(html).toContain("+4 earlier today");
  expect(html).toContain("12 today");
});
