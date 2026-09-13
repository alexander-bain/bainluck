/**
 * #5752 — EVERY MARKET CARD SAYS HOW OLD ITS PRICE IS.
 *
 * ═══ THE SPECIMEN ═══
 *
 * `bainluck.com/events/15310026`, the US Open women's final, live, 390px,
 * 2026-09-12 20:48Z. The hero said
 *
 *     Sabalenka  40%  –  60%  Rybakina      Live · Bain Luck blend · 20s
 *
 * and two screens down, under `MORE TENNIS`,
 *
 *     US Open Women's Singles Winner
 *       Aryna Sabalenka                     59%
 *
 * One question — a knockout final's winner IS the match winner — two answers,
 * nineteen points apart, and nothing on either card said which was current.
 *
 * It was a LAG, not a freeze, and that is what makes it a disclosure bug rather
 * than a pricing one: re-reading both in ONE command showed the market
 * repricing to 0.345 against a hero of 34%. At the moment of the screenshot its
 * price was 61 minutes old and had been set 20 minutes BEFORE the match
 * started, while the hero beside it restamped every 20 seconds.
 *
 * ═══ WHY THE ASSERTIONS ARE LABELLED ═══
 *
 * Borrowed from `priceAgeMark4970.test.tsx`, for its reason: ux/1201 shipped a
 * suite whose "SHIP" assertions were green against the parent, so they could
 * never have caught the bug. Per assertion:
 *
 *   SHIP     red against the parent. This is the change.
 *   GUARD    green against the parent, red against a named mutant of the new
 *            code. It protects a DECISION.
 *   CONTROL  green against both. It pins what must not move.
 *
 * ═══ THE ADOPTION HALF IS NOT OPTIONAL ═══
 *
 * 🔴 An absence-only suite ("no card renders an undated price") passes on a
 * DELETION — a card that stopped rendering its field entirely satisfies it
 * while showing a reader nothing. Worse here: there are SEVEN `<ActionBar>`
 * sites across `FuturesCard` and `ComparisonCard`, and a mutant that drops
 * `priceObservedAt` from six of them leaves every render test below green,
 * because they exercise whichever format their fixture happens to pick. The
 * source scan at the foot is the assertion that dies to that mutant, and it is
 * the reason this file reads two components as TEXT as well as rendering them.
 *
 * ═══ THE CLOCK ═══
 *
 * Gotcha #44. `PriceAgeMark` takes `nowMs` and its own suite pins an instant;
 * these components do not thread one, so `Date.now` is frozen rather than
 * stamps being built relative to whenever the suite runs.
 */

import { renderToStaticMarkup } from "react-dom/server";
import React from "react";
import fs from "fs";
import path from "path";

import { ActionBar } from "@/components/discover/shared";
import { FUTURES_STALE_AFTER_MS, SOURCE_STALE_AFTER_MS } from "@/lib/sourceAge";

/** A fixed instant. Every stamp below is an offset from it. */
const NOW = Date.parse("2026-09-12T20:48:00.000Z");
const MIN = 60 * 1000;
const ago = (ms: number) => new Date(NOW - ms).toISOString();

/**
 * The specimen's own age: 61 minutes.
 *
 * 🔴 #5843 MOVED THIS BAR OFF THE 30-MINUTE BOUND AND 61 MINUTES NO LONGER
 * DRAWS ON IT. That is not this specimen being abandoned — the specimen is a
 * card on the `MORE TENNIS` rail, which is `RelatedByTag`, and that surface
 * DELIBERATELY keeps the 30-minute bound (see its comment and the adoption
 * guard at the foot of this file). What moved is the Discover action bar, where
 * the same 30 minutes put the mark on 30 of 30 cards at once.
 *
 * So the constant below is kept and still exercised — against the rail, and as
 * the live-cadence case — and the bar's own assertions moved to a futures age.
 */
const SPECIMEN_AGE_MS = 61 * MIN;

/** Past the 6h futures bound: what a Discover ladder must be before it speaks. */
const STALE_FUTURES_AGE_MS = 7 * 60 * MIN;

let nowSpy: jest.SpyInstance;
beforeEach(() => {
  nowSpy = jest.spyOn(Date, "now").mockReturnValue(NOW);
});
afterEach(() => {
  nowSpy.mockRestore();
});

const bar = (priceObservedAt?: string | null, priceStatus?: string | null) =>
  renderToStaticMarkup(
    <ActionBar
      liked={false}
      setLiked={() => {}}
      shareUrl="https://bainluck.com/futures/1"
      shareTitle="US Open Women's Singles Winner"
      contentType="futures"
      itemId={1}
      priceObservedAt={priceObservedAt}
      priceStatus={priceStatus}
    />,
  );

