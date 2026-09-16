/**
 * #6238, THE SECOND HALF — THE CHART READOUT INVENTED AN AWAY PRICE OUT OF A
 * COMPLEMENT, AND ON A DRAW IT NAMED THE LOSER AT 99%.
 *
 * ux/1266 shipped the hero half of #6238 and named this gap in
 * `aDrawIsNotTheAwayTeamOnWeb6238.test.tsx` rather than leaving it to be
 * rediscovered. This is that gap closed.
 *
 * ═══ THE SPECIMEN, RE-MEASURED ON PRODUCTION BEFORE BUILDING ═══
 *
 * `/events/15305024` — Daejeon Citizen v Pohang Steelers, K League 1,
 * **finished 2–2 on 2026-09-12**. Photographed at 390px on 2026-09-16,
 * `artifacts/ux-1292/BEFORE-6238-chart-420.png`, the readout under the win
 * probability chart:
 *
 *     —      2 - 2      Citizen 1% — Steelers 99%
 *     5:07 AM
 *
 * The issue recorded `Citizen 63% — Steelers 37%`; four days later the same
 * surface reads **99% for Pohang Steelers**, and the page refutes it twice on
 * the way down — "Additional Markets" prints `Tie — Won`, `Daejeon Citizen —
 * Lost`, `Pohang Steelers — Lost`, and the score three inches to the left of
 * the 99% is `2 - 2`.
 *
 * 🔴 THE 99% IS NOT A STALE READING AND NOT A BAD ONE. It is the freshest
 * number the match ever had, and it is *correct arithmetic on the wrong
 * question*. The last blend point is `home_probability 0.01` (measured:
 * `/api/events/15305024/history`, `aggregate_line[-1]`, Kalshi's
 * `Daejeon Citizen` leg of a three-way market). Daejeon really were 1% to WIN a
 * game they were drawing with minutes left. `1 − 0.01` is **"Daejeon do not
 * win"** — away win *or* draw — and the draw was about to take all of it. So no
 * fresher capture and no better source helps: the defect is the subtraction,
 * which is why the fix withholds rather than corrects. `drawPricedWinner.ts`
 * carries the full argument.
 *
 * ═══ WHY A PROP AND NOT A NULL ═══
 *
 * The obvious shape — null `point.awayProb` at the producer, the way native
 * does it (`OddsChartView.swift:1631`) — is wrong on the web for a reason that
 * is documented rather than inherited: `ActiveChartPoint` is also read by
 * `resolveProbability`, where a null away price already means "we hold no
 * reading for this side" and renders an em-dash. Folding "withheld" into that
 * domain would make one value mean two things one layer up, which is the exact
 * mistake `probKnown` exists to undo (#3459). ux/1266 made the same call for
 * the hero — `awayWithheld` is a separate prop there too — so this follows the
 * sibling instead of inventing a second answer.
 *
 * And it is why `GamePlayCard` could never simply be fed a null: line 79 was
 * `awayPct ?? Math.round(point.awayProb * 100)`, a hard re-derivation, so a
 * null renders **`NaN%`**. `TestWithholdingNeverPrintsNaN` is that trap nailed
 * down, because it is the shape the next person will reach for first.
 *
 * Guards run BOTH directions per gotcha #43: a draw-priced sport withholds, and
 * a two-way sport is asserted UNCHANGED against the pre-fix render.
 */
import React from "react";
import { readFileSync } from "fs";
import { join } from "path";
import { renderToStaticMarkup } from "react-dom/server";

import GamePlayCard from "@/components/GamePlayCard";
import { chartTooltipPair } from "@/lib/drawPricedWinner";
import type { ActiveChartPoint } from "@/lib/types";

/** The production specimen, verbatim: 2–2 final, last blend point home 0.01. */
const CITIZEN = "Daejeon Citizen";
const STEELERS = "Pohang Steelers";
const SPECIMEN: ActiveChartPoint = {
  timestamp: "2026-09-12T12:07:00+00:00",
  homeProb: 0.01,
  awayProb: 0.99,
  homeScore: 2,
  awayScore: 2,
  period: null,
  clock: null,
};

