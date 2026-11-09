/** @jest-environment jsdom */
import React from "react";
import { createRoot, type Root } from "react-dom/client";
import { act } from "react-dom/test-utils";
import fixture from "../fixtures/tournamentHubUsOpen.20260903.json";
import { HUB_SECTIONS_FIRST, HUB_SECTIONS_REST } from "@/lib/tournament/hubBoot";

let mockSlug = "atp-brussels";
const mockRouter = { replace: jest.fn() };
const mockTournament = jest.fn();
const mockConcept = jest.fn();
const mockTracking = [jest.fn(), jest.fn(), jest.fn()];

jest.mock("next/navigation", () => ({
  useParams: () => ({ slug: mockSlug }),
  useRouter: () => mockRouter,
}));
jest.mock("next/link", () => ({
  __esModule: true,
  default: ({ children, ...props }: React.AnchorHTMLAttributes<HTMLAnchorElement>) =>
    <a {...props}>{children}</a>,
}));
jest.mock("@/hooks", () => ({
  usePageTracking: () => mockTracking[0](),
  useScrollDepth: () => mockTracking[1](),
  useEngagementTime: () => mockTracking[2](),
}));
jest.mock("@/lib/api", () => ({
  fetchTournament: (...args: unknown[]) => mockTournament(...args),
  fetchEventConcept: (...args: unknown[]) => mockConcept(...args),
}));
jest.mock("@/components/tournament/ContenderChart", () => () => null);
jest.mock("@/components/tournament/TournamentBoard", () => () => null);
jest.mock("@/components/tournament/TournamentBracket", () => () => null);
jest.mock("@/components/tournament/TournamentMatches", () => () => null);
jest.mock("@/components/tournament/TournamentProps", () => () => null);
jest.mock("@/components/tournament/TournamentResults", () => () => null);

import TournamentPage from "@/app/tournaments/[slug]/page";

function httpError(status: number) {
  return Object.assign(new Error(`HTTP ${status}`), { status });
}

function concept(key = "event:tennis:atp-brussels-winner", domain = "tennis") {
  return { event: { key, domain, status: "settled" } };
}

function deferred<T>() {
  let resolve!: (value: T) => void;
  let reject!: (reason: unknown) => void;
  const promise = new Promise<T>((accept, refuse) => {
    resolve = accept;
    reject = refuse;
  });
  return { promise, resolve, reject };
}

let root: Root;
let host: HTMLDivElement;

async function renderSlug(slug = mockSlug) {
  mockSlug = slug;
  await act(async () => {
    root.render(<TournamentPage />);
  });
}

beforeEach(() => {
  (globalThis as unknown as { IS_REACT_ACT_ENVIRONMENT: boolean }).IS_REACT_ACT_ENVIRONMENT = true;
  jest.clearAllMocks();
  mockTournament.mockReset();
  mockConcept.mockReset();
  mockSlug = "atp-brussels";
  host = document.createElement("div");
  root = createRoot(host);
  sessionStorage.clear();
});

afterEach(() => {
  act(() => root.unmount());
});

test.each([
  ["atp-brussels", "atp-tennis-brussels-belgium-singles-winner"],
  ["atp-basel", "atp-basel-winner"],
])("%s opens the existing resolver's canonical tennis hub", async (slug, canonical) => {
  mockTournament.mockRejectedValue(httpError(404));
  mockConcept.mockResolvedValue(concept(`event:tennis:${canonical}`));

  await renderSlug(slug);

  expect(mockTournament.mock.calls).toEqual([[slug, HUB_SECTIONS_FIRST]]);
  expect(mockConcept).toHaveBeenCalledWith(`event:tennis:${slug}-winner`);
  expect(mockRouter.replace).toHaveBeenCalledWith(`/event/tennis/${canonical}`);
  expect(host.textContent).not.toContain("Tournament unavailable");
  mockTracking.forEach((track) => expect(track).toHaveBeenCalled());
});

