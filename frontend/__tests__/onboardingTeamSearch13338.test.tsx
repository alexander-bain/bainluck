/** @jest-environment jsdom */

import React, { act } from "react";
import { createRoot } from "react-dom/client";
import OnboardingPage from "@/app/onboarding/page";
import { searchTeams } from "@/lib/api";

jest.mock("next/navigation", () => ({ useRouter: () => ({ push: jest.fn() }) }));
jest.mock("@/components/AuthProvider", () => ({
  useAuthContext: () => ({ isAuthenticated: true, isLoading: false }),
}));
jest.mock("@/hooks", () => ({
  usePageTracking: jest.fn(),
  useScrollDepth: jest.fn(),
  useEngagementTime: jest.fn(),
  useAnalytics: () => ({ track: jest.fn() }),
}));
jest.mock("@/lib/api", () => ({
  fetchUserPreferences: jest.fn().mockResolvedValue({ onboarding_completed: false }),
  searchTeams: jest.fn(),
}));

test("an unavailable team search recovers on the next query", async () => {
  const host = document.createElement("div");
  const root = createRoot(host);
  document.body.appendChild(host);
  const environment = globalThis as typeof globalThis & { IS_REACT_ACT_ENVIRONMENT: boolean };
  environment.IS_REACT_ACT_ENVIRONMENT = true;
  const lookup = jest.mocked(searchTeams);
  lookup.mockRejectedValueOnce(new Error("503")).mockResolvedValueOnce([{
    id: 1010,
    name: "Manchester City",
    sport_key: "soccer_epl",
    location: "Manchester",
    abbreviation: null,
    logo_url: null,
  }]);
  jest.useFakeTimers();

  async function enterQuery(value: string) {
    const input = host.querySelector("input")!;
    await act(async () => {
      Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, "value")!.set!.call(input, value);
      input.dispatchEvent(new Event("input", { bubbles: true }));
      await jest.advanceTimersByTimeAsync(300);
    });
  }

  try {
    await act(async () => root.render(<OnboardingPage />));
    const next = Array.from(host.querySelectorAll("button")).find(
      (button) => button.textContent?.trim() === "Continue"
    )!;
    act(() => next.click());

    await enterQuery("Real Madrid");
    expect(lookup).toHaveBeenNthCalledWith(1, "Real Madrid", expect.any(AbortSignal));
    expect(host.querySelector('[role="status"]')?.textContent).toContain("Team search is unavailable");

    await enterQuery("Manchester City");
    expect(lookup).toHaveBeenNthCalledWith(2, "Manchester City", expect.any(AbortSignal));
    expect(host.querySelector('[role="status"]')).toBeNull();
    expect(host.textContent).toContain("Manchester City");
  } finally {
    act(() => root.unmount());
    delete (environment as Partial<typeof environment>).IS_REACT_ACT_ENVIRONMENT;
    host.remove();
    jest.useRealTimers();
  }
});
