import React from "react";
import { renderToStaticMarkup } from "react-dom/server";

jest.mock("next/link", () => ({
  __esModule: true,
  default: ({ href, children, ...rest }: { href: string; children: React.ReactNode }) => (
    <a href={href} {...rest}>
      {children}
    </a>
  ),
}));

import { FuturesCard } from "../../components/discover/FuturesCard";
import { TournamentCard } from "../../components/discover/TournamentCard";
import { ConceptCard } from "../../components/discover/ConceptCard";
import {
  computeDiscoverInitials,
  isBlockedPexelsPhoto,
  resolveDiscoverFuturesVisual,
} from "../../lib/discover/discoverEntityVisual";
import type {
  FeedConceptData,
  FeedFuturesData,
  FeedItem,
  FeedTournamentData,
} from "@/lib/types";

function abHash(seed: string): number {
  return Array.from(seed).reduce((h, c) => ((h << 5) - h + c.charCodeAt(0)) | 0, 0);
}
function variantAId(): number {
  for (let id = 1; id < 10_000; id++) {
    if (Math.abs(abHash(`anon_${id}`)) % 2 !== 0) return id;
  }
  return 1;
}

describe("Discover image truth policy & monogram fallback (#12659)", () => {
  it("strips stock photos from person, team, film, song, and ticker markets and emits initials on a colour", () => {
    const person = resolveDiscoverFuturesVisual({
      name: "Will Jensen Huang publicly testify before Congress by June 30?",
      llm_sport_category: "tech",
      top_outcomes: [{ name: "Yes" }],
      image_url: "https://images.pexels.com/photos/11460276/pexels-photo-11460276.jpeg?h=350",
    });
    expect(person.imageUrl).toBeNull();
    expect(person.kind).toBe("person");
    expect(person.monogram.initials).toBe("JH");

    const song = resolveDiscoverFuturesVisual({
      name: "Who will be featured on GTA VI: The Album?",
      llm_sport_category: "entertainment",
      top_outcomes: [{ name: "Drake" }],
      image_url: "https://image.tmdb.org/t/p/w780/movie-backdrop.jpg",
    });
    expect(song.imageUrl).toBeNull();
    expect(song.kind).toBe("song");

    const ticker = resolveDiscoverFuturesVisual({
      name: "How high will Alphabet Inc. (GOOGL) go in 2026?",
      llm_sport_category: "economics",
      top_outcomes: [{ name: "Above $220" }],
      image_url: "https://images.pexels.com/photos/999/pexels-photo-999.jpeg",
    });
    expect(ticker.imageUrl).toBeNull();
    expect(ticker.monogram.initials).toBe("GOOGL");
    expect(computeDiscoverInitials("Kimi (Moonshot AI) IPO before 2027?")).toBe("KM");
    expect(isBlockedPexelsPhoto("https://images.pexels.com/photos/6289061/pexels-photo-6289061.jpeg")).toBe(true);
  });

  it("renders initials-on-colour monogram instead of a stock photo on Variant A entity cards without verified art", () => {
    const data = {
      id: variantAId(),
      name: '"The Odyssey" Rotten Tomatoes score?',
      llm_sport_category: "entertainment",
      sport_name: "Entertainment",
      status: "open",
      source: "kalshi",
      top_outcomes: [{ id: 1, name: "Above 85", probability: 0.62, movement: null }],
      outcome_count: 2,
      image_url: "https://images.pexels.com/photos/55555/pexels-photo-55555.jpeg?h=350",
    } as unknown as FeedFuturesData;
    const item = { type: "futures", score: 80, reason: "", headline: "", data } as unknown as FeedItem;
    const html = renderToStaticMarkup(
      <FuturesCard item={item} data={data} liked={false} setLiked={() => {}} trending={false} />,
    );
    expect(html).toContain('data-card-variant="A"');
    expect(html).not.toContain('data-testid="futures-hero-image"');
    expect(html).toContain('data-testid="futures-hero-monogram"');
    expect(html).toContain(">OD<");
  });

  it("renders verified logo with object-contain and portrait with object-top on Variant A", () => {
    const logoData = {
      id: variantAId(),
      name: "2026 NHL Stanley Cup Champion?",
      llm_sport_category: "hockey",
      sport_name: "NHL",
      status: "open",
      source: "kalshi",
      top_outcomes: [{ id: 1, name: "Carolina Hurricanes", probability: 0.21, movement: null }],
      outcome_count: 2,
      image_url: "https://a.espncdn.com/i/teamlogos/nhl/500/car.png",
      image_presentation: "logo",
    } as unknown as FeedFuturesData;
    const html = renderToStaticMarkup(
      <FuturesCard
        item={{ type: "futures", score: 80, reason: "", headline: "", data: logoData } as unknown as FeedItem}
        data={logoData}
        liked={false}
        setLiked={() => {}}
        trending={false}
      />,
    );
    expect(html).toContain('data-testid="futures-hero-image"');
    expect(html).toContain("object-contain");
  });

  it("renders verified portraits on TournamentCard and ConceptCard when served", () => {
    const tHtml = renderToStaticMarkup(
      <TournamentCard
        data={
          {
            name: "The ANNIKA driven by Gainbridge at Pelican",
            golfers: [{ name: "Hye-Jin Choi", probability: 0.24 }],
            image_url: "https://a.espncdn.com/i/headshots/golf/players/full/9945.png",
            image_presentation: "portrait",
          } as unknown as FeedTournamentData
        }
        liked={false}
        setLiked={() => {}}
      />,
    );
    expect(tHtml).toContain('data-testid="tournament-hero-image"');

    const cHtml = renderToStaticMarkup(
      <ConceptCard
        data={
          {
            key: "event:ufc:ufc-325",
            name: "UFC Fight Night",
            domain: "mma",
            status: "scheduled",
            leader: { name: "Ciryl Gane", probability: 0.68 },
            image_url: "https://a.espncdn.com/i/headshots/mma/players/full/4426000.png",
            image_presentation: "portrait",
          } as unknown as FeedConceptData
        }
        liked={false}
        setLiked={() => {}}
      />,
    );
    expect(cHtml).toContain('data-testid="concept-hero-image"');
  });
});
