/**
 * Period boundary derivation for chart annotations.
 * Extracts period transition timestamps from ESPN history, win prob history,
 * or scoring plays data — whichever is available.
 */

import type { ESPNHistoryPoint, WinProbHistoryPoint, ScoringPlay } from "./types";

export interface PeriodBoundary {
  /** ISO timestamp of the period transition */
  timestamp: string;
  /** Short display label (e.g., "Q2", "P2", "5", "2H") */
  label: string;
}

/**
 * Minimum gap between two period markers before their LABELS are collapsed into
 * one, as a fraction of the chart's visible time span.
 *
 * UX-P022 derived this on the win-probability chart: label collision is a
 * function of PIXELS, so the rule has to be purely proportional. The earlier
 * hybrid — `max(duration * N%, some minutes)` — mixes a pixel budget with a time
 * budget, and the two only agree at one chart length: on a three-hour game the
 * minutes floor is far too tight, on a twenty-minute live game it is far too
 * wide. 7% of the visible width is comfortably wider than a 2–4 character period
 * label at 11px, and means the same thing at every chart length.
 */
export const PERIOD_LABEL_MIN_SPACING_FRACTION = 0.07;

/**
 * Collapse period boundaries whose labels would overlap, keeping the LATER of
 * any too-close pair (so "HT" wins over "Q2 end", which names the same moment
 * better).
 *
 * Input must be timestamp-ascending — each chart bounds and filters the list its
 * own way first, because they disagree on what "on the chart" means: the
 * win-probability chart measures its drawn extent (CERT-1984), the score
 * differential chart requires a drawn score line (CERT-1989). Only the spacing
 * rule is shared, and it is shared because it is the same pixel problem on the
 * same page at the same width.
 *
 * #888-adjacent, routed by latency/467: the score differential chart carried a
 * private copy of the PRE-UX-P022 rule and rendered `TB2`, `TB3`, `T5T6` at
 * 390px while the win-probability chart directly above it spaced the identical
 * innings cleanly. One rule, two call sites, so a third chart cannot inherit the
 * old one by copy-paste.
 */
export function dedupePeriodLabels<T extends { timestamp: string }>(
  ascending: T[],
  chartDurationMs: number,
): T[] {
  const minSpacing = chartDurationMs * PERIOD_LABEL_MIN_SPACING_FRACTION;
  const deduped: T[] = [];
  for (const b of ascending) {
    const t = new Date(b.timestamp).getTime();
    if (deduped.length > 0) {
      const prevT = new Date(deduped[deduped.length - 1].timestamp).getTime();
      if (t - prevT < minSpacing) {
        deduped[deduped.length - 1] = b;
        continue;
      }
    }
    deduped.push(b);
  }
  return deduped;
}