/** A two-way control — the sport this issue is not about. */
const CELTICS = "Boston Celtics";
const THUNDER = "Oklahoma City Thunder";
const TWO_WAY: ActiveChartPoint = {
  timestamp: "2026-06-15T20:09:00+00:00",
  homeProb: 0.62,
  awayProb: 0.38,
  homeScore: 101,
  awayScore: 98,
  period: "4",
  clock: "1:09",
};

function render(
  point: ActiveChartPoint,
  homeTeam: string,
  awayTeam: string,
  awayWithheld?: boolean,
) {
  return renderToStaticMarkup(
    React.createElement(GamePlayCard, { activePoint: point, homeTeam, awayTeam, awayWithheld }),
  );
}

/**
 * The readout paragraph's text — every run of characters outside a tag.
 *
 * 🔴 NOT `replace(/<[^>]+>/g, "")`, and this is the repo's standing ruling, not
 * a preference: that is the shape of an HTML sanitizer and CodeQL calls it a
 * high-severity `js/incomplete-multi-character-sanitization`. It refused this
 * ship's first sha exactly as it refused `compactRowNamesItsAnswer4396`'s
 * (alert 2267 there, 2589 here), and a standing gate refusal is not something
 * to argue with in a test helper. The index walk is the same reading with
 * nothing sanitizer-shaped in it. No entity decoding is needed:
 * `renderToStaticMarkup` escapes only `& < > " '`, and none of the strings
 * asserted below contain one.
 */
function visibleText(fragment: string): string {
  let out = "";
  let i = 0;
  for (;;) {
    const open = fragment.indexOf("<", i);
    out += open < 0 ? fragment.slice(i) : fragment.slice(i, open);
    if (open < 0) break;
    const close = fragment.indexOf(">", open);
    if (close < 0) break;
    i = close + 1;
  }
  return out.split(/\s+/).filter(Boolean).join(" ");
}

/** What the reader actually reads in the probability line. */
function readout(html: string): string {
  const marker = 'data-testid="game-play-card-probability"';
  const at = html.indexOf(marker);
  if (at < 0) return "";
  const opens = html.indexOf(">", at);
  const closes = html.indexOf("</p>", opens);
  if (opens < 0 || closes < 0) return "";
  return visibleText(html.slice(opens + 1, closes));
}

describe("#6238 the chart readout withholds the away slot on a draw-priced sport", () => {
  it("the production specimen stops naming Pohang Steelers at 99%", () => {
    const text = readout(render(SPECIMEN, CITIZEN, STEELERS, true));

    // What it said on 2026-09-16, whole and by its halves, so a partial revert
    // cannot pass this.
    expect(text).not.toContain("Steelers 99%");
    expect(text).not.toContain("99%");
    expect(text).not.toContain("Steelers");
    // The separator goes with the slot. #5696's lesson on the hero: a withheld
    // number that leaves its punctuation behind reads `Citizen 1% —` and looks
    // like a load failure rather than a decision.
    expect(text).not.toContain("—");

    // The half we DO hold is still printed, and still named. A lone number has
    // to say whose it is.
    expect(text).toBe("Citizen 1%");
  });

  it("the losing side is not the only thing withheld — the rule is the sport, not the result", () => {
    // Same sport, a decisive-looking mid-game reading. This is the ARM that
    // kills the tempting narrow fix ("only withhold when the scores are level"):
    // the complement is not the away side's chances at ANY moment of a
    // three-way match, level or not.
    const midGame: ActiveChartPoint = { ...SPECIMEN, homeProb: 0.7, awayProb: 0.3, homeScore: 1, awayScore: 0 };
    expect(readout(render(midGame, CITIZEN, STEELERS, true))).toBe("Citizen 70%");
  });

  it("withholding never prints NaN — the trap the null-shaped fix falls into", () => {
    // `GamePlayCard.tsx:79` was `awayPct ?? Math.round(point.awayProb * 100)`.
    // Feed that a null and the reader gets `NaN%`. This asserts over the WHOLE
    // markup, not the readout paragraph, so a NaN leaking into an attribute or
    // a style is caught too.
    const html = render(SPECIMEN, CITIZEN, STEELERS, true);
    expect(html).not.toContain("NaN");
    // Exactly one percent sign survives: the one number we can source.
    expect((html.match(/%/g) || []).length).toBe(1);
  });

  it("the score, clock and period are untouched — only the invented number goes", () => {
    // The withheld slot must not take the rest of the card with it. On the
    // specimen the `2 - 2` beside the 99% is the very thing that refutes it.
    const html = render(SPECIMEN, CITIZEN, STEELERS, true);
    expect(html).toContain(">2<");
    expect(html).toContain("game-play-card-probability");
  });
});

