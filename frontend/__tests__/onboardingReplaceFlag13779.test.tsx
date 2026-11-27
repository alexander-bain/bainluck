import { minimalDom } from "./helpers/minimalDom";
import React, { act } from "react";
import { createRoot, type Root } from "react-dom/client";
import type { OnboardingSubmission, UserPreferencesResponse } from "@/lib/types";

type DomNode = {
  tagName?: string;
  textContent: string;
  childNodes: DomNode[];
  [extra: string]: unknown;
};

// `autoFocus` on `<input>` in OnboardingPage calls `domElement.focus()` on commit.
const rawCreateElement = (
  minimalDom.document as unknown as {
    createElement: (tag: string) => DomNode & { focus?: () => void };
  }
).createElement;
(
  minimalDom.document as unknown as {
    createElement: (tag: string) => DomNode & { focus?: () => void };
  }
).createElement = (tag: string) => {
  const el = rawCreateElement(tag);
  if (!el.focus) el.focus = () => {};
  return el;
};

const mockPush = jest.fn();
const mockFetchUserPreferences = jest.fn<Promise<UserPreferencesResponse>, []>();
const mockSubmitOnboarding = jest.fn<
  Promise<{ status: string; onboarding_completed: boolean }>,
  [OnboardingSubmission, string | null | undefined]
>();

jest.mock("next/navigation", () => ({
  __esModule: true,
  useRouter: () => ({ push: mockPush, replace: jest.fn(), prefetch: jest.fn() }),
}));

jest.mock("@/components/AuthProvider", () => ({
  __esModule: true,
  useAuthContext: () => ({
    isAuthenticated: true,
    isLoading: false,
    getToken: jest.fn().mockResolvedValue("test-token"),
    signInWithGoogle: jest.fn(),
  }),
}));

jest.mock("@/hooks", () => ({
  __esModule: true,
  usePageTracking: () => undefined,
  useScrollDepth: () => undefined,
  useEngagementTime: () => undefined,
  useAnalytics: () => ({ track: jest.fn() }),
}));

jest.mock("@/lib/api", () => ({
  __esModule: true,
  fetchUserPreferences: () => mockFetchUserPreferences(),
  submitOnboarding: (
    data: OnboardingSubmission,
    token?: string | null,
  ) => mockSubmitOnboarding(data, token),
  searchTeams: jest.fn().mockResolvedValue([]),
  searchTeamsByLocation: jest.fn().mockResolvedValue([]),
}));

import OnboardingPage from "@/app/onboarding/page";

function walk(node: DomNode): DomNode[] {
  return [node, ...node.childNodes.flatMap((child) => walk(child))];
}

function invokeClick(node: DomNode): void {
  const propsKey = Object.keys(node).find((k) => k.startsWith("__reactProps$"));
  const onClick = propsKey
    ? (node[propsKey] as { onClick?: () => unknown }).onClick
    : undefined;
  if (!onClick) {
    throw new Error(`Missing React onClick handler on <${node.tagName ?? "?"}>`);
  }
  onClick();
}

function findButtonByText(container: DomNode, label: string): DomNode {
  const found = walk(container).find(
    (node) => node.tagName === "BUTTON" && node.textContent.trim() === label,
  );
  if (!found) {
    throw new Error(`Button "${label}" not found`);
  }
  return found;
}

async function flushMicrotasks(): Promise<void> {
  await act(async () => {
    await Promise.resolve();
    await Promise.resolve();
  });
}