/**
 * How much wider than the collapse threshold a gap must be before both labels
 * read cleanly on the SAME row. Below this — but above the collapse threshold,
 * so both markers are kept — the later label drops one row.
 *
 * #6882 — NFL HALFTIME IS THE PAIR THIS EXISTS FOR, AND IT IS STRUCTURAL.
 * Measured on `/events/14638444` (Bills–Lions) at 390px with
 * `tools/period-label-gap-6882.mjs`, which reads the painted `getBoundingClientRect()`
 * of every marker label rather than its timestamp:
 *
 *   pair     clear gap (win prob / score diff)
 *   Q2 → HT      60.4px / 64.3px
 *   HT → Q3       3.4px /  5.5px   ← reads as one token, `HT Q3`
 *   Q3 → Q4      22.6px / 25.4px
 *
 * `HT → Q3` is 15.0 min on a 191.6 min span = 7.83%, so it clears
 * `PERIOD_LABEL_MIN_SPACING_FRACTION` by 1.6 minutes and both labels survive —
 * and then sit 3.4px apart. NFL halftime is structurally ~15 min and an NFL
 * broadcast structurally ~3.2 h, so this is a property of the sport: it happens
 * on every NFL game, on the one boundary a reader most needs distinguished.
 *
 * 🪤 RAISING `PERIOD_LABEL_MIN_SPACING_FRACTION` IS THE WRONG FIX, TWICE.
 * `dedupePeriodLabels` keeps the LATER of a too-close pair, so collapsing this
 * one DELETES `HT` from every NFL chart — strictly worse than the crowding. And
 * the constant is shared by both charts across every sport by deliberate design
 * (#888 / latency/467), so any move is also a claim about innings, halves and
 * hockey periods. The labels must both survive; only their layout changes.
 *
 * WHY 1.8. At 390px the plot is 252px wide (measured, above). Reading the 3.4px
 * gap back through the 5px label offset puts a 2-character label at 11px bold at
 * ~16.3px wide, so a 3-character one (`OT2`, `/Q1`) is ~24px. Clean separation
 * needs the label's own width plus ~8px of air = ~32px of marker-to-marker
 * distance, and 32/252 = 12.7% of the plot — 1.81× the 7% collapse threshold.
 * Rounded to 1.8, the band is 7%–12.6%: `HT → Q3` (7.83%) staggers, `Q3 → Q4`
 * (15.66%) does not, and neither sits near an edge.
 *
 * IT IS A MULTIPLE OF THE COLLAPSE THRESHOLD, NOT A SECOND INDEPENDENT NUMBER,
 * so the two rules cannot drift apart: the band is by construction "survived the
 * collapse, but only just", which is the defect stated exactly.
 *
 * Staying proportional rather than pixel-measured is forced, not preferred: both
 * charts size themselves through `ResponsiveContainer width="100%"` and never
 * learn their own pixel width, and the server render every guard test uses has
 * no viewport at all. A pixel rule would be untestable and would behave
 * differently in the rig than in the browser. Over-firing is the safe direction
 * anyway — a staggered label is still wholly present and readable, where an
 * over-collapsed one is gone.
 */
export const PERIOD_LABEL_STAGGER_SPACING_MULTIPLE = 1.8;

/**
 * Vertical drop, in px, of a label pushed to the second row. One line at the
 * 10–11px the two charts label at; the drop is shared so they stagger alike.
 */
export const PERIOD_LABEL_ROW_HEIGHT_PX = 13;

/**
 * Assign each surviving period label a row — 0 for the top row, 1 for one line
 * down — so that a pair too close to read side by side is spread vertically
 * instead of being collapsed.
 *
 * Input must be timestamp-ascending and ALREADY DEDUPED: this decides layout for
 * markers that are being drawn, and says nothing about which markers survive.
 * The two steps are deliberately separate — collapsing is about what the chart
 * claims, staggering is about how it reads.
 *
 * The FIRST of a crowded pair keeps the top row and the later one drops. That
 * ordering is not arbitrary: on the pair this was built for the survivor of a
 * collapse would have been `Q3`, so keeping the earlier label prominent is what
 * puts `HT` back where a reader looks for it.
 *
 * TWO ROWS ARE PROVABLY ENOUGH, given the collapse rule ran first. A marker only
 * drops when its predecessor is on row 0, so rows alternate at worst. Three
 * consecutive crowded markers put A and C both on row 0 — and every kept pair is
 * at least `PERIOD_LABEL_MIN_SPACING_FRACTION` apart, so A→C is at least twice
 * that (14%), which already clears the 12.6% stagger band. A and C cannot
 * collide, so no third row can be needed.
 */
export function assignPeriodLabelRows<T extends { timestamp: string }>(
  ascending: T[],
  chartDurationMs: number,
): Array<T & { labelRow: number }> {
  const staggerSpacing =
    chartDurationMs *
    PERIOD_LABEL_MIN_SPACING_FRACTION *
    PERIOD_LABEL_STAGGER_SPACING_MULTIPLE;
  const out: Array<T & { labelRow: number }> = [];
  for (const b of ascending) {
    const t = new Date(b.timestamp).getTime();
    let labelRow = 0;
    if (out.length > 0) {
      const prev = out[out.length - 1];
      const prevT = new Date(prev.timestamp).getTime();
      if (t - prevT < staggerSpacing && prev.labelRow === 0) labelRow = 1;
    }
    out.push({ ...b, labelRow });
  }
  return out;
}

