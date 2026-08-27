/**
 * DESKTOP CAPTURE RIG — /tournaments/us-open at a desktop window, before and
 * after UX-P145.
 *
 * Alex asked for "before/after desktop screenshots as artifacts". Chromium is
 * dead in this sandbox (Mach bootstrap denied; every flag combination fails),
 * so a PNG is not available to this lane. This is the substitute the repo
 * already uses and the one the last four queues were verdicted on: render the
 * ACTUAL shipped components with `renderToStaticMarkup`, wrap them in the app's
 * OWN compiled stylesheet from `.next/static/css`, and write a self-contained
 * HTML file Alex opens in a real browser at a real window size. Real
 * components, real CSS, real production numbers.
 *
 * ═══ WHY TWO FILES AND NOT TWO PANELS IN ONE ═══
 *
 * Because the whole subject is media queries. Tailwind's `lg:` is a VIEWPORT
 * query, not a container query. Two 700px panels side by side in one 1440px
 * window would both match `lg`, so the "before" panel would pick up desktop
 * rules it never had and the "after" panel would be laid out at half the width
 * it is being judged at. The comparison would be a drawing of the difference
 * rather than the difference.
 *
 * So each state is a full-width page of its own, and the instruction to Alex is
 * one line: open both, maximised, in the same window.
 *
 *   UX_CAPTURE_DIR=<dir> npx jest --testPathPatterns=usOpenDesktopCapture
 *     → us-open-desktop-before.html   (the pre-UX-P145 shell)
 *     → us-open-desktop-after.html    (what this queue ships)
 *
 * With no env var set it is an ordinary test that renders every panel and
 * asserts the rig still works.
 *
 * ═══ WHAT IS FAITHFUL AND WHAT IS RECONSTRUCTED ═══
 *
 * FAITHFUL: every component, the payload (a committed production read from
 * 2026-08-27), the app's compiled CSS, and — the part that matters — the
 * shipped `TOURNAMENT_SHELL` and `TOURNAMENT_COLUMNS` strings, imported rather
 * than retyped. A rig that hard-codes its own frame width is drawing a picture
 * of the page; this one renders the page's own layout classes, so if somebody
 * reverts them the artifact reverts with them.
 *
 * RECONSTRUCTED, and captioned as such in the artifact: the BEFORE file's
 * shell. `max-w-[560px]` with no column split is the string that was on
 * `page.tsx` until this commit — it is quoted from the diff, not re-derived.
 * Its playoff grid renders through today's component with the CSS variables
 * pinned to their phone values, so its columns are the phone's 118/46; what it
 * cannot reproduce is that the old template used fixed `46px` tracks where
 * today's uses `minmax(46px, 1fr)`, so inside the 560px column its cells spread
 * slightly wider than they truly did. That is a few pixels inside a panel whose
 * subject is a 560px column in a 1440px window, and saying so is cheaper than
 * pretending otherwise.
 *
 * The PHONE is not re-captured here. `usOpenBoardCapture` already renders it at
 * 390px and its assertions are unchanged by this queue — that suite passing IS
 * the evidence that mobile did not move.
 */

import React from "react";
import { renderToStaticMarkup } from "react-dom/server";
import fs from "node:fs";
import path from "node:path";

import ContenderChart from "@/components/tournament/ContenderChart";
import DrawToggle from "@/components/tournament/DrawToggle";
import PlayoffGrid from "@/components/tournament/PlayoffGrid";
import TournamentBoard from "@/components/tournament/TournamentBoard";
import TournamentBracket from "@/components/tournament/TournamentBracket";
import TournamentMatches from "@/components/tournament/TournamentMatches";
import TournamentProps from "@/components/tournament/TournamentProps";
import TournamentResults from "@/components/tournament/TournamentResults";
import { TOURNAMENT_COLUMNS, TOURNAMENT_SHELL } from "@/components/tournament/layout";
import {
  chartSeriesFor,
  defaultSelection,
  seriesColorByEntity,
} from "@/lib/contenderChart";
import { buildMatchList, type MatchListEntry, type TitleChances } from "@/lib/matchList";
import { readPlayoffGrid } from "@/lib/playoffGrid";
import { slateNotice, type SlateData } from "@/lib/slate";
import type { PropMarket } from "@/lib/tournamentProps";
import type { TournamentBoardData, TournamentPayload } from "@/lib/tournament";

const MOCKS = path.join(__dirname, "..", "..", "..", "docs", "mocks", "us-open");
const PAYLOAD_PATH = path.join(MOCKS, "payload-2026-08-27.json");

/**
 * THE SHELL AS IT WAS, quoted from the UX-P145 diff.
 *
 * Not imported from anywhere, because the point of this constant is that it no
 * longer exists in the codebase. Kept here so the "before" panel is the actual
 * defect Alex reported rather than an impression of it.
 */
