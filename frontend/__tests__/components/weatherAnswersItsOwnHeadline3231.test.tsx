// ux/1085 (#3231) — /weather answers the question its own headline asks.
//
// 🔴 WHAT A READER SAW. The page opens with the largest type on it posing a
// question — "What are the odds it rains tomorrow?" — and then answered it
// LAST, in the final section before the footer, behind four sections about
// other questions entirely.
//
// 🔴 MEASURED, NOT ARGUED. Production `www.bainluck.com/weather` at 390px,
// deployed commit `2614fbe8`, section offsets read off the live DOM
// (`getBoundingClientRect().top + scrollY`):
//
//     57    hero — "What are the odds it rains tomorrow?"
//     718   GLOBAL TEMPERATURE MAP
//     2016  NATURAL EVENTS
//     3767  CLIMATE DASHBOARD
//     5744  WILD CARDS
//     6558  PRECIPITATION — "Rain & rainfall", the answer
//     8605  page height
//
// The answer began 76% of the way down. Worse, the featured card BESIDE the
// headline answers a different question — on that load, "Where will it rain
// this weekend (Sep 5 - Sep 6)? — 99% — Miami" — so a reader who takes the
// headline at its word gets a weekend number for the wettest city in the
// carousel. That is the page-level shape of ux/1076's bug (a fallback that
// returned the WETTEST CITY's number under an NYC label), which is why the
// fix moves the answer up rather than re-wording the headline to match the
// carousel: re-wording would entrench the mismatch.
//
// 🔴 WHY ORDER AND NOT A PIXEL. jest here runs `testEnvironment: 'node'` —
// there is no layout engine, so no test in this file can measure an offset,
// and one that claimed to would be lying. What a guard CAN pin is the thing
// the offsets are downstream of: composition order. `RainForecast` brings its
// own <section> and SectionHeader, so its POSITION is the whole of its layout
// — pin the position and the 6,558px cannot come back silently.
//
// Every arm below was run red against the pre-fix page (RainForecast last).

import React from "react";
import { renderToStaticMarkup } from "react-dom/server";

// The three analytics hooks the page calls before any conditional return.
// They touch browser globals that do not exist under `testEnvironment: node`,
// and they are not the subject — stub them so the composition can render.
jest.mock("@/hooks", () => ({
  usePageTracking: () => undefined,
  useScrollDepth: () => undefined,
  useEngagementTime: () => undefined,
}));

// Each child is replaced by a marker so the assertion is about ORDER and
// nothing else — a child's own content cannot make an ordering arm pass or
// fail, and no child needs its network payload faked. `jest.mock` factories
// are hoisted above the imports, so each one requires React itself rather
// than closing over the module-scope import.
jest.mock("@/components/weather/WeatherHero", () => ({
  __esModule: true,
  default: () => require("react").createElement("div", { "data-section": "HERO" }, "HERO"),
}));
jest.mock("@/components/weather/TemperatureMap", () => ({
  __esModule: true,
  default: () => require("react").createElement("div", { "data-section": "MAP" }, "MAP"),
}));
jest.mock("@/components/weather/NaturalEvents", () => ({
  __esModule: true,
  default: () => require("react").createElement("div", { "data-section": "NATURAL" }, "NATURAL"),
}));
jest.mock("@/components/weather/ClimateDashboard", () => ({
  __esModule: true,
  default: () => require("react").createElement("div", { "data-section": "CLIMATE" }, "CLIMATE"),
}));
jest.mock("@/components/weather/WildCards", () => ({
  __esModule: true,
  default: () => require("react").createElement("div", { "data-section": "WILD" }, "WILD"),
}));
// RainForecast is the subject AND the module the page imports `SectionHeader`
// from, so the mock has to keep that named export real enough to render the
// two headers the page builds itself.
jest.mock("@/components/weather/RainForecast", () => ({
  __esModule: true,
  default: () => require("react").createElement("div", { "data-section": "RAIN" }, "RAIN"),
  SectionHeader: ({ kicker }: { kicker: string }) =>
    require("react").createElement("div", null, kicker),
}));

import WeatherPage from "@/app/weather/page";

/** Where each section marker appears in the rendered page, in render order. */
function sectionOrder(html: string): string[] {
  return [...html.matchAll(/data-section="([A-Z]+)"/g)].map((m) => m[1]);
}

describe("/weather answers the question its headline asks (#3231)", () => {
  const html = renderToStaticMarkup(React.createElement(WeatherPage));
  const order = sectionOrder(html);

  it("renders every section exactly once, so an ordering arm cannot pass by deletion", () => {
    // Without this, "RAIN comes before MAP" would also be satisfied by a page
    // that had dropped MAP on the floor — a guard that green-lights the wrong
    // repair is worse than no guard.
    // `[...order]` and not `order`: `Array.prototype.sort` sorts IN PLACE, so
    // sorting the shared array here silently reorders the input every arm
    // below reads. That is not hypothetical — it turned three of them red on
    // the first run of this file, and it would have turned them green on a
    // page that was still wrong.
    expect([...order].sort()).toEqual(["CLIMATE", "HERO", "MAP", "NATURAL", "RAIN", "WILD"].sort());
  });

  it("puts the rain answer immediately after the hero that asks for it", () => {
    // The acceptance criterion of #3231 in the only terms this environment can
    // honestly express: nothing about another question stands between the
    // question and its answer.
    expect(order[0]).toBe("HERO");
    expect(order[1]).toBe("RAIN");
  });

  it("no longer answers the headline last", () => {
    // The literal regression. Pre-fix this was the final section before the
    // footer; this arm is the one that reddens if it is ever moved back.
    expect(order[order.length - 1]).not.toBe("RAIN");
    expect(order.indexOf("RAIN")).toBeLessThan(order.indexOf("MAP"));
    expect(order.indexOf("RAIN")).toBeLessThan(order.indexOf("NATURAL"));
    expect(order.indexOf("RAIN")).toBeLessThan(order.indexOf("CLIMATE"));
    expect(order.indexOf("RAIN")).toBeLessThan(order.indexOf("WILD"));
  });

  it("keeps the sections that are not the subject in their existing relative order", () => {
    // Promoting rain is the whole change. If this arm reddens, the diff did
    // more than it said it did.
    const others = order.filter((s) => s !== "RAIN");
    expect(others).toEqual(["HERO", "MAP", "NATURAL", "CLIMATE", "WILD"]);
  });
});
