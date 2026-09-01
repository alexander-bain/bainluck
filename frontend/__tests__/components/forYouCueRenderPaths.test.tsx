/**
 * UX-P248 round two — THE "FOR YOU" CUE ON EVERY CARD THAT CAN CARRY IT.
 *
 * ═══ WHY THIS FILE EXISTS: CERT-678, STRIKE ONE, VERBATIM ═══
 *
 *   "The cue appears only on EventCard and generic FuturesCard Variant A.
 *    Threshold, leaderboard, Variant B, and ComparisonCard paths remain
 *    silently personalized with no explanation. Helper tests pass 33/33 and
 *    build/typecheck/identity/merge hygiene pass, but THERE IS NO RENDER-PATH
 *    GUARD."
 *
 * The cert is right, and the shape of the miss is a named one:
 * `reference_plant_must_hit_the_render`. `forYouCue.test.tsx` proves the
 * DECISION is correct — which reasons qualify, which are penalties, what the
 * chip prints when handed a cue. It cannot see whether any card calls it. It
 * passed 33/33 on a build where four of the six card paths never rendered the
 * chip at all, and it would pass again tomorrow if someone deleted every call
 * site. A library test stays green the day the component stops printing the
 * feature.
 *
 * So this file renders. Two halves, and NEITHER substitutes for the other:
 *
 *   PART 1 — BEHAVIOUR. Every card path is rendered for real, three times:
 *     boosted (cue must appear), downranked (cue must NOT appear — the
 *     original defect), anonymous (cue must not appear). Each case also
 *     asserts the marker of the path it MEANT to render, because a fixture
 *     that quietly falls through to Variant A would otherwise let a
 *     "leaderboard covered" test pass while the leaderboard stayed dark.
 *
 *   PART 2 — ENUMERATION FROM SOURCE. Part 1 can only test the paths whose
 *     existence the author already knew about, and not knowing is exactly what
 *     CERT-678 blocked. So the card paths are DERIVED from the source: every
 *     top-level component under `components/discover/` that accepts a feed
 *     `item`, every `<article>` root inside those components, every component
 *     that `DiscoverCard`/the Discover page hands an item to, and — across the
 *     stack — every feed item type the backend marks `personalized`. A new
 *     variant, a new card, or a newly personalizable item type turns this red
 *     without anybody remembering to come back here.
 *
 * ⚠️ EVERY SCAN IN PART 2 RAISES WHEN IT CANNOT PARSE. A source scan whose
 * regex stops matching reports "0 uncovered paths" and reads exactly like
 * success (`reference_source_scan_guard_must_raise_on_what_it_cannot_parse`),
 * so each scan first asserts it found the structures it knows are there.
 */

import React from "react";
import { renderToStaticMarkup } from "react-dom/server";
import fs from "node:fs";
import path from "node:path";

jest.mock("next/link", () => {
  const ReactLib = require("react");
  return {
    __esModule: true,
    default: ({ href, children, ...props }: { href: string; children: React.ReactNode }) =>
      ReactLib.createElement("a", { href, ...props }, children),
  };
});

jest.mock("@/components/Analytics", () => ({
  useAnalyticsContext: () => ({ track: () => {} }),
}));

import { EventCard } from "@/components/discover/EventCard";
import { FuturesCard, FuturesCompactRow } from "@/components/discover/FuturesCard";
import { ComparisonCard } from "@/components/discover/ComparisonCard";
import { GuessCard } from "@/components/discover/GuessCard";
import type { FeedItem, FeedEventData, FeedFuturesData } from "@/lib/types";

// ─────────────────────────────────────────────────────────────────────────────
// The three reader states every path is rendered in.
// ─────────────────────────────────────────────────────────────────────────────

/** The label `your_team:0.35` must produce, from `forYouCue.ts`'s vocabulary. */
const BOOSTED_LABEL = "One of your teams";
const CUE_TESTID = 'data-testid="for-you-cue"';

/** A real net uprank with a nameable reason — the cue is TRUE here. */
const BOOSTED = {
  personalized: true,
  multiplier: 1.35,
  personalization_reasons: ["your_team:0.35"],
};

/**
 * 🔴 THE ORIGINAL DEFECT, carried onto every path.
 *
 * `personalized: true` (it is — `is_personalized` is `bool(reasons)`) and a
 * REAL `your_team` boost, outweighed by a suppression the reader themselves
 * asked for. The naive `{item.personalized && <ForYou/>}` prints the cue here,
 * and so does a vocabulary-only check. The card finished LOWER than it started.
 */
