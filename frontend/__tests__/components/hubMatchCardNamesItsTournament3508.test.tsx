/**
 * #3508 — a hub match card names the tournament it belongs to.
 *
 * ═══ WHAT A READER SAW ═══
 *
 * Production, `/hub/tennis`, 390x844, 2026-09-06. Six consecutive cards, each a
 * bare "X vs Y" with two percentages and nothing else:
 *
 *     Choinski / Donski vs Harrison / Skupski     <- US Open Men Doubles
 *     Dart / Lumsden vs Bucsa / Melichar-Martinez <- US Open Women Doubles
 *     Kim vs Tamm                                 <- ATP Challenger, third tier
 *
 * 0 of 81 Kalshi rows on the rail named their tournament, so a Slam and a
 * Challenger were visually identical. The 14 Polymarket rows DID name theirs,
 * but only because the tournament happens to be inside their market name
 * ("US Open WTA: Mirra Andreeva vs Anastasia Potapova") — which is why an
 * instrument that detects "is this the US Open?" from card text is really
 * detecting "did this row come from Polymarket?".
 *
 * ═══ WHAT THIS GUARDS ═══
 *
 * The damaging regression is not "the label is missing" — it is "the label is
 * WRONG", a Slam wearing a Challenger's name, because a reader who is told the
 * wrong tournament is worse off than one told nothing. So the two are rendered
 * side by side in one payload and pinned in both directions, which is a thing
 * asserting one card alone cannot do: a bug that stamps every card "Challenger"
 * passes a single-card happy-path test.
 *
 * The absent case is pinned too, and it is not a corner: Polymarket rows carry
 * no competition, and during the split deploy (Vercel ships the frontend before
 * Heroku) EVERY row is absent for a while. A card with no tournament must come
 * out exactly as it does today rather than rendering an empty eyebrow, a blank
 * line, or the string "undefined".
 */

import React from "react";
import { renderToStaticMarkup } from "react-dom/server";

jest.mock("next/link", () => ({
  __esModule: true,
  default: ({
    href,
    className,
    children,
  }: {
    href: string;
    className?: string;
    children: React.ReactNode;
  }) => (
    <a href={href} className={className}>
      {children}
    </a>
  ),
}));

