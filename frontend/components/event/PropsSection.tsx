"use client";

/**
 * PropsSection — the archetype-agnostic props body: THE SCRIPT → THE DIVERGENCE
 * → WHAT HIT.
 *
 * Queue L2-118 Phase 1, from strategy_event_page_primitives.md ("The shared
 * body … Props section — three states: THE SCRIPT (pregame expectation set) /
 * THE DIVERGENCE (movement vs pregame marks) / WHAT HIT (graded)"). This is the
 * ONE component under all three heroes (duel / field / container) — the duel
 * event page is its first consumer.
 *
 * State machine (the settled-means-settled dimension):
 *   upcoming  → THE SCRIPT      what the market expects before the event
 *   live      → THE DIVERGENCE  how far reality has moved from that script
 *   settled   → WHAT HIT        the script, graded
 *
 * Phase-1 honesty rule: the pregame-mark and graded fields (`pregame_mark`,
 * `graded_result`) are shipped by #195 (Wednesday). Until they arrive they are
 * null, and this component renders an explicit, quiet "pending" line BEHIND the
 * same interface — never a fabricated number. Phase 2 (Friday) is a payload
 * swap: fill the fields, the chrome is already here. The parent page decides
 * whether to MOUNT this section (gate on payload presence) so nothing
 * half-populated reaches production before #195.
 */

export type PropsState = "script" | "divergence" | "graded";

export interface PropMark {
  /** Stable key. */
  key: string | number;
  /** Prop label, e.g. "LeBron James 25+ points". */
  label: string;
  /**
   * THE SCRIPT: pregame expectation as a probability (0–1). #195 field — null
   * until the pregame-mark backend lands.
   */
  pregame_mark: number | null;
  /** Current / live probability (0–1). Available today. */
  current: number | null;
  /**
   * WHAT HIT: settled grade. #195 field — null until graded resolution lands.
   */
  graded_result?: "hit" | "miss" | "push" | null;
  /** Optional human-readable result, e.g. "31 pts — hit". */
  graded_label?: string | null;
}

interface PropsSectionProps {
  items: PropMark[];
  /** Explicit state, or derive from `eventStatus` when omitted. */
  state?: PropsState;
  /** Event status used to derive the state when `state` is omitted. */
  eventStatus?: string | null;
  title?: string;
}

const STATE_META: Record<PropsState, { eyebrow: string; blurb: string }> = {
  script: {
    eyebrow: "The script",
    blurb: "What the market expected before the event.",
  },
  divergence: {
    eyebrow: "The divergence",
    blurb: "How far the live number has moved from the pregame script.",
  },
  graded: {
    eyebrow: "What hit",
    blurb: "The pregame script, graded.",
  },
};

export function deriveState(eventStatus?: string | null): PropsState {
  const s = (eventStatus ?? "").toLowerCase();
  if (s === "completed" || s === "closed" || s === "settled" || s === "final") {
    return "graded";
  }
  if (s === "live" || s === "in_progress" || s === "inprogress") {
    return "divergence";
  }
  return "script";
}

function pct(p: number | null | undefined): string {
  return p == null ? "—" : `${Math.round(p * 100)}%`;
}

/**
 * Absolute movement of a prop from its pregame mark to the current number, or
 * null when either endpoint is missing (a forward-only mark that can't yet
 * diverge). Used to rank THE DIVERGENCE biggest-mover-first.
 */
function absMovement(item: PropMark): number | null {
  if (item.pregame_mark == null || item.current == null) return null;
  return Math.abs(item.current - item.pregame_mark);
}

/**
 * THE DIVERGENCE ranking: biggest mover (|current − pregame_mark|) first. Rows
 * with no computable movement (missing mark or current) sink to the bottom,
 * keeping their original relative order (stable). Non-mutating — returns a copy.
 */
function rankByDivergence(items: PropMark[]): PropMark[] {
  return items
    .map((item, i) => ({ item, i, mv: absMovement(item) }))
    .sort((a, b) => {
      if (a.mv == null && b.mv == null) return a.i - b.i;
      if (a.mv == null) return 1;
      if (b.mv == null) return -1;
      if (b.mv !== a.mv) return b.mv - a.mv;
      return a.i - b.i;
    })
    .map((x) => x.item);
}

