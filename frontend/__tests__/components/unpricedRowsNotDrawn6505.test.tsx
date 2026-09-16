/**
 * #6505 — A DISCOVER CARD DOES NOT DRAW A ROW IT HAS NO NUMBER FOR.
 *
 * ═══ THE DEFECT ═══
 *
 * Production `/api/feed?limit=200`, 2026-09-16 07:2xZ, DOM-read at 390px: five
 * futures cards drew a board whose rows print `—` where the percentage goes.
 * "Velo Point of Sale Growth in September" drew eight rungs and one number.
 *
 * ═══ WHY IT HAS TO BE A RENDER TEST ═══
 *
 * Every assertion a payload test could make about these specimens is true at the
 * broken commit — the rows ARE in `distribution_outcomes` and `threshold_points`,
 * correctly, and the serializer is not what is wrong. The defect is one layer
 * later, in what the card lays out. Same seam as
 * `refusedLadderRendersTheField4610.test.tsx`, which exists for the same reason.
 *
 * ═══ THE FIXTURES ARE THE SERVED PAYLOADS ═══
 *
 * `unpricedRowsNotDrawn6505.json` holds four cards copied verbatim out of that
 * production read, defect included, at the hour the defect was live (the four
 * are three specimens and one control). Nothing here is typed by hand, and
 * nothing here is re-snapshotted later: a fresh capture taken from a fixed tree
 * contains no defect, and the controls below would then pass against nothing.
 *
 * ═══ EVERY ABSENCE IS PAIRED WITH A PRESENCE ═══
 *
 * A card that renders nothing satisfies `not.toContain("—")` perfectly. So every
 * dash assertion is paired with the `data-card-format` marker of the root that
 * must have drawn, and with the number the reader is owed.
 */

import { renderToStaticMarkup } from "react-dom/server";
import React from "react";
import type { FeedFuturesData, FeedItem } from "@/lib/types";
import type { DiscoverGroupedItem } from "@/components/discover/types";

jest.mock("next/navigation", () => ({
  __esModule: true,
  useRouter: () => ({ push: jest.fn(), replace: jest.fn(), prefetch: jest.fn() }),
}));
jest.mock("next/link", () => ({
  __esModule: true,
  default: ({ href, children }: { href: string; children: React.ReactNode }) => (
    <a href={href}>{children}</a>
  ),
}));
jest.mock("next/image", () => ({
  __esModule: true,
  default: ({ alt }: { alt: string }) => <img alt={alt} />,
}));
jest.mock("@/components/Analytics", () => ({
  __esModule: true,
  useAnalyticsContext: () => ({ track: () => {} }),
}));

import DiscoverCard from "../../components/DiscoverCard";
import SERVED from "../fixtures/unpricedRowsNotDrawn6505.json";

type Specimen = { item: Record<string, unknown>; data: Record<string, unknown> };

/** A deep copy, so one test's edit cannot leak into the next. */
function specimen(key: keyof typeof SERVED): Specimen {
  return JSON.parse(JSON.stringify(SERVED[key])) as Specimen;
}

function render(s: Specimen): string {
  const item = { ...s.item, data: s.data as unknown as FeedFuturesData } as unknown as FeedItem;
  return renderToStaticMarkup(
    <DiscoverCard groupedItem={{ type: "item", item } as unknown as DiscoverGroupedItem} />
  );
}

/**
 * The card's value cells, in render order.
 *
 * Read off the cell's own class rather than by scanning for "—" anywhere in the
 * markup: the em-dash also appears in prose and in sibling components, and a
 * substring search over a whole card cannot tell a drawn dash from a mentioned
 * one. A per-text-node probe would be wrong in the other direction — see the
 * leaderboard's number span, which is a single text node by construction.
 */
function valueCells(markup: string): string[] {
  return [...markup.matchAll(/tabular-nums[^>]*>([^<]*)</g)].map((m) => m[1]);
}

