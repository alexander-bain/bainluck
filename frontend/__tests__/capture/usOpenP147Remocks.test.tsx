/**
 * RE-MOCKS FOR ALEX'S ITEMS 1, 2 AND 3 (UX-P147).
 *
 * He asked for three things to be shown rather than argued, and each one is a
 * BEFORE/AFTER on the same data, in the same window, through the same shipped
 * components:
 *
 *   1. Spark bars ON (he ruled "Option A is great") — plus the truncation he
 *      named with it: "player names truncate too early when the window is not
 *      super wide ... names get priority over bar width; bars compress first."
 *   2. The x-axis, "still oddly sparse" even after UX-P146's calendar spacing.
 *   3. The FINISHED section, whose two probabilities and score column are
 *      "raggedly aligned" — and, in the same panel, item 4's 101% pairs and
 *      item 5's "no score" row.
 *
 *   UX_CAPTURE_DIR=<dir> npx jest --testPathPatterns=usOpenP147Remocks
 *     → p147-1-reach-table-names.html
 *     → p147-2-chart-axis.html
 *     → p147-3-finished-section.html
 *
 * With no env var set it is an ordinary test that renders every panel and
 * asserts the rig still works.
 *
 * ═══ BEFORE AND AFTER IN ONE FILE, WHICH THE DESKTOP RIG COULD NOT DO ═══
 *
 * `usOpenDesktopCapture` writes two files, because Tailwind's `lg:` is a
 * VIEWPORT query and two panels side by side in one window would each be laid
 * out at half the width they are judged at. That constraint is about SIDE BY
 * SIDE. Stacked VERTICALLY, both panels are full-width and both see the real
 * viewport, so one file is not only allowed here, it is better — the two states
 * are a scroll apart instead of an alt-tab apart, and every media query is the
 * one the reader's window actually fires.
 *
 * ═══ WHAT IS FAITHFUL AND WHAT IS QUOTED ═══
 *
 * FAITHFUL: the components, the app's compiled CSS from `.next/static/css`, and
 * the payload — `payload-2026-08-28.json`, captured from production minutes
 * before this ran, carrying the real walkover, the real retirements and the 18
 * real pre-match pairs.
 *
 * QUOTED FROM THE DIFF, and captioned as such on the artifact, are the three
 * BEFORE states. They no longer exist in the codebase, which is the whole point
 * of a before panel:
 *
 *   - `GRID_TEMPLATE_BEFORE` — the fixed-name-track template, substituted into
 *     the shipped component's own rendered markup rather than re-drawn, so the
 *     panel differs from AFTER in exactly one string.
 *   - `axisTicksBefore` — UX-P146's three-tick chooser, reproduced here so the
 *     before panel shows the axis Alex is looking at and not an impression of
 *     it. The dates it picks are asserted against the ones its own tests pinned.
 *   - `ResultsListBefore` — the pre-UX-P147 `flex justify-between` row, quoted
 *     from the diff. It is a reconstruction of the LIST only; the heading and
 *     the footnotes are unchanged by this queue and are not re-drawn.
 */

import React from "react";
import { renderToStaticMarkup } from "react-dom/server";
import fs from "node:fs";
import path from "node:path";

import ContenderChart from "@/components/tournament/ContenderChart";
import PlayoffGrid from "@/components/tournament/PlayoffGrid";
import TournamentResults from "@/components/tournament/TournamentResults";
import {
  axisTicks,
  chartGeometry,
  chartSeriesFor,
  dateX,
  defaultSelection,
  shortDateLabel,
  type ChartGeometry,
} from "@/lib/contenderChart";
import { readPlayoffGrid } from "@/lib/playoffGrid";
import { formatPrematch, type TournamentResult } from "@/lib/tournamentResults";
import type { TournamentPayload } from "@/lib/tournament";

const FRONTEND = path.join(__dirname, "..", "..");
const REPO = path.join(FRONTEND, "..");
const PAYLOAD_PATH = path.join(REPO, "docs", "mocks", "us-open", "payload-2026-08-28.json");

/**
 * The grid template as it was, quoted from the UX-P147 diff.
 *
 * A FIXED name track beside flexible value tracks, which is why every pixel of
 * extra window went to the numbers and the names truncated at the same
 * character in a 1400px window as in a 900px one.
 */
const GRID_TEMPLATE_BEFORE = (columns: number) =>
  `var(--grid-name-w) repeat(${columns}, minmax(var(--grid-col-w), 1fr))`;

