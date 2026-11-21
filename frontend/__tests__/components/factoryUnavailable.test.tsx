import React from "react";
import { renderToStaticMarkup } from "react-dom/server";
import FactoryFloor from "@/app/factory/FactoryFloor";
import { createFactoryReader } from "@/app/factory/data";
import type { FactoryData } from "@/app/factory/types";

jest.mock("next/navigation", () => ({
  useRouter: () => ({ refresh: jest.fn() }),
}));
jest.mock("@/hooks/usePageTracking", () => ({ usePageTracking: jest.fn() }));
jest.mock("@/hooks/useScrollDepth", () => ({ useScrollDepth: jest.fn() }));
jest.mock("@/hooks/useEngagementTime", () => ({
  useEngagementTime: jest.fn(),
}));

const snapshot: FactoryData = {
  schema_version: 1,
  generated_at: "2026-11-18T15:58:00Z",
  observed_since: "2026-11-18T01:14:00Z",
  changes: [],
  jams: [],
  signals: { tests: "passing", testflight: "success" },
  coverage: [],
};
const response = { ok: true, status: 200, json: async () => snapshot };
const timeout = Object.assign(new Error("The read timed out"), {
  name: "TimeoutError",
});

it("draws the floor when a timed-out read succeeds on retry", async () => {
  const fetcher = jest
    .fn()
    .mockRejectedValueOnce(timeout)
    .mockResolvedValueOnce(response);
  const read = createFactoryReader(fetcher);
  const html = renderToStaticMarkup(
    <FactoryFloor {...await read()} renderedAt="2026-11-18T15:59:00Z" />,
  );
  expect(fetcher).toHaveBeenCalledTimes(2);
  expect(fetcher.mock.calls[0][1].signal).not.toBe(
    fetcher.mock.calls[1][1].signal,
  );
  expect(html).toContain('data-factory-row="Server"');
  expect(html).toContain('data-reader="current"');
  expect(html).not.toContain("The floor can&#x27;t be read right now");
});

it("keeps the earlier floor and shows its age after a timeout", async () => {
  const fetcher = jest
    .fn()
    .mockResolvedValueOnce(response)
    .mockRejectedValue(timeout);
  const cacheWrite = jest.fn();
  const read = createFactoryReader(fetcher, (load) => async () => {
    const entry = await load();
    cacheWrite(entry);
    return entry;
  });
  expect((await read()).data).toEqual(snapshot);

  const html = renderToStaticMarkup(
    <FactoryFloor {...await read()} renderedAt="2026-11-18T16:02:00Z" />,
  );
  expect(fetcher).toHaveBeenCalledTimes(3);
  expect(cacheWrite).toHaveBeenCalledTimes(1);
  expect(html).toContain('data-factory-row="Server"');
  expect(html).toContain('data-motion="paused"');
  expect(html).toContain("Not updating");
  expect(html).toContain(
    "Last read 7:58 AM PT, 4 min ago. Updates have stopped.",
  );
});

it("draws the fresh floor on the first visit after the cache ages out", async () => {
  const visitAt = "2026-11-18T21:38:00Z";
  const clock = jest.spyOn(Date, "now").mockReturnValue(Date.parse(visitAt));
  const cached = {
    data: { ...snapshot, generated_at: "2026-11-18T21:03:00Z" },
    checkedAt: Date.parse("2026-11-18T21:08:00Z"),
  };
  const fresh = { ...snapshot, generated_at: "2026-11-18T21:37:00Z" };
  let finishRead!: () => void;
  const responseInFlight = new Promise((resolve) => {
    finishRead = () => resolve({ ...response, json: async () => fresh });
  });
  const fetcher = jest.fn().mockReturnValue(responseInFlight);
  const read = createFactoryReader(fetcher, (refresh) => async () => {
    // Next returns this old cache entry while it revalidates in the background.
    void refresh();
    return cached;
  });

  try {
    const firstVisit = read();
    await Promise.resolve();
    finishRead();
    const html = renderToStaticMarkup(
      <FactoryFloor {...await firstVisit} renderedAt={visitAt} />,
    );
    expect(fetcher).toHaveBeenCalledTimes(1);
    expect(html).toContain("Read at ");
    expect(html).toContain("1:37 PM");
    expect(html).not.toContain("1:03 PM");
    expect(html).not.toContain("Not updating");
    expect(html).not.toContain("Updates have stopped.");
  } finally {
    clock.mockRestore();
  }
});

it("shows the unreadable state when no read has succeeded", async () => {
  const fetcher = jest.fn().mockRejectedValue(timeout);
  const read = createFactoryReader(fetcher);
  const html = renderToStaticMarkup(
    <FactoryFloor {...await read()} renderedAt="2026-11-18T16:02:00Z" />,
  );
  expect(fetcher).toHaveBeenCalledTimes(2);
  expect(html).toContain("The floor can&#x27;t be read right now");
  expect(html).toContain("No successful copy has been read yet.");
  expect(html).not.toContain("Shipped today");
});

it("shows an unavailable floor and the last good time without any historical counts", () => {
  const html = renderToStaticMarkup(
    <FactoryFloor
      data={null}
      lastGoodAt="2026-11-18T01:14:00Z"
      renderedAt="2026-11-18T02:00:00Z"
    />,
  );
  expect(html).toContain("The floor can&#x27;t be read right now");
  expect(html).toContain("5:14 PM PT");
  expect(html).not.toContain("Shipped today");
  expect(html).not.toContain("Saved snapshot");
});

it("shows the full Checks queue and preserves the floor when its reading is invalid", async () => {
  const queue = {
    waiting: 131, running: 12, machines: 40,
    longest_wait_minutes: 1, queued_without_jobs: 2,
  };
  const read = createFactoryReader(jest.fn()
    .mockResolvedValueOnce({ ...response, json: async () => ({
      ...snapshot, signals: { ...snapshot.signals, checks_queue: queue },
    }) })
    .mockResolvedValueOnce({ ...response, json: async () => ({
      ...snapshot, signals: { ...snapshot.signals, checks_queue: { ...queue, waiting: -1 } },
    }) }));
  const html = renderToStaticMarkup(
    <FactoryFloor {...await read()} renderedAt="2026-11-18T15:59:00Z" />,
  );
  expect(html).toContain('data-queue-waiting="131"');
  expect(html).toContain("Runs running</dt><dd>12");
  expect(html).toContain("Borrowed machines</dt><dd>40");
  expect(html).toContain("Longest wait</dt><dd>1 minute");
  expect(html).toContain("GitHub lists 2 queued runs with no job details.");
  const invalid = renderToStaticMarkup(
    <FactoryFloor {...await read()} renderedAt="2026-11-18T15:59:00Z" />,
  );
  expect(invalid).toContain("Queue details are missing from this read.");
  expect(invalid).toContain('data-factory-row="Server"');
});