/** The rungs drawn by the ladder root, label side. */
const VELO_RUNGS = [
  "Above 175",
  "Above 190",
  "Above 200",
  "Above 210",
  "Above 220",
  "Above 230",
  "Above 250",
];

describe("#6505 — the threshold ladder draws only the rungs it can price", () => {
  it("test_velo_ladder_drops_its_eight_unpriced_rungs", () => {
    const markup = render(specimen("velo_threshold_ladder"));

    // The one rung we hold a price for, with its number and its label — the
    // positive half, first, so an empty render cannot pass this file.
    expect(markup).toContain("Above 240");
    expect(markup).toContain("73%");

    // And the eight blanks are gone.
    for (const rung of VELO_RUNGS) {
      expect(markup).not.toContain(rung);
    }
    expect(valueCells(markup)).not.toContain("—");
  });

  it("keeps the ladder root, because the hero cannot name a threshold rung", () => {
    // The widening this ship makes, stated as the reader's outcome rather than
    // as a constant: with one rung left, the old `>= 2` bar would drop the card
    // to the plain hero, whose served caption for this market is "Resolves
    // within a month" (#4640 refuses a threshold label as a subject). The reader
    // would get a bare 73% with nothing saying 73% of WHAT.
    const markup = render(specimen("velo_threshold_ladder"));
    expect(markup).toContain('data-card-format="heatmap"');
  });

  it("CONTROL: a one-rung ladder that dropped NOTHING keeps the old bar", () => {
    // The widening is scoped to the drop. A market that simply has one rung is
    // the shape the `>= 2` bar was written for and does not change today.
    const one = specimen("velo_threshold_ladder");
    const card = one.data.discover_card as Record<string, unknown>;
    card.threshold_points = (card.threshold_points as Array<Record<string, unknown>>).filter(
      (p) => p.probability != null
    );
    const markup = render(one);
    expect(markup).not.toContain('data-card-format="heatmap"');
  });
});