function signedDelta(from: number | null | undefined, to: number | null | undefined): string | null {
  if (from == null || to == null) return null;
  const d = Math.round((to - from) * 100);
  if (d === 0) return "±0";
  return d > 0 ? `↑ ${d}` : `↓ ${Math.abs(d)}`;
}

export default function PropsSection({
  items,
  state,
  eventStatus,
  title = "Props",
}: PropsSectionProps) {
  if (!items || items.length === 0) return null;

  const activeState = state ?? deriveState(eventStatus);
  const meta = STATE_META[activeState];

  // THE DIVERGENCE ranks biggest-mover-first; SCRIPT and WHAT HIT keep the
  // payload order (the endpoint already orders by prominence).
  const rows = activeState === "divergence" ? rankByDivergence(items) : items;

  return (
    <section id="props-script" className="bg-surface-card rounded-card shadow-card p-6">
      <div className="flex items-baseline gap-2.5 mb-1">
        <span className="text-[11px] font-bold uppercase tracking-[0.1em] text-text-primary">
          {meta.eyebrow}
        </span>
        <span className="text-sm text-text-secondary">{title}</span>
      </div>
      <p className="text-xs text-text-muted mb-4">{meta.blurb}</p>

      <div className="space-y-2">
        {rows.map((item) => (
          <PropRow key={item.key} item={item} state={activeState} />
        ))}
      </div>
    </section>
  );
}

function PropRow({ item, state }: { item: PropMark; state: PropsState }) {
  return (
    <div className="flex items-center gap-3 py-2 border-b border-surface-elevated last:border-0">
      <span className="flex-1 min-w-0 text-sm text-text-primary truncate">{item.label}</span>
      {state === "script" && <ScriptValue item={item} />}
      {state === "divergence" && <DivergenceValue item={item} />}
      {state === "graded" && <GradedValue item={item} />}
    </div>
  );
}

/** Honest "pending" chip for a #195 field that hasn't shipped yet. */
function Pending({ note }: { note: string }) {
  return (
    <span className="font-mono text-[11px] text-text-muted tabular-nums shrink-0">{note}</span>
  );
}

function ScriptValue({ item }: { item: PropMark }) {
  if (item.pregame_mark == null) {
    // #195 seam: the pregame mark isn't captured yet.
    return <Pending note="pregame mark pending" />;
  }
  return (
    <span className="font-mono text-sm font-semibold text-text-primary tabular-nums shrink-0">
      {pct(item.pregame_mark)}
    </span>
  );
}

function DivergenceValue({ item }: { item: PropMark }) {
  const delta = signedDelta(item.pregame_mark, item.current);
  const up = delta?.startsWith("↑");
  const flat = delta === "±0";
  return (
    <div className="flex items-center gap-2 shrink-0">
      {item.pregame_mark != null ? (
        <span className="font-mono text-[11px] text-text-muted tabular-nums">
          {pct(item.pregame_mark)} →
        </span>
      ) : (
        <Pending note="script pending" />
      )}
      <span className="font-mono text-sm font-semibold text-text-primary tabular-nums">
        {pct(item.current)}
      </span>
      {delta && (
        <span
          className={[
            "font-mono text-[11px] font-bold tabular-nums px-1.5 py-0.5 rounded-full",
            flat
              ? "text-text-muted"
              : up
                ? "text-accent-brand bg-accent-brand/15"
                : "text-accent-danger bg-accent-danger/15",
          ].join(" ")}
        >
          {delta}
        </span>
      )}
    </div>
  );
}

function GradedValue({ item }: { item: PropMark }) {
  if (item.graded_result == null) {
    // #195 seam: grading hasn't landed for this prop yet.
    return <Pending note="grading pending" />;
  }
  const isHit = item.graded_result === "hit";
  const isPush = item.graded_result === "push";
  return (
    <span
      className={[
        "font-mono text-xs font-bold tabular-nums px-2 py-0.5 rounded-full shrink-0",
        isPush
          ? "text-text-muted bg-surface-elevated"
          : isHit
            ? "text-accent-brand bg-accent-brand/15"
            : "text-accent-danger bg-accent-danger/15",
      ].join(" ")}
    >
      {item.graded_label ?? (isHit ? "Hit" : isPush ? "Push" : "Miss")}
    </span>
  );
}
