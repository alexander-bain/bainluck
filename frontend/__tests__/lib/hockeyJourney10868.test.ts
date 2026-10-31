/**
 * #10868 — the web hockey journey (route `nhl-journey`) on REAL retained
 * production bodies: the same facts the native adapter suites assert
 * (`ios/.../BainLuckTests/HockeyJourney*Adapter10868Tests.swift`), through the
 * web authorities the page already uses.
 *
 * PREPARED, NOT RUN: written under a quiet-CPU hold (#10090 timing window); the
 * lead runs `npx jest --testPathPatterns=hockeyJourney10868` under a grant.
 *
 * FIXTURE — `hockeyJourney10868.fixtures.json` (sha256 3e576d7d…19c9, re-hashed
 * below), generated and verified by `/tmp/cli-10868-web/make_subsets.py`
 * (`python3 -I make_subsets.py <design-dir> <out.json> <manifest.json>`): every
 * kept top-level member and array element is the source's BYTES in source
 * order; the parsed subset equals the selected source elements key by key.
 * Sources under `artifacts/discovery-containers-release-plan/event-page-design-20261011/`:
 *
 *   finalDetail     atlas-v6/raw/nhl-15169793-detail.json — WHOLE, byte for byte
 *                   (sha256 a11c662df1fd7c94c080cf0c7455c6771da9f8f38de3a44517a0a633f03ea348).
 *                   Minnesota Wild 4–1 Boston Bruins, completed, captured 2026-10-11.
 *   finalHistory    atlas-v6/raw/nhl-15169793-history.json (1,335,078 B, sha256
 *                   cba7c334e453ea653530b0e8c3bde4bb612835019e08ef3dc320e0901a887525),
 *                   the native history fixture's own kept indexes:
 *                     history 313–316, 372–391, 480–493 of 494 · bookmaker_history {}
 *                     espn_history 0, 39, 80, 119, 120 of 121
 *                     win_prob_history polymarket 0, 1530–1532 of 1533; kalshi 0,
 *                       868–870 of 871; stat_model 0, 1, 102–104 of 105
 *                     period_markers 0, 35, 36, 70, 71 of 104
 *                     aggregate_line 1893–1899, 2081–2084, 2355–2385, 2419, 2443–2447,
 *                       2465–2469, 2495–2499, 2526–2534 of 2535
 *   finalMarkets    atlas-v6/raw/nhl-15169793-game-markets.json (147,727 B, sha256
 *                   3abba0f2f3c0a4875a394e3f82d7bf14cea76c2dfd690d6b61490b477a7806dc):
 *                     totals 0 of 9 · player_props 2, 3, 38–42, 47, 48, 59–66 of 83 ·
 *                     team_totals 3 of 10 · spreads 0, 2 of 9 · other 0, 1 of 38 ·
 *                     props_script [], game_question_matrix {}, stream_market_ids [],
 *                     outcome_market_ids {}, outcome_revision_at {}, outcome_observed_at {},
 *                     closed_winner_market_ids [] (emptied; not read by this screen)
 *   pregameDetail   shipping-adoption-20261027/cli-candidate-20261030/retained-payloads/
 *                   nhl-15338496-detail-20261030T201355Z.json — WHOLE, byte for byte
 *                   (sha256 50fbf4678a308e40481340e9b998a2a0870795dd8b04dfdfb05e31caf3dcc1da).
 *                   New Jersey Devils at Vegas Golden Knights, scheduled 22:00Z,
 *                   captured 20:13:55Z.
 *   pregameHistory  …/nhl-15338496-history-20261030T201355Z.json (430,695 B, sha256
 *                   0fe7e8cd334d2b32b5d808bd2dbdec974bef052a53775991b1457bd37fafe812):
 *                     history 5–8, 57–61 of 62 · bookmaker_history {} ·
 *                     win_prob_history polymarket 0, 984 of 985; kalshi 0, 551 of 552 ·
 *                     aggregate_line 54–62, 513–521, 1095–1102 of 1103
 *   pregameMarkets  …/nhl-15338496-game-markets-20261030T201355Z.json (149,674 B, sha256
 *                   8e475781f15a79de89253a56485a4da4a303e2f219d503208267aedd77fecd4a):
 *                     totals 0 · player_props 30, 31, 34, 35, 60–65 of 105 ·
 *                     team_totals 0 · spreads 0, 1 of 16 · other 0–3 of 4 · same emptied keys
 *
 * WHAT A SUBSET CHANGES: rows left out are absent, so an in-game interval
 * across them is wider than served and the chart's own rule breaks there — the
 * in-game runs below are runs OF THE SUBSET. Pre-match intervals are never
 * judged, so the before frame is one run.
 *
 * CONSTRUCTED here, and named where used: `now`; the hero pair, taken from the
 * page's own `resolveProbability` exactly as page.tsx calls it; a live replay of
 * the final body (status, scores, score clock and ESPN period/clock edited); a
 * live replay of the pregame body (status only); one-key start variants
 * (`start_is_tbd: true` on the pregame event, `commence_time_is_kickoff: false`
 * on the pregame and final bodies); a missing history response (null /
 * undefined); and, for All props during play, ONE row's fields (Jack Eichel 1+
 * points, Kalshi: its `observed_at`, or its settlement) with every other row
 * verbatim. The variants mirror native's (`HockeyJourneyHistoryAdapter10868Tests`,
 * `HockeyJourneyOriginalsAdapter10868Tests`, `HockeyJourneyEventPageHost10868Tests`,
 * slice01 c2768ea8). Jest runs in UTC
 * (`jest.config.js`); clock words are compared through the same formatter the
 * screen uses, never a hard-coded spelling, because ICU may print a narrow
 * no-break space before AM/PM.
 */

import { existsSync, readFileSync } from "fs";
import { join } from "path";
import { createHash } from "crypto";
import fixtures from "./hockeyJourney10868.fixtures.json";
import type { EventDetailResponse, EventHistoryResponse } from "@/lib/types";
import type { GameMarketsResponse } from "@/lib/api";
import { resolveProbability } from "@/lib/eventKeyStats";
import { formatSourceStamp } from "@/lib/sourceAge";
import { isRecentQuote } from "@/lib/nflEventCardDeck";
import { PROP_HIT_LABEL, PROP_MISS_LABEL } from "@/lib/propGrade";
import { formatLiveClockLabel } from "@/lib/gameTimeLabel";
import { eventPageProjectedPair, projectedFinalFormat } from "@/lib/projectedFinalPair";
import { finalForecastComparison, finalScorePeriod } from "@/lib/finalForecastComparison";
import { sportPricesADraw } from "@/lib/drawPricedWinner";
import { teamShortNames } from "@/lib/teamShortName";
import {
  beforeForecast,
  buildHockeyJourney,
  dayWords,
  forecastSlot,
  historyGameEnd,
  hockeyJourneyContribution,
  hockeyJourneyHeadline,
  hockeyJourneyHeader,
  hockeyJourneyHistory,
  hockeyJourneyOriginals,
  hockeyJourneyPhase,
  matrixProvenanceLine,
  NO_HELD_CHOICE,
  ownHockeyHistory,
  resolveContributionChoice,
  timeWords,
  unavailableHistory,
  type HockeyJourneyHost,
  type HockeyJourneySlot,
  MATRIX_WORDS,
} from "@/lib/eventPage10868/hockeyJourney";
import { CONTRIBUTION_WORDS, ORIGINALS_WORDS } from "@/lib/eventPage10868/hockeyJourneyProps";
import { BEFORE_WINDOW_MS } from "@/lib/eventPage10868/hockeyJourneyHistory";

const finalDetail = fixtures.finalDetail as unknown as EventDetailResponse;
const finalHistory = fixtures.finalHistory as unknown as EventHistoryResponse;
const finalMarkets = fixtures.finalMarkets as unknown as GameMarketsResponse;
const pregameDetail = fixtures.pregameDetail as unknown as EventDetailResponse;
const pregameHistory = fixtures.pregameHistory as unknown as EventHistoryResponse;
const pregameMarkets = fixtures.pregameMarkets as unknown as GameMarketsResponse;

const FINAL_NOW = Date.parse("2026-10-11T04:56:41Z");
const PREGAME_NOW = Date.parse("2026-10-30T20:13:55Z");

const ms = (iso: string) => Date.parse(iso);
const stamp = (iso: string) => formatSourceStamp(new Date(Date.parse(iso)).toISOString());
const text = (slot: HockeyJourneySlot) => slot.text;

/** The page's own hero pair for a body, as page.tsx resolves it (no chart point, no preview). */
function pageHero(event: EventDetailResponse, history: EventHistoryResponse, isLive: boolean) {
  const resolved = resolveProbability(event, history, null, isLive, false, false, false, true);
  return {
    homeProb: resolved.homeProb,
    awayProb: resolved.awayProb,
    homePct: resolved.homePct,
    awayPct: resolved.awayPct,
    probSourceLabel: resolved.probSourceLabel,
  };
}

function host(nowMs: number, extra: Partial<HockeyJourneyHost> = {}): HockeyJourneyHost {
  return { nowMs, hero: null, probabilityObservedAt: null, ...extra };
}

describe("#10868 fixture integrity", () => {
  it("is the generated, verified subset file", () => {
    const raw = readFileSync(join(__dirname, "hockeyJourney10868.fixtures.json"));
    expect(createHash("sha256").update(raw).digest("hex")).toBe(
      "3e576d7de23d1131fea56c3961f8f6cc047f7cfe682d50510fe6620b217e19c9",
    );
    expect(finalDetail.id).toBe(15169793);
    expect(finalHistory.aggregate_line).toHaveLength(67);
    expect(finalHistory.history).toHaveLength(38);
    expect(pregameDetail.id).toBe(15338496);
    expect(pregameHistory.aggregate_line).toHaveLength(26);
    expect(pregameHistory.blend_edge_pinned).toBe(true);
  });
});

