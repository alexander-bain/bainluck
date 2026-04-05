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
 * Normalize ESPN's verbose period strings into short chart labels.
 *
 * Basketball/Football: "1st Quarter" -> "Q1", "Halftime" -> "HT"
 * Hockey: "1st Period" -> "P1"
 * Baseball: "Top 3rd" / "Bottom 3rd" -> "3"
 * Soccer: "1st Half" -> "1H", "2nd Half" -> "2H"
 * Generic: "Overtime" -> "OT"
 */
export function normalizePeriodLabel(raw: string): string {
  if (!raw) return "";
  let s = raw.trim();

  // Reject pre-game date strings like "Wed, March 25th at 10:00 PM EDT"
  // These leak from ESPN status_detail during game transitions
  if (/\b(January|February|March|April|May|June|July|August|September|October|November|December)\b/i.test(s)) return "";
  if (/\b(Mon|Tue|Wed|Thu|Fri|Sat|Sun)\b.*\bat\b/i.test(s)) return "";

  // Strip clock prefix: "11:05 - 1st Quarter" → "1st Quarter"
  // ESPN status_detail includes game clock before the period name
  s = s.replace(/^[\d.:]+\s*-\s*/, "");

  // Strip "End of " / "Start of " prefix: "End of 1st Quarter" → "1st Quarter"
  s = s.replace(/^(?:end|start)\s+of\s+/i, "");

  // Halftime
  if (/^half\s*time$/i.test(s) || s === "HT") return "HT";

  // Overtime variants
  if (/^(overtime|ot)$/i.test(s)) return "OT";
  if (/^(\d+)\w*\s+overtime$/i.test(s)) {
    const m = s.match(/^(\d+)/);
    return m ? `OT${m[1]}` : "OT";
  }

  // Quarter (basketball, football): "1st Quarter" -> "Q1"
  const qMatch = s.match(/^(\d+)\w*\s+quarter$/i);
  if (qMatch) return `Q${qMatch[1]}`;

  // Period (hockey): "1st Period" -> "P1"
  const pMatch = s.match(/^(\d+)\w*\s+period$/i);
  if (pMatch) return `P${pMatch[1]}`;

  // Half (soccer): "1st Half" -> "1H"
  const hMatch = s.match(/^(\d+)\w*\s+half$/i);
  if (hMatch) return `${hMatch[1]}H`;

  // Baseball innings: "Top 3rd" / "Bottom 3rd" / "Mid 3rd" -> "3"
  const iMatch = s.match(/^(?:top|bottom|mid|end)\s+(\d+)/i);
  if (iMatch) return iMatch[1];

  // Plain ordinal inning: "3rd" -> "3" (sometimes ESPN just sends this)
  const ordMatch = s.match(/^(\d+)(?:st|nd|rd|th)$/i);
  if (ordMatch) return ordMatch[1];

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
): PeriodBoundary[] {
  // Top priority: backend-computed period markers from scoring_plays table.
  // These come from StatPal play-by-play and have period info on every play,
  // covering games where ESPN and win_prob_history have no period data.
  if (periodMarkers && periodMarkers.length > 0) {
    const boundaries = periodMarkers.map((m) => ({
      timestamp: m.timestamp,
      label: normalizePeriodLabel(m.period),
    })).filter((b) => b.label);
    if (boundaries.length > 0) return applyCommenceTime(boundaries, commenceTime);
  }

  // Prefer win prob history — its timestamps are always present in chartData
  // (added via ensurePoint), so ReferenceLine x values will match chart categories.
  // ESPN history timestamps come from a separate table (ESPNSnapshot) and may not
  // have matching entries in the chart data when win_prob_snapshots deduped them.
  if (winProbHistory) {
    const boundaries = deriveBoundariesFromWinProb(winProbHistory);
    if (boundaries.length > 0) return applyCommenceTime(boundaries, commenceTime);
  }

  // Fallback to ESPN history (explicit period field, different table)
  if (espnHistory && espnHistory.length > 1) {
    const boundaries = deriveBoundariesFromEspn(espnHistory);
    if (boundaries.length > 0) return applyCommenceTime(boundaries, commenceTime);
  }

  // Try scoring plays
  if (scoringPlays && scoringPlays.length > 1) {
    const boundaries = deriveBoundariesFromScoringPlays(scoringPlays);
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
    const isFirstPeriod = /^(Q1|P1|1H|1|R1)$/i.test(first.label);
    if (isFirstPeriod) {
      result[0] = { ...first, timestamp: commenceTime };
    }
  }

  return result;
}

function deriveBoundariesFromEspn(history: ESPNHistoryPoint[]): PeriodBoundary[] {
  // Sort by timestamp
  const sorted = [...history].sort(
    (a, b) => new Date(a.timestamp).getTime() - new Date(b.timestamp).getTime()
  );

  // Collect the first timestamp we see for each unique period label
  const firstSeen = new Map<string, string>();

  for (const point of sorted) {
    if (!point.period) continue;
    const label = normalizePeriodLabel(point.period);
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
  winProbHistory: Record<string, WinProbHistoryPoint[]>
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

  // Sort by timestamp
  allPoints.sort((a, b) => new Date(a.timestamp).getTime() - new Date(b.timestamp).getTime());

  // Collect the first timestamp we see for each unique period label.
  // This handles missed transitions (e.g., ESPN sync started in Q2).
  const firstSeen = new Map<string, string>();

  for (const point of allPoints) {
    const label = normalizePeriodLabel(point.period);
    if (!label) continue;
    if (!firstSeen.has(label)) {
      firstSeen.set(label, point.timestamp);
    }
  }

  return Array.from(firstSeen.entries())
    .sort((a, b) => new Date(a[1]).getTime() - new Date(b[1]).getTime())
    .map(([label, timestamp]) => ({ timestamp, label }));
}

function deriveBoundariesFromScoringPlays(plays: ScoringPlay[]): PeriodBoundary[] {
  // Group scoring plays by period, use earliest timestamp per unique period
  const sorted = [...plays]
    .filter((p) => p.period && p.timestamp)
    .sort((a, b) => new Date(a.timestamp).getTime() - new Date(b.timestamp).getTime());

  if (sorted.length === 0) return [];

  const firstSeen = new Map<string, string>();

  for (const play of sorted) {
    if (!play.period) continue;
    const label = normalizePeriodLabel(play.period);
    if (!label) continue;
    if (!firstSeen.has(label)) {
      firstSeen.set(label, play.timestamp);
    }
  }

  return Array.from(firstSeen.entries())
    .sort((a, b) => new Date(a[1]).getTime() - new Date(b[1]).getTime())
    .map(([label, timestamp]) => ({ timestamp, label }));
}
