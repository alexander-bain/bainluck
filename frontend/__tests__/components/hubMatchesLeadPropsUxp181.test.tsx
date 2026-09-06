/**
 * UX-P181 (#2167) — MATCHES leads PROPS on every competition hub.
 *
 * ═══ WHAT A READER SAW ═══
 *
 * Measured on the deployed /hub/tennis during the US Open, 2026-09-06, phone
 * width (390px), heading offsets read out of the live DOM:
 *
 *     y=    287   Tournaments
 *     y=    498   Props     147
 *     y= 23,746   Matches   126     <- about 28 phone screens down
 *     y= 38,812   More Markets 29
 *
 * Two live US Open singles matches were playing at the time. Both were on the
 * page, under 147 set-games and total-sets prop cards.
 *
 * ═══ WHY IT ONLY BECAME WRONG NOW ═══
 *
 * `SECTION_ORDER` put props above matches from the beginning and it did not
 * matter, because the matches rail was nearly always empty: it could only show
 * head-to-heads the matcher had FAILED to link (#2167), so /hub/tennis headed
 * "MATCHES · 56" over zero US Open singles. The linked-match rail filled it,
 * and the pre-existing order became the thing standing between a reader and
 * the match they opened the page for.
 *
 * The rule the constant now encodes: a market DERIVED from a match sorts below
 * the match. "Set 3 Games O/U 9.5" is only meaningful once you know the match
 * is on.
 *
 * ═══ WHAT THIS GUARDS ═══
 *
 * The real page component, rendered server-side over a payload holding both
 * sections, asserting on the ORDER OF THE HEADINGS IN THE MARKUP rather than on
 * the constant. A test that read `SECTION_ORDER` would pass if the array were
 * right and `orderedSections` ignored it.
 */

import React from "react";
import { renderToStaticMarkup } from "react-dom/server";

jest.mock("next/link", () => ({
  __esModule: true,
  default: ({ href, children }: { href: string; children: React.ReactNode }) => (
    <a href={href}>{children}</a>
  ),
}));

let currentCompetition = "tennis";
jest.mock("next/navigation", () => ({
  useParams: () => ({ competition: currentCompetition }),
}));

let currentPayload: unknown = null;
jest.mock("swr", () => ({
  __esModule: true,
  default: () => ({ data: currentPayload, error: undefined }),
}));

jest.mock("@/hooks", () => ({
  usePageTracking: () => undefined,
  useScrollDepth: () => undefined,
  useEngagementTime: () => undefined,
  useAnalytics: () => ({ trackEvent: () => undefined }),
}));

import CompetitionHubPage from "../../app/hub/[competition]/page";

/** A market in the shape the hub sections carry. */
const market = (id: number, name: string, section: string) => ({
  id,
  name,
  source: "kalshi",
  external_id: `X-${id}`,
  market_tier: 5,
  category: "championship",
  resolution_date: null,
  outcome_count: 2,
  top_outcomes: [
    { id: id * 10, name: "A", probability: 0.6, opening_probability: 0.5, rank: 1, movement_24h: null, team_id: null },
    { id: id * 10 + 1, name: "B", probability: 0.4, opening_probability: 0.5, rank: 2, movement_24h: null, team_id: null },
  ],
  canonical_market_key: null,
  group_id: null,
  section,
});

const payload = (sections: Record<string, unknown[]>) => ({
  competition: "tennis",
  label: "Tennis",
  title: "Tennis",
  emoji: "🎾",
  blurb: "",
  sport_key: "tennis_atp",
  section_labels: {},
  upcoming_label: "Upcoming Tournaments",
  upcoming_label_neutral: "Tournaments",
  upcoming: [],
  sections,
  total_markets: Object.values(sections).reduce((n, v) => n + v.length, 0),
  tier: "standard",
});

const render = (sections: Record<string, unknown[]>): string => {
  currentPayload = payload(sections);
  return renderToStaticMarkup(React.createElement(CompetitionHubPage));
};

/** Where each heading lands in the markup; -1 when it never printed. */
const headingOrder = (html: string, headings: string[]) =>
  headings.map((h) => [h, html.indexOf(`>${h}<`)] as const);

describe("UX-P181 — the hub prints matches above props", () => {
  const MATCHES = [market(1, "Mensik vs Tien", "matches"), market(2, "Zverev vs Tabilo", "matches")];
  const PROPS = [
    market(3, "Mensik vs. Tien: Set 3 Games O/U 9.5", "props"),
    market(4, "Mensik vs. Tien: Set 4 Games O/U 10.5", "props"),
  ];

  it("puts the Matches heading before the Props heading", () => {
    const html = render({ props: PROPS, matches: MATCHES });
    const [[, matchesAt], [, propsAt]] = headingOrder(html, ["Matches", "Props"]);

    expect(matchesAt).toBeGreaterThan(-1);
    expect(propsAt).toBeGreaterThan(-1);
    expect(matchesAt).toBeLessThan(propsAt);
  });

  it("does not depend on the order the payload happens to serialise in", () => {
    // The object above already lists `props` first; this is the same assertion
    // with the keys the other way round, so a pass cannot come from the payload's
    // own key order rather than from SECTION_ORDER.
    const html = render({ matches: MATCHES, props: PROPS });
    const [[, matchesAt], [, propsAt]] = headingOrder(html, ["Matches", "Props"]);

    expect(matchesAt).toBeLessThan(propsAt);
  });

  it("still puts tournament winners above matches", () => {
    // The paired positive for the section that legitimately outranks both: a
    // hub is a tournament page first. Moving matches up must not have moved
    // them above the thing the competition IS.
    const html = render({
      futures: [market(5, "2026 US Open Winner", "futures"), market(6, "2026 Wimbledon Winner", "futures")],
      props: PROPS,
      matches: MATCHES,
    });
    const [[, futuresAt], [, matchesAt], [, propsAt]] = headingOrder(html, [
      "Tournament Winners",
      "Matches",
      "Props",
    ]);

    expect(futuresAt).toBeGreaterThan(-1);
    expect(futuresAt).toBeLessThan(matchesAt);
    expect(matchesAt).toBeLessThan(propsAt);
  });
});
