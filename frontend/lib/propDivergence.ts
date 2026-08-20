/**
 * THE DIVERGENCE rail — the pregame mark vs where a prop is now.
 *
 * UX-P098 (UX-AMBITION-1, slice 1). Transcribed from
 * `.claude/handoff/strategy_divergence_rail_spec.md` plus Alex's three ruled
 * verdicts, which arrived through Fable and are NOT re-litigated here:
 *
 *   V1  the pregame page LEADS with five live questions, not the whole prop
 *       set; the full set sits behind a single expand.
 *   V2  every selected row renders a travelled bar; a row that cleared the
 *       measured surprise threshold ADDITIONALLY renders a sentence. The
 *       sentence is an escalation, never an alternative rendering.
 *   V3  a prop that vanished for want of trading may vanish silently; a prop
 *       that vanished for any OTHER taxonomy reason must surface — and a
 *       reason that reads UNKNOWN renders as unknown, never as silence.
 *
 * ZERO new backend fields. Verified on production 2026-08-18: `pregame_mark`
 * ships on the `player_props[]` rows the endpoint already serves.
 */

import { parsePlayerName } from "./playerPropsGrouping";
import type { PlayerPropRow } from "./playerPropsGrouping";
import type { PropGrade } from "./propGrade";
import { readOverSideResolution } from "./propResolution";

/**
 * The surprise threshold — MEASURED, not tuned.
 *
 * Travel distribution over 143 production props carrying both marks
 * (`15199882` scheduled + `14788546` completed, captured 2026-08-18):
 * p50 0.5 pts · p75 11.7 · **p90 21.0** · p95 27.7 · max 40.0.
 *
 * The distribution is strongly BIMODAL — the median prop does not move at all,
 * and the ones that move, move far. That is what makes travel a real signal
 * here rather than noise being dressed up.
 *
 * 0.20 sits at p90 = 11% of props (16/143), so a typical five-row rail carries
 * one or two sentences and three or four bare bars, which is the shape V2
 * describes. At 0.15 a majority of the rail becomes prose and the escalation
 * stops meaning anything.
 *
 * If a future population flattens that bimodality that is A NEW MEASUREMENT TO
 * RECORD, not a knob to turn. Re-derive per sport when n allows — the constant
 * is a measurement's current value, not a preference.
 */
export const PROP_SURPRISE_TRAVEL = 0.2;

/**
 * The OFF-SCRIPT line — where the detail view puts the fold.
 *
 * Distinct from `PROP_SURPRISE_TRAVEL`, and for a different job: 0.20 decides
 * who gets a SENTENCE, 0.10 decides who is above the fold at all. The detail
 * view shows every eligible question, so it needs a second, lower cut to keep
 * "moved" from meaning "exists".
 *
 * MEASURED, and the measurement reproduces the ratified mock's own count rather
 * than quoting it. Mock 2 (`docs/mockups/event-props-script-divergence-mock.html`)
 * is drawn from event **14788546**, Cardinals @ Reds, and states "34 of 97 rungs
 * moved 10+ points from their own pregame mark". Running the shipped parser over
 * that same production payload (now `__tests__/fixtures/eventPlayerProps.14788546.json`)
 * yields 100 distinct questions of which **exactly 34** travel >= 0.10.
 *
 * Travel distribution on that payload: p50 0.023 · p75 0.137 · **p90 0.210** ·
 * p95 0.280 · max 0.400 — which also re-derives `PROP_SURPRISE_TRAVEL = 0.20`
 * at p90 on a payload independent of the one slice 1 measured it on.
 *
 * Same discipline as its neighbour: a future population that moves this is a new
 * measurement to record, not a knob to turn.
 */
export const PROP_OFF_SCRIPT_TRAVEL = 0.1;

/**
 * POST-GAME the ranking key is SURPRISE, not travel — #2011, ruled by Fable
 * (cycle 102 (c)): "the post-game rail must rank by |resolution − pregame
 * mark|, not travel."
 *
 * Travel is a distance between two PRICES. Once a question has resolved, the
 * last traded price is not where it ended — the outcome is. A prop marked 92.5%
 * that resolved NO has travelled 0.0 points and surprised by 92.5, and on
 * production event `15199902` it ranks **18th of 39** by travel while a
 * 9.5-point non-event (Ohtani 2+ home runs) ranks 2nd. Three such rows on that
 * one page: Braxton Fulford 1+ (92.5 pts, travel-rank 18), Connor Norby 1+
 * (92.0, rank 19), Willi Castro 2+ (83.0, rank 30).
 *
 * ── BOTH CONSTANTS MEASURED ON THE SETTLED POPULATION, NOT COPIED ──
 *
 * Surprise over 57 typed rows across 12 settled production events
 * (2026-08-19): p25 7.0 · p50 13.0 · p75 20.0 · **p90 83.0** · max 93.0. Even
 * more strongly bimodal than travel, and with an EMPTY PLATEAU: the same six
 * rows clear 50, 60, 70 and 80 points. So any cut inside [0.50, 0.80] selects
 * an identical set, and the constant does not balance on the plateau's width.
 *
 * `PROP_SURPRISE_RESOLUTION = 0.50` takes the plateau's LOWER edge, where the
 * number also means something without a percentile: a surprise of half or more
 * is a question whose pregame mark favoured **the other outcome**. 6/57 =
 * 10.5% of rows, which is the same escalation rate `PROP_SURPRISE_TRAVEL`
 * produces in-game (11%) — V2's shape is preserved across the whistle rather
 * than re-tuned.
 */
export const PROP_SURPRISE_RESOLUTION = 0.5;

/**
 * The post-game fold — the settled twin of `PROP_OFF_SCRIPT_TRAVEL`, and for
 * the same job: keeping "off script" from collapsing into "exists".
 *
 * p75 of the settled distribution above = 0.20, selecting 15/57 = 26.3% —
 * alongside the travel fold's 34/100 = 34% on the mock's own game. A 0.10 cut
 * was measured and rejected: it admits 59.6% of rows, because post-game the
 * floor on surprise is set by the mark itself (a prop marked 8% that resolved
 * NO surprises by 8 points), and a heavy favourite doing exactly what it was
 * supposed to do is the script being FOLLOWED, not left.
 *
 * Same discipline as its three neighbours: a future population that moves this
 * is a new measurement to record, not a knob to turn.
 */
export const PROP_OFF_SCRIPT_RESOLUTION = 0.2;

