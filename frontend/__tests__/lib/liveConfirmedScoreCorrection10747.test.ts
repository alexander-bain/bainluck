/**
 * #10747 — a LIVE hero takes a newer confirmed whole score over an older held
 * history score, including an official correction downward.
 *
 * `computeLastChartPoint` let a non-null history pair win whenever it existed.
 * So the page could hold the event row's confirmed 3–2 (`score_observed_at`
 * newer than every history row behind the pair) and still print the history
 * row's 4–2, while the probability beside it was already current. The event
 * row's stamp is written only when a writer read a score and the row holds
 * exactly that pair after the write (live's PR #4912), so on an explicitly
 * live page a strictly newer confirmation of a DIFFERENT full pair is the
 * newer reading of the score.
 *
 * The new rule is opt-in (sixth argument, `eventStatus === "live"`) and
 * atomic: both values and the clock come from the event row, or none do.
 * Every refusal below keeps the existing #4571 / #5521 / #7315 selection.
 */
import fs from "fs";
import path from "path";
import { computeLastChartPoint } from "@/lib/eventKeyStats";
import { newestServedScore } from "@/lib/event/newestServedScore";
import { fetchEventWithLiveFrame } from "@/lib/reconcileEventPoll";
import type { EventHistoryResponse } from "@/lib/types";

const T1 = "2026-10-08T01:00:00Z"; // the held history row
const T2 = "2026-10-08T01:05:00Z"; // the event row's confirmation
const T3 = "2026-10-08T01:10:00Z"; // a newer history half

function espnRow(overrides: Record<string, unknown> = {}) {
  return {
    timestamp: T1,
    home_probability: 0.6,
    away_probability: 0.4,
    home_score: 4,
    away_score: 2,
    period: "7",
    game_clock: null,
    ...overrides,
  };
}

function hist(partial: Partial<EventHistoryResponse> = {}): EventHistoryResponse {
  return {
    event_id: 1,
    history: [],
    espn_history: [espnRow()],
    aggregate_line: [{ timestamp: "2026-10-08T01:06:00Z", home_probability: 0.57 }],
    completed_at: null,
    ...partial,
  } as unknown as EventHistoryResponse;
}

describe("#10747 the live hero takes a newer confirmed whole pair", () => {
  test("THE SPECIMEN: held 4–2 at t1, confirmed 3–2 at t2, live — the hero prints 3–2 dated t2", () => {
    const pt = computeLastChartPoint(hist(), 3, 2, T2, null, "live");
    expect([pt?.homeScore, pt?.awayScore]).toEqual([3, 2]);
    expect(pt?.scoreStamp).toBe(T2);
    expect(pt?.scoreFrom).toBe("event");
  });

  test("the probability, period and clock are untouched by the adoption", () => {
    const live = computeLastChartPoint(hist(), 3, 2, T2, null, "live")!;
    const dflt = computeLastChartPoint(hist(), 3, 2, T2, null)!;
    for (const key of ["homeProb", "awayProb", "probKnown", "timestamp", "period", "clock"] as const) {
      expect(live[key]).toEqual(dflt[key]);
    }
    expect(live.homeProb).toBe(0.57);
    expect(live.period).toBe("7");
  });

  test("an upward update is the same rule, not a special case", () => {
    const pt = computeLastChartPoint(hist(), 5, 2, T2, null, "live");
    expect([pt?.homeScore, pt?.awayScore, pt?.scoreStamp]).toEqual([5, 2, T2]);
  });

  test("zero is a complete score", () => {
    const pt = computeLastChartPoint(hist(), 0, 2, T2, null, "live");
    expect([pt?.homeScore, pt?.awayScore, pt?.scoreFrom]).toEqual([0, 2, "event"]);
  });

  test("the input history is not rewritten", () => {
    const h = hist();
    const before = JSON.parse(JSON.stringify(h));
    computeLastChartPoint(h, 3, 2, T2, null, "live");
    expect(h).toEqual(before);
  });

  test("a scoring play that produced the OLD pair is withheld by the existing #8967 check", () => {
    const plays = [{ timestamp: T1, home_score: 4, away_score: 2, text: "Solo homer" }];
    const live = computeLastChartPoint(hist({ scoring_plays: plays } as never), 3, 2, T2, null, "live");
    expect(live?.scoringPlay).toBeNull();
    // CONTROL: the default view still prints 4–2 beside the play that made it.
    const dflt = computeLastChartPoint(hist({ scoring_plays: plays } as never), 3, 2, T2, null);
    expect(dflt?.scoringPlay).toMatchObject({ home_score: 4, away_score: 2 });
  });
});

