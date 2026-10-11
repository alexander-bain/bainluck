/** @jest-environment jsdom */
import React, { act } from "react";
import { createRoot } from "react-dom/client";
import QuestionCatalog from "@/components/event/QuestionCatalog";
import MarketBrowser from "@/components/event/MarketBrowser";
import { buildQuestionCatalog, catalogQuote } from "@/lib/questionCatalog";
import type { GameMarketsResponse } from "@/lib/api";

(
  globalThis as typeof globalThis & { IS_REACT_ACT_ENVIRONMENT: boolean }
).IS_REACT_ACT_ENVIRONMENT = true;

let host: HTMLDivElement;
let root: ReturnType<typeof createRoot>;
beforeEach(() => {
  host = document.createElement("div");
  document.body.append(host);
  root = createRoot(host);
});
afterEach(() => {
  act(() => root.unmount());
  host.remove();
});
function render(node: React.ReactNode) {
  act(() => root.render(node));
}
function button(text: string) {
  const found = Array.from(host.querySelectorAll("button")).find(
    (b) => b.textContent === text,
  );
  expect(found).toBeDefined();
  return found!;
}
function click(text: string) {
  act(() => button(text).click());
}
function search(value: string) {
  const input = host.querySelector("input")!;
  act(() => {
    Object.getOwnPropertyDescriptor(
      HTMLInputElement.prototype,
      "value",
    )!.set!.call(input, value);
    input.dispatchEvent(new Event("input", { bubbles: true }));
  });
}

const NOW = Date.parse("2026-10-11T18:00:00Z");
const FRESH = "2026-10-11T17:58:00Z";
const OLD = "2026-10-11T16:00:00Z";

function markets(over: Partial<GameMarketsResponse> = {}): GameMarketsResponse {
  return {
    event_id: 1,
    home_team: "Kansas City Chiefs",
    away_team: "Buffalo Bills",
    home_score: null,
    away_score: null,
    status: "scheduled",
    totals: [],
    player_props: [],
    team_totals: [],
    spreads: [],
    period_markets: [],
    matchups: [],
    other: [],
    pace: null,
    ...over,
  } as GameMarketsResponse;
}

const rungs = (n: number, source = "kalshi") =>
  Array.from({ length: n }, (_, i) => ({
    market_name: "Patrick Mahomes passing yards",
    outcome_name: `Patrick Mahomes: ${200 + i * 25}+`,
    threshold: 200 + i * 25,
    over_probability: 0.9 - i * 0.1,
    source,
    movement: null,
  }));

describe("grouping keeps venue and question identity", () => {
  test("the same title at two venues stays two groups; nothing is merged by text", () => {
    const groups = buildQuestionCatalog(
      markets({ player_props: [...rungs(2, "kalshi"), ...rungs(2, "polymarket")] }),
      "scheduled",
      NOW,
    );
    expect(groups.map((g) => g.source)).toEqual(["Kalshi", "Polymarket"]);
    expect(groups.every((g) => g.outcomes.length === 2)).toBe(true);
  });

  test("a question no card draws still lands in the catalog", () => {
    const groups = buildQuestionCatalog(
      markets({
        other: [
          { market_name: "Will there be a safety?", outcome_name: "Yes", probability: 0.07, source: "kalshi" },
        ] as GameMarketsResponse["other"],
      }),
      "scheduled",
      NOW,
    );
    expect(groups).toHaveLength(1);
    expect(groups[0]).toMatchObject({ family: "More questions", question: "Will there be a safety?" });
    expect(groups[0].outcomes[0].probability).toBe(0.07);
  });

  test("separate venue contracts under one title stay separate (served market id)", () => {
    const groups = buildQuestionCatalog(
      markets({
        other: [
          { market_name: "Both teams to score", outcome_name: "Yes", probability: 0.525, source: "kalshi", _market_id: 64953335 },
          { market_name: "Both teams to score", outcome_name: "Yes", probability: 0.365, source: "kalshi", _market_id: 64953321 },
          { market_name: "Both teams to score", outcome_name: "14+ points", probability: 0.84, source: "kalshi", _market_id: 64953349 },
          { market_name: "Both teams to score", outcome_name: "21+ points", probability: 0.32, source: "kalshi", _market_id: 64953349 },
        ] as GameMarketsResponse["other"],
      }),
      "scheduled",
      NOW,
    );
    expect(groups.map((g) => g.outcomes.map((o) => o.label))).toEqual([
      ["Yes"],
      ["Yes"],
      ["14+ points", "21+ points"],
    ]);
  });

  test("families come out in page order whatever order the payload lists them", () => {
    const groups = buildQuestionCatalog(
      markets({
        other: [{ market_name: "Q", outcome_name: "Yes", probability: 0.5, source: "kalshi" }] as GameMarketsResponse["other"],
        totals: [{ threshold: 47.5, over_probability: 0.52, source: "kalshi", market_type: "totals", market_name: "Total points", outcome_name: "Over 47.5", movement: null }],
      }),
      "scheduled",
      NOW,
    );
    expect(groups.map((g) => g.family)).toEqual(["Game lines", "More questions"]);
  });
});

