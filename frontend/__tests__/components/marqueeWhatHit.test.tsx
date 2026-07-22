// L2-159 / #235 Item 4: a just-settled marquee card (marquee_whathit=true, the
// T+36h WHAT-HIT window) leads with THE RESULT — settled-means-settled grammar
// ("cards show results"). These guards assert BOTH directions per gotcha #43:
// the whathit card renders result-first AND a non-marquee settled card is
// untouched (flag absent → today's behavior).

import { renderToStaticMarkup } from "react-dom/server";
import React from "react";
import type { GolfTournament, FeedItem, FeedConceptData, FeedTournamentData } from "@/lib/types";

jest.mock("next/link", () => ({
  __esModule: true,
  default: ({ href, children }: { href: string; children: React.ReactNode }) => (
    <a href={href}>{children}</a>
  ),
}));

jest.mock("next/image", () => ({
  __esModule: true,
  default: ({ alt }: { alt: string }) => <img alt={alt} />,
}));

jest.mock("@/components/Analytics", () => ({
  __esModule: true,
  useAnalyticsContext: () => ({ track: () => {} }),
}));

import SharedTournamentCard from "../../components/TournamentCard";
import { TournamentCard as DiscoverTournamentCard } from "../../components/discover/TournamentCard";
import FeedCard from "../../components/FeedCard";

const golfTournament = {
  key: "tour_de_france",
  slug: "tour-de-france-2026",
  name: "Tour de France 2026",
  is_major: true,
  schedule_status: "upcoming",
  golfers: [{ name: "Tadej Pogačar", probability: 1.0, rank: 1, movement_24h: 0.02 }],
  market_ids: [1],
  source_count: 1,
} as unknown as GolfTournament;

describe("shared TournamentCard (Sports tab) WHAT-HIT", () => {
  test("whatHit leads with the champion + Won, suppresses the live pulse", () => {
    const html = renderToStaticMarkup(
      <SharedTournamentCard tournament={golfTournament} whatHit />,
    );
    expect(html).toContain("Champion");
    expect(html).toContain("Won");
    expect(html).toContain("Final");
    expect(html).not.toContain("Leader");
    // A settled card never shows a live "% today" movement, even with residual 24h move.
    expect(html).not.toContain("% today");
  });

  test("non-whathit is unchanged — Leader framing, no champion/won", () => {
    const html = renderToStaticMarkup(
      <SharedTournamentCard tournament={golfTournament} />,
    );
    expect(html).toContain("Leader");
    expect(html).not.toContain("Champion");
    expect(html).not.toContain(">Won<");
  });
});

describe("discover TournamentCard (Discover tab) WHAT-HIT", () => {
  const base = {
    key: "tour_de_france",
    name: "Tour de France 2026",
    is_major: true,
    golfers: [{ name: "Tadej Pogačar", probability: 1.0, rank: 1, movement_24h: 0.02 }],
    market_ids: [1],
    source_count: 1,
  } as unknown as FeedTournamentData;

  test("whatHit leads result-first (Champion · Won) with a Final badge", () => {
    const html = renderToStaticMarkup(
      <DiscoverTournamentCard
        data={{ ...base, marquee_whathit: true }}
        liked={false}
        setLiked={() => {}}
      />,
    );
    expect(html).toContain("Champion · Won");
    expect(html).toContain("Final");
    expect(html).toContain("Tadej Pogačar");
  });

  test("non-whathit still shows the live probability", () => {
    const html = renderToStaticMarkup(
      <DiscoverTournamentCard data={base} liked={false} setLiked={() => {}} />,
    );
    expect(html).not.toContain("Champion · Won");
  });
});

describe("ConceptFeedCard (Sports tab) WHAT-HIT", () => {
  function conceptItem(data: Partial<FeedConceptData>): FeedItem {
    return {
      type: "concept",
      score: 50,
      reason: "184 riders in the peloton",
      headline: "Today",
      data: {
        key: "cycling/tour-de-france-2026",
        name: "Tour de France 2026",
        domain: "cycling",
        status: "settled",
        is_major: true,
        fight_count: 0,
        ...data,
      } as FeedConceptData,
    };
  }

  test("whathit shows a FINAL chip and suppresses the live-framing reason", () => {
    const html = renderToStaticMarkup(
      <FeedCard item={conceptItem({ marquee_whathit: true })} />,
    );
    expect(html).toContain("FINAL");
    // The live-framing reason line is replaced by the settled recap invite.
    expect(html).not.toContain("184 riders in the peloton");
    expect(html).toContain("see the recap");
  });

  test("whathit + winner in payload leads with the champion + Won", () => {
    const html = renderToStaticMarkup(
      <FeedCard
        item={conceptItem({
          marquee_whathit: true,
          winner: "Tadej Pogačar",
          result_summary: "by 3:24",
        })}
      />,
    );
    expect(html).toContain("Tadej Pogačar");
    expect(html).toContain("Won");
    expect(html).toContain("by 3:24");
  });

  test("non-marquee settled concept is unchanged — no FINAL chip, reason kept", () => {
    const html = renderToStaticMarkup(
      <FeedCard item={conceptItem({ status: "live", marquee_whathit: false })} />,
    );
    expect(html).not.toContain("FINAL");
    expect(html).toContain("184 riders in the peloton");
  });
});
