import { AGREEMENT_TOLERANCE } from "./otherMarketGroups";

export function posOnRail(value: number, min: number, max: number): number {
  return Math.max(0, Math.min(100, ((value - min) / (max - min)) * 100));
}

/**
 * Float slack on the tolerance comparison, matching `otherMarketGroups`:
 * `0.52 - 0.5` is `0.020000000000000018` in IEEE 754, so a bare `>` would
 * withhold a pair sitting EXACTLY at tolerance.
 */
const TOLERANCE_EPSILON = 1e-9;

export interface RungCollapseResult<T> {
  rows: T[];
  /** Redundant rows removed because their duplicates agreed. */
  collapsed: number;
  /** Rungs withheld because their duplicates disagreed beyond tolerance. */
  withheld: number;
}

/**
 * Collapse market-map rows that describe the SAME rung into one row each.
 *
 * Why this exists — measured on production 2026-08-09, event 15191147
 * (Athletics @ Boston Red Sox, final). Its `period_markets` bucket carried 28
 * `half_total` rows spanning only 7 real thresholds, because FOUR different
 * games' Kalshi tickers were linked to one event:
 *
 *   KXMLBF5TOTAL-26JUL27…, -26JUL28…, -26JUL29…, -26JUL30…  on an Aug 9 game.
 *
 * The 1st-half total ladder therefore painted every rung four times, and two
 * of those repeats disagreed outright — `Over 1.5` rendered as 99% immediately
 * above `Over 1.5` at 1%. The corruption is not only cosmetic: the duplicated
 * points are fed to `buildDensityFromThresholds`, which quadruples their
 * weight, and to the closest-to-50% `reduce` that places the pre-game O/U
 * marker, so a wrong line can be picked from a repeated point.
 *
 * The monotonicity filter downstream cannot catch this. It tests
 * `prob <= lastProb`, and equal duplicates pass trivially, so a run of four
 * identical rungs slides straight through the guard meant to keep the ladder
 * sane.
 *
 * Policy is deliberately IDENTICAL to the "Additional Markets" section
 * (UX-P037): duplicates that agree collapse to one row; duplicates that
 * materially disagree are WITHHELD, never averaged and never resolved by
 * picking the more extreme value. The event page gets one agreement rule, not
 * two — hence the shared `AGREEMENT_TOLERANCE` import rather than a second
 * constant. Showing both sides would be showing source divergence, which the
 * standing *"the blend is the product"* ruling forbids.
 *
 * The full-game `totals` path already deduped by threshold (keeping the
 * highest `bookmaker_count`); the period paths and both spread paths never
 * did. This closes that inconsistency rather than inventing a new rule.
 *
 * PURE: no I/O, no React. Input order is preserved.
 */
export function collapseDuplicateRungs<T>(
  rows: T[],
  keyOf: (row: T) => string,
  probOf: (row: T) => number,
): RungCollapseResult<T> {
  const order: string[] = [];
  const byKey = new Map<string, T[]>();

  for (const row of rows) {
    const key = keyOf(row);
    let bucket = byKey.get(key);
    if (!bucket) {
      bucket = [];
      byKey.set(key, bucket);
      order.push(key);
    }
    bucket.push(row);
  }

  const kept: T[] = [];
  let collapsed = 0;
  let withheld = 0;

  for (const key of order) {
    const group = byKey.get(key) as T[];
    if (group.length === 1) {
      kept.push(group[0]);
      continue;
    }

    const probs = group.map(probOf);
    const spread = Math.max(...probs) - Math.min(...probs);

    if (spread > AGREEMENT_TOLERANCE + TOLERANCE_EPSILON) {
      withheld += 1;
      continue;
    }

    kept.push(group[0]);
    collapsed += group.length - 1;
  }

  return { rows: kept, collapsed, withheld };
}

export function rgbaFromIntensity(intensity: number, rgb: string): string {
  const alpha = 0.10 + (intensity / 100) * 0.78;
  return `rgba(${rgb},${alpha.toFixed(2)})`;
}

