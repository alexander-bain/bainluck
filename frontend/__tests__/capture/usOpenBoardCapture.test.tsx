/**
 * CAPTURE RIG — the real /tournaments/us-open hub, over real production data.
 *
 * Chromium is dead in this sandbox (Mach bootstrap denied), so a screenshot is
 * not available to this lane. This is the substitute the repo already uses:
 * render the ACTUAL shipped components with `renderToStaticMarkup`, wrap them
 * in the app's OWN compiled stylesheet from `.next/static/css`, and write a
 * self-contained HTML file Alex can open. Real components, real CSS, real
 * numbers — not a re-creation of the page in mock markup.
 *
 * Two jobs, and the second is why it lives under `__tests__`:
 *
 *   1. `UX_CAPTURE_DIR=<dir> npx jest --testPathPatterns=usOpenBoardCapture`
 *      writes `us-open-reskin.html` at a 390px mobile viewport.
 *   2. With no env var set it is an ordinary test that renders every state and
 *      asserts the rig still works.
 *
 * The payloads are produced by the BACKEND's own `build_boards`, `build_slate`
 * and `build_props` over bounded production reads, so this file exercises both
 * halves end to end: if the Python changes shape, the render breaks here.
 *
 * UX-P138 re-renders it with Alex's rulings 1, 2, 4, 5, 6, 7 and 8 applied.
 * The biggest change is structural: the Tournament tab's spine is now ONE
 * match list with round pills (`TournamentMatches`), because the slate and the
 * bracket's match cards were always the same list split by pipeline.
 *
 * WHAT IS SYNTHETIC, and why any of it is: the boards, the slate and the
 * curated questions are committed production reads. Three panels are not, and
 * each says so on its own caption — decided matches with scores, a multi-round
 * pill strip, and a freshly-priced questions section. All three demonstrate
 * seams our pipeline does not fill yet, and the alternative to synthesising
 * them is a sentence promising Alex they will look fine.
 */

import React from "react";
import { renderToStaticMarkup } from "react-dom/server";
import fs from "node:fs";
import path from "node:path";

import ContenderChart from "@/components/tournament/ContenderChart";
import TournamentBoard from "@/components/tournament/TournamentBoard";
import TournamentBracket from "@/components/tournament/TournamentBracket";
import TournamentMatches from "@/components/tournament/TournamentMatches";
import TournamentProps from "@/components/tournament/TournamentProps";
import {
  chartSeriesFor,
  defaultSelection,
  seriesColorByEntity,
  toggleSelection,
} from "@/lib/contenderChart";
import { buildMatchList, type MatchListEntry, type TitleChances } from "@/lib/matchList";
import { buildPlayoffGrid } from "@/lib/playoffGrid";
import { slateNotice, type Broadcast, type SlateData, type SlateMatch } from "@/lib/slate";
import type { PropMarket } from "@/lib/tournamentProps";
import type { TournamentBoardData, TournamentPayload } from "@/lib/tournament";

const MOCKS = path.join(__dirname, "..", "..", "..", "docs", "mocks", "us-open");
const SLATE_PATH = path.join(MOCKS, "slate-2026-08-25.json");
const PAYLOAD_PATH = path.join(MOCKS, "payload-2026-08-25.json");
const PROPS_PATH = path.join(MOCKS, "props-2026-08-26.json");

function loadPayload(): TournamentPayload {
  return JSON.parse(fs.readFileSync(PAYLOAD_PATH, "utf8")) as TournamentPayload;
}
function loadSlate(): SlateData {
  return JSON.parse(fs.readFileSync(SLATE_PATH, "utf8")) as SlateData;
}
function loadProps(): PropMarket[] {
  return JSON.parse(fs.readFileSync(PROPS_PATH, "utf8")) as PropMarket[];
}

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

const BROADCASTS: Broadcast[] = [
  { region: "US", channels: ["ESPN", "ESPN2", "ESPN+"], note: null },
  { region: "UK", channels: ["Sky Sports Tennis"], note: null },
  { region: "AU", channels: ["Stan Sport"], note: null },
];