describe("#10868 matrix — a finished game (15169793, Wild 4–1 Bruins)", () => {
  const journey = buildHockeyJourney({
    event: finalDetail,
    history: finalHistory,
    gameMarkets: finalMarkets,
    host: host(FINAL_NOW),
  });
  const { matrix } = journey.headline;
  const [home, away] = matrix.rows;

  it("reads the phase from the status and titles the final", () => {
    expect(hockeyJourneyPhase(finalDetail, FINAL_NOW)).toBe("final");
    expect(journey.header.title).toBe("Final: Minnesota Wild 4–1 Boston Bruins");
    expect(journey.headline.state).toBe("Final");
    expect(journey.headline.stateContext).toBe(dayWords(ms(finalDetail.commence_time)));
    expect(matrix.columns.map((c) => c.title)).toEqual(["Pregame chance", "Final goals", "Pregame forecast"]);
  });

  it("remembers the served pre-match 66% / 34% beside the final 4–1 and the served verdict", () => {
    expect(home.values[0]).toEqual({ kind: "value", text: "66%", spoken: "66 percent" });
    expect(away.values[0]).toEqual({ kind: "value", text: "34%", spoken: "34 percent" });
    // `kalshi` is not among this body's served source names, so it stays unnamed.
    expect(matrix.columns[0].provenance).toBe("Pre-match");
    expect(home.values[1]).toEqual({ kind: "value", text: "4", spoken: "4 goals" });
    expect(away.values[1]).toEqual({ kind: "value", text: "1", spoken: "1 goal" });
    expect(matrix.columns[1].provenance).toBe(`ESPN · score observed ${stamp("2026-10-04T05:59:38.451734+00:00")}`);
    expect(finalDetail.hero_settled_result).toBe("home");
    expect(home.result).toBe("Won");
    expect(away.result).toBe("Lost");
  });

  it("never prints the settled hero as a chance", () => {
    expect(finalDetail.hero_probability).toBe(1);
    for (const row of matrix.rows) {
      for (const slot of row.values) expect([">99%", "<1%", "100%", "0%"]).not.toContain(slot.text);
    }
  });

  it("says hockey has no admitted pregame forecast instead of printing a reference value", () => {
    expect(projectedFinalFormat(finalDetail.sport)).toBeNull();
    expect(finalDetail.pregame_projection).toBeUndefined();
    expect(
      finalForecastComparison({
        sportKey: finalDetail.sport,
        status: finalDetail.status,
        homeScore: 4,
        awayScore: 1,
        actualPeriod: finalScorePeriod(finalDetail.sport, finalDetail.final_score_period),
        projection: finalDetail.pregame_projection,
      }),
    ).toBeNull();
    expect(home.values[2]).toEqual({ kind: "absent", text: "No pregame forecast" });
    expect(away.values[2]).toEqual({ kind: "absent", text: "No pregame forecast" });
    expect(matrix.columns[2].provenance).toBeNull();
  });

  it("keeps an admitted forecast's half goal at its own precision", () => {
    // Row 376 of the full history (in this subset): the approved reference's 4.0 / 2.5.
    const row = finalHistory.history.find((r) => r.timestamp === "2026-10-03T23:46:00+00:00");
    expect(row?.bookmaker_count).toBe(1);
    expect(forecastSlot(row!.projected_home_score!)).toEqual({ kind: "value", text: "4", spoken: "4 goals" });
    expect(forecastSlot(row!.projected_away_score!)).toEqual({ kind: "value", text: "2.5", spoken: "2.5 goals" });
    expect(forecastSlot(1)).toEqual({ kind: "value", text: "1", spoken: "1 goal" });
  });
});

describe("#10868 matrix — before the start (15338496, Devils at Golden Knights)", () => {
  const observedAt = pregameDetail.hero_probability_observed_at ?? null;
  const hero = pageHero(pregameDetail, pregameHistory, false);
  const fresh = host(PREGAME_NOW, { hero, probabilityObservedAt: observedAt });

  it("prints the hero's own 51% / 49% as the current chance on the quote's own clock", () => {
    expect(hero.homePct).toBe(51);
    expect(hero.awayPct).toBe(49);
    const headline = hockeyJourneyHeadline(pregameDetail, pregameHistory, fresh);
    const start = ms(pregameDetail.commence_time);
    expect(hockeyJourneyPhase(pregameDetail, PREGAME_NOW)).toBe("before");
    expect(hockeyJourneyHeader(pregameDetail, "before").title).toBe("Vegas Golden Knights vs New Jersey Devils");
    expect(headline.state).toBe(`Before game · ${timeWords(start)} start`);
    expect(headline.state).toMatch(/^Before game · 10:00\sPM start$/u);
    expect(headline.stateContext).toBe(dayWords(start));
    const { matrix } = headline;
    expect(matrix.columns[0].title).toBe("Current chance");
    expect(matrix.rows[0].values[0]).toEqual({ kind: "value", text: "51%", spoken: "51 percent" });
    expect(matrix.rows[1].values[0]).toEqual({ kind: "value", text: "49%", spoken: "49 percent" });
    // The hero's `blend` source has no served display name here, so it is not named.
    expect(matrix.columns[0].provenance).toBe(`Recorded ${stamp(observedAt!)}`);
  });

  it("withholds the forecast production refuses for hockey (served 3.5 / 2.5 from 19 sportsbooks)", () => {
    expect(pregameDetail.current_odds?.projected_home_score).toBe(3.5);
    expect(pregameDetail.current_odds?.projected_away_score).toBe(2.5);
    expect(
      eventPageProjectedPair({
        odds: pregameDetail.current_odds,
        sportKey: pregameDetail.sport,
        commenceTime: pregameDetail.commence_time,
        isLive: false,
        ladderPair: pregameHistory.pm_spread_data?.projected_final,
      }),
    ).toBeNull();
    const { matrix } = hockeyJourneyHeadline(pregameDetail, pregameHistory, fresh);
    expect(matrix.rows.map((r) => r.values[1])).toEqual([
      { kind: "absent", text: "No pregame forecast" },
      { kind: "absent", text: "No pregame forecast" },
    ]);
    expect(matrix.columns[1].provenance).toBeNull();
  });

  it("calls a stale, undated or interrupted quote the last recorded chance, never current", () => {
    const stale = host(ms(observedAt!) + 31 * 60 * 1000, { hero, probabilityObservedAt: observedAt });
    const undated = host(PREGAME_NOW, { hero, probabilityObservedAt: null });
    const interrupted = host(PREGAME_NOW, { hero, probabilityObservedAt: observedAt, deliveryInterrupted: true });
    for (const h of [stale, undated, interrupted]) {
      const { matrix } = hockeyJourneyHeadline(pregameDetail, pregameHistory, h);
      expect(matrix.columns[0].title).toBe("Last recorded chance");
      expect(text(matrix.rows[0].values[0])).toBe("51%");
    }
  });

  it("reads the phase from the status alone and gives a missing score its own words", () => {
    expect(hockeyJourneyPhase(pregameDetail, ms("2026-10-30T23:30:00Z"))).toBe("before");
    const live = { ...pregameDetail, status: "live" } as EventDetailResponse; // CONSTRUCTED: status only
    const { matrix } = hockeyJourneyHeadline(live, pregameHistory, host(ms("2026-10-30T22:30:00Z")));
    expect(matrix.phase).toBe("live");
    expect(matrix.rows[0].values[2]).toEqual({ kind: "absent", text: "Score unavailable" });
    expect(matrix.columns[2].provenance).toBeNull();
    expect(matrix.rows[0].values[3]).toEqual({ kind: "absent", text: "No in-game forecast" });
  });
});

describe("#10868 matrix — during play (CONSTRUCTED live replay of 15169793)", () => {
  // Only status, scores, the score's clock and ESPN's period/clock are edited.
  const live = {
    ...finalDetail,
    status: "live",
    home_score: 2,
    away_score: 1,
    score_observed_at: "2026-10-04T01:45:25Z",
    espn: { ...finalDetail.espn, period: "2nd Period", game_clock: "4:09" },
  } as EventDetailResponse;
  const now = ms("2026-10-04T01:46:00Z");
  const headline = hockeyJourneyHeadline(live, finalHistory, host(now));

  it("keeps the score on its own clock and never dates ESPN's period by it", () => {
    expect(headline.state).toBe(formatLiveClockLabel("2nd Period", "4:09", " · "));
    expect(headline.stateContext).toBe("Game state from ESPN");
    const scoreClock = stamp("2026-10-04T01:45:25Z")!;
    expect(headline.stateContext ?? "").not.toContain(scoreClock);
    const { matrix } = headline;
    expect(matrix.columns.map((c) => c.title)).toEqual(["Pregame chance", "Last recorded chance", "Goals", "Projected final"]);
    expect(matrix.rows[0].values[2]).toEqual({ kind: "value", text: "2", spoken: "2 goals" });
    expect(matrix.columns[2].provenance).toBe(`ESPN · score observed ${scoreClock}`);
    expect(text(matrix.rows[0].values[0])).toBe("66%");
  });

  it("prints no in-game forecast where none is admitted, and no retained one beneath it", () => {
    expect(headline.matrix.rows.map((r) => r.values[3])).toEqual([
      { kind: "absent", text: "No in-game forecast" },
      { kind: "absent", text: "No in-game forecast" },
    ]);
    expect(headline.historicalForecast).toBeNull();
    // No hero pair handed in: the slot says so rather than borrowing a number.
    expect(headline.matrix.rows[0].values[1]).toEqual({ kind: "absent", text: "No recorded chance" });
  });
});

