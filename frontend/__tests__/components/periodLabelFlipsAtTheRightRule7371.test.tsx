// #7371 — A LIVE GAME'S NEWEST INNING MARKER STOPS PRINTING AS A SINGLE ORPHAN
// LETTER, WITHOUT LOSING ITS CAPTION.
//
// ── WHAT THE READER SAW ──────────────────────────────────────────────────────
//
// `/events/15314713` (Angels–Twins, hero `Top 10th`, `live · 3m ago`) at 390px,
// 2026-09-20 04:46Z, site `v4796`. The win-probability chart drew its dashed
// period rule at the plot's right edge captioned with a bare **`T`**. The other
// marker on the same chart read `T8` correctly.
//
// There is no code path that emits a bare `T`: `normalizePeriodLabel` builds a
// baseball label as prefix + inning (`"Top 10th"` → `T10`). It is `T10` with its
// last two glyphs cut off — the third instance of one structural clip, after
// #3525's stray `5` and #3541's bare `F`, and the first on a caption the reader
// needs (`T10` is printed nowhere else on the chart; `Final` was on the hero).
//
// ── WHY THE EXISTING GUARD DID NOT CATCH IT, WHICH IS NOT WHAT THE ISSUE SAID ─
//
// #7371 reads the miss as `chartTextStaysInsideThePlot.test.tsx` being keyed on
// the spelling `Final`. Measured: that file's `textsGrowingOffTheRightEdge` is
// already keyed on the SHAPE — any `<text>` with `text-anchor="start"` at
// `x >= PLOT_RIGHT_PX` — and would have flagged a clipped `T10` on sight. What
// it could not see is a marker it never rendered: its fixture is
// `eventStatus="closed"`, `isLive={false}` and passes NO period boundaries at
// all, so the period-marker arm of that chart had never been in the rig at a
// width. The gap was the FIXTURE'S POPULATION, not the assertion's key.
//
// So the assertion below is deliberately the same shape test as the older
// guard's, run over the population that was missing: live charts, with markers.
//
// ── TWO REAL SPECIMENS, BECAUSE THE ISSUE CLAIMS A BLAST RADIUS ──────────────
//
// #7371 says this is "every baseball game for the first minutes of each half
// inning, and the same for `Q`/`P`/`H` markers in the other sports". One MLB
// fixture cannot witness that, so both are rendered:
//
//   MLB  `GET /api/events/15314713/history`, every series cut at 04:46:30Z —
//        two minutes after the `Top 10th` marker, which is exactly the chart the
//        reader was looking at. A live chart IS the completed history truncated
//        at now, so nothing here is synthesised.
//   NFL  the #6882 fixture (Bills–Lions), cut the same way two minutes after the
//        `4th Quarter` marker. Different sport, different label family, an
//        existing file re-read rather than a second megabyte checked in.
//
// Neither is thinned: the flip decision is a fraction of the chart's own span,
// so a fixture with its series trimmed is a fixture that no longer reproduces
// the page.
//
// ── WHAT "FIXED" MEANS HERE ──────────────────────────────────────────────────
//
// Not "no text off the right edge" on its own: deleting the caption passes that
// and is what #3541 did. Both halves are pinned — nothing grows off the edge AND
// the last marker still says `T10` / `Q4`, whole, inside the plot.

import React from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { readFileSync } from "fs";
import { join } from "path";

/** The viewport every pixel claim in this file is made at. */
const PHONE_SVG_PX = 390;

jest.mock("recharts", () => {
  const actual = jest.requireActual("recharts");
  return {
    __esModule: true,
    ...actual,
    // recharts draws NOTHING inside a ResponsiveContainer without a viewport, so
    // a chart rendered as-is emits no `<text>` and every assertion below would
    // pass over an empty string. Same mock, same reason, as
    // `chartTextStaysInsideThePlot.test.tsx`.
    ResponsiveContainer: ({ children }: { children: React.ReactElement }) =>
      React.cloneElement(children, { width: PHONE_SVG_PX, height: 300 }),
  };
});

