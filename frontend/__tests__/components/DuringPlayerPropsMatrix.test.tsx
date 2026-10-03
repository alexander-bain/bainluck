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
  const html = renderToStaticMarkup(<DuringPlayerPropsMatrix data={data} initialSelection={selectQuestion(row)} />);
  expect(html).toContain('role="dialog"'); expect(html).toContain('aria-modal="true"');
  expect(html).toContain("Aaron Judge · Hits · 2+"); expect(html).toContain("kalshi · Yes · over");
  expect(html).toContain("Observed 2026-10-02T19:00:00Z"); expect(html).toContain("Pregame comparison unavailable.");
});
test("deployed under-to-over relation is navigable from both exact details with own source side", () => {
  const under: DuringPropsRow = { ...row, question_key: "server-under", predicate: { kind: "count_at_most", count: 1, side: "under", label: "1 or fewer" }, complement_question_key: row.question_key,
    current: { ...row.current, probability: .3 }, contributors: [{ ...row.contributors[0], side: "under", outcome_id: 21, probability: .3, outcome_name: "No" }] };
  const projection = { ...data, rows: [row, under] };
  const overHtml = renderToStaticMarkup(<DuringPlayerPropsMatrix data={projection} initialSelection={selectQuestion(row)} />);
  expect(overHtml).toContain("View under · 1 or fewer");
  const underHtml = renderToStaticMarkup(<DuringPlayerPropsMatrix data={projection} initialSelection={selectQuestion(under)} />);
  expect(underHtml).toContain("View over · 2+"); expect(underHtml).toContain("30%");
  expect(underHtml).toContain("kalshi · No · under"); expect(underHtml).not.toContain("70%");
});
test("withdrawn selection stays unavailable and unsupported/null fallback renders nothing", () => {
  const html = renderToStaticMarkup(<DuringPlayerPropsMatrix data={{ ...data, rows: [] }} initialSelection={selectQuestion(row)} />);
  expect(html).toContain("This exact question is no longer");
  expect(renderToStaticMarkup(<DuringPlayerPropsMatrix data={null} />)).toBe("");
});
