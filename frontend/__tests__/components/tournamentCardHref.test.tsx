// #213 surface unification: the shared golf TournamentCard now links to the
// canonical Event Concept page (/event/golf/<slug>) — Alex ruled concept =
// canonical after his live-day side-by-side on The Open (GOLF_DEFAULT_TO_EVENT_PAGE
// flipped true). The old /categories/golf/tournaments/<slug> route 308s to the
// same concept slug (next.config.mjs). Still NOT the generic /sport page (#926).

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

describe("shared TournamentCard href (#213 concept-canonical)", () => {
  test("links to the canonical Event Concept page, not the old bespoke route or /sport", () => {
    const html = renderToStaticMarkup(<TournamentCard tournament={tournament} />);
    expect(html).toContain('href="/event/golf/the-open-championship"');
    expect(html).not.toContain("/categories/golf/tournaments/");
    expect(html).not.toContain("/sport/");
  });

  test("hrefOverride still wins", () => {
    const html = renderToStaticMarkup(
      <TournamentCard tournament={tournament} href="/custom/path" />,
    );
    expect(html).toContain('href="/custom/path"');
  });
});