describe("#10868 history — the finished game", () => {
  const history = hockeyJourneyHistory(finalHistory, finalDetail, "final", FINAL_NOW);
  const [home, away] = history.series;
  const homePoints = home.runs.flat();
  const awayPoints = away.runs.flat();

  it("draws the blend from the last pregame row to the web chart's own game end, never the settlement", () => {
    expect(history.line).toBe("blend");
    expect(home.id).toBe("blend:15169793:home");
    expect(home.name).toBe("Minnesota Wild");
    const settlement = finalHistory.aggregate_line![finalHistory.aggregate_line!.length - 1];
    expect(settlement).toEqual({ timestamp: "2026-10-04T02:48:00+00:00", home_probability: 1.0 });
    expect(homePoints.some((p) => p.p === 1)).toBe(false);
    expect(historyGameEnd(finalHistory, finalDetail)).toBe(ms("2026-10-04T02:48:00Z"));
    expect(homePoints.every((p) => p.t <= ms("2026-10-04T02:48:00Z"))).toBe(true);
    expect(homePoints.some((p) => p.t === ms("2026-10-04T03:14:00+00:00"))).toBe(false);
    expect(homePoints[0]).toMatchObject({ t: ms("2026-10-03T23:59:00+00:00"), p: 0.66, hollow: true });
    expect(homePoints.filter((p) => p.hollow)).toHaveLength(1);
    expect(homePoints[homePoints.length - 1]).toMatchObject({ t: ms("2026-10-04T02:48:00+00:00"), p: 0.98847 });
    expect(history.domain).toEqual({ lower: ms("2026-10-03T23:59:00+00:00"), upper: ms("2026-10-04T02:48:00+00:00") });
    expect(history.caption).toBe("Game history");
    expect(history.readout).toBe("single");
    expect(history.absence).toBeNull();
  });

  it("starts a new run across each in-game hole the chart's own rule refuses to cross", () => {
    const bounds = home.runs.map((run) => [run[0].t, run[run.length - 1].t]);
    expect(bounds).toEqual(
      [
        ["2026-10-03T23:59:00+00:00", "2026-10-04T00:19:00+00:00"],
        ["2026-10-04T00:53:00+00:00", "2026-10-04T00:53:00+00:00"],
        ["2026-10-04T01:20:00+00:00", "2026-10-04T01:24:00+00:00"],
        ["2026-10-04T01:42:00+00:00", "2026-10-04T01:46:00+00:00"],
        ["2026-10-04T02:12:00+00:00", "2026-10-04T02:16:00+00:00"],
        ["2026-10-04T02:43:00+00:00", "2026-10-04T02:48:00+00:00"],
      ].map((pair) => pair.map(ms)),
    );
    expect(home.runs.map((run) => run.length)).toEqual([19, 1, 5, 5, 5, 6]);
  });

  it("draws the away side as the other side of the same blend, row for row", () => {
    expect(sportPricesADraw(finalDetail.sport)).toBe(false);
    expect(away.id).toBe("blend:15169793:away");
    expect(away.runs.map((run) => run.length)).toEqual(home.runs.map((run) => run.length));
    expect(awayPoints).toHaveLength(homePoints.length);
    awayPoints.forEach((a, i) => {
      const h = homePoints[i];
      expect(a.t).toBe(h.t);
      expect(a.row).toBe(h.row);
      expect(a.hollow).toBe(h.hollow);
      expect(a.p).toBe(1 - h.p);
    });
    expect(awayPoints.some((p) => p.p === 0)).toBe(false);
    expect(history.notes).toEqual([
      "Source: Bain Luck",
      "Boston Bruins is the other side of the same line: 100% − Minnesota Wild.",
      "Gaps remain blank.",
    ]);
    expect(history.summary).toBe(
      "Minnesota Wild and Boston Bruins win probability, recorded observations only. " +
        "Boston Bruins is the other side of the same line: 100% − Minnesota Wild.",
    );
    const pregame = "2026-10-03T23:59:00+00:00";
    expect(home.before).toEqual({
      kind: "reading",
      figure: "66%",
      provenance: `Last pregame · ${stamp(pregame)}`,
      pointId: `blend:15169793:home#${pregame}`,
    });
    expect(away.before).toMatchObject({ kind: "reading", figure: "34%" });
    expect(home.recorded).toEqual({ kind: "absent", words: "Not recorded" });
  });

  it("guides the period starts only — no result, no end of period", () => {
    expect(history.guides.map((g) => g.label)).toEqual(["P1", "P2", "P3"]);
    expect(history.guides[2].t).toBe(ms("2026-10-04T02:08:56.957013+00:00"));
    expect(history.guides.every((g) => g.t >= history.domain!.lower && g.t <= history.domain!.upper)).toBe(true);
    expect(finalHistory.scoring_plays).toEqual([]);
  });
});

describe("#10868 history — before the start", () => {
  const history = hockeyJourneyHistory(pregameHistory, pregameDetail, "before", PREGAME_NOW);
  const [home, away] = history.series;
  const points = home.runs.flat();

  it("draws the recorded day ending at the last pregame reading, never the pinned edge", () => {
    // The day is measured back from the last pregame reading (20:11), not from the listed start
    // (22:00): the subset's 21:58 and 21:59 the day before are recorded readings inside it.
    const lastPregame = ms("2026-10-30T20:11:00+00:00");
    expect(points[0].t).toBe(ms("2026-10-29T21:58:00+00:00"));
    expect(points.some((p) => p.t < lastPregame - BEFORE_WINDOW_MS)).toBe(false);
    const pin = pregameHistory.aggregate_line![pregameHistory.aggregate_line!.length - 1];
    expect(pin.timestamp).toBe("2026-10-30T20:12:00+00:00");
    expect(points.some((p) => p.t === ms(pin.timestamp))).toBe(false);
    expect(points[points.length - 1]).toMatchObject({ t: lastPregame, hollow: true });
    expect(points).toHaveLength(25);
    expect(home.runs).toHaveLength(1);
  });

  it("says 0.505 against its complement once, as 51% / 49%, and names the other side", () => {
    const lastPregame = "2026-10-30T20:11:00+00:00";
    expect(home.before).toEqual({
      kind: "reading",
      figure: "51%",
      provenance: `Last pregame · ${stamp(lastPregame)}`,
      pointId: `blend:15338496:home#${lastPregame}`,
    });
    expect(away.before).toMatchObject({ kind: "reading", figure: "49%" });
    expect(away.runs.flat().map((p) => p.t)).toEqual(points.map((p) => p.t));
    expect(away.runs.flat().map((p) => p.p)).toEqual(points.map((p) => 1 - p.p));
    expect(history.notes).toContain("New Jersey Devils is the other side of the same line: 100% − Vegas Golden Knights.");
    expect(history.guides).toEqual([]);
    expect(history.caption).toBe("Before game");
    expect(history.xTicks.length).toBeGreaterThan(0);
    for (const tick of history.xTicks) {
      expect(tick.t).toBeGreaterThanOrEqual(history.domain!.lower);
      expect(tick.t).toBeLessThanOrEqual(history.domain!.upper);
    }
  });

});

describe("#10868 history — before the start, each side's own recorded day (CONSTRUCTED consensus bodies)", () => {
  // CONSTRUCTED: the pregame body with only its consensus `history` replaced (no venue series, no
  // blend, nothing pinned), so each team reads its OWN served value and the two can stop apart.
  // Kick-off 22:00Z (confirmed); read at 20:13:55Z.
  const consensusBody = (rows: Array<[string, number | null, number | null]>) =>
    ({
      ...pregameHistory,
      history: rows.map(([timestamp, home, away]) => ({
        timestamp,
        home_probability: home,
        away_probability: away,
        bookmaker_count: 5,
      })),
      aggregate_line: [],
      win_prob_history: {},
      bookmaker_history: {},
      blend_edge_pinned: false,
    }) as unknown as EventHistoryResponse;
  const times = (series: { runs: Array<Array<{ t: number }>> }) => series.runs.flat().map((p) => p.t);

  it("anchors each team to its own last pregame reading; the shared frame may span more than a day", () => {
    const body = consensusBody([
      ["2026-10-29T10:00:00Z", 0.6, 0.4],
      ["2026-10-29T12:00:00Z", 0.61, 0.39],
      ["2026-10-30T10:00:00Z", 0.62, 0.38], // the away side's last reading
      ["2026-10-30T11:30:00Z", 0.63, null], // the home side's last reading; no away value
      ["2026-10-30T21:00:00Z", 0.64, 0.36], // after now: not a reading yet
    ]);
    const h = hockeyJourneyHistory(body, pregameDetail, "before", PREGAME_NOW);
    expect(h.line).toBe("consensus");
    const [home, away] = h.series;
    expect(times(home)).toEqual(["2026-10-29T12:00:00Z", "2026-10-30T10:00:00Z", "2026-10-30T11:30:00Z"].map(ms));
    expect(times(away)).toEqual(["2026-10-29T10:00:00Z", "2026-10-29T12:00:00Z", "2026-10-30T10:00:00Z"].map(ms));
    // Each side ends at its own reading, hollow; neither borrows the other's clock.
    expect(home.runs.flat().filter((p) => p.hollow).map((p) => p.t)).toEqual([ms("2026-10-30T11:30:00Z")]);
    expect(away.runs.flat().filter((p) => p.hollow).map((p) => p.t)).toEqual([ms("2026-10-30T10:00:00Z")]);
    expect(times(away)).not.toContain(ms("2026-10-30T11:30:00Z"));
    expect(times(home)).not.toContain(ms("2026-10-29T10:00:00Z"));
    expect(home.before).toMatchObject({ kind: "reading", provenance: `Last pregame · ${stamp("2026-10-30T11:30:00Z")}` });
    expect(away.before).toMatchObject({ kind: "reading", provenance: `Last pregame · ${stamp("2026-10-30T10:00:00Z")}` });
    // Each side's own window is at most a day; the shared frame is NOT promised to be.
    for (const series of [home, away]) {
      const t = times(series);
      expect(t[t.length - 1] - t[0]).toBeLessThanOrEqual(BEFORE_WINDOW_MS);
    }
    expect(h.domain).toEqual({ lower: ms("2026-10-29T10:00:00Z"), upper: ms("2026-10-30T11:30:00Z") });
    expect(h.domain!.upper - h.domain!.lower).toBeGreaterThan(BEFORE_WINDOW_MS);
    expect([...times(home), ...times(away)].every((t) => t <= PREGAME_NOW)).toBe(true);
  });

  it("opens exactly one day before the last pregame reading, inclusive, whatever the listed start", () => {
    const body = consensusBody([
      ["2026-10-29T14:00:00Z", 0.55, 0.45], // 30 h before the last reading: outside
      ["2026-10-29T19:59:00Z", 0.56, 0.44], // one day and one minute before: outside
      ["2026-10-29T20:00:00Z", 0.57, 0.43], // exactly one day before: inside
      ["2026-10-30T08:00:00Z", 0.58, 0.42],
      ["2026-10-30T20:00:00Z", 0.59, 0.41], // the last pregame reading
    ]);
    const h = hockeyJourneyHistory(body, pregameDetail, "before", PREGAME_NOW);
    const expected = ["2026-10-29T20:00:00Z", "2026-10-30T08:00:00Z", "2026-10-30T20:00:00Z"].map(ms);
    expect(times(h.series[0])).toEqual(expected);
    expect(times(h.series[1])).toEqual(expected);
    // Older than the listed start less one day, and still drawn: the start is still in the future.
    expect(expected[0]).toBeLessThan(ms(pregameDetail.commence_time) - BEFORE_WINDOW_MS);
    expect(h.series[0].runs).toHaveLength(1);
  });

  it("a side with no pregame reading draws nothing, and the other side keeps its own day", () => {
    const body = consensusBody([
      ["2026-10-29T12:00:00Z", 0.61, null],
      ["2026-10-30T10:00:00Z", 0.62, null],
    ]);
    const h = hockeyJourneyHistory(body, pregameDetail, "before", PREGAME_NOW);
    const [home, away] = h.series;
    expect(times(home)).toEqual(["2026-10-29T12:00:00Z", "2026-10-30T10:00:00Z"].map(ms));
    expect(away.runs).toEqual([]);
    expect(away.before).toEqual({ kind: "absent", words: "Not recorded" });
    expect(h.summary).toBe(
      "Vegas Golden Knights win probability, recorded observations only. No recorded history for New Jersey Devils.",
    );
  });

  it("with no pregame reading on either side it is still \"No recorded history\"", () => {
    const body = consensusBody([
      ["2026-10-30T21:00:00Z", 0.64, 0.36], // after now
      ["2026-10-30T22:30:00Z", 0.66, 0.34], // after the start
    ]);
    const h = hockeyJourneyHistory(body, pregameDetail, "before", PREGAME_NOW);
    expect(h.series.map((s) => s.runs)).toEqual([[], []]);
    expect(h.absence).toEqual({ title: "No recorded history", words: null });
    expect(h.domain).toBeNull();
  });
});

