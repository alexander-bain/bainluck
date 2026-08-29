/**
 * UX-P181 artifact rig — renders `artifacts-ux-p181/golf-tour-badge.html`.
 *
 * Renders the SHIPPED `components/TournamentCard.tsx` against the banked
 * production payload, before and after, so the ship can be looked at rather
 * than described. Chromium is dead in this sandbox; a drawing is not a render.
 *
 * NO TIMEZONE GATE, deliberately. UX-P179 and UX-P180 — the two previous queues
 * on this same card — both shipped date defects and both needed one. This one is
 * a string served by the backend; it renders identically in every zone, and the
 * rig asserts that rather than inheriting a guard that buys nothing.
 *
 *   cd frontend && npx jest --testPathPatterns=golfTourBadgeAuthorityArtifact
 */

import fs from "fs";
import path from "path";
import React from "react";
import { renderToStaticMarkup } from "react-dom/server";

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

import TournamentCard from "@/components/TournamentCard";
import type { GolfTournament } from "@/lib/types";
import fixture from "../fixtures/uxp181_golf_tour_badge.json";

type Served = {
  tournaments_as_served: GolfTournament[];
  pga_schedule_rows: { name: string; tour: string }[];
  expected_after: Record<string, { tour: string; tour_label: string }>;
};
const FX = fixture as unknown as Served;

const served = (k: string) => {
  const t = FX.tournaments_as_served.find((x) => x.key === k);
  if (!t) throw new Error(`fixture no longer carries ${k}`);
  return t;
};
const fixed = (k: string): GolfTournament => ({ ...served(k), ...FX.expected_after[k] });

const render = (t: GolfTournament) =>
  renderToStaticMarkup(
    React.createElement(TournamentCard as React.FC, { tournament: t } as never),
  );

const panel = (title: string, note: string, markup: string) => `
  <section>
    <h2>${title}</h2>
    <p>${note}</p>
    <div class="stage">${markup}</div>
  </section>`;

