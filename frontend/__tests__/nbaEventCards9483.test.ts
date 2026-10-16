/**
 * #9483 NBA slice — the ladder cards read from the served question matrix
 * (design freeze v328, NBA-MAPPING.md / ACCEPTANCE.md journeys 10–12), on two
 * real bodies trimmed into fixtures:
 *
 *   - `nbaFinalMatrix15320337.json`: Clippers 104–101 Warriors, final. Every
 *     option is a settled result with comparison `not_quoted` and no pin.
 *   - `nbaPregameMatrix15327183.json`: Raptors @ Knicks before tip-off, every
 *     option `quoted` at 18:2xZ with `no_pregame_pin`.
 *
 * Both bodies predate the producer's `pregame_reading` field (PR #11125), so the
 * final cards keep their shape and confirmed results and say the pregame chance
 * is unavailable — the old-server fallback. They never read the terminal 0/100
 * as a chance and never rebuild 82.5% from movement. The field's own cases are
 * in `nbaPregameReading9483.test.ts`. Fixed clocks only (gotcha #44).
 */

import finalBody from "./fixtures/nbaFinalMatrix15320337.json";
import pregameBody from "./fixtures/nbaPregameMatrix15327183.json";
import {
  decodeQuestionMatrix,
  defaultLadderIndex,
  ladderCaption,
  marginLadderCard,
  marginWords,
  totalLadderCard,
  type LadderInputs,
} from "@/lib/nbaEventCards";
import { buildFinishCard, cardAt, nbaEventCards, type FinishCard } from "@/lib/nflEventCardDeck";

const FINAL_NOW = Date.parse("2026-10-05T04:00:00Z");
const PREGAME_NOW = Date.parse("2026-10-15T18:40:00Z");

function finalInputs(over: Partial<LadderInputs> = {}): LadderInputs {
  return {
    questions: decodeQuestionMatrix(finalBody.game_question_matrix),
    status: "completed",
    commenceTime: "2026-10-04T23:00:00Z",
    homeScore: finalBody.home_score,
    awayScore: finalBody.away_score,
    pregameProjection: null,
    homeShort: "Clippers",
    awayShort: "Warriors",
    nowMs: FINAL_NOW,
    ...over,
  };
}

function pregameInputs(over: Partial<LadderInputs> = {}): LadderInputs {
  return {
    questions: decodeQuestionMatrix(pregameBody.game_question_matrix),
    status: "scheduled",
    commenceTime: "2026-10-15T23:30:00Z",
    homeScore: null,
    awayScore: null,
    pregameProjection: null,
    homeShort: "Knicks",
    awayShort: "Raptors",
    nowMs: PREGAME_NOW,
    ...over,
  };
}

describe("#9483 NBA — the matrix decoder", () => {
  it("reads only contract 10238.v1", () => {
    expect(decodeQuestionMatrix(finalBody.game_question_matrix).length).toBeGreaterThan(20);
    expect(decodeQuestionMatrix({ ...finalBody.game_question_matrix, contract: "10238.v2" })).toEqual([]);
    expect(decodeQuestionMatrix(null)).toEqual([]);
    expect(decodeQuestionMatrix({ contract: "10238.v1", questions: "nope" })).toEqual([]);
  });

  it("admits a baseline only for a comparable, dated pregame pin", () => {
    const q = (comparison: unknown) =>
      decodeQuestionMatrix({
        contract: "10238.v1",
        questions: [{ question_key: "q", kind: "count_threshold", options: [{ option_key: "o", published: {}, comparison }] }],
      })[0].options[0].baseline;
    expect(q({ state: "comparable", baseline: { probability: 0.6, observed_at: "2026-10-15T23:29:00Z", basis: "pregame_pin" } })).toBe(0.6);
    expect(q({ state: "unavailable", baseline: { probability: 0.6, observed_at: "x", basis: "pregame_pin" } })).toBeNull();
    expect(q({ state: "comparable", baseline: { probability: 0.6, observed_at: "x", basis: "opening" } })).toBeNull();
    expect(q({ state: "comparable", baseline: { probability: 0.6, basis: "pregame_pin" } })).toBeNull();
    expect(q({ state: "comparable", baseline: { probability: 1.2, observed_at: "x", basis: "pregame_pin" } })).toBeNull();
  });
});

