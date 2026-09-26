import { formatShareProbability } from "./share";
// #7906 — the ONE shape measured to hold true peers. Every other shape was read
// against production and rejected; the tally is in `gradedWinner`'s comment.
import { SHAPE_PARTICIPATION } from "./marketShape";

const PEER_WINNER_SHAPES: ReadonlySet<string> = new Set([SHAPE_PARTICIPATION]);

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
 *
 * #7439 — A GRADED ROW IS UNBEATABLE IN A SORT BY PROBABILITY, AND ON A LIVE
 * MULTI-WINNER FIELD IT IS NOT THE ANSWER.
 *
 * `leader` arrives as `sort(by probability desc)[0]`, so a row already graded
 * `is_winner` sits at 1.0 and wins that sort forever. Production,
 * `/futures/114091` — *"Who will become a UFC champion in 2026?"*, 28 fighters,
 * `status: "open"`, resolving in December — headlined:
 *
 *     100%
 *     Sean Strickland
 *     Resolves Dec 31, 2026
 *
 * He did become a champion in 2026, so the grade is right; the question is still
 * open because it asks for *a* champion, not *the* champion. The reader met a
 * live field whose headline answer was 100% and a name.
 *
 * This is #7396's mechanic one surface over (there, `pickJourneyFuture` on the
 * team page) and the backend's `_championship_path_stmt` rule one layer down.
 *
 * 🪤 THE SCOPE IS THE WHOLE OF THE FIX, AND IT IS WHY THIS IS NOT A ONE-LINER.
 * 671 open tier<=3 markets carry a graded row beside live ones, and they FORK:
 *
 *   - `mutually_exclusive === false` (329 markets, the UFC shape): several rows
 *     can be graded YES and the question stays open. A graded row is a RESULT;
 *     the hero must feature the live leader. This branch.
 *   - `mutually_exclusive` true/unknown (342 markets): one graded row means the
 *     question IS answered. Skipping it would HIDE the answer and crown a
 *     runner-up — strictly worse than the status quo. Untouched, deliberately.
 *
 * So the new behaviour is gated on an EXPLICIT `false`. Absent/null/true keeps
 * today's answer, which also matches the serializer's own default
 * (`getattr(market, "mutually_exclusive", True)`) — an unknown field is mutex.
 *
 * The graded row is never deleted from the page: it keeps its table row, its
 * "Won" grade and its place in the outcome list. Only the FEATURED row moves.
 * When every row is graded there is no live leader to promote, so the fallback
 * is today's behaviour rather than an empty hero.
 *
 * 🪤 AND THE SECOND CLAUSE, WHICH REPLAYING THE REAL BOARDS IS WHAT FOUND.
 *
 * Promoting the best UNGRADED row is only an improvement when that row carries
 * a price. Measured over the 315 boards this rule moves, the promoted row is at
 * **exactly 0% on 51 of them (16%)** — mostly cumulative threshold ladders,
 * where the graded rung is the one already cleared and every tighter rung is
 * dead:
 *
 *   /futures/108569    "Above 56" graded 0.9995   ->  "Above 60"  0.0
 *   /futures/12925046  "Governor Democratic primary" 0.98
 *                                                 ->  "Senate Republican primary" 0.0
 *
 * A hero reading "0% Above 60" is not a repair of "100% Above 56"; it is a
 * different wrong headline, and arguably the worse one, because a board whose
 * every live row is at zero is DECIDED even though `mutually_exclusive` is
 * false — the cleared rung really is the answer.
 *
 * So the promotion needs a live row that is actually live. When the best
 * ungraded row has no price, there is no live leader and the fallback is
 * today's behaviour. That leaves 264 boards genuinely improved and no hero
 * printing a name beside 0%. A row at 3% still promotes: "the field's best shot
 * is 3%" is an odd sentence but a true one, and 0 is the only crisp line
 * between "unlikely" and "nothing here".
 */
export function pickHeroOutcome<
  T extends { is_winner?: boolean | null; probability?: number | null; name?: string | null },
