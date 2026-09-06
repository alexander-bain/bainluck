/**
 * #3538 — a hub outcome row says which outcome it is, ON THE CARD.
 *
 * ═══ WHY THIS EXISTS ALONGSIDE THE PURE TESTS ═══
 *
 * `__tests__/lib/hubOutcomeLabel3538.test.ts` proves `outcomeRowLabel` computes
 * the right string from the right two inputs. It cannot prove the card PASSES
 * those two inputs. The defect being fixed is precisely a wiring one — the row
 * already had the outcome's name and the card already had its own, and they
 * were never introduced — so a green pure suite over an unwired renderer is the
 * exact failure this file has to rule out.
 *
 * ═══ WHAT A READER SAW ═══
 *
 * Production `/hub/tennis`, 390px, 2026-09-06:
 *
 *     US Open ATP: Karen Khachanov vs Learner Tien
 *       US Open ATP: Karen Khacha…   66%
 *       US Open ATP: Karen Khacha…   56%
 *       US Open ATP: Karen Khacha…   53%
 *       US Open ATP: Karen Khacha…   51%
 *
 * Four prices, four labels a reader cannot tell apart. 31 of 62 rows on the rail.
 *
 * ═══ 🔴 WHY THE ARM IS ABOUT THE VISIBLE PREFIX, NOT THE STRING ═══
 *
 * THE LOAD-BEARING PARAGRAPH, and it corrects the obvious first draft of this
 * file. `truncate` is CSS (`text-overflow: ellipsis`), not string surgery — so
 * on the PARENT the DOM already holds four fully distinct strings, and an arm
 * counting distinct rendered labels PASSES on the bug. It was written that way
 * first and proved nothing; it is kept below, correctly labelled a CONTROL.
 *
 * What the reader loses is distinctness in the part that FITS. At 390px the row
 * shows roughly the first two dozen characters and the rest becomes "…", and on
 * the parent those characters are `US Open ATP: Karen K` on all four rows. So
 * the arm that encodes the complaint compares the leading VISIBLE_PREFIX of
 * each label and requires one distinct value per row.
 *
 * "The row no longer contains the card's name" is not enough on its own either:
 * it is satisfied by a renderer that prints every row empty, or as "Outcome".
 * The prefix-distinctness arm and the never-empty CONTROL together close that.
 *
 * The mirror is pinned in the same payload rather than a separate one: an MMA
 * card whose rows are two fighters' names, rendered on the same rail in the same
 * markup, must come through byte-identical. A stripper that ate real outcome
 * names would pass every tennis arm here and fail that one.
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

// ── Verbatim production data, `/api/hub/tennis` and `/api/hub/mma`, 2026-09-06 ──

const TENNIS_CARD = "US Open ATP: Karen Khachanov vs Learner Tien";

/** The first four rows the card actually draws, in served order. */
const TENNIS_ROWS: Array<[string, number]> = [
  ["US Open ATP: Karen Khachanov vs Learner Tien Total Sets: O/U 3.5", 0.66],
  ["US Open ATP: Karen Khachanov vs Learner Tien Set 1 O/U 9.5", 0.555],
  ["US Open ATP: Karen Khachanov vs Learner Tien Game Spread +/-2.5", 0.525],
  ["US Open ATP: Karen Khachanov vs Learner Tien Match O/U 38.5", 0.51],
];

/** The real match-winner row on that same card — must survive untouched. */
const TENNIS_WINNER_ROW: [string, number] = ["Karen Khachanov", 0.385];

const MMA_CARD = "MMA: Loud vs Natividad";
const MMA_ROWS: Array<[string, number]> = [
  ["Christian Natividad", 0.52],
  ["Colton Loud", 0.48],
];

