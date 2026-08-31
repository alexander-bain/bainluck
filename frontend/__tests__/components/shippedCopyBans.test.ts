/**
 * UX-P150 — THE COPY GUARD READS WHAT SHIPPED, NOT WHAT IS IN THE TREE.
 *
 * ═══ THE INCIDENT ═══
 *
 * UX-P145 swept the tournament copy for internal vocabulary. UX-P146 swept it
 * again for ruling 138's ban on the word *price*. Both were real sweeps, both
 * had render guards, both reported done. On 2026-08-28 Alex opened the LIVE
 * page and read:
 *
 *   > "No prices yet. We have not recorded a price for today's matches."
 *   > "Once the main draw starts, Kalshi and Polymarket list more of them…
 *   >  and the ones worth asking appear here as they are priced."
 *
 * Every one of those strings had been fixed. None of the fixes had landed. The
 * branch was clean and the guards were green because the guards read
 * `components/tournament/*.tsx` and `renderToStaticMarkup` — a working tree
 * and a fixture. Neither is a reader.
 *
 *   > Extend the pinned copy test to run against the strings the PRODUCTION
 *   > bundle serves, so branch-only sweeps can never look done again.
 *   > — Alex, 2026-08-28
 *
 * ═══ WHAT THIS FILE DOES, IN THREE LAYERS ═══
 *
 * 1. THE PREDICATE, PINNED. Every retired sentence Alex quoted is rendered
 *    back through the rules and MUST be rejected, and a set of legitimate
 *    strings MUST survive. A banned-word test that has never seen a banned
 *    word is a test whose regexes are wrong.
 *
 * 2. THE LOCAL BUILD. `.next/static/chunks` is the exact byte stream Vercel
 *    uploads. Scanning it catches everything the render guard cannot reach:
 *    copy in a branch a fixture never takes, copy in a component no test
 *    imports, copy in a page. CI runs `npm run build` before this suite, so in
 *    CI the directory is always there — and when it IS there and this test
 *    finds nothing, that is a claim about the artifact rather than the source.
 *
 * 3. PRODUCTION, ON DEMAND. Point `SHIPPED_BUNDLE_DIR` at a directory filled
 *    by `scripts/fetch-shipped-copy.mjs` and the same rules run over the
 *    chunks a browser downloaded from bainluck.com. That is the only layer
 *    that can answer "is it on production", and it is the one the ship proof
 *    for this queue is taken from.
 *
 * ═══ WHY LAYERS 2 AND 3 ARE CONDITIONAL, AND WHY THAT IS NOT A SILENT SKIP ═══
 *
 * A guard that quietly no-ops when its input is missing is worse than no
 * guard: it reports green and teaches everyone to trust it. So the bundle scan
 * is conditional on the directory EXISTING, and `it("...")` logs loudly and
 * names the exact command when it is not — plus `ciRequiresBundle` makes the
 * absence a hard failure under `CI`, where `npm run build` has always run and
 * a missing `.next` means the gate was skipped rather than satisfied.
 */

import fs from "node:fs";
import path from "node:path";

import {
  ALL_COPY_BANS,
  ATTRIBUTION_LITERALS,
  FUTURE_PROMISE_BANS,
  HISTORY_CLAIM_BANS,
  VENUE_BANS,
  clauseAround,
  expandJsonPayload,
  extractBundleStrings,
  findBannedCopy,
  isProse,
  isSourceAttribution,
  MARKET_OBJECT_NOUNS,
  NO_READING_COPY_BANS,
  OUR_SUBJECT_NOUNS,
  READING_NOUNS,
  scanBundleSource,
  surfaceOf,
  type BundleCopyHit,
} from "@/lib/copyBans";
import { FRESHNESS_DEFINITION } from "@/lib/tournamentProps";

/* ───────────────────────── layer 1: the predicate ───────────────────────── */

