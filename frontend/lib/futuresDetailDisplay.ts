import { formatShareProbability } from "./share";

// #883 futures-detail blend-only redesign — pure display helpers.
//
// The detail page shows ONE blended number and a plain-language clarification of
// WHY the blend line moved (#871-style). This logic is extracted here so it can
// be unit-tested without rendering the heavy page (SWR/framer/charts), mirroring
// searchFamilyDisplay.ts. D1 binds: probabilities only, no odds, no source names.

export interface MovementLeader {
  name?: string | null;
  probability: number | null;
  opening_probability?: number | null;
  probability_change_24h?: number | null;
}

/**
 * #883 L2-49 (resolved edge state): the outcome the hero features. On a resolved
 * market that's the actual WINNER (is_winner === true), which can differ from the
 * highest-probability outcome — falling back to the leader if none is flagged.
 * On a live market it's just the leader.
 */
export function pickHeroOutcome<T extends { is_winner?: boolean | null }>(
  outcomes: readonly T[],
  leader: T | null,
  resolved: boolean,
): T | null {
  if (!resolved) return leader;
  return outcomes.find((o) => o.is_winner === true) ?? leader;
}

/* ───────────────────────────────────────────────────────────────────────────
 * #6079 — THE WORD "won" HAS ONE SOURCE, AND IT IS THE GRADE.
 *
 * `pickHeroOutcome` answers "which row does this surface feature", and on a
 * resolved market with nothing graded it answers with the PRICE LEADER. That is
 * the right answer to its question — a settled page still has to show something
 * — and it is the wrong thing to put the word "won" in front of.
 *
 * Three surfaces describe that state and two of them already knew: `FuturesHero`
 * gates its chip on `resolvedWon={resolvedWinner?.is_winner === true}` and prints
 * grey "Resolved", and `futuresUnfurlCopy` gates `settledWon` the same way (#6032).
 * The unfurl TITLE and DESCRIPTION took the bare fallback, so one preview made two
 * claims at once. Measured on production 2026-09-14 05:36Z, `/futures/61000391`:
 *
 *   og:title    "No won - Overwatch: Sweden vs France - Game 4 Winner"   ❌
 *   og:image    64px "No" beside a grey RESOLVED pill                    ✅
 *
 * 🔴 "No won" IS THE READING, and the generic-binary substitution is what makes
 * it that: `leaderLabel` turns an ungraded `No` row into a sentence subject. The
 * frozen price is 0.91, so the fallback crowns a row for being expensive at the
 * moment trading stopped — UX-P232 measured that settlement freezes prices
 * "routinely NOT the highest on the board", which is why #6032 refused to read a
 * winner out of one.
 *
 * So the grade is asked for by name, in one place, and every surface that wants
 * to print "won" calls it. `pickHeroOutcome` is untouched: the subject and the
 * verdict are two different questions and collapsing them is the bug.
 * ─────────────────────────────────────────────────────────────────────────── */
export function gradedWinner<T extends { is_winner?: boolean | null }>(
  outcomes: readonly T[],
  leader: T | null,
  status: string | null | undefined,
): T | null {
  if (status !== "resolved") return null;
  const featured = pickHeroOutcome(outcomes, leader, true);
  return featured?.is_winner === true ? featured : null;
}

/** Generic binary-style outcome names that read better as "Yes" in a headline. */
export function isGenericOutcomeLabel(name: string | null | undefined): boolean {
  const n = (name || "").trim().toLowerCase();
  return n === "yes" || n === "no" || n === "" || n === "over" || n === "under";
}

/**
 * #5997 — A NAME THAT STATES A SIDE IS NEVER SUBSTITUTABLE BY "Yes".
 *
 * The "Yes" substitution exists so a hero has something to say when the outcome
 * it features is named with a bare identifier — "May 18", "2026", "Option A" —
 * which means nothing above a percentage. That is a readability fix and it is
 * fine. It becomes a lie the moment the featured outcome's own name states which
 * SIDE of the question it is: "Yes" is not a neutral placeholder, it is an
 * answer, and printing it over the `No` row's number answers the question
 * backwards.
 *
 * Measured on production 2026-09-13 by lane1b/224: `/futures/20571021` serves
 * `Yes: null, No: 0.39` and the hero read **"39% / Yes"**; `/futures/16634786`
 * serves `Yes: null, No: 0.664` and read **"66% / Yes"**. The caption went with
 * them, because it comes through `leaderLabel` below. **3,768 unresolved binary
 * markets have a leading (or sole-priced) `No` row** — every one of those pages
 * was crowning the wrong side.
 *
 * Over/Under and the comparative forms are here for the same reason and not as
 * a widening: "Yes" over an `Under 100` row asserts the opposite threshold, and
 * a name like `Under 100` is perfectly readable in a hero as itself. What is NOT
 * here is the bare-identifier family (dates, numbers, `Option A`) — those carry
 * no answer at all, so the substitution stays theirs.
 */
