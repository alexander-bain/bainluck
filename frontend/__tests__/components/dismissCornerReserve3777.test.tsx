/**
 * #3777 — the dismiss (×) button must not paint over the rest of its card.
 *
 * `DismissBtn` is `absolute top-3 right-3 z-10 w-7 h-7`, so it reserves NO
 * layout space. Everything else that reached the same corner was drawn
 * underneath it, behind an opaque `bg-black/30`. Measured on production
 * 2026-09-08 at 390px by intersecting the button's rect with every text run
 * and glyph in its own card (`artifacts-ux-1131/measure-corner.mjs`):
 *
 *   leaderboard  16/16 cards — all three confidence bars covered 100%
 *   heatmap       7/7  cards — ~21% of "Resolves <date>", i.e. the year
 *   variant A     0/6         — clean, and clean BY CONSTRUCTION
 *   variant B     0/6         — clean, and clean BY CONSTRUCTION
 *
 * The filed headline (a `● Live` pill rendering as `● L`) is the smaller half
 * of one mechanism: two elements claiming one corner, with the button winning
 * on `z-10`.
 *
 * ⚠️ WHAT THIS FILE CAN AND CANNOT PROVE. `jest.config.js` sets
 * `testEnvironment: 'node'`, and `renderToStaticMarkup` has no layout engine,
 * so NOTHING here measures an overlap. Only `measure-corner.mjs` against a
 * real browser does that, and it is the regression artifact of record. These
 * are two weaker but still useful claims:
 *
 *   1. `reserve is at least the button's own width` is a REAL invariant test —
 *      it reads `w-7` off the button's actual rendered markup and fails if
 *      either the pad shrinks or the button grows.
 *   2. The per-site tests prove the reserve is APPLIED at each of the five
 *      places, in both directions. A card with no `onDismiss` must not pay for
 *      a button it never draws — `FuturesCard` also renders on `/preferences`,
 *      in `ThemeBundleCard` and in `GroupedFeedRenderer` with no dismiss.
 *
 * Both directions matter: an absence-only guard passes on a card that renders
 * nothing at all, and a presence-only guard would not have caught the
 * over-reservation on the three non-dismissible surfaces.
 *
 * ── #4131: the corner's SECOND claimant ──────────────────────────────────────
 *
 * #3777 measured the ✕ and padded for it. It never added `TrendBadge` — also
 * absolute, also in that corner, 91px wide at `right-12` — to the sum, so a
 * card that is trending AND dismissible had the pill painted straight over the
 * date the pad had just uncovered. Measured on production 2026-09-08 at 390px
 * (discover/001, on #4131): pill left edge 139px from the card's right against
 * 36px reserved; the reader got "Resolves Se" and no date at all.
 *
 * The fix is a placement, not a bigger number: on the three TEXT cards the pill
 * joins the meta row (`TrendBadge inFlow`), so it takes layout space and the row
 * wraps. On the IMAGE cards (Variant A, Variant B, `EventCard`) it stays in the
 * corner, because there it floats over a photo or a gradient crest strip and
 * their top rows are left-aligned — the same reason #3777 found them clean.
 *
 * So the invariant these tests hold is: **the reserved corner has exactly one
 * occupant, the ✕.** A guard that only asserted "the pill is in flow" would be
 * satisfied by a card that stopped drawing the pill at all, so every claim below
 * carries its positive control.
 */

import { renderToStaticMarkup } from "react-dom/server";
import React from "react";

jest.mock("next/link", () => ({
  __esModule: true,
  default: ({ href, children }: { href: string; children: React.ReactNode }) => (
    <a href={href}>{children}</a>
  ),
}));

import { FuturesCard } from "../../components/discover/FuturesCard";
import { ComparisonCard } from "../../components/discover/ComparisonCard";
import { ConceptCard } from "../../components/discover/ConceptCard";
import { TournamentCard } from "../../components/discover/TournamentCard";
import { EventCard } from "../../components/discover/EventCard";
import {
  DismissBtn,
  TrendBadge,
  dismissCornerPad,
  dismissCornerBadge,
} from "../../components/discover/shared";
import type {
  FeedItem,
  FeedFuturesData,
  FeedConceptData,
  FeedTournamentData,
  FeedEventData,
} from "@/lib/types";