describe("quotes follow the existing flat-list rule — no new price engine", () => {
  const over = { market_name: "Total points", outcome_name: "Over 47.5", threshold: 47.5, over_probability: 0.52, source: "kalshi" };
  const under = { ...over, outcome_name: "Under 47.5" };

  test("an Under beside its Over twin is dropped; the Over prints the over chance", () => {
    const [group] = buildQuestionCatalog(
      markets({ totals: [over, under] as GameMarketsResponse["totals"] }),
      "scheduled",
      NOW,
    );
    expect(group.outcomes).toEqual([
      expect.objectContaining({ label: "Over 47.5", probability: 0.52 }),
    ]);
  });

  test("an Under with no twin stays reachable and never wears the over price or its complement", () => {
    const [group] = buildQuestionCatalog(
      markets({ totals: [under] as GameMarketsResponse["totals"] }),
      "scheduled",
      NOW,
    );
    expect(group.outcomes).toEqual([
      expect.objectContaining({ label: "Under 47.5", probability: null }),
    ]);
  });

  test("the route's inverted Under leg is an Under whatever its label says", () => {
    expect(catalogQuote({ ...rungs(1)[0], _inverted: true }, "scheduled", NOW)).toBeNull();
    expect(catalogQuote(rungs(1)[0], "scheduled", NOW)).toBe(0.9);
  });

  test("an outcome that names no side prints no over price", () => {
    expect(catalogQuote({ ...over, outcome_name: "Mahomes" }, "scheduled", NOW)).toBeNull();
  });

  test("during play a price seen before the game moved on prints nothing; a fresh one prints", () => {
    expect(catalogQuote({ ...over, observed_at: OLD }, "live", NOW)).toBeNull();
    expect(catalogQuote({ ...over, observed_at: FRESH }, "live", NOW)).toBe(0.52);
    // Pregame, the same old stamp is the pregame number and prints.
    expect(catalogQuote({ ...over, observed_at: OLD }, "scheduled", NOW)).toBe(0.52);
  });

  test("after the final no number prints: a settlement-era trade is not a forecast", () => {
    const groups = buildQuestionCatalog(
      markets({
        totals: [over] as GameMarketsResponse["totals"],
        other: [{ market_name: "Q", outcome_name: "Yes", probability: 1, source: "kalshi" }] as GameMarketsResponse["other"],
      }),
      "final",
      NOW,
    );
    expect(groups.flatMap((g) => g.outcomes.map((o) => o.probability))).toEqual([null, null]);
    expect(groups).toHaveLength(2);
  });

  test("a closed period row is listed and never priced", () => {
    const [group] = buildQuestionCatalog(
      markets({
        closed_period_markets: [
          { market_name: "1st half total", outcome_name: "Over 24.5", threshold: 24.5, probability: null, source: "kalshi", market_type: "half_total", period: "1st Half" },
        ] as unknown as GameMarketsResponse["closed_period_markets"],
      }),
      "live",
      NOW,
    );
    expect(group).toMatchObject({ family: "Periods", period: "1st Half" });
    expect(group.outcomes[0].probability).toBeNull();
  });
});

