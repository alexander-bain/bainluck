/**
 * #10239 — the finished-NFL mount, gated on one AUTHENTIC payload.
 *
 * The fixture is event 14780549 (PHI @ CHI, final CHI 27–7) as the history
 * route served it, trimmed to three whole books. Provenance and the raw read's
 * sha256 ride inside the file. Nobody observed this game's kickoff, so every
 * test here runs with `kickoffAt` null and the score floor taken from the
 * first-quarter marker an instrument saw.
 */

import fs from "fs";
import path from "path";
import React from "react";
import { renderToStaticMarkup } from "react-dom/server";
import ProjectedFinalPointsModule, {
  projectedFinalPointsMount,
} from "../../components/event/ProjectedFinalPointsModule";
import { ProjectedFinalPointsChartView } from "../../components/event/ProjectedFinalPointsChart";
import {
  buildProjectedFinalPointsSeries,
  inspectionInstants,
  seriesAt,
  type ProjectedFinalPointsInput,
  type ProjectedFinalPointsSeries,
} from "@/lib/projectedFinalPointsSeries";
import type { EventHistoryResponse } from "@/lib/types";

const FIXTURE = path.join(__dirname, "../fixtures/10239/finished-nfl-14780549-history.json");
const RAW = JSON.parse(fs.readFileSync(FIXTURE, "utf8")) as EventHistoryResponse & {
  _provenance: { raw_sha256: string; books_kept: string[]; complete_pair_counts_full_payload: Record<string, number> };
};
const NFL = "americanfootball_nfl";
/** The 1st Quarter marker's `not_before`, verbatim: the last poll that showed no first quarter. */
const FIRST_RECORDED_STATE = "2026-09-29T00:16:50.361763+00:00";
const COMPLETED_AT = "2026-09-29T03:12:51.383951+00:00";

function history(over: Partial<EventHistoryResponse> = {}): EventHistoryResponse {
  return { ...structuredClone(RAW), ...over };
}

function mounted(h: EventHistoryResponse = history()): ProjectedFinalPointsInput {
  const d = projectedFinalPointsMount({ sportKey: NFL, eventStatus: "completed", history: h });
  if (!d.mount) throw new Error(`expected a mount, got ${d.reason}`);
  return d.input;
}

function series(input: ProjectedFinalPointsInput): ProjectedFinalPointsSeries {
  const s = buildProjectedFinalPointsSeries(input);
  if (!s.supported) throw new Error("expected supported");
  return s;
}

const teams = { homeTeam: "Chicago Bears", awayTeam: "Philadelphia Eagles" };
const at = (iso: string) => Date.parse(iso);

describe("the fixture is the paid specimen", () => {
  it("carries the raw read's hash and the kept books' full-payload counts", () => {
    expect(RAW._provenance.raw_sha256).toBe("17052d6e14d5eb9191f559d8a3c275b769008f931dbe57507c1a48e781fa8d09");
    expect(RAW.event_id).toBe(14780549);
    expect(Object.keys(RAW.bookmaker_history ?? {}).sort()).toEqual([...RAW._provenance.books_kept].sort());
  });

  it("the trim cannot fake the book choice: DraftKings leads the FULL payload, not just the subset", () => {
    const counts = Object.entries(RAW._provenance.complete_pair_counts_full_payload).sort((a, b) => b[1] - a[1]);
    expect(counts[0][0]).toBe("draftkings");
    expect(counts[1][0]).toBe("williamhill_us");
  });
});

describe("authentic finished NFL game, kickoff unknown", () => {
  const input = mounted();
  const s = series(input);

  it("mounts with the picker's book, no kickoff, and the first recorded game state as the score floor", () => {
    expect(input.sourceKey).toBe("draftkings");
    expect(input.kickoffAt).toBeNull();
    expect(input.scoreObservationStartAt).toBe(FIRST_RECORDED_STATE);
    expect(input.finalAt).toBe(COMPLETED_AT);
    expect(s.sourceName).toBe("DraftKings");
    expect(s.phase).toBe("after");
  });

  it("admits the recorded scores from the floor, starting with the real recorded 0–0", () => {
    expect(s.actualSteps.map((a) => [a.home, a.away])).toEqual([
      [0, 0], [7, 0], [10, 0], [10, 7], [13, 7], [20, 7], [26, 7], [27, 7],
    ]);
    expect(s.actualSteps[0].at).toBe(at(FIRST_RECORDED_STATE));
    expect(s.latestActual).toMatchObject({ home: 27, away: 7 });
  });

  it("ends on DraftKings' last projection before the final, and never appends 27–7", () => {
    expect(s.latest).toMatchObject({ home: 27.5, away: 7.0 });
    expect(s.latest.at).toBe(at("2026-09-29T03:11:00Z"));
    for (const seg of s.segments) for (const p of seg) expect(p.at).toBeLessThan(at(COMPLETED_AT));
  });

  it("prints the recorded final beside the last projection: no '— final'", () => {
    const html = renderToStaticMarkup(<ProjectedFinalPointsChartView input={input} {...teams} cursorAt={null} />);
    expect(html).toContain("DraftKings");
    expect(html).toMatch(/data-actual="home"[^>]*>27 final/);
    expect(html).toMatch(/data-actual="away"[^>]*>7 final/);
    expect(html).not.toMatch(/—\s*final/);
    expect(html).toContain("27.5");
    expect(html).toContain("Last projection before the final");
  });

  it("never says kickoff anywhere a reader can see", () => {
    const html = renderToStaticMarkup(<ProjectedFinalPointsChartView input={input} {...teams} cursorAt={null} />);
    expect(html.toLowerCase()).not.toContain("kickoff");
    expect(html.toLowerCase()).not.toContain("kick-off");
  });
});