/**
 * ── PREGAME: THE SCRIPT ──────────────────────────────────────────────────────
 *
 * UX-P106 item 3. Before first pitch there is no travel and no outcome, so both
 * existing ranking keys are zero. Ranked by travel, a pregame rail is five
 * arbitrary flat bars under a header reading "What's moving" — the header
 * promising a story the data cannot carry, which is #2011's defect wearing the
 * other clock.
 *
 * The pregame key is CONVICTION: `|pregameMark − 0.5|`. How far from a coin
 * flip the market is willing to go. That is what THE SCRIPT *is* — the set of
 * claims tonight's market is actually making — and it is what THE DIVERGENCE
 * later diverges FROM.
 *
 * ── THE MEASUREMENT ──────────────────────────────────────────────────────────
 *
 * 183 eligible questions across FOUR production payloads (`15199886`,
 * `14788546`, `15199902`, `15194472`), run through the shipped candidate
 * builder rather than re-parsed: p50 0.272 · p75 0.380 · **p90 0.430** ·
 * p95 0.440.
 *
 * `PROP_SCRIPT_CONVICTION = 0.430` takes p90, selecting 11.5% — the same
 * escalation rate V2 produces in-game (11%) and post-game (10.5%). One rule,
 * three states, three measured lines; the SHAPE is preserved across the whistle
 * rather than re-tuned, which is the property #2011 established.
 *
 * It also means something without a percentile: conviction 0.430 is a market
 * priced at 93% or 7% — a claim the market is roughly thirteen-to-one on.
 *
 * ── ITS JOB IS TO NORMALISE, NOT TO SELECT ───────────────────────────────────
 *
 * Nothing is gated on this constant directly. Pregame is the one state with TWO
 * live signals, and `scriptSalience` divides each by its own p90 so they compete
 * on one scale; this is conviction's half of that divisor. A raw cut here fired
 * on 5 of 5 rows of a favourite-heavy card while sitting at 11.5% pooled — the
 * pooled rate was right and the per-card rate was not.
 *
 * ── AND IT IS COHERENT WITH THE OTHER HALF, WHICH IS THE POINT ───────────────
 *
 * On `15199902` the three biggest post-game surprises were marked 93.0%, 92.5%
 * and 92.0% — conviction 0.430 / 0.425 / 0.420, straddling this very line. The
 * rows THE SCRIPT would have led with pregame are the rows THE DIVERGENCE
 * ranked 1st, 2nd and 3rd afterwards. That is a coherence claim between the two
 * halves and it is checked in the suite; it is NOT a claim that conviction
 * predicts surprise, which n=41 cannot support (2 of 6 high-conviction rows
 * surprised, against 2 of 35 below the line).
 *
 * Same discipline as its three neighbours: a future population that moves this
 * is a new measurement to record, not a knob to turn.
 */
export const PROP_SCRIPT_CONVICTION = 0.43;

/**
 * The pregame fold — the third sibling of `PROP_OFF_SCRIPT_TRAVEL` and
 * `PROP_OFF_SCRIPT_RESOLUTION`, keeping "the script says something" from
 * collapsing into "the question exists".
 *
 * ── IT IS A SALIENCE RATIO, NOT A PROBABILITY, AND THAT IS THE POINT ─────────
 *
 * Pregame is the one state with TWO live signals: how far the market is from a
 * coin flip (conviction) and how far it has moved since it opened (travel).
 * `scriptSalience` puts them on one scale by dividing each by its OWN measured
 * p90, so 1.0 means "at the p90 of its own distribution" for either — a 27-point
 * pregame line move and a 92.5% favourite are then comparable, which they are
 * not in raw units.
 *
 * MEASURED on the same 183 questions: salience p50 0.767 · **p75 0.936** ·
 * p90 1.047. `0.94` selects **25.1%**, which lands beside the resolution fold's
 * 26.3% and inside the travel fold's 34% — the three folds agree on how much of
 * a page sits above the line, having been measured independently on three
 * different distributions.
 *
 * A first draft used a bare conviction cut at p75 = 0.38. It selected 29%
 * pooled but **20 of 40** on the Phillies payload, because that card is
 * favourite-heavy — a fold that varies from 26% to 50% by card is not a fold.
 * Salience is stabler precisely because a favourite-heavy card is also a
 * quiet one, and the two terms trade off.
 */
export const PROP_SCRIPT_FOLD = 0.94;

/**
 * ── STRUCTURAL RUNGS: THE ONE LINE THAT REMOVES RATHER THAN ESCALATES ────────
 *
 * UX-P107. Alex ruled this off the UX-P106 capture — the screenshot won the
 * call, not the suite: four of the five rows THE SCRIPT led with on the real
 * Phillies card were "Kyle Stowers: 5+ hits + runs + rbis — market says NO,
 * 95%". That is not a view the market is expressing. It is arithmetic. A
 * ladder that already prices 3+ at 10% cannot price 5+ anywhere but the floor,
 * so the 5+ rung's certainty is a fact about **its own position in its own
 * ladder**, and a rail that leads with it is quoting a subtraction.
 *
 * THE RULING: near-certain rungs whose certainty is explained by ladder
 * position are filtered out of the five-row script rail. Conviction ranking is
 * unchanged among what remains, and every suppressed rung stays reachable
 * through the same "See all N questions" expand — this is rail capacity, in the
 * exact sense `notSelected` already means it, never a taxonomy loss.
 *
 * ── THE BAR ALEX SET, AND WHY THE PREDICATE IS SHAPED THE WAY IT IS ──────────
 *
 * "'Structural' needs a real predicate — rung position within its own ladder
 * family plus threshold — never a bare probability cutoff; a genuine standalone
 * 94% market view must survive the filter."
 *
 * So the certainty line NEVER acts alone. A row is structural only when it is
 * BOTH near-certain AND sitting at the end of its own ladder that its certainty
 * points towards:
 *
 *   near-certain NO  + a LOWER rung exists  -> structural (the ladder's ceiling)
 *   near-certain YES + a HIGHER rung exists -> structural (the ladder's floor)
 *   family of one                           -> NEVER structural
 *
 * ** THE POPULATION HANDED US THE PROOF, ON ONE CARD, AT ONE PRICE. ** Event
 * `15199902` carries three questions reading "3+ hits", all priced at exactly
 * **6.0%**:
 *
 *   Jordan Beck: 3+ hits       family [3]      -> SURVIVES   (a standalone market)
 *   Kyle Tucker: 3+ hits       family [2,3]    -> suppressed (2+ is priced 15%)
 *   Braxton Fulford: 3+ hits   family [2,3]    -> suppressed (2+ is priced 11%)
 *
 * Same card, same stat, same threshold, same price, opposite dispositions. A
 * bare probability cutoff cannot tell them apart and would delete all three;
 * this predicate keeps the one where the market actually chose to say something.
 * That pair is asserted in the suite, and it is the test that reds if anyone
 * ever "simplifies" this back into a price comparison.
 *
 * ── THE CERTAINTY LINE IS MEASURED, ON THE DISTRIBUTION ALREADY RECORDED ─────
 *
 * Same 183 questions, same four production payloads, same shipped candidate
 * builder as `PROP_SCRIPT_CONVICTION`: p50 0.2725 · p75 0.380 · **p90 0.430** ·
 * **p95 0.440** · max 0.450.
 *
 * `PROP_SCRIPT_CONVICTION` takes p90. This takes **p95 of the same
 * distribution**, and the one-step gap is the whole argument:
 *
 *   ** THE THREE EXISTING LINES ESCALATE. THIS ONE REMOVES. ** A wrongly
 *   escalated row is a loud row on a page the user is already reading. A
 *   wrongly suppressed row is a market that is not on the rail at all. The
 *   costs are not symmetric, so the percentiles are not either — suppression
 *   sits one step TIGHTER than escalation on the very same distribution, rather
 *   than being tuned to a number that happened to clear Alex's four rows.
 *
 * It also means something without a percentile. Conviction 0.44 is a market
 * priced at 94% or 6%, and the measured floor of this whole eligible population
 * is 5.0% — no provider on it quotes below that. So the band is the bottom two
 * quoted points a market can occupy: the cheapest thing the book is able to say.
 *
 * Selects 13 of 183 (7.1%) as structural, sparing 1 lone near-certain row
 * (Beck). Every one of the 13 has a lower rung; **the upward arm has ZERO
 * specimens in this population** — the highest ladder rung carrying a higher
 * sibling is 92.5%, below the line. It is implemented because the asymmetry
 * would be arbitrary, not because it was observed, and it is exercised
 * synthetically and labelled as such. Same discipline as its four neighbours: a
 * future population that moves this is a new measurement to record.
 */
