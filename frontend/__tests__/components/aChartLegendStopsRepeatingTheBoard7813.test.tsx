/**
 * #7813 — THE CHART LEGEND STOPS REPEATING THE BOARD'S OWN QUESTION.
 *
 * ## What a reader met on production
 *
 * `https://bainluck.com/futures/61645756` at 390px, anonymous, 2026-09-21
 * (`artifacts/ux-1415/before-6765-PROD-390-61645756-top.png`). Under a chart, on a
 * page whose `<h1>` has just asked the question, the Probability Trend legend:
 *
 *     🔵 Alevtina Ibragimova
 *     🔴 Korea Open: Alevtina Ibragimova vs Yeon-Woo
 *        Ku Set 1 Winner
 *     🟢 Korea Open: Alevtina Ibragimova vs Yeon-Woo
 *        Ku Set 1 O/U 9.5
 *
 * Two of three entries wrap to two lines, and the only information in either is
 * `Set 1 Winner` / `Set 1 O/U 9.5`. The first entry — a plain player name — is what
 * a legend entry is supposed to look like. The same labels are printed a second
 * time in the hover tooltip, in a `max-w-[120px]` span, where all of a board's
 * series truncate to one indistinguishable string.
 *
 * ## Why #6765 shipped the rule and deliberately did not apply it here
 *
 * `withoutBoardNamePrefix` (#6765, `lib/futuresDetailDisplay.ts`) is unit-proven
 * over its whole refusal set and is measured on the same population: 194 outcome
 * rows on 66 open boards carry their board's name as a strict prefix, 0 of them
 * break at a non-separator, 0 strip to empty. That ship applied it at the hero,
 * the settled sentence, the All Outcomes rows and the movement caption, and left
 * the legend alone, because the legend is drawn by `FuturesChart` — which is
 * rendered by **eight** call sites, not the five the issue names:
 *
 *     app/futures/[id]/page.tsx           ← the one page whose <h1> IS the board
 *     app/categories/golf/page.tsx
 *     components/EvolutionView.tsx
 *     components/TeamSeasonJourney.tsx
 *     components/event/RaceToTitleChart.tsx
 *     components/event/SettledPathChart.tsx
 *     components/event/TwoSidedTimeline.tsx
 *     components/event/WinnerEvolutionChart.tsx
 *
 * ⚠️ IT IS A PAGE RULE, NOT A NAME RULE. On an event page the board's name is not
 * on screen at all, so there the prefix is the only thing telling a reader which
 * match a line belongs to — shortening it there would DESTROY information rather
 * than remove a repeat. So the board name is an optional prop passed by exactly one
 * call site, and the load-bearing half of this file is the proof that the other
 * seven did not move.
 *
 * ## What this file proves
 *
 * THE CONTROL (`the other seven surfaces`): the legend markup of each real
 * no-prop call-site prop shape is asserted byte-for-byte against a control
 * snapshotted from the PARENT COMMIT, while the repeat was still live on all eight
 * surfaces. A strawman arm asserts the control still CONTAINS the repeat, so a
 * control refreshed from this tree (which has no repeat to capture on those
 * shapes) fails instead of passing vacuously (notice 50).
 *
 * THE SHIP: with the prop, the specimen board's three legend entries become three
 * distinct strings and none of them contains the board's name.
 *
 * THE WIRING: a census of every `<FuturesChart …/>` tag in `app/` and `components/`
 * — exactly one file passes `marketName`, and it is the futures detail page. A
 * component test cannot see that class; it passes the prop itself.
 *
 * DOES NOT PROVE the hover tooltip at the render level: the tooltip only exists
 * after a pointer event and this project's jest has no jsdom to fire one. Its
 * wiring is read off the source below, and the reader-level proof is the
 * production AFTER frame in the PR.
 */