export function statesItsOwnSide(name: string | null | undefined): boolean {
  const n = (name || "").trim();
  if (!n) return false;
  return (
    /^(yes|no)(\s|$)/i.test(n) ||
    /^(over|under|above|below|at least|at most|more than|less than|fewer than)(\s|$)/i.test(n) ||
    /^[<>=]+\s*\d/.test(n)
  );
}

/**
 * Display label for the leader outcome — generic binaries become "Yes", EXCEPT
 * where the name states its own side (#5997), which is returned as served.
 */
export function leaderLabel(leader: MovementLeader | null): string | null {
  if (!leader) return null;
  const served = (leader.name || "").trim();
  if (statesItsOwnSide(served)) return served;
  return isGenericOutcomeLabel(leader.name) ? "Yes" : (leader.name as string);
}

/**
 * The name to print beside the hero's number, and in the settled sentence: the
 * outcome's OWN name, as served.
 *
 * ═══ #7256 — "Yes" IS AN ANSWER, AND THE HERO MAY ONLY PRINT ANSWERS THE BOARD
 * ACTUALLY CARRIES ═══
 *
 * #5997 narrowed the "Yes" substitution so it could not crown the opposite side
 * of a binary. It left the wide fallback standing — dates, bare numbers,
 * `Option A`, tokens of three characters or fewer — on the reasoning that such a
 * name "means nothing above a percentage". Two production specimens, one of them
 * Alex's, say the fallback is the larger defect:
 *
 *   /futures/55674185  2027 CONCACAF Gold Cup Champion, 23-way field
 *                      leader `USA` 0.41        hero read "41% / Yes"
 *   /futures/58776433  When will the Danube return to normal levels?, 3 rungs
 *                      leader `October 1 - 31, 2026` 0.55
 *                                               hero read "55% / Yes"
 *
 * Neither board has a row called "Yes". The page named the right answer twice —
 * in All Outcomes and in the chart legend — and mislabelled it in the one place
 * a reader looks first. Alex, filing the second: *"`Yes` is not an answer to a
 * 'when' question, and no row on the page carries it … the predicate is not
 * 'large field' but 'the market is not binary'."*
 *
 * ═══ THE MEASUREMENT IS WHAT RETIRES IT RATHER THAN NARROWS IT ═══
 *
 * Counted on production 2026-09-19 over all 43,510 open futures markets with a
 * priced board, applying this function's own predicates to each market's leading
 * outcome:
 *
 *   heroes printing "Yes"                          984
 *     …whose board carries no Yes/No row at all    933
 *     …on a non-binary market (Alex's predicate)   715
 *
 *   by arm:  <=3 chars 409 · date 560 · bare number 113 · `Option A` ___0___
 *
 * 🔴 THE ARM THE FALLBACK WAS WRITTEN FOR HAS NO MEMBERS. `Option|Choice|Bucket`
 * matched zero markets, while the three arms that do fire are answering real
 * questions: the short-token arm is `TCU`, `BYU`, `LSU`, `SMU`, `PSG`, `BTS`,
 * `SEC`, `USA`, `AfD`, `Tie`, `Odd` — teams, parties, a band and a conference,
 * every one of them the row a reader wants named. `PSG` is the sharpest case:
 * #4627 added a HAND_PICKED_LABELS entry so a hero would say "PSG" instead of
 * the fragment "Germain", and this function then replaced "PSG" with "Yes".
 *
 * So there is no narrowing left to do — a predicate whose justifying population
 * is empty is not a readability fix, and #6301's rule on this page already says
 * which way to resolve it: **no verdict beats a wrong one.** The rows that were
 * "unreadable" print a date, a price or a ticker, which is honest and is what
 * the reader's own board says three inches lower.
 *
 * ═══ WHAT THIS DOES NOT WEAKEN ═══
 *
 * #5997's ship is preserved a fortiori: it stopped "Yes" landing on a name that
 * states its own side, and nothing is substituted now, so every one of its arms
 * still holds. `statesItsOwnSide` stays exported and load-bearing for
 * `leaderLabel`, which is on the movement caption — and that caption is the
 * standing proof this change is right, because it uses the NARROW predicate and
 * has been printing "USA" correctly all along, beside a hero saying "Yes".
 *
 * The empty name is not a new hole: measured 0 leading outcomes with a blank name
 * across the same 43,510 markets, and `FuturesHero` gates every draw of this
 * value on `{outcomeName && …}`, so a blank one leaves the space empty rather
 * than explaining it (notice 34 / D102).
 */
export function heroOutcomeLabel(name: string): string {
  return name.trim();
}