/** Where a period label is anchored, in the `ReferenceLine` label's own words. */
export type PeriodLabelPosition = "insideTopLeft" | "insideTopRight";

/**
 * Painted width of one period label plus the air a reader needs after it, as a
 * fraction of the chart's visible span.
 *
 * NOT A NEW NUMBER. It is `PERIOD_LABEL_MIN_SPACING_FRACTION ×
 * PERIOD_LABEL_STAGGER_SPACING_MULTIPLE` — 12.6% — and that product is exactly
 * what #6882 derived it from: a 3-character label at 11px bold is ~24px, plus
 * ~8px of air, on the 252px plot a 390px screen draws, = 32px = 12.7%. #6882
 * spends it on the gap BETWEEN two markers; the rule below spends the same
 * budget on the gap between a marker and the plot's right rule, because it is
 * the same ink measured against a different obstacle. Naming it here is what
 * stops the two drifting into two numbers that mean one thing.
 */
export const PERIOD_LABEL_INK_FRACTION =
  PERIOD_LABEL_MIN_SPACING_FRACTION * PERIOD_LABEL_STAGGER_SPACING_MULTIPLE;

/**
 * Choose which side each period label grows out of, and drop a row where that
 * choice creates a collision the row rule above could not have seen.
 *
 * #7371 — A LIVE GAME'S NEWEST MARKER PRINTED A SINGLE ORPHAN GLYPH. On
 * `/events/15314713` (Angels–Twins, hero `Top 10th`) the right-hand period rule
 * was captioned **`T`**. There is no code path that emits a bare `T`: it is
 * `T10` with its last two glyphs cut off. `insideTopLeft` anchors the text
 * `start` at the rule, so a marker sitting ON the chart's last category grows
 * its label out of the svg, which ends 10px later at every width. Measured in
 * the rig at 390px before the fix: `x=385 anchor=start` against a plot rule at
 * 380 — 5px of room for a 24px word. It is the same structural clip as #3541's
 * bare `F` and #3525's stray `5`, on the one marker a live reader most wants.
 *
 * A live game reaches this shape every few minutes: the half-inning that just
 * started IS the newest data, so its boundary is at or within a pixel of the
 * right rule, and `Q`/`P`/`H` markers share the anchor in every other sport.
 *
 * WHY FLIP RATHER THAN DELETE THE CAPTION. #3541 answered the same clip by
 * dropping the `Final` marker's label, and that was right there: the hero
 * already carries a FINAL chip, so the word was redundant and its anchor could
 * not be changed without colliding with a period label it is not spaced
 * against. Neither holds here. `T10` is not printed anywhere else on the chart,
 * and a period label collides only with other period labels — which this
 * module already spaces, so the flip can be spaced by the same rule instead of
 * being a special case pleading its own exception.
 *
 * THE FLIPPED LABEL NEEDS TWICE THE BUDGET. A left-anchored label and a
 * right-anchored one on either side of a gap grow TOWARD each other, so the gap
 * has to hold both inks — that is UX-P022's finding, and it is why alternating
 * anchors was removed. It is not an argument against flipping the LAST label,
 * which has no neighbour to its right; it is the reason the flipped label's
 * clearance from its predecessor is `2 × PERIOD_LABEL_INK_FRACTION` rather than
 * the one-way stagger band. Under that, it drops a row — the same remedy #6882
 * chose for `HT → Q3`, for the same reason: both markers keep their caption.
 *
 * Over-firing is the safe direction (a staggered label is wholly readable, a
 * collapsed one is gone), and both charts size themselves through
 * `ResponsiveContainer width="100%"` and never learn their pixel width, so the
 * rule stays proportional like every other rule here.
 *
 * Input must be timestamp-ascending and ALREADY ROWED by
 * `assignPeriodLabelRows`: this is the second layout pass and it only ever
 * raises a row, never lowers one.
 */
