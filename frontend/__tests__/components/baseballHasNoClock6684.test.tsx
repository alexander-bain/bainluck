/**
 * #6684 — EVERY LIVE MLB GAME PAGE PAINTED A "0:00" GAME CLOCK, AND BASEBALL
 * HAS NO CLOCK.
 *
 * ═══ THE SPECIMEN ═══
 *
 * `https://bainluck.com/events/15313145` (Padres @ Rockies), 390px,
 * 2026-09-17 03:25Z. Under the win-probability chart, the game-state badge:
 *
 *     Bottom 8th 0:00      CR 3 - 9 SD      Rockies 0% — Padres 100%
 *
 * "0:00" beside a half-inning reads as an expired timer on a game that is still
 * being played — the most natural reading is "this is over", directly above a
 * live chart. Re-confirmed on `/events/15313147` (Mariners @ Angels, live,
 * `Bottom 7th` / `0:00`) while building.
 *
 * ═══ IT IS EVERY MLB ROW, AND FOOTBALL IS THE TRAP ═══
 *
 * Production, `events.game_clock` over 14 days:
 *
 *   | sport                  | rows | DISTINCT | == "0:00" |
 *   |------------------------|------|----------|-----------|
 *   | baseball_mlb           |  187 |      1   | 187 (100%)|
 *   | americanfootball_ncaaf |   81 |      1   |  81 (100%)|
 *   | americanfootball_nfl   |   16 |      1   |  16 (100%)|
 *   | soccer_usa_mls         |   43 |     13   |   0  (0%) |
 *   | soccer_spain_la_liga   |   28 |     10   |   0  (0%) |
 *
 * 🔴 READ THAT TABLE WRONG AND YOU DECLARE FOOTBALL CLOCKLESS. The football
 * rows are 100% `0:00` too — because they are FINISHED games, where the clock
 * really did run out. The distinguishing fact is the DISTINCT count on the LIVE
 * series, not the share of zeros: the ESPN snapshot series carries 90 distinct
 * NFL clock values against exactly 1 for MLB (292 of 292 rows the placeholder,
 * across 38 events). `gameHasAClock` is declared `true` for football
 * deliberately, and the test below pins that so nobody "fixes" it later.
 *
 * ═══ WHY THE RULE IS IN `trustedLiveClock` AND KEYED ON A DECLARATION ═══
 *
 * That function is already the named authority for *which of ESPN's clock
 * fields a card may paint*, and it holds three measured rules. None can reach
 * this one, because all three are about the two STRINGS: `"Bottom 8th"` is not
 * pregame, `"0:00"` is not a substring of it, and `"0:00"` does not equal it.
 * The fourth rule is about the SPORT.
 *
 * So the fact is DECLARED in `sportVocab` and the key is passed down. A
 * `sportKey.startsWith("baseball")` at the call site — or inside the helper —
 * would be the same defect one layer down: the spelling of a key is not a claim
 * about a sport.
 *
 * ═══ THE GUARD THAT MATTERS IS THE WIRING ONE ═══
 *
 * `sportKey` is OPTIONAL, deliberately (an absent key must leave all four
 * existing callers behaviourally identical). That means **TypeScript cannot
 * tell me if the page stops passing it** — the helper would be perfectly
 * correct and the reader would still read `0:00`. The source scans below are
 * the only thing standing between "the rule exists" and "the rule runs", and
 * each carries an anti-vacuous control that fires on the pre-fix text.
 */
import React from "react";
import { readFileSync } from "fs";
import { join } from "path";
import { renderToStaticMarkup } from "react-dom/server";
import GamePlayCard from "@/components/GamePlayCard";
import { trustedLiveClock, formatLiveClockLabel } from "@/lib/gameTimeLabel";
import { sportVocab, UNSCORED_IN_POINTS } from "@/lib/marketMapUtils";
import type { ActiveChartPoint } from "@/lib/types";

const FRONTEND = join(__dirname, "..", "..");
const read = (rel: string) => readFileSync(join(FRONTEND, rel), "utf8");

