/**
 * THE X-AXIS, BEFORE AND AFTER — UX-P207.
 *
 * Alex, on the live `/tournaments/us-open` on opening day: *"The x-axis in the
 * chart is weird"* — and he named the ticks: **1 Aug, 6 Aug, 10 Aug, then a gap
 * to 26 Aug, 30 Aug**. This renders that axis and the one that replaces it, on
 * the same payload, through the same shipped component.
 *
 *   UX_CAPTURE_DIR=<dir> npx jest --testPathPatterns=usOpenP207Axis
 *     → p207-1-axis-mens.html      the window Alex filed (30 days, one hole)
 *     → p207-2-axis-womens.html    the other draw (5 days) — a different step
 *     → p207-3-tournament-tab.html the whole tab: chart, results, board
 *
 * With no env var set it is an ordinary test that renders every panel and
 * asserts the properties the panels are supposed to show.
 *
 * ═══ WHAT IS FAITHFUL AND WHAT IS QUOTED ═══
 *
 * FAITHFUL: the components, the app's compiled CSS from `.next/static/css`, and
 * `payload-2026-08-31.json` — captured from production for this queue, carrying
 * the men's fifteen-day price hole that is the whole subject.
 *
 * QUOTED FROM THE DIFF, and captioned as such on the artifact: `axisTicksBefore`
 * is the UX-P147 chooser this replaces, reproduced here so the BEFORE panel is
 * the axis Alex read and not an impression of it. Its output is asserted
 * against the sequence he filed, so the reproduction cannot silently drift.
 *
 * ═══ WHY THIS IS HTML AND NOT A PNG ═══
 *
 * Chromium does not run in this sandbox, so the lane's proof rail is a rendered
 * HTML page carrying the app's own stylesheet — openable in Alex's browser at
 * any width, which is better than a screenshot for a change whose whole subject
 * is what happens at three widths (`reference_agent_cannot_produce_browser_evidence`).
 */

import React from "react";
import { renderToStaticMarkup } from "react-dom/server";
import fs from "node:fs";
import path from "node:path";

import ContenderChart from "@/components/tournament/ContenderChart";
import TournamentBoard from "@/components/tournament/TournamentBoard";
import TournamentResults from "@/components/tournament/TournamentResults";
import {
  axisSpanDays,
  axisStepDays,
  axisTicks,
  chartGeometry,
  chartSeriesFor,
  dateX,
  defaultSelection,
  seriesColorByEntity,
  shortDateLabel,
  type AxisTick,
  type ChartGeometry,
} from "@/lib/contenderChart";
import type { TournamentBoardData, TournamentPayload } from "@/lib/tournament";

const FRONTEND = path.resolve(__dirname, "..", "..");
const REPO = path.resolve(FRONTEND, "..");
const PAYLOAD_PATH = path.join(REPO, "docs", "mocks", "us-open", "payload-2026-08-31.json");
const OUT_DIR = process.env.UX_CAPTURE_DIR ?? "";

const WIDTH = 320;

/* =========================================================================
 * THE AXIS AS IT WAS — quoted from the UX-P207 diff
 * =========================================================================
 *
 * UX-P147's chooser: twelve calendar slots, each SNAPPED to the nearest
 * observed date, deduped, and dropped when its label would collide with one
 * already placed. `end` is the two real ends, placed unconditionally.
 *
 * It is here so the BEFORE panel shows the axis Alex is looking at. The test
 * below asserts it reproduces his filed sequence exactly; if the reproduction
 * ever stops matching, the panel is a lie and the assertion says so.
 */
type BeforeTier = "end" | "major" | "wide" | "fine";

const LABEL_CLEARANCE_BEFORE: Record<BeforeTier, number> = {
  end: 38 / 358,
  major: 38 / 358,
  wide: 38 / 486,
  fine: 38 / 817,
};

function slotTierBefore(k: number): BeforeTier {
  if (k % 4 === 0) return "major";
  if (k % 2 === 0) return "wide";
  return "fine";
}

function dayNumberBefore(iso: string): number {
  return Math.round(Date.parse(`${iso}T00:00:00Z`) / 86_400_000);
}

