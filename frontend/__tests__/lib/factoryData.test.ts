import { createFactoryReader } from "@/app/factory/data";

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
    expect(await read()).toEqual({
      data,
      lastGoodAt: data.generated_at,
      readFailed: false,
    });
    expect(await read()).toEqual({
      data,
      lastGoodAt: data.generated_at,
      readFailed: true,
    });
  });
});