/** `/events/15313147`, live, read from the database while building. */
const MLB_LIVE: ActiveChartPoint = {
  timestamp: "2026-09-17T04:12:00+00:00",
  homeProb: 0.04,
  awayProb: 0.96,
  homeScore: 2,
  awayScore: 7,
  period: "Bottom 7th",
  clock: "0:00",
};

/** The control: a sport whose clock is a real clock. */
const NFL_LIVE: ActiveChartPoint = {
  timestamp: "2026-09-14T20:41:00+00:00",
  homeProb: 0.62,
  awayProb: 0.38,
  homeScore: 17,
  awayScore: 13,
  period: "3rd Quarter",
  clock: "4:22",
};

/**
 * The readout's visible text.
 *
 * 🔴 NOT `replace(/<[^>]+>/g, "")` — that is the shape of an HTML sanitizer and
 * CodeQL refuses it as a high-severity `js/incomplete-multi-character-
 * sanitization`. It has already refused two shas in this repo
 * (`chartReadoutWithholdsTheDraw6238`, `compactRowNamesItsAnswer4396`). The
 * index walk is the same reading with nothing sanitizer-shaped in it.
 */
function visibleText(fragment: string): string {
  let out = "";
  let i = 0;
  for (;;) {
    const open = fragment.indexOf("<", i);
    out += open < 0 ? fragment.slice(i) : fragment.slice(i, open);
    if (open < 0) break;
    const close = fragment.indexOf(">", open);
    if (close < 0) break;
    i = close + 1;
  }
  return out.split(/\s+/).filter(Boolean).join(" ");
}

const renderCard = (point: ActiveChartPoint, sportKey?: string) =>
  visibleText(
    renderToStaticMarkup(
      React.createElement(GamePlayCard, {
        activePoint: point,
        homeTeam: "Los Angeles Angels",
        awayTeam: "Seattle Mariners",
        sportKey,
      }),
    ),
  );

describe("#6684 — a sport with no clock never paints one", () => {
  test("THE DEFECT: baseball withholds the placeholder clock", () => {
    expect(trustedLiveClock("Bottom 8th", "0:00", "baseball_mlb")).toEqual({
      period: "Bottom 8th",
      gameClock: "",
    });
  });

  /**
   * THE LOAD-BEARING HALF. Every assertion about "0:00 is gone" is ALSO
   * satisfied by returning `{period: "", gameClock: ""}` and blanking the whole
   * badge — and "gone" is a worse answer than "wrong here". `Bottom 8th` is the
   * real and useful half; the reader loses the inning to lose the fake timer.
   * Without this line the mutant that blanks both fields passes every other
   * test in this file.
   */
  test("the PERIOD survives — the badge is narrowed, not deleted", () => {
    expect(trustedLiveClock("Bottom 8th", "0:00", "baseball_mlb").period).toBe("Bottom 8th");
    expect(renderCard(MLB_LIVE, "baseball_mlb")).toContain("Bottom 7th");
  });

  /**
   * The tempting narrow fix is `clock === "0:00"`, and it is the wrong rule: it
   * would let any other placeholder ESPN invents through, and it says nothing
   * about the sport. Baseball withholds a clock-SHAPED string too.
   */
  test("it is the SPORT, not the string — baseball withholds a plausible clock too", () => {
    expect(trustedLiveClock("Bottom 8th", "7:21", "baseball_mlb").gameClock).toBe("");
    expect(trustedLiveClock("Top 3rd", "0.0", "baseball_mlb").gameClock).toBe("");
  });

  test("a sport WITH a clock is untouched (gotcha #43 — both directions)", () => {
    expect(trustedLiveClock("3rd Quarter", "4:22", "americanfootball_nfl")).toEqual({
      period: "3rd Quarter",
      gameClock: "4:22",
    });
    expect(trustedLiveClock("65'", "65:12", "soccer_epl").gameClock).toBe("65:12");
    expect(trustedLiveClock("Q4", "1:09", "basketball_nba").gameClock).toBe("1:09");
    expect(renderCard(NFL_LIVE, "americanfootball_nfl")).toContain("4:22");
  });

  /**
   * The compatibility contract. `sportKey` is optional so the other callers
   * keep today's behaviour EXACTLY — and this is also the control that proves
   * the render assertions above are not vacuous: the same card, same point,
   * without the key, still prints the defect.
   */
  test("an ABSENT key changes nothing — and that is how we know the test bites", () => {
    expect(trustedLiveClock("Bottom 8th", "0:00")).toEqual({
      period: "Bottom 8th",
      gameClock: "0:00",
    });
    expect(renderCard(MLB_LIVE)).toContain("0:00");
    expect(renderCard(MLB_LIVE, "baseball_mlb")).not.toContain("0:00");
  });

  test("an UNDECLARED sport keeps its clock — the default may not delete a real field", () => {
    expect(trustedLiveClock("Innings 12", "3:30", "cricket_international_t20").gameClock).toBe("3:30");
    expect(UNSCORED_IN_POINTS.gameHasAClock).toBe(true);
  });

  test("the first three rules still run for a clockless sport", () => {
    // Rule 1 outranks it: a pregame period takes the whole badge down, and the
    // period must NOT come back just because the sport is baseball.
    expect(
      trustedLiveClock("Mon, August 10th at 8:00 PM EDT", "0:00", "baseball_mlb"),
    ).toEqual({ period: "", gameClock: "" });
  });

  test("formatLiveClockLabel forwards the key — the param is not decorative", () => {
    expect(formatLiveClockLabel("Bottom 8th", "0:00", " ", "baseball_mlb")).toBe("Bottom 8th");
    expect(formatLiveClockLabel("Bottom 8th", "0:00", " · ")).toBe("Bottom 8th · 0:00");
  });
});