const DISMISS = () => {};

// ── markup helpers ───────────────────────────────────────────────────────────

const VOID_TAGS = new Set(["img", "br", "hr", "input", "path", "circle", "rect", "line", "polyline", "polygon", "meta", "source"]);

function classTokens(tag: string): string[] {
  const m = tag.match(/class="([^"]*)"/);
  return m ? m[1].split(/\s+/).filter(Boolean) : [];
}

/**
 * The `class` tokens of the element that ENCLOSES `marker`.
 *
 * Walks the markup keeping a tag stack, so the answer is the marker's real
 * parent. The obvious shortcut — "the last `<` before the marker" — is wrong
 * and silently so: the tag immediately before `Live` is the pulse `<span>`
 * sibling, and before the dismiss button's marker it is the `<svg>` child, so
 * that version read an empty class list and would have passed a `not.toContain`
 * assertion for entirely the wrong reason.
 *
 * Anchoring on a marker rather than asserting a whole class string also keeps
 * the test off the exact Tailwind ordering.
 */
function enclosingClasses(html: string, marker: string): string[] {
  return ancestorClasses(html, marker, 0);
}

/**
 * `up = 0` is the marker's own parent (`enclosingClasses`); `up = 1` is that
 * element's parent, and so on. #4131 needs the grandparent — the meta ROW the
 * pill now lives in — and asserting on the real tree beats matching a class
 * string that source-order changes would silently move.
 */
function ancestorClasses(html: string, marker: string, up: number): string[] {
  const at = html.indexOf(marker);
  if (at < 0) throw new Error(`marker not found in markup: ${marker}`);
  const stack: string[][] = [];
  const tagRe = /<(\/?)([a-zA-Z][a-zA-Z0-9-]*)([^>]*)>/g;
  let m: RegExpExecArray | null;
  while ((m = tagRe.exec(html)) !== null) {
    if (m.index >= at) break;
    const [full, slash, name, attrs] = m;
    if (slash) stack.pop();
    else if (!VOID_TAGS.has(name.toLowerCase()) && !attrs.trimEnd().endsWith("/")) {
      stack.push(classTokens(full));
    }
  }
  if (stack.length <= up) throw new Error(`marker has no ancestor ${up} levels up: ${marker}`);
  return stack[stack.length - 1 - up];
}

/** The `class` tokens of a fragment's ROOT element. */
function rootClasses(html: string): string[] {
  const m = html.match(/<[a-zA-Z][^>]*>/);
  if (!m) throw new Error("no root element in markup");
  return classTokens(m[0]);
}

/** Tailwind spacing scale → px, for the utilities this fix uses. */
function spacingPx(token: string): number {
  const m = token.match(/^(?:pr|w|right)-(\d+(?:\.\d+)?)$/);
  if (!m) throw new Error(`not a spacing utility: ${token}`);
  return parseFloat(m[1]) * 4;
}

// ── fixtures ─────────────────────────────────────────────────────────────────

function itemFor(data: FeedFuturesData): FeedItem {
  return { type: "futures", score: 90, reason: "", headline: "", data } as unknown as FeedItem;
}

function heatmapData(): FeedFuturesData {
  return {
    id: 77,
    name: "When will the Fed cut rates?",
    llm_sport_category: "economics",
    sport_name: "Economics",
    resolution_date: "2027-03-31T00:00:00Z",
    top_outcomes: [
      { id: 1, name: "Sep 2026", probability: 0.62, movement: null },
      { id: 2, name: "Dec 2026", probability: 0.24, movement: null },
      { id: 3, name: "2027 or later", probability: 0.14, movement: null },
    ],
    outcome_count: 3,
    confidence_tier: "moderate",
    discover_card: {
      suggested_format: "threshold_heatmap",
      threshold_points: [
        { label: "Sep 2026", probability: 0.62, value: 1 },
        { label: "Dec 2026", probability: 0.24, value: 2 },
        { label: "2027 or later", probability: 0.14, value: 3 },
      ],
    },
  } as unknown as FeedFuturesData;
}

