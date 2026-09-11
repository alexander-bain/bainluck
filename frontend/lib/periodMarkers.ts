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
 */
const BARE_PERIOD_UNIT: Array<[RegExp, (n: string) => string]> = [
  [/^americanfootball_/i, (n) => `Q${n}`],
  [/^basketball_/i, (n) => `Q${n}`],
  [/^icehockey_/i, (n) => `P${n}`],
  [/^soccer_/i, (n) => `${n}H`],
];

/** The sport-aware completion of a bare period number, or null to leave it be. */
function labelBarePeriod(n: string, sport?: string | null): string | null {
  if (!sport) return null;
  for (const [prefix, format] of BARE_PERIOD_UNIT) {
    if (prefix.test(sport)) return format(n);
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
