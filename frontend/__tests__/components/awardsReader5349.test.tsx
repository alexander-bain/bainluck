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
  expect(announcedNom).toContain("Settled by Kalshi");
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
        outcomes: [{ name: "Dune: Part Three", probability: 0.85, won: false }],
        result: { state: "pending", evidence_kind: "none", venue: null },
      })}
    />,
  );
  expect(openNom).toContain(">Not announced<");
  expect(openNom).toContain("Covers candidates listed in available markets");
  expect(openNom).not.toContain("Settled by");
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
  expect(withVenue).toContain("Settled by Kalshi");

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
  expect(withoutVenue).not.toContain("Settled by");
});
test("awards page sections explain that coverage reflects available prediction markets", () => {
  const html = renderToStaticMarkup(<EventConceptPage />);
  expect(html).toContain("Covers categories with available prediction markets, not every official award category.");
  expect(html).toContain("Covers nominations and side markets from available prediction markets, not the full official ballot.");
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