/**
 * DOES THIS BAND DRAW A SHAPE, OR ONE FLAT COLOUR? (#3210)
 *
 * Alex, from a production LOOK of `/events/15304847` at 390px:
 *
 *   > The band underneath is a single flat purple block — the card promises a
 *   > distribution and draws none.
 *
 * ═══ WHY THE TEST IS THE RENDERED COLOUR AND NOT A RUNG COUNT ═══
 *
 * The obvious rule is "fewer than three rungs cannot describe a shape", and it
 * is true — `buildDensityFromThresholds` turns N thresholds into N−1 PDF
 * points, and with a single point every segment is assigned that same point's
 * density, so the rail comes out mathematically constant. Two rungs are the
 * common tennis case and that is the case in the issue.
 *
 * But a rung count is a PROXY, and the three events measured on production on
 * 2026-09-05 show it is the wrong one. `/events/15304420` had **three**
 * game-total rungs — 36.5, 38.5 and 40.5 — and every one of them was quoted at
 * `over_probability` 0.20. Three rungs, two PDF points, both with `dp = 0`, so
 * the whole band normalises to zero and paints one flat wash. A count-based
 * test calls that card a distribution; the reader sees the same solid block.
 *
 * So the question is asked of the thing the reader actually looks at: the rail
 * paints one `<div>` per segment coloured by `rgbaFromIntensity`, and if every
 * one of those divs gets the SAME colour string then the band is one block, by
 * construction, whatever produced it. No tolerance to tune and no threshold to
 * defend — the predicate is exact about the pixels.
 *
 * ═══ WHAT IT DELIBERATELY DOES NOT CATCH ═══
 *
 * A band with two barely-distinguishable colours (say intensity 96 beside 95)
 * would read solid to a reader and passes this test. That is on purpose: every
 * looser rule needs a perceptual constant nobody has measured, and the cost of
 * being strict here is only that a card keeps a band it could have replaced —
 * never that a card loses one it earned. Widen it when a production LOOK
 * produces the counter-example, not before.
 *
 * PURE: no I/O, no React.
 */
export function densityDrawsShape(density: number[], accentRgb: string): boolean {
  if (density.length < 2) return false;
  const first = rgbaFromIntensity(density[0], accentRgb);
  return density.some((d) => rgbaFromIntensity(d, accentRgb) !== first);
}

/**
 * Spelled out to nine, because these are counts in a sentence and not data:
 * "Two lines quoted" is Alex's own wording in #3210 and "2 lines quoted" is
 * not. Above nine the digits win, as they do in any house style.
 */
const COUNT_WORDS = ["No", "One", "Two", "Three", "Four", "Five", "Six", "Seven", "Eight", "Nine"];

/**
 * `"Two lines quoted"` — what a map says INSTEAD of promising a distribution
 * it cannot draw (#3210).
 *
 * Alex listed three options on that issue and this is the sentence from his
 * own text: *"Two lines quoted" with the rungs named is true and useful;
 * "Final games distribution" over a solid bar is not.* The rungs are named
 * directly beneath it — see `MarketMap`'s inline ladder — so the count is not
 * a substitute for the content, it is the heading over it.
 *
 * Note what this deliberately does NOT replace: the live and settled subtitles
 * ("Where it's heading / landed vs what was expected") describe the MARKERS on
 * the rail, which are drawn whether or not the band has a shape. Only the
 * sentences that claim a *distribution* are answerable by this one.
 */
export function quotedLinesPhrase(rungCount: number): string {
  const word = COUNT_WORDS[rungCount] ?? String(rungCount);
  return `${word} ${rungCount === 1 ? "line" : "lines"} quoted`;
}

export interface ParsedSpread {
  team: string;
  threshold: number;
  probability: number;
  source: string;
  isHome: boolean;
  margin: number;
}

export function parseSpreadOutcome(
  outcomeName: string,
  probability: number,
  source: string,
  homeTeam: string,
  awayTeam: string
): ParsedSpread | null {
  const lower = outcomeName.toLowerCase();
  const homeWords = homeTeam.toLowerCase().split(" ");
  const awayWords = awayTeam.toLowerCase().split(" ");
  const isHome = homeWords.some((w) => w.length >= 3 && lower.includes(w));
  const isAway = awayWords.some((w) => w.length >= 3 && lower.includes(w));
  if (!isHome && !isAway) return null;

  const matches = outcomeName.match(/(\d+\.?\d*)/g);
  if (!matches || matches.length === 0) return null;
  const threshold = parseFloat(matches[matches.length - 1]);

  const team = isHome ? homeTeam : awayTeam;
  const margin = isHome ? threshold : -threshold;

  return { team, threshold, probability, source, isHome, margin };
}