function leaderboardData(): FeedFuturesData {
  const rows = [
    { label: "Chiefs", probability: 0.31, movement: null },
    { label: "Eagles", probability: 0.24, movement: null },
    { label: "Ravens", probability: 0.13, movement: null },
    { label: "49ers", probability: 0.09, movement: null },
  ];
  return {
    id: 78,
    name: "NFL Super Bowl Winner",
    llm_sport_category: "americanfootball_nfl",
    sport_name: "NFL",
    resolution_date: "2027-02-14T00:00:00Z",
    top_outcomes: rows.map((r, i) => ({ id: i + 1, name: r.label, probability: r.probability, movement: null })),
    outcome_count: rows.length,
    confidence_tier: "moderate",
    discover_card: {
      suggested_format: "outcome_distribution",
      distribution_outcomes: rows,
      remaining_outcome_count: 28,
    },
  } as unknown as FeedFuturesData;
}

function conceptData(status: "live" | "upcoming" | "completed", whatHit: boolean): FeedConceptData {
  return {
    id: 91,
    name: "US Open",
    slug: "us-open",
    status,
    marquee_whathit: whatHit,
    domain: "sports",
    leaders: [{ name: "Alcaraz", probability: 0.41 }],
  } as unknown as FeedConceptData;
}

function tournamentData(): FeedTournamentData {
  return {
    id: 92,
    name: "The Masters",
    marquee_whathit: true,
    leaders: [{ name: "Scheffler", probability: 0.22, movement: null }],
    start_date: null,
    commence_time: null,
    resolution_date: null,
  } as unknown as FeedTournamentData;
}

function eventData(): FeedEventData {
  return {
    id: 93,
    home_team: "Boston Red Sox",
    away_team: "New York Yankees",
    sport_key: "baseball_mlb",
    sport_label: "MLB",
    llm_sport_category: "baseball_mlb",
    status: "upcoming",
    commence_time: "2026-10-01T23:05:00Z",
    current_odds: { home_probability: 0.55, away_probability: 0.45 },
  } as unknown as FeedEventData;
}

function eventItem(data: FeedEventData): FeedItem {
  return { type: "event", score: 90, reason: "", headline: "", data } as unknown as FeedItem;
}

// ── 1. the invariant ─────────────────────────────────────────────────────────

describe("#3777 the reserved corner is at least the button that occupies it", () => {
  // Read the button's real geometry off its own markup, so this fails if
  // someone widens the button without widening what the rows reserve.
  const btnClasses = rootClasses(renderToStaticMarkup(<DismissBtn onDismiss={DISMISS} />));

  it("the button is still an absolute, out-of-flow, opaque corner control", () => {
    // If any of these stop being true the whole mechanism changes and the
    // reserve may no longer be the right fix — fail loudly rather than
    // silently keep padding for nothing.
    expect(btnClasses).toContain("absolute");
    expect(btnClasses).toContain("top-3");
    expect(btnClasses).toContain("right-3");
    expect(btnClasses).toContain("z-10");
    expect(btnClasses.some((c) => c.startsWith("bg-black/"))).toBe(true);
  });

  it("dismissCornerPad reserves at least the button's width", () => {
    const width = spacingPx(btnClasses.find((c) => /^w-\d/.test(c))!);
    const pad = spacingPx(dismissCornerPad(DISMISS));
    expect(width).toBe(28);
    expect(pad).toBeGreaterThanOrEqual(width);
  });

  it("dismissCornerBadge clears the button, and lands on TrendBadge's line", () => {
    const inset = spacingPx(btnClasses.find((c) => /^right-\d/.test(c))!);
    const width = spacingPx(btnClasses.find((c) => /^w-\d/.test(c))!);
    const badge = spacingPx(dismissCornerBadge(DISMISS));
    expect(badge).toBeGreaterThanOrEqual(inset + width);
    // The house line `TrendBadge` has always used, extended rather than forked.
    expect(dismissCornerBadge(DISMISS)).toBe("right-12");
  });

  it("reserves nothing when the card is not dismissible", () => {
    expect(dismissCornerPad(undefined)).toBe("");
    expect(dismissCornerBadge(undefined)).toBe("right-3");
  });
});

// ── 2. the five sites, both directions ───────────────────────────────────────

