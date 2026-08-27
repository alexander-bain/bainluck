/**
 * Curated tournament props and futures (UX-P132 re-skin, Alex's item 5).
 *
 * "Beyond the two winner markets and today's matches, surface a section of
 * interesting tournament props/futures — curated, not a dump."
 *
 * The curation lives in the REGISTER, not here and not at request time. Same
 * doctrine as every other row on this page: a market not in the register does
 * not render. That is what makes "curated, not a dump" a structural property
 * rather than a promise — there is no code path that could surface an
 * uncurated market, because the page never asks the database what exists.
 *
 * The interestingness bar is applied by the agent when the register is written.
 * A prop earns its place by being a question a person would actually ask about
 * this tournament — "can Sinner complete the calendar slam" — not by having
 * volume.
 */

import type { RoundName } from "./bracket";

export type PriceState = "live" | "stale" | "dark";

/**
 * Curated key suffix -> the round the market is about reaching.
 *
 * MOVED HERE FROM `advanceToStage.ts` by UX-P138, to break a cycle rather than
 * to reorganise for taste: `curatedProps` has to know whether a market is an
 * advance-to-round question (ruling 8 routes those to the grid), and importing
 * `advanceToStage` to ask would have made these two modules import each other.
 * "Which round is this question about" is a property of a prop market, so it
 * belongs on the prop market's own module and `advanceToStage` re-exports it.
 *
 * Ordered longest-first so `round-of-16` is tested before any shorter token
 * could claim it. Keys come from the register and are written by hand, so this
 * is a closed set, not a heuristic over free text.
 */
const ROUND_SUFFIXES: { suffix: string; round: RoundName }[] = [
  { suffix: "round-of-128", round: "R128" },
  { suffix: "round-of-64", round: "R64" },
  { suffix: "round-of-32", round: "R32" },
  { suffix: "round-of-16", round: "R16" },
  { suffix: "quarterfinals", round: "QF" },
  { suffix: "quarter-finals", round: "QF" },
  { suffix: "semifinals", round: "SF" },
  { suffix: "semi-finals", round: "SF" },
  { suffix: "final", round: "F" },
];

/**
 * Which round a curated prop is about reaching, or `null`.
 *
 * `null` for every prop that is not an advance-to-stage market at all — "Will
 * Sinner actually play?" and "Can Alcaraz win a second major this year?" are
 * both curated, both good, and neither is a cell in the playoff grid.
 */
export function advanceRound(market: { key?: string | null }): RoundName | null {
  const key = (market.key ?? "").toLowerCase();
  for (const entry of ROUND_SUFFIXES) {
    if (key.endsWith(`-${entry.suffix}`)) return entry.round;
  }
  return null;
}

export interface PropOutcome {
  entity_key: string;
  display_name: string;
  probability: number | null;
  /**
   * THIS outcome's own freshness, not the card's (UX-P135). The old rule let
   * one outcome refreshed an hour ago mark a twenty-day-old answer live.
   */
  probability_is_live: boolean;
  observed_at: string | null;
  age_hours: number | null;
  price_state: PriceState;
  /** Does this outcome answer the card's question? Curated, never inferred. */
  is_answer: boolean;
}

export interface PropMarket {
  key: string;
  /** The question, phrased as a person would ask it. */
  title: string;
  /** Why it is interesting — one clause, or null. Never an LLM hook. */
  hook: string | null;
  draw: string | null;
  source: string;
  outcomes: PropOutcome[];
  /**
   * The outcome whose probability answers `title`, or `null` for a field
   * market where no single outcome does. `null` is a supported state, not a
   * missing value: it selects the ranked-list rendering.
   */
  answer_entity_key: string | null;
  /** The AND over the card's PRICED outcomes — a ranked field is published too. */
  price_state: PriceState;
  observed_at: string | null;
  age_hours: number | null;
  freshest_observed_at: string | null;
  freshest_age_hours: number | null;
  /** Entity keys of priced outcomes that are not live. */
  stale_outcomes: string[];
  mixed_freshness: boolean;
}

/**
 * Props for the selected draw, plus the tournament-wide ones.
 *
 * A prop with `draw: null` belongs to the whole tournament and shows under
 * both pills — hiding "who wins the calendar slam" from the women's tab
 * because it was filed as tournament-wide would be a filter bug that looks
 * like a curation decision.
 */
export function propsForDraw(markets: PropMarket[], draw: string): PropMarket[] {
  return markets.filter((market) => market.draw === null || market.draw === draw);
}