import { renderToStaticMarkup } from "react-dom/server";
import React from "react";
import { readFileSync, readdirSync, statSync } from "fs";
import { join } from "path";
import { FuturesChart } from "../../components/FuturesChart";
import type { FuturesOutcomeHistory } from "@/lib/types";

const ROOT = join(__dirname, "..", "..");

/** `/futures/61645756` as the API served it, 2026-09-21. Entry 2 carries no board
 *  prefix and is the in-fixture control: it must never move, on any surface. */
const KOREA_OPEN = "Korea Open: Alevtina Ibragimova vs Yeon-Woo Ku";
const SERIES = [
  `${KOREA_OPEN} Set 1 O/U 9.5`,
  "Alevtina Ibragimova",
  `${KOREA_OPEN} Set 1 Winner`,
];

function hist(name: string, i: number): FuturesOutcomeHistory {
  const base = Date.UTC(2026, 8, 20, 0, 0, 0);
  return {
    outcome_id: 100 + i,
    name,
    history: Array.from({ length: 6 }, (_, k) => ({
      timestamp: new Date(base + k * 3600_000).toISOString(),
      probability: 0.4 + i * 0.05 + k * 0.01,
    })),
  } as unknown as FuturesOutcomeHistory;
}

const DATA = SERIES.map(hist);
const ALL = new Set(DATA.map((d) => d.outcome_id));

/** The static legend element, exactly as served — opening tag to its own closing
 *  `</div>`. It contains only spans, so the first `</div>` is its own. */
function staticLegend(html: string): string {
  const at = html.indexOf('aria-label="Chart legend"');
  if (at === -1) return "";
  const open = html.lastIndexOf("<div", at);
  const close = html.indexOf("</div>", at);
  return html.slice(open, close + "</div>".length);
}

/** Every label painted in a legend entry, static or interactive, in order. The
 *  inner HTML is ASSERTED to be text rather than stripped with a tag regex: the
 *  assertion is the stronger check (it fails loudly if a later ship wraps the
 *  label in an element) and a `replace(/<[^>]*>/g, "")` is CodeQL
 *  `js/incomplete-multi-character-sanitization`, high — a notice-32 refuse on the
 *  whole sha. The entities are decoded in ONE pass; a chained decoder is
 *  `js/double-escaping`. Both cost #6765 a force-push. */
const ENTITY: Record<string, string> = {
  quot: '"',
  "#x27": "'",
  "#39": "'",
  lt: "<",
  gt: ">",
  amp: "&",
};