import OddsChart from "@/components/OddsChart";
import ScoreDifferentialChart from "@/components/ScoreDifferentialChart";
import { AnalyticsProvider } from "@/components/Analytics";
import {
  anchorPeriodLabels,
  derivePeriodBoundaries,
  PERIOD_LABEL_INK_FRACTION,
  PERIOD_LABEL_MIN_SPACING_FRACTION,
  PERIOD_LABEL_STAGGER_SPACING_MULTIPLE,
} from "@/lib/periodMarkers";

/** The plot's right rule: the svg less each chart's own `right: 10` margin. */
const PLOT_RIGHT_PX = PHONE_SVG_PX - 10;

type Wire = Record<string, never>;

function readWire(file: string): Wire {
  return JSON.parse(readFileSync(join(__dirname, "../fixtures", file), "utf8"));
}

/**
 * The same game, as it was N ms into it — every series cut at one instant.
 *
 * A live chart is not a different payload shape from a finished one, it is the
 * finished one without its tail, which is why a completed fixture can witness a
 * live defect exactly. `status` goes to `live` because the components branch on
 * it, and the marker list is cut with everything else: a boundary the game has
 * not reached yet is not on the page either.
 */
function liveCutAt(wire: Wire, cutMs: number): Wire {
  const keep = <T extends { timestamp: string }>(rows: T[]) =>
    rows.filter((r) => new Date(r.timestamp).getTime() <= cutMs);
  const out: Record<string, unknown> = { ...wire, status: "live", completed_at: null };
  for (const key of [
    "history",
    "espn_history",
    "score_history",
    "aggregate_line",
    "scoring_plays",
    "period_markers",
  ]) {
    const value = (wire as Record<string, unknown>)[key];
    if (Array.isArray(value) && value.length > 0 && "timestamp" in (value[0] as object)) {
      out[key] = keep(value as { timestamp: string }[]);
    }
  }
  out.win_prob_history = Object.fromEntries(
    Object.entries(wire.win_prob_history as Record<string, { timestamp: string }[]>).map(
      ([source, points]) => [source, keep(points)]
    )
  );
  return out as Wire;
}

/** Minutes after the last period marker at which each specimen was live. */
const TWO_MINUTES_MS = 2 * 60_000;

const MLB: Wire = readWire("periodLabelRightRule.15314713.mlb-live-t10.json");

const NFL_FINAL: Wire = readWire("periodLabelStagger.14638444.nfl-final.json");
const NFL: Wire = liveCutAt(
  NFL_FINAL,
  new Date(
    (NFL_FINAL.period_markers as unknown as { timestamp: string; period: string }[])
      .filter((m) => /4th/i.test(m.period))
      .slice(-1)[0].timestamp
  ).getTime() + TWO_MINUTES_MS
);

interface Specimen {
  name: string;
  wire: Wire;
  sport: string;
  /** The caption the clip ate, whole. */
  lastLabel: string;
}

const SPECIMENS: Specimen[] = [
  { name: "MLB Angels–Twins, Top 10th", wire: MLB, sport: "baseball_mlb", lastLabel: "T10" },
  { name: "NFL Bills–Lions, 4th Quarter", wire: NFL, sport: "americanfootball_nfl", lastLabel: "Q4" },
];

function boundaries(s: Specimen) {
  return derivePeriodBoundaries(
    undefined,
    undefined,
    undefined,
    s.wire.commence_time,
    s.wire.period_markers,
    s.sport
  );
}

function renderOdds(s: Specimen): string {
  return renderToStaticMarkup(
    React.createElement(
      AnalyticsProvider,
      null,
      React.createElement(OddsChart, {
        history: s.wire.history,
        homeTeam: s.wire.home_team,
        awayTeam: s.wire.away_team,
        commenceTime: s.wire.commence_time,
        espnHistory: s.wire.espn_history,
        winProbHistory: s.wire.win_prob_history,
        winProbSources: s.wire.win_prob_sources,
        aggregateLine: s.wire.aggregate_line,
        scoringPlays: s.wire.scoring_plays,
        eventStatus: "live",
        isLive: true,
        periodBoundaries: boundaries(s),
      } as never)
    )
  );
}

