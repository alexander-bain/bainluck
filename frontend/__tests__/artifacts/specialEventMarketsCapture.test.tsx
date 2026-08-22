/**
 * CAPTURE RIG — the settled Additional Markets section, BEFORE and AFTER.
 *
 * UX-P115 (#2086). Writes standalone HTML into a capture directory that
 * `tools/render-captures.sh` turns into PNGs from any browser-capable window.
 * This window is not one: Chromium and Chrome both abort with
 * `bootstrap_check_in … Permission denied (1100)` before painting, and no flag
 * reaches it. Producing the HTML does not need a browser; rendering it does.
 * Same split as `tools/capture-prop-rail.sh`.
 *
 * OPT-IN. It writes files, so it is skipped unless `CAPTURE_DIR` is set:
 *
 *     CAPTURE_DIR=.claude/handoff/artifacts-ux-p115 \
 *       npx jest --testPathPatterns=specialEventMarketsCapture
 *
 * The BEFORE render is not a screenshot of an old build — it is this same
 * component driven with `eventStatus` withheld, which is byte-for-byte what the
 * defect produced, because the defect WAS the prop never being read. That makes
 * the pair a true control: one payload, one component, one variable.
 */

import { renderToStaticMarkup } from "react-dom/server";
import React from "react";
import fs from "node:fs";
import path from "node:path";

import SpecialEventMarkets from "@/components/SpecialEventMarkets";
import type { GameMarketsResponse } from "@/lib/api";

const CAPTURE_DIR = process.env.CAPTURE_DIR;
const maybe = CAPTURE_DIR ? describe : describe.skip;

/** Event 15177664 `other[]`, verbatim from production 2026-08-21. */
const PRODUCTION_OTHER = [
  { market_name: "Stan Wawrinka vs Roman Andres Burruchaga: Set 1 Winner", outcome_name: "Roman Andres Burruchaga", probability: 0.99, source: "kalshi" },
  { market_name: "Stan Wawrinka vs Roman Andres Burruchaga: Set 1 Winner", outcome_name: "Stan Wawrinka", probability: 0.01, source: "kalshi" },
  { market_name: "Stan Wawrinka vs Roman Andres Burruchaga: Set 2 Winner", outcome_name: "Stan Wawrinka", probability: 0.99, source: "kalshi" },
  { market_name: "Stan Wawrinka vs Roman Andres Burruchaga: Set 2 Winner", outcome_name: "Roman Andres Burruchaga", probability: 0.01, source: "kalshi" },
  { market_name: "Stan Wawrinka vs Roman Andres Burruchaga: Exact Match Score", outcome_name: "Roman Andres Burruchaga wins 2-1", probability: 0.99, source: "kalshi" },
  { market_name: "Stan Wawrinka vs Roman Andres Burruchaga: Exact Match Score", outcome_name: "Stan Wawrinka wins 2-0", probability: 0.01, source: "kalshi" },
  { market_name: "Stan Wawrinka vs Roman Andres Burruchaga: Exact Match Score", outcome_name: "Stan Wawrinka wins 2-1", probability: 0.01, source: "kalshi" },
  { market_name: "Stan Wawrinka vs Roman Andres Burruchaga: Exact Match Score", outcome_name: "Roman Andres Burruchaga wins 2-0", probability: 0.01, source: "kalshi" },
];

function payload(): GameMarketsResponse {
  return {
    event_id: 15177664,
    home_team: "Stan Wawrinka",
    away_team: "Roman Andres Burruchaga",
    status: "closed",
    other: PRODUCTION_OTHER,
    totals: [],
    player_props: [],
    team_totals: [],
    spreads: [],
    period_markets: [],
    matchups: [],
  } as unknown as GameMarketsResponse;
}