export function anchorPeriodLabels<T extends { timestamp: string; labelRow: number }>(
  ascending: T[],
  chartDurationMs: number,
  chartEndMs: number,
): Array<T & { labelPosition: PeriodLabelPosition }> {
  const ink = chartDurationMs * PERIOD_LABEL_INK_FRACTION;
  const out: Array<T & { labelPosition: PeriodLabelPosition }> = [];
  for (const b of ascending) {
    const t = new Date(b.timestamp).getTime();
    // Room to the right of this marker, measured against the plot's right rule.
    const flip = chartEndMs - t < ink;
    let labelRow = b.labelRow;
    if (flip && out.length > 0) {
      const prev = out[out.length - 1];
      const prevT = new Date(prev.timestamp).getTime();
      if (t - prevT < 2 * ink && prev.labelRow === 0) labelRow = 1;
    }
    out.push({
      ...b,
      labelRow,
      labelPosition: flip ? "insideTopRight" : "insideTopLeft",
    });
  }
  return out;
}

/**
 * Largest plausible gap WITHIN a single game's period/inning markers. No sport
 * that renders period gridlines (NBA/NFL/MLB/NHL/soccer) has a 6-hour mid-game
 * pause, so a gap this large means the marker stream jumped to a DIFFERENT
 * game's data merged onto the same event (gotcha #32 territory — e.g. the
 * live-MLB exhibit whose period_markers still carried the prior day's innings).
 */
const SESSION_GAP_MS = 6 * 60 * 60 * 1000;

/**
 * Keep only the LAST contiguous session of a timestamp-ascending marker list.
 *
 * When markers from an earlier game are wrongly merged onto an event, their
 * inning/period labels ("Top 5th" from yesterday) get anchored to yesterday's
 * timestamp by the first-seen collapse below, then either vanish from the
 * visible domain or — in a wide "All" window — collide on the 12-hour "h:mm a"
 * categorical axis and render an inning to the LEFT of an earlier one (the
 * "T9 left of T1" bug, L2-163 Item 2c). Cutting to the latest contiguous run
 * discards the stale segment so the current game's innings stay monotonic. A
 * clean single-game stream (no large gaps) passes through unchanged.
 */
function keepLatestSession<T extends { timestamp: string }>(sorted: T[]): T[] {
  if (sorted.length < 2) return sorted;
  let cut = 0;
  for (let i = 1; i < sorted.length; i++) {
    const gap =
      new Date(sorted[i].timestamp).getTime() -
      new Date(sorted[i - 1].timestamp).getTime();
    if (gap > SESSION_GAP_MS) cut = i;
  }
  return cut > 0 ? sorted.slice(cut) : sorted;
}

