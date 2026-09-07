/**
 * THE MATCH LIST — one list of matches for the whole tournament, by round.
 *
 * UX-P138, Alex's STRUCTURAL RULING 4: "Tournament tab = the MATCH LIST with
 * round pills; Bracket tab = the PLAYOFF GRID." Adopted. The counter-structure
 * argument is in the report; the short version is that the page had TWO match
 * lists — the slate on one tab, the bracket's match cards on the other — and
 * nothing told the reader why they were different lists or which one to trust.
 * They were the same list, split by which pipeline happened to produce it.
 *
 * So this file is the join. A match is a match:
 *
 *   - Qualifying matches come from the SLATE, which is a matchup-and-date feed
 *     with real prices and no draw position.
 *   - Main-draw matches come from the BRACKET, which is a draw-position fold
 *     with title probabilities and no prices.
 *   - A bracket match whose two names also appear in the slate ABSORBS that
 *     slate row: it keeps the draw position and gains the price. The slate row
 *     does not then render a second time, which is the duplicate the old
 *     two-list layout printed on every main-draw day.
 *
 * ALEX'S RULING 1, the standing rule this file exists to make structural:
 * **match odds everywhere a match shows.** A side carries TWO numbers that
 * answer two different questions, and the whole of UX-P137's ruling 2 was
 * about not letting one be mistaken for the other:
 *
 *   - `matchProbability` — to win THIS match. The primary. Big type.
 *   - `titleChance` — to win the whole tournament. A muted secondary chip,
 *     self-labelling, because Alex asked for both on the nothing-played view
 *     and then asked for it "without it being too busy".
 *
 * NEITHER IS EVER COMPUTED FROM THE OTHER, in either direction. They come from
 * different markets — a match market and the champion market — and a page that
 * derived one from the other would be printing a model output in the type
 * reserved for a price.
 *
 * ALEX'S RULING 2: a decided match prints the SCORE with the outcome. The seam
 * is `score` on both source types. **We hold no scores and no results at all
 * today** — see the note on `MatchListEntry.score` — so nothing renders one
 * until a result feed lands. The rig demonstrates it against the synthetic
 * fixture, and the report says plainly that the world has this and our data
 * does not.
 */

import {
  ROUND_LABELS,
  ROUND_NAMES,
  roundIsUnreached,
  type BracketRound,
  type PrematchPair,
  type RoundName,
} from "./bracket";
import { orientLinescore, type SlateLinescore } from "./linescore";
import { isPredictionMarketSource } from "./prematchReading";
import { matchupEventHref, type MatchupEventIds } from "./tournamentEventLink";
import { BOOKS_MARKER } from "./tournamentResults";
import {
  formatSlateProbability,
  matchBroadcast,
  moveDirection,
  slateRowFreshnessLabel,
  slateRowIsPresentedAsLive,
  slateStalenessLabel,
  type Broadcast,
  type PlayerImage,
  type ResolvedBroadcast,
  type SlateMatch,
} from "./slate";

/**
 * Round keys, in the order a tournament plays them.
 *
 * `qualifying` is not a `RoundName` — it is not part of the draw fold and has
 * no bracket position — but it is unquestionably a round of this tournament
 * and it is the ONLY round we hold matches for today. A pill strip that could
 * not name it would have exactly one thing to show and nothing to call it.
 */
export type MatchRoundKey = "qualifying" | RoundName;

export const MATCH_ROUND_ORDER: MatchRoundKey[] = ["qualifying", ...ROUND_NAMES];

export const MATCH_ROUND_LABELS: Record<MatchRoundKey, string> = {
  qualifying: "Qualifying",
  ...ROUND_LABELS,
};

/** Short label for the pill strip — a phone has no room for "Quarter-finals". */
export const MATCH_ROUND_PILL_LABELS: Record<MatchRoundKey, string> = {
  qualifying: "Qual",
  R128: "R128",
  R64: "R64",
  R32: "R32",
  R16: "R16",
  QF: "QF",
  SF: "SF",
  F: "Final",
};

/**
 * Normalise whatever the slate calls a round onto a key we can order.
 *
 * The slate's `round` is a free string from the register ("qualifying" today).
 * An unrecognised value returns `null` and the match is filed under
 * `qualifying` rather than dropped — losing a real match because we could not
 * classify it is strictly worse than filing it one pill to the left, and the
 * pill still names a real round the tournament plays.
 */
export function slateRoundKey(round: string | null | undefined): MatchRoundKey {
  const raw = (round ?? "").trim().toLowerCase();
  if (raw === "") return "qualifying";
  const direct = MATCH_ROUND_ORDER.find((key) => key.toLowerCase() === raw);
  if (direct) return direct;
  if (raw.startsWith("qual")) return "qualifying";
  if (raw.includes("128")) return "R128";
  if (raw.includes("64")) return "R64";
  if (raw.includes("32")) return "R32";
  if (raw.includes("16")) return "R16";
  if (raw.startsWith("quarter")) return "QF";
  if (raw.startsWith("semi")) return "SF";
  if (raw === "final" || raw === "f") return "F";
  return "qualifying";
}

/**
 * Why a side has no name yet. Three different facts, three different sentences
 * (UX-P137, ruling 3 — "nothing renders blank").
 */
export type SidePlaceholder = "none" | "register-hole" | "awaiting-feeder";

