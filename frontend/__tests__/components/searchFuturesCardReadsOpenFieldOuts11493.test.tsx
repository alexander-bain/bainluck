/**
 * #11493 — Search never gives an eliminated team a World Series chance.
 *
 * Production 2026-10-23 09:37Z, `/api/events/search?q=Brewers` → futures 114584
 * "MLB World Series Champion 2026", `status: "open"`, `market_type: "field"`.
 * The card printed Astros 1%, D-backs 1%, Yankees <1%. Those three legs are
 * served `is_winner: false` + `resolution_source: "api_settlement"`; the two
 * clubs still playing carry `resolution_source: null`.
 *
 * One leg per arm, rendered through the card a reader sees: graded out, alive
 * with a served-null source, an absent source (older payload), the retraction,
 * and a graded-false leg the book still prices as a contender. Plus the scope
 * fences: the opt-in, a non-field shape, and a resolved market.
 */
import React from "react";
import { renderToStaticMarkup } from "react-dom/server";
import FuturesCard from "@/components/FuturesCard";
import SearchFamilyCard from "@/components/SearchFamilyCard";
import { openFieldLegIsOut } from "@/lib/openFieldLegOut";
import type { FuturesFamily, FuturesMarket, FuturesOutcome } from "@/lib/types";

jest.mock("next/link", () => ({
  __esModule: true,
  default: ({ children, href }: { children: React.ReactNode; href: string }) => (
    <a href={href}>{children}</a>
  ),
}));

type Leg = Partial<FuturesOutcome> & { id: number; name: string; probability: number | null };

const leg = (l: Leg) =>
  ({ american_odds: null, rank: null, movement: null, is_winner: false, ...l }) as unknown as FuturesOutcome;

// The served legs, verbatim except Rays' source key, which the absent-source
// arm drops below.
const BREWERS = leg({ id: 1634478, name: "Milwaukee Brewers", probability: 0.64, resolution_source: null });
const RAYS = leg({ id: 1634488, name: "Tampa Bay Rays", probability: 0.3655, resolution_source: null });
const ASTROS = leg({ id: 1634474, name: "Houston Astros", probability: 0.005, resolution_source: "api_settlement" });
const DBACKS = leg({ id: 1634486, name: "Arizona Diamondbacks", probability: 0.005, resolution_source: "api_settlement" });
const YANKEES = leg({ id: 1634467, name: "New York Yankees", probability: 0.004, resolution_source: "api_settlement" });

const market = (over: Partial<FuturesMarket> = {}, legs = [BREWERS, RAYS, ASTROS, DBACKS, YANKEES]) =>
  ({
    id: 114584,
    name: "MLB World Series Champion 2026",
    sport: null,
    sport_name: null,
    category: "championship",
    llm_sport_category: "baseball",
    market_tier: 1,
    market_type: "field",
    status: "open",
    source: "polymarket",
    resolution_date: "2026-10-31T23:55:00+00:00",
    outcome_count: 31,
    top_outcomes: legs,
    ...over,
  }) as unknown as FuturesMarket;

/** Each row's name → its right-hand cell, as the reader sees the card. */
function rows(html: string): Record<string, string> {
  const out: Record<string, string> = {};
  const text = html.replace(/<[^>]+>/g, "|").replace(/&lt;/g, "<").replace(/&gt;/g, ">");
  const cells = text.split("|").map((c) => c.trim()).filter(Boolean);
  for (const name of ["Milwaukee Brewers", "Tampa Bay Rays", "Houston Astros", "Arizona Diamondbacks", "New York Yankees"]) {
    const i = cells.indexOf(name);
    if (i >= 0) out[name] = cells.slice(i + 1).find((c) => /%$|^Out$|^Lost$|^Won$/.test(c)) ?? "";
  }
  return out;
}

/** The served five with one leg swapped: a two-leg fixture would switch on
 *  the duel's pair rounding (#2831) and move the numbers this suite pins. */
const withLeg = (swap: FuturesOutcome) =>
  [BREWERS, RAYS, ASTROS, DBACKS, YANKEES].map((l) => (l.id === swap.id ? swap : l));

const card = (m: FuturesMarket, readsOpenFieldOuts = true) =>
  renderToStaticMarkup(<FuturesCard market={m} readsOpenFieldOuts={readsOpenFieldOuts} />);

