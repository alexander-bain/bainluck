/**
 * #10224 — the web futures detail's reading of `representation=verified_title`.
 *
 * Fixtures under `__tests__/fixtures/verifiedTitle10224/` are the server's REAL
 * route output (PR #10216 at 358c040443), dumped through
 * `backend/tests/test_futures_verified_title_9387.py`'s own `detail()` /
 * `timeline()` helpers over its retained 86832 / 40533 / 129037 trio:
 *   detail-odds-verified / timeline-odds-verified   — sportsbook page, three venues
 *   detail-kalshi-verified / timeline-kalshi-verified — Kalshi page, source order
 *   detail-*-default — the same rows, no opt-in (old/default callers)
 *   detail-odds-refused / timeline-odds-refused — opted in, anchor missing ⇒ source
 */
import oddsVerified from "../fixtures/verifiedTitle10224/detail-odds-verified.json";
import oddsDefault from "../fixtures/verifiedTitle10224/detail-odds-default.json";
import oddsRefused from "../fixtures/verifiedTitle10224/detail-odds-refused.json";
import kalshiVerified from "../fixtures/verifiedTitle10224/detail-kalshi-verified.json";
import oddsTimeline from "../fixtures/verifiedTitle10224/timeline-odds-verified.json";
import kalshiTimeline from "../fixtures/verifiedTitle10224/timeline-kalshi-verified.json";
import refusedTimeline from "../fixtures/verifiedTitle10224/timeline-odds-refused.json";
import {
  chartCurrentAgrees,
  contributorKeys,
  effectiveRepresentation,
  heroContributorLabels,
  heroValueIsSourceOwn,
  historyBasisLabel,
  sanitizeVerifiedTitleDetail,
  timelineToChartHistory,
  verifiedChartVerdict,
} from "@/lib/verifiedTitleDetail";
import type { FuturesMarketDetailResponse, ProbabilityTimelineResponse } from "@/lib/types";

const detail = (x: unknown) => structuredClone(x) as FuturesMarketDetailResponse;
const timeline = (x: unknown) => structuredClone(x) as ProbabilityTimelineResponse;
const BUFFALO_ODDS = 1309486;
const BUFFALO_KALSHI = 643833;

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