jest.mock("next/navigation", () => ({
  useParams: () => ({ competition: "tennis" }),
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

/** Verbatim rows from the production rail on 2026-09-06. */
const SLAM_NAME = "Dart / Lumsden vs Bucsa / Melichar-Martinez";
const CHALLENGER_NAME = "Kim vs Tamm";
const POLYMARKET_NAME = "US Open WTA: Mirra Andreeva vs Anastasia Potapova";

const SLAM_COMPETITION = "US Open Women Doubles";
const CHALLENGER_COMPETITION = "ATP Challenger Phan Thiet 3";

const market = (
  id: number,
  name: string,
  competition: string | null,
  source = "kalshi",
) => ({
  id,
  name,
  source,
  external_id: `X-${id}`,
  market_tier: 5,
  category: "game_prop",
  resolution_date: null,
  outcome_count: 2,
  top_outcomes: [0, 1].map((i) => ({
    id: id * 10 + i,
    name: `Side ${i}`,
    probability: i === 0 ? 0.71 : 0.35,
    opening_probability: 0.5,
    rank: i + 1,
    movement_24h: null,
    team_id: null,
  })),
  canonical_market_key: null,
  group_id: null,
  section: "matches",
  ...(competition === null ? {} : { competition }),
});

const payloadWith = (matches: unknown[]) => ({
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
  sections: { matches },
  total_markets: matches.length,
  tier: 3,
  pool_counts: {},
  section_counts: {
    matches: {
      total: matches.length,
      shown: matches.length,
      dropped: 0,
      answers: matches.length,
    },
  },
  cache: null,
  availability: "fresh",
});

const render = () =>
  renderToStaticMarkup(React.createElement(CompetitionHubPage));

/** The rendered card for a match, as a markup slice starting at its name. */
function cardFor(markup: string, name: string): string {
  const at = markup.indexOf(name);
  expect(at).toBeGreaterThan(-1);
  // Back up to the enclosing card anchor, forward to the next one.
  const start = markup.lastIndexOf("<a ", at);
  const next = markup.indexOf("<a ", at);
  return markup.slice(start, next === -1 ? markup.length : next);
}

describe("#3508: a hub match card says which tournament it belongs to", () => {
  it("a Slam and a Challenger on the same rail are told apart", () => {
    currentPayload = payloadWith([
      market(1, SLAM_NAME, SLAM_COMPETITION),
      market(2, CHALLENGER_NAME, CHALLENGER_COMPETITION),
    ]);
    const markup = render();

    const slam = cardFor(markup, SLAM_NAME);
    const challenger = cardFor(markup, CHALLENGER_NAME);

    // Each card names its OWN tournament...
    expect(slam).toContain(SLAM_COMPETITION);
    expect(challenger).toContain(CHALLENGER_COMPETITION);

    // ...and, the direction that actually misleads, not the other one's. A bug
    // that hoisted one label onto every card would satisfy the two assertions
    // above and fail here.
    expect(slam).not.toContain("Challenger");
    expect(challenger).not.toContain("US Open");
  });

  it("the tournament is drawn on the card, not merely present in the payload", () => {
    currentPayload = payloadWith([market(1, SLAM_NAME, SLAM_COMPETITION)]);
    const card = cardFor(render(), SLAM_NAME);

    // Ordering alone is NOT enough to assert here: `indexOf` returns -1 when
    // the label is missing entirely, and -1 is less than any real index, so an
    // ordering-only check passes vacuously on a card that never drew it.
    const labelAt = card.indexOf(SLAM_COMPETITION);
    const nameAt = card.indexOf(SLAM_NAME);
    expect(labelAt).toBeGreaterThanOrEqual(0);
    expect(nameAt).toBeGreaterThanOrEqual(0);
    // An eyebrow ABOVE the match name, not a stray string elsewhere.
    expect(labelAt).toBeLessThan(nameAt);
  });

  it("a card with no tournament renders exactly as it did before", () => {
    // Both the ordinary absent cases: a Polymarket row (never has one) and a
    // Kalshi row during the split deploy (does not have one YET).
    currentPayload = payloadWith([
      market(1, POLYMARKET_NAME, null, "polymarket"),
      market(2, CHALLENGER_NAME, null),
    ]);
    const markup = render();

    expect(markup).toContain(POLYMARKET_NAME);
    expect(markup).toContain(CHALLENGER_NAME);
    // No empty eyebrow, and above all no "undefined"/"null" leaking to a reader.
    expect(markup).not.toContain("undefined");
    expect(markup).not.toMatch(/>\s*null\s*</);
    expect(cardFor(markup, CHALLENGER_NAME)).not.toMatch(
      /text-\[11px\][^"]*"><\/span>/,
    );
  });

  it("an empty-string tournament is not drawn as a blank line", () => {
    currentPayload = payloadWith([market(1, CHALLENGER_NAME, "")]);
    const card = cardFor(render(), CHALLENGER_NAME);

    expect(card).toContain(CHALLENGER_NAME);
    expect(card).not.toMatch(/text-\[11px\][^"]*"><\/span>/);
  });

  it("a long tournament name cannot push the card sideways again", () => {
    // UX-P183 (#2877) fixed a 292px horizontal blowout on this exact card. The
    // eyebrow is a NEW unbreakable string on it, so it carries the same
    // discipline — otherwise this ship silently reopens that one.
    currentPayload = payloadWith([
      market(1, SLAM_NAME, "ATP Challenger Ciudad de Guayaquil Presented By Something"),
    ]);
    const card = cardFor(render(), SLAM_NAME);

    const eyebrow = /<span class="([^"]*text-\[11px\][^"]*)"/.exec(card);
    expect(eyebrow).not.toBeNull();
    expect(eyebrow![1]).toMatch(/(^|\s)truncate(\s|$)/);
    expect(eyebrow![1]).toMatch(/(^|\s)min-w-0(\s|$)/);
  });

  it("control: the card still prints its two probabilities", () => {
    // Passes on both sides of this change by design — it asserts nothing about
    // the tournament, so it proves the suite runs rather than that the diff
    // landed.
    currentPayload = payloadWith([market(1, SLAM_NAME, SLAM_COMPETITION)]);
    const card = cardFor(render(), SLAM_NAME);

    expect(card).toContain("71%");
    expect(card).toContain("35%");
  });
});
