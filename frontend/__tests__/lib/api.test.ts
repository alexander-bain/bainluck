import {
  setAuthTokenGetter,
  fetchSports,
  syncPins,
  addPin,
  getBestProbability,
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

describe("getBestProbability", () => {
  it("returns betting odds for non-live games even when model data exists", () => {
    const result = getBestProbability({
      status: "completed",
      current_odds: { home_probability: 0.6, away_probability: 0.4 },
      win_probability_sources: {
        espn: {
          value: 0.2,
          display_name: "ESPN",
          type: "model",
          color: "#000000",
        },
      },
    });

    expect(result).toEqual({
      homeProb: 0.6,
      awayProb: 0.4,
      source: "betting",
      sourceName: null,
    });
  });

  it("returns betting odds for live games when no model sources are present", () => {
    const result = getBestProbability({
      status: "live",
      current_odds: { home_probability: 0.55, away_probability: 0.45 },
    });

    expect(result).toEqual({
      homeProb: 0.55,
      awayProb: 0.45,
      source: "betting",
      sourceName: null,
    });
  });

  it("prefers ESPN model when it diverges from betting odds by more than 15%", () => {
    const result = getBestProbability({
      status: "live",
      current_odds: { home_probability: 0.5, away_probability: 0.5 },
      win_probability_sources: {
        espn: {
          value: 0.71,
          display_name: "ESPN",
          type: "model",
          color: "#123456",
        },
        stat_model: {
          value: 0.68,
          display_name: "Model",
          type: "model",
          color: "#654321",
        },
      },
    });

    expect(result.homeProb).toBeCloseTo(0.71, 10);
    expect(result.awayProb).toBeCloseTo(0.29, 10);
    expect(result.source).toBe("model");
    expect(result.sourceName).toBe("ESPN");
  });

  it("falls back to stat_model when ESPN source is absent", () => {
    const result = getBestProbability({
      status: "live",
      current_odds: { home_probability: 0.5, away_probability: 0.5 },
      win_probability_sources: {
        stat_model: {
          value: 0.7,
          display_name: "Stat Model",
          type: "model",
          color: "#abcdef",
        },
      },
    });

    expect(result.homeProb).toBeCloseTo(0.7, 10);
    expect(result.awayProb).toBeCloseTo(0.3, 10);
    expect(result.source).toBe("model");
    expect(result.sourceName).toBe("Stat Model");
  });

  it("keeps betting odds when divergence is exactly 15%", () => {
    const result = getBestProbability({
      status: "live",
      current_odds: { home_probability: 0.5, away_probability: 0.5 },
      win_probability_sources: {
        espn: {
          value: 0.649,
          display_name: "ESPN",
          type: "model",
          color: "#123123",
        },
      },
    });

    expect(result).toEqual({
      homeProb: 0.5,
      awayProb: 0.5,
      source: "betting",
      sourceName: null,
    });
  });

  it("keeps betting odds when model value is missing", () => {
    const result = getBestProbability({
      status: "live",
      current_odds: { home_probability: 0.4, away_probability: 0.6 },
      win_probability_sources: {
        espn: {
          value: null as unknown as number,
          display_name: "ESPN",
          type: "model",
          color: "#777777",
        },
      },
    });

    expect(result).toEqual({
      homeProb: 0.4,
      awayProb: 0.6,
      source: "betting",
      sourceName: null,
    });
  });
});
