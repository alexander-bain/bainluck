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
    // #1935: this case now carries a result_summary. It used to pass a bare
    // `marquee_whathit: true`, which the empty-envelope classifier no longer
    // admits — a settled card with no winner AND no summary can only print
    // "see the recap", which is a settled card that cannot say what happened.
    // The behaviour this test exists for (FINAL chip, live-framing reason
    // replaced by the settled recap invite) is unchanged and still asserted.
    const html = renderToStaticMarkup(
      <FeedCard
        item={conceptItem({
          marquee_whathit: true,
          result_summary: "Decided on the final stage",
        })}
      />,
    );
    expect(html).toContain("FINAL");
    // The live-framing reason line is replaced by what actually happened. With a
    // summary on the payload the card leads with THAT rather than the generic
    // "see the recap" invite, which is the better of the two settled framings —
    // the invite is the fallback for a card that has nothing more specific.
    expect(html).not.toContain("184 riders in the peloton");
    expect(html).toContain("Decided on the final stage");
  });

  test("#1935: a whathit concept with NO nameable result renders nothing", () => {
    const html = renderToStaticMarkup(
      <FeedCard item={conceptItem({ marquee_whathit: true })} />,
    );
    expect(html).toBe("");
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

  test("non-marquee live concept is failed closed — nothing to predict (#1486)", () => {
    // L2-215 Item 1: a live/upcoming concept carries no outcome, so the FeedCard
    // dispatcher now suppresses it at the eligibility boundary rather than rendering
    // a bare reason-only tile. Only WHAT-HIT (settled result) concepts surface.
    const html = renderToStaticMarkup(
      <FeedCard item={conceptItem({ status: "live", marquee_whathit: false })} />,
    );
    expect(html).toBe("");
  });
});