describe("the rules reject the copy Alex read on production", () => {
  /**
   * Verbatim, from Alex's 2026-08-28 review of the live page. Each entry is a
   * sentence that WAS served to a reader; each must be rejected, and the
   * comment names the rule it must be rejected BY, so a rule that stops
   * existing cannot be covered for by a neighbour.
   */
  const RETIRED: [string, RegExp][] = [
    // ruling 138 — the word is PROBABILITY
    ["No prices yet. We have not recorded a price for today's matches.", /price/i],
    ["47 matches have prices that do not agree yet.", /price/i],
    ["We know who is in this draw, but nobody has priced it yet.", /price/i],
    ["cells carry a market price.", /price/i],
    ["They come back when they are priced again.", /price/i],
    // ruling 141 — venue names
    ["we asked Kalshi and Polymarket and neither runs that market.", /venue|Kalshi/i],
    ["Polymarket 20 days ago", /venue|Polymarket/i],
    // ruling 142 — future-tense promises
    ["New questions are coming — check back soon.", /promise|later|coming/i],
    ["Matches appear here as they are scheduled.", /section WILL|appear here/i],
    ["Questions about sets, games and margins appear here as soon as anyone opens one.", /appear here|future|promise/i],
    ["It is in the draw; the number comes later.", /later/i],
    // the whole sentence, all three rulings at once — Alex's headline example
    [
      "Once the main draw starts, Kalshi and Polymarket list more of them beyond who-reaches-what, and the ones worth asking appear here as they are priced.",
      /./,
    ],
  ];

  it.each(RETIRED)("rejects %j", (sentence, whyPattern) => {
    const hits = findBannedCopy(sentence);
    expect(hits.length).toBeGreaterThan(0);
    // Not just "something fired" — the REASON has to be about the right thing,
    // or a stray `stale` rule could carry a venue-name test forever.
    expect(hits.map((h) => `${h.ban.id} ${h.ban.why}`).join(" | ")).toMatch(whyPattern);
  });

  it("the replacement for 'No market yet' passes — the fix is not itself banned", () => {
    expect(findBannedCopy("No probability yet")).toEqual([]);
  });

  /**
   * The other half, and the half that decides whether this guard survives
   * contact with a real page: it must NOT fire on the product's own content.
   * Market questions are written by markets and half of them start with
   * "Will"; a rule that eats those is a rule somebody turns off.
   */
  const ALLOWED = [
    "Will Sinner actually play?",
    "Who will be the men's singles champion?",
    "Can Sinner win a second major this year?",
    "How many slams for Alcaraz this year?",
    "Updates paused. These are the last probabilities we saw, not live ones.",
    "No market has put a probability on today's matches.",
    "This section holds the questions about this draw worth asking beyond who reaches which round.",
    "Nobody is quoting this match yet. It is in the draw with no probability against it.",
    "Nothing is on right now. This is where the day's matches sit.",
    "one reading 20 days ago",
    "This draw has none with a probability against them.",
    // UX-P155 — the four replacements for ruling 141's last narrative debt.
    // The failure mode of a copy fix is a replacement that trips a different
    // rule and gets reverted, so each new sentence is pinned as passing next
    // to the sentence it replaced (which is pinned as rejected, below).
    "Open questions, merged into one number",
    "Who wins each tournament, one number per golfer",
    "Daily “Will it rain?” questions, one per day",
    "Sportsbooks, ESPN, prediction markets, and live stat models each have a guess.",
  ];

  it.each(ALLOWED)("leaves legitimate copy alone: %j", (sentence) => {
    expect(findBannedCopy(sentence)).toEqual([]);
  });

  it("every rule is reachable — no rule is dead weight", () => {
    // A rule nobody can trigger is a rule that will be silently broken by the
    // next refactor of the regex list.
    for (const ban of ALL_COPY_BANS) {
      expect(ban.pattern.source.length).toBeGreaterThan(2);
      expect(ban.why).not.toEqual("");
      expect(ban.id).toMatch(/^[a-z0-9-]+$/);
    }
    const ids = ALL_COPY_BANS.map((b) => b.id);
    expect(new Set(ids).size).toBe(ids.length);
  });

  it("the venue ban is case-sensitive on purpose — the source ids survive", () => {
    // `kalshi` and `polymarket` are enum values on `source`, `group_id` and
    // `stale_sources`, and they are read by the sentinels and CERT-411. The
    // ruling is about a NAME in a sentence, so the pattern is capitalised.
    expect(findBannedCopy("Kalshi is where we read that.", VENUE_BANS).length).toBe(1);
    expect(findBannedCopy('source: "kalshi"', VENUE_BANS)).toEqual([]);
    expect(findBannedCopy('group_id: "polymarket:12345"', VENUE_BANS)).toEqual([]);
  });

  /**
   * ═══ RULING 141 AS AMENDED — THE HALF UX-P150 DID NOT HAVE ═══
   *
   * Queue 013 ran under the ruling as first written ("banned in user-facing
   * copy, everywhere") and Alex narrowed it the same day: banned when the copy
   * is ABOUT our sourcing, allowed — "and often good" — when it attributes a
   * number or line the reader is looking at.
   *
   * A blanket name ban and the amended rule disagree about real strings, so
   * this block pins both sides of the line. The narrative half repeats what
   * UX-P150 removed, because the amendment explicitly KEEPS those two removals
   * and the risk now runs the other way: a rule loosened to admit captions
   * could quietly re-admit the empty state Alex was reading.
   */
  describe("a venue name attributing a number is allowed; talking about our suppliers is not", () => {
    const ATTRIBUTION = [
      // Chart series names — Alex's own example of the allowed class.
      "Kalshi Implied",
      "Polymarket Implied",
      // Source chips beside a figure, from /weather and /politics.
      "Polymarket & Kalshi ·",
      "Kalshi · 10 cities",
      "Both Kalshi and Polymarket",
      // A provenance caption fenced by the design system's separators.
      "Polymarket · atp-alcaraz-zverev-2026-01-30 · real price series",
      // Two venues attributing two numbers on one row.
      "Polymarket 27% · Kalshi 22%",
      // The descriptive caption that needs ATTRIBUTION_LITERALS to be seen.
      "DataGolf win-probability model + Kalshi futures",
    ];

    it.each(ATTRIBUTION)("attribution passes: %j", (label) => {
      expect(findBannedCopy(label, VENUE_BANS)).toEqual([]);
    });

    const NARRATIVE = [
      // The two removals ruling 141 pins. Both must stay rejected.
      "we asked Kalshi and Polymarket and neither runs that market.",
      "Polymarket 20 days ago",
      // Promotional and coverage claims — the class the ruling was issued at.
      "Kalshi + Polymarket, unified",
      "Tournament odds from Polymarket, Kalshi, sportsbooks & DataGolf",
      "Sportsbooks, ESPN, Kalshi, Polymarket, and live stat models each have a guess.",
      // Verbatim as it shipped, curly quotes and all. It was paraphrased here
      // while it was live; now that it is retired the pin has to be the real
      // string, because `?` is a clause boundary and the paraphrase never
      // exercised the split.
      "Daily “Will it rain?” markets from Kalshi",
      // An apposition is a sentence, not a label — the em dash must not fence
      // the venue names off into a label-shaped middle.
      "Our sources — Kalshi and Polymarket — each have a guess.",
    ];

    it.each(NARRATIVE)("narrative is rejected: %j", (sentence) => {
      expect(findBannedCopy(sentence, VENUE_BANS).length).toBeGreaterThan(0);
    });

    it("judges each occurrence, so a caption cannot shelter a sentence", () => {
      // One string, both uses. Matching only the first occurrence — which is
      // what the pre-amendment `text.match()` did — would return the caption,
      // find it allowed, and report the page clean.
      const both = "Kalshi Implied. We read every number from Kalshi and Polymarket.";
      const hits = findBannedCopy(both, VENUE_BANS);
      expect(hits.map((h) => h.ban.id).sort()).toEqual(["venue-kalshi", "venue-polymarket"]);
    });

    it("the clause, not the whole page, is the unit of judgment", () => {
      // The render sweep hands this function a whole component's visible text.
      // A legitimate chip must survive being next to prose, and prose must not
      // be excused by a chip three sentences away.
      const page =
        "Alcaraz 62%. Kalshi Implied. Nobody is answering that question, so we have nothing to show.";
      expect(findBannedCopy(page, VENUE_BANS)).toEqual([]);
      expect(clauseAround(page, page.indexOf("Kalshi"))).toBe(" Kalshi Implied");
    });

    it("every ATTRIBUTION_LITERALS entry is still doing work", () => {
      // Same discipline as OWED: an entry that the shape rule now handles on
      // its own is a hand-written exception nobody needs, and leaving it makes
      // the next reader think the shape rule is weaker than it is.
      for (const entry of ATTRIBUTION_LITERALS) {
        expect(entry.why).not.toEqual("");
        expect(findBannedCopy(entry.literal, VENUE_BANS)).toEqual([]);
        // Strip the literal to its shape and it must NOT pass on shape alone.
        expect(isSourceAttribution(entry.literal.replace(/Kalshi|Polymarket/g, "X"))).toBe(false);
      }
    });
  });

  it("the future-promise rules do not fire on a market question", () => {
    for (const q of ["Will Djokovic reach the final?", "Will there be a five-setter?"]) {
      expect(findBannedCopy(q, FUTURE_PROMISE_BANS)).toEqual([]);
    }
  });

  /**
   * ═══ CERT-537 — OUR VOICE MAY NOT SETTLE A QUESTION ABOUT ALL OF HISTORY ═══
   *
   * `HISTORY_CLAIM_BANS` is the newest group and the only one whose authority
   * is a graded cert rather than an Alex ruling, so it is pinned harder than
   * the others: the blocked sentences on one side, the shipped replacements on
   * the other, and — because this rule lives one word away from vocabulary the
   * product genuinely needs — a third list of TRUE past-tense copy that must
   * survive it.
   *
   * The reasoning for the line it draws is in `lib/copyBans.ts`. The short
   * version: an absolute quantifier over our receipt of a number is
   * unsupportable in every wire shape, so a text scan can judge it; "…yet" is
   * conditionally true, so a component judges it by reading `observed_at`.
   */
  describe("an absolute claim about all of history is rejected", () => {
    const HISTORY_CLAIMS: [string, RegExp][] = [
      // Verbatim, UX-P211 as shipped to CERT-537. Both halves of the sentence
      // are independently banned, which is why the ban ids are asserted rather
      // than a bare "something fired".
      [
        "No number ever reached us for Iga Swiatek, so this comparison was never complete.",
        /ever-reached-us|no-reading-ever|was-never-complete/,
      ],
      ["No number ever reached us for Carlos Alcaraz.", /ever-reached-us/],
      ["We never received a probability for this question.", /we-never-had/],
      ["We have never seen a number on this market.", /we-never-had/],
      ["Nobody ever quoted this match.", /nobody-ever/],
      ["At no point did a probability arrive for this leg.", /at-no-point/],
      ["This comparison was never complete.", /was-never-complete/],

      // ═══ CERT-539 — the five rewordings that passed BOTH layers ═══
      //
      // Every one of these makes the identical all-of-history claim about our
      // receipt of a number, and every one walked around all six of the
      // original patterns AND the shipped-bundle scanner. They are listed
      // verbatim as the cert executed them, so a future narrowing that
      // re-opens any single family fails here by name.
      [
        "There has never been a probability for this market.",
        /there-was-never-a-reading/,
      ],
      ["This question never had a probability.", /never-had-a-reading/],
      [
        "We have not once received a number for this market.",
        /not-once-received/,
      ],
      ["We did not receive a number at any time.", /no-reading-at-any-time/],
      [
        "A probability has never been available for this question.",
        /reading-never-been/,
      ],

      // ═══ CERT-547 — the claims that ESCAPED, and why they did ═══
      //
      // Every verb rule spelled its determiner `(?:a |an |any )?` and simply
      // had no arm for `the`. So the plainest form of each claim — the one a
      // writer reaches for first — walked straight through all eleven rules
      // while the paraphrases CERT-539 added were caught. The determiner list
      // is now `DET`, in one place, and these pin it.
      //
      // ⚠️ These are also the reason the vocabulary could not simply be
      // narrowed: admitting `the` widens every rule at once, so the scope had
      // to move to `PAGE_SUBJECT` in the same change.
      [
        "We never received the probability for this question.",
        /we-never-had|never-had-a-reading/,
      ],
      ["This question never had the number.", /never-had-a-reading/],
      [
        "We have not once received the number for this market.",
        /not-once-received/,
      ],
      [
        "There has never been the probability for this market.",
        /there-was-never-a-reading/,
      ],
      // The same claim in the determiners a writer actually varies between.
      [
        "We never had a single reading for this market.",
        /we-never-had|never-had-a-reading/,
      ],
      ["This market never had one probability.", /never-had-a-reading/],
      // `nobody-ever`'s surviving verbs, each on a page subject.
      ["Nobody ever priced this question.", /nobody-ever/],
      ["Nobody ever listed this leg.", /nobody-ever/],
      // `no-reading-ever` and `at-no-point` were anchored in this repair too
      // (see the prose corpus). This keeps the first reachable in its anchored
      // form; `at-no-point`'s existing specimen above already is one, because
      // "…arrive for this leg" leaves the subject OUTSIDE the matched core.
      //
      ["No probability ever arrived for this market.", /no-reading-ever/],

      // ═══ CERT-549 — a core that SPANS the page subject ate its own anchor ═══
      //
      // 🔴 THIS EXACT SENTENCE WAS DOCUMENTED IN-TREE AS A KNOWN LIMIT AND THE
      // BRANCH WAS STAGED ANYWAY. The comment that used to sit here explained
      // why "At no point did this leg carry a probability." could not fire —
      // `at-no-point`'s own `[^.!?]{0,60}` gap swallows "this leg", so
      // `anchored` looked for a SECOND page subject and found none — and then
      // told the next reader not to be surprised. **A documented hole is still
      // a hole**, and the cert found it in one probe.
      //
      // `anchored`'s second arm is now a clause-scoped LOOKAHEAD instead of a
      // suffix, so the subject may sit anywhere ahead in the clause, including
      // inside the core. It strictly subsumes the arm it replaced.
      ["At no point did this leg carry a probability.", /at-no-point/],
      // The same shape on the other rule whose core can span its subject.
      ["At no point did this market carry a price.", /at-no-point/],
      // ⚠️ MAKES THE REST OF `PAGE_SUBJECT` LOAD-BEARING. Mutant I (narrowing it
      // to `this` alone) SURVIVED the first battery because every claim above
      // says "this". A writer who says "that market" is making the same
      // unsupportable claim and must not be served by the demonstrative they
      // happened to pick.
      [
        "We never had a probability for that market.",
        /we-never-had|never-had-a-reading/,
      ],
    ];

    it.each(HISTORY_CLAIMS)("rejects %j", (sentence, whyPattern) => {
      const hits = findBannedCopy(sentence, HISTORY_CLAIM_BANS);
      expect(hits.length).toBeGreaterThan(0);
      expect(hits.map((h) => h.ban.id).join(" | ")).toMatch(whyPattern);
    });

    /**
     * The replacements `incompleteComparisonNote` now emits, pinned as PASSING
     * beside the sentences they retired. A copy fix that trips a neighbouring
     * rule is a copy fix that gets reverted, and this group is close enough to
     * the retired wording that the risk is real rather than theoretical.
     */
    const REPLACEMENTS = [
      "We have no number for Iga Swiatek, so this comparison is not complete and the question has closed.",
      "We have no number for Carlos Alcaraz yet, so this comparison is not complete.",
      "We have no number for 3 of the names in it, so this comparison is not complete and the question has closed.",
    ];

    it.each(REPLACEMENTS)("the shipped replacement passes: %j", (sentence) => {
      expect(findBannedCopy(sentence)).toEqual([]);
    });

    /**
     * ⚠️ THE HALF THIS GROUP DELIBERATELY DOES NOT BAN.
     *
     * "…has not reached us yet" is FALSE only when `observed_at` is populated,
     * which a string cannot know. UX-P212 fixed that where it belongs, in the
     * component. Pinning it as passing here is not an endorsement of the
     * sentence — it records that the copy layer is knowingly silent about it,
     * so a later reader does not "complete" this group by adding the pattern
     * and discovering, one cert later, that it fires on correct copy.
     */
    it("the conditional tense is left to the component, on purpose", () => {
      expect(
        findBannedCopy("No number has reached us for Carlos Alcaraz yet.", HISTORY_CLAIM_BANS)
      ).toEqual([]);
    });

    /**
     * The reason this group is six narrow patterns and not `\bnever\b`. Every
     * string below is real copy in this tree, every one is TRUE and supported
     * by the data behind it, and a broad rule eats all of them.
     */
    const TRUE_PAST_TENSE = [
      // components/PropDivergence*.tsx — a status a market really has.
      "settled but never graded",
      // lib/calibrationCohort.ts — a cohort DEFINED by the fact it states.
      "Excluded: 412 untraded outcomes, whose price never moved off its opening line.",
      "that never moved does not prove that it didn't.",
      // lib/story-content.ts — a product promise, not a claim about our data.
      "No odds formats, ever. Nothing to deposit, nothing to buy.",
      // A market question may contain the word; markets write these, not us.
      "Will Djokovic ever win another major?",
      // The freshness copy the page really ships: bounded, and about what we
      // HAVE rather than about all of history.
      "Updates paused. These are the last probabilities we saw, not live ones.",
      "No market has put a probability on today's matches.",
      "Nobody is quoting this match yet. It is in the draw with no probability against it.",

      // ═══ CERT-539 — the three sentences the group used to reject wrongly ═══
      //
      // None of these says anything about our receipt of a number: they are
      // ordinary supported sports and chart prose, and each one would have
      // failed a product-wide build gate on copy that is simply true. The
      // patterns that matched them (`at-no-point`, `was-never-complete`,
      // `nobody-ever`) are now bound to a reading noun, a page subject and a
      // quoting verb respectively.
      "At no point did either player face a break point.",
      "The comeback was never complete.",
      "Nobody ever scored more than 30 points in this game.",

      // The near-misses of those three narrowings, so a re-widening is caught
      // at the edge rather than only in the middle.
      "You can dismiss this at any time.",
      "The chart shows the comeback was never complete.",
      "Nobody ever led by more than two breaks.",
      "At no point was the match in doubt.",

      // ═══ CERT-546 — the two the CERT-539 repair still got wrong ═══
      //
      // `we-never-had` was left untouched by that repair because the cert had
      // not named it, and `not-once-received` was written new WITHOUT an object
      // — the UX-P215b report named it as the most likely thing wrong and then
      // shipped it anyway. Both are now bound to `READING` like their siblings.
      "We never had a chance after halftime.",
      "The quarterback has not once received a snap under center.",

      // ═══ Found by sweeping EVERY pattern after CERT-546, not just its two ═══
      //
      // `nobody-ever` was bound to a verb list, which is only half a scope: the
      // verbs collide with ordinary prose the moment the object is not ours.
      // No cert named these; the sweep did.
      "Nobody ever reported the score.",
      "Nobody ever offered him a contract.",
      "Nobody ever posted a better time.",
      "Nobody ever traded places with him.",
      "We never got a look at the second serve.",
      "We have never seen a comeback like it.",
    ];

    it.each(TRUE_PAST_TENSE)("supported past-tense copy survives: %j", (sentence) => {
      expect(findBannedCopy(sentence, HISTORY_CLAIM_BANS)).toEqual([]);
    });

    /**
     * ═══ THE CLASS GUARD CERT-546 ASKED FOR WITHOUT SAYING SO ═══
     *
     * 🔴 A CERT'S FINDING LIST IS A SAMPLE, NOT A CENSUS. CERT-539 named three
     * over-broad patterns; the repair narrowed those three and left a fourth
     * (`we-never-had`) untouched because nobody had pointed at it, and wrote a
     * fifth (`not-once-received`) with no object at all. CERT-546 then found
     * both. Fixing named instances one cert at a time is how a group takes four
     * rounds to converge.
     *
     * This is the census. Every sentence below uses one of this group's own
     * grammatical shapes — "never had a ___", "not once received a ___",
     * "nobody ever <verb> ___", "there has never been a ___", "at no point ___"
     * — with an object that is NOT a reading, NOT a market and NOT a thing on
     * our page. Every one is ordinary supported prose. None may fire.
     *
     * ⚠️ A NEW PATTERN IN THIS GROUP MUST BE RUN AGAINST THIS LIST, and the
     * cheapest way to make sure it is, is that this test already runs against
     * ALL of `HISTORY_CLAIM_BANS` rather than naming any of them. An unbound
     * rule cannot be added without turning this red.
     *
     * ═══ CERT-547, AND WHY THE CENSUS ABOVE WAS STILL NOT ONE ═══
     *
     * It was a census of SENTENCES somebody had thought of, which is a sample
     * wearing a census's name. Re-run mechanically against all eleven rules
     * after CERT-547, the group had **eight** false positives, not the two the
     * cert listed — `nobody-ever` alone fired on five, one for every pairing of
     * a general verb (`reported`, `posted`, `offered`, `published`) with a
     * `MARKET_OBJECT`. The cert had shown one corner of a product.
     *
     * 🔴 AND THE TWO ERROR DIRECTIONS WERE COUPLED, which is the real reason
     * this took four rounds. "This team never had the answer for their zone"
     * passed only because the determiner list omitted `the` — the very omission
     * that let CERT-547's false negatives ("We never received THE probability
     * for this question") escape. Fixing either direction alone re-opens the
     * other. They had to move together, and the scope had to stop living in the
     * noun list: see `PAGE_SUBJECT` in `lib/copyBans.ts`.
     *
     * The sentences below are therefore organised BY VOCABULARY MEMBER, and the
     * test after them requires every member of all three lists to appear here.
     */
    const ORDINARY_SPORTS_PROSE = [
      // ── the graded specimens, verbatim, oldest first ──
      "We never had a chance after halftime.",
      "The quarterback has not once received a snap under center.",
      "Nobody ever reported the score.",
      "Nobody ever offered him a contract.",
      "Nobody ever posted a better time.",
      "Nobody ever traded places with him.",
      "Nobody ever scored more than 30 points in this game.",
      "At no point did either player face a break point.",
      "At no point was the match in doubt.",
      "The comeback was never complete.",
      "The chart shows the comeback was never complete.",
      "There has never been a crowd like this one.",
      "There was never any doubt.",
      "This team never had a winning season.",
      "A champion has never been crowned here.",
      "He did not miss a first serve at any time.",
      "We never got a look at the second serve.",
      "We have never seen a comeback like it.",
      "You can dismiss this at any time.",
      // ── CERT-547's two, verbatim ──
      "Nobody ever reported the game was delayed.",
      "We never had an answer for their press.",
      // ── the five `nobody-ever` pairings the cert did not list ──
      "Nobody ever reported the match was postponed.",
      "Nobody ever posted the line for that contest.",
      "Nobody ever offered the outcome anyone wanted.",
      "Nobody ever published the event schedule.",
      "Nobody ever listed him among the favourites.",
      // ── the coupling cases: our nouns under `the`/`their`, which only the
      //    determiner bug was hiding. These are the ones that would have come
      //    back as CERT-548 had the two directions been fixed separately. ──
      "This team never had the answer for their zone.",
      "We never had the data to justify the trade.",
      "We never had the market cornered.",
      "There has never been a value like that on this roster.",
      "We never had a figure like him in the clubhouse.",
      "The chart shows the record was never complete.",
      "This game never had the answer anyone wanted.",
      "That contest never had a figure worth watching.",
      "No answer ever came from the bench.",
      // ── one per remaining vocabulary member, so the coverage test below can
      //    be satisfied honestly rather than by a keyword stuffed into a
      //    sentence nobody would write ──
      "He never had the number nine shirt.",
      "Nobody ever paid the price for that mistake.",
      "The probability of rain was high all afternoon.",
      "We never had a reading on the wind that day.",
      "We never had a quote from the coach.",
      "The estimate of the crowd was never released.",
      "This prop bet him to lead the league in tackles.",
      "The series went the distance for the first time.",
      "He never had a card shown against him.",
      "That leg of the relay was his fastest.",
      "The history between these two runs deep.",
      "A comparison with his rookie year flatters him.",
      "The only question was whether he would start.",
      // ── the two rules this repair left unanchored in its FIRST draft, and the
      //    sentences that proved that wrong. Found by sweeping, not by a cert:
      //    "no ___ ever" and "at no point ___" read as distinctive frames and
      //    are not. ──
      "At no point was the market in doubt.",
      "At no point did the line move.",
      "At no point was the outcome in question.",
      "No market ever felt out of reach for them.",
      "No data ever suggested he was slowing down.",
      "No number ever suited him better than 23.",
      // ⚠️ THE ONE THAT MAKES `nobody-ever`'s VERB LIST LOAD-BEARING. Mutant D
      // (restoring `reported|posted|offered|published`) SURVIVED the first
      // battery: every other control here says "the game", so the inline
      // demonstrative was doing all the work and the verb narrowing was
      // untested. This sentence pairs a general verb WITH a demonstrative, so
      // only the verb list can save it.
      "Nobody ever reported that outcome to the league.",
      // ── CERT-549's two false positives, verbatim ──
      //
      // 🔴 BOTH WERE SELF-DISCLOSED BY THE PREVIOUS ROUND AND SHIPPED ANYWAY.
      // The report called the dangling-preposition arm "the most attackable
      // line in the change" and left it; the cert attacked exactly it.
      // **A SELF-DISCLOSURE IS NOT A MITIGATION.**
      "The ball never reached us in the upper deck.",
      // A complete sentence that merely ENDS on a preposition. The interpolated
      // -subject arm accepted it because it spelled the trailing space `\s*`
      // instead of `\s+`; the space is the hole the `${…}` left, so it is the
      // one part of that shape that is not optional.
      "We never had a number to play for",
      // ── the three `ever-reached-us` false positives the SWEEP found and the
      //    cert did not name. Each satisfies the page anchor honestly — they
      //    really are about something on this page — so anchoring alone did not
      //    save them. The rule needed a READING as its SUBJECT: the anchor says
      //    where a claim lives, never what arrived. Fourth consecutive round in
      //    which sweeping beat the cert's list. ──
      "The ball never reached us before this game ended.",
      "The crowd never came to us during this contest.",
      "He never got to us in that game.",
    ];

    it.each(ORDINARY_SPORTS_PROSE)(
      "no history rule fires on prose with nothing of ours in it: %j",
      (sentence) => {
        const hits = findBannedCopy(sentence, HISTORY_CLAIM_BANS);
        expect(hits.map((h) => `${h.ban.id} on ${JSON.stringify(sentence)}`)).toEqual([]);
      }
    );

    /**
     * 🔴 THE MECHANISM THAT ENDS THE CYCLE.
     *
     * CERT-539, 546 and 547 each found a vocabulary member that had never been
     * tried against ordinary prose — `we-never-had`'s missing object, then
     * `not-once-received`'s, then `nobody-ever`'s verb list, then `answer` and
     * `figure` as nouns. Four rounds, each discovering one more member of a
     * list anybody could have enumerated on day one.
     *
     * So enumerate it. Every noun the scope is built from must appear in at
     * least one negative control above. A word cannot enter the vocabulary
     * without the sentence that proves it survivable arriving beside it, and
     * that sentence is written by the author rather than by the next cert.
     *
     * This is deliberately a coverage assertion and not a generated corpus: a
     * machine-built sentence proves the regex does not match a string, whereas
     * the point is whether a HUMAN would write it. The list is the promise; the
     * sentences are the evidence.
     */
    it("every scope noun has a negative control — no member enters untested", () => {
      const corpus = ORDINARY_SPORTS_PROSE.join(" ").toLowerCase();
      const uncovered = [
        ...new Set([
          ...READING_NOUNS,
          ...OUR_SUBJECT_NOUNS,
          ...MARKET_OBJECT_NOUNS,
        ]),
      ].filter((noun) => !new RegExp(`\\b${noun}s?\\b`).test(corpus));
      expect(uncovered).toEqual([]);
    });

    it("every history rule is reachable — none is dead weight", () => {
      // The `ALL_COPY_BANS` sweep above proves the ids are well-formed. This
      // proves each PATTERN can actually fire, which is the property that
      // decays silently when a regex is edited.
      for (const ban of HISTORY_CLAIM_BANS) {
        const fired = HISTORY_CLAIMS.some(([sentence]) =>
          findBannedCopy(sentence, [ban]).length > 0
        );
        expect([ban.id, fired]).toEqual([ban.id, true]);
      }
    });
  });
});

