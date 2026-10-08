/**
 * #10727 — THE SEARCH RESULTS PAGE CANCELS A SUPERSEDED REQUEST.
 *
 * `/search` re-runs its results request whenever the URL's q / sport / page
 * changes. L2-198 (#1469) made a late response for an older query unpublishable
 * (the `ignore` guard), but the request itself kept running: it kept
 * downloading, and on a timeout or network error `apiFetch` retried it up to
 * twice more — for a result nobody would see. `searchEvents` had no `signal`,
 * so the page could not cancel it.
 *
 * This renders the real page over the real `searchEvents` → `apiFetch` path with
 * a controllable `fetch`, so the assertions read the signal the network layer
 * actually received. Mutation map:
 *   - drop `controller.abort()` from the page cleanup  → the two abort tests fail
 *   - drop `signal: options?.signal` from searchEvents → the two abort tests fail
 *   - drop the `ignore` guard in `.then`               → the late-response test fails
 *   - drop the `ignore` guard in `.catch`              → the no-error test fails
 */

import "./helpers/minimalDom";
import React, { act } from "react";
import { createRoot, type Root } from "react-dom/client";

let mockParams = new URLSearchParams();
jest.mock("next/navigation", () => ({
  useSearchParams: () => mockParams,
  useRouter: () => ({ push: jest.fn(), replace: jest.fn() }),
}));
jest.mock("next/link", () => ({
  __esModule: true,
  default: ({ children }: { children: React.ReactNode }) => <span>{children}</span>,
}));
const mockTrack = jest.fn();
jest.mock("@/hooks", () => ({
  usePinnedEvents: () => ({ isPinned: () => false, togglePin: jest.fn(), isMaxReached: false }),
  usePinnedFutures: () => ({ isPinned: () => false, togglePin: jest.fn(), isMaxReached: false }),
  usePageTracking: () => undefined,
  useScrollDepth: () => undefined,
  useEngagementTime: () => undefined,
  useAnalytics: () => ({ track: mockTrack }),
}));
jest.mock("@/components/CategoryBrowser", () => ({ __esModule: true, default: () => null }));
jest.mock("@/components/LeagueChips", () => ({ __esModule: true, default: () => null }));
jest.mock("@/components/LoadingState", () => ({
  __esModule: true,
  default: ({ message }: { message: string }) => <p>LOADING {message}</p>,
}));
jest.mock("@/components/ErrorState", () => ({
  __esModule: true,
  default: ({ message }: { message: string }) => <p>ERROR {message}</p>,
}));
jest.mock("@/lib/analytics", () => ({ trackEvent: jest.fn() }));

import SearchPage from "@/app/search/page";

// ── a fetch the test resolves by hand ──────────────────────────────────────
type Call = {
  url: string;
  init: RequestInit;
  resolve: (body: unknown) => void;
};
let calls: Call[] = [];

/** `abortable: false` models a response already on the wire when the abort lands. */
function installFetch({ abortable }: { abortable: boolean }) {
  global.fetch = jest.fn((url: string, init: RequestInit) => {
    return new Promise<Response>((resolve, reject) => {
      const call: Call = {
        url,
        init,
        resolve: (body) =>
          resolve({ ok: true, status: 200, json: async () => body } as unknown as Response),
      };
      if (abortable) {
        init.signal?.addEventListener("abort", () =>
          reject(new DOMException("Aborted", "AbortError")),
        );
      }
      calls.push(call);
    });
  }) as unknown as typeof fetch;
}

/** An empty answer whose `did_you_mean` names which response got published. */
function body(marker: string) {
  return {
    results: [],
    futures: [],
    teams: [],
    sports: [],
    event_concepts: [],
    futures_families: [],
    pagination: { page: 1, per_page: 25, total_results: 0, total_pages: 0 },
    did_you_mean: marker,
  };
}

const flush = () => act(async () => { for (let i = 0; i < 10; i++) await Promise.resolve(); });

