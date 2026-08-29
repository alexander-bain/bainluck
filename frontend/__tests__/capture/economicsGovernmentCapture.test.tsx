/**
 * UX-P171 — THE ECONOMICS PAGE STOPS CLAIMING THREE MARKETS IT SHOWS NONE OF.
 *
 * ═══ WHAT THIS IS ═══
 *
 * `/economics` renders nine sections. Eight have content. The ninth and last —
 * "Government & Fiscal · Shutdowns, debt, DOGE" — rendered a header, a pill
 * reading "3 active", and then an EMPTY bordered card. Zero words inside it.
 *
 * Two separate mistakes stacked:
 *
 *   THE GATE READ A DIFFERENT FIELD THAN THE RENDER.
 *         The section was gated on `t.government.count > 0` — the number of
 *         markets classified into the theme — while the body mapped over
 *         `t.government.markets`, the subset narrow enough to fit a Market row.
 *         When those two disagree the gate opens on a body with nothing in it.
 *         Every OTHER section in the file gates its inner cards on their own
 *         list (`rate_cuts.length > 0`, `stocks.length > 0`, ...). The sibling
 *         page had already solved the outer half too: politics' `ThemeSection`
 *         guards `if (!data.markets?.length) return null` and spells the
 *         difference out as "N shown · M total". Two of three surfaces had the
 *         fix; economics did not.
 *
 *   THE PRODUCER THREW THE MARKETS AWAY.
 *         `_market_row()` returns None above five outcomes. All three
 *         government markets have seven to nine. So `count` was 3 and `markets`
 *         was `[]` — not because the data was missing, but because the page
 *         refused to render the shape it came in. The three are live, priced,
 *         and interesting: a nine-rung "how much will Trump cut" spending
 *         ladder and two US-trade-deficit bracket distributions.
 *
 * ═══ THE READER COUNT ═══
 *
 * 100% of loads, every load, and it is not conditional on scroll position
 * beyond reaching the last section. `GET /api/economics` was pulled three times
 * on 2026-08-29 and was byte-identical each time modulo `updated_at`; the
 * government theme read `count: 3, markets: []` in all three.
 *
 * ═══ THE THING THAT WOULD HAVE BEEN EASY AND WRONG ═══
 *
 * Hiding the section. It removes the lie and it is one line. It also deletes
 * three live markets that the badge had just finished telling the reader about,
 * and it papers over OUR bug at the display layer — the data is perfect, the
 * producer is discarding it. So the section is now gated on what it renders AND
 * given something true to render.
 *
 * ═══ THE ONE THAT NEEDED CARE ═══
 *
 * "Government spending increase in 2026" is a CUMULATIVE ladder — nine rows of
 * "At least $X", summing to 571%. Those are not a distribution: each row is an
 * independent probability of clearing its own bar (gotcha #17). Normalizing
 * them against each other, or picking a "modal bracket", would have replaced
 * one lie with a subtler one. Ladders render raw and say so; only genuine
 * partitions are normalized.
 *
 * ═══ WHAT EVERY ROW HERE IS MADE OF ═══
 *
 * Every assertion renders the SHIPPED economics page against the verbatim
 * `GET /api/economics` body banked before a line of the fix was written
 * (`backend/tests/fixtures/uxp171_economics_government.json`). Nothing is drawn
 * by hand and there is no source-level arm — a guard that reads the file stays
 * green when someone deletes the call site.
 *
 *   TZ=UTC npx jest --testPathPatterns=economicsGovernmentCapture
 */

import React from "react";
import { renderToStaticMarkup } from "react-dom/server";
import fs from "node:fs";
import path from "node:path";

const FRONTEND = path.join(__dirname, "..", "..");
const REPO = path.join(FRONTEND, "..");
const FIXTURE = path.join(
  REPO,
  "backend",
  "tests",
  "fixtures",
  "uxp171_economics_government.json",
);

const banked = JSON.parse(fs.readFileSync(FIXTURE, "utf8"));
const SERVED_BEFORE = banked.served_before;
const GOV_AFTER = banked.served_after_government;

/** The payload the dyno will serve once the backend half deploys. */
const SERVED_AFTER = {
  ...SERVED_BEFORE,
  themes: { ...SERVED_BEFORE.themes, government: GOV_AFTER },
};

/* ── SWR and the analytics hooks are all that stand between page and payload ─ */

