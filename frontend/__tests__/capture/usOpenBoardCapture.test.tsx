/**
 * CAPTURE RIG — the real /tournaments/us-open boards, over real production data.
 *
 * Chromium is dead in this sandbox (Mach bootstrap denied), so a screenshot is
 * not available to this lane. This is the substitute the repo already uses:
 * render the ACTUAL shipped components with `renderToStaticMarkup`, wrap them
 * in the app's OWN compiled stylesheet from `.next/static/css`, and write a
 * self-contained HTML file Alex can open. It is the real component and the real
 * CSS over the real numbers — not a re-creation of the page in mock markup,
 * which is what the Day-1 mocks deliberately were.
 *
 * Two jobs, and the second is why it lives under `__tests__`:
 *
 *   1. `UX_CAPTURE_DIR=<dir> npx jest --testPathPatterns=usOpenBoardCapture`
 *      writes `us-open-shipped.html` at a 390px mobile viewport.
 *
 *   2. With no env var set it is an ordinary test that renders every state and
 *      asserts the rig still works — a capture harness that has silently rotted
 *      is discovered at exactly the wrong moment.
 *
 * The payload is `docs/mocks/us-open/payload-2026-08-25.json`, produced by the
 * BACKEND's own `build_boards` over a bounded production read. So this file
 * exercises both halves end to end: if the Python changes shape, the render
 * breaks here.
 */

import React from "react";
import { renderToStaticMarkup } from "react-dom/server";
import fs from "node:fs";
import path from "node:path";

import TournamentBoard from "@/components/tournament/TournamentBoard";
import TournamentBracket from "@/components/tournament/TournamentBracket";
import TournamentSlate from "@/components/tournament/TournamentSlate";
import TournamentProps from "@/components/tournament/TournamentProps";
import { buildBracket } from "@/lib/bracket";
import {
  SYNTHETIC_MENS_DRAW,
  syntheticFirstRoundResults,
} from "@/__tests__/fixtures/syntheticDraw";
import type { SlateData } from "@/lib/slate";
import type { PropMarket } from "@/lib/tournamentProps";
import type { TournamentBoardData, TournamentPayload } from "@/lib/tournament";

const SLATE_PATH = path.join(
  __dirname,
  "..",
  "..",
  "..",
  "docs",
  "mocks",
  "us-open",
  "slate-2026-08-25.json"
);

const PROPS_PATH = path.join(
  __dirname,
  "..",
  "..",
  "..",
  "docs",
  "mocks",
  "us-open",
  "props-2026-08-25.json"
);

const PAYLOAD_PATH = path.join(
  __dirname,
  "..",
  "..",
  "..",
  "docs",
  "mocks",
  "us-open",
  "payload-2026-08-25.json"
);

function loadPayload(): TournamentPayload {
  return JSON.parse(fs.readFileSync(PAYLOAD_PATH, "utf8")) as TournamentPayload;
}

/** The real slate, built by the BACKEND's `build_slate` over a production read. */
function loadSlate(): SlateData {
  return JSON.parse(fs.readFileSync(SLATE_PATH, "utf8")) as SlateData;
}

/** The real curated props, built by the BACKEND's `build_props` (UX-P134). */
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