/*
 * `isGenericOutcomeName` was DELETED by #7256, not narrowed.
 *
 * It existed for one caller — `heroOutcomeLabel` above — and answered one
 * question: "is this name too bare to print, so that 'Yes' reads better?" The
 * production count of the family it was written to rescue (`Option A`,
 * `Choice 1`, `Bucket 3`) is zero, and every other arm it fired on was a real
 * answer being overwritten. With the substitution retired there is no caller
 * left, and an exported predicate that nothing calls is worse than no predicate:
 * the next reader would take its existence as evidence that the hero still
 * substitutes. The arms it recognised are recorded in `heroOutcomeLabel`'s
 * measurement table rather than kept as code.
 *
 * `statesItsOwnSide` (#5997) is the predicate that survives, and it is still
 * load-bearing for `leaderLabel`.
 */

/**
 * #883 L2-55: the <title>/SEO text for a futures-detail page. On a SETTLED market
 * the title is "<winner> won - <market>" — NO percentage (the last-traded % read
 * as a bug in the hero, and it was still leaking via metadata). Live markets keep
 * "<leader> <prob>% - <market>". Pure so it's unit-tested.
 */
export function futuresTitleText(opts: {
  marketName: string;
  isResolved: boolean;
  winnerName?: string | null;
  leaderName?: string | null;
  probabilityLabel?: string | null;
}): string {
  // #6079 — RESOLVED IS A TERMINAL BRANCH, not a preference for the winner form.
  // It used to fall through when nothing was graded, so narrowing the "won" test
  // alone would have moved this title from "No won - …" to "No 91% - …" — a LIVE
  // shape on a closed market, which is the percentage L2-55 exists to keep out of
  // settled titles and the same claim the card refuses to draw (no 96px numeral,
  // no bar, once `isResolved`). With no grade there is nothing to crown, so the
  // name stands alone; the RESOLVED pill in the picture carries the state.
  if (opts.isResolved) {
    return opts.winnerName ? `${opts.winnerName} won - ${opts.marketName}` : opts.marketName;
  }
  if (opts.leaderName && opts.probabilityLabel) {
    return `${opts.leaderName} ${opts.probabilityLabel} - ${opts.marketName}`;
  }
  return opts.marketName;
}

/**
 * #6127 — THE ONE PLACE THAT ANSWERS "IS THERE A PRICE ON THIS BOARD AT ALL?"
 *
 * The leader's label, or `null` — never a dash, and never a name without a
 * number behind it. Named and shared for the same reason `shareForecastPercents`
 * is: `layout.tsx` and `opengraph-image.tsx` describe the same market from the
 * same payload, and until this function existed they asked the question in two
 * places and answered it two different ways.
 *
 * The WORDS already had the rule three lines up — `leaderName &&
 * probabilityLabel`, else the market name alone — and they have had it since
 * L2-55. The PICTURE wrote `formatShareProbability(...) || "--"`, so on a market
 * nobody has quoted it drew a dash in 96px type, crowned a name beside it and
 * laid a bar stub under it. This returns the label or nothing, so the slot is
 * dropped rather than filled (notice 34 / D102: leave the space empty, do not
 * explain the emptiness).
 *
 * THE LEADER ALONE DECIDES, and that is a property of `topOutcome`, not an
 * assumption: it sorts on `probability ?? -1`, so an unpriced row can never
 * outrank a priced one. A `null` at the top means the whole board is `null`.
 *
 * ═══ THE EXACT ZERO IS NOT THE OPEN QUESTION IT IS ON THE GAME CARD ═══
 *
 * `formatShareProbability` counts an exact 0 as "no number", and on `/events/[id]`
 * that clause collides with #4963 — *"a finished game's loser is 0%, and 0% is a
 * fact"* — which is why #6119 had to keep its picture-side predicate narrower
 * than its words. There is no such collision here. A settled futures market takes
 * the `isResolved` branch on BOTH surfaces, which draws the winner and prints no
 * percentage at all (L2-53/L2-55), so a graded 0% never reaches this rule. The
 * only rows it can see are unresolved boards, where the words have always been
 * quiet about a zero too — so this predicate is the words' rule whole, with no
 * gap to assert. `futuresNoPriceUnfurl6127.test.tsx` pins the equivalence in both
 * directions so a later edit to either surface cannot open one.
 *
 * WITHHOLDS ONLY. A price can arrive on the next poll, so a quiet card is all
 * this licenses: it crowns nobody, it does not touch the status word or the
 * settled branch, and no cache window reads it.
 */
export function futuresBoardPrice(leader: MovementLeader | null | undefined): string | null {
  if (!leader) return null;
  return formatShareProbability(leader.probability);
}

