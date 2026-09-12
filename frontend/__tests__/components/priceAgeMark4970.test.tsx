/**
 * #4970 CARD HALF — a market card's price says when it stopped being current.
 *
 * ═══ WHY THE ASSERTIONS ARE LABELLED ═══
 *
 * ux/1201 shipped a suite where three of five assertions it had labelled SHIP
 * were green against the parent commit — they were describing behaviour that
 * already existed, so they could never have caught the bug being fixed. The
 * fix is to say, per assertion, what it is for, and to have MEASURED it:
 *
 *   SHIP     red against the parent. This is the change.
 *   GUARD    green against the parent, red against a plausible mutant of the
 *            new code. It protects a DECISION, not the diff.
 *   CONTROL  green against both. It pins what must not move.
 *
 * A GUARD with no named mutant is a wish. Each one below names the mutation it
 * dies to, and the file's foot records the run.
 *
 * ═══ THE CLOCK IS AN ARGUMENT OR A MOCK, NEVER AMBIENT ═══
 *
 * Gotcha #44: an anchor must not branch on the clock. `PriceAgeMark` takes
 * `nowMs`, so its unit tests pin an instant directly. `SpecialEventMarkets`
 * does not thread one — production should not have to — so the component tests
 * freeze `Date.now` instead of building stamps relative to whenever the suite
 * happens to run.
 */

import { renderToStaticMarkup } from "react-dom/server";
import React from "react";

import SpecialEventMarkets from "../../components/SpecialEventMarkets";
import { PriceAgeMark } from "@/components/event/PriceAgeMark";
import { SOURCE_STALE_AFTER_MS } from "@/lib/sourceAge";
import { buildMarketSection, mergeOutcomes } from "@/lib/otherMarketGroups";
import type { GameMarketsResponse } from "@/lib/api";

/** A fixed instant. Every stamp below is expressed as an offset from it. */
const NOW = Date.parse("2026-09-12T00:30:00.000Z");
const MIN = 60 * 1000;
const HOUR = 60 * MIN;
const ago = (ms: number) => new Date(NOW - ms).toISOString();

/** One market name, so a `buildMarketSection` fixture groups into one card. */
const MKT = "Angels vs Nationals: Number of Home Runs";

/**
 * Three rival outcomes, none of them a two-way market summing to ~1.
 *
 * That shape is deliberate and `specialEventMarketsSettled`'s header explains
 * why: `findWinProbMarkets` strips any two-outcome market summing to ~1 and
 * `isRedundantWithMarketMaps` strips total+over/under, so the obvious fixture
 * renders NOTHING and a suite of absence-assertions passes against an empty
 * string. Every assertion below that expects a mark therefore also proves the
 * card rendered at all.
 */
const ROWS = (observedAt: string | null | undefined) => [
  {
    market_name: "Angels vs Nationals: Number of Home Runs",
    outcome_name: "2 home runs",
    probability: 0.47,
    source: "kalshi",
    ...(observedAt === undefined ? {} : { observed_at: observedAt }),
  },
  {
    market_name: "Angels vs Nationals: Number of Home Runs",
    outcome_name: "3 home runs",
    probability: 0.31,
    source: "kalshi",
    ...(observedAt === undefined ? {} : { observed_at: observedAt }),
  },
  {
    market_name: "Angels vs Nationals: Number of Home Runs",
    outcome_name: "4 home runs",
    probability: 0.05,
    source: "kalshi",
    ...(observedAt === undefined ? {} : { observed_at: observedAt }),
  },
];

function payload(rows: ReturnType<typeof ROWS>): GameMarketsResponse {
  return {
    event_id: 15309635,
    home_team: "Washington Nationals",
    away_team: "Los Angeles Angels",
    home_score: 1,
    away_score: 2,
    status: "live",
    totals: [],
    player_props: [],
    team_totals: [],
    spreads: [],
    period_markets: [],
    matchups: [],
    other: rows,
    pace: null,
  } as unknown as GameMarketsResponse;
}

const render = (
  observedAt: string | null | undefined,
  status = "live",
) =>
  renderToStaticMarkup(
    <SpecialEventMarkets data={payload(ROWS(observedAt))} eventStatus={status} />,
  );

