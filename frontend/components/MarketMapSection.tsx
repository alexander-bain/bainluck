"use client";

import { useMemo } from "react";
import MarketMap, { ladderGraded } from "./MarketMap";
import type { MarketMapMarker, MarketMapLadderRow } from "./MarketMap";
import type { GameMarketsResponse } from "@/lib/api";
import type { PlayedLinescore, SportScoringVocab } from "@/lib/marketMapUtils";
import {
  parseSpreadRungs,
  isFullGameSpread,
  isGameTotal,
  buildDensityFromSpreads,
  buildDensityFromThresholds,
  sportVocab,
  withUnit,
  unitPhrase,
  halfLabel,
  distributionTense,
  playedCountAbsence,
  playedUnits,
  mapColumnHeading,
  posOnRail,
  collapseDuplicateRungs,
  densityDrawsShape,
  quotedLinesPhrase,
  settledLinesPhrase,
  derivePeriod,
  marketMapIsGraded,
  selectGameTotalRungs,
  selectHalfTotalRungs,
  settledHalfTotalsFromGrades,
  ladderQuotesALine,
  settledLadderQuotesALine,
  probabilitiesQuoteALine,
  TOTAL_MAP_HALVES,
} from "@/lib/marketMapUtils";
import { formatProbability } from "@/lib/api";
import { teamShortName } from "@/lib/teamShortName";

/**
 * The rail colours, named once (#3210).
 *
 * `densityDrawsShape` answers its question by comparing the colours the rail
 * would actually paint, so it is handed the SAME accent the rail is handed.
 * Today that is belt-and-braces — `rgbaFromIntensity` varies only the alpha,
 * so the predicate's answer does not depend on the rgb and a mismatch would be
 * harmless. It is written this way for the day the ramp becomes colour-aware,
 * because on that day a repeated literal is a silent wrong answer rather than
 * a compile error.
 */
const MARGIN_ACCENT = "37,99,235";
const TOTAL_ACCENT = "124,58,237";

interface MarketMapSectionProps {
  gameMarkets: GameMarketsResponse;
  eventStatus: string;
  homeTeam: string;
  awayTeam: string;
  homeAbbr?: string;
  awayAbbr?: string;
  homeColor?: string;
  awayColor?: string;
  homeLogo?: string;
  awayLogo?: string;
  homeWinProb?: number;
  awayWinProb?: number;
  homeSpread?: number | null;
  overUnder?: number | null;
  /**
   * ═══ #5414: WHAT THE MARKET QUOTED BEFORE PLAY, FOR THE TILE THAT SAYS SO ═══
   *
   * `homeSpread` / `overUnder` above are the LATEST snapshot. Three of this
   * card's markers are labelled `Pre-game`, and two of them (the `live` and
   * `done` arms) are drawn on a game whose latest snapshot is no longer a
   * pre-game quantity at all. Measured on event 15310077 (Cubs–Pirates): the
   * last snapshot was captured 21:00Z against an 18:20Z first pitch, at
   * `home_probability` 0.999 and `spread` **-7.9**, on a game that OPENED at
   * -1.5. So the freshest number is the wrong number under this label, and it
   * gets wronger the longer the game runs.
   *
   * These two are `events.opening_*` — the last pre-game consensus, frozen at
   * first pitch by `_maybe_set_opening_odds`. They outrank the latest snapshot
   * on every arm, including `pre`, where the two agree anyway (both keep
   * updating until the game starts) and preferring one rule to a
   * status-dependent pair is one less thing to get wrong.
   *
   * ⚠️ **A QUOTED LINE, NOT A DERIVED ONE — WHICH IS WHY `hasDerivedSpread`
   * DOES NOT GATE THEM.** #2441 banned a spread this page INVENTED from the
   * win probability over a sport with no points. `opening_home_spread` is the
   * median of the `spreads` market's home `point` across the quoting books
   * (`odds_polling._parse_snapshot_values` → `_maybe_set_opening_odds`); for
   * tennis those books quote GAMES, which is the unit this file already
   * declares for tennis (`unit: "games"`, `marginRange: 6`). #2441's rule is
   * "show what a venue quoted, lose only what we made up" — this is the
   * quoted half, so it passes the rule rather than bypassing it. Coverage is
   * not the reason either: 129 of 129 US Open ATP events carry one (measured
   * 2026-09-11, 30 days). The unit question tennis really does have is
   * `scoreboardCountsTheUnit`, and that is answered separately and unchanged.
   *
   * Both `number | null`: a PICK'EM opens at a spread of exactly **0.0**, so
   * every test between here and the marker is `!= null`, never truthiness.
   * 557 of 7,717 events with an opening spread (7.2%) opened at 0.
   */
  openingHomeSpread?: number | null;
  openingOverUnder?: number | null;
  sportKey?: string;
  espnHistory?: Array<{ period?: string; home_score?: number; away_score?: number; timestamp?: string }>;
  /**
   * The per-set games line, where the event has one (live/073). It is what
   * makes a tennis map able to say where the match landed: the scoreboard
   * beside it counts sets, and every rail on this page is drawn in games.
   */
  linescore?: PlayedLinescore | null;
  /**
   * #5206: this match passed the point of being upcoming and NOTHING reported
   * how it went — `suspended`, or `scheduled` well past its own kickoff.
   *
   * It arrives as a decided boolean rather than as a `commence_time` this
   * component would re-derive, because the page already asks the question once
   * (`hasNoReportedResult`, `page.tsx`) to draw the hero's "No result reported".
   * Two graders reading one input and disagreeing is #1650, and the whole point
   * of `lib/eventState.ts` is that no two surfaces answer this differently.
   */
  noResultReported?: boolean;
}

interface HalfScores {
  h1Home: number;
  h1Away: number;
  h2Home: number;
  h2Away: number;
}

/** ESPN's baseball `period`: `Top 5th`, `Middle 5th`, `Bottom 5th`, `End 5th`. */
const INNING_PERIOD = /^(top|mid(?:dle)?|bot(?:tom)?|end)\s+(\d+)(?:st|nd|rd|th)$/i;

function inningOf(period: string): { end: boolean; inning: number } | null {
  const m = INNING_PERIOD.exec(period.trim());
  return m ? { end: m[1].toLowerCase() === "end", inning: Number(m[2]) } : null;
}

/**
 * Is this ESPN row the moment the first period closed?
 *
 * #8557: an inning sport says where its first period stops
 * (`firstHalfEndsAfterInning`) and the row is ESPN's `End 5th`; every other
 * sport keeps the halftime vocabulary it had, passed in by the caller because
 * the settled and live readers never agreed on it (`end of 2nd` is the settled
 * one's alone) and this ship does not move either.
 */
function closesFirstHalf(period: string, vocab: SportScoringVocab, halftime: RegExp): boolean {
  if (vocab.firstHalfEndsAfterInning == null) return halftime.test(period);
  const at = inningOf(period);
  return at != null && at.end && at.inning === vocab.firstHalfEndsAfterInning;
}

function deriveHalfScores(
  espnHistory: MarketMapSectionProps["espnHistory"],
  finalHome: number | null,
  finalAway: number | null,
  vocab: SportScoringVocab
): HalfScores | null {
  if (!espnHistory || espnHistory.length === 0) return null;
  if (finalHome == null || finalAway == null) return null;

  const htEntry = [...espnHistory].reverse().find(
    (e) => e.period && closesFirstHalf(e.period, vocab, /halftime|^ht$|end of 2nd/i) && e.home_score != null
  );
  if (!htEntry || htEntry.home_score == null || htEntry.away_score == null) return null;

  return {
    h1Home: htEntry.home_score,
    h1Away: htEntry.away_score,
    h2Home: finalHome - htEntry.home_score,
    h2Away: finalAway - htEntry.away_score,
  };
}

/**
 * Determine which half the game is currently in from ESPN history.
 * Returns "1H" or "2H" (null if unknown).
 */
function detectCurrentHalf(
  espnHistory: MarketMapSectionProps["espnHistory"],
  vocab: SportScoringVocab
): "1H" | "2H" | null {
  if (!espnHistory || espnHistory.length === 0) return null;
  const latest = espnHistory[espnHistory.length - 1];
  if (!latest.period) return null;
  // #8557: `Top 3rd` fell through to "2H" below, so a live first-five card
  // looked for a halftime row that baseball never writes and drew no Actual.
  // `End 5th` is still the first period, as `Halftime` is. A row that names
  // no inning (`Delayed`) is unknown here, not the second period.
  const endsAfter = vocab.firstHalfEndsAfterInning;
  if (endsAfter != null) {
    const at = inningOf(latest.period);
    if (!at) return null;
    return at.inning <= endsAfter ? "1H" : "2H";
  }
  const p = latest.period.toLowerCase();
  if (/1st quarter|1st half|first half|^q1\b|^q2\b|2nd quarter/i.test(p)) return "1H";
  if (/halftime|^ht$/i.test(p)) return "1H";
  return "2H";
}

/**
 * Derive live half scores for in-progress games.
 * - In the 1st half: h1 = current game scores, h2 = null
 * - In the 2nd half: h1 = halftime scores, h2 = current - halftime
 */
function deriveLiveHalfScores(
  espnHistory: MarketMapSectionProps["espnHistory"],
  currentHome: number | null,
  currentAway: number | null,
  currentHalf: "1H" | "2H" | null,
  vocab: SportScoringVocab
): { h1Home: number; h1Away: number; h2Home: number | null; h2Away: number | null } | null {
  if (currentHome == null || currentAway == null || !currentHalf) return null;

  if (currentHalf === "1H") {
    return { h1Home: currentHome, h1Away: currentAway, h2Home: null, h2Away: null };
  }

  // 2nd half: need halftime scores
  if (!espnHistory || espnHistory.length === 0) return null;
  const htEntry = espnHistory.find(
    (e) => e.period && closesFirstHalf(e.period, vocab, /halftime|^ht$/i) && e.home_score != null
  );
  if (!htEntry || htEntry.home_score == null || htEntry.away_score == null) return null;

  return {
    h1Home: htEntry.home_score,
    h1Away: htEntry.away_score,
    h2Home: currentHome - htEntry.home_score,
    h2Away: currentAway - htEntry.away_score,
  };
}

