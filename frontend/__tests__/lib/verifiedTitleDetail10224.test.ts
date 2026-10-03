/**
 * #10224 — the web futures detail's reading of `representation=verified_title`.
 *
 * Fixtures under `__tests__/fixtures/verifiedTitle10224/` are the server's REAL
 * route output (PR #10216 at 358c040443), dumped through
 * `backend/tests/test_futures_verified_title_9387.py`'s own `detail()` /
 * helpers over its retained 86832 / 40533 / 129037 trio:
 *   detail-odds-verified   — sportsbook page, three venues
 *   detail-kalshi-verified — Kalshi page
 *   detail-*-default — the same rows, no opt-in (old/default callers)
 *   detail-odds-refused — opted in, anchor missing ⇒ source
 */
import oddsVerified from "../fixtures/verifiedTitle10224/detail-odds-verified.json";
import oddsDefault from "../fixtures/verifiedTitle10224/detail-odds-default.json";
import oddsRefused from "../fixtures/verifiedTitle10224/detail-odds-refused.json";
import kalshiVerified from "../fixtures/verifiedTitle10224/detail-kalshi-verified.json";
import {
  contributorKeys,
  effectiveRepresentation,
  heroContributorLabels,
  heroValueIsSourceOwn,
  relatedEventsOnDetailScale,
  sanitizeVerifiedTitleDetail,
  verifiedHistoryLabel,
} from "@/lib/verifiedTitleDetail";
import type { FuturesMarketDetailResponse, RelatedEvent } from "@/lib/types";

const detail = (x: unknown) => structuredClone(x) as FuturesMarketDetailResponse;
const BUFFALO_ODDS = 1309486;
const RAMS_ODDS = 1309485;

describe("effective representation", () => {
  it("reads the real verified wire, and everything else is source", () => {
    expect(effectiveRepresentation(detail(oddsVerified))).toBe("verified_title");
    expect(effectiveRepresentation(detail(oddsDefault))).toBe("source");
    expect(effectiveRepresentation(detail(oddsRefused))).toBe("source");
    expect(effectiveRepresentation({ representation: "VERIFIED_TITLE" })).toBe("source");
    expect(effectiveRepresentation({ representation: 1 })).toBe("source");
    expect(effectiveRepresentation(undefined)).toBe("source");
  });

  it("CONTROL: the default fixture carries none of the new keys", () => {
    const d = oddsDefault as Record<string, unknown>;
    expect(d.representation).toBeUndefined();
    expect(d.contributing_sources).toBeUndefined();
    expect((d.outcomes as Record<string, unknown>[])[0].contributing_sources).toBeUndefined();
  });
});

describe("hero contributors are the displayed outcome's, never the union", () => {
  it("the real three-venue wire labels all three", () => {
    const d = detail(oddsVerified);
    const hero = d.outcomes.find((o) => o.id === BUFFALO_ODDS)!;
    expect(heroContributorLabels(d, hero)).toEqual(["Sportsbooks", "Kalshi", "Polymarket"]);
  });

  it("an outcome with one contributor is one source, whatever the union says", () => {
    const d = detail(oddsVerified);
    expect(d.contributing_sources).toEqual(["odds_api", "kalshi", "polymarket"]);
    const hero = { ...d.outcomes[0], contributing_sources: ["kalshi"] };
    expect(heroContributorLabels(d, hero)).toEqual(["Kalshi"]);
  });

  it("no contributor is an empty answer; an unknown key is unlabellable", () => {
    const d = detail(oddsVerified);
    expect(heroContributorLabels(d, { ...d.outcomes[0], contributing_sources: [] })).toEqual([]);
    expect(heroContributorLabels(d, { ...d.outcomes[0], contributing_sources: ["books"] })).toBeUndefined();
    expect(heroContributorLabels(d, { ...d.outcomes[0], contributing_sources: "kalshi" as never })).toBeUndefined();
    expect(contributorKeys(["polymarket", "odds_api", "polymarket"])).toEqual(["odds_api", "polymarket"]);
  });

  it("CONTROL: source mode never reads contributors, even if a row carries some", () => {
    const d = detail(oddsRefused);
    expect(heroContributorLabels(d, { ...d.outcomes[0], contributing_sources: ["kalshi"] })).toBeUndefined();
    expect(heroContributorLabels(detail(oddsDefault), detail(oddsDefault).outcomes[0])).toBeUndefined();
  });

  it("the ambient source curve draws only behind a source-own value", () => {
    const d = detail(oddsVerified);
    expect(heroValueIsSourceOwn(d, d.outcomes[0])).toBe(false);
    expect(heroValueIsSourceOwn(d, { ...d.outcomes[0], contributing_sources: ["odds_api"] })).toBe(true);
    expect(heroValueIsSourceOwn(d, { ...d.outcomes[0], contributing_sources: ["kalshi"] })).toBe(false);
    expect(heroValueIsSourceOwn(detail(oddsDefault), detail(oddsDefault).outcomes[0])).toBe(true);
  });
});

