/**
 * THE CAPTURE HARNESS — UX-P107.
 *
 * Three of the four rulings this queue implements were made by Alex FROM A
 * SCREENSHOT, and two of them were invisible to a green suite (a number whose
 * subject flipped down the page; an unlabelled unit). UX-P106 produced its
 * capture by hand and left nothing behind, so this queue had to build the rig
 * again. It is committed this time.
 *
 * Two jobs, and the second is why it lives under `__tests__`:
 *
 *   1. `UX_CAPTURE_DIR=<dir> npx jest --testPathPatterns=propRailCapture`
 *      writes one self-contained HTML file per state, styled with the app's
 *      OWN compiled stylesheet from `.next/static/css`, at a 390px mobile
 *      viewport. `tools/capture-prop-rail.sh` then drives headless Chromium
 *      over them. Run it twice — once with the three source files swapped to
 *      the previous commit — and the pair is a real before/after of the same
 *      card, not a re-creation of one.
 *
 *   2. With no env var set it is an ordinary test that renders every state and
 *      asserts the rig itself still works. A capture harness that has silently
 *      rotted is discovered at exactly the wrong moment — when a ruling needs
 *      proving and there is no time to rebuild it.
 *
 * IMPORTS ARE DELIBERATELY MINIMAL. This file is executed against the PREVIOUS
 * commit's components to produce the "before" half, so it may only import
 * symbols that exist on both sides of the change. Nothing from UX-P107's own
 * API appears here — no `chanceLabel`, no `structuralSuppressed`.
 */

import { renderToStaticMarkup } from "react-dom/server";
import React from "react";
import fs from "node:fs";
import path from "node:path";

import PropDivergenceRail from "@/components/PropDivergenceRail";
import PropDivergenceDetail from "@/components/PropDivergenceDetail";
import { selectDivergenceRows } from "@/lib/propDivergence";
import type { PlayerPropRow } from "@/lib/playerPropsGrouping";

import phillies from "../fixtures/eventPlayerProps.15199886.json";
import dodgers from "../fixtures/eventPlayerProps.15199902.settled.json";
import reds from "../fixtures/eventPlayerProps.14788546.json";

const FRONTEND_ROOT = path.resolve(__dirname, "../..");
const OUT_DIR = process.env.UX_CAPTURE_DIR;

type Surface = "rail" | "detail";

const STATES: Array<{
  slug: string;
  title: string;
  rows: PlayerPropRow[];
  status: string;
  surface?: Surface;
}> = [
  {
    slug: "pregame",
    title: "THE SCRIPT — pregame · event 15199886 (Phillies @ Marlins)",
    rows: phillies as unknown as PlayerPropRow[],
    status: "scheduled",
  },
  {
    slug: "settled",
    title: "HOW THE PROPS LANDED — settled · event 15199902",
    rows: dodgers as unknown as PlayerPropRow[],
    status: "completed",
  },
  {
    slug: "live",
    title: "WHAT'S MOVING — in-game · event 15199886 (control: neither ruling touches it)",
    rows: phillies as unknown as PlayerPropRow[],
    status: "live",
  },
  {
    // WHERE THE SUPPRESSED RUNGS WENT. Alex's ruling says they "stay reachable
    // in See all 40", and that clause is the half a rail-only capture cannot
    // show — the rail's job here is to NOT contain them.
    slug: "pregame-expanded",
    title: "SEE ALL 40 — pregame expand · event 15199886 (the suppressed rungs live here)",
    rows: phillies as unknown as PlayerPropRow[],
    status: "scheduled",
    surface: "detail",
  },
  {
    // UX-P109 / ruling 112 — THE PROOF SUBJECT. Brady Singer's strikeout ladder
    // collapsed onto the 5% floor before first pitch, so his 5+ rung is both
    // structural AND the second-biggest mover on the card (39.0% -> 5.0%,
    // 34.0 pt). UX-P108's unconditional floor deleted it; this is where that
    // shows up on a screen. `15199886` stays in the set as the CONTROL — ruling
    // 112 must not move Alex's own card, whose three structural rungs are flat.
    slug: "pregame-singer",
    title: "THE SCRIPT — pregame · event 14788546 (Cardinals @ Reds; the Singer rung)",
    rows: reds as unknown as PlayerPropRow[],
    status: "scheduled",
  },
  {
    slug: "singer-expanded",
    title: "SEE ALL 100 — pregame expand · event 14788546 (membership is a control)",
    rows: reds as unknown as PlayerPropRow[],
    status: "scheduled",
    surface: "detail",
  },
];