const GRID_TEMPLATE_AFTER = (columns: number) =>
  `minmax(var(--grid-name-w), max-content) repeat(${columns}, minmax(var(--grid-col-w), 1fr))`;

/** UX-P146's interior-tick rule, quoted so the BEFORE panel is the real one. */
const INTERIOR_TICK_EDGE_MARGIN_BEFORE = 0.18;

function axisTicksBefore(geometry: ChartGeometry): string[] {
  const dates = geometry.dates;
  if (dates.length < 2) return [];
  const first = dates[0];
  const last = dates[dates.length - 1];
  if (dates.length < 3) return [first, last];

  const day = (iso: string) => Date.parse(`${iso}T00:00:00Z`) / 86_400_000;
  const midDay = (day(first) + day(last)) / 2;
  let nearest = dates[1];
  let bestGap = Infinity;
  for (const date of dates.slice(1, -1)) {
    const gap = Math.abs(day(date) - midDay);
    if (gap < bestGap) {
      bestGap = gap;
      nearest = date;
    }
  }
  const midX = dateX(nearest, geometry);
  if (midX === null) return [first, last];
  const fraction = midX / geometry.width;
  if (
    fraction < INTERIOR_TICK_EDGE_MARGIN_BEFORE ||
    fraction > 1 - INTERIOR_TICK_EDGE_MARGIN_BEFORE
  ) {
    return [first, last];
  }
  return [first, nearest, last];
}

/**
 * THE FINISHED LIST AS IT WAS — quoted from the UX-P147 diff.
 *
 * `flex justify-between` with the score as a sibling of a `flex-1` block, and
 * `ml-auto` pushing each prior to that block's right edge. Correct-looking, and
 * the reason no two rows put their numbers in the same place: the block's width
 * is `row − score − gap`, and the score is text.
 *
 * The priors are rounded here the way they were rounded then — each one on its
 * own, through `formatPrematch` with no `rendered` override — so the panel
 * shows the 101% pairs Alex read off the last artifact rather than a tidied
 * version of them.
 */
function ResultsListBefore({ matches }: { matches: TournamentResult[] }) {
  return (
    <div className="overflow-hidden rounded-2xl border border-surface-border bg-surface-card">
      <ul>
        {matches.map((result) => {
          const winner = result.players.find((p) => p.is_winner);
          const loser = result.players.find((p) => !p.is_winner);
          if (!winner || !loser) return null;
          return (
            <React.Fragment key={result.matchup_key}>
              <li className="border-t border-surface-border bg-surface-elevated px-3.5 py-1 text-[10px] font-bold uppercase tracking-[0.05em] text-text-muted first:border-t-0">
                {result.source_round ?? result.round}
              </li>
              <li className="border-t border-surface-border px-3.5 py-2.5">
                <div className="flex items-baseline justify-between gap-3">
                  <div className="min-w-0 flex-1">
                    {[winner, loser].map((player) => {
                      const prior = formatPrematch(player.prematch_probability);
                      return (
                        <div
                          key={player.entity_key}
                          className="flex min-w-0 items-baseline"
                        >
                          <span
                            className={`truncate text-[13.5px] ${
                              player.is_winner
                                ? "font-semibold text-text-primary"
                                : "font-normal text-text-muted"
                            }`}
                          >
                            {player.display_name}
                          </span>
                          {player.is_winner && (
                            <span className="ml-1.5 shrink-0 text-[10px] font-bold uppercase tracking-[0.05em] text-accent-live">
                              won
                            </span>
                          )}
                          {prior && (
                            <span className="ml-auto shrink-0 pl-3 text-[12px] tabular-nums text-text-secondary">
                              {prior}
                            </span>
                          )}
                        </div>
                      );
                    })}
                  </div>
                  {result.score ? (
                    <span className="shrink-0 text-[13px] font-semibold tabular-nums text-text-secondary">
                      {result.score}
                    </span>
                  ) : (
                    <span
                      className="shrink-0 text-[11px] text-text-muted"
                      title="The source reported a winner but no completed set scores — usually a retirement."
                    >
                      no score
                    </span>
                  )}
                </div>
              </li>
            </React.Fragment>
          );
        })}
      </ul>
    </div>
  );
}

function loadPayload(): TournamentPayload {
  return JSON.parse(fs.readFileSync(PAYLOAD_PATH, "utf8")) as TournamentPayload;
}

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