/* ─────────────────── the extractor, before it is trusted ─────────────────── */

describe("reading copy back out of minified JavaScript", () => {
  it("does not stitch two literals into one fake string", () => {
    // The bug that made the first draft of this scanner useless: a global
    // /"([^"]*)"/ run over minified code matches from the CLOSING quote of one
    // literal to the OPENING quote of the next, and reports the code between
    // them as copy. This is that exact shape.
    const src = 'if("dark"===e.price_state)return null;let t="No numbers yet";';
    const strings = extractBundleStrings(src);
    expect(strings).toContain("dark");
    expect(strings).toContain("No numbers yet");
    expect(strings.some((s) => s.includes("price_state"))).toBe(false);
  });

  it("splits a template literal at its interpolations", () => {
    // eslint-disable-next-line no-useless-escape
    const src = "const s=`We have not seen a new number on ${n} questions in a while.`;";
    const strings = extractBundleStrings(src);
    expect(strings).toContain("We have not seen a new number on ");
    expect(strings).toContain(" questions in a while.");
  });

  it("surfaceOf reads the ROUTE out of a chunk path, in both layouts", () => {
    // The local build nests them; `fetch-shipped-copy.mjs` reproduces the same
    // nesting on purpose. If either flattens, every route chunk becomes
    // "shared" and the tournament gate passes by scanning nothing.
    expect(surfaceOf("app/tournaments/[slug]/page-0a584f.js")).toBe("app/tournaments");
    expect(surfaceOf("_next/static/chunks/app/tournaments/[slug]/page-0a584f.js")).toBe(
      "app/tournaments"
    );
    expect(surfaceOf("app/admin/matching/page-fedb32.js")).toBe("app/admin");
    expect(surfaceOf("3657-bef4a5.js")).toBe("shared");
  });

  it("isProse keeps sentences and drops identifiers, classes and enums", () => {
    expect(isProse("No market has put a probability on today's matches.")).toBe(true);
    expect(isProse("we asked Kalshi and Polymarket and neither runs that market.")).toBe(true);
    expect(isProse("data-price-state")).toBe(false);
    expect(isProse("priced_cells")).toBe(false);
    expect(isProse("mt-2 max-w-[62ch] text-[11.5px] leading-snug")).toBe(false);
    expect(isProse("===e.price_state)return null;if(")).toBe(false);
  });

  /**
   * ═══ THE JSON HOLE — UX-P155, 2026-08-28 ═══
   *
   * The scan reported `/about` clean while the page rendered a venue name.
   * Both were true: `lib/data/alcaraz-ao-2026-series.json` reaches the bundle
   * as `JSON.parse('{…}')`, one code-shaped literal that `isProse` rejects on
   * its braces, so every sentence inside it was invisible here.
   *
   * That is the same failure this whole file was built for — a guard reporting
   * green about bytes it never read — so it gets the same treatment: a planted
   * violation in the exact emitted shape, which must be found.
   */
  it("sees copy inside an inlined JSON import, not just bare literals", () => {
    const planted =
      'var n=JSON.parse(\'{"caption":"We asked Kalshi and Polymarket and neither runs that market.","pts":[1,2]}\');';
    const hits = scanBundleSource("chunk.js", planted);
    expect(hits.map((h) => h.ban.id).sort()).toEqual(["venue-kalshi", "venue-polymarket"]);
  });

  it("expandJsonPayload leaves ordinary literals alone", () => {
    // If it treated every string as maybe-JSON the scan would double-report,
    // and a `{` in real copy would start swallowing sentences.
    expect(expandJsonPayload("No probability yet")).toBeNull();
    expect(expandJsonPayload("{not json}")).toBeNull();
    // Keys are identifiers, not copy — only values come back.
    expect(expandJsonPayload('{"headline":"Two words here","n":4}')).toEqual(["Two words here"]);
    expect(expandJsonPayload('["a sentence here","and another"]')).toEqual([
      "a sentence here",
      "and another",
    ]);
  });

  it("finds a planted violation in a bundle-shaped source", () => {
    // The scan must survive minification, not just clean source. If this ever
    // goes green because `scanBundleSource` stopped looking, the two bundle
    // tests below would go green for the same reason and say nothing.
    const planted =
      'function O(e){return e.n?"Live number.":"Once the main draw starts, Kalshi lists more of them."}';
    const hits = scanBundleSource("planted.js", planted);
    expect(hits.map((h) => h.ban.id).sort()).toEqual(["once-the", "venue-kalshi"]);
  });

  /**
   * CERT-537's sentence, in the shape the bundle would actually carry it.
   *
   * The layer-1 pins prove `findBannedCopy` rejects the string. They do NOT
   * prove the SHIPPED-COPY layer would have caught it, and those are different
   * claims — the JSON hole above is this file's own worked example of layer 1
   * passing while layer 2 read nothing. UX-P211's sentence is assembled from a
   * template literal, so it reaches a chunk SPLIT at its interpolation, which
   * is exactly the shape a naive plant would miss.
   *
   * So the plant is the emitted shape, not the source sentence: the ban has to
   * fire on a fragment that no longer contains the subject's name. It does,
   * because "No number ever reached us for " is banned by the quantifier and
   * not by anything after it — which is the property that makes this group
   * work on a minified bundle at all.
   *
   * ⚠️ **WIDENED BY UX-P231, NOT DELETED — AND THE TITLE NOW SAYS THE TRUE
   * THING.** This test asserted that the DEFAULT bundle scan catches a history
   * claim, and Alex's D25-scope ruling condemns exactly that: the group applies
   * only to copy emitted by the no-reading components, and a minified chunk
   * cannot say which component a string came from. What was always real here is
   * the EXTRACTION claim — that a template literal split at its interpolation
   * still reaches the scanner as prose, and that the conditional half stays
   * clean. That half is preserved verbatim by handing the scan the fenced list
   * explicitly. The condemned half is replaced by its opposite, which is the
   * fence proven at the very layer that used to over-enforce it.
   */
  it("extracts UX-P211's history claim from the shape a chunk really carries it", () => {
    const planted =
      'function T(e,t){return t?`No number ever reached us for ${e}, so this comparison was never complete.`:`We have no number for ${e} yet.`}';
    const hits = scanBundleSource(
      "app/tournaments/[slug]/page-0a584f.js",
      planted,
      NO_READING_COPY_BANS,
    );
    expect(hits.length).toBeGreaterThan(0);
    // THREE rules fire on one sentence, and that is the intended shape rather
    // than redundancy: "no number … ever" and "ever reached us" are different
    // readings of the same quantifier, and "was never complete" is a second,
    // independent claim in the trailing clause. A sentence that can only be
    // caught by one pattern is one regex edit away from being served.
    expect(hits.map((h) => h.ban.id).sort()).toEqual([
      "ever-reached-us",
      "no-reading-ever",
      "was-never-complete",
    ]);
    // `app/tournaments` is the one surface with NO entry in OWED, so a hit
    // there fails the gate outright rather than joining a debt list.
    expect(hits.every((h) => h.surface === "app/tournaments")).toBe(true);
    // The replacement half of the same ternary must NOT be a hit, or the guard
    // would be firing on the chunk rather than on the sentence.
    expect(hits.every((h) => !h.literal.includes("We have no number for"))).toBe(true);

    // 🔴 THE FENCE, AT THE LAYER THAT USED TO ENFORCE IT. The identical plant,
    // scanned with the DEFAULT list, is clean — because a minified chunk cannot
    // answer "which component emitted this", and a scanner that guessed is the
    // false-positive engine six certs kept walking into.
    expect(scanBundleSource("app/tournaments/[slug]/page-0a584f.js", planted)).toEqual([]);
  });

  /**
   * ═══ CERT-539 — AN ALTERNATE SHAPE, THROUGH LAYER 2 ═══
   *
   * The cert's finding was not only that five rewordings passed the predicate;
   * it was that `scanBundleSource` reported clean on them too. Pinning the new
   * families at layer 1 alone would answer half the finding and leave the other
   * half exactly as it was — this file's own JSON-hole test is the worked
   * example of layer 1 passing while layer 2 read nothing.
   *
   * So the alternate wording is planted in the emitted shape as well, and a
   * DIFFERENT wording from the one above: no "ever", no "reached us", no
   * "complete". If a future edit narrows the group back to UX-P213's six
   * literals, the layer-1 pins and this one fail together, which is the
   * signal that the claim — not the sentence — is what the rule is holding.
   *
   * ⚠️ **WIDENED BY UX-P231 FOR THE SAME REASON AS ITS SIBLING ABOVE.** The
   * alternate-wording claim and the clean-conditional claim are untouched; the
   * list is now named explicitly, and the fence gets its own assertion.
   */
  it("extracts a REWORDED history claim from the shape a chunk really carries it", () => {
    const planted =
      'function R(e,t){return t?`There has never been a probability for ${e}.`:`We have no probability for ${e} yet.`}';
    const hits = scanBundleSource(
      "app/tournaments/[slug]/page-0a584f.js",
      planted,
      NO_READING_COPY_BANS,
    );
    expect(hits.length).toBeGreaterThan(0);
    expect(hits.map((h) => h.ban.id).sort()).toEqual(["there-was-never-a-reading"]);
    expect(hits.every((h) => h.surface === "app/tournaments")).toBe(true);
    // The conditional half is the sentence the product is allowed to say, and
    // it must stay clean or the plant is proving nothing about the quantifier.
    expect(hits.every((h) => !h.literal.includes("We have no probability for"))).toBe(true);
    // The fence: the same plant is invisible to the default list.
    expect(scanBundleSource("app/tournaments/[slug]/page-0a584f.js", planted)).toEqual([]);
  });

  /**
   * The other side of CERT-539, at the layer that would actually break a build.
   *
   * A false positive here is not a nuisance — `scanBundleSource` feeds the
   * product-wide gate, so an over-broad rule fails a deploy on true copy. The
   * three narrowed patterns are therefore proven clean in the EMITTED shape
   * too, not only against a bare string.
   */
  it("supported sports prose survives the bundle scan", () => {
    const planted =
      'function S(){return["At no point did either player face a break point.","The comeback was never complete.","Nobody ever scored more than 30 points in this game."]}';
    const hits = scanBundleSource("app/tournaments/[slug]/page-0a584f.js", planted);
    expect(hits.map((h) => `${h.ban.id}: ${h.literal}`)).toEqual([]);
  });
});

