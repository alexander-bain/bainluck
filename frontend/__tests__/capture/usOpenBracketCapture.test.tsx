/**
 * CAPTURE RIG — the BRACKET TAB, at phone width, ahead of the ceremony.
 *
 * Charter amendment 2026-08-25 ("blockers block items, never lanes"): Alex's
 * verdict on the bracket has to land before the real draw does.
 *
 * Chromium is dead in this sandbox (Mach bootstrap denied), so a screenshot is
 * not available to this lane. This is the substitute the repo already uses:
 * render the ACTUAL shipped component with `renderToStaticMarkup`, wrap it in
 * the app's OWN compiled stylesheet from `.next/static/css`, and write a
 * self-contained HTML file. Real component, real CSS — not a re-creation.
 *
 * UX-P138 RE-RENDERS IT UNDER ALEX'S STRUCTURAL RULING 4: the Bracket tab is
 * the PLAYOFF GRID now, not a round strip and a list of match cards. Those
 * moved to the Tournament tab and are captured in `us-open-reskin.html`.
 *
 * The pre-draw panel still LEADS, because the ceremony is tomorrow and that
 * panel is what a real visitor sees until it happens.
 *
 * Two jobs, and the second is why it lives under `__tests__`:
 *
 *   1. `UX_CAPTURE_DIR=<dir> npx jest --testPathPatterns=usOpenBracketCapture`
 *      writes `us-open-bracket.html`, every state at a 390px viewport.
 *   2. With no env var set it is an ordinary test that renders each state and
 *      asserts the rig still works — a capture harness that has silently
 *      rotted is discovered at exactly the wrong moment.
 *
 * WHICH NUMBERS ARE REAL, stated per panel in the artifact itself: the BOARDS
 * and the ADVANCE-TO-ROUND markets are committed production reads, so the
 * sparse grid in panels 2-3 is genuinely what Alex will see tomorrow. The DRAW
 * is a synthetic fixture under `__tests__/`, which the Next.js app tree does
 * not compile, so it cannot reach a production bundle even by accident.
 */

import React from "react";
import { renderToStaticMarkup } from "react-dom/server";
import fs from "node:fs";
import path from "node:path";

import TournamentBracket from "@/components/tournament/TournamentBracket";
import PlayoffGrid from "@/components/tournament/PlayoffGrid";
import { buildBracket } from "@/lib/bracket";
import { buildMatchList } from "@/lib/matchList";
import { buildPlayoffGrid, type PlayoffGrid as GridModel } from "@/lib/playoffGrid";
import type { PropMarket } from "@/lib/tournamentProps";
import type { SlateData, SlateMatch } from "@/lib/slate";
import type { TournamentBoardData, TournamentPayload, TournamentRow } from "@/lib/tournament";
import {
  SYNTHETIC_MENS_DRAW,
  syntheticFirstRoundResults,
  syntheticPartialResults,
} from "@/__tests__/fixtures/syntheticDraw";

const MOCKS = path.join(__dirname, "..", "..", "..", "docs", "mocks", "us-open");