function renderSdc(s: Specimen): string {
  return renderToStaticMarkup(
    React.createElement(ScoreDifferentialChart, {
      history: s.wire.history,
      homeTeam: s.wire.home_team,
      awayTeam: s.wire.away_team,
      commenceTime: s.wire.commence_time,
      scoreHistory: s.wire.score_history,
      espnHistory: s.wire.espn_history,
      eventStatus: "live",
      sportKey: s.sport,
      periodBoundaries: boundaries(s),
    } as never)
  );
}

interface EmittedText {
  x: number;
  anchor: string;
  content: string;
}

/**
 * Every `<text>` the chart emits, with the two attributes that decide whether a
 * reader sees all of it: where it starts and which way it grows.
 *
 * Reads the `<tspan>` shape recharts emits by name rather than stripping tags —
 * a strip is a sanitizer shape and CodeQL flags it
 * `js/incomplete-multi-character-sanitization` at high severity (the note
 * `chartTextStaysInsideThePlot.test.tsx` carries for the same reason).
 */
function emittedTexts(html: string): EmittedText[] {
  const texts = [...html.matchAll(/<text\b([^>]*)>([\s\S]*?)<\/text>/g)];
  // The rig has to actually draw text, or every filter below is vacuous.
  expect(texts.length).toBeGreaterThan(0);
  const out: EmittedText[] = [];
  for (const [, attrs, body] of texts) {
    const x = Number(/\bx="(-?[\d.]+)"/.exec(attrs)?.[1] ?? "NaN");
    if (Number.isNaN(x)) continue;
    const anchor = /text-anchor="(\w+)"/.exec(attrs)?.[1] ?? "start";
    const tspans = [...body.matchAll(/<tspan\b[^>]*>([^<]*)<\/tspan>/g)];
    if (tspans.length === 0 && body.includes("<")) {
      throw new Error(`unrecognised <text> body shape: ${JSON.stringify(body)}`);
    }
    const content = (tspans.length > 0 ? tspans.map((m) => m[1]).join("") : body).trim();
    out.push({ x, anchor, content });
  }
  return out;
}

/** The same two-part shape every instance of this bug has had. */
function growingOffTheRightEdge(texts: EmittedText[]): string[] {
  return texts
    .filter(
      (t) => t.x < 0 || t.x > PHONE_SVG_PX || (t.anchor === "start" && t.x >= PLOT_RIGHT_PX)
    )
    .map((t) => t.content);
}

describe.each(SPECIMENS)("#7371 — $name really is a chart that clipped", (specimen) => {
  // Strawman guards. Every assertion in the next block is about a marker sitting
  // at the right rule; on a fixture whose last marker is comfortably inside, all
  // of them pass while the page still prints one glyph.
  it("ends on the marker the hero named, spelled in full", () => {
    const derived = boundaries(specimen);
    expect(derived.length).toBeGreaterThan(1);
    expect(derived[derived.length - 1].label).toBe(specimen.lastLabel);
    // More than one glyph is what makes the clip a lie rather than an
    // abbreviation: `T` is a prefix of `T10`, so the reader cannot tell.
    expect(specimen.lastLabel.length).toBeGreaterThan(1);
  });

  it("puts that marker inside one label's ink of the last reading", () => {
    const derived = boundaries(specimen);
    const last = new Date(derived[derived.length - 1].timestamp).getTime();
    const points = Object.values(
      specimen.wire.win_prob_history as Record<string, { timestamp: string }[]>
    ).flat();
    const history = specimen.wire.history as unknown as { timestamp: string }[];
    const first = new Date(history[0].timestamp).getTime();
    const end = Math.max(...points.map((p) => new Date(p.timestamp).getTime()));
    // ~2 minutes left on a 3-hour chart, against the 12.6% a left-anchored
    // 3-character label needs. That is the geometry, and it is why the caption
    // could only ever have been a first glyph.
    expect((end - last) / (end - first)).toBeLessThan(PERIOD_LABEL_INK_FRACTION / 5);
  });
});

