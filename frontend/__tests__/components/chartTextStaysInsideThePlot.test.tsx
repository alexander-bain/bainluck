/**
 * #3520 + #3525 — NO CHART PRINTS TEXT A READER CANNOT PARSE AT PHONE WIDTH.
 *
 * Two bugs, one sentence: **no rendered text outside a chart's plot bounds, and
 * no two tick labels overlapping, at 390px.** They were filed separately because
 * they are different charts, and they are guarded together because a guard
 * written against either one alone would have let the other ship.
 *
 * WHAT WAS ON THE PAGE, both read off production on 2026-09-06 at 390px:
 *
 *   #3520  /tournaments/us-open, the contender chart, BOTH draws. Eight daily
 *          labels across a ~305px plot, of which the axis believed it had 358:
 *              30 Au31 Aug    1 Sep    2 Sep    3 Sep    4 Sep    5 Sep 6 Sep
 *          `30 Aug` and `31 Aug` overprinted into one 11-character non-word,
 *          `5 Sep` and `6 Sep` touched, and the `0%` y-label hung out of the
 *          plot's bottom and printed over the leading `3`.
 *
 *   #3525  /events/{id}, the win-probability chart, EVERY event page. A bare `5`
 *          floating past the plot's right edge on the 50% gridline — a `50%`
 *          `ReferenceLine` label at `position: "right"`, clipped by the card to
 *          its first glyph.
 *
 * ═══ WHY THIS GUARD MEASURES THE RENDER AND NOT THE MODULE ═══
 *
 * `contenderChart.ts` already had a battery asserting its labels clear 44px of
 * pitch, and it was green throughout — because both the module and the guard
 * computed that pitch against `TIER_PLOT_PX.major = 358`, a number 17% larger
 * than the plot production actually draws. Two artifacts agreeing about a wrong
 * input agree perfectly and prove nothing.
 *
 * So this file takes the widths from a RULER — see `LABEL_PX` and `PLOT_PX` —
 * lays out the labels the component really emits, and asks whether the boxes
 * collide. It resolves the emitted CSS rather than re-deriving the alignment
 * rule, and `resolveLabelBox` THROWS on any positioning shape it does not
 * recognise, so a future rewrite of the strip cannot quietly make it vacuous.
 */

import React from "react";
import { renderToStaticMarkup } from "react-dom/server";

import ContenderChart from "@/components/tournament/ContenderChart";
import type { TournamentRow } from "@/lib/tournament";

jest.mock("@/components/Analytics/AnalyticsProvider", () => ({
  __esModule: true,
  useAnalyticsContext: () => ({ track: () => {} }),
  AnalyticsProvider: ({ children }: { children: React.ReactNode }) => children,
}));

// recharts draws NOTHING inside a ResponsiveContainer without a viewport, so a
// test that rendered the chart as-is would assert over an empty string and pass
// on both arms (same reason as `chartDrawsALineYouCanSee.test.tsx`).
jest.mock("recharts", () => {
  const actual = jest.requireActual("recharts");
  return {
    __esModule: true,
    ...actual,
    ResponsiveContainer: ({ children }: { children: React.ReactElement }) =>
      React.cloneElement(children, { width: PHONE_SVG_PX, height: 300 }),
  };
});

/** The viewport every claim in this file is made at. */
const PHONE_SVG_PX = 390;

/**
 * Plot widths, in CSS px, MEASURED off production screenshots at each
 * breakpoint — never read from `TIER_PLOT_PX`, which is the thing under test.
 *
 * Method: find the chart card's own left and right border columns in the PNG
 * (DPR 2, so CSS is half the image px), take off the 1px borders and the card's
 * `px-3.5`, and cross-check against the rendered tick pitch in the same shot.
 *
 *   390px  → artifacts-live-073/usopen-womens.png  borders 56/723   → ~305
 *   1024px → artifacts-live-074/usopen-lg.png      borders 96/1125  → ~486
 *   1600px → artifacts-live-074/usopen-2xl.png     borders 96/1787  → ~817
 */
const PLOT_PX = { phone: 305, lg: 486, xxl: 817 } as const;

