/**
 * #8286 — the Discover golf card prints a tournament's name the way it was
 * served.
 *
 * ── WHAT A READER SAW ───────────────────────────────────────────────────────
 *
 * Production `/discover`, 390px, 2026-09-23 20:45Z: the golf card read
 * "Fedex Open De France". `GET /api/feed` served `data.name` =
 * "FedEx Open de France"; the card re-cased it with `toTitleCaseAcronymSafe`,
 * which lowercases every word and capitalises its first letter.
 *
 * ── THE DENOMINATOR ─────────────────────────────────────────────────────────
 *
 * The 97 distinct names `/api/golf` served in the same minute, through each
 * caser:
 *
 *     toTitleCaseAcronymSafe        31 changed  (the card, before)
 *     toAcronymSafePreservingCase   10 changed  (capitalises every word)
 *     toAcronymSafeKeepingCase       1 changed  ("the Memorial" → "The")
 *
 * ── THE ARMS ────────────────────────────────────────────────────────────────
 *
 *  1. The specimen, entered at `DiscoverCard` so a rewired card cannot pass.
 *  2. Five more of the 31, one per damage shape (acronym, ampersand, an
 *     all-caps brand word, a lowercase connector, an internal capital).
 *  3. CONTROL, UX-P050: a machine-cased "Pga" still reads "PGA". Without this
 *     arm the suite passes on `const title = data.name`, which would bring
 *     back the defect the old caser was added for.
 *  4. The helper's own edges: the leading letter, null, underscores.
 */

import { renderToStaticMarkup } from "react-dom/server";
import React from "react";
import type { FeedTournamentData, FeedItem } from "@/lib/types";
import { toAcronymSafeKeepingCase } from "@/lib/titleCase";

jest.mock("next/navigation", () => ({
  __esModule: true,
  useRouter: () => ({ push: jest.fn(), replace: jest.fn(), prefetch: jest.fn() }),
}));
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

import DiscoverCard from "../../components/DiscoverCard";

function tournamentItem(name: string): FeedItem {
  return {
    type: "tournament",
    score: 85,
    reason: "DP World Tour: Ludvig Aberg leads at 10.5%",
    headline: "Live",
    data: {
      key: "fedex_open_de_france",
      name,
      tour: "dp_world",
      tour_label: "DP World Tour",
      is_major: false,
      venue: "Le Golf National",
      golfers: [
        { name: "Ludvig Aberg", probability: 0.105, rank: 1, movement_24h: null },
        { name: "Tommy Fleetwood", probability: 0.087, rank: 2, movement_24h: null },
      ],
      market_ids: [60482001],
      source_count: 2,
    } as unknown as FeedTournamentData,
  } as unknown as FeedItem;
}

function draw(name: string): string {
  return renderToStaticMarkup(
    <DiscoverCard groupedItem={{ type: "single", item: tournamentItem(name) }} positionIndex={0} />,
  );
}

/** Text nodes only — every tag, and therefore every attribute, removed. */
function visible(html: string): string {
  return html.replace(/<[^>]*>/g, " ").replace(/\s+/g, " ");
}

describe("#8286 — the Discover golf card keeps the served casing", () => {
  it("prints the production specimen as served", () => {
    const html = draw("FedEx Open de France");
    expect(visible(html)).toContain("FedEx Open de France");
    expect(html).not.toContain("Fedex Open De France");
    expect(html).not.toContain("FedEx Open De France");
  });

  it.each([
    ["RBC Canadian Open", "Rbc Canadian Open"],
    ["AT&T Pebble Beach Pro-Am", "Pro-am"],
    ["THE CJ CUP Byron Nelson", "The Cj Cup"],
    ["Sony Open in Hawaii", "Open In Hawaii"],
    ["VidantaWorld Mexico Open", "Vidantaworld"],
  ])("prints %s as served", (served, damaged) => {
    const text = visible(draw(served));
    // renderToStaticMarkup escapes "&" as "&amp;" in text nodes.
    expect(text.replace(/&amp;/g, "&")).toContain(served);
    expect(text).not.toContain(damaged);
  });

  it("CONTROL (UX-P050): a machine-cased acronym is still shouted", () => {
    const text = visible(draw("Golfers To Win A Pga Tour Major In 2027"));
    expect(text).toContain("Golfers To Win A PGA Tour Major In 2027");
    expect(text).not.toContain("Pga");
  });
});

describe("toAcronymSafeKeepingCase", () => {
  it("capitalises only the first letter of the whole string", () => {
    expect(toAcronymSafeKeepingCase("the Memorial Tournament")).toBe("The Memorial Tournament");
    expect(toAcronymSafeKeepingCase("Open de Espana presented by Madrid")).toBe(
      "Open de Espana presented by Madrid",
    );
  });

  it("returns empty for empty input and treats underscores as spaces", () => {
    expect(toAcronymSafeKeepingCase(null)).toBe("");
    expect(toAcronymSafeKeepingCase(undefined)).toBe("");
    expect(toAcronymSafeKeepingCase("")).toBe("");
    expect(toAcronymSafeKeepingCase("pga_tour major")).toBe("PGA tour major");
  });
});