describe("#10868 history — the pregame window never reaches the live, final or unconfirmed frames", () => {
  // CONSTRUCTED: the line's rows older than `t` made unreadable — the same rows, indexes and clocks,
  // with no value. Live and final open AT the last pregame reading, so nothing older can move them.
  const blankLineBefore = (body: EventHistoryResponse, t: number) =>
    ({
      ...body,
      aggregate_line: (body.aggregate_line ?? []).map((p) =>
        Date.parse(p.timestamp) < t ? { ...p, home_probability: null } : p,
      ),
    }) as unknown as EventHistoryResponse;
  const hollowOf = (h: ReturnType<typeof hockeyJourneyHistory>) => {
    const hollow = h.series[0].runs.flat().find((p) => p.hollow);
    expect(hollow).toBeDefined();
    return hollow!.t;
  };

  it("the final frame is identical with or without every row older than its last pregame reading", () => {
    const full = hockeyJourneyHistory(finalHistory, finalDetail, "final", FINAL_NOW);
    const t = hollowOf(full);
    expect(t).toBe(ms("2026-10-03T23:59:00+00:00"));
    expect(hockeyJourneyHistory(blankLineBefore(finalHistory, t), finalDetail, "final", FINAL_NOW)).toEqual(full);
  });

  it("the live frame (CONSTRUCTED status-only replay) is identical too", () => {
    const live = { ...finalDetail, status: "live" } as EventDetailResponse;
    const now = ms("2026-10-04T01:46:00Z");
    const full = hockeyJourneyHistory(finalHistory, live, "live", now);
    const t = hollowOf(full);
    expect(hockeyJourneyHistory(blankLineBefore(finalHistory, t), live, "live", now)).toEqual(full);
  });

  it("an unconfirmed start keeps every recorded row, older than any day, as before", () => {
    const unconfirmed = { ...pregameHistory, commence_time_is_kickoff: false } as EventHistoryResponse;
    const h = hockeyJourneyHistory(unconfirmed, pregameDetail, "before", PREGAME_NOW);
    expect(h.series[0].runs.flat()).toHaveLength(25);
    expect(h.markKey).toBeNull();
  });

  it("positive control: the same blanking DOES change the before frame, which reads the older rows", () => {
    const full = hockeyJourneyHistory(pregameHistory, pregameDetail, "before", PREGAME_NOW);
    const t = hollowOf(full);
    const blanked = hockeyJourneyHistory(blankLineBefore(pregameHistory, t), pregameDetail, "before", PREGAME_NOW);
    expect(blanked).not.toEqual(full);
    expect(blanked.series[0].runs.flat().map((p) => p.t)).toEqual([t]);
  });
});

describe("#10868 history — a future start never shortens the recorded day (Rams 14780558, retained subset)", () => {
  // Retained `probability-movement-v89/raw/nfl-pregame-detail.json` (sha256 1f81fa52…0eb9) and
  // `nfl-pregame-history.json` (sha256 c32ce440…8332), Rams vs Bills, kick-off 2026-10-13T00:15Z
  // (confirmed), read 2026-10-12T05:45:12Z — about 18.5 h early. SUBSET, every kept value verbatim:
  // the detail keys this helper reads; history aggregate_line rows 0, 831, 832, 1141, 1142 of 1143
  // (1142 is the pinned edge), consensus rows 0 and 74 of 75, the first kalshi and polymarket points,
  // and the served flags. bookmaker_history is EMPTIED here (21 books served; none is read for the
  // window). The full bodies are read below where present.
  const ramsDetail = {
    "id": 14780558,
    "sport": "americanfootball_nfl",
    "home_team": "Los Angeles Rams",
    "away_team": "Buffalo Bills",
    "commence_time": "2026-10-13T00:15:00+00:00",
    "start_is_tbd": false,
    "completed_at": null,
    "status": "scheduled",
    "home_score": null,
    "away_score": null
  } as unknown as EventDetailResponse;
  const ramsHistory = {
    "event_id": 14780558,
    "commence_time": "2026-10-13T00:15:00+00:00",
    "completed_at": null,
    "status": "scheduled",
    "commence_time_is_kickoff": true,
    "blend_edge_pinned": true,
    "blend_edge_observed_at": "2026-10-12T05:45:00.084170+00:00",
    "evidence_contract": {
      "v": "7878.v1",
      "resolution_s": 300
    },
    "history": [
      {
        "timestamp": "2026-10-11T05:45:00+00:00",
        "home_probability": 0.6098,
        "away_probability": 0.3902,
        "over_under": 54.6,
        "projected_home_score": 29.0,
        "projected_away_score": 25.6,
        "bookmaker_count": 21,
        "probability_range": {
          "min": 0.5951,
          "max": 0.6211
        }
      },
      {
        "timestamp": "2026-10-12T04:37:00+00:00",
        "home_probability": 0.6092,
        "away_probability": 0.3908,
        "over_under": null,
        "projected_home_score": null,
        "projected_away_score": null,
        "bookmaker_count": 2,
        "probability_range": {
          "min": 0.6092,
          "max": 0.6092
        }
      }
    ],
    "bookmaker_history": {},
    "espn_history": [],
    "score_history": [],
    "scoring_plays": [],
    "period_markers": [],
    "win_prob_history": {
      "kalshi": [
        {
          "timestamp": "2026-10-11T05:45:42.061922+00:00",
          "home_probability": 0.615,
          "away_probability": 0.385,
          "draw_probability": null,
          "game_state": null
        }
      ],
      "polymarket": [
        {
          "timestamp": "2026-10-11T05:45:15.598351+00:00",
          "home_probability": 0.615,
          "away_probability": 0.385,
          "draw_probability": null,
          "game_state": null
        }
      ]
    },
    "aggregate_line": [
      {
        "timestamp": "2026-10-11T05:45:00+00:00",
        "home_probability": 0.615
      },
      {
        "timestamp": "2026-10-12T00:14:00+00:00",
        "home_probability": 0.6145
      },
      {
        "timestamp": "2026-10-12T00:15:00+00:00",
        "home_probability": 0.6145
      },
      {
        "timestamp": "2026-10-12T05:44:00+00:00",
        "home_probability": 0.615
      },
      {
        "timestamp": "2026-10-12T05:45:00+00:00",
        "home_probability": 0.615
      }
    ]
  } as unknown as EventHistoryResponse;
  const RAMS_NOW = ms("2026-10-12T05:45:12.645Z");
  const h = hockeyJourneyHistory(ramsHistory, ramsDetail, "before", RAMS_NOW);
  const [home, away] = h.series;
  const points = home.runs.flat();
  const kickoff = ms(ramsDetail.commence_time);

  it("draws the readings older than the start less one day, up to the last real reading", () => {
    expect(h.line).toBe("blend");
    expect(h.caption).toBe("Before game");
    expect(points.map((p) => p.t)).toEqual(
      ["2026-10-11T05:45:00+00:00", "2026-10-12T00:14:00+00:00", "2026-10-12T00:15:00+00:00", "2026-10-12T05:44:00+00:00"].map(ms),
    );
    // Two of them sit before the start less one day: the window a future start used to cut off.
    expect(points.filter((p) => p.t < kickoff - BEFORE_WINDOW_MS)).toHaveLength(2);
    // The pinned 05:45 edge is the hero's, never a reading; the last real reading is hollow.
    expect(points.some((p) => p.t === ms("2026-10-12T05:45:00+00:00"))).toBe(false);
    expect(points.filter((p) => p.hollow).map((p) => p.t)).toEqual([ms("2026-10-12T05:44:00+00:00")]);
    expect(home.runs).toHaveLength(1);
    expect(h.domain).toEqual({ lower: ms("2026-10-11T05:45:00+00:00"), upper: ms("2026-10-12T05:44:00+00:00") });
    expect(h.guides).toEqual([]);
    expect(h.xTicks.length).toBeGreaterThan(0);
    expect(h.xTicks.length).toBeLessThanOrEqual(4);
    for (const tick of h.xTicks) {
      expect(tick.t).toBeGreaterThanOrEqual(h.domain!.lower);
      expect(tick.t).toBeLessThanOrEqual(h.domain!.upper);
    }
  });

  it("keeps the away side the other side of the same rows, at the same clocks", () => {
    expect(sportPricesADraw(ramsDetail.sport)).toBe(false);
    const awayPoints = away.runs.flat();
    expect(awayPoints.map((p) => p.t)).toEqual(points.map((p) => p.t));
    expect(awayPoints.map((p) => p.p)).toEqual(points.map((p) => 1 - p.p));
    expect(h.notes[0]).toBe("Source: Bain Luck");
  });

  // #10868 hockey F1, W3. TEST CONTROL, NOT HOCKEY FORECAST EVIDENCE: the projected-final format
  // authority refuses every hockey pregame pair, so a history-derived ladder can only be reached
  // through this NFL event. The relabelled ids below are test controls.
  describe("W3: a before-the-start forecast reads only this game's own body (NFL-keyed test control)", () => {
    // The real 15338496 body (Devils at Golden Knights): `projected_final` 3.7 / 2.4, verbatim.
    const foreign = pregameHistory;
    // Retained `nfl-pregame-history.json` (sha256 c32ce440…8332) `pm_spread_data.projected_final`, verbatim.
    const ownLadder = {
      ...ramsHistory,
      pm_spread_data: { projected_final: { home_score: 28.8, away_score: 25.5, spread_source: "kalshi", total_source: "kalshi" } },
    } as unknown as EventHistoryResponse;
    // Retained `nfl-pregame-detail.json` (sha256 1f81fa52…0eb9) `current_odds`, verbatim.
    const ramsWithBooks = {
      ...ramsDetail,
      current_odds: {
        captured_at: "2026-10-12T04:37:03.501709+00:00",
        home_probability: 0.615,
        away_probability: 0.385,
        away_rendered_percent: 38,
        home_rendered_percent: 62,
        spread: -3.5,
        over_under: 54.4,
        projected_home_score: 29.0,
        projected_away_score: 25.4,
        bookmaker_count: 22,
      },
    } as unknown as EventDetailResponse;
    const pair = (home: number, away: number, provenance: string) => ({
      title: MATRIX_WORDS.projectedGoals,
      home: forecastSlot(home),
      away: forecastSlot(away),
      provenance,
    });
    const LADDER = "Prediction-market lines before the start";
    const relabelled = { ...foreign, event_id: ramsDetail.id } as EventHistoryResponse; // TEST CONTROL

    it("is NFL-keyed because hockey's format authority refuses the pair", () => {
      expect(projectedFinalFormat(pregameDetail.sport)).toBeNull();
      expect(projectedFinalFormat(ramsDetail.sport)).not.toBeNull();
      expect(foreign.event_id).toBe(15338496);
      expect(foreign.pm_spread_data?.projected_final).toEqual({
        home_score: 3.7,
        away_score: 2.4,
        spread_source: "sportsbook",
        total_source: "sportsbook",
      });
    });

    it("takes no ladder pair from another game's body", () => {
      expect(beforeForecast(ramsDetail, foreign)).toBeNull();
      expect(beforeForecast(ramsDetail, null)).toBeNull();
      // The same bytes under this game's id print, so the id alone withholds them.
      expect(beforeForecast(ramsDetail, relabelled)).toEqual(pair(3.7, 2.4, LADDER));
    });

    it("still prints this game's own ladder pair", () => {
      expect(beforeForecast(ramsDetail, ownLadder)).toEqual(pair(28.8, 25.5, LADDER));
    });

    it("keeps the game's own sportsbook pair beside another game's body", () => {
      const books = pair(29, 25.4, "Before the start · 22 sportsbooks");
      expect(beforeForecast(ramsWithBooks, foreign)).toEqual(books);
      expect(beforeForecast(ramsWithBooks, null)).toEqual(books);
    });

    it("the composed page with another game's body is exactly the page with none", () => {
      const build = (history: EventHistoryResponse | null) =>
        buildHockeyJourney({ event: ramsDetail, history, gameMarkets: null, host: host(RAMS_NOW) });
      const page = build(foreign);
      expect(page).toEqual(build(null));
      expect(page.headline.matrix.rows.map((r) => r.values[1])).toEqual([
        { kind: "absent", text: "No pregame forecast" },
        { kind: "absent", text: "No pregame forecast" },
      ]);
      expect(page.history.absence).toEqual({ title: "History unavailable", words: null });
      expect(build(relabelled).headline.matrix.rows.map((r) => text(r.values[1]))).toEqual(["3.7", "2.4"]);
    });
  });
});

