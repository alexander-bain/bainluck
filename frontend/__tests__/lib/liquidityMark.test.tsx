/**
 * UX-P157 — the illiquidity mark: the words, the glyph, and the three reveals.
 *
 * The backend owns the GRADE and `backend/tests/test_market_liquidity_ux157.py`
 * guards it. This file guards the half a reader actually meets, and every case
 * below is a sentence someone could read on the page:
 *
 *   1. **Silence is the default.** `traded` and `unknown` draw nothing. A mark
 *      on every number is furniture, and `unknown` in particular must stay
 *      silent — we cannot mark what a venue publishes nothing to check.
 *   2. **The reveal answers "precisely when".** Alex's constraint, verbatim.
 *      The relative age is the thing he already called ambiguous.
 *   3. **The non-hover paths exist and say the same sentence.** A phone has no
 *      hover and neither does a keyboard; `liquidityReveal` returns ONE string
 *      so the four disclosure mechanisms cannot drift apart.
 *   4. **It never crashes a grid.** A poison payload is an unmarked cell, not a
 *      thrown render — one bad cell must not blank 336 of them.
 */

import React from "react";
import { renderToStaticMarkup } from "react-dom/server";

import LiquidityMark from "@/components/LiquidityMark";
import {
  LIQUIDITY_DEFINITION,
  isMarked,
  liquidityReveal,
  preciseObservedAt,
  readLiquidity,
} from "@/lib/liquidity";

const OBSERVED = "2026-08-27T21:14:00.000Z";

describe("readLiquidity fails closed", () => {
  it("keeps the four known levels", () => {
    for (const level of ["traded", "thin", "barely", "unknown"] as const) {
      expect(readLiquidity(level)).toBe(level);
    }
  });

  it("reads anything it does not recognise as unknown, never as a mark", () => {
    // A mark invented from a value we do not understand is indistinguishable,
    // on the page, from one the backend measured.
    for (const bad of [null, undefined, 42, {}, [], "illiquid", "THIN"]) {
      expect(readLiquidity(bad)).toBe("unknown");
      expect(isMarked(readLiquidity(bad))).toBe(false);
    }
  });

  it("is silent for both non-marking levels", () => {
    expect(isMarked("traded")).toBe(false);
    expect(isMarked("unknown")).toBe(false);
    expect(isMarked("thin")).toBe(true);
    expect(isMarked("barely")).toBe(true);
  });
});

describe("the reveal", () => {
  it("says nothing at all for a traded or uncheckable number", () => {
    expect(liquidityReveal({ liquidity: "traded" }, OBSERVED)).toBeNull();
    expect(liquidityReveal({ liquidity: "unknown" }, OBSERVED)).toBeNull();
    expect(liquidityReveal({}, OBSERVED)).toBeNull();
  });

  it("names the level, the reason, and precisely when the number reached us", () => {
    const sentence = liquidityReveal(
      { liquidity: "thin", liquidity_reasons: ["no_trades_24h"] },
      OBSERVED
    );
    expect(sentence).toContain("Thinly traded");
    expect(sentence).toContain("nobody has traded it in the last day");
    expect(sentence).toContain("Treat this as a rough guide.");
    // ALEX'S CONSTRAINT: "mouse-over reveals precisely when the probability was
    // last updated". An absolute clock time, not "32 hours ago" — the relative
    // age is the phrasing he called ambiguous in the first place.
    expect(sentence).toContain("Last number: ");
    expect(sentence).toContain(preciseObservedAt(OBSERVED) as string);
  });

  it("names BOTH reasons when both are true", () => {
    const sentence = liquidityReveal(
      {
        liquidity: "barely",
        liquidity_reasons: ["no_trades_24h", "spread_exceeds_price"],
      },
      OBSERVED
    ) as string;
    expect(sentence).toContain("Barely traded");
    expect(sentence).toContain("nobody has traded it in the last day");
    expect(sentence).toContain(
      "the gap between what buyers offer and what sellers want is wider than the number itself"
    );
    expect(sentence).toContain("little more than a guess");
  });

  it("stays a readable sentence when the reasons are missing or poisoned", () => {
    const sentence = liquidityReveal(
      { liquidity: "barely", liquidity_reasons: ["not-a-reason"] as string[] },
      OBSERVED
    ) as string;
    expect(sentence).toContain("Barely traded.");
    expect(sentence).not.toContain("undefined");
    expect(sentence).not.toContain("  ");
  });

  it("drops the timestamp rather than printing a broken one", () => {
    for (const bad of [null, undefined, "", "not-a-date"]) {
      const sentence = liquidityReveal(
        { liquidity: "thin", liquidity_reasons: ["no_trades_24h"] },
        bad
      ) as string;
      expect(sentence).toContain("Thinly traded");
      expect(sentence).not.toContain("Last number");
      expect(sentence).not.toContain("Invalid Date");
    }
  });

  it("never claims the market traded at that moment", () => {
    /**
     * We do not receive trades. The timestamp is when a probability last
     * reached us, and `tournamentProps.FRESHNESS_DEFINITION` exists because
     * over-claiming here is the easy mistake. "Last number" is deliberate.
     */
    const sentence = liquidityReveal(
      { liquidity: "thin", liquidity_reasons: ["no_trades_24h"] },
      OBSERVED
    ) as string;
    expect(sentence).not.toMatch(/last traded at|changed hands|last trade/i);
  });
});

