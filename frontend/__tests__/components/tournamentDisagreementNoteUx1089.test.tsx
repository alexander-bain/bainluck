/**
 * UX-1089 — THE NOTE UNDER THE DRAW MAY ONLY COUNT CARDS THAT EXIST.
 *
 * Found by LOOK, on production, on the last weekend of the US Open. The
 * women's Round of 16 drew two cards reading
 *
 *     Naomi Osaka
 *     Elena Rybakina
 *     This match is in the draw with no probability against it. That is not
 *     a statement about whether a venue listed one.
 *
 * and then, one line below the list:
 *
 *     2 matches have numbers that do not agree yet.
 *
 * Both statements are about the SAME two fixtures (Osaka–Rybakina and
 * Jovic–Gauff, `priced: false`, both probabilities `null` in the live
 * payload), and they cannot both be true. A match with no numbers cannot have
 * numbers that disagree.
 *
 * UX-P142 already drew this distinction — "UNPRICED IS NOT INCOHERENT" — and
 * fixed the CARD: `!entry.coherent && entry.priced` chooses the collapsed
 * two-names treatment. The count one screen below kept the older, wider
 * selector (`!entry.coherent`), so the pointer and the thing it points at
 * drifted apart the moment a real unpriced fixture arrived. `build_slate`
 * emits `coherent: false` for an unpriced row, so the drift is not a rare
 * shape: it is what the released main draw looks like before a venue quotes
 * it.
 *
 * The fix is not "add `&& priced` in a second place" — that is the same bug
 * with a longer fuse. Both call sites now ask ONE exported predicate,
 * `showsDisagreement`, so a future change to what counts as a disagreement
 * cannot move the card without moving the note.
 *
 * Hence the third arm below, which is the one that matters: it renders the
 * real component with one of each row and asserts the NUMBER IN THE NOTE
 * EQUALS THE NUMBER OF COLLAPSED CARDS. Pinning each side separately is what
 * let them drift in the first place.
 */

import React from "react";
import { renderToStaticMarkup } from "react-dom/server";

import TournamentMatches from "@/components/tournament/TournamentMatches";
import { matchListFromSlate, showsDisagreement } from "@/lib/matchList";
import type { SlateMatch, SlateSide } from "@/lib/slate";

const countOf = (html: string, needle: string) =>
  (html.match(new RegExp(needle, "g")) ?? []).length;

function side(overrides: Partial<SlateSide> = {}): SlateSide {
  return {
    entity_key: "naomi-osaka",
    display_name: "Naomi Osaka",
    seed: null,
    country: "JP",
    role: "participant",
    probability: 0.6,
    opening_probability: 0.6,
    move: 0,
    raw_probability: 0.6,
    raw_opening_probability: 0.6,
    age_hours: 0.2,
    price_state: "live",
    ...overrides,
  };
}

function match(overrides: Partial<SlateMatch> = {}): SlateMatch {
  return {
    matchup_key: "womens-singles:osaka-vs-rybakina:2026-09-07",
    draw: "womens-singles",
    draw_label: "Women's Singles",
    round: "R16",
    scheduled_date: "2026-09-07T15:00:00+00:00",
    sides: [
      side(),
      side({
        entity_key: "elena-rybakina",
        display_name: "Elena Rybakina",
        country: "KZ",
        probability: 0.4,
        opening_probability: 0.4,
        raw_probability: 0.4,
        raw_opening_probability: 0.4,
      }),
    ],
    coherent: true,
    raw_sum: 1,
    opening_raw_sum: 1,
    probability_is_live: true,
    price_state: "live",
    observed_at: "2026-09-06T04:50:00+00:00",
    age_hours: 0.2,
    freshest_observed_at: "2026-09-06T04:50:00+00:00",
    freshest_age_hours: 0.2,
    stale_sides: [],
    mixed_freshness: false,
    favourite: "naomi-osaka",
    has_moved: false,
    source_count: 1,
    ...overrides,
  };
}