describe("no cross-estimator movement survives", () => {
  it("verified mode drops rank_change_24h on every row and keeps the server's nulls", () => {
    const d = detail(oddsVerified);
    d.outcomes[0].rank_change_24h = 2;
    const out = sanitizeVerifiedTitleDetail(d);
    expect(out.outcomes.map((o) => o.rank_change_24h)).toEqual(d.outcomes.map(() => null));
    expect(out.outcomes.every((o) => o.opening_probability === null && o.probability_change_24h === null)).toBe(true);
    expect(out.outcomes.map((o) => o.probability)).toEqual(d.outcomes.map((o) => o.probability));
  });

  it("CONTROL: a source-mode body is returned untouched", () => {
    const d = detail(oddsRefused);
    d.outcomes[0].rank_change_24h = 2;
    expect(sanitizeVerifiedTitleDetail(d)).toBe(d);
    expect(sanitizeVerifiedTitleDetail(d).outcomes[0].rank_change_24h).toBe(2);
  });
});

describe("#10244 the chart is the source's own /history, named as that source's", () => {
  it("a verified page labels the chart with its source's name", () => {
    expect(verifiedHistoryLabel(detail(oddsVerified))).toBe("Sportsbooks history");
    expect(verifiedHistoryLabel(detail(kalshiVerified))).toBe("Kalshi history");
  });

  it("CONTROL: source mode (default or refused) has no label — the card is unchanged", () => {
    expect(verifiedHistoryLabel(detail(oddsDefault))).toBeNull();
    expect(verifiedHistoryLabel(detail(oddsRefused))).toBeNull();
    expect(verifiedHistoryLabel(undefined)).toBeNull();
  });

  it("a source outside the vocabulary is never given an invented name", () => {
    const d = detail(oddsVerified);
    d.source = "books";
    expect(verifiedHistoryLabel(d)).toBeNull();
  });
});

/** Production's shape on /futures/86832: the strip's rows carry the SOURCE value. */
function billsAtRams(ids: { away?: number; home?: number } = { away: BUFFALO_ODDS, home: RAMS_ODDS }): RelatedEvent[] {
  return [
    {
      event_id: 1,
      home_team: "Los Angeles Rams",
      away_team: "Buffalo Bills",
      commence_time: "2026-10-04T20:25:00Z",
      status: "scheduled",
      sport: "americanfootball_nfl",
      home_score: null,
      away_score: null,
      linked_teams: [
        { side: "home", team_name: "Los Angeles Rams", outcome_id: ids.home, outcome_name: "Los Angeles Rams",
          probability: 0.107361, american_odds: 831, rank: 2, outcome_is_team: true },
        { side: "away", team_name: "Buffalo Bills", outcome_id: ids.away, outcome_name: "Buffalo Bills",
          probability: 0.112913, american_odds: 786, rank: 1, outcome_is_team: true },
      ],
    },
  ];
}
const byTeam = (events: RelatedEvent[]) =>
  Object.fromEntries(events[0].linked_teams.map((t) => [t.team_name, t]));

describe("#10243 Games This Week prints the detail's own number for each outcome id", () => {
  it("a verified page prints the table's verified value, not the route's source value", () => {
    const d = detail(oddsVerified);
    const rows = byTeam(relatedEventsOnDetailScale(d, billsAtRams()));
    const table = new Map(d.outcomes.map((o) => [o.id, o]));
    expect(rows["Buffalo Bills"].probability).toBe(table.get(BUFFALO_ODDS)!.probability);
    expect(rows["Buffalo Bills"].probability).toBe(0.13);
    expect(rows["Los Angeles Rams"].probability).toBe(table.get(RAMS_ODDS)!.probability);
    expect(rows["Buffalo Bills"].american_odds).toBe(table.get(BUFFALO_ODDS)!.american_odds);
  });

  it("joined by id, not by position or name: swapped ids swap the numbers", () => {
    const d = detail(oddsVerified);
    const rows = byTeam(relatedEventsOnDetailScale(d, billsAtRams({ away: RAMS_ODDS, home: BUFFALO_ODDS })));
    expect(rows["Buffalo Bills"].probability).toBe(0.105);
    expect(rows["Los Angeles Rams"].probability).toBe(0.13);
  });

  it("no id, or an id the detail does not carry, prints no number — never the source one", () => {
    const d = detail(oddsVerified);
    const rows = byTeam(relatedEventsOnDetailScale(d, billsAtRams({ away: undefined, home: 999 })));
    expect(rows["Buffalo Bills"].probability).toBeNull();
    expect(rows["Los Angeles Rams"].probability).toBeNull();
  });

  it("CONTROL: source mode (default or refused) returns the events untouched", () => {
    const events = billsAtRams();
    expect(relatedEventsOnDetailScale(detail(oddsDefault), events)).toBe(events);
    expect(relatedEventsOnDetailScale(detail(oddsRefused), events)).toBe(events);
    expect(relatedEventsOnDetailScale(undefined, events)).toBe(events);
  });
});