export const PROP_STRUCTURAL_CERTAINTY = 0.44;

/** V1: five, not "about five". */
export const RAIL_MAX_ROWS = 5;

/**
 * At most two rows per player. Without it, one player having a big night owns
 * the whole rail — and the rail's job is to describe the GAME. "Hits", "Home
 * Runs" and "Hits + Runs + RBI" all move together for a player who just
 * homered, so the collision is a matter of time even when today's payload
 * happens to rank five distinct players.
 */
export const RAIL_MAX_PER_PLAYER = 2;

/**
 * V3's disappearance taxonomy. Only the first two are benign; the rest are
 * Alex's "that sounds very bad" cases and must reach the screen.
 *
 * `unknown` is deliberately a MEMBER of this enum rather than a fallback to
 * `no_real_price`. Claiming "it never traded" when we cannot tell "it never
 * traded" from "we mis-classified it" is exactly the invention gotcha #53
 * forbids — an empty is not an absence.
 */
export type PropDropReason =
  /** 1 — never traded / no real price. Benign: hide silently. */
  | "no_real_price"
  /** 2 — outside the interesting band. Benign, and applied UPSTREAM (step 9). */
  | "outside_band"
  /** 3 — mis-classified into another section. The #1976 §5 class. NOT benign. */
  | "misclassified"
  /** 4 — linked to the wrong game (#1976 §3 / #1970). NOT benign. */
  | "wrong_game"
  /** 5 — settled but never graded (#1976 §2). NOT benign. */
  | "ungraded"
  /** Unreadable for a reason we cannot name. Renders AS unknown. NOT benign. */
  | "unknown";

const BENIGN_REASONS: ReadonlySet<PropDropReason> = new Set<PropDropReason>([
  "no_real_price",
  "outside_band",
]);

export function isBenignDrop(reason: PropDropReason): boolean {
  return BENIGN_REASONS.has(reason);
}

export interface DivergenceRow {
  /** Stable identity for React keys and tests: market name + threshold. */
  key: string;
  /** The QUESTION, e.g. "Alec Bohm: 1+ home runs". Never the provider string. */
  label: string;
  player: string;
  stat: string;
  threshold: number;
  /** Where the market opened the question, 0..1. */
  pregameMark: number;
  /** Where it is now, 0..1. */
  current: number;
  /** |current - pregameMark|, 0..1. */
  travel: number;
  /** Which way it travelled. `flat` when travel rounds to nothing. */
  direction: "over" | "under" | "flat";
  /**
   * In-game: travel at or above PROP_SURPRISE_TRAVEL. Post-game: surprise at or
   * above PROP_SURPRISE_RESOLUTION. One flag, two measured lines — the surface
   * asks "does this row escalate to prose", and the answer depends on whether
   * the question is still open.
   */
  surprising: boolean;
  /** Present only when `surprising`. V2: the sentence is an escalation. */
  sentence: string | null;
  /** Settled games freeze: the bar shows the journey, it stops implying motion. */
  settled: boolean;
  /**
   * PREGAME ONLY (UX-P106). The event has not started, so there is no travel to
   * rank by and no outcome to be surprised by — the rail shows THE SCRIPT.
   */
  pregame: boolean;
  /**
   * How far from a coin flip the market is willing to go, `|pregameMark − 0.5|`,
   * and the PREGAME RANKING KEY.
   *
   * Present in every state (it is a fact about the mark, not about the clock) so
   * the settled surface can be checked for coherence against the pregame one.
   */
  conviction: number;
  /**
   * WHAT THE SCRIPT ACTUALLY SAYS — typed off the OVER-SIDE mark, and never off
   * the row's own `outcome_name`.
   *
   * This is ruling (a) carried forward, and on this population it is not a
   * corner case: **154 of 183 pregame marks (84.2%) sit BELOW 0.5**, so the
   * script is overwhelmingly a set of confident NEGATIVE predictions. A surface
   * that renders the mark as "how likely" without naming the direction reads as
   * "nothing is going to happen tonight" on 84% of its rows, and a surface that
   * types on the row's outcome inverts every Polymarket "Under" leg — the exact
   * mechanism that made #2011's prescribed rule wrong on 9 of 57 rows.
   *
   * `toss_up` is its own value rather than a default, because a market at 50%
   * is making no claim and must not be rendered as a weak one.
   */
  scriptSide: "will" | "wont" | "toss_up";
  /**
   * A near-certain rung whose certainty is explained by its position in its own
   * ladder — see `PROP_STRUCTURAL_CERTAINTY`. Alex's ruling filters these out of
   * the pregame rail; they remain in `eligible` and in the detail view.
   *
   * Computed in EVERY state, like `conviction`, because it is a fact about the
   * ladder rather than about the clock — and because a flag only computed where
   * it is consumed cannot be checked anywhere else. Only the pregame rail acts
   * on it.
   *
   * Derived from the same basis `conviction` is derived from (pregame `current`,
   * otherwise `pregameMark`) rather than from `scriptSide`, which is always typed
   * off `current`. Post-game those two disagree, and a flag that silently means
   * a different thing in a state nobody reads it in is the shape of the next bug.
   */
  structural: boolean;
  /**
   * POST-GAME ONLY (#2011). Where the question actually landed, on the same
   * over axis `current` and `pregameMark` are quoted on: 1 the over resolved
   * YES, 0 it resolved NO, `null` nothing may be stated.
   *
   * Deliberately null on a live row even if a leg happens to carry a `hit`:
   * the in-game treatment is the red/green travelled bar, explicitly approved,
   * and only there.
   */
  resolution: 0 | 1 | null;
  /**
   * POST-GAME ONLY. `|resolution - pregameMark|`, and the settled RANKING KEY.
   * `null` when the row carries no readable verdict — never a fabricated 0,
   * which would file the ungraded rows in among the genuinely unsurprising
   * ones (#2011's named residual).
   */
  surprise: number | null;
  /**
   * POST-GAME ONLY. The settled state from `readPropGrade`, so the surface can
   * say `SETTLED_NO_GRADE_LABEL` for a WITHHOLD rather than inventing silence.
   */
  grade: PropGrade | null;
}

