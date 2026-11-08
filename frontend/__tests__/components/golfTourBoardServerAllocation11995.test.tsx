import "../helpers/minimalDom";
import React, { act } from "react";
import { createRoot } from "react-dom/client";
import { fetchGolfTournament, fetchGolfLeaderboard, fetchSportHierarchyDetail } from "@/lib/api";
import type { GolfGolfer, GolfLeaderboardPlayer, GolfTournamentDetailResponse } from "@/lib/types";

jest.mock("next/navigation", () => ({
  useParams: () => ({ sport: "golf", league: "pga", slug: "synthetic-masters" }),
}));
jest.mock("next/link", () => ({
  __esModule: true,
  default: ({ children, href }: { children: React.ReactNode; href: string }) => <a href={href}>{children}</a>,
}));
jest.mock("@/hooks", () => ({
  usePageTracking: jest.fn(), useScrollDepth: jest.fn(), useEngagementTime: jest.fn(),
}));
jest.mock("@/components/EvolutionView", () => ({ EvolutionView: () => null }));
jest.mock("@/lib/api", () => ({
  ...jest.requireActual("@/lib/api"),
  fetchGolfTournament: jest.fn(), fetchGolfLeaderboard: jest.fn(), fetchSportHierarchyDetail: jest.fn(),
}));

import SportEventDetailPage from "@/app/sport/[sport]/[league]/[slug]/page";

const names = ["Alice Smith", "Bob Jones", "Casey Reed"];
const allocation = [34, 33, 33];
let host: HTMLElement;
let root: ReturnType<typeof createRoot>;

function golfer(name: string, probability: number, rendered_percent?: number | null): GolfGolfer {
  return { name, probability, rendered_percent, american_odds: null,
    opening_probability: null, movement_24h: null, rank: 1, sources: { datagolf: probability }, top_5_prob: 60 };
}

function livePlayer(name: string, i: number): GolfLeaderboardPlayer {
  return { name, position: `${i + 1}`, score: "-3", total_score_raw: -3,
    today: "-1", today_raw: -1, thru: "9", hole: "9", current_round: 2,
    win_prob: 100 / 3, rendered_percent: allocation[i], win_prob_change: null,
    position_change: null, top_5_prob: 60, top_10_prob: null, top_20_prob: null, make_cut_prob: null };
}

async function render(golfers: GolfGolfer[], players: GolfLeaderboardPlayer[] = []) {
  const tournament: GolfTournamentDetailResponse = {
    tournament: { name: "Synthetic Masters", slug: "synthetic-masters", key: "synthetic-masters",
      is_major: true, is_womens: false, start_date: null, end_date: null, venue: null,
      location: null, schedule_status: null, commence_time: null, resolution_date: null },
    golfers, markets: [], evolution_market_id: null, biggest_movers: [],
  };
  jest.mocked(fetchGolfTournament).mockResolvedValue(tournament);
  jest.mocked(fetchGolfLeaderboard).mockResolvedValue({ status: "live", event_name: "Synthetic Masters",
    current_round: 2, last_updated: null, tour: "pga", player_count: players.length, has_snapshot: false, players });
  jest.mocked(fetchSportHierarchyDetail).mockResolvedValue({ slug: "golf", name: "Golf",
    leagues: [{ slug: "pga", name: "PGA Tour", sport_keys: [] }], showcase_events: [] });
  await act(async () => { root.render(<SportEventDetailPage />); });
}

function descendants(node: Node): Node[] {
  return [node, ...Array.from(node.childNodes).flatMap(descendants)];
}

function row(name: string): string[] {
  const nameNode = descendants(host).find((node) =>
    (node as HTMLElement).tagName === "SPAN" && node.textContent === name);
  expect(nameNode).toBeDefined();
  return Array.from(nameNode!.parentNode!.childNodes).map((node) => node.textContent ?? "");
}

beforeEach(() => {
  host = document.createElement("div");
  document.body.appendChild(host);
  root = createRoot(host);
});
afterEach(() => { act(() => root.unmount()); document.body.removeChild(host); jest.clearAllMocks(); });

it("prints the full live field's server allocation while overlapping Top 5 prices stay 60/60/60", async () => {
  await render([], names.map(livePlayer));
  expect(names.map((name) => row(name).slice(-2))).toEqual([
    ["34%", "60%"], ["33%", "60%"], ["33%", "60%"],
  ]);
  expect(names.reduce((sum, name) => sum + Number.parseInt(row(name).at(-2)!), 0)).toBe(100);
});

it("keeps the allocation attached to the tournament price selected ahead of live odds", async () => {
  await render([golfer(names[0], 0.255, 25)], names.map(livePlayer));
  expect(row(names[0]).slice(-2)).toEqual(["25%", "60%"]);
  expect(row(names[1]).slice(-2)).toEqual(["33%", "60%"]);
});

it("does not borrow the live allocation when the selected tournament price has none", async () => {
  await render([golfer(names[0], 0.255)], names.map(livePlayer));
  expect(row(names[0]).slice(-2)).toEqual(["26%", "60%"]);
});

it("uses tournament allocations without a live leaderboard", async () => {
  await render(names.map((name, i) => golfer(name, 1 / 3, allocation[i])));
  expect(names.map((name) => row(name).slice(-2))).toEqual([
    ["34%", "60%"], ["33%", "60%"], ["33%", "60%"],
  ]);
});

it.each([undefined, null, -1, 101, 1.5, Number.NaN, Number.POSITIVE_INFINITY])(
  "preserves legacy decimal precision for absent or invalid allocation %s", async (rendered) => {
    await render([golfer(names[0], 0.015, rendered)]);
    expect(row(names[0]).slice(-2)).toEqual(["1.5%", "60%"]);
  },
);

it("preserves uncertain boundary markers for allocated zero and 100", async () => {
  await render([golfer(names[0], 0.004, 0), golfer(names[1], 0.996, 100)]);
  expect(row(names[0]).slice(-2)).toEqual(["<1%", "60%"]);
  expect(row(names[1]).slice(-2)).toEqual([">99%", "60%"]);
});