/** Tiers a screen of each width shows, in the order the strip emits them. */
const VISIBLE_AT = {
  phone: ["major"],
  lg: ["major", "wide"],
  xxl: ["major", "wide", "fine"],
} as const;

/** The card's own horizontal padding, which is the real bound on a label. */
const CARD_PADDING_PX = 14;

/** Air two neighbouring labels need before a reader stops reading them as two. */
const MIN_AIR_PX = 3;

/**
 * Width of a rendered `30 Aug` style label, in CSS px, from the same ruler.
 *
 * Measured off `artifacts-live-073/crop-axis-labels.png` — a 3x crop of a DPR-2
 * shot, so 6x, and the ink runs divide out cleanly: `1 Sep` is 147–150 crop px
 * (24.6–25.1 CSS) and `30 Aug` is ~185 (30.8 CSS). That is a fixed part for the
 * space and the three-letter month plus one part per tabular digit — the digits
 * are tabular, so every digit is the same width whatever it is. Rounded UP on
 * both terms, because a guard that under-measures the ink is a guard that lets
 * a touching pair through.
 */
const LABEL_PX = { month: 19.5, perDigit: 6.3 } as const;

function labelWidthPx(label: string): number {
  const digits = (label.match(/\d/g) ?? []).length;
  const width = LABEL_PX.month + LABEL_PX.perDigit * digits;
  // A label shape nobody measured must not be silently costed at the month
  // rate — `shortDateLabel` falls back to the raw ISO string on a bad date.
  if (!/^\d{1,2} [A-Z][a-z]{2}$/.test(label)) {
    throw new Error(`unmeasured axis label shape: ${JSON.stringify(label)}`);
  }
  return width;
}

interface LabelBox {
  label: string;
  tier: string;
  left: number;
  right: number;
}

/**
 * Resolve one emitted label to its box in PLOT coordinates (0 = the plot's left
 * rule, `plotPx` = its right), for a given plot width.
 *
 * Handles both the shape shipping now and the one #3520 replaced, so this file
 * can be run against the parent commit to prove it fails there. Anything else
 * throws: an unrecognised style must be a loud failure, never a silent skip.
 */
function resolveLabelBox(style: string, width: number, plotPx: number): [number, number] {
  const transform = /transform:([^;]*)/.exec(style)?.[1]?.trim() ?? "";

  // Current shape: `left:calc(<bleed>px + <fraction> * (100% - <2*bleed>px))`,
  // where the strip is the plot plus a bleed at each end.
  const bled = /left:calc\((\d+(?:\.\d+)?)px \+ (\d*\.?\d+(?:e-?\d+)?) \* \(100% - (\d+(?:\.\d+)?)px\)\)/
    .exec(style);
  if (bled) {
    const bleed = Number(bled[1]);
    const fraction = Number(bled[2]);
    expect(Number(bled[3])).toBe(bleed * 2);
    const nudge = /translateX\(calc\(-50% \+ (-?\d+(?:\.\d+)?)px\)\)/.exec(transform);
    const centre = fraction * plotPx + (nudge ? Number(nudge[1]) : 0);
    if (!nudge && transform !== "translateX(-50%)") {
      throw new Error(`unrecognised transform on a bled label: ${JSON.stringify(transform)}`);
    }
    return [centre - width / 2, centre + width / 2];
  }

  // Pre-#3520 shape: `left:<pct>%` over a strip exactly as wide as the plot,
  // with a three-way alignment. Kept only so the fail-on-parent run is real.
  const plain = /left:(\d*\.?\d+)%/.exec(style);
  if (plain) {
    const at = (Number(plain[1]) / 100) * plotPx;
    if (transform === "none" || transform === "") return [at, at + width];
    if (transform === "translateX(-50%)") return [at - width / 2, at + width / 2];
    if (transform === "translateX(-100%)") return [at - width, at];
  }
  throw new Error(`unrecognised axis label positioning: ${JSON.stringify(style)}`);
}