export interface MatchListSide {
  /** `null` only for a placeholder side. */
  entityKey: string | null;
  /** The player, or the sentence that says what will fill this slot. */
  displayName: string;
  seed: number | null;
  /** Register-pinned face + flag (ruling 8). `null` on a placeholder side. */
  image: PlayerImage | null;
  /** TO WIN THIS MATCH. The primary number (ruling 1). */
  matchProbability: number | null;
  /** What the market said before it started — the detail view's addition. */
  openingProbability: number | null;
  move: number | null;
  /** TO WIN THE TOURNAMENT. The muted secondary chip (ruling 1). */
  titleChance: number | null;
  isWinner: boolean;
  placeholder: SidePlaceholder;
  /** UX-P157. This side's own book grade — see `lib/liquidity`. */
  liquidity?: string | null;
  liquidity_reasons?: string[] | null;
  /** The side's own last reading, for the reveal's "precisely when". */
  observedAt?: string | null;
}

export interface MatchListEntry {
  id: string;
  /**
   * Does ANY source quote this match (UX-P142)?
   *
   * `false` is the released main draw four days out. Separate from `coherent`,
   * which is two quotes disagreeing: this row has no quotes at all, and the
   * two states get different sentences because they are different facts.
   */
  priced: boolean;
  round: MatchRoundKey;
  roundLabel: string;
  /** ISO string, or `null` for a bracket match with no scheduled date. */
  scheduledDate: string | null;
  /**
   * `scheduledDate` is a DAY, not a time (Q463) — the source has published no
   * order of play for this fixture, so the timestamp is midnight local. The
   * row says TBD and prints no clock; see `SlateMatch.start_is_tbd`.
   */
  startIsTbd: boolean;
  /** ESPN's live state for the fixture, or `null` when it carries none (Q463). */
  liveState: "in_progress" | "upcoming" | null;
  /**
   * ESPN's words for that state — "3rd Set" (#2550). Read ONLY alongside
   * `liveState === "in_progress"`: on an upcoming row the same field carries
   * the full scheduled sentence ("Tue, September 1st at 9:00 PM EDT"), which
   * is why `liveMatchLabel` refuses it rather than the row printing it.
   */
  statusDetail: string | null;
  /**
   * The set-by-set games (live/063, #2746), ORIENTED TO `sides` — or `null`.
   *
   * `null` means there is no line this row may draw, which covers both "ESPN
   * states none" (the ordinary case for a match that has not started) and "the
   * line could not be pointed at these two sides". It never means zero-all.
   */
  linescore: SlateLinescore | null;
  drawLabel: string | null;
  sides: [MatchListSide, MatchListSide];
  decided: boolean;
  /**
   * "6-1, 6-4" (Alex's ruling 2), or `null`.
   *
   * ALWAYS `null` on real data today, and that is a statement about our
   * pipeline rather than about this code. Neither `build_bracket` nor
   * `build_slate` emits a result, let alone a score: the register carries a
   * draw, prices and matchups, and nothing anywhere in the backend has ever
   * held who won a tennis match or by what. The seam is here, typed and
   * rendered, so the day a result feed lands it is an ingest change and not
   * another layout pass — the same posture `matchBroadcast` takes toward
   * per-match rights.
   */
  score: string | null;
  coherent: boolean;
  isLive: boolean;
  /** "3 hours ago", naming the stale side when only one is old. `null` if live. */
  freshnessLabel: string | null;
  broadcast: ResolvedBroadcast | null;
  /**
   * The one sentence this row is allowed, or `null` (Alex's ruling 6).
   * See `matchDetailNote` — most rows get `null`, on purpose.
   */
  detailNote: string | null;
  /**
   * OUR event id, when this match has an `events` row — Alex's item 7,
   * "matches click through to the standard event page".
   *
   * `null` on every US Open match today, and that is a data fact rather than a
   * missing feature: checked 2026-08-26, **zero** of the register's matchups
   * have an `events` row. The US Open qualifying draw was never ingested as
   * events at all, so there is no page to click through to.
   *
   * The seam is here, typed and rendered, because the fix is an ingest change
   * and the link should not be a second layout pass on the day it lands. It is
   * REGISTER-OWNED (`matchup.event_id`), never derived from a name match at
   * render time — a link to the wrong match is worse than no link, and a name
   * join across two systems that disagree about `Auger-Aliassime` is exactly
   * how you get one.
   *
   * The report's honest assessment of the DESTINATION is separate and less
   * comfortable: today's tennis event pages carry surname-only participants, no
   * blended win probability (`win_probability_sources` is null on every tennis
   * event checked), no player images and no props. Linking to one before that
   * is fixed would send a reader from a rich page to a bare one.
   */
  eventId: number | null;
  /**
   * THE REGISTER'S KEY FOR THIS FIXTURE, and the address of its own page
   * (UX-P149) — `/tournaments/{slug}/matches/{matchupKey}`.
   *
   * Separate from `id`, which is the LIST's key and is a draw-slot id on a
   * bracket-sourced row. Only a registered matchup has a page, so a bracket
   * row that never joined a slate row carries `null` here and renders no link
   * rather than one that 404s.
   *
   * This is what `eventId` was reaching for and could not have: it is
   * register-owned, it exists today on every priced fixture, and it needs no
   * `events` row — which is the blocker lane1's Q426 note named as the reason
   * the props had nowhere to go.
   */
  matchupKey: string | null;
  source: "slate" | "bracket";
  /**
   * The word this row's number wears, or `null` when it needs none (#3729).
   *
   * `"books"` where the backend filled a blank row from its own event's
   * sportsbook consensus. Every other row is `null` and prints nothing, which
   * is the state the whole list was in before — including a bracket row, which
   * joins its price from the slate and carries whatever that row carried.
   */
  priceMarker: string | null;
}

