"use client";

import React from "react";

import ShowMore, { COLLAPSED_LIST_COUNT } from "./ShowMore";
import {
  FIELD_RANK_LIMIT,
  answerOutcome,
  curatedProps,
  curatedPropsEmptyReason,
  formatPropProbability,
  propGoverningAgeHours,
  printedOutcomes,
  propIsPresentedAsLive,
  propStaleOutcomes,
  rankedOutcomes,
  type PropMarket,
} from "@/lib/tournamentProps";
import { stalenessLabel } from "@/lib/tournament";

/**
 * The curated questions section (UX-P132 re-skin, Alex's item 5).
 *
 * Renders only what the register curated. There is no "show everything" path
 * and no query behind this — a market not in the register cannot appear here,
 * which is what keeps "curated, not a dump" true as the tournament grows.
 *
 * The honesty treatment is the page's, unchanged: a non-live number is muted
 * and never presented in the confident type.
 *
 * THE NAME (UX-P137, Alex's ruling 7). "Props/Futures" is gambling vocabulary
 * and the label was doing real damage: it is the only heading on a
 * probability-first page that requires a sportsbook to parse.
 *
 * `SECTION_HEADING` is a single constant because Alex picks the final wording
 * on his next pass and it should be a one-line change, not a search. The
 * alternatives, and why the rendered default won, are in the UX-P137 report.
 *
 * ALEX RULED (UX-P140): the name is **"More predictions"**. It is the last
 * section on the page, and what it holds is more of exactly what the page has
 * already been printing — predictions. Naming it by its content rather than by
 * its rhetoric means the reader never has to work out what a new noun means.
 *
 * WHAT THIS SECTION IS NOW (UX-P138, Alex's ruling 8). It used to hold eleven
 * questions, eight of which were "Does <player> reach the <round>?". Those are
 * not props — they are the playoff grid, and they render there. What is left
 * is the section's actual brief, in Alex's words: "genuinely fun items — 'Will
 * Sinner actually play?' is the archetype", rotated by
 * `lib/tournamentProps.curatedProps` so a question that resolves, goes dark, or
 * is the second copy of a template drops out rather than sitting here forever.
 *
 * ═══ UX-P139, ALEX'S ITEM 10: "THE SECTION WAS INVISIBLE" ═══
 *
 * "The questions/props section was INVISIBLE in the artifact Alex viewed —
 * find why and make the demo state obvious."
 *
 * WHY, measured. The section rendered, in all nine panels of the UX-P138
 * artifact; it rendered its EMPTY state, and the empty state was a small
 * dashed box in muted 12.5px type with no heading weight and no border colour.
 * Between two bordered white cards it reads as a divider. That is the finding:
 * not a missing section, a section that had been styled down to invisibility
 * on the assumption it would rarely be empty. It is empty every time, because
 * every card it holds is dark:
 *
 *     sinner-competes        Yes .63    last observed 2026-08-19  (~188h)
 *     sinner-second-major    2+ .555    last observed 2026-07-24  (~810h)
 *
 * Two changes, and neither of them is "show a stale number":
 *
 * 1. **The empty state now has the same visual weight as a populated one** —
 *    the same card border, the same heading treatment, and the reason in
 *    readable type rather than in a caption. A section the reader cannot see
 *    cannot tell them anything, including that something is wrong.
 * 2. **It says what WILL be here**, because during the tournament there will
 *    be real Kalshi and Polymarket props beyond round-advancement (Alex's item
 *    10). An empty section that only apologises reads as a dead feature; one
 *    that names the next thing reads as a section between deliveries.
 *
 * The eight "does X reach the Y" cards are gone from the register entirely as
 * of v7 — they are grid cells, `reaches` pins all 336, and a market in two
 * collections is a divergence waiting to happen. The runtime rotation rule
 * that used to drop them stays, as the guard it always was.
 */

/** Alex's pick, ruled UX-P140. Every surface reads it from here. */
export const SECTION_HEADING = "More predictions";

