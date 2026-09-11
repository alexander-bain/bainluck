/**
 * #4571 — THE DISPLAYED SCORE OWNS THE BADGE CLOCK.
 *
 * WHAT A READER GETS TODAY. Outside tennis the hero prints a green
 * `live · 6s ago` over a score of entirely unknown age. #4469 fixed the glance
 * for tennis by feeding `heroFreshness` the games line's `observed_at`; every
 * other sport falls down the `: null` arm of that same ternary, so the badge
 * ages the PRICE and says nothing about the number beside it. CERT-2545's
 * grader put it in one sentence — *"the badge can still age only the price"* —
 * and BLOCKed live's backend half for having no consumer. This is the consumer.
 *
 * ═══ WHY THIS IS NOT THE SIX-LINE WIRING IT LOOKS LIKE ═══
 *
 * The obvious binding is wrong, and it is wrong in the direction that reads as
 * correct. `page.tsx` renders
 *
 *     bestHomeScore = lastChartPoint?.homeScore ?? event?.home_score ?? null
 *
 * and `computeLastChartPoint` resolves `homeScore` and `timestamp` through TWO
 * INDEPENDENT CASCADES: `homeScore` falls through `lastEspn -> event.home_score`,
 * while `timestamp` falls through `lastEspn -> lastWp -> lastHist`. When there
 * is no ESPN row they come apart — the score is the event row's and the
 * timestamp is a PRICE SNAPSHOT'S. Dating the score with `lastChartPoint
 * .timestamp` therefore re-commits the exact defect #4571 was filed to kill,
 * wearing a face that looks precise. live/146 proved it on production event
 * 15298476: 0 `espn_history` rows, win-prob sources `['kalshi','polymarket']`,
 * so `homeScore` was the event row's `2` while `timestamp` was Kalshi's clock.
 * That case is pinned below as `THE TRAP`, because it is the implementation a
 * reasonable person writes from the cert's wording.
 *
 * The first spec handed to this lane (live/138, 2026-09-10) proposed the other
 * plausible shape — bind the event stamp only when `lastChartPoint?.homeScore
 * == null`. That is also wrong, and measurably so: `computeLastChartPoint`
 * ALREADY falls back to `event.home_score`, so on the event-row branch
 * `lastChartPoint.homeScore` is non-null and the guard never fires. live/146's
 * census puts that branch at 28 of the 36 events rendering a score in a 30-hour
 * window — the majority, not an edge — so the fix would have shipped inert on
 * the case it was written for. Both near-misses are asserted below so neither
 * can be reintroduced by someone simplifying this code.
 *
 * ═══ THE RULE ═══
 *
 * The stamp follows PROVENANCE, not position: the arm that supplied the number
 * supplies its clock. A side that renders no number contributes no age. A side
 * that renders a number whose arm has no stamp makes the pair undatable and the
 * answer is null — an absence must not be dated (#3473), and a glance is only as
 * current as its oldest half, which is `heroFreshness`'s own rule one level up.
 *
 * ═══ WHAT SHIPS DARK, SAID PLAINLY ═══
 *
 * `event.score_observed_at` IS NOT ON PRODUCTION. live's backend sha (`8f290789`,
 * CERT-2545) is blocked on this half existing, so today the event-row arm reports
 * null and the badge ages on the price exactly as it does now. That is the
 * majority branch, so **most of this ship is not observable until live's sha
 * lands** and no screenshot can show it. What IS live today is the ESPN arm —
 * `espn_history[last].timestamp` is already served — so a live ESPN-dense event
 * starts telling the truth on merge. The tests below cover both arms; only one
 * of them can be photographed this week.
 *
 * RED-FIRST, measured against `32d5a3cd` rather than reasoned: **14 failed, 2
 * passed of 16**. On the parent `computeLastChartPoint` emits no `scoreStamp`
 * or `scoreFrom` at all, so every assertion naming either reads `undefined` and
 * fails — including the ones written as controls. That is worth saying rather
 * than dressing up: a suite where almost everything is red on the parent cannot
 * by itself distinguish *"the binding is correct"* from *"the fields now exist"*.
 *
 * The two rows that ARE green on both sides are the ones carrying that weight,
 * and both are pure prohibitions — the only kind of assertion that survives the
 * fix being reverted:
 *
 *   1. **THE TRAP** — `lastChartPoint.timestamp` is a price clock on the
 *      majority branch and is never the score's age. Green on the parent because
 *      the parent does not date the score at all; it stays green only while
 *      nobody "simplifies" this into the obvious one-liner.
 *   2. **The tennis arm control** — #4469's `linescore.observed_at` is still the
 *      first arm of the ternary. This ship must not regress the ship before it.
 *
 * The remaining correctness pressure comes from the mutation table in the PR,
 * not from the red count. A suite for a freshness fix that only asserted "a
 * stamp appears" would pass on the price clock, which is the whole defect.
 *
 * ═══ AMENDED — THE ARM IS AN ARRAY, NOT A WRITER ═══
 *
 * The first commit shipped the history arm labelled `"espn"`. live/147 measured
 * that it cannot be: `espn_history` is not all ESPN. `routes/events.py:15649`
 * appends MLB Stats API and `stat_model` rows into it with no origin key,
 * shaped like ESPN rows, then sorts by timestamp — and the supplement is dense
 * (~50–130 points) where ESPN is sparse (2–16), so on **8 of 15** recent scoring
 * MLB events the LAST row, the one this cascade reads, is a supplement.
 * `scoreStamp` was correct throughout, because each row carries its own
 * timestamp; only the label would have lied. The sting is that those MLB rows
 * are exactly the arm that can be photographed, so the label would have been
 * least trustworthy where it was most visible.
 *
 * So the value is `"history"` and the field is explicitly NOT an attribution.
 * Its own red-first, measured against `4e6b2744` (master carrying the first
 * commit): **3 failed, 15 passed of 18** — the two arm-label rows and the new
 * naming guard. The two rows added with it are pure prohibitions and green on
 * both sides: the arm is never called `espn`, and the page never renders
 * `scoreFrom` at all.
 */

