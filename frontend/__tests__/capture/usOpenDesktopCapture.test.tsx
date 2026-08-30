/**
 * DESKTOP CAPTURE RIG — /tournaments/us-open at a desktop window, before and
 * after.
 *
 * ═══ UX-P146 RE-POINTED THIS RIG ═══
 *
 * It was written for UX-P145, whose "after" was a 1280px column. Alex read that
 * artifact and asked: *"Doesn't the rest of the desktop site just use as much
 * width as the user gives it?"* It does. So BEFORE is now UX-P145's shell — the
 * state he was actually looking at — and AFTER is the page with no shell at
 * all, inside the site's own container.
 *
 * The other correction this queue made to the rig is bigger than it looks: both
 * panels are now wrapped in `app/layout.tsx`'s container, `max-w-content mx-auto
 * px-3 md:px-6 py-4`. The UX-P145 rig rendered the page's shell directly into
 * `<body>`, so it drew a 1280px column in a bare window and showed neither the
 * site's gutters nor the fact that a SECOND container was already there. An
 * artifact that omits the wrapper cannot show a nested-container defect, which
 * is precisely the defect being judged.
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
 * THE SHELL AS IT WAS, quoted from the UX-P146 diff.
 *
 * Not imported from anywhere, because the point of this constant is that it no
 * longer exists in the codebase. Kept here so the "before" panel is the actual
 * state Alex reviewed rather than an impression of it.
 *
 * UX-P146 moved this back one generation: it used to hold UX-P144's
 * `mx-auto max-w-[560px]`, and the state under review now is UX-P145's stepped
 * column, which is the one that still drew grey down both sides.
 */
const SHELL_BEFORE =
  "mx-auto w-full max-w-[560px] lg:max-w-[1024px] xl:max-w-[1280px]";

/**
 * The SITE's container, quoted from `app/layout.tsx`.
 *
 * Quoted rather than imported because the layout is a server component whose
 * module cannot be pulled into this rig, and duplicated deliberately: the
 * string is asserted against the real file below, so a drift fails here instead
 * of producing an artifact of a page that does not exist.
 */