function PropCard({ market }: { market: PropMarket }) {
  // The headline number is the CURATED answer, never the biggest number in the
  // market. See `answerOutcome` for the measured specimen this rule exists to
  // stop: a 99% printed under a question whose true answer was 1%.
  const answer = answerOutcome(market);
  const ranked = answer === null ? rankedOutcomes(market) : [];

  // LIVENESS IS THE AND OVER EVERY PRINTED OUTCOME (CERT-411 round 2).
  // This used to read `ranked[0].probability_is_live` — the leader's flag,
  // standing in for the whole card. A field card whose leader refreshed an
  // hour ago and whose runner-up is twenty days old rendered fully confident,
  // with no age on it anywhere. The rule now lives in the pure layer with the
  // board's and the slate's, so all three surfaces cannot drift apart again.
  const isLive = propIsPresentedAsLive(market);
  const stale = propStaleOutcomes(market);
  const printedCount = printedOutcomes(market).length;
  const freshness = isLive ? null : stalenessLabel(propGoverningAgeHours(market));

  return (
    <li
      className="border-t border-surface-border px-3.5 py-3 first:border-t-0"
      data-testid="prop-market"
      data-key={market.key}
      data-live={isLive ? "true" : "false"}
      data-price-state={market.price_state}
      data-shape={answer ? "answer" : "field"}
    >
      <div className="flex items-baseline justify-between gap-3">
        <span className="min-w-0 text-[14px] font-semibold text-text-primary">
          {market.title}
        </span>
        {answer && (
          <span
            className={`shrink-0 text-[17px] font-bold tabular-nums tracking-tight ${
              isLive ? "text-text-primary" : "text-text-secondary"
            }`}
            data-testid="prop-probability"
          >
            {formatPropProbability(answer.probability)}
          </span>
        )}
      </div>

      <div className="mt-px text-[11.5px] text-text-muted">
        {answer && <span data-testid="prop-answer">{answer.display_name}</span>}
        {/* THE STATED REASON (CERT-411 round 2). A muted card that does not
            say why it is muted is read as a bug, or not read at all. Names the
            stale outcomes when only some of them are old, exactly as
            `rowFreshnessLabel` does on the boards — a page that words one
            admission two ways teaches the reader one of them is decorative. */}
        {freshness !== null && (
          <span className="text-accent-warning" data-testid="prop-age">
            {answer ? " · " : ""}
            {stale.length > 0 && stale.length < printedCount
              ? `${stale.map((outcome) => outcome.display_name).join(" + ")} ${freshness}`
              : freshness}
          </span>
        )}
      </div>

      {/* A field market ranks instead. There is deliberately no headline
          number here: "who will win a slam" has no single answer, and picking
          the leader to fill the slot is exactly the guess this card refuses. */}
      {answer === null && ranked.length > 0 && (
        <ol className="mt-1.5 space-y-0.5" data-testid="prop-field">
          {ranked.slice(0, FIELD_RANK_LIMIT).map((outcome) => (
            <li
              key={outcome.entity_key}
              className="flex items-baseline justify-between gap-3 text-[12px]"
              data-testid="prop-field-row"
            >
              <span className="min-w-0 truncate text-text-secondary">
                {outcome.display_name}
              </span>
              <span
                className={`shrink-0 tabular-nums ${
                  outcome.probability_is_live ? "text-text-primary" : "text-text-secondary"
                }`}
              >
                {formatPropProbability(outcome.probability)}
              </span>
            </li>
          ))}
        </ol>
      )}

      {market.hook && (
        <p className="mt-1 text-[11.5px] leading-snug text-text-secondary" data-testid="prop-hook">
          {market.hook}
        </p>
      )}
    </li>
  );
}

/**
 * WHERE THE ROUND QUESTIONS WENT — and why this sentence is unconditional.
 *
 * UX-P138 printed it only when `curated.dropped.advance > 0`, i.e. only when a
 * reach question was in the payload and got rotated out at render. UX-P139
 * removed those eight from the register itself (`props_declined`), which is the
 * more correct fix — one market in two collections is a divergence waiting to
 * happen — and the side effect was that the pointer disappeared with them.
 *
 * That made the sentence a fact about our BUILD PIPELINE rather than about the
 * page: it appeared when the rotation happened to fire and vanished once the
 * same decision was made one layer earlier, even though what it tells the
 * reader ("reach-a-round questions live on the Bracket tab") became MORE true,
 * not less. On a page whose ship is "a hub that orients at a glance", an
 * orientation line that blinks out when the underlying structure hardens is
 * backwards. So it is structural now, and the count rides it only while a
 * rotation is genuinely what happened.
 */
function MovedToGrid({ dropped }: { dropped: number }) {
  return (
    <p
      className="mt-2 text-[11px] text-text-muted"
      data-testid="props-moved-to-grid"
      data-dropped={dropped}
    >
      {dropped > 0
        ? `${dropped} question${dropped === 1 ? " about reaching a round is" : "s about reaching a round are"} on the Bracket tab.`
        : "Questions about reaching a round — the quarters, the semis, the final — are on the Bracket tab."}
    </p>
  );
}