describe("#3777 in-flow header rows clear the dismiss corner", () => {
  it("heatmap: the reserve is on the row, and absent without onDismiss", () => {
    const data = heatmapData();
    const withBtn = renderToStaticMarkup(
      <FuturesCard item={itemFor(data)} data={data} liked={false} setLiked={() => {}} trending={false} onDismiss={DISMISS} />,
    );
    const without = renderToStaticMarkup(
      <FuturesCard item={itemFor(data)} data={data} liked={false} setLiked={() => {}} trending={false} />,
    );
    const pad = dismissCornerPad(DISMISS);
    expect(withBtn).toContain(`gap-1.5 mb-1 ${pad}`);
    expect(without).not.toContain(`gap-1.5 mb-1 ${pad}`);
    // Positive control: the row itself still renders in both, so the absence
    // above is a missing pad and not a missing card.
    expect(withBtn).toContain("Resolves Mar 31, 2027");
    expect(without).toContain("Resolves Mar 31, 2027");
    expect(without).not.toContain('aria-label="Less like this"');
  });

  it("leaderboard: the row carrying the confidence glyph reserves the corner", () => {
    const data = leaderboardData();
    const withBtn = renderToStaticMarkup(
      <FuturesCard item={itemFor(data)} data={data} liked={false} setLiked={() => {}} trending={false} onDismiss={DISMISS} />,
    );
    const without = renderToStaticMarkup(
      <FuturesCard item={itemFor(data)} data={data} liked={false} setLiked={() => {}} trending={false} />,
    );
    const pad = dismissCornerPad(DISMISS);
    expect(withBtn).toContain('data-card-format="leaderboard"');
    expect(withBtn).toContain(`items-center gap-1.5 ${pad}`);
    expect(without).not.toContain(`items-center gap-1.5 ${pad}`);
    // The glyph this fix exists to uncover is actually on the card.
    expect(withBtn).toContain('role="img"');
    expect(without).toContain('role="img"');
  });

  it("comparison: the row carrying 'Resolves …' reserves the corner", () => {
    const data = leaderboardData();
    const withBtn = renderToStaticMarkup(
      <ComparisonCard item={itemFor(data)} data={data} liked={false} setLiked={() => {}} trending={false} onDismiss={DISMISS} />,
    );
    const without = renderToStaticMarkup(
      <ComparisonCard item={itemFor(data)} data={data} liked={false} setLiked={() => {}} trending={false} />,
    );
    const pad = dismissCornerPad(DISMISS);
    expect(withBtn).toContain('data-card-format="comparison"');
    expect(withBtn).toContain(`gap-1.5 mb-1 ${pad}`);
    expect(without).not.toContain(`gap-1.5 mb-1 ${pad}`);
    expect(withBtn).toContain("Resolves Feb 14, 2027");
    expect(without).toContain("Resolves Feb 14, 2027");
  });
});

describe("#3777 corner badges step aside for the dismiss button", () => {
  it("concept: the Live pill is not under the button", () => {
    const data = conceptData("live", false);
    const withBtn = renderToStaticMarkup(
      <ConceptCard data={data} liked={false} setLiked={() => {}} onDismiss={DISMISS} />,
    );
    const without = renderToStaticMarkup(
      <ConceptCard data={data} liked={false} setLiked={() => {}} />,
    );
    expect(enclosingClasses(withBtn, "Live")).toContain(dismissCornerBadge(DISMISS));
    // Without a button the pill keeps the corner — no dead gap.
    expect(enclosingClasses(without, "Live")).toContain("right-3");
    expect(enclosingClasses(without, "Live")).not.toContain("right-12");
  });

  it("concept: the Final pill is not under the button", () => {
    const data = conceptData("completed", true);
    const withBtn = renderToStaticMarkup(
      <ConceptCard data={data} liked={false} setLiked={() => {}} onDismiss={DISMISS} />,
    );
    const without = renderToStaticMarkup(
      <ConceptCard data={data} liked={false} setLiked={() => {}} />,
    );
    expect(enclosingClasses(withBtn, "🏁 Final")).toContain(dismissCornerBadge(DISMISS));
    expect(enclosingClasses(without, "🏁 Final")).toContain("right-3");
  });

  it("tournament: the Final pill is not under the button", () => {
    const data = tournamentData();
    const withBtn = renderToStaticMarkup(
      <TournamentCard data={data} liked={false} setLiked={() => {}} onDismiss={DISMISS} />,
    );
    const without = renderToStaticMarkup(
      <TournamentCard data={data} liked={false} setLiked={() => {}} />,
    );
    expect(enclosingClasses(withBtn, "🏁 Final")).toContain(dismissCornerBadge(DISMISS));
    expect(enclosingClasses(without, "🏁 Final")).toContain("right-3");
  });
});