/** Every axis label the component emitted, laid out at one plot width. */
function labelBoxes(html: string, plotPx: number, tiers: readonly string[]): LabelBox[] {
  const strip = html.slice(html.indexOf('data-testid="chart-axis"'));
  const spans = [...strip.matchAll(/<span([^>]*?)>([^<]*)<\/span>/g)];
  const out: LabelBox[] = [];
  for (const [, attrs, label] of spans) {
    if (!attrs.includes('data-testid="chart-axis-label"')) continue;
    const tier = /data-tier="(\w+)"/.exec(attrs)?.[1] ?? "";
    if (!tiers.includes(tier)) continue;
    const style = /style="([^"]*)"/.exec(attrs)?.[1] ?? "";
    const [left, right] = resolveLabelBox(style, labelWidthPx(label), plotPx);
    out.push({ label, tier, left, right });
  }
  return out.sort((a, b) => a.left - b.left);
}

const trend = (start: string, days: number) =>
  Array.from({ length: days }, (_, i) => ({
    date: new Date(Date.parse(`${start}T00:00:00Z`) + i * 86_400_000).toISOString().slice(0, 10),
    probability: 0.2 + (i % 4) * 0.05,
  }));

const rowFor = (start: string, days: number, key = "player-a"): TournamentRow =>
  ({
    entity_key: key,
    display_name: "A Player",
    probability: 0.24,
    is_live: true,
    trend: trend(start, days),
  }) as unknown as TournamentRow;

function renderAxis(start: string, days: number): string {
  const rows = [rowFor(start, days)];
  return renderToStaticMarkup(
    <ContenderChart
      rows={rows}
      draw="womens-singles"
      selection={rows.map((entry) => entry.entity_key)}
      onToggle={() => {}}
    />
  );
}

