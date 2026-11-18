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
  expect(html).toContain("Shipped today");
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
  expect(html).toContain("Shipped today");
  expect(html).toContain('data-motion="paused"');
  expect(html).toContain("Not updating");
  expect(html).toContain(
    "Last read 7:58 AM PT, 4 min ago. Updates have stopped.",
  );
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