describe("the catalog keeps the reader's place", () => {
  test("a large group previews six outcomes and opens to all of them", () => {
    render(<QuestionCatalog data={markets({ player_props: rungs(9) })} status="scheduled" />);
    expect(host.querySelectorAll("li")).toHaveLength(6);
    click("Show all 9 outcomes");
    expect(host.querySelectorAll("li")).toHaveLength(9);
    expect(button("Show fewer outcomes").getAttribute("aria-expanded")).toBe("true");
  });

  test("an opened group and a search survive a live refresh with new numbers", () => {
    const first = markets({ player_props: rungs(9) });
    render(<QuestionCatalog data={first} status="scheduled" />);
    click("Show all 9 outcomes");
    search("Mahomes");
    const refreshed = markets({
      player_props: rungs(9).map((r) => ({ ...r, over_probability: r.over_probability - 0.05 })),
    });
    render(<QuestionCatalog data={refreshed} status="scheduled" />);
    expect(host.querySelector("input")!.value).toBe("Mahomes");
    expect(host.querySelectorAll("li")).toHaveLength(9);
    expect(host.textContent).toContain("85%");
  });

  test("an opened group is still open after the reader visits another family", () => {
    const data = markets({
      player_props: rungs(9),
      other: [{ market_name: "Will there be a safety?", outcome_name: "Yes", probability: 0.07, source: "kalshi" }] as GameMarketsResponse["other"],
    });
    render(<QuestionCatalog data={data} status="scheduled" />);
    click("Show all 9 outcomes");
    click("More questions");
    expect(host.textContent).toContain("Will there be a safety?");
    click("Player props");
    expect(host.querySelectorAll("li")).toHaveLength(9);
  });

  test("the details name the original question, venue and lines", () => {
    render(<QuestionCatalog data={markets({ player_props: rungs(2) })} status="scheduled" />);
    const details = host.querySelector("[data-question-group] details")!;
    expect(details.textContent).toContain("Patrick Mahomes passing yards");
    expect(details.textContent).toContain("Kalshi");
    expect(details.textContent).toContain("200, 225");
  });

  test("an unnamed source key never reaches the screen", () => {
    render(
      <QuestionCatalog
        data={markets({ player_props: rungs(1, "odds_api_internal_key") })}
        status="scheduled"
      />,
    );
    expect(host.textContent).not.toContain("odds_api_internal_key");
    expect(host.textContent).toContain("Patrick Mahomes passing yards");
  });

  test("nothing served, nothing drawn", () => {
    render(<QuestionCatalog data={markets()} status="scheduled" />);
    expect(host.innerHTML).toBe("");
  });
});

test("MarketBrowser: the family being read stays put when a refresh lists a new family first", () => {
  const item = (group: string, i: number) => ({
    key: `${group}-${i}`,
    group,
    search: `${group} ${i}`,
    content: <span>{`${group} row ${i}`}</span>,
  });
  render(<MarketBrowser label="Questions" items={[item("Periods", 1), item("Matchups", 1)]} />);
  expect(host.textContent).toContain("Periods row 1");
  render(
    <MarketBrowser
      label="Questions"
      items={[item("Game lines", 1), item("Periods", 1), item("Matchups", 1)]}
    />,
  );
  expect(host.textContent).toContain("Periods row 1");
  expect(host.textContent).not.toContain("Game lines row 1");
  expect(button("Periods").getAttribute("aria-pressed")).toBe("true");
});