describe("inspection is retained and nothing later leaks in", () => {
  const input = mounted();
  const instants = inspectionInstants(series(input));

  it("every inspectable moment reads only projections and scores recorded by then", () => {
    expect(instants.length).toBeGreaterThan(100);
    for (const t of instants) {
      const v = seriesAt(input, t);
      if (!v.supported) continue;
      for (const seg of v.segments) for (const p of seg) expect(p.at).toBeLessThanOrEqual(t);
      for (const a of v.actualSteps) expect(a.at).toBeLessThanOrEqual(t);
      expect(v.end).toBeLessThanOrEqual(t);
    }
  });

  it("mid-game, the readout shows the score at the cursor, not the 20–7 recorded later", () => {
    const cursor = instants.filter((t) => t < at("2026-09-29T02:16:51.214009Z")).pop()!;
    expect(cursor).toBeGreaterThan(at("2026-09-29T02:05:51.252553Z"));
    const html = renderToStaticMarkup(<ProjectedFinalPointsChartView input={input} {...teams} cursorAt={cursor} />);
    expect(html).toMatch(/data-actual="home"[^>]*>13 scored/);
    expect(html).not.toMatch(/>20 scored/);
    expect(html).not.toMatch(/27 (final|scored)/);
    expect(html).toContain("Projection at this point");
  });

  it("before the first recorded game state, a cursor shows no actual score at all", () => {
    const cursor = instants.filter((t) => t < at(FIRST_RECORDED_STATE)).pop()!;
    expect(cursor).toBeDefined();
    const v = seriesAt(input, cursor);
    expect(v.supported && v.actualSteps).toEqual([]);
    const html = renderToStaticMarkup(<ProjectedFinalPointsChartView input={input} {...teams} cursorAt={cursor} />);
    expect(html).not.toContain("data-actual=");
  });
});

describe("the score floor refuses an estimated or unobserved marker", () => {
  const markers = RAW.period_markers ?? [];
  const q1 = markers[0];
  const withQ1 = (over: Partial<typeof q1>) => history({ period_markers: [{ ...q1, ...over }, ...markers.slice(1)] });
  const reason = (h: EventHistoryResponse) => {
    const d = projectedFinalPointsMount({ sportKey: NFL, eventStatus: "completed", history: h });
    return d.mount ? "mount" : d.reason;
  };

  it("the authentic marker is an observed first-quarter state", () => {
    expect(q1).toMatchObject({ period: "1st Quarter", source: "espn_state", precision: "first_seen", not_before: FIRST_RECORDED_STATE });
  });

  it.each([
    ["an estimated marker", { source: "estimated" }],
    ["a marker with no source", { source: undefined }],
    ["a first-score marker", { precision: "first_score" }],
    ["a marker with no lower bound", { not_before: null }],
  ])("omits the module for %s", (_label, over) => {
    expect(reason(withQ1(over))).toBe("no_recorded_game_state");
  });

  it("does not borrow a later quarter's marker as the floor", () => {
    expect(reason(history({ period_markers: markers.slice(1) }))).toBe("no_recorded_game_state");
    expect(reason(history({ period_markers: undefined }))).toBe("no_recorded_game_state");
  });

  it("does not take the marker's timestamp in place of its not_before", () => {
    expect(mounted().scoreObservationStartAt).not.toBe(q1.timestamp);
  });
});

describe("supported and unsupported mounts", () => {
  const html = (props: Partial<React.ComponentProps<typeof ProjectedFinalPointsModule>>) =>
    renderToStaticMarkup(
      <ProjectedFinalPointsModule sportKey={NFL} eventStatus="completed" history={history()} {...teams} {...props} />,
    );

  it("a finished NFL game with every input renders the module", () => {
    expect(html({})).toContain("Projected final points");
    expect(html({ eventStatus: "closed" })).toContain("Projected final points");
  });

  it.each([
    ["another sport", { sportKey: "baseball_mlb" }, "sport_not_supported"],
    ["a live game", { eventStatus: "live" }, "not_finished"],
    ["a scheduled game", { eventStatus: "scheduled" }, "not_finished"],
    ["no completion boundary", { history: history({ completed_at: undefined }) }, "not_finished"],
    ["no history yet", { history: null }, "not_finished"],
    ["no named sportsbook", { history: history({ bookmaker_history: { not_a_book: RAW.bookmaker_history!.draftkings } }) }, "no_named_book"],
  ] as const)("%s renders nothing, not an empty frame", (_label, props, reason) => {
    expect(html(props as never)).toBe("");
    const d = projectedFinalPointsMount({
      sportKey: NFL,
      eventStatus: "completed",
      history: history(),
      ...(props as object),
    } as never);
    expect(d.mount ? "mount" : d.reason).toBe(reason);
  });

  it("the module reads what the page adopted: no fetch or polling of its own", () => {
    const src = fs.readFileSync(path.join(__dirname, "../../components/event/ProjectedFinalPointsModule.tsx"), "utf8");
    expect(src).not.toMatch(/\bfetch\w*\(|useSWR|setInterval|@\/lib\/api/);
  });

  it("the page only imports the module and calls it beside the score section", () => {
    const page = fs.readFileSync(path.join(__dirname, "../../app/events/[id]/page.tsx"), "utf8");
    expect(page.match(/ProjectedFinalPointsModule/g)?.length).toBe(3);
    expect(page).toMatch(/<ProjectedFinalPointsModule\s+sportKey=\{event\.sport\}\s+eventStatus=\{event\.status\}\s+history=\{historyData\}/);
    expect(page.indexOf("<ProjectedFinalPointsModule")).toBeGreaterThan(page.indexOf("<ScoreDifferentialChart"));
  });
});