/** Tailwind is not available to a static render, so the tokens are inlined. */
function page(title: string, caption: string, body: string): string {
  return `<!doctype html>
<html><head><meta charset="utf-8"><title>${title}</title>
<style>
  body { font: 14px -apple-system, system-ui, sans-serif; margin: 0; padding: 20px;
         background: #f6f7f9; color: #111827; width: 390px; }
  .caption { font-size: 12px; color: #6b7280; margin: 0 0 14px; line-height: 1.45; }
  h3 { font-size: 17px; margin: 0; letter-spacing: -0.01em; }
  .bg-surface-card { background: #fff; }
  .border-surface-border { border-color: #e5e7eb; }
  .bg-surface-border { background: #e5e7eb; }
  .text-text-secondary { color: #4b5563; }
  .text-text-muted { color: #9ca3af; }
  .bg-violet-400 { background: #a78bfa; }
  [class*="bg-text-muted"] { background: #d1d5db; }
  .rounded-xl { border-radius: 12px; } .rounded-lg { border-radius: 8px; }
  .rounded-full { border-radius: 9999px; }
  .border { border-width: 1px; border-style: solid; }
  .p-4 { padding: 16px; } .p-3 { padding: 12px; }
  .mb-4 { margin-bottom: 16px; } .mb-3 { margin-bottom: 12px; } .mb-2 { margin-bottom: 8px; }
  .mt-0\\.5 { margin-top: 2px; }
  .grid { display: grid; gap: 16px; }
  .flex { display: flex; } .items-center { align-items: center; }
  .items-baseline { align-items: baseline; } .items-end { align-items: flex-end; }
  .justify-between { justify-content: space-between; }
  .gap-2 { gap: 8px; } .flex-1 { flex: 1; }
  .text-lg { font-size: 17px; } .text-sm { font-size: 13px; } .text-xs { font-size: 11px; }
  .font-semibold { font-weight: 600; } .font-medium { font-weight: 500; }
  .font-mono { font-family: ui-monospace, SFMono-Regular, Menlo, monospace; }
  .tabular-nums { font-variant-numeric: tabular-nums; }
  .h-1\\.5 { height: 6px; } .overflow-hidden { overflow: hidden; }
  .max-w-\\[140px\\] { max-width: 140px; } .h-full { height: 100%; }
  .w-10 { width: 40px; } .text-right { text-align: right; }
  .space-y-3 > * + * { margin-top: 12px; } .space-y-1\\.5 > * + * { margin-top: 6px; }
  .shadow-sm { box-shadow: 0 1px 2px rgba(0,0,0,.05); }
</style></head>
<body><p class="caption">${caption}</p>${body}</body></html>`;
}

maybe("capture: Additional Markets on a settled event", () => {
  // Resolved with a fallback, not a `CAPTURE_DIR as string` cast: jest EVALUATES
  // the body of a skipped `describe` to collect its test names, so a throw here
  // fails the suite on every ordinary run — which is how the first draft of this
  // rig reddened the full gate while claiming to be opt-in.
  const dir = path.resolve(__dirname, "../../..", CAPTURE_DIR ?? ".");

  beforeAll(() => fs.mkdirSync(dir, { recursive: true }));

  const cases: Array<[string, string | undefined, string]> = [
    [
      "BEFORE-special-markets-settled",
      undefined,
      "BEFORE — event 15177664, a tennis match that finished 2026-07-23, as the page " +
        "rendered it on 2026-08-21. Filled bars and live-looking percentages a month after " +
        "the result. This is the component with <code>eventStatus</code> unread, which is " +
        "exactly what the defect was.",
    ],
    [
      "AFTER-special-markets-settled",
      "closed",
      "AFTER — same payload, same component, <code>eventStatus=\"closed\"</code>. No bars, " +
        "every number declared as a closing quote, the settled state stated once. No verdict " +
        "is claimed: the grade exists in the database but is not on this payload (#2089).",
    ],
  ];

  test.each(cases)("%s", (name, status, caption) => {
    const html = renderToStaticMarkup(
      <SpecialEventMarkets data={payload()} eventStatus={status} />,
    );
    // The generator asserts its OWN artifact — a capture rig that silently
    // writes an empty page is worse than one that fails.
    expect(html).toContain("Additional Markets");
    expect(html).toContain("Roman Andres Burruchaga");

    const file = path.join(dir, `${name}.html`);
    fs.writeFileSync(file, page(name, caption, html), "utf8");
    expect(fs.statSync(file).size).toBeGreaterThan(1000);
  });

  test("the two captures actually differ", () => {
    const before = fs.readFileSync(path.join(dir, "BEFORE-special-markets-settled.html"), "utf8");
    const after = fs.readFileSync(path.join(dir, "AFTER-special-markets-settled.html"), "utf8");
    expect(before).not.toEqual(after);
    expect(before).toMatch(/style="width:\s*\d/);
    expect(after).not.toMatch(/style="width:\s*\d/);
  });
});