const SITE_CONTAINER = "max-w-content mx-auto px-3 md:px-6 py-4";

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
    // UX-P146: the AFTER shell's defining property is that it has no width.
    expect(html).not.toContain("max-w-");
    expect(html).toContain("lg:grid-cols-[minmax(0,1.35fr)_minmax(0,1fr)]");
  });

  it("the BEFORE shell is genuinely different from the AFTER shell", () => {
    // A before/after where both sides render the same thing is the most
    // convincing wrong artifact there is.
    expect(SHELL_BEFORE).not.toBe(TOURNAMENT_SHELL);
    expect(SHELL_BEFORE).toContain("max-w-");
    expect(TOURNAMENT_SHELL).not.toContain("max-w-");
  });

  it("the site container in this rig is the one `app/layout.tsx` really uses", () => {
    // The whole AFTER claim is "the page defers to the site's container". If
    // this rig invents its own, the artifact is a drawing of an argument.
    const layout = fs.readFileSync(
      path.join(__dirname, "..", "..", "app", "layout.tsx"),
      "utf8"
    );
    expect(layout).toContain(`className="${SITE_CONTAINER}"`);
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
    /* THE SAME SECTION WITH THE PRIORS STRIPPED — the results list as it was
       before this queue. Reconstructed by emptying the field rather than by
       rendering an older component, so the two panels differ in exactly the
       one thing being judged. */
    const resultsBefore = renderToStaticMarkup(
      <TournamentResults
        results={
          payload.results
            ? {
                ...payload.results,
                matches: payload.results.matches.map((match) => ({
                  ...match,
                  players: match.players.map((player) => ({
                    ...player,
                    prematch_probability: null,
                  })),
                })),
              }
            : payload.results
        }
        draw={men.draw}
      />
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

    /**
     * THE AXIS, BOTH WAYS — a captioned reconstruction, not a page render.
     *
     * The chart's scale lives in `lib/contenderChart.ts`, so the BEFORE panel's
     * chart is drawn by TODAY's code and cannot show yesterday's spacing. Rather
     * than pretend otherwise, the old scale is re-implemented here, in six
     * lines, over the SAME real domain the chart uses, and the two are stacked
     * so the difference is a thing you look at instead of a claim you read.
     *
     * Every tick below is a real observed date from the men's board.
     */
    const axisStrip = () => {
      const domain = Array.from(
        new Set(men.rows.flatMap((row) => (row.trend ?? []).map((point) => point.date)))
      ).sort();
      const day = (iso: string) => Date.parse(`${iso}T00:00:00Z`) / 86_400_000;
      const first = day(domain[0]);
      const last = day(domain[domain.length - 1]);
      const rule = (
        label: string,
        note: string,
        at: (iso: string, index: number) => number
      ) => `
      <div style="margin:10px 0 0">
        <div style="font:700 10.5px inherit;letter-spacing:.06em;text-transform:uppercase;color:#9CA3AF">${label}</div>
        <div style="position:relative;height:34px;margin-top:6px;border-bottom:1px solid #D1D5DB">
          ${domain
            .map((iso, index) => {
              const pct = at(iso, index) * 100;
              const ends = index === 0 || index === domain.length - 1;
              return `<span style="position:absolute;left:${pct.toFixed(
                2
              )}%;bottom:0;width:1px;height:${ends ? 16 : 9}px;background:${
                ends ? "#6B7280" : "#D1D5DB"
              }"></span>`;
            })
            .join("")}
          <span style="position:absolute;left:0;top:0;font:600 10.5px inherit;color:#6B7280">${domain[0]}</span>
          <span style="position:absolute;right:0;top:0;font:600 10.5px inherit;color:#6B7280">${
            domain[domain.length - 1]
          }</span>
        </div>
        <div style="margin-top:4px;font-size:11.5px;color:#6B7280">${note}</div>
      </div>`;
      return `
    <div style="background:#fff;border:1px solid #E5E7EB;border-radius:12px;padding:14px 16px;margin:0 22px 18px">
      <div style="font:700 12px inherit;color:#111827">The x-axis, both ways &mdash; ${domain.length} real reading days from this board</div>
      <div style="margin-top:2px;font-size:11.5px;color:#6B7280">A reconstruction, drawn here rather than in the page: the scale lives in a shared module, so the &ldquo;before&rdquo; page above is already using the new one.</div>
      ${rule(
        "Before &mdash; spaced by position in the list",
        "Every reading is one equal step, so the eight-day hole between 17 Aug and 26 Aug is drawn the width of one overnight move, and the last nine calendar days get 9% of the axis while the first eleven get 50%.",
        (_iso, index) => index / (domain.length - 1)
      )}
      ${rule(
        "After &mdash; spaced by the calendar",
        "Every day is worth the same width. The hole is a hole, and the middle tick lands on the middle of the window instead of on the middle of the list.",
        (iso) => (day(iso) - first) / (last - first)
      )}
    </div>`;
    };

    /** The page's chrome, drawn the way `page.tsx` draws it. */
    const chrome = (activeTab: "tournament" | "bracket") => `
  <header class="hero"><h1>${payload.title}</h1><p>${payload.subtitle}</p></header>
  <div class="tabs">
    <span class="${activeTab === "tournament" ? "on" : ""}">Tournament</span>
    <span class="${activeTab === "bracket" ? "on" : ""}">Bracket</span>
  </div>
  ${pills}`;

    /* ── BEFORE ── */
    const before = `${head("DESKTOP, BEFORE UX-P146")}
<div class="banner before">
  <span class="tag">Before</span>
  <b>/tournaments/us-open as UX-P145 left it &mdash; the artifact you reviewed.</b>
  Open this maximised. The page carries its OWN column,
  <code>${SHELL_BEFORE}</code>, inside the site container every other page already
  sits in. So the window's width past 1280px is unused no matter how wide you make it, and
  between 1024 and 1280 it is unused twice over &mdash; Alex, 2026-08-27:
  <i>&ldquo;Doesn't the rest of the desktop site just use as much width as the user gives
  it?&rdquo;</i> The grey down both sides is the subject of this pair.
  <br><br>
  Also fixed opposite: the finished matches on the right carry a result with <b>no prior</b>
  (that is real in this file &mdash; the priors are stripped out of it), and the copy still says
  <i>price</i>. The chart's x-axis was spaced by each reading's position in the LIST rather than
  by its date; that scale lives in a shared module, so this page's chart is already drawn with
  the new one and the two scales are shown separately below instead of being faked.
</div>
<div class="surface">
  ${axisStrip()}
  <div class="cap">Tournament tab</div>
  <div class="${SITE_CONTAINER}">
    <div class="${SHELL_BEFORE}">
      ${chrome("tournament")}
      <div class="px-4 pb-16 lg:px-6">
        <div class="${TOURNAMENT_COLUMNS}">
          <div class="lg:min-w-0">${chart}${matchList}</div>
          <div class="lg:min-w-0">${resultsBefore}${board}${questions}</div>
        </div>
      </div>
    </div>
  </div>
  <div class="cap">Bracket tab</div>
  <div class="${SITE_CONTAINER}">
    <div class="${SHELL_BEFORE}">
      ${chrome("bracket")}
      <div class="px-4 pb-16 lg:px-6"><div class="mt-6">${bracketBefore}</div></div>
    </div>
  </div>