const DOWNRANKED = {
  personalized: true,
  multiplier: 0.9,
  personalization_reasons: ["your_team:0.35", "sport_suppress:-0.50"],
};

/** An anonymous reader: nothing was reordered, so there is nothing to say. */
const ANON = {};

type Personalization = Record<string, unknown>;

/**
 * `GuessCard` picks its threshold with `Math.random()` (`generateThreshold` in
 * `discover/utils.ts`), so two renders of the same item differ by design. The
 * "arms are not accidentally identical" oracle below compares whole markup and
 * would be meaningless — it would report a difference for every item, boosted
 * or not. Pinned for every path so the comparison means what it says.
 */
let randomSpy: jest.SpyInstance;
beforeEach(() => {
  randomSpy = jest.spyOn(Math, "random").mockReturnValue(0.42);
});
afterEach(() => {
  randomSpy.mockRestore();
});

// ─────────────────────────────────────────────────────────────────────────────
// Fixtures. One per render path, each pinned to the marker that proves the
// branch was actually taken.
// ─────────────────────────────────────────────────────────────────────────────

function eventData(): FeedEventData {
  return {
    id: 15200290,
    external_id: "evt-15200290",
    sport: "americanfootball_nfl",
    sport_name: "NFL",
    home_team: "Denver Broncos",
    away_team: "Green Bay Packers",
    commence_time: "2030-01-01T12:00:00.000Z",
    status: "scheduled",
    home_score: null,
    away_score: null,
  } as unknown as FeedEventData;
}

/**
 * The A/B split is `hash(session + market id) % 2`, and `renderToStaticMarkup`
 * runs the `useState` initializer with the hydration-stable "anon" seed and
 * never the effect — so the variant is a pure function of the id here, exactly
 * as it is for a logged-out reader. Mirrored from `FuturesCard.tsx`, the same
 * way `futuresCardVariantBGlyph.test.tsx` does it.
 */
function abHash(seed: string): number {
  return Array.from(seed).reduce((h, c) => ((h << 5) - h + c.charCodeAt(0)) | 0, 0);
}
function isVariantB(id: number): boolean {
  return Math.abs(abHash(`anon_${id}`)) % 2 === 0;
}
function idForVariant(wantB: boolean): number {
  for (let id = 1; id < 100_000; id++) {
    if (isVariantB(id) === wantB) return id;
  }
  throw new Error(`no id found for variant ${wantB ? "B" : "A"}`);
}

function plainFuturesData(id: number): FeedFuturesData {
  return {
    id,
    name: "Will the Broncos win the AFC West?",
    llm_sport_category: "americanfootball_nfl",
    sport_name: "NFL",
    resolution_date: "2027-01-10T00:00:00Z",
    source: "kalshi",
    top_outcomes: [{ id: 1, name: "Yes", probability: 0.58, movement: 2.1 }],
    outcome_count: 2,
    volume_24h: 1_400_000,
    confidence_tier: "high",
  } as unknown as FeedFuturesData;
}