export function isFullGameSpread(marketName: string): boolean {
  const lower = (marketName || "").toLowerCase();
  return (
    !lower.includes("1h") &&
    !lower.includes("1st half") &&
    !lower.includes("first half") &&
    !lower.includes("2h") &&
    !lower.includes("2nd half") &&
    !lower.includes("second half") &&
    !lower.includes("first 5")
  );
}

export function isGameTotal(outcomeName: string): boolean {
  return !outcomeName.includes(":");
}

export function buildDensityFromSpreads(
  spreads: ParsedSpread[],
  rangeMin: number,
  rangeMax: number,
  segments: number = 14
): number[] {
  if (spreads.length === 0) return new Array(segments).fill(5);

  const density = new Array(segments).fill(0);
  const step = (rangeMax - rangeMin) / segments;

  for (const s of spreads) {
    const segIdx = Math.floor((s.margin - rangeMin) / step);
    const clampedIdx = Math.max(0, Math.min(segments - 1, segIdx));
    density[clampedIdx] += s.probability;
  }

  const peak = Math.max(...density, 0.01);
  return density.map((d) => Math.round((d / peak) * 96));
}

export function buildDensityFromThresholds(
  thresholds: Array<{ threshold: number; overProbability: number }>,
  rangeMin: number,
  rangeMax: number,
  segments: number = 12
): number[] {
  if (thresholds.length < 2) return new Array(segments).fill(8);

  const sorted = [...thresholds].sort((a, b) => a.threshold - b.threshold);

  const rawPdf: Array<{ mid: number; density: number }> = [];
  for (let i = 0; i < sorted.length - 1; i++) {
    const dt = sorted[i + 1].threshold - sorted[i].threshold;
    if (dt <= 0) continue;
    const dp = sorted[i].overProbability - sorted[i + 1].overProbability;
    rawPdf.push({
      mid: (sorted[i].threshold + sorted[i + 1].threshold) / 2,
      density: Math.max(0, dp / dt),
    });
  }

  if (rawPdf.length === 0) return new Array(segments).fill(8);

  const step = (rangeMax - rangeMin) / segments;
  const density = new Array(segments).fill(0);

  for (let i = 0; i < segments; i++) {
    const x = rangeMin + (i + 0.5) * step;
    let d = 0;

    if (rawPdf.length === 1) {
      d = rawPdf[0].density;
    } else if (x <= rawPdf[0].mid) {
      d = rawPdf[0].density * Math.max(0, 1 - (rawPdf[0].mid - x) / (step * 3));
    } else if (x >= rawPdf[rawPdf.length - 1].mid) {
      d = rawPdf[rawPdf.length - 1].density * Math.max(0, 1 - (x - rawPdf[rawPdf.length - 1].mid) / (step * 3));
    } else {
      for (let j = 0; j < rawPdf.length - 1; j++) {
        if (x >= rawPdf[j].mid && x <= rawPdf[j + 1].mid) {
          const t = (x - rawPdf[j].mid) / (rawPdf[j + 1].mid - rawPdf[j].mid);
          d = rawPdf[j].density * (1 - t) + rawPdf[j + 1].density * t;
          break;
        }
      }
    }
    density[i] = d;
  }

  // Smooth: simple 3-point moving average to reduce choppiness
  const smoothed = density.map((_, i) => {
    const prev = i > 0 ? density[i - 1] : density[i];
    const next = i < density.length - 1 ? density[i + 1] : density[i];
    return (prev + density[i] * 2 + next) / 4;
  });

  const peak = Math.max(...smoothed, 0.001);
  return smoothed.map((d) => Math.round((d / peak) * 96));
}