export default function TournamentProps({
  markets,
  draw,
}: {
  markets: PropMarket[];
  draw: string;
}) {
  // ROTATION (ruling 8) — advance-to-round questions to the grid, resolved and
  // dark ones out, one card per template family, most interesting first.
  const curated = curatedProps(markets, draw);
  const visible = curated.markets;
  const [expanded, setExpanded] = React.useState(false);

  if (visible.length === 0) {
    // An empty section still appears, and says WHY, with a number. A section
    // that vanishes teaches the reader it does not exist; one that says
    // "nothing curated yet" over a register holding eleven markets is simply
    // wrong, and it is the only channel by which a curation gap reaches anyone
    // who can close it.
    const reason = curatedPropsEmptyReason(curated);
    return (
      <section data-testid="tournament-props" data-considered={curated.considered}>
        <h2
          className="mb-2 mt-6 text-xs font-bold uppercase tracking-[0.07em] text-text-muted"
          data-testid="props-heading"
        >
          {SECTION_HEADING}
        </h2>
        {/* ITEM 10. Same border, same background, same padding as a populated
            card. The old dashed 12.5px whisper between two solid cards read as
            a divider, which is how a section that renders in every panel can
            still be invisible. */}
        <div
          className="overflow-hidden rounded-2xl border border-surface-border bg-surface-card px-3.5 py-3.5"
          data-testid="props-empty"
          data-dropped-dark={curated.dropped.dark}
          data-dropped-advance={curated.dropped.advance}
        >
          <div className="text-[14px] font-semibold text-text-primary">
            {reason === null ? "Nothing curated yet" : "Nothing worth asking right now"}
          </div>
          <p className="mt-1 text-[12.5px] leading-snug text-text-secondary" data-testid="props-empty-reason">
            {reason ??
              "Beyond the title race and today’s matches, we only show questions we think are worth asking. None are registered for this draw yet."}
          </p>
          {/* WHAT WILL BE HERE. A section that only apologises reads as a dead
              feature; naming the next thing reads as one between deliveries.
              Deliberately a statement about the SOURCES, not a promise about a
              date — we do not control when they list. */}
          <p className="mt-2 border-t border-surface-border pt-2 text-[11.5px] leading-snug text-text-muted">
            Questions like <i>Will Sinner actually play?</i> live here. Once the main
            draw starts, Kalshi and Polymarket list more of them beyond who-reaches-what,
            and the ones worth asking appear here as they are priced.
          </p>
        </div>
        <MovedToGrid dropped={curated.dropped.advance} />
      </section>
    );
  }

  const shown = expanded ? visible : visible.slice(0, COLLAPSED_LIST_COUNT);

  const rotatedOut =
    curated.dropped.dark + curated.dropped.resolved + curated.dropped.template;

  return (
    <section data-testid="tournament-props" data-considered={curated.considered}>
      <h2
        className="mb-2 mt-6 text-xs font-bold uppercase tracking-[0.07em] text-text-muted"
        data-testid="props-heading"
      >
        {SECTION_HEADING}
        <span className="ml-1.5 font-normal normal-case tracking-normal">
          · {visible.length}
        </span>
      </h2>
      <div className="overflow-hidden rounded-2xl border border-surface-border bg-surface-card">
        <ul>
          {shown.map((market) => (
            <PropCard key={market.key} market={market} />
          ))}
        </ul>
        {visible.length > COLLAPSED_LIST_COUNT && (
          <ShowMore
            expanded={expanded}
            total={visible.length}
            onToggle={() => setExpanded((value) => !value)}
          />
        )}
      </div>

      {/* NO SILENT ROTATION. A section that quietly shrank from eleven cards to
          one reads as "not much is happening"; the truth may be that ten
          questions went dark, which is a different problem for a different
          person. Advance-to-round drops are NOT counted here — they did not
          rotate out, they moved, and the sentence says where. */}
      {rotatedOut > 0 && (
        <p className="mt-2 text-[11px] text-text-muted" data-testid="props-rotated-out">
          {rotatedOut} other question{rotatedOut === 1 ? "" : "s"} rotated out — answered,
          gone dark, or a near-duplicate of one above.
        </p>
      )}
      <MovedToGrid dropped={curated.dropped.advance} />
    </section>
  );
}