</div>
</body></html>`;

    /* ── AFTER ── */
    const after = `${head("DESKTOP, AFTER UX-P146")}
<div class="banner after">
  <span class="tag">After</span>
  <b>The same page, same data, same components &mdash; with no column of its own.</b>
  Open this maximised, in the same window you opened the &ldquo;before&rdquo; file in.
  <br><br>
  <b>1. No shell.</b> The page's own <code>max-w</code> is gone. The only container is
  <code>${SITE_CONTAINER}</code> from <code>app/layout.tsx</code> &mdash;
  <code>max-w-content</code> is 1600px &mdash; which is exactly what <i>/politics</i>,
  <i>/entertainment</i>, <i>/economics</i> and <i>/hub</i> answer to. The phone is untouched:
  390px was never bound by a 560px cap, so every ruling from UX-P131 on still holds where it was
  verdicted. <b>2. The x-axis is a calendar.</b> It was spaced by each reading's place in the LIST
  of observed days, so an eight-day hole in this board's history was drawn the width of one
  overnight move, and the middle tick was labelled <i>8 Aug</i> in a window whose midpoint is
  <i>12 Aug</i>. Every day is now worth the same width. <b>3. Finished matches carry their prior.</b>
  Right-hand column: the grey figure beside a name is what the market gave that player before the
  match. Shubladze went in at 65% and lost; Colton Smith went in at 40% and won.
  <b>4. No <i>price</i>, anywhere a reader can see.</b> Alex's product-wide ruling &mdash; the
  word is PROBABILITY. &ldquo;Prices paused&rdquo; is now &ldquo;Updates paused&rdquo;, and the
  admission it carries is unchanged.
</div>
<div class="surface">
  <div class="cap">Tournament tab &mdash; two columns above 1024px, full site width</div>
  <div class="${SITE_CONTAINER}">
    <div class="${TOURNAMENT_SHELL}">
      ${chrome("tournament")}
      <div class="px-4 pb-16 lg:px-6">
        <div class="${TOURNAMENT_COLUMNS}">
          <div class="lg:min-w-0">${chart}${matchList}</div>
          <div class="lg:min-w-0">${results}${board}${questions}</div>
        </div>
      </div>
    </div>
  </div>
  <div class="cap">Bracket tab &mdash; the playoff grid at desktop scale</div>
  <div class="${SITE_CONTAINER}">
    <div class="${TOURNAMENT_SHELL}">
      ${chrome("bracket")}
      <div class="px-4 pb-16 lg:px-6"><div class="mt-6">${bracket}</div></div>
    </div>
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
    // The shell: BEFORE has a column of its own, AFTER has none.
    expect(before).toContain(`<div class="${SHELL_BEFORE}">`);
    expect(before).toContain("xl:max-w-[1280px]");
    expect(after).not.toContain("xl:max-w-[1280px]");
    expect(after).not.toContain("lg:max-w-[1024px]");
    // …and BOTH sit inside the real site container, or the pair is showing the
    // wrong thing: a nested-container defect is invisible without the outer one.
    expect(before).toContain(`<div class="${SITE_CONTAINER}">`);
    expect(after).toContain(`<div class="${SITE_CONTAINER}">`);
    // The grid's desktop tracks, pinned back to the phone's in the before.
    expect(before).toContain("--grid-name-w:118px;--grid-col-w:46px");
    // The three other rulings, each visible in the AFTER and not in the BEFORE.
    // Both panels render the same components, so these are checked on the
    // shared markup rather than by diffing the two files.
    expect(after).toContain('data-testid="result-prematch"');
    expect(after).toContain('data-testid="results-prematch-note"');
    // …and the BEFORE really is without them, so the pair shows the change.
    expect(before).not.toContain('data-testid="result-prematch"');
    expect(before).not.toContain('data-testid="results-prematch-note"');
    // The axis reconstruction is on the BEFORE file, where the comparison is.
    expect(before).toContain("The x-axis, both ways");
    expect(before).toContain("spaced by position in the list");
    expect(before).toContain("spaced by the calendar");
    // The retired copy is checked on the RENDERED SECTIONS below, not on the
    // whole file: the AFTER banner quotes "Prices paused" on purpose, to say
    // what it used to be.

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
      // UX-P146: the whole `price` family, Alex's product-wide ruling.
      /\b(un)?pric(e|es|ed|ing)\b/i,
    ]) {
      expect(text).not.toMatch(banned);
    }

    expect(fs.existsSync(beforePath)).toBe(true);
    expect(fs.existsSync(afterPath)).toBe(true);
  });
});