export interface DivergenceDrop {
  reason: PropDropReason;
  benign: boolean;
  count: number;
  /** Up to a few examples, for the surfaced explanation. */
  examples: string[];
}

export interface DivergenceResult {
  rows: DivergenceRow[];
  /** Taxonomy-classified losses. Benign ones may be hidden; others may not. */
  dropped: DivergenceDrop[];
  /** Total non-benign losses — the number V3 says must never be swallowed. */
  nonBenignCount: number;
  /** UX-P106: the event has not started — the rail is THE SCRIPT. */
  pregame: boolean;
  /**
   * Eligible props that simply ranked below the top five. NOT a taxonomy loss:
   * these are reachable through the expand, so they are not "lost markets".
   * Kept separate precisely so rail capacity can never be mistaken for a defect.
   */
  notSelected: number;
  /** Total eligible rows before the cap — the denominator for "5 of N". */
  eligible: number;
  /**
   * POST-GAME ONLY. Settled questions with no readable verdict. They are
   * eligible — they are real questions and the expand still lists them — but
   * the rail will not spend one of its five slots saying nothing.
   */
  ungraded: number;
  /**
   * PREGAME ONLY (UX-P107). Near-certain ladder rungs the rail set aside
   * because their certainty is arithmetic — see `PROP_STRUCTURAL_CERTAINTY`.
   *
   * Counted over EVERY candidate, not just the ones the selection loop happened
   * to walk past before filling five slots. "How many did the rule remove" is a
   * fact about the card; a number that also depended on where the loop stopped
   * would be neither, and would move when an unrelated row changed rank.
   *
   * They are inside `eligible` and inside `notSelected`, exactly like a row that
   * merely ranked sixth — rail capacity, never a taxonomy loss.
   */
  structuralSuppressed: number;
  /**
   * Whether the game is over. On the result rather than inferred from the rows,
   * because an EMPTY rail still has to know — `rows.some(r => r.settled)` reads
   * "not settled" for a settled page with nothing to show, which is how the
   * heading came to say "What's moving" over a finished game.
   */
  settled: boolean;
  /**
   * Why there are no rows, when there are none. Same three-way vocabulary
   * `groupPlayerProps` already uses, extended rather than reinvented.
   *
   * `ungraded` is the fourth member, added by #2011: a settled game every one
   * of whose questions went ungraded is neither `clean` (nothing was wrong with
   * the data we were shown) nor `unreadable` (no guard caught anything) — it is
   * a page with real questions and no published outcomes, and saying so is the
   * honest-empty ruling 027 asks for.
   *
   * `structural` is the fifth, added by UX-P107, and it is `ungraded`'s pregame
   * twin: a card whose every high-conviction question turned out to be a ladder
   * rung. The rule is applied WITHOUT an escape hatch — a filter that quietly
   * un-applies itself when it would empty a surface is two behaviours with one
   * name, and the second one only ever runs where nobody is looking. So the
   * rail empties, and the page says which rule emptied it and where the
   * questions went (ruling 027).
   */
  emptyReason: "none" | "clean" | "unreadable" | "ungraded" | "structural" | null;
}

export interface DivergenceInput {
  playerProps?: readonly PlayerPropRow[] | null;
  /** Event status; a settled game freezes the rail. */
  status?: string | null;
}

const SETTLED_STATUSES: ReadonlySet<string> = new Set([
  "completed",
  "closed",
  "settled",
  "final",
  "resolved",
]);

export function isSettledStatus(status?: string | null): boolean {
  return SETTLED_STATUSES.has((status || "").toLowerCase());
}

const LIVE_STATUSES: ReadonlySet<string> = new Set([
  "live",
  "in_progress",
  "inprogress",
  "in progress",
  "halftime",
  "delayed",
  "suspended",
]);

/**
 * The event has not started.
 *
 * NOT `!settled` — that would put a live game on THE SCRIPT and hand it a
 * ranking key of zero movement while the movement is the entire story. And NOT
 * an allowlist of `scheduled`, either: the status vocabulary on this payload is
 * provider-shaped and an unrecognised value must not silently become a pregame
 * page for a game already in the third inning.
 *
 * So it is a triple: settled → landed, live → moving, anything else → script.
 * An UNKNOWN status therefore lands on THE SCRIPT, which is the safe end — the
 * script states pregame marks, which are true at every point in the game; the
 * other two states make claims about a clock we would be guessing at.
 */
export function isPregameStatus(status?: string | null): boolean {
  const s = (status || "").toLowerCase();
  return !SETTLED_STATUSES.has(s) && !LIVE_STATUSES.has(s);
}

function isFiniteNumber(v: unknown): v is number {
  return typeof v === "number" && Number.isFinite(v);
}

/**
 * Both thresholds are written as inclusive lines in whole points — the mock
 * says "moved 10+ points", the spec says "rows at or above 20 pts". Travel is
 * a float subtraction of two provider prices, so the exact-boundary case does
 * NOT survive a naive `>=`:
 *
 *     0.6 - 0.5 === 0.09999999999999998    (< 0.10)
 *     0.7 - 0.5 === 0.19999999999999996    (< 0.20)
 *
 * A prop that moved exactly twenty points therefore read as NOT surprising,
 * silently, on the shipped slice-1 rail. Found in UX-P101 by a `>=` -> `>`
 * mutation that survived every payload-derived assertion, because the captured
 * fixtures happen to contain no row sitting exactly on a line.
 *
 * The epsilon is a representation tolerance, not a widened threshold: it admits
 * the boundary and nothing else. A genuine near-miss (0.195) still misses.
 */
const TRAVEL_EPSILON = 1e-9;

export function travelAtOrAbove(travel: number, threshold: number): boolean {
  return travel >= threshold - TRAVEL_EPSILON;
}

/**
 * Both providers' lines read as "N or more", so both render as `N+`.
 *
 *   Polymarket  "... O/U 3.5" -> Over means at least 4        -> "4+"
 *   Kalshi      threshold 4.0 -> the OUTCOME says "Trea Turner: 4+", i.e. the
 *                                integer is already inclusive -> "4+"
 *
 * The Kalshi half is read off the real payload rather than inferred: on
 * `15199886`, threshold `4.0` ships beside outcome text `"Trea Turner: 4+"` and
 * threshold `1.0` beside `"Kyle Schwarber: 1+"`. Rendering those as "over 4"
 * would be a different (and wrong) question — off by one against the provider's
 * own words.
 */