/* ───────────────── layers 2 and 3: what actually shipped ───────────────── */

function scanDir(dir: string): BundleCopyHit[] {
  const hits: BundleCopyHit[] = [];
  const walk = (d: string) => {
    for (const entry of fs.readdirSync(d, { withFileTypes: true })) {
      const full = path.join(d, entry.name);
      if (entry.isDirectory()) walk(full);
      else if (entry.name.endsWith(".js")) {
        hits.push(...scanBundleSource(path.relative(dir, full), fs.readFileSync(full, "utf8")));
      }
    }
  };
  walk(dir);
  return hits;
}

function countChunks(dir: string): number {
  let n = 0;
  for (const entry of fs.readdirSync(dir, { withFileTypes: true })) {
    if (entry.isDirectory()) n += countChunks(path.join(dir, entry.name));
    else if (entry.name.endsWith(".js")) n += 1;
  }
  return n;
}

function report(hits: BundleCopyHit[]): string {
  return hits
    .map((h) => `  [${h.ban.id}] ${h.surface}  (${h.file})\n    ${h.ban.why}\n    "${h.literal}"`)
    .join("\n");
}

/**
 * Surfaces the rulings do not reach.
 *
 * `app/admin` is staff-only — ruling 138 already recorded that it is
 * "arguably outside user-facing altogether", and its copy exists to name the
 * exact venue and the exact enum that an operator has to go and fix.
 * The rest is third-party code we did not write and cannot reword.
 */
