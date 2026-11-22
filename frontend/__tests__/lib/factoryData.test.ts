import { createFactoryReader, validateSnapshot } from "@/app/factory/data";

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