describe("#5752 the Discover action bar carries the card's price age", () => {
  it("SHIP: a ladder priced seven hours ago says so", () => {
    // Red against the parent: `ActionBar` had no such prop and rendered no mark
    // for any input, so this string could not appear.
    const html = bar(ago(STALE_FUTURES_AGE_MS));
    expect(html).toContain('data-testid="price-age-mark"');
    expect(html).toContain("7h ago");
  });

  it("SHIP: the mark speaks for the CARD, not for one row", () => {
    // `scope` changes no pixel and exists so a guard can name the place — see
    // `PriceAgeMark`'s own header. A mutant passing `scope="row"` from the bar
    // would claim one row's age for a card holding four prices.
    expect(bar(ago(STALE_FUTURES_AGE_MS))).toContain('data-scope="card"');
  });

  it("GUARD: a card priced a minute ago says NOTHING", () => {
    // Mutant: drop the freshness early-return in `PriceAgeMark`, or pass the
    // stamp through a formatter that always prints. Green against the parent
    // (which rendered no mark at all), red against that mutant.
    expect(bar(ago(1 * MIN))).not.toContain('data-testid="price-age-mark"');
  });

  it("GUARD: the boundary is the 6h futures one, and it is the SHARED constant", () => {
    // Mutant: a local `6 * 60 * 60 * 1000` in the component instead of
    // `FUTURES_STALE_AFTER_MS`. The two would agree today and drift the first
    // time the backend's `STALE_PRICE_HOURS` moves — which is the whole subject
    // of `lib/sourceAge`'s header. Asserting either side of the shared constant
    // dies to a second copy that has been edited.
    expect(bar(ago(FUTURES_STALE_AFTER_MS + MIN))).toContain("price-age-mark");
    expect(bar(ago(FUTURES_STALE_AFTER_MS - MIN))).not.toContain("price-age-mark");
  });

  it("SHIP: #5843 — the hourly cluster that wore the mark 30-of-30 is silent", () => {
    // THE DEFECT, at its measured size. Every datable card in the cache built
    // 2026-09-13 10:41Z sat at 50.2–50.4m, because they are polled together on
    // an hourly beat and crossed a 30-minute line together. Red against the
    // parent at every one of the ages below.
    //
    // The ages, not one age, because the population is a SAWTOOTH: the same
    // page reads 7, 32 or 9 marks depending on the minute of the hour, so an
    // assertion pinned to a single age would be green for a mutant that moved
    // the bound to anywhere else inside the hour.
    for (const mins of [31, 45, 50, 59, 61, 120, 359]) {
      expect(bar(ago(mins * MIN))).not.toContain("price-age-mark");
    }
  });

  it("GUARD: a LIVE card keeps the 30-minute bound", () => {
    // Mutant: pass `cadence="futures"` unconditionally from the bar, or drop
    // the `priceStatus === "live"` arm. `ConceptCard`'s specimen is a live
    // concept whose price had gone quiet — Vuelta a España 2026 at 169.6m in
    // that same feed read — and a flat 6h silences exactly it.
    expect(bar(ago(SPECIMEN_AGE_MS), "live")).toContain("price-age-mark");
    expect(bar(ago(SPECIMEN_AGE_MS), "live")).toContain('data-cadence="live"');
    // ...and it is the SHARED 30 minutes, not a third number.
    expect(bar(ago(SOURCE_STALE_AFTER_MS + MIN), "live")).toContain("price-age-mark");
    expect(bar(ago(SOURCE_STALE_AFTER_MS - MIN), "live")).not.toContain("price-age-mark");
  });

  it("GUARD: an absent status is treated as a futures ladder, not as live", () => {
    // Mutant: `priceStatus !== "open" ? "live" : "futures"`, or any default that
    // falls to the 30-minute arm. A caller that forgets the prop would then
    // reproduce the 30-of-30 defect silently, which is the one way this fix
    // regresses without any assertion above noticing.
    for (const missing of [undefined, null, "open", "resolved", "LIVE", ""]) {
      const html = bar(ago(50 * MIN), missing as string | null | undefined);
      expect(html).not.toContain("price-age-mark");
    }
    // `"LIVE"` above is deliberate: the payload's value is lowercase, and a
    // case-insensitive match here would be a second liveness rule.
    expect(bar(ago(STALE_FUTURES_AGE_MS))).toContain('data-cadence="futures"');
  });

  it("GUARD: an undatable price is not a fresh one", () => {
    // "ABSENT IS NOT ZERO" (`lib/sourceAge`'s header). A market we have never
    // observed, and a payload from before this shipped, must both draw nothing
    // — never "just now", which is what a `?? Date.now()` fallback would give.
    for (const missing of [null, undefined, "", "not a date"]) {
      const html = bar(missing as string | null | undefined);
      expect(html).not.toContain("price-age-mark");
      expect(html).not.toMatch(/NaN|Invalid|just now/i);
    }
  });

  it("CONTROL: Like and Share are untouched when there is no age to show", () => {
    // The mark sits between two `flex-1` spacers, so an absent mark must leave
    // the bar byte-identical to the one every non-futures card still renders.
    expect(bar(null)).toBe(bar(undefined));
    expect(bar(null)).toContain("Like");
    expect(bar(null)).toContain("Share");
  });

  it("CONTROL: showing an age takes nothing away from the bar", () => {
    const html = bar(ago(STALE_FUTURES_AGE_MS));
    expect(html).toContain("Like");
    expect(html).toContain("Share");
  });
});

