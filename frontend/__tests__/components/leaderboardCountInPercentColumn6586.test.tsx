/**
 * #6586 — A LEADERBOARD'S REMAINDER ROW DOES NOT PUT A HEADCOUNT IN THE
 * PERCENTAGE COLUMN.
 *
 * ═══ THE DEFECT ═══
 *
 * Production `https://bainluck.com/` at 390px, 2026-09-16 17:20Z. Every
 * leaderboard card's last row rendered `+{remainingCount}` into the same
 * right-hand cell that holds `29%` / `14%` / `10%` / `7%` on the four rows above
 * it, with nothing marking that the unit had changed from a percentage to a
 * headcount:
 *
 *     4  Jesse Love                      7%
 *     5  Field and remaining outcomes   +36     <- 36 DRIVERS
 *
 * ═══ WHY IT IS NOT MERELY AMBIGUOUS ═══
 *
 * That card's field really does hold 39% of the probability. The count printed
 * 36. A reader reading the column as percentages is three points from the truth
 * and has no way to notice. Measured over all 44 leaderboard cards in one
 * `/api/feed?limit=200` pass: 19 counts within 10 points of the share they would
 * be mistaken for, 7 within 3. The two specimens below are the photographed card
 * and the closest collision served that hour — `+40` against a real share of 41%.
 *
 * ═══ WHY THE FIX IS A LABEL AND NOT THE REAL PERCENTAGE ═══
 *
 * Printing the field's true share is not available to this row: `1 - sum(shown)`
 * is NEGATIVE on 6 of those 44 cards while #6583's over-round is unresolved
 * (Sweden coalition -148%, PPA reach-the-final -154%). So the honest move is to
 * say the count in words and leave the percentage column empty, rather than to
 * state a share the card cannot compute.
 *
 * ═══ THE FIXTURE IS THE SERVED PAYLOAD, SNAPSHOTTED WHILE THE DEFECT WAS LIVE ═══
 *
 * `leaderboardCountInPercentColumn6586.json` is two cards copied verbatim from
 * that read, at the hour the defect was on the page. It is never re-snapshotted:
 * a capture taken from a fixed tree contains no defect and the RED-FIRST arm
 * below would then pass against nothing (notice 50).
 *
 * ═══ EVERY ABSENCE IS PAIRED WITH A PRESENCE ═══
 *
 * A card that rendered nothing satisfies "no count in the value column" perfectly,
 * so each absence is paired with the `data-card-format="leaderboard"` marker of
 * the root that must have drawn and with the number the reader is owed.
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
import SERVED from "../fixtures/leaderboardCountInPercentColumn6586.json";

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
 * The remainder row's markup, or "" when the card did not draw one.
 *
 * Sliced off the row's own structural marker rather than by scanning the whole
 * card: the card's prose, its caption and its sibling rows all contain digits,
 * and a substring search over the whole card cannot tell a number printed IN
 * this row from one printed anywhere else on it — which is the only question
 * this file asks.
 */
function remainderRow(markup: string): string {
  const start = markup.indexOf('data-row="field-remainder"');
  if (start === -1) return "";
  const end = markup.indexOf("</div>", start);
  return markup.slice(start, end === -1 ? undefined : end);
}

/** The value cells of the whole card, in render order — the percentage column. */
function valueCells(markup: string): string[] {
  return [...markup.matchAll(/tabular-nums[^>]*>([^<]*)</g)].map((m) => m[1]);
}