const EXEMPT_SURFACES = new Set(["app/admin"]);

/* ═══ CERT-430, FINDING 4: EXEMPT THE PACKAGE, NOT THE FILENAME ═══
 *
 * THE DEFECT, measured by the cert: this list used to be
 *
 *     [/polyfills-/, /\bframework-/, /\bfd9d1056-/, /\b463d092a-/, /\bb3bee427-/]
 *
 * and the last three are webpack's CONTENT-DERIVED vendor chunk ids. Delete
 * `.next`, rebuild, and Firebase Auth's own sentence — "The mobile app
 * identifier is not registered for the current project." — came back in
 * `568dbb46-…`, which nothing matched, so a clean build failed a copy gate on
 * prose no human here has ever been able to edit. The bundle was fine; the
 * exemption had gone stale by being written in the one identifier a rebuild is
 * allowed to change.
 *
 * That is not a list to extend. Any enumeration of hashes is wrong the moment a
 * dependency is bumped, and the failure it produces — a red gate on somebody
 * else's string — is the kind teams fix by loosening the rules.
 *
 * ═══ WHAT REPLACES IT ═══
 *
 * A string is a dependency's if the dependency SHIPS it and we do not write it.
 * Both halves are checked against the tree, not against a filename:
 *
 *   • `vendorOwner` finds the literal in an installed package's own source and
 *     returns the package it belongs to. Survives every rebuild and every
 *     version bump, because it asks the package.
 *   • `authoredHere` refuses that exemption for anything present in our own
 *     source. A sentence we wrote is ours even if a dependency happens to
 *     contain the same words.
 *
 * The check is LAST in `unowned` and memoised, because it is the only one that
 * reads the disk — on a clean run it never executes at all, and a run with one
 * unlisted hit pays about a second.
 *
 * ⚠️ IT FAILS CLOSED. No `node_modules`, an unreadable tree, or a literal the
 * minifier reshaped all mean "not attributed", and an unattributed hit FAILS.
 * The alternative — excusing a hit we could not explain — is the exact shape of
 * the bug this replaces.
 */

