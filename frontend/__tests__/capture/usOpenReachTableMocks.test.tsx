/**
 * "CHANCE OF REACHING" — TWO MOCKS, ONE QUESTION (UX-P146).
 *
 * Alex, on the UX-P145 desktop artifact:
 *
 *   > The "Chance of reaching" table — I REALLY like it. Would subtle spark
 *   > bars help scanning, or make it busy?
 *
 * The charter answer to a question shaped like that is a picture, not a
 * paragraph: **visual mocks, never word-MC.** So this rig writes the same table,
 * on the same production data, through the same shipped component, twice — once
 * with the bars and once without — and Alex opens both.
 *
 *   UX_CAPTURE_DIR=<dir> npx jest --testPathPatterns=usOpenReachTableMocks
 *     → reach-table-with-bars.html
 *     → reach-table-plain.html
 *
 * ═══ WHY ONE COMPONENT AND A PROP, NOT TWO DRAWINGS ═══
 *
 * A mock hand-built for the question is a picture of an idea. This one renders
 * `PlayoffGrid` with `sparkBars` on and off, against the app's own compiled
 * CSS, so whichever way Alex rules the change is a one-line default and the
 * thing he judged is the thing that ships. It also means the mock cannot
 * flatter the proposal: the bars are laid out by the real grid template at the
 * real column widths, so if they crowd an 84px desktop column they will crowd
 * it in the artifact.
 *
 * ═══ IS IT REAL DATA? THE SOURCED ANSWER, ON THE ARTIFACT ═══
 *
 * Alex asked that of the table itself, and it belongs on the page he is
 * looking at rather than only in a report. Measured off the committed register
 * and the 2026-08-27 production payload, and asserted below so the banner
 * cannot drift from the file:
 *
 *   - The four reach columns are **336 cells, each from its own pinned
 *     Polymarket market** (336 distinct market ids, 336 distinct outcome ids).
 *   - Kalshi was asked for **all 448** reach identities and runs **none** of
 *     them. That is the 560 `missing` source blocks in the register and it is
 *     the whole of the "no mkt" column — not a gap in our linking.
 *   - The title column is the board's blend of **4 real winner markets**
 *     (Kalshi 34277822 / 34277839, Polymarket 114159 / 114160).
 *   - Nothing in any cell is chained, simulated or derived from another cell.
 *
 * So: yes, real markets — with one correction worth stating plainly, which is
 * that the reach half is Polymarket-only today rather than Kalshi+Polymarket.
 */

import React from "react";
import { renderToStaticMarkup } from "react-dom/server";
import fs from "node:fs";
import path from "node:path";

import PlayoffGrid from "@/components/tournament/PlayoffGrid";
import { readPlayoffGrid } from "@/lib/playoffGrid";
import type { TournamentPayload } from "@/lib/tournament";

const FRONTEND = path.join(__dirname, "..", "..");
const REPO = path.join(FRONTEND, "..");
const PAYLOAD_PATH = path.join(REPO, "docs", "mocks", "us-open", "payload-2026-08-27.json");
const REGISTER_PATH = path.join(
  REPO,
  "backend",
  "data",
  "tournament_registers",
  "us-open-2026.json"
);

/** The measured provenance the banner prints. Asserted, then rendered. */
const SOURCING = {
  reachCells: 336,
  polymarketMarkets: 336,
  kalshiReachBlocks: 448,
  kalshiReachLive: 0,
  winnerMarkets: 4,
};

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

interface RegisterSourceBlock {
  source?: string;
  status?: string;
  market_id?: number | string | null;
  outcome_id?: number | null;
}

/** Counted off the committed register, not asserted from memory. */
function reachSourcing() {
  const register = JSON.parse(fs.readFileSync(REGISTER_PATH, "utf8")) as {
    reaches?: { sources?: RegisterSourceBlock[] }[];
    players?: { sources?: RegisterSourceBlock[] }[];
  };
  const live = { kalshi: 0, polymarket: 0 };
  const blocks = { kalshi: 0, polymarket: 0 };
  const markets = new Set<string>();
  for (const reach of register.reaches ?? []) {
    for (const block of reach.sources ?? []) {
      const source = block.source === "kalshi" ? "kalshi" : "polymarket";
      blocks[source] += 1;
      if (block.status === "missing") continue;
      live[source] += 1;
      if (block.market_id !== null && block.market_id !== undefined) {
        markets.add(`${source}:${block.market_id}`);
      }
    }
  }
  const winnerMarkets = new Set<string>();
  for (const player of register.players ?? []) {
    for (const block of player.sources ?? []) {
      if (block.status === "missing") continue;
      if (block.market_id !== null && block.market_id !== undefined) {
        winnerMarkets.add(`${block.source}:${block.market_id}`);
      }
    }
  }
  return { live, blocks, markets, winnerMarkets };
}