describe("#10747 freshness: strictly newer than BOTH selected history halves", () => {
  test("an equal event stamp refuses", () => {
    const pt = computeLastChartPoint(hist(), 3, 2, T1, null, "live");
    expect([pt?.homeScore, pt?.scoreStamp, pt?.scoreFrom]).toEqual([4, T1, "history"]);
  });

  test("an older event stamp refuses", () => {
    const pt = computeLastChartPoint(hist(), 3, 2, "2026-10-08T00:55:00Z", null, "live");
    expect([pt?.homeScore, pt?.scoreStamp, pt?.scoreFrom]).toEqual([4, T1, "history"]);
  });

  test("an event stamp BETWEEN the two halves refuses — the oldest half is not the bar", () => {
    // Home comes off a newer score_history row (t3), away off ESPN (t1): the
    // snapshot carries no away score, so #5521 keeps that side on ESPN. The
    // pair's `scoreStamp` is its OLDEST half, t1; t2 beats it but not t3.
    const h = hist({
      score_history: [{ timestamp: T3, home_score: 5, away_score: null }],
    } as never);
    const pt = computeLastChartPoint(h, 3, 2, T2, null, "live");
    expect([pt?.homeScore, pt?.awayScore]).toEqual([5, 2]);
    expect(pt?.scoreFrom).toBe("history");
    expect(pt?.scoreStamp).toBe(T1);
  });

  test("a raw sibling clock does not stand in for the SELECTED newer half", () => {
    // ESPN at t1 is the raw ESPN clock; the selected pair is the t3 snapshot.
    const h = hist({
      score_history: [{ timestamp: T3, home_score: 4, away_score: 3 }],
    } as never);
    const pt = computeLastChartPoint(h, 3, 2, T2, null, "live");
    expect([pt?.homeScore, pt?.awayScore, pt?.scoreStamp]).toEqual([4, 3, T3]);
  });

  test("CONTROL: an event stamp newer than both halves does adopt", () => {
    const h = hist({
      score_history: [{ timestamp: T3, home_score: 5, away_score: null }],
    } as never);
    const pt = computeLastChartPoint(h, 3, 2, "2026-10-08T01:15:00Z", null, "live");
    expect([pt?.homeScore, pt?.awayScore, pt?.scoreFrom]).toEqual([3, 2, "event"]);
  });
});

describe("#10747 confirmation and atomicity: anything less keeps the prior selection", () => {
  const prior = (pt: ReturnType<typeof computeLastChartPoint>) =>
    [pt?.homeScore, pt?.awayScore, pt?.scoreFrom];

  test.each([
    ["absent event stamp", undefined],
    ["null event stamp", null],
    ["unparseable event stamp", "soon"],
    ["empty event stamp", ""],
  ])("%s", (_why, stamp) => {
    expect(prior(computeLastChartPoint(hist(), 3, 2, stamp, null, "live"))).toEqual([4, 2, "history"]);
  });

  test.each([
    ["home event score absent", null, 2],
    ["away event score absent", 3, undefined],
    ["home event score not finite", Number.NaN, 2],
    ["away event score not finite", 3, Number.POSITIVE_INFINITY],
  ])("%s", (_why, home, away) => {
    const pt = computeLastChartPoint(hist(), home as number, away as number, T2, null, "live");
    expect([pt?.homeScore, pt?.awayScore]).toEqual([4, 2]);
    expect(pt?.scoreFrom).toBe("history");
  });

  test("one history side absent: not a whole held pair, so the existing mixed rule stands", () => {
    const h = hist({ espn_history: [espnRow({ away_score: null })] } as never);
    const pt = computeLastChartPoint(h, 3, 2, T2, null, "live");
    expect([pt?.homeScore, pt?.awayScore, pt?.scoreFrom]).toEqual([4, 2, "mixed"]);
  });

  test("a history half with no stamp is an unknown age, never assumed older", () => {
    const h = hist({ espn_history: [espnRow({ timestamp: "" })] } as never);
    const pt = computeLastChartPoint(h, 3, 2, T2, null, "live");
    expect(prior(pt)).toEqual([4, 2, "history"]);
    expect(pt?.scoreStamp).toBeNull();
  });

  test("a history half with an unparseable stamp is an unknown age", () => {
    const h = hist({ espn_history: [espnRow({ timestamp: "later" })] } as never);
    expect(prior(computeLastChartPoint(h, 3, 2, T2, null, "live"))).toEqual([4, 2, "history"]);
  });
});

