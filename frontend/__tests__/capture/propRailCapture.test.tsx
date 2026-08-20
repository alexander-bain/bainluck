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

  it("the app stylesheet was found — an unstyled capture is a misleading one", () => {
    // If this reds, run `npm run build` first. A capture taken without the real
    // CSS looks broken in ways the code is not, and reviewing it wastes the one
    // thing the capture is for.
    expect(css.length).toBeGreaterThan(10_000);
  });
});
