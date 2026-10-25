import { awardsRefreshInterval, awardsResult, splitChildren, childLeader } from "@/lib/eventConceptDisplay";
import type { EventConceptChild } from "@/lib/types";
const NOW = Date.UTC(2026, 9, 12, 12);
const pending: EventConceptChild = { market_id: 1, market_name: "Best Picture", settled: false, probability: .99, outcomes: [{ name: "Favorite", probability: .99, won: false }] };
const edition = (children = [pending], key = "event:awards:oscars-2026") => ({ event: { domain: "awards", key, status: "unknown" }, children });
test("explicit awards undecided beats price convergence; other domains retain their existing fallback", () => {
  expect(splitChildren([pending], "awards")).toEqual({ live: [pending], settled: [] });
  expect(splitChildren([pending], "ufc")).toEqual({ live: [], settled: [pending] });
  expect(childLeader(pending)?.name).toBe("Favorite"); // shared helper unchanged
});
test("announcement requires own outcome grade, never price or standalone convenience winner", () => {
  expect(awardsResult({ ...pending, settled: true, graded_winner: "Favorite" })).toMatchObject({ state: "closed", names: [] });
  const graded = { ...pending, settled: true, outcomes: [{ name: "Actual winner", probability: null, won: true }] };
  expect(awardsResult(graded)).toMatchObject({ state: "announced", names: ["Actual winner"], prop: false });
});
test("ties preserve every grade; prop result keeps its distinction", () => {
  const tie = { ...pending, graded_winner: null, outcomes: [{ name: "A", probability: .1, won: true }, { name: "B", probability: null, won: true }, { name: "Favorite", probability: .99, won: false }] };
  expect(awardsResult(tie).names).toEqual(["A", "B"]);
  expect(awardsResult({ ...tie, kind: "prop", prop_type: "nominations" })).toMatchObject({
    prop: true,
    nominations: true,
    settledByLabel: null,
  });
  expect(awardsResult({ ...tie, kind: "prop", prop_type: "occurrence" })).toMatchObject({
    prop: true,
    nominations: false,
    settledByLabel: null,
  });
});

test("result.venue maps supported settling providers and never invents a provider when null or unconfirmed", () => {
  const announcedOutcomes = [{ name: "The Pitt", probability: 1, won: true }];
  expect(
    awardsResult({
      ...pending,
      settled: true,
      outcomes: announcedOutcomes,
      result: { state: "announced", evidence_kind: "venue_settlement", venue: "kalshi" },
    }).settledByLabel,
  ).toBe("Settled by Kalshi");
  expect(
    awardsResult({
      ...pending,
      settled: true,
      outcomes: announcedOutcomes,
      result: { state: "announced", evidence_kind: "venue_settlement", venue: "Polymarket" },
    }).settledByLabel,
  ).toBe("Settled by Polymarket");
  expect(
    awardsResult({
      ...pending,
      settled: true,
      outcomes: announcedOutcomes,
      result: { state: "announced", evidence_kind: "venue_settlement", venue: null },
    }).settledByLabel,
  ).toBeNull();
  expect(
    awardsResult({
      ...pending,
      settled: true,
      outcomes: announcedOutcomes,
      result: { state: "announced", evidence_kind: "venue_settlement", venue: "oddschecker" },
    }).settledByLabel,
  ).toBeNull();
  expect(
    awardsResult({
      ...pending,
      settled: true,
      outcomes: [{ name: "Favorite", probability: 0.99, won: false }],
      result: { state: "closed", evidence_kind: "unconfirmed_grade", venue: "kalshi" },
    }).settledByLabel,
  ).toBeNull();
});
test("bounded relevant unknown edition uses existing cadence and stops with own results", () => {
  expect(awardsRefreshInterval(edition(), NOW, NOW)).toBe(30000);
  expect(awardsRefreshInterval(edition(), NOW, NOW + 30 * 60 * 1000)).toBe(0);
  expect(awardsRefreshInterval(edition([{ ...pending, outcomes: [{ name: "Winner", probability: null, won: true }] }]), NOW, NOW)).toBe(0);
  expect(awardsRefreshInterval(edition(), NOW + 1, NOW)).toBe(0);
});
test("historical, remote future, dated out-of-window, missing identity and non-awards never acquire awards polling", () => {
  for (const key of ["event:awards:oscars-2025", "event:awards:oscars-2028", "event:awards:oscars", "invalid"]) expect(awardsRefreshInterval(edition([pending], key), NOW, NOW)).toBe(0);
  for (const date of [NOW - 13 * 3600000, NOW + 25 * 3600000]) expect(awardsRefreshInterval({ ...edition(), event: { ...edition().event, end_date: new Date(date).toISOString() } }, NOW, NOW)).toBe(0);
  expect(awardsRefreshInterval({ ...edition(), event: { ...edition().event, domain: "ufc", status: "live" } }, NOW, NOW)).toBe(0);
  expect(awardsRefreshInterval(edition([]), NOW, NOW)).toBe(0);
});

test("initial missing data arms only an eligible awards route, never null/invalid/historical data", () => {
  expect(awardsRefreshInterval(undefined, NOW, NOW, "event:awards:oscars-2026")).toBe(30000);
  expect(awardsRefreshInterval(undefined, NOW, NOW, "event:awards:oscars-2025")).toBe(0);
  expect(awardsRefreshInterval(undefined, NOW, NOW, "event:ufc:oscars-2026")).toBe(0);
  expect(awardsRefreshInterval(null, NOW, NOW, "event:awards:oscars-2026")).toBe(0);
  expect(awardsRefreshInterval(undefined, NOW, NOW + 30 * 60 * 1000, "event:awards:oscars-2026")).toBe(0);
});
