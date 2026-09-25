/**
 * #8524 — `/hub/esports` prop cards read "Games Total: O/U 4.5" with no match.
 *
 * Seen on production 2026-09-25 03:10Z at 390px. The backend now serves
 * `event_title` (the venue's match name) ONLY on a card whose own name names no
 * match (`backend/app/utils/hub_prop_matchup.py`, guarded by
 * `test_hub_prop_card_names_its_match_8524.py`). These pin the card half on the
 * real page render: the title is drawn, it outranks the competition, it wraps
 * to two lines without being able to push the card sideways, and a card served
 * without it is byte-for-byte the #3508 card.
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
  useParams: () => ({ competition: "esports" }),
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

/** Verbatim from `/api/hub/esports` + the group's stored title, 2026-09-25. */
const GAMES_TOTAL = "Games Total: O/U 4.5";
const MATCH_TITLE =
  "Honor of Kings: Talent Gaming vs Rogue Warriors (BO5) - King Pro League Grand Finals Group Stage";
const LOS = "Will LOS Qualify for Worlds 2026?";

const prop = (id: number, name: string, extra: Record<string, unknown> = {}) => ({
  id,
  name,
  source: "polymarket",
  external_id: `0x${id}`,
  market_tier: 5,
  category: "game_prop",
  resolution_date: null,
  outcome_count: 2,
  top_outcomes: [0, 1].map((i) => ({
    id: id * 10 + i,
    name: i === 0 ? "Over" : "Under",
    probability: 0.5,
    opening_probability: 0.5,
    rank: i + 1,
    movement_24h: null,
    team_id: null,
  })),
  canonical_market_key: null,
  group_id: `polymarket:${id}`,
  section: "props",
  prop_type: "series prop",
  ...extra,
});

const payloadWith = (props: unknown[]) => ({
  competition: "esports",
  label: "Esports",
  title: "Esports",
  emoji: "🎮",
  blurb: "",
  sport_key: "esports",
  section_labels: {},
  upcoming_label: "Upcoming",
  upcoming_label_neutral: "Upcoming",
  upcoming: [],
  sections: { props },
  total_markets: props.length,
  tier: 3,
  pool_counts: {},
  section_counts: {
    props: { total: props.length, shown: props.length, dropped: 0, answers: props.length },
  },
  cache: null,
  availability: "fresh",
});

const render = () => renderToStaticMarkup(React.createElement(CompetitionHubPage));

function cardFor(markup: string, name: string): string {
  const at = markup.indexOf(name);
  expect(at).toBeGreaterThan(-1);
  const start = markup.lastIndexOf("<a ", at);
  const next = markup.indexOf("<a ", at);
  return markup.slice(start, next === -1 ? markup.length : next);
}

const eyebrowOf = (card: string) =>
  /<span class="([^"]*text-\[11px\][^"]*)">([^<]*)<\/span>/.exec(card);

describe("#8524: a hub prop card names the match it is about", () => {
  it("draws the served match title above the question", () => {
    currentPayload = payloadWith([prop(1, GAMES_TOTAL, { event_title: MATCH_TITLE })]);
    const card = cardFor(render(), GAMES_TOTAL);
    const eyebrow = eyebrowOf(card);
    expect(eyebrow).not.toBeNull();
    expect(eyebrow![2]).toBe(MATCH_TITLE);
    expect(card.indexOf(MATCH_TITLE)).toBeLessThan(card.indexOf(GAMES_TOTAL));
  });

  it("before this field, the same card named no match at all", () => {
    currentPayload = payloadWith([prop(1, GAMES_TOTAL)]);
    const card = cardFor(render(), GAMES_TOTAL);
    expect(eyebrowOf(card)).toBeNull();
    expect(card).not.toContain(" vs ");
  });

  it("the match outranks a competition when both are served", () => {
    currentPayload = payloadWith([
      prop(1, GAMES_TOTAL, { event_title: MATCH_TITLE, competition: "King Pro League" }),
    ]);
    const card = cardFor(render(), GAMES_TOTAL);
    expect(eyebrowOf(card)![2]).toBe(MATCH_TITLE);
    expect(card).not.toContain(">King Pro League<");
  });

  it("wraps to two lines and cannot push the card sideways", () => {
    currentPayload = payloadWith([prop(1, GAMES_TOTAL, { event_title: MATCH_TITLE })]);
    const cls = eyebrowOf(cardFor(render(), GAMES_TOTAL))![1].split(/\s+/);
    expect(cls).toEqual(expect.arrayContaining(["min-w-0", "line-clamp-2", "break-words"]));
    // `block` sets `display` after `line-clamp-2` does and the title ran to
    // three lines in the 390px render — the clamp only holds without it.
    expect(cls).not.toContain("block");
    expect(cls).not.toContain("truncate");
  });

  it("a card served without it keeps the #3508 competition line exactly", () => {
    currentPayload = payloadWith([prop(2, LOS, { competition: "LCK" })]);
    const eyebrow = eyebrowOf(cardFor(render(), LOS));
    expect(eyebrow![2]).toBe("LCK");
    expect(eyebrow![1]).toBe(
      "block min-w-0 truncate text-[11px] font-semibold text-text-muted leading-snug",
    );
  });
});