const market = (
  id: number,
  name: string,
  rows: Array<[string, number]>,
  source: string,
) => ({
  id,
  name,
  source,
  external_id: `X-${id}`,
  market_tier: 5,
  category: "game_prop",
  resolution_date: null,
  outcome_count: rows.length,
  top_outcomes: rows.map(([rowName, probability], i) => ({
    id: id * 100 + i,
    name: rowName,
    probability,
    opening_probability: 0.5,
    rank: i + 1,
    movement_24h: null,
    team_id: null,
  })),
  canonical_market_key: null,
  group_id: source === "polymarket" ? "polymarket:975445" : null,
  section: "matches",
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

const render = () => renderToStaticMarkup(React.createElement(CompetitionHubPage));

/** The rendered card for a market, as a markup slice starting at its name. */
function cardFor(markup: string, name: string): string {
  const at = markup.indexOf(name);
  expect(at).toBeGreaterThan(-1);
  const start = markup.lastIndexOf("<a ", at);
  const next = markup.indexOf("<a ", at);
  return markup.slice(start, next === -1 ? markup.length : next);
}

/**
 * The outcome labels a reader sees on a card, in order.
 *
 * Read off the row span's own class list, which predates this diff — not off
 * any attribute the fix adds, so the extractor works identically on the parent
 * and cannot be vacuously empty there.
 */
function outcomeLabelsIn(card: string): string[] {
  return [
    ...card.matchAll(
      /<span class="flex-1 min-w-0 text-\[13px\] text-text-secondary truncate">([^<]*)<\/span>/g,
    ),
  ].map((m) => m[1]);
}

/**
 * How much of a row a reader actually sees before CSS ellipsis takes over, at
 * the 390px width this was measured at. Deliberately conservative — the real
 * cut is font-dependent, and a SMALLER number is the stricter test.
 */
const VISIBLE_PREFIX = 20;

describe("#3538: four prices stop sitting under four identical labels", () => {
  it("🔴 the part of each row that FITS ON SCREEN is different on every row", () => {
    // The arm that encodes the reader's complaint. On the parent all four rows
    // begin `US Open ATP: Karen K`, so this collapses to 1 distinct value.
    currentPayload = payloadWith([market(1, TENNIS_CARD, TENNIS_ROWS, "polymarket")]);

    const labels = outcomeLabelsIn(cardFor(render(), TENNIS_CARD));
    const visible = labels.map((l) => l.slice(0, VISIBLE_PREFIX));

    expect(labels).toHaveLength(4);
    expect(new Set(visible).size).toBe(4);
  });

  it("CONTROL (passes on both arms) — the DOM holds four distinct strings", () => {
    // It always did: `truncate` is CSS, so the full names were in the markup on
    // the parent too. Kept as a control precisely because it is NOT evidence of
    // the fix, and labelling it otherwise would be the dead-control mistake.
    currentPayload = payloadWith([market(1, TENNIS_CARD, TENNIS_ROWS, "polymarket")]);

    const labels = outcomeLabelsIn(cardFor(render(), TENNIS_CARD));

    expect(new Set(labels).size).toBe(labels.length);
  });

  it("and each says which market it is", () => {
    currentPayload = payloadWith([market(1, TENNIS_CARD, TENNIS_ROWS, "polymarket")]);

    expect(outcomeLabelsIn(cardFor(render(), TENNIS_CARD))).toEqual([
      "Total Sets: O/U 3.5",
      "Set 1 O/U 9.5",
      "Game Spread +/-2.5",
      "Match O/U 38.5",
    ]);
  });

  it("no row still opens with the card's own headline", () => {
    currentPayload = payloadWith([market(1, TENNIS_CARD, TENNIS_ROWS, "polymarket")]);

    for (const label of outcomeLabelsIn(cardFor(render(), TENNIS_CARD))) {
      expect(label.startsWith("US Open ATP")).toBe(false);
    }
  });

  it("the card's headline itself is untouched — only the rows change", () => {
    currentPayload = payloadWith([market(1, TENNIS_CARD, TENNIS_ROWS, "polymarket")]);

    expect(cardFor(render(), TENNIS_CARD)).toContain(TENNIS_CARD);
  });
});

describe("#3538: the mirror — a real outcome name is never eaten", () => {
  it("🔴 the match-winner row survives on the very card whose headline contains it", () => {
    currentPayload = payloadWith([
      market(1, TENNIS_CARD, [TENNIS_WINNER_ROW, ...TENNIS_ROWS.slice(0, 3)], "polymarket"),
    ]);

    const labels = outcomeLabelsIn(cardFor(render(), TENNIS_CARD));

    expect(labels[0]).toBe("Karen Khachanov");
    expect(labels.every((l) => l.trim().length > 0)).toBe(true);
  });

  it("CONTROL (passes on both arms) — an MMA card on the same rail is byte-identical", () => {
    currentPayload = payloadWith([
      market(1, TENNIS_CARD, TENNIS_ROWS, "polymarket"),
      market(2, MMA_CARD, MMA_ROWS, "kalshi"),
    ]);

    expect(outcomeLabelsIn(cardFor(render(), MMA_CARD))).toEqual([
      "Christian Natividad",
      "Colton Loud",
    ]);
  });

  it("CONTROL (passes on both arms) — every rendered row is non-empty", () => {
    // The one failure this fix must be incapable of producing, asserted over a
    // mixed rail rather than a single card.
    currentPayload = payloadWith([
      market(1, TENNIS_CARD, [...TENNIS_ROWS, TENNIS_WINNER_ROW], "polymarket"),
      market(2, MMA_CARD, MMA_ROWS, "kalshi"),
    ]);
    const markup = render();

    const all = [
      ...outcomeLabelsIn(cardFor(markup, TENNIS_CARD)),
      ...outcomeLabelsIn(cardFor(markup, MMA_CARD)),
    ];

    expect(all.length).toBeGreaterThan(0);
    for (const label of all) expect(label.trim()).not.toBe("");
  });
});
