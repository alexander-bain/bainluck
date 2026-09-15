/**
 * #6349 — A CHART WINDOW MAY NOT END BEFORE IT STARTS, AND THE SCORE IS EVIDENCE
 * OF WHEN THE GAME WAS PLAYED.
 *
 * The reader's report: `/events/15296797` (Banfield 1-1 Barracas Central, FINAL)
 * drew a Win Probability panel with axes, a `+ 3 sources` control and no line,
 * above a "Score Differential" heading with nothing under it at all.
 *
 * It was read as a no-data page. It is not. Measured off production on
 * 2026-09-15, the payload holds 1,907 betting points, 2,741 aggregate points,
 * 638 Polymarket, 497 Kalshi and six sportsbook series. What it does NOT hold is
 * a single point after kickoff on any of them: the books closed at 02:08Z and
 * the match began at 22:00Z, 19h52m later. The only series inside the match is
 * `score_history` — 22:03Z 0-0, 22:49Z 1-0, 23:26Z 1-1.
 *
 * That combination drove two helpers into disagreement:
 *
 *  - `maxPostStartSeriesPoints` COUNTS `score_history`, so the page chose
 *    "Since Start" and pinned both charts to it. (OddsChart's own
 *    `hasPostStartData` does not count it, so the page rendered with the "Since
 *    Start" pill DISABLED and selected — read from the live DOM.)
 *  - `computeSharedChartDomain`'s completed-game end ladder DID NOT. With ESPN
 *    empty and Kalshi/Polymarket deliberately excluded from `GAME_END_SOURCES`,
 *    it fell through to the sportsbook tail and produced `end` = 02:08Z against
 *    a `start` of 22:00Z.
 *
 * An inverted window makes `fillMinuteGaps` no-op, which is how both panels came
 * out blank. The pre-existing FLOOR guards `end < allStart` — the first point of
 * the whole event, 15 days earlier — so it passed and could never have caught
 * this.
 *
 * Every test below pairs with a control, because a window rule that fixes this
 * page by widening every page is not a fix.
 */

import {
  computeSharedChartDomain,
  defaultChartTimeRange,
} from "@/lib/eventKeyStats";

// Fixed anchor — offset first, then use. Never `Date.now()` (gotcha #44).
const KICKOFF_MS = Date.UTC(2026, 8, 14, 22, 0, 0);
const MIN = 60 * 1000;
const at = (offsetMin: number, seconds = 0) =>
  new Date(KICKOFF_MS + offsetMin * MIN + seconds * 1000).toISOString();

const ms = (iso: string) => new Date(iso).getTime();

/** The specimen's shape: every odds series dead ~20h before kickoff. */
const PREGAME_ODDS = [
  { timestamp: at(-1200), home_probability: 0.63, away_probability: 0.37 },
  { timestamp: at(-1199), home_probability: 0.64, away_probability: 0.36 },
  { timestamp: at(-1192), home_probability: 0.62, away_probability: 0.38 },
];

/** The only series inside the match. The last row carries SECONDS on purpose —
 *  it is the row the end is derived from, and a window that truncates to the
 *  minute excludes the very observation that defined it. */
const IN_GAME_SCORES = [
  { timestamp: at(3, 53), home_score: 0, away_score: 0 },
  { timestamp: at(49, 53), home_score: 1, away_score: 0 },
  { timestamp: at(86, 54), home_score: 1, away_score: 1 },
];

// eslint-disable-next-line @typescript-eslint/no-explicit-any
const payload = (over: Record<string, unknown>): any => ({
  event_id: 1,
  commence_time: new Date(KICKOFF_MS).toISOString(),
  history: PREGAME_ODDS,
  score_history: [],
  espn_history: [],
  win_prob_history: {},
  bookmaker_history: {},
  ...over,
});

const COMMENCE = new Date(KICKOFF_MS).toISOString();
const domain = (
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  data: any,
  range: "all" | "live",
  status = "completed",
) => computeSharedChartDomain(data, range, status, COMMENCE, "soccer_argentina_primera_division");

