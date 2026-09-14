/**
 * ux/1241 (#5984) — TWO DEFECTS ON ONE ROW OF THE US OPEN MEN'S FINAL.
 *
 * Seen on production at 390px, 20:11Z 2026-09-13, under `Additional Markets`
 * on `/events/15310688`, with the score at 6-3, 6-6 and set 2 heading to a
 * tiebreak:
 *
 *     Zverev won Set 1
 *     Zverev wins Set 2      ▭▭▭▭▭▭ (empty bar)      100%
 *
 * 1. `100%` OVER A PROBABILITY THAT IS NOT 1. The reader's own endpoint —
 *    `GET /api/events/15310688/game-markets`, not the `/api/futures/…` the
 *    issue measured — served that row at `probability: 0.999`, `is_winner:
 *    null`. `OutcomeBar` printed `renderedPercent(prob)`, which is the
 *    cross-runtime ROUNDING contract and deliberately carries no boundary
 *    rule, so an unresolved set was printed to a reader as decided.
 *    `probabilityDisplay` has owned that rule since UX-P046 and its own
 *    docblock already says the two compose. This line took the integer and
 *    skipped the rule.
 *
 * 2. THE BAR WAS NOT EMPTY — IT WAS FULL AND INVISIBLE. The fill for any row
 *    that is not rank 0 was `bg-text-muted/40`, which composites over the
 *    `bg-surface-border` track to 1.30:1. At that contrast a 99.9%-wide fill
 *    and a 0%-wide one are the same picture, so the half of the row a reader
 *    takes in first silently contradicted the number beside it.
 *
 * ── WHY THE CONTRAST ARM COMPUTES AND DOES NOT STRING-MATCH ─────────────────
 *
 * `expect(html).toContain("bg-text-muted")` would pass for any token someone
 * swapped in later, and would red on a rename that changed nothing a reader
 * sees. The property that matters is not the spelling, it is the ORDERING:
 * the non-leader bar must be visible against its own track AND must stay
 * subordinate to the leader's violet. Both directions, per gotcha #43 — the
 * first draft of this fix reached for `text-secondary` because the LABEL in
 * that same row uses it, and at 3.90:1 it is darker than the leader's 2.20:1,
 * so the de-emphasised row would have out-shouted the emphasised one. A fix
 * for invisibility that overshoots into prominence is the same bug facing the
 * other way, and only a computed assertion catches it.
 *
 * The fixture is the verbatim `other[]` of that payload, captured at the time
 * above.
 */

import { renderToStaticMarkup } from "react-dom/server";
import React from "react";

import SpecialEventMarkets from "../../components/SpecialEventMarkets";
import { SETTLED_QUOTE_PREFIX } from "@/lib/settledQuote";
import type { GameMarketsResponse } from "@/lib/api";

const SET2 = "Set 2 Winner: Zverev vs Shelton";
const SET1 = "Set 1 Winner: Zverev vs Shelton";
const MATCH = "US Open ATP: Alexander Zverev vs Ben Shelton";
const SCORE = "Alexander Zverev vs Ben Shelton: Exact Match Score";

/** Verbatim wire, `GET /api/events/15310688/game-markets` at 20:11Z. */
const WIRE = [
  { market_name: SET2, outcome_name: "Yes", probability: 0.999, source: "polymarket", is_winner: null, resolution_source: null },
  { market_name: SET2, outcome_name: "No", probability: 0.0005, source: "polymarket", is_winner: null, resolution_source: null },
  { market_name: SET1, outcome_name: "Yes", probability: 1.0, source: "polymarket", is_winner: true, resolution_source: "api_settlement" },
  { market_name: SET1, outcome_name: "No", probability: null, source: "polymarket", is_winner: false, resolution_source: "api_settlement" },
  { market_name: MATCH, outcome_name: "Yes", probability: 0.915, source: "polymarket", is_winner: null, resolution_source: null },
  { market_name: MATCH, outcome_name: "No", probability: 0.09, source: "polymarket", is_winner: null, resolution_source: null },
  { market_name: "Zverev vs Shelton", outcome_name: "Alexander Zverev", probability: 0.9, source: "kalshi", is_winner: null, resolution_source: null },
  { market_name: "Zverev vs Shelton", outcome_name: "Ben Shelton", probability: 0.1, source: "kalshi", is_winner: null, resolution_source: null },
  { market_name: SCORE, outcome_name: "Alexander Zverev wins 3-0", probability: 0.65, source: "kalshi", is_winner: null, resolution_source: null },
  { market_name: SCORE, outcome_name: "Alexander Zverev wins 3-1", probability: 0.23, source: "kalshi", is_winner: null, resolution_source: null },
  { market_name: SCORE, outcome_name: "Ben Shelton wins 3-2", probability: 0.11, source: "kalshi", is_winner: null, resolution_source: null },
  { market_name: SCORE, outcome_name: "Alexander Zverev wins 3-2", probability: 0.09, source: "kalshi", is_winner: null, resolution_source: null },
  { market_name: SCORE, outcome_name: "Ben Shelton wins 3-0", probability: 0.01, source: "kalshi", is_winner: null, resolution_source: null },
  { market_name: SCORE, outcome_name: "Ben Shelton wins 3-1", probability: 0.01, source: "kalshi", is_winner: null, resolution_source: null },
];