function thresholdPhrase(threshold: number): string {
  return `${Math.ceil(threshold)}+`;
}

/** "Janson Junk" -> "Junk's". Deterministic; no possessive edge-case cleverness
 *  beyond the standard trailing-s rule. */
function possessive(player: string): string {
  const parts = player.trim().split(/\s+/);
  const last = parts[parts.length - 1] || player;
  return last.endsWith("s") ? `${last}'` : `${last}'s`;
}

function pct(p: number): string {
  return `${Math.round(p * 100)}%`;
}

/**
 * The sentence, for surprising rows only. Arithmetic over two numbers already
 * on the row — deterministic, reproducible, and renderable offline from the
 * payload alone. Never `hook_description`, never an LLM.
 */
export function divergenceSentence(
  player: string,
  label: string,
  pregameMark: number,
  current: number,
  settled: boolean,
  resolution?: 0 | 1 | null,
): string {
  const question = label.includes(": ") ? label.split(": ").slice(1).join(": ") : label;

  // NO PREGAME BRANCH, DELIBERATELY. A draft of UX-P106 added one — "The market
  // says Stowers' 5+ hits+runs+rbis won't happen — 95%" — and the rendered
  // capture showed it restating the bar directly beneath it, four times on a
  // five-row rail. The direction the script states lives on the ROW (`scriptSide`)
  // and is rendered by `ScriptMark` and its aria-label; a sentence that repeats
  // its own bar is not V2's escalation.

  // #2011: post-game the sentence must state the OUTCOME, not the last traded
  // price. "finished at 58%" is a price wearing the grammar of a result, and it
  // is the sentence half of the same defect as the bar that ends there.
  if (settled && resolution != null) {
    // Same vocabulary as the badge beside it and the prop card below it —
    // `hit` / `missed` is the verb form of PROP_HIT_LABEL / PROP_MISS_LABEL,
    // not a third word (see `resolutionLabel`, and #1650).
    const verdict = resolution === 1 ? "and it hit." : "and it missed.";
    return `${possessive(player)} ${question} was marked ${pct(pregameMark)} — ${verdict}`;
  }

  const tail = settled
    ? `finished at ${pct(current)}.`
    : `it's ${pct(current)} now.`;
  return `${possessive(player)} ${question} opened at ${pct(pregameMark)} — ${tail}`;
}

/**
 * Select the rail's rows and account for everything that did not make it.
 *
 * Ranked by travel over the props eligible to be shown at all. Eligibility is
 * "has both a pregame mark and a current price"; the interesting band
 * (0.05..0.95) is NOT re-implemented here — the rail inherits whatever the
 * endpoint served, per spec.
 */
export function selectDivergenceRows(input: DivergenceInput): DivergenceResult {
  const built = buildCandidates(input);
  const settled = built.settled;
  const pregame = built.pregame;

  const empty = (emptyReason: DivergenceResult["emptyReason"]): DivergenceResult => ({
    rows: [],
    dropped: [],
    nonBenignCount: 0,
    notSelected: 0,
    eligible: 0,
    ungraded: 0,
    structuralSuppressed: 0,
    settled,
    pregame,
    emptyReason,
  });

  if (built.noRows) return empty("none");

  const { candidates, dropped, nonBenignCount } = built;

  if (candidates.length === 0) {
    // Rows existed and none survived. Which empty it is depends on whether a
    // guard caught something — `unreadable` when it did, `clean` when the data
    // was simply benign-empty.
    return {
      ...empty(nonBenignCount > 0 ? "unreadable" : "clean"),
      dropped,
      nonBenignCount,
    };
  }

  const ungraded = settled ? candidates.filter((r) => r.surprise == null).length : 0;
  const structuralSuppressed = pregame
    ? candidates.filter((r) => r.structural).length
    : 0;

  const perPlayer = new Map<string, number>();
  const selected: DivergenceRow[] = [];
  for (const row of candidates) {
    if (selected.length >= RAIL_MAX_ROWS) break;
    // #2011: post-game the rail names the biggest surprises. A question with no
    // published verdict has no surprise, and spending one of five slots on
    // "Resolved · grading unavailable" is the rail asserting it has a story
    // when it does not. The expand still lists every one of them.
    //
    // `break`, not `continue`, ON PURPOSE: `bySurprise` already sorts every
    // ungraded row behind every graded one, so the first one IS the end of the
    // list. A `continue` would be a SECOND expression of that same rule, and
    // the two would then be free to disagree — a mutation that reversed the
    // sort's null-handling passed the whole suite while the filter quietly
    // covered for it. One rule, load-bearing, and now mutation-visible.
    if (settled && row.surprise == null) break;
    // UX-P107, and `continue` rather than `break` ON PURPOSE, which is the
    // opposite call from the line above it. `bySurprise` sorts every ungraded
    // row to the end, so the first one IS the end of the list; structural rungs
    // are scattered through the conviction order by construction — they are the
    // MOST convinced rows on the card, so they cluster at the TOP — and a
    // `break` here would truncate the rail at its first ladder rung and throw
    // away everything the rule was supposed to promote.
    //
    // Placed BEFORE the per-player cap so a suppressed rung does not spend one
    // of its player's two slots on the way out. Brady Singer alone carries SIX
    // structural rungs on `14788546`; charged against the cap, he would silence
    // his own 2+ strikeouts — the one rung in that ladder the market has a view
    // about — and the rule would have made the page worse in his name.
    if (pregame && row.structural) continue;
    const n = perPlayer.get(row.player) ?? 0;
    if (n >= RAIL_MAX_PER_PLAYER) continue;
    perPlayer.set(row.player, n + 1);
    selected.push(withSentence(row, settled));
  }

  if (selected.length === 0) {
    // A settled page with real questions and not one published outcome, or a
    // pregame page whose every question turned out to be a ladder rung. Neither
    // is `clean` and neither is `unreadable`: honest-empty needs its own word
    // (ruling 027), and each of these has one.
    return {
      ...empty(
        settled && ungraded > 0
          ? "ungraded"
          : pregame && structuralSuppressed > 0
            ? "structural"
            : "clean",
      ),
      dropped,
      nonBenignCount,
      notSelected: candidates.length,
      eligible: candidates.length,
      ungraded,
      structuralSuppressed,
      settled,
      pregame,
    };
  }

  return {
    rows: selected,
    dropped,
    nonBenignCount,
    notSelected: candidates.length - selected.length,
    eligible: candidates.length,
    ungraded,
    structuralSuppressed,
    settled,
    pregame,
    emptyReason: null,
  };
}

