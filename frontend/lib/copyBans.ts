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
 *
 * ═══ WHAT IS BANNED, AND ON WHOSE AUTHORITY ═══
 *
 * | Group | Ruling | Clause |
 * |---|---|---|
 * | `JARGON_BANS` | UX-P145, Alex 2026-08-27 | our pipeline's nouns are not the reader's |
 * | `TRADING_VOCAB_BANS` | ruling 138, Alex 2026-08-27 | the word is PROBABILITY, never *price* |
 * | `VENUE_BANS` | ruling 141 AS AMENDED, Alex 2026-08-28 | a page may not talk ABOUT its suppliers; it may still say which line is whose |
 * | `FUTURE_PROMISE_BANS` | ruling 142, Alex 2026-08-28 | a section states what it IS, not what it WILL be |
 * | `PRICE_FORMAT_BANS` | the standing no-price-format ruling, #2442 | the reader gets a probability, never a betting line |
 * | `HISTORY_CLAIM_BANS` | CERT-537 (UX-P212), no ruling yet | our voice may not settle a question about ALL OF HISTORY |
 *
 * ⚠️ THE LAST ROW'S AUTHORITY IS A CERT FINDING, NOT AN ALEX RULING, AND THAT
 * IS STATED RATHER THAN PAPERED OVER. Every other group here cites a ruling.
 * This one encodes a graded BLOCK plus the doctrine line UX-P212 paid for; it
 * is narrower than a ruling would be (see the group's own header for the line
 * it deliberately does not cross) and it wants one.
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
 * THE STANDING NO-PRICE-FORMAT RULING, FINALLY WITH A GATE (#2442).
 *
 * ═══ WHY THIS GROUP EXISTS ═══
 *
 * Alex, reading `/events/15293846` during the tournament on 2026-08-31, counted
 * **six gambling formats on one screen**: `Betting Odds (market)`,
 * `Individual sportsbooks`, `Sportsbooks`, `+4.5`, `spread`, `total`. His note:
 * *a ratified rule being broken on the flagship page.*
 *
 * It had been ratified and never encoded. The other four groups in this file
 * each got a gate the day they were ruled; this one lived as a habit, and a
 * habit is what a page drifts away from between reviews. The whole argument of
 * this file — that a sweep proves something about a working tree and a GATE
 * proves something about a reader — applies to it exactly as written.
 *
 * ═══ WHAT IS BANNED, AND WHAT IS DELIBERATELY NOT ═══
 *
 * Narrow on purpose. This file's own recorded failure mode is a broad rule that
 * fires on the product's real content and gets switched off within a week, so
 * every pattern here is a phrase only a betting slip produces.
 *
 * **Not banned, and each omission is a decision:**
 *
 *   • **The bare word `odds`.** Alex's own instruction on #2442 — *"the word
 *     odds alone is fine — do not over-rotate"*. `The Odds API` is a supplier's
 *     name and `Betting Odds` is caught by the source-name normaliser at the
 *     render, not by a text rule that would also fail our own vendor.
 *   • **The bare word `total`.** It is an ordinary English noun that the pace
 *     card, the calibration tables and every scoring surface use correctly. The
 *     betting sense is caught by the `spread`-family pattern's neighbours
 *     instead, and by the render guard on the sections themselves.
 *   • **American odds (`-150 / +130`).** DELIBERATELY ABSENT, and this is the
 *     trap: `/about` carries `Not "-150 / +130" — just probabilities` directly
 *     under its 60/40 display, and that line is the product's founding
 *     argument. Alex was asked in 2026-07-31 and ruled it stays. The rule bans
 *     a betting format used as a **selling point**; it does not ban naming the
 *     format we refuse to show. A pattern here could not tell those apart, and
 *     a compliance-minded sweep would delete the counter-example and silently
 *     destroy the page's argument.
 *
 * ═══ WHAT THIS GROUP CANNOT SEE, AND WHAT COVERS IT ═══
 *
 * `handicap-notation` scores **zero** hits on the built bundle and is still the
 * single string Alex quoted first. That is not a dead rule — `BER +4.5` is
 * ASSEMBLED AT RUNTIME from a team abbreviation and a threshold, so no literal
 * of it exists to scan. A bundle gate is structurally blind to every label
 * built from data, which is why the render guard
 * (`__tests__/components/eventPriceFormats.test.tsx`) is the primary instrument
 * for this group and the bundle scan is the backstop. Keeping the pattern here
 * means a future hard-coded example is caught by both.
 */
export const PRICE_FORMAT_BANS: CopyBan[] = [
  {
    id: "betting-spread-noun",
    // The betting NOUN, identified by the word in front of it. A bare
    // `/\bspread\b/` would fire on the verb ("spread across four rounds") and
    // on `buildDensityFromSpreads`-shaped prose, which is how a rule like this
    // earns its deletion.
    pattern:
      /\b(point|pregame|pre-game|projected|game|the|full[- ]game|closing|opening|against the)\s+spreads?\b/i,
    why: 'the point spread is a betting line — the reader gets a margin in the sport\'s own units (#2442)',
  },
  {
    id: "handicap-notation",
    // `BER +4.5`, `WAW -1.5`. An uppercase competitor abbreviation followed by
    // a signed number is a handicap and nothing else; a real sentence does not
    // produce that shape.
    pattern: /\b[A-Z]{2,4}\s[+−-]\d+(\.\d+)?\b/,
    why: 'a signed handicap beside a competitor is a betting line, not a margin (#2442)',
  },
  {
    id: "over-under",
    pattern: /\bover\s*[/-]\s*under\b|\bo\/u\b/i,
    why: '"over/under" is the betting name for a total (#2442)',
  },
  {
    id: "moneyline",
    pattern: /\bmoney\s?line\b/i,
    why: 'the moneyline is the price we convert AWAY from — the reader gets the probability (#2442)',
  },
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
 */
export const HISTORY_CLAIM_BANS: CopyBan[] = [
  {
    id: "ever-reached-us",
    pattern: /\b(ever|never) (reached|arrived at|came to|got to) us\b/i,
    why: "quantifies over all of history; the payload carries the latest observation, not the archive (CERT-537)",
  },
  {
    id: "no-reading-ever",
    pattern: /\bno (number|price|probability|reading|quote|answer|market|data)s?\b[^.!?]{0,40}\bever\b/i,
    why: "quantifies over all of history; the payload carries the latest observation, not the archive (CERT-537)",
  },
  {
    id: "we-never-had",
    pattern: /\bwe (have )?never (had|held|received|saw|seen|got|read|recorded)\b/i,
    why: "a claim about our whole record, made from a payload that carries only the newest reading (CERT-537)",
  },
  {
    id: "was-never-complete",
    pattern: /\bwas never (complete|completed|available|quoted|published|reported|answered)\b/i,
    why: "settles a question about the past that no field on the card records (CERT-537)",
  },
  {
    id: "nobody-ever",
    pattern: /\b(nobody|no one|no-one) ever\b/i,
    why: "quantifies over all of history; we cannot tell a market nobody quoted from one we were not reading (CERT-537)",
  },
  {
    id: "at-no-point",
    pattern: /\bat no point\b/i,
    why: "quantifies over all of history; the payload carries the latest observation, not the archive (CERT-537)",
  },
];

/** Every rule, in the order a report should read them. */
export const ALL_COPY_BANS: CopyBan[] = [
  ...JARGON_BANS,
  ...TRADING_VOCAB_BANS,
  ...VENUE_BANS,
  ...FUTURE_PROMISE_BANS,
  ...PRICE_FORMAT_BANS,
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