/** Tags stripped, entities decoded — what a reader actually sees. */
const visible = (html: string) =>
  html
    .replace(/<[^>]*>/g, " ")
    .replace(/&#x27;/g, "'")
    .replace(/&quot;/g, '"')
    .replace(/&#x2F;/g, "/")
    .replace(/&amp;/g, "&")
    .replace(/\s+/g, " ")
    .trim();

const MARK = /data-testid="price-age-mark"/g;
const marks = (html: string) => html.match(MARK)?.length ?? 0;
/* WHERE the mark is, not just how many. A count alone cannot tell a card-level
   mark from a row-level one, and the mutant that lets a card speak over a MIXED
   card moves the mark without changing the count — measured, it survived a test
   that counted only. */
const cardMarks = (html: string) => html.match(/data-scope="card"/g)?.length ?? 0;
const rowMarks = (html: string) => html.match(/data-scope="row"/g)?.length ?? 0;

let clock: jest.SpyInstance;
beforeEach(() => {
  clock = jest.spyOn(Date, "now").mockReturnValue(NOW);
});
afterEach(() => clock.mockRestore());

// ─────────────────────────────────────────────────────────────────────────────
// SHIP — red against the parent. There was no mark on these rows at all.
// ─────────────────────────────────────────────────────────────────────────────

describe("SHIP: a live price that has gone quiet says so on the card", () => {
  test("a 42-minute-old card prints its age ONCE, not once per row", () => {
    const html = render(ago(42 * MIN));
    // ONE mark for a three-row card. The count is the assertion: the first cut
    // of this ship marked every row, and on the live slate that was 21 of 21
    // rows — eight identical `41m ago`s down one card. Measured, then changed.
    expect(marks(html)).toBe(1);
    expect(cardMarks(html)).toBe(1);
    expect(rowMarks(html)).toBe(0);
    expect(visible(html)).toContain("42m ago");
    expect(visible(html).match(/42m ago/g)).toHaveLength(1);
  });

  test("the exact stamp is in a tooltip, not in the page body (notice 34)", () => {
    const html = render(ago(3 * HOUR));
    // The body carries the short relative age only …
    expect(visible(html)).toContain("3h ago");
    // … and the absolute time lives in `title`, which notice 34 names as the
    // place a method note may go.
    expect(html).toMatch(/title="Last seen [^"]+"/);
    expect(visible(html)).not.toMatch(/Last seen/);
  });

  /* The OVER half of the threshold. Lives here and not beside its UNDER twin
     because it is red against the parent and the twin is green, and a pair
     filed under one label is how a green assertion gets counted as a catch. */
  test("over the threshold, the mark appears (31 minutes)", () => {
    expect(marks(render(ago(SOURCE_STALE_AFTER_MS + MIN)))).toBe(1);
  });
});

// ─────────────────────────────────────────────────────────────────────────────
// SHIP (lib) — the merge layer. Also red against the parent: `MergedOutcome`
// had no `observedAt` at all, so every one of these read `undefined`.
// ─────────────────────────────────────────────────────────────────────────────

describe("SHIP: a merged outcome is as old as its OLDEST contributor", () => {
  /* The decision, not just the plumbing: newest-wins would let one live venue
     vouch for a row that is mostly stale — the reassuring answer rather than
     the true one. CERT-411 round 2's rule for the tournament cards, applied to
     the same problem one surface over. */
  test("two venues that agree on the price but not on the clock", () => {
    const { outcomes } = mergeOutcomes([
      { label: "2 home runs", probability: 0.47, source: "kalshi", observedAt: ago(2 * MIN) },
      { label: "2 home runs", probability: 0.47, source: "polymarket", observedAt: ago(3 * HOUR) },
    ]);
    expect(outcomes).toHaveLength(1);
    expect(outcomes[0].observedAt).toBe(ago(3 * HOUR));
  });

  /* Mutant: compare the stamps as STRINGS (`s < acc` instead of
     `Date.parse(s) < Date.parse(acc)`).

     THE FIRST VERSION OF THIS TEST DID NOT KILL IT, and the reason is worth
     keeping. It paired "2026-09-12T00:00:00+00:00" against
     "2026-09-11T21:00:00Z" and asserted the second — but those fall on
     different DATES, so lexicographic order and chronological order agree and
     both implementations return the same row. The comment claimed to catch a
     mutant the assertion could not see. MEASURED: it survived; this pair kills
     it.

     A discriminating pair needs the same date and different offsets:
       20:00-04:00  is  2026-09-12T00:00Z   <- later
       23:00+00:00  is  2026-09-11T23:00Z   <- earlier, and the right answer
     String order puts "20:00:00-04:00" first and picks the LATER row.

     ⚠️ HONEST SCOPE: our wire currently serialises `+00:00` uniformly (censused
     over 601 legs, #4970), so this guards a SHAPE rather than a defect anyone
     can see today. It is cheap and it is correct; it is not evidence that a
     string compare is breaking something live. */
  test("mixed UTC offsets are compared as time, not as text", () => {
    const { outcomes } = mergeOutcomes([
      { label: "2 home runs", probability: 0.47, source: "kalshi", observedAt: "2026-09-11T20:00:00-04:00" },
      { label: "2 home runs", probability: 0.47, source: "polymarket", observedAt: "2026-09-11T23:00:00+00:00" },
    ]);
    expect(outcomes[0].observedAt).toBe("2026-09-11T23:00:00+00:00");
  });

  /* Mutant: drop the `Number.isNaN(Date.parse(s))` filter. An unreadable stamp
     would then win the `reduce` and poison a row that has a good one. */
  test("an unreadable stamp is ignored, not preferred", () => {
    const { outcomes } = mergeOutcomes([
      { label: "2 home runs", probability: 0.47, source: "kalshi", observedAt: "not a date" },
      { label: "2 home runs", probability: 0.47, source: "polymarket", observedAt: ago(90 * MIN) },
    ]);
    expect(outcomes[0].observedAt).toBe(ago(90 * MIN));
  });
});

// ─────────────────────────────────────────────────────────────────────────────
// GUARD — green against the parent (which drew nothing anywhere, so every
// "renders no mark" assertion trivially passed). Each names its mutant.
// ─────────────────────────────────────────────────────────────────────────────

describe("GUARD: the mark stays silent everywhere it would be noise", () => {
  /* Mutant: `if (!sourceIsStale(...)) return null` → `if (false) return null`.
     Without this, the p50 live price — 17.9 minutes, the poll cadence — prints
     "17m ago" on every row of every card, four times out of five. */
  test("a fresh price draws nothing at all", () => {
    const html = render(ago(4 * MIN));
    expect(marks(html)).toBe(0);
    expect(visible(html)).not.toMatch(/ago/);
  });

  /* Mutant: move `SOURCE_STALE_AFTER_MS`, in either direction. Gotcha "a TUNED
     constant needs a guard pinning it from BOTH sides" — a one-sided assertion
     lets the threshold drift the way it is not asserted and stays green.
     Only the UNDER half is a guard; the OVER half is the ship, and it is in the
     SHIP block below rather than hidden inside a test labelled GUARD. */
  test("under the threshold, nothing is drawn (29 minutes)", () => {
    expect(marks(render(ago(SOURCE_STALE_AFTER_MS - MIN)))).toBe(0);
  });

  /* THE OTHER DIRECTION, per gotcha #43 — a cap's guard asserts both ways.
     The card may only speak for its rows when they agree. A mutant dropping
     the `staleLive.length === livePriced.length` test would put ONE mark over
     a card holding a four-minute-old row and a three-day-old one, which is
     false about the fresh one (CERT-411 round 2). Measured 0 of 23 cards
     tonight — rare, not impossible, and the mark is a claim either way. */
  test("a MIXED card does not speak for its rows; the stale one speaks alone", () => {
    const html = renderToStaticMarkup(
      <SpecialEventMarkets
        data={payload([
          { market_name: MKT, outcome_name: "2 home runs", probability: 0.47, source: "kalshi", observed_at: ago(4 * MIN) },
          { market_name: MKT, outcome_name: "3 home runs", probability: 0.31, source: "polymarket", observed_at: ago(3 * HOUR) },
          { market_name: MKT, outcome_name: "4 home runs", probability: 0.05, source: "kalshi", observed_at: ago(4 * MIN) },
        ] as ReturnType<typeof ROWS>)}
        eventStatus="live"
      />,
    );
    // Exactly one mark, AND IT IS THE ROW'S. The count alone is not the
    // assertion: with the agreement test removed the card speaks instead and
    // the count is still 1, which is how the first version of this test let
    // that mutant live. `data-scope` is what makes the claim checkable.
    expect(marks(html)).toBe(1);
    expect(cardMarks(html)).toBe(0);
    expect(rowMarks(html)).toBe(1);
    expect(visible(html)).toContain("3h ago");
    expect(visible(html)).not.toContain("4m ago");
    // All three rows still render, so this is not a suppression.
    expect(visible(html)).toContain("47%");
    expect(visible(html)).toContain("31%");
    expect(visible(html)).toContain("5%");
  });

  /* Mutant — AND THE ONE IT ACTUALLY DIES TO IS NOT THE OBVIOUS ONE.
     The obvious mutation is `if (!sourceIsStale(observedAt, now))` →
     `if (observedAt != null && !sourceIsStale(...))`, i.e. letting an undatable
     price through the gate. MEASURED: that mutant SURVIVES, and it survives for
     a good reason — `formatSourceAge` returns null for an undatable stamp and
     the `age === null` bail below it catches the row anyway. So the gate's null
     branch is subsumed.
     Removing BOTH together — the gate's null branch and the bail that subsumes
     it — kills these two, which is what proves the survivor equivalent rather
     than merely unexercised (ux/1201's rule, third outcome). These therefore
     guard the BAIL. Both wire shapes are covered because production emits both:
     the key is absent on completed events, null elsewhere (census on #4970). */
  test.each([
    ["null on the wire", null],
    ["key absent from the wire", undefined],
  ])("a price we cannot date draws nothing — %s", (_label, value) => {
    const html = render(value as string | null | undefined);
    expect(marks(html)).toBe(0);
    // And the card still rendered, so this is not an empty-fixture pass.
    expect(visible(html)).toContain("47%");
  });

  /* THE DECISION THIS FILE EXISTS TO PROTECT.
     Mutant: hoist `<PriceAgeMark>` above the `frozen` early-return in
     `OutcomeBar`, which is the natural "why isn't it showing on settled games?"
     edit. Every row of a finished game is old, the section already says
     `settled` once in its header, and every row already reads `last quote 41%`
     — so a mark per row re-states the header N times and buries the only case
     the mark is for. Asserted for the whole settled vocabulary, not one word,
     because `isSettledStatus` is the predicate and a single spelling would let
     the others regress. */
  test.each(["closed", "completed", "settled", "final", "resolved"])(
    "a settled game shows no age on any row — status %s",
    (status) => {
      const html = render(ago(9 * HOUR), status);
      expect(marks(html)).toBe(0);
      expect(visible(html)).not.toMatch(/ago/);
      // Not an empty render: the settled treatment is present and doing its job.
      expect(visible(html)).toMatch(/last quote/i);
    },
  );
});

describe("GUARD: an undated price is never dated as 'now'", () => {
  /* Mutant: `observedAt: row.observed_at ?? null` -> `?? new Date().toISOString()`
     on the carry path inside `buildMarketSection`. `lib/sourceAge`'s "ABSENT IS
     NOT ZERO": a price we have never observed must not read as one we just
     checked.

     THIS GOES THROUGH `buildMarketSection`, NOT `mergeOutcomes`, AND THAT IS
     THE WHOLE POINT. The first draft called `mergeOutcomes` directly with
     `observedAt: null` and claimed in its own comment to die to this exact
     mutant. MEASURED: it SURVIVED. The `?? null` being mutated lives one layer
     above, on the row-construction path, and a test that hands `mergeOutcomes`
     an already-built row cannot reach it. The comment named a mutant the
     assertion could not see, which is a false promise to the next reader in
     exactly the shape ux/1201 was written about. */
  test("a wire row with no stamp produces an outcome with no stamp", () => {
    const section = buildMarketSection([
      { market_name: MKT, outcome_name: "2 home runs", probability: 0.47, source: "kalshi" },
      { market_name: MKT, outcome_name: "3 home runs", probability: 0.31, source: "kalshi", observed_at: null },
      { market_name: MKT, outcome_name: "4 home runs", probability: 0.05, source: "kalshi" },
    ]);
    const card = section.categories.flatMap((c) => c.cards)[0];
    // Not an empty-fixture pass: the card exists and carries its three rows.
    expect(card.outcomes).toHaveLength(3);
    for (const o of card.outcomes) expect(o.observedAt).toBeUndefined();
  });

  /* The same path in the direction that must keep working. Without this,
     "always undefined" would satisfy the assertion above — the truncated-bound
     shape of a vacuous guard. */
  test("a wire row WITH a stamp carries it through to the outcome", () => {
    const section = buildMarketSection([
      { market_name: MKT, outcome_name: "2 home runs", probability: 0.47, source: "kalshi", observed_at: ago(90 * MIN) },
      { market_name: MKT, outcome_name: "3 home runs", probability: 0.31, source: "kalshi", observed_at: ago(90 * MIN) },
      { market_name: MKT, outcome_name: "4 home runs", probability: 0.05, source: "kalshi", observed_at: ago(90 * MIN) },
    ]);
    const card = section.categories.flatMap((c) => c.cards)[0];
    expect(card.outcomes.map((o) => o.observedAt)).toEqual([
      ago(90 * MIN), ago(90 * MIN), ago(90 * MIN),
    ]);
  });
});

describe("GUARD: PriceAgeMark on its own, with the clock passed in", () => {
  const only = (el: React.ReactElement) => renderToStaticMarkup(el);

  test("it renders nothing rather than an empty wrapper when fresh", () => {
    expect(only(<PriceAgeMark observedAt={ago(MIN)} nowMs={NOW} />)).toBe("");
  });

  /* Mutant: delete the `age === null` bail. It is unreachable while
     `sourceIsStale` and `formatSourceAge` share a parse — but the render must
     not be the thing that discovers they stopped agreeing. */
  test("it never prints the word null", () => {
    for (const stamp of [ago(45 * MIN), ago(50 * HOUR), null, undefined, "nonsense"]) {
      expect(only(<PriceAgeMark observedAt={stamp} nowMs={NOW} />)).not.toMatch(/null/i);
    }
  });
});

// ─────────────────────────────────────────────────────────────────────────────
// CONTROL — green against both. What must not move.
// ─────────────────────────────────────────────────────────────────────────────

describe("CONTROL: nothing else on the card changes", () => {
  test("the printed percentages are untouched by a stale price", () => {
    for (const html of [render(ago(2 * MIN)), render(ago(6 * HOUR))]) {
      expect(visible(html)).toContain("47%");
      expect(visible(html)).toContain("31%");
      expect(visible(html)).toContain("5%");
    }
  });

  test("a fresh live card is byte-identical to one with no stamp at all", () => {
    // The strongest statement of "draws nothing": not merely no mark, but the
    // same markup the component produced before this ship for that row state.
    expect(render(ago(MIN))).toEqual(render(undefined));
  });

  test("no banned word reaches the reader (notice 33)", () => {
    const seen = visible(render(ago(3 * HOUR)));
    for (const banned of ["bookmaker", "bookmakers", "books", "per-bookmaker"]) {
      expect(seen.toLowerCase()).not.toContain(banned);
    }
  });
});

/**
 * ── THE MUTATION RUN, MEASURED 2026-09-12 (ux/1202) ─────────────────────────
 *
 * Labels above are not aspirations. Against the parent `508e098c` six
 * assertions were red; everything else was green and had to earn its place by
 * killing a NAMED mutant. Ten were run:
 *
 *   M1   drop the freshness early-return in `PriceAgeMark`    KILLED (5)
 *   M3   `?? null` -> `?? new Date().toISOString()`           KILLED (1)  *
 *   M4   let an undatable price through the gate              SURVIVED — equivalent  **
 *   M5   newest-wins in `oldestSourceStamp`                   KILLED (2)
 *   M6   compare stamps as text, not as parsed time           KILLED (1)  ***
 *   M7   drop the `Number.isNaN` skip                         KILLED (1)
 *   M8   let a MIXED card speak for all its rows              KILLED (1)  ****
 *   M9   `isLivePriced` ignores `settled`                     KILLED (5)
 *   M10  card speaks when no live row is stale                KILLED (1)
 *
 * (M2, "render the mark above `OutcomeBar`'s frozen return", was run against
 * the first per-row design and killed by 5; the design then moved the mark to
 * the card header and M9 is its successor on the same decision.)
 *
 * ═══ THREE OF THESE SURVIVED THEIR OWN TEST FIRST ═══
 *
 * That is the finding, and it is the reason the run is written down rather
 * than summarised as "mutation tested".
 *
 *   *    M3 survived because its test called `mergeOutcomes` directly and the
 *        `?? null` being mutated lives one layer above, in
 *        `buildMarketSection`. The test now goes through the real carry path.
 *   **   M4 survived alone and is genuinely equivalent: removing it TOGETHER
 *        with the `age === null` bail that subsumes it kills three assertions.
 *        Compound-killed is what distinguishes an equivalent survivor from an
 *        unexercised line (ux/1201's third outcome). The null-safety is real;
 *        it simply lives in the bail rather than in the gate.
 *   ***  M6 survived because the original pair fell on different DATES, where
 *        lexicographic and chronological order agree — both implementations
 *        returned the same row. The pair now differs only by UTC offset.
 *   **** M8 survived because the test counted marks and a count cannot tell a
 *        card-level mark from a row-level one: with the agreement test removed
 *        the mark MOVES from the row to the header and the count stays 1.
 *        `data-scope` was added to the component for no reason other than to
 *        make that claim checkable.
 *
 * Each of the three would have shipped as a green assertion describing a
 * defence that was not there.
 */