/** V2's escalation, applied identically by all three views. */
function withSentence(row: DivergenceRow, settled: boolean): DivergenceRow {
  if (!row.surprising) return row;
  return {
    ...row,
    sentence: divergenceSentence(
      row.player,
      row.label,
      row.pregameMark,
      row.current,
      settled,
      row.resolution,
    ),
  };
}

interface BuiltCandidates {
  candidates: DivergenceRow[];
  dropped: DivergenceDrop[];
  nonBenignCount: number;
  settled: boolean;
  pregame: boolean;
  /** No input rows at all — distinct from "rows existed, none survived". */
  noRows: boolean;
}

/**
 * THE ONE ADMISSION RULE, shared by the rail and the detail view.
 *
 * Extracted in UX-P101 rather than copied. A second implementation of "which
 * props may be shown" is the #1951 defect exactly — that issue was a THIRD copy
 * of the feed's admission rule, in no parity test, silently carrying a stale
 * arm. The rail and the detail view must disagree about *how many* rows to show
 * and about *nothing else*; the only way to guarantee that is for the predicate
 * to exist once.
 */
function buildCandidates(input: DivergenceInput): BuiltCandidates {
  const rows = input.playerProps ?? [];
  const settled = isSettledStatus(input.status);
  const pregame = isPregameStatus(input.status);

  if (rows.length === 0) {
    return {
      candidates: [],
      dropped: [],
      nonBenignCount: 0,
      settled,
      pregame,
      noRows: true,
    };
  }

  const dropCounts = new Map<PropDropReason, { count: number; examples: string[] }>();
  const noteDrop = (reason: PropDropReason, at: string) => {
    const cur = dropCounts.get(reason) ?? { count: 0, examples: [] };
    cur.count += 1;
    if (cur.examples.length < 3 && at) cur.examples.push(at);
    dropCounts.set(reason, cur);
  };

  // THE DEDUPE KEY MUST BE THE PARSED IDENTITY, NOT THE MARKET NAME.
  //
  // The two providers put the player in different places, and a name-keyed
  // dedupe is wrong for one of them in a way that DELETES DATA:
  //
  //   Polymarket  market "Alec Bohm: Home Runs O/U 0.5"    outcome "Over"/"Under"
  //               -> two legs, ONE question. Must collapse.
  //   Kalshi      market "Philadelphia vs Miami: Hits"     outcome "Edmundo Sosa: 2+"
  //               -> ONE market name covering MANY DISTINCT PLAYERS. Must NOT
  //                  collapse; two players on the same line share market name
  //                  AND threshold and differ only in the outcome.
  //
  // Keying on `market_name|threshold` reads correctly on the Polymarket shape
  // and silently drops players on the Kalshi one. That is #1639 exactly — "17
  // distinct players collapsed into ONE card, titled with the matchup and
  // wearing whichever headshot arrived first" — so this is a re-entry into a
  // known defect, not a hypothetical.
  //
  // Parsing FIRST and keying on `player|stat|threshold` is correct for both:
  // the Over/Under legs parse to the same identity and collapse, while distinct
  // players parse to distinct identities and survive.
  //
  // #2011 ADDS ONE THING TO THIS: the sibling leg is COLLAPSED, not DISCARDED.
  //
  // Both legs of a Polymarket O/U carry a typed `hit`, and they type opposite
  // verdicts about opposite sides of the same line. Keeping whichever arrived
  // first and reading its `hit` as the over-side result is a coin flip on the
  // ingest order — so every leg's verdict is collected here and reconciled by
  // `readOverSideResolution`, which maps them all onto the over axis and
  // withholds if they then disagree.
  const seen = new Set<string>();
  const candidates: DivergenceRow[] = [];
  /** Every leg of a question, in payload order, keyed by parsed identity. */
  const legs = new Map<string, PlayerPropRow[]>();

  for (const row of rows) {
    const marketName = (row.market_name || "").trim();
    const outcomeName = (row.outcome_name || "").trim();
    const threshold = row.threshold;
    const at = marketName || outcomeName || "(unnamed row)";

    if (!marketName || !isFiniteNumber(threshold)) {
      // A prop row with no name or no line cannot be read, and we cannot tell
      // WHY it is shaped that way from here. V3: that renders as unknown.
      noteDrop("unknown", at);
      continue;
    }

    const current = row.over_probability;
    const pregameMark = (row as PlayerPropRow & { pregame_mark?: number | null })
      .pregame_mark;

    if (!isFiniteNumber(current) || !isFiniteNumber(pregameMark)) {
      // No real price on at least one end. This IS reason 1, and it is the one
      // absence Alex is willing to hide.
      noteDrop("no_real_price", at);
      continue;
    }

    const parsed = parsePlayerName(marketName, outcomeName);
    if (!parsed || !parsed.player) {
      // The row is priced and named but does not parse as a player prop — the
      // shape #1976 §5 was made of. Not benign; we do not know it never traded,
      // we know we could not read it.
      noteDrop("misclassified", at);
      continue;
    }

    const key = `${parsed.player}|${parsed.stat}|${threshold}`;
    // The sibling Over/Under leg of the SAME question: it contributes no second
    // row, but it DOES contribute its verdict.
    const bucket = legs.get(key);
    if (bucket) bucket.push(row);
    else legs.set(key, [row]);
    if (seen.has(key)) continue;
    seen.add(key);

    const travel = Math.abs(current - pregameMark);
    candidates.push({
      key,
      label: `${parsed.player}: ${thresholdPhrase(threshold)} ${parsed.stat.toLowerCase()}`,
      player: parsed.player,
      stat: parsed.stat,
      threshold,
      pregameMark,
      current,
      travel,
      direction: travel < 0.005 ? "flat" : current > pregameMark ? "over" : "under",
      surprising: travelAtOrAbove(travel, PROP_SURPRISE_TRAVEL),
      sentence: null,
      settled,
      pregame,
      // ── WHICH NUMBER CONVICTION IS ABOUT, AND A SCREENSHOT SETTLED IT ──
      //
      // Pregame this is `current`, not `pregameMark`, and the first draft had
      // it the other way round. The rendered capture showed the cost on the
      // first row of the real Phillies payload: Schwarber's 1+ home runs
      // OPENED at 27% and is 55% NOW, and the row printed the sentence
      // "opened at 27% — it's 55% now" directly above a bar reading
      // "market says NO, 73%". One row, two answers, and the bar was quoting
      // last week.
      //
      // `pregame_mark` is the OPENING capture. Before first pitch the script as
      // it STANDS is the current price — that is the number Alex's pre-game
      // ritual is asking for — and the opening mark is the movement story,
      // which the sentence already tells. Post-game `current` is the last
      // traded price and worthless (#2011), so there conviction stays on the
      // mark, which is also what the coherence check compares.
      conviction: Math.abs((pregame ? current : pregameMark) - 0.5),
      // Typed off the OVER-side mark. `pregameMark` is already the over-side
      // price (`over_probability`'s pregame twin), so this cannot pick up the
      // leg's own polarity — which is the inversion ruling (a) is about.
      scriptSide: current > 0.5 ? "will" : current < 0.5 ? "wont" : "toss_up",
      // Set in a second pass — a rung cannot be classified until its whole
      // ladder family has been read, and the family is only complete once the
      // payload has been walked.
      structural: false,
      resolution: null,
      surprise: null,
      grade: null,
    });
  }

  // PREGAME: TWO SIGNALS, NOT ONE — AND THE FIRST DRAFT OF THIS GOT IT WRONG.
  //
  // The first attempt replaced travel with conviction outright, on the premise
  // that "nothing has moved before first pitch". THREE RULED SLICE-1 TESTS
  // CAUGHT IT, and they were right: `pregameMark` is the OPENING capture, not
  // the price at first pitch, so pregame travel is the line move since the
  // market opened — real, and on `15199886` as large as 27.7 points. V1/V2
  // ruled that escalation and it is not this queue's to delete.
  //
  // So pregame carries both, because both are true statements about a question
  // that has not started: what the market EXPECTS (conviction) and what it has
  // CHANGED ITS MIND ABOUT (travel). A row clearing either line escalates.
  //
  // ── AND PREGAME KEEPS TRAVEL AS THE *ONLY* ESCALATION, WHICH TOOK THREE GOES ──
  //
  // Conviction ranks the rail and folds the detail view. It does NOT earn a
  // sentence, and the rendered capture is what settled that: escalating on
  // conviction put FIVE SENTENCES ON A FIVE-ROW RAIL, four of them
  // near-identical — "Stowers' 5+ hits+runs+rbis won't happen — 95%",
  // "Sosa's … — 94%", "Sanoja's … — 94%". V2 says the sentence is an
  // ESCALATION; at 5 of 5 it is the default rendering.
  //
  // The threshold was the wrong thing to reach for. A pregame script sentence
  // RESTATES ITS OWN BAR — the bar beneath it already reads "market says NO,
  // 95%" — so there is nothing to escalate TO. The in-game sentence adds the
  // journey (opened X, now Y) and the post-game one adds the outcome; the
  // pregame one adds a second copy.
  //
  // Two tuned thresholds were tried and both were unsafe for the same reason:
  // the 5%-mark rows on that card land at salience 1.0465 against a measured
  // p90 of 1.047, so any cut in that region balances on 0.0005. #2011 called
  // that out by name when it took the LOWER EDGE OF AN EMPTY PLATEAU instead.
  // There is no plateau here, so the answer is not a better number.
  //
  // Travel-only is therefore also unchanged from before this queue, which is
  // why V1/V2's ruled escalation needed no exception written for it.

  // ── STRUCTURAL RUNGS (UX-P107) ───────────────────────────────────────────
  //
  // A SECOND PASS, and it has to be: "is this rung near-certain because of
  // where it sits in its own ladder" is not answerable while the ladder is
  // still being built. The family key is `player|stat`, which is the dedupe key
  // minus its threshold — the same identity, one level up, so the two cannot
  // drift apart into two different ideas of what a ladder is.
  const byFamily = new Map<string, DivergenceRow[]>();
  for (const row of candidates) {
    const familyKey = `${row.player}|${row.stat}`;
    const bucket = byFamily.get(familyKey);
    if (bucket) bucket.push(row);
    else byFamily.set(familyKey, [row]);
  }
  for (const family of byFamily.values()) {
    // ALEX'S BAR, FIRST AND UNCONDITIONALLY: a standalone market is never
    // structural, however certain it is. There is no ladder to explain it, so
    // its price is its own claim and the rail may lead with it.
    //
    // AN EQUIVALENT MUTANT LIVES HERE, and it is recorded rather than hidden:
    // deleting this line changes no behaviour, because the position test below
    // already implies it — a family of one contains only the row itself, and
    // `row.threshold < row.threshold` is false on both arms. A mutation that
    // removed it survived the suite, and that is the correct outcome, not a
    // test hole.
    //
    // It stays for two reasons. It states the clause where a reader looks for
    // it, and it stops being redundant the moment anyone widens the position
    // test — which is exactly when Alex's bar would otherwise be silently lost.
    if (family.length < 2) continue;
    for (const row of family) {
      if (row.conviction < PROP_STRUCTURAL_CERTAINTY - TRAVEL_EPSILON) continue;
      // Same epsilon discipline as `travelAtOrAbove`, and for the same reason:
      // conviction is a float subtraction, `0.94 - 0.5` is 0.44000000000000006
      // and `0.06 - 0.5` is -0.44000000000000006 — either could have landed on
      // the wrong side of a naive comparison on a different pair of prices.
      const basis = pregame ? row.current : row.pregameMark;
      row.structural =
        basis < 0.5
          ? // Near-certain NO at a rung the ladder has already anchored BELOW.
            family.some((sibling) => sibling.threshold < row.threshold)
          : // Near-certain YES at a rung the ladder still asks ABOVE. Zero
            // specimens in the measured population; synthetic coverage only.
            family.some((sibling) => sibling.threshold > row.threshold);
    }
  }

  // POST-GAME: restate every row on the resolution axis. Nothing here runs on a
  // live game — the in-game treatment is the travelled bar, and only there.
  if (settled) {
    for (const row of candidates) {
      const { grade, resolution } = readOverSideResolution(legs.get(row.key) ?? []);
      row.grade = grade;
      row.resolution = resolution;
      row.surprise = resolution == null ? null : Math.abs(resolution - row.pregameMark);
      // The escalation line changes with the question's state; the escalation
      // RULE does not (V2). An ungraded row can never escalate — it has nothing
      // to say, and `surprise` is null rather than a fabricated 0.
      row.surprising =
        row.surprise != null &&
        travelAtOrAbove(row.surprise, PROP_SURPRISE_RESOLUTION);
    }
  }

  const dropped: DivergenceDrop[] = [...dropCounts.entries()].map(
    ([reason, { count, examples }]) => ({
      reason,
      benign: isBenignDrop(reason),
      count,
      examples,
    }),
  );
  const nonBenignCount = dropped
    .filter((d) => !d.benign)
    .reduce((n, d) => n + d.count, 0);

  // Three states, three ranking keys — and each one is the only key its state
  // has any data for. Pregame ranks by conviction (nothing has travelled),
  // in-game by travel (nothing has resolved), post-game by surprise (the last
  // traded price is not where it ended).
  candidates.sort(settled ? bySurprise : pregame ? byConviction : byTravel);

  return { candidates, dropped, nonBenignCount, settled, pregame, noRows: false };
}