const NODE_MODULES = path.join(__dirname, "..", "..", "node_modules");
const OUR_SOURCE = ["app", "components", "lib", "hooks"].map((d) =>
  path.join(__dirname, "..", "..", d)
);

function fileContains(file: string, literal: string): boolean {
  try {
    return fs.readFileSync(file, "utf8").includes(literal);
  } catch {
    return false;
  }
}

/** Walk `dir` for `exts` files; the first one containing `literal` wins. */
function findInTree(dir: string, literal: string, exts: RegExp): string | null {
  let entries: fs.Dirent[];
  try {
    entries = fs.readdirSync(dir, { withFileTypes: true });
  } catch {
    return null;
  }
  const dirs: string[] = [];
  for (const entry of entries) {
    const full = path.join(dir, entry.name);
    if (entry.isDirectory()) {
      if (entry.name === ".bin" || entry.name === ".cache") continue;
      dirs.push(full);
    } else if (exts.test(entry.name) && fileContains(full, literal)) {
      return full;
    }
  }
  for (const child of dirs) {
    const hit = findInTree(child, literal, exts);
    if (hit !== null) return hit;
  }
  return null;
}

/** The npm package a path under `node_modules` belongs to — scopes included. */
function packageNameOf(file: string): string {
  const parts = path.relative(NODE_MODULES, file).split(path.sep);
  return parts[0].startsWith("@") ? `${parts[0]}/${parts[1]}` : parts[0];
}

const vendorCache = new Map<string, string | null>();

/** The installed package that ships this exact string, or `null`. */
function vendorOwner(literal: string): string | null {
  const cached = vendorCache.get(literal);
  if (cached !== undefined) return cached;
  const inSource = OUR_SOURCE.some(
    (dir) => findInTree(dir, literal, /\.(ts|tsx|js|jsx|json)$/) !== null
  );
  const file = inSource ? null : findInTree(NODE_MODULES, literal, /\.(js|mjs|cjs)$/);
  const owner = file === null ? null : packageNameOf(file);
  vendorCache.set(literal, owner);
  return owner;
}

/**
 * ═══ EXEMPT — the ruling says these are ALLOWED here, so they are not debt ═══
 *
 * Distinct from `OWED` below, and the distinction is the point. OWED means *we
 * owe a fix*; a line in it is a promise. EXEMPT means *the ruling carves this
 * out*, and filing a carve-out as debt is how a debt list stops being read: it
 * grows a permanent floor nobody can pay, and the entries that COULD be paid
 * get lost against it.
 *
 * UX-P150 put both of these in OWED because it was running the unamended
 * ruling, under which every venue name was a violation somewhere on the
 * spectrum. Ruling 141 names them as exempt on its face.
 */
const EXEMPT: Record<string, string[]> = {
  // "Deliberate comparison surfaces only" — the standing carve-out, which
  // ruling 141 restates: `/calibration` exists to publish how well each source
  // predicts, and "a source-accuracy table with the sources anonymised is not
  // a stronger version of itself". The methodology prose is the table's
  // argument, so it names them too. Ruling 138's `price` debt on this surface
  // is NOT exempt and stays in OWED.
  "app/calibration": ["venue-kalshi", "venue-polymarket"],
  // "A legal disclosure of who we read data from has to name who we read data
  // from. `/privacy` is exempt on its face." — ruling 141.
  "app/privacy": ["venue-kalshi", "venue-polymarket"],
};