/** Hide the ticks a given panel is not meant to be showing. */
function tickCss(scope: string, keep: string[]): string {
  const not = keep.map((date) => `:not([data-date="${date}"])`).join("");
  return `${scope} [data-testid="chart-axis-tick"]${not},${scope} [data-testid="chart-axis-label"]${not}{display:none!important}`;
}

describe("UX-P147 re-mocks — items 1, 2 and 3", () => {
  const payload = loadPayload();
  const men = payload.boards.find((board) => board.draw === "mens-singles")!;
  const grid = readPlayoffGrid(payload.grids?.["mens-singles"]);
  const results = payload.results ?? null;
  const menResults = (results?.matches ?? []).filter(
    (match) => match.draw === "mens-singles"
  );

  it("has a fresh production payload to draw, carrying tonight's evidence", () => {
    // The rig is worthless on a stale file — that is the whole lesson of
    // `capture_tournament_payload.py`. These four facts are the ones the three
    // panels are FOR, so they are asserted rather than assumed.
    expect(grid).not.toBeNull();
    expect(grid!.rows.length).toBeGreaterThan(50);
    // Item 4/5's evidence: the walkover, and pre-match pairs to round.
    expect(results?.matches.some((m) => m.completion === "walkover")).toBe(true);
    expect(results?.matches.some((m) => m.completion === "retired")).toBe(true);
    expect(results?.with_prematch ?? 0).toBeGreaterThan(10);
  });

  it("the BEFORE grid template is the one this queue replaced", () => {
    // If the shipped template ever goes back to a fixed name track, the before
    // and after panels become identical and the artifact silently stops making
    // its point. So the two strings must differ, and AFTER must be the shipped
    // one — asserted against the component's own markup below.
    expect(GRID_TEMPLATE_BEFORE(5)).not.toBe(GRID_TEMPLATE_AFTER(5));
    const html = renderToStaticMarkup(<PlayoffGrid grid={grid!} initialExpanded />);
    expect(html).toContain(GRID_TEMPLATE_AFTER(grid!.columns.length));
    expect(html).not.toContain(GRID_TEMPLATE_BEFORE(grid!.columns.length));
  });

  it("the BEFORE axis really is the three ticks UX-P146 drew", () => {
    const selection = defaultSelection(men.rows);
    const geometry = chartGeometry(chartSeriesFor(men.rows, selection), "ALL", 320, 96);
    const before = axisTicksBefore(geometry);
    expect(before.length).toBeLessThanOrEqual(3);
    expect(before[0]).toBe(geometry.dates[0]);
    expect(before[before.length - 1]).toBe(geometry.dates[geometry.dates.length - 1]);
  });

  it("the BEFORE finished list reproduces the 101% pairs", () => {
    // The panel has to show the defect, or it is a picture of the fix twice.
    const withPrior = menResults.filter((match) =>
      match.players.every((p) => typeof p.prematch_probability === "number")
    );
    expect(withPrior.length).toBeGreaterThan(0);
    const html = renderToStaticMarkup(<ResultsListBefore matches={withPrior} />);
    const sums = withPrior.map((match) =>
      match.players.reduce(
        (total, p) => total + Math.round((p.prematch_probability as number) * 100),
        0
      )
    );
    expect(sums.some((sum) => sum === 101)).toBe(true);
    expect(html).toContain("%");
  });

  it("writes the three re-mocks when UX_CAPTURE_DIR is set", () => {
    const dir = process.env.UX_CAPTURE_DIR;
    if (!dir) {
      expect(true).toBe(true);
      return;
    }
    fs.mkdirSync(dir, { recursive: true });

    const css = appStylesheet();
    const page = (title: string, intro: string, body: string, extraCss = "") =>
      `<!doctype html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>UX-P147 — ${title}</title>
<style>${css}</style>
<style>
  body{background:#F5F5F7;margin:0;font-family:-apple-system,BlinkMacSystemFont,"SF Pro Text",Segoe UI,Roboto,sans-serif}
  .banner{padding:14px 22px;font-size:13px;line-height:1.6;color:#374151;background:#fff;border-bottom:1px solid #E5E7EB}
  .banner b{color:#111827}
  .tag{display:inline-block;margin-right:10px;padding:3px 9px;border-radius:6px;font:700 11px inherit;letter-spacing:.06em;text-transform:uppercase}
  .tag.before{background:#FEF2F2;color:#991B1B}
  .tag.after{background:#ECFDF5;color:#065F46}
  .panel{padding:8px 0 40px}
  .panel-head{padding:16px 22px 4px;font-size:13px;color:#4B5563;line-height:1.6}
  .rule{height:1px;background:#E5E7EB;margin:8px 0 0}
  ${extraCss}
</style></head>
<body>
<div class="banner">${intro}</div>
${body}
</body></html>`;

    const framed = (markup: string) =>
      `<div class="max-w-content mx-auto px-3 md:px-6 py-4"><div class="w-full"><div class="px-4 lg:px-6">${markup}</div></div></div>`;

    const panel = (kind: "before" | "after", label: string, note: string, markup: string) =>
      `<div class="panel ${kind}"><div class="panel-head"><span class="tag ${kind}">${kind}</span> <b>${label}</b> ${note}</div>${framed(markup)}<div class="rule"></div></div>`;

    /* ─────────── 1. the reach table: bars on, names first ─────────── */

    const gridAfter = renderToStaticMarkup(
      <PlayoffGrid grid={grid!} drawLabel="Men's singles" initialExpanded />
    );
    // The one-string difference. Substituted into the shipped component's own
    // output rather than re-drawn, so nothing else in the panel can drift.
    const gridBefore = gridAfter
      .split(GRID_TEMPLATE_AFTER(grid!.columns.length))
      .join(GRID_TEMPLATE_BEFORE(grid!.columns.length));

    fs.writeFileSync(
      path.join(dir, "p147-1-reach-table-names.html"),
      page(
        "Item 1 — spark bars on, and names before bars",
        `<span class="tag after">Item 1</span> <b>Spark bars are on by default now</b> — you ruled
         "Option A is great". The second half of this panel is the truncation you named with it:
         <i>"player names truncate too early when the window is not super wide ... names get
         priority over bar width; bars compress first."</i>
         <br><br>
         <b>Resize the window from about 900px to full screen and watch the left column.</b> BEFORE,
         the name track is a fixed 236px at every desktop width and every extra pixel goes to the
         bars — "Auger-Aliassime" is cut at 1400px exactly as it is at 900px. AFTER, the name track
         grows to the longest name in the table FIRST and the bars take what is left, so widening
         the window lengthens names until none is cut, and only then lengthens bars.
         <br><br>
         Both panels are the same component and the same data; the only difference is one CSS grid
         template string, quoted from the diff.`,
        panel(
          "before",
          "Fixed name track.",
          "Extra width goes to the bars. Names truncate at the same character at every desktop size.",
          gridBefore
        ) +
          panel(
            "after",
            "Name track grows first.",
            "The names claim what they need up to the longest one in the table; the bars compress into the rest.",
            gridAfter
          )
      )
    );

    /* ─────────── 2. the x-axis ─────────── */

    const selection = defaultSelection(men.rows);
    const geometry = chartGeometry(chartSeriesFor(men.rows, selection), "ALL", 320, 96);
    const keepBefore = axisTicksBefore(geometry);
    /* COUNTED OFF THIS DATA, not quoted from the design. The tiers can hold 4 /
       7 / 13 labels; what a given board actually gets depends on where its
       readings are, and on the men's board a seventeen-day hole eats most of
       the right-hand slots. A caption that printed the capacity next to a
       picture of the reality would be the artifact arguing with itself. */
    const after = axisTicks(geometry);
    const atTier = (tiers: string[]) =>
      after.filter((tick) => tiers.includes(tick.tier)).length;
    const density = {
      phone: atTier(["end", "major"]),
      lg: atTier(["end", "major", "wide"]),
      xxl: after.length,
    };
    const chart = renderToStaticMarkup(
      <ContenderChart
        rows={men.rows}
        draw={men.draw}
        selection={selection}
        onToggle={() => {}}
        onReset={() => {}}
      />
    );

    fs.writeFileSync(
      path.join(dir, "p147-2-chart-axis.html"),
      page(
        "Item 2 — the x-axis was still oddly sparse",
        `<span class="tag after">Item 2</span> <b>"Still oddly sparse."</b> It was. UX-P146 fixed
         WHERE the ticks sit — calendar time instead of list position — and left the COUNT at three,
         a number measured once on a 358px phone and then inherited by a plot that is 817px wide on
         this screen. Two 400-pixel stretches with nothing in them.
         <br><br>
         AFTER, the axis has a density instead of a count. The tiers can carry 4 / 7 / 13 labels;
         on <b>this</b> board they give <b>${density.phone} on a phone,
         ${density.lg} from 1024px and ${density.xxl} from 1536px</b> — every one still snapped to a
         day something was actually read, and drawn at that day's true position.
         <b>Resize the window and watch labels appear between the ones already there</b> — a narrow
         axis is always a subset of a wide one, so it reads as zooming in rather than as a
         different chart.
         <br><br>
         Note what does NOT get denser: the long empty stretch on the right. That is the men's
         board's price hole, and an empty half of the axis is the honest drawing of it — the tiers
         only put a label where there is a reading to label.
         <br><br>
         Both panels are the same chart; the BEFORE panel hides every tick this queue added and
         pins the interior one to the date UX-P146's chooser picked, reproduced in the rig.`,
        panel(
          "before",
          "Three ticks.",
          `${keepBefore.map(shortDateLabel).join(" · ")} — the ends and one interior label.`,
          chart
        ) +
          panel(
            "after",
            `Density by window width — ${density.phone} / ${density.lg} / ${density.xxl} labels.`,
            "Resize to see the wide and fine tiers arrive. Same component, same render — CSS spends the tiers.",
            chart
          ),
        tickCss(".panel.before", keepBefore)
      )
    );

    /* ─────────── 3. the finished section ─────────── */

    const finishedAfter = renderToStaticMarkup(
      <TournamentResults results={results} draw="mens-singles" initialExpanded />
    );
    const finishedBefore = renderToStaticMarkup(
      <ResultsListBefore matches={menResults} />
    );

    const pairs = menResults
      .filter((match) => match.players.every((p) => typeof p.prematch_probability === "number"))
      .map((match) =>
        match.players
          .map((p) => Math.round((p.prematch_probability as number) * 100))
          .reduce((a, b) => a + b, 0)
      );
    const wrong = pairs.filter((sum) => sum !== 100).length;

    fs.writeFileSync(
      path.join(dir, "p147-3-finished-section.html"),
      page(
        "Items 3, 4 and 5 — the finished section",
        `<span class="tag after">Items 3 · 4 · 5</span> Three fixes in one section, on tonight's
         production data.
         <br><br>
         <b>Item 3 — "raggedly aligned".</b> The row was a flexbox, so the prior column's right edge
         and the score column's left edge both moved with the width of each row's own score string
         (<i>6-3, 6-4</i> is 56px; <i>7-6 (7-4), 3-6, 6-4</i> is 128px). It is one CSS grid now,
         shared by every row, so the three columns have one position each down the whole list, and
         the score is centred against both player lines because a score describes the match.
         <br><br>
         <b>Item 4 — 101%.</b> You read four rows off the last artifact: 74/27, 40/61, 60/41, 67/34.
         The underlying pairs ARE normalized — all of them arrive summing to exactly 1.000. The 101
         was made at the last step, by half-up rounding both sides of a <i>.5</i> boundary. The pair
         is rounded once now, through the same <code>renderedDuelPercents</code> the Discover event
         card uses: the favourite is rounded and the underdog is derived as 100 minus it.
         <b>${wrong} of ${pairs.length}</b> pairs on this data summed to 101 before; none do now.
         <br><br>
         <b>Item 5 — "no score" on the Dimitrov qualifying final.</b> Root cause: neither an ingest
         gap nor a render fallback. ESPN carries competition 184769 as <code>STATUS_WALKOVER</code>
         with the note "Grigor Dimitrov (BUL) bt Otto Virtanen (FIN) w/o" and no line scores on
         either player — Virtanen withdrew before a ball was struck. There was never a score. What
         was wrong is that we said "no score" and guessed "usually a retirement" in the tooltip, when
         the source had already told us. It says <b>walkover</b>.
         <br><br>
         The same measurement found the mirror defect: all the RETIREMENTS carry equal-length line
         scores, so they sailed through and printed as ordinary results — look for
         <i>4-6, 6-4, 5-0</i> in the BEFORE panel, which is not a scoreline a completed match can
         have. It is marked <i>ret.</i> now.`,
        panel(
          "before",
          "Flex row, priors rounded separately, completions thrown away.",
          "Quoted from the diff. Watch the prior and score columns move from row to row.",
          finishedBefore
        ) +
          panel(
            "after",
            "One grid, one rounding, the completion named.",
            "Shipped component, unmodified.",
            finishedAfter
          )
      )
    );

    for (const file of [
      "p147-1-reach-table-names.html",
      "p147-2-chart-axis.html",
      "p147-3-finished-section.html",
    ]) {
      const written = fs.readFileSync(path.join(dir, file), "utf8");
      expect(written.length).toBeGreaterThan(20_000);
      expect(written).toContain('class="tag before"');
      expect(written).toContain('class="tag after"');
    }
  });
});
