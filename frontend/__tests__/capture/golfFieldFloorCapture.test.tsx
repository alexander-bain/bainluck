/**
 * UX-P161 — THE GOLF FIELD STOPS SAYING "NO CHANCE", for Alex's eyeball.
 *
 * ═══ WHAT THIS IS ═══
 *
 * UX-P046 established the rule once — a probability strictly inside (0, 1) may
 * never print `0%`, because `0%` reads as IMPOSSIBLE — and put it in
 * `formatProbabilityPercent`. `/categories/golf` never adopted it. Every printed
 * probability on that page was its own `Math.round(p * 100)`, and the shared
 * `TournamentCard` used a third idiom, `(p * 100).toFixed(0)`.
 *
 * ═══ WHAT EVERY PANEL IS MADE OF ═══
 *
 * Every row here is the SHIPPED `GolferRow` component, and every number comes
 * from `backend/tests/fixtures/golf_field_20260829.json` — the verbatim output of
 * `GET /api/golf` captured 2026-08-29. Nothing on this page is drawn by hand.
 *
 *   • Panel 1 — the Rogers Charity Classic field: 15 named professionals, every
 *     one of whom printed `0%`, BEFORE and AFTER.
 *   • Panel 2 — the Tour Championship field, which was already correct, BEFORE
 *     and AFTER. It must be byte-identical in both columns: the fix is invisible
 *     everywhere it does not apply, and that is as load-bearing as panel 1.
 *
 * ═══ HOW "BEFORE" IS PRODUCED, EXACTLY ═══
 *
 * There is no payload channel to strip here — the rounding was inline in the
 * component — so BEFORE cannot be made by omitting a served field. It is the
 * REAL render of the shipped component with one mechanical text substitution
 * applied to the output: the formatted string is replaced by the pre-queue
 * expression's own output, `${Math.round(p * 100)}%`. That is a transform over a
 * genuine render, not a redraw, and `assertTransformIsFaithful` below proves it
 * did what it claims (BEFORE contains `0%`, AFTER contains `<1%`) rather than
 * asking the reader to take it on trust.
 *
 *   UX_CAPTURE_DIR=<dir> TZ=UTC npx jest --testPathPatterns=golfFieldFloorCapture
 *
 * With no env var set it is an ordinary test that renders every panel and
 * asserts the rig works, same as the other capture rigs.
 */

import React from "react";
import { renderToStaticMarkup } from "react-dom/server";
import fs from "node:fs";
import path from "node:path";

jest.mock("next/navigation", () => ({
  __esModule: true,
  useRouter: () => ({ push: jest.fn(), replace: jest.fn(), prefetch: jest.fn() }),
}));
jest.mock("next/link", () => ({
  __esModule: true,
  default: ({ href, children }: { href: string; children: React.ReactNode }) => (
    <a href={href}>{children}</a>
  ),
}));

import { GolferRow } from "@/components/golf/GolferRow";
import type { GolfGolfer } from "@/lib/types";

const FRONTEND = path.join(__dirname, "..", "..");
const REPO = path.join(FRONTEND, "..");
const FIXTURE = path.join(
  REPO,
  "backend",
  "tests",
  "fixtures",
  "golf_field_20260829.json",
);

interface FixtureTournament {
  key: string;
  name: string;
  golfers: GolfGolfer[];
}

function tournaments(): FixtureTournament[] {
  return JSON.parse(fs.readFileSync(FIXTURE, "utf8")).tournaments;
}

/** The pre-queue expression, verbatim: one inline round, no floor. */
function oldPrinted(p: number): string {
  return `${Math.round(p * 100)}%`;
}

/** What `formatProbability` yields today, as it appears in escaped markup. */
function newPrintedEscaped(p: number): string {
  const rounded = Math.round(p * 100);
  if (rounded <= 0 && p > 0) return "&lt;1%";
  if (rounded >= 100 && p < 1) return "&gt;99%";
  return `${rounded}%`;
}

/** The app's own compiled stylesheet, so the rows look like the product. */
function appStylesheet(): string {
  const dir = path.join(FRONTEND, ".next", "static", "css");
  try {
    return fs
      .readdirSync(dir)
      .filter((f) => f.endsWith(".css"))
      .map((f) => fs.readFileSync(path.join(dir, f), "utf8"))
      .join("\n");
  } catch {
    return "";
  }
}

const rowHtml = (g: GolfGolfer, key: string) =>
  renderToStaticMarkup(
    <GolferRow golfer={g} tournamentKey={key} showSourceBreakdown />,
  );

/**
 * BEFORE: the real render, with the printed number swapped back to the
 * pre-queue expression's output. Applied to the row percentage and to each
 * per-source figure, which used the same idiom.
 */