/**
 * ═══ THE DEBT, ENUMERATED — ruling 138's "owed, not done", made executable ═══
 *
 * Rulings 138, 141 and 142 are product-wide and permanent. This queue swept
 * the TOURNAMENT surfaces, which is what Alex was reading. Every other surface
 * that still violates them is listed here, by surface and by the exact rule it
 * breaks, so that:
 *
 *   • the ship surfaces are gated HARD — `app/tournaments` is not in this map
 *     and any hit on it fails, on the branch and on production alike;
 *   • a NEW surface can never quietly join the debt — an unlisted surface with
 *     any hit fails, which is the only property that makes a debt list worth
 *     writing down;
 *   • a NEW KIND of violation on an already-owed surface still fails — the key
 *     is (surface, rule), not surface;
 *   • the list can only be paid DOWN. Removing an entry is a one-line diff
 *     next to the fix; adding one requires saying so out loud in review.
 *
 * `/calibration` is the heaviest entry and deliberately NOT swept here: ruling
 * 138 flagged that the `price_moved` dimension is a real distinction about
 * TRADING, and "did trading move the number" has to keep meaning what "did
 * trading move the price" meant. That is a rewrite with judgment in it, not a
 * find-and-replace, and doing it badly would cost the page its meaning.
 *
 * ═══ THE VENUE ENTRIES, RE-READ AGAINST THE AMENDMENT (UX-P152) ═══
 *
 * Ruling 141 as amended requires each venue line here to be classified rather
 * than paid down as written, because several were never debt. Measured against
 * this build, with the attribution/narrative test applied:
 *
 *   • `app/politics` — the only venue prose was `title="Both Kalshi and
 *     Polymarket"` on a source chip. Attribution. Entries REMOVED, not fixed.
 *   • `app/weather` — the chips ("Polymarket & Kalshi ·", "Kalshi · 10
 *     cities") are attribution; the sub-theme subtitle "Daily 'Will it rain?'
 *     markets from Kalshi" is a coverage claim. `venue-polymarket` removed,
 *     `venue-kalshi` still owed for that one sentence.
 *   • `app/calibration`, `app/privacy` — moved to EXEMPT above.
 *   • `app/about`, `app/categories`, `shared` — still narrative, still owed.
 *
 * The chart series names ("Kalshi Implied"), the case-study provenance
 * captions and the cross-source legends on Discover cards never appear below
 * because the rule no longer fires on them. That is the amendment working:
 * they were listed as the next thing to sweep and the call reversed.
 *
 * ═══ THE VENUE DEBT IS PAID — UX-P155, 2026-08-28 ═══
 *
 * The re-read above left exactly four narrative sentences standing, and this
 * queue rewrote all four. Measured against this build, every `venue-*` entry
 * in the map below went dead at once, so there are now NO venue entries in
 * OWED — not fewer, none:
 *
 *   • `app/about` — "Kalshi + Polymarket, unified" → "Open questions, merged
 *     into one number". The key is gone from the map entirely; it held nothing
 *     else. The reader who wants the names still gets them fifty lines down
 *     the same page, in the source table that attributes 63% and 59% to them —
 *     which is the amendment's allowed class, and is why removing the blurb
 *     costs the page nothing.
 *   • `app/categories` — "Tournament odds from Polymarket, Kalshi, sportsbooks
 *     & DataGolf" → "Who wins each tournament, one number per golfer". The
 *     `SourceLegend` further down the page carries the attribution.
 *   • `app/weather` — "Daily 'Will it rain?' markets from Kalshi" → "…
 *     questions, one per day". The `<SourceBadge src="kalshi" />` sits on the
 *     same row and renders the name; the sentence was saying it twice.
 *   • `shared` — the landing blurb's "Sportsbooks, ESPN, Kalshi, Polymarket,
 *     and live stat models" → "Sportsbooks, ESPN, prediction markets, and live
 *     stat models". The KINDS survive, which is the fact the sentence carried:
 *     four different ways of guessing, weighted by track record.
 *
 * What remains in the map is rulings 138 and 142 only. Ruling 141 is closed on
 * the branch — and, per ruling 142, not closed at all until the production
 * layer below has been run against a post-deploy fetch.
 *
 * ═══ `app/weather`'s RULING-142 DEBT IS PAID — UX-P219, 2026-08-31 ═══
 *
 * The surface owed exactly one rule, `appear-here`, and it was owed by four
 * empty states saying the same thing in four voices: "… appear here when they
 * reopen" on the daily rain card, the monthly rainfall card, the climate
 * dashboard and the temperature map. Each now says what the card is FOR —
 * "This card tracks daily city temperature markets." — which is true whether
 * or not anything ever reopens, and was the whole of ruling 142's point.
 *
 * The key is DELETED rather than emptied, the same as `app/about` above, so the
 * surface is gated hard from here: any future `appear-here` on `/weather` is an
 * unlisted (surface, rule) pair and fails. The four sites also carry a per-card
 * render guard, because this map's absence assertion cannot see a sub-line that
 * is deleted instead of rewritten —
 * `__tests__/capture/weatherEmptyStatesStateWhatTheyAre.test.tsx`.
 *
 * ═══ RULING 142 IS PAID IN FULL — UX-P220, 2026-08-31 ═══
 *
 * UX-P219 paid `app/weather` and, in doing so, found why the debt had survived
 * two sweeps: a green capture was asserting the banned sentence VERBATIM, so
 * the debt list said "we owe a fix" while a test said "keep it exactly as it
 * is". A census of this build found the remaining debt was not six surfaces
 * but SEVEN SENTENCES, several of them shared:
 *
 *   • `components/discover/EndOfFeedCard.tsx` — "new markets open throughout
 *     the day, so check back soon" → "…that is every market in your feed right
 *     now." One sentence; it was the whole of `app/search`'s debt and half of
 *     `shared`'s, because the card bundles into both. The Refresh button and
 *     the category links under it are the affordance the promise was standing
 *     in for, and they were already there.
 *   • `app/discover/page.tsx` — the daily challenge's "Check back after the
 *     feed refreshes." → where the challenge draws its questions FROM.
 *   • `components/OddsChart.tsx` — "Win probability will update live once the
 *     game starts" → "This chart plots win probability minute by minute." One
 *     sentence carrying TWO of `shared`'s three promise ids (`once-the` and
 *     `will-populate`), which is why the map made the debt look wider than it
 *     was.
 *   • `app/categories`, `app/my-stuff`, `app/sports`, `app/hub` — four empty
 *     states saying "Check back…" in four voices; each now says what its page
 *     lists or follows.
 *   • `app/playoffs` — "No championship odds available yet / Odds will appear
 *     when sportsbooks and prediction markets publish…". Both lines went: the
 *     headline's "yet" was a promise the rules do not catch, and shipping it
 *     next to a rewritten sub-line would have been half a fix.
 *
 * Six keys are DELETED and `shared` keeps only its ruling-138 ids, so OWED now
 * holds nothing but ruling 138. The `ruling 142 is closed` test below makes
 * that structural, and the per-site render guard —
 * `__tests__/capture/emptyStatesStateWhatTheyAre.test.tsx` — pins each site,
 * because this map's absence assertion cannot see a sentence that is rewritten
 * on one surface and still shipping on another.
 */
const OWED: Record<string, string[]> = {
  // The methodology page still says "price" throughout, for the reason in
  // ruling 138. Its venue names are EXEMPT, not owed.
  "app/calibration": ["price-family", "blend"],
  "app/privacy": ["price-family"],
  "app/politics": ["price-family"],
  // "the price at the pump", "Gas price", "Inflation & Consumer Prices" —
  // ruling 138 explicitly SPARES these: they are prices of goods in the world,
  // which is what those markets are about. Listed so the exemption is visible.
  "app/economics": ["price-family"],
  // `app/about` sat here until UX-P155. It held only the two venue names in
  // "Kalshi + Polymarket, unified"; with that line rewritten the surface ships
  // clean, so the key is deleted rather than left as an empty array.
  "app/futures": ["price-family"],
  // #2442's `moneyline` rule is OWED here, and the reason is the ruling's own
  // distinction rather than a shortage of time. The two hits are the
  // methodology copy on `/events/{id}/models` — "Moneyline odds from each
  // bookmaker are converted to implied probabilities, then the vig is
  // removed". That names the format we convert AWAY from, in a paragraph whose
  // whole subject is that we do not show it. Alex's 2026-07-31 ruling draws
  // exactly this line: the rule bans a betting format used as a SELLING POINT,
  // never naming the thing Bain Luck refuses to show, and `/about`'s
  // `Not "-150 / +130"` is the pinned counter-example. Deleting this sentence
  // would make the methodology page less honest, not more compliant.
  "app/events": ["price-family", "blend", "moneyline"],
  // `app/categories`, `app/search`, `app/hub`, `app/my-stuff`, `app/sports` and
  // `app/playoffs` sat here until UX-P220. Each held ruling-142 entries only, so
  // with the last promise rewritten the keys are deleted rather than emptied —
  // the same treatment `app/about` got in UX-P155, and what makes any future
  // promise on those surfaces an UNLISTED pair rather than a forgiven one.
  //
  // Components shared across routes: the marketing blurbs on the landing shell
  // and `lib/priceCadenceCopy.ts`. The live-game chart caption was the third
  // and is gone; `check-back`, `once-the` and `will-populate` went with it.
  // `app/admin` is NOT listed for #2442's `moneyline` rule even though the
  // console describes what it ingests as "Moneyline, spreads, totals from 10+
  // sportsbooks". It is already in `EXEMPT_SURFACES` above — an operator
  // surface behind the admin secret, where the supplier's vocabulary is the
  // correct vocabulary — and an OWED entry that `unowned()` can never reach is
  // exactly the dead debt this map's own discipline forbids.
  shared: ["blend", "price-family"],
};

/**
 * The venue rule ids, read off `VENUE_BANS` rather than spelled out — a third
 * venue added to the ruling is covered without touching this file.
 */
const ATTRIBUTION_AWARE_IDS = new Set(VENUE_BANS.map((b) => b.id));

/** Hits that neither the ruling's carve-outs nor the debt list account for. */
function unowned(hits: BundleCopyHit[]): BundleCopyHit[] {
  return hits.filter((h) => {
    if (EXEMPT_SURFACES.has(h.surface)) return false;
    if ((EXEMPT[h.surface] ?? []).includes(h.ban.id)) return false;
    if ((OWED[h.surface] ?? []).includes(h.ban.id)) return false;
    // LAST, and the only check that touches the disk — see `vendorOwner`.
    return vendorOwner(h.literal) === null;
  });
}

describe("third-party prose is attributed to its package, not to a chunk name", () => {
  // CERT-430, finding 4. Each of these is the mechanism doing the thing the
  // hash list could not: answering the question from the tree, so that a
  // dependency bump — which renames every vendor chunk — changes nothing here.

  it("SPECIMEN: the Firebase sentence that reddened a clean build is attributed", () => {
    // The exact string, from the cert's clean rebuild. It moved from chunk
    // `463d092a-…` to `568dbb46-…` and the gate went red on prose nobody here
    // can edit. Attributed by package, the chunk's name is irrelevant.
    // The owner is named, not merely "not ours" — `@firebase/auth-compat` is
    // the package that ships the sentence, and `firebase` re-exports it. Either
    // is a true answer to "whose string is this", which is why the assertion is
    // on the family rather than on whichever copy the walk reaches first.
    expect(
      vendorOwner("The mobile app identifier is not registered for the current project.")
    ).toMatch(/firebase/);
  });

  it("our own copy is never excused, even where a dependency echoes it", () => {
    // The half that keeps this from becoming a blanket amnesty. `authoredHere`
    // wins: a sentence in `app/`, `components/` or `lib/` is ours, and the only
    // way to clear it is to change it.
    expect(vendorOwner(FRESHNESS_DEFINITION)).toBeNull();
    expect(vendorOwner("Nothing to ask yet")).toBeNull();
  });

  it("a string no package ships is not attributed — the check can fail", () => {
    expect(vendorOwner("Kalshi and Polymarket both quote this fake sentence.")).toBeNull();
  });
});

