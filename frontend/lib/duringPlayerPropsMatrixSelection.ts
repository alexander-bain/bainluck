/** #10358: presentation of the accepted #10236.v1 projection only.
 * The caller owns transport/adoption fences. Keys, labels, blends and deltas
 * remain producer facts; this adapter never reconstructs a proposition.
 */
import { formatProbabilityPercent } from "./probabilityDisplay";

export interface DuringPropsStat {
  stat_key: string;
  label: string;
  unit: string;
  unit_singular: string;
  period_key: "full_game";
  period_label: string;
  predicate: "count_at_least";
}
export interface DuringPropsContributor {
  source: string;
  market_id: number | null;
  outcome_id: number | null;
  outcome_name: string | null;
  side: "over" | "under";
  period_key: "full_game";
  probability: number | null;
  observed_at: string | null;
}
export interface DuringPropsRow {
  question_key: string;
  subject: { key: string; label: string; kind: "player" };
  stat_key: string;
  period_key: "full_game";
  predicate: { kind: "count_at_least" | "count_at_most"; count: number; side: "over" | "under"; label: string };
  complement_question_key: string | null;
  current: { state: "quoted" | "actual_only" | "unavailable"; probability: number | null; basis: "single_source" | "blend_mean" | null; observed_at: string | null };
  contributors: DuringPropsContributor[];
  comparison: { state: "comparable" | "unavailable"; reason: string | null; baseline: { probability: number; observed_at: string; basis: "pregame_pin" } | null; delta_points: number | null };
  result: unknown;
  _market_id: number | null;
  _market_ids: number[];
  contributor_outcome_ids: number[];
}
export interface DuringPlayerProps {
  contract: "10236.v1";
  stats: DuringPropsStat[];
  rows: DuringPropsRow[];
  coverage: { scope: "linked_markets_loaded_for_event"; subjects: number; questions: number; quoted: number; actual_only: number; unavailable: number; refused: Record<string, number> };
}
export type QuestionSelection = { statKey: string; subjectKey: string; questionKey: string };
export type SourceSelection = Pick<DuringPropsContributor, "source" | "market_id" | "outcome_id" | "side" | "period_key">;

export function finiteChance(value: unknown): value is number {
  return typeof value === "number" && Number.isFinite(value) && value >= 0 && value <= 1;
}
export function quotedChance(row: DuringPropsRow): number | null {
  return row.current.state === "quoted" && finiteChance(row.current.probability) ? row.current.probability : null;
}
// The site's one percentage rule (boundaries + rounding) — never a local copy.
export function chanceLabel(value: number): string {
  return formatProbabilityPercent(value);
}
export function exactChanceLabel(value: number): string {
  return `${Number((value * 100).toPrecision(12))}%`;
}
export function comparisonPoints(row: DuringPropsRow): number | null {
  const c = row.comparison;
  const before = Date.parse(c.baseline?.observed_at ?? "");
  const now = Date.parse(row.current.observed_at ?? "");
  return quotedChance(row) !== null && c.state === "comparable" && c.reason === null &&
    c.baseline?.basis === "pregame_pin" && finiteChance(c.baseline.probability) &&
    Number.isFinite(before) && Number.isFinite(now) && before < now &&
    typeof c.delta_points === "number" && Number.isFinite(c.delta_points) && Math.abs(c.delta_points) <= 100
    ? c.delta_points : null;
}
export function compactChange(row: DuringPropsRow): string | null {
  const points = comparisonPoints(row);
  return points !== null && Math.abs(points) >= 1 ? `${points > 0 ? "+" : "−"}${Math.round(Math.abs(points))}%` : null;
}
export function selectQuestion(row: DuringPropsRow): QuestionSelection {
  return { statKey: row.stat_key, subjectKey: row.subject.key, questionKey: row.question_key };
}
export function resolveQuestion(data: DuringPlayerProps | null, selection: QuestionSelection): DuringPropsRow | null {
  if (data?.contract !== "10236.v1") return null;
  return data.rows.find(row => row.stat_key === selection.statKey && row.subject.key === selection.subjectKey && row.question_key === selection.questionKey) ?? null;
}
export function sourceKey(source: SourceSelection): string {
  return JSON.stringify([source.source, source.market_id, source.outcome_id, source.side, source.period_key]);
}
export function resolveSource(row: DuringPropsRow | null, selected: SourceSelection): DuringPropsContributor | null {
  return row?.contributors.find(source => sourceKey(source) === sourceKey(selected)) ?? null;
}
export function complementQuestion(data: DuringPlayerProps, row: DuringPropsRow): DuringPropsRow | null {
  const sameQuestionContext = (other: DuringPropsRow) => other.subject.key === row.subject.key &&
    other.stat_key === row.stat_key && other.period_key === row.period_key && other.predicate.side !== row.predicate.side;
  const direct = row.complement_question_key ? data.rows.find(other => other.question_key === row.complement_question_key && sameQuestionContext(other)) : null;
  if (direct) return direct;
  // The deployed producer serves under -> over, with null on the over row.
  // Reverse that exact served edge for navigation, never its count/key/price.
  const reverse = data.rows.filter(other => other.complement_question_key === row.question_key && sameQuestionContext(other));
  return reverse.length === 1 ? reverse[0] : null;
}

export interface MatrixColumn { key: string; label: string; underOnly: boolean }
export interface MatrixPlayer { key: string; label: string; cells: Array<DuringPropsRow | null> }
export function matrixForStat(data: DuringPlayerProps | null, statKey: string): { columns: MatrixColumn[]; players: MatrixPlayer[]; questions: number; withoutQuote: number } {
  if (data?.contract !== "10236.v1" || !data.stats.some(stat => stat.stat_key === statKey && stat.period_key === "full_game" && stat.predicate === "count_at_least")) return { columns: [], players: [], questions: 0, withoutQuote: 0 };
  const rows = data.rows.filter(row => row.stat_key === statKey && row.subject.kind === "player" && row.period_key === "full_game" &&
    Number.isInteger(row.predicate.count) && row.predicate.count >= 0);
  // An unpaired under stays reachable under its OWN served label, with no
  // grid price. It never creates an over threshold, key or 1-minus quote.
  const gridRows = rows.filter(row => {
    if (row.predicate.kind === "count_at_least" && row.predicate.side === "over") return true;
    if (row.predicate.kind !== "count_at_most" || row.predicate.side !== "under") return false;
    const over = complementQuestion(data, row);
    // Hide an under only when that exact over detail can navigate back to it.
    // Ambiguous or withdrawn edges leave the own under question in the grid.
    return !over || complementQuestion(data, over)?.question_key !== row.question_key;
  });
  const columnKey = (row: DuringPropsRow) => JSON.stringify([row.predicate.kind, row.predicate.count, row.predicate.label]);
  const columns = Array.from(new Map(gridRows.map(row => [columnKey(row), { key: columnKey(row), label: row.predicate.label,
    underOnly: row.predicate.side === "under", count: row.predicate.count }])).values())
    .sort((a, b) => Number(a.underOnly) - Number(b.underOnly) || a.count - b.count);
  const subjects = Array.from(new Map(gridRows.map(row => [row.subject.key, row.subject])).values());
  const players = subjects.map(subject => ({ key: subject.key, label: subject.label,
    cells: columns.map(column => gridRows.find(row => row.subject.key === subject.key && columnKey(row) === column.key) ?? null) }));
  return { columns, players, questions: rows.length, withoutQuote: rows.filter(row => quotedChance(row) === null).length };
}