describe("#6505 — the leaderboard draws only the rows it can price", () => {
  it("test_lacrosse_board_drops_its_zero_priced_rows", () => {
    const markup = render(specimen("premier_lacrosse_distribution"));

    // Two real rows survive, in order, with their numbers.
    expect(markup).toContain('data-card-format="leaderboard"');
    expect(markup).toContain("Philadelphia Waterdogs");
    expect(markup).toContain("Denver Outlaws");
    const ranks = [...markup.matchAll(/aria-label="Rank (\d+)"/g)].map((m) => Number(m[1]));
    expect(ranks).toEqual([1, 2]);

    // The six rows sitting at 0.00 bid / 1.00 ask are not drawn…
    expect(markup).not.toContain("Boston Cannons");
    expect(markup).not.toContain("California Redwoods");
    expect(valueCells(markup)).not.toContain("—");

    // …and they are still counted, so the card does not shrink the field it
    // claims. Six undrawn rows, none of them already in `remaining`.
    expect(markup).toContain("Field and remaining outcomes");
    expect(markup).toContain("+6");
  });

  it("test_nascar_board_with_one_priced_driver_falls_to_its_own_hero", () => {
    // Three of four rows were dashes. One priced row is not a leaderboard, and
    // the bar is NOT widened here — unlike the ladder, this card's caption
    // states its own answer, so nothing the reader needed is lost.
    const markup = render(specimen("nascar_food_city_distribution"));

    expect(markup).not.toContain('data-card-format="leaderboard"');
    expect(markup).not.toContain("Patrick Staropoli");
    expect(markup).not.toContain("Dawson Cram");

    // The paired presence: the answer is still on the card, from the served
    // caption, which is why falling through is acceptable here.
    expect(markup).toContain("Anthony Alfredo");
  });

  it("CONTROL: a board with four priced rows is untouched", () => {
    // The US Open women's card carries four priced rows and four unpriced ones.
    // The unpriced four already sat past the slice (`leaderFirstSlice` sorts
    // them last), so this card must render exactly as it does today — same root,
    // same four names, same rank run. This is the assertion that fails if the
    // filter is widened into something that drops real rows.
    const markup = render(specimen("us_open_women_distribution"));

    expect(markup).toContain('data-card-format="leaderboard"');
    for (const name of ["Sabalenka", "Rybakina", "Gauff", "Eala"]) {
      expect(markup).toContain(name);
    }
    const ranks = [...markup.matchAll(/aria-label="Rank (\d+)"/g)].map((m) => Number(m[1]));
    expect(ranks).toEqual([1, 2, 3, 4]);
  });

  it("CONTROL: a three-row board that dropped NOTHING still falls through", () => {
    // The bend is scoped to "cleared the bar before the drop, not after". A card
    // that was under four rows to begin with is the shape the `>= 4` bar was
    // written for and must not change today — otherwise this ship quietly turns
    // every small field into a leaderboard, which is a different decision than
    // the one #6505 argues for. (The sibling clause, for the REFUSED ladder, is
    // controlled the same way in `refusedLadderRendersTheField4610.test.tsx`.)
    const three = specimen("premier_lacrosse_distribution");
    const card = three.data.discover_card as Record<string, unknown>;
    card.distribution_outcomes = (
      card.distribution_outcomes as Array<{ probability: number | null }>
    )
      .filter((r) => r.probability != null && r.probability > 0)
      .concat([{ label: "Utah Archers", probability: 0.3 } as never]);

    expect(card.distribution_outcomes).toHaveLength(3);
    const markup = render(three);
    expect(markup).not.toContain('data-card-format="leaderboard"');
  });

  it("test_remaining_count_still_counts_every_undrawn_outcome", () => {
    // The count is taken off the UNFILTERED list. Measured on the control, whose
    // backend `remaining_outcome_count` is 17 over 25 outcomes: four drawn, four
    // dropped by this ship, 17 never sent — 21.
    const markup = render(specimen("us_open_women_distribution"));
    expect(markup).toContain("+21");
  });
});

describe("#6505 — RED-FIRST: the specimens really are broken without the filter", () => {
  /**
   * The strawman guard. Each fixture is asserted to CONTAIN the unpriced rows
   * that the tests above prove are not drawn — so if a later capture, a fixture
   * edit, or an upstream serializer change quietly removes them, this file stops
   * being a guard and says so here rather than passing for the wrong reason.
   */
  it("every specimen still carries the unpriced rows the card must refuse", () => {
    const velo = specimen("velo_threshold_ladder").data.discover_card as {
      threshold_points: Array<{ label: string; probability: number | null }>;
    };
    expect(velo.threshold_points.filter((p) => p.probability == null).map((p) => p.label)).toEqual(
      expect.arrayContaining(VELO_RUNGS)
    );

    const lacrosse = specimen("premier_lacrosse_distribution").data.discover_card as {
      distribution_outcomes: Array<{ label: string; probability: number | null }>;
    };
    expect(
      lacrosse.distribution_outcomes.filter((r) => r.probability === 0).map((r) => r.label)
    ).toEqual(
      expect.arrayContaining(["Boston Cannons", "California Redwoods"])
    );

    const nascar = specimen("nascar_food_city_distribution").data.discover_card as {
      distribution_outcomes: Array<{ probability: number | null }>;
    };
    expect(nascar.distribution_outcomes.filter((r) => r.probability == null)).toHaveLength(3);

    const usopen = specimen("us_open_women_distribution").data.discover_card as {
      distribution_outcomes: Array<{ probability: number | null }>;
      remaining_outcome_count: number;
    };
    expect(usopen.distribution_outcomes.filter((r) => r.probability == null)).toHaveLength(4);
    expect(usopen.remaining_outcome_count).toBe(17);
  });
});