// ── 3. the surfaces that must NOT pay ────────────────────────────────────────

describe("#3777 non-dismissible surfaces reserve nothing", () => {
  it("a FuturesCard with no onDismiss renders no button and no pad", () => {
    for (const data of [heatmapData(), leaderboardData()]) {
      const html = renderToStaticMarkup(
        <FuturesCard item={itemFor(data)} data={data} liked={false} setLiked={() => {}} trending={false} />,
      );
      expect(html).not.toContain('aria-label="Less like this"');
      expect(html).not.toContain(" pr-9");
      // Positive control — the card rendered something.
      expect(html).toContain("<article");
    }
  });
});

// ── 4. #4131 — the corner has exactly one occupant ───────────────────────────

const PILL = "🔥 Trending";

describe("#4131 the trend pill has two placements and they cannot drift", () => {
  const corner = renderToStaticMarkup(<TrendBadge />);
  const flow = renderToStaticMarkup(<TrendBadge inFlow />);

  it("the corner placement is still the absolute overlay the image cards need", () => {
    const cls = rootClasses(corner);
    expect(cls).toContain("absolute");
    expect(cls).toContain("top-3");
    expect(cls).toContain("right-12");
    expect(cls).toContain("z-10");
    expect(corner).toContain('data-trend-placement="corner"');
    expect(corner).toContain(PILL);
  });

  it("the in-flow placement takes layout space and claims no corner", () => {
    const cls = rootClasses(flow);
    expect(cls).toContain("inline-flex");
    expect(cls).not.toContain("absolute");
    // The whole point: no inset utility at all, so it cannot be over anything.
    expect(cls.some((c) => /^(?:top|right|bottom|left)-/.test(c))).toBe(false);
    expect(flow).toContain('data-trend-placement="flow"');
    expect(flow).toContain(PILL);
  });

  it("both placements wear the same pill, so one cannot be restyled alone", () => {
    // Anchored on the look, not the layout — a shared constant is the fix, and
    // this fails the moment someone hand-edits one of the two class strings.
    for (const token of ["bg-orange-500/90", "text-[10px]", "rounded-full", "px-2", "py-0.5"]) {
      expect(rootClasses(corner)).toContain(token);
      expect(rootClasses(flow)).toContain(token);
    }
  });
});

