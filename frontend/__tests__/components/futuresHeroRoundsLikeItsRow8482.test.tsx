// #8482 — the futures hero prints the same number as the row it features.
//
// Production `/futures/61318328` (US x Iran ceasefire continues through
// October 31?), 2026-09-24: the hero read 57% over a Yes row and a Discover card
// both reading 58%. The wire was `0.575`, and the hero rounded it with
// `Math.round(p * 100)` — the #3867 half-point case, where `0.575 * 100` lands
// a hair below 57.5 — while the row went through `renderedPercent`.
//
// Two arms: the hero's own fallback is the contract's rounding, and when the
// page has already decided the row's integer (a two-outcome pair, #2831) the
// hero prints THAT, not a second rounding.
import { readFileSync } from "fs";
import path from "path";
import React from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { FuturesHero } from "../../components/FuturesHero";
import { renderedOutcomeRowPercents, renderedPercent } from "../../lib/renderedPercent";

const CURVE = [0.5, 0.52, 0.55, 0.57, 0.575];

function heroPercents(html: string): string[] {
  return Array.from(html.matchAll(/data-testid="hero-percent"[^>]*>(\d+)</g)).map((m) => m[1]);
}

describe("#8482 — FuturesHero rounds like the row it features", () => {
  test("the specimen is the half-point case: raw rounding says 57, the contract says 58", () => {
    // If this ever stops holding, the tests below stop discriminating.
    expect(Math.round(0.575 * 100)).toBe(57);
    expect(renderedPercent(0.575)).toBe(58);
  });

  test.each([
    ["plain numeral", undefined],
    ["ambient numeral", CURVE],
  ])("%s: wire 0.575 prints 58, and the Yes/No bar agrees", (_label, points) => {
    const html = renderToStaticMarkup(
      <FuturesHero
        name="US x Iran ceasefire continues through October 31?"
        probability={0.575}
        outcomeName="Yes"
        sparklinePoints={points}
      />,
    );
    expect(heroPercents(html)).toEqual(["58"]);
    expect(html).toContain("width:58%");
  });

  test("the row's decided integer wins over a second rounding", () => {
    // A pair summing to 1.01 is normalized once by the row rule: 0.575/1.01 → 57.
    const [yesRow] = renderedOutcomeRowPercents([0.575, 0.435]);
    expect(yesRow).toBe(57);
    expect(renderedPercent(0.575)).not.toBe(yesRow);

    const html = renderToStaticMarkup(
      <FuturesHero name="M" probability={0.575} rendered={yesRow} outcomeName="Yes" />,
    );
    expect(heroPercents(html)).toEqual(["57"]);
  });

  test("a rendered integer never prints without a probability behind it", () => {
    const html = renderToStaticMarkup(
      <FuturesHero name="M" probability={null} rendered={58} outcomeName="Yes" />,
    );
    expect(heroPercents(html)).toEqual([]);
  });

  test("the futures page hands the hero its row's integer", () => {
    const page = readFileSync(
      path.join(__dirname, "../../app/futures/[id]/page.tsx"),
      "utf8",
    );
    expect(page).toMatch(
      /rendered=\{heroOutcome \? renderedById\.get\(heroOutcome\.id\)\?\.current \?\? null : null\}/,
    );
  });
});
