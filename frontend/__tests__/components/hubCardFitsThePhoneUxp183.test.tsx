/**
 * UX-P183 (#2877) — a hub card fits the phone it is drawn on.
 *
 * ═══ WHAT A READER SAW ═══
 *
 * Production, `/hub/tennis`, 2026-09-06 07:40Z, viewport 390x844:
 *
 *     grid cell  `grid gap-3 sm:grid-cols-2 lg:grid-cols-3`   358px
 *     the card   `<a class="block bg-surface-card …">`        650px   left 16, right 666
 *     its row    `flex items-center gap-2 py-1.5`             616px
 *     document.documentElement.scrollWidth                    666
 *
 * The card overhangs its own grid cell by 292px, so the page drags sideways and
 * the right-hand 292px — which is exactly where the probability sits — is off
 * the screen. The numbers were in the DOM the whole time: card 1 held 72%/29%,
 * card 2 56%/50%, card 3 74%/27%, all past x=390. "The card prints one number"
 * is the product; on a phone the first 73 cards of the tennis hub printed none.
 *
 * ═══ THE CAUSE, AND WHY IT LOOKED LIKE IT WAS ALREADY HANDLED ═══
 *
 * The outcome name already had `truncate`. `truncate` is
 * `overflow:hidden; text-overflow:ellipsis; white-space:nowrap` — and that last
 * one is the trap. A flex item defaults to `min-width: auto`, meaning it will
 * not shrink below its CONTENT's min-content width, and `nowrap` makes the
 * min-content width the entire unbroken string. So `truncate` on a `flex-1`
 * child with no `min-w-0` does not merely fail to help: the `nowrap` it adds is
 * what makes the row unshrinkable in the first place. It reads like the problem
 * is solved and is the reason the row grows.
 *
 * ═══ WHAT THIS GUARDS, AND WHY IT IS NOT A RESTATEMENT OF THE DIFF ═══
 *
 * Asserting `className.includes("min-w-0")` on the one element I edited would
 * be the diff written twice: it passes for exactly the instance I already fixed
 * and says nothing about the next one. jsdom does no layout, so measuring is
 * not available either.
 *
 * So this asserts the RULE the bug is an instance of, over every element the
 * real page renders: **a `truncate` inside a flex or grid container must carry
 * `min-w-0`.** That fires on the element fixed here, and it fires on the next
 * card anyone adds to this page with the same mistake — which is the actual
 * failure mode, since the two classes are written in different files by
 * different people months apart and look correct individually.
 */

import React from "react";
import { renderToStaticMarkup } from "react-dom/server";

// The `className` pass-through matters: the card IS a `next/link`, so a mock
// that drops className renders the card with no classes and every assertion
// about the card's classes becomes unfalsifiable.
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

/** The real doubles pair whose name set the 616px row on production. */
const LONG_NAME = "Kevin Krawietz / Tim Putz";
const LONGER_NAME = "Jean-Julien Rojer / Theodore Winegar";

const market = (id: number, name: string, outcomes: string[]) => ({
  id,
  name,
  source: "kalshi",
  external_id: `X-${id}`,
  market_tier: 5,
  category: "championship",
  resolution_date: null,
  outcome_count: outcomes.length,
  top_outcomes: outcomes.map((n, i) => ({
    id: id * 10 + i,
    name: n,
    probability: i === 0 ? 0.72 : 0.29,
    opening_probability: 0.5,
    rank: i + 1,
    movement_24h: null,
    team_id: null,
  })),
  canonical_market_key: null,
  group_id: null,
  section: "matches",
});

const payload = {
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
  sections: {
    matches: [
      market(1, "Krawietz / Puetz vs Rojer J-J / Winegar", [LONG_NAME, LONGER_NAME]),
    ],
  },
  total_markets: 1,
  tier: 3,
  pool_counts: {},
  section_counts: { matches: { total: 1, shown: 1, dropped: 0, answers: 1 } },
  cache: null,
  availability: "fresh",
};

/** Every `class="…"` in the markup, with its element's tag, in document order. */
function elements(markup: string) {
  const out: { tag: string; cls: string; index: number }[] = [];
  const re = /<([a-z]+)\b([^>]*)>/g;
  let m: RegExpExecArray | null;
  while ((m = re.exec(markup)) !== null) {
    const cls = /class="([^"]*)"/.exec(m[2])?.[1] ?? "";
    out.push({ tag: m[1], cls, index: m.index });
  }
  return out;
}

const isFlexOrGrid = (cls: string) =>
  /(^|\s)(flex|inline-flex|grid|inline-grid)(\s|$)/.test(cls);

const canShrink = (cls: string) => /(^|\s)min-w-0(\s|$)/.test(cls);

describe("UX-P183 (#2877): a hub card cannot overflow the phone it is drawn on", () => {
  beforeEach(() => {
    currentPayload = payload;
  });

  it("every truncating element inside a flex or grid row can actually shrink", () => {
    const markup = renderToStaticMarkup(React.createElement(CompetitionHubPage));
    const els = elements(markup);

    // An element truncates if it says so; it can only DO it if some ancestor
    // chain lets it shrink. Approximated in document order: the nearest
    // preceding flex/grid container is its formatting context here, because
    // this page's cards are shallow.
    const offenders: string[] = [];
    for (let i = 0; i < els.length; i++) {
      const el = els[i];
      if (!/(^|\s)truncate(\s|$)/.test(el.cls)) continue;
      const parentIsFlexOrGrid = els
        .slice(0, i)
        .reverse()
        .find((p) => isFlexOrGrid(p.cls));
      if (!parentIsFlexOrGrid) continue;
      if (!canShrink(el.cls)) offenders.push(el.cls);
    }

    expect(offenders).toEqual([]);
  });

  it("the outcome name is present, truncating, AND shrinkable — all three", () => {
    const markup = renderToStaticMarkup(React.createElement(CompetitionHubPage));

    expect(markup).toContain(LONG_NAME);
    const row = elements(markup).find((e) => e.cls.includes("truncate"));
    expect(row).toBeDefined();
    // Both directions of the actual bug: `truncate` without `min-w-0` never
    // truncates, and `min-w-0` without `truncate` wraps to two lines instead.
    expect(row!.cls).toMatch(/(^|\s)truncate(\s|$)/);
    expect(row!.cls).toMatch(/(^|\s)min-w-0(\s|$)/);
  });

  it("the card itself can shrink inside its grid cell", () => {
    const markup = renderToStaticMarkup(React.createElement(CompetitionHubPage));
    const card = elements(markup).find(
      (e) => e.tag === "a" && e.cls.includes("bg-surface-card") && e.cls.includes("rounded-2xl"),
    );
    expect(card).toBeDefined();
    expect(card!.cls).toMatch(/(^|\s)min-w-0(\s|$)/);
  });

  it("the probability still renders beside the name it belongs to", () => {
    // The fix must shrink the name, not delete the number: a truncation that
    // also dropped the percentage would satisfy every width assertion above.
    const markup = renderToStaticMarkup(React.createElement(CompetitionHubPage));
    expect(markup).toContain("72%");
    expect(markup).toContain("29%");
  });
});