/**
 * HOW A SPORT IS SCORED — DECLARED, NEVER ASSUMED (#2441).
 *
 * ═══ THE DEFECT ═══
 *
 * Alex, on `/events/15293846` (a US Open match) on 2026-08-31: the page showed
 * **`PRE-GAME BER +4.5`**, **`Total: expected vs final — PRE-GAME 40`**,
 * **`Margin: expected vs final`** and a rail reading **`WAW by 18+ / BER by
 * 18+`**. *"Tennis has no point spread and no 40-point total. This is a generic
 * event template applied to a sport it does not fit, and it is the clearest
 * single tell that the page was not built for tennis."*
 *
 * Every one of those numbers came from here. The old `sportVocab` named three
 * sports and **fell through to points for everything else** — so tennis,
 * cricket, golf, darts, chess and every sport we have not yet met inherited
 * basketball's furniture by default, and the ±18 rail inherited basketball's
 * scale.
 *
 * ═══ WHY A REGISTRY AND NOT A FOURTH `if` ═══
 *
 * A fallthrough default is a claim about every sport that has not been written
 * down yet, made by whoever wrote the default. Adding `tennis` to the chain
 * fixes the page Alex read and leaves the next sport to be discovered the same
 * way — by him.
 *
 * So the polarity is inverted: **a sport gets scoring furniture only by being
 * NAMED, with its unit and its scale.** `UNSCORED_IN_POINTS` is what an
 * unrecognised sport gets, and it declares `hasDerivedSpread: false`, which
 * SUPPRESSES the derived-spread marker rather than inventing one. Silence now
 * means "we have not said", not "assume basketball". Same shape as the
 * win-prob blend's declared prefix registry (CERT-636), and for the same
 * reason: the previous version there was also a spelling test standing in for
 * a semantic one.
 *
 * ═══ WHAT `hasDerivedSpread` ACTUALLY GATES ═══
 *
 * Not the ladder — the MARKER. A tennis match really does have a game-spread
 * market (Kalshi quotes `Berrettini -1.5 games`) and a game total (`Over 34.5
 * games`), and those are true things worth showing in their own units. What is
 * NOT true is `current_odds.home_spread`, which is a POINTS figure derived from
 * the moneyline by a model that assumes interchangeable points. On the
 * Berrettini match that model produced **-4.3**, and the page printed it as
 * `BER +4.5` over a sport with no points at all.
 *
 * So a sport that declares `hasDerivedSpread: false` keeps every market a
 * bookmaker or exchange actually quoted, and loses only the number we made up.
 */
export interface SportScoringVocab {
  marginTitle: string;
  totalTitle: string;
  /** Plural, as the axis and the tiles say it: "points", "runs", "games". */
  unit: string;
  unitSingular: string;
  /**
   * How far the margin rail reaches, in THIS sport's units. Was `18` for
   * everything that was not baseball/hockey/soccer, which is how a tennis rail
   * came to be labelled `by 18+`.
   */
  marginRange: number;
  /**
   * May the page draw a spread it DERIVED from the win probability?
   *
   * True only where the sport is scored in interchangeable points and an
   * expected margin is a real quantity. `false` is the default an unnamed sport
   * inherits, because the failure it prevents (a fabricated margin in a unit
   * the sport does not have) is worse than the one it causes (a marker missing
   * from a sport that could have had one, which is one line to add here).
   */
  hasDerivedSpread: boolean;
  /**
   * ═══ ux/1034 B5: DOES THE SCOREBOARD COUNT THE THING THE MARKET QUOTES? ═══
   *
   * Alex, on `/events/15293830` (Marozsan–Zheng, US Open) on 2026-09-02: the
   * Score Differential widget's *"Actual Score Diff"* line *"sits flat"* beside
   * a fluid win-probability chart, and *"the green projection is the books'
   * game spread"*.
   *
   * He had the diagnosis exactly right, and it is one bug in three places. Our
   * `events.home_score` / `away_score` for a tennis match are **SETS** — that
   * match ended `0 — 3`. Everything the market quotes for it is in **GAMES**:
   * `over_under` 34.8, `projected_home_score` 15.1 / `projected_away_score`
   * 19.7, `Zheng -1.5 games`. So three widgets were plotting one unit against
   * the other and printing the result as a fact:
   *
   *   - the Score Differential chart drew a ±3 set line under a ±5 game axis;
   *   - the margin map graded `FINAL ZHE by 3+` (three SETS) against
   *     `PRE-GAME ZHE by 1.5+` (one and a half GAMES);
   *   - the totals map graded `FINAL 3 games` (three SETS, summed) against
   *     `PRE-GAME 35` (thirty-five GAMES).
   *
   * `#2441` already stopped this page inventing a tennis POINT spread. This is
   * the same defect from the other side: not a number we made up, but a real
   * number read in the wrong unit — which is worse, because it looks sourced.
   *
   * ⚠️ **THE DEFAULT HERE IS `true`, UNLIKE `hasDerivedSpread`, AND THAT IS ON
   * PURPOSE.** #2441's polarity is right for furniture we might invent: an
   * unnamed sport should inherit no spread model. It is wrong for this
   * question, because "the scoreboard counts what the market quotes" is true of
   * very nearly every sport there is — rugby, cricket, AFL, handball — and
   * false only where play is scored in nested units and the market quotes the
   * inner one. Defaulting false would silently delete a true, useful line from
   * every sport nobody has got round to declaring; defaulting true leaves the
   * status quo everywhere except the case that was measured. The RARE thing is
   * named, which is the same principle applied to a different distribution.
   */
  scoreboardCountsTheUnit: boolean;
  /**
   * What the scoreboard counts INSTEAD, plural, when it does not count `unit`.
   *
   * Empty where the question does not arise. It exists so the suppressed
   * widgets can say which two units they are refusing to mix — "the scoreboard
   * reports sets" is the whole explanation, and a widget that just goes quiet
   * reads as broken.
   */
  scoreboardUnit: string;
}

