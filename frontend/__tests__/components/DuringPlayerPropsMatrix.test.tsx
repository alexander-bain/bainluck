import React from "react";
import { renderToStaticMarkup } from "react-dom/server";
import DuringPlayerPropsMatrix from "../../components/DuringPlayerPropsMatrix";
import { selectQuestion, type DuringPlayerProps, type DuringPropsRow } from "../../lib/duringPlayerPropsMatrixSelection";

const row: DuringPropsRow = {
  question_key: "server-question", subject: { key: "opaque-player", label: "Aaron Judge", kind: "player" }, stat_key: "hits", period_key: "full_game",
  predicate: { kind: "count_at_least", count: 2, side: "over", label: "2+" }, complement_question_key: null,
  current: { state: "quoted", probability: 0, basis: "single_source", observed_at: "2026-10-02T19:00:00Z" },
  contributors: [{ source: "kalshi", market_id: 10, outcome_id: 20, outcome_name: "Yes", side: "over", period_key: "full_game", probability: 0, observed_at: "2026-10-02T19:00:00Z" }],
  comparison: { state: "unavailable", reason: "no_pregame_pin", baseline: null, delta_points: null },
  result: null, _market_id: 10, _market_ids: [10], contributor_outcome_ids: [20],
};
const data: DuringPlayerProps = {
  contract: "10236.v1", stats: [{ stat_key: "hits", label: "Hits", unit: "hits", unit_singular: "hit", period_key: "full_game", period_label: "Game", predicate: "count_at_least" }], rows: [row],
  coverage: { scope: "linked_markets_loaded_for_event", subjects: 90, questions: 90, quoted: 90, actual_only: 0, unavailable: 0, refused: {} },
};
test("semantic matrix names player/stat/threshold/zero chance and accurate loaded coverage", () => {
  const html = renderToStaticMarkup(<DuringPlayerPropsMatrix data={data} />);
  expect(html).toContain('aria-label="Aaron Judge, Hits, 2+, 0% chance"');
  expect(html).toContain("1 player · 1 question loaded"); expect(html).not.toContain("90 players");
  expect(html).toContain('scope="row"'); expect(html).toContain("sticky left-0");
  expect(html).toContain("text-[22px]"); expect(html).toContain("min-h-[72px]");
});
test("a pregame move is spoken in percentage points, with no stray percent sign", () => {
  const moved: DuringPropsRow = { ...row, current: { ...row.current, probability: .62 },
    comparison: { state: "comparable", reason: null, baseline: { probability: .5, observed_at: "2026-10-02T17:00:00Z", basis: "pregame_pin" }, delta_points: 12 } };
  const html = renderToStaticMarkup(<DuringPlayerPropsMatrix data={{ ...data, rows: [moved] }} />);
  expect(html).toContain('aria-label="Aaron Judge, Hits, 2+, 62% chance, +12 percentage points since pregame"');
});
test("actual-only and absent quote disclose unavailable", () => {
  const html = renderToStaticMarkup(<DuringPlayerPropsMatrix data={{ ...data, rows: [{ ...row, current: { ...row.current, state: "actual_only" } }] }} />);
  expect(html).toContain("1 without a current quote"); expect(html).toContain("current chance unavailable");
  expect(html).not.toContain("0% chance");
});
test("under-only exact question stays reachable but has no over grid price", () => {
  const under: DuringPropsRow = { ...row, predicate: { kind: "count_at_most", count: 1, side: "under", label: "1 or fewer" }, current: { ...row.current, probability: .7 } };
  const html = renderToStaticMarkup(<DuringPlayerPropsMatrix data={{ ...data, rows: [under] }} />);
  expect(html).toContain("Under only"); expect(html).toContain("See under");
  expect(html).not.toContain("70% chance"); expect(html).not.toContain("30%");
});
test("exact selected detail exposes own source identity and observation; no borrowed comparison", () => {
  jest.useFakeTimers().setSystemTime(new Date("2026-10-02T19:38:30Z"));
  try {
    const html = renderToStaticMarkup(<DuringPlayerPropsMatrix data={data} initialSelection={selectQuestion(row)} />);
    expect(html).toContain('role="dialog"'); expect(html).toContain('aria-modal="true"');
    expect(html).toContain("Aaron Judge · Hits · 2+"); expect(html).toContain("Kalshi · Yes");
    expect(html).toContain("Updated 38 min ago"); expect(html).toContain("Pregame comparison unavailable.");
    // the source identity survives for probes, off the reader's screen
    expect(html).toContain('data-market-id="10"'); expect(html).toContain('data-outcome-id="20"');
  } finally { jest.useRealTimers(); }
});
test("#10358 served dialog: no raw stamp, stored key, repeated side or ids on the reader's screen", () => {
  const polymarket: DuringPropsRow = { ...row, predicate: { kind: "count_at_most", count: 0, side: "under", label: "0 or fewer" },
    current: { ...row.current, probability: .79, observed_at: "2026-10-03T22:08:09.607225+00:00" },
    contributors: [{ source: "polymarket", market_id: 64019751, outcome_id: 241052474, outcome_name: "Under", side: "under", period_key: "full_game", probability: .79, observed_at: "2026-10-03T22:08:09.607225+00:00" }],
    comparison: { state: "comparable", reason: null, baseline: { probability: .75, observed_at: "2026-10-03T21:00:00Z", basis: "pregame_pin" }, delta_points: 4 } };
  const html = renderToStaticMarkup(<DuringPlayerPropsMatrix data={{ ...data, rows: [polymarket] }} initialSelection={selectQuestion(polymarket)} />);
  const text = html.replace(/<[^>]+>/g, " ");
  expect(text).toContain("Polymarket"); expect(text).toContain("Updated ");
  expect(text).not.toMatch(/\d{4}-\d{2}-\d{2}T/); expect(text).not.toMatch(/\bpolymarket\b/);
  expect(text).not.toMatch(/Under · under/i); expect(text).not.toContain("64019751"); expect(text).not.toContain("241052474");
  expect(text).not.toContain("Observed"); expect(text).toContain("since pregame (75%).");
});
test("#10358 the detail sheet stacks above the z-50 bottom nav", () => {
  const html = renderToStaticMarkup(<DuringPlayerPropsMatrix data={data} initialSelection={selectQuestion(row)} />);
  expect(html).toMatch(/class="fixed inset-0 z-\[100\] /); expect(html).not.toMatch(/fixed inset-0 z-50 /);
});
test("deployed under-to-over relation is navigable from both exact details with own source side", () => {
  const under: DuringPropsRow = { ...row, question_key: "server-under", predicate: { kind: "count_at_most", count: 1, side: "under", label: "1 or fewer" }, complement_question_key: row.question_key,
    current: { ...row.current, probability: .3 }, contributors: [{ ...row.contributors[0], side: "under", outcome_id: 21, probability: .3, outcome_name: "No" }] };
  const projection = { ...data, rows: [row, under] };
  const overHtml = renderToStaticMarkup(<DuringPlayerPropsMatrix data={projection} initialSelection={selectQuestion(row)} />);
  expect(overHtml).toContain("View under · 1 or fewer");
  const underHtml = renderToStaticMarkup(<DuringPlayerPropsMatrix data={projection} initialSelection={selectQuestion(under)} />);
  expect(underHtml).toContain("View over · 2+"); expect(underHtml).toContain("30%");
  expect(underHtml).toContain("Kalshi · No"); expect(underHtml).not.toContain("70%");
});
test("withdrawn selection stays unavailable and unsupported/null fallback renders nothing", () => {
  const html = renderToStaticMarkup(<DuringPlayerPropsMatrix data={{ ...data, rows: [] }} initialSelection={selectQuestion(row)} />);
  expect(html).toContain("This question isn&#x27;t available right now.");
  expect(renderToStaticMarkup(<DuringPlayerPropsMatrix data={null} />)).toBe("");
});
