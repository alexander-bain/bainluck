/**
 * #1930 — a category label renders as "Mma". It should be "MMA".
 *
 * Current reproducing path on /daily (frontend/app/daily/page.tsx):
 * a futures question with no served `sport_name` carries the raw
 * `llm_sport_category` slug (`category: data.sport_name ||
 * data.llm_sport_category || "Markets"`), and `categoryLabel`
 * (components/daily/TodaysSetCard.tsx) title-cases that slug with an
 * acronym-blind per-word capitalizer — so the pill the reader meets
 * (`{categoryLabel(question)}`, no CSS `uppercase` rescue) reads "Mma",
 * and the answers list below renders the raw slug untouched ("mma").
 *
 * The fix routes the label through the shared acronym-aware caser
 * (`lib/titleCase.ts`), so this guards the call the reader actually meets
 * rather than the caser in isolation: the slug, the row mapping the page
 * calls, and the issue's neighbour acronyms.
 */

import { categoryLabel, toTodaysSetRows } from "../components/daily/TodaysSetCard";

describe("#1930 category acronyms on /daily", () => {
  it("renders 'mma' as 'MMA', not 'Mma'", () => {
    expect(categoryLabel({ category: "mma" })).toBe("MMA");
  });

  it("renders the issue's neighbour acronyms in their own casing", () => {
    expect(categoryLabel({ category: "mlb" })).toBe("MLB");
    expect(categoryLabel({ category: "nba" })).toBe("NBA");
    expect(categoryLabel({ category: "nfl" })).toBe("NFL");
    expect(categoryLabel({ category: "nhl" })).toBe("NHL");
    expect(categoryLabel({ category: "ncaa" })).toBe("NCAA");
    expect(categoryLabel({ category: "ufc" })).toBe("UFC");
    expect(categoryLabel({ category: "epl" })).toBe("EPL");
    expect(categoryLabel({ category: "f1" })).toBe("F1");
    expect(categoryLabel({ category: "mls" })).toBe("MLS");
    expect(categoryLabel({ category: "npb" })).toBe("NPB");
    expect(categoryLabel({ category: "kbo" })).toBe("KBO");
  });

  it("still title-cases plain categories and underscore slugs", () => {
    expect(categoryLabel({ category: "politics" })).toBe("Politics");
    expect(categoryLabel({ category: "horse_racing" })).toBe("Horse Racing");
  });

  it("maps the label through toTodaysSetRows, the mapping the page calls", () => {
    const rows = toTodaysSetRows(
      [{ id: "q1", subject: "s", category: "mma" }],
      [],
      0,
      false,
    );
    expect(rows[0].categoryLabel).toBe("MMA");
  });
});
