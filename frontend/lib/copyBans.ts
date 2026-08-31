/**
 * THE BANNED-LANGUAGE RULES, IN ONE PLACE, SO A SWEEP CANNOT BE PARTIAL.
 *
 * ═══ WHY THIS FILE EXISTS ═══
 *
 * Alex, reading the LIVE production tournament page on 2026-08-28, found the
 * copy that UX-P145 and UX-P146 had already "swept". Every one of those sweeps
 * was real: the branch was clean, the render guards were green, the report said
 * done. None of it was on production, because the branch had never landed.
 *
 *   > Extend the pinned copy test to run against the strings the PRODUCTION
 *   > bundle serves, so branch-only sweeps can never look done again.
 *
 * A guard that reads `components/tournament/*.tsx` proves something about a
 * working tree. A guard that reads the JavaScript a browser downloads proves
 * something about a reader. Those are different claims and only the second one
 * is the ship. So the rules live here, as data, and three consumers apply the
 * SAME list to three different bodies of text:
 *
 *   1. `tournamentPlainLanguage.test.tsx` — server-rendered component output,
 *      which is the only place that catches copy assembled at render time.
 *   2. `shippedCopyBans.test.ts` — the built `.next` bundle, which is the exact
 *      bytes Vercel uploads, and (when pointed at one) a directory of chunks
 *      downloaded from production.
 *   3. `scripts/fetch-shipped-copy.mjs` — the fetcher that fills that
 *      directory. It carries no rules of its own, deliberately: a scanner that
 *      re-declares the list is a scanner that drifts from it.
 *   4. `noReadingCopyClaims.test.tsx` — the FOURTH consumer, and the only one
 *      that applies `HISTORY_CLAIM_BANS`. It reads the empty-state / no-reading
 *      producers by name, because that group's scope is WHERE the string lives
 *      and only a render knows that. See the fence below.
 *
 * ⚠️ **THE FOUR DO NOT ALL APPLY THE SAME LIST ANY MORE, AND THAT IS THE POINT.**
 * Consumers 1-3 carry `ALL_COPY_BANS`; consumer 4 carries `NO_READING_COPY_BANS`.
 *
 * ═══ WHAT IS BANNED, AND ON WHOSE AUTHORITY ═══
 *
 * | Group | Ruling | Clause |
 * |---|---|---|
 * | `JARGON_BANS` | UX-P145, Alex 2026-08-27 | our pipeline's nouns are not the reader's |
 * | `TRADING_VOCAB_BANS` | ruling 138, Alex 2026-08-27 | the word is PROBABILITY, never *price* |
 * | `VENUE_BANS` | ruling 141 AS AMENDED, Alex 2026-08-28 | a page may not talk ABOUT its suppliers; it may still say which line is whose |
 * | `FUTURE_PROMISE_BANS` | ruling 142, Alex 2026-08-28 | a section states what it IS, not what it WILL be |
 * | `HISTORY_CLAIM_BANS` | CERT-537 (UX-P212) + **Alex D25-scope, 2026-08-28** | our voice may not settle a question about ALL OF HISTORY — **in the no-reading components only** |
 *
 * ⚠️ **THE LAST ROW IS THE ONLY GROUP THAT IS NOT CODEBASE-WIDE, AND THAT IS
 * ALEX'S RULING, NOT AN IMPLEMENTATION CONVENIENCE.** It wanted a ruling for
 * five rounds; on 2026-08-31 it got one, and the ruling was about SCOPE rather
 * than about the words. See `ALL_COPY_BANS` / `NO_READING_COPY_BANS` below —
 * the fence is the two lists, and the reasoning is written there.
 *
 * ═══ WHAT IS NOT BANNED ═══
 *
 * Data contracts (`price_state`, `data-price-state`, `priced_cells`,
 * `PRICED_STATES`, the `kalshi`/`polymarket` source ids), code, comments and
 * reports. Every consumer strips attributes and identifiers before applying
 * these rules, so the exemption is structural rather than an allowlist.
 */

export interface CopyBan {
  /** Stable id, so a report can name the rule that fired. */
  id: string;
  pattern: RegExp;
  why: string;
}

/** Our pipeline's vocabulary, in the grammatical form that makes it jargon. */
export const JARGON_BANS: CopyBan[] = [
  { id: "gone-dark", pattern: /\bgone dark\b/i, why: '"gone dark" is our price_state enum' },
  { id: "goes-dark", pattern: /\bgoes dark\b/i, why: '"goes dark" is our price_state enum' },
  { id: "went-dark", pattern: /\bwent dark\b/i, why: '"went dark" is our price_state enum' },
  { id: "rotated-out", pattern: /\brotated out\b/i, why: '"rotated out" is our render rule' },
  { id: "rotation", pattern: /\brotation\b/i, why: '"rotation" is our render rule' },
  { id: "curated", pattern: /\bcurated\b/i, why: '"curated" is our editorial process' },
  { id: "curation", pattern: /\bcuration\b/i, why: '"curation" is our editorial process' },
  { id: "registered", pattern: /\bregistered\b/i, why: '"registered" is the name of our JSON file' },
  { id: "the-register", pattern: /\bthe register\b/i, why: '"the register" is the name of our JSON file' },
  { id: "census", pattern: /\bcensus(ed)?\b/i, why: '"census" is our data-collection step' },
  { id: "blend", pattern: /\bblend(ed|s)?\b/i, why: '"blend" is our aggregation step' },
  { id: "stale", pattern: /\bstale\b/i, why: '"stale" is our price_state enum' },
];

/**
 * Ruling 138. The whole `price` stem — noun, verb, participle and gerund.
 *
 * One stem rule replaces the eleven hand-written variants UX-P145 needed in
 * order to ban the verb while sparing the noun. The word is PROBABILITY.
 */
export const TRADING_VOCAB_BANS: CopyBan[] = [
  {
    id: "price-family",
    pattern: /\b(un)?pric(e|es|ed|ing)\b/i,
    why: '"price" is trading vocabulary — the word is PROBABILITY (ruling 138)',
  },
];