/**
 * The declared sports. A prefix/substring match against the sport key, in
 * order, so `basketball_nba` and `basketball_ncaab` share one entry.
 *
 * Ranges are the sport's own realistic spread of outcomes, not a round number:
 * an NBA game is decided by up to ~18, a baseball game by ~5, a best-of-five
 * tennis match by ~6 games in the margin the market actually quotes.
 */
const SPORT_SCORING: { match: string[]; vocab: SportScoringVocab }[] = [
  {
    match: ["baseball", "mlb"],
    vocab: { marginTitle: "Run margin map", totalTitle: "Runs map", unit: "runs", unitSingular: "run", marginRange: 5, hasDerivedSpread: true, scoreboardCountsTheUnit: true, scoreboardUnit: "" },
  },
  {
    match: ["hockey", "nhl"],
    vocab: { marginTitle: "Goal margin map", totalTitle: "Goals map", unit: "goals", unitSingular: "goal", marginRange: 5, hasDerivedSpread: true, scoreboardCountsTheUnit: true, scoreboardUnit: "" },
  },
  {
    match: ["soccer", "mls", "epl", "uefa", "fifa"],
    vocab: { marginTitle: "Goal margin map", totalTitle: "Goals map", unit: "goals", unitSingular: "goal", marginRange: 5, hasDerivedSpread: true, scoreboardCountsTheUnit: true, scoreboardUnit: "" },
  },
  {
    // #2441's subject. A tennis match is scored in games inside sets; the
    // market quotes a game spread and a game total, and NEITHER is a point.
    // `hasDerivedSpread: false` is what stops `BER +4.5` being drawn from a
    // points model over a sport with no points.
    match: ["tennis"],
    vocab: { marginTitle: "Game margin map", totalTitle: "Games map", unit: "games", unitSingular: "game", marginRange: 6, hasDerivedSpread: false, scoreboardCountsTheUnit: false, scoreboardUnit: "sets" },
  },
  {
    match: ["basketball", "nba", "wnba", "ncaab"],
    vocab: { marginTitle: "Margin map", totalTitle: "Points map", unit: "points", unitSingular: "point", marginRange: 18, hasDerivedSpread: true, scoreboardCountsTheUnit: true, scoreboardUnit: "" },
  },
  {
    match: ["americanfootball", "nfl", "ncaaf"],
    vocab: { marginTitle: "Margin map", totalTitle: "Points map", unit: "points", unitSingular: "point", marginRange: 18, hasDerivedSpread: true, scoreboardCountsTheUnit: true, scoreboardUnit: "" },
  },
];