describe("UX-P181 artifact", () => {
  it("renders the shipped card before and after, and asserts its own output", () => {
    const OMEGA = "omega_european_masters";
    const HUSQ = "husqvarna_british_masters";
    const TC = "tour_championship";

    const html = `<!doctype html>
<html lang="en"><head><meta charset="utf-8">
<title>UX-P181 — the Omega European Masters stops being badged PGA Tour</title>
<script src="https://cdn.tailwindcss.com"></script>
<style>
  body{font:14px/1.55 -apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif;
       background:#fafafa;color:#111;margin:0;padding:32px;max-width:860px}
  h1{font-size:20px;margin:0 0 6px} h2{font-size:14px;margin:26px 0 4px}
  p{color:#555;margin:0 0 10px} code{background:#eee;padding:1px 4px;border-radius:3px}
  .stage{background:#fff;border:1px solid #e5e5e5;border-radius:10px;padding:14px;max-width:420px}
  .lede{background:#fff;border:1px solid #e5e5e5;border-radius:10px;padding:14px;margin-bottom:8px}
  table{border-collapse:collapse;font-size:13px;margin-top:6px}
  td,th{border:1px solid #e5e5e5;padding:4px 9px;text-align:left}
</style></head><body>
<h1>UX-P181 — the Omega European Masters stops being badged &ldquo;PGA Tour&rdquo;</h1>
<div class="lede">
<p><b>One payload, two answers.</b> <code>GET /api/golf</code> served
<code>tournaments[].tour_label = "PGA Tour"</code> for the Omega European Masters
while, in the same response, <code>pga_schedule[]</code> carried that tournament
as <code>tour: "euro"</code> &mdash; DP World Tour. Its only open market is
<code>KXDPWORLDTOUR-OMEM26</code>: Kalshi&rsquo;s own series ticker names the
tour. Its sibling one week earlier, the Husqvarna British Masters, was already
filed correctly, because DataGolf happened to supply
<code>market_metadata-&gt;&gt;'tour'</code> for that one and not for this one.</p>
<p><code>_classify_tour</code> consulted none of the three and ended in a bare
<code>return "pga"</code>. Measured against production 2026-08-29 over all
<b>110</b> open golf markets: <b>69 (63%) were decided by that default</b>, and
<b>8 of them carried a ticker that contradicted it</b>.</p>
<p>It is not only a chip. On <code>/categories/golf</code> the <code>tour</code>
key is the <b>section grouping</b> and <code>tour_label</code> is the section
<b>heading</b>, so the page filed two consecutive-week DP World Tour events under
two different headings. The card also renders on <code>/sport/*</code> and in the
Discover feed via <code>FeedCard</code> &mdash; six call sites across five files.</p>
<table>
<tr><th>served tournament</th><th>today</th><th>after</th><th>decided by</th></tr>
<tr><td>Tour Championship</td><td>PGA Tour</td><td>PGA Tour</td><td>DataGolf metadata</td></tr>
<tr><td><b>Omega European Masters</b></td><td><b>PGA Tour</b></td><td><b>DP World Tour</b></td><td><b>Kalshi ticker</b></td></tr>
<tr><td>Husqvarna British Masters</td><td>DP World Tour</td><td>DP World Tour</td><td>DataGolf metadata</td></tr>
<tr><td>Golfers To Win A Pga Tour Major In 2027</td><td>PGA Tour</td><td>PGA Tour</td><td>&ldquo;PGA Tour&rdquo; in the name</td></tr>
<tr><td>Golfers To Win A Pga Tour Major Before 2030</td><td>PGA Tour</td><td>PGA Tour</td><td>&ldquo;PGA Tour&rdquo; in the name</td></tr>
</table>
<p style="margin-top:8px">Exactly one served card changes. The other four
<b>re-earn</b> their badges from evidence rather than defaulting into them
&mdash; which is what makes inverting the bare default a measured decision for a
later queue instead of a guess.</p>
</div>
${panel(
  "BEFORE — a DP World Tour event wearing a PGA Tour chip",
  'The card as production serves it today. The chip reads <code>⛳ PGA Tour</code>, and on <code>/categories/golf</code> this card sits under the <b>PGA Tour</b> heading.',
  render(served(OMEGA)),
)}
${panel(
  "AFTER — the shipped card, with the tour its own ticker names",
  'The same component, the same fixture, with the value <code>_classify_tour</code> now returns. The chip reads <code>⛳ DP World Tour</code> and the card moves into the <b>DP World Tour</b> section &mdash; next to the Husqvarna British Masters, where it belongs.',
  render(fixed(OMEGA)),
)}
${panel(
  "CONTROL — the sibling that was already right",
  'The Husqvarna British Masters, one week earlier and the same tour. It was correct before and is byte-identical after; the rig asserts that rather than claiming it. A fix that widened its way to <code>dp_world</code> by breaking the DataGolf metadata arm would fail here.',
  render(fixed(HUSQ)),
)}
${panel(
  "CONTROL — the PGA Tour event that must stay a PGA Tour event",
  'The Tour Championship. The dangerous version of this fix is a bare <code>\\bpga\\b</code> recognizer: three DP World Tour events on the current DataGolf schedule are named <b>BMW PGA Championship</b> and <b>BMW Australian PGA Championship</b>, and it would badge them PGA Tour &mdash; manufacturing the exact defect being removed. The recognizer requires the full phrase &ldquo;PGA Tour&rdquo;.',
  render(fixed(TC)),
)}
</body></html>`;

    const out = path.join(__dirname, "../../../artifacts-ux-p181");
    fs.mkdirSync(out, { recursive: true });
    const file = path.join(out, "golf-tour-badge.html");
    fs.writeFileSync(file, html);

    // The rig asserts its own output — a file that captured the wrong thing is
    // worse than no file.
    const w = fs.readFileSync(file, "utf8");
    expect(w).toContain("Omega European Masters");
    // Exactly one panel shows the defect and exactly three show DP World Tour
    // (after, control-sibling, and the lede's table row is <b>-wrapped so it
    // does not match the bare chip form).
    const chips = [...w.matchAll(/<span>⛳ ([^<]*)<\/span>/g)].map((m) => m[1]);
    expect(chips).toEqual(["PGA Tour", "DP World Tour", "DP World Tour", "PGA Tour"]);
    // Zone-independence, asserted rather than assumed: no rendered chip depends
    // on the clock or the locale, so there is nothing here for a TZ gate to do.
    expect(chips.join()).not.toMatch(/\d{4}/);
  });
});
