import React from "react";
import { renderToStaticMarkup } from "react-dom/server";
import Prototype from "@/app/kernels-preview/futures/Prototype";
import {
  bodyKind,
  payloadVerdict,
  percentText,
  storedShape,
  type PrototypeData,
} from "@/app/kernels-preview/futures/_model";
import field from "@/app/kernels-preview/futures/_data/108629.json";
import participation from "@/app/kernels-preview/futures/_data/227.json";
import oneLeg from "@/app/kernels-preview/futures/_data/109918.json";
import settled from "@/app/kernels-preview/futures/_data/108645.json";
import duel from "@/app/kernels-preview/futures/_data/109085.json";
import type { FuturesMarketDetailResponse } from "@/lib/types";

jest.mock("@/hooks", () => ({
  usePageTracking: jest.fn(),
  useScrollDepth: jest.fn(),
  useEngagementTime: jest.fn(),
}));
jest.mock("@/components/FuturesChart", () => ({
  FuturesChart: () => <div>Recorded chart</div>,
}));

function asDetail(value: unknown) {
  return value as FuturesMarketDetailResponse;
}
function render(
  detail: FuturesMarketDetailResponse,
  history: PrototypeData["history"] = [],
) {
  const data: PrototypeData = {
    detail,
    history,
    sources: ["kalshi"],
    related: [],
    capturedAt: "2026-11-04T02:33:00Z",
    historyNote: null,
    settledAt: "2026-11-04T02:27:31Z",
  };
  return renderToStaticMarkup(<Prototype data={data} />);
}

test("field top three retain their served shares of all 24, with the rest reachable", () => {
  const detail = asDetail(field.detail);
  const html = render(detail);
  expect(html).toContain("21 more");
  expect(detail.outcomes).toHaveLength(24);
  expect(html).toContain(">24<");
  expect(html).toContain(">states<");
  expect(html).toContain("Florida");
  expect(html).toContain("Nevada");
  expect(html).toContain("Kansas");
  expect(html).toContain(
    percentText(detail.outcomes.find((o) => o.name === "Nevada")!.probability),
  );
  expect(html).not.toContain("without a price");
});

test("a duel reuses the actual two-sided event hero and chart-card composition", () => {
  const html = render(asDetail(duel.detail));
  expect(html.match(/data-hero-digits=""/g) ?? []).toHaveLength(2);
  expect(html).toContain("Adam Hamilton");
  expect(html).toContain("Roger Marshall");
  expect(html).toContain('data-testid="win-probability-card"');
  expect(html).toContain("Back to Discover");
});

test("the native related-market rail has real destinations", () => {
  const data: PrototypeData = {
    detail: asDetail(field.detail),
    history: [],
    sources: ["kalshi"],
    capturedAt: "2026-11-04T02:33:00Z",
    historyNote: null,
    settledAt: null,
    related: [
      {
        id: 109085,
        name: "Kansas Senate winner",
        lead: "Adam Hamilton",
        probability: 0.98,
        verdict: null,
        sources: ["kalshi", "polymarket"],
      },
    ],
  };
  const html = renderToStaticMarkup(<Prototype data={data} />);
  expect(html).toContain("Bigger Picture");
  expect(html).toContain('href="/kernels-preview/futures/109085"');
});

test("the stored shape survives while a nonexclusive field takes the independent band", () => {
  const detail = asDetail(participation.detail);
  expect(storedShape(detail)).toBe("field");
  expect(bodyKind(detail)).toBe("participation");
  const html = render(detail);
  expect(html).toContain("these do not add to 100%");
  expect(html).toContain("94%");
  expect(
    detail.outcomes.reduce((sum, o) => sum + (o.probability ?? 0), 0),
  ).toBeGreaterThan(1);
});

test("a one-leg retraction produces neither a loss nor an invented second side", () => {
  const detail = asDetail(oneLeg.detail);
  expect(storedShape(detail)).toBe("unshaped");
  expect(payloadVerdict(detail, detail.outcomes[0])).toBeNull();
  const html = render(detail);
  expect(html).toContain("Result unavailable");
  expect(html).toContain("Last recorded");
  expect(html).not.toContain(">Lost<");
  expect(html).not.toContain(">No<");
  expect(html).toContain("1 outcome");
});

test("a real settled grade features the winner and renders result words", () => {
  const detail = asDetail(settled.detail);
  const html = render(detail);
  expect(html).toContain("Keisha Lance Bottoms");
  expect(html).toContain(">Won<");
  expect(html).toContain(">Lost<");
  expect(html).toContain("6:27 PM PT");
  expect(html).not.toContain("100%");
});

test("raw gambling formats cannot leak through an outcome render", () => {
  const detail = asDetail(field.detail);
  const html = render({
    ...detail,
    outcomes: detail.outcomes.map((o) => ({
      ...o,
      american_odds: 87654321,
      opening_american_odds: -87654321,
    })),
  });
  expect(html).not.toContain("87654321");
  expect(html).toContain("Source information reserved");
});

test("whole numbers keep the existing live boundary marks", () => {
  expect(percentText(0.575)).toBe("58%");
  expect(percentText(0.995)).toBe(">99%");
  expect(percentText(0.004)).toBe("<1%");
});

test("the server renders the answer while reader-timezone chart labels wait for the browser", () => {
  const html = render(
    asDetail(field.detail),
    field.history.outcomes as PrototypeData["history"],
  );
  expect(html).toContain("Closest Governor race in 2026");
  expect(html).toContain("Loading probability history");
  expect(html).not.toContain("Recorded chart");
});

test("a stale one-leg study waits for the browser timezone before rendering its exact age stamp", () => {
  const data: PrototypeData = {
    detail: asDetail(oneLeg.detail),
    history: [],
    sources: ["kalshi"],
    related: [],
    capturedAt: "2026-11-04T02:33:00Z",
    historyNote: null,
    settledAt: null,
  };
  const html = renderToStaticMarkup(
    <Prototype data={data} initialStudy="open" />,
  );
  expect(html).toContain("58");
  expect(html).not.toContain('data-testid="price-age-mark"');
  expect(html).not.toContain("Last number:");
});
