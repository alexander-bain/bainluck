// #999 L2-66 Item 0: the shared golf TournamentCard links to the BESPOKE golf
// tournament detail (/categories/golf/tournaments/[slug]) — NOT /event/[key]
// (reverted during OPEN-SPRINT-1 until the event surface's live leaderboard
// clears the bar) and NOT the generic /sport page (#926).

import { renderToStaticMarkup } from "react-dom/server";
import React from "react";
import type { GolfTournament } from "@/lib/types";

jest.mock("next/link", () => ({
  __esModule: true,
  default: ({ href, children }: { href: string; children: React.ReactNode }) => (
    <a href={href}>{children}</a>
  ),
}));

import TournamentCard from "../../components/TournamentCard";

const tournament = {
  key: "the_open",
  slug: "the-open-championship",
  name: "The Open Championship",
  is_major: true,
  schedule_status: "upcoming",
  golfers: [{ name: "Scottie Scheffler", probability: 0.12, rank: 1, movement_24h: null }],
  market_ids: [6],
  source_count: 2,
} as unknown as GolfTournament;

describe("shared TournamentCard href (L2-66 Item 0)", () => {
  test("links to the bespoke golf tournament detail, not /event or /sport", () => {
    const html = renderToStaticMarkup(<TournamentCard tournament={tournament} />);
    expect(html).toContain('href="/categories/golf/tournaments/the-open-championship"');
    expect(html).not.toContain("/event/");
    expect(html).not.toContain("/sport/");
  });

  test("hrefOverride still wins", () => {
    const html = renderToStaticMarkup(
      <TournamentCard tournament={tournament} href="/custom/path" />,
    );
    expect(html).toContain('href="/custom/path"');
  });
});