let root: Root;
let host: { textContent: string };

function render(qs: string) {
  mockParams = new URLSearchParams(qs);
  act(() => root.render(<SearchPage />));
}

beforeEach(() => {
  calls = [];
  mockTrack.mockReset();
  (globalThis as Record<string, unknown>).localStorage = {
    getItem: () => "sess-10727",
    setItem: () => undefined,
  };
  const doc = document as unknown as {
    createElement: (t: string) => { textContent: string };
    body: { appendChild: (n: unknown) => void };
  };
  host = doc.createElement("div");
  doc.body.appendChild(host);
  root = createRoot(host as unknown as Element);
});

afterEach(() => {
  act(() => root.unmount());
});

const searchCalls = () => calls.filter((c) => c.url.includes("/api/events/search?"));

describe("#10727 a superseded full-results request is cancelled", () => {
  it.each([
    ["query", "q=dallas", "q=dallas+cowboys"],
    ["sport filter", "q=dallas", "q=dallas&sport=americanfootball_nfl"],
    ["page", "q=dallas", "q=dallas&page=2"],
  ])("changing the %s aborts the previous request; the current one stays live", async (_, first, second) => {
    installFetch({ abortable: true });
    render(first);
    await flush();
    render(second);
    await flush();

    const [old, current] = searchCalls();
    expect(searchCalls()).toHaveLength(2);
    expect(old.init.signal?.aborted).toBe(true);
    expect(current.init.signal?.aborted).toBe(false);
  });

  it("navigating away (unmount) aborts the in-flight request", async () => {
    installFetch({ abortable: true });
    render("q=dallas");
    await flush();
    const [inflight] = searchCalls();
    expect(inflight.init.signal?.aborted).toBe(false);

    act(() => root.unmount());
    expect(inflight.init.signal?.aborted).toBe(true);
    root = createRoot(host as unknown as Element); // afterEach unmounts again
  });

  it("a cancelled request shows no error, and the current query still publishes", async () => {
    installFetch({ abortable: true });
    render("q=dallas");
    await flush();
    render("q=dallas+cowboys");
    await flush(); // the old fetch has rejected with AbortError by now

    expect(host.textContent).not.toContain("ERROR");
    expect(host.textContent).toContain('LOADING Searching for "dallas cowboys"');

    searchCalls()[1].resolve(body("current-answer"));
    await flush();
    expect(host.textContent).toContain('No results for "dallas cowboys"');
    expect(host.textContent).toContain("current-answer");
    expect(host.textContent).not.toContain("ERROR");
  });

  it("a response that lands after the abort never replaces the current query", async () => {
    installFetch({ abortable: false });
    render("q=dallas");
    await flush();
    render("q=dallas+cowboys");
    await flush();
    const [old, current] = searchCalls();

    current.resolve(body("current-answer"));
    await flush();
    old.resolve(body("stale-answer"));
    await flush();

    expect(host.textContent).toContain("current-answer");
    expect(host.textContent).not.toContain("stale-answer");
    const submits = mockTrack.mock.calls.filter(([name]) => name === "search_submit");
    expect(submits).toEqual([
      ["search_submit", expect.objectContaining({ query: "dallas cowboys", surface: "search" })],
    ]);
  });

  it("the current request keeps its URL params and anonymous session header", async () => {
    installFetch({ abortable: true });
    render("q=dallas&sport=americanfootball_nfl&page=2");
    await flush();
    const [call] = searchCalls();
    const url = new URL(call.url);
    expect(url.searchParams.get("q")).toBe("dallas");
    expect(url.searchParams.get("sport")).toBe("americanfootball_nfl");
    expect(url.searchParams.get("page")).toBe("2");
    expect(url.searchParams.get("per_page")).toBe("25");
    expect((call.init.headers as Record<string, string>)["x-session-id"]).toBe("sess-10727");
    expect(call.init.signal).toBeDefined();
  });
});
