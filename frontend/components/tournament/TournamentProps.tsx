import React from "react";

import {
  answerOutcome,
  formatPropProbability,
  propsForDraw,
  rankedOutcomes,
  type PropMarket,
} from "@/lib/tournamentProps";

/**
 * The curated props & futures section (UX-P132 re-skin, Alex's item 5).
 *
 * Renders only what the register curated. There is no "show everything" path
 * and no query behind this — a market not in the register cannot appear here,
 * which is what keeps "curated, not a dump" true as the tournament grows.
 *
 * The honesty treatment is the page's, unchanged: a non-live number is muted
 * and never presented in the confident type.
 */

/** A field market: no single outcome answers the question, so nothing leads. */
const FIELD_RANK_LIMIT = 3;

function PropCard({ market }: { market: PropMarket }) {
  // The headline number is the CURATED answer, never the biggest number in the
  // market. See `answerOutcome` for the measured specimen this rule exists to
  // stop: a 99% printed under a question whose true answer was 1%.
  const answer = answerOutcome(market);
  const ranked = answer === null ? rankedOutcomes(market) : [];
  const isLive = answer
    ? answer.probability_is_live === true
    : ranked.length > 0 && ranked[0].probability_is_live === true;

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

      {answer && (
        <div className="mt-px text-[11.5px] text-text-muted" data-testid="prop-answer">
          {answer.display_name}
        </div>
      )}

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

  if (visible.length === 0) {
    // An empty section still appears, and says why. A section that vanishes
    // when it has nothing teaches the reader it does not exist.
    return (
      <section data-testid="tournament-props">
        <h2 className="mb-2 mt-6 text-xs font-bold uppercase tracking-[0.07em] text-text-muted">
          Props &amp; futures
        </h2>
        <div
          className="rounded-2xl border border-dashed border-surface-border bg-surface-card px-4 py-5 text-center"
          data-testid="props-empty"
        >
          <div className="text-[14px] font-semibold text-text-primary">Nothing curated yet</div>
          <p className="mt-1 text-[12.5px] text-text-secondary">
            Beyond the title race and today&rsquo;s matches, we only show questions worth asking.
            None are registered for this draw yet.
          </p>
        </div>
      </section>
    );
  }

  return (
    <section data-testid="tournament-props">
      <h2 className="mb-2 mt-6 text-xs font-bold uppercase tracking-[0.07em] text-text-muted">
        Props &amp; futures
        <span className="ml-1.5 font-normal normal-case tracking-normal">
          · {visible.length}
        </span>
      </h2>
      <div className="overflow-hidden rounded-2xl border border-surface-border bg-surface-card">
        <ul>
          {visible.map((market) => (
            <PropCard key={market.key} market={market} />
          ))}
        </ul>
      </div>
    </section>
  );
}