/**
 * Does this row's number need to say where it came from?
 *
 * One decision for the card, and it is NOT a new one: `prematchAttribution`
 * makes the same call for the finished list, off the same `isPredictionMarketSource`
 * set and printing the same `BOOKS_MARKER` word. An absent source keeps the
 * meaning it has always had on this payload — the product's own reading, which
 * reads as itself — so a cached payload picks up no caveat it did not earn.
 */
export function priceMarkerFor(source: string | null | undefined): string | null {
  if (source == null || isPredictionMarketSource(source)) return null;
  return BOOKS_MARKER;
}

/** Unordered pair key — the only thing the slate and the draw share. */
function pairKey(a: string, b: string): string {
  return [a, b].sort().join("|");
}

/**
 * WHERE THIS CARD GOES WHEN YOU TAP IT (ux/1002) — `/events/{id}` or `null`.
 *
 * TWO SOURCES, IN THIS ORDER, AND THE ORDER IS THE POINT:
 *
 *  1. `entry.eventId` — the row's own stamp. On a slate row the server already
 *     put the answer here (`build_match_row` reads the same `by_matchup` map),
 *     and a row that carries its own id needs no map to be routable. This also
 *     keeps a caller that passes no `eventIds` behaving exactly as before.
 *  2. `eventIds[entry.matchupKey]` — the payload's PUBLISHED map, which is what
 *     the FINISHED list has read since #2568 and what Alex named as already
 *     holding the answer the live card was missing.
 *
 * ═══ THE SECOND SOURCE IS INERT TODAY, AND SAYING SO IS THE POINT (ux/1008) ═══
 *
 * Round one of this change claimed the map links cards the row's own id cannot.
 * CERT-724 blocked it, and re-measuring showed the claim is false for a
 * structural reason: `build_slate` fills a row's `event_id` FROM this same map
 * when the register does not pin one (`tournament_slate.py:692`), so a slate
 * row's own id is a superset of the map and step 2 can never fire productively.
 * Rendered through the real component on the captured payload, the two rules
 * produce the identical ten hrefs — pinned by `tournamentMatchLink1002`.
 *
 * It is kept, not deleted, for one narrow reason: it makes both lists on the
 * hub resolve through ONE rule instead of two implementations, which is the
 * condition that let them drift apart in the first place. It is a fail-safe,
 * not a feature, and it must not be described as a feature again.
 *
 * The one population it could ever serve — a bracket row whose slate row was
 * dropped — it does NOT serve, because `matchListFromBracket` discards
 * `matchupKey` alongside `eventId` (CERT-724). That is unfixed on purpose:
 * `ingest_espn_draw.py` never writes `draw_slot`, so `build_bracket` returns
 * `[]` and production has no bracket rows. See `lib/tournamentEventLink.ts`
 * for the `espn:` refusal, which is load-bearing on both paths.
 *
 * NEVER a third source. There is no name join here and there must not be one:
 * a reader who taps a card and lands on somebody else's match has been lied to
 * by the surface whose entire posture is that identity is pinned (ruling 048).
 */
export function matchEventHref(
  entry: Pick<MatchListEntry, "eventId" | "matchupKey">,
  eventIds?: MatchupEventIds
): string | null {
  if (
    typeof entry.eventId === "number" &&
    Number.isFinite(entry.eventId) &&
    entry.eventId > 0
  ) {
    return `/events/${entry.eventId}`;
  }
  return matchupEventHref(entry.matchupKey, eventIds);
}

/**
 * The one sentence a match row may carry, or `null` (ALEX'S RULING 6).
 *
 * THE COMPLAINT, verbatim: "probability + movement delta + a sentence
 * restating both is three renderings of one fact." It was exactly that. The
 * row printed `78%`, then `−4`, then "Alcaraz opened at 82%, down to 78%" —
 * and the sentence's only new token was the opening price, buried in a clause
 * that repeated the two numbers already on the row.
 *
 * So the rule is not "shorten the sentence", it is: **a sentence appears only
 * when it adds something the numbers do not.** Three cases survive, and they
 * survive because in each one the numbers on the row cannot say it:
 *
 *   1. An INCOHERENT pair shows no numbers at all (gotcha #23), so the row is
 *      two names and nothing else. Without the sentence it is unreadable.
 *   2. A MOVED price: the row shows the delta but never the origin. "Opened at
 *      82%" is the one fact the chip cannot carry.
 *   3. A DECIDED match with no score: the outcome chip says who won, and the
 *      pre-match number says what was expected, but "the favourite lost" is
 *      only legible if you compare them yourself.
 *
 * Everything else — and it is most rows — returns `null`. A flat match's
 * silence IS the information, and "has not moved" was a sentence saying
 * nothing three times over.
 */
/** The word a live row falls back to when ESPN has no better one (#2550). */
export const LIVE_MATCH_FALLBACK_LABEL = "LIVE";

/**
 * What the badge on a match being played RIGHT NOW says — or `null` when the
 * row is not one (#2550).
 *
 * The shopper found the hub printing "4:05 PM" over a match four hours into
 * its third set. The server had said `in_progress` and "3rd Set" on that row
 * all along; the renderer read neither. A stale start time is worse than no
 * time: a reader who comes back at 4:05 has missed two sets.
 *
 * `statusDetail` IS NOT TRUSTED ON ITS FACE. The same field on an `upcoming`
 * row carries the whole scheduled sentence — "Tue, September 1st at 9:00 PM
 * EDT" — and ESPN flips `state` to `in` on its own cadence, so a row can be
 * live for a beat while its detail is still the schedule. A detail that still
 * reads like one (a clock, an "at", or simply too long to be "3rd Set") is
 * refused and the row says the word instead. Refusing costs the reader "3rd
 * Set"; accepting puts a date inside a red LIVE pill.
 *
 * `decided` short-circuits because a finished match is a result, not a state.
 */