/**
 * The outcome whose number the card prints as its headline.
 *
 * REPLACES `leadingOutcome`, which took the highest-probability outcome and
 * was wrong in the most dangerous possible way. The props census measured it:
 * "Can Sinner complete the calendar slam?" is backed by a Kalshi threshold
 * ladder whose outcomes are `1+ / 2+ / 3+ Grand Slam wins`. The max is `1+` at
 * 99%, so the card printed **99%** under a question whose real answer is
 * ~1%. The number was true of *something*; it just was not an answer to the
 * question printed above it, which is the worst kind of wrong because it reads
 * as authoritative.
 *
 * Now the register names the answer and this function only looks it up. A
 * market with no named answer returns `null` — the caller must then rank
 * rather than invent a headline.
 */
export function answerOutcome(market: PropMarket): PropOutcome | null {
  if (market.answer_entity_key === null) return null;
  return (
    market.outcomes.find(
      (outcome) => outcome.entity_key === market.answer_entity_key
    ) ?? null
  );
}

/**
 * A field market's outcomes, best first — the rendering for a question no
 * single outcome answers. Unpriced outcomes are dropped from the ranking
 * because there is nothing to rank them by, not hidden as a judgement.
 */
export function rankedOutcomes(market: PropMarket): PropOutcome[] {
  return market.outcomes
    .filter((outcome) => outcome.probability !== null)
    .sort((a, b) => (b.probability as number) - (a.probability as number));
}

export function formatPropProbability(probability: number | null): string {
  if (probability === null || !Number.isFinite(probability)) return "—";
  return `${Math.round(probability * 100)}%`;
}

/** How many outcomes a field card ranks. Only these contribute to liveness. */
export const FIELD_RANK_LIMIT = 3;

/**
 * The outcomes a card actually PRINTS — the only ones that get a vote.
 *
 * An answer card prints one number. A field card prints its top few. An
 * outcome the card does not print cannot make it stale and cannot make it
 * live, which is the difference between "this card's numbers are old" and
 * "something in this market is old".
 */
export function printedOutcomes(market: PropMarket): PropOutcome[] {
  const answer = answerOutcome(market);
  if (answer !== null) return [answer];
  return rankedOutcomes(market).slice(0, FIELD_RANK_LIMIT);
}

/**
 * Is this card allowed the live treatment? (CERT-411 round 2, 2026-08-26.)
 *
 * THE BUG THIS REPLACES, in one line: `ranked.length > 0 &&
 * ranked[0].probability_is_live` — a field card took its liveness from the
 * LEADER alone. So a card ranking three outcomes, its leader refreshed an hour
 * ago and its runner-up twenty days old, rendered in the confident type with
 * no age anywhere on it. The reader is shown three numbers and told all three
 * are current when one of them is three weeks stale.
 *
 * That is the same defect UX-P135 fixed on the boards (a row is as fresh as
 * its OLDEST leg) and on the slate (a pair is live only when BOTH sides are),
 * and it survived here because this component reached past the pure layer and
 * read an outcome flag directly. Hence this function: the rule now lives where
 * a guard can reach it, in one place, for all three surfaces.
 *
 * ANY printed contributor that is not live demotes the card. An unpriced
 * market — nothing printed — is not live either: there is no reading to be
 * fresh.
 */
export function propIsPresentedAsLive(market: PropMarket): boolean {
  const printed = printedOutcomes(market);
  if (printed.length === 0) return false;
  return printed.every(
    (outcome) => outcome.probability !== null && outcome.probability_is_live === true
  );
}

/** Longest age among the printed outcomes — the card is as fresh as its oldest. */
export function propGoverningAgeHours(market: PropMarket): number | null {
  const ages = printedOutcomes(market)
    .map((outcome) => outcome.age_hours)
    .filter((age): age is number => typeof age === "number" && Number.isFinite(age));
  if (ages.length === 0) return null;
  return Math.max(...ages);
}

/**
 * The stale outcomes a muted card should name — mirrors `rowFreshnessLabel`.
 *
 * A muted number with no stated reason is worse than either a live one or an
 * absent one: the reader assumes a bug, or does not notice. Empty for a live
 * card, because a healthy card that keeps apologising teaches the reader the
 * apology is decorative.
 */
export function propStaleOutcomes(market: PropMarket): PropOutcome[] {
  if (propIsPresentedAsLive(market)) return [];
  return printedOutcomes(market).filter(
    (outcome) => outcome.probability !== null && outcome.probability_is_live !== true
  );
}