function axisTicksBefore(geometry: ChartGeometry): AxisTick[] {
  const dates = geometry.dates;
  if (dates.length < 2) return [];
  const first = dates[0];
  const last = dates[dates.length - 1];
  const firstX = dateX(first, geometry);
  const lastX = dateX(last, geometry);
  if (firstX === null || lastX === null) return [];

  const make = (date: string, x: number, tier: BeforeTier) =>
    ({ date, x, label: shortDateLabel(date), tier } as unknown as AxisTick);
  const kept = [make(first, firstX, "end"), make(last, lastX, "end")];
  if (dates.length < 3) return kept;

  const firstDay = dayNumberBefore(first);
  const lastDay = dayNumberBefore(last);
  const interior = dates.slice(1, -1);
  const taken = new Set<string>([first, last]);
  const rank: Record<BeforeTier, number> = { end: 0, major: 1, wide: 2, fine: 3 };
  const order = [...Array(11).keys()]
    .map((i) => i + 1)
    .sort((a, b) => rank[slotTierBefore(a)] - rank[slotTierBefore(b)] || a - b);

  for (const k of order) {
    const tier = slotTierBefore(k);
    const target = firstDay + ((lastDay - firstDay) * k) / 12;
    let nearest: string | null = null;
    let best = Infinity;
    for (const date of interior) {
      if (taken.has(date)) continue;
      const gap = Math.abs(dayNumberBefore(date) - target);
      if (gap < best) {
        best = gap;
        nearest = date;
      }
    }
    if (nearest === null) continue;
    const x = dateX(nearest, geometry);
    if (x === null) continue;
    const fraction = x / geometry.width;
    const clashes = kept.some((other) => {
      const clearance = Math.min(
        LABEL_CLEARANCE_BEFORE[tier],
        LABEL_CLEARANCE_BEFORE[other.tier as BeforeTier]
      );
      return Math.abs(other.x / geometry.width - fraction) < clearance;
    });
    if (clashes) continue;
    taken.add(nearest);
    kept.push(make(nearest, x, tier));
  }
  return kept.sort((a, b) => a.x - b.x);
}

/* ===================================================================== */

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

/** The three widths the tiers are spent at, as a caption a reader can act on. */
function densityCaption(ticks: AxisTick[]): string {
  const at = (tiers: string[]) => ticks.filter((t) => tiers.includes(t.tier));
  const gaps = (subset: AxisTick[]) =>
    subset.slice(1).map((t, i) => ((t.x - subset[i].x) / WIDTH) * 100);
  const say = (name: string, subset: AxisTick[]) => {
    const g = gaps(subset).map((v) => v.toFixed(1));
    const uniform = new Set(g).size <= 1;
    return `${name}: ${subset.length} labels, gaps ${g.join(" / ")}%${
      uniform ? " — EVEN" : " — UNEVEN"
    }`;
  };
  return [
    say("phone", at(["end", "major"])),
    say("lg", at(["end", "major", "wide"])),
    say("2xl", ticks),
  ].join(" · ");
}

/** A static strip of ticks + labels, drawn the way the component draws them. */
function AxisStrip({ ticks, tiers }: { ticks: AxisTick[]; tiers: string[] }) {
  const visible = ticks.filter((t) => tiers.includes(t.tier));
  return (
    <div className="relative mt-1 h-8 border-t border-surface-border">
      {visible.map((tick) => {
        const fraction = tick.x / WIDTH;
        return (
          <React.Fragment key={tick.date}>
            <span
              className="absolute top-0 block h-2 w-px bg-surface-border"
              style={{ left: `${fraction * 100}%` }}
            />
            <span
              className="absolute top-3 whitespace-nowrap text-[9.5px] tabular-nums text-text-muted"
              style={{
                left: `${fraction * 100}%`,
                transform:
                  fraction <= 15 / 358
                    ? "none"
                    : fraction >= 1 - 15 / 358
                      ? "translateX(-100%)"
                      : "translateX(-50%)",
              }}
            >
              {tick.label}
            </span>
          </React.Fragment>
        );
      })}
    </div>
  );
}