/**
 * The same board, with the server-owned liveness fields set to live.
 *
 * SYNTHETIC, deliberately derived rather than hand-written: it starts from the
 * real production board so the row shape, the field set and the trend arrays
 * are whatever the backend actually emits today. Only the four fields the
 * server owns for liveness are moved. A hand-authored "live board" literal
 * would pass forever after the real payload changed shape underneath it.
 */
function makeLiveBoard(board: TournamentBoardData): TournamentBoardData {
  return {
    ...board,
    price_state: "live",
    age_hours: 0.2,
    newest_observed_at: "2026-08-25T23:20:00+00:00",
    rows: board.rows.map((row) => ({
      ...row,
      probability_is_live: true,
      price_state: "live",
      age_hours: 0.2,
      observed_at: "2026-08-25T23:20:00+00:00",
    })),
  };
}

function titleChancesFor(board: TournamentBoardData): TitleChances {
  const out: TitleChances = {};
  for (const row of board.rows) out[row.entity_key] = row.probability;
  return out;
}

/**
 * ONE match list for a draw — the join `page.tsx` performs (ruling 4).
 *
 * Kept in a helper so the artifact renders through the SAME call the page
 * makes. A capture that assembled its own entry list would be a drawing of the
 * page rather than the page.
 */
function matchesFor(
  slate: SlateData,
  board: TournamentBoardData,
  extra: SlateMatch[] = []
): MatchListEntry[] {
  return buildMatchList({
    slate: [...slate.matches.filter((m) => m.draw === board.draw), ...extra],
    titleChances: titleChancesFor(board),
    broadcasts: BROADCASTS,
  });
}

/**
 * MAIN-DRAW matches between board contenders — Alex's ruling 1, demonstrated.
 *
 * SYNTHETIC FIXTURES, real players, REAL TITLE PRICES, and it has to be
 * synthetic for a reason worth stating: `build_slate` prices the qualifying
 * draw and nothing else, so **not one match we serve today involves a player
 * the championship board holds** — there is a test above that measures exactly
 * that and expects zero overlap. Ruling 1's whole subject is a row carrying
 * both a match number and a title chip, and on real data no such row exists.
 * Pairing the top of the board against itself is the smallest thing that puts
 * the treatment on screen without inventing a price the board did not publish:
 * the CHIPS are production numbers, only the fixtures and the match odds are
 * made up.
 */
function mainDrawFrom(board: TournamentBoardData, template: SlateMatch): SlateMatch[] {
  const rows = board.rows.slice(0, 10);
  const out: SlateMatch[] = [];
  for (let i = 0; i + 1 < rows.length; i += 2) {
    const favourite = Number((0.52 + ((i * 9) % 30) / 100).toFixed(2));
    out.push({
      ...template,
      matchup_key: `main-draw-${i}`,
      draw: board.draw,
      draw_label: board.label,
      round: "R128",
      scheduled_date: "2026-08-31T17:00:00+00:00",
      probability_is_live: true,
      price_state: "live",
      age_hours: 0.2,
      sides: [
        {
          ...template.sides[0],
          entity_key: rows[i].entity_key,
          display_name: rows[i].display_name,
          seed: rows[i].seed,
          probability: favourite,
          opening_probability: Number((favourite - 0.04).toFixed(2)),
          move: 0.04,
        },
        {
          ...template.sides[1],
          entity_key: rows[i + 1].entity_key,
          display_name: rows[i + 1].display_name,
          seed: rows[i + 1].seed,
          probability: Number((1 - favourite).toFixed(2)),
          opening_probability: Number((1 - favourite + 0.04).toFixed(2)),
          move: -0.04,
        },
      ],
      favourite: rows[i].entity_key,
      has_moved: true,
    });
  }
  return out;
}

/**
 * DECIDED matches with scores — Alex's ruling 2, demonstrated on real names.
 *
 * SYNTHETIC, and the report is blunt about why it has to be: **nothing in this
 * codebase holds the result of a tennis match.** Not the register, not
 * `build_slate`, not `build_bracket`. There is no field to read and no feed
 * behind one. `winner_entity_key` and `score` are seams added by UX-P138 so
 * that the day a result feed lands it is an ingest change; this fills them by
 * hand, over real players, so the rendering can be verdicted now.
 */