describe("the built bundle — the bytes Vercel uploads", () => {
  const dir = path.join(__dirname, "..", "..", ".next", "static", "chunks");
  const present = fs.existsSync(dir);

  it("the build output exists, or CI has skipped its own gate", () => {
    if (present) {
      expect(present).toBe(true);
      return;
    }
    const message =
      "No .next/static/chunks — the shipped-copy scan did NOT run.\n" +
      "  Run `npm run build` first. This is the layer that catches copy no fixture renders.";
    if (process.env.CI) throw new Error(message);
    console.warn(`\n⚠️  ${message}\n`);
  });

  (present ? it : it.skip)("the tournament surfaces ship no banned language at all", () => {
    // The ship. Not "fewer than before" and not "none that we know about":
    // zero, on the surface Alex read, in the artifact that gets uploaded.
    const hits = scanDir(dir).filter((h) => h.surface === "app/tournaments");
    if (hits.length > 0) {
      throw new Error(`banned language on the tournament surfaces:\n${report(hits)}`);
    }
  });

  (present ? it : it.skip)("no surface violates a rule that is not already written down", () => {
    const hits = unowned(scanDir(dir));
    if (hits.length > 0) {
      throw new Error(
        "banned language on a surface/rule pair that is NOT in OWED.\n" +
          "Either fix it, or add the (surface, rule) to OWED with a reason — silently is not one of the options.\n" +
          report(hits)
      );
    }
  });

  (present ? it : it.skip)("the vendor exemption is EXERCISED by this build, not just available", () => {
    // Non-vacuity for the mechanism that replaced the hash list. The specimen
    // above proves `vendorOwner` can resolve a package; this proves the bundle
    // path actually goes through it, on the bytes this build produced.
    //
    // The hits below are the ones EXEMPT and OWED do not account for, so each
    // one either names a package or fails the gate three tests up. If a build
    // ever legitimately ships no third-party prose at all, this is the line to
    // relax — deliberately, with a note, not by deleting the mechanism.
    const candidates = scanDir(dir).filter(
      (h) =>
        !EXEMPT_SURFACES.has(h.surface) &&
        !(EXEMPT[h.surface] ?? []).includes(h.ban.id) &&
        !(OWED[h.surface] ?? []).includes(h.ban.id)
    );
    const owners = candidates
      .map((h) => vendorOwner(h.literal))
      .filter((owner): owner is string => owner !== null);
    expect(owners.length).toBeGreaterThan(0);
  });

  it("ruling 141 is closed: no venue rule may be carried as debt again", () => {
    // The other rulings' entries are debt — a promise to pay. This one has
    // been paid in full, and the difference should be structural rather than
    // an empty space in a list. Re-listing a venue name as OWED would be a
    // one-line diff that reads like housekeeping; this makes it a diff that
    // has to delete a test with a ruling number on it.
    //
    // Not "there are no venue hits" — the bundle scan above already says that,
    // and only for the surfaces it can see. This says the DEBT LIST may never
    // absorb one, which is the failure the OWED map exists to prevent.
    const venueDebt = Object.entries(OWED).flatMap(([surface, ids]) =>
      ids.filter((id) => ATTRIBUTION_AWARE_IDS.has(id)).map((id) => `${surface} → ${id}`)
    );
    expect(venueDebt).toEqual([]);
  });

  it("ruling 142 is closed: no future-promise rule may be carried as debt again", () => {
    // UX-P220. Same shape as ruling 141 above, and for the same reason: the
    // difference between "paid" and "small" should be structural, not an empty
    // space in a list that the next queue can quietly refill.
    //
    // Ruling 142's debt outlived two sweeps because nothing stopped a surface
    // being ADDED back. `app/weather` was paid by UX-P219; the last six —
    // categories, search, hub, my-stuff, sports, playoffs — plus all three of
    // `shared`'s promise ids were paid here. Re-listing any of them would be a
    // one-line diff that reads like housekeeping; this makes it delete a test
    // with a ruling number on it.
    //
    // Read off `FUTURE_PROMISE_BANS` rather than spelled out, so a fourth
    // promise rule added to the ruling is covered without touching this file.
    const promiseIds = new Set(FUTURE_PROMISE_BANS.map((b) => b.id));
    const promiseDebt = Object.entries(OWED).flatMap(([surface, ids]) =>
      ids.filter((id) => promiseIds.has(id)).map((id) => `${surface} → ${id}`)
    );
    expect(promiseDebt).toEqual([]);
  });

  (present ? it : it.skip)("the debt list has no dead entries — it can only be paid down", () => {
    // A surface that was fixed but left on the list makes the debt look bigger
    // than it is, and makes the next reader distrust the whole map.
    //
    // OWED only. `EXEMPT` is a statement about what the ruling ALLOWS on a
    // surface, not a measurement of what it currently says, so an exemption
    // that stops firing is not stale — it is a page that happened to reword.
    //
    // ⚠️ THE SEPARATOR IS WRITTEN AS AN ESCAPE, NOT TYPED (UX-P210-3, UX-P213).
    // It was two RAW NUL bytes until 2026-08-31, and a raw NUL makes the whole
    // file binary to the tools that read this repo: `grep -c 'ban'` on it
    // exited 1 — "no match" — against 27 real matches, and `git grep` returned
    // nothing at all. That is worse than a wrong answer, because a grep that
    // finds nothing reads exactly like a grep that ran. CERT-507 blocked
    // `ux-150` partly on a reproduction that came back false HERE for this
    // reason. NUL is still the right joiner — no surface or rule id can
    // contain it — so only its spelling changed, and `nulByteFreeSource`
    // keeps the next one out of the tree.
    const live = new Set(scanDir(dir).map((h) => `${h.surface}\u0000${h.ban.id}`));
    const dead: string[] = [];
    for (const [surface, ids] of Object.entries(OWED)) {
      for (const id of ids) {
        if (!live.has(`${surface}\u0000${id}`)) dead.push(`${surface} → ${id}`);
      }
    }
    if (dead.length > 0) {
      throw new Error(
        `OWED entries that no longer fire — delete them:\n  ${dead.join("\n  ")}`
      );
    }
  });
});

describe("production — the chunks a browser downloaded from bainluck.com", () => {
  const dir = process.env.SHIPPED_BUNDLE_DIR;
  const present = Boolean(dir) && fs.existsSync(dir as string);

  it("says plainly when it did not run, instead of passing", () => {
    if (present) {
      // The empty-directory case is the one that matters: a scan of nothing
      // returns nothing, and "no hits" would read as "production is clean".
      // Recursive: `fetch-shipped-copy.mjs` preserves `app/<route>/…` nesting
      // because `surfaceOf` needs it, so a top-level readdir counts zero and
      // this test would report "did not run" over a perfectly good download.
      expect(countChunks(dir as string)).toBeGreaterThan(0);
      return;
    }
    console.warn(
      "\n⚠️  SHIPPED_BUNDLE_DIR unset — production was NOT scanned. This run proves\n" +
        "    nothing about bainluck.com. To prove it:\n" +
        "      node scripts/fetch-shipped-copy.mjs --url https://www.bainluck.com/tournaments/us-open-2026\n" +
        "      SHIPPED_BUNDLE_DIR=$TMPDIR/bainluck-shipped npx jest shippedCopyBans\n"
    );
  });

  (present ? it : it.skip)("serves no banned language on the tournament surfaces", () => {
    const hits = scanDir(dir as string).filter((h) => h.surface === "app/tournaments");
    if (hits.length > 0) {
      throw new Error(
        `banned language LIVE on production (${dir}):\n${report(hits)}\n\n` +
          "This is the ship. A green branch does not close it."
      );
    }
  });

  (present ? it : it.skip)("serves nothing that is not already written down", () => {
    // The prod fetch only pulls ONE page's chunks, so the dead-entry check
    // above deliberately does not run here: most of OWED is simply not in the
    // download, and "absent" would be indistinguishable from "fixed".
    const hits = unowned(scanDir(dir as string));
    if (hits.length > 0) {
      throw new Error(`unlisted banned language LIVE on production:\n${report(hits)}`);
    }
  });
});