describe("#9483 NBA journey 10 — the exact final total (15320337)", () => {
  const card = totalLadderCard(finalInputs())!;

  it("the actual is the final score's sum: 205", () => {
    expect(card.phase).toBe("after");
    expect(card.actual).toBe(205);
  });

  it("Over 206.5 (outcome 240505185) is LOST; Over 204.5 is WON — the producer's verdicts", () => {
    const over2065 = card.points.find((p) => p.x === 206.5)!;
    expect(over2065.optionKey).toBe("o:240505185");
    expect(over2065.result).toBe(false);
    expect(card.points.find((p) => p.x === 204.5)!.result).toBe(true);
  });

  it("with nothing drawn, the card opens on the line nearest the actual 205", () => {
    expect(card.points[defaultLadderIndex(card)!].x).toBe(204.5);
  });

  it("no pregame chance is drawn: this body predates pregame_reading, and 0/100 is never a chance", () => {
    expect(card.points.every((p) => p.chance === null && p.now === null)).toBe(true);
    expect(ladderCaption(card)).toBe("Pregame chance unavailable for these lines");
    expect(card.points.find((p) => p.x === 206.5)!.detail.baseline).toBeNull();
  });

  it("a comparison pin on a settled option is NOT drawn: a final reads only the producer's pregame_reading", () => {
    const pinned = JSON.parse(JSON.stringify(finalBody.game_question_matrix));
    for (const q of pinned.questions) {
      for (const o of q.options) {
        if (o.option_key === "o:240505185") {
          o.comparison = {
            state: "comparable",
            reason: null,
            baseline: { probability: 0.825, observed_at: "2026-10-04T22:58:37.402964Z", basis: "pregame_pin" },
          };
        }
      }
    }
    const withPin = totalLadderCard(finalInputs({ questions: decodeQuestionMatrix(pinned) }))!;
    expect(withPin.points.every((p) => p.chance === null)).toBe(true);
    expect(ladderCaption(withPin)).toBe("Pregame chance unavailable for these lines");
  });
});

describe("#9483 NBA journey 11 — the signed margin", () => {
  const card = marginLadderCard(finalInputs({ pregameProjection: { home: 109.8, away: 112.5 } }))!;

  it("Clippers by 3 actual against a Warriors-by-2.7 projection", () => {
    expect(card.actual).toBe(3);
    expect(marginWords(card, card.actual!)).toBe("Clippers by 3");
    expect(card.forecast).toBe(-2.7);
    expect(marginWords(card, card.forecast!)).toBe("Warriors by 2.7");
  });

  it("each team's lines sit on their own side, never complemented", () => {
    const home = card.points.filter((p) => p.side === "home");
    const away = card.points.filter((p) => p.side === "away");
    expect(home.length).toBeGreaterThan(0);
    expect(away.length).toBeGreaterThan(0);
    expect(home.every((p) => p.x > 0)).toBe(true);
    expect(away.every((p) => p.x < 0)).toBe(true);
    // "Golden State wins by over 1.5 points" is Warriors by 2+, at −1.5.
    const gsw15 = card.points.find((p) => p.optionKey === "o:240505114")!;
    expect(gsw15).toMatchObject({ x: -1.5, label: "Warriors by 2+", side: "away", result: false });
  });

  it("an option on the other side of its question is refused, not borrowed", () => {
    const flipped = JSON.parse(JSON.stringify(finalBody.game_question_matrix));
    for (const q of flipped.questions) if (q.kind === "signed_handicap") for (const o of q.options) o.side = o.side === "home" ? "away" : "home";
    expect(marginLadderCard(finalInputs({ questions: decodeQuestionMatrix(flipped) }))).toBeNull();
  });

  it("first-half lines never enter the full-game ladder", () => {
    const halves = JSON.parse(JSON.stringify(finalBody.game_question_matrix));
    for (const q of halves.questions) q.period = { key: "half_1", label: "1st half" };
    expect(marginLadderCard(finalInputs({ questions: decodeQuestionMatrix(halves) }))).toBeNull();
    expect(totalLadderCard(finalInputs({ questions: decodeQuestionMatrix(halves) }))).toBeNull();
  });
});