function legendLabels(html: string): string[] {
  return [...html.matchAll(/<span class="text-text-primary[^"]*">([^]*?)<\/span>/g)].map((m) => {
    expect(m[1]).not.toContain("<");
    return m[1].replace(/&(quot|#x27|#39|lt|gt|amp);/g, (s, n: string) => ENTITY[n] ?? s);
  });
}

/* ── The real prop shapes of the call sites that pass NO board name ───────────
 *
 * Copied from the call sites themselves (the census at the bottom keeps this list
 * honest about which files exist). The three that pass `showLegend={false}` —
 * EvolutionView, TwoSidedTimeline, TeamSeasonJourney — draw no legend at all and
 * are covered by the "no legend anywhere" arm.
 */
const GOLF_HUB = <FuturesChart historyData={DATA} greenTheme fieldCeiling height={240} />;
const RACE_TO_TITLE = (
  <FuturesChart
    historyData={DATA}
    selectedOutcomes={ALL}
    fixedYAxis
    fieldCeiling
    showAxes
    showLegend
    height={280}
  />
);
const SETTLED_PATH = (
  <FuturesChart
    historyData={DATA}
    selectedOutcomes={ALL}
    fixedYAxis
    stepInterpolation
    showAxes
    showLegend
    height={260}
    settled
  />
);
const WINNER_EVOLUTION = (
  <FuturesChart
    historyData={DATA}
    fixedYAxis
    fieldCeiling
    stepInterpolation
    showAxes
    showLegend
    height={280}
  />
);

/* ── THE FROZEN CONTROLS ──────────────────────────────────────────────────────
 *
 * Captured from the parent commit of this ship, 2026-09-21, with the repeat live.
 * DO NOT REFRESH THESE FROM THIS TREE. Their entire content is the defect that
 * these seven surfaces must KEEP, so a snapshot taken after the fix would contain
 * nothing to compare and the strawman arm below would fail. If a legitimate legend
 * restyle ever reddens them, split the assertion (byte-identity of the remainder
 * plus a positive arm for the changed part) rather than re-capturing — notice 50.
 *
 * Two literals rather than four: the palette is the only thing that differs
 * between the default-palette surfaces, and the golf hub is the green one.
 */
const NAME_SPAN = 'class="text-text-primary truncate max-w-[160px]"';
const controlLegend = (c1: string, c2: string, c3: string): string =>
  `<div class="flex flex-wrap gap-x-3 gap-y-1.5" aria-label="Chart legend">` +
  `<span class="flex items-center gap-2 text-sm">` +
  `<span class="w-3 h-3 rounded-full flex-shrink-0" style="background-color:${c1}"></span>` +
  `<span ${NAME_SPAN}>Korea Open: Alevtina Ibragimova vs Yeon-Woo Ku Set 1 O/U 9.5</span></span>` +
  `<span class="flex items-center gap-2 text-sm">` +
  `<span class="w-3 h-3 rounded-full flex-shrink-0" style="background-color:${c2}"></span>` +
  `<span ${NAME_SPAN}>Alevtina Ibragimova</span></span>` +
  `<span class="flex items-center gap-2 text-sm">` +
  `<span class="w-3 h-3 rounded-full flex-shrink-0" style="background-color:${c3}"></span>` +
  `<span ${NAME_SPAN}>Korea Open: Alevtina Ibragimova vs Yeon-Woo Ku Set 1 Winner</span></span>` +
  `</div>`;

const CONTROL_DEFAULT_PALETTE = controlLegend("#2563eb", "#dc2626", "#16a34a");
const CONTROL_GREEN_PALETTE = controlLegend("#006747", "#2d8659", "#6b7280");

describe("#7813 THE CONTROL — the seven surfaces that pass no board name do not move", () => {
  it("the controls still hold the repeat, so they were not refreshed from this tree", () => {
    // The strawman guard. Every assertion below is satisfiable by a control
    // captured after the fix; none of them is satisfiable by one that still
    // contains the defect UNLESS the defect is genuinely still being served to
    // these seven surfaces, which is the whole claim.
    for (const control of [CONTROL_DEFAULT_PALETTE, CONTROL_GREEN_PALETTE]) {
      expect(control.split(KOREA_OPEN).length - 1).toBe(2);
      expect(control).toContain(`${KOREA_OPEN} Set 1 Winner`);
    }
  });

  it("the golf hub legend is byte-identical to the control", () => {
    expect(staticLegend(renderToStaticMarkup(GOLF_HUB))).toBe(CONTROL_GREEN_PALETTE);
  });

  it("RaceToTitleChart, SettledPathChart and WinnerEvolutionChart are byte-identical", () => {
    for (const el of [RACE_TO_TITLE, SETTLED_PATH, WINNER_EVOLUTION]) {
      expect(staticLegend(renderToStaticMarkup(el))).toBe(CONTROL_DEFAULT_PALETTE);
    }
  });

  it("an empty or null board name is 'no board on screen', not a board called nothing", () => {
    // A caller that threads a payload field which happens to be absent gets
    // today's behaviour, never a half-applied rule.
    for (const marketName of [undefined, null, "", "   "]) {
      const html = renderToStaticMarkup(
        <FuturesChart
          historyData={DATA}
          selectedOutcomes={ALL}
          fixedYAxis
          fieldCeiling
          showAxes
          showLegend
          height={280}
          marketName={marketName}
        />,
      );
      expect(staticLegend(html)).toBe(CONTROL_DEFAULT_PALETTE);
    }
  });

  it("a padded series name keeps its padding where no board is named", () => {
    // The precise reason `seriesLabel` guards on the board rather than letting
    // `withoutBoardNamePrefix` refuse for itself: the helper trims what it
    // returns, so routed through it unconditionally the seven no-board surfaces
    // would render a padded name differently than they do today. This is the
    // smallest observable difference between "identity" and "refuses to shorten",
    // and it is the one the byte-identity controls above cannot see.
    const padded = ["  Alevtina Ibragimova  "].map(hist);
    for (const marketName of [undefined, "   "]) {
      const html = renderToStaticMarkup(
        <FuturesChart
          historyData={padded}
          selectedOutcomes={new Set([100])}
          fixedYAxis
          showAxes
          showLegend
          marketName={marketName}
        />,
      );
      expect(legendLabels(html)).toEqual(["  Alevtina Ibragimova  "]);
    }
  });

  it("the three surfaces that suppress the legend still draw none", () => {
    // EvolutionView, TwoSidedTimeline and TeamSeasonJourney. A legend appearing
    // here would be a new element on three pages, not a shortened label.
    const suppressed = renderToStaticMarkup(
      <FuturesChart
        historyData={DATA}
        selectedOutcomes={ALL}
        fixedYAxis
        showAxes
        showLegend={false}
        height={240}
      />,
    );
    expect(suppressed).not.toContain("Chart legend");
    expect(legendLabels(suppressed)).toEqual([]);
  });

  it("a mini sparkline, which defaults the legend off, is unaffected too", () => {
    const mini = renderToStaticMarkup(<FuturesChart historyData={DATA} mini />);
    expect(mini).not.toContain("Chart legend");
  });
});

describe("#7813 THE SHIP — the futures detail page's own legend", () => {
  /** The futures page's shape: it is the only call site passing `onToggleOutcome`,
   *  so the interactive button legend — the one in the production frame, and the
   *  one with no `truncate`, which is why its entries wrap rather than cut — is
   *  reachable from nowhere else. */
  const page = (marketName?: string) =>
    renderToStaticMarkup(
      <FuturesChart
        historyData={DATA}
        selectedOutcomes={ALL}
        onToggleOutcome={() => {}}
        fixedYAxis
        fieldCeiling
        marketName={marketName}
      />,
    );

  it("prints three distinct short entries where two used to wrap", () => {
    expect(legendLabels(page(KOREA_OPEN))).toEqual([
      "Set 1 O/U 9.5",
      "Alevtina Ibragimova",
      "Set 1 Winner",
    ]);
  });

  it("no entry contains the board name the <h1> has already asked", () => {
    const html = page(KOREA_OPEN);
    const legend = html.slice(html.indexOf('class="flex flex-wrap gap-3"'));
    expect(legend).not.toContain(KOREA_OPEN);
  });

  it("without the prop that same page shape is exactly today's page", () => {
    expect(legendLabels(page())).toEqual(SERIES);
  });

  it("leaves an ordinary board's names alone, board name or no board name", () => {
    const US_OPEN = "2027 US Open Men's Singles Winner";
    const names = ["Jakub Mensik", "Jannik Sinner", "Carlos Alcaraz"];
    const html = renderToStaticMarkup(
      <FuturesChart
        historyData={names.map(hist)}
        selectedOutcomes={new Set(names.map((_, i) => 100 + i))}
        onToggleOutcome={() => {}}
        fixedYAxis
        marketName={US_OPEN}
      />,
    );
    expect(legendLabels(html)).toEqual(names);
  });

  it("keeps a series whose name is SHORTER than its board — `Italy`", () => {
    // The live proof the refusal works: `/futures/61294085` serves `Italy` on a
    // board called `Italy vs. Slovenia`. A `startsWith`-and-slice would print an
    // empty legend entry beside a coloured dot.
    const VOLLEY = "Italy vs. Slovenia";
    const names = ["Italy", `${VOLLEY}: Total Sets O/U 3.5`];
    const html = renderToStaticMarkup(
      <FuturesChart
        historyData={names.map(hist)}
        selectedOutcomes={new Set([100, 101])}
        onToggleOutcome={() => {}}
        fixedYAxis
        marketName={VOLLEY}
      />,
    );
    expect(legendLabels(html)).toEqual(["Italy", "Total Sets O/U 3.5"]);
  });

  it("never paints an empty entry: every label still has ink", () => {
    for (const label of legendLabels(page(KOREA_OPEN))) {
      expect(label.trim().length).toBeGreaterThan(0);
    }
  });
});

describe("#7813 THE WIRING — exactly one call site passes a board name", () => {
  function walk(dir: string, out: string[] = []): string[] {
    for (const entry of readdirSync(dir)) {
      if (entry === "node_modules" || entry === ".next" || entry.startsWith(".")) continue;
      const full = join(dir, entry);
      if (statSync(full).isDirectory()) walk(full, out);
      else if (/\.tsx$/.test(entry)) out.push(full);
    }
    return out;
  }

  const files = [...walk(join(ROOT, "app")), ...walk(join(ROOT, "components"))]
    .map((f) => ({ rel: f.slice(ROOT.length + 1), src: readFileSync(f, "utf8") }))
    // The component's own file declares the prop; it is not a call site.
    .filter((f) => f.rel !== "components/FuturesChart.tsx")
    .map((f) => ({
      ...f,
      tags: [...f.src.matchAll(/<FuturesChart\b[\s\S]*?\/>/g)].map((m) => m[0]),
    }))
    .filter((f) => f.tags.length > 0);

  it("the census finds the call sites at all — a zero-row scan is not a pass", () => {
    expect(files.map((f) => f.rel).sort()).toEqual([
      "app/categories/golf/page.tsx",
      "app/futures/[id]/page.tsx",
      "components/EvolutionView.tsx",
      "components/TeamSeasonJourney.tsx",
      "components/event/RaceToTitleChart.tsx",
      "components/event/SettledPathChart.tsx",
      "components/event/TwoSidedTimeline.tsx",
      "components/event/WinnerEvolutionChart.tsx",
    ]);
  });

  it("the futures detail page passes it", () => {
    const page = files.find((f) => f.rel === "app/futures/[id]/page.tsx");
    expect(page!.tags.some((t) => /\bmarketName=\{market\?\.name\}/.test(t))).toBe(true);
  });

  it("and nothing else does — a new surface must state its case here", () => {
    const passing = files
      .filter((f) => f.tags.some((t) => /\bmarketName\b/.test(t)))
      .map((f) => f.rel);
    expect(passing).toEqual(["app/futures/[id]/page.tsx"]);
  });

  it("the hover tooltip reads the same label as the legend", () => {
    // The tooltip is built in a pointer handler and this project's jest has no
    // jsdom, so this is a wiring read, not a render: both the tooltip's value list
    // and both legend branches must go through the one helper, or the page would
    // shorten a label in the legend and print the long one on hover.
    const src = readFileSync(join(ROOT, "components/FuturesChart.tsx"), "utf8");
    expect(src.split("seriesLabel(outcome.name)").length - 1).toBe(3);
    expect(src).toContain("name: seriesLabel(outcome.name),");
    // And the helper is not reached at all when no board is on screen — the two
    // lines the byte-identity controls above depend on. The board is trimmed
    // before the guard, so `"   "` is "no board" rather than a board named with
    // three spaces (which would reach the helper and trim the series name).
    expect(src).toContain("const board = marketName?.trim();");
    expect(src).toContain("board ? withoutBoardNamePrefix(name, board) : name");
  });
});
