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
  admittedFinalScore,
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
/** A reader clock for the finished mount. A finished game reads its completion boundary, never this. */
const READER_NOW = "2026-10-04T18:00:00Z";

function history(over: Partial<EventHistoryResponse> = {}): EventHistoryResponse {
  return { ...structuredClone(RAW), ...over };
}

function mounted(h: EventHistoryResponse = history()): ProjectedFinalPointsInput {
  const d = projectedFinalPointsMount({ sportKey: NFL, eventStatus: "completed", history: h, now: READER_NOW });
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
/** The final the page's hero prints for 14780549. */
const PAGE_FINAL = { home: 27, away: 7 };

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
    const html = renderToStaticMarkup(
      <ProjectedFinalPointsChartView input={input} {...teams} finalScore={PAGE_FINAL} cursorAt={null} />,
    );
    expect(html).toContain("DraftKings");
    expect(html).toMatch(/data-actual="home"[^>]*>27 final/);
    expect(html).toMatch(/data-actual="away"[^>]*>7 final/);
    expect(html).not.toMatch(/—\s*final/);
    expect(html).toContain("27.5");
    expect(html).toContain("Last projection before the final");
    expect(html).not.toContain("data-final=");
  });

  it("without the page's final, the same last row is only the last recorded score", () => {
    const html = renderToStaticMarkup(<ProjectedFinalPointsChartView input={input} {...teams} cursorAt={null} />);
    expect(html).toMatch(/data-actual="home"[^>]*>27 last recorded/);
    expect(html).toMatch(/data-actual="away"[^>]*>7 last recorded/);
    expect(html).not.toMatch(/\d+ final</);
  });

  it("never says kickoff anywhere a reader can see", () => {
    const html = renderToStaticMarkup(<ProjectedFinalPointsChartView input={input} {...teams} cursorAt={null} />);
    expect(html.toLowerCase()).not.toContain("kickoff");
    expect(html.toLowerCase()).not.toContain("kick-off");
  });
});

describe("the last recorded row is not the final: 14780549 with its 27–7 row missing", () => {
  // The real fixture, minus only the final 27–7 row. 26–7 (02:50:51Z) is the state before the
  // extra point; the game's completion stamp is still present, so the module still mounts.
  const scores = RAW.score_history ?? [];
  const missingFinalRow = history({ score_history: scores.slice(0, -1) });
  const input = mounted(missingFinalRow);
  const view = (finalScore: { home: number; away: number } | null, cursorAt: number | null = null) =>
    renderToStaticMarkup(
      <ProjectedFinalPointsChartView input={input} {...teams} finalScore={finalScore} cursorAt={cursorAt} />,
    );

  it("the trimmed history really ends on 26–7, and the dropped row was 27–7", () => {
    expect(scores[scores.length - 1]).toMatchObject({ home_score: 27, away_score: 7 });
    expect(series(input).latestActual).toMatchObject({ home: 26, away: 7 });
    expect(series(input).phase).toBe("after");
  });

  it("labels 26–7 the last recorded score and shows the page's 27–7 final apart from it", () => {
    const html = view(PAGE_FINAL);
    expect(html).toMatch(/data-actual="home"[^>]*>26 last recorded/);
    expect(html).toMatch(/data-actual="away"[^>]*>7 last recorded/);
    expect(html).toMatch(/data-final="home"[^>]*>27 final/);
    expect(html).toMatch(/data-final="away"[^>]*>7 final/);
    expect(html).not.toMatch(/26 final/);
  });

  it("the final is not drawn into the history: the score steps still end at 26–7", () => {
    expect(series(input).actualSteps.map((a) => [a.home, a.away]).pop()).toEqual([26, 7]);
    expect(series(input).actualSteps.some((a) => a.home === 27)).toBe(false);
  });

  it("with no final from the page, nothing is called final", () => {
    const html = view(null);
    expect(html).toMatch(/data-actual="home"[^>]*>26 last recorded/);
    expect(html).not.toContain("data-final=");
    expect(html).not.toMatch(/\d+ final</);
  });

  it("no inspected moment shows the final or any score recorded after it", () => {
    for (const cursor of inspectionInstants(series(input))) {
      const html = view(PAGE_FINAL, cursor);
      expect(html).not.toContain("data-final=");
      expect(html).not.toMatch(/\d+ (final|last recorded)</);
      expect(html).not.toMatch(/>27 scored</);
    }
  });
});