/** The app's real compiled Tailwind, so the capture is not a lookalike. */
function appStylesheet(): string {
  const dir = path.join(__dirname, "..", "..", ".next", "static", "css");
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

/** The real championship boards — a bounded production read, committed. */
const PAYLOAD = JSON.parse(
  fs.readFileSync(path.join(MOCKS, "payload-2026-08-25.json"), "utf8")
) as TournamentPayload;

/** The register's eleven curated props, priced by the backend's own build_props. */
const PROPS = JSON.parse(
  fs.readFileSync(path.join(MOCKS, "props-2026-08-26.json"), "utf8")
) as PropMarket[];

const SLATE = JSON.parse(
  fs.readFileSync(path.join(MOCKS, "slate-2026-08-25.json"), "utf8")
) as SlateData;

const MEN = PAYLOAD.boards[0];
const WOMEN = PAYLOAD.boards[1];

/** The grid Alex actually gets tomorrow: real boards, real curated markets. */
const realGrid = (board: TournamentBoardData) =>
  buildPlayoffGrid({
    board,
    propMarkets: PROPS,
    matches: buildMatchList({
      slate: SLATE.matches.filter((m) => m.draw === board.draw),
    }),
    draw: board.draw,
  });

/**
 * A SECOND-WEEK state, so the design can be verdicted separately from the data.
 *
 * Derived, never hand-written: the board rows are the synthetic draw's own
 * slots, so the row shape is whatever `TournamentBoardData` actually is today
 * and this fixture cannot drift away from the type. What it adds is the thing
 * production does not have yet — a played draw and a priced next round — so
 * the dense grid Alex is being asked to judge exists somewhere in the artifact
 * rather than only in a sentence promising it later.
 */
const PLAYED = 40;
const SYN_RESULTS = syntheticPartialResults(SYNTHETIC_MENS_DRAW, PLAYED);
const SYN_ROUNDS = buildBracket(SYNTHETIC_MENS_DRAW, SYN_RESULTS);

function synRow(index: number): TournamentRow {
  const slot = SYNTHETIC_MENS_DRAW[index];
  return {
    entity_key: slot.entity_key,
    display_name: slot.display_name,
    seed: slot.seed,
    country: null,
    rank: index / 2 + 1,
    state: "live",
    probability: slot.probability ?? Number((0.06 - index * 0.001).toFixed(4)),
    probability_is_live: true,
    observed_at: "2026-09-02T18:00:00+00:00",
    age_hours: 0.3,
    price_state: "live",
    freshest_observed_at: "2026-09-02T18:00:00+00:00",
    freshest_age_hours: 0.3,
    stale_sources: [],
    mixed_freshness: false,
    source_count: 2,
    sources: [],
    blend_rule: "equal_weight_midpoint",
    divergent: false,
    trend: [],
    trend_delta: null,
  };
}

const SYN_BOARD: TournamentBoardData = {
  draw: "mens-singles",
  label: "Men's Singles",
  rows: Array.from({ length: 16 }, (_, i) => synRow(i * 2)),
  contenders: 16,
  unpriced: 0,
  rows_not_live: 0,
  mixed_freshness_rows: 0,
  price_state: "live",
  newest_observed_at: "2026-09-02T18:00:00+00:00",
  age_hours: 0.3,
};

/**
 * The next round, PRICED — one live match market per surviving player pair.
 *
 * This is the column that makes a real grid dense, and it is the one thing our
 * pipeline could serve today and does not: `build_slate` prices qualifying and
 * nothing else. Synthesised here rather than asserted in prose.
 */
const SYN_SLATE: SlateMatch[] = SYN_ROUNDS[1].matches
  .filter((m) => m.top !== null && m.bottom !== null)
  .slice(0, 12)
  .map((m, i) => ({
    matchup_key: `syn-r64-${i}`,
    draw: "mens-singles",
    draw_label: "Men's Singles",
    round: "R64",
    scheduled_date: "2026-09-02T19:00:00+00:00",
    sides: [
      {
        entity_key: m.top!.entity_key,
        display_name: m.top!.display_name,
        seed: m.top!.seed,
        country: null,
        role: "participant",
        probability: Number((0.5 + ((i * 7) % 34) / 100).toFixed(2)),
        opening_probability: Number((0.5 + ((i * 5) % 30) / 100).toFixed(2)),
        move: 0.02,
        raw_probability: null,
        raw_opening_probability: null,
        age_hours: 0.3,
        price_state: "live",
      },
      {
        entity_key: m.bottom!.entity_key,
        display_name: m.bottom!.display_name,
        seed: m.bottom!.seed,
        country: null,
        role: "participant",
        probability: Number((0.5 - ((i * 7) % 34) / 100).toFixed(2)),
        opening_probability: Number((0.5 - ((i * 5) % 30) / 100).toFixed(2)),
        move: -0.02,
        raw_probability: null,
        raw_opening_probability: null,
        age_hours: 0.3,
        price_state: "live",
      },
    ],
    coherent: true,
    raw_sum: 1,
    opening_raw_sum: 1,
    probability_is_live: true,
    price_state: "live",
    observed_at: "2026-09-02T18:50:00+00:00",
    age_hours: 0.3,
    freshest_observed_at: "2026-09-02T18:50:00+00:00",
    freshest_age_hours: 0.3,
    stale_sides: [],
    mixed_freshness: false,
    favourite: m.top!.entity_key,
    has_moved: true,
    source_count: 1,
  }));

/** Curated reach markets against the synthetic field, so the middle fills too. */
const SYN_PROPS: PropMarket[] = [0, 2, 4, 6].map((i) => {
  const slot = SYNTHETIC_MENS_DRAW[i * 2];
  const surname = slot.display_name.split(" ").slice(-1)[0];
  const round = i < 4 ? "quarterfinals" : "semifinals";
  const key = `${surname.toLowerCase()}-${round}`;
  return {
    key,
    title: `Does ${surname} reach the ${round}?`,
    hook: null,
    draw: "mens-singles",
    source: "polymarket",
    answer_entity_key: `${key}:yes`,
    price_state: "live",
    observed_at: "2026-09-02T18:00:00+00:00",
    age_hours: 0.4,
    freshest_observed_at: "2026-09-02T18:00:00+00:00",
    freshest_age_hours: 0.4,
    stale_outcomes: [],
    mixed_freshness: false,
    outcomes: [
      {
        entity_key: `${key}:yes`,
        display_name: "Yes",
        probability: Number((0.62 - i * 0.07).toFixed(3)),
        probability_is_live: true,
        observed_at: "2026-09-02T18:00:00+00:00",
        age_hours: 0.4,
        price_state: "live",
        is_answer: true,
      },
    ],
  };
});

const SYN_MATCHES = buildMatchList({ rounds: SYN_ROUNDS, slate: SYN_SLATE });
const SYN_GRID: GridModel = buildPlayoffGrid({
  board: SYN_BOARD,
  propMarkets: SYN_PROPS,
  matches: SYN_MATCHES,
  draw: "mens-singles",
});

describe("the bracket capture rig still renders every state", () => {
  it("renders the pre-ceremony state WITH both winner boards", () => {
    const html = renderToStaticMarkup(
      <TournamentBracket grid={null} drawReleased={false} preDrawBoards={PAYLOAD.boards} />
    );
    expect(html).toContain('data-testid="bracket-unreleased"');
    expect((html.match(/data-testid="tournament-board"/g) ?? []).length).toBe(2);
  });

  it("the REAL grid is sparse, and the artifact must not pretend otherwise", () => {
    // The honest state, asserted rather than described. Today we price eight
    // advance markets across both draws and one title column each; the middle
    // is holes, and the panel says so with a counter.
    const grid = realGrid(MEN);
    expect(grid.rows.length).toBe(MEN.rows.length);
    expect(grid.pricedCells).toBeLessThan(grid.totalCells);
    expect(grid.columns.map((c) => c.key)).toContain("title");
    // Alcaraz and Zverev have curated semi-final markets; Djokovic and Shelton
    // quarter-finals. If the committed props file goes stale this drops to a
    // one-column grid and the panel silently becomes the board again.
    expect(grid.columns.filter((c) => c.kind === "reach").length).toBeGreaterThan(0);
  });

  it("the women's grid is a genuinely different field, not the men's twice", () => {
    const men = renderToStaticMarkup(<PlayoffGrid grid={realGrid(MEN)} />);
    const women = renderToStaticMarkup(<PlayoffGrid grid={realGrid(WOMEN)} />);
    expect(men).toContain("Alcaraz");
    expect(women).toContain("Sabalenka");
    expect(women).not.toContain("Alcaraz");
  });

  it("the SECOND-WEEK grid is dense, so the design can be judged apart from the data", () => {
    expect(SYN_GRID.columns.length).toBeGreaterThan(2);
    expect(SYN_GRID.pricedCells).toBeGreaterThan(SYN_GRID.rows.length);
    // A played round produces reached ticks; a lost one produces an out row.
    const states = SYN_GRID.rows.flatMap((r) => Object.values(r.cells).map((c) => c.state));
    expect(states).toContain("priced");
  });

  it("never puts more than four numeric columns on a phone", () => {
    for (const grid of [realGrid(MEN), realGrid(WOMEN), SYN_GRID]) {
      expect(grid.columns.length).toBeLessThanOrEqual(4);
    }
  });

  it("the committed props file really carries the advance-to-stage markets", () => {
    // If this file goes stale, every reach column silently disappears and the
    // grid degrades to a one-column copy of the championship board.
    expect(PROPS.length).toBe(11);
    const advance = PROPS.filter((p) => /(-semifinals|-quarterfinals|-round-of-16)$/.test(p.key));
    expect(advance.length).toBe(8);
  });

  it("writes the capture when UX_CAPTURE_DIR is set", () => {
    const dir = process.env.UX_CAPTURE_DIR;
    if (!dir) {
      expect(true).toBe(true);
      return;
    }
    fs.mkdirSync(dir, { recursive: true });

    const phone = (
      caption: string,
      note: string,
      body: React.ReactElement,
      women = false,
      showPills = true
    ) => `
  <div class="col">
    <div class="cap">${caption}</div>
    <div class="phone">
      <header class="hero"><h1>US Open 2026</h1><p>Flushing Meadows &middot; 08-30 to 09-13</p></header>
      <div class="tabs"><span>Tournament</span><span class="on">Bracket</span></div>
      ${
        showPills
          ? `<div class="pills"><span${women ? "" : ' class="on"'}>Men's</span><span${
              women ? ' class="on"' : ""
            }>Women's</span></div>`
          : ""
      }
      <div class="pad">${renderToStaticMarkup(body)}</div>
    </div>
    <div class="sub">${note}</div>
  </div>`;

    const html = `<!doctype html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>US Open — the Bracket tab is the playoff grid (ruling 4)</title>
<style>${appStylesheet()}</style>
<style>
  body{background:#F5F5F7;margin:0;font-family:-apple-system,BlinkMacSystemFont,"SF Pro Text",Segoe UI,Roboto,sans-serif}
  .note{max-width:1300px;margin:0 auto;padding:16px;font-size:12.5px;line-height:1.6;color:#374151;background:#fff;border-bottom:1px solid #E5E7EB}
  .note b{color:#111827}
  .note ol{margin:8px 0 0;padding-left:20px}
  .note li{margin-bottom:5px}
  .warn{background:#FFFBEB;border:1px solid #FDE68A;border-radius:10px;padding:11px 14px;margin:10px 0 0}
  .rail{display:flex;gap:22px;justify-content:center;align-items:flex-start;flex-wrap:wrap;padding:20px 16px 60px;max-width:1400px;margin:0 auto}
  .col{width:390px}
  .phone{width:390px;background:#F5F5F7;border:1px solid #E5E7EB;border-radius:12px;overflow:hidden;max-height:820px;overflow-y:auto}
  .cap{font:700 11.5px inherit;letter-spacing:.07em;text-transform:uppercase;color:#6B7280;padding:0 2px 7px}
  .sub{padding:9px 2px 0;font-size:11.5px;line-height:1.5;color:#6B7280}
  .sub b{color:#111827}
  .tabs{display:flex;border-bottom:1px solid #E5E7EB;background:#fff}
  .tabs span{flex:1;text-align:center;padding:13px 0;font:600 13.5px inherit;color:#9CA3AF;border-bottom:2px solid transparent}
  .tabs span.on{color:#111827;border-bottom-color:#111827}
  .pills{display:flex;gap:6px;padding:0 16px 12px;background:#fff;border-bottom:1px solid #E5E7EB}
  .pills span{border-radius:999px;padding:6px 14px;font:600 13px inherit;background:#F0F0F2;color:#6B7280}
  .pills span.on{background:#111827;color:#F8FAFC}
  header.hero{padding:16px;background:#fff;border-bottom:1px solid #E5E7EB}
  header.hero h1{margin:0;font-size:24px;letter-spacing:-.02em;color:#111827}
  header.hero p{margin:2px 0 0;font-size:13px;color:#6B7280}
  .pad{padding:16px}
  .lead{background:#111827;color:#F8FAFC;padding:10px 16px;font:700 12px inherit;letter-spacing:.06em;text-transform:uppercase}
</style></head>
<body>
<div class="note">
<b>The Bracket tab is the PLAYOFF GRID &mdash; your ruling 4, adopted.</b> These are the SHIPPED
components and the app's own compiled CSS at a 390px viewport. Each phone scrolls.
<ol>
<li><b>Adopted, not countered.</b> You invited a counter-structure and asked for both rendered if
one existed. There isn't one worth your time, and the one-paragraph argument is in the report: the
tree was measured unusable on a phone at UX-P136, one-round-at-a-time turned this tab into a second
match list, and the grid is the only structure tried that answers &ldquo;how far does this player
get&rdquo; without either. The match list moved to the Tournament tab
(<code>us-open-reskin.html</code>), which is the other half of the ruling.</li>
<li><b>Every cell is a market's answer to exactly its own column.</b> Three sources: your own match
price for the next round, the register's curated &ldquo;does X reach the Y&rdquo; markets for the
middle, and the championship board for the title. <b>Nothing is chained or simulated.</b> A grid of
P(reach round N) is trivial to fill by multiplying match odds down the draw; it would be dense
where this one is sparse and every number in it would be a model output printed in the type this
app reserves for a price.</li>
<li><b>Ruling 3 applied: &ldquo;priced to get there&rdquo; is gone.</b> The section reads
<b>&ldquo;Chance of reaching&rdquo;</b>. <i>Priced</i> is a trading verb and <i>get there</i> is a
bet's payoff condition. Runners-up rejected: &ldquo;Odds of reaching&rdquo; (the exact word the
site's no-price-format rule exists to avoid) and &ldquo;Progression&rdquo; (accurate, and jargon).</li>
<li><b>Ruling 8 applied: the eight &ldquo;Does Gauff reach the semifinals?&rdquo; cards are cells
now,</b> not props. They were eight near-identical cards in a section meant for interesting
questions &mdash; both the wrong home and the repeating template the same ruling forbids.</li>
</ol>
<div class="warn">
<b>THE HONEST PART, and it is the thing to look at first.</b> Panels 2 and 3 are what you get
tomorrow, on real data, and the middle of that grid is mostly holes: we price <b>eight</b>
advance-to-round questions across both draws and one title column each. The dense
&ldquo;next round&rdquo; column needs main-draw match prices and <code>build_slate</code> serves
qualifying only. Panels 4-6 are a SECOND-WEEK state built on the synthetic draw so you can verdict
the DESIGN separately from the data poverty &mdash; and so the ask (curate more reach markets,
price the main draw) is visible rather than a promise. <b>The tab is also still called
&ldquo;Bracket&rdquo; and holds no bracket</b>; that is one line in <code>TABS</code> if you want
&ldquo;Path&rdquo; instead.
</div>
</div>

<div class="lead">1 &mdash; What a visitor sees today, and until the ceremony (UX-P137 ruling 1, unchanged)</div>
<div class="rail">
${phone(
  "1 &middot; Before the draw",
  "Real production boards, both draws, unfiltered by the gender pill. The tradeable truth about this tournament on the day before a ceremony.",
  <TournamentBracket grid={null} drawReleased={false} preDrawBoards={PAYLOAD.boards} />,
  false,
  false
)}
</div>

<div class="lead">2 &mdash; The grid on REAL data: what tomorrow actually looks like</div>
<div class="rail">
${phone(
  "2 &middot; Men's &mdash; real boards, real markets",
  "36 contenders, 4 curated reach markets, 36 title prices. The legend under the grid states its own coverage &mdash; a sparse grid that does not say it is sparse reads as a rendering fault.",
  <PlayoffGrid grid={realGrid(MEN)} drawLabel={MEN.label} />
)}
${phone(
  "3 &middot; Women's &mdash; real boards, real markets",
  "44 contenders and 4 curated reach markets, including the only round-of-16 one we hold. A genuinely different field, same component.",
  <PlayoffGrid grid={realGrid(WOMEN)} drawLabel={WOMEN.label} />,
  true
)}
${phone(
  "4 &middot; Men's &mdash; the same grid, expanded",
  "What &ldquo;Show all 36&rdquo; opens onto. Every row the board holds, most of them title-only, which is the honest shape of the field.",
  <PlayoffGrid grid={realGrid(MEN)} drawLabel={MEN.label} initialExpanded />
)}
</div>

<div class="lead">3 &mdash; The grid in the second week: the design, judged apart from the data</div>
<div class="rail">
${phone(
  "5 &middot; Second week &mdash; dense",
  "SYNTHETIC draw and SYNTHETIC main-draw match prices. Next round from the match market, quarter-finals from curated markets, title from the board. This is the shape the grid is FOR.",
  <PlayoffGrid grid={SYN_GRID} drawLabel="Men's Singles" />
)}
${phone(
  "6 &middot; Second week &mdash; expanded",
  "Sixteen survivors, four columns, holes where nobody prices the question. The ✓ is a round already reached; a knocked-out player's whole row goes to em-dashes.",
  <PlayoffGrid grid={SYN_GRID} drawLabel="Men's Singles" initialExpanded />
)}
${phone(
  "7 &middot; A round that does not fit",
  "The width cap, said out loud. Three reach columns plus the title is what 390px holds; a fourth reach round is NAMED in the legend rather than dropped silently.",
  <PlayoffGrid
    grid={buildPlayoffGrid({
      board: SYN_BOARD,
      propMarkets: [
        ...SYN_PROPS,
        {
          ...SYN_PROPS[0],
          key: "extra-final",
          title: `Does ${SYN_BOARD.rows[0].display_name.split(" ").slice(-1)[0]} reach the final?`,
          answer_entity_key: "extra-final:yes",
          outcomes: [{ ...SYN_PROPS[0].outcomes[0], entity_key: "extra-final:yes", probability: 0.31 }],
        },
      ],
      matches: SYN_MATCHES,
      draw: "mens-singles",
    })}
    drawLabel="Men's Singles"
  />
)}
</div>
</body></html>`;

    const out = path.join(dir, "us-open-bracket.html");
    fs.writeFileSync(out, html);

    // The rig must not silently write a page whose panels failed to render.
    expect(fs.existsSync(out)).toBe(true);
    expect(html.length).toBeGreaterThan(20000);

    // ---- one assertion per claim the page makes, so no panel goes empty ----
    // Ruling 1's pre-draw panel still carries BOTH boards.
    expect(html).toContain('data-testid="bracket-unreleased"');
    expect((html.match(/data-testid="tournament-board"/g) ?? []).length).toBe(2);
    // Ruling 4: the grid rendered, with rows and real cells, on every panel.
    expect((html.match(/data-testid="playoff-grid"/g) ?? []).length).toBe(6);
    expect((html.match(/data-testid="grid-row"/g) ?? []).length).toBeGreaterThan(40);
    expect((html.match(/data-origin="curated"/g) ?? []).length).toBeGreaterThan(4);
    expect((html.match(/data-origin="board"/g) ?? []).length).toBeGreaterThan(20);
    expect(html).toContain('data-origin="match"');
    // Ruling 3: the gambling phrasing is gone and the probability phrasing is in.
    expect(html).toContain("Chance of reaching");
    expect(html).not.toContain("Priced to get there");
    // Ruling 2's vocabulary: each column still names its own question.
    expect(html).toContain("To win the title");
    expect(html).toContain("To reach the");
    // The holes are visible AND explained — this is the honesty claim.
    expect(html).toContain('data-state="unpriced"');
    expect(html).toContain("Not priced");
    expect(html).toContain('data-testid="grid-coverage"');
    // The width cap is never silent.
    expect(html).toContain('data-testid="grid-dropped-columns"');
    // Both draws, which is the half of the ask a single-draw capture would miss.
    expect(html).toContain("Alcaraz");
    expect(html).toContain("Sabalenka");
    // Collapsed AND expanded are both on the page.
    expect(html).toContain("Show all 36");
    // And the stylesheet actually loaded — an unstyled capture is not a verdict.
    expect(appStylesheet().length).toBeGreaterThan(1000);
  });
});