describe("#11493 Search futures card: an open field's knocked-out legs read Out", () => {
  it("the specimen: three eliminated clubs read Out, Brewers 64% and Rays 37% unchanged", () => {
    expect(rows(card(market()))).toEqual({
      "Milwaukee Brewers": "64%",
      "Tampa Bay Rays": "37%",
      "Houston Astros": "Out",
      "Arizona Diamondbacks": "Out",
      "New York Yankees": "Out",
    });
  });

  it("an absent resolution_source (older payload) keeps today's price", () => {
    const { resolution_source: _drop, ...noKey } = ASTROS as FuturesOutcome & { resolution_source?: string };
    const html = card(market({}, withLeg(noKey as FuturesOutcome)));
    expect(rows(html)["Houston Astros"]).toBe("1%");
  });

  it("the retraction earns nothing", () => {
    const retracted = leg({ ...ASTROS, resolution_source: "ungradeable_result" });
    expect(rows(card(market({}, withLeg(retracted))))["Houston Astros"]).toBe("1%");
  });

  it("a guess-family source is not an authority", () => {
    const guessed = leg({ ...ASTROS, resolution_source: "inferred_from_price" });
    expect(rows(card(market({}, withLeg(guessed))))["Houston Astros"]).toBe("1%");
  });

  it("a graded-false leg the book still prices as a contender keeps its price (#4597 residue)", () => {
    const priced = leg({ ...RAYS, resolution_source: "api_settlement" });
    expect(rows(card(market({}, withLeg(priced))))["Tampa Bay Rays"]).toBe("37%");
  });

  it("without the opt-in, every other surface renders as before", () => {
    expect(rows(card(market(), false))["Houston Astros"]).toBe("1%");
  });

  it("only a ranked field reads Out: a ladder or a Yes/No side keeps its price", () => {
    for (const market_type of ["quantity", "claim", "duel", null]) {
      expect(rows(card(market({ market_type })))["Houston Astros"]).toBe("1%");
    }
  });

  it("a resolved market keeps outcomeRowVerdict's Lost", () => {
    expect(rows(card(market({ status: "resolved" })))["Houston Astros"]).toBe("Lost");
  });
});

describe("#11493 the rule itself", () => {
  const open = { status: "open", market_type: "field" } as const;
  it.each([
    ["graded out", { is_winner: false, resolution_source: "api_settlement", probability: 0.005 }, true],
    ["graded out, no price", { is_winner: false, resolution_source: "clob_authoritative", probability: null }, true],
    ["alive, served null", { is_winner: false, resolution_source: null, probability: 0.005 }, false],
    ["absent source", { is_winner: false, probability: 0.005 }, false],
    ["retraction", { is_winner: false, resolution_source: "ungradeable_result", probability: 0.005 }, false],
    ["winner", { is_winner: true, resolution_source: "api_settlement", probability: 0.995 }, false],
    ["ungraded null", { is_winner: null, resolution_source: "api_settlement", probability: 0.005 }, false],
    ["at the ceiling", { is_winner: false, resolution_source: "api_settlement", probability: 0.2 }, false],
  ])("%s", (_name, l, expected) => {
    expect(openFieldLegIsOut(open, l)).toBe(expected);
  });
  it("only an open market", () => {
    for (const status of ["resolved", "closed", "withdrawn"] as const) {
      expect(openFieldLegIsOut({ status, market_type: "field" }, ASTROS)).toBe(false);
    }
  });
});

describe("#11493 Search family card leader", () => {
  const family = (legs: FuturesOutcome[]) =>
    ({
      family_key: "entity:astros",
      label: "Astros",
      headline: market({}, legs),
      members: [],
      more_count: 0,
      member_count: 1,
    }) as unknown as FuturesFamily;
  const text = (html: string) => html.replace(/<[^>]+>/g, " ").replace(/&lt;/g, "<").replace(/\s+/g, " ");

  it("a knocked-out leader reads Out, a live one keeps its price", () => {
    expect(text(renderToStaticMarkup(<SearchFamilyCard family={family([ASTROS])} />))).toMatch(/Houston Astros Out/);
    expect(text(renderToStaticMarkup(<SearchFamilyCard family={family([BREWERS])} />))).toMatch(/Milwaukee Brewers 64%/);
  });
});
