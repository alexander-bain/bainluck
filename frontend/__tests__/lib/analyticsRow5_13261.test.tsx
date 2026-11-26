/**
 * #13261 row 5: Web follow_team and pin_item analytics strictly behind "Allow" (181-C).
 *
 * Verifies through the real analytics core + sanitizer boundary that:
 *  - Neither `follow_team` nor `pin_item` is sent when consent is unset or declined ("none").
 *  - After explicit "Allow" (`updateConsent('all')`), both events fire with only the
 *    declared privacy-safe fields (no user_id, email, or team names).
 */

describe("#13261 row 5 — Web follow_team and pin_item behind Allow (181-C)", () => {
  const ORIGINAL_GA_ID = process.env.NEXT_PUBLIC_GA_MEASUREMENT_ID;
  let gtagMock: jest.Mock;
  let storage: Map<string, string>;

  beforeEach(() => {
    jest.resetModules();
    process.env.NEXT_PUBLIC_GA_MEASUREMENT_ID = "G-TEST13261";
    storage = new Map<string, string>();
    gtagMock = jest.fn();

    const localStorageMock = {
      getItem: (k: string) => (storage.has(k) ? storage.get(k)! : null),
      setItem: (k: string, v: string) => {
        storage.set(k, String(v));
      },
      removeItem: (k: string) => {
        storage.delete(k);
      },
      clear: () => {
        storage.clear();
      },
      key: (i: number) => Array.from(storage.keys())[i] ?? null,
      get length() {
        return storage.size;
      },
    };

    Object.defineProperty(global, "localStorage", {
      value: localStorageMock,
      configurable: true,
      writable: true,
    });
    Object.defineProperty(global, "window", {
      value: {
        location: {
          href: "https://www.bainluck.com/onboarding",
          pathname: "/onboarding",
          search: "",
          origin: "https://www.bainluck.com",
        },
        gtag: gtagMock,
        dataLayer: [],
        navigator: { userAgent: "node" },
        localStorage: localStorageMock,
        addEventListener: jest.fn(),
        removeEventListener: jest.fn(),
        dispatchEvent: jest.fn(),
      },
      configurable: true,
      writable: true,
    });
    Object.defineProperty(global, "document", {
      value: {
        title: "Bain Luck",
        referrer: "",
        head: { appendChild: jest.fn() },
        createElement: jest.fn(() => ({ async: false, src: "" })),
        addEventListener: jest.fn(),
        removeEventListener: jest.fn(),
        visibilityState: "visible",
      },
      configurable: true,
      writable: true,
    });
  });

  function emittedEvents(name: string) {
    return gtagMock.mock.calls.filter(
      (call) => call[0] === "event" && call[1] === name
    );
  }

  test("refuses to send follow_team or pin_item without Allow consent (181-C)", async () => {
    const core = await import("@/lib/analytics/core");
    const { trackFollowTeam, trackPinItem } = await import(
      "@/lib/analytics/followPin"
    );

    // Consent unset
    core.initializeAnalytics();
    trackFollowTeam({
      action: "follow",
      sport: "basketball_nba",
      relation_type: "follow",
      surface: "onboarding",
    });
    trackPinItem({ item_type: "event", action: "pin" });
    trackPinItem({ item_type: "future", action: "unpin" });
    expect(emittedEvents("follow_team")).toHaveLength(0);
    expect(emittedEvents("pin_item")).toHaveLength(0);

    // Consent explicitly declined ("none")
    core.updateConsent("none");
    trackFollowTeam({
      action: "unfollow",
      sport: "americanfootball_nfl",
      relation_type: "follow",
      surface: "preferences",
    });
    trackPinItem({ item_type: "event", action: "unpin" });
    expect(emittedEvents("follow_team")).toHaveLength(0);
    expect(emittedEvents("pin_item")).toHaveLength(0);
  });

  test("sends sanitized follow_team and pin_item after Allow consent", async () => {
    const core = await import("@/lib/analytics/core");
    const { trackFollowTeam, trackPinItem } = await import(
      "@/lib/analytics/followPin"
    );
    const { sanitizeEvent } = await import("@/lib/analytics/sanitize");

    core.initializeAnalytics();
    core.updateConsent("all");
    gtagMock.mockClear();

    trackFollowTeam({
      action: "follow",
      sport: "basketball_nba",
      relation_type: "follow",
      surface: "onboarding",
    });
    trackPinItem({ item_type: "event", action: "pin" });
    trackPinItem({ item_type: "future", action: "unpin" });

    const followCalls = emittedEvents("follow_team");
    expect(followCalls).toHaveLength(1);
    expect(followCalls[0][2]).toMatchObject({
      action: "follow",
      sport: "basketball_nba",
      relation_type: "follow",
      surface: "onboarding",
    });

    const pinCalls = emittedEvents("pin_item");
    expect(pinCalls).toHaveLength(2);
    expect(pinCalls[0][2]).toMatchObject({
      item_type: "event",
      action: "pin",
    });
    expect(pinCalls[1][2]).toMatchObject({
      item_type: "future",
      action: "unpin",
    });

    // Sanitizer strips any accidental PII keys from follow_team / pin_item
    const clean = sanitizeEvent("follow_team", {
      action: "follow",
      sport: "basketball_nba",
      user_id: "uid_secret",
      email: "reader@example.com",
    });
    expect(clean).not.toBeNull();
    expect(clean?.params).toEqual({
      action: "follow",
      sport: "basketball_nba",
    });
  });

  afterAll(() => {
    if (ORIGINAL_GA_ID === undefined) {
      delete process.env.NEXT_PUBLIC_GA_MEASUREMENT_ID;
    } else {
      process.env.NEXT_PUBLIC_GA_MEASUREMENT_ID = ORIGINAL_GA_ID;
    }
  });
});
