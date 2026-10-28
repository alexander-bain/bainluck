/**
 * #10090 — WHICH STATE A SURFACE ADOPTED, as compact strings for the page's
 * `data-display-*` (headline) and `data-chart-*` (chart) attributes.
 *
 * Passive: every identity is read off state the page already holds — the
 * committed fold revision (`lib/foldRevision.ts`), the authority-v3
 * domain/session the preview reader admitted (`lib/authorityPreview.ts`), and
 * the revision a pushed frame carried. Nothing here selects a value, opens a
 * transport or adds an id the producer does not already send.
 *
 * Equal values are the reason this exists: `data-probability` and the SVG path
 * cannot tell two adoptions of the same number apart, and these strings can.
 * The empty string always means UNAVAILABLE — never "same as before". A
 * refused or expired preview is not displayed, so it never appears here; the
 * surface reports what it actually shows instead.
 *
 * Three clocks stay separate: `receivedAt` is the preview's monotonic receipt
 * (`performance.now()`), `observedAt` is the source observation clock, and the
 * DOM evaluation time belongs to whoever samples the attributes. DOM is not
 * paint.
 */
import { parseFoldRevision } from "./foldRevision";
import type { BlendPreviewState } from "./blendPreview";
import type { LiveChartFrame, LiveChartPoint } from "./liveChartHistory";

/** `fold:<row>=<rev>,…` in numeric row order, or "" when no valid vector. */
export function foldIdentity(value: unknown): string {
  const vector = parseFoldRevision(value);
  if (!vector) return "";
  const rows = Object.keys(vector).sort((a, b) => Number(a) - Number(b) || (a < b ? -1 : 1));
  return rows.length ? `fold:${rows.map(row => `${row}=${vector[row]}`).join(",")}` : "";
}

/**
 * The admitted preview's v3 identity: authority domain and stream session,
 * then the fold sequence (several rows) or epoch/sequence (one row), then the
 * committed base it was composed on. "" without an admitted v3 authority.
 */
export function previewIdentity(state: BlendPreviewState | null | undefined): string {
  const authority = state?.authority;
  if (!state || !authority) return "";
  const base = foldIdentity(state.baseFoldRevision ?? { [String(state.eventId)]: state.baseRev });
  const order = authority.fold ? `f${state.seq}` : `e${state.epoch}.s${state.seq}`;
  return `v3:${authority.incarnation}:${authority.namespace}:${authority.session}:${order}${base ? `:${base}` : ""}`;
}

export type DisplayBasis = "preview" | "committed" | "unavailable";

export interface HeadlineDisplayIdentity {
  basis: DisplayBasis;
  state: string;
  /** Monotonic receipt of the displayed preview; null for committed/unavailable. */
  receivedAt: number | null;
  /** Source observation clock of the displayed value, or null when unknown. */
  observedAt: string | null;
}

export const UNAVAILABLE_HEADLINE: HeadlineDisplayIdentity = {
  basis: "unavailable", state: "", receivedAt: null, observedAt: null,
};

/**
 * The headline's adopted state. `heroBlend` is the page's own answer that the
 * hero shows the selected blend; `previewShown` is `displayedPreview` !== null
 * for the same render. A fallback (history edge, opening line) has no adopted
 * blend identity, so it is unavailable rather than borrowing the detail's.
 */
export function headlineDisplayIdentity(input: {
  heroBlend: boolean;
  previewShown: boolean;
  preview: BlendPreviewState | null | undefined;
  committedRevision: unknown;
  observedAt: string | null | undefined;
}): HeadlineDisplayIdentity {
  if (!input.heroBlend) return UNAVAILABLE_HEADLINE;
  const observedAt = typeof input.observedAt === "string" && Number.isFinite(Date.parse(input.observedAt))
    ? input.observedAt : null;
  if (input.previewShown) {
    const receivedAt = input.preview?.receivedAt;
    return {
      basis: "preview", state: previewIdentity(input.preview), observedAt,
      receivedAt: typeof receivedAt === "number" && Number.isFinite(receivedAt) ? receivedAt : null,
    };
  }
  return { basis: "committed", state: foldIdentity(input.committedRevision), receivedAt: null, observedAt };
}

/** `data-display-*` for the hero element. Strings only; "" = unavailable. */
export function headlineDisplayAttributes(identity: HeadlineDisplayIdentity | null | undefined) {
  const id = identity ?? UNAVAILABLE_HEADLINE;
  return {
    "data-display-basis": id.basis,
    "data-display-state": id.state,
    "data-display-received": id.receivedAt === null ? "" : String(Math.round(id.receivedAt * 1000) / 1000),
    "data-display-observed-at": id.observedAt ?? "",
  };
}