describe("#6586 — the remainder row says its own units", () => {
  it("test_nascar_board_says_36_more_and_prints_no_36_in_the_value_column", () => {
    const markup = render(specimen("nascar_oreilly_36_vs_39"));

    // Positive first, and the render path named: an empty card cannot pass.
    expect(markup).toContain('data-card-format="leaderboard"');
    expect(markup).toContain("Justin Allgaier");
    expect(markup).toContain("29%");

    // The count is still told to the reader — this ship moves it, never drops it.
    const row = remainderRow(markup);
    expect(row).toContain("Field and 36 more outcomes");

    // …and it is no longer a bare number sitting in the percentage column.
    expect(row).not.toContain(">+36<");
    expect(valueCells(markup)).not.toContain("+36");
    expect(valueCells(markup)).not.toContain("36");
  });

  it("test_press_secretary_count_40_is_not_printed_where_its_real_share_41_belongs", () => {
    // The closest collision served that hour. The field's true share is 41%; the
    // old row printed +40 into the percentage column, one point off a number the
    // card never computed. This arm is the whole reason the ship is not cosmetic.
    const markup = render(specimen("press_secretary_40_vs_41"));

    expect(markup).toContain('data-card-format="leaderboard"');
    const row = remainderRow(markup);
    expect(row).toContain("Field and 40 more outcomes");
    expect(row).not.toContain(">+40<");
    expect(valueCells(markup)).not.toContain("+40");
  });

  it("test_a_field_of_one_says_outcome_not_outcomes", () => {
    // The count now sits in a sentence, so it takes a plural. #2645 exists
    // because the sibling surface shipped "+1 more outcomes"; this arm is that
    // slip pinned on the surface the count just moved to. Built by trimming the
    // payload to five rows with nothing remaining upstream, so the whole count
    // is the single sent-but-undrawn row: 0 + (5 - 4) = 1.
    const one = specimen("nascar_oreilly_36_vs_39");
    const card = one.data.discover_card as Record<string, unknown>;
    card.distribution_outcomes = (
      card.distribution_outcomes as Array<Record<string, unknown>>
    ).slice(0, 5);
    card.remaining_outcome_count = 0;

    const row = remainderRow(render(one));
    expect(row).toContain("Field and 1 more outcome");
    expect(row).not.toContain("Field and 1 more outcomes");
  });

  it("test_the_remainder_row_occupies_only_two_of_its_three_columns", () => {
    // The structural form of the rule, so a future row that reintroduces ANY
    // right-hand value — a count, a share, a dash — reddens here whatever it is
    // styled as.
    //
    // 🔴 THE FIRST DRAFT OF THIS ARM DID NOT DO THAT, AND A MUTATION RUN SAID SO.
    // It read the percentage column through `valueCells`, which keys on
    // `tabular-nums`. The broken row's `+36` span carried `text-right text-xs
    // font-semibold` and no `tabular-nums` — so the exact defect this file is
    // named for was invisible to it, and it was the one arm of five that PASSED
    // against the restored broken component. A filter that is correct on every
    // cell it examines still lies if something else chooses which cells it
    // examines. Counting the row's own children asks the question directly.
    const markup = render(specimen("nascar_oreilly_36_vs_39"));
    const row = remainderRow(markup);
    expect(row).not.toBe("");
    expect([...row.matchAll(/<span\b/g)]).toHaveLength(2); // rank + label, no value

    // Paired positive: the four rows ABOVE it do still fill the column, so this
    // is a statement about the remainder row and not about an empty board.
    expect(valueCells(markup).filter((c) => c.endsWith("%"))).toEqual([
      "29%",
      "14%",
      "10%",
      "7%",
    ]);
  });

  /**
   * RED-FIRST — the arm that makes the three above load-bearing.
   *
   * At the broken commit the remainder row rendered
   *   <span class="text-right text-xs font-semibold">+36</span>
   * as its third grid child. Reproduced here from the same fixture by rendering
   * that row's old shape, so this file states what it is guarding against rather
   * than only asserting today's output. If `remainderRow` ever stops finding the
   * row, the negatives above go vacuous — and this arm is what catches that,
   * because it proves the slicer finds a row whose content it can read.
   */
  it("RED-FIRST: the old shape is what these assertions would have caught", () => {
    const markup = render(specimen("nascar_oreilly_36_vs_39"));
    const row = remainderRow(markup);

    // The slicer really did isolate a row with content — not an empty string that
    // satisfies every `not.toContain` above for free.
    expect(row.length).toBeGreaterThan(40);
    expect(row).toContain("Field and");

    const broken = row.replace(
      "Field and 36 more outcomes",
      'Field and remaining outcomes</span><span class="text-right text-xs font-semibold">+36'
    );
    // The assertion the fix turns from failing to passing, run against the old
    // markup to prove it discriminates.
    expect(broken).toContain(">+36<");
    expect(row).not.toContain(">+36<");
  });
});