describe("#10747 scope: only an explicitly live, unfinished view", () => {
  test.each([
    ["omitted", undefined],
    ["null", null],
    ["unknown", "weird"],
    ["scheduled", "scheduled"],
    ["suspended", "suspended"],
    ["completed", "completed"],
    ["Live (case differs)", "Live"],
  ])("status %s keeps the default history pick", (_why, status) => {
    const pt = computeLastChartPoint(hist(), 3, 2, T2, null, status as string | null | undefined);
    expect([pt?.homeScore, pt?.awayScore, pt?.scoreStamp, pt?.scoreFrom]).toEqual([4, 2, T1, "history"]);
  });

  test.each([
    ["a parseable completed_at", "2026-10-08T01:20:00Z"],
    ["an empty completed_at (present, malformed)", ""],
    ["an unparseable completed_at", "final"],
  ])("%s refuses even when the caller says live", (_why, completedAt) => {
    const pt = computeLastChartPoint(hist({ completed_at: completedAt } as never), 3, 2, T2, null, "live");
    expect([pt?.homeScore, pt?.awayScore, pt?.scoreFrom]).toEqual([4, 2, "history"]);
  });

  test("same whole pair, newer stamp: history provenance and the #4571 confirmation clock", () => {
    const pt = computeLastChartPoint(hist(), 4, 2, T2, null, "live");
    expect([pt?.homeScore, pt?.awayScore, pt?.scoreFrom, pt?.scoreStamp]).toEqual([4, 2, "history", T2]);
  });

  test("no history pair at all: the event arm already speaks, unchanged", () => {
    const pt = computeLastChartPoint(hist({ espn_history: [] } as never), 3, 2, T2, null, "live");
    expect([pt?.homeScore, pt?.awayScore, pt?.scoreFrom, pt?.scoreStamp]).toEqual([3, 2, "event", T2]);
  });
});

describe("#10747 through the page's production chain", () => {
  test("a live detail read carrying the correction reaches the hero via fetchEventWithLiveFrame → newestServedScore", async () => {
    const detail = {
      id: 1,
      status: "live",
      home_score: 3,
      away_score: 2,
      score_observed_at: T2,
      completed_at: null,
    };
    const event = await fetchEventWithLiveFrame(
      async () => detail as never,
      () => null,
    );
    const served = newestServedScore(event as never, undefined);
    const pt = computeLastChartPoint(
      hist(),
      served.home_score,
      served.away_score,
      served.score_observed_at,
      null,
      (event as { status?: string }).status,
    );
    expect([pt?.homeScore, pt?.awayScore, pt?.scoreStamp]).toEqual([3, 2, T2]);
  });

  test("the page passes the event's own status as the sixth argument", () => {
    const PAGE = path.resolve(__dirname, "../../app/events/[id]/page.tsx");
    const code = fs
      .readFileSync(PAGE, "utf8")
      .replace(/\/\*[\s\S]*?\*\//g, " ")
      .split("\n")
      .map((line) => line.replace(/(^|\s)\/\/.*$/, "$1"))
      .join("\n");
    expect(code).toMatch(
      /computeLastChartPoint\(\s*historyData,\s*servedScore\.home_score,\s*servedScore\.away_score,\s*servedScore\.score_observed_at,\s*event\?\.status === "live" \? event\?\.espn \?\? null : null,\s*event\?\.status,?\s*\)/,
    );
  });
});