describe("the page's final score is refused unless it is a whole pair", () => {
  it.each([
    ["absent", null],
    ["half a pair", { home: 27, away: null }],
    ["not a number", { home: Number.NaN, away: 7 }],
    ["infinite", { home: Number.POSITIVE_INFINITY, away: 7 }],
    ["negative", { home: -1, away: 7 }],
    ["fractional", { home: 27.5, away: 7 }],
  ] as const)("%s", (_label, pair) => {
    expect(admittedFinalScore(pair as never)).toBeNull();
  });

  it("a whole pair, including a real 0–0, is admitted as given", () => {
    expect(admittedFinalScore({ home: 27, away: 7 })).toEqual({ home: 27, away: 7 });
    expect(admittedFinalScore({ home: 0, away: 0 })).toEqual({ home: 0, away: 0 });
  });

  it("a refused pair leaves the last row as the last recorded score, never a dash", () => {
    const html = renderToStaticMarkup(
      <ProjectedFinalPointsModule sportKey={NFL} eventStatus="completed" history={history()} finalScore={{ home: 27, away: null }} {...teams} />,
    );
    expect(html).toMatch(/data-actual="home"[^>]*>27 last recorded/);
    expect(html).not.toContain("data-final=");
    expect(html).not.toMatch(/—\s*final/);
  });

  it("the module passes the page's whole pair through: 27–7 reads final", () => {
    const html = renderToStaticMarkup(
      <ProjectedFinalPointsModule sportKey={NFL} eventStatus="completed" history={history()} finalScore={PAGE_FINAL} {...teams} />,
    );
    expect(html).toMatch(/data-actual="home"[^>]*>27 final/);
    expect(html).not.toContain("data-final=");
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
    const html = renderToStaticMarkup(
      <ProjectedFinalPointsChartView input={input} {...teams} finalScore={PAGE_FINAL} cursorAt={cursor} />,
    );
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
    const d = projectedFinalPointsMount({ sportKey: NFL, eventStatus: "completed", history: h, now: READER_NOW });
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
    expect(RAW.status).toBe("completed");
    expect(html({})).toContain("Projected final points");
    expect(html({ eventStatus: "closed" })).toContain("Projected final points");
    // completed and closed are one phase on either side.
    expect(html({ history: history({ status: "closed" }) })).toContain("Projected final points");
  });

  it("the module carries the history's own status through its memo, in both directions", () => {
    // Dropping status would refuse every mount; reading it from anywhere but the history would admit this one.
    expect(html({ history: history({ status: "live" }) })).toBe("");
    expect(html({ history: history({ status: "completed" }) })).toContain("Projected final points");
  });

  it.each([
    ["another sport", { sportKey: "baseball_mlb" }, "sport_not_supported"],
    // The authentic rows carry no provenance (#10461), so only a finished, whole-served page may read them.
    ["a live game whose rows carry no provenance", { eventStatus: "live", history: history({ status: "live", completed_at: undefined }) }, "no_named_book"],
    ["a scheduled game whose rows carry no provenance", { eventStatus: "scheduled", history: history({ status: "scheduled", completed_at: undefined }) }, "no_named_book"],
    ["a postponed game", { eventStatus: "postponed" }, "status_not_supported"],
    ["no status", { eventStatus: null }, "status_not_supported"],
    ["no completion boundary", { history: history({ completed_at: undefined }) }, "not_finished"],
    ["no history yet", { history: null }, "no_history"],
    // The page and its history disagree on the phase, or the history does not say: refused, never reconciled.
    ["a finished page over a live history, completion stamped", { history: history({ status: "live" }) }, "history_phase_mismatch"],
    ["a finished page over a scheduled history, completion stamped", { history: history({ status: "scheduled" }) }, "history_phase_mismatch"],
    ["a finished page over a history with a null status", { history: history({ status: null }) }, "history_phase_mismatch"],
    ["a finished page over a history with no status", { history: history({ status: undefined }) }, "history_phase_mismatch"],
    ["a finished page over a postponed history", { history: history({ status: "postponed" }) }, "history_phase_mismatch"],
    ["a live page over a finished history", { eventStatus: "live" }, "history_phase_mismatch"],
    ["a scheduled page over a finished history", { eventStatus: "scheduled" }, "history_phase_mismatch"],
    ["no named sportsbook", { history: history({ bookmaker_history: { not_a_book: RAW.bookmaker_history!.draftkings } }) }, "no_named_book"],
  ] as const)("%s renders nothing, not an empty frame", (_label, props, reason) => {
    expect(html(props as never)).toBe("");
    const d = projectedFinalPointsMount({
      sportKey: NFL,
      eventStatus: "completed",
      history: history(),
      now: READER_NOW,
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
    // The final is the hero's own pair, under the hero's gates: finished, not voided, not stoppage filler.
    expect(page).toMatch(
      /finalScore=\{isFinished && !venueVoided && !heroScoreIsStoppageFiller \? \{ home: bestHomeScore, away: bestAwayScore \} : null\}/,
    );
    expect(page.indexOf("<ProjectedFinalPointsModule")).toBeGreaterThan(page.indexOf("<ScoreDifferentialChart"));
  });
});

/**
 * #10461 before and during. The same authentic game, re-served as a live
 * payload would be once the route names each row: no completion boundary,
 * and every row `recorded` with its capture 17 s into its displayed minute.
 */
describe("before and during: rows count only by served provenance", () => {
  const withProvenance = (h: EventHistoryResponse, kind = "recorded"): EventHistoryResponse => ({
    ...h,
    bookmaker_history: Object.fromEntries(
      Object.entries(h.bookmaker_history ?? {}).map(([book, rows]) => [
        book,
        rows.map((r) => ({ ...r, kind, observed_at: r.timestamp.replace(/:00\+00:00$/, ":17+00:00") })),
      ]),
    ),
  });
  const livePayload = (over: Partial<EventHistoryResponse> = {}) =>
    withProvenance(history({ completed_at: undefined, status: "live", ...over }));
  const MID_GAME = "2026-09-29T01:30:00Z";
  const PREGAME = "2026-09-29T00:00:00Z";

  it("the derived rows really are recorded captures inside their own minute", () => {
    const rows = livePayload().bookmaker_history!.draftkings!;
    expect(rows.every((r) => r.kind === "recorded" && Date.parse(r.observed_at!) - Date.parse(r.timestamp) === 17_000)).toBe(true);
  });

  it("during: mounts, places readings at their capture, shows nothing after now, and floors actuals at the observed state", () => {
    const d = projectedFinalPointsMount({ sportKey: NFL, eventStatus: "live", history: livePayload(), now: MID_GAME });
    if (!d.mount) throw new Error(`expected a mount, got ${d.reason}`);
    expect(d.input.asOf).toBe(MID_GAME);
    expect(d.input.kickoffAt).toBeNull();
    expect(d.input.scoreObservationStartAt).toBe(FIRST_RECORDED_STATE);
    const s = series(d.input);
    expect(s.phase).toBe("during");
    expect(s.end).toBe(at(MID_GAME));
    expect(s.segments.flat().every((p) => p.at <= at(MID_GAME) && new Date(p.at).getUTCSeconds() === 17)).toBe(true);
    expect(s.actualSteps.length).toBeGreaterThan(0);
    expect(s.actualSteps[0].at).toBeGreaterThanOrEqual(at(FIRST_RECORDED_STATE));
    expect(s.actualSteps.every((a) => a.at <= at(MID_GAME))).toBe(true);
    const html = renderToStaticMarkup(<ProjectedFinalPointsChartView input={d.input} {...teams} cursorAt={null} />);
    expect(html).toContain('data-projected-final-points="during"');
    // Each side's readout is a score so far: never "final", never "last recorded".
    expect(html.match(/data-actual="(home|away)">\d+ scored</g)).toHaveLength(2);
    expect(html).not.toContain("data-final=");
    expect(html).not.toMatch(/\d+ final<|last recorded/);
    expect(html).toContain("┅ Actual score");
  });

  it("during without an observed game state renders nothing: the schedule is never a kickoff", () => {
    const d = projectedFinalPointsMount({ sportKey: NFL, eventStatus: "live", history: livePayload({ period_markers: [] }), now: MID_GAME });
    expect(d.mount ? "mount" : d.reason).toBe("no_recorded_game_state");
  });

  it("before: forecasts with no actual score and no invented 0–0, and no first-quarter marker needed", () => {
    const d = projectedFinalPointsMount({ sportKey: NFL, eventStatus: "scheduled", history: livePayload({ status: "scheduled", period_markers: [] }), now: PREGAME });
    if (!d.mount) throw new Error(`expected a mount, got ${d.reason}`);
    const s = series(d.input);
    expect(s.phase).toBe("before");
    expect(s.actualSteps).toEqual([]);
    expect(s.latestActual).toBeNull();
    expect(s.segments.flat().every((p) => p.at <= at(PREGAME))).toBe(true);
    const html = renderToStaticMarkup(<ProjectedFinalPointsChartView input={d.input} {...teams} cursorAt={null} />);
    expect(html).toContain('data-projected-final-points="before"');
    expect(html).not.toContain("data-actual=");
    expect(html).not.toMatch(/\d+ scored/);
    expect(html).not.toContain("┅ Actual score");
  });

  it("scheduled with retained past game state still draws forecasts only", () => {
    // The live payload keeps its observed Q1 marker and recorded scores; the clock is mid-game.
    const h = livePayload({ status: "scheduled" });
    expect(h.period_markers?.length).toBeGreaterThan(0);
    expect((h.score_history ?? []).some((r) => Date.parse(r.timestamp) <= at(MID_GAME))).toBe(true);
    const d = projectedFinalPointsMount({ sportKey: NFL, eventStatus: "scheduled", history: h, now: MID_GAME });
    if (!d.mount) throw new Error(`expected a mount, got ${d.reason}`);
    expect(d.input.scoreObservationStartAt).toBeNull();
    expect(d.input.kickoffAt).toBeNull();
    expect(d.input.actuals).toEqual([]);
    expect(d.input.finalAt).toBeNull();
    const s = series(d.input);
    expect(s.phase).toBe("before");
    expect(s.actualSteps).toEqual([]);
    expect(s.latestActual).toBeNull();
    for (const t of inspectionInstants(s)) {
      const v = seriesAt(d.input, t);
      if (!v.supported) continue;
      expect(v.phase).toBe("before");
      expect(v.actualSteps).toEqual([]);
    }
    const html = renderToStaticMarkup(<ProjectedFinalPointsChartView input={d.input} {...teams} cursorAt={null} />);
    expect(html).toContain('data-projected-final-points="before"');
    expect(html).not.toContain("data-actual=");
    expect(html).not.toContain("┅ Actual score");
  });

  it("a completion stamp on an unfinished page is refused, never read as after", () => {
    const AFTER_COMPLETION = "2026-09-29T04:00:00Z";
    for (const [eventStatus, status] of [["live", "live"], ["scheduled", "scheduled"]] as const) {
      const h = livePayload({ status, completed_at: COMPLETED_AT });
      const d = projectedFinalPointsMount({ sportKey: NFL, eventStatus, history: h, now: AFTER_COMPLETION });
      expect([eventStatus, d.mount ? "mount" : d.reason]).toEqual([eventStatus, "stale_completion"]);
      const html = renderToStaticMarkup(
        <ProjectedFinalPointsModule sportKey={NFL} eventStatus={eventStatus} history={h} {...teams} />,
      );
      expect(html).toBe("");
    }
  });

  it("rows the route names synthetic never mount a live chart", () => {
    const h = withProvenance(history({ completed_at: undefined, status: "live" }), "synthetic");
    const d = projectedFinalPointsMount({ sportKey: NFL, eventStatus: "live", history: h, now: MID_GAME });
    expect(d.mount ? "mount" : d.reason).toBe("no_named_book");
  });

  it("a finished page with provenance reads it, and the paid finished view is unchanged", () => {
    const d = projectedFinalPointsMount({ sportKey: NFL, eventStatus: "completed", history: withProvenance(history()), now: READER_NOW });
    if (!d.mount) throw new Error(`expected a mount, got ${d.reason}`);
    expect(d.input.sourceKey).toBe("draftkings");
    const before = series(mounted());
    const after = series(d.input);
    expect(after.latest).toMatchObject({ home: before.latest.home, away: before.latest.away, at: before.latest.at + 17_000 });
    expect(after.segments.flat().map((p) => [p.home, p.away])).toEqual(before.segments.flat().map((p) => [p.home, p.away]));
  });
});