describe("#6238 a two-way sport is UNCHANGED (gotcha #43, the other direction)", () => {
  it("both sides still print when the away price is real", () => {
    const text = readout(render(TWO_WAY, CELTICS, THUNDER, false));
    expect(text).toBe("Celtics 62% — Thunder 38%");
  });

  it("silence means two-sided: an absent prop keeps today's behaviour byte-for-byte", () => {
    // The polarity that makes this rule opt-in. Every caller that predates the
    // prop — and every surface reusing this card — keeps its exact render.
    expect(render(TWO_WAY, CELTICS, THUNDER, undefined)).toBe(
      render(TWO_WAY, CELTICS, THUNDER, false),
    );
  });

  it("a two-way pair is still rounded by the duel rule, not per side (#3295)", () => {
    // 0.615/0.385 rounds to 62/38 through `renderedDuelPercents` and to 62/39
    // through two independent half-up roundings. Pinned here because the
    // withholding branch sits directly on top of that call and a careless
    // rewrite would bypass it.
    const halves: ActiveChartPoint = { ...TWO_WAY, homeProb: 0.615, awayProb: 0.385 };
    expect(readout(render(halves, CELTICS, THUNDER))).toBe("Celtics 62% — Thunder 38%");
  });
});

describe("#6238 the chart's own tooltip prints the same pair, so it takes the same rule", () => {
  /**
   * `OddsChart`'s `CustomTooltip` is the other place on this card that says a
   * team's name beside a percentage: one line per source, plus the blend. It
   * derived the away half as `100 - homeProb` inline — the same subtraction, in
   * a different format, four hundred lines from the readout.
   *
   * Leaving it would have shipped the split this file's own sibling warns
   * about: the readout tensed and its neighbour on the same chart not, in one
   * frame. The rule lives in `drawPricedWinner.ts` with the readout's, so the
   * two cannot drift.
   */
  it("withheld: one named number, no invented opponent", () => {
    expect(chartTooltipPair(CITIZEN, 1, STEELERS, true)).toBe("Daejeon Citizen: 1.0%");
  });

  it("two-way: the pair is unchanged, separator and one decimal included", () => {
    expect(chartTooltipPair(CELTICS, 62.4, THUNDER, false)).toBe(
      "Boston Celtics: 62.4% | Oklahoma City Thunder: 37.6%",
    );
  });

  it("the chart actually calls it — an adopted rule, not an orphaned helper", () => {
    // A helper nothing calls is a docstring. This is the assertion that would
    // have gone red if the tooltip had been left on its inline subtraction.
    const chart = readFileSync(
      join(__dirname, "..", "..", "components", "OddsChart.tsx"),
      "utf8",
    );
    expect(chart).toContain("chartTooltipPair(");
    // …and the inline derivation it replaced is gone, not merely unused.
    expect(chart).not.toMatch(/const awayProb = 100 - homeProb/);
  });
});

describe("#6238 the page hands the card the same answer it gives the hero", () => {
  const PAGE = readFileSync(
    join(__dirname, "..", "..", "app", "events", "[id]", "page.tsx"),
    "utf8",
  );

  it("the readout and the chart are both told, from the page's single derivation", () => {
    // `awaySlotWithheld` is computed ONCE at the top of the page from
    // `sportPricesADraw(event.sport)`. Two derivations of one rule is how the
    // hero and the card came to disagree in the first place.
    expect(PAGE).toMatch(/const awaySlotWithheld = sportPricesADraw\(event\.sport\)/);
    // The card below the chart…
    expect(PAGE).toMatch(/<GamePlayCard[\s\S]{0,900}?awayWithheld=\{awaySlotWithheld\}/);
    // …and BOTH chart instances: the inline one and the fullscreen one. A
    // reader who taps the expand control must not get the old number back.
    expect((PAGE.match(/awayWithheld=\{awaySlotWithheld\}/g) || []).length).toBe(4);
  });
});
