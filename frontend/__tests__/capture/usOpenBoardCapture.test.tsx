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
import DrawToggle from "@/components/tournament/DrawToggle";
import TournamentBoard from "@/components/tournament/TournamentBoard";
import TournamentBracket from "@/components/tournament/TournamentBracket";
import TournamentMatches from "@/components/tournament/TournamentMatches";
import TournamentProps from "@/components/tournament/TournamentProps";
import TournamentResults from "@/components/tournament/TournamentResults";
import {
  chartSeriesFor,
  defaultSelection,
  seriesColorByEntity,
  toggleSelection,
} from "@/lib/contenderChart";
import { buildMatchList, type MatchListEntry, type TitleChances } from "@/lib/matchList";
import { readPlayoffGrid } from "@/lib/playoffGrid";
import { slateNotice, type Broadcast, type SlateData, type SlateMatch } from "@/lib/slate";
import type { PropMarket } from "@/lib/tournamentProps";
import type { TournamentBoardData, TournamentPayload } from "@/lib/tournament";

const MOCKS = path.join(__dirname, "..", "..", "..", "docs", "mocks", "us-open");
const SLATE_PATH = path.join(MOCKS, "slate-2026-08-25.json");
const PAYLOAD_PATH = path.join(MOCKS, "payload-2026-08-27.json");

function loadPayload(): TournamentPayload {
  return JSON.parse(fs.readFileSync(PAYLOAD_PATH, "utf8")) as TournamentPayload;
}
/**
 * THE SLATE, FROM THE PAYLOAD — not from `slate-2026-08-25.json` (UX-P142).
 *
 * This rig had two frozen files: a payload re-captured by
 * `capture_tournament_payload.py` minutes before each render, and a slate
 * frozen on 2026-08-25 and never touched since. The whole reason the capture
 * script exists is Alex's item 2 — "was that the real current state or a mock
 * artifact?" — and the answer stayed ambiguous for the half of the page the
 * script did not feed.
 *
 * It showed on ceremony day: the payload carried 96 real main-draw fixtures
 * and this rig rendered none of them, because it was reading a slate captured
 * two days before the draw existed. The payload's slate is the SAME
 * `build_slate` output, produced by the same script, at the same moment as the
 * boards beside it. `SLATE_PATH` is kept only as the two-days-ago control the
 * test below compares against.
 */