/**
 * ═══ THE SOURCE SCAN ═══
 *
 * These read the components as TEXT because the defect they catch is one that
 * no render of a single fixture can see: a format that quietly stops passing
 * the stamp. `FuturesCard` alone has four `<ActionBar>` sites (ladder,
 * threshold, binary, default) and the format chosen depends on
 * `discover_card.suggested_format` and the outcome arity, so a fixture proves
 * one of them and says nothing about the other three.
 */
const read = (rel: string) =>
  fs.readFileSync(path.join(__dirname, "..", "..", rel), "utf8");

describe("#5752 adoption — every futures card format hands the bar its stamp", () => {
  const FILES = [
    "components/discover/FuturesCard.tsx",
    "components/discover/ComparisonCard.tsx",
  ];

  it.each(FILES)("GUARD: every <ActionBar> in %s passes priceObservedAt", (rel) => {
    // Mutant: delete `priceObservedAt={data.price_observed_at}` from any ONE
    // site. Every render assertion above stays green; this one dies.
    const code = read(rel);
    const sites = code.split("<ActionBar").slice(1);
    expect(sites.length).toBeGreaterThan(0);
    for (const site of sites) {
      // Up to the element's close — enough to hold its whole prop list.
      const props = site.slice(0, site.indexOf("/>"));
      expect(props).toContain("priceObservedAt={data.price_observed_at}");
    }
  });

  it.each(FILES)("GUARD: every <ActionBar> in %s also passes priceStatus (#5843)", (rel) => {
    // Mutant: add the cadence to the bar but wire `priceStatus` at only the
    // format a fixture happens to render. The stamp and the cadence are two
    // props now, and an age shown against the WRONG bound is worse than no age
    // — so the adoption scan has to cover both or it half-covers the ship.
    const code = read(rel);
    for (const site of code.split("<ActionBar").slice(1)) {
      const props = site.slice(0, site.indexOf("/>"));
      expect(props).toContain("priceStatus={data.status}");
    }
  });

  it("GUARD: the bar renders the shared mark, not a sixth age formatter", () => {
    // `lib/sourceAge`'s header counts four hand-rolled formatters in this repo
    // and explains that a fifth is how a reader learns that "40m ago" and
    // "40 min ago" are two different facts. A mutant that inlines
    // `${mins}m ago` here would pass every render assertion above.
    const code = read("components/discover/shared.tsx");
    expect(code).toContain("<PriceAgeMark");
    expect(code).toMatch(/import \{ PriceAgeMark \} from "@\/components\/event\/PriceAgeMark"/);
    expect(code).not.toMatch(/\$\{\w+\}m ago/);
  });

  it("GUARD: the rail the issue was filed on draws the same mark", () => {
    // `RelatedByTag` IS the `MORE TENNIS` grid in the specimen. It is not a
    // Discover card and inherits nothing from `ActionBar`, so a change that
    // fixed only the feed would leave the reported page exactly as it was.
    const code = read("components/RelatedByTag.tsx");
    expect(code).toContain("<PriceAgeMark");
    expect(code).toContain("d.price_observed_at");
  });

  it("GUARD: #5843 left the rail on the 30-minute bound ON PURPOSE", () => {
    // Mutant: a tidy-up that "makes the rail consistent with the feed" by
    // passing `cadence="futures"` here too. It reads like removing a leftover
    // and it silences THIS FILE'S specimen — the 61-minute card sitting two
    // screens under a hero that restamps every 20 seconds. The reasoning is in
    // the component's own comment; this is the assertion that makes deleting it
    // cost something. Six rows beside a live hero is not thirty cards on a cold
    // open, and the rail is the one place an age is what ranks two answers to
    // one question.
    const code = read("components/RelatedByTag.tsx");
    const site = code.slice(code.indexOf("<PriceAgeMark"));
    expect(site.slice(0, site.indexOf("/>"))).not.toContain("cadence");
  });
});

/**
 * ═══ MUTATION RUN (one at a time, baseline restored green between each) ═══
 *
 * Baseline 11/11 green before and after each, so every failure below is
 * attributable to its own mutation.
 *
 *   M1  drop the freshness early-return in `PriceAgeMark`        KILLED (2)
 *   M2  `priceObservedAt` not forwarded from `ActionBar`         KILLED (3)
 *   M3  remove the prop from ONE of the four `FuturesCard` sites KILLED (1) —
 *       and 0 of the render assertions, which is why the scan exists
 *   M4  `scope="row"` instead of `"card"`                        KILLED (1)
 *   M5  `observedAt={priceObservedAt ?? <a stale now>}`          KILLED (1)
 *   M6  drop `<PriceAgeMark>` from `RelatedByTag`                KILLED (1)
 */