/**
 * What a sport we have not declared gets.
 *
 * Deliberately NOT basketball's entry under another name. The titles avoid
 * naming a unit at all, the rail is narrow, and no derived spread is drawn —
 * so an undeclared sport renders only what a market actually quoted, in the
 * market's own words, and nothing this file invented.
 */
export const UNSCORED_IN_POINTS: SportScoringVocab = {
  marginTitle: "Margin map",
  totalTitle: "Scoring map",
  unit: "",
  unitSingular: "",
  marginRange: 6,
  hasDerivedSpread: false,
  // `true`, and see the field's own note for why this default runs the other
  // way from `hasDerivedSpread`'s: an unnamed sport almost certainly does
  // score in the unit its market quotes, and defaulting false would delete a
  // true line from every sport nobody has declared yet.
  scoreboardCountsTheUnit: true,
  scoreboardUnit: "",
};

export function sportVocab(sportKey: string | undefined): SportScoringVocab {
  const key = (sportKey || "").toLowerCase();
  if (!key) return UNSCORED_IN_POINTS;
  for (const entry of SPORT_SCORING) {
    if (entry.match.some((m) => key.includes(m))) return entry.vocab;
  }
  return UNSCORED_IN_POINTS;
}

/**
 * `"33 games"`, or just `"33"` for a sport whose unit we have not declared.
 *
 * `UNSCORED_IN_POINTS.unit` is deliberately the empty string — an undeclared
 * sport should print the number a market quoted and NOT a unit this file
 * guessed. Every template that interpolates the unit therefore has to survive
 * it being absent, and doing that inline produces `"33 "` and
 * `"Final  distribution"`. One helper, so a new call site cannot reintroduce
 * the double space.
 */
export function withUnit(value: string | number, vocab: SportScoringVocab): string {
  return vocab.unit ? `${value} ${vocab.unit}` : String(value);
}

/** `"Final games distribution"` / `"Final distribution"`. Same reason. */
export function unitPhrase(prefix: string, vocab: SportScoringVocab, suffix: string): string {
  return [prefix, vocab.unit, suffix].filter(Boolean).join(" ");
}

/**
 * How a widget admits it does not hold the played count — IN THE TENSE THE
 * MATCH IS ACTUALLY IN.
 *
 * #3136, Alex, on `/events/15301243` (Wu 0–3 Alcaraz, FINAL the day before):
 *
 *   > "we do not hold the games played **yet**" — the *yet* is a promise about
 *   > a match still in progress. This one is complete.
 *
 * He is right, and the promise is one nothing will keep. Re-measured on that
 * event 2026-09-05: `/api/events/15301243/history` returns `espn_history` with
 * **0** entries and `score_history` with **4**, every one of them a SET count
 * (`0-0, 0-1, 0-2, 0-3`); `/api/events/15301243` carries `home_score` /
 * `away_score` and nothing per-set. No payload this page fetches has ever held
 * a game count for this match, and none will now that it is over. "Yet" on a
 * FINAL page is therefore not optimism, it is a false claim about our roadmap.
 *
 * ── WHY THIS IS A SHARED HELPER AND NOT TWO STRING LITERALS ──────────────────
 *
 * TWO widgets on that one page owe the reader this sentence — the Games map and
 * the Score Differential note directly above it — and they owe it about the same
 * missing number for the same reason. The tense is the part that goes stale, so
 * it is the part that must not be written twice: the day one of them learns that
 * a finished match is finished and the other does not, the page tells a reader
 * both that the count is coming and that it never came. `sportVocab` is already
 * shared between these two for exactly this reason ("two answers to it is how
 * one of them comes to disagree with the other"); this is that rule applied to
 * the clause rather than to the unit.
 *
 * Each surface keeps its own sentence AROUND the clause, because a card subtitle
 * and a chart footnote are not the same sentence — only the claim is.
 */
export function playedCountAbsence(unit: string, isDone: boolean): string {
  const what = unit ? `the ${unit} played` : "the played count";
  return isDone ? `we did not record ${what}` : `we do not hold ${what} yet`;
}