describe("#6684 — the declaration lives in the vocab table", () => {
  test("baseball is the one declared NO, and its prefix siblings inherit it", () => {
    expect(sportVocab("baseball_mlb").gameHasAClock).toBe(false);
    // The point of declaring on the prefix rather than the full key: a league
    // we have not enumerated is still baseball.
    expect(sportVocab("baseball_kbo").gameHasAClock).toBe(false);
    expect(sportVocab("baseball_npb").gameHasAClock).toBe(false);
  });

  /**
   * 🔴 THE TRAP, PINNED. Football reads 100% `0:00` in `events.game_clock` and
   * it has a real clock — those rows are finished games. Anyone widening this
   * rule off that table alone would blank the clock from every live NFL game.
   */
  test("football is declared TRUE despite its 100% 0:00 population", () => {
    expect(sportVocab("americanfootball_nfl").gameHasAClock).toBe(true);
    expect(sportVocab("americanfootball_ncaaf").gameHasAClock).toBe(true);
  });

  test("the clocked sports are declared TRUE", () => {
    for (const key of ["soccer_epl", "basketball_nba", "icehockey_nhl", "hockey_nhl"]) {
      expect(sportVocab(key).gameHasAClock).toBe(true);
    }
  });

  /**
   * Tennis is declared `false` because it is TRUE, not because anything
   * changes: tennis never sends the field (measured — 0 of 34 live tennis
   * events carry a `game_clock`, 0 rows in 14 days), and an empty clock is
   * already withheld by the trimming above. Declaring it `true` would have
   * written a falsehood into the table a later reader would trust.
   */
  test("tennis is declared honestly, and it is inert", () => {
    expect(sportVocab("tennis_atp").gameHasAClock).toBe(false);
    expect(trustedLiveClock("Set 2", null, "tennis_atp")).toEqual({ period: "Set 2", gameClock: "" });
    expect(trustedLiveClock("Set 2", null)).toEqual({ period: "Set 2", gameClock: "" });
  });
});

/**
 * THE WIRING. `sportKey` is optional, so none of this is type-checked: the
 * helper can be perfectly correct while the page quietly stops passing the key
 * and the reader keeps reading `0:00`.
 */