const SHELL_BEFORE = "mx-auto max-w-[560px]";

/** The grid's pre-UX-P145 measurements, for the same reason. */
const GRID_VARS_BEFORE = { "--grid-name-w": "118px", "--grid-col-w": "46px" } as React.CSSProperties;

function loadPayload(): TournamentPayload {
  return JSON.parse(fs.readFileSync(PAYLOAD_PATH, "utf8")) as TournamentPayload;
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

function titleChancesFor(board: TournamentBoardData): TitleChances {
  const out: TitleChances = {};
  for (const row of board.rows) out[row.entity_key] = row.probability;
  return out;
}

function matchesFor(slate: SlateData, board: TournamentBoardData): MatchListEntry[] {
  return buildMatchList({
    slate: slate.matches.filter((m) => m.draw === board.draw),
    titleChances: titleChancesFor(board),
  });
}

describe("US Open DESKTOP capture rig", () => {
  const payload = loadPayload();
  const slate = payload.slate as SlateData;
  const props = (payload.props ?? []) as PropMarket[];
  const men = payload.boards[0];

  /* ─────────── the rig's own guards, run with or without the env var ─────────── */

  it("has the production payload the mobile rig uses — same file, same read", () => {
    expect(payload.boards).toHaveLength(2);
    expect(slate.matches.length).toBeGreaterThan(30);
    expect(payload.grids?.["mens-singles"]).toBeTruthy();
  });

  it("renders the AFTER shell with the shipped class strings, not a copy", () => {
    // The one property that makes this artifact evidence rather than art.
    const html = renderToStaticMarkup(
      <div className={TOURNAMENT_SHELL}>
        <div className={TOURNAMENT_COLUMNS}>
          <div />
        </div>
      </div>
    );
    expect(html).toContain("max-w-[560px]");
    expect(html).toContain("lg:max-w-[1024px]");
    expect(html).toContain("xl:max-w-[1280px]");
    expect(html).toContain("lg:grid-cols-[minmax(0,1.35fr)_minmax(0,1fr)]");
  });

  it("the BEFORE shell is genuinely different from the AFTER shell", () => {
    // A before/after where both sides render the same thing is the most
    // convincing wrong artifact there is.
    expect(SHELL_BEFORE).not.toBe(TOURNAMENT_SHELL);
    expect(SHELL_BEFORE).not.toContain("lg:");
    expect(TOURNAMENT_SHELL).toContain("lg:");
  });

  it("the desktop grid fills its width instead of scrolling", () => {
    const grid = readPlayoffGrid(payload.grids?.["mens-singles"]);
    const html = renderToStaticMarkup(<PlayoffGrid grid={grid!} initialExpanded />);
    expect(html).toContain("minmax(var(--grid-col-w), 1fr)");
    expect(html).toContain("lg:[--grid-name-w:236px]");
  });

  it("the compiled stylesheet is present — an unstyled capture is not a verdict", () => {
    const css = appStylesheet();
    expect(css.length).toBeGreaterThan(1000);
    // And it really carries the desktop rules. If `npm run build` has not been
    // re-run since the classes were added, the artifact would render as the
    // phone and read as a failed fix.
    expect(css).toContain("--grid-name-w:236px");
    expect(css).toContain("@media (min-width:1024px)");
  });

  /* ─────────── the artifacts ─────────── */

  it("writes the before/after desktop captures when UX_CAPTURE_DIR is set", () => {
    const dir = process.env.UX_CAPTURE_DIR;
    if (!dir) {
      expect(true).toBe(true);
      return;
    }
    fs.mkdirSync(dir, { recursive: true });

    const selection = defaultSelection(men.rows);
    const seriesColors = seriesColorByEntity(chartSeriesFor(men.rows, selection));
    const entries = matchesFor(slate, men);
    const grid = readPlayoffGrid(payload.grids?.["mens-singles"]);

    const chart = renderToStaticMarkup(
      <ContenderChart
        rows={men.rows}
        draw={men.draw}
        selection={selection}
        onToggle={() => {}}
        onReset={() => {}}
      />
    );
    const matchList = renderToStaticMarkup(
      <TournamentMatches
        entries={entries}
        notice={slateNotice(slate)}
        initialRound="R128"
      />
    );
    const results = renderToStaticMarkup(
      <TournamentResults results={payload.results} draw={men.draw} />
    );
    const board = renderToStaticMarkup(
      <TournamentBoard board={men} seriesColors={seriesColors} />
    );
    const questions = renderToStaticMarkup(
      <TournamentProps markets={props} draw={men.draw} />
    );
    const pills = renderToStaticMarkup(
      <DrawToggle draw="mens-singles" onSelect={() => {}} />
    );
    const bracket = renderToStaticMarkup(
      <TournamentBracket
        grid={grid}
        drawReleased={payload.draw_released}
        drawLabel={men.label}
        drawReleaseLabel={payload.draw_release_label}
        mainDrawLabel={payload.main_draw_label}
        initialExpanded
      />
    );
    // The same bracket with the CSS variables pinned to their phone values —
    // the grid as it was before this queue. See the file header for the one
    // way this reconstruction is imperfect.
    const bracketBefore = `<div style="--grid-name-w:118px;--grid-col-w:46px">${bracket}</div>`;

    const head = (title: string) => `<!doctype html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>${payload.title} — ${title}</title>
<style>${appStylesheet()}</style>
<style>
  body{background:#F5F5F7;margin:0;font-family:-apple-system,BlinkMacSystemFont,"SF Pro Text",Segoe UI,Roboto,sans-serif}
  .banner{padding:14px 22px;font-size:13px;line-height:1.6;color:#374151;background:#fff;border-bottom:1px solid #E5E7EB}
  .banner b{color:#111827}
  .banner .tag{display:inline-block;margin-right:10px;padding:3px 9px;border-radius:6px;font:700 11px inherit;letter-spacing:.06em;text-transform:uppercase}
  .before .tag{background:#FEE2E2;color:#991B1B}
  .after .tag{background:#DCFCE7;color:#14532D}
  .cap{padding:20px 22px 6px;font:700 11.5px inherit;letter-spacing:.07em;text-transform:uppercase;color:#9CA3AF}
  .surface{background:#F5F5F7;padding-bottom:48px}
  .ruler{position:relative;height:18px;margin:0 22px 4px;border-left:1px solid #D1D5DB;border-right:1px solid #D1D5DB;border-bottom:1px solid #D1D5DB}
  .ruler span{position:absolute;top:-2px;left:50%;transform:translateX(-50%);background:#F5F5F7;padding:0 8px;font:600 10.5px inherit;color:#9CA3AF}
  .tabs{display:flex;border-bottom:1px solid #E5E7EB;background:#fff}
  .tabs span{flex:1;text-align:center;padding:13px 0;font:600 13.5px inherit;color:#9CA3AF;border-bottom:2px solid transparent}
  .tabs span.on{color:#111827;border-bottom-color:#111827}
  header.hero{padding:16px;background:#fff;border-bottom:1px solid #E5E7EB}
  header.hero h1{margin:0;font-size:24px;letter-spacing:-.02em;color:#111827}
  header.hero p{margin:2px 0 0;font-size:13px;color:#6B7280}
</style></head>
<body>`;

    /** The page's chrome, drawn the way `page.tsx` draws it. */
    const chrome = (activeTab: "tournament" | "bracket") => `
  <header class="hero"><h1>${payload.title}</h1><p>${payload.subtitle}</p></header>
  <div class="tabs">
    <span class="${activeTab === "tournament" ? "on" : ""}">Tournament</span>
    <span class="${activeTab === "bracket" ? "on" : ""}">Bracket</span>
  </div>
  ${pills}`;

    /* ── BEFORE ── */
    const before = `${head("DESKTOP, BEFORE UX-P145")}
<div class="banner before">
  <span class="tag">Before</span>
  <b>/tournaments/us-open as it renders today, in a desktop browser.</b>
  Open this maximised. Everything on the page lives inside one <code>${SHELL_BEFORE}</code>
  column, so the window's width is unused no matter how wide you make it &mdash; Alex, 2026-08-27:
  <i>&ldquo;weirdly narrow, like we only made a mobile version.&rdquo;</i>
  The props section is live in production (the flag folds to <code>true</code> in the shipped
  bundle), and its empty state is the copy ruled forbidden: <b>&ldquo;3 curated questions have
  gone dark and rotated out&hellip;&rdquo;</b>
</div>
<div class="surface">
  <div class="cap">Tournament tab</div>
  <div class="${SHELL_BEFORE}">
    ${chrome("tournament")}
    <div class="px-4 pb-16">${chart}${matchList}${results}${board}${questions}</div>
  </div>
  <div class="cap">Bracket tab &mdash; the playoff grid at phone measurements</div>
  <div class="${SHELL_BEFORE}">
    ${chrome("bracket")}
    <div class="px-4 pb-16"><div class="mt-6">${bracketBefore}</div></div>
  </div>
</div>
</body></html>`;

    /* ── AFTER ── */
    const after = `${head("DESKTOP, AFTER UX-P145")}
<div class="banner after">
  <span class="tag">After</span>
  <b>The same page, same data, same components &mdash; with a desktop presentation.</b>
  Open this maximised, in the same window you opened the &ldquo;before&rdquo; file in.
  <br><br>
  <b>1. The shell widens</b> to 1024px at <code>lg</code> and 1280px at <code>xl</code>; the 560px
  phone column is untouched below that, so every ruling from UX-P131 on still holds where it was
  verdicted. <b>2. The Tournament tab is two columns:</b> the title race and the day's card on the
  left, what just happened and the standings on the right &mdash; on a phone the board is thirty
  rows below the chart, and here it is beside it. <b>3. The bracket fills the width</b> at
  236/84px tracks instead of 118/46, and never scrolls sideways; P138's scroll ruling still governs
  the phone it was measured on. <b>4. Prose is capped</b> at its own measure &mdash; the table
  wants 1280px, a 12px paragraph does not. <b>5. No internal jargon:</b> no
  <i>curated</i>, <i>gone dark</i>, <i>rotated out</i>, <i>priced</i>, <i>registered</i>,
  <i>stale</i> or <i>blended</i> in anything a reader sees.
</div>
<div class="surface">
  <div class="cap">Tournament tab &mdash; two columns above 1024px</div>
  <div class="${TOURNAMENT_SHELL}">
    ${chrome("tournament")}
    <div class="px-4 pb-16 lg:px-6">
      <div class="${TOURNAMENT_COLUMNS}">
        <div class="lg:min-w-0">${chart}${matchList}</div>
        <div class="lg:min-w-0">${results}${board}${questions}</div>
      </div>
    </div>
  </div>
  <div class="cap">Bracket tab &mdash; the playoff grid at desktop scale</div>
  <div class="${TOURNAMENT_SHELL}">
    ${chrome("bracket")}
    <div class="px-4 pb-16 lg:px-6"><div class="mt-6">${bracket}</div></div>
  </div>
</div>
</body></html>`;

    const beforePath = path.join(dir, "us-open-desktop-before.html");
    const afterPath = path.join(dir, "us-open-desktop-after.html");
    fs.writeFileSync(beforePath, before);
    fs.writeFileSync(afterPath, after);

    /* ── the rig must not write a page whose panels failed to render ── */
    for (const [name, html] of [
      ["before", before],
      ["after", after],
    ] as const) {
      expect(html.length).toBeGreaterThan(20000);
      expect(html).toContain('data-testid="contender-chart"');
      expect(html).toContain('data-testid="tournament-matches"');
      expect(html).toContain('data-testid="tournament-board"');
      expect(html).toContain('data-testid="tournament-props"');
      expect(html).toContain('data-testid="playoff-grid"');
      expect(html).toContain('data-testid="draw-toggle"');
      // Real data in both, so the comparison is like for like.
      expect(html).toContain("Carlos Alcaraz");
      expect(html).toMatch(/data-round="R128"/);
      if (!html.includes("@media (min-width:1024px)")) {
        throw new Error(`${name}: the compiled stylesheet did not make it into the artifact`);
      }
    }

    /* ── and the two files must actually DIFFER in the way claimed ── */
    // The shell.
    expect(before).toContain(`<div class="${SHELL_BEFORE}">`);
    expect(before).not.toContain("lg:max-w-[1024px]");
    expect(after).toContain("lg:max-w-[1024px]");
    expect(after).toContain("xl:max-w-[1280px]");
    // The column split, in the after only.
    expect(before).not.toContain("lg:grid-cols-");
    expect(after).toContain("lg:grid-cols-[minmax(0,1.35fr)_minmax(0,1fr)]");
    // The grid's desktop tracks, pinned back to the phone's in the before.
    expect(before).toContain("--grid-name-w:118px;--grid-col-w:46px");

    /* ── the language claim on the banner has to be true of the PAGE ── */
    // The banner says "no internal jargon in anything a reader sees". A caption
    // that claims a property the artifact does not have is worse than no
    // caption, so it is checked against the rendered sections rather than
    // trusted. (The BEFORE banner quotes the old sentence deliberately, which
    // is why this runs over the sections and not over the whole file.)
    const rendered = [chart, matchList, results, board, questions, bracket].join("");
    const text = rendered.replace(/<[^>]*>/g, " ");
    for (const banned of [
      /\bcurated\b/i,
      /\bgone dark\b/i,
      /\brotated out\b/i,
      /\bregistered\b/i,
      /\bblended\b/i,
      /\bstale\b/i,
      /\bare priced\b/i,
      /\bunpriced\b/i,
    ]) {
      expect(text).not.toMatch(banned);
    }

    expect(fs.existsSync(beforePath)).toBe(true);
    expect(fs.existsSync(afterPath)).toBe(true);
  });
});
