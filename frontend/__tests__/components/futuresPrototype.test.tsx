import React from "react";
import { renderToStaticMarkup } from "react-dom/server";
import Prototype from "@/app/kernels-preview/futures/Prototype";
import { bodyKind, observations, openingFor, payloadVerdict, percentText, storedShape, type PrototypeData } from "@/app/kernels-preview/futures/_model";
import type { FuturesMarketDetailResponse, FuturesOutcomeHistory } from "@/lib/types";
import duel from "@/app/kernels-preview/futures/_data/109085.json";
import field from "@/app/kernels-preview/futures/_data/108629.json";
import participation from "@/app/kernels-preview/futures/_data/227.json";
import oneLeg from "@/app/kernels-preview/futures/_data/109918.json";
import finalOneLeg from "@/app/kernels-preview/futures/_data/109918-final.json";
import settled from "@/app/kernels-preview/futures/_data/108645.json";

jest.mock("@/hooks", () => ({ usePageTracking: jest.fn(), useScrollDepth: jest.fn(), useEngagementTime: jest.fn() }));
function dataFor(raw: typeof oneLeg | typeof field | typeof settled | typeof participation | typeof duel): PrototypeData {
  return { detail: raw.detail as unknown as FuturesMarketDetailResponse, history: raw.history.outcomes as FuturesOutcomeHistory[], sources: ["kalshi"], related: [], capturedAt: "2026-11-04T02:33:38Z", settledAt: null, historyNote: null };
}
function render(data: PrototypeData, props: Partial<React.ComponentProps<typeof Prototype>> = {}) {
  return renderToStaticMarkup(<Prototype data={data} {...props} />);
}

test("an independent field never enters the winner normalization branch", () => {
  const data = dataFor(participation);
  expect(storedShape(data.detail)).toBe("field");
  expect(bodyKind(data.detail)).toBe("participation");
  expect(render(data)).toContain("These chances do not add to 100%");
  expect(render(data)).toContain("94%");
});

test("a multi-venue blend gets no one-venue opening, path, or normalized split", () => {
  const data = dataFor(duel);
  data.sources = ["kalshi", "polymarket"];
  data.detail = { ...data.detail, outcomes: data.detail.outcomes.map((row, i) => ({ ...row, probability: i ? .024 : .97125 })) };
  expect(openingFor(data,data.detail.outcomes[0])).toBeNull();
  const html = render(data);
  expect(html).toContain("97%");
  expect(html).not.toContain('data-kind="observed-run"');
  expect(html).not.toContain("98%");
});

test("the field retains full-field shares and a route to every named outcome", () => {
  const html = render(dataFor(field));
  expect(html).toContain("29%");
  expect(html).toContain("21");
  expect(html).toContain(" more");
  expect(html).toContain("All outcomes · ");
  expect(html).not.toContain(">Other<");
});

test("ungradeable is not a loss and a one-leg view has no invented No", () => {
  const data = dataFor(oneLeg);
  expect(payloadVerdict(data.detail,data.detail.outcomes[0])).toBeNull();
  const html = render(data, { initialStudy: "open", initialMissing: true });
  expect(html).toContain("No recent price");
  expect(html).not.toContain("Result unavailable");
  expect(html).not.toContain(">Lost<");
  expect(html).not.toContain(">No<");
});

test("a later authoritative one-leg result replaces the ungradeable boolean", () => {
  const data = dataFor(oneLeg);
  data.finalDetail = finalOneLeg.detail as unknown as FuturesMarketDetailResponse;
  const html = render(data);
  expect(html).toContain(">Won<");
  expect(html).toContain("Opening chance");
  expect(html).toContain("38%");
  const headline = html.split('aria-label="Market headline"')[1].split("</section>")[0];
  expect(headline).not.toContain("100%");
});

test("settlement annotations are excluded before domains, paths and inspection", () => {
  const data = dataFor(settled);
  const id = data.detail.outcomes[0].id;
  const points = observations(data.history,id);
  const raw = data.history.find((s) => s.outcome_id === id)!;
  const synthetic = raw.history.filter((p) => p.bookmaker === "settlement");
  expect(synthetic.length).toBeGreaterThan(0);
  expect(points).toHaveLength(raw.history.length - synthetic.length);
  expect(points.at(-1)!.probability).toBe(.959);
  const headline = render(data).split('aria-label="Market headline"')[1].split("</section>")[0];
  expect(headline).toContain("56%");
  expect(headline).not.toContain("100%");
});

test("gambling formats cannot leak into headline, graphic or native sheet", () => {
  const data = dataFor(field);
  data.detail = { ...data.detail, outcomes: data.detail.outcomes.map((row) => ({ ...row, american_odds: 87654321, opening_american_odds: -87654321 })) };
  const html = render(data);
  expect(html).not.toContain("87654321");
  expect(html).toContain("Source information reserved");
  expect(html).toContain("<dialog");
});

test("whole-number boundary language never claims a near-certainty is certain", () => {
  expect(percentText(.575)).toBe("58%");
  expect(percentText(.995)).toBe(">99%");
  expect(percentText(.004)).toBe("<1%");
});