describe("#9483 NBA — before tip-off (15327183)", () => {
  const total = totalLadderCard(pregameInputs())!;
  const margin = marginLadderCard(pregameInputs())!;

  it("the dots are the current quotes, named as the pregame chance; no actual, no grade", () => {
    expect(total.phase).toBe("before");
    // A quote counts only while its own clock is under 30 minutes old at 18:40Z. The quiet
    // lines last stamped at 17:01Z are real prices and still lose their dots: unknown age
    // is not current (the NFL and phone rule).
    for (const p of total.points) {
      const recent = Date.parse(p.detail.observedAt!) >= PREGAME_NOW - 30 * 60_000;
      expect(p.chance).toBe(recent ? p.detail.quoted : null);
    }
    expect(total.points.some((p) => p.chance !== null)).toBe(true);
    expect(total.points.some((p) => p.chance === null)).toBe(true);
    expect(total.points.every((p) => p.result === null)).toBe(true);
    expect(total.actual).toBeNull();
    expect(ladderCaption(total)).toBe("Pregame chance of finishing above each line");
    expect(margin.points.find((p) => p.label === "Knicks by 6+")!.detail.quoted).toBe(0.5);
  });

  it("a quote whose clock passes 30 minutes loses its dot (journey 6)", () => {
    const aged = cardAt(total, Date.parse("2026-10-15T19:30:00Z"));
    expect(aged.kind === "ladder" && aged.points.every((p) => p.chance === null)).toBe(true);
  });

  it("at tip-off the dots switch to the admitted pin; with none served, they are empty — never the live quote", () => {
    const live = totalLadderCard(pregameInputs({ status: "live", homeScore: 20, awayScore: 18, nowMs: Date.parse("2026-10-15T23:40:00Z") }))!;
    expect(live.phase).toBe("during");
    expect(live.points.every((p) => p.chance === null)).toBe(true);
    expect(live.actual).toBe(38);
  });

  it("opens on the drawn line nearest even odds", () => {
    const i = defaultLadderIndex(margin)!;
    const drawn = margin.points.filter((p) => p.chance !== null);
    const best = Math.min(...drawn.map((p) => Math.abs(p.chance! - 0.5)));
    expect(Math.abs(margin.points[i].chance! - 0.5)).toBe(best);
  });

  it("the deck order is margin, totals, then the projected finish", () => {
    const finish: FinishCard = { kind: "finish", id: "finish", phase: "before", pregame: { away: 110, home: 114, at: 1 }, projectedNow: null, final: null };
    expect(nbaEventCards("basketball_nba", finish, { margin, total }).map((c) => c.id)).toEqual(["margin", "total", "finish"]);
    expect(nbaEventCards("americanfootball_nfl", finish, { margin, total })).toEqual([]);
  });

  it("the projected finish is admitted for NBA too", () => {
    const card = buildFinishCard({
      sportKey: "basketball_nba",
      sourceKey: "draftkings",
      basis: "same_book_same_capture_full_game_spread_and_total",
      pairs: [{ timestamp: "2026-10-15T18:00:00Z", home: 114, away: 110, kind: "recorded" }],
      actuals: [],
      kickoffAt: null,
      finalAt: null,
      asOf: "2026-10-15T18:10:00Z",
    });
    expect(card).toMatchObject({ phase: "before", pregame: { home: 114, away: 110 } });
  });
});
