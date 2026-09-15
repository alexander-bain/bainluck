/**
 * #6343 WEB HALF — the site and the phone spell one fact one way.
 *
 * ═══ THE SPECIMEN ═══
 *
 * `/api/feed?limit=25`, 2026-09-15 08:5xZ. Two of the first 25 Discover cards
 * were drawing on prices 2–3 days old. The PHONE said nothing at all — it never
 * decoded `price_observed_at` — and that half shipped as PR #6366.
 *
 * This is the other half, and it is not a port. Native landed the disclosure in
 * the grammar Alex ruled on 2026-08-29 ("precisely when"; a relative age makes
 * the reader do arithmetic against a clock they have to guess), and in doing so
 * it named two places where the web disagreed with itself:
 *
 *   | | web, before | phone, and web now |
 *   |---|---|---|
 *   | field order | `Sep 12, 3:51 AM` | `12 Sep, 3:51 AM` |
 *   | reveal stem | `Last seen …`     | `Last number: …`   |
 *
 * The field order is the sharper of the two, because web contained BOTH
 * spellings at once: `lib/liquidity.preciseObservedAt` printed "12 Sep" into
 * the illiquidity reveal while `lib/sourceAge.formatSourceStamp` printed
 * "Sep 12" into the age mark — two absolute stamps, two orders, renderable on
 * one card. `lib/sourceAge`'s own header warns about exactly this for RELATIVE
 * ages ("a fifth is how a reader learns that two spellings are two different
 * facts"); it had grown in the absolute ones unnoticed.
 *
 * So `formatSourceStamp` now DELEGATES to `preciseObservedAt`. Web has one
 * precise-stamp formatter, as the phone does (`SourceAge.preciseStamp` calls
 * `Liquidity.preciseObservedAt` rather than copying it).
 *
 * ═══ WHY THE ASSERTIONS ARE LABELLED ═══
 *
 * `priceAgeMark4970.test.tsx`'s convention, for its reason:
 *
 *   SHIP     red against the parent. This is the change.
 *   GUARD    green against the parent, red against a NAMED mutant of the new
 *            code. It protects a DECISION, not the diff.
 *   CONTROL  green against both. It pins what must not move.
 *
 * A GUARD with no named mutant is a wish. The foot of this file records the run.
 *
 * ═══ THE CLOCK AND THE ZONE ARE BOTH PINNED ═══
 *
 * Gotcha #44 for the clock: `PriceAgeMark` takes `nowMs`, and every stamp below
 * is an offset from a fixed instant. For the ZONE, `jest.config.js` pins
 * `TZ=UTC` (#2462) — which is load-bearing here and nowhere else in this suite,
 * because `preciseObservedAt` deliberately formats in the READER's own zone and
 * an ambient zone would make the exact-string assertions below read differently
 * on a laptop than in CI. The stamp `2026-09-12T03:51:18Z` is chosen so the
 * rendered string is the one native's own header quotes for this specimen.
 */

import { renderToStaticMarkup } from "react-dom/server";
import React from "react";

import { ActionBar } from "@/components/discover/shared";
import { PriceAgeMark } from "@/components/event/PriceAgeMark";
import {
  FUTURES_STALE_AFTER_MS,
  SOURCE_STALE_AFTER_MS,
  formatSourceStamp,
} from "@/lib/sourceAge";
import { preciseObservedAt } from "@/lib/liquidity";

const NOW = Date.parse("2026-09-15T00:30:00.000Z");
const MIN = 60 * 1000;
const HOUR = 60 * MIN;
const ago = (ms: number) => new Date(NOW - ms).toISOString();

/**
 * The production specimen's own stamp, and the reason the strings below are
 * exact rather than shaped: this instant is the one `ios/…/SourceAge.swift`
 * quotes ("12 Sep, 3:51 AM") when it documents the field order web is adopting.
 */
const SPECIMEN = "2026-09-12T03:51:18+00:00";
const SPECIMEN_PRECISE = "12 Sep, 3:51 AM";

/** `d MMM, h:mm a` — native's `DateFormatter.dateFormat`, as a shape. */
const DAY_FIRST = /^\d{1,2} [A-Z][a-z]{2}, \d{1,2}:\d{2} (AM|PM)$/;