/* ───────────────────────────────────────────────────────────────────────────
 * #6032 — THE UNFURL CARD SAYS WHAT THE UNFURL TITLE SAYS.
 *
 * `futuresTitleText` above (L2-55) and `FuturesHero` (L2-53, Alex ruling) both
 * know the settled rule: the winner name is the story, and a settled market
 * carries NO percentage, because "the last-traded price read as a bug". The
 * third surface describing that same state — the OG image a pasted link draws —
 * never got it, so one preview carried both claims at once.
 *
 * Measured on production 2026-09-13 23:59Z, `/futures/60544511` (the market link
 * YOUR-TURN asks Alex to paste into a phone preview):
 *
 *   og:description  "77° or above won (Temperature in New York City ...)"  ✅
 *   og:image        96px "100%" over "77° or above leads at 100%
 *                    — 10 outcomes tracked."                                ❌
 *
 * 🔴 THE WORDING IS THE SMALLER HALF. The card featured the PRICE leader while
 * the title features the GRADED winner. UX-P232 measured why those differ:
 * settlement freezes every outcome at its last traded price, "routinely NOT the
 * highest on the board" — its case is "Arsenal vs Coventry: First Goalscorer",
 * grading Kai Havertz at 21% while two players who did not score sit frozen at
 * 99%. On that market the card drew a man who did not score, at 99%, over the
 * word "leads". A picture is the artifact a chat client caches and re-serves.
 *
 * So the SUBJECT and the COPY are decided together, here, by the same
 * `pickHeroOutcome` the title calls — the two cannot name different outcomes.
 * This is pure so the settled branch is unit-testable: the route it serves is an
 * edge-runtime `ImageResponse`, which is why the rule went missing there in the
 * first place.
 * ─────────────────────────────────────────────────────────────────────────── */

/* ───────────────────────────────────────────────────────────────────────────
 * #6061 — THE CAPTION CARRIES THE HOOK, OR IT CARRIES NOTHING.
 *
 * Filed paying #6049's after-check and fixed here: the card printed "N outcomes
 * tracked" twice, in this caption and again in the footer 116px below it. The
 * count was only the half that was literally doubled. Read the two production
 * cards whole and EVERY token of the fallback captions is already drawn, larger,
 * on the same 1200×630 canvas:
 *
 *   live    `/futures/60276241`  "Above 1 inch leads at 19% — 7 outcomes tracked."
 *                                 ^^^^^^^^^^^^ 40px   ^^^ 96px   ^^^^^^^^^^^^^^^^ footer
 *   settled `/futures/60544511`  "77° or above won — 10 outcomes tracked."
 *                                 ^^^^^^^^^^^^ 64px  ^^^ WON pill  ^^^^^^^^^^^^^^ footer
 *
 * So the answer is not "move the count" — it is that these captions were never
 * sentences. The hook branch already shows the intended division of labour: the
 * caption is the editorial line about the market, the footer is where a count
 * belongs as small grey type beside the wordmark (D102). Where there is no hook
 * there is no sentence, and restating the numerals in grey is the diagnostic
 * register notice 34 keeps off a reader's screen. Leave the space empty rather
 * than explain it.
 *
 * Retired with them: the count never pluralised here while the footer did, so a
 * one-outcome market read "1 outcomes tracked" in the caption and "1 outcome
 * tracked" underneath — two spellings of one fact, in one picture.
 *
 * `outcomeCount`/`probabilityLabel` leave this signature for the same reason: the
 * numbers are the route's to draw, and a parameter kept "just in case" is how the
 * caption started restating them.
 * ─────────────────────────────────────────────────────────────────────────── */

export interface FuturesUnfurlCopy {
  /** The outcome the card features — the graded winner once settled. */
  featuredName: string | null;
  isResolved: boolean;
  /** True only when the featured outcome is GRADED a winner. */
  settledWon: boolean;
  /**
   * The grey supporting line under the headline, or `null` when the card already
   * draws every fact this line would carry (#6061). Never a restatement.
   */
  subtitle: string | null;
}

export function futuresUnfurlCopy<
  T extends MovementLeader & { is_winner?: boolean | null },