/**
 * #4888 — WHAT A BARE PERIOD NUMBER MEANS, BY SPORT.
 *
 * ESPN's box-score fallback stores the period as a bare digit: the NFL season
 * opener (event 14780138) serves `period_markers` of exactly `"2"`, `"3"`, `"4"`,
 * source `espn_box`. Every branch of `normalizePeriodLabel` misses a bare digit
 * except the "already short" test, whose alternation ends in `\d+` and returns it
 * unchanged — so the chart drew dashed rules labelled `3` and `4` and a reader had
 * no way to learn they meant quarters. (Alex, 2026-09-09 iPad pass, item 6.)
 *
 * `"3"` alone is genuinely ambiguous — Q3 in football/basketball, P3 in hockey,
 * the 3rd inning in baseball — so the unit cannot be guessed inside a helper that
 * only sees the string. The caller knows the sport; this table is what it buys.
 *
 * WHY THIS LIVES HERE rather than reusing `lib/sportCategories.ts`: that module
 * answers "which tab does this league belong under", and its categories split pro
 * from college (`nfl`, `ncaaf`) in a way that has nothing to do with periods.
 * What a period number means is period knowledge, and it is four rows.
 *
 * BASEBALL IS DELIBERATELY ABSENT. A bare inning number cannot be completed
 * honestly — `T3` and `B3` are different moments and the digit does not say which
 * — so baseball keeps today's bare digit rather than gaining a fabricated half.
 *
 * #4955 — `regulation` IS NOT DECORATION; IT IS WHAT STOPS THE TABLE LYING.
 * A sport's period numbering runs past regulation into overtime, and completing
 * those with the regulation unit invents a period that does not exist: there is
 * no `Q5` in football, no `P4` in hockey, no `3H` in soccer. Past regulation we
 * return null and the caller's `?? s` leaves the bare digit — vague but true,
 * which is the same trade the baseball carve-out above makes. Unbounded, this
 * table turned an ambiguous label into a false one, the opposite direction from
 * the rest of #4888.
 *
 * ORDER-SENSITIVE, and the first matching row WINS OUTRIGHT — a row that matches
 * but is out of range returns null rather than falling through to a later row.
 * `basketball_ncaab` (men's college, two 20-minute halves) is therefore tested
 * before the `basketball_` row that gives everyone else quarters, and an NCAAB
 * `3` reads bare rather than picking up `Q3` from the row below it.
 *
 * The patterns are ANCHORED PREFIXES, not substrings, and that is load-bearing
 * here: `/^basketball_ncaab/` does not match `basketball_wncaab`, which plays
 * quarters and must keep them. (`sport_keys.py` carries both keys.)
 *
 * Table and bound mirror the Swift twin, `ios/…/Utilities/PeriodLabel.swift`
 * `barePeriodUnit` / `barePeriod` (#4888, PR #4925), so the two platforms read a
 * bare digit the same way. One known divergence past regulation, flagged by
 * native/107 and tracked under #1834, not introduced here: iOS falls through to
 * its ordinal (`5` → `5th`) where web leaves the bare digit (`5`). Web cannot
 * follow without contradicting its own plain-ordinal branch below, which
 * normalizes `"3rd"` → `"3"`.
 */
const BARE_PERIOD_UNIT: Array<{
  prefix: RegExp;
  regulation: number;
  format: (n: string) => string;
}> = [
  { prefix: /^americanfootball_/i, regulation: 4, format: (n) => `Q${n}` },
  { prefix: /^icehockey_/i, regulation: 3, format: (n) => `P${n}` },
  { prefix: /^soccer_/i, regulation: 2, format: (n) => `${n}H` },
  { prefix: /^basketball_ncaab/i, regulation: 2, format: (n) => `${n}H` },
  { prefix: /^basketball_/i, regulation: 4, format: (n) => `Q${n}` },
];

/** The sport-aware completion of a bare period number, or null to leave it be. */
function labelBarePeriod(n: string, sport?: string | null): string | null {
  if (!sport) return null;
  // `n` reaches here only from a `^\d+$` match, so this cannot be NaN — but it
  // CAN be 0, and `Q0` is as fabricated a period as `Q5`.
  const num = Number(n);
  if (!(num > 0)) return null;
  for (const { prefix, regulation, format } of BARE_PERIOD_UNIT) {
    if (!prefix.test(sport)) continue;
    return num <= regulation ? format(n) : null;
  }
  return null;
}

/**
 * Normalize ESPN's verbose period strings into short chart labels.
 *
 * Basketball/Football: "1st Quarter" -> "Q1", "Halftime" -> "HT"
 * Hockey: "1st Period" -> "P1"
 * Baseball: "Top 3rd" / "Bottom 3rd" -> "3"
 * Soccer: "1st Half" -> "1H", "2nd Half" -> "2H"
 * Generic: "Overtime" -> "OT"
 *
 * @param sport — the event's sport key (`americanfootball_nfl`, …). Optional and
 *   BACKWARD-COMPATIBLE: without it a bare period number renders exactly as it
 *   does today, so no existing caller changes behaviour by not passing it.
 */