/**
 * The app's real stylesheet, so the capture shows the shipped design tokens
 * rather than an approximation. Largest file in `.next/static/css` is the
 * global bundle; a mock palette here would make the capture unable to catch
 * the class of defect it exists to catch (contrast, weight, alignment).
 */
function appStylesheet(): string {
  const dir = path.join(FRONTEND_ROOT, ".next/static/css");
  if (!fs.existsSync(dir)) return "";
  const files = fs
    .readdirSync(dir)
    .filter((f) => f.endsWith(".css"))
    .map((f) => ({ f, size: fs.statSync(path.join(dir, f)).size }))
    .sort((a, b) => b.size - a.size);
  return files.length ? fs.readFileSync(path.join(dir, files[0].f), "utf8") : "";
}

function page(title: string, body: string, css: string): string {
  return `<!doctype html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=390, initial-scale=1">
<style>${css}</style>
<style>
  body { margin:0; background:#f4f5f7; font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif; }
  .cap-wrap { width:390px; padding:12px; box-sizing:border-box; }
  .cap-title { font:600 11px/1.4 ui-monospace, Menlo, monospace; color:#6b7280; padding:0 4px 8px; }
</style></head>
<body><div class="cap-wrap"><div class="cap-title">${title}</div>${body}</div></body></html>`;
}

describe("the rendered capture rig", () => {
  const css = appStylesheet();

  it.each(STATES.map((s) => [s.slug, s] as const))(
    "%s renders a non-empty surface",
    (_slug, state) => {
      const Component =
        state.surface === "detail" ? PropDivergenceDetail : PropDivergenceRail;
      const html = renderToStaticMarkup(
        React.createElement(Component, {
          playerProps: state.rows,
          status: state.status,
        }),
      );
      // Non-vacuity: a capture of an empty div proves nothing, and an empty
      // rail is exactly what a selection bug produces.
      expect(html.length).toBeGreaterThan(500);
      if (state.surface !== "detail") expect(html).toContain("rounded-card");

      if (OUT_DIR) {
        fs.mkdirSync(OUT_DIR, { recursive: true });
        fs.writeFileSync(path.join(OUT_DIR, `${state.slug}.html`), page(state.title, html, css));
      }
    },
  );

  // JOB 1 ONLY — see the header. The property is "a CAPTURE is never taken
  // unstyled", and a capture is written only when UX_CAPTURE_DIR is set.
  // `.next/static/css` exists only after `npm run build`, and CI's frontend-build
  // job runs `npm ci` -> Jest -> build -> typecheck, so when this ran
  // unconditionally it was not asserting the stated property at all — it was
  // asserting that the tree happened to have been built already. It passed for
  // the lane and again for the Integrator (both had built first) and could never
  // have been green in CI; it reddened master at `c0a26325` on its first push.
  // Scoped to the mode it guards, it is now true everywhere and still fires on
  // every real capture, which is the only time an unstyled render can mislead.
  const stylesheetGuard = OUT_DIR ? it : it.skip;
  stylesheetGuard("the app stylesheet was found — an unstyled capture is a misleading one", () => {
    // If this reds, run `npm run build` first. A capture taken without the real
    // CSS looks broken in ways the code is not, and reviewing it wastes the one
    // thing the capture is for.
    expect(css.length).toBeGreaterThan(10_000);
  });
});

