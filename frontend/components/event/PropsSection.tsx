"use client";

/**
 * PropsSection — the archetype-agnostic props body: THE SCRIPT → THE DIVERGENCE
 * → WHAT HIT.
 *
 * Queue L2-118 Phase 1, from strategy_event_page_primitives.md ("The shared
 * body … Props section — three states: THE SCRIPT (pregame expectation set) /
 * THE DIVERGENCE (movement vs pregame marks) / WHAT HIT (graded)"). This is the
 * ONE component under all three heroes (duel / field / container).
 *
 * State machine (the settled-means-settled dimension):
 *   upcoming  → THE SCRIPT      what the market expects before the event
 *   live      → THE DIVERGENCE  how far reality has moved from that script
 *   settled   → WHAT HIT        the script, graded
 *
 * Alex's ruling (The Open 2026): the section stops being a wall of numbers.
 * Marks that carry a `kind` (golf today; any prop-heavy event tomorrow —
 * majors, award shows) route to a SHAPE-appropriate visual:
 *   binary → a divergence bar: the pregame mark is a tick on the track, the
 *            current probability is the fill — the gap IS the story, visible
 *            without reading a number.
 *   field  → a named top-3 mini-race (question + named outcomes with heat
 *            bars). NEVER a probability without a name — the "Top Asian/
 *            Oceanic golfer has a probability but no name" bug class.
 *   ladder → the shared QuantityGroup heat ladder (the same visual as the
 *            Scoring & Records section Alex called out as great).
 * Marks WITHOUT a kind (game props from routes/events.py) render exactly the
 * legacy rows — nothing regresses behind this change.
 *
 * Honesty rules carried forward unchanged: null pregame/graded fields render an
 * explicit quiet "pending" line, never a fabricated number; `pending_label`
 * (L2-123 / #199 — the wide-spread/no-trade capture class) wins over any stray
 * price and renders the honest state, never blank.
 */

import QuantityGroup, { type QuantityRung } from "@/components/QuantityGroup";
import { probabilityHeat } from "@/lib/probabilityColors";

export type PropsState = "script" | "divergence" | "graded";

/** A named outcome riding on a field/ladder mark (probability-only). */
export interface PropMarkOutcome {
  name: string | null;
  probability: number | null;
  opening_probability?: number | null;
}