describe("#6349 the window may not end before it starts", () => {
  test("THE DEFECT — a completed game whose odds all predate kickoff gets a window it can draw", () => {
    const data = payload({ score_history: IN_GAME_SCORES });

    // The page pins "Since Start" on the strength of the score series — this is
    // the input that made the bug reachable, so the test states it rather than
    // assuming it.
    expect(defaultChartTimeRange(data, COMMENCE)).toBe("live");

    const d = domain(data, "live")!;
    expect(ms(d.end)).toBeGreaterThan(ms(d.start));
    // Before the fix `end` was the last sportsbook tick, ~20h BEFORE the start.
    expect(ms(d.end)).toBeGreaterThan(KICKOFF_MS);
  });

  test("the window reaches the LAST score observation, not the minute before it", () => {
    // 23:26:54 is the equaliser. A window snapped down to 23:26:00 excludes it
    // and a 1-1 match draws a score line that ends 1-0.
    const d = domain(payload({ score_history: IN_GAME_SCORES }), "live")!;
    const equaliser = ms(IN_GAME_SCORES[2].timestamp);
    expect(ms(d.end)).toBeGreaterThanOrEqual(equaliser);
    // ...and does not overshoot into a trailing buffer (L2-131): at most the
    // partial minute it had to round up through.
    expect(ms(d.end) - equaliser).toBeLessThan(MIN);
  });

  test("all three score rows land inside the window the chart is given", () => {
    const d = domain(payload({ score_history: IN_GAME_SCORES }), "live")!;
    const inside = IN_GAME_SCORES.filter(
      (p) => ms(p.timestamp) >= ms(d.start) && ms(p.timestamp) <= ms(d.end),
    );
    expect(inside).toHaveLength(3);
  });

  test("BACKSTOP — no score rows, and the only post-kickoff series is one the end ladder excludes", () => {
    // Kalshi and Polymarket are kept out of GAME_END_SOURCES on purpose: they
    // keep quoting past the final whistle. So this arm reaches neither the ESPN
    // branch nor the new score branch, `end` still comes off the sportsbook
    // tail, and the window still inverts. The end-before-start floor is what
    // catches it.
    const data = payload({
      win_prob_history: {
        kalshi: [
          { timestamp: at(10), probability: 0.6 },
          { timestamp: at(80), probability: 0.7 },
        ],
      },
    });
    expect(defaultChartTimeRange(data, COMMENCE)).toBe("live");

    const d = domain(data, "live")!;
    expect(ms(d.end)).toBeGreaterThan(ms(d.start));
  });

  test("a window that ends EXACTLY where it starts is as blank as an inverted one", () => {
    // The `<=` in the floor, not `<`. A mutation pass caught this: flipping it
    // to `<` left every other test green, and a zero-width window draws exactly
    // as much as a backwards one — nothing.
    //
    // The shape is not contrived. The only game-end evidence is a single score
    // snapshot taken at kickoff (the 0-0 every livescore feed opens with), while
    // Kalshi — excluded from GAME_END_SOURCES because it quotes past the final
    // whistle — carries the two post-start points that make the page choose
    // "Since Start". End lands on commence; so does start.
    const data = payload({
      score_history: [{ timestamp: at(0), home_score: 0, away_score: 0 }],
      win_prob_history: {
        kalshi: [
          { timestamp: at(10), probability: 0.6 },
          { timestamp: at(80), probability: 0.7 },
        ],
      },
    });
    expect(defaultChartTimeRange(data, COMMENCE)).toBe("live");

    const d = domain(data, "live")!;
    expect(ms(d.end)).toBeGreaterThan(ms(d.start));
  });

  test("CONTROL — a completed game with real in-game data keeps its game-duration window", () => {
    // The fix must not widen a page that was already right. ESPN runs through
    // the match, so the end ladder's first branch answers and the window is the
    // game — exactly what Alex's 2026-09-14 chart-timing direction asks for.
    const data = payload({
      history: [
        ...PREGAME_ODDS,
        { timestamp: at(5), home_probability: 0.6, away_probability: 0.4 },
        { timestamp: at(85), home_probability: 0.8, away_probability: 0.2 },
      ],
      espn_history: [
        { timestamp: at(5), home_win_probability: 0.6 },
        { timestamp: at(90), home_win_probability: 0.85 },
      ],
      score_history: IN_GAME_SCORES,
    });
    const d = domain(data, "live")!;
    expect(d.start).toBe(new Date(KICKOFF_MS).toISOString());
    // Ends at ESPN's last row (90m), NOT stretched to some later series.
    expect(ms(d.end)).toBe(KICKOFF_MS + 90 * MIN);
  });

  test("CONTROL — a scheduled game is untouched by any of this", () => {
    // None of the completed-game ladder runs; the window is the data's own
    // extent and the pregame odds drift IS the story.
    const data = payload({});
    const d = domain(data, "all", "scheduled")!;
    expect(ms(d.start)).toBe(ms(PREGAME_ODDS[0].timestamp));
    expect(ms(d.end)).toBe(ms(PREGAME_ODDS[2].timestamp));
  });

  test("CONTROL — the fallback is the honest full extent, not an arbitrary pad", () => {
    // When the floor fires it must land on data the chart actually holds. A
    // window wider than the event's own points would trade a blank chart for a
    // mostly-empty one.
    const data = payload({
      win_prob_history: {
        polymarket: [
          { timestamp: at(10), probability: 0.6 },
          { timestamp: at(80), probability: 0.7 },
        ],
      },
    });
    const d = domain(data, "live")!;
    expect(ms(d.start)).toBe(ms(PREGAME_ODDS[0].timestamp));
    expect(ms(d.end)).toBeGreaterThanOrEqual(ms(at(80)));
    expect(ms(d.end) - ms(at(80))).toBeLessThan(MIN);
  });
});