// The FULL retained bodies, read-only, from `$BAINLUCK_ARTIFACTS_DIR` or the repo's own `artifacts/`
// (UNTRACKED: present only where a reader put them). Every byte is pinned by sha256 before a single
// assertion; where they are absent the block is SKIPPED (named), and the embedded subsets above
// remain the permanent guard.
const RETAINED_DESIGN = "discovery-containers-release-plan/event-page-design-20261011";
const RETAINED_PAYLOADS = `${RETAINED_DESIGN}/shipping-adoption-20261027/cli-candidate-20261030/retained-payloads`;
const RETAINED: Record<string, [string, string]> = {
  ramsDetail: [`${RETAINED_DESIGN}/probability-movement-v89/raw/nfl-pregame-detail.json`,
    "1f81fa527d56660a7c3fb0b495b0a8489aa7b202a9cc200558c3b817940b0eb9"],
  ramsHistory: [`${RETAINED_DESIGN}/probability-movement-v89/raw/nfl-pregame-history.json`,
    "c32ce4402faf5849afd93802eb4918d5b92a4d50f576bc2538c422f80d588332"],
  knightsDetail: [`${RETAINED_PAYLOADS}/nhl-15338496-detail-20261030T201355Z.json`,
    "50fbf4678a308e40481340e9b998a2a0870795dd8b04dfdfb05e31caf3dcc1da"],
  knightsHistory: [`${RETAINED_PAYLOADS}/nhl-15338496-history-20261030T201355Z.json`,
    "0fe7e8cd334d2b32b5d808bd2dbdec974bef052a53775991b1457bd37fafe812"],
  finishedDetail: [`${RETAINED_PAYLOADS}/nhl-15338034-detail-20261030T201355Z.json`,
    "4bd4832c10c7f31626a9cd31df415ef806db1f5a8c9ac1934aba3386d7fbd6e4"],
  finishedHistory: [`${RETAINED_PAYLOADS}/nhl-15338034-history-20261030T201355Z.json`,
    "f82a66d49b870f4df63e52f3639981e22e6efd321921238eabc8a59512759d8d"],
};
const RETAINED_ROOTS = [process.env.BAINLUCK_ARTIFACTS_DIR, join(__dirname, "../../../artifacts")].filter(
  (root): root is string => !!root,
);
const retainedPath = (key: string) =>
  RETAINED_ROOTS.map((root) => join(root, RETAINED[key][0])).find((path) => existsSync(path)) ?? null;
const retainedPresent = Object.keys(RETAINED).every((key) => retainedPath(key) !== null);
function retained<T>(key: string): T {
  const raw = readFileSync(retainedPath(key)!);
  expect(createHash("sha256").update(raw).digest("hex")).toBe(RETAINED[key][1]);
  return JSON.parse(raw.toString("utf8")) as T;
}

(retainedPresent ? describe : describe.skip)("#10868 history — FULL retained bodies through the actual helper (skipped where absent)", () => {
  const blankLineBefore = (body: EventHistoryResponse, t: number) =>
    ({
      ...body,
      aggregate_line: (body.aggregate_line ?? []).map((p) =>
        Date.parse(p.timestamp) < t ? { ...p, home_probability: null } : p,
      ),
    }) as unknown as EventHistoryResponse;
  const summary = (h: ReturnType<typeof hockeyJourneyHistory>, oldFloor: number) =>
    h.series.map((s) => {
      const points = s.runs.flat();
      return {
        points: points.length,
        runs: s.runs.length,
        first: points.length ? new Date(points[0].t).toISOString() : null,
        last: points.length ? new Date(points[points.length - 1].t).toISOString() : null,
        hollow: points.filter((p) => p.hollow).map((p) => new Date(p.t).toISOString()),
        olderThanStartLessADay: points.filter((p) => p.t < oldFloor).length,
      };
    });

  it("Rams 14780558, read 18.5 h before the start: the whole recorded day, 1,142 readings a side", () => {
    const event = retained<EventDetailResponse>("ramsDetail");
    const body = retained<EventHistoryResponse>("ramsHistory");
    expect(body.aggregate_line).toHaveLength(1143);
    const h = hockeyJourneyHistory(body, event, "before", ms("2026-10-12T05:45:12.645Z"));
    expect(h.line).toBe("blend");
    const side = {
      points: 1142,
      runs: 1,
      first: "2026-10-11T05:45:00.000Z",
      last: "2026-10-12T05:44:00.000Z",
      hollow: ["2026-10-12T05:44:00.000Z"],
      olderThanStartLessADay: 832,
    };
    expect(summary(h, ms(event.commence_time) - BEFORE_WINDOW_MS)).toEqual([side, side]);
    expect(h.domain).toEqual({ lower: ms("2026-10-11T05:45:00Z"), upper: ms("2026-10-12T05:44:00Z") });
  });

  it("Golden Knights 15338496, read 1 h 46 min before the start: 1,102 readings a side", () => {
    const event = retained<EventDetailResponse>("knightsDetail");
    const body = retained<EventHistoryResponse>("knightsHistory");
    expect(body.aggregate_line).toHaveLength(1103);
    const h = hockeyJourneyHistory(body, event, "before", PREGAME_NOW);
    const side = {
      points: 1102,
      runs: 1,
      first: "2026-10-29T20:13:00.000Z",
      last: "2026-10-30T20:11:00.000Z",
      hollow: ["2026-10-30T20:11:00.000Z"],
      olderThanStartLessADay: 56,
    };
    expect(summary(h, ms(event.commence_time) - BEFORE_WINDOW_MS)).toEqual([side, side]);
  });

  it("the finished 15338034's final and live frames do not depend on anything older than the last pregame reading", () => {
    const event = retained<EventDetailResponse>("finishedDetail");
    const body = retained<EventHistoryResponse>("finishedHistory");
    const now = ms("2026-10-30T20:13:55Z");
    const final = hockeyJourneyHistory(body, event, "final", now);
    const t = final.series[0].runs.flat().find((p) => p.hollow)!.t;
    // The final frame as the helper draws it on the full body (unchanged by this correction).
    const side = {
      points: 165,
      runs: 1,
      first: "2026-10-29T23:59:00.000Z",
      last: "2026-10-30T02:43:00.000Z",
      hollow: ["2026-10-29T23:59:00.000Z"],
      olderThanStartLessADay: 0,
    };
    expect(summary(final, ms(event.commence_time) - BEFORE_WINDOW_MS)).toEqual([side, side]);
    expect(hockeyJourneyHistory(blankLineBefore(body, t), event, "final", now)).toEqual(final);
    const live = { ...event, status: "live" } as EventDetailResponse; // CONSTRUCTED: status only
    const liveNow = ms("2026-10-30T01:30:00Z");
    const during = hockeyJourneyHistory(body, live, "live", liveNow);
    const tl = during.series[0].runs.flat().find((p) => p.hollow)!.t;
    expect(hockeyJourneyHistory(blankLineBefore(body, tl), live, "live", liveNow)).toEqual(during);
  });
});