/**
 * In-game order: by travel, then by current price so the order is total and
 * stable across renders (a pure tie on travel is common — many props do not
 * move).
 */
function byTravel(a: DivergenceRow, b: DivergenceRow): number {
  return b.travel - a.travel || b.current - a.current || a.key.localeCompare(b.key);
}

/**
 * Pregame order: by conviction, strongest claim first.
 *
 * SYMMETRIC BY CONSTRUCTION, and that is load-bearing rather than tidy. 84.2%
 * of pregame marks on the measured population sit below 0.5, so any ordering
 * that ranked on the mark itself — rather than on its distance from a coin flip
 * — would put every confident "this will NOT happen" at the bottom of the rail
 * and lead with the questions the market has no view on. Willi Castro's 2+ hits
 * was marked 17.0% and produced an 83-point surprise; on a mark-ordered rail it
 * is 39th.
 *
 * The tiebreak runs through `byTravel`, so a pregame page that has already seen
 * some early movement still orders sensibly inside a conviction tie.
 */
function scriptSalience(row: DivergenceRow): number {
  // Each signal normalised by its OWN measured p90, so "at the p90 of its own
  // distribution" is 1.0 for both and the two compete on one scale instead of
  // one silently dominating because its units are bigger.
  return Math.max(
    row.travel / PROP_SURPRISE_TRAVEL,
    row.conviction / PROP_SCRIPT_CONVICTION,
  );
}

