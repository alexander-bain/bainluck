import React from "react";
import { renderToStaticMarkup } from "react-dom/server";
import Prototype from "@/app/kernels-preview/futures/Prototype";
import { bodyKind, payloadVerdict, percentText, storedShape, type PrototypeData } from "@/app/kernels-preview/futures/_model";
import field from "@/app/kernels-preview/futures/_data/108629.json";
import participation from "@/app/kernels-preview/futures/_data/227.json";
import oneLeg from "@/app/kernels-preview/futures/_data/109918.json";
import settled from "@/app/kernels-preview/futures/_data/108645.json";
import type { FuturesMarketDetailResponse } from "@/lib/types";

jest.mock("@/hooks", () => ({ usePageTracking: jest.fn(), useScrollDepth: jest.fn(), useEngagementTime: jest.fn() }));
jest.mock("@/components/FuturesChart", () => ({ FuturesChart: () => <div>Recorded chart</div> }));

function asDetail(value: unknown) { return value as FuturesMarketDetailResponse; }
function render(detail: FuturesMarketDetailResponse) {
  const data: PrototypeData = { detail, history: [], sources: ["kalshi"], related: [],
    capturedAt: "2026-11-04T02:33:00Z", historyNote: null, settledAt: "2026-11-04T02:27:31Z" };
  return renderToStaticMarkup(<Prototype data={data} />);
}

test("field top three retain their served shares of all 24, with the rest reachable", () => {
  const detail = asDetail(field.detail);
  const html = render(detail);
  expect(html).toContain("21 more");
  expect(html).toContain("24 outcomes");
  expect(html).toContain(percentText(detail.outcomes.find((o) => o.name === "Nevada")!.probability));
  expect(html).not.toContain("without a price");
});

test("the stored shape survives while a nonexclusive field takes the independent band", () => {
  const detail = asDetail(participation.detail);
  expect(storedShape(detail)).toBe("field");
  expect(bodyKind(detail)).toBe("participation");
  const html = render(detail);
  expect(html).toContain("these do not add to 100%");
  expect(html).toContain("94%");
  expect(detail.outcomes.reduce((sum, o) => sum + (o.probability ?? 0), 0)).toBeGreaterThan(1);
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
  const html = render({ ...detail, outcomes: detail.outcomes.map((o) => ({ ...o,
    american_odds: 87654321, opening_american_odds: -87654321 })) });
  expect(html).not.toContain("87654321");
  expect(html).toContain("Source information reserved");
});

test("whole numbers keep the existing live boundary marks", () => {
  expect(percentText(0.575)).toBe("58%");
  expect(percentText(0.995)).toBe(">99%");
  expect(percentText(0.004)).toBe("<1%");
});