export function liveMatchLabel(entry: {
  liveState: "in_progress" | "upcoming" | null;
  statusDetail: string | null;
  decided: boolean;
}): string | null {
  if (entry.liveState !== "in_progress" || entry.decided) return null;
  const detail = (entry.statusDetail ?? "").trim();
  const readsAsSchedule =
    detail.length > 24 || / at /i.test(detail) || /\d{1,2}:\d{2}/.test(detail);
  return detail === "" || readsAsSchedule ? LIVE_MATCH_FALLBACK_LABEL : detail;
}

/**
 * WHAT AN UNPRICED ROW MAY SAY ABOUT ITSELF (UX-P142, corrected by #2690).
 *
 * ═══ THE SENTENCE WAS RIGHT ABOUT A POPULATION IT NO LONGER DESCRIBES ═══
 *
 * UX-P142 wrote *"Nobody is quoting this match yet. It is in the draw with no
 * probability against it."* against a measured population, and the reasoning
 * held: on ceremony day the released main draw is 96 registered fixtures four
 * days out, and `tournament_slate.py` says why nobody lists them — *"nobody
 * quotes a first round before qualifying finishes"*. Both clauses were true of
 * every row that could reach them. `payload-2026-08-27.json` still proves it:
 * 96 of 113 slate rows unpriced, and **not one of them live or decided.**
 *
 * Then the AUTHORITY builder landed. It reuses the same `priced: false` flag
 * for ESPN-paired rows, and those rows CAN be live — #2690 caught this sentence
 * under a match in its third set, while `/sports` priced it 51/49 and
 * `/events/15300190` drew it a chart with five lead changes. Both clauses had
 * become false at once: the site was quoting the match, and it was not "in the
 * draw", it was being played.
 *
 * ═══ WHY THE FIX IS NOT THE ONE #2690 PROPOSED ═══
 *
 * The issue suggests *"We can't show a price for this match yet"*. That is a
 * ruling-138 violation (`price` is trading vocabulary; the word is
 * PROBABILITY) and `tournamentPlainLanguage` would reject it at the render.
 *
 * Nor may the sentence name a REASON. #2690 measures `priced: false` and
 * `event_id: null` coinciding 2 for 2 and calls linkage "the whole defect" —
 * but that is one afternoon, not the mechanism. `tournament_slate.py:790-809`
 * lists FOUR ways a row arrives unpriced: no link; a link whose sides do not
 * cover both athletes; a link whose outcomes we hold no probability for; and
 * `len(loaded_by_key) != 2`, one side priced and the other not. "We could not
 * tie this match to a market" would be a NEW false sentence on three of them.
 *
 * ═══ SO IT STATES ONLY WHAT THE ROW KNOWS ═══
 *
 * Where the match stands (which the row does know, and which is the fact
 * UX-P142 wanted — the fixture is real), that we have no probability, and an
 * explicit refusal of the inference. The refusal is not invented here: it is
 * the closing clause `prematchAbsenceNote` already ships on this same page.
 * That function and this one describe the same absence, and until now one
 * refused the claim about the world while the other asserted it.
 */
function unpricedDetailNote(entry: {
  decided: boolean;
  liveState: "in_progress" | "upcoming" | null;
}): string {
  const standing = entry.decided
    ? "This match is over"
    : entry.liveState === "in_progress"
      ? "This match is under way"
      : "This match is in the draw";
  // Second clause verbatim from UX-P142; third verbatim from the sibling
  // `prematchAbsenceNote`, so the page refuses this inference in one voice.
  return `${standing} with no probability against it. That is not a statement about whether a venue listed one.`;
}

/**
 * Does this row have TWO NUMBERS THAT DISAGREE — the one state the page is
 * allowed to describe that way (UX-1089)?
 *
 * The card and the count under the list both need this answer, and until now
 * they each spelled it out: the card asked `!coherent && priced` (UX-P142's
 * fix) and the count asked only `!coherent`. On 2026-09-06 the US Open women's
 * Round of 16 held two fixtures Kalshi had listed hours earlier and nobody had
 * quoted yet — `priced: false`, `coherent: false`, both probabilities `null` —
 * so the cards read "no probability against it" and the line one screen below
 * read "2 matches have numbers that do not agree yet", about the same two
 * matches.
 *
 * `build_slate` emits `coherent: false` for every unpriced row, so this is not
 * an exotic shape: it is what the released draw looks like before a venue
 * quotes it, and the note was wrong for as long as one existed.
 *
 * Exported, and asked by BOTH call sites, so the next change to what counts as
 * a disagreement cannot move one without the other.
 */
export function showsDisagreement(entry: { coherent: boolean; priced: boolean }): boolean {
  return !entry.coherent && entry.priced;
}

