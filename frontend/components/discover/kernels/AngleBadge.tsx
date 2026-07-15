/**
 * The angle badge system — the WHY-now of a Discover card, one per card max.
 *
 * Design source: "Discover Card System" handoff (2026-07-15), the finalized
 * `1j` angle-in-header treatment. The brief's mandate: today's badge soup
 * (FINAL + upset + EI + For you + league + date + more) collapses to a
 * hierarchy — **state + ONE angle + the kernel**. This component owns the "ONE
 * angle" half; `KernelCard` owns state + kernel.
 *
 * There are six canonical angles. `pickAngle()` resolves the single
 * highest-priority one from a card's signals so every surface derives the same
 * badge deterministically (Phase 2 wires it to feed data; the preview passes
 * explicit angles with realistic copy).
 *
 * Colors map onto the semantic accent tokens ONLY (light-mode, no raw palette —
 * CLAUDE.md design-system rule). Surprise and stakes deliberately share the
 * amber token (both read as "high drama") and are told apart by icon + copy.
 */

export type Angle =
  | "mover"
  | "surprise"
  | "resolving_soon"
  | "stakes"
  | "for_you"
  | "banter";

export interface AngleValue {
  kind: Angle;
  /** The human copy, e.g. "Moved 12 pts this week". */
  label: string;
}

interface AngleStyle {
  icon: string;
  /** Full literal Tailwind classes so the JIT compiler picks them up. */
  className: string;
}

// Full class strings (never interpolated) so Tailwind's content scan keeps them.
const ANGLE_STYLES: Record<Angle, AngleStyle> = {
  mover: { icon: "↕", className: "text-accent-futures bg-accent-futures/15" },
  surprise: { icon: "⚠", className: "text-accent-warning bg-accent-warning/15" },
  resolving_soon: { icon: "🕐", className: "text-accent-danger bg-accent-danger/10" },
  stakes: { icon: "🔥", className: "text-accent-warning bg-accent-warning/15" },
  for_you: { icon: "✦", className: "text-accent-brand bg-accent-brand/15" },
  banter: { icon: "💬", className: "text-text-secondary bg-surface-elevated" },
};

export function AngleBadge({ angle }: { angle: AngleValue | null }) {
  if (!angle) return null;
  const style = ANGLE_STYLES[angle.kind];
  return (
    <span
      className={`inline-flex items-center gap-1 rounded-full px-2 py-0.5 text-[11px] font-medium ${style.className}`}
      data-angle={angle.kind}
    >
      <span aria-hidden="true">{style.icon}</span>
      {angle.label}
    </span>
  );
}

// ── pickAngle — the deterministic resolver (one angle per card, max) ──

export interface AngleSignals {
  /** Absolute 24h/period movement in probability POINTS (0–100). */
  deltaPoints?: number | null;
  /** True when resolution is imminent (design: red 🕐 "Resolves Sunday"). */
  resolvesSoon?: boolean;
  /** Field/duel with no dominant favorite, or an upset in progress. */
  noClearFavorite?: boolean;
  /** Elimination / championship / high-EI stakes. */
  highStakes?: boolean;
  /** Personalized for this user ("✦ For you"). */
  personalized?: boolean;
  /** A narrative/talker card with nothing more specific to say. */
  banter?: boolean;
  /** Optional custom copy overrides, keyed by angle. */
  labels?: Partial<Record<Angle, string>>;
}

/** A movement of this many points or more earns the "mover" angle. */
export const MOVER_THRESHOLD_POINTS = 5;

/**
 * Resolve the single most "why-now" angle. Priority order, highest first:
 *   1. mover           — a big move is the strongest reason to look now
 *   2. resolving_soon  — it's about to matter
 *   3. surprise        — no clear favorite / upset
 *   4. stakes          — elimination / championship
 *   5. for_you         — personalized
 *   6. banter          — narrative fallback
 * Returns null when nothing rises to a badge (a calm card is fine).
 */
export function pickAngle(signals: AngleSignals): AngleValue | null {
  const labels = signals.labels ?? {};
  const delta = signals.deltaPoints != null ? Math.abs(signals.deltaPoints) : 0;

  if (delta >= MOVER_THRESHOLD_POINTS) {
    const dir = (signals.deltaPoints ?? 0) >= 0 ? "up" : "down";
    return {
      kind: "mover",
      label: labels.mover ?? `Moved ${delta.toFixed(delta < 10 ? 1 : 0)} pts ${dir === "up" ? "up" : "down"}`,
    };
  }
  if (signals.resolvesSoon) {
    return { kind: "resolving_soon", label: labels.resolving_soon ?? "Resolving soon" };
  }
  if (signals.noClearFavorite) {
    return { kind: "surprise", label: labels.surprise ?? "No clear favorite" };
  }
  if (signals.highStakes) {
    return { kind: "stakes", label: labels.stakes ?? "High stakes" };
  }
  if (signals.personalized) {
    return { kind: "for_you", label: labels.for_you ?? "For you" };
  }
  if (signals.banter) {
    return { kind: "banter", label: labels.banter ?? "Talker" };
  }
  return null;
}