const SCORES = ["6-1, 6-4", "7-6(4), 3-6, 6-2", "6-4, 7-5", "2-6, 6-3, 7-6(5)"];
function decidedFrom(matches: SlateMatch[]): SlateMatch[] {
  return matches.slice(0, 4).map((match, i) => ({
    ...match,
    matchup_key: `${match.matchup_key}:decided`,
    // The favourite loses one of the four — a fixture where the winner always
    // carries the bigger number lets a component that simply prints them in
    // winner-first order pass.
    winner_entity_key: match.sides[i === 2 ? 1 : 0].entity_key,
    score: SCORES[i],
    probability_is_live: false,
    price_state: "stale" as const,
  }));
}

/** A multi-round strip — the pill control has one round to show on real data. */
function reRound(matches: SlateMatch[], round: string, tag: string): SlateMatch[] {
  return matches.map((match) => ({
    ...match,
    matchup_key: `${match.matchup_key}:${tag}`,
    round,
  }));
}

/**
 * A freshly-priced questions section — ruling 8, with content.
 *
 * SYNTHETIC for the reason the panel states: applied to today's register the
 * rotation rule empties the section, because all three non-advance markets we
 * curate are dark (188 hours and 810 hours). That is the true state and panel
 * 1 shows it. This is what the same section looks like once somebody curates.
 */
function freshQuestions(source: PropMarket[]): PropMarket[] {
  const fun = source.filter((p) => !/-(semifinals|quarterfinals|round-of-16)$/.test(p.key));
  return fun.map((market) => ({
    ...market,
    price_state: "live",
    age_hours: 0.4,
    freshest_age_hours: 0.4,
    stale_outcomes: [],
    outcomes: market.outcomes.map((outcome) => ({
      ...outcome,
      probability_is_live: true,
      price_state: "live" as const,
      age_hours: 0.4,
    })),
  }));
}

