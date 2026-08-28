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
  /**
   * How many MARKETS the register declared for this card (CERT-430, finding 1).
   *
   * `1`, or absent, is an ordinary card. Anything higher is a COMPARISON — one
   * question printed across several markets — and the comparison rules in
   * `propLegs` below apply to it.
   *
   * Optional because a payload captured before UX-P156 does not carry it, and
   * reading a missing count as "one market" is the safe direction: it treats an
   * old capture as an ordinary card rather than as a comparison with legs it
   * cannot see. The live payload always sets it — `build_props` writes it from
   * `prop["markets"]`, and a guard asserts the committed register's cards do.
   */
  legs?: number;
  /** Declared markets we have no reading for. Named, never silently dropped. */
  unpriced_legs?: string[];
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
 *
 * ⚠️ NOT THE RULE FOR A COMPARISON. See `comparisonRows`: on a card built from
 * several declared markets, dropping the unpriced row is how one fresh leg
 * published a one-player answer to a two-player question (CERT-430).
 */
export function rankedOutcomes(market: PropMarket): PropOutcome[] {
  return market.outcomes
    .filter((outcome) => outcome.probability !== null)
    .sort((a, b) => (b.probability as number) - (a.probability as number));
}

/* =========================================================================
 * A COMPARISON IS COMPLETE OR IT IS NOT PRESENTED AS ONE (CERT-430, finding 1)
 * =========================================================================
 *
 * THE SPECIMEN, executed by the cert: the register declares `second-major`
 * across two markets — Alcaraz's and Sinner's. Alcaraz was unpriced; Sinner was
 * fresh at .555. `rankedOutcomes` dropped the unpriced row for having nothing
 * to rank it by, `printedOutcomes` therefore saw one live number, and the card
 * rendered LIVE, in the confident type, with one player under
 *
 *     "Who wins a second major this year?"
 *
 * Every step was locally reasonable and the result is the defect the combined
 * card was built to prevent: a structurally incomplete comparison laundered
 * into a current answer by the one leg that happened to arrive.
 *
 * ═══ WHAT IT DOES INSTEAD, AND WHY IT IS NOT A DELETION ═══
 *
 * Two rules are in tension here and both are load-bearing:
 *
 *   • Alex, 2026-08-28: *illiquid props render with honest freshness
 *     indication, never hidden — "that's part of the value of the product."*
 *   • CERT-430: a registered multi-source card with a missing leg must
 *     withhold live presentation and alarm.
 *
 * Hiding the card breaks the first; printing Sinner alone breaks the second.
 * So the card renders EVERY DECLARED SUBJECT, the missing one included and
 * visibly missing, it is never live, and `propIncompleteComparison` gives the
 * page the sentence that names what is absent. The reader sees the question,
 * both names, the one number we have, and the fact that the other has not
 * arrived — which is the whole truth and is strictly more than either of the
 * two failure modes shows.
 */

/** Declared markets behind this card. Absent means one — an ordinary card. */
export function propLegs(market: PropMarket): number {
  const legs = market.legs;
  return typeof legs === "number" && Number.isFinite(legs) && legs > 0 ? legs : 1;
}

/** Several declared markets, one question — the shape the rules above govern. */
export function propIsComparison(market: PropMarket): boolean {
  return propLegs(market) > 1;
}

/**
 * A comparison's rows: every subject it declared, quoted or not.
 *
 * Ordered best-first like a field, with the unquoted subjects last — they are
 * the ones the card is going to admit to, and burying them mid-list would make
 * the admission easy to miss.
 */
export function comparisonRows(market: PropMarket): PropOutcome[] {
  return market.outcomes.slice().sort((a, b) => {
    if (a.probability === null && b.probability === null) return 0;
    if (a.probability === null) return 1;
    if (b.probability === null) return -1;
    return b.probability - a.probability;
  });
}

/**
 * What a comparison is missing, or `null` when it is whole.
 *
 * `subjects` are the declared rows we have no number for. `undeclared` counts
 * legs the payload promised and did not deliver a row for at all — a register
 * or route fault rather than a pricing one, which the reader is told about in
 * the same breath because from where they sit it is the same hole.
 */