/**
 * WHAT THIS PAYLOAD RENDERS, established by reading the markup rather than by
 * assuming it — three facts that the first draft of this suite got wrong and
 * that every assertion below depends on:
 *
 *   1. The `No` side of a two-sided market NEVER becomes its own row. Labeling
 *      turns the `Yes` into `Zverev wins Set 2` and drops the complement, so
 *      the 0.0005 in the wire above reaches no reader and cannot be the
 *      specimen for the low boundary. See `LOW` below.
 *   2. `Set 1 Winner` is priced at EXACTLY 1.0, so `100%` appears on this card
 *      legitimately. An assertion of `not.toContain("100%")` is therefore
 *      wrong, not strict — the arms below pin the number to its ROW.
 *   3. The `US Open ATP: …` and bare `Zverev vs Shelton` cards are filtered as
 *      redundant with the win-probability hero, so 0.915 and 0.9 never print.
 */

/** The only row on this card that is decided by the score, per `completedSets`. */
const DECIDED = {
  side: "home" as const,
  homeTeam: "Alexander Zverev",
  awayTeam: "Ben Shelton",
};

function payload(other: unknown[] = WIRE): GameMarketsResponse {
  return {
    event_id: 15310688,
    home_team: "Alexander Zverev",
    away_team: "Ben Shelton",
    home_score: 2,
    away_score: 0,
    status: "live",
    totals: [],
    player_props: [],
    team_totals: [],
    spreads: [],
    period_markets: [],
    matchups: [],
    other,
    pace: null,
  } as unknown as GameMarketsResponse;
}

const render = (
  opts: { status?: string; other?: unknown[]; completedSets?: number } = {},
) =>
  renderToStaticMarkup(
    <SpecialEventMarkets
      data={payload(opts.other)}
      eventStatus={opts.status ?? "live"}
      completedSets={opts.completedSets}
      decidedSetsWinner={opts.completedSets ? DECIDED : undefined}
    />,
  );