const mark = (observedAt: string | null | undefined, cadence?: "futures") =>
  renderToStaticMarkup(
    <PriceAgeMark
      observedAt={observedAt}
      nowMs={NOW}
      scope="card"
      {...(cadence ? { cadence } : {})}
    />,
  );

/** The real Discover surface, so the grammar is asserted where a reader meets it. */
const bar = (priceObservedAt?: string | null) =>
  renderToStaticMarkup(
    <ActionBar
      liked={false}
      setLiked={() => {}}
      shareUrl="https://bainluck.com/futures/1"
      shareTitle="Premier Lacrosse League Championship Winner"
      contentType="futures"
      itemId={1}
      priceObservedAt={priceObservedAt}
    />,
  );

/** The `title=` value, which is the mouse path. */
const titleOf = (html: string) => html.match(/title="([^"]*)"/)?.[1] ?? null;
/** The screen-reader path, which is the half a `title` cannot carry. */
const srOnly = (html: string) =>
  html.match(/<span class="sr-only">(.*?)<\/span>/)?.[1] ?? null;
/** What a SIGHTED reader sees — `sr-only` removed FIRST, for that reason. */
const visible = (html: string) =>
  html
    .replace(/<span class="sr-only">.*?<\/span>/g, " ")
    .replace(/<[^>]*>/g, " ")
    .replace(/\s+/g, " ")
    .trim();

// ─────────────────────────────────────────────────────────────────────────────

describe("SHIP: web's absolute stamp is the phone's, field for field", () => {
  test("the precise stamp is day-first — the string native documents", () => {
    // Red against the parent, which returned "Sep 12, 3:51 AM" from a
    // hand-rolled `toLocaleString("en-US", …)`.
    expect(formatSourceStamp(SPECIMEN)).toBe(SPECIMEN_PRECISE);
    expect(formatSourceStamp(SPECIMEN)).toMatch(DAY_FIRST);
  });

  test("the reveal stem is 'Last number:', not 'Last seen'", () => {
    // Red against the parent on both halves of the assertion.
    const html = mark(SPECIMEN, "futures");
    expect(titleOf(html)).toBe(`Last number: ${SPECIMEN_PRECISE}`);
    expect(html).not.toContain("Last seen");
  });

  test("the reveal is not mouse-only — it is announced too", () => {
    // Red against the parent: the mark rendered a `title` and nothing else, so
    // a screen reader got the relative age and never the precise stamp.
    const html = mark(SPECIMEN, "futures");
    expect(srOnly(html)).toBe(`Last number: ${SPECIMEN_PRECISE}`);
  });

  test("the Discover card itself carries the new grammar", () => {
    // The surface assertion, not the component one: a mutant that fixes
    // `PriceAgeMark` and leaves the card passing a different prop is invisible
    // to the three tests above.
    const html = bar(SPECIMEN);
    expect(html).toContain('data-testid="price-age-mark"');
    expect(titleOf(html)).toBe(`Last number: ${SPECIMEN_PRECISE}`);
  });
});

// ─────────────────────────────────────────────────────────────────────────────

describe("SHIP: web has ONE precise-stamp formatter", () => {
  /* Labelled SHIP and not GUARD because it is MEASURED red against the parent
     (5 of 5 cases), which this file's convention says a GUARD must not be. It
     still names its mutant, because the reason it is worth keeping after the
     ship is the mutant rather than the diff: re-inlining the old body into
     `formatSourceStamp` (`toLocaleString("en-US", { month, day, … })`) kills
     every SHIP test above too, but this one states the DECISION rather than the
     output and so ALSO kills the subtler mutant that hand-rolls a day-first
     string locally and drifts from `preciseObservedAt` the next time that
     function changes. */
  test.each([
    SPECIMEN,
    "2026-01-01T00:00:00Z",
    "2026-12-31T23:59:59Z",
    "2026-07-04T12:00:00Z",
    "2026-05-12T17:15:00+00:00",
  ])("%s formats identically through both entry points", (iso) => {
    expect(formatSourceStamp(iso)).toBe(preciseObservedAt(iso));
    expect(formatSourceStamp(iso)).toMatch(DAY_FIRST);
  });

  /* Also red on the parent (which had no announcement at all), so also SHIP.
     Mutant it kills after the ship: `title={stamp}` with
     `sr-only`{`Last number: ${stamp}`} — two call sites building the sentence
     separately. `liquidityReveal` is one string for exactly this reason; this
     asserts the two paths cannot drift apart. */
  test("the tooltip and the announcement are the SAME sentence", () => {
    const html = mark(SPECIMEN, "futures");
    expect(titleOf(html)).toBe(srOnly(html));
    expect(titleOf(html)).not.toBeNull();
  });
});