describe("#10868 history — a start that is not a confirmed kick-off (CONSTRUCTED one-key variants)", () => {
  const UNCONFIRMED_WORDS = "Pregame and game readings are split at a confirmed start, and this game has none yet.";
  const variants: Array<[string, EventDetailResponse, EventHistoryResponse]> = [
    ["start_is_tbd: true", { ...pregameDetail, start_is_tbd: true } as EventDetailResponse, pregameHistory],
    [
      "commence_time_is_kickoff: false",
      pregameDetail,
      { ...pregameHistory, commence_time_is_kickoff: false } as EventHistoryResponse,
    ],
  ];

  it.each(variants)("%s keeps every recorded row as one unsplit history, with no baseline or guide", (_, event, body) => {
    expect(event.commence_time).toBe("2026-10-30T22:00:00+00:00");
    const h = hockeyJourneyHistory(body, event, "before", PREGAME_NOW);
    const [home, away] = h.series;
    const points = home.runs.flat();
    expect(h.absence).toBeNull();
    expect(home.runs).toHaveLength(1);
    // No one-day floor (it is measured from a confirmed start): 21:58 and 21:59 the day before are kept.
    expect(points).toHaveLength(25);
    expect(points[0].t).toBe(ms("2026-10-29T21:58:00+00:00"));
    expect(points[points.length - 1].t).toBe(ms("2026-10-30T20:11:00+00:00"));
    // The pinned edge is still not a reading.
    expect(points.some((p) => p.t === ms("2026-10-30T20:12:00+00:00"))).toBe(false);
    // No last-pregame baseline: no hollow mark, no "Last pregame" slot, no "Recorded" slot, no guide.
    expect(points.some((p) => p.hollow)).toBe(false);
    expect(h.guides).toEqual([]);
    expect(h.markKey).toBeNull();
    expect(h.readout).toBe("single");
    expect(h.beforeLabel).toBe("Start time not confirmed");
    for (const s of h.series) {
      expect(s.before).toEqual({ kind: "absent", words: UNCONFIRMED_WORDS });
      expect(s.recorded).toEqual({ kind: "absent", words: "Not recorded" });
    }
    // Same complement rule, row for row.
    expect(away.runs.flat().map((p) => p.t)).toEqual(points.map((p) => p.t));
    expect(away.runs.flat().map((p) => p.p)).toEqual(points.map((p) => 1 - p.p));
    expect(h.notes).toEqual([
      "Source: Bain Luck",
      "New Jersey Devils is the other side of the same line: 100% − Vegas Golden Knights.",
      "Gaps remain blank.",
    ]);
  });

  it("a finished game whose start is not a kick-off draws from its first row and still breaks every in-play hole", () => {
    const body = { ...finalHistory, commence_time_is_kickoff: false } as EventHistoryResponse; // CONSTRUCTED: one key
    const h = hockeyJourneyHistory(body, finalDetail, "final", FINAL_NOW);
    const [home, away] = h.series;
    // The gap rule judges in-play holes from the LISTED commence (00:00Z) even here,
    // so the game's five holes stay blank; only the first run reaches back to the first row.
    expect(home.runs.map((run) => run.length)).toEqual([42, 1, 5, 5, 5, 6]);
    expect(home.runs[0][0].t).toBe(ms("2026-10-02T23:52:00+00:00"));
    expect(home.runs[5][5]).toMatchObject({ t: ms("2026-10-04T02:48:00+00:00"), p: 0.98847 });
    const confirmed = hockeyJourneyHistory(finalHistory, finalDetail, "final", FINAL_NOW).series[0].runs;
    expect(home.runs.slice(1)).toEqual(confirmed.slice(1));
    // Settlement still removed, no hollow mark, no P1–P3 guides, unconfirmed words.
    expect(home.runs.flat().some((p) => p.p === 1)).toBe(false);
    expect(home.runs.flat().some((p) => p.hollow)).toBe(false);
    expect(h.guides).toEqual([]);
    expect(h.markKey).toBeNull();
    expect(h.beforeLabel).toBe("Start time not confirmed");
    expect(home.before).toEqual({ kind: "absent", words: UNCONFIRMED_WORDS });
    expect(away.runs.map((run) => run.length)).toEqual([42, 1, 5, 5, 5, 6]);
    expect(h.domain).toEqual({ lower: ms("2026-10-02T23:52:00+00:00"), upper: ms("2026-10-04T02:48:00+00:00") });
  });
});

describe("#10868 history — no history response (CONSTRUCTED: null / undefined)", () => {
  const answered = buildHockeyJourney({
    event: finalDetail,
    history: finalHistory,
    gameMarkets: finalMarkets,
    host: host(FINAL_NOW),
  });

  it.each([null, undefined])("history %p leaves only the chart unavailable", (missing) => {
    const j = buildHockeyJourney({ event: finalDetail, history: missing, gameMarkets: finalMarkets, host: host(FINAL_NOW) });
    // Everything else composes exactly as it does with the answer.
    expect(j.phase).toBe(answered.phase);
    expect(j.header).toEqual(answered.header);
    expect(j.headline).toEqual(answered.headline);
    expect(j.points).toEqual(answered.points);
    expect(j.assists).toEqual(answered.assists);
    expect(j.stories).toEqual(answered.stories);
    expect(j.originals).toEqual(answered.originals);
    expect(j.copy).toEqual(answered.copy);
    // The chart slot: "History unavailable" — never "No recorded history", no source note, no runs.
    const h = j.history;
    expect(h.absence).toEqual({ title: "History unavailable", words: null });
    expect(h.summary).toBe("History unavailable");
    expect(h.beforeLabel).toBe("History unavailable");
    expect(h.series.map((s) => s.before)).toEqual([
      { kind: "absent", words: "History unavailable" },
      { kind: "absent", words: "History unavailable" },
    ]);
    expect(h.series.every((s) => s.runs.length === 0)).toBe(true);
    expect(h.notes).toEqual([]);
    expect(h.line).toBeNull();
    expect(h.domain).toBeNull();
    expect([h.guides, h.xTicks, h.yTicks]).toEqual([[], [], []]);
    expect(h.markKey).toBeNull();
    expect(JSON.stringify(h)).not.toContain("No recorded history");
    expect(j.about).toEqual(answered.about.filter((line) => !answered.history.notes.includes(line)));
  });

  it("a body with no readable row is still \"No recorded history\"", () => {
    const empty = { ...pregameHistory, aggregate_line: [], history: [], win_prob_history: {} } as EventHistoryResponse; // CONSTRUCTED
    expect(hockeyJourneyHistory(empty, pregameDetail, "before", PREGAME_NOW).absence).toEqual({
      title: "No recorded history",
      words: null,
    });
  });
});

describe("#10868 hockey F1 — another game's history body is never this page's (exact event_id)", () => {
  // `finalHistory` is the REAL body of 15169793 (Wild–Bruins), held here on the page of 15338496
  // (Devils at Golden Knights). TEST CONTROL overlay: it also carries the pregame body's own ladder
  // pair (3.7 / 2.4), so nothing a foreign body holds can reach this page.
  const observedAt = pregameDetail.hero_probability_observed_at ?? null;
  const hero = pageHero(pregameDetail, pregameHistory, false);
  const fresh = host(PREGAME_NOW, { hero, probabilityObservedAt: observedAt });
  const build = (history: EventHistoryResponse | null) =>
    buildHockeyJourney({ event: pregameDetail, history, gameMarkets: pregameMarkets, host: fresh });
  const foreign = { ...finalHistory, pm_spread_data: pregameHistory.pm_spread_data } as EventHistoryResponse;
  const missing = build(null);
  const own = build(pregameHistory);

  it("decides ownership by the exact event_id alone", () => {
    expect(foreign.event_id).toBe(15169793);
    expect(pregameDetail.id).toBe(15338496);
    expect(ownHockeyHistory(pregameHistory, pregameDetail)).toBe(pregameHistory);
    expect(ownHockeyHistory(foreign, pregameDetail)).toBeNull();
    expect(ownHockeyHistory(null, pregameDetail)).toBeNull();
    expect(ownHockeyHistory(undefined, pregameDetail)).toBeNull();
    const { event_id: dropped, ...noId } = pregameHistory; // CONSTRUCTED: the id removed
    expect(dropped).toBe(15338496);
    expect(ownHockeyHistory(noId as unknown as EventHistoryResponse, pregameDetail)).toBeNull();
    const textId = { ...pregameHistory, event_id: "15338496" } as unknown as EventHistoryResponse; // CONSTRUCTED
    expect(ownHockeyHistory(textId, pregameDetail)).toBeNull();
  });

  it("W1: the page built with another game's body is exactly the page with no body", () => {
    const page = build(foreign);
    expect(page).toEqual(missing);
    const h = page.history;
    expect(h.absence).toEqual({ title: "History unavailable", words: null });
    expect(h.series.map((s) => s.id)).toEqual(["history:15338496:home", "history:15338496:away"]);
    expect(h.series.every((s) => s.runs.length === 0)).toBe(true);
    expect([h.notes, h.guides, h.xTicks, h.domain, h.line]).toEqual([[], [], [], null, null]);
    expect(JSON.stringify(h)).not.toContain("15169793");
    expect(page.about).not.toContain("Gaps remain blank.");
    expect(page.about.some((line) => line.startsWith("Source:"))).toBe(false);
    // The forecast stays its absence words; the own chance, stories and catalogue are untouched.
    expect(page.headline.matrix.rows.map((r) => r.values[1])).toEqual([
      { kind: "absent", text: "No pregame forecast" },
      { kind: "absent", text: "No pregame forecast" },
    ]);
    expect(page.headline.matrix.rows.map((r) => text(r.values[0]))).toEqual(["51%", "49%"]);
    expect(page.headline).toEqual(own.headline);
    expect([page.points, page.assists, page.stories, page.originals, page.copy]).toEqual([
      own.points,
      own.assists,
      own.stories,
      own.originals,
      own.copy,
    ]);
  });

  it("W1 control: the id is the only thing deciding", () => {
    // The foreign bytes relabelled to this game's id draw (TEST CONTROL)…
    const relabelled = build({ ...foreign, event_id: pregameDetail.id } as EventHistoryResponse);
    expect(relabelled).not.toEqual(missing);
    expect(relabelled.history.absence).toBeNull();
    // …and this game's own bytes relabelled to another id read as no body (TEST CONTROL).
    expect(build({ ...pregameHistory, event_id: 15169793 } as EventHistoryResponse)).toEqual(missing);
    expect(own).not.toEqual(missing);
  });

  it("W2: the chart reader refuses another game's body itself", () => {
    expect(hockeyJourneyHistory(foreign, pregameDetail, "before", PREGAME_NOW)).toEqual(
      unavailableHistory(pregameDetail, "before"),
    );
    expect(hockeyJourneyHistory(pregameHistory, finalDetail, "final", FINAL_NOW)).toEqual(
      unavailableHistory(finalDetail, "final"),
    );
    expect(hockeyJourneyHistory(pregameHistory, finalDetail, "live", FINAL_NOW)).toEqual(
      unavailableHistory(finalDetail, "live"),
    );
    // The same bytes under this page's id draw (TEST CONTROL).
    const relabelled = { ...foreign, event_id: pregameDetail.id } as EventHistoryResponse;
    expect(hockeyJourneyHistory(relabelled, pregameDetail, "before", PREGAME_NOW).absence).toBeNull();
  });
});