describe.each(SPECIMENS)(
  "#7371 — the win-probability chart keeps $name's last caption inside the plot",
  (specimen) => {
    it("draws no text off its own right-hand edge", () => {
      expect(growingOffTheRightEdge(emittedTexts(renderOdds(specimen)))).toEqual([]);
    });

    it("still says it, whole, and anchored so it grows INWARD", () => {
      // The half that stops "we deleted the caption" from passing the half
      // above. #3541 answered the identical clip by dropping the `Final` label,
      // which was right there (the hero carries a FINAL chip) and is wrong here:
      // nothing else on this chart names the current period.
      const hit = emittedTexts(renderOdds(specimen)).filter(
        (t) => t.content === specimen.lastLabel
      );
      expect(hit).toHaveLength(1);
      expect(hit[0].anchor).toBe("end");
      expect(hit[0].x).toBeLessThanOrEqual(PLOT_RIGHT_PX);
      // …and no orphan first glyph anywhere, which is what the reader saw.
      expect(emittedTexts(renderOdds(specimen)).map((t) => t.content)).not.toContain(
        specimen.lastLabel[0]
      );
    });

    it("leaves the interior markers growing rightward, as UX-P022 requires", () => {
      // The flip is for markers with no room to their right and NOTHING else.
      // Flipping every label is what UX-P022 removed: adjacent labels then grow
      // toward each other and meet in the middle (`TB2`, `T5T6` at 390px).
      const inner = emittedTexts(renderOdds(specimen)).filter(
        (t) => /^(?:[TB]\d+|Q\d|P\d|\d+H|HT|OT\d?)$/.test(t.content) && t.content !== specimen.lastLabel
      );
      expect(inner.length).toBeGreaterThan(0);
      for (const t of inner) {
        expect(t.anchor).toBe("start");
        expect(t.x).toBeLessThan(PLOT_RIGHT_PX);
      }
    });
  }
);

describe("#7371 — the score differential chart, the second call site", () => {
  const SDC_SOURCE = readFileSync(
    join(__dirname, "../../components/ScoreDifferentialChart.tsx"),
    "utf8"
  );

  it("prints nothing off its right edge either — the tie line's own caption was doing it", () => {
    // Found by this file's detector while it was aimed at the period markers:
    // the `y={0}` rule carried `value: "0"` at `position: "right"`, #3525's
    // exact shape, emitting `x=385 anchor=start` against a rule at 380. One
    // glyph, so it read as a stray digit rather than a truncation — and the
    // y-axis already prints `0` on that row, which is why the caption went
    // rather than moved.
    for (const specimen of SPECIMENS) {
      expect(growingOffTheRightEdge(emittedTexts(renderSdc(specimen)))).toEqual([]);
    }
  });

  it("still draws the tie line itself", () => {
    // The other half: a rule at zero is the chart's whole frame of reference.
    const html = renderSdc(SPECIMENS[0]);
    expect(html).toContain('stroke="rgba(0,0,0,0.2)"');
  });

  it("routes its period labels through the shared rule, with no anchor of its own", () => {
    // 🪤 THIS CALL SITE IS NOT REACHABLE BY A RENDER ASSERTION ON EITHER
    // SPECIMEN, AND SAYING SO IS THE POINT. On the MLB cut this chart's collapse
    // rule leaves ONE marker and it emits no label; on the NFL cut it draws none
    // at all, though it draws all four (`Q2 HT Q3 Q4`) on the same game once it
    // is final — the markers it can place are bounded by the drawn SCORE line
    // (CERT-1989), which on a live cut ends before the newest period does. So
    // the flip is proven here the only honest way left: the wiring, plus the
    // unit tests below over the rule both charts call.
    expect(SDC_SOURCE).toContain("anchorPeriodLabels(");
    expect(SDC_SOURCE).not.toContain('labelPosition: "insideTopLeft"');
  });
});