>(opts: {
  outcomes: readonly T[];
  leader: T | null;
  status?: string | null;
  hookDescription?: string | null;
}): FuturesUnfurlCopy {
  const isResolved = opts.status === "resolved";
  // `is_winner === true` is required before the word "won" is printed, mirroring
  // `FuturesHero`'s `resolvedWon` chip. `pickHeroOutcome` falls back to the price
  // leader when nothing is graded, and a fallback must not crown an ungraded row
  // — those say only what `status` proves.
  // #6079 — asked through `gradedWinner` rather than re-derived here, because the
  // unfurl TITLE needs the identical answer and the copy of this test that lived
  // in `layout.tsx` is exactly the one that went missing.
  const graded = gradedWinner(opts.outcomes, opts.leader, opts.status);
  const settledWon = graded !== null;
  // #6301 — THE NAME GOES WITH THE VERDICT, and until now it did not.
  //
  // `settledWon` was gated on the grade (#6079) and `featuredName` was not: it took
  // `pickHeroOutcome`'s price-leader fallback, so a settled field with nothing graded
  // put a LOSER's name at 64px on the share card and hung a grey RESOLVED pill beside
  // it. Production `/futures/58675941` (Vuelta a Espana 2026: Winner) serves 30 legs,
  // `is_winner:false` on every one, and this line named Tadej Pogacar — who lost that
  // race to Enric Mas Nicolau. The two halves of one sentence disagreed because only
  // one of them asked for the grade.
  //
  // The card degrades to the market title (`featuredName || title` at the call site),
  // which is honest and needs no explanation — notice 34.
  const featuredName = graded ? leaderLabel(graded) : null;

  // A SETTLED CARD GETS NO CAPTION AT ALL (#6061), and that keeps #6032's rule
  // rather than relaxing it: the hook leads on a LIVE market only, because
  // `hook_description` is pre-settlement editorial written while the question was
  // open ("...the question of rainfall in Dallas has become increasingly
  // pertinent") and under the word "Won" it reads as though the market were still
  // running — the call `layout.tsx` made for the description in #6002. The
  // settled card already says the result twice, in the 64px winner and the pill.
  //
  // Live: the hook if there is one. If there is not, the leader's name and price
  // are drawn at 40px and 96px directly above, so the only thing left worth
  // saying is the standing line for a card with no market story on it at all.
  const subtitle = isResolved
    ? null
    : opts.hookDescription ||
      (opts.leader ? null : "Prediction markets translated into intuitive probabilities.");

  return { featuredName, isResolved, settledWon, subtitle };
}

/**
 * The clarification that explains the blend line's movement. Deterministic,
 * blend-only (no per-source detail): prefer opening→current ("up X pts from
 * opening"), fall back to the 24h change, else null (nothing to say). Movements
 * under 1 point read as "roughly flat" rather than noisy decimals.
 */
export function movementExplanation(leader: MovementLeader | null): string | null {
  if (!leader) return null;
  const label = leaderLabel(leader);
  const cur = leader.probability;
  const open = leader.opening_probability;

  if (cur != null && open != null) {
    const delta = (cur - open) * 100;
    const mag = Math.abs(delta);
    if (mag >= 1) {
      return `${label} ${delta > 0 ? "up" : "down"} ${mag.toFixed(1)} pts from opening.`;
    }
    return `${label} roughly flat since opening.`;
  }

  const ch = leader.probability_change_24h;
  if (ch != null && Math.abs(ch * 100) >= 1) {
    const d = ch * 100;
    return `${label} ${d > 0 ? "up" : "down"} ${Math.abs(d).toFixed(1)} pts in the last 24h.`;
  }
  return null;
}

/* ───────────────────────────────────────────────────────────────────────────
 * UX-P233 — EVERY NUMBER ON THIS PAGE STATES ITS BASELINE (board item 11).
 *
 * Alex, on /futures/109441: **"Very confusing."** Three numbers about Amazon, all
 * on one screen, none of them saying which window it covers:
 *
 *     hero pill        ↓ 71.5 pts        (no window stated at all)
 *     chart caption    "Amazon up 13.5 pts from opening."
 *     table row        Open: 14%   -71.5%   27%
 *
 * Unlabelled they do not merely under-inform, they look like a contradiction: a
 * hero saying "down 71.5" beside a caption saying "up 13.5" about the same outcome.
 *
 * 🔴 AND THE OBVIOUS LABEL IS THE ONE WE MAY NOT WRITE. The field is
 * `probability_change_24h`, so "in the last 24h" is the tempting caption — and the
 * payload disproves it. CAL-P159 (board item 12) proved all four writers store
 * `new − previous`, a PER-WRITE delta, which then FREEZES when a row stops being
 * written; -0.715 is Amazon's Aug-18 → Aug-28 step. Measured live 2026-08-31 18:51Z,
 * every outcome on that market carries `last_updated: 2026-08-28T20:50Z` — 2.9 days
 * old. Writing "24h" beside a number the same payload dates to three days ago is a
 * claim about the past the payload refutes (gotcha #53), and this board has blocked
 * on that class six times. So the label names what the field IS — the last recorded
 * move — and dates it from `last_updated`.
 *
 * These are pure and unit-tested; the arithmetic fix for the field itself is board
 * item 12's, in the calibration lane. Nothing here changes any number's VALUE.
 * ─────────────────────────────────────────────────────────────────────────── */

/** A price is "current" for a day; past that the page owes the reader an as-of. */
const AS_OF_AFTER_DAYS = 1;

/**
 * How stale a price is, in days, or `null` when we cannot tell. Never 0 for a
 * missing stamp — that would read as "fresh", which is absence dressed as a fact.
 * A stamp in the future clamps to 0 rather than going negative.
 */
export function priceAgeDays(
  lastUpdated: string | null | undefined,
  now: Date = new Date(),
): number | null {
  if (!lastUpdated) return null;
  const then = new Date(lastUpdated);
  if (Number.isNaN(then.getTime())) return null;
  return Math.max(0, (now.getTime() - then.getTime()) / 86_400_000);
}