export function normalizePeriodLabel(raw: string, sport?: string | null): string {
  if (!raw) return "";
  let s = raw.trim();

  // Reject pre-game date strings like "Wed, March 25th at 10:00 PM EDT"
  // These leak from ESPN status_detail during game transitions
  if (/\b(January|February|March|April|May|June|July|August|September|October|November|December)\b/i.test(s)) return "";
  if (/\b(Mon|Tue|Wed|Thu|Fri|Sat|Sun)\b.*\bat\b/i.test(s)) return "";

  // Strip clock prefix: "11:05 - 1st Quarter" → "1st Quarter"
  // ESPN status_detail includes game clock before the period name
  s = s.replace(/^[\d.:]+\s*-\s*/, "");

  // Detect "End of" / "Start of" prefix before stripping
  const isEnd = /^end\s+(?:of\s+)?/i.test(s);
  s = s.replace(/^(?:end|start)\s+(?:of\s+)?/i, "");

  // Halftime
  if (/^half\s*time$/i.test(s) || s === "HT") return "HT";

  // Overtime variants
  if (/^(overtime|ot)$/i.test(s)) return "OT";
  if (/^(\d+)\w*\s+overtime$/i.test(s)) {
    const m = s.match(/^(\d+)/);
    return m ? `OT${m[1]}` : "OT";
  }

  // Quarter (basketball, football): "1st Quarter" → "Q1", "End of 1st Quarter" → "/Q1"
  const qMatch = s.match(/^(\d+)\w*\s+quarter$/i);
  if (qMatch) return isEnd ? `/Q${qMatch[1]}` : `Q${qMatch[1]}`;

  // Period (hockey): "1st Period" → "P1", "End of 1st Period" → "/P1"
  const pMatch = s.match(/^(\d+)\w*\s+period$/i);
  if (pMatch) return isEnd ? `/P${pMatch[1]}` : `P${pMatch[1]}`;

  // Half (soccer): "1st Half" → "1H", "End of 1st Half" → "/1H"
  const hMatch = s.match(/^(\d+)\w*\s+half$/i);
  if (hMatch) return isEnd ? `/${hMatch[1]}H` : `${hMatch[1]}H`;

  // Baseball innings: "Top 3rd" → "T3", "Bottom 5th" → "B5"
  // Skip "Middle" and "End" to avoid chart clutter — only show half-inning starts
  const iMatch = s.match(/^(top|bottom|mid(?:dle)?|end)\s+(\d+)/i);
  if (iMatch) {
    const half = iMatch[1].toLowerCase();
    if (half === "mid" || half === "middle" || half === "end") return "";
    const prefix = iMatch[1][0].toUpperCase();
    return `${prefix}${iMatch[2]}`;
  }

  // Plain ordinal inning: "3rd" -> "3" (sometimes ESPN just sends this)
  const ordMatch = s.match(/^(\d+)(?:st|nd|rd|th)$/i);
  if (ordMatch) return ordMatch[1];

  // #4888: a BARE number is the one member of the "already short" set below that
  // does not name its own unit — `Q1`, `P2`, `1H`, `OT`, `HT` all do. Complete it
  // from the sport when we know it; fall through to the old behaviour when we
  // don't, or when the sport has no honest completion (baseball).
  const bare = s.match(/^(\d+)$/);
  if (bare) return labelBarePeriod(bare[1], sport) ?? s;

  // Already short like "Q1", "P2", "1H", "OT"
  if (/^(Q\d|P\d|\d+H|OT\d?|HT|\d+)$/i.test(s)) return s.toUpperCase();

  // Golf round labels: "R1", "R2", "R3", "R4", "PO" (playoff)
  if (/^R\d$/i.test(s)) return s.toUpperCase();
  if (/^round\s+(\d+)$/i.test(s)) {
    const rMatch = s.match(/^round\s+(\d+)$/i);
    return rMatch ? `R${rMatch[1]}` : s;
  }
  if (/^playoff$/i.test(s)) return "PO";

  return s;
}