>(
  outcomes: readonly T[],
  leader: T | null,
  resolved: boolean,
  mutuallyExclusive?: boolean | null,
): T | null {
  if (!resolved) {
    if (mutuallyExclusive !== false) return leader;
    return pickLiveLeader(outcomes) ?? leader;
  }
  const winners = outcomes.filter((o) => o.is_winner === true);
  return winners.find((o) => !isLineOrPropLeg(o.name)) ?? winners[0] ?? leader;
}

/**
 * #8280 — A GAME BOARD'S TOTALS AND SPREAD LEGS WIN TOO, AND NONE OF THEM IS
 * THE WINNER.
 *
 * A Polymarket game market carries its moneyline, totals and spread legs as
 * outcomes of one board, and each is graded on its own. Production,
 * `/futures/114108` — *Kings vs. Blue Jackets*, served in this order:
 *
 *     O/U 5.5       won
 *     O/U 6.5       won
 *     Kings         won
 *     Spread -1.5   lost
 *
 * The hero took the first graded row and read **"O/U 5.5 WON"**: a number, not
 * a side, over a game the Kings won. Settled means settled — a hero shows the
 * winner.
 *
 * So among the graded rows the hero prefers one that names a side. This only
 * RE-ORDERS the graded rows; it never promotes an ungraded one and never
 * withholds. When every graded row is a line or a prop (a soccer board whose
 * moneyline leg is not in our copy), the first one is still featured, exactly
 * as before. That residue is known and is not this rule's to decide.
 *
 * A board whose first graded row already names a side is unchanged, which is
 * every single-winner board and every threshold ladder (`77° or above` matches
 * nothing here, so #6032's loosest-rung behaviour stands).
 *
 * The shapes below were read off the multi-winner Polymarket game boards on
 * production (2026-09-23): `O/U 5.5`, `X vs. Y: O/U 1.5`, `1H O/U 108.5`,
 * `Luka Dončić: Points O/U 30.5`, `O/U 1.5 Rounds`, `Spread -1.5`,
 * `Spread: Nashville SC (-2.5)`, `1H Spread: Lakers (-3.5)`,
 * `Rayo Vallecano de Madrid (-1.5)`, `Both Teams to Score` (sometimes cut to
 * `Both Teams to Sco`), questions ending `?` (`Fight won by KO/TKO?`), and the
 * bare matchup `Green vs. Zellhuber`, which names both sides and so neither.
 */
export function isLineOrPropLeg(name: string | null | undefined): boolean {
  const n = (name || "").trim();
  if (!n) return false;
  return (
    /\bO\/U\b/i.test(n) ||
    /^(1H |2H )?Spread\b/i.test(n) ||
    /\([+-]\d+(\.\d+)?\)$/.test(n) ||
    /^(over|under)\s+\d/i.test(n) ||
    /both teams to sco/i.test(n) ||
    /\?$/.test(n) ||
    /\svs\.?\s/i.test(n)
  );
}

/**
 * #7439 — the highest-probability outcome that is NOT already graded a winner
 * AND still carries a price, or null when there is no such row.
 *
 * Null therefore means "this board has no live leader", which is true in two
 * different ways — every row graded, or every ungraded row at 0% — and both
 * want the same answer from the caller: leave today's behaviour alone. See the
 * second clause on `pickHeroOutcome` for why the 0% case is not a repair.
 *
 * The comparator is byte-identical to the page's own `leader` memo, so on a
 * field with nothing graded this returns exactly the row `leader` already holds
 * — the new branch cannot re-order a healthy market. Stable-sorted on a copy:
 * ties keep payload order, the same way the page's does.
 */
export function pickLiveLeader<
  T extends { is_winner?: boolean | null; probability?: number | null },
>(outcomes: readonly T[]): T | null {
  return (
    [...outcomes]
      .sort((a, b) => (b.probability ?? 0) - (a.probability ?? 0))
      .find((o) => o.is_winner !== true && (o.probability ?? 0) > 0) ?? null
  );
}