import { computeLastChartPoint } from "../../lib/eventKeyStats";
import { heroFreshness } from "../../lib/event/heroFreshness";
import type { EventHistoryResponse } from "../../lib/types";
import fs from "fs";
import path from "path";

function hist(partial: Partial<EventHistoryResponse>): EventHistoryResponse {
  return { event_id: 1, history: [], ...partial } as unknown as EventHistoryResponse;
}

const ESPN_T = "2026-09-11T02:00:00Z";
const PRICE_T = "2026-09-11T02:09:50Z";
const EVENT_T = "2026-09-11T02:01:30Z";

/** An ESPN row carrying a score — the arm that is already on production. */
function espnRow(overrides: Record<string, unknown> = {}) {
  return {
    timestamp: ESPN_T,
    home_probability: 0.6,
    away_probability: 0.4,
    home_score: 21,
    away_score: 17,
    game_clock: "4:12",
    period: "4",
    ...overrides,
  };
}

/** A price snapshot — the clock that must never be mistaken for the score's. */
const priceOnlyWinProb = {
  kalshi: [{ timestamp: PRICE_T, home_probability: 0.58 }],
} as never;

describe("#4571 the score's stamp follows its provenance", () => {
  // ---- the ESPN arm: live on production today ----

  test("a score off the ESPN row is dated by that row, not by the price snapshot", () => {
    const pt = computeLastChartPoint(
      hist({ espn_history: [espnRow()] as never, win_prob_history: priceOnlyWinProb }),
      21,
      17,
      EVENT_T,
    );
    expect(pt!.homeScore).toBe(21);
    expect(pt!.scoreFrom).toBe("history");
    expect(pt!.scoreStamp).toBe(ESPN_T);
    // Not the event row's clock either — that describes a different number.
    expect(pt!.scoreStamp).not.toBe(EVENT_T);
  });

  test("the ESPN arm does not need the backend key, so it works on production today", () => {
    // `score_observed_at` omitted entirely, which is production's state.
    const pt = computeLastChartPoint(
      hist({ espn_history: [espnRow()] as never, win_prob_history: priceOnlyWinProb }),
      null,
      null,
    );
    expect(pt!.scoreStamp).toBe(ESPN_T);
    expect(pt!.scoreFrom).toBe("history");
  });

  // ---- the event-row arm: 28 of 36 scoring events, dark until live's sha lands ----

  test("a score off the event row is dated by score_observed_at", () => {
    const pt = computeLastChartPoint(
      hist({ espn_history: [] as never, win_prob_history: priceOnlyWinProb }),
      24,
      20,
      EVENT_T,
    );
    expect(pt!.homeScore).toBe(24);
    expect(pt!.scoreFrom).toBe("event");
    expect(pt!.scoreStamp).toBe(EVENT_T);
  });

  test("an ESPN row present but holding NO score falls through, and its stamp falls with it", () => {
    // The arm test is `!= null` on the ESPN VALUE, not on the row's existence.
    // A row that carries probabilities but no score supplies no score, so its
    // timestamp must not date one.
    const pt = computeLastChartPoint(
      hist({
        espn_history: [espnRow({ home_score: null, away_score: null })] as never,
        win_prob_history: priceOnlyWinProb,
      }),
      24,
      20,
      EVENT_T,
    );
    expect(pt!.homeScore).toBe(24);
    expect(pt!.scoreFrom).toBe("event");
    expect(pt!.scoreStamp).toBe(EVENT_T);
    expect(pt!.scoreStamp).not.toBe(ESPN_T);
  });

  // ---- THE TRAP, and the near-miss: green on BOTH sides, and the point of the suite ----

  test("THE TRAP: the point's own `timestamp` is a PRICE clock and is never the answer", () => {
    // live/146, production event 15298476: no ESPN rows, so `timestamp` falls
    // through to the win-prob cascade and reports Kalshi. Binding it as the
    // score's age is #4571 reintroduced in a form that reads as correct. This
    // control is green on both sides of the change on purpose — it is a claim
    // about what the fix must NOT do, and it would be satisfied by doing nothing
    // at all, which is exactly why the arm assertions above sit beside it.
    const pt = computeLastChartPoint(
      hist({ espn_history: [] as never, win_prob_history: priceOnlyWinProb }),
      2,
      3,
      EVENT_T,
    );
    expect(pt!.timestamp).toBe(PRICE_T);
    expect(pt!.scoreStamp).not.toBe(PRICE_T);
  });

  test("THE NEAR-MISS: `lastChartPoint.homeScore == null` is NOT the event-row test", () => {
    // The first spec proposed gating on this. `computeLastChartPoint` already
    // falls back to the event row, so on the majority branch the score is
    // non-null and that gate never fires — the fix would ship inert.
    const pt = computeLastChartPoint(
      hist({ espn_history: [] as never, win_prob_history: priceOnlyWinProb }),
      24,
      20,
      EVENT_T,
    );
    expect(pt!.homeScore).not.toBeNull();
    expect(pt!.scoreFrom).toBe("event");
  });

  // ---- mixed and undatable ----

  test("a pair split across two arms is dated by its OLDER half", () => {
    // ESPN holds home, the event row holds away. The pair on screen is only as
    // current as its stalest member — heroFreshness's rule, one level down.
    const pt = computeLastChartPoint(
      hist({
        espn_history: [espnRow({ away_score: null })] as never,
        win_prob_history: priceOnlyWinProb,
      }),
      21,
      17,
      EVENT_T,
    );
    expect(pt!.scoreFrom).toBe("mixed");
    expect(new Date(ESPN_T).getTime()).toBeLessThan(new Date(EVENT_T).getTime());
    expect(pt!.scoreStamp).toBe(ESPN_T);
  });

  test("a pair with ONE undatable half is undatable, not dated by its datable half", () => {
    // Caught by mutation: replacing the `datable = false; break` with a `continue`
    // leaves every single-arm case identical (both stamps null either way) and
    // changes only this one — the pair would take ESPN's clock while the away
    // number beside it has no known age. A pair is only as current as its oldest
    // half, and a half with no age has no place in that comparison.
    const pt = computeLastChartPoint(
      hist({
        espn_history: [espnRow({ away_score: null })] as never,
        win_prob_history: priceOnlyWinProb,
      }),
      21,
      17,
      // no `score_observed_at` — production's state today
    );
    expect(pt!.homeScore).toBe(21);
    expect(pt!.awayScore).toBe(17);
    expect(pt!.scoreFrom).toBe("mixed");
    expect(pt!.scoreStamp).toBeNull();
  });

  test("a rendered score whose arm has no stamp is UNDATABLE, not price-dated", () => {
    // Production today: the event row supplies the score and `score_observed_at`
    // does not exist yet. null is the honest answer and the badge falls back to
    // ageing the price alone — the current behaviour, unchanged.
    const pt = computeLastChartPoint(
      hist({ espn_history: [] as never, win_prob_history: priceOnlyWinProb }),
      24,
      20,
      // no stamp
    );
    expect(pt!.homeScore).toBe(24);
    expect(pt!.scoreFrom).toBe("event");
    expect(pt!.scoreStamp).toBeNull();
  });

  test("an unparseable stamp dates nothing", () => {
    const pt = computeLastChartPoint(
      hist({ espn_history: [] as never, win_prob_history: priceOnlyWinProb }),
      24,
      20,
      "not a date",
    );
    expect(pt!.scoreStamp).toBeNull();
  });

  test("CONTROL: no score on either side means no age to report", () => {
    const pt = computeLastChartPoint(
      hist({ espn_history: [] as never, win_prob_history: priceOnlyWinProb }),
      null,
      null,
      EVENT_T,
    );
    expect(pt!.homeScore).toBeNull();
    expect(pt!.scoreFrom).toBeNull();
    expect(pt!.scoreStamp).toBeNull();
  });

  // ---- the arm is an ARRAY, not a writer ----

  test("the history arm is never labelled `espn`, because `espn_history` is not all ESPN", () => {
    // Green on BOTH sides (the parent emits no `scoreFrom` at all), and it is a
    // pure prohibition, which is the only kind of assertion that survives this
    // being "tidied up" later.
    //
    // live/147 measured it: `routes/events.py:15649` appends MLB Stats API and
    // `stat_model` rows into `espn_history` with no origin key, shaped like ESPN
    // rows, then sorts by timestamp — and the supplement is dense (~50–130
    // points) where ESPN is sparse (2–16). On 8 of 15 recent scoring MLB events
    // the LAST row, the one this cascade reads, is a supplement. `scoreStamp`
    // stays correct because each row carries its own timestamp; only a label
    // naming ESPN would lie. The sting is that those MLB rows are exactly the
    // arm that can be photographed, so the label would be least trustworthy
    // where it is most visible.
    const pt = computeLastChartPoint(
      hist({ espn_history: [espnRow()] as never, win_prob_history: priceOnlyWinProb }),
      21,
      17,
      EVENT_T,
    );
    expect(pt!.scoreFrom).not.toBe("espn");
    // and the stamp is still right, which is the half that IS knowable
    expect(pt!.scoreStamp).toBe(ESPN_T);
  });

  // ---- what the badge does with it ----

  test("the badge blames the SCORE when the score is the older fact", () => {
    const pt = computeLastChartPoint(
      hist({ espn_history: [espnRow()] as never, win_prob_history: priceOnlyWinProb }),
      21,
      17,
      EVENT_T,
    );
    const stamp = heroFreshness({ priceStamp: PRICE_T, scoreStamp: pt!.scoreStamp });
    expect(stamp.fact).toBe("score");
    expect(stamp.stamp).toBe(ESPN_T);
  });
});

