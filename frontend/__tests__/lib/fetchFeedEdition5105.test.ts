/**
 * #5105 / #5102 — `fetchFeed`'s optional `edition` transport.
 *
 * Absent, the request is byte-identical to today's (URL and headers); present,
 * it adds one encoded `edition` parameter and changes nothing else.
 */
import { fetchFeed } from "@/lib/api";

const calls: Array<{ url: string; headers: unknown }> = [];

beforeEach(() => {
  calls.length = 0;
  global.fetch = jest.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
    calls.push({ url: String(input), headers: init?.headers });
    return {
      ok: true,
      status: 200,
      headers: { get: () => null },
      json: async () => ({ items: [], total: 0, limit: 20, offset: 0, has_more: false }),
    } as unknown as Response;
  }) as unknown as typeof fetch;
});

const PARAMS = { limit: 20, offset: 20, mode: "discover", event_pct: 0.15 };

describe("fetchFeed edition transport", () => {
  it("sends no edition parameter when none is given (URL and headers unchanged)", async () => {
    await fetchFeed(PARAMS);
    await fetchFeed({ ...PARAMS, edition: undefined });
    await fetchFeed({ ...PARAMS, edition: "" });

    expect(calls).toHaveLength(3);
    expect(calls[0].url).toMatch(/\/api\/feed\?limit=20&offset=20&event_pct=0\.15&mode=discover$/);
    expect(calls[1]).toEqual(calls[0]);
    expect(calls[2]).toEqual(calls[0]);
  });

  it("appends one encoded edition token and changes nothing else", async () => {
    await fetchFeed(PARAMS);
    await fetchFeed({ ...PARAMS, edition: "a+b/c=d&e f" });

    const [plain, pinned] = calls;
    expect(pinned.url).toBe(`${plain.url}&edition=a%2Bb%2Fc%3Dd%26e+f`);
    expect(new URL(pinned.url).searchParams.get("edition")).toBe("a+b/c=d&e f");
    expect(pinned.headers).toEqual(plain.headers);
  });
});
