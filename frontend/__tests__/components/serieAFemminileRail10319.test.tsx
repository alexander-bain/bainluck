import React from "react";
import { renderToStaticMarkup } from "react-dom/server";

let responses: Record<string, unknown> = {};
let requested: string[] = [];
jest.mock("swr", () => ({
  __esModule: true,
  default: (key: unknown) => {
    if (!key) return { data: undefined };
    const flat = Array.isArray(key) ? key.join("|") : String(key);
    requested.push(flat);
    return { data: responses[flat] };
  },
}));

// eslint-disable-next-line @typescript-eslint/no-var-requires
const RelatedByTag = require("@/components/RelatedByTag").default;
const TAGS = ["sport:soccer", "league:serie_a_femminile", "gender:women"];
const EXACT = `related-by-tag|${TAGS.join("|")}`;
const WIDE = "related-by-tag|sport:soccer";
const MENS = ["sport:soccer", "league:serie_a", "gender:men"];

function market(id: number, name: string, tags?: string[]) {
  return { type: "futures", data: {
    id, name, market_tags: tags, top_outcomes: [
      { name: "Parma", probability: 0.4 }, { name: "Ternana", probability: 0.6 },
    ], outcome_count: 2,
  } };
}
function game(id: number, tags?: string[]) {
  return { type: "event", data: {
    id, event_tags: tags, sport: "soccer_italy_serie_a_women",
    away_team: "Ternana", home_team: "Parma Calcio", status: "scheduled",
    commence_time: "2030-10-03T10:30:00Z", home_score: null, away_score: null,
    current_odds: { home_probability: 0.4, away_probability: 0.3 },
  } };
}
function render(items: unknown[], props: Record<string, unknown> = {}) {
  const tags = (props.tags ?? TAGS) as string[];
  requested = [];
  responses = {
    [`related-by-tag|${tags.join("|")}`]: { items },
    [WIDE]: { items: [market(900, "Men's fallback", MENS)] },
  };
  return renderToStaticMarkup(React.createElement(RelatedByTag, {
    tags, limit: 2, title: "More Serie A Femminile (Women)", ...props,
  }));
}

describe("#10319 — only corroborated events and markets fill the women's rail", () => {
  it("drops four men's competition cards before slicing so valid women keep seats", () => {
    const men = ["Serie A Champion", "Serie A Top Scorer", "Serie A Relegation", "Serie A Top Four"]
      .map((name, i) => market(i + 1, name, MENS));
    const html = render([...men, game(50, TAGS), market(51, "Serie A Femminile Winner", TAGS)]);
    expect(html).toContain('data-count="2"');
    expect(html).toContain('href="/events/50"');
    expect(html).toContain('href="/futures/51"');
    expect(html).toContain("More Serie A Femminile (Women)");
    for (let id = 1; id <= 4; id++) expect(html).not.toContain(`href="/futures/${id}"`);
    // Both use the unchanged ordinary rail card and probability field.
    expect((html.match(/data-testid="related-card-field"/g) ?? [])).toHaveLength(2);
    expect(html).toContain("40%");
    expect(html).toContain("30%");
    expect(requested).toEqual([EXACT]);
  });

  it("refuses untyped concepts even if a sport-only concept response supplies tags", () => {
    expect(render([{ type: "concept", data: {
      key: "ufc:1", name: "Unrelated concept", domain: "ufc", event_tags: TAGS,
    } }])).toBe("");
  });

  it.each([
    undefined, [], ["sport:soccer", "gender:women"], MENS,
    ["sport:soccer", "league:fifa_world_cup", "gender:women"],
    [...TAGS, "league:serie_a"], [...TAGS, "gender:men"], [...TAGS, "sport:basketball"],
  ])("refuses unknown, other-competition and conflicting returned tags: %j", (tags) => {
    expect(render([game(1, tags), market(2, "Women's-looking name alone", tags)])).toBe("");
  });

  it("leaves empty appropriate supply empty, even when a caller offers broad fallback", () => {
    expect(render([], { fallbackTags: ["sport:soccer"] })).toBe("");
    expect(requested).toEqual([EXACT]);
  });

  it("refuses an incomplete exact query without requesting a generic fallback", () => {
    expect(render([market(1, "Correct market", TAGS)], {
      tags: ["sport:soccer", "league:serie_a_femminile"], fallbackTags: ["sport:soccer"],
    })).toBe("");
    expect(requested).toEqual([]);
  });

  it("retains current-event exclusion and selects the next corroborated candidate", () => {
    const html = render([game(50, TAGS), game(51, TAGS), market(52, "Women's Winner", TAGS)], {
      excludeId: 50, excludeType: "event", limit: 1,
    });
    expect(html).not.toContain('href="/events/50"');
    expect(html).toContain('href="/events/51"');
    expect(html).not.toContain('href="/futures/52"');
  });
});

describe("#10319 — other queries keep their current card and fallback behavior", () => {
  it.each([
    ["sport:soccer", "league:serie_a"],
    ["sport:basketball", "league:wnba"],
    ["sport:soccer", "league:fifa_world_cup"],
  ])("does not require new competition tags or reject concepts for %j", (sport, league) => {
    const html = render([
      market(10, "Existing league winner"),
      { type: "concept", data: { key: "event:existing", name: "Existing concept", domain: "soccer" } },
    ], { tags: [sport, league], title: "Existing rail" });
    expect(html).toContain('href="/futures/10"');
    expect(html).toContain("Existing concept");
    expect(html).toContain('data-count="2"');
  });

  it("preserves the existing men's sport-only fallback on empty league supply", () => {
    const html = render([], {
      tags: ["sport:soccer", "league:serie_a"], fallbackTags: ["sport:soccer"],
      title: "More Serie A", fallbackTitle: "More Soccer",
    });
    expect(html).toContain("Men&#x27;s fallback");
    expect(html).toContain("More Soccer");
    expect(requested).toEqual(["related-by-tag|sport:soccer|league:serie_a", WIDE]);
  });
});