export type ChartEndpointBasis = "preview" | "push" | "hero" | "hero-edge" | "history" | "unavailable";

export interface ChartEndpointIdentity {
  /** The exact timestamp of the aggregate point the identity belongs to. */
  at: string;
  basis: ChartEndpointBasis;
  state: string;
  /** Committed history behind the line: `rev=<served history fold>;through=<served edge time>`. */
  coverage: string;
}

type ServedHistory = {
  aggregate_line?: LiveChartPoint[] | null;
  history_fold_revision?: unknown;
  blend_edge_fold_revision?: unknown;
} | undefined | null;

const lastOf = (line: LiveChartPoint[] | null | undefined) =>
  line && line.length > 0 ? line[line.length - 1] : undefined;

/**
 * Which input put the chart line's last point there, decided by OBJECT
 * identity and exact instants, never by comparing values. The page's pipeline
 * keeps every served point it does not rewrite and copies everything else
 * (`mergeLiveChartHistory`, `pinChartEdgeToHero`, `appendHeroObservation`,
 * `overlayBlendPreviewLine`), so:
 *
 * - `line` is not `final`'s own line → the preview projection drew it;
 * - the served point itself → `history` (only the served EDGE has a revision);
 * - a copy at a served instant → the served edge rewritten with the headline's
 *   committed value (`hero-edge`: the pin, or #8749's synthetic-edge repair);
 * - at an admitted frame's instant → that pushed frame and its own revision
 *   (a merged frame never shares a served instant, and an appended headline is
 *   strictly newer than every point already on the line);
 * - otherwise → the headline's committed observation appended (`hero`).
 *
 * `frames` must be the admitted bank `final` was merged from (or a superset
 * of the finished arm's subset — that arm appends no headline), never the raw
 * stream bank: a refused frame is not on the chart.
 */
export function chartEndpointIdentity(input: {
  served: ServedHistory;
  final: { aggregate_line?: LiveChartPoint[] | null } | undefined | null;
  line: LiveChartPoint[] | null | undefined;
  frames: LiveChartFrame[];
  heroRevision: unknown;
  preview: BlendPreviewState | null | undefined;
}): ChartEndpointIdentity | null {
  const { served, final, line, frames } = input;
  const servedLine = served?.aggregate_line ?? [];
  const servedEdge = lastOf(servedLine);
  const coverage = `rev=${foldIdentity(served?.history_fold_revision)};through=${servedEdge?.timestamp ?? ""}`;
  const endpoint = lastOf(line);
  if (!endpoint) return null;
  const at = endpoint.timestamp;
  const instant = Date.parse(at);
  if (line !== (final?.aggregate_line ?? undefined)) {
    return { at, basis: "preview", state: previewIdentity(input.preview), coverage };
  }
  if (servedLine.includes(endpoint)) {
    return {
      at, basis: "history",
      state: endpoint === servedEdge ? foldIdentity(served?.blend_edge_fold_revision) : "",
      coverage,
    };
  }
  if (servedLine.some(point => Date.parse(point.timestamp) === instant)) {
    return { at, basis: "hero-edge", state: foldIdentity(input.heroRevision), coverage };
  }
  const frame = frames.find(point => Date.parse(point.timestamp) === instant);
  if (frame) return { at, basis: "push", state: foldIdentity(frame.rev), coverage };
  return { at, basis: "hero", state: foldIdentity(input.heroRevision), coverage };
}

/**
 * `data-chart-*` for the chart wrapper. `drawnAt` is the exact aggregate point
 * the end dot draws (OddsChart's carried `bainLuckAt`), or undefined when the
 * dot is not the blend (a checkpoint, a single source, nothing drawn). The
 * line's identity applies only to that same point.
 */
export function chartEndpointAttributes(
  drawnAt: string | undefined, identity: ChartEndpointIdentity | null | undefined,
) {
  const matches = drawnAt !== undefined && identity != null && identity.at === drawnAt;
  return {
    "data-chart-endpoint-at": drawnAt ?? "",
    "data-chart-endpoint-basis": matches ? identity.basis : "unavailable",
    "data-chart-endpoint-state": matches ? identity.state : "",
    "data-chart-history": identity?.coverage ?? "",
  };
}
