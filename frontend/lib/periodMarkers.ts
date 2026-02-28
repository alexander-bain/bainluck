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
 */
export function derivePeriodBoundaries(
  espnHistory?: ESPNHistoryPoint[],
  winProbHistory?: Record<string, WinProbHistoryPoint[]>,
  scoringPlays?: ScoringPlay[],
): PeriodBoundary[] {
  // Try ESPN history first (most reliable)
  if (espnHistory && espnHistory.length > 1) {
    const boundaries = deriveBoundariesFromEspn(espnHistory);
    if (boundaries.length > 0) return boundaries;
  }

  // Try win prob history game_state
  if (winProbHistory) {
    const boundaries = deriveBoundariesFromWinProb(winProbHistory);
    if (boundaries.length > 0) return boundaries;
  }

  // Try scoring plays
  if (scoringPlays && scoringPlays.length > 1) {
    const boundaries = deriveBoundariesFromScoringPlays(scoringPlays);
    if (boundaries.length > 0) return boundaries;
  }

  return [];
}

function deriveBoundariesFromEspn(history: ESPNHistoryPoint[]): PeriodBoundary[] {
  // Sort by timestamp
  const sorted = [...history].sort(
    (a, b) => new Date(a.timestamp).getTime() - new Date(b.timestamp).getTime()
  );

  const boundaries: PeriodBoundary[] = [];
  const seenLabels = new Set<string>();
  let prevPeriod: string | null = null;

  for (const point of sorted) {
    if (!point.period) continue;
    const label = normalizePeriodLabel(point.period);
    if (!label) continue;

    if (prevPeriod !== null && label !== prevPeriod && !seenLabels.has(label)) {
      boundaries.push({ timestamp: point.timestamp, label });
      seenLabels.add(label);
    }
    prevPeriod = label;
  }

  return boundaries;
}

function deriveBoundariesFromWinProb(
  winProbHistory: Record<string, WinProbHistoryPoint[]>
): PeriodBoundary[] {
  // Merge all sources, extract period from game_state
  const allPoints: { timestamp: string; period: string }[] = [];

  for (const points of Object.values(winProbHistory)) {
    for (const point of points) {
      const period = (point.game_state as Record<string, unknown>)?.period;
      if (typeof period === "string" && period) {
        allPoints.push({ timestamp: point.timestamp, period });
      }
    }
  }

  if (allPoints.length < 2) return [];

  // Sort by timestamp
  allPoints.sort((a, b) => new Date(a.timestamp).getTime() - new Date(b.timestamp).getTime());

  const boundaries: PeriodBoundary[] = [];
  const seenLabels = new Set<string>();
  let prevPeriod: string | null = null;

  for (const point of allPoints) {
    const label = normalizePeriodLabel(point.period);
    if (!label) continue;

    if (prevPeriod !== null && label !== prevPeriod && !seenLabels.has(label)) {
      boundaries.push({ timestamp: point.timestamp, label });
      seenLabels.add(label);
    }
    prevPeriod = label;
  }

  return boundaries;
}

function deriveBoundariesFromScoringPlays(plays: ScoringPlay[]): PeriodBoundary[] {
  // Group scoring plays by period, use earliest timestamp per new period
  const sorted = [...plays]
    .filter((p) => p.period && p.timestamp)
    .sort((a, b) => new Date(a.timestamp).getTime() - new Date(b.timestamp).getTime());

  if (sorted.length < 2) return [];

  const boundaries: PeriodBoundary[] = [];
  const seenLabels = new Set<string>();
  let prevPeriod: string | null = null;

  for (const play of sorted) {
    if (!play.period) continue;
    const label = normalizePeriodLabel(play.period);
    if (!label) continue;

    if (prevPeriod !== null && label !== prevPeriod && !seenLabels.has(label)) {
      boundaries.push({ timestamp: play.timestamp, label });
      seenLabels.add(label);
    }
    prevPeriod = label;
  }

  return boundaries;
}