function panel(kind: "before" | "after", heading: string, note: string, body: string) {
  const tone = kind === "before" ? "#b4530a" : "#0a7b4a";
  return `
    <section style="margin:0 0 28px">
      <div style="font:700 11px/1.4 ui-sans-serif,system-ui;letter-spacing:.08em;
                  text-transform:uppercase;color:${tone};margin:0 0 4px">${kind}</div>
      <div style="font:600 15px/1.4 ui-sans-serif,system-ui;color:#111;margin:0 0 2px">${heading}</div>
      <div style="font:400 12.5px/1.5 ui-sans-serif,system-ui;color:#555;margin:0 0 10px;
                  max-width:74ch">${note}</div>
      ${body}
    </section>`;
}

function page(title: string, intro: string, body: string) {
  return `<!doctype html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>${title}</title>
<style>${appStylesheet()}</style>
<style>
  body{margin:0;padding:24px;background:#f6f6f5}
  .wrap{max-width:1600px;margin:0 auto}
  h1{font:700 22px/1.3 ui-sans-serif,system-ui;color:#111;margin:0 0 6px}
  .intro{font:400 13.5px/1.6 ui-sans-serif,system-ui;color:#444;max-width:78ch;margin:0 0 24px}
</style>
</head><body><div class="wrap">
<h1>${title}</h1><p class="intro">${intro}</p>
${body}
</div></body></html>`;
}

function boardOf(payload: TournamentPayload, draw: string): TournamentBoardData {
  const board = (payload.boards ?? []).find((entry) => entry.draw === draw);
  if (!board) throw new Error(`no ${draw} board in the payload`);
  return board;
}

function write(name: string, html: string) {
  if (!OUT_DIR) return;
  fs.mkdirSync(OUT_DIR, { recursive: true });
  fs.writeFileSync(path.join(OUT_DIR, name), html, "utf8");
}