export function matchDetailNote(entry: {
  coherent: boolean;
  decided: boolean;
  score: string | null;
  sides: [MatchListSide, MatchListSide];
  /**
   * REQUIRED, and deliberately not defaulted. The whole #2690 defect is a
   * sentence that could not see what state its row was in; a default would let
   * the next call site silently re-acquire that blindness with every test green
   * (both production call sites already pass a full `MatchListEntry`).
   */
  liveState: "in_progress" | "upcoming" | null;
  /** Absent reads as priced — every row before UX-P142 was. */
  priced?: boolean;
}): string | null {
  if (entry.priced === false) {
    // FOURTH CASE (UX-P142), re-aimed by #2690 — see `unpricedDetailNote`.
    return unpricedDetailNote(entry);
  }
  if (!entry.coherent) {
    return "The two numbers for this match do not agree yet, so we are not showing a split.";
  }

  if (entry.decided) {
    const winner = entry.sides.find((side) => side.isWinner);
    const loser = entry.sides.find((side) => !side.isWinner);
    if (
      winner &&
      loser &&
      winner.matchProbability !== null &&
      loser.matchProbability !== null &&
      loser.matchProbability > winner.matchProbability
    ) {
      // The upset. The two numbers are both on the row and the comparison
      // between them is not — this is the only decided row that gets words.
      return `${loser.displayName} was favoured at ${formatSlateProbability(
        loser.matchProbability
      )}.`;
    }
    return null;
  }

  // The biggest mover of the two. One sentence per row, never two.
  const moved = entry.sides
    .filter((side) => moveDirection(side.move) !== "flat")
    .sort((a, b) => Math.abs(b.move ?? 0) - Math.abs(a.move ?? 0))[0];
  if (moved && moved.openingProbability !== null) {
    return `${moved.displayName} opened at ${formatSlateProbability(
      moved.openingProbability
    )}.`;
  }
  return null;
}

/** Title chances by entity key, read off the championship board. */
export type TitleChances = Record<string, number | null>;

function sideFromSlate(
  side: SlateMatch["sides"][number],
  titleChances: TitleChances,
  winnerKey: string | null
): MatchListSide {
  return {
    entityKey: side.entity_key,
    displayName: side.display_name,
    seed: side.seed,
    image: side.image ?? null,
    matchProbability: side.probability,
    openingProbability: side.opening_probability,
    move: side.move,
    titleChance: titleChances[side.entity_key] ?? null,
    isWinner: winnerKey !== null && winnerKey === side.entity_key,
    placeholder: "none",
    // UX-P157. PER SIDE and not per row: a 90/10 is two separate venue rows,
    // and it is routinely the underdog's that nobody will trade at.
    liquidity: side.liquidity ?? null,
    liquidity_reasons: side.liquidity_reasons ?? null,
    observedAt: side.observed_at ?? null,
  };
}

/**
 * The slate, as match-list entries.
 *
 * Preserves server order within a round; the caller groups and filters.
 */
export function matchListFromSlate(
  matches: SlateMatch[],
  options: {
    titleChances?: TitleChances;
    broadcasts?: Broadcast[];
    region?: string;
  } = {}
): MatchListEntry[] {
  const titleChances = options.titleChances ?? {};
  const out: MatchListEntry[] = [];

  for (const match of matches) {
    if (!Array.isArray(match.sides) || match.sides.length !== 2) continue;
    const winnerKey = match.winner_entity_key ?? null;
    const sides: [MatchListSide, MatchListSide] = [
      sideFromSlate(match.sides[0], titleChances, winnerKey),
      sideFromSlate(match.sides[1], titleChances, winnerKey),
    ];
    // The favourite leads, exactly as the old slate row ordered them — but
    // only when the split is trustworthy. An incoherent pair keeps server
    // order, because picking the larger of two numbers we have refused to
    // display would smuggle the refused comparison back onto the page.
    if (match.coherent) {
      sides.sort((a, b) => (b.matchProbability ?? 0) - (a.matchProbability ?? 0));
    }

    const decided = winnerKey !== null;
    const round = slateRoundKey(match.round);
    const entry: MatchListEntry = {
      id: match.matchup_key,
      priced: match.priced !== false,
      round,
      roundLabel: MATCH_ROUND_LABELS[round],
      scheduledDate: match.scheduled_date ?? null,
      startIsTbd: match.start_is_tbd === true,
      liveState: match.live_state ?? null,
      statusDetail: match.status_detail ?? null,
      // ORIENTED TO THE SIDES AS DISPLAYED, NOT AS SERVED.
      //
      // `sides` was just sorted favourite-first, so on every row where the
      // underdog was served first the backend's `home` column is now this
      // row's SECOND side. Passing the line through unchanged would print the
      // set score against the wrong player — a swapped `6-4, 2-1` that reads
      // as a completely different match and that nothing on the card
      // contradicts.
      linescore: orientLinescore(
        match.linescore,
        sides[0].entityKey,
        sides[1].entityKey,
      ),
      drawLabel: match.draw_label ?? null,
      sides,
      decided,
      score: match.score ?? null,
      coherent: match.coherent,
      isLive: slateRowIsPresentedAsLive(match),
      freshnessLabel: slateRowFreshnessLabel(match),
      broadcast: matchBroadcast(match, options.broadcasts, options.region),
      detailNote: null,
      eventId: match.event_id ?? null,
      matchupKey: match.matchup_key ?? null,
      source: "slate",
      priceMarker: priceMarkerFor(match.price_source),
    };
    entry.detailNote = matchDetailNote(entry);
    out.push(entry);
  }
  return out;
}

/**
 * The draw, as match-list entries — with the slate's prices joined on.
 *
 * A bracket match has a position and a title probability per side; it has no
 * price on itself. The price for "Alcaraz beats Rublev today" lives in the
 * slate, keyed by the unordered pair. So this joins, exactly as
 * `prematchFromSlate` does, and for the same reason: the pair is the only key
 * the two datasets share.
 *
 * An undetermined slot NEVER renders blank (UX-P137, ruling 3). A round-one
 * hole is a register gap; a later hole is an unplayed feeder; the two get
 * different sentences because they are different facts.
 */