describe("#4571 the page hands the badge the score it actually rendered", () => {
  // No render harness exists for `app/events/[id]/page.tsx` (a client page behind
  // SWR and an SSE stream), so this is a source scan in the same shape as
  // #4469's `heroFreshnessWiring.test.ts`. It reads IDENTIFIERS and strips
  // comments first: this file's docblock and the page's both name the symbols
  // below, and an unstripped scan would pass on a comment describing wiring that
  // had been reverted.
  const PAGE = path.resolve(__dirname, "../../app/events/[id]/page.tsx");

  function executableSource(file: string): string {
    return fs
      .readFileSync(file, "utf8")
      .replace(/\/\*[\s\S]*?\*\//g, " ")
      .split("\n")
      .map((line) => line.replace(/(^|\s)\/\/.*$/, "$1"))
      .join("\n");
  }

  test("the non-tennis arm of the ternary is no longer a bare null", () => {
    const code = executableSource(PAGE);
    // #4469's tennis arm is untouched and still first — its own suite pins that.
    expect(code).toMatch(
      /scoreStamp:\s*liveGamesLine\s*\?\s*event\.linescore\?\.observed_at\s*:\s*renderedScoreStamp/,
    );
    // The pre-#4571 wiring. This is the regression to catch.
    expect(code).not.toMatch(
      /scoreStamp:\s*liveGamesLine\s*\?\s*event\.linescore\?\.observed_at\s*:\s*null/,
    );
  });

  test("CONTROL: #4469's tennis arm is still first, and still the games line's clock", () => {
    // Green on BOTH sides of this change, and the one that stops this ship
    // regressing the ship before it. A games line and an integer score are
    // different renderings; `linescore.observed_at` is the clock of the one that
    // is drawn, so it keeps precedence when it is drawn.
    const code = executableSource(PAGE);
    expect(code).toMatch(/scoreStamp:\s*liveGamesLine\s*\?\s*event\.linescore\?\.observed_at/);
  });

  test("the page reads the point's score stamp and never its bare timestamp", () => {
    const code = executableSource(PAGE);
    expect(code).toMatch(/lastChartPoint\.scoreStamp/);
    // THE TRAP at the call site: `lastChartPoint.timestamp` is a price clock on
    // the majority branch and must never be spent as a score age.
    expect(code).not.toMatch(/scoreStamp:\s*lastChartPoint[?.]*\.timestamp/);
    expect(code).not.toMatch(/renderedScoreStamp\s*=\s*lastChartPoint[?.]*\.timestamp/);
  });

  test("`scoreFrom` is carried but NEVER rendered — it is not an attribution", () => {
    // Green on both sides. live/147 asked for this explicitly: the value says
    // which ARRAY the number came out of, and on 53% of scoring MLB events that
    // array's last row is not ESPN. Naming a writer needs a `source` key on the
    // supplemented rows (live's slice, not ours), and even then it would be a
    // different field — backend `score_source` describes the `"event"` arm only.
    // D102 / notice 34 also bear on adding a second grey sentence to the hero.
    const code = executableSource(PAGE);
    expect(code).not.toMatch(/scoreFrom/);
  });

  test("the event row's clock is threaded into the helper as its fourth argument", () => {
    // Caught by mutation: a bare `toMatch(/event\?\.score_observed_at/)` passes
    // with the argument DELETED, because the same identifier appears again in
    // `renderedScoreStamp`'s no-history fallback a few lines below. Provenance
    // has to be decided where the cascade is; a page that does not hand the
    // helper the event clock can only re-derive it, which is the near-miss.
    const code = executableSource(PAGE);
    expect(code).toMatch(
      /computeLastChartPoint\(\s*historyData,\s*event\?\.home_score,\s*event\?\.away_score,\s*event\?\.score_observed_at,?\s*\)/,
    );
    // And it is a dependency of the memo, or the badge freezes at the first
    // stamp the page ever saw.
    expect(code).toMatch(/\[[^\]]*event\?\.score_observed_at[^\]]*\]/);
  });
});