test("a registered tournament retains both section requests and its own page", async () => {
  mockTournament.mockResolvedValue(fixture);

  await renderSlug("us-open");

  expect(mockTournament.mock.calls).toEqual([
    ["us-open", HUB_SECTIONS_FIRST],
    ["us-open", HUB_SECTIONS_REST],
  ]);
  expect(mockConcept).not.toHaveBeenCalled();
  expect(mockRouter.replace).not.toHaveBeenCalled();
  expect(host.textContent).toContain("US Open 2026");
});

test("two genuine 404s show an informational not-found state", async () => {
  mockTournament.mockRejectedValue(httpError(404));
  mockConcept.mockRejectedValue(httpError(404));

  await renderSlug("unknown-tournament");

  expect(mockConcept).toHaveBeenCalledTimes(1);
  expect(host.textContent).toContain("Tournament not found");
  expect(host.textContent).not.toMatch(/unavailable|settled|concluded/i);
  expect(mockRouter.replace).not.toHaveBeenCalled();
});

test.each([httpError(503), new TypeError("Failed to fetch")])(
  "an initial transient failure retains the error state without a fallback lookup",
  async (error) => {
    mockTournament.mockRejectedValue(error);
    await renderSlug();
    expect(host.textContent).toContain("Tournament unavailable");
    expect(mockConcept).not.toHaveBeenCalled();
    expect(mockRouter.replace).not.toHaveBeenCalled();
  },
);

test("a failed fallback remains a load failure", async () => {
  mockTournament.mockRejectedValue(httpError(404));
  mockConcept.mockRejectedValue(httpError(503));
  await renderSlug();
  expect(host.textContent).toContain("Tournament unavailable");
  expect(host.textContent).not.toMatch(/not found|settled|concluded/i);
});

test.each([
  ["event:golf:atp-brussels-winner", "golf"],
  ["tennis:atp-brussels-winner", "tennis"],
  ["event:tennis:", "tennis"],
  ["event:tennis:atp-brussels:winner", "tennis"],
  ["event:tennis:../other", "tennis"],
  ["event:tennis:atp-brussels-winner", "golf"],
])("a foreign or malformed resolver key %s cannot redirect", async (key, domain) => {
  mockTournament.mockRejectedValue(httpError(404));
  mockConcept.mockResolvedValue(concept(key, domain));
  await renderSlug();
  expect(mockRouter.replace).not.toHaveBeenCalled();
  expect(host.textContent).toContain("Tournament unavailable");
});

test("a stale first 404 cannot start the fallback after the slug changes", async () => {
  const first = deferred<unknown>();
  mockTournament.mockImplementation((slug) => slug === "atp-brussels" ? first.promise : Promise.resolve(fixture));
  await renderSlug();
  await renderSlug("us-open");
  await act(async () => first.reject(httpError(404)));
  expect(mockConcept).not.toHaveBeenCalled();
  expect(mockRouter.replace).not.toHaveBeenCalled();
  expect(host.textContent).toContain("US Open 2026");
});

test.each(["resolve", "reject"])("a stale fallback's %s cannot change the next page", async (result) => {
  const fallback = deferred<unknown>();
  mockTournament.mockImplementation((slug) => slug === "atp-brussels" ? Promise.reject(httpError(404)) : Promise.resolve(fixture));
  mockConcept.mockReturnValue(fallback.promise);
  await renderSlug();
  expect(mockConcept).toHaveBeenCalledTimes(1);
  await renderSlug("us-open");
  await act(async () => {
    if (result === "resolve") fallback.resolve(concept());
    else fallback.reject(httpError(404));
  });
  expect(mockRouter.replace).not.toHaveBeenCalled();
  expect(host.textContent).toContain("US Open 2026");
  expect(host.textContent).not.toContain("Tournament not found");
});

test("a registered page's second-section failure keeps the first section", async () => {
  mockTournament.mockResolvedValueOnce(fixture).mockRejectedValueOnce(httpError(404));
  await renderSlug("us-open");
  expect(host.textContent).toContain("US Open 2026");
  expect(mockConcept).not.toHaveBeenCalled();
  expect(mockRouter.replace).not.toHaveBeenCalled();
});