export function propIncompleteComparison(
  market: PropMarket
): { subjects: PropOutcome[]; undeclared: number } | null {
  if (!propIsComparison(market)) return null;
  const subjects = market.outcomes.filter((outcome) => outcome.probability === null);
  const undeclared = Math.max(0, propLegs(market) - market.outcomes.length);
  if (subjects.length === 0 && undeclared === 0) return null;
  return { subjects, undeclared };
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
 *
 * A COMPARISON PRINTS ALL OF ITS ROWS — every declared subject, and no rank
 * limit. Both halves of that are the same rule: a comparison the reader can
 * only partly see is not the object the card claims to be, whether the missing
 * subject was dropped for having no price or for sorting fourth.
 */
export function printedOutcomes(market: PropMarket): PropOutcome[] {
  const answer = answerOutcome(market);
  if (answer !== null) return [answer];
  if (propIsComparison(market)) return comparisonRows(market);
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
  // AND AN INCOMPLETE COMPARISON IS NEVER LIVE, whatever it prints. For a field
  // card this is already implied — the missing subject is one of the printed
  // rows and fails the `every` below. It is stated separately so the rule does
  // not depend on that: a multi-market card that also named an answer would
  // print one row, and one fresh answer must not certify a card whose other
  // declared leg produced nothing.
  if (propIncompleteComparison(market) !== null) return false;
  const printed = printedOutcomes(market);
  if (printed.length === 0) return false;
  return printed.every(
    (outcome) => outcome.probability !== null && outcome.probability_is_live === true
  );
}

/**
 * Longest age among the printed outcomes — the card is as fresh as its oldest.
 *
 * `null` when ANY printed outcome has no age, because a reading that never
 * arrived is older than every reading that did (gotcha #53, and the same rule
 * the backend's `governing_age_hours` applies). Returning the oldest of the
 * ones that DID arrive would let a card whose second row is missing entirely
 * report the age of its first row as the card's age.
 */
export function propGoverningAgeHours(market: PropMarket): number | null {
  const printed = printedOutcomes(market);
  if (printed.length === 0) return null;
  const ages = printed
    .map((outcome) => outcome.age_hours)
    .filter((age): age is number => typeof age === "number" && Number.isFinite(age));
  if (ages.length !== printed.length) return null;
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
 * WHAT THIS SECTION SHOWS — AND, SINCE UX-P154, WHAT IT NEVER HIDES
 * =========================================================================
 *
 * UX-P138, ALEX'S RULING 8, verbatim: "The advance-to-round 'questions'
 * ('Does Gauff reach the semifinals?') are NOT props — they become the playoff
 * grid. The props section is for genuinely fun items — 'Will Sinner actually
 * play?' is the archetype — and needs a freshness rule: when a prop resolves
 * or goes stale, it rotates out, curated by interestingness, never a repeating
 * template."
 *
 * ═══ AND ALEX'S ITEM 4, 2026-08-28, WHICH OVERRULES HALF OF IT ═══
 *
 * **NEVER EXCLUDE PROPS.** In his words: illiquid props render with honest
 * freshness indication, never hidden — *"that's part of the value of the
 * product."*
 *
 * That is a direct reversal of ruling 8's "rotates out", and it is right for a
 * reason ruling 8 could not see from where it was written. A thin market on a
 * real question is not noise to be filtered — it IS the product, because the
 * alternative places a reader can go do not have that question at all. What
 * makes an old number dangerous is presenting it as a current one, and the
 * honesty treatment already solves that. Deleting the card solves it by
 * deleting the value.
 *
 * The measured consequence, which is the whole ship of UX-P154: this section
 * has been EMPTY on production every day since it was built. All three of its
 * cards were older than 48 hours, so all three were dropped, so the reader got
 * an apology where three real questions should have been.
 *
 * ═══ THE RULES NOW ═══
 *
 * Only ONE rule still removes a card, and it does not hide anything:
 *
 *   1. STRUCTURAL — an advance-to-round market is not a prop. It is a cell in
 *      the grid and it is rendered THERE. Nothing is hidden; the section says
 *      where it went.
 *
 * Two former drops are now TREATMENTS. The card renders either way:
 *
 *   • QUIET (was "dark") — an old reading is shown with its age said out loud.
 *     See `propFreshness`.
 *   • LOOKS DECIDED (was "resolved") — a card pinned at 0 or 1. Note that
 *     `propIsResolved` INFERS settlement from the number, which is a guess, and
 *     an illiquid market sitting at 99.9% is not a settled one. Inferring
 *     settlement and then HIDING the card is the worst available combination:
 *     a wrong guess with no way for the reader to notice. So it labels instead.
 *     Real settlement detection is lane1's (flagged in the UX-P154 report).
 *
 * And one former drop is now a COMBINE, which is Alex's item 1:
 *
 *   • TEMPLATE FAMILY — two cards asking one question about different subjects
 *     become ONE card with one row each. Never a deletion. See
 *     `combinePropFamilies`, and `backend/app/utils/prop_template_family.py`
 *     for the same rule where the register is written.
 */

/**
 * Beyond this age we call a reading QUIET and say so on the card.
 *
 * Deliberately the SAME 48-hour boundary the slate and the boards use, rather
 * than a fourth opinion about what old means.
 *
 * ⚠️ SINCE UX-P154 THIS IS A TREATMENT THRESHOLD, NOT A FILTER. It decides how
 * loudly a card admits its age; it has never again decided whether the card
 * exists. The name kept the word "dark" for one release so the diff was
 * readable, and then stopped: `dark` is our own `price_state` enum and the
 * copy guard bans it from anything a reader sees.
 */
export const PROP_QUIET_AFTER_HOURS = 48;

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

/** Old enough that the card says so loudly. Never a reason to hide it. */
export function propIsQuiet(market: PropMarket): boolean {
  const age = propGoverningAgeHours(market);
  if (age === null) return true;
  return age >= PROP_QUIET_AFTER_HOURS;
}

/* =========================================================================
 * FRESHNESS — WHAT THE TIMESTAMP MEANS, SAID IN ONE PLACE
 * =========================================================================
 *
 * ═══ ALEX'S ITEM 3, 2026-08-28 ═══
 *
 * **Staleness is per card, not per section**, because liquidity varies within
 * a section — one question can be quoted every fifteen minutes while the one
 * under it has not moved in a month, and a banner over both is wrong about
 * one of them. (That half was already true here and is now guarded.)
 *
 * And the part that was NOT true: *the "32 hours ago" ambiguity is real —
 * created? updated? last traded?*
 *
 * ═══ THE ANSWER, TRACED TO THE QUERY ═══
 *
 * It is **none of those three.** `age_hours` is derived from
 *
 *     MAX(futures_odds_snapshots.captured_at) WHERE probability IS NOT NULL
 *
 * (`backend/app/routes/tournaments.py::_load_prices`), and every refresh writes
 * a snapshot whether or not the number moved. So the timestamp means:
 *
 *     **the last time a probability for this question reached us.**
 *
 * Not when the market was created. Not when the venue last updated a row —
 * `futures_outcomes.last_updated` was measured a month stale against running
 * snapshots on day 1, which is exactly why the route does not read it. Not when
 * it last traded; we do not receive trades.
 *
 * ⚠️ AND THE LIMIT OF WHAT IT CAN TELL A READER, because the label must not
 * over-claim. "32 hours" has two possible causes and the number cannot tell
 * them apart: the market may be quoted and untraded, or our reader may not be
 * covering it. Both are "no new number reached us in 32 hours", which is
 * therefore what the copy says — a fact about our knowledge, not a claim about
 * the market's activity. Writing "nobody has traded this in 32 hours" would be
 * inventing the half we do not have.
 */

/** The sentence that defines the age, once per section. Never per card. */
export const FRESHNESS_DEFINITION =
  "“Last number” is when we last saw a new probability for a question — not when it was created, and not when it last changed hands.";

export type PropFreshnessState = "fresh" | "waiting" | "quiet";

export interface PropFreshness {
  state: PropFreshnessState;
  /** Longest age among the outcomes the card PRINTS, in hours. */
  ageHours: number | null;
  /** "Last number 32 hours ago" / "No number yet". Always self-labelling. */
  label: string;
  /** Just the age — "32 hours ago" — for treatments that label separately. */
  age: string;
  /** Which printed outcomes are the old ones, when only some of them are. */
  staleOutcomes: PropOutcome[];
}

/**
 * One freshness verdict per card, computed from the outcomes the card prints.
 *
 * Three states rather than two, because "we have never had a number" and "we
 * had one and it is old" are different facts to a reader deciding whether to
 * believe the page:
 *
 *   • `fresh`   — every printed number is live. The card says nothing.
 *   • `waiting` — old, but inside the day-or-two the whole page calls recent.
 *   • `quiet`   — past `PROP_QUIET_AFTER_HOURS`, or never seen at all. This is
 *                 the state that used to delete the card.
 */
export function propFreshness(market: PropMarket): PropFreshness {
  const ageHours = propGoverningAgeHours(market);
  const staleOutcomes = propStaleOutcomes(market);
  const age = freshnessAge(ageHours);

  if (propIsPresentedAsLive(market)) {
    return { state: "fresh", ageHours, label: "", age, staleOutcomes: [] };
  }
  const state: PropFreshnessState =
    ageHours === null || ageHours >= PROP_QUIET_AFTER_HOURS ? "quiet" : "waiting";
  return {
    state,
    ageHours,
    label: ageHours === null ? "No number yet" : `Last number ${age}`,
    age,
    staleOutcomes,
  };
}

/**
 * "32 hours ago" / "20 days ago" / "never".
 *
 * Rounded DOWN, like every other age on this page — "8 days ago" must never
 * flatter to "7". Deliberately a local copy of `stalenessLabel`'s arithmetic
 * rather than an import: this module is imported BY `lib/tournament.ts`'s
 * types and importing back would close a cycle.
 */
export function freshnessAge(ageHours: number | null): string {
  if (ageHours === null || !Number.isFinite(ageHours)) return "never";
  if (ageHours < 1) {
    const minutes = Math.max(1, Math.floor(ageHours * 60));
    return `${minutes} min ago`;
  }
  if (ageHours < 48) {
    const hours = Math.floor(ageHours);
    return `${hours} hour${hours === 1 ? "" : "s"} ago`;
  }
  return `${Math.floor(ageHours / 24)} days ago`;
}

/**
 * The template family a question belongs to.
 *
 * ═══ THE HISTORY, BECAUSE ALEX ASKED WHY NOTHING TRIGGERED ═══
 *
 * Alex, 2026-08-28: *"Was this a bespoke solution? I thought we'd built tools
 * to identify groups and surface them as groups. Why didn't any of them
 * trigger?"*
 *
 * This function is the tool he means, and here is its whole history:
 *
 *  - **UX-P138** keyed it on the topic — `alcaraz-second-major` and
 *    `sinner-second-major` both reduced to `second-major` — and `curatedProps`
 *    used it as a CAP, keeping whichever card scored better and deleting the
 *    other. It deleted Alcaraz.
 *  - **UX-P147** rekeyed it on the WHOLE key to stop that (*"DIFFERENT PLAYERS
 *    and must both render"*, ruling 139). Both men came back — and so did the
 *    repetition, because the only two outcomes the machinery had were two cards
 *    or one card and a deletion.
 *  - **And since register keys are unique by construction** (the population
 *    pass refuses duplicates), keying on the whole key made the cap
 *    STRUCTURALLY UNREACHABLE. From UX-P147 to UX-P154 `dropped.template` could
 *    not be non-zero. The rule everybody was reasoning about was dead.
 *
 * That is the answer: the tool was a cap, a cap can only delete, and the one
 * fix that stopped it deleting also stopped it running.
 *
 * ═══ WHAT IT IS NOW ═══
 *
 * The key is still the whole register key — ruling 139 is intact and this
 * function still cannot collapse across subjects, because it never collapses at
 * all. It is now used only to prove IDENTITY (has this exact card been seen
 * twice), and grouping across subjects is `combinePropFamilies`, which
 * combines instead of dropping.
 */
export function propTemplateFamily(market: PropMarket): string {
  return (market.key ?? "").toLowerCase();
}

/* =========================================================================
 * COMBINING — ALEX'S ITEM 1, AT THE RENDER LAYER
 * =========================================================================
 *
 * *"GENERALIZE: template-family props render as one combined card BY THE
 * SYSTEM. FORMATTING pillar: bespoke solutions to systemic shapes are
 * defects."*
 *
 * There are two layers where that can be true and both need to be:
 *
 *  - `backend/app/utils/prop_template_family.py` detects families among the
 *    MARKETS, so the register is written with one composed card instead of a
 *    human typing out its legs. That is the primary fix.
 *  - This function is the second half, and it is what makes the guarantee hold
 *    for a register the new pass did not write — including every register
 *    already committed. Two cards that ask one question about different
 *    subjects are merged here, at render, into one card with a row each.
 *
 * **It combines or it renders both. It never deletes.** Where the members'
 * own titles do not share enough for us to name the combined question, the
 * cards render separately — visibly repetitive, which is a thing a person can
 * see and fix, rather than invisibly halved, which is not. That is ruling 139
 * satisfied in substance: no subject is ever collapsed away.
 */

/** How many leading/trailing words two titles must share to be combinable. */
export const MIN_SHARED_TITLE_WORDS = 2;

function titleWords(title: string): string[] {
  return (title ?? "").trim().split(/\s+/).filter(Boolean);
}

/**
 * The combined card's question, derived from the members' OWN titles, or null.
 *
 * "Can Alcaraz win a second major this year?" and "Can Sinner win a second
 * major this year?" share "Can" in front and "win a second major this year?"
 * behind, so the question is *"Can … win a second major this year?"* and the
 * ellipsis is exactly the slot the rows fill.
 *
 * Nothing is invented. Where a register NAMES the family — which is what the
 * population pass now writes — that curated sentence is used instead and this
 * function is never consulted; it is the fallback that makes combining
 * unconditional rather than curation-dependent.
 *
 * Returns `null` when the titles share fewer than `MIN_SHARED_TITLE_WORDS`, or
 * when any member's title is entirely shared (one title contained in another is
 * not a template, it is a truncation).
 */
export function propFamilyTitle(titles: string[]): string | null {
  if (titles.length < 2) return null;
  const words = titles.map(titleWords);
  if (words.some((w) => w.length === 0)) return null;

  const same = (index: number, from: "head" | "tail") =>
    words.every((w) => {
      const a = from === "head" ? w[index] : w[w.length - 1 - index];
      const b =
        from === "head" ? words[0][index] : words[0][words[0].length - 1 - index];
      return a !== undefined && b !== undefined && a.toLowerCase() === b.toLowerCase();
    });

  const shortest = Math.min(...words.map((w) => w.length));
  let head = 0;
  while (head < shortest && same(head, "head")) head += 1;
  let tail = 0;
  while (tail < shortest - head && same(tail, "tail")) tail += 1;

  if (head + tail < MIN_SHARED_TITLE_WORDS) return null;
  // Every member must have something of its own in the middle, or one title is
  // a truncation of another rather than the same question about someone else.
  if (words.some((w) => w.length - head - tail <= 0)) return null;

  const lead = words[0].slice(0, head);
  const trail = tail > 0 ? words[0].slice(words[0].length - tail) : [];
  return [...lead, "…", ...trail].join(" ");
}

/**
 * One card per template family; every member survives as a row.
 *
 * A family here is: same `propTopic`, different `propSubject`. Both come from
 * the register key, so nothing is inferred from free text — two questions that
 * happen to share phrasing are not a template, and two that share a curated
 * topic and differ by subject are, however they are worded.
 *
 * The combined card is a FIELD card by construction: `answer_entity_key` is
 * `null`, so the renderer ranks its rows and never guesses which member's
 * number belongs in the big type. Each row is the member's own answer outcome,
 * relabelled to the member's subject — because three rows reading "Yes" is a
 * list of one word, and what the reader is comparing is the subjects.
 *
 * The rows are NOT normalised to sum to 100. Two independent questions can both
 * resolve Yes; a combined card is a comparison, never a field of one winner.
 */
export function combinePropFamilies(markets: PropMarket[]): {
  markets: PropMarket[];
  combined: number;
} {
  const groups = new Map<string, PropMarket[]>();
  for (const market of markets) {
    const topic = propTopic(market);
    const subject = propSubject(market);
    // A subject-less key is a question about the tournament, not about anybody,
    // and two of those sharing a topic are the same question twice — not a
    // family. Keyed apart so they can never merge.
    const key = subject === "" ? `solo:${market.key}` : `topic:${topic}`;
    groups.set(key, [...(groups.get(key) ?? []), market]);
  }

  const out: PropMarket[] = [];
  let combined = 0;
  for (const group of groups.values()) {
    if (group.length < 2) {
      out.push(group[0]);
      continue;
    }
    const merged = mergeFamily(group);
    if (merged === null) {
      // Could not name the combined question from the members' own words. Both
      // render. Repetition a person can see beats a deletion they cannot.
      out.push(...group);
      continue;
    }
    combined += group.length - 1;
    out.push(merged);
  }
  return { markets: out, combined };
}

function mergeFamily(group: PropMarket[]): PropMarket | null {
  // TWO MEMBERS WITH THE SAME SUBJECT ARE NOT A COMPARISON. Two cards sharing a
  // register key are a duplicate, which is a different problem with a different
  // fix, and merging them would print one subject twice under one question.
  // The identical-titles case happens to be caught by `propFamilyTitle` as
  // well; this catches the one that is not — same key, different wording.
  const subjects = group.map(propSubject);
  if (new Set(subjects).size !== subjects.length) return null;

  const title = propFamilyTitle(group.map((m) => m.title));
  if (title === null) return null;

  const key = propTopic(group[0]);
  const rows: PropOutcome[] = [];
  for (const member of group) {
    const printed = printedOutcomes(member);
    // A member with nothing to print would be a blank row under a question
    // about it, which is worse than the repetition this is avoiding.
    if (printed.length !== 1) return null;
    const subject = propSubject(member);
    rows.push({
      ...printed[0],
      entity_key: `${key}:${subject}`,
      // The member's own subject, title-cased from the register key — which is
      // how this page names that subject everywhere else. `propSubject` returns
      // one token today; the split survives a future multi-token subject rather
      // than printing it hyphenated.
      display_name: subject
        .split("-")
        .map((part) => part.charAt(0).toUpperCase() + part.slice(1))
        .join(" "),
      is_answer: false,
    });
  }

  const ages = rows
    .map((row) => row.age_hours)
    .filter((age): age is number => typeof age === "number" && Number.isFinite(age));
  const observed = rows
    .map((row) => row.observed_at)
    .filter((at): at is string => typeof at === "string");
  const live = rows.filter((row) => row.probability_is_live === true).length;
  // A MEMBER THAT ARRIVED WITHOUT A NUMBER IS A MISSING LEG, not a quiet one —
  // the same hole `build_props` reports as `unpriced_legs` when the register
  // composed the card, reaching the same rules by the same field. This path
  // combines at render, for a register that was written before the population
  // pass could compose families, so it has to carry the fact too.
  const unpriced = rows.filter((row) => row.probability === null);

  return {
    key,
    title,
    // The members' hooks are about individual subjects and a combined card is
    // not, so none of them survives. A hook is one clause of editorial and
    // there is no honest way to merge two.
    hook: null,
    draw: group[0].draw,
    source: group.every((m) => m.source === group[0].source) ? group[0].source : "mixed",
    outcomes: rows,
    // No single outcome answers a comparison. This is the shape, not a gap.
    answer_entity_key: null,
    legs: group.length,
    unpriced_legs: unpriced.map((row) => row.entity_key),
    price_state: unpriced.length
      ? "dark"
      : rows.every((r) => r.price_state === "live")
        ? "live"
        : "stale",
    // AS FRESH AS ITS OLDEST ROW, like every other combined thing on this page.
    observed_at: observed.length ? observed.slice().sort()[0] : null,
    // AS OLD AS ITS OLDEST ROW, and a row nobody has ever seen is older than
    // any of them — so a card missing a reading has no age, it has a hole.
    age_hours: ages.length === rows.length ? Math.max(...ages) : null,
    freshest_observed_at: observed.length ? observed.slice().sort().reverse()[0] : null,
    freshest_age_hours: ages.length ? Math.min(...ages) : null,
    stale_outcomes: rows
      .filter((row) => row.probability_is_live !== true)
      .map((row) => row.entity_key),
    mixed_freshness: live > 0 && live < rows.length,
  };
}

/**
 * The leading token of a register key — the player or thing a question is
 * about. `alcaraz-second-major` -> `alcaraz`. Empty for a single-token key,
 * which is a question about the tournament rather than about anybody.
 */
export function propSubject(market: PropMarket): string {
  const parts = (market.key ?? "").toLowerCase().split("-");
  return parts.length <= 1 ? "" : parts[0];
}

/**
 * A register key with its subject removed — the shape of the question.
 * `alcaraz-second-major` -> `second-major`. This is what `propTemplateFamily`
 * used to return, and the reason it no longer does is written above it.
 */
export function propTopic(market: PropMarket): string {
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
  /**
   * Every card that is not on this list, by reason. Reported, never silent.
   *
   * ⚠️ SINCE UX-P154 ONLY `advance` CAN BE NON-ZERO, and it is not a hiding —
   * those questions render on the Bracket tab and the section says so. The
   * other three keys are kept, always 0, and asserted to be 0 by a guard,
   * because that is a stronger statement than deleting them: a future change
   * that starts hiding a curated question again turns a test red instead of
   * quietly reintroducing the behaviour Alex ruled out.
   */
  dropped: {
    advance: number;
    /** Always 0 (Alex, item 4). A settled-looking card is labelled, not hidden. */
    resolved: number;
    /** Always 0 (Alex, item 4). An old card says its age, and renders. */
    dark: number;
    /** Always 0 (Alex, item 1). A family is combined, not capped. */
    template: number;
  };
  /** How many cards merged INTO another. Every subject survives as a row. */
  combined: number;
  /** How many the register holds for this draw before any of this. */
  considered: number;
}

/**
 * The section's contents.
 *
 * Order is by interestingness. Membership is the register's call minus the one
 * structural rule; this function never promotes anything the register did not
 * curate, which keeps "curated, not a dump" a structural property rather than
 * a promise — and, since UX-P154, it never hides anything the register DID
 * curate either.
 */
export function curatedProps(markets: PropMarket[], draw: string): CuratedProps {
  const forDraw = propsForDraw(markets, draw);
  const dropped = { advance: 0, resolved: 0, dark: 0, template: 0 };

  const surviving: PropMarket[] = [];
  for (const market of forDraw) {
    // The ONE removal, and it is a relocation. An advance-to-round market is a
    // cell in the playoff grid and renders there; `MovedToGrid` says where.
    if (advanceRound(market) !== null) {
      dropped.advance += 1;
      continue;
    }
    // NO OTHER FILTER (Alex, 2026-08-28, item 4): *"illiquid props render with
    // honest freshness indication, never hidden — that's part of the value of
    // the product."* Age and apparent settlement are treatments; see
    // `propFreshness` and `propIsResolved`.
    surviving.push(market);
  }

  // Combine BEFORE ordering, so a combined card is ranked on what it actually
  // prints rather than on whichever member happened to sort first.
  const { markets: kept, combined } = combinePropFamilies(surviving);
  kept.sort((a, b) => propInterestScore(a) - propInterestScore(b));

  return { markets: kept, dropped, combined, considered: forDraw.length };
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
  const { advance } = result.dropped;
  // ⚠️ THE AGE BRANCH IS GONE, and its absence is the ship (Alex, item 4). This
  // function used to lead with "We have not seen a new number on 3 questions in
  // a while, so they are hidden for now" — which was an accurate description of
  // a behaviour that should not have existed. Those three questions render now,
  // each saying its own age. An empty section can no longer be caused by
  // anything except an empty draw or a draw whose every question is a
  // reach-a-round one.
  if (advance > 0) {
    return "Every question for this draw is about how far a player gets — those are on the Bracket tab.";
  }
  return null;
}