/* ───────────────────────────────────────────────────────────────────────────
 * UX-P260 (#2624) — A DATE ON AN INSTANT BELONGS TO THE READER, NOT TO UTC.
 *
 * Alex, on `/futures/1` at 20:12 PT on **Sep 1**: the hero pill read
 * **"last move · Sep 2"**. The site was dating a price move TOMORROW. The same
 * page contradicted itself 400px lower — the Probability Trend axis ended at
 * "Sep 1 5 PM", the same instant, formatted correctly.
 *
 * This function used to pin `timeZone: "UTC"`, and its reasoning is preserved
 * here because it was not silly:
 *
 *     "A label built from the machine's local zone is a claim whose answer
 *      depends on where it renders, and a guard for it is a test whose answer
 *      depends on where it runs (the trap CERT-534 named one lane over)."
 *
 * The second half of that is a real hazard and this repo is still paying it —
 * #2462 leaves `discoverTournamentCardTiming` five-red on clean master for
 * anyone outside UTC. But the cure was worse than the disease: it bought a
 * deterministic GUARD by making the SHIPPED LABEL wrong for every reader west
 * of Greenwich, every evening. For US users that is every move after 17:00 PT.
 *
 * 🔵 THE DISTINCTION THAT DECIDES IT, and it is the whole fix: **a calendar date
 * is not an instant.** A tournament runs Sep 3–6 no matter where you stand, so
 * `gameTimeLabel.ts`, `UpcomingTournaments.tsx`, `NextEditionStrip.tsx` and the
 * golf/playoff pages are RIGHT to pin UTC on their date-only values — pinning is
 * what stops "2026-09-05" sliding to Sep 4 in Los Angeles. A price move is the
 * opposite: it happened at one moment, and the only honest name for that moment's
 * day is the day it was where the reader is standing. Those seven sites are
 * deliberately untouched; this one was the only one formatting an instant.
 *
 * So the zone becomes a PARAMETER instead of a constant. That answers the old
 * comment's objection rather than overriding it: the guards below pass an
 * explicit zone and are therefore deterministic wherever they run, while the
 * page passes nothing and gets the reader's own clock — the same thing
 * `FuturesChart` has always done one component away (`FuturesChart.tsx:300`
 * formats with no `timeZone`, which is why the axis was already right).
 *
 * Safe to render locally on this page specifically: the futures detail page
 * takes its payload from `useSWR` behind an early return, so the label is never
 * in the server HTML and there is no hydration boundary to mismatch across. The
 * chart is the standing proof — it has formatted local here for as long as it
 * has existed.
 *
 * Nothing here changes any number's VALUE, or the arithmetic in `priceAgeDays`,
 * which compares epoch milliseconds and never had a zone to get wrong.
 * ─────────────────────────────────────────────────────────────────────────── */

/**
 * "Aug 28" — the day the given INSTANT fell on, in `timeZone` when one is
 * supplied, otherwise in the zone the code is running in (in the browser: the
 * reader's own). Guards MUST pass an explicit zone; the app deliberately does not.
 */
function instantDayLabel(when: Date, timeZone?: string): string {
  return when.toLocaleDateString("en-US", {
    month: "short",
    day: "numeric",
    ...(timeZone ? { timeZone } : {}),
  });
}

/**
 * The window label for a movement figure: **"last move · Aug 28"**, or plain
 * "last move" when the payload carries no stamp to date it with.
 *
 * The noun does NOT change with the clock. A per-write delta on a row written ten
 * minutes ago is still a per-write delta, so a fresh row does not earn the word
 * "today" and no row ever earns "24h" — see the block comment above.
 */
export function movementWindowLabel(
  lastUpdated: string | null | undefined,
  now: Date = new Date(),
  timeZone?: string,
): string {
  if (priceAgeDays(lastUpdated, now) == null) return "last move";
  return `last move · ${instantDayLabel(new Date(lastUpdated as string), timeZone)}`;
}

/**
 * "as of Aug 28" for a price the payload dates to more than a day ago, else `null`.
 *
 * Null in BOTH unprovable directions: a genuinely fresh price needs no as-of (the
 * label would be noise, not honesty), and a price with no stamp gets no claim about
 * its freshness OR its staleness, because we cannot support either.
 */
export function asOfLabel(
  lastUpdated: string | null | undefined,
  now: Date = new Date(),
  timeZone?: string,
): string | null {
  const age = priceAgeDays(lastUpdated, now);
  if (age == null || age <= AS_OF_AFTER_DAYS) return null;
  return `as of ${instantDayLabel(new Date(lastUpdated as string), timeZone)}`;
}

export type FuturesSortField = "probability" | "change" | "name";
export type FuturesSortDirection = "asc" | "desc";

export interface SortableOutcome {
  name: string;
  probability: number | null;
  probability_change_24h?: number | null;
  /** Grading, on a settled market only. See `sortFuturesOutcomes`'s `resolved`. */
  is_winner?: boolean | null;
}