/* =========================================================================
 * ROTATION — what this section is FOR, and what falls out of it
 * =========================================================================
 *
 * UX-P138, ALEX'S RULING 8, verbatim: "The advance-to-round 'questions'
 * ('Does Gauff reach the semifinals?') are NOT props — they become the playoff
 * grid. The props section is for genuinely fun items — 'Will Sinner actually
 * play?' is the archetype — and needs a freshness rule: when a prop resolves
 * or goes stale, it rotates out, curated by interestingness, never a repeating
 * template."
 *
 * Four rules, in the order they run. Each drops cards, and every drop is
 * COUNTED and reported to the caller, because a section that silently shrinks
 * reads as "nothing is happening here" rather than "the register has gone
 * quiet" — and those need different fixes from different people.
 *
 *   1. STRUCTURAL — an advance-to-round market is not a prop. It is a cell in
 *      the grid and it is rendered there. Eight of our eleven are these.
 *   2. RESOLVED — a settled question is not a question. Nothing to predict.
 *   3. DARK — a reading old enough that we no longer call it a price is not an
 *      answer to anything. Stale is fine and wears the honesty treatment; dark
 *      rotates out.
 *   4. TEMPLATE — at most ONE card per template family. "Can Alcaraz win a
 *      second major this year?" and "Can Sinner win a second major this year?"
 *      differ by a name. Two of them is a template; the more interesting one
 *      is a question.
 *
 * ⚠️ APPLIED TO TODAY'S REGISTER THIS RULE EMPTIES THE SECTION, and that is a
 * true statement about our data rather than a bug in the rule. Of the three
 * non-advance markets we curate, `sinner-competes` was last priced 188 hours
 * ago and both `*-second-major` cards 810 hours — 34 days. Every one is dark.
 * The report states it and the empty state says it in words; showing a
 * month-old number under a heading that calls it a prediction would be the
 * page arguing with its own freshness doctrine.
 */

/**
 * Beyond this age a reading is not a price (Alex's ruling 8, "goes stale ...
 * rotates out").
 *
 * Deliberately the SAME 48-hour boundary the slate's `dark_after_hours`
 * carries and the boards' `price_state` uses, rather than a fourth opinion
 * about what old means. One vocabulary: `live` is confident, `stale` is muted
 * and says its age, `dark` is gone. A section-specific threshold would be a
 * second definition of staleness on a page whose whole freshness doctrine is
 * that there is one.
 */
export const PROP_DARK_AFTER_HOURS = 48;

/**
 * A settled question. `probability` pinned at the rails is the observable — a
 * market that has resolved trades at 0 or 1 — and it is deliberately a tight
 * band rather than a loose one: a genuine 98% is still a question.
 */
export function propIsResolved(market: PropMarket): boolean {
  const printed = printedOutcomes(market);
  if (printed.length === 0) return false;
  return printed.every(
    (outcome) =>
      outcome.probability !== null &&
      (outcome.probability <= 0.001 || outcome.probability >= 0.999)
  );
}

/** Older than we are willing to call a price at all. */
export function propIsDark(market: PropMarket): boolean {
  const age = propGoverningAgeHours(market);
  if (age === null) return true;
  return age >= PROP_DARK_AFTER_HOURS;
}

/**
 * The template family a question belongs to — its shape with the player
 * removed.
 *
 * Register keys are hand-written and follow `<subject>-<topic>`, so the family
 * is the key with its leading subject token dropped: `alcaraz-second-major`
 * and `sinner-second-major` both reduce to `second-major`. A single-token key
 * is its own family. Nothing is inferred from the TITLE text: two questions
 * that happen to share phrasing are not a template, and two that share a
 * curated topic are, whatever they are worded like.
 */
export function propTemplateFamily(market: PropMarket): string {
  const key = (market.key ?? "").toLowerCase();
  const parts = key.split("-");
  return parts.length <= 1 ? key : parts.slice(1).join("-");
}

/**
 * How interesting a question is, lower is better — used to ORDER the section
 * and to pick the survivor of a template family.
 *
 * Genuine uncertainty is the whole appeal. "Will Sinner actually play?" at 63%
 * is a question; the same market at 99% is an announcement. So the score is
 * distance from a coin flip, with live readings ahead of stale ones because a
 * fresher coin flip beats an older one at the same distance.
 *
 * This is a RANKING, not a gate. Nothing is dropped for being uninteresting —
 * the register's curation is what decides membership, and this only decides
 * order. A heuristic that silently deleted curated content would move the
 * curation bar out of the register and into a sort function.
 */
