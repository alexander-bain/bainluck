/**
 * #13261 row 5 / #13315 — Real call-site tests for `usePinnedIds` and `<OnboardingPage />`.
 *
 * Uses `minimalDom` + `react-dom/client` under Jest's node environment and runs
 * through the real analytics `core` + `sanitize` pipeline with `window.gtag` spied
 * (no mock on `@/lib/analytics/followPin` or `@/lib/analytics/core`).
 */
import "../helpers/minimalDom";
const ORIGINAL_GA_ID = process.env.NEXT_PUBLIC_GA_MEASUREMENT_ID;
process.env.NEXT_PUBLIC_GA_MEASUREMENT_ID = "G-TEST13315";
import React, { act } from "react";
import { createRoot } from "react-dom/client";

const mockRouterPush = jest.fn();
jest.mock("next/navigation", () => ({
  __esModule: true,
  useRouter: () => ({ push: mockRouterPush }),
  usePathname: () => "/onboarding",
  useSearchParams: () => new URLSearchParams(),
}));

const mockAuthState = {
  isAuthenticated: true,
  isLoading: false,
  user: { uid: "test-uid-13315" },
  getToken: jest.fn(async () => "tok-13315"),
  signInWithGoogle: jest.fn(),
};
jest.mock("@/components/AuthProvider", () => ({
  __esModule: true,
  useAuthContext: () => mockAuthState,
}));

const mockSearchTeamsByLocation = jest.fn();
const mockSearchTeams = jest.fn();
const mockSubmitOnboarding = jest.fn();
const mockFetchUserPreferences = jest.fn();
const mockFetchUserPins = jest.fn();
const mockAddPin = jest.fn();
const mockRemovePin = jest.fn();

jest.mock("@/lib/api", () => ({
  __esModule: true,
  searchTeamsByLocation: (...args: unknown[]) => mockSearchTeamsByLocation(...args),
  searchTeams: (...args: unknown[]) => mockSearchTeams(...args),
  submitOnboarding: (...args: unknown[]) => mockSubmitOnboarding(...args),
  fetchUserPreferences: (...args: unknown[]) => mockFetchUserPreferences(...args),
  fetchUserPins: (...args: unknown[]) => mockFetchUserPins(...args),
  addPin: (...args: unknown[]) => mockAddPin(...args),
  removePin: (...args: unknown[]) => mockRemovePin(...args),
}));

jest.mock("@/hooks/usePageTracking", () => ({
  __esModule: true,
  usePageTracking: () => undefined,
}));
jest.mock("@/hooks/useScrollDepth", () => ({
  __esModule: true,
  useScrollDepth: () => undefined,
}));
jest.mock("@/hooks/useEngagementTime", () => ({
  __esModule: true,
  useEngagementTime: () => undefined,
}));

const mockContextTrack = jest.fn();
jest.mock("@/hooks/useAnalytics", () => ({
  __esModule: true,
  usePageTracking: () => undefined,
  useScrollDepth: () => undefined,
  useEngagementTime: () => undefined,
  useAnalytics: () => ({ track: mockContextTrack }),
}));

import { initializeAnalytics, updateConsent } from "@/lib/analytics/core";
import { usePinnedIds, type UsePinnedIdsResult } from "@/hooks/usePinnedIds";
import OnboardingPage from "@/app/onboarding/page";

type El = {
  tagName?: string;
  textContent?: string;
  childNodes?: El[];
  [key: string]: unknown;
};

function descendants(rootNode: El): El[] {
  const out: El[] = [];
  for (const c of rootNode.childNodes ?? []) {
    out.push(c, ...descendants(c));
  }
  return out;
}

function reactProps(node: El): Record<string, (arg?: unknown) => void> {
  const key = Object.keys(node).find((k) => k.startsWith("__reactProps$"));
  if (!key) throw new Error(`no __reactProps$ on <${node.tagName}>`);
  return node[key] as Record<string, (arg?: unknown) => void>;
}