/**
 * `BER by 4.5+` — a MARGIN, not a handicap (#2442).
 *
 * This printed `BER +4.5`: a competitor abbreviation followed by a signed
 * number, which is a betting line and nothing else. Alex quoted it first among
 * the six gambling formats he counted on one screen.
 *
 * The number does not change and neither does what it means. `by N+` states the
 * thing the reader actually wants — how far ahead — in the sport's own units,
 * and it is the wording `MARGIN_LADDER_LABEL` below now shares, so the headline
 * and the ladder cannot drift into two grammars.
 */
function formatMarginLabel(margin: number, teamAbbr: string, threshold: number): string {
  if (margin === 0) return "Tied";
  const val = threshold % 1 === 0 ? Math.abs(threshold) : Math.abs(threshold).toFixed(1);
  return marginLadderLabel(teamAbbr, val);
}

/** One grammar for "this competitor, this far ahead", used by every ladder. */
function marginLadderLabel(teamAbbr: string, threshold: number | string): string {
  return `${teamAbbr} by ${threshold}+`;
}

/**
 * `BC by 7` — a margin that HAPPENED, where the rung grammar above would lie.
 *
 * #7380, measured on production 2026-09-19 at 390px: `/events/15304450`, Boston
 * College 28 Rutgers 21, drew `FINAL BC by 7+` on a final margin of exactly 7,
 * and a live card drew `ACTUAL JMU by 13+` over a scoreboard reading 13–26.
 * "7+" means seven OR MORE; a played margin has no more left in it. The same
 * screen already disagreed with itself twice over — the totals card one slot
 * down prints its settled total as `49 points`, and the half rail below printed
 * its exact margin without a suffix.
 *
 * The `+` is not a slip in `marginLadderLabel`: a rung IS a threshold, and
 * `gradeMarginRung` grades it `>=` for exactly that reason. It stays on rungs,
 * and on the PRE-GAME / PROJECTION tiles, which quote a cover line — a handicap,
 * not a measurement. This is the other case: ACTUAL and FINAL are the scoreboard,
 * and a scoreboard is stated.
 *
 * NOT `BC +7`, which is the spelling the half rail reached for and the one #2442
 * removed from this page — a competitor abbreviation followed by a signed number
 * is a betting line, the first of the six gambling formats Alex counted on one
 * screen. #2442's answer was `by N` in the sport's own units; the `+` it added
 * belonged to the rung it was fixing. So the half rail's two markers are brought
 * here rather than copied from, and all four sites now spell one quantity one way.
 */
function exactMarginLabel(teamAbbr: string, margin: number): string {
  if (margin === 0) return "Tied";
  return `${teamAbbr} by ${Math.abs(margin)}`;
}

/**
 * #6203. How a margin rung finished, against the final margin of the scope that
 * rung belongs to — the game for the full-game rail, the half for a period one.
 *
 * #3769 gave the TOTALS ladder this rule: `probability` is read live and
 * collapses to the RESOLVED price the moment a market settles, so a settled
 * rung must be graded against the final rather than quoted. The margin rail was
 * left out of it, so one settled card printed "EACH LINE VS THE FINAL" over its
 * totals and "LAST QUOTE FOR WINNING BY" over its margins — two tenses, one tap
 * apart, the second describing settlement values as if they were quotes.
 * Written once, for both margin rails, because this file's own history is a
 * list of the three places that came to disagree about one grammar.
 *
 * `finalMargin` is signed home-minus-away; `threshold` is a magnitude and
 * `isHome` names the side, so an away rung grades against the mirror.
 *
 * INCLUSIVE, where the totals rule is strict, because the LABEL is inclusive.
 * Every rung on this rail is written by `marginLadderLabel` as `NYG by 15+`,
 * and "15+" is true of a 15-point win: grading it "not cleared" would
 * contradict the FINAL marker the same rail draws at 15. Both spellings that
 * reach here agree with the label — "wins by 15 or more points" is `>= 15`
 * outright (#3788/#6199 keeps that shape as a rung precisely because it is
 * bounded at one end only), and a cover line is quoted at `.5`, where `>` and
 * `>=` cannot disagree. An integer cover line would be a push, an outcome this
 * rail cannot draw; it grades the claim the label makes rather than inventing a
 * third state.
 */
export function gradeMarginRung(
  finalMargin: number | null,
  isHome: boolean,
  threshold: number
): MarketMapLadderRow["outcome"] {
  if (finalMargin == null) return undefined;
  return (isHome ? finalMargin : -finalMargin) >= threshold ? "cleared" : "missed";
}

/**
 * #8585 — served abbreviations that are English words, which every label on
 * this card turns into a sentence: Ole Miss's real ESPN code printed "FINAL
 * MISS by 8" under a hero saying the Rebels won — read as "the forecast missed
 * by 8". "NO" (New Orleans) reads "FINAL NO by 8" the same way. These sides
 * take the short name the hero already uses instead. Upper-case keys; the
 * served code is compared upper-cased.
 */
const ABBREVIATIONS_THAT_READ_AS_WORDS: ReadonlySet<string> = new Set(["MISS", "NO"]);

function deriveAbbr(team: string, provided?: string, sportKey?: string): string {
  if (provided) {
    if (!ABBREVIATIONS_THAT_READ_AS_WORDS.has(provided.trim().toUpperCase())) return provided;
    return teamShortName(team, null, sportKey) || provided;
  }
  const words = team.split(" ");
  return words[words.length - 1].slice(0, 3).toUpperCase();
}

