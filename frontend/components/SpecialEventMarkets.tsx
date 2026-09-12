"use client";

import { useMemo } from "react";
import type { GameMarketsResponse } from "@/lib/api";
import {
  buildMarketSection,
  FALLBACK_CATEGORY,
  MAX_CARDS_PER_CATEGORY,
  MAX_OUTCOMES_PER_CARD,
  type DecidedSetsWinner,
  type MarketCard,
  type TennisSetsWon,
} from "@/lib/otherMarketGroups";
import {
  isSettledStatus,
  SETTLED_SECTION_NOTE_NO_QUOTES,
  SETTLED_QUOTE_PREFIX,
} from "@/lib/settledQuote";
import { isPregameStatus } from "@/lib/propDivergence";
import { renderedPercent } from "@/lib/renderedPercent";
import { PriceAgeMark } from "@/components/event/PriceAgeMark";
import { oldestSourceStamp, sourceIsStale } from "@/lib/sourceAge";

interface SpecialEventMarketsProps {
  data: GameMarketsResponse;
  eventStatus?: string;
  /**
   * Sets already played out, for a match still in progress. The event page
   * passes it for tennis only; everything else leaves it undefined and no row
   * changes. See `buildMarketSection`'s `completedSets`.
   */
  completedSets?: number;
  /**
   * Who took those sets, when the score can say — so a decided row can state
   * the result instead of a frozen price. Tennis only; see
   * `decidedSetsWinnerFor`.
   */
  decidedSetsWinner?: DecidedSetsWinner | null;
  /**
   * The per-side set tally, so an exact-match-score row the board has already
   * ruled out stops carrying a price. Tennis only; see `tennisSetsWonFor`.
   */
  setsWon?: TennisSetsWon | null;
}

/**
 * Is this row still carrying a LIVE price?
 *
 * The two early returns in `OutcomeBar` decide this today and #4970 needs the
 * same answer one layer up, in `PropMiniCard`, to know whether a card's age can
 * be stated once for the whole card. Named here rather than re-derived there,
 * because a card that disagrees with its own rows about which of them are live
 * is the failure this whole section keeps re-learning (#2086).
 */
function isLivePriced(
  outcome: MarketCard["outcomes"][0],
  settled: boolean,
): boolean {
  if (outcome.result) return false;
  return !(settled || outcome.decided === true);
}

function OutcomeBar({
  outcome,
  rank,
  settled,
  /**
   * Draw this row's own age mark. False when the CARD is speaking for all of
   * its rows — see `PropMiniCard`.
   */
  showAge = false,
}: {
  outcome: MarketCard["outcomes"][0];
  rank: number;
  /** #2086: the game is over, so this number is a frozen quote, not a chance. */
  settled: boolean;
  showAge?: boolean;
}) {
  // #3867's ORIGINAL SURFACE. Alex filed the issue against these rows: on
  // `/events/15306225` the served 0.565 printed 56% and 0.145 printed 14% while
  // 0.585 and 0.615 printed 59% and 62%, one half rounding up and its neighbour
  // down for a reason invisible on screen. Moving the rule into the contract did
  // not reach this line, because this line was a second copy of the rule
  // (CERT-2224). It is the contract's now; the bar's WIDTH below stays raw
  // geometry, which is a picture and not a claim.
  const percent = renderedPercent(outcome.prob) ?? 0;
  // A finished GAME settles every row; a finished SET settles only the rows
  // that asked about it. Both end in the same render, because both are the same
  // statement to a reader: this number stopped being a chance.
  const frozen = settled || outcome.decided === true;

  // The strongest state: the question is answered AND this view can say what
  // the answer was. No bar and no number — a percentage beside `Noskova won
  // Set 1` invites the reader to price a set that is already in the books.
  // A struck row is the same shape but the opposite emphasis. `Tiafoe won Set 2`
  // is something that happened and reads bold; `Medvedev 3-0 — no longer
  // possible` is a row being crossed off, and it sits at the bottom of the card
  // precisely so it stops competing for the reader's eye.
  if (outcome.result) {
    return (
      <div className="flex items-baseline gap-2 text-xs" data-testid="special-markets-result">
        <div
          className={`flex-1 ${outcome.unreachable ? "text-text-muted" : "font-semibold"}`}
          data-testid={outcome.unreachable ? "special-markets-unreachable" : undefined}
        >
          {outcome.result}
        </div>
      </div>
    );
  }

  // A settled row loses the bar, exactly as `PropTravelBar`'s `ResolvedMark`
  // does. A filled bar is a picture of a live distribution; leaving it up and
  // only re-wording the caption keeps the lie in the part of the row a reader
  // actually looks at.
  if (frozen) {
    return (
      <div className="flex items-baseline gap-2 text-xs">
        <div className={`flex-1 ${rank === 0 ? "font-semibold" : "text-text-secondary"}`}>
          {outcome.label}
        </div>
        <span className="font-mono tabular-nums text-text-muted">
          {SETTLED_QUOTE_PREFIX} {percent}%
        </span>
      </div>
    );
  }

  return (
    <div className="flex items-center gap-2">
      <div className={`text-xs flex-1 ${rank === 0 ? "font-semibold" : "text-text-secondary"}`}>
        {outcome.label}
      </div>
      {/* #4970, the MIXED case only. The card speaks for its rows whenever they
          all agree about being stale, which is every card measured so far
          (23 of 23, 0 mixed) — see `PropMiniCard`. This per-row mark is what
          happens when they DISAGREE: one row quoted four minutes ago beside one
          quoted three days ago cannot be summarised by a single number without
          the summary being false about one of them (CERT-411 round 2).

          Only a LIVE row reaches this line — `result` and `frozen` both
          returned above — so a settled card never draws an age here. */}
      {showAge && <PriceAgeMark observedAt={outcome.observedAt} />}
      <div className="flex-1 h-1.5 rounded-full bg-surface-border overflow-hidden max-w-[140px]">
        <div
          className={`h-full rounded-full transition-all duration-500 ${rank === 0 ? "bg-violet-400" : "bg-text-muted/40"}`}
          style={{ width: `${outcome.prob * 100}%` }}
        />
      </div>
      <span className="font-mono tabular-nums text-xs font-semibold w-10 text-right">
        {percent}%
      </span>
    </div>
  );
}

