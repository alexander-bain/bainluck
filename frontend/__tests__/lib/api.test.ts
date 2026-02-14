import {
  setAuthTokenGetter,
  fetchSports,
  syncPins,
  addPin,
} from "../../lib/api";

describe("frontend/lib/api", () => {
  const originalFetch = global.fetch;

  beforeEach(() => {
    jest.resetAllMocks();
    setAuthTokenGetter(null);
  });

  afterAll(() => {
    global.fetch = originalFetch;
  });

  it("attaches Authorization header when auth token getter returns a token", async () => {
    setAuthTokenGetter(async () => "test-token");

    global.fetch = jest.fn().mockResolvedValue({
      ok: true,
      json: jest.fn().mockResolvedValue({ sports: [] }),
    } as unknown as Response);

    await fetchSports();

    expect(global.fetch).toHaveBeenCalledWith(
      "http://localhost:8000/api/sports",
      expect.objectContaining({
        headers: expect.objectContaining({
          Authorization: "Bearer test-token",
        }),
      })
    );
  });

  it("does not attach Authorization header when auth token getter returns null", async () => {
    setAuthTokenGetter(async () => null);

    global.fetch = jest.fn().mockResolvedValue({
      ok: true,
      json: jest.fn().mockResolvedValue({ sports: [] }),
    } as unknown as Response);

    await fetchSports();

    expect(global.fetch).toHaveBeenCalledWith(
      "http://localhost:8000/api/sports",
      expect.objectContaining({
        headers: {},
      })
    );
  });

  it("throws parsed backend error detail for failed requests", async () => {
    global.fetch = jest.fn().mockResolvedValue({
      ok: false,
      status: 401,
      json: jest.fn().mockResolvedValue({ detail: "Unauthorized" }),
    } as unknown as Response);

    await expect(fetchSports()).rejects.toThrow("Unauthorized");
  });

  it("falls back to Unknown error when failed response body is not JSON", async () => {
    global.fetch = jest.fn().mockResolvedValue({
      ok: false,
      status: 500,
      json: jest.fn().mockRejectedValue(new Error("invalid json")),
    } as unknown as Response);

    await expect(fetchSports()).rejects.toThrow("Unknown error");
  });

  it("includes JSON body and auth header for mutating requests", async () => {
    setAuthTokenGetter(async () => "mutate-token");

    global.fetch = jest.fn().mockResolvedValue({
      ok: true,
      json: jest.fn().mockResolvedValue({ events: [1], futures: [2] }),
    } as unknown as Response);

    await syncPins({ events: [1], futures: [2] });

    expect(global.fetch).toHaveBeenCalledWith(
      "http://localhost:8000/api/me/pins",
      {
        method: "PUT",
        headers: {
          "Content-Type": "application/json",
          Authorization: "Bearer mutate-token",
        },
        body: JSON.stringify({ events: [1], futures: [2] }),
      }
    );
  });

  it("sends POST mutation payload for addPin", async () => {
    global.fetch = jest.fn().mockResolvedValue({
      ok: true,
      json: jest.fn().mockResolvedValue({}),
    } as unknown as Response);

    await addPin("event", 42);

    expect(global.fetch).toHaveBeenCalledWith(
      "http://localhost:8000/api/me/pins",
      expect.objectContaining({
        method: "POST",
        body: JSON.stringify({ pin_type: "event", target_id: 42 }),
      })
    );
  });
});