function makeLocalStorage() {
  const storage = new Map<string, string>();
  return {
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
}

describe("#13315 call-site telemetry — usePinnedIds and OnboardingPage", () => {
  let gtagMock: jest.Mock;
  let host: El;
  let root: ReturnType<typeof createRoot>;

  beforeEach(() => {
    process.env.NEXT_PUBLIC_GA_MEASUREMENT_ID = "G-TEST13315";

    const ls = makeLocalStorage();
    const doc = global.document as unknown as Record<string, unknown>;
    doc.title = "Bain Luck";
    doc.referrer = "";
    doc.head = { appendChild: jest.fn() };
    doc.visibilityState = "visible";
    const origCreateElement = doc.createElement as (tag: string) => El;
    doc.createElement = (tag: string) => {
      const el = origCreateElement(tag);
      el.focus = () => {};
      return el;
    };

    gtagMock = jest.fn();
    const win = global.window as unknown as Record<string, unknown>;
    win.location = {
      href: "https://www.bainluck.com/onboarding",
      pathname: "/onboarding",
      search: "",
      origin: "https://www.bainluck.com",
    };
    win.gtag = gtagMock;
    win.dataLayer = [];
    win.localStorage = ls;
    win.dispatchEvent = jest.fn();
    Object.defineProperty(global, "localStorage", {
      value: ls,
      configurable: true,
      writable: true,
    });

    initializeAnalytics();
    updateConsent("all");
    gtagMock.mockClear();
    mockContextTrack.mockClear();
    mockRouterPush.mockReset();

    mockAuthState.isAuthenticated = false;
    mockAuthState.isLoading = false;
    mockAuthState.user = { uid: "test-uid-13315" };
    mockFetchUserPins.mockResolvedValue({ events: [], futures: [] });
    mockAddPin.mockResolvedValue({});
    mockRemovePin.mockResolvedValue({});
    mockFetchUserPreferences.mockResolvedValue({ onboarding_completed: false, favorites: [] });
    mockSearchTeamsByLocation.mockResolvedValue([]);
    mockSearchTeams.mockResolvedValue([]);
    mockSubmitOnboarding.mockResolvedValue({ status: "ok" });

    host = document.createElement("div") as unknown as El;
    document.body.appendChild(host as unknown as Node);
    root = createRoot(host as unknown as Element);
  });

  afterEach(() => {
    act(() => root.unmount());
    document.body.removeChild(host as unknown as Node);
  });

  afterAll(() => {
    if (ORIGINAL_GA_ID === undefined) {
      delete process.env.NEXT_PUBLIC_GA_MEASUREMENT_ID;
    } else {
      process.env.NEXT_PUBLIC_GA_MEASUREMENT_ID = ORIGINAL_GA_ID;
    }
  });

  function gtagEvents(name: string) {
    return gtagMock.mock.calls.filter((call) => call[0] === "event" && call[1] === name);
  }

  test("usePinnedIds emits pin_item with item_type 'event' or 'future', and skips duplicates/max/unpinned", () => {
    const futuresPolicy = { base: "bainluck_pinnedFutures" };
    const eventsPolicy = { base: "bainluck_pinnedEvents" };
    let latestFuture!: UsePinnedIdsResult;
    let latestEvent!: UsePinnedIdsResult;

    function Harness() {
      latestFuture = usePinnedIds(futuresPolicy, "future", "futures", 2);
      latestEvent = usePinnedIds(eventsPolicy, "event", "events", 2);
      return null;
    }

    act(() => {
      root.render(React.createElement(Harness));
    });
    gtagMock.mockClear();

    // Unpin something not pinned -> 0 events
    act(() => {
      latestFuture.unpin(999);
    });
    expect(gtagEvents("pin_item")).toHaveLength(0);

    // Pin first future -> 1 pin_item with item_type: 'future'
    act(() => {
      expect(latestFuture.pin(101)).toBe(true);
    });
    expect(gtagEvents("pin_item")).toHaveLength(1);
    expect(gtagEvents("pin_item")[0][2]).toMatchObject({ item_type: "future", action: "pin" });

    // Refused duplicate pin -> still 1 event
    act(() => {
      expect(latestFuture.pin(101)).toBe(false);
    });
    expect(gtagEvents("pin_item")).toHaveLength(1);

    // Pin second future (reaches max = 2) -> 2 events
    act(() => {
      expect(latestFuture.pin(102)).toBe(true);
    });
    expect(gtagEvents("pin_item")).toHaveLength(2);

    // Refused at-max pin -> still 2 events
    act(() => {
      expect(latestFuture.pin(103)).toBe(false);
    });
    expect(gtagEvents("pin_item")).toHaveLength(2);

    // Valid unpin -> 1 unpin event with item_type: 'future'
    act(() => {
      latestFuture.unpin(101);
    });
    expect(gtagEvents("pin_item")).toHaveLength(3);
    expect(gtagEvents("pin_item")[2][2]).toMatchObject({ item_type: "future", action: "unpin" });

    // Pin an event -> item_type: 'event'
    act(() => {
      expect(latestEvent.pin(501)).toBe(true);
    });
    expect(gtagEvents("pin_item")).toHaveLength(4);
    expect(gtagEvents("pin_item")[3][2]).toMatchObject({ item_type: "event", action: "pin" });
  });

  async function selectAllFourOnboardingTeams() {
    mockAuthState.isAuthenticated = true;
    mockSearchTeamsByLocation.mockResolvedValue([
      { id: 1, name: "Boston Celtics", sport_key: "basketball_nba", logo_url: null, location: "Boston" },
    ]);
    mockSearchTeams.mockImplementation(async (q: string) => {
      if (q.includes("Cowboys")) {
        return [{ id: 2, name: "Dallas Cowboys", sport_key: "americanfootball_nfl", logo_url: null, location: "Dallas" }];
      }
      if (q.includes("Duke")) {
        return [{ id: 3, name: "Duke Blue Devils", sport_key: "basketball_ncaab", logo_url: null, location: "Durham" }];
      }
      if (q.includes("Yankees")) {
        return [{ id: 4, name: "New York Yankees", sport_key: "baseball_mlb", logo_url: null, location: "New York" }];
      }
      return [];
    });

    await act(async () => {
      root.render(React.createElement(OnboardingPage));
    });
    await act(async () => {
      await Promise.resolve();
    });

    const changeInput = async (placeholderSub: string, val: string) => {
      const inp = descendants(host).find(
        (n) => n.tagName === "INPUT" && String(n.placeholder ?? "").includes(placeholderSub)
      );
      if (!inp) throw new Error(`Input containing "${placeholderSub}" not found`);
      await act(async () => {
        reactProps(inp).onChange({ target: { value: val } });
      });
      await act(async () => {
        await new Promise((r) => setTimeout(r, 350));
        await Promise.resolve();
      });
    };

    const clickButton = async (textSub: string) => {
      const btn = descendants(host).find(
        (n) => n.tagName === "BUTTON" && String(n.textContent ?? "").includes(textSub)
      );
      if (!btn) throw new Error(`Button containing "${textSub}" not found`);
      await act(async () => {
        reactProps(btn).onClick();
        await Promise.resolve();
      });
    };

    // Step 1: Location (local team auto-selected)
    await changeInput("City or region", "Boston");
    await clickButton("Continue");

    // Step 2: Follow team — tapping must NOT send follow_team yet!
    await changeInput("Cowboys", "Cowboys");
    await clickButton("Dallas Cowboys");
    expect(gtagEvents("follow_team")).toHaveLength(0);
    expect(mockContextTrack.mock.calls.filter((c) => c[0] === "follow_team")).toHaveLength(0);
    await clickButton("Continue");

    // Step 3: Alma mater (college filter accepts basketball_ncaab)
    await changeInput("Duke", "Duke");
    await clickButton("Duke Blue Devils");
    await clickButton("Continue");

    // Step 4: Sports -> Continue
    await clickButton("Continue");

    // Step 5: Rivals
    await changeInput("Yankees", "Yankees");
    await clickButton("New York Yankees");
    expect(gtagEvents("follow_team")).toHaveLength(0);
  }

  test("OnboardingPage sends 0 follow_team on failed save and 1 per saved team across all 4 kinds on success", async () => {
    await selectAllFourOnboardingTeams();

    // Failed save -> 0 follow_team events
    mockSubmitOnboarding.mockRejectedValueOnce(new Error("server 500"));
    const doneBtnFail = descendants(host).find(
      (n) => n.tagName === "BUTTON" && String(n.textContent ?? "").trim() === "Done"
    )!;
    await act(async () => {
      reactProps(doneBtnFail).onClick();
      await Promise.resolve();
      await Promise.resolve();
    });
    expect(mockSubmitOnboarding).toHaveBeenCalledTimes(1);
    expect(gtagEvents("follow_team")).toHaveLength(0);

    // Retry and succeed -> 1 follow_team per saved team (local, follow, alma_mater, rival)
    mockSubmitOnboarding.mockResolvedValueOnce({ status: "ok" });
    const doneBtnOk = descendants(host).find(
      (n) => n.tagName === "BUTTON" && String(n.textContent ?? "").trim() === "Done"
    )!;
    await act(async () => {
      reactProps(doneBtnOk).onClick();
      await Promise.resolve();
      await Promise.resolve();
    });

    expect(mockSubmitOnboarding).toHaveBeenCalledTimes(2);
    const events = gtagEvents("follow_team").map((c) => c[2]);
    expect(events).toHaveLength(4);
    expect(events).toEqual([
      expect.objectContaining({ action: "follow", sport: "basketball_nba", relation_type: "local", surface: "onboarding" }),
      expect.objectContaining({ action: "follow", sport: "americanfootball_nfl", relation_type: "follow", surface: "onboarding" }),
      expect.objectContaining({ action: "follow", sport: "basketball_ncaab", relation_type: "alma_mater", surface: "onboarding" }),
      expect.objectContaining({ action: "follow", sport: "baseball_mlb", relation_type: "rival", surface: "onboarding" }),
    ]);
  });
});