describe("#10868 points and assists — the finished game", () => {
  const names = teamShortNames(
    { name: finalDetail.home_team, abbreviation: finalDetail.home_team_data?.abbreviation },
    { name: finalDetail.away_team, abbreviation: finalDetail.away_team_data?.abbreviation },
    finalDetail.sport,
  );
  const points = hockeyJourneyContribution("points", finalDetail, finalMarkets, FINAL_NOW)!;
  const assists = hockeyJourneyContribution("assists", finalDetail, finalMarkets, FINAL_NOW)!;

  it("groups one ladder per player under stable source-record ids and keeps goals rows out", () => {
    expect(points.orientation).toBe("columns");
    expect(points.phase).toBe("final");
    expect(points.eyebrow).toBe("PLAYER POINTS");
    expect(points.chartTitle).toBe("Pregame chances · at least this many");
    expect(points.chooserTitle).toBe("Choose player · 3");
    expect(points.players.map((p) => p.id)).toEqual(["player:kirill kaprizov", "player:max shabanov", "player:quinn hughes"]);
    expect(points.players.map((p) => p.team)).toEqual([names.home, null, names.home]);
    const hughes = points.players[2];
    expect(hughes.milestones.map((m) => m.id)).toEqual([
      "kalshi|Boston vs Minnesota: Points-Quinn Hughes: 1+",
      "kalshi|Boston vs Minnesota: Points-Quinn Hughes: 2+",
      "kalshi|Boston vs Minnesota: Points-Quinn Hughes: 3+",
    ]);
    expect(hughes.milestones.map((m) => m.target)).toEqual(["1+", "2+", "3+"]);
    expect(hughes.milestones.map((m) => m.title)).toEqual(["1+ points", "2+ points", "3+ points"]);
    expect(assists.orientation).toBe("bars");
    for (const card of [points, assists]) {
      for (const p of card.players) expect(p.milestones.some((m) => m.id.includes(": Goals-"))).toBe(false);
    }
  });

  it("prints no settled row as a chance; the result is the settlement and the count is the box", () => {
    const hughes = points.players[2];
    for (const m of hughes.milestones) {
      expect(m.before).toBeNull();
      expect(m.beforeMissing).toBe("Unavailable");
      expect(m.current).toBeNull();
      expect(m.progress).toBeNull();
    }
    expect(hughes.defaultMilestoneId).toBeNull();
    expect(hughes.milestones.map((m) => m.result?.words)).toEqual([PROP_HIT_LABEL, PROP_HIT_LABEL, PROP_MISS_LABEL]);
    expect(hughes.milestones.map((m) => m.result?.kind)).toEqual(["reached", "reached", "missed"]);
    expect(hughes.actual).toEqual({
      kind: "count",
      count: "2",
      unit: "points",
      breakdown: "1 goal + 1 assist",
      detail: "box score after the final",
    });
    expect(hughes.milestones[0].timing).toEqual([
      "Pregame chance: Unavailable",
      "Final count: box score after the final",
      `Final result: ${PROP_HIT_LABEL} · settled by Kalshi`,
    ]);
    expect(points.players[0].actual).toMatchObject({ kind: "count", count: "2", breakdown: "2 goals + 0 assists" });
    // "Max Shabanov" is not named exactly by the box ("Maxim Shabanov"): fail closed.
    expect(points.players[1].actual).toEqual({ kind: "unavailable", words: "Final count unavailable" });
    expect(points.players[1].milestones.map((m) => m.result?.words)).toEqual([PROP_HIT_LABEL, PROP_MISS_LABEL]);
    const hughesAssists = assists.players.find((p) => p.id === "player:quinn hughes")!;
    expect(hughesAssists.milestones.map((m) => m.result?.words)).toEqual([PROP_HIT_LABEL, PROP_MISS_LABEL, PROP_MISS_LABEL]);
    expect(hughesAssists.actual).toMatchObject({ kind: "count", count: "1", unit: "assist", breakdown: null });
  });

  it("calls an unknown settlement unconfirmed, never missed", () => {
    const flipped = {
      ...finalMarkets,
      player_props: finalMarkets.player_props.map((row) =>
        row.outcome_name === "Quinn Hughes: 3+" && row.market_name.endsWith(": Points") ? { ...row, is_winner: null } : row,
      ),
    } as GameMarketsResponse; // CONSTRUCTED: one settlement field cleared
    const card = hockeyJourneyContribution("points", finalDetail, flipped, FINAL_NOW)!;
    const hughes = card.players.find((p) => p.id === "player:quinn hughes")!;
    expect(hughes.milestones[2].result).toEqual({ kind: "unconfirmed", words: "Result unconfirmed" });
  });
});

describe("#10868 points and assists — before the start and once play starts", () => {
  it("before the start the pregame chance is the quote's own price on its own recent clock", () => {
    const points = hockeyJourneyContribution("points", pregameDetail, pregameMarkets, PREGAME_NOW)!;
    expect(points.phase).toBe("before");
    expect(points.players.map((p) => p.name)).toEqual(["Jack Eichel", "Jack Hughes"]);
    const eichel = points.players[0];
    const first = eichel.milestones[0];
    expect(first.before?.probability).toBe(0.685);
    expect(first.before?.text).toBe("69%");
    expect(first.before?.detail).toBe(`recorded ${stamp("2026-10-30T20:12:00.557237+00:00")} · Kalshi`);
    expect(first.current).toBeNull();
    expect(eichel.actual).toEqual({ kind: "unavailable", words: "Count unavailable" });
    expect(eichel.defaultMilestoneId).toBe("kalshi|New Jersey vs Vegas: Points-Jack Eichel: 2+");

    const aged = hockeyJourneyContribution("points", pregameDetail, pregameMarkets, ms("2026-10-30T20:43:01Z"))!;
    for (const m of aged.players[0].milestones) {
      expect(m.before).toBeNull();
      expect(m.beforeMissing).toBe("No recent probability update");
    }
    expect(aged.players[0].defaultMilestoneId).toBeNull();
  });

  it("once play starts the pregame chance is the served mark, and a pre-start quote is no in-game reading", () => {
    const live = { ...pregameDetail, status: "live" } as EventDetailResponse; // CONSTRUCTED: status only
    const points = hockeyJourneyContribution("points", live, pregameMarkets, ms("2026-10-30T22:30:00Z"))!;
    expect(points.phase).toBe("live");
    const m = points.players.find((p) => p.name === "Jack Eichel")!.milestones[0];
    expect(m.before?.probability).toBe(0.645);
    expect(m.before?.detail).toBe("saved before the start · Kalshi");
    expect(m.current).toEqual({ kind: "unavailable", words: "No in-game reading" });
    expect(m.result).toBeNull();
    expect(m.timing).toEqual([
      "Pregame chance: saved before the start · Kalshi",
      "In-game chance: No in-game reading",
      "Count so far: Count unavailable",
    ]);
  });
});

describe("#10868 All props", () => {
  it("after the final lists every catalogued original with its served grade and no chance", () => {
    const page = hockeyJourneyOriginals(finalDetail, finalMarkets, FINAL_NOW);
    expect(page.scope).toBe("nhl:15169793:final:originals");
    expect(page.originals).toHaveLength(23);
    expect(page.context).toBe("23 originals");
    expect(new Set(page.originals.map((o) => o.key)).size).toBe(23);
    const byIdentity = (market: string, side: string) =>
      page.originals.find((o) => o.identity.market === market && o.identity.side === side)!;
    expect(byIdentity("64871068", "243945029").label).toBe("Kirill Kaprizov 2+ points");
    expect(byIdentity("64870807", "243939188").label).toBe("Quinn Hughes 2+ assists");
    expect(byIdentity("64871068", "243945042").label).toBe("Quinn Hughes 3+ points");
    expect(byIdentity("63539066", "239380538").label).toBe("Over 1.5 goals scored");
    for (const o of page.originals) {
      expect(o.mode).toBe("result");
      expect(o.later).toBeNull();
      expect(o.pregame).toEqual({ kind: "missing", words: "No pregame chance" });
      expect(o.about.rules).toBe("Rules unavailable");
    }
    // Web's one settled vocabulary (lib/propGrade.ts); native prints OutcomeVerdict's "Won" / "Lost".
    expect(byIdentity("64871068", "243945029").grade).toEqual({ hit: true, words: PROP_HIT_LABEL, provenance: "Settlement · Kalshi" });
    expect(byIdentity("64871068", "243945042").grade).toEqual({ hit: false, words: PROP_MISS_LABEL, provenance: "Settlement · Kalshi" });
    expect(byIdentity("63253211", "238404189").grade).toEqual({ hit: true, words: PROP_HIT_LABEL, provenance: "Settlement · Polymarket" });
    expect(byIdentity("64870910", "243940844").grade?.words).toBe(PROP_MISS_LABEL);
  });

  it("before the start prints each original's own recent price, or says it has none", () => {
    const page = hockeyJourneyOriginals(pregameDetail, pregameMarkets, PREGAME_NOW);
    expect(page.originals).toHaveLength(18);
    const eichel = page.originals.find((o) => o.outcome === "Jack Eichel: 1+" && o.title.endsWith(": Points"))!;
    expect(eichel.label).toBe("Jack Eichel 1+ points");
    expect(eichel.mode).toBe("pregame");
    expect(eichel.pregame).toEqual({
      kind: "value",
      text: "69%",
      placement: 0.685,
      provenance: `${stamp("2026-10-30T20:12:00.557237+00:00")} · Kalshi`,
    });
    const devils = page.originals.find((o) => o.identity.market === "68189231" && o.identity.side === "255929341")!;
    expect(devils.identity.source).toBe("polymarket");
    expect(devils.pregame).toEqual({ kind: "missing", words: "No recent probability update" });
    for (const o of page.originals) {
      expect(o.later).toBeNull();
      expect(o.grade).toBeNull();
    }
  });
});