function PropMiniCard({
  item,
  settled,
  live,
}: {
  item: MarketCard;
  settled: boolean;
  /** #4970: only a LIVE event's card can go quiet. See `SpecialEventMarkets`. */
  live: boolean;
}) {
  const maxSourceCount = Math.max(...item.outcomes.map((o) => o.sourceCount ?? 1));
  const sourceCount =
    maxSourceCount > 1 ? maxSourceCount : new Set(item.outcomes.map((o) => o.source)).size;

  /* ── #4970 CARD HALF: THE AGE IS SAID ONCE, FOR THE CARD ──────────────────
     The first cut of this put a mark on every stale ROW, and the measurement
     killed it. On the live slate (2026-09-12 01:45Z, `other` rows over 60
     events) EVERY priced row on a live event was past the thirty-minute bar —
     21 of 21 — because these markets are polled on a slower cadence than the
     hero above them. A per-row mark therefore did not mean "one row in five",
     it meant eight identical `41m ago`s stacked down one card, which is the
     grey-text noise notice 34 bans and D102 tempers.

     Said once in the header it is the opposite: one small mark next to the
     card's title, stating the thing that is actually news — the hero is 29
     seconds old and these prices are forty minutes old.

     WHY IT IS SAFE TO SAY IT ONCE, AND WHAT HAPPENS WHEN IT IS NOT.
     Of 23 multi-row cards on that slate, staleness was UNIFORM across the card
     in 23 and mixed in 0 — rows share a poll batch, so one stamp speaks for
     all of them. But "0 of 23 tonight" is not "never", and a single mark over
     a card holding a four-minute-old row and a three-day-old one is false
     about one of them (CERT-411 round 2, which is that exact bug on the
     tournament cards). So the card only speaks when its live rows AGREE: all
     stale ⇒ one card mark; otherwise ⇒ no card mark and the stale rows carry
     their own. Both directions are asserted, per gotcha #43.

     `livePriced` is the denominator and not `item.outcomes`, because a decided
     or answered row has no live price for an age to be about — including it
     would make a card of eight settled set-winners plus one live row read as
     "mixed" and silently move the mark to the wrong place. */
  const livePriced = live ? item.outcomes.filter((o) => isLivePriced(o, settled)) : [];
  const staleLive = livePriced.filter((o) => sourceIsStale(o.observedAt));
  const cardSpeaksForAll = livePriced.length > 0 && staleLive.length === livePriced.length;
  const cardStamp = cardSpeaksForAll
    ? oldestSourceStamp(staleLive.map((o) => o.observedAt))
    : null;

  // K10: cap the bars a single card can stack. Live MLB games put 34–61 props
  // under one heading; the overflow is DISCLOSED, never dropped (gotcha #43).
  const shown = item.outcomes.slice(0, MAX_OUTCOMES_PER_CARD);
  const rest = item.outcomes.slice(MAX_OUTCOMES_PER_CARD);

  return (
    <div className="border border-surface-border rounded-lg p-3">
      <div className="flex items-center justify-between mb-2">
        <div className="font-medium text-sm">{item.name}</div>
        <div className="flex items-center gap-2">
          <PriceAgeMark observedAt={cardStamp} scope="card" />
          {sourceCount > 1 && (
            <span className="text-[10px] font-semibold text-blue-600">{sourceCount}x</span>
          )}
        </div>
      </div>
      <div className="space-y-1.5">
        {shown.map((o, i) => (
          <OutcomeBar
            key={o.label}
            outcome={o}
            rank={i}
            settled={settled}
            showAge={live && !cardSpeaksForAll}
          />
        ))}
      </div>
      {rest.length > 0 && (
        <details className="mt-1.5">
          <summary className="cursor-pointer select-none py-1 text-[11px] text-text-muted">
            {rest.length} more
          </summary>
          <div className="space-y-1.5 pt-1.5">
            {rest.map((o) => (
              <OutcomeBar
                key={o.label}
                outcome={o}
                rank={1}
                settled={settled}
                showAge={live && !cardSpeaksForAll}
              />
            ))}
          </div>
        </details>
      )}
    </div>
  );
}

