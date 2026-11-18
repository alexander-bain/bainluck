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
  it("keeps the last good time and returns no floor when the next read fails", async () => {
    const fetcher = jest
      .fn()
      .mockResolvedValueOnce({ ok: true, json: async () => data })
      .mockRejectedValueOnce(new Error("offline"));
    const read = createFactoryReader(fetcher as typeof fetch);
    expect((await read()).data?.generated_at).toBe(data.generated_at);
    expect(await read()).toEqual({ data: null, lastGoodAt: data.generated_at });
  });

  it("keeps an unknown first failure explicit", async () => {
    const read = createFactoryReader(
      jest.fn().mockResolvedValue({ ok: false }) as typeof fetch,
    );
    expect(await read()).toEqual({ data: null, lastGoodAt: null });
  });

  it("refuses malformed data and excludes the legacy cache from the page", async () => {
    const fetcher = jest
      .fn()
      .mockResolvedValueOnce({
        ok: true,
        json: async () => ({ ...data, _collector: { private: "metadata" } }),
      })
      .mockResolvedValueOnce({
        ok: true,
        json: async () => ({ ...data, generated_at: "invalid" }),
      });
    const read = createFactoryReader(fetcher as typeof fetch);
    expect(await read()).toEqual({ data, lastGoodAt: data.generated_at });
    expect(await read()).toEqual({ data: null, lastGoodAt: data.generated_at });
  });
});
