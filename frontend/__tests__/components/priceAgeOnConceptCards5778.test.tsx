/**
 * #5778 — THE CONCEPT CARD SAYS HOW OLD ITS PRICE IS.
 *
 * ═══ THE SPECIMEN ═══
 *
 * The FIRST card on Discover, 390px, 2026-09-12 22:5xZ:
 *
 *     Vuelta a España 2026                              LIVE
 *     Enric Mas Nicolau                                  96%
 *
 * Measured against production (`futures_markets` × `futures_outcomes`,
 * `MAX(last_updated)`), the 184-competitor GC field behind that 96% was last
 * priced 5h 01m earlier; its siblings ran to 15h 58m. Nothing on the card said
 * so and nothing on it COULD — the concept payload carried no stamp at all,
 * while a futures card two screens down had carried one since #5752.
 *
 * ═══ WHY THE ASSERTIONS ARE LABELLED ═══
 *
 * Borrowed from `priceAgeOnFeedCards5752.test.tsx`, for its reason:
 *
 *   SHIP     red against the parent. This is the change.
 *   GUARD    green against the parent, red against a named mutant.
 *   CONTROL  green against both. It pins what must not move.
 *
 * ═══ WHAT THIS FILE ADDS THAT #5752's DOES NOT ═══
 *
 * `ActionBar`'s own behaviour — the 30-minute bar, the shared vocabulary, the
 * undatable case — is #5752's and is not re-proven here. What is new is that
 * the CONCEPT card reaches it: a different component, a different data shape,
 * and one the #5752 adoption scan does not read. The render below therefore
 * drives the real `ConceptCard`, not `ActionBar` directly, because the whole
 * defect was a card that never handed the bar anything.
 *
 * ═══ THE CLOCK ═══
 *
 * Gotcha #44: a fixed instant with every stamp an offset from it, never a
 * wall-clock hour, so the suite cannot decide its own verdict differently at
 * 23:59 than at 00:01.
 */

import { renderToStaticMarkup } from "react-dom/server";
import React from "react";
import fs from "fs";
import path from "path";

import { ConceptCard } from "@/components/discover/ConceptCard";
import { SOURCE_STALE_AFTER_MS } from "@/lib/sourceAge";
import type { FeedConceptData } from "@/lib/types";

const NOW = Date.parse("2026-09-12T22:51:00.000Z");
const MIN = 60 * 1000;
const ago = (ms: number) => new Date(NOW - ms).toISOString();

/** The specimen's own age. */
const SPECIMEN_AGE_MS = 5 * 60 * MIN + 1 * MIN;

let nowSpy: jest.SpyInstance;
beforeEach(() => {
  nowSpy = jest.spyOn(Date, "now").mockReturnValue(NOW);
});
afterEach(() => {
  nowSpy.mockRestore();
});

/** The production shape, verbatim from `GET /api/feed?limit=100` at 22:5xZ. */
const VUELTA: FeedConceptData = {
  key: "event:cycling:vuelta-2026",
  name: "Vuelta a España 2026",
  domain: "cycling",
  status: "live",
  start_date: "2026-08-22",
  is_major: true,
  fight_count: 0,
  entry_count: 9,
  is_marquee: true,
  marquee_whathit: false,
  leader: {
    name: "Enric Mas Nicolau",
    probability: 0.96,
    movement_24h: null,
    field_size: 184,
  },
};

const card = (price_observed_at?: string | null) =>
  renderToStaticMarkup(
    <ConceptCard
      data={{ ...VUELTA, price_observed_at }}
      liked={false}
      setLiked={() => {}}
    />,
  );

const read = (rel: string) =>
  fs.readFileSync(path.join(process.cwd(), rel), "utf8");