describe("chart history: authentic geometry, its own label, no synthetic endpoint", () => {
  it("labels from the timeline's own history_basis", () => {
    expect(historyBasisLabel(timeline(oddsTimeline).history_basis)).toBe("Sportsbooks history");
    expect(historyBasisLabel(timeline(kalshiTimeline).history_basis)).toBe("Kalshi history");
    expect(historyBasisLabel({ kind: "blend", source: "kalshi", market_id: 1 })).toBeNull();
    expect(historyBasisLabel({ kind: "single_source", source: "books", market_id: 1 })).toBeNull();
    expect(historyBasisLabel({ kind: "single_source", source: "kalshi", market_id: "1" })).toBeNull();
    expect(historyBasisLabel(undefined)).toBeNull();
  });

  it("every series is a metadata row: same id, byte-identical name, route order", () => {
    for (const fixture of [oddsTimeline, kalshiTimeline]) {
      const t = timeline(fixture);
      const chart = timelineToChartHistory(t, { withCurrent: true });
      expect(chart.outcomes.map((o) => o.outcome_id)).toEqual(t.outcomes.map((m) => m.id));
      expect(chart.outcomes.map((o) => o.name)).toEqual(t.outcomes.map((m) => m.name));
      for (const series of chart.outcomes) {
        expect(t.timeline.some((e) => Object.prototype.hasOwnProperty.call(e.outcomes, series.name))).toBe(true);
      }
    }
    // The Kalshi board's own order is NOT probability order; it is kept.
    const kalshi = timelineToChartHistory(timeline(kalshiTimeline), { withCurrent: true });
    const names = kalshi.outcomes.map((o) => o.name);
    expect(names).toEqual((kalshiTimeline as ProbabilityTimelineResponse).outcomes.map((m) => m.name));
    const byVerifiedValue = [...(kalshiTimeline as ProbabilityTimelineResponse).outcomes]
      .sort((a, b) => (b.current_probability ?? 0) - (a.current_probability ?? 0))
      .map((m) => m.name);
    expect(names).not.toEqual(byVerifiedValue);
  });

  it("points are exactly the buckets: same timestamps and values, nothing appended", () => {
    const t = timeline(oddsTimeline);
    const chart = timelineToChartHistory(t, { withCurrent: true });
    const buffalo = chart.outcomes.find((o) => o.outcome_id === BUFFALO_ODDS)!;
    expect(buffalo.history.map((p) => [p.timestamp, p.probability])).toEqual(
      t.timeline.map((e) => [e.timestamp, e.outcomes["Buffalo Bills"]]),
    );
    // The current verified 13% is not the source history's last value, and it is
    // not drawn as one.
    const meta = t.outcomes.find((m) => m.id === BUFFALO_ODDS)!;
    expect(meta.current_probability).toBe(0.13);
    expect(buffalo.history[buffalo.history.length - 1].probability).not.toBe(0.13);
    expect(buffalo.history.every((p) => p.bookmaker === "odds_api")).toBe(true);
    expect(chart.total_data_points).toBe(t.timeline.length * t.outcomes.length);
  });

  it("a bucket without the name stays a gap; a near-miss name is not that series", () => {
    const t = timeline(oddsTimeline);
    delete (t.timeline[1].outcomes as Record<string, number>)["Buffalo Bills"];
    (t.timeline[2].outcomes as Record<string, number>)["Buffalo Bills "] = 0.5;
    delete (t.timeline[2].outcomes as Record<string, number>)["Buffalo Bills"];
    const buffalo = timelineToChartHistory(t, { withCurrent: true }).outcomes.find(
      (o) => o.outcome_id === BUFFALO_ODDS,
    )!;
    expect(buffalo.history.map((p) => p.timestamp)).toEqual([t.timeline[0].timestamp]);
  });

  it("persistent disagreement keeps the history and drops current metadata", () => {
    const t = timeline(oddsTimeline);
    const agreed = timelineToChartHistory(t, { withCurrent: true });
    const held = timelineToChartHistory(t, { withCurrent: false });
    expect(held.outcomes.map((o) => o.history)).toEqual(agreed.outcomes.map((o) => o.history));
    expect(agreed.outcomes.every((o) => o.current_price_available === true)).toBe(true);
    expect(held.outcomes.every((o) => !("current_price_available" in o))).toBe(true);
  });

  it("a Field row (id null) and malformed rows are not drawn", () => {
    const t = timeline(oddsTimeline);
    t.outcomes.push({ id: null, name: "Field", current_probability: 0.1 });
    t.outcomes.push({ id: 1.5, name: "X", current_probability: 0.1 } as never);
    const ids = timelineToChartHistory(t, { withCurrent: true }).outcomes.map((o) => o.outcome_id);
    expect(ids).not.toContain(null);
    expect(ids).not.toContain(1.5);
  });
});

describe("detail and chart current context", () => {
  it("the real frozen pair agrees, on both pages", () => {
    expect(chartCurrentAgrees(detail(oddsVerified), timeline(oddsTimeline), BUFFALO_ODDS)).toBe(true);
    expect(chartCurrentAgrees(detail(kalshiVerified), timeline(kalshiTimeline), BUFFALO_KALSHI)).toBe(true);
  });

  it("same mode with a newer value disagrees", () => {
    const t = timeline(oddsTimeline);
    t.outcomes.find((m) => m.id === BUFFALO_ODDS)!.current_probability = 0.135;
    expect(chartCurrentAgrees(detail(oddsVerified), t, BUFFALO_ODDS)).toBe(false);
  });

  it("same value with different contributors disagrees", () => {
    const t = timeline(oddsTimeline);
    t.outcomes.find((m) => m.id === BUFFALO_ODDS)!.contributing_sources = ["odds_api", "kalshi"];
    expect(chartCurrentAgrees(detail(oddsVerified), t, BUFFALO_ODDS)).toBe(false);
  });

  it("a mode mismatch disagrees in both directions", () => {
    expect(chartCurrentAgrees(detail(oddsVerified), timeline(refusedTimeline), BUFFALO_ODDS)).toBe(false);
    expect(chartCurrentAgrees(detail(oddsRefused), timeline(oddsTimeline), BUFFALO_ODDS)).toBe(false);
  });

  it("CONTROL: a sibling's change does not move the hero's comparison", () => {
    const t = timeline(oddsTimeline);
    t.outcomes.find((m) => m.id !== BUFFALO_ODDS)!.current_probability = 0.5;
    expect(chartCurrentAgrees(detail(oddsVerified), t, BUFFALO_ODDS)).toBe(true);
  });

  it("one retry, then persistent", () => {
    expect(verifiedChartVerdict(null, false)).toBe("pending");
    expect(verifiedChartVerdict(true, true)).toBe("agree");
    expect(verifiedChartVerdict(false, false)).toBe("retry");
    expect(verifiedChartVerdict(false, true)).toBe("persistent");
  });
});