export function propInterestScore(market: PropMarket): number {
  const printed = printedOutcomes(market);
  const best = printed
    .map((outcome) => outcome.probability)
    .filter((p): p is number => p !== null && Number.isFinite(p))
    .map((p) => Math.abs(p - 0.5))
    .sort((a, b) => a - b)[0];
  const distance = best ?? 0.5;
  return propIsPresentedAsLive(market) ? distance : distance + 1;
}

export interface CuratedProps {
  markets: PropMarket[];
  /** Every drop, by reason. Reported, never silent. */
  dropped: {
    advance: number;
    resolved: number;
    dark: number;
    template: number;
  };
  /** How many the register holds for this draw before any rotation. */
  considered: number;
}

/**
 * The section's contents after rotation (Alex's ruling 8).
 *
 * Order is by interestingness. Membership is the register's call minus the
 * four rules above; this function never promotes anything the register did not
 * curate, which is what keeps "curated, not a dump" a structural property
 * rather than a promise.
 */
export function curatedProps(markets: PropMarket[], draw: string): CuratedProps {
  const forDraw = propsForDraw(markets, draw);
  const dropped = { advance: 0, resolved: 0, dark: 0, template: 0 };

  const surviving: PropMarket[] = [];
  for (const market of forDraw) {
    if (advanceRound(market) !== null) {
      dropped.advance += 1;
      continue;
    }
    if (propIsResolved(market)) {
      dropped.resolved += 1;
      continue;
    }
    if (propIsDark(market)) {
      dropped.dark += 1;
      continue;
    }
    surviving.push(market);
  }

  surviving.sort((a, b) => propInterestScore(a) - propInterestScore(b));

  const seen = new Set<string>();
  const kept: PropMarket[] = [];
  for (const market of surviving) {
    const family = propTemplateFamily(market);
    if (seen.has(family)) {
      dropped.template += 1;
      continue;
    }
    seen.add(family);
    kept.push(market);
  }

  return { markets: kept, dropped, considered: forDraw.length };
}

/**
 * The sentence an empty section owes the reader, or `null` when it has cards.
 *
 * A section that vanishes teaches the reader it does not exist; a section that
 * says "nothing here yet" when eleven markets are on file and three of them
 * dropped out for age is simply wrong. So the empty state names the actual
 * reason, which is also the only way the curation gap ever reaches anybody who
 * can fix it.
 *
 * ═══ UX-P145: IT HAS TO SAY IT IN THE READER'S WORDS ═══
 *
 * Alex, on the live page: this sentence read **"3 curated questions have gone
 * dark and rotated out. They come back when they are priced again."** Every
 * load-bearing word in it is ours, not the reader's. *Curated* is our editorial
 * process, *gone dark* is our price-state enum, *rotated out* is our render
 * rule, and *priced* is a trading verb — the reader is told four things about
 * our pipeline and nothing about their tournament.
 *
 * The rewrite keeps the two properties the old sentence had and the vocabulary
 * it did not: it still gives the COUNT (a section that quietly shrinks reads as
 * "not much is happening" when the truth is that three questions aged out), and
 * it still says the state is temporary. `propsCopy.test.tsx` pins the result
 * against the banned list so this cannot regress by a well-meaning edit.
 *
 * *Price* as a NOUN survives the sweep on purpose — "the last prices we saw" is
 * plain English on a prediction-market page and is the honesty language the
 * boards, the slate and the calibration page already share. It is *priced* as a
 * VERB done to a question that is jargon, which is the same line Alex's own
 * ruling 3 drew on "priced to get there" (`lib/playoffGrid.ts`).
 */
export function curatedPropsEmptyReason(result: CuratedProps): string | null {
  if (result.markets.length > 0) return null;
  const { dark, resolved, template, advance } = result.dropped;
  if (dark > 0) {
    const one = dark === 1;
    return `We have not seen a new number on ${dark} question${one ? "" : "s"} in a while, so ${
      one ? "it is" : "they are"
    } hidden for now. New questions are coming — check back soon.`;
  }
  if (resolved > 0) {
    const one = resolved === 1;
    return `${resolved} question${one ? " has" : "s have"} been answered and ${
      one ? "is" : "are"
    } no longer up for debate. New questions are coming — check back soon.`;
  }
  if (template > 0) {
    return "The only questions left for this draw ask the same thing as one we already show.";
  }
  if (advance > 0) {
    return "Every question for this draw is about how far a player gets — those are on the Bracket tab.";
  }
  return null;
}