export interface PropMark {
  /** Stable key. */
  key: string | number;
  /** Prop label, e.g. "LeBron James 25+ points". */
  label: string;
  /**
   * Prop archetype — decides the visual (see header). Absent → legacy row
   * rendering (game props that predate the shape contract).
   */
  kind?: "binary" | "ladder" | "field" | null;
  /** The bare question ("Top American Golfer") — `label` may bake the favorite
   *  in for legacy rendering; the visual renderers use this. */
  question?: string | null;
  /** Top priced outcomes: field → top 3, ladder → its rungs, binary → []. */
  outcomes?: PropMarkOutcome[] | null;
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
  /**
   * The Open 2026 p0 (settled-means-settled): this mark is individually graded
   * even while the section as a whole is live (a completed round on an
   * in-progress tournament). When true the row renders WHAT HIT regardless of
   * the section state — a completed round can never show live odds.
   */
  settled?: boolean | null;
  /**
   * L2-123 / #199 honesty seam: when set, this prop family carries NO honest price
   * (the wide-spread/no-trade capture class — e.g. a not-yet-live round leader). The
   * row renders this quiet label ("Opens after Round 1", "No market yet") instead of
   * a fabricated flat number or an arbitrary crowned leader — and never blank.
   */
  pending_label?: string | null;
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

/** A card mark carries a shape-appropriate visual: a field or ladder with ≥2
 *  named outcomes and no pending state. Everything else renders as a row. */
function isCardMark(item: PropMark): boolean {
  if (item.pending_label?.trim()) return false;
  if (item.kind !== "field" && item.kind !== "ladder") return false;
  const outs = (item.outcomes ?? []).filter(
    (o) => o.name && typeof o.probability === "number",
  );
  return outs.length >= 2;
}

/** A binary mark with a live number renders the divergence-bar row. */
function isBinaryBarMark(item: PropMark): boolean {
  return (
    item.kind === "binary" && !item.pending_label?.trim() && item.current != null
  );
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
  // payload order (the endpoint already orders by prominence). Cards and rows
  // partition AFTER ranking so both halves keep the movement order.
  const ranked = activeState === "divergence" ? rankByDivergence(items) : items;
  const cards = ranked.filter(isCardMark);
  const rows = ranked.filter((item) => !isCardMark(item));

  return (
    <section id="props-script" className="bg-surface-card rounded-card shadow-card p-6">
      <div className="flex items-baseline gap-2.5 mb-1">
        <span className="text-[11px] font-bold uppercase tracking-[0.1em] text-text-primary">
          {meta.eyebrow}
        </span>
        <span className="text-sm text-text-secondary">{title}</span>
      </div>
      <p className="text-xs text-text-muted mb-4">{meta.blurb}</p>

      {rows.length > 0 && (
        <div className="space-y-2">
          {rows.map((item) =>
            isBinaryBarMark(item) ? (
              <BinaryBarRow key={item.key} item={item} state={activeState} />
            ) : (
              <PropRow key={item.key} item={item} state={activeState} />
            ),
          )}
        </div>
      )}

      {cards.length > 0 && (
        <div className={`grid gap-3 sm:grid-cols-2 ${rows.length > 0 ? "mt-4" : ""}`}>
          {cards.map((item) =>
            item.kind === "ladder" ? (
              <LadderPropCard key={item.key} item={item} />
            ) : (
              <FieldPropCard key={item.key} item={item} />
            ),
          )}
        </div>
      )}
    </section>
  );
}

// ---------------------------------------------------------------------------
// Rows — legacy contract, unchanged (game props + pending + no-price marks).
// ---------------------------------------------------------------------------

function PropRow({ item, state }: { item: PropMark; state: PropsState }) {
  // L2-123 / #199: a family with no honest price renders one quiet pending label
  // ("Opens after Round N" / "No market yet") in every state — never a fabricated
  // number, never a crowned arbitrary leader, never blank.
  const pending = item.pending_label?.trim();
  // The Open 2026 p0: a mark that is individually settled (a completed round on a
  // still-live tournament) renders WHAT HIT even though the section is otherwise
  // live — settled-means-settled, no live odds for a concluded round.
  const rowState: PropsState = item.settled ? "graded" : state;
  return (
    <div className="flex items-center gap-3 py-2 border-b border-surface-elevated last:border-0">
      <span className="flex-1 min-w-0 text-sm text-text-primary truncate">{item.label}</span>
      {pending ? (
        <Pending note={pending} />
      ) : (
        <>
          {rowState === "script" && <ScriptValue item={item} />}
          {rowState === "divergence" && <DivergenceValue item={item} />}
          {rowState === "graded" && <GradedValue item={item} />}
        </>
      )}
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

// ---------------------------------------------------------------------------
// Binary — the divergence bar. The pregame mark is a tick on the track, the
// current probability is the fill: the gap between them IS the divergence,
// visible without reading a number.
// ---------------------------------------------------------------------------

function BinaryBarRow({ item, state }: { item: PropMark; state: PropsState }) {
  const cur = item.current;
  const mark = item.pregame_mark;
  const heat = probabilityHeat(cur);
  const fillPct = cur != null ? Math.max(2, Math.round(cur * 100)) : 0;
  const tickPct = mark != null ? Math.round(mark * 100) : null;
  return (
    <div className="py-2 border-b border-surface-elevated last:border-0">
      <div className="flex items-center gap-3">
        <span className="flex-1 min-w-0 text-sm text-text-primary truncate">
          {item.question ?? item.label}
        </span>
        {state === "graded" ? (
          <GradedValue item={item} />
        ) : (
          <DivergenceValue item={item} />
        )}
      </div>
      <div className="relative mt-1.5 h-2 rounded-full bg-surface-elevated overflow-hidden">
        <div
          className={`absolute inset-y-0 left-0 rounded-full ${heat.bar}`}
          style={{ width: `${fillPct}%` }}
        />
        {tickPct != null && (
          <div
            className="absolute inset-y-0 w-0.5 bg-text-muted"
            style={{ left: `${Math.min(99, Math.max(0, tickPct))}%` }}
            aria-hidden
          />
        )}
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Field — a named top-3 mini-race. The question is the header; every number
// sits NEXT TO its name (the "probability with no name" bug class can't
// recur). The favorite carries the opening → current arc.
// ---------------------------------------------------------------------------

function FieldPropCard({ item }: { item: PropMark }) {
  const outs = (item.outcomes ?? []).filter(
    (o) => o.name && typeof o.probability === "number",
  );
  return (
    <div className="rounded-lg border border-surface-elevated p-3">
      <div className="text-xs font-semibold uppercase tracking-wide text-text-secondary mb-2">
        {item.question ?? item.label}
      </div>
      <div className="space-y-1.5">
        {outs.map((o, i) => {
          const heat = probabilityHeat(o.probability);
          const w = Math.max(2, Math.round((o.probability ?? 0) * 100));
          const delta =
            i === 0 ? signedDelta(o.opening_probability, o.probability) : null;
          const up = delta?.startsWith("↑");
          const flat = delta === "±0";
          return (
            <div key={`${o.name}-${i}`}>
              <div className="flex items-center gap-2">
                <span className="flex-1 min-w-0 text-sm text-text-primary truncate">
                  {o.name}
                </span>
                {delta && !flat && (
                  <span
                    className={[
                      "font-mono text-[10px] font-bold tabular-nums px-1 py-0.5 rounded-full",
                      up
                        ? "text-accent-brand bg-accent-brand/15"
                        : "text-accent-danger bg-accent-danger/15",
                    ].join(" ")}
                  >
                    {delta}
                  </span>
                )}
                <span
                  className={`font-mono text-sm font-semibold tabular-nums shrink-0 ${heat.text}`}
                >
                  {pct(o.probability)}
                </span>
              </div>
              <div className="mt-0.5 h-1.5 rounded-full bg-surface-elevated overflow-hidden">
                <div
                  className={`h-full rounded-full ${heat.bar}`}
                  style={{ width: `${w}%` }}
                />
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Ladder — the shared QuantityGroup heat ladder (same visual language as the
// Scoring & Records section): one question, its rungs, heat top-to-bottom.
// ---------------------------------------------------------------------------

/** First number in an outcome label ("Under 63.5" → 63.5, "2+ …" → 2) for the
 *  ladder's ascending sort. */
function rungValue(name: string): number | undefined {
  const m = name.match(/-?\d+(?:\.\d+)?/);
  return m ? Number(m[0]) : undefined;
}

function LadderPropCard({ item }: { item: PropMark }) {
  const rungs: QuantityRung[] = (item.outcomes ?? [])
    .filter((o) => o.name && typeof o.probability === "number")
    .map((o) => ({
      key: o.name as string,
      label: o.name as string,
      probability: o.probability,
      value: rungValue(o.name as string),
    }));
  return (
    <div className="rounded-lg border border-surface-elevated p-3">
      <div className="text-xs font-semibold uppercase tracking-wide text-text-secondary mb-1">
        {item.question ?? item.label}
      </div>
      <QuantityGroup bare rungs={rungs} wideLabels />
    </div>
  );
}