describe("the glyph", () => {
  const marked = {
    liquidity: "barely",
    liquidity_reasons: ["no_trades_24h", "spread_exceeds_price"],
  };

  it("renders nothing for a traded or uncheckable number", () => {
    expect(
      renderToStaticMarkup(<LiquidityMark facts={{ liquidity: "traded" }} />)
    ).toBe("");
    expect(
      renderToStaticMarkup(<LiquidityMark facts={{ liquidity: "unknown" }} />)
    ).toBe("");
    expect(renderToStaticMarkup(<LiquidityMark facts={{}} />)).toBe("");
  });

  it("grades: the thin ring is half filled and the barely ring is hollow", () => {
    const thin = renderToStaticMarkup(
      <LiquidityMark
        facts={{ liquidity: "thin", liquidity_reasons: ["no_trades_24h"] }}
      />
    );
    const barely = renderToStaticMarkup(<LiquidityMark facts={marked} />);

    // Both draw the ring — the constant that makes the fill read as a
    // QUANTITY rather than as two unrelated icons.
    expect(thin).toContain("<circle");
    expect(barely).toContain("<circle");
    // Only the thin one carries the semicircle fill. Emptier is thinner.
    expect(thin).toContain("<path");
    expect(barely).not.toContain("<path");
    expect(thin).toContain('data-level="thin"');
    expect(barely).toContain('data-level="barely"');
  });

  it("is a focusable button that announces the sentence", () => {
    const html = renderToStaticMarkup(
      <LiquidityMark facts={marked} observedAt={OBSERVED} />
    );
    // A tooltip nobody can focus is a tooltip half the readers do not have.
    expect(html).toContain("<button");
    expect(html).toContain('type="button"');
    expect(html).toContain("aria-label=");
    expect(html).toContain("Barely traded");
    // …and the mouse path is on the same element.
    expect(html).toContain("title=");
  });

  it("is inert chrome when the surface already carries the sentence", () => {
    /**
     * The grid case. Its cell `title` and `sr-only` text already include the
     * reveal, so a focusable control here would add up to 336 tab stops to the
     * bracket, each announcing what the cell just read out — and a focusable
     * control inside an `aria-hidden` wrapper is a defect in its own right.
     */
    const html = renderToStaticMarkup(
      <LiquidityMark facts={marked} observedAt={OBSERVED} size="sm" decorative />
    );
    expect(html).not.toContain("<button");
    expect(html).toContain('aria-hidden="true"');
    // The mouse still gets an answer.
    expect(html).toContain("title=");
  });

  it("draws the same glyph at both sizes", () => {
    const sm = renderToStaticMarkup(
      <LiquidityMark facts={marked} size="sm" decorative />
    );
    const md = renderToStaticMarkup(
      <LiquidityMark facts={marked} size="md" decorative />
    );
    // One 24-unit viewBox, scaled — not two hand-tuned paths that happen to
    // look alike.
    expect(sm).toContain('viewBox="0 0 24 24"');
    expect(md).toContain('viewBox="0 0 24 24"');
    expect(sm).toContain('width="8"');
    expect(md).toContain('width="10"');
  });
});

describe("the definition line", () => {
  it("says that an unmarked number has not been cleared", () => {
    // GOTCHA #53 in one clause. Where a venue publishes nothing to check, we
    // cannot mark — so silence is a limit on us, not a verdict on the market.
    expect(LIQUIDITY_DEFINITION).toContain("no mark");
    expect(LIQUIDITY_DEFINITION).toContain("not been able to question");
  });

  it("teaches both glyphs so the key and the mark cannot drift", () => {
    expect(LIQUIDITY_DEFINITION).toContain("half mark");
    expect(LIQUIDITY_DEFINITION).toContain("hollow mark");
  });

  it("carries no banned trading vocabulary", () => {
    // Ruling 138: the `price` stem is banned outright — the word is
    // PROBABILITY. Ruling 141: no venue name is the subject of reader copy.
    expect(LIQUIDITY_DEFINITION).not.toMatch(/\b(un)?pric(e|es|ed|ing)\b/i);
    expect(LIQUIDITY_DEFINITION).not.toMatch(/\b(Kalshi|Polymarket)\b/);
    expect(LIQUIDITY_DEFINITION).not.toMatch(/\bstale\b/i);
  });
});