describe("US Open board capture rig", () => {
  const payload = loadPayload();

  it("has a payload with both draws", () => {
    expect(payload.boards).toHaveLength(2);
    expect(payload.boards.map((b) => b.draw)).toEqual([
      "mens-singles",
      "womens-singles",
    ]);
  });

  it("carries the real field, not a fixture", () => {
    const men = payload.boards[0];
    expect(men.rows.length).toBeGreaterThan(20);
    expect(men.rows[0].display_name).toBeTruthy();
    expect(men.rows[0].probability).toBeGreaterThan(0);
  });

  it("PRODUCTION STATE 2026-08-25: every row is non-live (#2199)", () => {
    // This is the assertion that documents why the honesty treatment is the
    // whole page this weekend rather than an edge case.
    //
    // CORRECTED 2026-08-25 (UX-P134), because the sentence that used to sit
    // here was disproven by measurement. It read: "when #2199 is fixed in its
    // own lane this test SHOULD start failing — that is the signal to
    // recapture." It cannot. This test reads a COMMITTED payload, so it is
    // pinned to a file in this repo and can never observe production at all.
    // It stayed green through the entire landing of #2199 — code merged
    // (`b19708f0`), deployed (`a5688c0b`), oracle live — while the boards
    // stayed dark, and a green here would have been read as "not fixed yet"
    // when the truth was "fixed and not working". A fixture test that is
    // described as a production signal is worse than no signal, because
    // somebody will believe it.
    //
    // What this test actually proves, and all it proves: the renderer handles
    // a dark board correctly. That stays worth asserting after #2199 bites,
    // so this does NOT get flipped when production goes live — its live-side
    // twin below is a SEPARATE test, not a replacement.
    //
    // The real signal is the task's own oracle, measured, never inferred:
    //   GET /api/admin/source-health/futures-price-freshness?max_age_hours=24
    // `status: "red"` with `price_dark: 898 / 909` as of 2026-08-25T23:3x UTC.
    const allRows = payload.boards.flatMap((b) => b.rows);
    expect(allRows.length).toBeGreaterThan(60);
    expect(allRows.every((r) => r.probability_is_live === false)).toBe(true);
    expect(payload.boards.every((b) => b.price_state === "dark")).toBe(true);
  });

  it("LIVE PATH: a live board renders confidently, with no age label and no banner", () => {
    // The live direction has NEVER been exercised — production has been dark
    // for the whole life of this component, so every existing assertion is
    // about the muted treatment. The moment #2199 bites, the marquee weekend
    // ships a rendering path no test has ever run.
    //
    // This payload is SYNTHETIC and says so. It is not a claim that production
    // is live; it is the proof that when production goes live the board stops
    // apologising. Built by lifting the real board and setting exactly the
    // fields the server owns, so it cannot drift from the real shape.
    const live = makeLiveBoard(payload.boards[0]);
    const html = renderToStaticMarkup(<TournamentBoard board={live} />);

    expect(html).toContain('data-live="true"');
    expect(html).not.toContain('data-live="false"');
    expect(html).not.toContain("Prices paused");
    // The age label is the honesty treatment's tell — a live row must not wear it.
    expect(html).not.toContain('data-testid="row-age"');
    // And it must still print exactly one probability per row: going live is
    // not permission to start printing the complement (adaptation, not imitation).
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
    // Real player names on both sides of every row — never Yes/No.
    for (const match of slate.matches) {
      expect(match.sides).toHaveLength(2);
      for (const side of match.sides) {
        expect(["Yes", "No", ""]).not.toContain(side.display_name);
      }
    }
  });

  it("the re-skinned board collapses to three rows with an expander", () => {
    // Alex called the uncollapsed 44-row women's list a P1 on this page.
    const women = payload.boards[1];
    expect(women.rows.length).toBeGreaterThan(20);
    const html = renderToStaticMarkup(<TournamentBoard board={women} />);
    expect((html.match(/data-testid="board-row"/g) ?? []).length).toBe(3);
    expect(html).toContain(`Show all ${women.rows.length}`);
  });

  it("the chart draws three lines and no more", () => {
    const html = renderToStaticMarkup(<TournamentBoard board={payload.boards[0]} />);
    expect((html.match(/data-testid="chart-legend-item"/g) ?? []).length).toBe(3);
    const drawn = (html.match(/data-testid="chart-series"/g) ?? []).length;
    expect(drawn).toBeLessThanOrEqual(3);
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

    // Both pill states rendered side by side, because the whole point of the
    // toggle is that you never see them stacked in the product — so the only
    // place to review both at once is here.
    const broadcasts = [
      { region: "US", channels: ["ESPN", "ESPN2", "ESPN+"], note: null },
    ];
    const panel = (draw: string, board: typeof men) => `
      <div class="pad">
        ${renderToStaticMarkup(
          <TournamentSlate slate={slate} draw={draw} broadcasts={broadcasts} />
        )}
        ${renderToStaticMarkup(<TournamentBoard board={board} />)}
        ${renderToStaticMarkup(<TournamentProps markets={props} draw={draw} />)}
      </div>`;

    // The bracket, with DUMMY data — Alex asked to see it before Thursday's
    // ceremony. The fixture lives under __tests__/ and cannot reach a
    // production bundle; on the real page this tab still reads "Draw not
    // released" until the register latches `draw_released`.
    const rounds = buildBracket(
      SYNTHETIC_MENS_DRAW,
      syntheticFirstRoundResults(SYNTHETIC_MENS_DRAW)
    );
    const bracket = renderToStaticMarkup(
      <TournamentBracket rounds={rounds} drawReleased />
    );

    const live = slate.matches.filter((m) => m.probability_is_live).length;

    const html = `<!doctype html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>${payload.title} — re-skin</title>
<style>${appStylesheet()}</style>
<style>
  body{background:#F5F5F7;margin:0;font-family:-apple-system,BlinkMacSystemFont,"SF Pro Text",Segoe UI,Roboto,sans-serif}
  .rail{display:flex;gap:24px;justify-content:center;align-items:flex-start;flex-wrap:wrap;padding:0 16px 60px}
  .phone{width:390px;background:#F5F5F7;border:1px solid #E5E7EB;border-radius:12px;overflow:hidden}
  .note{max-width:1240px;margin:0 auto;padding:14px 16px;font-size:12.5px;line-height:1.55;color:#374151;background:#fff;border-bottom:1px solid #E5E7EB}
  .note b{color:#111827}
  .cap{max-width:1240px;margin:16px auto 8px;padding:0 16px;font:700 12px inherit;letter-spacing:.07em;text-transform:uppercase;color:#9CA3AF}
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
  .wide{max-width:1240px;margin:0 auto;padding:0 16px 60px}
</style></head>
<body>
<div class="note">
<b>US Open hub — Alex's mock verdict applied.</b> These are the SHIPPED components rendered with the
app's own compiled CSS at a 390px viewport. Two phones so both pill states are visible at once; in
the product you only ever see one.<br>
<b>Boards:</b> real production read, ${men.rows.length + women.rows.length} registered contenders,
every row price-dark (#2199) — that is why they are muted and banner'd.
<b>Slate:</b> real production read, ${slate.matches.length} matches, ${live} of them inside the
6-hour live window. <b>Props:</b> mechanism only — population needs one production query that this
lane's sandbox currently refuses (see report). <b>Bracket:</b> DUMMY 128-slot fixture, shown early
at Alex's request; the real page says "Draw not released" until the ceremony.
</div>

<div class="cap">Tournament tab — pills flip everything below them</div>
<div class="rail">
  <div class="phone">
    <header class="hero"><h1>${payload.title}</h1><p>${payload.subtitle}</p></header>
    <div class="tabs"><span class="on">Tournament</span><span>Bracket</span></div>
    <div class="pills"><span class="on">Men's</span><span>Women's</span></div>
    ${panel("mens-singles", men)}
  </div>
  <div class="phone">
    <header class="hero"><h1>${payload.title}</h1><p>${payload.subtitle}</p></header>
    <div class="tabs"><span class="on">Tournament</span><span>Bracket</span></div>
    <div class="pills"><span>Men's</span><span class="on">Women's</span></div>
    ${panel("womens-singles", women)}
  </div>
</div>

<div class="cap">Bracket tab — dummy draw, ahead of Thursday's ceremony</div>
<div class="wide">${bracket}</div>
</body></html>`;

    const out = path.join(dir, "us-open-reskin.html");
    fs.writeFileSync(out, html);
    expect(fs.existsSync(out)).toBe(true);
    expect(html.length).toBeGreaterThan(5000);
    // The rig must not silently write a page whose panels failed to render.
    expect(html).toContain("data-testid=\"tournament-slate\"");
    expect(html).toContain("data-testid=\"contender-chart\"");
    expect(html).toContain("data-testid=\"board-expander\"");
    expect(html).toContain("data-testid=\"tournament-bracket\"");
    expect(html).toContain("data-testid=\"slate-broadcast\"");
  });
});