describe("UX-P146: the reach table, with bars and without", () => {
  const payload = loadPayload();
  const grid = readPlayoffGrid(payload.grids?.["mens-singles"]);

  it("has a grid to draw at all", () => {
    expect(grid).not.toBeNull();
    expect(grid!.rows.length).toBeGreaterThan(50);
    expect(grid!.columns.length).toBe(5);
  });

  it("the sourcing claim on the banner is TRUE of the register", () => {
    // A caption that claims a provenance the data does not have is worse than
    // no caption. Alex asked "is it real data?" — the answer has to be counted,
    // and counted here, next to the artifact that prints it.
    const { live, blocks, markets, winnerMarkets } = reachSourcing();
    expect(live.polymarket).toBe(SOURCING.reachCells);
    expect(markets.size).toBe(SOURCING.polymarketMarkets);
    expect(blocks.kalshi).toBe(SOURCING.kalshiReachBlocks);
    // The correction that goes on the banner: Kalshi runs NONE of them.
    expect(live.kalshi).toBe(SOURCING.kalshiReachLive);
    expect(winnerMarkets.size).toBe(SOURCING.winnerMarkets);
  });

  it("the bars are ON by default — Alex ruled 'Option A is great'", () => {
    // UX-P146 shipped this defaulting to OFF, with the two artifacts rendered
    // for Alex's eye. He ruled for the bars, so the default flipped; the prop
    // survives only so the rejected option can still be re-rendered from the
    // shipped component if the question is ever reopened.
    const html = renderToStaticMarkup(<PlayoffGrid grid={grid!} initialExpanded />);
    expect(html).toContain('data-testid="grid-spark-bar"');
    const plain = renderToStaticMarkup(
      <PlayoffGrid grid={grid!} initialExpanded sparkBars={false} />
    );
    expect(plain).not.toContain('data-testid="grid-spark-bar"');
  });

  it("every PRICED cell gets a bar and nothing else does", () => {
    const html = renderToStaticMarkup(
      <PlayoffGrid grid={grid!} initialExpanded sparkBars />
    );
    const bars = (html.match(/data-testid="grid-spark-bar"/g) ?? []).length;
    const numbers = (html.match(/data-testid="grid-cell" data-state="(live|stale|dark)"/g) ?? [])
      .length;
    expect(bars).toBeGreaterThan(200);
    // A bar is a length, so a cell with no number must not have one — a
    // zero-width bar under "no mkt" reads as "0%", which is a claim we are
    // explicitly not making.
    expect(bars).toBe(numbers);
    // …and the numbers themselves are untouched by the treatment.
    const plain = renderToStaticMarkup(
      <PlayoffGrid grid={grid!} initialExpanded sparkBars={false} />
    );
    const digitsOf = (markup: string) =>
      (markup.match(/>(\d{1,3}(\.\d)?%)</g) ?? []).join("");
    expect(digitsOf(html)).toBe(digitsOf(plain));
  });

  it("a bar's fill is the cell's own probability, not a rank", () => {
    // The failure that would make the whole treatment a lie: bars scaled to the
    // column's maximum rather than to 0-100, so a 6% favourite in a thin column
    // draws a full bar.
    const html = renderToStaticMarkup(
      <PlayoffGrid grid={grid!} initialExpanded sparkBars />
    );
    const fills = [...html.matchAll(/data-fill="([\d.]+)"/g)].map((m) => Number(m[1]));
    expect(fills.length).toBeGreaterThan(200);
    expect(Math.max(...fills)).toBeLessThanOrEqual(100);
    // Nothing is normalized to fill the cell: the largest bar on this data is
    // well under the full width, because nobody is a lock to reach anything.
    expect(Math.max(...fills)).toBeLessThan(100);
    expect(Math.min(...fills)).toBeGreaterThanOrEqual(0);
  });

  it("writes both mocks when UX_CAPTURE_DIR is set", () => {
    const dir = process.env.UX_CAPTURE_DIR;
    if (!dir) {
      expect(true).toBe(true);
      return;
    }
    fs.mkdirSync(dir, { recursive: true });

    const css = appStylesheet();
    const { live, blocks, markets, winnerMarkets } = reachSourcing();

    const page = (
      title: string,
      tag: string,
      pitch: string,
      body: string
    ) => `<!doctype html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Chance of reaching — ${title}</title>
<style>${css}</style>
<style>
  body{background:#F5F5F7;margin:0;font-family:-apple-system,BlinkMacSystemFont,"SF Pro Text",Segoe UI,Roboto,sans-serif}
  .banner{padding:14px 22px;font-size:13px;line-height:1.6;color:#374151;background:#fff;border-bottom:1px solid #E5E7EB}
  .banner b{color:#111827}
  .banner .tag{display:inline-block;margin-right:10px;padding:3px 9px;border-radius:6px;font:700 11px inherit;letter-spacing:.06em;text-transform:uppercase;background:#EEF2FF;color:#3730A3}
  .sourcing{margin-top:10px;padding-top:10px;border-top:1px dashed #E5E7EB;font-size:12px;color:#4B5563}
  .surface{background:#F5F5F7;padding:24px 0 64px}
</style></head>
<body>
<div class="banner">
  <span class="tag">${tag}</span>
  <b>${title}</b> ${pitch}
  <br><br>
  Open <b>reach-table-with-bars.html</b> and <b>reach-table-plain.html</b> in the same
  window, at the same width, and switch between the two tabs. Same data, same component,
  same CSS — the only difference is the bar.
  <div class="sourcing">
    <b>Is it real data?</b> Yes, and here is the count. The four reach columns are
    <b>${live.polymarket} cells from ${markets.size} separate Polymarket markets</b>, each one
    pinned in the register against exactly the question in its column — nothing is chained,
    simulated, or derived from another cell. The title column is the board's blend of
    <b>${winnerMarkets.size} winner markets</b> (Kalshi ×2, Polymarket ×2).
    One correction worth stating: Kalshi was asked for
    <b>all ${blocks.kalshi}</b> reach identities and runs <b>${live.kalshi}</b> of them, so the
    reach half is Polymarket-only today. That is what every <i>no mkt</i> below is — an
    absent market, not a broken link.
  </div>
</div>
<div class="surface">${body}</div>
</body></html>`;

    /* The grid inside the site's own container, the way the page now renders
       it — see `components/tournament/layout.ts`. A mock in a narrower frame
       than the real page would answer the busyness question at the wrong
       width, and width is most of that question. */
    const framed = (markup: string) =>
      `<div class="max-w-content mx-auto px-3 md:px-6 py-4"><div class="w-full"><div class="px-4 pb-16 lg:px-6">${markup}</div></div></div>`;

    const withBars = framed(
      renderToStaticMarkup(
        <PlayoffGrid grid={grid!} drawLabel="Men's singles" initialExpanded sparkBars />
      )
    );
    /* `sparkBars={false}` EXPLICITLY — added by UX-P149 as a repair, not a
       style change. This call relied on the prop's default being `false`, and
       UX-P147 flipped that default to `true` when Alex ruled "Option A is
       great". From that moment the rig wrote an "Option B — no spark bars"
       artifact WITH spark bars, and its own self-check below went red. It only
       ever runs under `UX_CAPTURE_DIR`, so CI never saw it. */
    const plain = framed(
      renderToStaticMarkup(
        <PlayoffGrid
          grid={grid!}
          drawLabel="Men's singles"
          initialExpanded
          sparkBars={false}
        />
      )
    );

    const barsPath = path.join(dir, "reach-table-with-bars.html");
    const plainPath = path.join(dir, "reach-table-plain.html");
    fs.writeFileSync(
      barsPath,
      page(
        "With spark bars",
        "Option A",
        "A single faint rule under each number, filled from the right to that cell's own " +
          "probability. One colour everywhere, no labels, no axis — the number is already the " +
          "label. This lane's recommendation, for what it is worth: the bar is what lets you " +
          "find the shape of a row without reading five numbers.",
        withBars
      )
    );
    fs.writeFileSync(
      plainPath,
      page(
        "No spark bars",
        "Option B",
        "The table exactly as it ships today. Nothing added — the argument for it is that " +
          "56 rows × 4 bars is 224 more marks on a surface whose whole appeal is that it is " +
          "quiet and every cell means one thing.",
        plain
      )
    );

    /* The rig must not write a page whose subject failed to render. */
    for (const [name, html] of [
      ["with-bars", withBars],
      ["plain", plain],
    ] as const) {
      expect(html).toContain('data-testid="playoff-grid"');
      expect(html).toContain("Carlos Alcaraz");
      if (!css.includes("@media (min-width:1024px)")) {
        throw new Error(`${name}: the compiled stylesheet is missing its desktop rules`);
      }
    }
    // …and the two files must differ in exactly the way claimed, and only that.
    expect(withBars).toContain('data-testid="grid-spark-bar"');
    expect(plain).not.toContain('data-testid="grid-spark-bar"');
    expect(fs.existsSync(barsPath)).toBe(true);
    expect(fs.existsSync(plainPath)).toBe(true);
  });
});