describe("#13779 OnboardingPage replace flag (Fable ask #1)", () => {
  let host: DomNode;
  let root: Root;

  beforeEach(() => {
    jest.clearAllMocks();
    mockSubmitOnboarding.mockResolvedValue({
      status: "ok",
      onboarding_completed: true,
    });
    host = (minimalDom.document as unknown as {
      createElement: (tag: string) => DomNode;
    }).createElement("div");
    root = createRoot(host as unknown as Element);
  });

  afterEach(async () => {
    await act(async () => {
      root.unmount();
    });
  });

  it("returning person removes one team and lowers one level with replace=true", async () => {
    mockFetchUserPreferences.mockResolvedValue({
      home_location: "Boston",
      onboarding_completed: true,
      sport_affinities: {
        nfl: 1.0,
        nba: 1.0,
        college_football: 1.0,
        college_basketball: 1.0,
      },
      favorites: [
        {
          team_id: 101,
          team_name: "New England Patriots",
          relation_type: "follow",
          sport_key: "americanfootball_nfl",
          logo_url: null,
          source: "onboarding",
        },
        {
          team_id: 102,
          team_name: "Boston Celtics",
          relation_type: "follow",
          sport_key: "basketball_nba",
          logo_url: null,
          source: "onboarding",
        },
      ],
    });

    await act(async () => {
      root.render(React.createElement(OnboardingPage));
    });
    await flushMicrotasks();

    // Step 1 -> Step 2 (Follow)
    await act(async () => {
      invokeClick(findButtonByText(host, "Continue"));
    });

    const celticsBadge = walk(host).find(
      (node) => node.tagName === "SPAN" && node.textContent.includes("Boston Celtics"),
    );
    if (!celticsBadge) {
      throw new Error("Expected Boston Celtics chip on Step 2");
    }
    const removeCelticsBtn = walk(celticsBadge).find((node) => node.tagName === "BUTTON");
    if (!removeCelticsBtn) {
      throw new Error("Expected remove button inside Boston Celtics chip");
    }
    await act(async () => {
      invokeClick(removeCelticsBtn);
    });

    // Step 2 -> Step 3 -> Step 4 (Sport affinities)
    await act(async () => {
      invokeClick(findButtonByText(host, "Continue"));
    });
    await act(async () => {
      invokeClick(findButtonByText(host, "Continue"));
    });

    // Lower NFL from "Love it" (1.0) to "Big moments" (0.3)
    const nflRow = walk(host).find(
      (node) =>
        node.tagName === "DIV" &&
        node.childNodes.some(
          (child) => child.tagName === "SPAN" && child.textContent.trim() === "NFL",
        ),
    );
    if (!nflRow) {
      throw new Error("Expected NFL row on Step 4");
    }
    await act(async () => {
      invokeClick(findButtonByText(nflRow, "Big moments"));
    });

    // Step 4 -> Step 5 -> Done
    await act(async () => {
      invokeClick(findButtonByText(host, "Continue"));
    });
    await act(async () => {
      invokeClick(findButtonByText(host, "Done"));
    });
    await flushMicrotasks();

    expect(mockSubmitOnboarding).toHaveBeenCalledTimes(1);
    const [submitted, token] = mockSubmitOnboarding.mock.calls[0];
    expect(token).toBe("test-token");
    expect(submitted.replace).toBe(true);
    expect(submitted.follow_teams).toEqual([{ team_id: 101 }]);
    expect(submitted.sport_affinities.nfl).toBe(0.3);
    expect(submitted.sport_affinities.nba).toBe(1.0);
  });

  it("keeps replace=false when fetchUserPreferences fails so fallback defaults never wipe saved choices", async () => {
    mockFetchUserPreferences.mockRejectedValue(new Error("network down"));

    await act(async () => {
      root.render(React.createElement(OnboardingPage));
    });
    await flushMicrotasks();

    for (let i = 0; i < 4; i++) {
      await act(async () => {
        invokeClick(findButtonByText(host, "Continue"));
      });
    }
    await act(async () => {
      invokeClick(findButtonByText(host, "Done"));
    });
    await flushMicrotasks();

    expect(mockSubmitOnboarding).toHaveBeenCalledTimes(1);
    expect(mockSubmitOnboarding.mock.calls[0][0].replace).toBe(false);
  });

  it("sends replace=true for a confirmed new user whose onboarding_completed is false", async () => {
    mockFetchUserPreferences.mockResolvedValue({
      home_location: null,
      onboarding_completed: false,
      sport_affinities: {},
      favorites: [],
    });

    await act(async () => {
      root.render(React.createElement(OnboardingPage));
    });
    await flushMicrotasks();

    for (let i = 0; i < 4; i++) {
      await act(async () => {
        invokeClick(findButtonByText(host, "Continue"));
      });
    }
    await act(async () => {
      invokeClick(findButtonByText(host, "Done"));
    });
    await flushMicrotasks();

    expect(mockSubmitOnboarding).toHaveBeenCalledTimes(1);
    expect(mockSubmitOnboarding.mock.calls[0][0].replace).toBe(true);
  });
});