function heatmapFuturesData(): FeedFuturesData {
  return {
    ...plainFuturesData(77),
    name: "When will the Fed cut rates?",
    top_outcomes: [
      { id: 1, name: "Sep 2026", probability: 0.62, movement: null },
      { id: 2, name: "Dec 2026", probability: 0.24, movement: null },
      { id: 3, name: "2027 or later", probability: 0.14, movement: null },
    ],
    outcome_count: 3,
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

const FOUR_OUTCOMES = [
  { id: 1, name: "No change", probability: 0.56, movement: null },
  { id: 2, name: "Cut 25bp", probability: 0.24, movement: null },
  { id: 3, name: "Cut 50bp", probability: 0.13, movement: null },
  { id: 4, name: "Hike", probability: 0.07, movement: null },
];

/**
 * `top_outcomes` keys the option on `name`; `discover_card.distribution_outcomes`
 * keys it on `label`. Two shapes, one concept — and the leaderboard branch
 * throws on the wrong one rather than falling through, which is the reason the
 * `marker` assertion is not the only thing keeping these fixtures honest.
 */
const FOUR_DISTRIBUTION_ROWS = FOUR_OUTCOMES.map((o) => ({
  label: o.name,
  probability: o.probability,
  movement: o.movement,
}));

function leaderboardFuturesData(): FeedFuturesData {
  return {
    ...plainFuturesData(88),
    name: "What does the Fed do in September?",
    top_outcomes: FOUR_OUTCOMES,
    outcome_count: 4,
    discover_card: {
      suggested_format: "outcome_distribution",
      distribution_outcomes: FOUR_DISTRIBUTION_ROWS,
      remaining_outcome_count: 0,
    },
  } as unknown as FeedFuturesData;
}

function comparisonFuturesData(): FeedFuturesData {
  return {
    ...plainFuturesData(99),
    name: "Which studio takes Best Picture?",
    top_outcomes: FOUR_OUTCOMES,
    outcome_count: 6,
    discover_card: {
      suggested_format: "outcome_distribution",
      distribution_outcomes: FOUR_DISTRIBUTION_ROWS,
      remaining_outcome_count: 2,
    },
  } as unknown as FeedFuturesData;
}

function futuresItem(data: FeedFuturesData, p: Personalization): FeedItem {
  return { type: "futures", score: 90, reason: "", headline: "", data, ...p } as unknown as FeedItem;
}
function eventItem(data: FeedEventData, p: Personalization): FeedItem {
  return { type: "event", score: 90, reason: "", headline: "", data, ...p } as unknown as FeedItem;
}

/**
 * The render paths, each with the marker that proves the branch was taken.
 *
 * `marker` is not decoration. Without it a fixture that stops satisfying its
 * branch predicate — an outcome count that drops below four, a
 * `suggested_format` the backend renames — falls through to Variant A, finds
 * the chip Variant A has always had, and reports the leaderboard covered.
 */
const RENDER_PATHS: {
  name: string;
  marker: string;
  render: (p: Personalization) => string;
}[] = [
  {
    name: "EventCard (game card)",
    marker: 'data-card-format="event"',
    render: (p) => {
      const data = eventData();
      return renderToStaticMarkup(
        <EventCard item={eventItem(data, p)} data={data} liked={false} setLiked={() => {}} trending={false} />,
      );
    },
  },
  {
    name: "FuturesCard — threshold heatmap",
    marker: 'data-card-format="heatmap"',
    render: (p) => {
      const data = heatmapFuturesData();
      return renderToStaticMarkup(
        <FuturesCard item={futuresItem(data, p)} data={data} liked={false} setLiked={() => {}} trending={false} />,
      );
    },
  },
  {
    name: "FuturesCard — outcome-distribution leaderboard",
    marker: 'data-card-format="leaderboard"',
    render: (p) => {
      const data = leaderboardFuturesData();
      return renderToStaticMarkup(
        <FuturesCard item={futuresItem(data, p)} data={data} liked={false} setLiked={() => {}} trending={false} />,
      );
    },
  },
  {
    name: "FuturesCard — Variant B (data-pure)",
    marker: 'data-card-variant="B"',
    render: (p) => {
      const data = plainFuturesData(idForVariant(true));
      return renderToStaticMarkup(
        <FuturesCard item={futuresItem(data, p)} data={data} liked={false} setLiked={() => {}} trending={false} />,
      );
    },
  },
  {
    name: "FuturesCard — Variant A (image-led)",
    marker: 'data-card-variant="A"',
    render: (p) => {
      const data = plainFuturesData(idForVariant(false));
      return renderToStaticMarkup(
        <FuturesCard item={futuresItem(data, p)} data={data} liked={false} setLiked={() => {}} trending={false} />,
      );
    },
  },
  {
    name: "ComparisonCard",
    marker: 'data-card-format="comparison"',
    render: (p) => {
      const data = comparisonFuturesData();
      return renderToStaticMarkup(
        <ComparisonCard item={futuresItem(data, p)} data={data} liked={false} setLiked={() => {}} trending={false} />,
      );
    },
  },
  {
    name: "GuessCard (the guess slot is a real feed position)",
    marker: "data-guess-card",
    render: (p) => {
      const data = plainFuturesData(4242);
      return renderToStaticMarkup(<GuessCard item={futuresItem(data, p)} />);
    },
  },
  {
    name: "FuturesCompactRow (group + theme-bundle rows)",
    // Not a card: it has no <article>. Asserting that IS the marker — it proves
    // the row rendered rather than some card standing in for it.
    marker: "<a href=",
    render: (p) => {
      const data = plainFuturesData(5150);
      return renderToStaticMarkup(<FuturesCompactRow item={futuresItem(data, p)} data={data} />);
    },
  },
];

// ─────────────────────────────────────────────────────────────────────────────
// PART 1 — BEHAVIOUR: the cue is on the page, on every path, in both directions.
// ─────────────────────────────────────────────────────────────────────────────

describe("PART 1 — every card path renders the cue for a boosted reader", () => {
  it.each(RENDER_PATHS.map((p) => [p.name, p] as const))("%s", (_name, p) => {
    const html = p.render(BOOSTED);
    // The fixture really took the branch it claims (gotcha: a guard that races
    // passes under both arms).
    expect(html).toContain(p.marker);
    expect(html).toContain(CUE_TESTID);
    expect(html).toContain('data-for-you-reason="your_team"');
    expect(html).toContain(BOOSTED_LABEL);
  });
});

describe("🔴 PART 1 — no path labels a DOWNRANKED card 'for you'", () => {
  it.each(RENDER_PATHS.map((p) => [p.name, p] as const))("%s", (_name, p) => {
    const html = p.render(DOWNRANKED);
    expect(html).toContain(p.marker);
    expect(html).not.toContain(CUE_TESTID);
    expect(html).not.toContain(BOOSTED_LABEL);
  });
});

describe("PART 1 — no path shows a cue to an anonymous reader", () => {
  it.each(RENDER_PATHS.map((p) => [p.name, p] as const))("%s", (_name, p) => {
    const html = p.render(ANON);
    expect(html).toContain(p.marker);
    expect(html).not.toContain(CUE_TESTID);
  });
});

describe("PART 1 — the three arms are not accidentally identical", () => {
  // If a path's fixture were broken such that all three arms produced the same
  // markup, the two negative suites above would pass for the wrong reason.
  it.each(RENDER_PATHS.map((p) => [p.name, p] as const))("%s differs when boosted", (_name, p) => {
    expect(p.render(BOOSTED)).not.toBe(p.render(DOWNRANKED));
    expect(p.render(DOWNRANKED)).toBe(p.render(ANON));
  });
});

// ─────────────────────────────────────────────────────────────────────────────
// PART 2 — ENUMERATION FROM SOURCE.
// ─────────────────────────────────────────────────────────────────────────────

const REPO = path.join(__dirname, "..", "..", "..");
const DISCOVER_DIR = path.join(REPO, "frontend", "components", "discover");

function readTsx(dir: string): { file: string; src: string }[] {
  const out: { file: string; src: string }[] = [];
  for (const entry of fs.readdirSync(dir, { withFileTypes: true })) {
    const full = path.join(dir, entry.name);
    if (entry.isDirectory()) out.push(...readTsx(full));
    else if (entry.name.endsWith(".tsx")) out.push({ file: path.relative(REPO, full), src: fs.readFileSync(full, "utf8") });
  }
  return out;
}

type Chunk = { file: string; name: string; body: string };

/**
 * Blank out comments, preserving offsets.
 *
 * Both of this helper's rules were forced by this suite failing, and both are
 * worth keeping as prose because both are ways a source scan lies quietly.
 *
 *  1. The `<article>` scan matched `<article>` inside PROSE. `FuturesCard.tsx`
 *     has a comment reading "the card's accessible name is on the <article>",
 *     which the naive scan read as an extra card root — starting mid-comment,
 *     ending at the real Variant A root, containing no chip.
 *
 *  2. 🔴 LINE COMMENTS MUST BE BLANKED FIRST. `FuturesCard.tsx` line 360 has a
 *     `//` comment containing the literal `/discover/*`. Running the block rule
 *     first, that `/*` opened a phantom comment that ran 110 lines to the next
 *     real `*​/` and SWALLOWED Variant B's entire `<article>` root — the scan
 *     then reported three roots where there are four, and Variant B, one of the
 *     four paths CERT-678 blocked on, silently left the guard's coverage. A
 *     scan that under-counts reads exactly like a codebase with less to check.
 *
 * The `articleRoots` cross-check below exists because neither of those was
 * caught by reasoning about the regex.
 */
function blankComments(src: string): string {
  const blank = (m: string) => m.replace(/[^\n]/g, " ");
  return src.replace(/^[ \t]*\/\/.*$/gm, blank).replace(/\/\*[\s\S]*?\*\//g, blank);
}

/**
 * The `<article>` roots of a component, with an INDEPENDENT oracle.
 *
 * A real JSX root opens its own line; a prose mention sits mid-sentence. That
 * is a different signal from "is it inside a comment", so the two disagreeing
 * means the comment blanking mis-parsed — and this raises instead of returning
 * a plausible smaller number.
 */
function articleRoots(body: string): number[] {
  const code = blankComments(body);
  const found = [...code.matchAll(/<article[\s>]/g)].map((m) => m.index as number);
  const lineStart = [...body.matchAll(/^[ \t]*<article[\s>]/gm)].length;
  if (found.length !== lineStart) {
    throw new Error(
      `<article> scan disagrees with itself: ${found.length} outside comments vs ` +
        `${lineStart} at line start. The comment blanking mis-parsed this source; ` +
        `fix the scan rather than trusting either number.`,
    );
  }
  return found;
}

/**
 * Split a module into its top-level `function` declarations.
 *
 * Deliberately per-COMPONENT and not per-FILE. A file-level "does this source
 * contain `<ForYouChip`" check is exactly the guard CERT-678 would have let
 * through: `FuturesCard.tsx` contained one chip and had four card paths
 * (`reference_containment_guard_satisfied_by_sibling_call_sites`).
 */
function topLevelFunctions(file: string, src: string): Chunk[] {
  const re = /^(?:export\s+)?(?:default\s+)?function\s+([A-Za-z0-9_]+)\s*\(/gm;
  const marks = [...src.matchAll(re)].map((m) => ({ name: m[1], start: m.index as number }));
  return marks.map((m, i) => ({
    file,
    name: m.name,
    body: src.slice(m.start, i + 1 < marks.length ? marks[i + 1].start : src.length),
  }));
}

/** The destructured prop names of a chunk, or null when the shape is unparsed. */
function destructuredProps(body: string): string[] | null {
  const m = /^(?:export\s+)?(?:default\s+)?function\s+\w+\s*\(\s*\{([\s\S]*?)\}\s*:/.exec(body);
  if (!m) return null;
  return m[1].split(",").map((s) => s.trim().split(/[:=]/)[0].trim()).filter(Boolean);
}

const DISCOVER_SOURCES = readTsx(DISCOVER_DIR);
const DISCOVER_CHUNKS = DISCOVER_SOURCES.flatMap(({ file, src }) => topLevelFunctions(file, src));

describe("PART 2 — the scan can actually parse what it is scanning", () => {
  it("found the discover component sources", () => {
    expect(DISCOVER_SOURCES.length).toBeGreaterThanOrEqual(15);
    expect(DISCOVER_SOURCES.map((s) => path.basename(s.file))).toEqual(
      expect.arrayContaining(["EventCard.tsx", "FuturesCard.tsx", "ComparisonCard.tsx", "GuessCard.tsx", "shared.tsx"]),
    );
  });

  it("split them into top-level components", () => {
    expect(DISCOVER_CHUNKS.length).toBeGreaterThanOrEqual(20);
    expect(DISCOVER_CHUNKS.map((c) => c.name)).toEqual(
      expect.arrayContaining(["EventCard", "FuturesCard", "FuturesCompactRow", "ComparisonCard", "GuessCard", "ForYouChip"]),
    );
  });

  it("`<ForYouChip` is a real component and not a string nobody defines", () => {
    const chip = DISCOVER_CHUNKS.find((c) => c.name === "ForYouChip");
    expect(chip).toBeDefined();
    expect(chip!.file.endsWith("shared.tsx")).toBe(true);
    expect(chip!.body).toContain("data-testid=\"for-you-cue\"");
  });

  it("every chunk's props parsed — an unreadable signature is a RED, not a skip", () => {
    const unparsed = DISCOVER_CHUNKS.filter((c) => destructuredProps(c.body) === null && /\bitem\b/.test(c.body.slice(0, c.body.indexOf("{", c.body.indexOf("(")) + 400)));
    // A helper with no props at all is fine; one that mentions `item` in its
    // signature and cannot be parsed is the case that must never pass quietly.
    expect(unparsed.map((c) => `${c.file}:${c.name}`)).toEqual([]);
  });
});

/** Every discover component that receives a feed `item` must be able to explain itself. */
const ITEM_TAKING = DISCOVER_CHUNKS.filter((c) => (destructuredProps(c.body) ?? []).includes("item"));

describe("PART 2 — every component that takes a feed item renders the cue", () => {
  it("the set of item-taking components is the one we think it is", () => {
    // Not a cap on the set — a NEW item-taking component is covered by the
    // assertion below and does not need to be listed here. This pins the
    // known ones so a rename cannot empty the set and turn the next test
    // vacuous (`reference_zero_yield_sweep_needs_a_known_hit_control`).
    expect(ITEM_TAKING.map((c) => c.name).sort()).toEqual(
      expect.arrayContaining(["ComparisonCard", "EventCard", "FuturesCard", "FuturesCompactRow", "GuessCard"]),
    );
  });

  it.each(ITEM_TAKING.map((c) => [`${c.file}:${c.name}`, c] as const))("%s", (_label, chunk) => {
    expect(chunk.body).toContain("<ForYouChip");
  });
});

describe("🔴 PART 2 — every <article> root inside those components carries the cue", () => {
  /**
   * THE ARM THAT WOULD HAVE CAUGHT CERT-678.
   *
   * `FuturesCard` is ONE component with FOUR `<article>` roots, so
   * per-component coverage is not enough: the previous build satisfied
   * "FuturesCard renders the chip" with a chip only Variant A ever reached.
   * Each `<article>` is one card the reader can be looking at, so each one is
   * checked on its own, from its opening tag to the next root or end of
   * component.
   */
  const articleBlocks = ITEM_TAKING.flatMap((chunk) => {
    const code = blankComments(chunk.body);
    const starts = articleRoots(chunk.body);
    return starts.map((start, i) => ({
      label: `${chunk.file}:${chunk.name} <article> #${i + 1}`,
      block: code.slice(start, i + 1 < starts.length ? starts[i + 1] : code.length),
    }));
  });

  it("found the article roots (the scan is not vacuous)", () => {
    // 4 in FuturesCard + 1 EventCard + 1 ComparisonCard. GuessCard and
    // FuturesCompactRow root on a <div>/<a> and are covered by the
    // per-component arm above.
    expect(articleBlocks.length).toBeGreaterThanOrEqual(6);
    expect(articleBlocks.filter((b) => b.label.includes("FuturesCard.tsx:FuturesCard")).length).toBe(4);
  });

  it("blanking comments did not eat the code it was protecting", () => {
    // The strip runs over every scanned body; if it over-matched it would
    // delete real JSX and every assertion below would pass on nothing.
    const futures = ITEM_TAKING.find((c) => c.name === "FuturesCard")!;
    const code = blankComments(futures.body);
    expect(code.split("<ForYouChip").length - 1).toBe(4);
    expect(code).toContain('data-card-variant="A"');
    expect(code).toContain('data-card-format="leaderboard"');
    // ...and it really did remove the prose that broke the first run.
    expect(futures.body).toContain("accessible name is on the <article>");
    expect(code).not.toContain("accessible name is on the <article>");
  });

  it.each(articleBlocks.map((b) => [b.label, b] as const))("%s", (_label, b) => {
    expect(b.block).toContain("<ForYouChip");
  });
});

describe("PART 2 — nothing is handed a feed item by a component we have not covered", () => {
  /**
   * The dispatch side. `DiscoverCard` chooses between `EventCard`,
   * `ComparisonCard` and `FuturesCard` for one item, and `app/discover/page.tsx`
   * substitutes `GuessCard` for a whole feed slot — the path neither the
   * original ship nor the cert block named. Reading the call sites means a
   * fifth destination cannot be added without this turning red.
   */
  const CALL_SITE_FILES = [
    path.join(REPO, "frontend", "components", "DiscoverCard.tsx"),
    path.join(REPO, "frontend", "app", "discover", "page.tsx"),
    path.join(DISCOVER_DIR, "ThemeBundleCard.tsx"),
    path.join(DISCOVER_DIR, "GroupCard.tsx"),
  ];

  function componentsGivenAnItem(raw: string): string[] {
    const src = blankComments(raw);
    const found: string[] = [];
    for (const m of src.matchAll(/\bitem=\{/g)) {
      const before = src.slice(0, m.index as number);
      const open = before.lastIndexOf("<");
      if (open < 0) continue;
      const tagSoFar = before.slice(open);
      // A `>` in between means the `<` belonged to an earlier, closed tag —
      // refuse to guess rather than attribute the prop to the wrong component.
      if (tagSoFar.includes(">")) continue;
      const name = /^<([A-Z]\w*)/.exec(tagSoFar);
      if (name) found.push(name[1]);
    }
    return [...new Set(found)];
  }

  const destinations = new Set<string>();
  /**
   * A destination may be a LEAF (it draws the card, so it must draw the cue) or
   * a FORWARDER defined in one of these same files, which just passes the item
   * along — `DiscoverCard`'s own inner `SingleCard` is one. A forwarder is
   * covered transitively, because this scan already collected ITS `item={...}`
   * call sites from the same source. What a forwarder may not be is a dead end:
   * it has to hand the item to somebody.
   */
  const localFunctions = new Map<string, string>();
  for (const file of CALL_SITE_FILES) {
    expect(fs.existsSync(file)).toBe(true);
    const src = fs.readFileSync(file, "utf8");
    componentsGivenAnItem(src).forEach((n) => destinations.add(n));
    for (const chunk of topLevelFunctions(path.relative(REPO, file), src)) {
      localFunctions.set(chunk.name, chunk.body);
    }
  }

  it("the call-site scan found destinations (not vacuous)", () => {
    expect([...destinations].sort()).toEqual(
      expect.arrayContaining(["ComparisonCard", "EventCard", "FuturesCard", "FuturesCompactRow", "GuessCard"]),
    );
  });

  it.each([...destinations].sort().map((n) => [n] as const))(
    "%s either draws the cue or forwards the item to something that does",
    (name) => {
      const leaf = DISCOVER_CHUNKS.find((c) => c.name === name);
      if (leaf) {
        expect(leaf.body).toContain("<ForYouChip");
        expect(RENDER_PATHS.some((p) => p.name.includes(name))).toBe(true);
        return;
      }
      // Not a discover card component — the only other thing it is allowed to
      // be is a forwarder declared in a file this scan already read.
      const forwarder = localFunctions.get(name);
      expect(forwarder).toBeDefined();
      expect(blankComments(forwarder!)).toMatch(/\bitem=\{/);
    },
  );
});

describe("🔴 PART 2 — cross-stack: the backend cannot personalize a type we do not cover", () => {
  /**
   * `personalized`, `multiplier` and `personalization_reasons` are attached
   * per ITEM in `routes/feed.py`. Today only `event` and `futures` items get
   * them, which is why `TournamentCard`, `ConceptCard` and the bundle wrappers
   * are correctly silent — they are not personalized, so there is nothing true
   * to say on them. The day that changes, this goes red and names the type.
   */
  const feedSrc = fs.readFileSync(path.join(REPO, "backend", "app", "routes", "feed.py"), "utf8");

  it("the source really is the feed route (not vacuous)", () => {
    expect(feedSrc).toContain("compute_futures_multiplier");
    expect(feedSrc).toContain("compute_event_multiplier");
  });

  const sites = [...feedSrc.matchAll(/item\["personalized"\]\s*=\s*True/g)];

  it("found the per-item attachment sites", () => {
    // Three today: one event loop and two futures loops. A drop to zero is the
    // regex going stale, not the feature disappearing.
    expect(sites.length).toBeGreaterThanOrEqual(3);
  });

  it("attaches personalization to exactly the item types this suite covers", () => {
    const types = new Set<string>();
    for (const site of sites) {
      const before = feedSrc.slice(0, site.index as number);
      const typeMatches = [...before.matchAll(/"type":\s*"(\w+)"/g)];
      expect(typeMatches.length).toBeGreaterThan(0);
      types.add(typeMatches[typeMatches.length - 1][1]);
    }
    expect([...types].sort()).toEqual(["event", "futures"]);
  });

  it("a bundle member keeps its personalization, which is why the compact row carries the cue", () => {
    // `_public_member_item` strips only underscore keys plus a named few, so
    // `personalized` / `multiplier` / `personalization_reasons` survive into
    // `FeedBundleData.items` and reach `FuturesCompactRow` and the
    // `ThemeBundleCard` member cards.
    const bundles = fs.readFileSync(path.join(REPO, "backend", "app", "utils", "discover_bundles.py"), "utf8");
    expect(bundles).toContain("def _public_member_item");
    const fn = bundles.slice(bundles.indexOf("def _public_member_item"), bundles.indexOf("def _make_bundle_item"));
    expect(fn).toContain('key.startswith("_")');
    expect(fn).not.toContain("personalized");
    expect(fn).not.toContain("multiplier");
  });
});