export default function SpecialEventMarkets({
  data,
  eventStatus,
  completedSets,
  decidedSetsWinner,
  setsWon,
}: SpecialEventMarketsProps) {
  const section = useMemo(
    () =>
      buildMarketSection(data.other, {
        completedSets,
        decidedSetsWinner,
        setsWon,
        // #5181: our names for the two sides, so a bare venue matchup title
        // (`Vancouver vs Los Angeles G`) is re-titled with the same words the
        // hero uses one screen above it.
        homeTeam: data.home_team,
        awayTeam: data.away_team,
      }),
    [
      data.other,
      data.home_team,
      data.away_team,
      completedSets,
      decidedSetsWinner,
      setsWon,
    ],
  );

  // #2086. `eventStatus` has been DECLARED on this component's props and PASSED
  // by the event page since the section shipped — and destructured by nobody, so
  // every `other` row printed a live-looking chance on a game that had finished.
  // A grep for `eventStatus` here finds the declaration and the call site and
  // reads as handled; an optional prop that is never destructured is invisible
  // to tsc. Measured 2026-08-21: of 158 priced rows on 40 settled events, the
  // MODAL row sits in 0.40–0.60 — a coin-flip on a match that ended a week ago,
  // which reads far more plausibly than the 99% the issue was filed on.
  //
  // The predicate is `isSettledStatus`, not a local `=== "completed"` pair: the
  // page, `MarketMapSection` and `propDivergence` were already carrying three
  // spellings of "settled" between them, and this is the widest owned one.
  const settled = isSettledStatus(eventStatus);

  /* #4970: IS THE EVENT LIVE — not merely "not finished".
     `!settled` is the wrong test and the measurement says so. On the slate of
     2026-09-12 the non-settled `other` rows were mostly SCHEDULED games, whose
     prices are legitimately a day old because nobody is trading them yet; every
     one of those cards would have carried a permanent age mark, which is the
     same noise this ship removed at row level arriving one level up.
     The news is a CONTRADICTION: the hero above these cards re-reads every 29
     seconds while the prices in them are forty minutes old. A pregame page's
     hero is not ticking, so there is nothing for a stale price to contradict.
     Expressed with the codebase's own triple — settled / live / pregame
     (`isPregameStatus`'s header) — rather than a fourth status vocabulary; a
     suspended or delayed game counts as live there, and should, because an
     eleven-hour-old price under a rain delay is exactly what a reader wants
     told. An UNKNOWN status lands on pregame and draws nothing, which is the
     safe end for the same reason it is there. */
  const live = !settled && !isPregameStatus(eventStatus);

  if (section.categories.length === 0) return null;

  return (
    <div>
      <div className="flex items-end justify-between mb-4">
        <div>
          <h3 className="text-lg font-semibold tracking-tight">Additional Markets</h3>
          {/* ── NOTICE 34 (#4167): THE SUBTITLE WAS THREE DIAGNOSTICS ──────────
              It read, in grey, under the heading:

                58 markets grouped by category · settled — any percentage is a
                last quote · 1 hidden (conflicting duplicate price)

              Alex, 2026-09-08 4:00pm PT, on exactly this class of text: "all the
              grey text is madness, and shouldn't be user-facing at all". The
              ruling names three shapes and bans all three from the page body,
              and this one line held one of each:

                * a COVERAGE COUNT   — "58 markets grouped by category"
                * a METHOD NOTE      — "any percentage is a last quote"
                * a LIMITATION       — "1 hidden (conflicting duplicate price)"

              The count and the limitation are gone. The reader can see how many
              cards there are by looking at them, and "1 hidden" explains an
              absence they cannot see and could not act on — the ruling's own
              remedy is to leave it out, not to narrate it.

              THE STATE WORD SURVIVES, AND IT IS THE ONE JUDGEMENT HERE.
              Notice 34 allows "at most one short caption", and bans method
              NOTES rather than state. `settled` on its own is state: it is what
              the section is, not how we computed it. Dropping it outright is
              the single move that could make a last quote on a finished game
              read as a live price, which is the harm #3752 was filed on — so
              the clause reduces to `SETTLED_SECTION_NOTE_NO_QUOTES`, a constant
              the codebase already models for the case where no row quotes.

              `settledSectionNote(quotedOutcomes)` is therefore no longer called
              from the web render. Both constants stay exported: `lib/settledQuote`
              is mirrored in Swift and `settledQuoteParity.test.ts` pins
              `SETTLED_QUOTE_SECTION_NOTE` against the app's own string. The app
              half of notice 34 is native's to make, not something to force by
              deleting a shared constant out from under it (#4167 records it). */}
          {settled && (
            <p
              className="text-sm text-text-muted mt-0.5"
              data-testid="special-markets-settled-note"
            >
              {SETTLED_SECTION_NOTE_NO_QUOTES}
            </p>
          )}
        </div>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
        {section.categories.map((cat) => {
          const shownCards = cat.cards.slice(0, MAX_CARDS_PER_CATEGORY);
          const restCards = cat.cards.slice(MAX_CARDS_PER_CATEGORY);
          /* #4286. Compared against the exported constant rather than the
             literal `"Other Markets"`, so renaming the bucket cannot silently
             turn this suppression off and leave the duplication back on the
             page with no test failing. */
          const isLoneFallback =
            section.categories.length === 1 && cat.title === FALLBACK_CATEGORY;
          return (
            <div
              key={cat.title}
              className="bg-surface-card border border-surface-border rounded-xl shadow-sm p-4"
            >
              {/* ── #4286: THREE NAMES FOR ONE IDEA, IN FOUR LINES ──────────
                  A reader on a settled event met, before a single market:

                      Additional Markets      <- the section heading
                      settled
                      Other Markets           <- this card's title
                      additional markets      <- this card's subtitle

                  `Other Markets` is the FALLBACK bucket — "gap K11", the one
                  rows land in when no category pattern claims them — and this
                  module's own header records that on MLB it took 100% of rows
                  on 6 of 6 games. So it is very often the section's ONLY card,
                  and when it is, its title says the heading again and its
                  subtitle says it a third time.

                  Two suppressions, both about information rather than length:

                  * The subtitle is now `""` for the fallback (see
                    `categorizeMarketName`) and an empty subtitle draws nothing.
                    Every real category keeps its own — `scoring & flow`,
                    `statistical milestones` — because those say something the
                    title does not.
                  * The fallback's TITLE is dropped only when it is the
                    section's ONLY card. With a sibling beside it the title is
                    load-bearing — it is the one thing distinguishing the two —
                    so it stays, and the guard asserts that direction too.

                  🔴 NOT A NOTICE-34 CHANGE, and it must not be extended into
                  one. These are HEADINGS, not diagnostic prose: no coverage
                  count, no method note, no limitation. It sits one line under
                  #4167's notice-34 sweep and the temptation to treat it the
                  same way is obvious and wrong. */}
              {(!isLoneFallback || cat.subtitle) && (
                <div className="mb-3">
                  {!isLoneFallback && <div className="font-semibold">{cat.title}</div>}
                  {cat.subtitle && (
                    <div className="text-xs text-text-muted">{cat.subtitle}</div>
                  )}
                </div>
              )}
              <div className="space-y-3">
                {shownCards.map((item) => (
                  <PropMiniCard key={item.name} item={item} settled={settled} live={live} />
                ))}
                {restCards.length > 0 && (
                  <details>
                    <summary className="cursor-pointer select-none text-center text-[10px] text-text-muted py-1">
                      +{restCards.length} more
                    </summary>
                    <div className="space-y-3 pt-3">
                      {restCards.map((item) => (
                        <PropMiniCard key={item.name} item={item} settled={settled} live={live} />
                      ))}
                    </div>
                  </details>
                )}
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
}