/**
 * UX-P230 — the "All Outcomes" table's ordering.
 *
 * ONE CONVENTION, and it is the whole point of this function: **every comparator
 * below is written ASCENDING** (a before b when the result is negative), and the
 * direction flip at the bottom is the ONLY place that reverses. `desc` therefore
 * means "biggest first" for probability, "biggest gainer first" for change, and
 * Z→A for name.
 *
 * The detail page previously kept these comparators inline and authored two of
 * the three in reverse (`b - a`) while `name` used the normal convention — so the
 * shared inverter, written for `name`, flipped the other two a SECOND time. Under
 * the default `probability`/`desc` the table rendered ascending: on market 109441
 * the 27% leader the hero is entirely about was the LAST of eight rows, under a
 * pill reading "Probability ↓".
 *
 * Keeping it here rather than inline is not tidying: an inline switch can only be
 * exercised through the page's default state, which is exactly why five of the six
 * field×direction combinations had never been under test.
 *
 * ─────────────────────────────────────────────────────────────────────────────
 * UX-P232 (CERT-598's block) — `resolved`: THE RESULTS ORDER LEADS WITH THE WINNER.
 *
 * On a SETTLED market the hero is not the price leader. `pickHeroOutcome` above
 * deliberately features the GRADED WINNER, whose last-traded probability is frozen
 * at whatever it was when the market closed and is routinely NOT the highest on the
 * board. Production, 2026-08-31: "Arsenal vs Coventry: First Goalscorer" grades Kai
 * Havertz at 21% while two players who did not score are frozen at 99%. Ordering by
 * price alone therefore put a loser at the top of a section headed "Final Results",
 * with the winner at row three — UX-P230's own defect (hero and table disagreeing)
 * surviving into the one state it never rendered.
 *
 * So `resolved` promotes graded winners, and its LIMIT is the point:
 *
 *   - It applies to the RESULTS ORDER only — `probability` + `desc`, the page
 *     default, the one ordering that claims to answer "what happened".
 *   - An explicit `name` or `change` sort, or `probability` ASCENDING, is a request
 *     for a different question and is answered literally. Lifting a 21% winner above
 *     a 2% longshot under a pill reading "Probability ↑" would make the arrow lie.
 *
 * The promotion is written as an ordinary ASCENDING primary key (winner sorts LAST)
 * so the single direction flip at the bottom stays the only reverser in this
 * function. An early `return` here would skip that flip, and a comparator with two
 * exits is how you get one that is not antisymmetric.
 */
export function sortFuturesOutcomes<T extends SortableOutcome>(
  outcomes: readonly T[],
  field: FuturesSortField,
  direction: FuturesSortDirection,
  resolved = false,
): T[] {
  const winnerLeads = resolved && field === "probability" && direction === "desc";

  return [...outcomes].sort((a, b) => {
    let comparison = 0;

    if (winnerLeads) {
      // Ascending like everything else: `is_winner === true` sorts last here, and
      // the flip below lifts it to the top. `false` and `null` are both simply
      // "not the winner" — an ungraded row is never promoted over a graded loser.
      comparison =
        (a.is_winner === true ? 1 : 0) - (b.is_winner === true ? 1 : 0);
    }

    if (comparison === 0) {
      switch (field) {
        case "probability":
          comparison = (a.probability ?? 0) - (b.probability ?? 0);
          break;
        case "change": {
          // The signed change, never its magnitude: ascending puts the biggest
          // losers first, descending the biggest gainers.
          const aChange = a.probability_change_24h ?? 0;
          const bChange = b.probability_change_24h ?? 0;
          comparison = aChange - bChange;
          break;
        }
        case "name":
          comparison = a.name.localeCompare(b.name);
          break;
      }
    }

    return direction === "asc" ? comparison : -comparison;
  });
}