export function matchListFromBracket(
  rounds: BracketRound[],
  options: {
    slate?: SlateMatch[];
    prematch?: Record<string, PrematchPair>;
    titleChances?: TitleChances;
    broadcasts?: Broadcast[];
    region?: string;
    /** Decided-match scores by bracket match id. Empty in production — see `score`. */
    scores?: Record<string, string>;
  } = {}
): MatchListEntry[] {
  const titleChances = options.titleChances ?? {};
  const scores = options.scores ?? {};
  const slateByPair = new Map<string, SlateMatch>();
  for (const match of options.slate ?? []) {
    if (!Array.isArray(match.sides) || match.sides.length !== 2) continue;
    slateByPair.set(
      pairKey(match.sides[0].entity_key, match.sides[1].entity_key),
      match
    );
  }

  const out: MatchListEntry[] = [];
  for (const round of rounds) {
    // A ROUND NOBODY HAS REACHED CONTRIBUTES NOTHING TO A MATCH LIST.
    //
    // UX-P136's lesson, restated in this structure. On the morning of the draw
    // every round after the first is 63 cards reading "Winner of R128 #1" v
    // "Winner of R128 #2", and under ruling 4 each of those rounds would also
    // get its own pill — a strip of seven where six open onto a wall. The
    // future is the GRID's subject now, and the grid says something true about
    // it. A round appears in this list the moment one real name lands in it.
    if (roundIsUnreached(round)) continue;
    for (const match of round.matches) {
      const decided = match.winnerKey !== null;
      const joined =
        match.top && match.bottom
          ? slateByPair.get(pairKey(match.top.entity_key, match.bottom.entity_key))
          : undefined;
      const priceFor = (entityKey: string): SlateMatch["sides"][number] | undefined =>
        joined?.sides.find((side) => side.entity_key === entityKey);

      const build = (
        slot: BracketRound["matches"][number]["top"],
        from: string | null
      ): MatchListSide => {
        if (slot === null) {
          return {
            entityKey: null,
            // UX-P145: was "No registered player". The reader does not have a
            // register; they have a draw with a slot nobody has filled in.
            // `placeholder: "register-hole"` keeps our name for it where our
            // names belong — on a data attribute, not in the sentence.
            displayName:
              from === null ? "Player to be confirmed" : `Winner of ${from.replace("-", " #")}`,
            seed: null,
            image: null,
            matchProbability: null,
            openingProbability: null,
            move: null,
            titleChance: null,
            isWinner: false,
            placeholder: from === null ? "register-hole" : "awaiting-feeder",
          };
        }
        const price = priceFor(slot.entity_key);
        // Ruling 1: the MATCH number is the primary. Live price when the slate
        // has one; the pre-match number when the match is over and the live
        // price has collapsed to 1 or 0; `null` when we simply have neither.
        const pre =
          match.top && slot.entity_key === match.top.entity_key
            ? (options.prematch?.[match.id]?.top ?? null)
            : (options.prematch?.[match.id]?.bottom ?? null);
        return {
          entityKey: slot.entity_key,
          displayName: slot.display_name,
          seed: slot.seed,
          // A draw slot carries no image of its own; like the price, it comes
          // from the slate row this match absorbed.
          image: price?.image ?? null,
          matchProbability: decided ? pre : (price?.probability ?? pre),
          openingProbability: price?.opening_probability ?? pre,
          move: decided ? null : (price?.move ?? null),
          // The title chance prefers the BOARD, because the board is the
          // surface this number is published on and two surfaces printing
          // different values for one question is the divergence bug, not a
          // feature. The draw slot's own copy is the fallback.
          titleChance: titleChances[slot.entity_key] ?? slot.probability ?? null,
          isWinner: match.winnerKey === slot.entity_key,
          placeholder: "none",
        };
      };

      const sides: [MatchListSide, MatchListSide] = [
        build(match.top, match.topFrom),
        build(match.bottom, match.bottomFrom),
      ];

      const entry: MatchListEntry = {
        id: match.id,
        priced: joined ? joined.priced !== false : false,
        round: match.round,
        roundLabel: MATCH_ROUND_LABELS[match.round],
        scheduledDate: joined?.scheduled_date ?? null,
        startIsTbd: joined?.start_is_tbd === true,
        liveState: joined?.live_state ?? null,
        statusDetail: joined?.status_detail ?? null,
        // The bracket path gets the line from the SLATE row it joined to, and
        // from nowhere else — a draw slot carries no score. `null` when the
        // fixture is not on today's slate, which is the ordinary case for a
        // bracket match days out.
        //
        // AND IT IS RE-ORIENTED, BECAUSE THE JOIN IS ORDER-BLIND. `pairKey`
        // sorts its two keys so a slate row matches its bracket fixture
        // whichever way round each names the pair — which is what makes the
        // join work, and exactly what makes the score's columns unsafe to
        // carry across it. These sides are the DRAW's top/bottom; the line's
        // columns are the slate row's, and about half the time those are
        // opposite.
        linescore: orientLinescore(
          joined?.linescore,
          sides[0].entityKey,
          sides[1].entityKey,
        ),
        drawLabel: joined?.draw_label ?? null,
        sides,
        decided,
        score: scores[match.id] ?? joined?.score ?? null,
        coherent: joined ? joined.coherent : true,
        isLive: joined ? slateRowIsPresentedAsLive(joined) : false,
        freshnessLabel: joined ? slateRowFreshnessLabel(joined) : null,
        broadcast: joined
          ? matchBroadcast(joined, options.broadcasts, options.region)
          : null,
        detailNote: null,
        // A positioned draw slot has no event of its own; the link, like the
        // price, comes from the slate row it absorbed.
        eventId: joined?.event_id ?? null,
        matchupKey: joined?.matchup_key ?? null,
        source: "bracket",
        // The marker travels with the number, and the number came from the
        // slate row this slot absorbed — a draw slot has no price of its own.
        priceMarker: priceMarkerFor(joined?.price_source),
      };
      entry.detailNote = matchDetailNote(entry);
      out.push(entry);
    }
  }
  return out;
}