export default function MarketMapSection({
  gameMarkets,
  eventStatus,
  homeTeam,
  awayTeam,
  homeAbbr,
  awayAbbr,
  homeColor,
  awayColor,
  homeLogo,
  awayLogo,
  homeWinProb,
  awayWinProb,
  homeSpread,
  overUnder,
  openingHomeSpread,
  openingOverUnder,
  sportKey,
  espnHistory,
  linescore,
  noResultReported = false,
}: MarketMapSectionProps) {
  const hAbbr = deriveAbbr(homeTeam, homeAbbr, sportKey);
  const aAbbr = deriveAbbr(awayTeam, awayAbbr, sportKey);
  const vocab = sportVocab(sportKey);

  const isLive = eventStatus === "live";
  const isDone = marketMapIsGraded(eventStatus);
  const status = isLive ? "live" : isDone ? "done" : "pre";

  /**
   * ── #5206: A FORECAST AND A RESULT ARE TWO QUESTIONS, AND SO ARE THEIR MARKS ──
   *
   * `status` is a three-value type threaded through twenty call sites and into
   * `MarketMap` itself, so an unreported match has nowhere to land but `"pre"` —
   * the branch that draws a forward-looking `Projection` mark and a
   * `Projected N` headline. On production a suspended match therefore carried a
   * hero reading "No result reported" and, one card below, "Scoring map —
   * Projected 3". The web twin of #4018, whose line applies verbatim.
   *
   * Widening `status` to a fourth value would touch every one of those sites for
   * a question only two of them ask. What is actually wrong is narrower than the
   * state: the marks are in the WRONG TENSE. A match that should already have
   * happened has no forecast to offer — but the number the market quoted before
   * it is still true, and still worth showing.
   *
   * So this does not suppress the map; it moves the forecast into the past
   * tense, reusing the vocabulary the file already owns rather than inventing
   * one. `type: "pre" / label: "Pre-game"` is exactly what the `done` branch and
   * the half-maps' `isDone ? "pre" : "proj"` already emit for the same reason.
   * The ladder, the density and the distribution are untouched: those are what
   * the market says, not a claim about what will happen.
   */
  const noForecast = noResultReported;

  /**
   * ux/1034 B5: the scoreboard's two numbers, ONLY where they count the thing
   * this map's rail is drawn in.
   *
   * On a tennis match they are SETS (`0 — 3`) and the rail is GAMES, so every
   * downstream use — the margin marker, the total marker, the "expected vs
   * final" grading — was comparing three sets against a game line and printing
   * the answer as a fact. Nulling them here rather than at each use is
   * deliberate: there are six call sites across the four maps on this page, and
   * a gate per site is a gate somebody adds a seventh site beside.
   *
   * The maps keep every rung, every density and every pre-game marker. What
   * goes is only the half we cannot state — see `scoreboardCountsTheUnit`.
   *
   * live/073: AND WHERE THE SCOREBOARD DOES NOT COUNT THE UNIT, THE LINESCORE
   * DOES. The half we could not state is stated now — `6-3, 6-4, 6-1` is 26
   * games — so these two stop being null on a tennis page that has a line, and
   * every one of those six downstream call sites lands on the real number
   * without knowing where it came from. `playedUnits` is the one place that
   * decides; see its note.
   */
  const played = playedUnits(
    vocab,
    { home: gameMarkets.home_score, away: gameMarkets.away_score },
    linescore
  );
  const homeScore = played?.home ?? null;
  const awayScore = played?.away ?? null;

  /**
   * The sentence a suppressed map owes the reader.
   *
   * A map that simply drops its Final tile reads as a map that failed to load.
   * This says which two units it refuses to mix and what is missing, in the
   * sport's own words — `unit` and `scoreboardUnit` both come from the vocab,
   * so a second set-scored sport declared tomorrow gets the sentence for free.
   *
   * #3136: the CLAIM half comes from `playedCountAbsence`, which is what stops
   * a finished match being told the count is still on its way. See that
   * helper — the tense is shared with the Score Differential note above this
   * card precisely so the two cannot disagree on one page.
   */
  //
  // live/073: `played` and not `scoreboardCountsTheUnit`, so the sentence
  // disappears the moment the number arrives. A page that holds the line and
  // still says it did not record the games is the same false claim in the
  // opposite direction.
  const unitMismatchNote =
    !vocab.scoreboardCountsTheUnit &&
    vocab.scoreboardUnit &&
    (isLive || isDone) &&
    played == null
      ? `The scoreboard reports ${vocab.scoreboardUnit}, this market quotes ` +
        `${vocab.unit} — ${playedCountAbsence(vocab.unit, isDone)}.`
      : null;

  const halfScores = useMemo(
    () => deriveHalfScores(espnHistory, homeScore, awayScore, vocab),
    [espnHistory, homeScore, awayScore, vocab]
  );

  const currentHalf = useMemo(
    () => (isLive ? detectCurrentHalf(espnHistory, vocab) : null),
    [isLive, espnHistory, vocab]
  );

  const liveHalfScores = useMemo(
    () => (isLive ? deriveLiveHalfScores(espnHistory, homeScore, awayScore, currentHalf, vocab) : null),
    [isLive, espnHistory, homeScore, awayScore, currentHalf, vocab]
  );

  // ── Margin Map ──
  const marginData = useMemo(() => {
    const fullGameSpreads = (gameMarkets.spreads || []).filter((s) =>
      isFullGameSpread(s.market_name || "")
    );
    if (fullGameSpreads.length === 0) return null;

    /* #4598: A RUNG BELONGS TO THE RAIL'S OWN UNIT, OR IT IS NOT ON THIS RAIL.
       This map is measured in `vocab.unit`; a venue quotes a tennis match in
       BOTH games and sets, and both parse to the same `(side, threshold)` key.
       On the US Open men's semi-final that collision withheld the real game
       rung as a disagreement and left a SET rung to draw the projection —
       `TIA by 1.5+` over a hero reading Tiafoe 27%. A rung that states no unit
       is kept, which is every points sport; see `spreadRungMatchesRail`. */
    const parsedRaw = parseSpreadRungs(fullGameSpreads, homeTeam, awayTeam, vocab.unit);

    // One rung per (side, threshold). Duplicates arrive when several games'
    // markets are linked to one event; see collapseDuplicateRungs.
    const parsed = collapseDuplicateRungs(
      parsedRaw,
      (p) => `${p.isHome ? "H" : "A"}|${p.threshold}`,
      (p) => p.probability,
    ).rows;

    if (parsed.length === 0) return null;

    // #2441: the rail's reach is DECLARED by the sport, not inferred from a
    // three-name low-scoring list with basketball as the else. That else is
    // what labelled a tennis rail `WAW by 18+ / BER by 18+`.
    /* ux/1034 B5: is there a scoreboard half to this map at all? `homeScore` is
       already nulled for a sport whose scoreboard counts something else, so
       this one test governs the marker AND the "expected vs final" grading —
       a title that promises a comparison the card cannot draw is the same
       defect one level up. */
    const hasScoreboard = homeScore != null && awayScore != null;

    const maxMargin = vocab.marginRange;
    const rangeMin = -maxMargin;
    const rangeMax = maxMargin;

    const density = buildDensityFromSpreads(parsed, rangeMin, rangeMax, 12);
    const bandDrawsShape = densityDrawsShape(density, MARGIN_ACCENT);

    /* #6359: AND THE BADGE OVER THIS CARD IS TENSED TOO — IT WAS THE LAST OF
       THE THREE THAT WAS NOT.
       `/events/15306857` (Gwangju FC 1 – 1 FC Anyang, FINAL) printed `ANY 62%`
       in the top-right, directly over its own PRE-GAME Tied / FINAL Tied tiles
       and four `not cleared` rungs. Anyang did not win; nothing on the badge
       said which tense it was in.
       The routed diagnosis — a stale pre-match snapshot — does not hold, and
       the distinction is why the fix is here rather than upstream. That event's
       `current_odds.captured_at` is 11:51:27Z against a 10:00Z kickoff and an
       11:56Z finish, so the quote is IN-PLAY, five minutes from full time. It
       is not stale. It is a win probability, which is a question a settled card
       has already answered — a fresher capture would not have helped, because
       on a DRAW no team's probability can converge and the last honest reading
       is whatever the market thought while it was still a question. A decisive
       result hides this: the last capture converges to ~100% for the winner, so
       the badge reads as a result everywhere except the one class (~25% of
       soccer fixtures) where the reader cannot tell.
       So it is a tense defect, and the file already rules it twice — the pace
       card's `headlineValue` (#5206) and the totals card's `headlineVal`
       (`isDone ? "" : …`, in the SAME "expected vs final" family two cards
       below this one, which is why the production screenshot shows one card
       tensed and its neighbour not). `isDone`, the same predicate the rungs
       below grade on, so the card's two halves cannot disagree about which
       tense it is in.
       A settled card says nothing here rather than saying it carefully: the
       result is already on the card twice (the FINAL tile and the graded
       ladder), so a label would only add a second voice, and notice 34's rule
       for the empty case is to leave it empty. `live` and `pre` keep the badge
       — there it is a current reading of an open question. */
    const homeFavored = (homeWinProb ?? 0) > 0.5;
    const favoredAbbr = homeFavored ? hAbbr : aAbbr;
    const favoredProb = homeFavored ? homeWinProb : awayWinProb;
    /* #6853: A LIVE GAME IS NEVER 100%.
       This was `${Math.round(favoredProb * 100)}%`, an inline round that skips
       the boundary rule every other percent on the page goes through. On the
       marquee NFL game at 03:16Z, `2:50 - 4th Quarter`, `current_odds` served
       `home_probability 0.999` and this card headlined **`BUF 100%`** one screen
       below a hero reading **`>99%`** off the same number — a certainty claim on
       a game that was still being played, contradicted by the page itself.
       `formatProbability` is the function the hero uses, and its docstring
       already states the rule this needs: "a served 100 over a probability of
       0.996 is still `>99%`, because rounding may never move a probability
       across a boundary it is not on". Every value inside 1–99% prints
       identically, so this changes exactly the two ends that were lying.
       Population: the closing stretch of any one-sided game — the window a
       reader is most likely to have the page open.
       The `isDone` arm is untouched: a settled card prints no headline here at
       all (#5206), because the result is already on the card twice. */
    const headline = isDone || favoredProb == null
      ? ""
      : `${favoredAbbr} ${formatProbability(favoredProb)}`;

    const markers: MarketMapMarker[] = [];

    // #5414: THE QUOTED PRE-GAME LINE FIRST — see `openingHomeSpread`.
    //
    // Every marker built from `projValue` below is labelled `Pre-game` or is
    // the `pre` arm's forecast, so the pre-game quote is the number they are
    // all asking for. It is ungated by `hasDerivedSpread` because it is a line
    // the books quoted, not one this page derived; the docstring on the prop
    // carries the reasoning and the measurement.
    //
    // `!= null`, not truthiness: a pick'em opens at exactly 0.0, and
    // `-0` is still a number that must reach the "Tied" label below rather
    // than fall through to the rung fallback as if no line existed.
    //
    // #2441 (unchanged in what it gates, now the SECOND rung): `homeSpread` is
    // the LATEST snapshot's figure, and it is still gated on
    // `hasDerivedSpread`, because on a sport that declares no derived spread
    // this page has no standing to draw one.
    //
    // ⚠️ **AND IT IS ADMISSIBLE ONLY WHILE `status === "pre"`.** That is new
    // here, and it is what makes correcting its spelling safe. `page.tsx` fed
    // this prop `current_odds.home_spread`, a key the API has never emitted
    // (it serialises the same column as `spread`), so the rung has never once
    // fired on the event page and the rung fallback below is what every reader
    // has actually been shown. Spelling it correctly without a tense rule
    // would have switched it ON for live and settled games — where the marker
    // it feeds is labelled `Pre-game` and the latest snapshot is emphatically
    // not a pre-game quantity (event 15310077's was -7.9 on a game that opened
    // at -1.5). Before the game starts the two tenses coincide and the fresher
    // number is the better one, so `pre` keeps it.
    // #8721: AND ONLY WHERE THE SPORTSBOOKS' SPREAD IS A MARGIN AT ALL. For
    // baseball it is the run line, a ±1.5 handicap whatever the matchup (#8617's
    // flag). Measured on production 2026-09-25 21:42Z: `/events/15318545`, Cubs @
    // Red Sox at 48% – 52%, opening spread 1.5 and current 1.1, printed
    // `PRE-GAME CHC by 1.5+` and `PROJECTION CHC by 1.5+` above a ladder pricing
    // "Cubs by 2+" at 37%. Both sportsbook values stop here; the ladder and the
    // scoreboard tiles are untouched.
    const sportsbookSpreadIsAMargin = vocab.sportsbookSpreadIsAMargin;
    let projValue =
      sportsbookSpreadIsAMargin && openingHomeSpread != null ? -openingHomeSpread : null;
    if (projValue == null && status === "pre") {
      projValue =
        sportsbookSpreadIsAMargin && vocab.hasDerivedSpread && homeSpread != null ? -homeSpread : null;
    }
    // CERT-2674: AND THE RUNG FALLBACK IS A PRE-STATUS FALLBACK TOO.
    //
    // The first cut of this fix left the fallback reachable on `live` and
    // `done`, where the marker it feeds is labelled `Pre-game` — so a card with
    // no opening line went on presenting a CURRENT rung as the pre-game
    // reading, which is the whole defect, surviving in the 9.5% of events that
    // carry no opening spread. Worse on a settled card: #3769 measured that a
    // finished match's rung prices are the RESOLVED ones (0.0005 on both of
    // Paul–Alcaraz's), so "closest to a coin flip" there is not a market
    // opinion at all, it is an artefact of settlement.
    //
    // A tile with nothing true to say says nothing: `projValue` stays null, the
    // three arms below are already each guarded on `projValue != null`, and the
    // `Pre-game` marker is simply not drawn. Alex's rule for the empty case —
    // leave the space empty, do not explain the emptiness (notice 34).
    //
    // On `pre` the fallback stands and must: the marker there is `Projection`,
    // an unplayed game's quoted rungs are live pre-game quotes, and it is the
    // only number many a scheduled card has.
    if (projValue == null && status === "pre" && parsed.length > 0) {
      const closest = parsed.reduce((best, s) =>
        Math.abs(s.probability - 0.5) < Math.abs(best.probability - 0.5) ? s : best
      );
      // #8721: the rung stands in for the run line only if the market makes it
      // at least even money. A baseball ladder's smallest cut is 1.5 runs, so on
      // a close game the rung nearest a coin flip is a long shot ("Cubs by 2+" at
      // 37%), and `Projection CHC by 1.5+` would be the run line again, spelled
      // from Kalshi. Scoped to the sports #8617 flags; a dense points ladder
      // always has a rung near 50% and keeps its reading.
      if (sportsbookSpreadIsAMargin || closest.probability >= 0.5) {
        projValue = closest.isHome ? closest.threshold : -closest.threshold;
      }
    }
    const projTeamAbbr = projValue != null ? (projValue > 0 ? hAbbr : projValue < 0 ? aAbbr : "TIE") : null;
    const projLogo = projValue != null ? (projValue > 0 ? homeLogo : awayLogo) : undefined;

    // #5045: AND A SECOND, LIVE VALUE — because `Pre-game` and `Projection`
    // are two different tenses and a card cannot say both with one number.
    //
    // #5414 repointed `projValue` at the frozen opening line, which made the
    // `Pre-game` tile honest and, on the `live` arm below, left `Projection`
    // printing that same pre-game number under a forward-looking word. The lie
    // changed sides rather than going away. Measured on production
    // 2026-09-12 13:50Z, `/events/15297956` Genoa 0-1 Frosinone, live at 19' —
    // payload and frame read in the SAME command, because every number here
    // moves:
    //
    //   opening_odds.spread  -0.5  → both tiles printed `GEN by 0.5+`
    //   current_odds.spread  +0.5  → the live market says `FRO by 0.5+`
    //   current_odds.home_probability 0.2958, projected score 1.0 — 1.5
    //
    // So the card named Genoa as the projected winner on a screen whose own
    // header read `FRO 66%` and whose own ACTUAL read `FRO by 1+`. The `1st
    // half` margin map beside it got `FRO by 1.5+` right off its live ladder —
    // the working control on the same screen, and the shape copied here.
    //
    // ⚠️ **`hasDerivedSpread` GATES THIS ONE AND NOT `projValue`**, and the
    // asymmetry is #2441's, not a slip: the opening line is a quote a venue
    // published, while this is the latest snapshot of the same column and is
    // what that ruling governs (see the `homeSpread` note at the top of this
    // block). Tennis therefore keeps its `Pre-game` tile and draws no live
    // projection, which is the honest pair for a sport this page may not
    // invent a spread for.
    const liveProjValue =
      sportsbookSpreadIsAMargin && vocab.hasDerivedSpread && homeSpread != null ? -homeSpread : null;
    const liveProjTeamAbbr =
      liveProjValue != null ? (liveProjValue > 0 ? hAbbr : liveProjValue < 0 ? aAbbr : "TIE") : null;
    const liveProjLogo =
      liveProjValue != null ? (liveProjValue > 0 ? homeLogo : awayLogo) : undefined;

    // #2442: the SECOND margin formatter on this page, and the one the sweep
    // for `formatMarginLabel` missed — the render guard caught it printing
    // `LAL +4.5` on the projection mark after the ladder had already been
    // fixed. Both now route through `marginLadderLabel`, so there is one
    // grammar and a third copy cannot quietly disagree with the other two.
    function formatMargin(val: number, team: string): string {
      if (val === 0) return "Tied";
      return marginLadderLabel(
        team,
        Math.abs(val) % 1 === 0 ? Math.abs(val) : Math.abs(val).toFixed(1)
      );
    }

    if (status === "pre") {
      if (projValue != null) {
        // #5206: past tense for a match nobody reported — see `noForecast`.
        markers.push({
          key: noForecast ? "pre" : "proj",
          value: projValue,
          type: noForecast ? "pre" : "proj",
          label: noForecast ? "Pre-game" : "Projection",
          displayValue: formatMargin(projValue, projTeamAbbr || ""),
          logoUrl: noForecast ? undefined : projLogo,
          logoFallback: noForecast ? undefined : projTeamAbbr || "",
        });
      }
    } else if (status === "live") {
      const actualMargin = homeScore != null && awayScore != null ? homeScore - awayScore : null;
      if (actualMargin != null) {
        const actualTeam = actualMargin > 0 ? hAbbr : actualMargin < 0 ? aAbbr : "TIE";
        markers.push({
          key: "actual",
          value: actualMargin,
          type: "actual",
          label: "Actual",
          // #7380: the scoreboard, not a rung — see `exactMarginLabel`.
          displayValue: exactMarginLabel(actualTeam, actualMargin),
        });
      }
      // #5045: ONE GUARD PER TILE, because they now hold two different
      // quantities and either can exist without the other. A live card with an
      // opening line and no current spread shows PRE-GAME alone; one with a
      // current spread and no opening line shows PROJECTION alone.
      if (projValue != null) {
        markers.push({
          key: "pre",
          value: projValue,
          type: "pre",
          label: "Pre-game",
          displayValue: formatMargin(projValue, projTeamAbbr || ""),
        });
      }
      // A tile with nothing true to say says nothing (notice 34): where the
      // live spread is absent — or gated off by #2441 — the `Projection` tile
      // is simply not drawn, rather than falling back to the pre-game number
      // and restating it under the other tense, which is the defect.
      if (liveProjValue != null) {
        markers.push({
          key: "proj",
          value: liveProjValue,
          type: "proj",
          label: "Projection",
          displayValue: formatMargin(liveProjValue, liveProjTeamAbbr || ""),
          logoUrl: liveProjLogo,
          logoFallback: liveProjTeamAbbr || "",
        });
      }
    } else {
      const finalMargin = homeScore != null && awayScore != null ? homeScore - awayScore : null;
      if (projValue != null) {
        markers.push({
          key: "pre",
          value: projValue,
          type: "pre",
          label: "Pre-game",
          displayValue: formatMargin(projValue, projTeamAbbr || ""),
        });
      }
      if (finalMargin != null) {
        const finalTeam = finalMargin > 0 ? hAbbr : finalMargin < 0 ? aAbbr : "TIE";
        markers.push({
          key: "final",
          value: finalMargin,
          type: "final",
          label: "Final",
          // #7380: the scoreboard, not a rung — see `exactMarginLabel`.
          displayValue: exactMarginLabel(finalTeam, finalMargin),
        });
      }
    }

    /* #6203: gated on the same `status === "done"` + scoreboard test the title
       and the FINAL marker are gated on, so the ladder grades exactly when the
       rail draws the number it grades against — #3769's rule for the totals
       card, and the reason a card can never promise a comparison it cannot
       make. Spelled out rather than reusing `hasScoreboard` so the nulls
       narrow. */
    const finalMarginGraded =
      status === "done" && homeScore != null && awayScore != null
        ? homeScore - awayScore
        : null;

    const ladder: MarketMapLadderRow[] = [];
    const homeSorted = parsed.filter((p) => p.isHome).sort((a, b) => a.threshold - b.threshold);
    const awaySorted = parsed.filter((p) => !p.isHome).sort((a, b) => a.threshold - b.threshold);

    for (const s of awaySorted.reverse()) {
      ladder.push({
        label: marginLadderLabel(aAbbr, s.threshold),
        probability: Math.round(s.probability * 100),
        side: "left",
        outcome: gradeMarginRung(finalMarginGraded, false, s.threshold),
      });
    }
    for (const s of homeSorted) {
      ladder.push({
        label: marginLadderLabel(hAbbr, s.threshold),
        probability: Math.round(s.probability * 100),
        side: "right",
        outcome: gradeMarginRung(finalMarginGraded, true, s.threshold),
      });
    }

    return {
      // L2-131 Item 4: a settled game grades the distribution — actual final
      // margin vs the pregame mass — so it reads "expected vs final".
      title: status === "done" && hasScoreboard
        ? "Margin: expected vs final"
        // #2441: the title is the DECLARED one, not "Full game " + it.
        // Prefixing stuttered the moment a sport's unit was the word "game"
        // ("Full game game margin map"), and every declared title already
        // names the scope. The half maps below carry their own period label,
        // so the contrast this prefix used to draw is still drawn.
        : vocab.marginTitle,
      subtitle: unitMismatchNote
        // ux/1034 B5: this card cannot say where it landed, and says so rather
        // than grading three sets against a game-and-a-half line.
        ? unitMismatchNote
        : status === "done" && hasScoreboard
        // #2442: "the pregame spread" is a betting line. What the sentence
        // means is the distribution the market had before play, which is
        // what the reader is looking at on the rail beside it.
        ? "Where it landed vs what was expected"
        // #3210, the same tense bug on the map directly above the totals one.
        // Fixed in the same pass deliberately: leaving it would put "Final
        // margin distribution" and "Where it's heading vs what was expected"
        // on two rails of one live card, which is worse than the bug.
        : status === "live" && hasScoreboard
        ? "Where it's heading vs what was expected"
        // #3210: and a card that draws no shape does not call itself a
        // distribution. The two live/settled sentences above are about the
        // MARKERS, which are drawn either way — only this one is a claim about
        // the band, so only this one is answerable by the band.
        : bandDrawsShape
        // #3593: `distributionTense`, not the literal "Final". This arm is the
        // fall-through, so it is what a PRE-GAME card gets — and it was telling
        // the reader of an unplayed game where its margin finally landed.
        ? `${distributionTense(status)} ${vocab.unit === "runs" ? "run-" : vocab.unit === "goals" ? "goal-" : ""}margin distribution`
        : quotedLinesPhrase(ladder.length),
      headline,
      rangeMin,
      rangeMax,
      density,
      bandDrawsShape,
      accentRgb: MARGIN_ACCENT,
      axisLabels: {
        left: `${aAbbr} by ${maxMargin}+`,
        mid: "0",
        right: `${hAbbr} by ${maxMargin}+`,
      },
      zeroPosition: 0,
      markers,
      ladder,
    };
  }, [gameMarkets.spreads, status, isDone, homeScore, awayScore, homeWinProb, awayWinProb, homeSpread, openingHomeSpread, homeTeam, awayTeam, hAbbr, aAbbr, homeLogo, awayLogo, sportKey, vocab]);

  // ── Total Map ──
  const totalData = useMemo(() => {
    // #3240: the selection lives in `marketMapUtils` so the Score Differential
    // note can ask whether THIS card renders instead of guessing from whether
    // the page happens to hold a played count.
    const gameTotals = selectGameTotalRungs(gameMarkets.totals, eventStatus);

    if (gameTotals.length === 0) return null;

    const ouLine = gameTotals.reduce((closest, t) =>
      Math.abs(t.over_probability - 0.5) < Math.abs(closest.over_probability - 0.5) ? t : closest
    );

    const minThresh = gameTotals[0].threshold;
    const maxThresh = gameTotals[gameTotals.length - 1].threshold;
    const actualTotal = homeScore != null && awayScore != null ? homeScore + awayScore : null;
    const paceProj = (vocab.scoreboardCountsTheUnit ? gameMarkets.pace?.projected_total : null) ?? null;
    const allValues = [minThresh, maxThresh];
    if (actualTotal != null) allValues.push(actualTotal);
    if (paceProj != null) allValues.push(paceProj);
    if (overUnder != null) allValues.push(overUnder);
    // #5414: the number `ouVal` now prefers has to be inside the rail it is
    // drawn on, or the marker pins to an end and reads as an extreme.
    if (openingOverUnder != null) allValues.push(openingOverUnder);
    const dataMin = Math.min(...allValues);
    const dataMax = Math.max(...allValues);
    const span = dataMax - dataMin;
    const pad = Math.max(span * 0.15, 3);
    const rangeMin = Math.max(0, Math.floor(dataMin - pad));
    const rangeMax = Math.ceil(dataMax + pad);

    const density = buildDensityFromThresholds(
      gameTotals.map((t) => ({ threshold: t.threshold, overProbability: t.over_probability })),
      rangeMin,
      rangeMax,
      12
    );
    const bandDrawsShape = densityDrawsShape(density, TOTAL_ACCENT);

    /* ux/1034 B5: `pace` is derived from the same scoreboard, so it inherits
       the same unit. Dropping it with the scores keeps "Projected 6" — a
       set-count run forward — off a rail that reads to 40 games. */
    const pace = vocab.scoreboardCountsTheUnit ? gameMarkets.pace : null;
    const scored = pace?.total_scored ?? (homeScore != null && awayScore != null ? homeScore + awayScore : null);
    /* #6831: A RUN-FORWARD OF NOTHING IS NOT A FORECAST.
       `pace.projected_total` is the score so far extrapolated over the whole
       game — measured on `/events/14638444` at 00:29Z, `total_scored 6` with
       `fraction_elapsed 0.097` gave `projected_total 62`, i.e. exactly
       `scored / elapsed`. So a scoreless game projects 0 at EVERY elapsed
       fraction, and 0 is not null: both consumers below drew it. On tonight's
       marquee NFL game, 11:08 into the 1st quarter at 0 – 0, this card headlined
       "Projected 0" over its own `PRE-GAME 55` tile while the hero one screen up
       read "Projected final: 32 – 24".
       That is every live game between kickoff and the first score, which is the
       window a reader is most likely to be watching.
       This file already declines rather than fabricates twice — #5206's
       `noForecast` and the neighbouring card's `isDone ? "" : …` — but both of
       those rule on TENSE. Here the tense is right and the VALUE has no standing,
       so it is the same posture on a new axis. Dropped at the single binding the
       headline and the marker share, so the two halves of the card cannot
       disagree about whether there is a projection at all.
       `> 0` rather than `!= 0`: it also refuses a negative, which the estimator
       cannot currently emit — this is the value we PRINT, so it is guarded on
       what makes it printable, not on the upstream formula that happens to
       produce it today.
       Deliberately NOT touched: `paceProj` at the top of this block, which only
       widens the rail's range. `actualTotal` already pushes the same 0, so the
       rail is unchanged either way, and leaving it keeps this diff to the one
       question it is answering. */
    const projectedRaw = pace?.projected_total ?? null;
    const projected = projectedRaw != null && projectedRaw > 0 ? projectedRaw : null;
    // #5414: the quoted pre-game total first, for the same reason the margin
    // map takes the quoted pre-game spread first — this value feeds a marker
    // labelled `Pre-game` on the live and settled arms, and `overUnder` is the
    // LATEST snapshot's total, which on a finished game is not a pre-game
    // quantity. Fixed on the same pass as the margin one deliberately: the two
    // rails sit on ONE card, and #3210's own finding on this file is that
    // fixing one and leaving the other is worse than the bug.
    //
    // `??`, so an opening total of 0 would be taken rather than skipped — the
    // pick'em reasoning on `openingHomeSpread` applied to the other rail.
    //
    // And `overUnder` survives only on `pre`, the same tense rule the margin
    // rail applies to `homeSpread`: once play starts, the latest total under a
    // `Pre-game` label is a wrong answer.
    //
    // CERT-2674: and `ouLine.threshold` is a PRE-STATUS fallback for the same
    // reason the margin rail's rung fallback is — on a live or settled card the
    // marker this feeds is labelled `Pre-game`, and #3769 measured that a
    // finished match's rung prices are the RESOLVED ones, so the
    // nearest-to-even rung there is an artefact of settlement rather than an
    // opinion anyone held before play. Nullable, and both arms below draw the
    // marker only when it is a real pre-game reading.
    const ouVal: number | null =
      openingOverUnder ?? (status === "pre" ? overUnder ?? ouLine.threshold : null);

    // #5206: `Projected 3` on a match nobody reported was the headline in the
    // bug report. In `pre` this number is just the over/under LINE rounded — a
    // quote, dressed as a forecast — so an unreported match shows no headline
    // at all rather than a projection it has no standing to make.
    // CERT-2674: `ouVal` is nullable now, and on `pre` it cannot be null —
    // `ouLine.threshold` is that arm's final fallback and `gameTotals` is
    // non-empty by the early return above. The `?? ouLine.threshold` is here so
    // the compiler knows it, not because the branch can be reached.
    const headlineValue = status === "pre"
      ? noForecast
        ? ""
        : `Projected ${Math.round(ouVal ?? ouLine.threshold)}`
      : status === "live" && projected != null
      ? `Projected ${Math.round(projected)}`
      : "";

    const markers: MarketMapMarker[] = [];

    if (status === "pre") {
      // CERT-2674: see `headlineValue` — on this arm `ouVal` cannot be null.
      const preVal = ouVal ?? ouLine.threshold;
      markers.push({
        key: noForecast ? "pre" : "proj",
        value: preVal,
        type: noForecast ? "pre" : "proj",
        // #5206: past tense for a match nobody reported — see `noForecast`.
        label: noForecast ? "Pre-game" : "Projection",
        displayValue: String(Math.round(preVal)),
        // #3360: the ring carries its own number. `hideTile: true` means this
        // marker draws NO tile underneath, so the dot was the only mark on the
        // rail and it was empty — a 26px ring with nothing in it, which reads
        // as a missing value rather than a marker. `logoFallback` is what
        // MarketMap renders inside a `proj` dot.
        //
        // #5206: a `pre` mark draws its own TILE, so it needs neither the
        // fallback nor `hideTile` — carrying them over would hide the only mark
        // on the rail and reproduce #3360 in the arm this fix creates.
        logoFallback: noForecast ? undefined : String(Math.round(preVal)),
        hideTile: noForecast ? undefined : true,
      });
    } else if (status === "live") {
      if (scored != null) {
        markers.push({
          key: "actual",
          value: scored,
          type: "actual",
          label: "Actual",
          displayValue: withUnit(scored, vocab),
        });
      }
      // CERT-2674: only when there IS a pre-game reading. With no opening total
      // this rail used to label the nearest-to-even CURRENT rung `Pre-game` —
      // and on a settled card those prices are the RESOLVED ones (#3769), so it
      // was an artefact of settlement wearing a pre-game label. No number, no
      // marker; the rail, the band and the ladder are all still drawn.
      if (ouVal != null) {
        markers.push({
          key: "pre",
          value: ouVal,
          type: "pre",
          label: "Pre-game",
          displayValue: String(Math.round(ouVal)),
        });
      }
      if (projected != null) {
        markers.push({
          key: "proj",
          value: projected,
          type: "proj",
          label: "Projection",
          displayValue: String(projected.toFixed(1)),
          // #3360: rounded, not `toFixed(1)`. Measured in the real browser on
          // the real dot (Inter, 8px, weight 950, 22px inner box): "36.4" is
          // 20.72px and only just fits, but "108.5" is 25.36px and OVERFLOWS a
          // 26px ring — so the one-decimal string was already broken for every
          // high-total sport, tennis simply never reached three digits. The
          // tile below still carries the decimal via `displayValue`.
          logoFallback: String(Math.round(projected)),
        });
      }
    } else {
      // CERT-2674: only when there IS a pre-game reading. With no opening total
      // this rail used to label the nearest-to-even CURRENT rung `Pre-game` —
      // and on a settled card those prices are the RESOLVED ones (#3769), so it
      // was an artefact of settlement wearing a pre-game label. No number, no
      // marker; the rail, the band and the ladder are all still drawn.
      if (ouVal != null) {
        markers.push({
          key: "pre",
          value: ouVal,
          type: "pre",
          label: "Pre-game",
          displayValue: String(Math.round(ouVal)),
        });
      }
      if (scored != null) {
        markers.push({
          key: "final",
          value: scored,
          type: "final",
          label: "Final",
          displayValue: withUnit(scored, vocab),
        });
      }
    }

    /* #3769: on a settled match `over_probability` is the RESOLVED price, not
       the pregame one — production served 0.0005 for both of Paul–Alcaraz's
       rungs while the scheduled control served 0.445 — so a done ladder grades
       against the final instead of quoting it. Gated on the same `scored` the
       FINAL marker is gated on (see the `status === "live"` note below), so the
       ladder grades exactly when the rail draws the number it grades against:
       if `scored` is the wrong unit the tile above is already wrong, and the
       two must not disagree about one card. */
    const gradeAgainst = status === "done" ? scored : null;
    const gradeRung = (threshold: number): MarketMapLadderRow["outcome"] =>
      gradeAgainst == null ? undefined : gradeAgainst > threshold ? "cleared" : "missed";
    const ladder: MarketMapLadderRow[] = gameTotals.map((t) => ({
      label: `Over ${t.threshold}`,
      probability: Math.round(t.over_probability * 100),
      side: "right" as const,
      outcome: gradeRung(t.threshold),
    }));

    const midLabel = String(Math.round((rangeMin + rangeMax) / 2));

    return {
      // L2-131 Item 4: settled totals grade expected vs final, same as margins.
      title: status === "done" && scored != null
        ? "Total: expected vs final"
        : vocab.totalTitle,
      subtitle: unitMismatchNote
        // ux/1034 B5: `FINAL 3 games` on this card was three SETS, summed, over
        // a rail whose pre-game mark was 35 GAMES.
        ? unitMismatchNote
        : status === "done" && scored != null
        // #2442's wording, through #2441's unit helper: an undeclared sport
        // has no unit to interpolate, and inlining it produced "Final
        // distribution" with a double space.
        ? "Where it landed vs what was expected"
        // #3210: THREE TENSES, NOT TWO. This used to be the `else` of "done",
        // so a match in play was told where its games "Final"-ly landed while
        // an ACTUAL rung sat on the rail beside it counting them as they were
        // played (confirmed live 2026-09-05 on `/events/15304420`: `ACTUAL 14
        // games` under "Final games distribution", second set in progress).
        // The data was present-tense and only the sentence was past-tense.
        // Gated on the same `scored` the ACTUAL marker is gated on, so the
        // sentence promises a comparison exactly when the rail draws one.
        : status === "live" && scored != null
        ? "Where it's heading vs what was expected"
        // #3210's own body: two match-scope rungs 4 games apart, spread over 12
        // segments, paint one solid purple block. `densityDrawsShape` asks the
        // rail what colours it would use, so this arm fires on exactly the
        // cards a reader sees as flat — including `/events/15304420`, whose
        // THREE rungs were all quoted at 0.20 and are just as shapeless as two.
        : bandDrawsShape
        // #3593: same fall-through, same fix, same card. "Projected 8" over
        // "Final runs distribution" was one card in two tenses about one
        // unplayed game (`/events/15305464`, 2026-09-06).
        ? unitPhrase(distributionTense(status), vocab, "distribution")
        : quotedLinesPhrase(ladder.length),
      headline: headlineValue,
      rangeMin,
      rangeMax,
      density,
      bandDrawsShape,
      accentRgb: TOTAL_ACCENT,
      axisLabels: { left: String(rangeMin), mid: midLabel, right: `${rangeMax}+` },
      markers,
      ladder,
    };
  }, [gameMarkets.totals, gameMarkets.pace, status, eventStatus, homeScore, awayScore, overUnder, openingOverUnder, vocab, sportKey]);

  // #3240: `derivePeriod` now lives in `marketMapUtils` beside the half-total
  // selector that also needs it.

  // ── Period Margin Maps (half spreads) ──
  const halfMarginMaps = useMemo(() => {
    const halfSpreads = (gameMarkets.period_markets || []).filter((s) => s.market_type === "half_spread");
    const halfGroups: Record<string, typeof halfSpreads> = {};
    for (const s of halfSpreads) {
      const key = derivePeriod(s);
      if (!halfGroups[key]) halfGroups[key] = [];
      halfGroups[key].push(s);
    }

    type MapData = Parameters<typeof MarketMap>[0] & { status: "pre" | "live" | "done" };
    const maps: Array<{ key: string; data: MapData }> = [];

    for (const half of ["1H", "2H"] as const) {
      const spreads = halfGroups[half];
      if (!spreads || spreads.length === 0) continue;

      // #4598: the same seam as the full-game rail above, deliberately the same
      // CALL and not the same rule written twice — see `parseSpreadRungs`.
      const rawParsedAll = parseSpreadRungs(spreads, homeTeam, awayTeam, vocab.unit);
      // Collapse before the monotonicity pass: equal duplicates satisfy
      // `prob <= lastProb` trivially, so that guard cannot remove them.
      const rawParsed = collapseDuplicateRungs(
        rawParsedAll,
        (p) => `${p.isHome ? "H" : "A"}|${p.threshold}`,
        (p) => p.probability,
      ).rows;
      if (rawParsed.length === 0) continue;

      // Enforce monotonicity per team: P(team wins by X) >= P(team wins by X+Y)
      const enforceMonotonic = (items: typeof rawParsed): typeof rawParsed => {
        const sorted = [...items].sort((a, b) => a.threshold - b.threshold);
        const clean: typeof rawParsed = [];
        let lastProb = 1.0;
        for (const s of sorted) {
          if (s.probability <= lastProb) {
            clean.push(s);
            lastProb = s.probability;
          }
        }
        return clean;
      };

      const homeClean = enforceMonotonic(rawParsed.filter((p) => p.isHome));
      const awayClean = enforceMonotonic(rawParsed.filter((p) => !p.isHome));
      const parsed = [...homeClean, ...awayClean];
      if (parsed.length === 0) continue;

      // #2441: same declared reach as the full-game rail above.
      const maxM = vocab.marginRange;
      const density = buildDensityFromSpreads(parsed, -maxM, maxM, 12);
      const bandDrawsShape = densityDrawsShape(density, MARGIN_ACCENT);

      // Ladder: sort sequentially along number line (away big → tie → home big)
      const allSorted = [...parsed].sort((a, b) => {
        const marginA = a.isHome ? a.threshold : -a.threshold;
        const marginB = b.isHome ? b.threshold : -b.threshold;
        return marginA - marginB;
      });
      /* #6203, the period half of the same rule. The half TOTALS card already
         grades (see its `gradeRung` below); leaving the half MARGIN card
         quoting would reproduce, one card lower, the exact two-tenses defect
         this ship is closing on the full-game pair. Same gate as this card's
         own FINAL marker — `isDone && halfScores` — computed ONCE so the marker
         and the grade cannot disagree about one card. */
      const halfFinalMargin =
        isDone && halfScores
          ? half === "1H"
            ? halfScores.h1Home - halfScores.h1Away
            : halfScores.h2Home - halfScores.h2Away
          : null;

      const ladder: MarketMapLadderRow[] = allSorted.map((s) => ({
        label: marginLadderLabel(s.isHome ? hAbbr : aAbbr, s.threshold),
        probability: Math.round(s.probability * 100),
        side: (s.isHome ? "right" : "left") as "left" | "right",
        outcome: gradeMarginRung(halfFinalMargin, s.isHome, s.threshold),
      }));

      // Find the closest-to-50% spread as the projection marker
      const closest50 = parsed.reduce((best, s) =>
        Math.abs(s.probability - 0.5) < Math.abs(best.probability - 0.5) ? s : best
      );
      const projMargin = closest50.isHome ? closest50.threshold : -closest50.threshold;
      const projTeam = projMargin > 0 ? hAbbr : projMargin < 0 ? aAbbr : "TIE";

      const label = halfLabel(half, vocab);

      const halfMarkers: MarketMapMarker[] = [];

      // Live actual for in-progress games (first, matching full game order)
      if (isLive && liveHalfScores) {
        const hs = half === "1H"
          ? { home: liveHalfScores.h1Home, away: liveHalfScores.h1Away }
          : liveHalfScores.h2Home != null && liveHalfScores.h2Away != null
            ? { home: liveHalfScores.h2Home, away: liveHalfScores.h2Away }
            : null;
        if (hs) {
          const margin = hs.home - hs.away;
          const team = margin > 0 ? hAbbr : margin < 0 ? aAbbr : "TIE";
          halfMarkers.push({
            key: "actual",
            value: margin,
            type: "actual",
            label: "Actual",
            // #7380: `JMU +13` was #2442's handicap spelling; one grammar now.
            displayValue: exactMarginLabel(team, margin),
          });
        }
      }

      // Projection / Pre-game spread.
      //
      // #5488: NOT on a finished half whose ladder has stopped quoting. The
      // marker's value is `closest50`, the rung nearest a coin flip in the
      // ladder AS IT STANDS. Before the whistle that is a reading. After it the
      // rungs are the settled ones, every one of them ~0.99 or ~0.01, and
      // "nearest a coin flip" returns whichever rung the step happens to sit on
      // — an artefact of where settlement landed, printed under a label that
      // claims somebody expected it. The full-game rail above escapes by
      // falling back to the frozen `opening_home_spread` (#5414); there is no
      // `opening_half_spread` column, so a half has no pre-game quantity at all
      // and the honest finished card carries no such tile.
      //
      // The test is the ladder's shape and NOT `isDone`, which is the same
      // choice #5143 made for the half TOTALS map below and pinned a control
      // against — see `settledHalfMapDropsFakePregame5143`. This is that rule's
      // body, reached through `probabilitiesQuoteALine` rather than copied, so
      // the two half maps cannot drift on where the interior is.
      //
      // Measured on production 2026-09-11 via `/api/events/<id>/game-markets`,
      // both settled and both failing the interior test: `/events/15303008`
      // (Stade Rennais 1-0 Marseille) printed `PRE-GAME OLM by 1.5+` on its 2nd
      // half off four rungs reading 0.02 / 0.005 / 0.01 / 0.01, and
      // `/events/15304450` (Boston College 28-21 Rutgers) carried 21 rungs of
      // which every single one is 0.99, 0.04 or 0.01.
      // #7639: the question is asked once PLAY HAS STARTED, not only once it
      // has stopped.
      //
      // `!isDone ||` made the GAME's status the gate on whether the ladder was
      // asked about its shape at all, and a half finishes long before its game
      // does. Seen at 390px on 2026-09-20 5:58 PM PDT, `/events/15312237`
      // (Inter Miami 1-1 San Diego, MLS, LIVE at 56'): the 1st half card read
      // `PROJECTION MIA by 1.5+` over a half that had already finished level,
      // beside a 2nd half card printing the identical tile in the identical
      // place on the rail. The venue's own `First Half Winner` in the same
      // payload read `Tie 0.99 / Miami 0.01 / San Diego 0.01`.
      //
      // Its 1H ladder, rendered: `SD by 1.5+ 1%`, `MIA by 1.5+ 1%`. Two rungs,
      // both settled, ZERO inside the interior band — the exact population
      // `probabilitiesQuoteALine` was written to refuse, and does refuse the
      // moment the game goes final. `closest50` over two equal 1% rungs elects
      // one arbitrarily, so even the TEAM on that tile was rung order.
      //
      // WHY NOT `quotesALine` ALONE. Because #5488 considered that and declined
      // it, and its CONTROL says so in as many words: before the whistle a dead
      // half ladder is a book that has not opened yet, the marker is still a
      // projection off a live game, and the shape test has no business removing
      // it. That control renders `scheduled` and stands untouched here. What it
      // did not have in view is the state between its two: a game in play, where
      // a dead half ladder is a book that has CLOSED. Kickoff is the line
      // between those two readings of the same silence, so kickoff is the gate.
      const playHasStarted = isLive || isDone;
      // #8721, one card lower: the full-game rail's rule for a sport whose
      // sportsbook spread is not a margin (baseball). There a rung stands in
      // for a projection only before first pitch and only at even money or
      // better. Kalshi's smallest First 5 cut is 1.5 runs, so on
      // `/events/15318868` (Dodgers @ Giants, LAD 75%) the rung nearest a coin
      // flip was "SF -1.5 first 5 innings" at 24% — the iPhone printed
      // `PRE-GAME SF by 1.5+` off it (native, PR #8775). Points sports keep
      // `closest50` whatever its price: a dense ladder always has a rung near 50%.
      const halfRungIsAProjection =
        vocab.sportsbookSpreadIsAMargin || (!playHasStarted && closest50.probability >= 0.5);
      if (
        halfRungIsAProjection &&
        (!playHasStarted || probabilitiesQuoteALine(parsed.map((p) => p.probability)))
      ) {
        halfMarkers.push({
          key: "proj",
          // #5206: the half maps already made this exact distinction for a
          // finished game; an unreported match earns it for the same reason.
          type: isDone || noForecast ? "pre" : "proj",
          value: projMargin,
          label: isDone || noForecast ? "Pre-game" : "Projection",
          displayValue: formatMarginLabel(projMargin, projTeam, closest50.threshold),
          logoFallback: projTeam,
        });
      }

      // Final actual for completed games
      if (isDone && halfScores) {
        const hs = half === "1H"
          ? { home: halfScores.h1Home, away: halfScores.h1Away }
          : { home: halfScores.h2Home, away: halfScores.h2Away };
        const margin = hs.home - hs.away;
        const team = margin > 0 ? hAbbr : margin < 0 ? aAbbr : "TIE";
        halfMarkers.push({
          key: "final",
          value: margin,
          type: "final",
          label: "Final",
          // #7380: `JMU +13` was #2442's handicap spelling; one grammar now.
          displayValue: exactMarginLabel(team, margin),
        });
      }

      maps.push({
        key: `margin-${half}`,
        data: {
          variant: "margin" as const,
          title: `${label} margin`,
          // #3210, same rule as the full-game rail above it: a period card with
          // no shape in its band names its rungs instead of promising a curve.
          //
          // #6203 carries #6169's third arm across to the margin rail. A graded
          // ladder prints no percentage at all, so "Eight lines quoted" over
          // eight `cleared` rows names a thing the reader cannot see — and the
          // grading this ship adds is what newly makes that arm reachable here.
          // The full-game rail above needs no such arm: its `quotedLinesPhrase`
          // fall-through sits behind the `done && hasScoreboard` branch, which
          // is the same condition that grades, so a graded ladder can never
          // arrive there. Decided by the same `ladderGraded` the heading and the
          // rows are decided by, so the three cannot drift.
          subtitle: bandDrawsShape
            ? `${label} margin distribution`
            : ladderGraded(ladder)
            ? settledLinesPhrase(ladder.length)
            : quotedLinesPhrase(ladder.length),
          headline: "",
          rangeMin: -maxM,
          rangeMax: maxM,
          density,
          bandDrawsShape,
          accentRgb: MARGIN_ACCENT,
          axisLabels: { left: `${aAbbr} by ${maxM}+`, mid: "Tie", right: `${hAbbr} by ${maxM}+` },
          zeroPosition: 0,
          markers: halfMarkers,
          ladder,
          status,
        },
      });
    }
    return maps;
  }, [gameMarkets.period_markets, status, homeTeam, awayTeam, hAbbr, aAbbr, sportKey, vocab, isDone, isLive, halfScores, liveHalfScores, homeLogo, awayLogo]);

  // #5527: the halves' totals where no halftime row exists — see the card below.
  const halfTotalsFromGrades = useMemo(
    () =>
      settledHalfTotalsFromGrades(
        gameMarkets.period_markets,
        eventStatus,
        homeScore != null && awayScore != null ? homeScore + awayScore : null
      ),
    [gameMarkets.period_markets, eventStatus, homeScore, awayScore]
  );

  // ── Period Total Maps (half totals) ──
  const halfTotalMaps = useMemo(() => {
    const allPeriod = gameMarkets.period_markets || [];
    type MapData = Parameters<typeof MarketMap>[0] & { status: "pre" | "live" | "done" };
    const maps: Array<{ key: string; data: MapData }> = [];

    // #3240: grouping, collapse and the monotonicity pass moved to
    // `selectHalfTotalRungs` so this card and the Score Differential note are
    // gated on one selection rather than two that can drift apart.
    for (const halfKey of TOTAL_MAP_HALVES) {
      const cleaned = selectHalfTotalRungs(allPeriod, halfKey);
      if (cleaned.length === 0) continue;

      // #5013: this card IS its line — the headline, the marker and the band
      // all come off the same ladder — so a ladder that has stopped quoting
      // has nothing honest to draw and the half does not render. A finished
      // game keeps its card: those ladders are settled by definition, and what
      // that card carries is the half's actual score, not a forecast.
      //
      // #5143: and the PRE-GAME tile is a forecast, so `isDone` must not carry
      // it through. On SF@LAR (`/events/14632820`, Final 27-7) both halves
      // printed `PRE-GAME 8` inside a game whose own card printed `PRE-GAME 41`
      // — the same 8 twice, off two unrelated ladders. Both had settled to a
      // step (1H `7.5→0.99 … 17.5→0.01`, 2H `7.5→0.99 … 21.5→0.01`), every rung
      // is ~49 points from a coin flip, and the closest-to-50% reduce below
      // therefore keeps the FIRST — the lowest threshold. 7.5 rounds to 8.
      // The full-game card escapes only because it has a real line to fall back
      // on (`overUnder ?? ouLine.threshold`); a half has none.
      const quotesALine = ladderQuotesALine(cleaned);
      if (!isDone && !quotesALine) continue;

      // #5502: and after the whistle ONE interior rung is not a line either.
      // Settlement does not land on every rung at once — Rennes 1-0 Marseille
      // (`/events/15303008`) served a settled 2nd half of `0.5→0.99`,
      // `1.5→0.20`, `2.5→0.01`: the ends graded right against a one-goal half,
      // and the 0.20 is Over 1.5 resolved FALSE still wearing a live price. It
      // is the only rung inside the band, so the test above passes, `ouLine`
      // elects it, and the card printed `PRE-GAME 2`. A line that was really
      // there passes THROUGH the middle and leaves more than one rung in the
      // band. Settled cards only: a live ladder with one interior rung is
      // quoting, and #5143's control keeps the tile on a finished game whose
      // ladders did quote.
      const quotesAPreGameLine = isDone
        ? settledLadderQuotesALine(cleaned)
        : quotesALine;

      const ouLine = cleaned.reduce((best, t) =>
        Math.abs(t.overProbability - 0.5) < Math.abs(best.overProbability - 0.5) ? t : best
      );

      const dataMin = cleaned[0].threshold;
      const dataMax = cleaned[cleaned.length - 1].threshold;
      const span = dataMax - dataMin;
      const pad = Math.max(span * 0.15, 3);
      const rangeMin = Math.max(0, Math.floor(dataMin - pad));
      const rangeMax = Math.ceil(dataMax + pad);
      const density = buildDensityFromThresholds(cleaned, rangeMin, rangeMax, 12);

      /* #6169: THE HALF CARD GRADES TOO — it was the unbuilt half of #3769.
         That rule ("a done ladder grades against the final instead of quoting
         it") is implemented for the full-game total card at `gradeRung` above
         and was never implemented here, so this ladder carried no `outcome`,
         `ladderGraded()` was false for every half card ever rendered, and a
         finished half could only ever quote a price.

         Photographed on production 2026-09-14, `/events/14637256` (Giants 28
         Cowboys 20, SNF, Final): this card printed `FINAL 27 points` and, two
         inches below, `Over 7.5 … Over 24.5 — 50%` — seven lines a 27-point
         half had cleared, each called a coin flip, while the 1st half card
         beside it read correctly. The price is separately wrong there (#6169's
         serving half, `routes/events.py`), but the grade does not consult the
         price: it is decided by the score, so this card reads honestly whatever
         the ladder is quoting.

         Gated on the same `isDone && halfScores` the FINAL marker below is
         gated on — #3769's own rule that the ladder grades exactly when the
         card draws the number it grades against — and computed ONCE so the
         marker and the grade can never disagree about one card.

         #5527: and with no halftime row, the number the half ladders' own
         grades pin, checked against the game's final
         (`settledHalfTotalsFromGrades`). `/events/15194200` (Norway 3-2
         Denmark) has no ESPN history, so both halves printed `LAST QUOTE FOR
         GOING OVER` over rows the venue had called. Still a NUMBER, drawn as
         the FINAL marker and graded against like any other — the ESPN score
         wins wherever it exists. */
      const halfFinalTotal =
        isDone && halfScores
          ? halfKey === "1H"
            ? halfScores.h1Home + halfScores.h1Away
            : halfScores.h2Home + halfScores.h2Away
          : halfTotalsFromGrades[halfKey];
      const gradeRung = (threshold: number): MarketMapLadderRow["outcome"] =>
        halfFinalTotal == null ? undefined : halfFinalTotal > threshold ? "cleared" : "missed";

      const ladder: MarketMapLadderRow[] = cleaned.map((t) => ({
        label: `Over ${t.threshold}`,
        probability: Math.round(t.overProbability * 100),
        side: "right" as const,
        outcome: gradeRung(t.threshold),
      }));

      const midLabel = String(Math.round((rangeMin + rangeMax) / 2));
      const label = halfLabel(halfKey, vocab);

      const halfTotalMarkers: MarketMapMarker[] = [];

      // Live actual for in-progress games (first, matching full game order)
      if (isLive && liveHalfScores) {
        const ht = halfKey === "1H"
          ? liveHalfScores.h1Home + liveHalfScores.h1Away
          : liveHalfScores.h2Home != null && liveHalfScores.h2Away != null
            ? liveHalfScores.h2Home + liveHalfScores.h2Away
            : null;
        if (ht != null) {
          halfTotalMarkers.push({
            key: "actual",
            value: ht,
            type: "actual",
            label: "Actual",
            displayValue: withUnit(ht, vocab),
          });
        }
      }

      // Pre-game O/U — only where the ladder is actually quoting one. #5143:
      // on a settled ladder `ouLine` is the lowest rung rather than a line, and
      // a tile labelled "Pre-game" is a claim about what was expected. The card
      // keeps its FINAL below, which is the half's real score and the whole
      // reason #5013 let a finished game keep the card at all.
      if (quotesAPreGameLine) {
        halfTotalMarkers.push({
          key: "pre",
          value: ouLine.threshold,
          type: "pre",
          label: "Pre-game",
          displayValue: String(Math.round(ouLine.threshold)),
        });
      }

      // Final actual for completed games — the same number the ladder grades
      // against (#6169), read from the one binding above rather than recomputed.
      if (halfFinalTotal != null) {
        halfTotalMarkers.push({
          key: "final",
          value: halfFinalTotal,
          type: "final",
          label: "Final",
          displayValue: withUnit(halfFinalTotal, vocab),
        });
      }

      // Compute range that includes all marker values
      const allVals = halfTotalMarkers.map((m) => m.value);
      const effectiveMin = Math.max(0, Math.floor(Math.min(dataMin, ...allVals) - Math.max(span * 0.15, 3)));
      const effectiveMax = Math.ceil(Math.max(dataMax, ...allVals) + Math.max(span * 0.15, 3));
      const effectiveDensity = buildDensityFromThresholds(cleaned, effectiveMin, effectiveMax, 12);
      // The band this card actually paints is `effectiveDensity`, not the
      // `density` computed above off the un-widened range — ask the one that
      // renders.
      const bandDrawsShape = densityDrawsShape(effectiveDensity, TOTAL_ACCENT);
      const effectiveMid = String(Math.round((effectiveMin + effectiveMax) / 2));

      const headlineVal = isDone ? "" : `O/U ${Math.round(ouLine.threshold)}`;

      maps.push({
        key: `total-${halfKey}`,
        data: {
          variant: "total" as const,
          title: `${label} ${vocab.totalTitle.toLowerCase()}`,
          // #6169: and the sentence over the ladder moves with it. A graded
          // ladder prints no percentage at all, so "Eight lines quoted" over
          // eight `cleared` rows named a thing the reader cannot see — the same
          // one-card-two-tenses defect #3210 fixed above, arriving through the
          // grading this ship adds. Decided by the same `ladderGraded` the
          // heading and the rows are decided by, so the three cannot drift.
          subtitle: bandDrawsShape
            ? unitPhrase(label, vocab, "distribution")
            : ladderGraded(ladder)
            ? settledLinesPhrase(ladder.length)
            : quotedLinesPhrase(ladder.length),
          headline: headlineVal,
          rangeMin: effectiveMin,
          rangeMax: effectiveMax,
          density: effectiveDensity,
          bandDrawsShape,
          accentRgb: TOTAL_ACCENT,
          axisLabels: { left: String(effectiveMin), mid: effectiveMid, right: `${effectiveMax}+` },
          markers: halfTotalMarkers,
          ladder,
          status,
        },
      });
    }
    return maps;
  }, [gameMarkets.period_markets, status, vocab, isDone, isLive, halfScores, liveHalfScores, halfTotalsFromGrades]);

  // #3136: the headings below are counted, not assumed — see `mapColumnHeading`.
  // A tennis match has no halves, so its totals column has always held exactly
  // one card under a heading that said there were several.
  const marginCardCount = (marginData ? 1 : 0) + halfMarginMaps.length;
  const totalCardCount = (totalData ? 1 : 0) + halfTotalMaps.length;

  const hasMargin = marginCardCount > 0;
  const hasTotal = totalCardCount > 0;

  if (!hasMargin && !hasTotal) return null;

  return (
    <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
      {/* Left column: Margin maps grouped */}
      {hasMargin && (
        <div className="rounded-2xl border border-surface-border bg-surface-card/50 p-2 space-y-2">
          {/* The eyebrow names a column that GROUPS several cards, so it earns
              its space only when there is more than one to group. With a single
              card it printed that card's own title verbatim, immediately above
              it: a reader on the US Open SF page saw "GAME MARGIN MAP" in small
              grey caps and then "Game margin map" in the card beneath, and the
              same again for "GAMES MAP". Tennis has no halves, so the column can
              never hold more than one card and the duplicate was guaranteed on
              every tennis match page.

              D102 allows small grey type "where it makes sense and offers the
              reader value" — a label that repeats the heading 20px below it
              offers none.

              #2442, CERT-642's second finding. "Total maps" is the betting noun
              for an over/under and it survived the first sweep because the
              guard's fixture supplied no totals, so this column never rendered.
              Both headings come from the sport's declared vocabulary, like the
              titles inside them.

              #2441 adds the empty-unit arm: an UNDECLARED sport has no unit to
              build a heading from, and interpolating one produces " maps". So it
              falls back to the plain noun rather than to a guess. */}
          {marginCardCount > 1 && (
            <div className="px-2 pt-1 text-[10px] font-black uppercase tracking-widest text-text-muted">
              {mapColumnHeading(vocab.unit ? vocab.marginTitle : "Margin map", marginCardCount)}
            </div>
          )}
          {marginData && (
            <MarketMap variant="margin" {...marginData} status={status} />
          )}
          {halfMarginMaps.map((pm) => (
            <MarketMap key={pm.key} {...pm.data} />
          ))}
        </div>
      )}

      {/* Right column: Total maps grouped */}
      {hasTotal && (
        <div className="rounded-2xl border border-surface-border bg-surface-card/50 p-2 space-y-2">
          {/* Same rule as the margin column above. */}
          {totalCardCount > 1 && (
            <div className="px-2 pt-1 text-[10px] font-black uppercase tracking-widest text-text-muted">
              {mapColumnHeading(vocab.unit ? vocab.totalTitle : "Scoring map", totalCardCount)}
            </div>
          )}
          {totalData && (
            <MarketMap variant="total" {...totalData} status={status} />
          )}
          {halfTotalMaps.map((pm) => (
            <MarketMap key={pm.key} {...pm.data} />
          ))}
        </div>
      )}
    </div>
  );
}