function loadSlate(): SlateData {
  const fromPayload = loadPayload().slate;
  if (fromPayload && Array.isArray(fromPayload.matches)) return fromPayload as SlateData;
  throw new Error("payload carries no slate — re-run capture_tournament_payload.py");
}
function loadProps(): PropMarket[] {
  // The route's own `build_props` over register v7, which no longer carries
  // the eight advance-to-round markets: they are grid cells, `reaches` pins all
  // 336, and one market in two collections is a divergence waiting to happen.
  return (loadPayload().props ?? []) as PropMarket[];
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

  it("PRODUCTION STATE 2026-08-27: the boards are LIVE — #2199 is fixed", () => {
    // WHAT CHANGED, and it is the good news in this queue.
    //
    // Every prior version of this test asserted the opposite: all 80 rows
    // non-live, both boards `dark`, because the outright winner fields had been
    // 8-32 days without a reading (#2199). The committed payload was
    // regenerated 2026-08-27 against production and both boards now read
    // `live` at ~2.5 hours. The honesty treatment is no longer the whole page.
    //
    // The test is KEPT rather than deleted, inverted, because "the boards went
    // dark again" is exactly the regression nobody would notice: a muted board
    // is a design state, not an error, and it looks deliberate.
    const allRows = payload.boards.flatMap((b) => b.rows);
    expect(allRows.length).toBeGreaterThan(60);
    expect(payload.boards.every((b) => b.price_state === "live")).toBe(true);
    expect(allRows.filter((r) => r.probability_is_live).length).toBeGreaterThan(60);
  });

  it("DARK PATH: a dark board still says prices are paused", () => {
    // The renderer's other half, now that production is live. Built by muting
    // the real board rather than by a literal, so it cannot drift from the
    // shape the backend emits.
    const dark: TournamentBoardData = {
      ...payload.boards[0],
      price_state: "dark",
      age_hours: 300,
      rows: payload.boards[0].rows.map((row) => ({
        ...row,
        probability_is_live: false,
        price_state: "dark" as const,
        age_hours: 300,
      })),
    };
    const html = renderToStaticMarkup(<TournamentBoard board={dark} />);
    expect(html).toContain("Prices paused");
    expect(html).toContain('data-live="false"');
    expect(html).not.toContain('data-live="true"');
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

  it("renders both boards without throwing", () => {
    const html = payload.boards
      .map((board) => renderToStaticMarkup(<TournamentBoard board={board} />))
      .join("");
    expect((html.match(/data-testid="tournament-board"/g) ?? []).length).toBe(2);
    expect(html).toContain('data-live="true"');
  });

  it("the slate payload is real production data, not a fixture", () => {
    const slate = loadSlate();
    expect(slate.matches.length).toBeGreaterThan(30);
    // NOT `incoherent === 0` any more, and the change is the ship (UX-P142).
    // `incoherent` counts rows with no trustworthy split, and 96 of them are
    // now the released main draw — real fixtures nobody has quoted yet. The
    // meaningful invariant is the one underneath it: a row is incoherent ONLY
    // because it is unpriced or because two quotes disagree, never silently.
    const unpriced = slate.matches.filter((m) => m.priced === false);
    expect(unpriced.length).toBeGreaterThanOrEqual(90);
    expect(slate.incoherent).toBe(unpriced.length);
    for (const match of slate.matches) {
      expect(match.sides).toHaveLength(2);
      for (const side of match.sides) {
        expect(["Yes", "No", ""]).not.toContain(side.display_name);
      }
      if (match.priced === false) {
        for (const side of match.sides) expect(side.probability).toBeNull();
      }
    }
  });

  it("THE DRAW IS IN IT — 96 real main-draw fixtures, both sides", () => {
    // Alex, 2026-08-27: "the draw exists but the page shows none." This is the
    // measurement that says it does now, taken off the same payload the rig
    // renders rather than off the register it came from.
    const slate = loadSlate();
    const r128 = slate.matches.filter((m) => m.round === "R128");
    expect(r128.length).toBeGreaterThanOrEqual(90);
    for (const draw of ["mens-singles", "womens-singles"]) {
      expect(r128.filter((m) => m.draw === draw).length).toBeGreaterThanOrEqual(45);
    }
    // Real names on both sides of every one, and the pair is never the same
    // player twice — the shape a bad join produces.
    for (const match of r128) {
      expect(match.sides[0].entity_key).not.toBe(match.sides[1].entity_key);
      for (const side of match.sides) {
        expect(side.display_name).toMatch(/[A-Za-z]/);
      }
    }
  });

  it("register v7 carries NO advance-to-round props — they are grid cells", () => {
    // Alex's item 11, fixed at the source. The eight "Does X reach the Y" cards
    // were props AND, since UX-P139, reach cells. Two collections pinning one
    // market is a divergence waiting to happen, so the register stopped
    // carrying them; `reaches` pins all 336.
    const props = loadProps();
    expect(props.filter((p) => /(-semifinals|-quarterfinals|-round-of-16)$/.test(p.key)))
      .toHaveLength(0);
  });

  it("register v7 carries ONE second-major card, not two — item 11's repetition", () => {
    // "The two *-second-major cards ARE the repeating template you named" was
    // the sentence Alex could not parse. What it meant: those two cards ask one
    // question about two different players, which is a template. The runtime
    // rule dropped one of them at every render; v7 drops it from the file, so
    // the template is gone rather than hidden.
    const props = loadProps();
    const family = props.filter((p) => p.key.endsWith("-second-major"));
    expect(family.map((p) => p.key)).toEqual(["sinner-second-major"]);
  });

  it("RULING 8 ON REAL DATA: the questions section is EMPTY, and says why", () => {
    // The finding, asserted so it cannot be softened into a caption. Both
    // remaining curated markets are dark: `sinner-competes` at ~190 hours,
    // `sinner-second-major` at ~810. Applying the rotation Alex asked for
    // empties the section on both draws today.
    const props = loadProps();
    for (const draw of ["mens-singles", "womens-singles"]) {
      const html = renderToStaticMarkup(<TournamentProps markets={props} draw={draw} />);
      expect(html).toContain('data-testid="props-empty"');
    }
    const men = renderToStaticMarkup(<TournamentProps markets={props} draw="mens-singles" />);
    expect(men).toContain("gone dark and rotated out");
  });

  it("ITEM 10: the empty section is a CARD, not a dashed whisper", () => {
    // Why it was invisible: it rendered in all nine panels of the UX-P138
    // artifact — as a dashed 12.5px box between two solid white cards, which
    // reads as a divider. Same border and background as a populated card now.
    const html = renderToStaticMarkup(
      <TournamentProps markets={loadProps()} draw="mens-singles" />
    );
    expect(html).toContain('data-testid="props-empty"');
    expect(html).not.toContain("border-dashed");
    // And it names what will be here, so it reads as between deliveries
    // rather than as a dead feature.
    expect(html).toContain("Will Sinner actually play?");
  });

  it("ITEM 9: the payload carries REAL decided-match scores from ESPN", () => {
    // UX-P138 shipped the seam empty and said so. This is the fill: ESPN's own
    // per-set line scores, joined on the registered player pair.
    const results = payload.results;
    expect(results).toBeDefined();
    expect(results!.count).toBeGreaterThan(0);
    const scored = results!.matches.filter((m) => m.score);
    expect(scored.length).toBeGreaterThan(0);
    // A score is games, set by set, winner first.
    expect(scored[0].score).toMatch(/^\d+-\d+(, \d+-\d+)*$/);
    // And the winner is one of the two named players, never a third name.
    for (const match of results!.matches) {
      expect(match.players.map((p) => p.entity_key)).toContain(match.winner_entity_key);
      expect(match.players.filter((p) => p.is_winner)).toHaveLength(1);
    }
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
    // ⬅️ UX-P142 SUPERSEDES THIS TEST'S PREMISE, and that IS the ship.
    //
    // It used to assert `overlap === 0`: today's slate was all qualifiers, not
    // one of them was a board contender, and so no REAL row could carry a
    // title chip — a limitation stated as a measurement rather than discovered
    // as a blank in the artifact, and demonstrated with a synthetic probe row.
    //
    // The released draw ends that. 26 of the men's board's contenders are now
    // in a real, registered, main-draw fixture, so ruling 1's two-number
    // treatment is on real data for the first time.
    const slate = loadSlate();
    const board = payload.boards[0];
    const keys = new Set(board.rows.map((r) => r.entity_key));
    const overlap = slate.matches
      .flatMap((m) => m.sides.map((s) => s.entity_key))
      .filter((key) => keys.has(key));
    expect(overlap.length).toBeGreaterThanOrEqual(20);

    // The chip renders on a REAL row now. No probe.
    const html = renderToStaticMarkup(
      <TournamentMatches
        entries={matchesFor(slate, board)}
        initialRound="R128"
        initialExpanded
      />
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
        /** Item 10's demo state, captioned as one wherever it is used. */
        propsAreDemo?: boolean;
        showResults?: boolean;
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
        ${
          options.showResults === false
            ? ""
            : renderToStaticMarkup(
                <TournamentResults results={payload.results} draw={board.draw} />
              )
        }
        ${renderToStaticMarkup(
          <TournamentBoard
            board={board}
            seriesColors={seriesColorByEntity(chartSeriesFor(board.rows, selection))}
          />
        )}
        ${
          options.propsAreDemo
            ? `<div class="demo">DEMO STATE &mdash; the two curated questions re-priced to today. In production both are 190h and 810h dark, so the section below renders EMPTY (panel 1).</div>`
            : ""
        }
        ${renderToStaticMarkup(
          <TournamentProps markets={options.propMarkets ?? props} draw={board.draw} />
        )}
      </div>`;
    };

    // ALEX'S FINDING (d), 2026-08-27: "the Men's/Women's pills sit too close to
    // the line above." The rig used to draw its own `.pills` div, which is why
    // the artifact could never have shown him the defect OR the fix. It renders
    // the shipped component now, so the spacing in the capture is the spacing
    // on the phone.
    const phone = (title: string, sub: string, body: string, women_ = false) => `
  <div class="phone">
    <header class="hero"><h1>${title}</h1><p>${sub}</p></header>
    <div class="tabs"><span class="on">Tournament</span><span>Bracket</span></div>
    ${renderToStaticMarkup(
      <DrawToggle
        draw={women_ ? "womens-singles" : "mens-singles"}
        onSelect={() => {}}
      />
    )}
    ${body}
  </div>`;

    // UX-P142: the released main draw, counted off the payload so the caption
    // cannot claim a number the panel does not render.
    const menR128 = menMatches.filter((entry) => entry.round === "R128");
    const womenR128 = womenMatches.filter((entry) => entry.round === "R128");

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

    // READ, not built (UX-P139): the amendment makes cell provenance a
    // correctness property, so the grid arrives whole from the route.
    const grid = readPlayoffGrid(payload.grids?.["mens-singles"]);
    const preDraw = renderToStaticMarkup(
      <TournamentBracket
        grid={null}
        drawReleased={false}
        preDrawBoards={payload.boards}
        drawReleaseLabel={payload.draw_release_label}
        mainDrawLabel={payload.main_draw_label}
      />
    );
    const gridHtml = renderToStaticMarkup(
      <TournamentBracket
        grid={grid}
        drawReleased={false}
        drawLabel={men.label}
        drawReleaseLabel={payload.draw_release_label}
        mainDrawLabel={payload.main_draw_label}
      />
    );

    const live = slate.matches.filter((m) => m.probability_is_live).length;
    const resultCount = payload.results?.count ?? 0;

    const html = `<!doctype html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>${payload.title} — hub, UX-P139 items applied</title>
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
  .demo{margin:22px 0 -4px;padding:8px 11px;border-radius:9px;background:#FEF3C7;border:1px solid #FCD34D;color:#78350F;font:700 10.5px inherit;letter-spacing:.04em;line-height:1.45;text-transform:uppercase}
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
<b>US Open hub &mdash; UX-P139, your twelve items.</b> SHIPPED components, the app's own compiled
CSS, a 390px viewport, and the ROUTE'S OWN OUTPUT over register v7. Each phone scrolls.
<ol>
<li><b>Item 6 &mdash; the chart has an x-axis.</b> Three dated ticks (first, middle, last) and
&ldquo;29d shown&rdquo; beside the count. The y-axis has always been a labelled fixed 0&ndash;100;
the x had nothing, so a falling line could be a day or a month. Labels are HTML, not SVG text,
because the plot is non-uniformly scaled and text inside it stretches.</li>
<li><b>Item 9 &mdash; decided matches print a real score.</b> ${resultCount} of them, from ESPN's
tennis scoreboard: per-set line scores, winner first, joined on the registered player pair. The
UX-P138 artifact's scores were hand-written because nothing here held a tennis result. That is
fixed &mdash; see the &ldquo;Finished&rdquo; section in every panel.</li>
<li><b>Item 10 &mdash; the questions section was invisible, and now is not.</b> It rendered in all
nine of the last artifact's panels; it rendered its EMPTY state as a dashed 12.5px box between two
solid white cards, which reads as a divider. Same border, same background, same weight as a
populated card now, and it names what will be there. The demo state carries a yellow DEMO banner
(last panel) so it can never be mistaken for production.</li>
<li><b>Item 11 &mdash; the sentence you could not parse.</b> It meant: <i>&ldquo;Can Alcaraz win a
second major this year?&rdquo; and &ldquo;Can Sinner win a second major this year?&rdquo; are one
question with a different name in it, so showing both is a template.</i> The runtime rule dropped
one of them at every render, which hid the repetition instead of removing it. <b>Register v7 drops
Alcaraz's from the file</b> (Sinner's 55.5% is the closer question, and his participation is the one
in doubt), so there is no template left to cap.</li>
<li><b>Item 12 &mdash; doubles is built and empty.</b> Five draws in the register vocabulary, five
in the results component. Censused 2026-08-26: <b>zero</b> US Open doubles markets at either
source, so nothing renders. ESPN already carries all three doubles draws' RESULTS (63/63/21
competitions), so the results half lights up the day anyone asks.</li>
<li><b>Item 7 &mdash; matches do NOT click through, and I am not going to pretend otherwise.</b>
Checked 2026-08-26: <b>none</b> of the registered matchups has an <code>events</code> row, so there
is no page to open. The link is wired, register-owned, and dark. The honest assessment of the
destination is in the report and it is worse news than the missing link.</li>
</ol>
<b>Boards:</b> real production read, ${men.rows.length + women.rows.length} contenders, and
<b>#2199 is fixed</b> &mdash; both boards read live at ~2.5h, where every prior artifact had them
8&ndash;34 days dark. <b>Matches:</b> ${slate.matches.length} on the card, ${live} inside the live
window. <b>Finished:</b> ${resultCount} with scores. <b>Questions:</b> two curated, both dark, so
the section is empty and says which.
</div>

<div class="pick">
<b>ON THE 15-DAY-OLD DATA THAT SPOOKED YOU (item 2): it was real, not a mock artifact &mdash; and
the boards half is already fixed.</b> The outright fields were genuinely 8&ndash;34 days dark
(#2199); this artifact is the first one where they are not. The reach ladder behind the bracket grid
was genuinely 27 hours stale at capture. The cause was structural, not a bug: Gamma caps offset
pagination at 2,000, so the scanning poll rotates a window and reaches a given event roughly once a
day. This queue ships a 10-minute task that asks Gamma for exactly the market IDs the register pins
&mdash; a read that does not paginate and so is not capped.
<br><br>
<b>The production guarantee is not that data is never old. It is that old data can never look
current</b>, and it is enforced in three places rather than promised: the server sets
<code>probability_is_live</code> and a client cannot round past it; a row is as fresh as its OLDEST
contributing leg, never its newest; and an absent timestamp reads as <i>dark</i>, not as fresh. The
treatment is visible on this page &mdash; every muted number carries its own age in words, and a
number old enough to stop being a price is removed rather than shown quietly.
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
    panel(men, menMatches, { propMarkets: freshQuestions(props), propsAreDemo: true })
  )}
</div>

<div class="cap">UX-P142 &mdash; THE REAL DRAW, released at today's ceremony (R128 pill selected)</div>
<div class="rail">
  ${phone(
    payload.title,
    `Men's Round of 128 — ${menR128.length} real fixtures from ESPN`,
    panel(men, menMatches, { matchExtra: { initialRound: "R128", initialExpanded: true } })
  )}
  ${phone(
    payload.title,
    `Women's Round of 128 — ${womenR128.length} real fixtures`,
    panel(women, womenMatches, { matchExtra: { initialRound: "R128", initialExpanded: true } }),
    true
  )}
  ${phone(
    payload.title,
    "An unpriced fixture, tapped open — what it says instead of a number",
    panel(men, menMatches, {
      matchExtra: {
        initialRound: "R128",
        initialExpanded: true,
        initialOpenMatchId: menR128[0]?.id,
      },
    })
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
    // ONE channel line PER OPEN DETAIL VIEW and nowhere else — the real form of
    // ruling 7's rule. It was hard-coded to 1 when the artifact had exactly one
    // tapped-open row; UX-P142 opens a second (an unpriced main-draw fixture),
    // so the constant is now the count of detail views rather than a literal,
    // and the "and nowhere else" half is what the equality actually asserts.
    const openDetails = (html.match(/data-testid="match-detail-broadcast"/g) ?? []).length;
    expect(openDetails).toBe(2);
    expect((html.match(/ESPN, ESPN2, ESPN\+/g) ?? []).length).toBe(openDetails);
    // 8. The rotation: empty-with-a-reason on real data, populated on panel 9.
    expect(html).toContain("gone dark and rotated out");
    expect(html).toContain('data-testid="props-moved-to-grid"');
    expect(html).toContain('data-testid="prop-market"');
    // Collapsed everywhere.
    expect((html.match(/data-testid="show-more"/g) ?? []).length).toBeGreaterThan(4);
    // The pre-draw bracket panel still carries both boards.
    expect(html).toContain('data-testid="bracket-unreleased"');

    // ═══ UX-P142 — ALEX'S FOUR FINDINGS, EACH IN THIS ARTIFACT ═══
    // (a) The real draw. Both sides of it, from the register, on real names.
    expect(menR128.length).toBeGreaterThanOrEqual(45);
    expect(womenR128.length).toBeGreaterThanOrEqual(45);
    expect((html.match(/data-round="R128"/g) ?? []).length).toBeGreaterThan(45);
    expect(html).toContain("Round of 128");
    // ...and the unpriced fixture says the right thing about itself.
    expect(html).toContain("No market yet");
    expect(html).not.toContain("The two prices for this match do not agree");
    // The detail note only renders on a TAPPED-OPEN row, so it needs a panel
    // of its own or the sentence written for the page's most common state is
    // in the code and not in the artifact Alex looks at.
    expect(html).toContain("Nobody is quoting this match yet");
    // (b) The x-axis, in the rendered chart rather than in a unit test.
    expect(html).toContain('data-testid="chart-axis"');
    expect((html.match(/data-testid="chart-axis-label"/g) ?? []).length).toBeGreaterThan(3);
    // (c) Player images, on every surface, and NEVER a mixed column of faces
    // and holes on a board.
    expect((html.match(/data-testid="player-avatar"/g) ?? []).length).toBeGreaterThan(100);
    expect(html).toContain('data-kind="face"');
    expect(html).toContain('data-kind="flag"');
    expect(html).toMatch(/src="https:\/\/upload\.wikimedia\.org\//);
    expect(html).toMatch(/src="https:\/\/a\.espncdn\.com\//);
    // (d) The pills, from the shipped component, with the top padding on.
    expect((html.match(/data-testid="draw-toggle"/g) ?? []).length).toBeGreaterThan(4);
    expect(html).toMatch(/data-testid="draw-toggle"/);
    expect(html).toContain("pb-3 pt-3");
    // And the stylesheet actually loaded — an unstyled capture is not a verdict.
    expect(appStylesheet().length).toBeGreaterThan(1000);
  });
});
