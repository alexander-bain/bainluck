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
 *   5. **The reveal stays SHORT and says none of our arithmetic.** Alex,
 *      2026-08-29, on the version this replaced: *"the mouseover text is way to
 *      verbose. no need to reference buyers and sellers. can just clarify that
 *      the numbers isn't moving and is less reliable."* The bans below are that
 *      ruling with a test around it, because copy that nobody pins grows back.
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

  it("says the number is not moving, that it is less reliable, and when it reached us", () => {
    const sentence = liquidityReveal(
      { liquidity: "thin", liquidity_reasons: ["no_trades_24h"] },
      OBSERVED
    ) as string;
    // ALEX, 2026-08-29, in as many words: *clarify that the number isn't moving
    // and is less reliable*. That is the whole sentence, and this is it.
    expect(sentence).toContain("This number hasn't moved in a while");
    expect(sentence).toContain("treat it as less reliable");
    // ALEX'S EARLIER CONSTRAINT, which survives the trim: "mouse-over reveals
    // precisely when the probability was last updated". An absolute clock time,
    // not "32 hours ago" — the relative age is the phrasing he called ambiguous.
    expect(sentence).toContain("Last number: ");
    expect(sentence).toContain(preciseObservedAt(OBSERVED) as string);
  });

  it("GRADES in words: much less reliable is the hollow mark's half of it", () => {
    const barely = liquidityReveal(
      {
        liquidity: "barely",
        liquidity_reasons: ["no_trades_24h", "spread_exceeds_price"],
      },
      OBSERVED
    ) as string;
    const thin = liquidityReveal(
      { liquidity: "thin", liquidity_reasons: ["no_trades_24h"] },
      OBSERVED
    ) as string;
    expect(barely).toContain("treat it as much less reliable");
    expect(thin).toContain("treat it as less reliable");
    expect(thin).not.toContain("much less");
  });

  it("says ONE reason even when both facts failed — the verbosity Alex cut", () => {
    /**
     * The old sentence listed both, and the second clause bought the reader
     * nothing: two failing facts do not lead to two different responses. The
     * grade carries "worse", not the enumeration.
     */
    const sentence = liquidityReveal(
      {
        liquidity: "barely",
        liquidity_reasons: ["no_trades_24h", "spread_exceeds_price"],
      },
      OBSERVED
    ) as string;
    expect(sentence).toContain("This number hasn't moved in a while");
    expect(sentence).not.toContain("Barely anybody is trading this market");
    expect(sentence).not.toContain(", and ");
    // Short enough to read in a tooltip without scanning: the old one ran past
    // 230 characters on this exact payload.
    expect(sentence.length).toBeLessThan(120);
  });

  it("makes no movement claim for a number marked only on its book", () => {
    /**
     * A market can be quoting an absurd range and still have traded this
     * morning. "Hasn't moved" on that outcome would be a claim we never
     * measured — the over-claim `FRESHNESS_DEFINITION` exists to refuse.
     */
    const sentence = liquidityReveal(
      { liquidity: "thin", liquidity_reasons: ["spread_exceeds_price"] },
      OBSERVED
    ) as string;
    expect(sentence).toContain("Barely anybody is trading this market");
    expect(sentence).not.toContain("hasn't moved");
    expect(sentence).toContain("treat it as less reliable");
  });

  it("carries none of the arithmetic that produced the grade", () => {
    // ALEX'S BAN, 2026-08-29: no buyers, no sellers — and by the same logic no
    // bid, ask or spread, which is the same sportsbook vocabulary arriving by a
    // different door. Ruling 138's `price` stem and ruling 141's venue names
    // are banned here too, for the reasons the definition's own test gives.
    for (const facts of [
      { liquidity: "thin", liquidity_reasons: ["no_trades_24h"] },
      { liquidity: "thin", liquidity_reasons: ["spread_exceeds_price"] },
      {
        liquidity: "barely",
        liquidity_reasons: ["no_trades_24h", "spread_exceeds_price"],
      },
    ]) {
      const sentence = liquidityReveal(facts, OBSERVED) as string;
      expect(sentence).not.toMatch(/\bbuyers?\b|\bsellers?\b/i);
      expect(sentence).not.toMatch(/\bbids?\b|\basks?\b|\bspreads?\b|\bmidpoints?\b/i);
      expect(sentence).not.toMatch(/\b(un)?pric(e|es|ed|ing)\b/i);
      expect(sentence).not.toMatch(/\b(Kalshi|Polymarket)\b/);
      expect(sentence).not.toMatch(/\bstale\b/i);
    }
  });

  it("stays a readable sentence when the reasons are missing or poisoned", () => {
    // The wide-book stem is the fallback because it claims only what being
    // marked already means. It must never fall back to the movement claim.
    const sentence = liquidityReveal(
      { liquidity: "barely", liquidity_reasons: ["not-a-reason"] as string[] },
      OBSERVED
    ) as string;
    expect(sentence).toContain("Barely anybody is trading this market");
    expect(sentence).toContain("treat it as much less reliable");
    expect(sentence).not.toContain("undefined");
    expect(sentence).not.toContain("  ");
  });

  it("drops the timestamp rather than printing a broken one", () => {
    for (const bad of [null, undefined, "", "not-a-date"]) {
      const sentence = liquidityReveal(
        { liquidity: "thin", liquidity_reasons: ["no_trades_24h"] },
        bad
      ) as string;
      expect(sentence).toContain("This number hasn't moved in a while");
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
    // The rendered apostrophe is an entity, so the assertion sits either side
    // of it — a pin that breaks on HTML escaping is a pin on the wrong thing.
    expect(html).toContain("moved in a while");
    expect(html).toContain("much less reliable");
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
    // ALEX, 2026-08-29: no buyers and no sellers, here as well as in the
    // reveal. The key sits under the same grid the tooltip belongs to, so a
    // ban the tooltip keeps and the key breaks is not a ban.
    expect(LIQUIDITY_DEFINITION).not.toMatch(/\bbuyers?\b|\bsellers?\b/i);
    expect(LIQUIDITY_DEFINITION).not.toMatch(/\bbids?\b|\basks?\b|\bspreads?\b/i);
  });

  it("says what the marks mean without teaching the two facts underneath", () => {
    // "One sign of that" and "both" is the whole of what a reader needs to
    // order two symbols; the count's ingredients are ours to carry.
    expect(LIQUIDITY_DEFINITION).toContain("hasn't moved in a while");
    expect(LIQUIDITY_DEFINITION).toContain("less reliable");
    expect(LIQUIDITY_DEFINITION).not.toContain("in the last day");
  });
});
