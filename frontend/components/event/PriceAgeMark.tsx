"use client";

import {
  SOURCE_STALE_AFTER_MS,
  formatSourceAge,
  formatSourceStamp,
  sourceIsStale,
} from "@/lib/sourceAge";

/**
 * WHEN A PRICE ON A MARKET CARD STOPPED BEING CURRENT (#4970, card half).
 *
 * ═══ IT DRAWS NOTHING ALMOST ALL OF THE TIME, AND THAT IS THE FEATURE ═══
 *
 * The issue is titled "Show when a live probability stops being current", and
 * the mark is written to that sentence rather than to "show how old every
 * number is". It returns `null` for a price inside `SOURCE_STALE_AFTER_MS`, and
 * `null` for a price we cannot date at all.
 *
 * Measured on production 2026-09-12 (latency/342, 2,651 priced legs): the p50
 * age is **17.9 minutes**, which is the poll cadence and not news, and 22.1% of
 * legs are past thirty minutes. So a mark on every row would print "18m ago"
 * four times out of five — the same number, next to every price, telling a
 * reader nothing they can act on. That is precisely the shape notice 34 bans
 * ("a reader sees the number, the small source mark, and at most one short
 * caption") and D102 tempers ("small grey type is fine where it makes sense and
 * offers the reader value"). An age has value exactly when it is surprising.
 *
 * ═══ AND NOTHING ON A ROW WHOSE QUESTION IS ALREADY ANSWERED ═══
 *
 * 🔴 The caller must not render this for a settled or decided row, and
 * `SpecialEventMarkets` does not. A finished game's rows are ALL old — the
 * section already says `settled` once, at the top, and every row already reads
 * `last quote 41%`. Adding "3d ago" to each of them re-states the section
 * header once per row and buries the one case this mark exists for: a LIVE
 * question whose price has gone quiet. Staleness is only news while the answer
 * is still open.
 *
 * ═══ NO SIXTH VOCABULARY ═══
 *
 * The words are `formatSourceAge`'s, unchanged — the same "42m ago" the
 * sportsbook table and `/events/{id}/models` print, and the threshold is the
 * same `SOURCE_STALE_AFTER_MS` those two already share. `lib/sourceAge`'s
 * header counts four hand-rolled age formatters in this repo and explains that
 * a fifth is how a reader learns that two spellings are two different facts;
 * this component adds a PLACE, not a vocabulary.
 *
 * The exact stamp goes in `title`, which is where notice 34 puts a method note
 * — "a tooltip on the source mark" — and never in the page body.
 *
 * ═══ `nowMs` IS AN ARGUMENT ═══
 *
 * Gotcha #44. A guard pins "31 minutes draws, 29 does not" at a fixed instant
 * instead of building stamps relative to whenever the suite runs. Production
 * passes nothing and gets `Date.now()`.
 */
export function PriceAgeMark({
  observedAt,
  nowMs,
  scope = "row",
}: {
  /** The wire's `observed_at`. Absent and null are the same answer here. */
  observedAt: string | null | undefined;
  nowMs?: number;
  /**
   * Is this mark speaking for ONE row or for the whole CARD?
   *
   * It changes no pixel, and it exists because a guard could not tell the two
   * apart without it. `SpecialEventMarkets` may state an age once in the card
   * header (when every live row agrees) or per stale row (when they do not),
   * and a test asserting only "there is one mark" passes for BOTH — measured:
   * the mutant that lets a card speak over a mixed card survived a test written
   * that way. Emitted as `data-scope` so the assertion can name the place.
   */
  scope?: "row" | "card";
}) {
  const now = nowMs ?? Date.now();
  // `sourceIsStale` is FALSE for an undatable stamp, which is the conservative
  // answer and the reason there is no separate absent branch below: a price we
  // cannot date is not a price we can call stale.
  if (!sourceIsStale(observedAt, now)) return null;
  const age = formatSourceAge(observedAt, now);
  // Unreachable while `sourceIsStale` is true — both read the same parse — but
  // the render must not be the thing that discovers they disagreed.
  if (age === null) return null;

  return (
    <span
      className="inline-flex items-center gap-1 text-text-muted"
      data-testid="price-age-mark"
      data-scope={scope}
      data-observed-at={observedAt ?? undefined}
      title={
        formatSourceStamp(observedAt)
          ? `Last seen ${formatSourceStamp(observedAt)}`
          : undefined
      }
    >
      {/* Fixed width, unlike the chip #4251 was filed on: a 5px dot plus a
          bounded age cannot take a market label's line away from it. */}
      <span
        aria-hidden="true"
        className="h-[5px] w-[5px] shrink-0 rounded-full bg-text-muted/60"
      />
      <span className="text-[10px] leading-none whitespace-nowrap">{age}</span>
    </span>
  );
}

export { SOURCE_STALE_AFTER_MS };
