// The card Alex actually grades — extracted from `app/admin/labeling/page.tsx`
// so that #2060's display invariant can be asserted at the DISPLAY layer.
//
// ## Why this is a component now
//
// #2060 asks for "a display-layer invariant test that any two-outcome card's
// rendered values sum to exactly 100". While this JSX lived inside a stateful
// page behind admin auth, the strongest available check was a source grep — and
// a grep cannot tell a rendered field from a declared one. A mutation that
// replaced the commence-time conditional with `{false && (` passed every grep in
// the suite. So the card is a component, and the invariant is asserted against
// its real rendered output.
//
// Presentational only: no fetching, no auth, no state. Everything it needs
// arrives as props, which is what makes it renderable in a test.

import { renderedPercent } from "@/lib/renderedPercent";

export interface LabelingCardOutcome {
  name: string | null;
  probability: number | null;
  /** What the source shipped, before #2060's truncation repair. */
  name_at_source?: string | null;
  /**
   * The whole percent the SERVER rendered for this outcome (#2060). Served
   * rather than re-derived here, because the server has to compute it anyway for
   * the card fingerprint — and a client that recomputes it is a client that can
   * disagree with the digest gating its own write. Optional only for a payload
   * from a pre-#2060 backend.
   */
  rendered_percent?: number | null;
}

export interface LabelingCardData {
  name: string;
  source: string;
  category: string;
  image_url: string | null;
  hook_description: string | null;
  rendered_probability: number | null;
  top_outcomes: LabelingCardOutcome[];
  /** #2060 item 2 — a probability is ungradeable without a when. */
  commence_time?: string | null;
  resolution_date?: string | null;
  /** #2060 item 3 — `name` is the repaired text; this is what Kalshi shipped. */
  name_at_source?: string | null;
}

// ── #2060: this page had a FOURTH copy of the rounding rule ──────────────────
//
// `Math.round(val * 100)`, inline, not even calling `renderedPercent` — so the
// contract that exists to keep three runtimes agreeing was not being consulted by
// one of the surfaces it is about. It happened to compute the same answer, which
// is exactly how this kind of drift survives: it is right until the rule changes,
// and then it is silently the only place that did not.

export function pct(val: number | null | undefined): string {
  const p = renderedPercent(val ?? null);
  return p == null ? "--" : `${p}%`;
}

/** Prefer the SERVER's percent; fall back to the shared rule for old payloads. */
export function pctOf(
  served: number | null | undefined,
  raw: number | null | undefined,
): string {
  if (served != null) return `${served}%`;
  return pct(raw);
}

/** "Sat Aug 22, 5:40 PM" — the card's WHEN (#2060 item 2). */
export function whenLabel(iso: string | null | undefined): string | null {
  if (!iso) return null;
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return null;
  return d.toLocaleString(undefined, {
    weekday: "short",
    month: "short",
    day: "numeric",
    hour: "numeric",
    minute: "2-digit",
  });
}

export default function LabelingCard({ card }: { card: LabelingCardData }) {
  const starts = whenLabel(card.commence_time);
  const resolves = whenLabel(card.resolution_date);

  return (
    <div className="bg-surface-card rounded-2xl border border-surface-border overflow-hidden shadow-sm">
      {card.image_url && (
        <div className="relative h-48 bg-surface-elevated">
          {/* eslint-disable-next-line @next/next/no-img-element */}
          <img
            src={card.image_url}
            alt=""
            className="w-full h-full object-cover"
            onError={(e) => {
              (e.target as HTMLImageElement).style.display = "none";
            }}
          />
        </div>
      )}
      <div className="p-5 space-y-3">
        <div className="flex items-start justify-between gap-3">
          <h2 className="text-base font-semibold text-text-primary leading-snug flex-1">
            {card.name}
          </h2>
          {card.rendered_probability != null && (
            <span
              className="text-2xl font-bold text-accent-brand shrink-0"
              data-testid="card-headline-percent"
            >
              {/* The headline reads the SAME served integer as the first outcome
                  row. Rounding `rendered_probability` separately is how the hero
                  and the field disagree by a point on exactly the cards #2060 is
                  about. */}
              {pctOf(card.top_outcomes?.[0]?.rendered_percent, card.rendered_probability)}
            </span>
          )}
        </div>
        {/* #2060 item 2 — WHEN. Kalshi's `resolution_date` on a game market is the
            CLOSE time, not the start (gotcha #14), so it was never the answer to
            "when is this". */}
        {(starts || resolves) && (
          <div className="flex gap-3 text-[11px] text-text-muted">
            {starts && <span data-testid="card-commence">Starts {starts}</span>}
            {resolves && <span data-testid="card-resolves">Resolves {resolves}</span>}
          </div>
        )}
        {card.hook_description && (
          <p className="text-sm text-text-secondary leading-relaxed">
            {card.hook_description}
          </p>
        )}
        {card.top_outcomes && card.top_outcomes.length > 1 && (
          <div className="space-y-1 pt-1">
            {card.top_outcomes.slice(0, 4).map((o, i) => (
              <div key={i} className="flex items-center justify-between text-sm">
                <span className="text-text-secondary truncate flex-1 mr-2">
                  {o.name || "Outcome"}
                </span>
                <span className="font-mono text-text-primary" data-testid="card-outcome-percent">
                  {pctOf(o.rendered_percent, o.probability)}
                </span>
              </div>
            ))}
          </div>
        )}
        <div className="flex gap-1.5 flex-wrap pt-1">
          <span className="text-[11px] px-2 py-0.5 rounded-full bg-surface-elevated text-text-muted">
            {card.category}
          </span>
          <span className="text-[11px] px-2 py-0.5 rounded-full bg-surface-elevated text-text-muted">
            {card.source}
          </span>
        </div>
      </div>
    </div>
  );
}