describe("UX-P207 capture — the x-axis, before and after", () => {
  const payload = loadPayload();

  /** One draw's before/after panel pair, plus the assertions each panel claims. */
  function axisPanels(draw: string) {
    const board = boardOf(payload, draw);
    const selection = defaultSelection(board.rows);
    const geometry = chartGeometry(chartSeriesFor(board.rows, selection), "ALL", WIDTH, 96);
    return {
      board,
      selection,
      geometry,
      before: axisTicksBefore(geometry),
      after: axisTicks(geometry),
      span: axisSpanDays(geometry) ?? 0,
    };
  }

  it("reproduces the sequence Alex filed, so the BEFORE panel is not an impression", () => {
    const { before } = axisPanels("mens-singles");
    // `lg` is where he was reading — the desktop page.
    const lg = before.filter((t) => ["end", "major", "wide"].includes(t.tier));
    expect(lg.map((t) => t.label)).toEqual([
      "1 Aug", "6 Aug", "10 Aug", "26 Aug", "31 Aug",
    ]);
    // He wrote "30 Aug" because 30 Aug was the last reading at 2:40pm PT; the
    // payload captured for this queue runs one day further. Everything before
    // the last label is his sequence exactly.
    const gaps = lg.slice(1).map((t, i) => ((t.x - lg[i].x) / WIDTH) * 100);
    expect(Math.max(...gaps) / Math.min(...gaps)).toBeGreaterThan(3.9);
  });

  it("writes the men's panel — a month-long window with a fifteen-day hole", () => {
    const { board, selection, geometry, before, after, span } = axisPanels("mens-singles");
    expect(axisStepDays(span)).toBe(7);
    expect(after.map((t) => t.label)).toEqual(["3 Aug", "10 Aug", "17 Aug", "24 Aug", "31 Aug"]);

    const chart = renderToStaticMarkup(
      <ContenderChart
        rows={board.rows}
        draw={board.draw}
        selection={selection}
        onToggle={() => {}}
        onReset={() => {}}
      />
    );
    write(
      "p207-1-axis-mens.html",
      page(
        "UX-P207 · the men's title race, x-axis before and after",
        `The window is ${span} days, 1 Aug → 31 Aug, with a fifteen-day price hole from ` +
          `11 Aug to 25 Aug. Both strips are drawn from that one domain at the same scale ` +
          `as the chart. Resize the window: the AFTER strips are what a phone, an ` +
          `<code>lg</code> window and a <code>2xl</code> window each show.`,
        panel(
          "before",
          "Ticks snapped to the nearest reading.",
          `Every candidate inside the hole snapped back onto a tick already placed and was ` +
            `dropped, so the labels cluster where the readings are dense. ${densityCaption(before)}. ` +
            `Quoted from the diff — this code no longer exists.`,
          renderToStaticMarkup(
            <div className="rounded-2xl border border-surface-border bg-surface-card p-4">
              <AxisStrip ticks={before} tiers={["end", "major", "wide"]} />
            </div>
          )
        ) +
          panel(
            "after",
            "One weekly step, anchored on the latest reading.",
            `17 Aug and 24 Aug are inside the hole and nothing was read on either — which is ` +
              `the point: the hole is now legible AS a fortnight. ${densityCaption(after)}. ` +
              `Below is the live component, not a strip.`,
            `<div class="rounded-2xl border border-surface-border bg-surface-card p-4">${
              renderToStaticMarkup(<AxisStrip ticks={after} tiers={["major", "wide", "fine"]} />)
            }</div><div style="margin-top:14px">${chart}</div>`
          )
      )
    );
  });

  it("writes the women's panel — a six-day window, where the step is daily", () => {
    const { board, selection, before, after, span } = axisPanels("womens-singles");
    // The SAME code, a different step, with no timeframe button involved: `ALL`
    // on this board is five days.
    expect(span).toBe(5);
    expect(axisStepDays(span)).toBe(1);
    expect(after).toHaveLength(6);
    // BEFORE was uneven on a phone here too — 40 / 20 / 40 — which is the same
    // defect on the draw nobody filed it against.
    const phoneBefore = before.filter((t) => ["end", "major"].includes(t.tier));
    const phoneGaps = phoneBefore.slice(1).map((t, i) => ((t.x - phoneBefore[i].x) / WIDTH) * 100);
    expect(new Set(phoneGaps.map((g) => g.toFixed(1))).size).toBeGreaterThan(1);
    // AFTER is even at every width.
    const afterGaps = after.slice(1).map((t, i) => ((t.x - after[i].x) / WIDTH) * 100);
    expect(new Set(afterGaps.map((g) => g.toFixed(1))).size).toBe(1);

    const chart = renderToStaticMarkup(
      <ContenderChart
        rows={board.rows}
        draw={board.draw}
        selection={selection}
        onToggle={() => {}}
        onReset={() => {}}
      />
    );
    write(
      "p207-2-axis-womens.html",
      page(
        "UX-P207 · the women's title race, x-axis before and after",
        `The second draw, and the reason the step is not a table keyed on the timeframe ` +
          `button: <code>ALL</code> here is ${span} days, so the same code that drew the men's ` +
          `board weekly draws this one daily.`,
        panel(
          "before",
          "Uneven on a phone — 40 / 20 / 40.",
          `Nobody filed this one, and it is the same defect: the coarse tier's slots snapped ` +
            `onto whichever days happened to be observed. ${densityCaption(before)}.`,
          renderToStaticMarkup(
            <div className="rounded-2xl border border-surface-border bg-surface-card p-4">
              <AxisStrip ticks={before} tiers={["end", "major"]} />
            </div>
          )
        ) +
          panel(
            "after",
            "Six daily ticks, even at every width.",
            `${densityCaption(after)}. Below is the live component.`,
            `<div class="rounded-2xl border border-surface-border bg-surface-card p-4">${
              renderToStaticMarkup(<AxisStrip ticks={after} tiers={["major", "wide", "fine"]} />)
            }</div><div style="margin-top:14px">${chart}</div>`
          )
      )
    );
  });

  it("writes the whole Tournament tab — the chart above the lists that have faces", () => {
    // ALEX'S OTHER ASK, in the same view: "No images for the players?" The tab
    // has three lists that draw people, and this renders the two the payload
    // populates today so the faces and the axis are judged in one place.
    const board = boardOf(payload, "mens-singles");
    const selection = defaultSelection(board.rows);
    const series = chartSeriesFor(board.rows, selection);
    const chart = renderToStaticMarkup(
      <ContenderChart
        rows={board.rows}
        draw={board.draw}
        selection={selection}
        onToggle={() => {}}
        onReset={() => {}}
      />
    );
    const results = renderToStaticMarkup(
      <TournamentResults results={payload.results ?? null} draw="mens-singles" />
    );
    const boardHtml = renderToStaticMarkup(
      <TournamentBoard board={board} seriesColors={seriesColorByEntity(series)} />
    );

    /* FACES, COUNTED AT THE RENDER rather than read off the payload — a payload
     * full of `image` blocks proves nothing about what the page draws, and here
     * the two lists disagree, which is the finding.
     *
     * ONE AVATAR PER RENDERED SLOT is the render contract and holds on both
     * lists. What differs is WHICH of `PlayerAvatar`'s three steps each slot
     * lands on, and that is a property of the PAYLOAD:
     *
     *   • the contender board  — `boards[].rows[].image` is populated in
     *     production today (36/36 men, 44/44 women), so these are faces now.
     *   • the finished matches — `results.matches[].players[]` carries NO
     *     `image` key in production, so all 248 slots fall to initials. That is
     *     not a regression in this component: `827c5bd9`'s BACKEND half, which
     *     joins the register's pins onto each result player and emits
     *     `player_slots` / `with_face` / `with_flag`, is on this branch and NOT
     *     DEPLOYED. Measured on all three captured payloads (08-27, 08-28,
     *     08-31): 152/152, 188/188 and 248/248 slots with no image block.
     *
     * So the assertion below is the honest one — every slot draws something,
     * the board draws people, and the results list is pinned at the state the
     * merge changes. It goes RED the day the backend half lands, which is
     * exactly when this caption needs rewriting.
     */
    const count = (html: string, needle: string) =>
      (html.match(new RegExp(needle, "g")) ?? []).length;
    const boardRows = count(boardHtml, 'data-testid="board-row"');
    const resultSlots = count(results, 'data-testid="result-player"');
    const avatars = (html: string) => count(html, 'data-testid="player-avatar"');
    const initials = (html: string) => count(html, 'data-kind="initials"');

    expect(boardRows).toBeGreaterThan(0);
    expect(resultSlots).toBeGreaterThan(0);
    // The render contract, on both lists: a slot never renders empty.
    expect(avatars(boardHtml)).toBe(boardRows);
    expect(avatars(results)).toBe(resultSlots);
    // The board draws PEOPLE today, from production's own pins.
    expect(initials(boardHtml)).toBe(0);
    expect(count(boardHtml, 'data-kind="face"')).toBe(boardRows);
    // And the results list is at the pre-merge state, stated rather than hidden.
    expect(initials(results)).toBe(resultSlots);
    expect(payload.results?.player_slots ?? null).toBeNull();

    write(
      "p207-3-tournament-tab.html",
      page(
        "UX-P207 · the Tournament tab, men's singles",
        `The two asks from the same view, rendered from <code>payload-2026-08-31.json</code> ` +
          `as production serves it. <b>The chart's axis is now a weekly calendar grid.</b> ` +
          `<b>The contender board draws ${avatars(boardHtml)} faces</b> and ` +
          `${initials(boardHtml)} initials — that half is live on the site today. ` +
          `<b>The finished matches draw ${avatars(results)} avatars, all ${initials(results)} ` +
          `of them initials</b>, and that is the pre-merge state, not a defect in the ` +
          `component: production's <code>results.matches[].players[]</code> carries no ` +
          `<code>image</code> key at all, because the backend half of <code>827c5bd9</code> ` +
          `(the register-pin join) is on this branch and not deployed. The same component ` +
          `draws faces the moment it lands.`,
        `<div style="max-width:820px">${chart}<div style="height:16px"></div>${results}` +
          `<div style="height:16px"></div>${boardHtml}</div>`
      )
    );
  });
});