let swrPayload: unknown;
let swrError: unknown;

jest.mock("swr", () => ({
  __esModule: true,
  default: () => ({ data: swrPayload, error: swrError }),
}));

jest.mock("@/hooks", () => ({
  __esModule: true,
  usePageTracking: () => undefined,
  useScrollDepth: () => undefined,
  useEngagementTime: () => undefined,
}));

// eslint-disable-next-line @typescript-eslint/no-var-requires
const EconomicsPage = require("@/app/economics/page").default;

function render(payload: unknown, error: unknown = undefined): string {
  swrPayload = payload;
  swrError = error;
  return renderToStaticMarkup(React.createElement(EconomicsPage));
}

/** Strip tags so assertions read what a PERSON reads, not what React emitted. */
function visibleText(markup: string): string {
  return markup
    .replace(/<[^>]*>/g, " ")
    .replace(/&ldquo;|&rdquo;/g, '"')
    .replace(/&middot;/g, "·")
    .replace(/&#x27;|&apos;/g, "'")
    .replace(/&amp;/g, "&")
    .replace(/\s+/g, " ")
    .trim();
}

const GOV_KICKER = "Government & Fiscal";
/** renderToStaticMarkup escapes the ampersand — matching the raw form against
 *  markup is a `not.toContain` that can never fail. Anchor on the markup form. */
const GOV_KICKER_MARKUP = "Government &amp; Fiscal";
const GOV_TITLE = "Shutdowns, debt, DOGE";

/**
 * The slice of markup from the government kicker to the end of its section.
 * Assertions about "the section" must not be satisfied by a sibling section —
 * a disjunctive match over a whole page finds a neighbour.
 */
function governmentSection(markup: string): string | null {
  const start = markup.indexOf(GOV_KICKER_MARKUP);
  if (start === -1) return null;
  // The government section is the last one in the content column; the footer
  // that follows is the reliable terminator.
  const end = markup.indexOf("Prediction market data", start);
  return markup.slice(start, end === -1 ? undefined : end);
}

/* ═══════════════════════════════════════════════════════════════════════ */

describe("UX-P171 · the banked BEFORE is genuinely the broken state", () => {
  test("the fixture really is count-three, zero-rows", () => {
    expect(SERVED_BEFORE.themes.government.count).toBe(3);
    expect(SERVED_BEFORE.themes.government.markets).toEqual([]);
  });

  test("government is the ONLY section whose gate opened on an empty body", () => {
    const census = banked._section_census.sections;
    const lying = Object.entries(census).filter(
      ([, s]: [string, any]) => s.gate_count > 0 && s.rendered_rows === 0,
    );
    expect(lying.map(([k]) => k)).toEqual(["government"]);
    // ...and the other eight really do render something, so this is a census
    // of the whole page and not a census of one section.
    expect(Object.keys(census)).toHaveLength(9);
  });

  test("the three markets were dropped by width, not by absence", () => {
    const pop = banked._government_population;
    // Five classify as government; two lead at 99.85% and 100% and are dropped
    // as probability-extreme before the section is built. Three survive — the
    // "3 active" the badge printed — and not one fits a Market row.
    expect(pop.classified_government).toBe(5);
    expect(pop.excluded_probability_extreme).toBe(2);
    expect(pop.surviving_government).toBe(3);
    expect(pop.renderable_as_market_row).toBe(0);
    expect(pop.market_ids).toHaveLength(3);
  });
});

describe("UX-P171 · the section stops rendering a claim with nothing under it", () => {
  test("BEFORE the backend half lands, the section hides rather than lies", () => {
    // An old dyno serves no `distributions` key at all. The page must not draw
    // a header and an empty card just because `count` is 3.
    const markup = render(SERVED_BEFORE);
    expect(markup).not.toContain(GOV_KICKER_MARKUP);
    expect(markup).not.toContain(GOV_TITLE);
    // The escaped form is the one that exists; prove the anchor is real by
    // finding it in the AFTER render.
    expect(render(SERVED_AFTER)).toContain(GOV_KICKER_MARKUP);
  });

  test("a section that renders nothing contributes no words either", () => {
    const text = visibleText(render(SERVED_BEFORE));
    expect(text).not.toContain(GOV_TITLE);
    // The badge is the specific thing that was making the claim.
    expect(text).not.toContain("3 active");
  });

  test("the other eight sections are untouched by that gate change", () => {
    const text = visibleText(render(SERVED_BEFORE));
    for (const kicker of [
      "Federal Reserve",
      "Inflation & Consumer Prices",
      "Jobs & Employment",
      "GDP & Recession",
      "Markets & Indices",
      "Energy & Commodities",
      "Housing & Mortgages",
      "Trade & Tariffs",
    ]) {
      expect(text).toContain(kicker);
    }
  });

  test("an explicitly empty government theme is also hidden", () => {
    const markup = render({
      ...SERVED_BEFORE,
      themes: {
        ...SERVED_BEFORE.themes,
        government: { count: 7, markets: [], distributions: [] },
      },
    });
    expect(markup).not.toContain(GOV_KICKER_MARKUP);
  });

  test("a narrow market alone is still enough to open the section", () => {
    const text = visibleText(
      render({
        ...SERVED_BEFORE,
        themes: {
          ...SERVED_BEFORE.themes,
          government: {
            count: 1,
            markets: [
              { q: "Government shutdown on Oct 1, 2026?", prob: 22, src: "kalshi", delta: null, market_id: 1 },
            ],
            distributions: [],
          },
        },
      }),
    );
    expect(text).toContain(GOV_TITLE);
    expect(text).toContain("Government shutdown on Oct 1, 2026?");
  });
});

describe("UX-P171 · the three live markets become visible", () => {
  test("all three appear by name once the backend half lands", () => {
    const section = governmentSection(render(SERVED_AFTER));
    expect(section).not.toBeNull();
    const text = visibleText(section as string);
    expect(text).toContain("Government spending increase in 2026");
    expect(text).toContain("US Trade Deficit in 2026?");
    expect(text).toContain("When will the debt limit be increased?");
  });

  test("the section now renders words, not just markup", () => {
    const section = governmentSection(render(SERVED_AFTER)) as string;
    // The BEFORE card's whole contribution was a heading and an empty box. A
    // section that renders 400 bytes and zero words is lying about being alive.
    expect(visibleText(section).length).toBeGreaterThan(200);
  });

  test("the badge's number is now true of what is below it", () => {
    const section = governmentSection(render(SERVED_AFTER)) as string;
    const text = visibleText(section);
    expect(text).toContain("3 active");
    expect(GOV_AFTER.distributions).toHaveLength(3);
  });
});

describe("UX-P171 · a cumulative ladder is not a distribution", () => {
  const ladder = GOV_AFTER.distributions.find(
    (d: any) => d.q === "Government spending increase in 2026",
  );

  test("the spending market is recognised as a threshold ladder", () => {
    expect(ladder).toBeDefined();
    expect(ladder.q).toBe("Government spending increase in 2026");
    expect(ladder.rows).toHaveLength(9);
  });

  test("its rows are served RAW — never rescaled to sum to 100", () => {
    const total = ladder.rows.reduce((a: number, r: [number, string]) => a + r[0], 0);
    // Nine overlapping "at least" thresholds. 571%, and that is correct.
    expect(Math.round(total)).toBe(571);
    expect(ladder.rows[0][0]).toBe(97);
    expect(ladder.rows[8][0]).toBe(7.5);
  });

  test("the reader is told the rows overlap, so 571% is not a mystery", () => {
    const text = visibleText(governmentSection(render(SERVED_AFTER)) as string);
    expect(text).toContain("Chance of clearing each threshold");
    expect(text).toContain("Thresholds overlap");
  });

  test("the ladder prints its thresholds and its percentages", () => {
    const text = visibleText(governmentSection(render(SERVED_AFTER)) as string);
    expect(text).toContain("At least $400 billion");
    expect(text).toContain("57%");
    expect(text).toContain("At least $1 trillion");
  });

  test("no ladder row is described as the modal bracket", () => {
    const text = visibleText(governmentSection(render(SERVED_AFTER)) as string);
    // "Modal bracket highlighted" belongs to the partition cards only. The
    // lowest rung of a cumulative ladder is always the biggest number and
    // calling it modal would be meaningless.
    const bracketCards = GOV_AFTER.distributions.filter((d: any) => d.kind === "brackets");
    expect(bracketCards).toHaveLength(1);
    expect(text.match(/Modal bracket highlighted/g)).toHaveLength(1);
    // Two of the three are ladders, so the overlap note appears twice.
    expect(text.match(/Thresholds overlap/g)).toHaveLength(2);
  });

  test("the DEADLINE ladder is left raw too", () => {
    // "Before Jan 1, 2028" nests exactly like "At least $400 billion" — the
    // rungs overlap, so 264.5% is the honest total.
    const deadline = GOV_AFTER.distributions.find(
      (d: any) => d.q === "When will the debt limit be increased?",
    );
    expect(deadline.kind).toBe("ladder");
    const total = deadline.rows.reduce((a: number, r: [number, string]) => a + r[0], 0);
    expect(Math.round(total * 10) / 10).toBe(264.5);
    const text = visibleText(governmentSection(render(SERVED_AFTER)) as string);
    expect(text).toContain("Before Jan 1, 2028");
  });
});


describe("UX-P171 · a genuine partition IS normalized", () => {
  const partition = GOV_AFTER.distributions.find(
    (d: any) => d.q === "US Trade Deficit in 2026?",
  );

  test("the 124% overround is scaled back to a real distribution", () => {
    const total = partition.rows.reduce((a: number, r: [number, string]) => a + r[0], 0);
    expect(total).toBeGreaterThan(99);
    expect(total).toBeLessThan(101);
  });

  test("normalization preserved the ordering and the leader", () => {
    expect(partition.rows[0][1]).toBe("800–900B");
    expect(partition.rows[0][0]).toBeGreaterThan(partition.rows[1][0]);
  });

  test("its brackets are rendered and labelled", () => {
    const text = visibleText(governmentSection(render(SERVED_AFTER)) as string);
    expect(text).toContain("800–900B");
    expect(text).toContain("8 brackets");
  });
});

describe("UX-P171 · no bar width is ever NaN", () => {
  /** Percentage widths only — SourceChip's fixed pixel dots are not scaled. */
  function percentWidths(markup: string): string[] {
    return (markup.match(/width:\s*([^;"]+)/g) || [])
      .map((m) => m.split(":")[1].trim())
      .filter((w) => w.endsWith("%"));
  }

  test("the shipped AFTER page emits only finite percentage widths", () => {
    const widths = percentWidths(render(SERVED_AFTER));
    expect(widths.length).toBeGreaterThan(0);
    for (const w of widths) {
      expect(Number.isFinite(parseFloat(w))).toBe(true);
    }
  });

  test("an all-zero ladder still draws finite bars", () => {
    // Math.max(4, 0/0) is NaN and CSS drops the declaration in silence.
    const zeroed = {
      ...SERVED_BEFORE,
      themes: {
        ...SERVED_BEFORE.themes,
        government: {
          count: 1,
          markets: [],
          distributions: [
            {
              q: "Nothing has traded yet",
              kind: "ladder",
              rows: [[0, "At least $1"], [0, "At least $2"]],
              src: "kalshi",
              market_id: 9,
            },
          ],
        },
      },
    };
    const markup = render(zeroed);
    expect(markup).toContain("Nothing has traded yet");
    for (const w of percentWidths(markup)) {
      expect(w).not.toContain("NaN");
      expect(Number.isFinite(parseFloat(w))).toBe(true);
    }
  });

  test("an all-zero rate-cuts field draws finite bars too", () => {
    const zeroed = {
      ...SERVED_BEFORE,
      themes: {
        ...SERVED_BEFORE.themes,
        fed: {
          ...SERVED_BEFORE.themes.fed,
          rate_cuts: [[0, "0 cuts"], [0, "1 cut"]],
        },
      },
    };
    const markup = render(zeroed);
    expect(markup).toContain("How many cuts in 2026?");
    for (const w of percentWidths(markup)) {
      expect(w).not.toContain("NaN");
      expect(Number.isFinite(parseFloat(w))).toBe(true);
    }
  });
});

describe("UX-P171 · loading and errors are still distinguishable from empty", () => {
  test("still loading shows the skeleton, not a hidden section", () => {
    const markup = render(undefined);
    expect(markup).not.toContain(GOV_KICKER_MARKUP);
    expect(markup).toContain("animate-pulse");
  });

  test("a fetch error reads as an error", () => {
    const text = visibleText(render(undefined, new Error("boom")));
    expect(text).toContain("Failed to load economics data");
  });
});