describe("#10868 All props — during play a quote is current only as the in-game reading admits it", () => {
  const live = { ...pregameDetail, status: "live" } as EventDetailResponse; // CONSTRUCTED: status only
  const HISTORICAL = "Last recorded probability (historical)";
  /** CONSTRUCTED: Jack Eichel 1+ points (Kalshi, outcome 256284771) with `fields` changed; every other row verbatim. */
  function withEichel(fields: Record<string, unknown>): GameMarketsResponse {
    return {
      ...pregameMarkets,
      player_props: pregameMarkets.player_props.map((row) =>
        row.contributor_outcome_ids?.[0] === 256284771 ? { ...row, ...fields } : row,
      ),
    } as unknown as GameMarketsResponse;
  }
  const eichelOf = (page: ReturnType<typeof hockeyJourneyOriginals>) =>
    page.originals.find((o) => o.identity.market === "68282128" && o.identity.side === "256284771")!;

  it("a stale quote observed during play is no headline figure; Details keep it with its own clock and venue", () => {
    const page = hockeyJourneyOriginals(live, withEichel({ observed_at: "2026-10-30T22:05:00Z" }), ms("2026-10-30T22:45:00Z"));
    expect(page.originals).toHaveLength(18);
    const o = eichelOf(page);
    expect(o.identity).toEqual({ source: "kalshi", market: "68282128", side: "256284771" });
    expect(o.mode).toBe("current");
    expect(o.later).toEqual({ kind: "missing", words: "No recent probability update" });
    const at = stamp("2026-10-30T22:05:00Z");
    expect(o.about.historical).toEqual({
      text: "69%",
      recorded: `${at} · Kalshi`,
      label: HISTORICAL,
      value: `69%, recorded ${at} · Kalshi`,
    });
    // The served baseline stays the served mark, not the quote.
    expect(o.pregame).toMatchObject({ kind: "value", placement: 0.645, provenance: "Saved before the start · Kalshi" });
    // Every other original was last quoted before the start: no current figure anywhere on the page.
    for (const other of page.originals) {
      expect(other.later?.kind).toBe("missing");
      expect(other.about.historical?.recorded).toBeTruthy();
    }
    expect(page.originals.filter((x) => x !== o).every((x) => x.later?.kind === "missing" && x.later.words === "No in-game reading")).toBe(true);
  });

  it("a still-recent PRE-START quote read after the start (22:00Z event, 21:50Z quote, 22:05Z reader) is not current", () => {
    expect(isRecentQuote("2026-10-30T21:50:00Z", ms("2026-10-30T22:05:00Z"))).toBe(true);
    const page = hockeyJourneyOriginals(live, withEichel({ observed_at: "2026-10-30T21:50:00Z" }), ms("2026-10-30T22:05:00Z"));
    const o = eichelOf(page);
    expect(o.later).toEqual({ kind: "missing", words: "No in-game reading" });
    const at = stamp("2026-10-30T21:50:00Z");
    expect(o.about.historical).toEqual({ text: "69%", recorded: `${at} · Kalshi`, label: HISTORICAL, value: `69%, recorded ${at} · Kalshi` });
    // Nothing borrowed: the baseline is the served mark (0.645), never the 0.685 quote.
    expect(o.pregame).toMatchObject({ kind: "value", placement: 0.645, provenance: "Saved before the start · Kalshi" });
    expect(o.identity).toEqual({ source: "kalshi", market: "68282128", side: "256284771" });
  });

  it("a dated, post-start, recent quote is the current chance, and keeps no historical copy", () => {
    const page = hockeyJourneyOriginals(live, withEichel({ observed_at: "2026-10-30T22:20:00Z" }), ms("2026-10-30T22:30:00Z"));
    const o = eichelOf(page);
    expect(o.later).toEqual({
      kind: "value",
      text: "69%",
      placement: 0.685,
      provenance: `Recorded ${stamp("2026-10-30T22:20:00Z")} · Kalshi`,
    });
    expect(o.about.historical).toBeNull();
  });

  it("an undated quote is no recent update; Details keep it with no time", () => {
    const page = hockeyJourneyOriginals(live, withEichel({ observed_at: null }), ms("2026-10-30T22:30:00Z"));
    const o = eichelOf(page);
    expect(o.later).toEqual({ kind: "missing", words: "No recent probability update" });
    expect(o.about.historical).toEqual({ text: "69%", recorded: null, label: HISTORICAL, value: "69%, time unknown" });
  });

  it("a venue-settled row shows no chance and keeps no quote", () => {
    const settled = withEichel({ observed_at: "2026-10-30T22:20:00Z", is_winner: true, resolution_source: "api_settlement" });
    const o = eichelOf(hockeyJourneyOriginals(live, settled, ms("2026-10-30T22:30:00Z")));
    expect(o.later).toEqual({ kind: "missing", words: "No current chance" });
    expect(o.about.historical).toBeNull();
  });
});

describe("#10868 the composed page", () => {
  it("offers the points and assists stories in a fixed order, manually, and counts All props", () => {
    const journey = buildHockeyJourney({
      event: finalDetail,
      history: finalHistory,
      gameMarkets: finalMarkets,
      host: host(FINAL_NOW),
    });
    expect(journey.phase).toBe("final");
    expect(journey.stories.map((s) => s.id)).toEqual(["points", "assists"]);
    expect(journey.copy.manualStatus).toBe("Use Previous or Next to see each story");
    expect(journey.copy.allPropsLabel).toBe("All 23 original outcomes");
    expect(journey.about).toContain("Pregame chance: Pre-match");
    expect(journey.about).toContain("Gaps remain blank.");
  });
});

describe("#10868 matrix hierarchy and About — what the native layout model carries", () => {
  it("leads with the current chance during play and keeps native's labelled-pair groups", () => {
    const final = hockeyJourneyHeadline(finalDetail, finalHistory, host(FINAL_NOW)).matrix;
    expect([final.lead, final.groups]).toEqual([0, [[0], [1, 2]]]);
    const before = hockeyJourneyHeadline(pregameDetail, pregameHistory, host(PREGAME_NOW)).matrix;
    expect([before.lead, before.groups]).toEqual([0, [[0, 1]]]);
    const live = { ...pregameDetail, status: "live" } as EventDetailResponse; // CONSTRUCTED: status only
    const during = hockeyJourneyHeadline(live, pregameHistory, host(ms("2026-10-30T22:30:00Z"))).matrix;
    expect(during.columns[during.lead].title).toMatch(/chance$/);
    expect([during.lead, during.groups]).toEqual([1, [[0, 1], [2, 3]]]);
  });

  it("moves each column's source and clock to About only because About carries every one", () => {
    for (const journey of [
      buildHockeyJourney({ event: finalDetail, history: finalHistory, gameMarkets: finalMarkets, host: host(FINAL_NOW) }),
      buildHockeyJourney({
        event: pregameDetail,
        history: pregameHistory,
        gameMarkets: pregameMarkets,
        host: host(PREGAME_NOW, {
          hero: pageHero(pregameDetail, pregameHistory, false),
          probabilityObservedAt: pregameDetail.hero_probability_observed_at ?? null,
        }),
      }),
    ]) {
      const removed = journey.headline.matrix.columns.filter((c) => c.provenance);
      expect(removed.length).toBeGreaterThan(0);
      for (const column of removed) expect(journey.about).toContain(matrixProvenanceLine(column));
      expect(journey.provenanceInAbout).toBe(true);
      // The game state and its context stay in the headline.
      expect(journey.headline.state).toBeTruthy();
    }
    const final = buildHockeyJourney({ event: finalDetail, history: finalHistory, gameMarkets: finalMarkets, host: host(FINAL_NOW) });
    expect(final.about).toContain(`Final goals: ESPN · score observed ${stamp("2026-10-04T05:59:38.451734+00:00")}`);
    expect(final.headline.matrix.rows.map((r) => r.result)).toEqual(["Won", "Lost"]);
  });
});

describe("#10868 points and assists — the reader's held choice (native selection rules)", () => {
  const points = hockeyJourneyContribution("points", finalDetail, finalMarkets, FINAL_NOW)!;
  const HUGHES = "player:quinn hughes";
  const HUGHES_2 = "kalshi|Boston vs Minnesota: Points-Quinn Hughes: 2+";

  it("shows the first player at its default only before the reader chooses", () => {
    const none = resolveContributionChoice(points, NO_HELD_CHOICE);
    expect(none.player?.id).toBe("player:kirill kaprizov");
    expect(none.notice).toBeNull();
    const pregame = hockeyJourneyContribution("points", pregameDetail, pregameMarkets, PREGAME_NOW)!;
    const def = resolveContributionChoice(pregame, NO_HELD_CHOICE);
    expect(def.player?.name).toBe("Jack Eichel");
    expect(def.selected?.id).toBe("kalshi|New Jersey vs Vegas: Points-Jack Eichel: 2+");
  });

  it("resolves a held player and milestone exactly", () => {
    const held = resolveContributionChoice(points, { playerId: HUGHES, milestoneId: HUGHES_2 });
    expect(held.player?.id).toBe(HUGHES);
    expect(held.selected?.id).toBe(HUGHES_2);
    expect(held.notice).toBeNull();
  });

  it("keeps a held player that is no longer served — no other player is shown in its place", () => {
    const without = { ...points, players: points.players.filter((p) => p.id !== HUGHES) }; // CONSTRUCTED: one player gone
    const held = resolveContributionChoice(without, { playerId: HUGHES, milestoneId: HUGHES_2 });
    expect(held).toEqual({ player: null, selected: null, notice: "Selected player unavailable." });
  });

  it("keeps a held milestone that is no longer served — no other milestone is selected", () => {
    const held = resolveContributionChoice(points, { playerId: HUGHES, milestoneId: "kalshi|gone" });
    expect(held.player?.id).toBe(HUGHES);
    expect(held.selected).toBeNull();
    expect(held.notice).toBe("Selected milestone unavailable.");
  });
});

// ─── Reader words: one spelling on both platforms (Design copy principle, 2026-10-31) ─

describe("every reader word the native hockey adapters and the web twin both name is spelled the same", () => {
  const UTILITIES = join(__dirname, "../../../ios/Bain Luck/Bain Luck/Utilities");
  /** The `enum Words` string constants of one native adapter, by name. */
  const nativeWords = (file: string): Record<string, string> => {
    const source = readFileSync(join(UTILITIES, file), "utf8");
    const start = source.indexOf("enum Words");
    expect(start).toBeGreaterThan(-1);
    const body = source.slice(start, source.indexOf("\n    }\n", start));
    const words: Record<string, string> = {};
    for (const m of body.matchAll(/static let (\w+) = "((?:[^"\\]|\\.)*)"/g)) words[m[1]] = m[2];
    return words;
  };
  const tables: [string, Record<string, unknown>, number][] = [
    ["HockeyJourneyPageAdapter10868.swift", MATRIX_WORDS, 19],
    ["HockeyJourneyContributionAdapter10868.swift", CONTRIBUTION_WORDS, 20],
    ["HockeyJourneyOriginalsAdapter10868.swift", ORIGINALS_WORDS, 11],
  ];

  it.each(tables)("%s", (file, web, sharedAtLeast) => {
    const native = nativeWords(file);
    const shared = Object.keys(native).filter((key) => key in web);
    // Not vacuous: the parse finds the tables (counts at 2026-10-31; a new shared word only raises them).
    expect(shared.length).toBeGreaterThanOrEqual(sharedAtLeast);
    expect(Object.fromEntries(shared.map((key) => [key, web[key]]))).toEqual(
      Object.fromEntries(shared.map((key) => [key, native[key]])),
    );
  });

  it("the availability words say what is unavailable, never the pipeline", () => {
    expect([MATRIX_WORDS.forecastWithheld, CONTRIBUTION_WORDS.notPriced, CONTRIBUTION_WORDS.boxSoFar,
      ORIGINALS_WORDS.noSettlement, ORIGINALS_WORDS.disputed]).toEqual([
      "Forecast unavailable", "Chance unavailable", "box score · update time not recorded",
      "Result not recorded yet", "Result sources disagree",
    ]);
    const all = [MATRIX_WORDS, CONTRIBUTION_WORDS, ORIGINALS_WORDS].flatMap((t) =>
      Object.values(t as Record<string, unknown>).filter((v): v is string => typeof v === "string"));
    for (const word of all) expect(word).not.toMatch(/\b(served|priced|withheld|admitted|payload)\b/i);
  });
});