/**
 * ── RULING 112'S DEFERRED COST: THE PIXEL PAIR, ON DEMAND FROM REALITY ───────
 *
 * Alex deferred the layout question to pixels and said the day a real payload
 * asks it, he wants the card BOTH ways. `ladderPivotContests` is the detector;
 * this is the half that turns a fired detector into two pictures and a routing
 * note, without anyone having to remember to look.
 *
 * ** THE COUNTERFACTUAL IS RENDERED, NOT DRAWN. ** The second picture has to come
 * out of the same component and the same payload, or it is an illustration of the
 * alternative rather than the alternative. So it is produced by removing the one
 * rung that took the ladder's slot and re-rendering — and the harness then
 * ASSERTS the resulting rail equals the detector's own `counterfactualRows`. If
 * those disagree, the pair is wrong in a way a reader could not see, so the
 * harness reds instead of shipping it. That assertion is the only reason this is
 * trustworthy enough to put in front of a ruling.
 *
 * Finding the raw row is done by trying each removal rather than by re-parsing
 * `market_name`/`outcome_name` — the payloads carry the player in DIFFERENT
 * fields per provider (Kalshi in the outcome, Polymarket in the market), and a
 * parser here would be a fourth implementation of an identity this file has no
 * business knowing. Removal-and-compare needs no such knowledge and is exact.
 *
 * ** A SWEEP THAT FOUND NOTHING WRITES THAT DOWN. ** Zero contests is the
 * expected reading today and it must not be indistinguishable from a sweep that
 * never ran (gotcha #53). The manifest records the payloads examined either way.
 */
type ContestArtifact = {
  event: string;
  ladder: string;
  mover: string;
  pivot: string;
  moverTravelPt: number;
  pivotTravelPt: number;
};

function counterfactualPayload(
  rows: PlayerPropRow[],
  status: string,
  wantLabels: string[],
): PlayerPropRow[] | null {
  for (let i = 0; i < rows.length; i += 1) {
    const without = [...rows.slice(0, i), ...rows.slice(i + 1)];
    const got = selectDivergenceRows({ playerProps: without, status }).rows.map((r) => r.label);
    if (got.length === wantLabels.length && got.every((l, j) => l === wantLabels[j])) {
      return without;
    }
  }
  return null;
}

describe("ruling 112's deferred cost — routed to Alex the day a payload asks", () => {
  const css = appStylesheet();
  const PREGAME = STATES.filter((s) => s.status === "scheduled" && s.surface !== "detail");
  const found: ContestArtifact[] = [];

  it.each(PREGAME.map((s) => [s.slug, s] as const))(
    "%s: sweep for a contested ladder",
    (slug, state) => {
      const result = selectDivergenceRows({ playerProps: state.rows, status: state.status });

      for (const contest of result.ladderPivotContests) {
        const want = contest.counterfactualRows.map((r) => r.label);
        const without = counterfactualPayload(state.rows, state.status, want);
        // The pair must be two renders of one payload. If a single removal cannot
        // reproduce the detector's counterfactual, the two disagree about what the
        // alternative IS, and a picture of that would mislead the ruling.
        expect(without).not.toBeNull();

        found.push({
          event: slug,
          ladder: contest.ladder,
          mover: `${contest.mover.label} (${(contest.mover.travel * 100).toFixed(1)} pt, structural)`,
          pivot: `${contest.pivot.label} (${(contest.pivot.travel * 100).toFixed(1)} pt, market-live)`,
          moverTravelPt: Number((contest.mover.travel * 100).toFixed(1)),
          pivotTravelPt: Number((contest.pivot.travel * 100).toFixed(1)),
        });

        if (OUT_DIR) {
          fs.mkdirSync(OUT_DIR, { recursive: true });
          const stem = `contest-${slug}-${contest.ladder.replace(/[^a-z0-9]+/gi, "-")}`;
          const shot = (suffix: string, title: string, props: PlayerPropRow[]) =>
            fs.writeFileSync(
              path.join(OUT_DIR, `${stem}-${suffix}.html`),
              page(
                title,
                renderToStaticMarkup(
                  React.createElement(PropDivergenceRail, {
                    playerProps: props,
                    status: state.status,
                  }),
                ),
                css,
              ),
            );
          shot("a-mover", `SHIPPED (ruling 112) — ${contest.mover.label}`, state.rows);
          shot("b-pivot", `ALTERNATIVE — ${contest.pivot.label}`, without as PlayerPropRow[]);
        }
      }
    },
  );

  afterAll(() => {
    if (!OUT_DIR) return;
    fs.mkdirSync(OUT_DIR, { recursive: true });
    fs.writeFileSync(
      path.join(OUT_DIR, "ladder-pivot-contests.json"),
      JSON.stringify(
        {
          swept: PREGAME.map((s) => s.slug),
          contests: found.length,
          detail: found,
          note:
            found.length === 0
              ? "SWEEP RAN, ZERO CONTESTS. Ruling 112's reported cost is not being paid on any payload in the harness — the question is still not ripe. Nothing to route."
              : "CONTESTS FOUND — the *-a-mover.html / *-b-pivot.html pairs are for Alex. Ruling 112 shipped the mover; the pivot half is the alternative he deferred to pixels.",
        },
        null,
        2,
      ) + "\n",
    );
  });
});