describe("#4131 text cards put the pill in the meta row, never over the date", () => {
  /**
   * The claim, in one shape for all three: the pill renders, it renders INSIDE
   * the row that carries the dismiss reserve, and it renders BEFORE that row's
   * right-hand run. Before the fix the pill was a sibling of the card's padding
   * container, so its index was LOWER than the row's — restoring the absolute
   * badge fails `rowAt < pillAt`, and deleting the pill fails `toContain`.
   */
  function expectPillInRow(html: string, rowMarker: string, rightRun: string) {
    const pillAt = html.indexOf(PILL);
    const rowAt = html.indexOf(rowMarker);
    const rightAt = html.indexOf(rightRun);
    expect(pillAt).toBeGreaterThan(-1);
    expect(rowAt).toBeGreaterThan(-1);
    expect(rightAt).toBeGreaterThan(-1);
    expect(rowAt).toBeLessThan(pillAt);
    expect(pillAt).toBeLessThan(rightAt);
    expect(enclosingClasses(html, PILL)).toContain("inline-flex");
    // Nothing in this card sits on the badge line any more — the reserved
    // corner is the ✕'s alone, which is what `dismissCornerPad` is sized for.
    expect(html).not.toContain("right-12");
    // …and the ✕ is still there to justify the reserve.
    expect(html).toContain('aria-label="Less like this"');
  }

  it("heatmap", () => {
    const data = heatmapData();
    const html = renderToStaticMarkup(
      <FuturesCard item={itemFor(data)} data={data} liked={false} setLiked={() => {}} trending onDismiss={DISMISS} />,
    );
    expectPillInRow(html, `gap-1.5 mb-1 ${dismissCornerPad(DISMISS)}`, "Resolves Mar 31, 2027");
  });

  it("leaderboard", () => {
    const data = leaderboardData();
    const html = renderToStaticMarkup(
      <FuturesCard item={itemFor(data)} data={data} liked={false} setLiked={() => {}} trending onDismiss={DISMISS} />,
    );
    expect(html).toContain('data-card-format="leaderboard"');
    expectPillInRow(html, `items-center gap-1.5 ${dismissCornerPad(DISMISS)}`, "Resolves Feb 14, 2027");
  });

  it("comparison", () => {
    const data = leaderboardData();
    const html = renderToStaticMarkup(
      <ComparisonCard item={itemFor(data)} data={data} liked={false} setLiked={() => {}} trending onDismiss={DISMISS} />,
    );
    expect(html).toContain('data-card-format="comparison"');
    expectPillInRow(html, `gap-1.5 mb-1 ${dismissCornerPad(DISMISS)}`, "Resolves Feb 14, 2027");
  });

  it("the row that now holds the pill wraps, so the date moves down rather than being squeezed", () => {
    // Without `flex-wrap` the three runs share one line and the browser shrinks
    // them instead — the same information loss by another mechanism. Read off
    // the pill's real PARENT row, not off a class string in the source.
    const heat = heatmapData();
    const board = leaderboardData();
    const rows = [
      renderToStaticMarkup(
        <FuturesCard item={itemFor(heat)} data={heat} liked={false} setLiked={() => {}} trending onDismiss={DISMISS} />,
      ),
      renderToStaticMarkup(
        <FuturesCard item={itemFor(board)} data={board} liked={false} setLiked={() => {}} trending onDismiss={DISMISS} />,
      ),
      renderToStaticMarkup(
        <ComparisonCard item={itemFor(board)} data={board} liked={false} setLiked={() => {}} trending onDismiss={DISMISS} />,
      ),
    ];
    for (const html of rows) {
      const row = ancestorClasses(html, PILL, 1);
      expect(row).toContain("flex");
      expect(row).toContain("flex-wrap");
      expect(row).toContain(dismissCornerPad(DISMISS));
    }
  });

  it("no pill at all when the card is not trending, and the card still renders", () => {
    for (const [Card, data] of [
      [FuturesCard, heatmapData()],
      [FuturesCard, leaderboardData()],
      [ComparisonCard, leaderboardData()],
    ] as const) {
      const html = renderToStaticMarkup(
        <Card item={itemFor(data)} data={data} liked={false} setLiked={() => {}} trending={false} onDismiss={DISMISS} />,
      );
      expect(html).not.toContain(PILL);
      expect(html).not.toContain("data-trend-placement");
      expect(html).toContain("<article");
      expect(html).toContain("Resolves ");
    }
  });
});

describe("#4131 image cards keep the corner, because nothing of the reader's is there", () => {
  it("EventCard floats the pill over the crest strip", () => {
    const data = eventData();
    const html = renderToStaticMarkup(
      <EventCard item={eventItem(data)} data={data} liked={false} setLiked={() => {}} trending onDismiss={DISMISS} />,
    );
    expect(html).toContain('data-trend-placement="corner"');
    expect(enclosingClasses(html, PILL)).toContain("absolute");
    expect(enclosingClasses(html, PILL)).toContain("right-12");
    // Positive control: the strip the pill floats over is the card's own art,
    // and the matchup — the thing a reader must not lose — is below it.
    expect(html).toContain("Boston Red Sox");
  });

  it("EventCard draws no pill when it is not trending", () => {
    const data = eventData();
    const html = renderToStaticMarkup(
      <EventCard item={eventItem(data)} data={data} liked={false} setLiked={() => {}} trending={false} onDismiss={DISMISS} />,
    );
    expect(html).not.toContain(PILL);
    expect(html).toContain("Boston Red Sox");
  });
});
