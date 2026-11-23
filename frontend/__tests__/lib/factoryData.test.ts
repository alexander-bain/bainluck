import { createFactoryReader, validateSnapshot } from "@/app/factory/data";
import type { FactoryData } from "@/app/factory/types";

const data = {
  schema_version: 1,
  generated_at: "2026-11-18T01:14:00Z",
  observed_since: "2026-11-18T01:14:00Z",
  changes: [],
  jams: [],
  signals: {},
  coverage: [],
};

describe("Factory live reads", () => {
  it("refuses malformed data and excludes the legacy cache from the page", async () => {
    const fetcher = jest
      .fn()
      .mockResolvedValueOnce({
        ok: true,
        json: async () => ({ ...data, _collector: { private: "metadata" } }),
      })
      .mockResolvedValue({
        ok: true,
        json: async () => ({ ...data, generated_at: "invalid" }),
      });
    const read = createFactoryReader(fetcher as typeof fetch);
    const first = await read();
    expect(first).toEqual({
      data,
      lastGoodAt: data.generated_at,
      readAt: expect.any(String),
      readFailed: false,
    });
    expect(await read()).toEqual({
      data,
      lastGoodAt: data.generated_at,
      readAt: first.readAt,
      readFailed: true,
    });
  });
});

it("accepts the Factory lane and excludes unpublishable lane updates", () => {
  const payload = validateSnapshot({
    ...data,
    signals: { tests: "passing", testflight: "success" },
    changes: [{
      number: 13434, title: "Explain Factory picture refusals and runner waits",
      builder: "Factory", station: "Write", line: "Website",
      last_activity: data.generated_at, merged_at: null, live_at: null,
      unsure: false, reasons: [], side_track: false, timing: null,
    }],
    lane_updates: {
      Factory: { at: data.generated_at, text: "checking the floor" },
      C: { at: data.generated_at, text: "visiting sample.invalid" },
      B: { at: data.generated_at, text: "asking @unused" },
      S: { at: "2026-11-18T01:14:01Z", text: "reviewing a capture" },
    },
  });
  expect(payload.changes[0].builder).toBe("Factory");
  expect(payload.lane_updates).toEqual({ Factory: { at: data.generated_at, text: "checking the floor" } });
});

it("keeps only public check-in metadata for signed NOW reports", () => {
  const untrusted = {
    ...data,
    crew_posts: {
      F: { at: "2026-11-18T00:30:00Z", comment_id: 7093663542, body: "Discussion" },
      C: { at: "2026-11-18T00:30:00Z", comment_id: "unsuitable" },
      E: { at: "2026-11-17T22:13:59Z", comment_id: 123 },
      D: { at: "2026-11-18T01:14:01Z", comment_id: 124 },
    },
  };
  const payload = validateSnapshot(untrusted as unknown as FactoryData);
  expect(payload.crew_posts).toEqual({
    F: { at: "2026-11-18T00:30:00.000Z", comment_id: 7093663542 },
    C: { at: "2026-11-18T00:30:00.000Z" },
  });
});
