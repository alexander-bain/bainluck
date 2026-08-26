"use client";

import React from "react";

import ShowMore, { COLLAPSED_LIST_COUNT } from "./ShowMore";
import {
  FIELD_RANK_LIMIT,
  answerOutcome,
  formatPropProbability,
  propGoverningAgeHours,
  printedOutcomes,
  propIsPresentedAsLive,
  propStaleOutcomes,
  propsForDraw,
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
 * probability-first page that requires a sportsbook to parse. The content is
 * unchanged — eleven curated questions, eight of them about reaching a round.
 *
 * `SECTION_HEADING` is a single constant because Alex picks the final wording
 * on his next pass and it should be a one-line change, not a search. The
 * alternatives, and why the rendered default won, are in the UX-P137 report.
 */

/** Alex's pick lands here. See the report for the three candidates. */
export const SECTION_HEADING = "Questions worth asking";

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

export default function TournamentProps({
  markets,
  draw,
}: {
  markets: PropMarket[];
  draw: string;
}) {
  const visible = propsForDraw(markets, draw);
  const [expanded, setExpanded] = React.useState(false);

  if (visible.length === 0) {
    // An empty section still appears, and says why. A section that vanishes
    // when it has nothing teaches the reader it does not exist.
    return (
      <section data-testid="tournament-props">
        <h2
          className="mb-2 mt-6 text-xs font-bold uppercase tracking-[0.07em] text-text-muted"
          data-testid="props-heading"
        >
          {SECTION_HEADING}
        </h2>
        <div
          className="rounded-2xl border border-dashed border-surface-border bg-surface-card px-4 py-5 text-center"
          data-testid="props-empty"
        >
          <div className="text-[14px] font-semibold text-text-primary">Nothing curated yet</div>
          <p className="mt-1 text-[12.5px] text-text-secondary">
            Beyond the title race and today&rsquo;s matches, we only show questions we think are
            worth asking. None are registered for this draw yet.
          </p>
        </div>
      </section>
    );
  }

  const shown = expanded ? visible : visible.slice(0, COLLAPSED_LIST_COUNT);

  return (
    <section data-testid="tournament-props">
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
    </section>
  );
}
