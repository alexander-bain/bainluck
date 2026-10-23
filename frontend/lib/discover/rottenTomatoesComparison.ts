import type { FeedFuturesData, FeedItem } from "@/lib/types";
import { answerRung, printsAPercent } from "./leaderOrder";

interface ScorePoint {
  label: string;
  value: number;
  unit: string;
  direction: string;
  probability: number;
}

export interface RottenTomatoesComparison {
  columns: ScorePoint[];
  rows: { item: FeedItem; data: FeedFuturesData; points: ScorePoint[] }[];
}

/** Presentation of an existing server bundle, never a new membership resolver.
 * Each row remains its own full question, deadline and probability curve.
 * Align only identical published labels AND typed coordinates. In particular,
 * "Above 70" is not "70+", and critic and audience scores cannot share a grid.
 * No interpolation, averaging, normalization or inferred outcome probabilities.
 */
export function rottenTomatoesComparison(items: readonly FeedItem[]): RottenTomatoesComparison | null {
  if (items.length < 2) return null;
  let measure: string | undefined;
  const rows: RottenTomatoesComparison["rows"] = [];
  for (const item of items) {
    if (item.type !== "futures") return null;
    const data = item.data as FeedFuturesData;
    // This is the explicit producer display grammar. Unrecognized questions
    // keep the existing full compact rows rather than having their scope cut off.
    const match = /^.+ · (Rotten Tomatoes(?: audience| critics)? score)$/i.exec(data.name);
    if (!match || (measure && measure !== match[1].toLowerCase())) return null;
    measure = match[1].toLowerCase();
    if (data.status !== "open" || data.resolved) return null;
    const card = (data as FeedFuturesData & { discover_card?: {
      comparison_theme?: string;
      suggested_format?: string;
      threshold_points?: unknown[];
      public_source_disagreement?: boolean;
    } }).discover_card;
    if (card?.comparison_theme !== "rotten_tomatoes_scores"
      || card.suggested_format !== "threshold_heatmap" || card.public_source_disagreement
      || !Array.isArray(card.threshold_points)) return null;
    const points: ScorePoint[] = [];
    const keys = new Set<string>();
    for (const raw of card.threshold_points) {
      if (!raw || typeof raw !== "object") return null;
      const p = raw as Record<string, unknown>;
      if (p.source !== "outcome" || typeof p.label !== "string"
        || typeof p.value !== "number" || !Number.isFinite(p.value)
        || p.value < 0 || p.value > 100 || typeof p.unit !== "string"
        || !["", "%"].includes(p.unit) || p.direction !== "above") return null;
      // Keep operator spelling explicit; the generic threshold parser's
      // direction alone does not distinguish strict Above from inclusive N+.
      const label = /^(?:Above (\d+(?:\.\d+)?)%?|(\d+(?:\.\d+)?)\+)$/.exec(p.label);
      if (!label || Number(label[1] ?? label[2]) !== p.value) return null;
      const key = pointKey(p as unknown as ScorePoint);
      if (keys.has(key)) return null;
      keys.add(key);
      if (typeof p.probability !== "number" || !printsAPercent(p.probability)
        || p.probability > 1) continue;
      points.push(p as unknown as ScorePoint);
    }
    if (points.length < 2) return null;
    rows.push({ item, data, points });
  }
  const common = rows[0].points.filter(point => rows.every(row =>
    row.points.some(other => pointKey(other) === pointKey(point))
  )).sort((a, b) => a.value - b.value);
  if (common.length < 2) return null;
  // Use the existing answer-rung rule on the server's first-ranked member,
  // with neighboring shared rungs. This selects a compact preview, not a new
  // film ranking. Every full curve stays reachable through its original link.
  const anchor = answerRung(common)!;
  const start = Math.max(0, Math.min(common.indexOf(anchor) - 1, common.length - 3));
  const columns = common.slice(start, start + 3);
  return {
    columns,
    rows: rows.map(row => ({ ...row, points: columns.map(column =>
      row.points.find(point => pointKey(point) === pointKey(column))!
    ) })),
  };
}

function pointKey(point: ScorePoint): string {
  return JSON.stringify([point.label, point.value, point.unit, point.direction]);
}