describe("US Open board capture rig", () => {
  const payload = loadPayload();

  it("has a payload with both draws", () => {
    expect(payload.boards).toHaveLength(2);
    expect(payload.boards.map((b) => b.draw)).toEqual(["mens-singles", "womens-singles"]);
  });

  it("carries the real field, not a fixture", () => {
    const men = payload.boards[0];
    expect(men.rows.length).toBeGreaterThan(20);
    expect(men.rows[0].display_name).toBeTruthy();
    expect(men.rows[0].probability).toBeGreaterThan(0);
  });

  it("PRODUCTION STATE 2026-08-25: every row is non-live (#2199)", () => {
    // This documents why the honesty treatment is the whole page this weekend
    // rather than an edge case.
    //
    // CORRECTED 2026-08-25 (UX-P134): the sentence that used to sit here said
    // this test SHOULD start failing when #2199 was fixed. It cannot. It reads
    // a COMMITTED payload, so it is pinned to a file in this repo and can
    // never observe production. It stayed green through the entire landing of
    // #2199 while the boards stayed dark, and a green here would have read as
    // "not fixed yet" when the truth was "fixed and not working".
    //
    // What it actually proves: the renderer handles a dark board correctly.
    // Its live-side twin below is a SEPARATE test, not a replacement.
    const allRows = payload.boards.flatMap((b) => b.rows);
    expect(allRows.length).toBeGreaterThan(60);
    expect(allRows.every((r) => r.probability_is_live === false)).toBe(true);
    expect(payload.boards.every((b) => b.price_state === "dark")).toBe(true);
  });

  it("LIVE PATH: a live board renders confidently, with no age label and no banner", () => {
    const live = makeLiveBoard(payload.boards[0]);
    const html = renderToStaticMarkup(<TournamentBoard board={live} />);
    expect(html).toContain('data-live="true"');
    expect(html).not.toContain('data-live="false"');
    expect(html).not.toContain("Prices paused");
    expect(html).not.toContain('data-testid="row-age"');
    const perRow = html.split('data-testid="board-row"').slice(1);
    expect(perRow.length).toBe(3);
    for (const row of perRow) {
      expect((row.match(/data-testid="row-probability"/g) ?? []).length).toBe(1);
    }
  });

  it("renders both boards without throwing, and says prices are paused", () => {
    const html = payload.boards
      .map((board) => renderToStaticMarkup(<TournamentBoard board={board} />))
      .join("");
    expect(html).toContain("Prices paused");
    expect(html).toContain('data-live="false"');
    expect(html).not.toContain('data-live="true"');
  });

  it("the slate payload is real production data, not a fixture", () => {
    const slate = loadSlate();
    expect(slate.matches.length).toBeGreaterThan(30);
    expect(slate.incoherent).toBe(0);
    for (const match of slate.matches) {
      expect(match.sides).toHaveLength(2);
      for (const side of match.sides) {
        expect(["Yes", "No", ""]).not.toContain(side.display_name);
      }
    }
  });

  it("the props payload is register v4's ELEVEN, not UX-P134's four", () => {
    const props = loadProps();
    expect(props).toHaveLength(11);
    expect(props.filter((p) => p.draw === "womens-singles")).toHaveLength(4);
    expect(props.filter((p) => /(-semifinals|-quarterfinals|-round-of-16)$/.test(p.key)))
      .toHaveLength(8);
  });

  it("RULING 8 ON REAL DATA: the questions section is EMPTY, and says why", () => {
    // The finding, asserted so it cannot be softened into a caption. Every
    // non-advance market we curate is dark: `sinner-competes` at 188 hours,
    // both `*-second-major` at 810. Applying the rotation Alex asked for
    // empties the section on both draws today.
    const props = loadProps();
    for (const draw of ["mens-singles", "womens-singles"]) {
      const html = renderToStaticMarkup(<TournamentProps markets={props} draw={draw} />);
      expect(html).toContain('data-testid="props-empty"');
      expect(html).toContain('data-testid="props-moved-to-grid"');
    }
    const men = renderToStaticMarkup(<TournamentProps markets={props} draw="mens-singles" />);
    expect(men).toContain("gone dark and rotated out");
  });

  it("the re-skinned board collapses to three rows with an expander", () => {
    const women = payload.boards[1];
    expect(women.rows.length).toBeGreaterThan(20);
    const html = renderToStaticMarkup(<TournamentBoard board={women} />);
    expect((html.match(/data-testid="board-row"/g) ?? []).length).toBe(3);
    expect(html).toContain(`Show all ${women.rows.length}`);
  });

  it("the chart draws three lines and no more, by default", () => {
    const board = payload.boards[0];
    const html = renderToStaticMarkup(
      <ContenderChart
        rows={board.rows}
        draw={board.draw}
        selection={defaultSelection(board.rows)}
        onToggle={() => {}}
      />
    );
    expect((html.match(/data-testid="chart-legend-item"/g) ?? []).length).toBe(3);
    expect((html.match(/data-testid="chart-series"/g) ?? []).length).toBeLessThanOrEqual(3);
  });

  it("the chart is no longer inside the board — it moved up the page", () => {
    const html = renderToStaticMarkup(<TournamentBoard board={payload.boards[0]} />);
    expect(html).not.toContain('data-testid="contender-chart"');
  });

  it("does NOT copy the reference's two-sided price pills", () => {
    // Adaptation, not imitation: Kalshi's rows carry green/red YES/NO pills.
    // That is a trading format. Our rows print ONE blended probability.
    const html = renderToStaticMarkup(<TournamentBoard board={payload.boards[0]} />);
    const perRow = html.split('data-testid="board-row"').slice(1);
    expect(perRow.length).toBe(3);
    for (const row of perRow) {
      expect((row.match(/data-testid="row-probability"/g) ?? []).length).toBe(1);
    }
  });

  it("RULING 1 ON REAL DATA: match rows carry the title chip when the board prices it", () => {
    // Today's slate is all qualifiers and NONE of them is a board contender,
    // so no real row can carry a chip. Stated here as a measurement rather
    // than discovered as a blank in the artifact.
    const slate = loadSlate();
    const board = payload.boards[0];
    const keys = new Set(board.rows.map((r) => r.entity_key));
    const overlap = slate.matches
      .flatMap((m) => m.sides.map((s) => s.entity_key))
      .filter((key) => keys.has(key));
    expect(overlap).toHaveLength(0);
    // And the chip appears the moment one of them IS a contender.
    const contender = board.rows[0];
    const synthetic: SlateMatch = {
      ...slate.matches[0],
      matchup_key: "chip-probe",
      draw: board.draw,
      sides: [
        { ...slate.matches[0].sides[0], entity_key: contender.entity_key, display_name: contender.display_name },
        slate.matches[0].sides[1],
      ],
    };
    // Expanded, because the probe row sorts to the end of 31 qualifiers and
    // the list collapses to five — a chip assertion against a collapsed list
    // would be asserting about rows that are not on screen.
    const html = renderToStaticMarkup(
      <TournamentMatches entries={matchesFor(slate, board, [synthetic])} initialExpanded />
    );
    expect(html).toContain('data-testid="match-title-chip"');
  });

  it("writes the capture when UX_CAPTURE_DIR is set", () => {
    const dir = process.env.UX_CAPTURE_DIR;
    if (!dir) {
      expect(true).toBe(true);
      return;
    }
    fs.mkdirSync(dir, { recursive: true });

    const slate = loadSlate();
    const props = loadProps();
    const men = payload.boards[0];
    const women = payload.boards[1];

    const menMatches = matchesFor(slate, men);
    const womenMatches = matchesFor(slate, women);
    const menSlate = slate.matches.filter((m) => m.draw === "mens-singles");

    /**
     * THE PAGE, in its UX-P138 order: chart, then the match list with round
     * pills, then the championship board, then the curated questions.
     */
    const panel = (
      board: TournamentBoardData,
      entries: MatchListEntry[],
      options: {
        chartExtra?: Record<string, unknown>;
        selection?: string[];
        matchExtra?: Record<string, unknown>;
        propMarkets?: PropMarket[];
      } = {}
    ) => {
      const selection = options.selection ?? defaultSelection(board.rows);
      return `
      <div class="pad">
        ${renderToStaticMarkup(
          <ContenderChart
            rows={board.rows}
            draw={board.draw}
            selection={selection}
            onToggle={() => {}}
            onReset={() => {}}
            {...(options.chartExtra ?? {})}
          />
        )}
        ${renderToStaticMarkup(
          <TournamentMatches
            entries={entries}
            notice={slateNotice(slate)}
            {...(options.matchExtra ?? {})}
          />
        )}
        ${renderToStaticMarkup(
          <TournamentBoard
            board={board}
            seriesColors={seriesColorByEntity(chartSeriesFor(board.rows, selection))}
          />
        )}
        ${renderToStaticMarkup(
          <TournamentProps markets={options.propMarkets ?? props} draw={board.draw} />
        )}
      </div>`;
    };

    const phone = (title: string, sub: string, body: string, women_ = false) => `
  <div class="phone">
    <header class="hero"><h1>${title}</h1><p>${sub}</p></header>
    <div class="tabs"><span class="on">Tournament</span><span>Bracket</span></div>
    <div class="pills"><span${women_ ? "" : ' class="on"'}>Men's</span><span${
      women_ ? ' class="on"' : ""
    }>Women's</span></div>
    ${body}
  </div>`;

    // A fourth line added by the picker — shows the added colour AND the reset.
    const withFourth = toggleSelection(
      defaultSelection(men.rows),
      men.rows[7]?.entity_key ?? men.rows[3].entity_key
    );

    // Ruling 1: main-draw fixtures between board contenders, so the two-number
    // treatment is on screen at all. See `mainDrawFrom` for why no real row
    // can carry a title chip today.
    const mainDraw = mainDrawFrom(men, menSlate[0]);
    const mainDrawEntries = buildMatchList({
      slate: mainDraw,
      titleChances: titleChancesFor(men),
      broadcasts: BROADCASTS,
    });

    // Ruling 2: those same fixtures, decided, with hand-written scores.
    const decidedEntries = buildMatchList({
      slate: decidedFrom(mainDraw),
      titleChances: titleChancesFor(men),
      broadcasts: BROADCASTS,
    });

    // Ruling 4: the pill strip with something to switch between.
    const multiRound = buildMatchList({
      slate: [
        ...menSlate.slice(0, 8),
        ...reRound(menSlate.slice(8, 20), "R128", "r128"),
        ...reRound(menSlate.slice(20, 26), "R64", "r64"),
      ],
      titleChances: titleChancesFor(men),
      broadcasts: BROADCASTS,
    });

    // Ruling 7: one row's detail view open.
    const detailOpenId = mainDrawEntries[0]?.id;

    const grid = buildPlayoffGrid({
      board: men,
      propMarkets: props,
      matches: menMatches,
      draw: "mens-singles",
    });
    const preDraw = renderToStaticMarkup(
      <TournamentBracket grid={null} drawReleased={false} preDrawBoards={payload.boards} />
    );
    const gridHtml = renderToStaticMarkup(
      <TournamentBracket grid={grid} drawReleased drawLabel={men.label} />
    );

    const live = slate.matches.filter((m) => m.probability_is_live).length;

    const html = `<!doctype html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>${payload.title} — hub, UX-P138 rulings applied</title>
<style>${appStylesheet()}</style>
<style>
  body{background:#F5F5F7;margin:0;font-family:-apple-system,BlinkMacSystemFont,"SF Pro Text",Segoe UI,Roboto,sans-serif}
  .rail{display:flex;gap:24px;justify-content:center;align-items:flex-start;flex-wrap:wrap;padding:0 16px 40px}
  .phone{width:390px;background:#F5F5F7;border:1px solid #E5E7EB;border-radius:12px;overflow:hidden;max-height:900px;overflow-y:auto}
  .note{max-width:1240px;margin:0 auto;padding:14px 16px;font-size:12.5px;line-height:1.55;color:#374151;background:#fff;border-bottom:1px solid #E5E7EB}
  .note b{color:#111827}
  .note ol{margin:8px 0 0;padding-left:20px}
  .note li{margin-bottom:5px}
  .cap{max-width:1240px;margin:18px auto 8px;padding:0 16px;font:700 12px inherit;letter-spacing:.07em;text-transform:uppercase;color:#9CA3AF}
  .pick{max-width:1240px;margin:14px auto;padding:12px 16px;background:#FFFBEB;border:1px solid #FDE68A;border-radius:10px;font-size:12.5px;line-height:1.6;color:#374151}
  .pick b{color:#111827}
  .tabs{display:flex;border-bottom:1px solid #E5E7EB;background:#fff}
  .tabs span{flex:1;text-align:center;padding:13px 0;font:600 13.5px inherit;color:#9CA3AF;border-bottom:2px solid transparent}
  .tabs span.on{color:#111827;border-bottom-color:#111827}
  .pills{display:flex;gap:6px;padding:0 16px 12px;background:#fff;border-bottom:1px solid #E5E7EB}
  .pills span{border-radius:999px;padding:6px 14px;font:600 13px inherit;background:#F0F0F2;color:#6B7280}
  .pills span.on{background:#111827;color:#F8FAFC}
  header.hero{padding:16px;background:#fff;border-bottom:1px solid #E5E7EB}
  header.hero h1{margin:0;font-size:24px;letter-spacing:-.02em;color:#111827}
  header.hero p{margin:2px 0 0;font-size:13px;color:#6B7280}
  .pad{padding:0 16px 32px}
</style></head>
<body>
<div class="note">
<b>US Open hub &mdash; your eight rulings applied.</b> SHIPPED components, the app's own compiled
CSS, a 390px viewport. Each phone scrolls.
<ol>
<li><b>Ruling 4 &mdash; the Tournament tab is THE MATCH LIST with round pills.</b> The slate and the
Bracket tab's match cards were two lists of the same fixtures split by which pipeline made them;
they are one list now, and a draw position that also appears in the slate absorbs it rather than
rendering twice. Pills only appear for rounds that HAVE matches &mdash; today that is one, so the
strip is suppressed (panels 1-2) and panel 7 shows it with three.</li>
<li><b>Ruling 1 &mdash; match odds everywhere, title chance as a muted chip.</b> Big number: to win
this match. Grey chip after the name: <code>22% title</code>, and it says the word so a bare
percentage can never mean two things again. The density answer is that ONE number is big, the
second is a chip, and the sentence that used to sit under both is gone.</li>
<li><b>Ruling 6 &mdash; the redundancy is dead at the source.</b> <code>matchNarrative</code> is
deleted, not just unrendered. A flat row now says nothing, which is the information. The one
genuinely additive fact &mdash; the OPENING price &mdash; moved into the tapped detail.</li>
<li><b>Ruling 7 &mdash; where to watch is on the DETAIL view.</b> Tap a row (panel 6). It is in
exactly one place, and it is not on the closed row.</li>
<li><b>Ruling 2 &mdash; decided matches print the score with the outcome</b> (panel 9).</li>
<li><b>Ruling 5 &mdash; the picker got a filter and a way back</b> (panels 3-5).</li>
<li><b>Ruling 8 &mdash; the questions section rotates</b> (panels 1-2 and 10).</li>
</ol>
<b>Boards:</b> real production read, ${men.rows.length + women.rows.length} registered contenders,
every row price-dark (#2199). <b>Matches:</b> real production read, ${slate.matches.length}
qualifiers, ${live} inside the live window. <b>Questions:</b> register v4's eleven &mdash; eight are
now grid cells and three are dark, so the section is empty and says so.
</div>

<div class="pick">
<b>THREE THINGS THAT NEED YOU, not the integrator.</b>
(1) <b>Ruling 2 has no data behind it.</b> Nothing in this codebase holds the result of a tennis
match &mdash; not the register, not the slate builder, not the bracket. Panel 8's scores are hand-
written over real names. The seam is built and typed; the feed does not exist.
(2) <b>Ruling 8 empties the questions section today.</b> All three non-advance markets we curate
are dark: <code>sinner-competes</code> 188 hours, both <code>*-second-major</code> 810 hours &mdash;
34 days. Applying the freshness rule you asked for removes them. Panel 9 is what the section looks
like once somebody curates. This is a register ask, not a code one.
(3) <b>The two <code>*-second-major</code> cards ARE the repeating template you named</b> &mdash;
same question, name swapped. The family cap keeps one (Sinner, 55.5%, closer to a coin flip than
Alcaraz at 25%) and the section counts the drop out loud rather than quietly having one fewer card.
</div>

<div class="cap">1&ndash;2 &mdash; The Tournament tab on real data. Pills flip everything below them.</div>
<div class="rail">
  ${phone(payload.title, payload.subtitle, panel(men, menMatches))}
  ${phone(payload.title, payload.subtitle, panel(women, womenMatches), true)}
</div>

<div class="cap">3&ndash;5 &mdash; Ruling 5: the picker, against DataGolf</div>
<div class="rail">
  ${phone(
    payload.title,
    "Picker open — the filter is the gap that mattered",
    panel(men, menMatches, { chartExtra: { initialPickerOpen: true } })
  )}
  ${phone(
    payload.title,
    'Picker filtered — typed "dj"',
    panel(men, menMatches, {
      chartExtra: { initialPickerOpen: true, initialFilter: "dj" },
    })
  )}
  ${phone(
    payload.title,
    "A fourth line added — and now there is a way back",
    panel(men, menMatches, { selection: withFourth })
  )}
</div>

<div class="cap">6 &mdash; Ruling 1: both numbers on a main-draw row (SYNTHETIC fixtures, REAL title prices)</div>
<div class="rail">
  ${phone(
    payload.title,
    "Ruling 1 — match number big, title chance as a chip",
    panel(men, mainDrawEntries)
  )}
</div>

<div class="cap">7&ndash;9 &mdash; Rulings 7, 4 and 2: the detail view, the pills, the scores</div>
<div class="rail">
  ${phone(
    payload.title,
    "Ruling 7 — one row tapped open",
    panel(men, mainDrawEntries, { matchExtra: { initialOpenMatchId: detailOpenId } })
  )}
  ${phone(
    payload.title,
    "Ruling 4 — three rounds, three pills (synthetic rounds, real matches)",
    panel(men, multiRound, { matchExtra: { initialRound: "R128" } })
  )}
  ${phone(
    payload.title,
    "Ruling 2 — decided matches (SYNTHETIC results: we hold none)",
    panel(men, decidedEntries)
  )}
</div>

<div class="cap">10 &mdash; Ruling 8: what the questions section looks like when it is not dark</div>
<div class="rail">
  ${phone(
    payload.title,
    "SYNTHETIC freshness — the same three markets, re-priced today",
    panel(men, menMatches, { propMarkets: freshQuestions(props) })
  )}
</div>

<div class="cap">Bracket tab &mdash; before the draw and after it (full states: us-open-bracket.html)</div>
<div class="rail">
  <div class="phone"><div class="pad">${preDraw}</div></div>
  <div class="phone"><div class="pad">${gridHtml}</div></div>
</div>
</body></html>`;

    const out = path.join(dir, "us-open-reskin.html");
    fs.writeFileSync(out, html);
    expect(fs.existsSync(out)).toBe(true);
    expect(html.length).toBeGreaterThan(5000);

    // ---- the rig must not write a page whose panels failed to render ----
    expect(html).toContain('data-testid="tournament-matches"');
    expect(html).toContain('data-testid="contender-chart"');
    expect(html).toContain('data-testid="board-expander"');
    expect(html).toContain('data-testid="playoff-grid"');

    // ---- one assertion per ruling ----
    // 4. Chart above the match list, and the pill strip really rendered.
    expect(html.indexOf('data-testid="contender-chart"')).toBeLessThan(
      html.indexOf('data-testid="tournament-matches"')
    );
    expect(html).toContain('data-testid="match-round-strip"');
    expect((html.match(/data-testid="match-round-pill"/g) ?? []).length).toBeGreaterThan(2);
    // 1. Both numbers, and the chip says what it is.
    expect(html).toContain('data-testid="match-probability"');
    expect(html).toContain('data-testid="match-title-chip"');
    expect(html).toContain("% title");
    expect(html).toContain("To win this match");
    // 2. Scores with outcomes.
    expect(html).toContain('data-testid="match-score"');
    expect(html).toContain("6-1, 6-4");
    expect(html).toContain('data-outcome="won"');
    expect(html).toContain('data-outcome="out"');
    // 5. The picker: open, filtered, and the reset.
    expect(html).toContain('data-testid="chart-picker-filter"');
    expect(html).toContain('data-testid="chart-picker-option"');
    expect(html).toContain('data-testid="chart-reset"');
    expect(html).toContain('data-selected="4"');
    // 6. No restating sentence anywhere in the artifact's RENDERED rows.
    expect(html).not.toContain('data-testid="slate-narrative"');
    // 7. Where to watch: present, and ONLY in a detail view.
    expect(html).toContain('data-testid="match-detail-broadcast"');
    expect(html).not.toContain('data-testid="slate-row-broadcast"');
    expect((html.match(/ESPN, ESPN2, ESPN\+/g) ?? []).length).toBe(1);
    // 8. The rotation: empty-with-a-reason on real data, populated on panel 9.
    expect(html).toContain("gone dark and rotated out");
    expect(html).toContain('data-testid="props-moved-to-grid"');
    expect(html).toContain('data-testid="prop-market"');
    // Collapsed everywhere.
    expect((html.match(/data-testid="show-more"/g) ?? []).length).toBeGreaterThan(4);
    // The pre-draw bracket panel still carries both boards.
    expect(html).toContain('data-testid="bracket-unreleased"');
    // And the stylesheet actually loaded — an unstyled capture is not a verdict.
    expect(appStylesheet().length).toBeGreaterThan(1000);
  });
});