/**
 * Ruling 141, AS AMENDED BY ALEX ON 2026-08-28. The amendment is the operative
 * text and this file is where it is enforced, so read the distinction first.
 *
 * ═══ WHAT THE FIRST ENCODING GOT WRONG ═══
 *
 * UX-P150 (queue 013) implemented the ruling as first written — "venue names
 * are banned in user-facing copy, everywhere" — and Alex narrowed it the same
 * day:
 *
 *   > the venue-name ban was overinterpreted. The precise rule: venue names are
 *   > BANNED in narrative/empty-state/promotional copy … but ALLOWED — and
 *   > often good — as SOURCE ATTRIBUTION of a number or line the user is
 *   > looking at.
 *
 * A blanket name ban is not a smaller version of the amended rule, it is a
 * different rule: it would fail a trend chart for labelling its own faint
 * source line, which makes the chart less legible rather than more abstract.
 * So the pattern still finds every capitalised venue name, and
 * `isSourceAttribution` decides whether the name is the SUBJECT of the sentence
 * or the LABEL on a figure.
 *
 * ═══ HOW THE TWO ARE TOLD APART, WITHOUT A DOM ═══
 *
 * Two of the three consumers see a bare string — a literal prised out of a
 * minified chunk — with no element, no class and no neighbouring number to
 * consult. What they DO see is the shape of the clause the name sits in, and
 * the shape is the tell:
 *
 *   • A LABEL is names, figures and separators. "Polymarket & Kalshi ·",
 *     "Kalshi Implied", "Kalshi · 10 cities", "Both Kalshi and Polymarket".
 *     Strip the venue names out and nothing is left that a sentence needs.
 *   • NARRATIVE needs lowercase words to hold itself together — "we asked …
 *     and neither runs that market", "Kalshi + Polymarket, unified",
 *     "Tournament odds from Polymarket, Kalshi, sportsbooks & DataGolf". Those
 *     leftover lowercase words ARE the sentence, and the sentence is about our
 *     sourcing.
 *
 * The rule is therefore: after removing the venue names, the separators, the
 * figures and a closed list of words a source label may legitimately contain,
 * a clause with NO lowercase word left is attribution; anything else is
 * narrative. Deliberately strict in that direction — a caption misread as
 * narrative gets one line in `ATTRIBUTION_LITERALS` with its reason, whereas a
 * sentence misread as a caption is a silent hole in the ruling.
 *
 * It is also what keeps the two removals ruling 141 PINS: "Polymarket 20 days
 * ago" leaves "days ago" behind, and that phrase is the giveaway — the name is
 * not labelling the number beside it, it is telling the reader about our
 * reading schedule.
 *
 * It does not touch the source ids (`kalshi`, `polymarket`) that the payload,
 * the enums and the sentinels are built on — those never reach a rendered text
 * node, and the consumers of this list strip attributes before applying it.
 */
export const VENUE_BANS: CopyBan[] = [
  {
    id: "venue-kalshi",
    pattern: /\bKalshi\b/,
    why: 'a venue name as the SUBJECT of reader copy — a page may attribute a number to a venue, not talk about its suppliers (ruling 141 as amended)',
  },
  {
    id: "venue-polymarket",
    pattern: /\bPolymarket\b/,
    why: 'a venue name as the SUBJECT of reader copy — a page may attribute a number to a venue, not talk about its suppliers (ruling 141 as amended)',
  },
];

/** The bans that answer to `isSourceAttribution` rather than firing outright. */
const ATTRIBUTION_AWARE_BANS: ReadonlySet<string> = new Set(VENUE_BANS.map((b) => b.id));

/**
 * Source captions the SHAPE rule cannot recognise, each with the reason.
 *
 * A provenance caption under a chart is attribution by any reading of Alex's
 * test — the reader is looking at the exhibit and the caption says what drew
 * it — but a descriptive one ("win-probability model", "futures") carries the
 * lowercase words that otherwise mark narrative. Rather than widen the
 * vocabulary until the rule stops meaning anything, the handful of real cases
 * are named here.
 *
 * Same discipline as the `OWED` map in `shippedCopyBans.test.ts`, opposite
 * polarity: an entry has to say which figure it attributes, and a test asserts
 * every entry is still doing work.
 */
export const ATTRIBUTION_LITERALS: { literal: string; why: string }[] = [
  {
    literal: "DataGolf win-probability model + Kalshi futures",
    why: "provenance caption under the McIlroy case-study bars in lib/story-content.ts — it names what produced the three numbers on screen",
  },
  {
    literal: "Alcaraz win probability through the match (Polymarket)",
    why: "caption on the /about trust exhibit — it names the source of the line being plotted, which is the amendment's own example of the allowed class. Lives in lib/data/alcaraz-ao-2026-series.json and was invisible to the bundle scan until `expandJsonPayload` (UX-P155)",
  },
];

/** Words a source LABEL may carry without becoming a sentence about sourcing. */
const LABEL_WORDS = /^(source|sources|and|vs|via|sportsbook|sportsbooks)$/i;

/**
 * Where one clause ends and the next begins.
 *
 * Sentence enders, plus the typographic fences the design system uses to
 * separate labels from each other (`·`, `•`, `|`) — "Polymarket · atp-… · real
 * price series" is three labels, not one sentence. The em dash is deliberately
 * NOT here: it fences appositions inside a sentence ("our sources — Kalshi and
 * Polymarket — each have a guess"), and splitting on it would hand a narrative
 * sentence a label-shaped middle.
 */
const CLAUSE_BOUNDARY = /[.!?;\n·•|]/;

/** The clause a match sits in — the unit ruling 141's amended test judges. */
export function clauseAround(text: string, index: number): string {
  let start = 0;
  let end = text.length;
  for (let i = index; i >= 0; i -= 1) {
    if (CLAUSE_BOUNDARY.test(text[i])) {
      start = i + 1;
      break;
    }
  }
  for (let i = index; i < text.length; i += 1) {
    if (CLAUSE_BOUNDARY.test(text[i])) {
      end = i;
      break;
    }
  }
  return text.slice(start, end);
}

/**
 * Is this clause a source LABEL rather than a sentence about our sourcing?
 *
 * Allowed: the reader is looking at a number or a line and this says whose it
 * is. Banned: the clause's content IS the supplier list.
 */
