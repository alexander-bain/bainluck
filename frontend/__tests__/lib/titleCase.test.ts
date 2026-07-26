// L2-174 Item 3b — acronym-safe title casing. Guards the exact mangles the queue
// called out ("A Pga Tour Major") plus the underscore-tag path the two callers
// (getSubcategoryDisplayName, hub sectionLabel) feed it.

import { toTitleCaseAcronymSafe } from "../../lib/titleCase";

describe("toTitleCaseAcronymSafe", () => {
  it("preserves known acronyms while capitalizing the rest", () => {
    expect(toTitleCaseAcronymSafe("a pga tour major")).toBe("A PGA Tour Major");
    expect(toTitleCaseAcronymSafe("nba mvp")).toBe("NBA MVP");
    expect(toTitleCaseAcronymSafe("nfl roy race")).toBe("NFL ROY Race");
  });

  it("handles underscore-separated tags (the subcategory/hub path)", () => {
    expect(toTitleCaseAcronymSafe("pga_tour_major")).toBe("PGA Tour Major");
    expect(toTitleCaseAcronymSafe("fed_rate")).toBe("Fed Rate");
    expect(toTitleCaseAcronymSafe("al_east")).toBe("AL East");
  });

  it("still title-cases plain words with no acronyms", () => {
    expect(toTitleCaseAcronymSafe("best picture")).toBe("Best Picture");
  });

  // L2-183 — lock the sibling acronyms the queue named, so wiring more callers
  // through this formatter can't regress any of them into "Nba"/"Gdp"/"Ai".
  it("preserves the full sibling acronym set (league / macro / tech)", () => {
    expect(toTitleCaseAcronymSafe("nfl")).toBe("NFL");
    expect(toTitleCaseAcronymSafe("mlb")).toBe("MLB");
    expect(toTitleCaseAcronymSafe("nhl")).toBe("NHL");
    expect(toTitleCaseAcronymSafe("ufc")).toBe("UFC");
    expect(toTitleCaseAcronymSafe("wnba")).toBe("WNBA");
    expect(toTitleCaseAcronymSafe("gdp forecast")).toBe("GDP Forecast");
    expect(toTitleCaseAcronymSafe("cpi report")).toBe("CPI Report");
    expect(toTitleCaseAcronymSafe("ai race")).toBe("AI Race");
  });

  it("matches acronyms even with surrounding punctuation", () => {
    expect(toTitleCaseAcronymSafe("(mvp) odds")).toBe("(MVP) Odds");
  });

  it("returns empty string for empty/nullish input", () => {
    expect(toTitleCaseAcronymSafe("")).toBe("");
    expect(toTitleCaseAcronymSafe(null)).toBe("");
    expect(toTitleCaseAcronymSafe(undefined)).toBe("");
  });
});