/**
 * THE match list: the draw where we have it, the slate where we do not.
 *
 * The dedup is the point. A slate match whose pair is already positioned in
 * the draw is dropped, because the bracket entry ABSORBED it — same match, one
 * row, with both the draw position and the price. Before this, a main-draw
 * afternoon printed every match twice on two tabs and nothing said they were
 * the same match.
 */
export function buildMatchList(options: {
  slate?: SlateMatch[];
  rounds?: BracketRound[];
  prematch?: Record<string, PrematchPair>;
  titleChances?: TitleChances;
  broadcasts?: Broadcast[];
  region?: string;
  scores?: Record<string, string>;
}): MatchListEntry[] {
  const slate = options.slate ?? [];
  const rounds = options.rounds ?? [];
  const bracketEntries = matchListFromBracket(rounds, options);

  const absorbed = new Set<string>();
  for (const round of rounds) {
    for (const match of round.matches) {
      if (match.top && match.bottom) {
        absorbed.add(pairKey(match.top.entity_key, match.bottom.entity_key));
      }
    }
  }

  const remaining = slate.filter((match) => {
    if (!Array.isArray(match.sides) || match.sides.length !== 2) return false;
    return !absorbed.has(pairKey(match.sides[0].entity_key, match.sides[1].entity_key));
  });

  return [...matchListFromSlate(remaining, options), ...bracketEntries];
}

export interface MatchRoundPill {
  round: MatchRoundKey;
  label: string;
  shortLabel: string;
  total: number;
  decided: number;
}

/**
 * The round pills — ONLY rounds that actually have matches (ruling 4).
 *
 * A pill for a round we hold nothing for is the empty-tab failure with a
 * smaller footprint: the reader taps it and gets a wall. Rounds appear as the
 * draw reaches them.
 */
export function matchRoundPills(entries: MatchListEntry[]): MatchRoundPill[] {
  const counts = new Map<MatchRoundKey, { total: number; decided: number }>();
  for (const entry of entries) {
    const bucket = counts.get(entry.round) ?? { total: 0, decided: 0 };
    bucket.total += 1;
    if (entry.decided) bucket.decided += 1;
    counts.set(entry.round, bucket);
  }
  return MATCH_ROUND_ORDER.filter((round) => counts.has(round)).map((round) => ({
    round,
    label: MATCH_ROUND_LABELS[round],
    shortLabel: MATCH_ROUND_PILL_LABELS[round],
    total: counts.get(round)?.total ?? 0,
    decided: counts.get(round)?.decided ?? 0,
  }));
}

/**
 * Which round to open on: the earliest one still being played.
 *
 * "Where the tournament is" — the same rule the round strip used, kept because
 * it was right: opening on a Round of 128 that finished a week ago is the
 * default that makes a reader tap before they can read anything.
 */
export function defaultMatchRound(entries: MatchListEntry[]): MatchRoundKey | null {
  const pills = matchRoundPills(entries);
  if (pills.length === 0) return null;
  return (pills.find((pill) => pill.decided < pill.total) ?? pills[pills.length - 1]).round;
}

/**
 * Which DRAW to open on: the one with a match on court right now.
 *
 * The sibling of `defaultMatchRound` above, and it exists for the same reason
 * — "where the tournament is" — applied to the axis that rule never covered.
 * The round default follows play; the draw default did not, and the gap was a
 * hardcoded `useState("mens-singles")` that had never read the slate.
 *
 * ═══ WHAT IT COST, MEASURED (live/077 item 2) ═══
 *
 * Sampled on production 2026-09-05 at 15:04-15:22Z, with Potapova-Anisimova
 * and Keys-Zheng both `STATUS_IN_PROGRESS` on ESPN and both priced and moving
 * on our own slate: the phone-width Round of 32 list showed **neither**, and
 * opened on the 11:30 men's match instead. Nothing was dropped and nothing was
 * mis-sorted — the two live matches are WOMEN'S, the page opens on the men's
 * draw, and the collapsed list shows five rows of the draw it opened on. The
 * two in-progress rows were one untaken tap away and nothing on screen said
 * so. A reader landing at 15:04Z was told the tournament's live matches did
 * not exist.
 *
 * This is why the rule keys on `live_state` and NOT on `scheduled_date`
 * against the clock: `live_state` is ESPN's own state (see `SlateMatch`), and
 * a five-setter outlives any elapsed-time window we could invent. "Started
 * three hours ago" is not evidence a match is over, and a default that guessed
 * from a timestamp would swap the page onto a draw whose matches had all
 * finished.
 *
 * ═══ WHY EARLIEST-STARTED, AND WHY NOT "THE MOST LIVE MATCHES" ═══
 *
 * Ties are the whole design question here, because a US Open afternoon runs
 * both draws at once. Counting live matches per draw picks the busier
 * scoreboard, which is a fact about the ORDER OF PLAY and not about what the
 * reader came for. Earliest-started picks the match nearest a result, matches
 * the word `defaultMatchRound` already uses for the same job one axis over,
 * and is stable as later matches begin: a new start cannot move the answer,
 * only a finish can. `draws` order breaks an exact tie so the result is
 * deterministic on a payload where two matches share a start time — 6 of the
 * 15 Round-of-32 rows did on the day this was written.
 *
 * Returns `null` for "nothing is on" — the caller keeps its own opening draw
 * rather than this function inventing one. A tournament between sessions has
 * no live draw, and that is not the same as a preference.
 *
 * THE CALLER RESOLVES THIS ONCE, at first payload, and never again: see
 * `page.tsx`. A default that re-evaluated would swap the page out from under a
 * reader the moment a match in the other draw started.
 */