/**
 * NON-VACUITY FOR THE SWEEP ABOVE.
 *
 * Every production payload reports zero contests today, which is the expected
 * reading — and it means the sweep's render-and-assert path never executes. A
 * green run therefore proves the detector is quiet, not that the rig can produce
 * a pair. Those are different claims, and the day one is needed is the day it is
 * too late to find out.
 *
 * So the contested shape from `propLadderPivotContest.test.tsx` is driven through
 * the SAME helper the sweep uses. If a single removal cannot reproduce the
 * detector's counterfactual, the rig would have shipped Alex a mismatched pair,
 * and this reds instead.
 */
describe("the contest rig can actually produce a pair", () => {
  function rung(player: string, stat: string, line: number, mark: number, current = mark) {
    return {
      market_name: `St. Louis vs Cincinnati: ${stat}`,
      outcome_name: `${player}: ${line}+`,
      threshold: line,
      over_probability: current,
      pregame_mark: mark,
      source: "kalshi",
    } as unknown as PlayerPropRow;
  }

  const CONTESTED: PlayerPropRow[] = [
    rung("Brady Singer", "strikeouts", 5, 0.39, 0.05),
    rung("Brady Singer", "strikeouts", 2, 0.46, 0.3),
    rung("Brycen Mautz", "strikeouts", 5, 0.6, 0.2),
    rung("Ivan Herrera", "hits + runs + rbis", 1, 0.75, 0.463),
    rung("Victor Scott", "hits + runs + rbis", 1, 0.74, 0.455),
    rung("Bryan Torres", "hits + runs + rbis", 1, 0.73, 0.45),
  ];

  it("renders both halves, and the alternative matches the detector's own counterfactual", () => {
    const result = selectDivergenceRows({ playerProps: CONTESTED, status: "scheduled" });
    expect(result.ladderPivotContests).toHaveLength(1);
    const [contest] = result.ladderPivotContests;

    const want = contest.counterfactualRows.map((r) => r.label);
    const without = counterfactualPayload(CONTESTED, "scheduled", want);
    expect(without).not.toBeNull();

    // Both halves render a real card, and they are genuinely different pictures.
    const shot = (props: PlayerPropRow[]) =>
      renderToStaticMarkup(
        React.createElement(PropDivergenceRail, { playerProps: props, status: "scheduled" }),
      );
    const a = shot(CONTESTED);
    const b = shot(without as PlayerPropRow[]);
    expect(a).toContain("rounded-card");
    expect(b).toContain("rounded-card");
    expect(a).not.toEqual(b);
    // Named, so a pair that differed for some unrelated reason would not pass.
    expect(a).toContain(contest.mover.label);
    expect(a).not.toContain(contest.pivot.label);
    expect(b).toContain(contest.pivot.label);
    expect(b).not.toContain(contest.mover.label);
  });
});
