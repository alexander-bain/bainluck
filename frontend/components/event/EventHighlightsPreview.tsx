"use client";

/**
 * #10346 pilot — three supported takeaways from one completed game, with the
 * full catalogue one tap away. Renders only what `highlightsPreviewFor` returns;
 * see `lib/eventHighlightsPreview.ts` for the evidence and what the copy may not
 * say. Phone: a swipeable row. Wider screens: three columns.
 */

import {
  ALL_MARKETS_ANCHOR_ID,
  formatQuotePercent,
  formatRecordedAt,
  sourceMark,
  type CountVisual,
  type EventHighlight,
  type EventHighlightsPreview as Preview,
  type HighlightQuote,
} from "@/lib/eventHighlightsPreview";

/** Open the catalogue's fold and bring it into view. */
export function openAllMarkets(doc: Pick<Document, "getElementById"> = document): boolean {
  const anchor = doc.getElementById(ALL_MARKETS_ANCHOR_ID);
  if (!anchor) return false;
  const fold = anchor.querySelector("details");
  if (fold) fold.open = true;
  anchor.scrollIntoView({ behavior: "smooth", block: "start" });
  return true;
}

/** One mark per official event against the line it needed. Count marks, never percent. */
function CountMarks({ visual }: { visual: CountVisual }) {
  const slots = Math.max(visual.actual, visual.line);
  const plural = visual.actual === 1 ? visual.unit : `${visual.unit}s`;
  return (
    <div data-visual="count">
      <div className="flex gap-1" aria-hidden="true">
        {Array.from({ length: slots }, (_, i) => (
          <div key={i} className="min-w-0 flex-1">
            <div
              className={`h-2.5 rounded-sm ${
                i < visual.actual ? "bg-accent-brand" : "border border-surface-border"
              }`}
              data-mark={i < visual.actual ? "hit" : "open"}
            />
            {visual.marks?.[i] && (
              <div className="mt-1 truncate text-[11px] text-text-secondary">{visual.marks[i]}</div>
            )}
          </div>
        ))}
      </div>
      <div className="mt-1.5 flex items-baseline justify-between gap-3 text-xs">
        <span className="font-semibold tabular-nums text-text-primary">
          {visual.actual} {plural}
        </span>
        <span className="tabular-nums text-text-secondary">needed {visual.line}+</span>
      </div>
    </div>
  );
}

/** One chance on the shared 0–100% scale, labelled with its phase and recorded time. */
function ChanceRow({ quote }: { quote: HighlightQuote }) {
  const pct = formatQuotePercent(quote.probability, quote.whole);
  return (
    <div data-when={quote.when}>
      {/* Fixed label and number columns, so paired bars start and scale together. */}
      <div className="grid grid-cols-[5.5rem_minmax(0,1fr)_3.75rem] items-center gap-2">
        <span className="text-xs font-medium text-text-secondary">{quote.when}</span>
        <div className="h-1.5 rounded-full bg-surface-elevated" aria-hidden="true">
          <div
            className="h-1.5 rounded-full bg-accent-brand/60"
            style={{ width: `${Math.max(0, Math.min(1, quote.probability)) * 100}%` }}
          />
        </div>
        <span className="text-right text-lg font-semibold tabular-nums text-text-primary">{pct}</span>
      </div>
      <div className="text-[11px] text-text-muted">
        {sourceMark(quote)} ·{" "}
        <time dateTime={quote.observedAt} title={`${quote.observedAt.replace("T", " ").slice(0, 19)} UTC`}>
          {formatRecordedAt(quote.observedAt)}
        </time>
      </div>
    </div>
  );
}

/** Exact-source details, only where the shown number combines more than one source. */
function Sources({ quotes }: { quotes: readonly HighlightQuote[] }) {
  const combined = quotes.filter((q) => q.contributors.length > 1);
  if (combined.length === 0) return null;
  return (
    <details className="text-[11px] text-text-muted">
      <summary className="cursor-pointer">Sources</summary>
      <ul className="mt-1 space-y-0.5">
        {combined.flatMap((q) =>
          q.contributors.map((c) => (
            <li key={`${q.when}-${c.outcomeId}`}>
              {q.when} · {c.source} {formatQuotePercent(c.probability)} ·{" "}
              <time dateTime={c.observedAt}>{formatRecordedAt(c.observedAt)}</time>
            </li>
          )),
        )}
      </ul>
    </details>
  );
}

function HighlightCard({ highlight }: { highlight: EventHighlight }) {
  const { before, after, visual } = highlight;
  const quotes = after ? [before, after] : [before];
  return (
    <li
      className="flex w-[85%] shrink-0 snap-start flex-col gap-3 rounded-xl border border-surface-border bg-surface-card p-4 md:w-auto"
      data-highlight-id={highlight.id}
    >
      <div>
        <div className="text-[11px] font-semibold uppercase tracking-[0.04em] text-text-muted">{highlight.subject}</div>
        <h3 className="mt-1 text-base font-semibold leading-snug text-text-primary">{highlight.headline}</h3>
        <p className="mt-0.5 text-sm text-text-secondary">{highlight.detail}</p>
      </div>
      {visual && <CountMarks visual={visual} />}
      <div className="flex flex-col gap-2" data-visual={after ? "paired" : "chance"}>
        <div className="text-xs font-medium text-text-primary">Chance of {before.question}</div>
        {quotes.map((q) => (
          <ChanceRow key={q.when} quote={q} />
        ))}
      </div>
      <Sources quotes={quotes} />
    </li>
  );
}

export default function EventHighlightsPreview({
  preview,
  catalogueAvailable,
}: {
  preview: Preview;
  catalogueAvailable: boolean;
}) {
  return (
    <section
      className="rounded-xl bg-surface-card p-4 shadow-card"
      aria-labelledby="event-highlights-heading"
      data-testid="event-highlights-preview"
    >
      <div className="flex items-baseline justify-between gap-3">
        <h2 id="event-highlights-heading" className="text-sm font-semibold text-text-primary">
          Three takeaways
        </h2>
        <span className="text-[11px] text-text-muted">{preview.officialSource}</span>
      </div>
      <ol className="-mx-4 mt-3 flex items-start snap-x snap-mandatory gap-3 overflow-x-auto px-4 pb-1 md:mx-0 md:grid md:grid-cols-3 md:items-start md:overflow-visible md:px-0">
        {preview.highlights.map((highlight) => (
          <HighlightCard key={highlight.id} highlight={highlight} />
        ))}
      </ol>
      {catalogueAvailable && (
        <button
          type="button"
          onClick={() => openAllMarkets()}
          className="mt-3 min-h-11 w-full rounded-lg border border-surface-border text-sm font-semibold text-text-primary"
          data-testid="event-highlights-all-markets"
        >
          See every prop and market
        </button>
      )}
    </section>
  );
}