describe("#3520 — the contender axis fits the plot it is drawn in", () => {
  /**
   * THE SPECIMEN. 30 Aug → 6 Sep is the exact window the US Open women's board
   * was serving when this was filed: eight daily readings, span 7, which is the
   * worst case the ladder can produce (a prime number of intervals, so no
   * stride divides it and the endpoints cannot both fall out of one).
   */
  const SPECIMEN = { start: "2026-08-30", days: 8 };

  it("does not overprint the two oldest labels — the pair Alex could not read", () => {
    const html = renderAxis(SPECIMEN.start, SPECIMEN.days);
    const boxes = labelBoxes(html, PLOT_PX.phone, VISIBLE_AT.phone);
    expect(boxes.length).toBeGreaterThanOrEqual(2);
    // Stated as the reader's complaint: whatever the axis chooses to print, the
    // leftmost two labels are two labels.
    const air = boxes[1].left - boxes[0].right;
    expect(`${boxes[0].label} | ${boxes[1].label} air=${air.toFixed(1)}px`).toBe(
      `${boxes[0].label} | ${boxes[1].label} air=${air.toFixed(1)}px`
    );
    expect(air).toBeGreaterThanOrEqual(MIN_AIR_PX);
  });

  it("keeps the window's first and last day ON the axis", () => {
    // The footer beside this axis says `7d shown`. If the axis reads
    // `31 Aug … 6 Sep` the chart is arguing with itself, and the reader who
    // counts the axis is the one who is wrong for no reason.
    const html = renderAxis(SPECIMEN.start, SPECIMEN.days);
    const boxes = labelBoxes(html, PLOT_PX.phone, VISIBLE_AT.phone);
    expect(boxes[0].label).toBe("30 Aug");
    expect(boxes[boxes.length - 1].label).toBe("6 Sep");
  });

  it("never overlaps two labels, at any width, over every window the ladder makes", () => {
    // Not the specimen: the whole space. A 7-day tennis window is what is on
    // the page today and a 30-day golf one is what is on it next week, so the
    // property is asserted over the ladder rather than over this tournament.
    for (const days of [3, 4, 5, 6, 7, 8, 9, 11, 13, 14, 21, 31, 46, 61, 91, 121, 201, 366]) {
      const html = renderAxis("2026-01-01", days);
      for (const width of ["phone", "lg", "xxl"] as const) {
        const boxes = labelBoxes(html, PLOT_PX[width], VISIBLE_AT[width]);
        for (let i = 1; i < boxes.length; i += 1) {
          const air = boxes[i].left - boxes[i - 1].right;
          const where = `${days}d ${width}: ${boxes[i - 1].label}|${boxes[i].label}`;
          expect(`${where} air>=${MIN_AIR_PX}: ${air >= MIN_AIR_PX}`).toBe(`${where} air>=${MIN_AIR_PX}: true`);
        }
      }
    }
  });

  it("never lets a label leave the card, which is what the alignment was FOR", () => {
    // The hard left/right alignment #3520 removed existed for a real reason —
    // a centred label at x=0 hangs off the card — and the bleed has to keep
    // paying that debt or this is a swap of one visible defect for another.
    for (const days of [3, 5, 7, 8, 13, 31, 91, 366]) {
      const html = renderAxis("2026-01-01", days);
      for (const width of ["phone", "lg", "xxl"] as const) {
        const plot = PLOT_PX[width];
        for (const box of labelBoxes(html, plot, VISIBLE_AT[width])) {
          const where = `${days}d ${width} ${box.label}`;
          expect(`${where} left: ${box.left >= -CARD_PADDING_PX}`).toBe(`${where} left: true`);
          expect(`${where} right: ${box.right <= plot + CARD_PADDING_PX}`).toBe(`${where} right: true`);
        }
      }
    }
  });

  it("keeps the y-axis labels inside the plot, so `0%` stops landing on `30 Aug`", () => {
    // The third defect in the crop, and the one that reads as a typo rather
    // than a layout bug: `0%` was centred on the baseline rule, so half of it
    // sat below the plot in the date strip.
    const html = renderAxis(SPECIMEN.start, SPECIMEN.days);
    const labels = [...html.matchAll(/<span([^>]*?data-testid="chart-y-label"[^>]*?)>/g)];
    expect(labels.length).toBeGreaterThanOrEqual(2);
    const anchors = labels.map((match) => {
      const attrs = match[1];
      return {
        anchor: /data-anchor="(\w+)"/.exec(attrs)?.[1],
        top: /top:([\d.]+)%/.exec(attrs)?.[1],
        classes: /class="([^"]*)"/.exec(attrs)?.[1] ?? "",
      };
    });
    // The one ON the baseline is anchored by its bottom, so no ink is below it.
    const zero = anchors.find((entry) => entry.top === "100.00");
    expect(zero?.anchor).toBe("bottom");
    expect(zero?.classes).toContain("-translate-y-full");
    expect(zero?.classes).not.toContain("-translate-y-1/2");
    // The one on the ceiling is anchored by its top, for the same reason at the
    // other end; everything in between is still centred on its own rule.
    const ceiling = anchors.find((entry) => entry.top === "0.00");
    expect(ceiling?.anchor).toBe("top");
    expect(ceiling?.classes).not.toContain("-translate-y");
    for (const entry of anchors.filter((item) => item !== zero && item !== ceiling)) {
      expect(entry.anchor).toBe("centre");
      expect(entry.classes).toContain("-translate-y-1/2");
    }
  });
});