/**
 * Derive period boundary timestamps from available history data.
 * Tries sources in priority order:
 *   1. espnHistory (has explicit period field)
 *   2. winProbHistory game_state.period
 *   3. scoringPlays period field
 *
 * Returns boundaries for period *transitions* (not the first period).
 * E.g., for a basketball game: returns boundaries for Q2, Q3, Q4 starts.
 *
 * @param commenceTime — ISO timestamp of game start. When provided, the first
 *   period boundary (e.g., Q1) uses this as its timestamp instead of the first
 *   data point, which may arrive late.
 */
export function derivePeriodBoundaries(
  espnHistory?: ESPNHistoryPoint[],
  winProbHistory?: Record<string, WinProbHistoryPoint[]>,
  scoringPlays?: ScoringPlay[],
  commenceTime?: string,
  periodMarkers?: Array<{ timestamp: string; period: string }>,
  /** #4888: event sport key, so a bare period number can name its own unit. */
  sport?: string | null,
): PeriodBoundary[] {
  // Top priority: backend-computed period markers from scoring_plays table.
  // These come from StatPal play-by-play and have period info on every play,
  // covering games where ESPN and win_prob_history have no period data.
  if (periodMarkers && periodMarkers.length > 0) {
    // Dedup by exact label (start "Q1" and end "/Q1" are distinct)
    const sorted = keepLatestSession(
      [...periodMarkers].sort(
        (a, b) => new Date(a.timestamp).getTime() - new Date(b.timestamp).getTime()
      )
    );
    const firstSeen = new Map<string, string>();
    for (const m of sorted) {
      const label = normalizePeriodLabel(m.period, sport);
      if (label && !firstSeen.has(label)) {
        firstSeen.set(label, m.timestamp);
      }
    }
    const boundaries = Array.from(firstSeen.entries())
      .sort((a, b) => new Date(a[1]).getTime() - new Date(b[1]).getTime())
      .map(([label, timestamp]) => ({ timestamp, label }));
    if (boundaries.length > 0) return applyCommenceTime(boundaries, commenceTime);
  }

  // Prefer win prob history — its timestamps are always present in chartData
  // (added via ensurePoint), so ReferenceLine x values will match chart categories.
  // ESPN history timestamps come from a separate table (ESPNSnapshot) and may not
  // have matching entries in the chart data when win_prob_snapshots deduped them.
  if (winProbHistory) {
    const boundaries = deriveBoundariesFromWinProb(winProbHistory, sport);
    if (boundaries.length > 0) return applyCommenceTime(boundaries, commenceTime);
  }

  // Fallback to ESPN history (explicit period field, different table)
  if (espnHistory && espnHistory.length > 1) {
    const boundaries = deriveBoundariesFromEspn(espnHistory, sport);
    if (boundaries.length > 0) return applyCommenceTime(boundaries, commenceTime);
  }

  // Try scoring plays
  if (scoringPlays && scoringPlays.length > 1) {
    const boundaries = deriveBoundariesFromScoringPlays(scoringPlays, sport);
    if (boundaries.length > 0) return applyCommenceTime(boundaries, commenceTime);
  }

  return [];
}

/**
 * Post-process boundaries:
 * - Use commenceTime for the first period (Q1/P1/1H) since data may arrive late.
 * - Move "Final" to the last data point timestamp (not the first "Final" point).
 */
function applyCommenceTime(
  boundaries: PeriodBoundary[],
  commenceTime?: string,
): PeriodBoundary[] {
  if (boundaries.length === 0) return boundaries;

  const result = [...boundaries];

  // Fix first period: use commenceTime if available
  if (commenceTime) {
    const first = result[0];
    const isFirstPeriod = /^(Q1|P1|1H|1|R1|T1|B1)$/i.test(first.label);
    if (isFirstPeriod) {
      result[0] = { ...first, timestamp: commenceTime };
    }
  }

  return result;
}