describe("#6684 — the rule is actually REACHED by the reader's surface", () => {
  /**
   * The JSX element, sliced to its closing `/>`.
   *
   * 🪤 The slice's LENGTH is asserted first, and that is not decoration. A
   * slice that stops early returns a SHORTER string, and every `toMatch` on a
   * short string fails while every `not.toMatch` passes — a bad slice is
   * indistinguishable from a clean result. Three lines of arrange buy the
   * difference between a guard and an ornament.
   */
  function gamePlayCardElement(): string {
    const src = read("app/events/[id]/page.tsx");
    const open = src.indexOf("<GamePlayCard");
    expect(open).toBeGreaterThan(-1);
    const close = src.indexOf("/>", open);
    expect(close).toBeGreaterThan(open);
    const slice = src.slice(open, close + 2);
    // The real element carries eight props and two comment blocks; anything
    // under 400 chars means the slice stopped early and the scan is blind.
    expect(slice.length).toBeGreaterThan(400);
    // And it is ONE element — a second opening tag inside means we ran past it.
    expect(slice.indexOf("<GamePlayCard", 1)).toBe(-1);
    return slice;
  }

  /**
   * 🪤 `\b` IS LOAD-BEARING AND WAS ADDED AFTER A SURVIVING MUTANT. The first
   * version of this assertion read `/sportKey=\{event\.sport/`, and the mutant
   * that renames the prop to `xsportKey=` PASSED it — the pattern matches
   * happily inside the longer identifier. Fifteen green tests, the wire cut,
   * and the reader back on `0:00`. The word boundary is what makes the scan a
   * guard; without it the prop could be renamed to anything with a prefix.
   */
  test("the event page hands GamePlayCard the sport key", () => {
    expect(gamePlayCardElement()).toMatch(/\bsportKey=\{event\.sport/);
  });

  test("GamePlayCard hands it to the authority, and derives nothing itself", () => {
    const src = read("components/GamePlayCard.tsx");
    expect(src).toMatch(/trustedLiveClock\(\s*formatPeriod\(point\.period\),\s*point\.clock,\s*sportKey\s*\)/);
    // No private copy of the rule. A comment naming the sport is fine; code is not.
    const offenders = src
      .split("\n")
      .map((line, n) => ({ line, n: n + 1 }))
      .filter(({ line }) => !/^\s*(?:\/\/|\*|\/\*)/.test(line))
      .filter(({ line }) => /"baseball|'baseball|0:00/.test(line));
    expect(offenders.map((o) => `GamePlayCard.tsx:${o.n}`)).toEqual([]);
  });

  /**
   * Both scans read real files, so a renamed prop or a moved element would make
   * them pass over nothing at all — the vacuous-guard trap. These assert the
   * matchers fire on the pre-fix text and refuse the post-fix text, so neither
   * can silently become an ornament.
   */
  test("the wiring matchers fire on the pre-fix shapes", () => {
    const preFixElement = `<GamePlayCard
              activePoint={activeChartPoint}
              homeTeam={event.home_team}
              awayTeam={event.away_team}
              lastPoint={lastChartPoint}
              awayWithheld={awaySlotWithheld}
            />`;
    expect(preFixElement).not.toMatch(/\bsportKey=\{event\.sport/);
    expect(preFixElement.length).toBeGreaterThan(200);
    // The renamed-prop mutant that survived the first cut of this file.
    expect(`${preFixElement}\n  xsportKey={event.sport || undefined}`).not.toMatch(
      /\bsportKey=\{event\.sport/,
    );

    const preFixCall = "  const trusted = trustedLiveClock(formatPeriod(point.period), point.clock);";
    expect(preFixCall).not.toMatch(
      /trustedLiveClock\(\s*formatPeriod\(point\.period\),\s*point\.clock,\s*sportKey\s*\)/,
    );

    const privateCopy = '  if (sportKey.startsWith("baseball")) clock = "";';
    expect(/"baseball|'baseball|0:00/.test(privateCopy)).toBe(true);
  });
});