export function defaultDraw(
  matches: SlateMatch[],
  draws: { id: string }[]
): string | null {
  let best: { draw: string; started: string; rank: number } | null = null;
  for (const match of matches) {
    if (match.live_state !== "in_progress") continue;
    const rank = draws.findIndex((entry) => entry.id === match.draw);
    // A draw the toggle does not offer cannot be opened on. Doubles and mixed
    // ride the same slate and would otherwise select a tab that does not exist.
    if (rank < 0) continue;
    const started = match.scheduled_date;
    if (
      best === null ||
      started < best.started ||
      (started === best.started && rank < best.rank)
    ) {
      best = { draw: match.draw, started, rank };
    }
  }
  return best?.draw ?? null;
}

export function matchesInRound(
  entries: MatchListEntry[],
  round: MatchRoundKey
): MatchListEntry[] {
  return entries.filter((entry) => entry.round === round);
}

/**
 * ═══ WHAT HAPPENED TO THE REST OF THE ROUND (#2450) ═══
 *
 * Alex: *"`ROUND OF 128 · 25 matches` next to `FINISHED · Men's Singles · 71`.
 * Nothing explains how a 128-draw shows 25 live and 71 finished, or what
 * happened to the rest."*
 *
 * He is doing the only arithmetic available to him and it does not close. Both
 * numbers are correct and they count DIFFERENT POPULATIONS, which is the one
 * thing neither of them said:
 *
 *   - `25` is the matches of this round still in the list. `build_slate` drops
 *     a matchup the moment it starts (`ALREADY_PLAYED: 28, DECIDED: 66` on the
 *     live payload 2026-09-01), so the list holds the unfinished remainder of
 *     the round and never the whole of it.
 *   - `71` is every finished match in this DRAW across every round, qualifying
 *     included — 178 rows platform-side, of which the men's singles held 84 on
 *     2026-09-01: 41 in the main draw and 43 across three qualifying rounds.
 *
 * So the two numbers cannot be added, subtracted or compared, and the page was
 * inviting a reader to do all three.
 *
 * ### The size of a round is definitional, and that is the missing anchor
 *
 * A round of 128 is 64 matches. Not a lookup, not a payload field, not an
 * assumption about the draw — `R128` MEANS 128 players, and 128 players is 64
 * matches. So the list can state the round's true size beside the count it is
 * showing, and the reader's arithmetic closes on the spot: 64 in the round, 16
 * here, the rest have finished.
 *
 * `null` for `qualifying`, which is the one key that is not a `RoundName`: it
 * buckets three rounds of a draw whose size we genuinely do not know, and
 * inventing a number for it would be exactly the unexplained figure this
 * function exists to remove.
 */
export function matchRoundSize(round: MatchRoundKey): number | null {
  if (round === "qualifying") return null;
  const players = ROUND_PLAYER_COUNTS[round];
  return players === undefined ? null : players / 2;
}

const ROUND_PLAYER_COUNTS: Record<RoundName, number> = {
  R128: 128,
  R64: 64,
  R32: 32,
  R16: 16,
  QF: 8,
  SF: 4,
  F: 2,
};

/**
 * The sentence that reconciles the two counts, or `null` when there is nothing
 * to reconcile.
 *
 * Deliberately does NOT say how many have finished. We know the round's size
 * and we know what is in this list; we do NOT know how many of the remainder
 * our results feed actually holds — 17 of the live payload's 82 Round-1 results
 * had already lost their register matchup, and 134 finished matches were
 * dropped for players the register does not carry. Printing `the other 48 have
 * finished` beside a Finished list showing 41 would replace one arithmetic
 * anyone can check with another one that also fails.
 *
 * So it states the two facts we can stand behind — the round's size, and that
 * finished matches leave this list — and lets the reader stop looking for the
 * missing rows.
 */
export function matchRoundReconciliation(
  round: MatchRoundKey,
  shown: number
): string | null {
  const size = matchRoundSize(round);
  if (size === null) return null;
  // The whole round is here: nothing is missing, so nothing needs explaining.
  if (shown >= size) return null;
  // "This round is 64 matches", not "a round of 128 is 64 matches": the label
  // reads naturally for the draw-size rounds and not at all for the named ones
  // ("a quarter-finals is 4 matches"), and the heading directly above already
  // says which round this is.
  return `This round is ${size} matches. Finished ones move to Finished, below.`;
}

/**
 * The muted secondary chip's text (ruling 1).
 *
 * SELF-LABELLING, and that is not decoration. The whole of UX-P137's ruling 2
 * was Alex being unable to tell what a bare percentage on this page meant, and
 * the answer turned out to be the chance of winning the entire tournament
 * printed beside the opponent a player was about to play. A chip that reads
 * "22%" beside a match number would re-create that exact confusion in a
 * smaller font. `null` when there is nothing to say — never "—", because an
 * absent chip is quieter than a chip apologising for being empty, and Alex's
 * density constraint is the binding one here.
 */
export function titleChipLabel(titleChance: number | null): string | null {
  if (titleChance === null || !Number.isFinite(titleChance)) return null;
  return `${Math.round(titleChance * 100)}% title`;
}

/** Full sentence for screen readers and `title=` — the chip is terse by design. */
export function titleChipDescription(displayName: string, titleChance: number): string {
  return `${displayName}: ${Math.round(
    titleChance * 100
  )}% chance of winning the tournament`;
}

/** The row's age line — mirrors the boards so the page words one idea one way. */
export function matchAgeLabel(ageHours: number | null): string {
  return slateStalenessLabel(ageHours);
}