function beforeHtml(g: GolfGolfer, key: string): string {
  let html = rowHtml(g, key);
  const targets = [g.probability, ...Object.values(g.sources)];
  for (const p of targets) {
    html = html.replace(newPrintedEscaped(p), oldPrinted(p));
  }
  return html;
}

function panel(t: FixtureTournament, changes: boolean): string {
  const rows = t.golfers
    .map((g) => {
      const before = beforeHtml(g, t.key);
      const after = rowHtml(g, t.key);
      return `<tr><td class="col">${before}</td><td class="col">${after}</td></tr>`;
    })
    .join("\n");
  const verdict = changes
    ? `<p class="note bad">Every row on the left claims this golfer is impossible. The live Kalshi probability is 0.003.</p>`
    : `<p class="note ok">Unchanged in both columns — the floor is invisible where it does not apply.</p>`;
  return `<section>
  <h2>${t.name}</h2>
  ${verdict}
  <table><thead><tr><th>BEFORE (deployed)</th><th>AFTER (this branch)</th></tr></thead>
  <tbody>${rows}</tbody></table>
</section>`;
}

describe("UX-P161 capture — the golf field floor", () => {
  const ts = tournaments();
  const rogers = ts.find((t) => t.name === "Rogers Charity Classic")!;
  const tourChamp = ts.find((t) => t.name === "Tour Championship")!;

  it("the fixture is the real production field", () => {
    expect(rogers.golfers).toHaveLength(15);
    expect(rogers.golfers.every((g) => g.probability === 0.003)).toBe(true);
    expect(tourChamp.golfers).toHaveLength(15);
  });

  it("assertTransformIsFaithful — BEFORE really prints 0%, AFTER really prints <1%", () => {
    for (const g of rogers.golfers) {
      const before = beforeHtml(g, rogers.key);
      const after = rowHtml(g, rogers.key);
      // The transform produced the old claim...
      expect(before).toContain(">0%<");
      expect(before).not.toContain("&lt;1%");
      // ...and the shipped component produces the new one.
      expect(after).toContain("&lt;1%");
      expect(after).not.toContain(">0%<");
    }
  });

  it("the already-correct field is byte-identical before and after", () => {
    for (const g of tourChamp.golfers) {
      expect(beforeHtml(g, tourChamp.key)).toBe(rowHtml(g, tourChamp.key));
    }
  });

  it("renders the artifact", () => {
    const css = appStylesheet();
    const html = `<!doctype html><html><head><meta charset="utf-8">
<title>UX-P161 — the golf field stops saying "no chance"</title>
<style>${css}</style>
<style>
 body{font:14px -apple-system,system-ui,sans-serif;background:#f6f7f8;color:#111;margin:0;padding:28px}
 h1{font-size:20px;margin:0 0 4px} h2{font-size:15px;margin:26px 0 6px}
 .lede{color:#555;max-width:70ch;line-height:1.5}
 table{border-collapse:collapse;width:100%;background:#fff;border:1px solid #e3e5e8;border-radius:8px;overflow:hidden}
 th{font-size:11px;text-transform:uppercase;letter-spacing:.06em;color:#666;text-align:left;padding:8px 12px;background:#fafbfc;border-bottom:1px solid #e3e5e8}
 td.col{padding:6px 12px;vertical-align:top;width:50%;border-bottom:1px solid #f0f1f3}
 td.col:first-child{border-right:1px solid #e3e5e8;background:#fffaf9}
 .note{font-size:12px;margin:0 0 8px} .bad{color:#b3261e} .ok{color:#3f6d4e}
</style></head><body>
<h1>UX-P161 — the golf field stops saying &ldquo;no chance&rdquo;</h1>
<p class="lede">Rendered from the shipped <code>GolferRow</code> over
<code>golf_field_20260829.json</code>, the verbatim output of <code>GET /api/golf</code>
captured 2026-08-29. BEFORE is the same real render with the printed number swapped
back to the pre-queue expression <code>Math.round(p * 100) + '%'</code>.</p>
${panel(rogers, true)}
${panel(tourChamp, false)}
</body></html>`;

    expect(html).toContain("&lt;1%");
    // The stylesheet actually loaded, so the rows are styled rather than bare.
    expect(css.length).toBeGreaterThan(1_000);
    const dir = process.env.UX_CAPTURE_DIR;
    if (dir) {
      fs.mkdirSync(dir, { recursive: true });
      const out = path.join(dir, "ux-p161-golf-field-floor.html");
      fs.writeFileSync(out, html, "utf8");
      // The rig asserts its own artifact (`reference_plant_must_hit_the_render`).
      expect(fs.readFileSync(out, "utf8")).toContain("&lt;1%");
    }
  });
});
