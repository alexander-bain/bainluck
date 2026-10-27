import React from "react";
import { renderToStaticMarkup } from "react-dom/server";
import sourceFixture from "../fixtures/awardsCategoryTruth5349.SYNTHETIC.json";
import type { EventConceptResponse } from "@/lib/types";
let mockEnvelope: EventConceptResponse;
let mockDomain = "awards";
let mockInterval: ((data: EventConceptResponse) => number) | undefined;
jest.mock("next/navigation", () => ({ useParams: () => ({ domain: mockDomain, slug: "oscars-2026" }), useRouter: () => ({ replace: () => {} }) }));
jest.mock("next/link", () => ({ __esModule: true, default: ({ children, ...props }: { children: React.ReactNode }) => <a {...props}>{children}</a> }));
jest.mock("swr", () => ({ __esModule: true, default: (key: unknown[], fetcher: unknown, options?: { refreshInterval?: (data: EventConceptResponse) => number }) => { if (key?.[0] === "event-concept") { mockInterval = options?.refreshInterval; return { data: mockEnvelope, error: null, isLoading: false }; } return { data: null, error: null, isLoading: false }; } }));
jest.mock("@/hooks", () => ({ usePageTracking: () => {}, useScrollDepth: () => {}, useEngagementTime: () => {} }));
jest.mock("@/lib/api", () => ({ fetchEventConcept: () => Promise.resolve(null), fetchFuturesHistory: () => Promise.resolve(null), formatProbability: (p: number | null) => p == null ? "—" : `${Math.round(p * 100)}%` }));
import EventConceptPage from "@/app/event/[domain]/[slug]/page";
import { AwardsCategoryCard } from "@/components/event/MatchupsRail";
const card = (values: Partial<EventConceptResponse["children"][number]>) => ({ market_id: 1, market_name: "Best Picture", probability: .99, settled: false, outcomes: [{ name: "Favorite", probability: .99, won: false }], ...values });
const grade = (name: string) => ({ name, probability: null, won: true });
// Actual separately reviewed backend output for synthetic rows. No production
// awards roster/calendar/reader acceptance claimed by this source fixture.
const envelope = (): EventConceptResponse => JSON.parse(JSON.stringify(sourceFixture)) as EventConceptResponse;
beforeEach(() => { mockEnvelope = envelope(); mockDomain = "awards"; });
test("actual page keeps the primary category visible and announces only its own factual winner", () => {
  const html = renderToStaticMarkup(<EventConceptPage />);
  expect(html).toContain('href="#awards-category-1"');
  expect(html).toContain('id="awards-category-1"');
  expect(html).toContain("Actual unpriced winner");
  expect(html).toContain("Not announced");
  expect(html).toContain("Trading closed · Result not yet confirmed");
  expect(html).toContain("Joint winners"); expect(html).toContain("Composer A"); expect(html).toContain("Composer B");
  expect(html).toContain("Another nominee"); expect(html).not.toContain(">Other<");
  expect(html).toContain("Guest1"); expect(html).toContain("Nominations and more");
  expect(html).not.toContain("Final"); expect(html).not.toContain("Completed (");
  expect(html).toContain("Probability history for Best Picture");
  expect(html).not.toContain("Two-sided");
  expect(html).not.toContain('href="#head-to-head"');
  expect(html).toMatch(/<a[^>]*href="#matchups"[^>]*>Categories<\/a>/);
});
test("closed-ungraded card never prints its favorite or standalone winner as a result", () => {
  const html = renderToStaticMarkup(<AwardsCategoryCard child={card({ settled: true, graded_winner: "Favorite" })} />);
  expect(html).toContain("Result not yet confirmed"); expect(html).not.toContain("Favorite"); expect(html).not.toContain("99%");
});
test("prop grade is a result, never labelled an award winner", () => {
  const html = renderToStaticMarkup(<AwardsCategoryCard child={card({ kind: "prop", settled: true, outcomes: [grade("Guest1")] })} />);
  expect(html).toContain("Guest1"); expect(html).toContain(">Result<"); expect(html).not.toContain("Winner");
  expect(html).not.toContain("From listed market candidates");
  expect(html).not.toContain("Covers candidates listed in available markets");
});
test("nominations prop distinguishes Nominated candidates and explains partial market coverage", () => {
  const announcedNom = renderToStaticMarkup(
    <AwardsCategoryCard
      child={card({
        kind: "prop",
        prop_type: "nominations",
        settled: true,
        outcomes: [grade("Nominated film A"), grade("Nominated film B")],
        result: { state: "announced", evidence_kind: "venue_settlement", venue: "kalshi" },
      })}
    />,
  );
  expect(announcedNom).toContain(">Nominated<");
  expect(announcedNom).toContain("Result source · Kalshi");
  expect(announcedNom).toContain("From listed market candidates — not the full official ballot");
  expect(announcedNom).not.toContain(">Winner<");
  expect(announcedNom).not.toContain(">Joint winners<");
  expect(announcedNom).not.toContain(">Result<");

  const openNom = renderToStaticMarkup(
    <AwardsCategoryCard
      child={card({
        kind: "prop",
        prop_type: "nominations",
        settled: false,
        outcomes: [
          { name: "The Odyssey", probability: 0.98, won: false },
          { name: "The Black Ball", probability: 0.95, won: false },
        ],
        result: { state: "pending", evidence_kind: "none", venue: null },
      })}
    />,
  );
  expect(openNom).toContain(">Best Picture<");
  expect(openNom).toContain(">Chance of a nomination<");
  expect(openNom).not.toContain(">Not announced<");
  expect(openNom).not.toContain(">Nominated<");
  expect(openNom).not.toContain(">Winner<");
  expect(openNom).toContain("Covers candidates listed in available markets");
  expect(openNom).not.toContain("Result source ·");

  const openCat = renderToStaticMarkup(
    <AwardsCategoryCard
      child={card({
        settled: false,
        outcomes: [{ name: "The Odyssey", probability: 0.45, won: false }],
        result: { state: "pending", evidence_kind: "none", venue: null },
      })}
    />,
  );
  expect(openCat).toContain(">Best Picture<");
  expect(openCat).toContain(">Not announced<");
  expect(openCat).not.toContain(">Chance of a nomination<");
  expect(openCat).not.toContain("Covers candidates listed in available markets");
  expect(openCat).not.toContain("From listed market candidates");

  const openSideProp = renderToStaticMarkup(
    <AwardsCategoryCard
      child={card({
        market_name: "Who will attend the Oscars",
        kind: "prop",
        prop_type: "occurrence",
        settled: false,
        outcomes: [{ name: "Guest2", probability: 0.9, won: false }],
        result: { state: "pending", evidence_kind: "none", venue: null },
      })}
    />,
  );
  expect(openSideProp).toContain(">Not announced<");
  expect(openSideProp).not.toContain(">Chance of a nomination<");
  expect(openSideProp).not.toContain("Covers candidates listed in available markets");
  expect(openSideProp).not.toContain("From listed market candidates");
});
test("announced category renders supported settling provider attribution and omits it when venue is null", () => {
  const withVenue = renderToStaticMarkup(
    <AwardsCategoryCard
      child={card({
        settled: true,
        outcomes: [grade("The Pitt")],
        result: { state: "announced", evidence_kind: "venue_settlement", venue: "kalshi" },
      })}
    />,
  );
  expect(withVenue).toContain(">Winner<");
  expect(withVenue).toContain("The Pitt");
  expect(withVenue).toContain("Result source · Kalshi");
  expect(withVenue).not.toContain("From listed market candidates");
  expect(withVenue).not.toContain("Covers candidates listed in available markets");

  const withoutVenue = renderToStaticMarkup(
    <AwardsCategoryCard
      child={card({
        settled: true,
        outcomes: [grade("The Pitt")],
        result: { state: "announced", evidence_kind: "venue_settlement", venue: null },
      })}
    />,
  );
  expect(withoutVenue).toContain(">Winner<");
  expect(withoutVenue).toContain("The Pitt");
  expect(withoutVenue).not.toContain("Result source ·");
});
test("awards page sections explain that coverage reflects available prediction markets", () => {
  const html = renderToStaticMarkup(<EventConceptPage />);
  const matchupsIdx = html.indexOf('id="matchups"');
  const propsIdx = html.indexOf('id="props"');
  expect(matchupsIdx).toBeGreaterThan(-1);
  expect(propsIdx).toBeGreaterThan(matchupsIdx);
  const categoriesSection = html.slice(matchupsIdx, propsIdx);
  const propsSection = html.slice(propsIdx);
  expect(categoriesSection).toContain("Covers categories with available prediction markets, not every official award category.");
  expect(categoriesSection).not.toContain("Covers nominations and side markets from available prediction markets, not the full official ballot.");
  expect(propsSection).toContain("Covers nominations and side markets from available prediction markets, not the full official ballot.");
  expect(propsSection).not.toContain("Covers categories with available prediction markets, not every official award category.");
  expect(html).toContain(">Nominated<");
  expect(html).toContain("From listed market candidates — not the full official ballot");
});
test("non-awards retain combat main-event deduplication and cadence", () => {
  mockDomain = "ufc"; mockEnvelope = { ...envelope(), event: { ...envelope().event, domain: "ufc", status: "live" } };
  const html = renderToStaticMarkup(<EventConceptPage />);
  expect(html).not.toContain('id="awards-category-1"');
  expect(mockInterval?.(mockEnvelope)).toBe(30000);
  const unknown = { ...mockEnvelope, event: { ...mockEnvelope.event, status: "unknown" as const } };
  expect(mockInterval?.(unknown)).toBe(0);
});