describe("#7371 — the flip rule itself", () => {
  const END = Date.UTC(2026, 8, 20, 4, 46, 30);
  const SPAN = 3 * 3_600_000;
  const INK = SPAN * PERIOD_LABEL_INK_FRACTION;
  const at = (msBeforeEnd: number, labelRow = 0) => ({
    timestamp: new Date(END - msBeforeEnd).toISOString(),
    labelRow,
  });

  it("is spent out of the same ink budget #6882 measured, not a new number", () => {
    // If these ever become two numbers, one of them is wrong: they are the same
    // 3-character label at 11px bold plus its air, measured once.
    expect(PERIOD_LABEL_INK_FRACTION).toBeCloseTo(
      PERIOD_LABEL_MIN_SPACING_FRACTION * PERIOD_LABEL_STAGGER_SPACING_MULTIPLE,
      12
    );
  });

  it("flips only the markers with no room to their right", () => {
    const out = anchorPeriodLabels([at(2 * INK), at(INK + 1000), at(INK - 1000), at(0)], SPAN, END);
    expect(out.map((b) => b.labelPosition)).toEqual([
      "insideTopLeft",
      "insideTopLeft",
      "insideTopRight",
      "insideTopRight",
    ]);
  });

  it("puts the boundary where the ink runs out, to the millisecond", () => {
    // A marker with one ink of room keeps the left anchor every other label has;
    // one with a shade less flips. Pinned either side rather than ON the tie:
    // `PERIOD_LABEL_INK_FRACTION` is 0.126 in binary floating point, so a span
    // times it is never a whole number of milliseconds and the exact-equality
    // case cannot be constructed from a `Date`. (A mutation pass confirms it:
    // `<` → `<=` is the one surviving mutant here, and it survives because no
    // integer-millisecond timestamp can tell the two apart.)
    expect(anchorPeriodLabels([at(Math.ceil(INK) + 1)], SPAN, END)[0].labelPosition).toBe(
      "insideTopLeft"
    );
    expect(anchorPeriodLabels([at(Math.floor(INK) - 1)], SPAN, END)[0].labelPosition).toBe(
      "insideTopRight"
    );
  });

  it("drops a flipped label one row when it would meet its neighbour's", () => {
    // The two grow TOWARD each other, so the gap has to hold both inks. At 1.5×
    // it does not, and the remedy is #6882's: keep both captions, stagger them.
    expect(anchorPeriodLabels([at(1.5 * INK), at(0)], SPAN, END).map((b) => b.labelRow)).toEqual([
      0, 1,
    ]);
    // At 2.5× both read on one row, so nothing moves.
    expect(anchorPeriodLabels([at(2.5 * INK), at(0)], SPAN, END).map((b) => b.labelRow)).toEqual([
      0, 0,
    ]);
  });

  it("does not stagger against a predecessor already on row 1", () => {
    // Two rows are provably enough (see `assignPeriodLabelRows`): a marker whose
    // predecessor already dropped has the top row free.
    expect(
      anchorPeriodLabels([at(1.5 * INK, 1), at(0)], SPAN, END).map((b) => b.labelRow)
    ).toEqual([1, 0]);
  });

  it("never lowers a row it was handed", () => {
    expect(
      anchorPeriodLabels([at(2.5 * INK, 1), at(0, 1)], SPAN, END).map((b) => b.labelRow)
    ).toEqual([1, 1]);
  });

  it("leaves a lone marker's row alone, wherever it sits", () => {
    const only = anchorPeriodLabels([at(0)], SPAN, END);
    expect(only[0].labelPosition).toBe("insideTopRight");
    expect(only[0].labelRow).toBe(0);
  });

  it("flips nothing on a chart whose markers are all well inside", () => {
    // The whole population before this change, unmoved — a rule that fires
    // everywhere is UX-P022's smear coming back.
    const out = anchorPeriodLabels([at(5 * INK), at(3 * INK), at(1.5 * INK)], SPAN, END);
    expect(out.every((b) => b.labelPosition === "insideTopLeft")).toBe(true);
    expect(out.map((b) => b.labelRow)).toEqual([0, 0, 0]);
  });
});