describe("#3525 — the win-probability chart prints nothing past its own edge", () => {
  // Imported lazily: the recharts mock above has to be installed first.
  // eslint-disable-next-line @typescript-eslint/no-var-requires
  const OddsChart = require("@/components/OddsChart").default;

  const START = Date.UTC(2026, 8, 2, 15, 56, 0); // fixed anchor — never Date.now()
  const POINTS = Array.from({ length: 12 }, (_, i) => ({
    timestamp: new Date(START + i * 60_000).toISOString(),
    home_probability: 0.3 + (i % 5) * 0.1,
    away_probability: 0.7 - (i % 5) * 0.1,
  }));

  // Props verbatim from `chartDrawsALineYouCanSee.test.tsx`, which is the file
  // that established this chart can be rendered headlessly at all.
  function chartHtml(): string {
    return renderToStaticMarkup(
      <OddsChart
        history={[]}
        homeTeam="Aryna Sabalenka"
        awayTeam="Taylor Townsend"
        commenceTime={new Date(START).toISOString()}
        isLive={false}
        eventStatus="closed"
        externalTimeRange="all"
        winProbHistory={{ kalshi: POINTS }}
        winProbSources={{
          kalshi: { display_name: "Kalshi", color: "#22c55e", type: "prediction_market" },
        }}
      />
    );
  }

  /** The plot's right rule: the svg less this chart's own `right: 10` margin. */
  const PLOT_RIGHT_PX = PHONE_SVG_PX - 10;

  /**
   * Text this chart draws that grows off its own right-hand edge.
   *
   * NO GLYPH-WIDTH MODEL, DELIBERATELY. Every instance of this bug has the same
   * two-part shape — an anchor point at or past the plot's right rule, and
   * `text-anchor="start"`, which grows the text further right from there — and
   * that shape is exactly readable off the markup. Estimating string widths to
   * catch it would add a second thing that can be wrong (recharts' own edge tick
   * labels are anchored `middle` on real positions and would trip a crude
   * estimate), for no extra reach.
   */
  function textsGrowingOffTheRightEdge(html: string): string[] {
    const texts = [...html.matchAll(/<text\b([^>]*)>([\s\S]*?)<\/text>/g)];
    // The rig has to actually draw text, or every filter below is vacuous.
    expect(texts.length).toBeGreaterThan(0);
    const out: string[] = [];
    for (const [, attrs, body] of texts) {
      const x = Number(/\bx="(-?[\d.]+)"/.exec(attrs)?.[1] ?? "NaN");
      const anchor = /text-anchor="(\w+)"/.exec(attrs)?.[1] ?? "start";
      if (Number.isNaN(x)) continue;
      const content = renderedLabel(body);
      if (x < 0 || x > PHONE_SVG_PX) out.push(content);
      else if (anchor === "start" && x >= PLOT_RIGHT_PX) out.push(content);
    }
    return out;
  }

  /**
   * The words inside one `<text>`, for naming an offender in the failure text.
   *
   * Recharts emits two shapes and this reads BOTH of them by name rather than
   * stripping tags with a `replace`. That is not fussiness: a strip is a
   * sanitizer shape, CodeQL flags it `js/incomplete-multi-character-sanitization`
   * at high severity, and it was the one red on this PR. Reading the shapes you
   * expect — and throwing on one you do not — is both cleaner and louder.
   */
  function renderedLabel(body: string): string {
    const tspans = [...body.matchAll(/<tspan\b[^>]*>([^<]*)<\/tspan>/g)];
    if (tspans.length > 0) return tspans.map((match) => match[1]).join("").trim();
    if (body.includes("<")) {
      throw new Error(`unrecognised <text> body shape: ${JSON.stringify(body)}`);
    }
    return body.trim();
  }

  it("draws no text off its own right-hand edge, bar the one still filed", () => {
    // `position: "right"` on a ReferenceLine puts its label PAST the plot, and
    // this chart's right margin is 10px against a ~22px label — so what shipped
    // was a `5`, the first glyph of `50%`, clipped at the card boundary.
    //
    // The same guard immediately found a second, louder one: the current
    // probability callout drew its number at `cx + 12` from a dot that sits ON
    // the right rule, so the number NEVER rendered — a callout with no value in
    // it, visible in the production shot as a ringed dot with nothing beside it.
    // Both are fixed. Neither may come back.
    const offenders = textsGrowingOffTheRightEdge(chartHtml());
    // `Final` is the third instance and is NOT fixed here — it is #3541. It is
    // a settled-only marker whose anchoring is governed by UX-P022's rule that
    // every boundary label anchors on the same side, and `minSpacing` (7% of
    // the chart) is sized for a label growing RIGHT; flipping this one to grow
    // LEFT out of the right rule walks it into the space the last period label
    // was given. That is a spacing decision, not a one-line flip. Pinned here
    // so the list cannot grow quietly and so FIXING it fails this line rather
    // than passing unnoticed — whoever closes #3541 changes this to `[]`.
    // Anything else appearing in this array is a regression.
    expect(offenders).toEqual(["Final"]);
  });

  it("prints `50%` exactly once, on the axis that owns it", () => {
    // The deleted label was a DUPLICATE as well as a clipped one: `yTicks`
    // includes 50, so the left axis already prints `50%` on this exact line.
    // Pinning the count stops it coming back as a tidy "move it inside".
    const html = chartHtml();
    expect(html.match(/>50%</g) ?? []).toHaveLength(1);
  });
});