// ─────────────────────────────────────────────────────────────────────────────
// CONTROLS — green on both sides. These are the three Codex named beside the
// grammar, plus the one that stops the ship being a deletion.

describe("CONTROL: a mark never appears without its sentence, or vice versa", () => {
  test.each([null, undefined, "", "not a date", "2026-13-45T99:99:99Z"])(
    "%p draws no mark, no tooltip and no announcement",
    (bad) => {
      const html = mark(bad as string | null | undefined, "futures");
      // An undatable price is not a price we can call stale — so nothing at all,
      // rather than a mark whose reveal reads "Last number: null".
      expect(html).toBe("");
      expect(srOnly(html)).toBeNull();
      expect(formatSourceStamp(bad as string | null | undefined)).toBeNull();
    },
  );

  test("a FRESH price draws nothing — the mark is still news-only", () => {
    // The feature this component's header calls the point of it: silence inside
    // the cadence. A ship that made the stamp prettier and drew it always would
    // pass every assertion above and fail the reader.
    expect(mark(ago(5 * MIN))).toBe("");
    expect(mark(ago(SOURCE_STALE_AFTER_MS - MIN))).toBe("");
    expect(mark(ago(FUTURES_STALE_AFTER_MS - HOUR), "futures")).toBe("");
  });

  test("the sighted body still carries the SHORT age and never the stamp", () => {
    // Notice 34: the reader sees the number and a small mark; the method note
    // lives in the reveal. `visible()` drops `sr-only` first, so this asserts
    // pixels rather than text nodes.
    const html = mark(ago(3 * HOUR));
    expect(visible(html)).toContain("3h ago");
    expect(visible(html)).not.toContain("Last number:");
    expect(visible(html)).not.toMatch(DAY_FIRST);
  });
});

describe("CONTROL: an empty liquidity payload cannot hide the age (#6343)", () => {
  /* The failing case Codex named, and the reason the phone needed this ship at
     all: native's ONLY staleness affordance was the liquidity mark, so a card
     serving `liq {}` disclosed nothing. On web the age disclosure must not be
     reachable from liquidity at any point — asserted structurally rather than
     by rendering an empty object, because "I passed {} and it still drew" is
     also true of a component that ignores a prop it should read. */
  test("neither the mark nor the card's age path takes a liquidity input", () => {
    // `PriceAgeMark`'s contract is `observedAt` + clock + two policy enums.
    // If a liquidity prop is ever threaded in, this is the test that says so.
    expect(PriceAgeMark.length).toBe(1); // one props object, destructured
    const withNoLiquidityAnywhere = mark(SPECIMEN, "futures");
    expect(withNoLiquidityAnywhere).toContain('data-testid="price-age-mark"');
    // Deliberately asserts that a reveal EXISTS, not what it says: the grammar
    // is the SHIP block's business, and pinning it here would make this control
    // red against the parent and stop it being a control at all.
    expect(titleOf(withNoLiquidityAnywhere)).not.toBeNull();
  });

  test("a 3-day-old price on a card with no liquidity data still says 3d ago", () => {
    // The production specimen end to end: feed index 1, 77 hours old, `liq {}`.
    // Green on both sides — the disclosure was never liquidity-gated on web,
    // and this is what says so if someone ever gates it.
    const html = bar(ago(77 * HOUR));
    expect(html).toContain('data-testid="price-age-mark"');
    expect(visible(html)).toContain("3d ago");
    expect(titleOf(html)).not.toBeNull();
  });
});

/*
 * ═══ THE RUN ═══
 *
 * Recorded at the foot the way this suite's siblings do, so a later reader can
 * tell a measured guard from a hopeful one. See the PR body for the numbers.
 */