const visible = (html: string) =>
  html
    .replace(/<[^>]*>/g, " ")
    .replace(/&#x27;/g, "'")
    .replace(/&quot;/g, '"')
    .replace(/&gt;/g, ">")
    .replace(/&lt;/g, "<")
    .replace(/&amp;/g, "&")
    .replace(/\s+/g, " ");

// ── The contrast model, calibrated against the tokens in `app/globals.css` ──
//
// Only the three colours this row can actually draw. A token added to the
// component and not here fails LOUDLY in `ratioForFill` rather than passing by
// default — an allowlist whose miss returns a plausible value is how a guard
// comes to certify a colour nobody measured.
const HEX: Record<string, string> = {
  "surface-border": "#E5E7EB",
  "text-muted": "#9CA3AF",
  "text-secondary": "#6B7280",
  "violet-400": "#A78BFA",
};
const TRACK = "surface-border";

const channel = (c: number) => {
  const s = c / 255;
  return s <= 0.04045 ? s / 12.92 : ((s + 0.055) / 1.055) ** 2.4;
};
const luminance = (hex: string) => {
  const h = hex.replace("#", "");
  const [r, g, b] = [0, 2, 4].map((i) => channel(parseInt(h.slice(i, i + 2), 16)));
  return 0.2126 * r + 0.7152 * g + 0.0722 * b;
};
const contrast = (a: string, b: string) => {
  const [la, lb] = [luminance(a), luminance(b)];
  return (Math.max(la, lb) + 0.05) / (Math.min(la, lb) + 0.05);
};
/** `token` or `token/NN` composited over the track, then measured against it. */
function ratioForFill(cls: string): number {
  const [token, alpha] = cls.split("/");
  const hex = HEX[token];
  if (!hex) throw new Error(`unmeasured bar colour: ${cls}`);
  const a = alpha ? Number(alpha) / 100 : 1;
  const f = [0, 2, 4].map((i) => parseInt(hex.replace("#", "").slice(i, i + 2), 16));
  const t = [0, 2, 4].map((i) => parseInt(HEX[TRACK].replace("#", "").slice(i, i + 2), 16));
  const composited =
    "#" +
    f
      .map((v, i) => Math.round(a * v + (1 - a) * t[i]).toString(16).padStart(2, "0"))
      .join("");
  return contrast(composited, HEX[TRACK]);
}

/** Every bar fill in the markup, in document order, as `bg-` token strings. */
function barFills(html: string): string[] {
  return [...html.matchAll(/class="h-full rounded-full[^"]*?bg-([\w-]+(?:\/\d+)?)"/g)].map(
    (m) => m[1],
  );
}

describe("#5984 arm 1 — a percentage may not claim a boundary its probability is not on", () => {
  test("THE SPECIMEN: the unresolved set prints >99%, where it printed 100%", () => {
    // Pinned to the row, because `100%` is on this card legitimately (fact 2).
    const text = visible(render());
    expect(text).toContain("Zverev wins Set 2 >99%");
    expect(text).not.toContain("Zverev wins Set 2 100%");
  });

  test("and the set that IS decided, priced at exactly 1.0, still says 100%", () => {
    // The two rows sit one above the other on the same card, which is the whole
    // point: the rule has to separate a market quoting certainty from a market
    // quoting 0.999, and both of them are on screen at once.
    //
    // ── #6138 MOVED THIS ROW'S VEHICLE, NOT THIS ROW'S RULE ──────────────────
    // The `Set 1 Winner` row in `WIRE` is verbatim production and carries
    // `is_winner: true, resolution_source: api_settlement`. Since #6138 a graded
    // row states `Won` instead of a price, so on the untouched payload this
    // assertion's specimen no longer prints a percentage at all — it prints the
    // answer, which is the better page and is asserted as such below.
    //
    // The CONTRACT here is the rounding boundary: an exact 1.0 may not be
    // demoted to `>99%` by the rule that demotes 0.999. That contract is
    // untouched and still needs the two rows side by side, so the grade — and
    // ONLY the grade — is declared off for this one assertion. Rewriting the
    // expectation to `Won` instead would delete the boundary test and leave
    // nothing asserting that `>99%` cannot swallow a genuine certainty.
    const ungradedSet1 = WIRE.map((r) =>
      r.market_name === SET1 ? { ...r, is_winner: null, resolution_source: null } : r,
    );
    expect(visible(render({ other: ungradedSet1 }))).toContain("Zverev wins Set 1 100%");
  });

  test("#6138: on the REAL wire that row is graded, so it states the result", () => {
    // The production state the assertion above had to step around, pinned here
    // so the two cannot drift apart silently: the payload is untouched, the row
    // is graded `api_settlement`, and a reader is told who won rather than shown
    // a price of 100% on a set that is over.
    const text = visible(render());
    expect(text).toContain("Zverev wins Set 1 Won");
    expect(text).not.toContain("Zverev wins Set 1 100%");
    // Its ungraded neighbour is untouched — the boundary rule above still runs
    // on a live row, which is what makes the pair meaningful.
    expect(text).toContain("Zverev wins Set 2 >99%");
  });

  test("THE SETTLED ARM OBEYS THE SAME RULE — which is the production state now", () => {
    // The match finished while this was being written, so the card a reader
    // loads today goes through `frozen`, not the live arm. A last quote of
    // 0.999 printed as `100%` is the same false certainty with a prefix in
    // front of it, and the first draft of this fix reached only the live arm.
    const text = visible(render({ status: "completed" }));
    expect(text).toContain(`Zverev wins Set 2 ${SETTLED_QUOTE_PREFIX} >99%`);
    expect(text).not.toContain(`Zverev wins Set 2 ${SETTLED_QUOTE_PREFIX} 100%`);
  });

  test("THE LOW END of the same rule, on a manufactured row", () => {
    // DECLARED: this value is not in the wire. The complement that WAS priced
    // 0.0005 is dropped by labeling before it reaches a reader (fact 1), so the
    // low boundary has no natural specimen on this payload and the row is made
    // by hand. The wire's genuine floor is 0.01, asserted in the same breath so
    // the arm cannot pass by moving everything small to `<1%`.
    const text = visible(
      render({
        other: WIRE.map((r) =>
          r.outcome_name === "Ben Shelton wins 3-0" ? { ...r, probability: 0.0005 } : r,
        ),
      }),
    );
    expect(text).toContain("Ben Shelton wins 3-0 <1%");
    expect(text).toContain("Ben Shelton wins 3-1 1%");
  });
});

describe("#5984 arm 1, the other direction — nothing that is not on a boundary moves", () => {
  test("ordinary rows print exactly the integer they printed before", () => {
    const text = visible(render());
    for (const printed of [
      "Alexander Zverev wins 3-0 65%",
      "Alexander Zverev wins 3-1 23%",
      "Ben Shelton wins 3-2 11%",
      "Alexander Zverev wins 3-2 9%",
      "Ben Shelton wins 3-0 1%",
    ]) {
      expect(text).toContain(printed);
    }
  });

  test("the #3867 rounding contract survives — 0.565 prints 57, not 56", () => {
    // `formatProbabilityPercent` rounds with `renderedPercent` internally. If a
    // later edit swapped in `Math.round(p * 100)` the boundary arms above would
    // all still pass and this value alone would move.
    const text = visible(
      render({
        other: WIRE.map((r) =>
          r.market_name === SCORE && r.outcome_name === "Alexander Zverev wins 3-0"
            ? { ...r, probability: 0.565 }
            : r,
        ),
      }),
    );
    expect(text).toContain("Alexander Zverev wins 3-0 57%");
    expect(text).not.toContain("Alexander Zverev wins 3-0 56%");
  });

  test("the boundaries themselves stay sayable: an exact 0 and an exact 1", () => {
    // The rule is about values STRICTLY inside the interval. A market quoting a
    // true 0 or a true 1 must still be able to say so, or the fix has replaced
    // one false statement with another.
    const text = visible(
      render({
        other: [
          { market_name: SCORE, outcome_name: "Alexander Zverev wins 3-0", probability: 1, source: "kalshi", is_winner: null, resolution_source: null },
          { market_name: SCORE, outcome_name: "Alexander Zverev wins 3-1", probability: 0, source: "kalshi", is_winner: null, resolution_source: null },
          { market_name: SCORE, outcome_name: "Ben Shelton wins 3-2", probability: 0.4, source: "kalshi", is_winner: null, resolution_source: null },
        ],
      }),
    );
    expect(text).toContain("Alexander Zverev wins 3-0 100%");
    expect(text).toContain("Alexander Zverev wins 3-1 0%");
    expect(text).not.toContain(">99%");
    expect(text).not.toContain("<1%");
  });
});

describe("#5984 arm 2 — a de-emphasised bar still has to be a picture of a quantity", () => {
  test("every fill the component can draw is one this suite has measured", () => {
    // Guards the allowlist itself: a new token added to `OutcomeBar` and not to
    // `HEX` throws here instead of quietly skipping the two arms below.
    const fills = barFills(render());
    expect(fills.length).toBeGreaterThan(0);
    for (const f of fills) expect(() => ratioForFill(f)).not.toThrow();
  });

  test("a non-leader fill is visible against its own track", () => {
    // `bg-text-muted/40` was 1.30:1 — the defect. Anything at or below 1.5:1 is
    // a bar a reader cannot read a quantity off at 6px.
    const fills = barFills(render());
    const nonLeader = fills.filter((f) => f !== "violet-400");
    expect(nonLeader.length).toBeGreaterThan(0);
    for (const f of nonLeader) expect(ratioForFill(f)).toBeGreaterThan(2);
  });

  test("THE OTHER DIRECTION: and never louder than the leader it sits under", () => {
    // `text-secondary` at 3.90:1 passes the arm above and inverts the card's
    // hierarchy against the leader's 2.20:1. Both bounds or neither.
    const fills = barFills(render());
    const leader = ratioForFill("violet-400");
    for (const f of fills.filter((x) => x !== "violet-400")) {
      expect(ratioForFill(f)).toBeLessThan(leader);
    }
  });

  test("THE SPECIMEN'S SHAPE: the card whose only live row is not rank 0", () => {
    // Why the men's final looked worse than the measurement suggests. Rank 0 is
    // the card's emphasised row, but a row that has RESOLVED draws no bar at
    // all — so on a card reading `Zverev won Set 1` / `Zverev wins Set 2` the
    // single bar on screen was a de-emphasised one, with no violet anywhere to
    // compare it against. That is the worst case for an invisible fill, and it
    // is the one Alex was looking at.
    const html = render({
      other: WIRE.filter((r) => r.market_name === SET1 || r.market_name === SET2),
      completedSets: 1,
    });
    // Set 1 is over and names its winner, so it renders as a RESULT and draws
    // no bar; set 2 is still being played and is the only bar on the card.
    expect(visible(html)).toContain("Zverev won Set 1");
    const fills = barFills(html);
    expect(fills).toEqual(["text-muted"]);
    expect(ratioForFill(fills[0])).toBeGreaterThan(2);
  });
});