/**
 * #8892 — A GAME CONTAINER LEADS WITH WHO WINS, NOT WITH ITS MOST LOPSIDED LEG.
 *
 * A Polymarket game container carries legs that answer DIFFERENT questions, so
 * "the highest-priced outcome" is just the most one-sided one. Production,
 * `/futures/61778284` — *LoL: Cloud9 vs Team Liquid (BO5)*, 2026-09-26:
 *
 *     Over — O/U 3.5 Games     71%    <- the hero, the unfurl title, the card
 *     ...
 *     Cloud9 — Match Winner    36%    <- the number the title asks for, row 6
 *
 * The server names that leg (`lead_outcome_id`, #8894): the one full-contest
 * winner leg the venue corroborates, null everywhere else. Null keeps every
 * caller's own rule, so every other board is byte-identical.
 *
 * Returns the named row only while it is on the board with a price. On a
 * settled market it returns null: the grade decides that hero (#8280 already
 * prefers the side-naming graded row), not a pre-game pointer.
 */
export function servedLeadOutcome<T extends { id: number; probability?: number | null }>(
  outcomes: readonly T[],
  leadOutcomeId: number | null | undefined,
  status: string | null | undefined,
): T | null {
  if (leadOutcomeId == null || status === "resolved") return null;
  const lead = outcomes.find((o) => o.id === leadOutcomeId);
  return lead && lead.probability != null ? lead : null;
}

/**
 * #8892 — the chart a game container opens on draws the line its hero leads with,
 * ALONE.
 *
 * The container's other legs answer other questions, and the caption under the
 * chart names the highest-priced DRAWN line (`pickCaptionSubject`, #8016). Seeding
 * the lead beside the price seeds would print "Over — O/U 3.5 Games down 1.5 pts
 * from opening" under a hero reading "Cloud9 — Match Winner". Every leg stays in
 * the list and toggles onto the chart as before.
 *
 * With no lead, or a lead the loaded history has no rows for, the price seeds
 * stand: an empty chart is worse than a chart about another leg. An empty
 * `historyIds` means history has not loaded yet, not that the lead has none.
 */
export function chartSeedsWithLead<T extends { id: number }>(
  priceSeeds: readonly T[],
  lead: T | null,
  historyIds: ReadonlySet<number>,
): readonly T[] {
  if (lead && (historyIds.size === 0 || historyIds.has(lead.id))) return [lead];
  return priceSeeds;
}

/**
 * #7439 — the outcomes the trend chart selects on FIRST PAINT.
 *
 * Lifted out of the page's seed effect so the rule can be asserted directly.
 * It was inline, which meant the only thing a test could do about it was grep
 * the page's source for a substring — and a substring cannot tell a correct
 * filter from an inverted one. Every arm below is now a real assertion.
 *
 * The graded row headlining the hero was ALSO seeding this chart, so an open
 * market drew a flat 100% line across its whole Probability Trend. Same defect,
 * same gate (`mutually_exclusive === false`), same refusal to touch the mutex
 * half — on a mutually-exclusive field the graded row is the answer and belongs
 * in the seed.
 *
 * This decides FIRST PAINT only. The graded row keeps its checkbox in the table
 * below and a reader can add it back; nothing is removed from the chart.
 *
 * `limit` is the live-market seed width; the settled branch is unchanged from
 * L2-156 Item 2 (the WINNER — which may not be the highest current probability
 * — plus the runner-up).
 */
export function pickChartSeedOutcomes<
  T extends {
    id: number;
    is_winner?: boolean | null;
    probability?: number | null;
    name?: string | null;
  },