/**
 * D102 / #4568 — the ALL OUTCOMES fold.
 *
 * Alex, 2026-09-09 (standing notice 37): "Untraded or vanished props go behind a
 * collapsed toggle ('Untraded props (3)') — present, openable, taking no real
 * estate when closed."
 *
 * WHAT A READER GOT BEFORE THIS. `bainluck.com/futures/114175`, "Who will be UFC
 * Heavyweight champion at the end of 2026?", 390px, 2026-09-17 20:2xZ — ranks
 * 15-19 of ALL OUTCOMES:
 *
 *     14  Rizvan Kuniev   LAST MOVE  -   LATEST  <1%
 *     15  Fighter E       LAST MOVE  -   LATEST  -
 *     16  Fighter D       LAST MOVE  -   LATEST  -
 *     17  Other           LAST MOVE  -   LATEST  -
 *     18  Fighter F       LAST MOVE  -   LATEST  -
 *     19  Fighter G       LAST MOVE  -   LATEST  -
 *
 * Five ranked, named, numberless rows at the foot of a championship ladder. The
 * Kalshi legs in #4568's original report ("Before Nov 1, 2025") are at least real
 * labels; these are placeholders.
 *
 * WHY THIS WAS NOT ALREADY HANDLED, which #4568 asked and nobody had answered.
 * The page's only collapse is `slice(0, 25)` — a flat overflow cap, blind to
 * price. Measured on four payloads: `11020528` serves 36 outcomes with ONE null
 * leg (cap hides rows 26-36, the null among them, so the page "looked" like it
 * folded); `108559` 22/2, `108555` 22/5 and `114175` 19/5 are all under 25, so
 * every numberless row rendered. The one page that appeared to have D102's
 * toggle was a coincidence of length. A count cap cannot become a semantic
 * partition by tuning the number.
 *
 * THE PREDICATE IS `probability == null`, AND IT IS THE RENDER'S OWN.
 * `OutcomeRow` prints `formatProbability(outcome.probability, { rendered })`,
 * and `formatProbability` returns `"-"` on null BEFORE it consults `rendered`
 * (`lib/api.ts:799`) — so the override cannot rescue a null, and this folds
 * exactly the rows that print a dash and no others. That check is the whole
 * point: the props twin of this fold (`components/event/PropsSection`) was first
 * built against a field that looked absent, and 89 of 89 rows it would have
 * folded carried a live price.
 *
 * THE LABEL IS D111's, NOT THIS ISSUE'S TITLE. #4568 was filed against D102's
 * original "Untraded" wording; Alex overruled that wording on 2026-09-10 and
 * `MORE_PROPS_LABEL` has read "More props" since. Neutral wording claims nothing
 * about WHY a row is folded, which is why it survived where "Untraded" did not.
 * Here "Untraded" would arguably even be true — but the ruling is about what the
 * reader is told, not about what we could defend, so this is "More outcomes".
 *
 * Collapsed, never dropped (gotcha #43): the rows stay reachable, keep their
 * served `rank`, and render in the normal row presentation.
 */
export function partitionOutcomesByPrice<T extends { probability: number | null }>(
  outcomes: readonly T[],
): { listed: T[]; folded: T[] } {
  const listed: T[] = [];
  const folded: T[] = [];
  for (const outcome of outcomes) {
    if (outcome.probability == null) folded.push(outcome);
    else listed.push(outcome);
  }
  return { listed, folded };
}

/**
 * #6989 — the sentence the "All Outcomes" table prints when the partition above
 * listed NOTHING, and `null` when it listed anything at all.
 *
 * `/futures/109681` ("CPI year-over-year in Oct 2026?") is the filed specimen:
 * 16 Kalshi legs on empty books (`bid 0.0000 / ask 0.9800`), all withheld by the
 * backend's empty-book guard, so all 16 arrive `probability: null` and
 * `partitionOutcomesByPrice` folds every one. The withholding is CORRECT — those
 * midpoints are the artifact #6757/#6727 exist to remove — and this function
 * changes nothing about it. What was wrong is what the reader was left with:
 *
 *     📊 All Outcomes   as of Feb 27
 *     [ Probability ↓ ] [ Last move ] [ Name ]
 *     ▶ More outcomes (16)
 *
 * A section named for outcomes showing none, three chips that sort an empty
 * list, and a seven-month-old date attached to prices nobody can see. Not a
 * blank card — a working control panel with nothing behind it, which is worse,
 * and diagnostic furniture of exactly the kind notice 34 / D102 forbid.
 *
 * WHY THE PREDICATE IS THE LISTED COUNT AND NOT `prices_withheld`.
 * Withholding is one way to get here and the page should not care which way it
 * did. The claim a sort chip makes is "there is an order you can put these rows
 * in"; the claim an as-of makes is "the numbers below were read on this date".
 * Both are false exactly when no row prints a number, whatever emptied it — a
 * withheld book, a market with no outcomes, a payload that arrived thin. One
 * count answers all three questions, so one count is the input.
 *
 * ONE STRING FOR BOTH STATES, deliberately. A settled field whose rows are all
 * numberless would print this under "Final Results", where it reads oddly but
 * stays TRUE: there are no current prices, and the rows are in the fold. The
 * resolved-specific alternative would have to say something about what was
 * recorded, and nothing on this payload supports such a claim (#6301's lesson:
 * no verdict beats a wrong one). Measured: settled markets carry `0.0`, not
 * `null`, so the reachable population here is open markets.
 *
 * The folded rows are NOT dropped (gotcha #43) — the caller keeps them behind
 * `More outcomes (N)`, which is D102's shape for present-but-priceless rows.
 */
export const NO_PRICED_OUTCOMES_NOTE = "No current prices for this market.";

export function noPricedOutcomesNote(listedCount: number): string | null {
  return listedCount === 0 ? NO_PRICED_OUTCOMES_NOTE : null;
}