function byConviction(a: DivergenceRow, b: DivergenceRow): number {
  return scriptSalience(b) - scriptSalience(a) || byTravel(a, b);
}

/**
 * Post-game order: by surprise from the pregame mark (#2011).
 *
 * Ungraded rows sort AFTER every graded one, and among themselves by travel so
 * the order stays total. They are NOT given a surprise of 0 — that would file
 * a question we could not read in among the questions that went exactly as
 * marked, which is the residual #2011 names by hand.
 */
function bySurprise(a: DivergenceRow, b: DivergenceRow): number {
  const as = a.surprise;
  const bs = b.surprise;
  if (as == null && bs == null) return byTravel(a, b);
  if (as == null) return 1;
  if (bs == null) return -1;
  return bs - as || byTravel(a, b);
}

export interface DivergenceDetailResult {
  /**
   * Questions that left their pregame mark. Above the fold.
   * In-game the fold is travel; post-game it is surprise (#2011).
   */
  offScript: DivergenceRow[];
  /** Questions still on script. Below the fold, same treatment, no sentence. */
  onScript: DivergenceRow[];
  /**
   * POST-GAME ONLY. Settled questions carrying no readable verdict — rendered
   * `SETTLED_NO_GRADE_LABEL`, with no bar and no surprise number.
   *
   * A third group, not a tail of `onScript`, because "still on script" is a
   * CLAIM about how the question landed and these are exactly the questions we
   * cannot make that claim about. Always empty in-game.
   */
  ungraded: DivergenceRow[];
  /** `offScript.length` — the mock's "N off script" badge. */
  offScriptCount: number;
  /** UX-P106: the event has not started — this is THE SCRIPT, not a divergence. */
  pregame: boolean;
  /** Every eligible question. The rail's `eligible` and this agree by construction. */
  eligible: number;
  dropped: DivergenceDrop[];
  nonBenignCount: number;
  emptyReason: DivergenceResult["emptyReason"];
  settled: boolean;
}

/**
 * THE DIVERGENCE detail view — every eligible question, not the top five.
 *
 * This is V1's other half: "the full prop set sits behind a single expand".
 * The rail answers *what should I look at*; this answers *what else is there*,
 * and on the ratified mock's own game that is *95 questions the rail cannot
 * reach* (100 eligible, 5 shown).
 *
 * Same grammar as the rail, deliberately: every row is a travelled bar, and a
 * row clearing `PROP_SURPRISE_TRAVEL` additionally carries a sentence. Two
 * differences, both of which are the point of a detail view:
 *
 *   1. NO `RAIL_MAX_ROWS`. Completeness is the contract.
 *   2. NO `RAIL_MAX_PER_PLAYER`. The rail caps two-per-player because a
 *      fixed-height element whose job is to describe the GAME can be
 *      monopolised by one player having a big night. The detail view's job is
 *      the opposite — capping it would silently withhold a player's other
 *      questions, which is the "why are we losing markets" complaint V3 exists
 *      to answer, re-introduced by the very screen meant to resolve it.
 *
 * The in-game fold is `PROP_OFF_SCRIPT_TRAVEL`; the post-game fold is
 * `PROP_OFF_SCRIPT_RESOLUTION` (#2011). In BOTH states a row below the fold can
 * never be surprising (0.10 < 0.20 and 0.20 < 0.50), so sentences appear above
 * the fold by construction rather than by a second rule — asserted, not assumed.
 *
 * Partitioning post-game by TRAVEL would be the ranking defect wearing a
 * different hat: Braxton Fulford's 1+ was marked 92.5% and did not happen, and
 * travelled 0.0 points doing it, so a travel fold files a 92.5-point surprise
 * under "Still on script".
 */
export function selectDivergenceDetail(input: DivergenceInput): DivergenceDetailResult {
  const built = buildCandidates(input);
  const { candidates, dropped, nonBenignCount, settled, pregame } = built;

  const base = {
    dropped,
    nonBenignCount,
    settled,
    pregame,
  };

  if (built.noRows) {
    return {
      ...base,
      offScript: [],
      onScript: [],
      ungraded: [],
      offScriptCount: 0,
      eligible: 0,
      emptyReason: "none",
    };
  }

  if (candidates.length === 0) {
    return {
      ...base,
      offScript: [],
      onScript: [],
      ungraded: [],
      offScriptCount: 0,
      eligible: 0,
      emptyReason: nonBenignCount > 0 ? "unreadable" : "clean",
    };
  }

  const offScript: DivergenceRow[] = [];
  const onScript: DivergenceRow[] = [];
  const ungraded: DivergenceRow[] = [];
  for (const row of candidates) {
    if (settled && row.surprise == null) {
      ungraded.push(row);
      continue;
    }
    // One partition rule, three measured lines. Each state folds on the only
    // distance it has: pregame on how far the market is from a coin flip,
    // in-game on how far the price has moved, post-game on how far the outcome
    // landed from the mark.
    const distance = settled
      ? (row.surprise as number)
      : pregame
        ? scriptSalience(row)
        : row.travel;
    const fold = settled
      ? PROP_OFF_SCRIPT_RESOLUTION
      : pregame
        ? PROP_SCRIPT_FOLD
        : PROP_OFF_SCRIPT_TRAVEL;
    if (travelAtOrAbove(distance, fold)) offScript.push(withSentence(row, settled));
    else onScript.push(row);
  }

  return {
    ...base,
    offScript,
    onScript,
    ungraded,
    offScriptCount: offScript.length,
    eligible: candidates.length,
    emptyReason: null,
  };
}