>(
  outcomes: readonly T[],
  resolved: boolean,
  mutuallyExclusive?: boolean | null,
  limit = 3,
): T[] {
  if (outcomes.length === 0) return [];

  const byProb = [...outcomes].sort(
    (a, b) => (b.probability ?? 0) - (a.probability ?? 0),
  );

  if (resolved) {
    // #8301 — the row the HERO features, asked through the hero's own helper.
    // This used to be the first graded row, which on a game board is a totals
    // line: `/futures/114108` headlined "Kings WON" over an empty chart, because
    // the seed was `O/U 5.5` and the history endpoint serves only Kings.
    const winner = pickHeroOutcome(outcomes, byProb[0], true) ?? byProb[0];
    const runnerUp = byProb.find((o) => o.id !== winner.id);
    return runnerUp ? [winner, runnerUp] : [winner];
  }

  // The gate carries BOTH of `pickHeroOutcome`'s clauses, so the chart and the
  // hero can never disagree about which row is this board's story: skip graded
  // rows only on a non-mutex field, and only when a priced live row exists at
  // all. On the 51 all-zero boards the hero holds, so the seed holds too.
  const live =
    mutuallyExclusive === false && pickLiveLeader(outcomes) !== null
      ? byProb.filter((o) => o.is_winner !== true)
      : byProb;

  // 🪤 `live` is never empty here, so there is deliberately no fallback branch.
  // An earlier draft carried `live.length > 0 ? live : byProb` and mutation
  // testing exposed it as unreachable: the early return leaves `byProb`
  // non-empty, the else-branch IS `byProb`, and the then-branch only runs when
  // `pickLiveLeader` found a priced ungraded row — which is itself a member of
  // the filtered list. Dead defensive code that no test can reach is how a
  // guard rots, so it is gone rather than left looking load-bearing.
  //
  // If the price clause in `pickLiveLeader` is ever loosened, that invariant
  // breaks and the fallback must come back.
  return live.slice(0, limit);
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
/* ───────────────────────────────────────────────────────────────────────────
 * #7906 — A BOARD THAT GRADED MANY WINNERS NAMES NONE OF THEM.
 *
 * #6079 gave the word "won" one source, and #6301 taught the three surfaces to
 * stay silent when that source grades NOBODY. Both ask "is the featured row a
 * winner". Neither asks "is it the ONLY one", and on a participation board that
 * is the whole question.
 *
 * Measured on production 2026-09-22 06:45Z, `/futures/61010898` at 390px:
 *
 *     BMW PGA Championship - Make the Cut
 *     Ludvig Aberg   WON                ← the hero
 *     Settled — Ludvig Aberg won.       ← the caption under the trend chart
 *     Final Results: 72 of 163 rows badged  Won · 100% Settled
 *
 * The payload serves `mutually_exclusive: false`, `market_type: 'participation'`
 * and seventy-two `is_winner: true` rows, because seventy-two golfers made that
 * cut. Aberg is one of them; he did not win the BMW PGA Championship. The crown
 * lands on him by accident of ordering: `pickHeroOutcome`'s resolved branch is
 * `outcomes.find((o) => o.is_winner === true)`, the FIRST graded row in payload
 * order. The 106-golfer board in #7906's original report reads "Jackson Suber
 * WON" for the same reason.
 *
 * 🔴 THE TEST IS THE COUNT OF GRADES, NOT `mutually_exclusive`. That flag cannot
 * carry this: CERT-609 on `independentOutcomesNote` records that only Kalshi's
 * `false` is affirmative, because Polymarket's parser turns an ABSENT `negRisk`
 * key into `false`. The number of graded rows is served by every source and
 * means the same thing in all of them.
 *
 * It is also the right test in the OTHER world, where plurality is corruption
 * rather than design. #6590 measured a MUTEX market serving two winners —
 * `/futures/60015154` printed "Settled — SK Beveren won." above a table badging
 * both `SK Beveren` and `Draw (…)` as Won, on a match that finished 3–0. There
 * we cannot tell which of the two rows is the lie, and #4923 already ruled that
 * case: no verdict beats a wrong one. One rule serves both.
 *
 * 🔴 BUT THE TWO WORLDS ARE REACHED BY TWO DIFFERENT DOORS, AND THE FIRST DRAFT
 * OF THIS GUARD USED ONE DOOR FOR BOTH. It withheld on any of five "peer" shapes
 * — `claim`, `container_member`, `duel`, `field`, `participation`. Four of those
 * were assumed, not read. Measured against production 2026-09-22 07:40Z:
 *
 *   duel   2,642 multi-winner boards, and they are NOT two-sided matches. They are
 *          independent markets grouped onto one board, where plural winners are
 *          CORRECT and the crown we print is the right answer:
 *            61674035  `Tiana Tian Deng` ‖ `Completed Match`      ← she won
 *            61507880  `Fight ends before round 3` ‖ `… round 2`  ← cumulative
 *            112963    `Pokrovsk by March 31` ‖ `… by February 28` ← cumulative
 *          Withholding there DELETES A TRUE STATEMENT. The ladders are the sharp
 *          end: this comment argues two paragraphs down that a ladder must keep
 *          its rung, and `duel` was stripping ladders — the exemption defeated by
 *          the shape it was written to protect, arriving through a third door.
 *   field  14,713 boards, mixed and with no discriminator available:
 *          61821192 `Alex Bolt` ‖ `… Set 1 Winner` crowns the real match winner
 *          today, while 61814734 `Map 1 Winner` ‖ `Match Winner` crowns a
 *          QUESTION name. Both `mutually_exclusive: false`, so the flag cannot
 *          separate them and a name heuristic would be the guess this guard
 *          refuses to make. Left alone; filed instead.
 *   claim  ZERO multi-winner boards. Including it was inert, not safe.
 *   container_member  unmeasurable (the aggregate times out). Unproven ⇒ out.
 *
 * So the shape door admits `participation` ALONE — 279 multi-winner boards, and a
 * 200-board sample carried no question-name leg at all: they are competitor lists,
 * which is what a peer board is. That is where this ship's own specimen lives.
 *
 * The contradiction door is `mutually_exclusive === true`, which is how #6590 is
 * still reached: of the 2,642 multi-winner `duel` boards exactly 22 declare
 * exclusivity, and a board that declares its outcomes exclusive and then grades two
 * IS the contradiction #4923 ruled on.
 *
 * That door turned out to be the larger half of this ship, and it is where the
 * flat impossibilities live. 644 `container_member` boards declare exclusivity and
 * then grade BOTH legs of a two-leg question:
 *
 *     19490985  "Set 1 Winner: Birrell vs Boulter"        → `No` AND `Yes`
 *     52362760  "Will the game go to extra innings?"      → `No` AND `Yes`
 *     949212    "…: First Half Winner"                    → both teams
 *     189108    "USD/JPY price on Feb 20 at 10am EST?"    → two DISJOINT buckets
 *
 * Today each prints "Settled — No won." on the strength of payload order, which is
 * a coin flip wearing a verdict. One of the two grades is a lie and nothing on the
 * page can say which, so the honest hero is silence — and the rows stay, so the
 * contradiction remains visible to anyone who looks. 🔴 This arm deliberately
 * overrides the `quantity` exemption: 189108 is not a cumulative ladder but a set
 * of mutually-exclusive buckets, and a cumulative ladder does not declare itself
 * exclusive. The exemption protects ladders, not the word `quantity`.
 *
 * 🔴 Only `true` may decide. CERT-609 records
 * that Polymarket's parser turns an ABSENT `negRisk` key into `false`, so a `false`
 * is not a claim of independence and is never read as one — which is also why this
 * arm cannot regress anything: a spurious `false` merely leaves today's behaviour.
 * The BMW PGA board is itself `mutually_exclusive: false`, so the flag can only ADD
 * boards to the rule, never gate the shape door.
 *
 * 🔴 PLURALITY ALONE IS NOT THE TEST — A LADDER'S PLURAL GRADES ARE ITS DESIGN.
 * On a cumulative threshold board several rungs being true is correct, and the
 * rungs are ORDERED, so the first true one is a canonical sentence. #6032's
 * specimen is exactly that: `/futures/60544511`, a New York temperature ladder
 * serving `77° or above`, `78° or above` and `82° or above` all graded true,
 * whose card correctly reads "77° or above won". Winners on a field or a
 * participation board are PEERS in no order at all, which is why choosing among
 * them can only be arbitrary — Aberg is crowned for being emitted first.
 *
 * (Whether a ladder should name its LOOSEST true rung is a real question and it
 * is not this one — #6032 asserts that behaviour deliberately and it stays.)
 *
 * 🔴 SO THE GUARD IS KEYED POSITIVELY, ON THE STORED SHAPE, AND DECLINES TO GUESS.
 * It fires only when `market_type` AFFIRMS that the winners are peers. The
 * tempting form — "decline unless the shape is `quantity`" — reads the same until
 * the shape is missing, and then it inverts: `resolveShapeFallback`'s
 * `NUMERIC_OUTCOME_RE` anchors its keywords at the START of the name, so
 * `"77° or above"` matches nothing and a temperature ladder classifies as a
 * FIELD. A negative test would therefore strip the crown from precisely the
 * boards this paragraph exempts, on every payload whose shape had not been
 * backfilled. Widening that regex is not this ship's to do — it re-shapes cards,
 * concept pages and the feed, all of which key off the same field.
 *
 * The honest cost, stated rather than papered over: a peer board that carries NO
 * stored `market_type` keeps today's behaviour and stays wrong. This fixes the
 * boards the API can prove, and never guesses on the ones it cannot.
 *
 * Single-winner boards are untouched byte for byte — the guard falls through and
 * the #6079/#6301 test below decides exactly as it did before. This withholds a
 * CROWN, never a row: the Final Results table still badges all seventy-two, which
 * is the honest place for that fact and the reason the silence leaves no hole.
 * ─────────────────────────────────────────────────────────────────────────── */
export function gradedWinner<T extends { is_winner?: boolean | null }>(
  outcomes: readonly T[],
  leader: T | null,
  status: string | null | undefined,
  marketType?: string | null,
  mutuallyExclusive?: boolean | null,
): T | null {
  if (status !== "resolved") return null;
  const peerShaped = PEER_WINNER_SHAPES.has(marketType ?? "");
  // 🔴 `=== true` and never a truthiness test: only an AFFIRMATIVE exclusivity
  // claim may withhold a crown. See the block comment — a `false` here is not
  // evidence of anything, so it must fall through rather than decide.
  const contradictory = mutuallyExclusive === true;
  if (peerShaped || contradictory) {
    // Counted rather than filtered: the answer is settled by the SECOND grade,
    // and a participation board carries 163 rows.
    let graded = 0;
    for (const outcome of outcomes) {
      if (outcome?.is_winner === true) {
        graded += 1;
        if (graded > 1) return null;
      }
    }
  }
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
export function boardOutcomeLabel(name: string, marketName?: string | null): string {
  return withoutBoardNamePrefix(name.trim(), marketName);
}

/**
 * #6765 — A BOARD DOES NOT REPEAT ITS OWN QUESTION ON EVERY LINE.
 *
 * `/futures/61645756` at 390px, 2026-09-21, prints this and nothing between the
 * two lines:
 *
 *     Korea Open: Alevtina Ibragimova vs Yeon-Woo Ku          ← the <h1>
 *     70%
 *     Korea Open: Alevtina Ibragimova vs Yeon-Woo Ku Set 1 O/U 9.5
 *
 * On these in-play tennis and table-tennis boards the venue's OUTCOME name is
 * the whole question plus a few words, so the only information in the second
 * line is `Set 1 O/U 9.5` and the reader has to re-read a 45-character prefix to
 * reach it. The same prefix then appears on every row of All Outcomes, where the
 * row is `truncate`d — three different sub-markets rendered as three visually
 * IDENTICAL rows ending in `…`, which is the worse half of this defect and the
 * reason the fix is not confined to the hero.
 *
 * ═══ THE RULE IS A BOUNDARY, NOT A LENGTH ═══
 *
 * Strip the board's own name when the outcome name STARTS with it AND the next
 * character is a separator. Both clauses matter: the boundary test is what stops
 * a board called `Italy` eating the first word of `Italymania`, and no tuned
 * length constant appears here because a threshold is exactly the kind of number
 * that drifts. Measured on production 2026-09-21 over every open futures market
 * — 194 outcome rows on 66 boards carry their board's name as a strict prefix,
 * and **0 of them break at a non-separator**, so a boundary test costs the fix
 * nothing and buys it the whole hostile family.
 *
 * ═══ IT CAN ONLY EVER REMOVE A REPEAT, NEVER THE ANSWER ═══
 *
 * Three refusals, each of which returns the name untouched:
 *
 *   - no board name to compare against (every other surface, unchanged);
 *   - the outcome name is the board name EXACTLY, or shorter — there is no
 *     remainder, and printing nothing is worse than printing a repeat;
 *   - the remainder is only separators. A row is never left blank by this.
 *
 * So the worst case is today's behaviour. Measured over the same 194 rows: the
 * shortest surviving remainder is 12 characters (`Set 1 Winner`), 0 rows strip to
 * empty, and the median line loses 43 characters of prefix.
 *
 * The comparison is case-insensitive and the remainder is sliced from the
 * ORIGINAL string, so a board that shouts its name does not re-case the answer.
 *
 * ⚠️ THIS IS A PAGE RULE, NOT A NAME RULE. It may only be applied where the board
 * name is on screen beside the outcome — `/futures/[id]`, whose `<h1>` IS the
 * market name. A card on Discover or a search result carries the outcome name
 * with no question above it, and there the prefix is the only thing naming the
 * match. That is why the market name is a parameter rather than something this
 * function looks up, and why `FuturesChart`'s legend is deliberately NOT changed
 * here: it is drawn on five surfaces and takes no market name (#7813).
 */
export function withoutBoardNamePrefix(name: string, marketName?: string | null): string {
  const label = name.trim();
  const board = (marketName ?? "").trim();
  if (!board || label.length <= board.length) return label;
  if (label.slice(0, board.length).toLowerCase() !== board.toLowerCase()) return label;
  if (!BOARD_PREFIX_SEPARATOR.test(label.charAt(board.length))) return label;
  const remainder = label.slice(board.length).replace(BOARD_PREFIX_LEADING, "").trim();
  return remainder || label;
}

/** The characters a venue puts between a board's name and the rest of an outcome
 *  name. Space and colon are the only two seen in the measured population (43
 *  and 2 of 45 heroes); the rest are here because a separator list that is
 *  narrower than the punctuation a venue actually uses fails CLOSED — an
 *  unrecognised separator leaves the repeat on the page, which is today. */
const BOARD_PREFIX_SEPARATOR = /[\s:;,\-–—|·/]/;
const BOARD_PREFIX_LEADING = /^[\s:;,\-–—|·/]+/;

/*
 * `isGenericOutcomeName` was DELETED by #7256, not narrowed.
 *
 * It existed for one caller — `boardOutcomeLabel` above — and answered one
 * question: "is this name too bare to print, so that 'Yes' reads better?" The
 * production count of the family it was written to rescue (`Option A`,
 * `Choice 1`, `Bucket 3`) is zero, and every other arm it fired on was a real
 * answer being overwritten. With the substitution retired there is no caller
 * left, and an exported predicate that nothing calls is worse than no predicate:
 * the next reader would take its existence as evidence that the hero still
 * substitutes. The arms it recognised are recorded in `boardOutcomeLabel`'s
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
  /** `FuturesMarket.market_type` (#7906) — optional; `gradedWinner` falls back
   *  to the outcome-name heuristic when a caller cannot supply it. */
  marketType?: string | null;
  /** `FuturesMarket.mutually_exclusive` (#7906) — only an affirmative `true`
   *  withholds a crown; absent or `false` leaves today's behaviour untouched. */
  mutuallyExclusive?: boolean | null;
}): FuturesUnfurlCopy {
  const isResolved = opts.status === "resolved";
  // `is_winner === true` is required before the word "won" is printed, mirroring
  // `FuturesHero`'s `resolvedWon` chip. `pickHeroOutcome` falls back to the price
  // leader when nothing is graded, and a fallback must not crown an ungraded row
  // — those say only what `status` proves.
  // #6079 — asked through `gradedWinner` rather than re-derived here, because the
  // unfurl TITLE needs the identical answer and the copy of this test that lived
  // in `layout.tsx` is exactly the one that went missing.
  // #7906 — the shape and the exclusivity claim travel with the question, so the
  // card declines a crown on exactly the boards the page declines one on, ladders
  // and grouped independent markets excepted in both.
  const graded = gradedWinner(
    opts.outcomes,
    opts.leader,
    opts.status,
    opts.marketType,
    opts.mutuallyExclusive,
  );
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
 * How many series the trend chart draws when the reader has selected none.
 * Exported so the caption below and the chart itself quote one number.
 */
export const CHART_LINES_WHEN_NONE_SELECTED = 5;

/**
 * #8016 — THE SET THE CHART ACTUALLY DRAWS, asked once so two surfaces cannot
 * disagree about it.
 *
 * This rule used to live only inside `FuturesChart`'s `displayedOutcomes` memo,
 * so the caption beneath the chart had no way to ask what the chart had drawn
 * and picked its subject from `market.outcomes` instead — every leg, including
 * the ones the chart deliberately leaves off. On `/futures/109257` ("Who will
 * Donald Trump meet in 2026?") that printed
 *
 *     legend:  Andy Burnham · Vladimir Putin · Mohammed bin Salman
 *     caption: "Lionel Messi up 81.0 pts from opening."
 *
 * Messi is `is_winner: true` at 1.00 from 0.19, so +81.0 is arithmetically
 * correct — and `pickChartSeedOutcomes` drops graded rows from a live non-mutex
 * field (#7439), so the one leg the sentence named was the one leg the chart
 * could never show. "Settled means settled" was being applied to the lines and
 * not to the caption.
 *
 * The chart is the authority on what is on screen, so the chart's own memo now
 * calls this too rather than keeping a second copy of the rule.
 */
export function visibleChartOutcomes<T extends { outcome_id: number }>(
  historyData: readonly T[],
  selected?: ReadonlySet<number> | null,
): T[] {
  if (selected && selected.size > 0) {
    return historyData.filter((o) => selected.has(o.outcome_id));
  }
  return historyData.slice(0, CHART_LINES_WHEN_NONE_SELECTED);
}

/**
 * #8016 — the caption's subject: the drawn line with the highest current
 * probability, or null when the chart is drawing nothing.
 *
 * 🔴 THE QUESTION IS "WHICH LINE LEADS", NOT "WHICH LEG MOVED MOST", and the
 * specimen cannot tell you which: on 109257 Messi is the probability leader
 * (1.00) AND the largest mover (+81.0), which is why #8016 describes the rule as
 * picking the biggest move. It does not. Inside the drawn set the two separate —
 * Putin moves most (−19.5), Burnham leads (0.95) — and the caption must name
 * Burnham. The selection rule is deliberately the same one `leader` uses — highest
 * `probability`, nulls sorting last — narrowed to the charted set and nothing
 * else, so a board whose leader IS charted (the ordinary case) is untouched.
 *
 * Returning null rather than falling back to the overall leader is the point:
 * a caption that reaches outside the chart to find a subject is the defect.
 * Notice 34 — leave the space empty rather than explain the emptiness.
 */
export function pickCaptionSubject<
  T extends { id: number; probability?: number | null },
>(outcomes: readonly T[], drawnIds: ReadonlySet<number>): T | null {
  if (drawnIds.size === 0) return null;
  const drawn = outcomes.filter((o) => drawnIds.has(o.id));
  if (drawn.length === 0) return null;
  return [...drawn].sort(
    (a, b) => (b.probability ?? 0) - (a.probability ?? 0),
  )[0];
}

/**
 * The clarification that explains the blend line's movement. Deterministic,
 * blend-only (no per-source detail): prefer opening→current ("up X pts from
 * opening"), fall back to the 24h change, else null (nothing to say). Movements
 * under 1 point read as "roughly flat" rather than noisy decimals.
 *
 * #6765 — `marketName` is OPTIONAL and shortens nothing on its own: it is handed
 * to the same `withoutBoardNamePrefix` the hero and the rows use, so a caption on
 * a board whose outcome names repeat its title reads "Set 1 O/U 9.5 up 22.0 pts
 * from opening." instead of the `<h1>` plus five words. It is applied to the
 * LABEL rather than to `leader.name`, which keeps `leaderLabel`'s #5997 rule
 * exactly where it is — a label that came back "Yes" or "No" has no board prefix
 * to lose, so the two rules cannot interact.
 */
export function movementExplanation(
  leader: MovementLeader | null,
  marketName?: string | null,
): string | null {
  if (!leader) return null;
  // `leaderLabel` is typed `string | null` for its own null-leader arm, which this
  // function has already returned on. The guard keeps the old shape EXACTLY — a
  // null label reaches the template literals below as it always did — rather than
  // coercing it to "" and inventing a caption with no subject.
  const served = leaderLabel(leader);
  const label = served === null ? served : withoutBoardNamePrefix(served, marketName);
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