export function isSourceAttribution(clause: string): boolean {
  if (ATTRIBUTION_LITERALS.some((entry) => clause.includes(entry.literal))) return true;
  const residue = clause.replace(/\b(Kalshi|Polymarket)\b/g, " ");
  const words = residue.match(/[A-Za-z][A-Za-z'’-]*/g) ?? [];
  return words.every((word) => !/^[a-z]/.test(word) || LABEL_WORDS.test(word));
}

/**
 * Ruling 142. A section states what it IS, not what it WILL be.
 *
 * ═══ WHY THESE PATTERNS AND NOT `\bwill\b` ═══
 *
 * Half the questions on this page are market questions that a market wrote:
 * *Will Sinner actually play?*, *Who will be the champion?*. Banning the bare
 * auxiliary would fire on the product's own content and this guard would be
 * switched off within a week — which is the real failure mode of a broad rule.
 *
 * So every pattern here is a phrase that only OUR voice produces: a promise
 * about a section, addressed to the reader, about a time that has not come.
 * A market question cannot accidentally contain "check back soon".
 */
export const FUTURE_PROMISE_BANS: CopyBan[] = [
  { id: "check-back", pattern: /\bcheck back\b/i, why: "a promise about later, not a statement about now" },
  { id: "coming-soon", pattern: /\bcoming soon\b/i, why: "a promise about later, not a statement about now" },
  { id: "are-coming", pattern: /\b(are|is) coming\b/i, why: "a promise about later, not a statement about now" },
  { id: "stay-tuned", pattern: /\bstay tuned\b/i, why: "a promise about later, not a statement about now" },
  { id: "watch-this-space", pattern: /\bwatch this space\b/i, why: "a promise about later, not a statement about now" },
  { id: "appear-here", pattern: /\bappear here\b/i, why: "describes what the section WILL hold, not what it holds" },
  { id: "show-up-here", pattern: /\bshow up here\b/i, why: "describes what the section WILL hold, not what it holds" },
  { id: "live-here-later", pattern: /\bwill (be|live|go|sit) here\b/i, why: "describes what the section WILL hold, not what it holds" },
  { id: "comes-later", pattern: /\b(comes|come) later\b/i, why: "a promise about later, not a statement about now" },
  { id: "as-soon-as", pattern: /\bas soon as (anyone|someone|they|we|it|a|the|there)\b/i, why: "a promise conditioned on a future event" },
  { id: "once-the", pattern: /\bonce the .{1,40} (starts|opens|begins)\b/i, why: "describes a state the page is not in yet" },
  { id: "will-populate", pattern: /\bwill (appear|show|list|open|arrive|populate|update|fill|carry)\b/i, why: "describes what the section WILL do, not what it does" },
];

/**
 * CERT-537 / UX-P212. Our voice may not settle a question about ALL OF HISTORY.
 *
 * ═══ THE INCIDENT, AND WHY A COPY RULE ANSWERS IT ═══
 *
 * UX-P211 removed the live treatment from a settled comparison card and
 * replaced it with a sentence about the past:
 *
 *   > No number ever reached us for Iga Swiatek, so this comparison was never
 *   > complete.
 *
 * The card printed that beside `observed_at` — the timestamp of a number that
 * had reached us. The route refutes its own copy: `PropOutcome.observed_at` is
 * `max(captured_at)` **where `probability IS NOT NULL`**
 * (`backend/app/utils/latest_observation.py`), loaded by a different statement
 * than `current_probability`, so a null current value beside a populated
 * timestamp is ordinary wire data and positive proof a number DID arrive.
 *
 * ═══ WHY THE ABSOLUTE FORM IS BANNABLE AS TEXT AND THE OTHER HALF IS NOT ═══
 *
 * This is the line the group draws, and it is a real distinction rather than a
 * convenient one.
 *
 *   • "No number EVER reached us" quantifies over all of history. Nothing we
 *     serve can support it: the newest observation is the most the payload
 *     carries, and even a null `observed_at` proves nothing, because Kalshi
 *     market data purges at ≥74/<86 days (`app/utils/kalshi_retention.py`) —
 *     the archive the sentence appeals to is one we do not hold. It is
 *     unsupportable in PRINCIPLE, in every wire shape, which is exactly the
 *     kind of claim a text scan can judge without seeing a payload.
 *   • "No number has reached us YET" is conditionally true — false only when
 *     `observed_at` is populated. Whether it is right is a question about the
 *     data in hand, so a component answers it by reading the field. Banning
 *     the string would ban a sentence that is often correct, which is how a
 *     rule earns a blanket suppression comment and stops being enforced.
 *
 * So: the absolute quantifier is banned here; the conditional tense is a
 * payload check, and UX-P212 fixed it where payload checks belong — in
 * `incompleteComparisonNote`, which now speaks only about what we HAVE.
 *
 * ═══ WHY NOT `\bnever\b` ═══
 *
 * Same reason `FUTURE_PROMISE_BANS` does not ban `\bwill\b`. Measured against
 * this tree, the bare word is load-bearing in copy that is TRUE and supported:
 * "settled but never graded" is a status a market really has, and
 * `/calibration` says "whose price never moved off its opening line" of a
 * cohort it defines by that very fact. A rule that eats those is a rule
 * somebody switches off within a week.
 *
 * Every pattern below therefore names an all-of-history quantifier ATTACHED TO
 * OUR RECEIPT OF A NUMBER — a shape only our voice produces, and one a market
 * question cannot wander into.
 *
 * ═══ CERT-539 MOVED THE GROUP IN BOTH DIRECTIONS AT ONCE ═══
 *
 * The first encoding was six hand-written literals, and the cert found it wrong
 * on both edges of the same scope:
 *
 *   • TOO NARROW. Five ordinary rewordings of the identical claim passed both
 *     the predicate and the shipped-bundle scanner — "There has never been a
 *     probability for this market.", "This question never had a probability.",
 *     "We have not once received a number for this market.", "We did not
 *     receive a number at any time.", "A probability has never been available
 *     for this question." A rule a paraphrase walks around is a rule that
 *     catches the sentence somebody already wrote, not the claim.
 *   • TOO BROAD. Three patterns had drifted off the declared scope and matched
 *     ordinary supported sports prose: "At no point did either player face a
 *     break point.", "The comeback was never complete.", "Nobody ever scored
 *     more than 30 points in this game." None of those says anything about our
 *     receipt of a number, and each would have failed a product-wide build gate
 *     on copy that is simply true.
 *
 * 🔴 THOSE ARE THE SAME DEFECT. Both come from writing whole sentences as
 * literals: a literal cannot be widened without hand-enumerating grammar, and
 * it cannot be kept in scope because the scope lives only in this comment. So
 * the fix is not "more literals" — it is to make the SCOPE a value.
 *
 * `READING` is the noun the whole group is about: a number we may or may not
 * have received. `OUR_SUBJECT` is the thing on the page that can be incomplete.
 * Every pattern composes one of them, so widening the grammar cannot widen the
 * scope, and a new noun is added in ONE place rather than in six regexes that
 * have already drifted apart once. (The lane has counted six duplicated
 * vocabularies across this repo — UX-P213-3. This is one fewer.)
 */

/**
 * A number we may or may not have received. THE scope of this whole group.
 *
 * ⚠️ `odds` IS DELIBERATELY ABSENT, AND IT WAS REMOVED AFTER A MEASUREMENT, not
 * on taste. Including it fired `no-reading-ever` on `lib/story-content.ts`'s
 * "No odds formats, ever. Nothing to deposit, nothing to buy." — a product
 * promise about our UI, not a claim about our data. It is also a word our own
 * voice does not use for a number (ruling 138: the word is PROBABILITY), so the
 * only copy that can contain it is copy about the FORMAT. Nothing is lost.
 *
 * That false positive was caught by the negative pins UX-P213 wrote, which is
 * the argument for keeping a list of true-and-supported copy beside every
 * content rule: widening this vocabulary is now a change with a safety net.
 *
 * ⚠️ `answer`, `figure` AND `value` WERE REMOVED BY CERT-547's SWEEP, and for a
 * reason worth keeping: they are the only members that stay ambiguous even with
 * `PAGE_SUBJECT` attached. "This game never had the answer anyone wanted." and
 * "That contest never had a figure worth watching." are ordinary sports writing
 * that satisfies BOTH halves of the scope — a demonstrative page subject and a
 * reading noun — so the anchor cannot rescue them and nothing else can either.
 * Every other member of this list is a word that, next to "this market", only
 * our voice produces. Nothing is lost: our own copy says probability or number,
 * never "we never had a value".
 */
export const READING_NOUNS = [
  "number",
  "price",
  "probability",
  "reading",
  "quote",
  "estimate",
  "market",
  "data",
] as const;

/** A thing on OUR page that can be incomplete — not an event in the world. */
export const OUR_SUBJECT_NOUNS = [
  "comparison",
  "chart",
  "card",
  "series",
  "history",
  "record",
  "reading",
  "quote",
  "number",
  "price",
  "probability",
  "estimate",
  "data",
] as const;

/**
 * A thing a venue puts a reading ON. The object of "nobody ever quoted ___".
 *
 * Separate from `READING` because the claim "nobody ever quoted this match" is
 * about the MARKET, not about the number — and separate from `OUR_SUBJECT`
 * because a match is not a thing on our page that can be incomplete.
 */
export const MARKET_OBJECT_NOUNS = [
  "match",
  "market",
  "question",
  "game",
  "event",
  "leg",
  "contest",
  "line",
  "outcome",
  "prop",
] as const;

/**
 * ⚠️ THE THREE LISTS ABOVE ARE EXPORTED SO A GUARD CAN ITERATE THEM.
 *
 * `shippedCopyBans.test.ts` requires every noun in all three to appear in at
 * least one negative-control sentence. That is the mechanism that ends the
 * CERT-539 → 546 → 547 cycle: each of those rounds was a noun (or a verb) that
 * had never been tried against ordinary prose, found one cert at a time. A word
 * can no longer enter the scope without the sentence that proves it safe
 * arriving in the same commit.
 *
 * Same discipline as `ATTRIBUTION_LITERALS`' "every entry is still doing work",
 * pointed the other way: there, every exemption must be load-bearing; here,
 * every inclusion must be survivable.
 */
const alt = (words: readonly string[]) => `(?:${words.join("|")})`;

const READING = alt(READING_NOUNS);
const OUR_SUBJECT = alt(OUR_SUBJECT_NOUNS);
const MARKET_OBJECT = alt(MARKET_OBJECT_NOUNS);

const rx = (source: string) => new RegExp(source, "i");

/* ═══════════════ CERT-547: THE SCOPE IS THE ANCHOR, NOT THE NOUN ═══════════════
 *
 * Three rounds tried to make the scope hold by purifying the noun lists, and
 * each round traded one direction of error for the other. CERT-547 caught both
 * at once: ordinary prose still failed ("Nobody ever reported the game was
 * delayed", "We never had an answer for their press") while basic intended
 * claims escaped ("We never received THE probability for this question").
 *
 * 🔴 A SWEEP OF ALL ELEVEN RULES FOUND EIGHT FALSE POSITIVES, NOT THE TWO THE
 * CERT LISTED — `nobody-ever` alone fired on five, one for every pairing of a
 * general verb with a `MARKET_OBJECT`. And the two failure directions turned
 * out to be COUPLED: "This team never had the answer for their zone" was clean
 * only because the determiner list omitted `the`, which is the very omission
 * that caused the false negatives. Fixing either one alone re-opens the other,
 * which is why rounds 2, 3 and 4 each bounced.
 *
 * ═══ WHY NOUN PURITY CANNOT WORK ═══
 *
 * There is no noun in this group's vocabulary that is safe on its own once the
 * determiner is allowed to be `the`. Measured, every one of these is ordinary
 * supported prose: "a figure like him in the clubhouse", "a value like that on
 * this roster", "the answer for their zone", "the market cornered", "the data
 * to justify the trade". Purifying the list until those pass leaves a list that
 * no longer contains the words our real claims use.
 *
 * ═══ WHAT ACTUALLY SEPARATES THEM ═══
 *
 * The group's own scope sentence already said it: an all-of-history quantifier
 * attached to OUR RECEIPT OF A NUMBER **for something on this page**. Every
 * genuine specimen carries that second half explicitly — "for this market",
 * "on this market", "for this question", "this question never had…", "this
 * comparison", "this match". Ordinary prose about the world does not, because
 * the world's nouns take `the` and `their`, while the thing on our page is
 * pointed at with a DEMONSTRATIVE.
 *
 * So the scope moves out of the noun list and into `PAGE_SUBJECT`, and the
 * vocabulary is free to stay broad. That is the opposite of the last three
 * rounds and it is what makes this one stable: widening a noun can no longer
 * widen the rule past our own page.
 */

/**
 * The thing on THIS page a reading would belong to.
 *
 * The demonstrative is load-bearing and is the whole discriminator. "the game"
 * is a game in the world; "this game" is the card the reader is looking at. A
 * rule keyed on the bare noun cannot tell those apart, and every false positive
 * across CERT-539/546/547 was on the `the`/`their` side of exactly that line.
 */
const PAGE_SUBJECT = `(?:this|that|these|those) ${MARKET_OBJECT}s?`;

/**
 * Determiners an intended claim may use.
 *
 * ⚠️ `the` IS THE ONE CERT-547 FOUND MISSING, and adding it is only safe
 * because `PAGE_SUBJECT` now carries the scope — before that, `the` was
 * accidentally load-bearing as a false-positive filter. See the block above.
 */
const DET = "(?:a |an |any |the |this |that |its |our |their |one |a single |even a )?";

/**
 * 🔴 THE PAGE SUBJECT IS USUALLY NOT A LITERAL, AND THE FIRST ANCHOR MISSED IT.
 *
 * Real copy names the subject with an interpolation — `There has never been a
 * probability for ${marketName}.` — and `splitTemplateLiteral` hands the bundle
 * scanner the fragment `"There has never been a probability for "`. The anchor
 * it needs was compiled away before the scanner ever saw the chunk, so an
 * anchor that only accepts a literal `this market` silently switches the whole
 * group off on the ONE layer that guards production. The suite's own planted
 * chunk caught this on the first run.
 *
 * A fragment that stops on a dangling preposition is exactly that shape, and
 * ordinary complete prose does not have it — "We never had a quote from the
 * coach." ends on its object, while "…a probability for " ends on the hole
 * where the object was. So a trailing preposition counts as the anchor.
 *
 * 🔴 CERT-549: THE TRAILING WHITESPACE IS THE WHOLE DISCRIMINATOR, AND IT WAS
 * OPTIONAL. Written `\s*$`, this arm also accepted a COMPLETE sentence that
 * merely happens to end on a preposition — "We never had a number to play for"
 * — which is ordinary sports prose and would have failed a build. The hole the
 * interpolation left is not the preposition, it is the SPACE AFTER IT: the
 * literal really is `"…a probability for "`, because the space precedes the
 * `${`. Requiring `\s+$` accepts the fragment and rejects the sentence, which
 * is exactly the distinction this arm was always claiming to make.
 *
 * ⚠️ Copy written `…for${x}` with no space would not be caught here. That is a
 * deliberate limit, not an oversight: no sentence in this codebase is written
 * that way, and widening it back is how the false positive returns.
 */
const INTERPOLATED_SUBJECT = String.raw`\b(?:for|on|in|about|from|of)\s+$`;

/**
 * Require the claim and the page subject in the SAME clause, in any position.
 *
 * "This question never had a probability" puts the subject first; "We never
 * received a probability for this question" puts it last. Both are the claim.
 *
 * 🔴 CERT-549: AND THE SUBJECT CAN SIT *INSIDE* THE CORE, WHICH THE POSITIONAL
 * FORM COULD NOT EXPRESS. "At no point did this leg carry a probability."
 * escaped every rule: `at-no-point`'s core spans from "At no point" to
 * "probability", so the page subject it needs is in the middle — consumed by
 * the core itself, leaving nothing before or after to anchor on. UX-P216 found
 * this hole, documented it in-tree as a known limit, and staged anyway; the
 * cert found it. **A documented hole is still a hole.**
 *
 * The second arm is therefore a clause-scoped LOOKAHEAD rather than a suffix.
 * From the match start it requires a page subject somewhere ahead in the same
 * clause — which covers the subject sitting inside the core AND the old
 * subject-after-core case, so it strictly subsumes the arm it replaces. The
 * `[^.!?]` bound is what keeps "same clause" honest: a subject in the NEXT
 * sentence cannot be borrowed.
 */
const anchored = (core: string) =>
  rx(
    `(?:\\b${PAGE_SUBJECT}\\b[^.!?]{0,60}?(?:${core})` +
      `|(?=[^.!?]{0,80}?\\b${PAGE_SUBJECT}\\b)(?:${core})` +
      `|(?:${core})[^.!?]{0,20}?${INTERPOLATED_SUBJECT})`
  );

/** Why-text shared by the patterns that quantify over an archive we do not hold. */
const NOT_THE_ARCHIVE =
  "quantifies over all of history; the payload carries the latest observation, not the archive (CERT-537/539)";

export const HISTORY_CLAIM_BANS: CopyBan[] = [
  {
    // ⚠️ CERT-549: THE LAST UNANCHORED VERB RULE, AND THE THIRD ROUND RUNNING IN
    // WHICH THE UNANCHORED ONE WAS THE DEFECT. It matched "The ball never
    // reached us in the upper deck." — a thing arriving at a person is ordinary
    // prose; a READING arriving at US is the claim.
    //
    // 🔴 AND THE ANCHOR WAS THE WRONG TOOL — TWICE OVER.
    //
    // Sweeping (not the cert, which named one specimen) found three more:
    // "The ball never reached us before this game ended.", "The crowd never
    // came to us during this contest." and "He never got to us in that game."
    // all satisfy the page anchor HONESTLY — they really are about something on
    // this page — so anchoring did not save them.
    //
    // And anchoring actively BROKE the real claim: production copy is "No
    // number ever reached us for ${playerName}.", whose subject is a PERSON,
    // not a `MARKET_OBJECT`. `PAGE_SUBJECT` cannot see it, so the group's
    // oldest specimen stopped firing. That failure is the lesson in miniature:
    // **the anchor says WHERE a claim lives; it cannot say WHAT arrived.**
    //
    // This is the only rule in the group with no reading noun anywhere in it —
    // that absence, not the anchor, was the defect. The SUBJECT must be a
    // reading, and then the frame is tight enough to need nothing else: a ball,
    // a crowd and a person are all rejected on the subject alone, and the real
    // claim keeps firing whatever its object turns out to be.
    id: "ever-reached-us",
    pattern: rx(
      String.raw`\b${READING}s?\b[^.!?]{0,20}?\b(?:ever|never) (?:reached|arrived at|came to|got to) us\b`
    ),
    why: NOT_THE_ARCHIVE,
  },
  {
    // ⚠️ ANCHORED AFTER MY OWN SWEEP, NOT AFTER A CERT. Left unanchored in the
    // first draft of this repair on the reasoning that "no ___ ever" is a
    // distinctive enough frame; it is not. Measured: "No market ever felt out
    // of reach for them.", "No data ever suggested he was slowing down." and
    // "No number ever suited him better than 23." all fired.
    id: "no-reading-ever",
    pattern: anchored(String.raw`\bno ${READING}s?\b[^.!?]{0,40}\bever\b`),
    why: NOT_THE_ARCHIVE,
  },
  {
    // ⚠️ CERT-546: THE LAST UNBOUND VERB PATTERN, AND IT WAS THE ONE I DID NOT
    // TOUCH. UX-P213 wrote this as a bare verb list with no object, and the
    // CERT-539 repair narrowed its three siblings while leaving this one alone
    // because the cert had not named it. It matched "We never had a chance
    // after halftime." — ordinary supported sports prose, the exact
    // build-breaking false-positive class CERT-539's P2 was about.
    //
    // 🔴 THE LESSON: A CERT'S FINDING LIST IS A SAMPLE, NOT A CENSUS. Having
    // been told three patterns were out of scope, the job was to check ALL of
    // them against the scope, not to fix the three that were named. There were
    // four.
    //
    // It now requires an object from `READING`, like every other verb rule
    // here. This makes it largely a subset of `never-had-a-reading` below, and
    // the overlap is deliberate — this file's own note: "a sentence that can
    // only be caught by one pattern is one regex edit away from being served."
    // ⚠️ CERT-547 CAUGHT IT AGAIN — "We never had an answer for their press."
    // The CERT-546 repair gave it an object from `READING`, which was the right
    // shape and the wrong scope: `answer` is an ordinary English noun and no
    // amount of object-checking rescues it. It is now ANCHORED instead, so the
    // sentence has to be about a reading for something on THIS page.
    id: "we-never-had",
    pattern: anchored(
      String.raw`\bwe (?:have |had )?never (?:had|held|received|saw|seen|got|read|recorded) ${DET}${READING}s?\b`
    ),
    why: "a claim about our whole record, made from a payload that carries only the newest reading (CERT-537)",
  },
  // ── CERT-539: the four grammar families that walked around the six above ──
  {
    // "There has never been a probability for this market."
    // ⚠️ Swept after CERT-547 and it was a false positive too, unnamed: "There
    // has never been a value like that on this roster." Anchored.
    id: "there-was-never-a-reading",
    pattern: anchored(
      String.raw`\bthere (?:has|have|had|was|were) never (?:been )?${DET}${READING}s?\b`
    ),
    why: NOT_THE_ARCHIVE,
  },
  {
    // "This question never had a probability." — the subject need not be "we".
    id: "never-had-a-reading",
    pattern: anchored(
      String.raw`\bnever (?:had|held|carried|showed|shown|received|got|recorded|saw|seen) ${DET}${READING}s?\b`
    ),
    why: "a claim about our whole record, made from a payload that carries only the newest reading (CERT-539)",
  },
  {
    // "We have not once received a number for this market."
    //
    // ⚠️ CERT-546. THE UX-P215b REPORT NAMED THIS PATTERN AS THE MOST LIKELY
    // THING WRONG WITH THE REPAIR — "the one pattern not composed from a
    // constant" — and the cert found exactly that: it matched "The quarterback
    // has not once received a snap under center." Writing the self-disclosure
    // was not the same as acting on it. **If you can name the weak line, fix
    // the weak line.**
    //
    // The object is what carries the scope, so the verbs stay a literal list
    // and `READING` supplies the object, exactly like its siblings.
    id: "not-once-received",
    pattern: anchored(
      String.raw`\bnot once (?:received|got|read|saw|seen|recorded|held|had) ${DET}${READING}s?\b`
    ),
    why: "an all-of-history quantifier in a different word; same unsupportable claim (CERT-539)",
  },
  {
    // "We did not receive a number at any time." The negation and the reading
    // noun are both required, so "you can dismiss this at any time" is safe.
    id: "no-reading-at-any-time",
    pattern: rx(
      String.raw`\b(?:no|not|n't|never)\b[^.!?]{0,60}\b${READING}s?\b[^.!?]{0,40}\bat any time\b`
    ),
    why: NOT_THE_ARCHIVE,
  },
  {
    // "A probability has never been available for this question."
    id: "reading-never-been",
    pattern: anchored(
      String.raw`\b${READING}s?\b[^.!?]{0,30}\b(?:has|have|had|was|were) never been\b`
    ),
    why: NOT_THE_ARCHIVE,
  },
  // ── CERT-539: the three that had drifted OUT of scope, pulled back in ──
  {
    // Was `/\bwas never (complete|…)\b/`, which rejected "The comeback was
    // never complete." The subject now has to be something on OUR page. At most
    // two words may sit between it and the verb, so a subject mentioned earlier
    // in a longer sentence cannot be borrowed by a later clause.
    // ⚠️ CERT-547 SWEEP, UNNAMED BY THE CERT: "The chart shows the record was
    // never complete." `record` is in `OUR_SUBJECT`, so binding the subject was
    // not enough — the subject also has to be OURS, and the demonstrative is
    // what says so. `this comparison` fires; `the record` does not.
    id: "was-never-complete",
    pattern: rx(
      String.raw`\b(?:this|that|these|those|our) ${OUR_SUBJECT}s?(?: [a-z]+){0,2} (?:was|were|has|have|had) never (?:complete|completed|available|quoted|published|reported|answered)\b`
    ),
    why: "settles a question about the past that no field on the card records (CERT-537)",
  },
  {
    // Was `/\b(nobody|no one|no-one) ever\b/`, which rejected "Nobody ever
    // scored more than 30 points in this game." Bound to QUOTING, which is the
    // thing we cannot distinguish from not having read.
    // ⚠️ CERT-546 DID NOT NAME THIS ONE AND IT HAD THE SAME DEFECT. The
    // CERT-539 repair bound it to a verb list, which is only half a scope: the
    // verbs collide with ordinary sports prose the moment the object is not
    // ours. "Nobody ever reported the score.", "Nobody ever offered him a
    // contract.", "Nobody ever posted a better time." — all three would have
    // failed a build. Found by sweeping every pattern against the declared
    // scope after CERT-546, rather than repairing only the two it listed.
    //
    // The object now has to be a reading or a thing we quote a reading ON.
    // 🔴 CERT-547 NAMED ONE FALSE POSITIVE HERE; THE SWEEP FOUND FIVE, one per
    // pairing of a general verb with a `MARKET_OBJECT`: "…reported the game was
    // delayed", "…reported the match was postponed", "…posted the line for that
    // contest", "…offered the outcome anyone wanted", "…published the event
    // schedule". `reported`, `posted`, `offered` and `published` are things
    // people do in the world; only `quote`, `price`, `list` and `trade` are
    // things a VENUE does to a market, and this rule is about a venue. The verb
    // list is now those four, and the object must still be on this page.
    //
    // ⚠️ NOT WRAPPED IN `anchored`, DELIBERATELY. This rule's OBJECT is the page
    // subject ("nobody ever quoted this match"), so an `anchored` wrapper would
    // demand a SECOND one and the rule would stop firing on its own specimen.
    // The demonstrative goes inline instead — same discriminator, one mention.
    id: "nobody-ever",
    pattern: rx(
      String.raw`\b(?:nobody|no one|no-one) ever (?:quoted|priced|listed|traded) (?:this|that|these|those) (?:${READING}|${MARKET_OBJECT})s?\b`
    ),
    why: "we cannot tell a market nobody quoted from one we were not reading (CERT-537)",
  },
  {
    // Was a bare `/\bat no point\b/`, which rejected "At no point did either
    // player face a break point." A reading noun must appear in the same
    // clause, on either side of the quantifier.
    // ⚠️ ANCHORED for the same reason as `no-reading-ever`: "At no point was the
    // market in doubt." fired, and that is ordinary economics prose.
    id: "at-no-point",
    pattern: anchored(
      String.raw`(?:\bat no point\b[^.!?]{0,60}\b${READING}s?\b|\b${READING}s?\b[^.!?]{0,60}\bat no point\b)`
    ),
    why: NOT_THE_ARCHIVE,
  },
];

/**
 * ═══ THE FENCE — ALEX, D25-scope, 2026-08-31 ═══
 *
 * > **The ban applies only to copy emitted by the empty-state / no-reading
 * > components. It does not apply to prose anywhere else in the codebase.**
 *
 * `HISTORY_CLAIM_BANS` IS DELIBERATELY NOT IN `ALL_COPY_BANS`, AND THIS IS THE
 * SHIP. Six certs — 539, 546, 547, 549, 551 and the round before them — blocked
 * this group, and **every one of the six was a false positive on ordinary sports
 * prose**, not a miss on empty-state copy. `Market data never reached us during
 * the outage.` is a true sentence in a normal paragraph. `We never had a chance
 * after halftime.` is a true sentence about a football game. The rule had no
 * business reading either.
 *
 * Six rounds answered by making the pattern cleverer, and each one traded one
 * direction of error for the other, because **the failure class was never "the
 * regex isn't expressive enough". It was that the regex was pointed at the whole
 * codebase.** Alex kept the rule's ambition and moved the fence instead.
 *
 * Two consequences, and they bind future rounds:
 *
 *   1. **Inside the fence the pattern may be as expressive as it likes.**
 *      Expressiveness was never the defect, so nothing here is narrowed.
 *   2. **A false positive on a string OUTSIDE the no-reading components is a
 *      SCOPE bug, and the repair is the fence, never the pattern.** If a future
 *      cert names such a sentence, the answer is that this list does not read it.
 *
 * ⚠️ **AND THE BUNDLE SCANNER CANNOT ENFORCE THIS GROUP AT ALL** — said out loud
 * rather than left to be discovered. A minified chunk hands you a bare string
 * with no component, no element and no call site, so "where does this string
 * live" is *unanswerable there by construction*. A scanner that guessed would be
 * precisely the false-positive engine the ruling just fenced off. So the group is
 * enforced at RENDER time, over the named producers in
 * `__tests__/components/noReadingCopyClaims.test.tsx`, and the bundle layer
 * carries `ALL_COPY_BANS` — which is a real reduction in coverage for this one
 * group, and the honest trade for coverage that was never sound.
 */
export const ALL_COPY_BANS: CopyBan[] = [
  ...JARGON_BANS,
  ...TRADING_VOCAB_BANS,
  ...VENUE_BANS,
  ...FUTURE_PROMISE_BANS,
];

/**
 * The list that applies INSIDE the fence: everything above, plus the history
 * claims. Only the no-reading / empty-state producers are read with this.
 *
 * Derived from `ALL_COPY_BANS` rather than re-spelled, so a group added to the
 * codebase-wide list is covered here without touching this line — the drift that
 * `event_concept_population.py` exists to prevent, one file over.
 */
export const NO_READING_COPY_BANS: CopyBan[] = [
  ...ALL_COPY_BANS,
  ...HISTORY_CLAIM_BANS,
];

export interface CopyBanHit {
  ban: CopyBan;
  /** The text the pattern actually matched. */
  matched: string;
  /** Enough surrounding text to recognise the sentence without opening a file. */
  context: string;
}

/**
 * Every rule that fires on `text`, with enough context to act on.
 *
 * At most one hit per rule — a report wants to know THAT the page says *price*,
 * not eleven times over. But the search walks every occurrence rather than
 * stopping at the first, because ruling 141's amended test is judged per
 * OCCURRENCE: a page may legitimately label a chart line "Kalshi" and then, two
 * paragraphs later, tell the reader we buy from Kalshi. Matching only the first
 * would let the second hide behind it.
 */
export function findBannedCopy(text: string, bans: CopyBan[] = ALL_COPY_BANS): CopyBanHit[] {
  const hits: CopyBanHit[] = [];
  for (const ban of bans) {
    const scanner = new RegExp(
      ban.pattern.source,
      ban.pattern.flags.includes("g") ? ban.pattern.flags : `${ban.pattern.flags}g`
    );
    const judged = ATTRIBUTION_AWARE_BANS.has(ban.id);
    for (const hit of text.matchAll(scanner)) {
      const at = hit.index ?? 0;
      if (judged && isSourceAttribution(clauseAround(text, at))) continue;
      hits.push({
        ban,
        matched: hit[0],
        context: text.slice(Math.max(0, at - 90), at + 110).replace(/\s+/g, " ").trim(),
      });
      break;
    }
  }
  return hits;
}

/**
 * Rendered markup → the words a reader actually sees.
 *
 * Attributes go first and entities are decoded after, in that order. Stripping
 * tags without stripping attributes would drag `data-price-state="dark"` and
 * `class="border-dashed"` into the text and every banned word would "fail"
 * forever, which is how a guard like this gets deleted for crying wolf.
 */
export function visibleTextFromHtml(html: string): string {
  return html
    .replace(/<[^>]*>/g, " ")
    .replace(/&mdash;/g, "—")
    .replace(/&ndash;/g, "–")
    .replace(/&amp;/g, "&")
    .replace(/&#x27;|&apos;/g, "'")
    .replace(/&quot;/g, '"')
    .replace(/\s+/g, " ")
    .trim();
}

// ---------------------------------------------------------------------------
// Reading copy back out of a shipped JavaScript bundle
// ---------------------------------------------------------------------------

/**
 * String literals in a minified bundle, scanned SEQUENTIALLY.
 *
 * The obvious version of this — one global regex for `"([^"]*)"` — is wrong in
 * a way that looks right: run over minified code it happily matches from the
 * CLOSING quote of one literal to the OPENING quote of the next, so the
 * "strings" it returns are stretches of executable code. The first draft of
 * this scanner reported `===e.price_state)return null;if(` as user-facing copy
 * containing the word *price*. A gate that cries wolf on its own extraction
 * step is a gate somebody deletes.
 *
 * So this walks the source one character at a time and tracks what it is
 * inside. It handles `"`, `'` and backtick strings, escapes, and line and block
 * comments. It does NOT try to distinguish a regex literal from a division —
 * that needs a real parser — which is why `isProse` below is a second filter
 * and not a nicety.
 */
export function extractBundleStrings(source: string): string[] {
  const out: string[] = [];
  let i = 0;
  const n = source.length;
  while (i < n) {
    const c = source[i];
    if (c === "/" && source[i + 1] === "/") {
      while (i < n && source[i] !== "\n") i += 1;
      continue;
    }
    if (c === "/" && source[i + 1] === "*") {
      i += 2;
      while (i < n && !(source[i] === "*" && source[i + 1] === "/")) i += 1;
      i += 2;
      continue;
    }
    if (c === '"' || c === "'" || c === "`") {
      const quote = c;
      i += 1;
      let buf = "";
      while (i < n) {
        const d = source[i];
        if (d === "\\") {
          const e = source[i + 1];
          if (e === "x" || e === "u") {
            // `·` minifies to `\xb7` and `’` to `’`. Decoding them is not
            // cosmetic: a half-decoded escape leaves the letters `x`/`u` glued
            // to the next word, which both hides a real match at a word
            // boundary and makes the failure report unreadable.
            const isBrace = e === "u" && source[i + 2] === "{";
            const start = i + (isBrace ? 3 : 2);
            const end = isBrace ? source.indexOf("}", start) : start + (e === "x" ? 2 : 4);
            const hex = source.slice(start, end);
            if (/^[0-9a-fA-F]+$/.test(hex)) {
              buf += String.fromCodePoint(parseInt(hex, 16));
              i = end + (isBrace ? 1 : 0);
              continue;
            }
          }
          // Every other escape survives as its literal second character, which
          // is enough for a text sweep. Newlines become spaces so a word
          // boundary still lands where a reader would see one.
          buf += e === "n" || e === "t" || e === "r" ? " " : e ?? "";
          i += 2;
          continue;
        }
        if (d === quote) {
          i += 1;
          break;
        }
        // A `${` inside a template literal ends this static chunk; the
        // interpolated expression is code, and the chunk after it is its own
        // piece of copy. Splitting here is why "…for ${n} questions" cannot be
        // stitched into a sentence that never existed.
        if (quote === "`" && d === "$" && source[i + 1] === "{") {
          out.push(buf);
          buf = "";
          let depth = 1;
          i += 2;
          while (i < n && depth > 0) {
            if (source[i] === "{") depth += 1;
            else if (source[i] === "}") depth -= 1;
            i += 1;
          }
          continue;
        }
        buf += d;
        i += 1;
      }
      out.push(buf);
      continue;
    }
    i += 1;
  }
  return out;
}

/**
 * ═══ COPY THAT ARRIVED THROUGH AN IMPORTED `.json` FILE ═══
 *
 * webpack inlines `import data from "./series.json"` as ONE literal:
 *
 *   var n = JSON.parse('{"caption":"Alcaraz win probability … (Polymarket)", …}')
 *
 * `extractBundleStrings` returns that whole document as a single string, and
 * `isProse` then rejects it on the braces — correctly, because as a string it
 * IS code-shaped. The consequence was a hole with the same shape as the one
 * this whole file exists to close: every sentence inside a JSON fixture was
 * invisible to the shipped-copy scan, so a page could serve banned copy from
 * a fixture and the gate would report clean.
 *
 * Found 2026-08-28 by UX-P155. Its render rig read a venue name off the
 * `/about` markup that this scanner had just passed as clean — the caption on
 * the Alcaraz chart, which lives in `lib/data/alcaraz-ao-2026-series.json`.
 * The caption itself turned out to be legitimate attribution; the blind spot
 * was not.
 *
 * So: a literal that parses as a JSON object or array is expanded into the
 * strings inside it, each judged on its own. Keys are skipped — they are
 * identifiers, and `Object.values` is what drops them.
 */
export function expandJsonPayload(literal: string): string[] | null {
  const s = literal.trim();
  const looksJson =
    (s.startsWith("{") && s.endsWith("}")) || (s.startsWith("[") && s.endsWith("]"));
  if (!looksJson) return null;
  let parsed: unknown;
  try {
    parsed = JSON.parse(s);
  } catch {
    return null;
  }
  const out: string[] = [];
  const walk = (value: unknown) => {
    if (typeof value === "string") out.push(value);
    else if (Array.isArray(value)) value.forEach(walk);
    else if (value && typeof value === "object") Object.values(value).forEach(walk);
  };
  walk(parsed);
  return out;
}

/**
 * Does this literal look like a sentence somebody wrote for a reader?
 *
 * Deliberately conservative in the direction of MISSING code rather than
 * missing copy: a bundle holds tens of thousands of identifiers, css class
 * strings and enum values, and one false positive in a deploy gate costs more
 * than one extra pass of the sweep.
 */
export function isProse(literal: string): boolean {
  const s = literal.trim();
  if (s.length < 8) return false;
  // At least two real words and a space between something. Requiring the two
  // words to be ADJACENT was too strict and quietly dropped real copy:
  // "Polymarket & Kalshi ·" is a source chip a reader looks at, and no two of
  // its words touch. Identifiers (`priced_cells`) have no space at all, and
  // Tailwind strings are caught by the bracket and css rules below.
  if (!/\s/.test(s)) return false;
  if ((s.match(/[A-Za-z]{3,}/g) ?? []).length < 2) return false;
  // Anything carrying operators or statement punctuation is code that this
  // extractor mis-sliced, or a template of class names.
  if (/[{}<>\\]|=>|===|!==|\|\||&&|;|\+\+|\$\{/.test(s)) return false;
  if (/\b(function|return|typeof|undefined|null|prototype|Symbol)\b/.test(s)) return false;
  // Tailwind's arbitrary-value syntax — `max-w-[62ch]`, `text-[11.5px]`. The
  // decimal point inside it defeats the "no sentence punctuation" test below,
  // so this marker is what actually rejects a className string.
  if (/-\[[^\]]*\]/.test(s)) return false;
  // Tailwind and css: runs of `token-token` separated by spaces, no sentence
  // punctuation and no capital letter starting a word.
  if (/^[a-z0-9:\-/[\].% ]+$/.test(s) && !/[.,?!]/.test(s)) return false;
  return true;
}

export interface BundleCopyHit extends CopyBanHit {
  /** The chunk the literal came from, for the report. */
  file: string;
  /** The route the chunk belongs to — stable across builds, unlike `file`. */
  surface: string;
  literal: string;
}

/**
 * Which SURFACE a chunk belongs to.
 *
 * Next names route chunks `app/<route>/page-<hash>.js` and shared chunks
 * `<number>-<hash>.js`, and both the hash AND the leading number change on
 * every build. Anything keyed on a filename resets itself the first time
 * somebody edits an unrelated page.
 */
export function surfaceOf(file: string): string {
  const normalised = file.replace(/\\/g, "/");
  const m = normalised.match(/(?:^|\/)app\/([^/]+)/);
  return m ? `app/${m[1]}` : "shared";
}

/** Apply the rules to one bundle chunk's prose literals. */
export function scanBundleSource(
  file: string,
  source: string,
  bans: CopyBan[] = ALL_COPY_BANS
): BundleCopyHit[] {
  const hits: BundleCopyHit[] = [];
  for (const raw of extractBundleStrings(source)) {
    // An inlined `.json` import is one code-shaped literal holding many real
    // sentences — see `expandJsonPayload`. Everything else is itself.
    for (const literal of expandJsonPayload(raw) ?? [raw]) {
      if (!isProse(literal)) continue;
      for (const hit of findBannedCopy(literal, bans)) {
        hits.push({ ...hit, file, surface: surfaceOf(file), literal: literal.trim().slice(0, 200) });
      }
    }
  }
  return hits;
}