/**
 * The two production rows, reproduced field-for-field from the 2026-09-06
 * 04:55Z `/api/tournaments/us-open` payload: `priced: false`, `coherent:
 * false`, `raw_sum: null`, and `probability: null` on BOTH sides.
 *
 * Written explicitly rather than through a default, because the whole subject
 * of this test is a row with no numbers and a helper that fills numbers in
 * would make every assertion below vacuous.
 */
function unpricedFixture(overrides: Partial<SlateMatch> = {}): SlateMatch {
  return match({
    priced: false,
    coherent: false,
    raw_sum: null,
    opening_raw_sum: null,
    probability_is_live: false,
    favourite: null,
    sides: [
      side({
        probability: null,
        opening_probability: null,
        move: null,
        raw_probability: null,
        raw_opening_probability: null,
      }),
      side({
        entity_key: "elena-rybakina",
        display_name: "Elena Rybakina",
        country: "KZ",
        probability: null,
        opening_probability: null,
        move: null,
        raw_probability: null,
        raw_opening_probability: null,
      }),
    ],
    ...overrides,
  });
}

/** Two quotes that genuinely disagree: priced, and the pair sums to 1.24. */
function disagreeingFixture(overrides: Partial<SlateMatch> = {}): SlateMatch {
  return match({
    matchup_key: "womens-singles:gauff-vs-jovic:2026-09-07",
    priced: true,
    coherent: false,
    raw_sum: 1.24,
    sides: [
      side({ entity_key: "coco-gauff", display_name: "Coco Gauff", probability: 0.86 }),
      side({ entity_key: "iva-jovic", display_name: "Iva Jovic", probability: 0.38 }),
    ],
    ...overrides,
  });
}

describe("UX-1089 — a fixture with no numbers is not a disagreement", () => {
  it("the note does not appear at all when the only odd rows are unpriced", () => {
    const html = renderToStaticMarkup(
      <TournamentMatches
        entries={matchListFromSlate([unpricedFixture(), match({ matchup_key: "womens-singles:swiatek-vs-zheng:2026-09-06" })])}
      />
    );

    // The lie, verbatim off the production screen.
    expect(html).not.toContain("do not agree");
    expect(html).not.toContain('data-testid="match-incoherent-count"');

    // And the row is still fully drawn — this fix must not reach the card,
    // which UX-P142 already got right.
    expect(html).toContain("Naomi Osaka");
    expect(html).toContain("Elena Rybakina");
    expect(html).not.toContain("Naomi Osaka vs Elena Rybakina");
    expect(html).toContain("no probability against it");
  });

  it("a real disagreement keeps its note and its collapsed card", () => {
    const html = renderToStaticMarkup(
      <TournamentMatches entries={matchListFromSlate([disagreeingFixture()])} />
    );

    expect(html).toContain("1 match has");
    expect(html).toContain("do not agree");
    expect(html).toContain('data-testid="match-incoherent"');
    expect(html).toContain("Coco Gauff vs Iva Jovic");
  });

  it("the number in the note equals the number of collapsed cards", () => {
    const html = renderToStaticMarkup(
      <TournamentMatches
        entries={matchListFromSlate([
          unpricedFixture(),
          unpricedFixture({ matchup_key: "womens-singles:mertens-vs-eala:2026-09-07" }),
          disagreeingFixture(),
          match({ matchup_key: "womens-singles:sabalenka-vs-townsend:2026-09-06" }),
        ])}
      />
    );

    // `match-incoherent` is the card treatment; the count is the note. One
    // predicate feeds both, so these two numbers are the same number.
    const cards = countOf(html, 'data-testid="match-incoherent"');
    expect(cards).toBe(1);
    expect(html).toContain(`${cards} match has`);
    expect(html).not.toContain("2 matches have");
    expect(html).not.toContain("3 matches have");
  });
});

describe("UX-1089 — the predicate both call sites share", () => {
  it("is false for an unpriced row and true only for a priced one that disagrees", () => {
    expect(showsDisagreement({ coherent: false, priced: false })).toBe(false);
    expect(showsDisagreement({ coherent: false, priced: true })).toBe(true);
    expect(showsDisagreement({ coherent: true, priced: false })).toBe(false);
    expect(showsDisagreement({ coherent: true, priced: true })).toBe(false);
  });
});