describe("#5778 the concept card carries its price age", () => {
  it("SHIP: the specimen card says its price is five hours old", () => {
    // Red against the parent: `ConceptCard` passed `ActionBar` no such prop and
    // `FeedConceptData` had no such field, so this string could not appear on
    // this card for any input.
    const html = card(ago(SPECIMEN_AGE_MS));
    expect(html).toContain('data-testid="price-age-mark"');
    expect(html).toContain("5h ago");
  });

  it("SHIP: the card still prints the number the age is ABOUT", () => {
    // The disclosure is worthless if it replaced the thing it qualifies. The
    // reader must see 96% AND how old it is, not one instead of the other.
    const html = card(ago(SPECIMEN_AGE_MS));
    expect(html).toContain("96%");
    expect(html).toContain("Enric Mas Nicolau");
  });

  it("GUARD: a freshly polled concept says NOTHING", () => {
    // The mark drawing on every card is the D102 / notice-34 failure: the same
    // grey number beside every price, telling a reader nothing they can act on.
    // Silence on a fresh card is the design working.
    expect(card(ago(2 * MIN))).not.toContain('data-testid="price-age-mark"');
  });

  it("GUARD: the boundary is the SHARED one, not a number copied here", () => {
    // A local 30-minute constant would drift from `lib/sourceAge` silently.
    // Driven off the exported threshold so a change there moves this with it.
    expect(card(ago(SOURCE_STALE_AFTER_MS - MIN))).not.toContain(
      'data-testid="price-age-mark"',
    );
    expect(card(ago(SOURCE_STALE_AFTER_MS + MIN))).toContain(
      'data-testid="price-age-mark"',
    );
  });

  it("GUARD: an undatable concept is not a fresh one", () => {
    // Three real backends produce this: golf (plain data, no market object), a
    // concept with no futures market, and tennis's compact cached row. `null`
    // and `undefined` must both draw NOTHING — never "now", never "0m ago".
    for (const value of [null, undefined]) {
      const html = card(value);
      expect(html).not.toContain('data-testid="price-age-mark"');
      expect(html).not.toContain("ago");
    }
  });

  it("CONTROL: a card with no age renders exactly as it did before", () => {
    // The mark sits between two `flex-1` spacers, so an absent one must leave
    // the bar byte-identical. This is what lets #5778 ship without re-shooting
    // every concept card that has nothing to disclose.
    expect(card(null)).toEqual(card(undefined));
  });

  it("CONTROL: Like, Pin and Share survive an age being shown", () => {
    const withAge = card(ago(SPECIMEN_AGE_MS));
    const without = card(null);
    for (const label of ["Like", "Share"]) {
      expect(without).toContain(label);
      expect(withAge).toContain(label);
    }
  });
});

describe("#5778 adoption — the card hands the bar its stamp", () => {
  it("GUARD: every <ActionBar> in ConceptCard passes priceObservedAt", () => {
    // Mutant: delete the prop. Every render assertion above dies too — but only
    // because this card has ONE bar today. The scan is here so that a second
    // `<ActionBar>` added for a settled or whathit layout cannot ship without
    // it, which is precisely how #5752's futures cards drifted across seven
    // sites.
    const code = read("components/discover/ConceptCard.tsx");
    const sites = code.split("<ActionBar").slice(1);
    expect(sites.length).toBeGreaterThan(0);
    for (const site of sites) {
      const props = site.slice(0, site.indexOf("/>"));
      expect(props).toContain("priceObservedAt={data.price_observed_at}");
    }
  });

  it("GUARD: the card reads the shared mark, not a sixth age formatter", () => {
    // `lib/sourceAge`'s header counts four hand-rolled formatters in this repo
    // and explains that a fifth is how a reader learns "5h ago" and "5 hr ago"
    // are two different facts. An inlined formatter here would pass every
    // render assertion above.
    const code = read("components/discover/ConceptCard.tsx");
    expect(code).not.toMatch(/\$\{\w+\}(m|h|d) ago/);
  });

  it("GUARD: the CONCEPT type carries the field, not just some type", () => {
    // 🔴 This assertion was VACUOUS when first written. It read
    // `expect(code).toContain("price_observed_at?: string | null;")` over the
    // whole of `lib/types.ts` — and #5752 had already put that exact line on
    // `FeedFuturesData`, so deleting it from `FeedConceptData` left the test
    // green. A mutant proved it. The scan is now scoped to the interface BLOCK.
    //
    // #2088's rule is what is being pinned: `null` is "checked, and this market
    // cannot be dated"; absent is "a payload built before #5778". Both draw
    // nothing, so the TYPE is the only place they stay distinct — and an
    // optional field typed `string | null` is what lets the backend keep
    // serving the key rather than omitting it.
    const code = read("lib/types.ts");
    const start = code.indexOf("export interface FeedConceptData {");
    expect(start).toBeGreaterThan(-1);
    const block = code.slice(start, code.indexOf("\n}", start));
    expect(block).toContain("price_observed_at?: string | null;");
  });
});