/** The per-period line the API serves beside a set score. `Event["linescore"]`. */
export interface PlayedLinescore {
  sets: [number, number][];
  home_games: number;
  away_games: number;
  source?: string;
}

/**
 * THE TWO NUMBERS IN THE UNIT THE MARKET QUOTES — or `null` if we hold none.
 *
 * live/073.  ux/1034 B5 nulled the scoreboard on a tennis page because
 * `home_score` is SETS and every rail on it is drawn in GAMES, and that was
 * right: a real number read in the wrong unit is worse than an absent one.
 * What it left behind is a page that says `PRE-GAME 29` on a match that
 * finished, under "we did not record the games played" — measured over the 207
 * anchored settled tennis rows of 2026-09-05, all of them.
 *
 * The games ARE recorded now.  `Event.linescore` carries the per-set line the
 * tennis authority writes off ESPN's board, in our home/away order, and its
 * totals are exactly the quantity the game-total market quotes.  So the rule
 * this helper states is not "trust the scoreboard" but *"count the unit"*:
 *
 *   1. the scoreboard, where it counts the unit (every sport but tennis);
 *   2. the linescore, where it does not and we have one;
 *   3. `null`, and the widgets say so in the sport's own words.
 *
 * ONE HELPER, because the answer is asked for by four maps and a chart on one
 * page, and the failure mode ux/1034 B5 was fixing is precisely two of them
 * answering it differently.  A caller that reaches past this into
 * `gameMarkets.home_score` is reintroducing that bug.
 */
export function playedUnits(
  vocab: SportScoringVocab,
  scoreboard: { home: number | null | undefined; away: number | null | undefined },
  linescore?: PlayedLinescore | null
): { home: number; away: number } | null {
  if (vocab.scoreboardCountsTheUnit) {
    const { home, away } = scoreboard;
    return home != null && away != null ? { home, away } : null;
  }
  // NOT `home_games != null` alone: a line with no sets in it is an absence
  // wearing a shape, and `0 – 0` beside a finished match is the empty-card
  // class all over again.
  if (
    linescore &&
    linescore.sets?.length > 0 &&
    typeof linescore.home_games === "number" &&
    typeof linescore.away_games === "number"
  ) {
    return { home: linescore.home_games, away: linescore.away_games };
  }
  return null;
}

/**
 * `"6-3, 6-4, 6-1"` — the line as a reader says it.
 *
 * The API serves `sets` in OUR home/away order, which is the order everything
 * else on the response is in and is NOT the order a result is spoken in.
 * `reversed` prints the away side first, because a scoreline read the other way
 * up asks the reader to reverse it in their head and half of them will not —
 * the rule `espn_tennis.format_score` states on the backend, applied to the
 * same data.
 *
 * WHO WON IS THE CALLER'S TO KNOW, and it is deliberately not inferred from the
 * games here: a tennis match is won on SETS and the loser can finish with more
 * games than the winner (6-7, 6-4, 6-2 is 18 games to 19 in the wrong
 * direction). The caller holds the set score; it passes the answer in.
 */
export function formatLinescore(
  sets: [number, number][] | undefined | null,
  { reversed = false }: { reversed?: boolean } = {}
): string {
  if (!sets || sets.length === 0) return "";
  return sets
    .map(([home, away]) => (reversed ? `${away}-${home}` : `${home}-${away}`))
    .join(", ");
}

/**
 * The heading over a column of market maps, counted rather than assumed.
 *
 * #3136, Alex: *"The section heading is `GAMES MAPS`, plural, over a single
 * card."* The column heading has been unconditionally plural since #2442 wrote
 * it, which is right on an NFL page (a full-game map plus 1H and 2H) and wrong
 * on the very common page that has exactly one — a tennis match has no halves,
 * so its totals column has always held one card under a heading announcing
 * several.
 *
 * The singular form is the sport's DECLARED title, not the plural with its `s`
 * removed, so a vocabulary whose title does not happen to end in " map" cannot
 * be mangled into one. The plural keeps #2442's construction verbatim for the
 * multi-card case that was already correct.
 */
export function mapColumnHeading(title: string, cardCount: number): string {
  return cardCount > 1 ? `${title.replace(/ map$/i, "")} maps` : title;
}
