/**
 * #10294 — a live game page shows a new score as soon as one of its own reads
 * carries it, not at the next 120 s detail read.
 *
 * Specimen: production 15320207 (CFL Calgary @ Saskatchewan, 2026-10-03). Detail
 * read at 03:54:03Z said 13–20 stamped 03:49:13Z. The page's game-markets read at
 * 03:55:11Z said 13–27 stamped 03:54:22Z. The hero printed 13–20 until the detail
 * read at 03:56:02Z. The values below are the served ones from live's packet
 * (`4571-served-walk/net-001-event.json`, `net-012-event.json`).
 */
import fs from "fs";
import path from "path";
import { newestServedScore } from "@/lib/event/newestServedScore";
import { computeLastChartPoint } from "@/lib/eventKeyStats";
import type { EventHistoryResponse } from "@/lib/types";

const DETAIL = {
  id: 15320207,
  status: "live",
  home_score: 13,
  away_score: 20,
  score_observed_at: "2026-10-03T03:49:13.160004+00:00",
};
const MARKETS = {
  event_id: 15320207,
  status: "live",
  home_score: 13,
  away_score: 27,
  score_observed_at: "2026-10-03T03:54:22.968600+00:00",
};

describe("#10294 newestServedScore", () => {
  test("the specimen: the newer game-markets read supplies the whole pair and its clock", () => {
    expect(newestServedScore(DETAIL, MARKETS)).toEqual({
      home_score: 13,
      away_score: 27,
      score_observed_at: "2026-10-03T03:54:22.968600+00:00",
      from: "game-markets",
    });
  });

  test("a same-score confirmation moves the clock alone (walk 2: 03:59:39Z → 04:05:06Z)", () => {
    const detail = { ...DETAIL, away_score: 27, score_observed_at: "2026-10-03T03:59:39.526845+00:00" };
    const markets = { ...MARKETS, score_observed_at: "2026-10-03T04:05:06.003215+00:00" };
    const got = newestServedScore(detail, markets);
    expect([got.home_score, got.away_score]).toEqual([13, 27]);
    expect(got.score_observed_at).toBe("2026-10-03T04:05:06.003215+00:00");
  });

  test("CONTROL: an older or equal game-markets read keeps detail", () => {
    const older = { ...MARKETS, away_score: 17, score_observed_at: "2026-10-03T03:17:41+00:00" };
    expect(newestServedScore(DETAIL, older)).toMatchObject({ away_score: 20, from: "detail" });
    const equal = { ...MARKETS, score_observed_at: DETAIL.score_observed_at };
    expect(newestServedScore(DETAIL, equal)).toMatchObject({ away_score: 20, from: "detail" });
  });

  test.each([
    ["no game-markets read yet", undefined],
    ["a different event id (detail answered with a canonical row)", { ...MARKETS, event_id: 15320206 }],
    ["game markets already says final", { ...MARKETS, status: "completed" }],
    ["half a pair", { ...MARKETS, home_score: null }],
    ["no stamp on game markets", { ...MARKETS, score_observed_at: null }],
    ["an unparseable stamp", { ...MARKETS, score_observed_at: "soon" }],
  ])("keeps detail: %s", (_why, markets) => {
    expect(newestServedScore(DETAIL, markets)).toEqual({ ...pick(DETAIL), from: "detail" });
  });

  test.each([
    ["detail is not live", { ...DETAIL, status: "completed" }],
    ["detail has no stamp — an unknown age is not upgraded by a guess", { ...DETAIL, score_observed_at: null }],
    ["detail has no id", { ...DETAIL, id: null }],
    ["detail carries a tennis games line only it serves", { ...DETAIL, linescore: { sets: [], observed_at: "2026-10-03T03:49:13+00:00" } }],
  ])("keeps detail: %s", (_why, detail) => {
    expect(newestServedScore(detail, MARKETS)).toEqual({ ...pick(detail), from: "detail" });
  });

  test("no detail read at all renders nothing, whatever game markets says", () => {
    expect(newestServedScore(undefined, MARKETS)).toEqual({
      home_score: null, away_score: null, score_observed_at: null, from: null,
    });
  });

  test("end to end through the chart point: with no ESPN rows the hero prints the newer pair, dated by it", () => {
    // 15320207 carried score_history but no espn_history, so the event-row arm
    // decides the hero (#5521: snapshots never fill in for absent ESPN rows).
    const history = {
      espn_history: [],
      score_history: [{ timestamp: "2026-10-03T03:28:15.275026+00:00", home_score: 13, away_score: 20 }],
      aggregate_line: [{ timestamp: "2026-10-03T03:54:16+00:00", home_probability: 0.07 }],
      completed_at: null,
    } as unknown as EventHistoryResponse;
    const served = newestServedScore(DETAIL, MARKETS);
    const point = computeLastChartPoint(history, served.home_score, served.away_score, served.score_observed_at);
    expect([point?.homeScore, point?.awayScore]).toEqual([13, 27]);
    expect(point?.scoreStamp).toBe("2026-10-03T03:54:22.968600+00:00");
    // CONTROL: the pre-fix inputs print the stale pair.
    const before = computeLastChartPoint(history, DETAIL.home_score, DETAIL.away_score, DETAIL.score_observed_at);
    expect([before?.homeScore, before?.awayScore]).toEqual([13, 20]);
  });
});

describe("#10294 the page's hero reads the newer of its two reads", () => {
  const PAGE = path.resolve(__dirname, "../../app/events/[id]/page.tsx");
  const code = fs
    .readFileSync(PAGE, "utf8")
    .replace(/\/\*[\s\S]*?\*\//g, " ")
    .split("\n")
    .map((line) => line.replace(/(^|\s)\/\/.*$/, "$1"))
    .join("\n");

  test("servedScore is built from the detail read and the game-markets read", () => {
    expect(code).toMatch(/servedScore\s*=\s*useMemo\(\s*\(\)\s*=>\s*newestServedScore\(event,\s*servedGameMarkets\)/);
  });

  test("the hero's fallback pair and its no-history clock read servedScore, not the detail row", () => {
    expect(code).toMatch(/bestHomeScore\s*=\s*lastChartPoint\?\.homeScore\s*\?\?\s*servedScore\.home_score/);
    expect(code).toMatch(/bestAwayScore\s*=\s*lastChartPoint\?\.awayScore\s*\?\?\s*servedScore\.away_score/);
    expect(code).not.toMatch(/bestHomeScore\s*=[^;]*event\?\.home_score/);
    expect(code).not.toMatch(/renderedScoreStamp[\s\S]{0,200}event\?\.score_observed_at/);
  });
});

function pick(d: { home_score?: number | null; away_score?: number | null; score_observed_at?: string | null }) {
  return {
    home_score: d.home_score ?? null,
    away_score: d.away_score ?? null,
    score_observed_at: d.score_observed_at ?? null,
  };
}