function deriveBoundariesFromEspn(history: ESPNHistoryPoint[], sport?: string | null): PeriodBoundary[] {
  // Sort by timestamp, then drop any stale earlier-game segment (L2-163).
  const sorted = keepLatestSession(
    [...history].sort(
      (a, b) => new Date(a.timestamp).getTime() - new Date(b.timestamp).getTime()
    )
  );

  // Collect the first timestamp we see for each unique period label
  const firstSeen = new Map<string, string>();

  for (const point of sorted) {
    if (!point.period) continue;
    const label = normalizePeriodLabel(point.period, sport);
    if (!label) continue;
    if (!firstSeen.has(label)) {
      firstSeen.set(label, point.timestamp);
    }
  }

  // Every unique period we observed gets a boundary at its first occurrence.
  // This handles missed transitions (e.g., ESPN sync started in Q2 — we still
  // mark Q2 even though we never saw Q1→Q2).
  return Array.from(firstSeen.entries())
    .sort((a, b) => new Date(a[1]).getTime() - new Date(b[1]).getTime())
    .map(([label, timestamp]) => ({ timestamp, label }));
}

function deriveBoundariesFromWinProb(
  winProbHistory: Record<string, WinProbHistoryPoint[]>,
  sport?: string | null,
): PeriodBoundary[] {
  // Merge all sources, extract period from game_state
  const allPoints: { timestamp: string; period: string }[] = [];

  for (const points of Object.values(winProbHistory)) {
    for (const point of points) {
      const gs = point.game_state as Record<string, unknown> | undefined;
      if (!gs) continue;

      // Standard period field (ESPN, stat_model)
      const period = gs.period;
      if (typeof period === "string" && period) {
        allPoints.push({ timestamp: point.timestamp, period });
        continue;
      }

      // MLB format: inning + inning_half (e.g., {inning: 3, inning_half: "top"})
      const inning = gs.inning;
      if (typeof inning === "number" && inning > 0) {
        const half = typeof gs.inning_half === "string" ? gs.inning_half : "top";
        // Construct a period string that normalizePeriodLabel can parse
        // e.g., "Top 3rd" → normalized to "3"
        const ordinal = inning === 1 ? "1st" : inning === 2 ? "2nd" : inning === 3 ? "3rd" : `${inning}th`;
        allPoints.push({
          timestamp: point.timestamp,
          period: `${half.charAt(0).toUpperCase() + half.slice(1)} ${ordinal}`,
        });
      }
    }
  }

  if (allPoints.length === 0) return [];

  // Sort by timestamp, then drop any stale earlier-game segment (L2-163).
  allPoints.sort((a, b) => new Date(a.timestamp).getTime() - new Date(b.timestamp).getTime());
  const session = keepLatestSession(allPoints);

  // Collect the first timestamp we see for each unique period label.
  // This handles missed transitions (e.g., ESPN sync started in Q2).
  const firstSeen = new Map<string, string>();

  for (const point of session) {
    const label = normalizePeriodLabel(point.period, sport);
    if (!label) continue;
    if (!firstSeen.has(label)) {
      firstSeen.set(label, point.timestamp);
    }
  }

  return Array.from(firstSeen.entries())
    .sort((a, b) => new Date(a[1]).getTime() - new Date(b[1]).getTime())
    .map(([label, timestamp]) => ({ timestamp, label }));
}

function deriveBoundariesFromScoringPlays(plays: ScoringPlay[], sport?: string | null): PeriodBoundary[] {
  // Group scoring plays by period, use earliest timestamp per unique period.
  // Drop any stale earlier-game segment first (L2-163).
  const sorted = keepLatestSession(
    [...plays]
      .filter((p) => p.period && p.timestamp)
      .sort((a, b) => new Date(a.timestamp).getTime() - new Date(b.timestamp).getTime())
  );

  if (sorted.length === 0) return [];

  const firstSeen = new Map<string, string>();

  for (const play of sorted) {
    if (!play.period) continue;
    const label = normalizePeriodLabel(play.period, sport);
    if (!label) continue;
    if (!firstSeen.has(label)) {
      firstSeen.set(label, play.timestamp);
    }
  }

  return Array.from(firstSeen.entries())
    .sort((a, b) => new Date(a[1]).getTime() - new Date(b[1]).getTime())
    .map(([label, timestamp]) => ({ timestamp, label }));
}
