"use client";

import {
  FUTURES_STALE_AFTER_MS,
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
 * number is". It returns `null` for a price inside its cadence's threshold, and
 * `null` for a price we cannot date at all.
 *
 * ═══ THE THRESHOLD IS THE CADENCE THAT SHOULD HAVE REPLACED THE PRICE (#5843) ═══
 *
 * 🔴 "Almost all of the time" above was FALSE for a futures card for as long as
 * this component has shipped, and the reason was one shared constant. A
 * sportsbook row restamps in minutes, so 30 minutes of silence from one is news.
 * A futures ladder is polled hourly at best, so 30 minutes is HALF its cadence
 * and the mark came on for the back half of every hour. Measured on the
 * Discover page's own paged request, 2026-09-13 10:53Z: **18 of 48** datable
 * cards would draw, against **7** under `cadence`. At the peak twelve minutes
 * earlier it was **30 of 30**, clustered at 50.2–50.4m, against **5**. The
 * counts carry their minute because the population is a sawtooth, not a level —
 * see `FUTURES_STALE_AFTER_MS`.
 *
 * So the threshold is picked by what SHOULD have replaced the number:
 *
 * - `"live"` (the default, `SOURCE_STALE_AFTER_MS`, 30m) — sportsbook rows,
 *   `/events/{id}/models` blocks, and event-page market rows, which
 *   `poll_live_prediction_markets` restamps every 2 minutes.
 * - `"futures"` (`FUTURES_STALE_AFTER_MS`, 6h) — the hourly-polled ladders, on
 *   the backend's own `LIVE_PRICE_STALE` number rather than one tuned here.
 *
 * The default is the pre-#5843 value, so a caller that says nothing is
 * unchanged; only the two futures surfaces pass the second one.
 *
 * ### The live card is why this is a cadence and not just a bigger number
 *
 * A flat 6h would have silenced the specimen `ConceptCard` was filed on — a card
 * under a `● Live` pill whose price had gone quiet — and that card is the single
 * best thing this mark ever draws. It was in the same feed read: **Vuelta a
 * España 2026, `status: "live"`, price 169.6m old**. A live card is on the
 * 2-minute poll, so it keeps the 30-minute bound and still draws, while the
 * twenty-nine `open` ladders beside it at 50 minutes go quiet. Raising one
 * number would have traded the defect for a worse one.
 *
 * ### The measurement, with its population named — because there are THREE
 *
 * An earlier revision of this comment quoted "22.1% on 2,651 priced legs" with no
 * population beside it, which is the one thing a staleness number cannot survive:
 * three independent cuts were taken within days of each other and they disagree by
 * an order of magnitude, entirely because they counted different legs.
 *
 * | cut | population | p50 age | past 30m |
 * |---|---|---|---|
 * | latency/342, 2026-09-12 | 2,651 priced legs, **all states** | 17.9m | 22.1% |
 * | ux/1206 | 717 **live** legs | **3.0m** | — |
 * | latency/346 | 206 legs | — | 28.6% |
 *
 * They are not in conflict and none supersedes the others. A live leg is polled
 * hard and sits at a 3-minute median; the all-states pool is dominated by rows
 * whose game is over and whose price will never move again, which is what drags
 * the median to 17.9m. Quote whichever cut matches the rows your caller actually
 * renders, and say which one you quoted.
 *
 * For THIS component the governing figure is the all-states 17.9m p50, because the
 * mark is placed on market-card rows rather than on the live blend: a mark on every
 * row would print "18m ago" four times out of five — the same number, next to every
 * price, telling a reader nothing they can act on. That is precisely the shape notice 34 bans
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
  cadence = "live",
}: {
  /** The wire's `observed_at`. Absent and null are the same answer here. */
  observedAt: string | null | undefined;
  nowMs?: number;
  /**
   * How often the pipeline SHOULD be replacing this price — see the header.
   *
   * A named pair rather than a raw `staleAfterMs`, for `scope`'s reason one
   * field up: the two values are a policy the repo shares with the backend, and
   * a caller free to pass `45 * 60 * 1000` is a caller free to invent a fourth
   * definition of stale. Emitted as `data-cadence` so a guard can assert which
   * bound a surface actually chose rather than inferring it from a rendered age.
   */
  cadence?: "live" | "futures";
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
  const staleAfterMs =
    cadence === "futures" ? FUTURES_STALE_AFTER_MS : SOURCE_STALE_AFTER_MS;
  // `sourceIsStale` is FALSE for an undatable stamp, which is the conservative
  // answer and the reason there is no separate absent branch below: a price we
  // cannot date is not a price we can call stale.
  if (!sourceIsStale(observedAt, now, staleAfterMs)) return null;
  const age = formatSourceAge(observedAt, now);
  // Unreachable while `sourceIsStale` is true — both read the same parse — but
  // the render must not be the thing that discovers they disagreed.
  if (age === null) return null;

  return (
    <span
      className="inline-flex items-center gap-1 text-text-muted"
      data-testid="price-age-mark"
      data-scope={scope}
      data-cadence={cadence}
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

export { FUTURES_STALE_AFTER_MS, SOURCE_STALE_AFTER_MS };
