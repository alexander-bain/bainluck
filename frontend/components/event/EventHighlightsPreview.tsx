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

function QuoteLine({ label, quote }: { label: string; quote: HighlightQuote }) {
  return (
    <div className="flex items-baseline justify-between gap-3">
      <div className="min-w-0">
        <div className="text-[11px] font-semibold uppercase tracking-[0.04em] text-text-muted">{label}</div>
        <div className="text-xs text-text-secondary">
          {quote.source} ·{" "}
          <time dateTime={quote.observedAt} title={`${quote.observedAt.replace("T", " ").slice(0, 16)} UTC`}>
            {quote.when}
          </time>
        </div>
      </div>
      <div className="text-xl font-semibold tabular-nums text-text-primary">{formatQuotePercent(quote.probability)}</div>
    </div>
  );
}

function HighlightCard({ highlight }: { highlight: EventHighlight }) {
  const { before, after } = highlight;
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
      <div className="flex flex-col gap-2 rounded-lg bg-surface-elevated p-3 md:mt-auto">
        <div className="text-xs font-medium text-text-secondary">{before.question}</div>
        <QuoteLine label={before.label ?? "Before"} quote={before} />
        {after && <QuoteLine label={after.label ?? "After"} quote={after} />}
        {before.caveat && <div className="text-xs text-text-muted">{before.caveat}</div>}
      </div>
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
      <ol className="-mx-4 mt-3 flex items-start snap-x snap-mandatory gap-3 overflow-x-auto px-4 pb-1 md:mx-0 md:grid md:grid-cols-3 md:items-stretch md:overflow-visible md:px-0">
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
