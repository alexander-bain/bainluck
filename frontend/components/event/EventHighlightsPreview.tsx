"use client";

/**
 * #10346 pilot — three supported takeaways from one completed game, with the
 * full catalogue one tap away. Renders only what `highlightsPreviewFor` returns;
 * see `lib/eventHighlightsPreview.ts` for the evidence and what the copy may not
 * say. Phone: a swipeable row. Wider screens: three columns.
 *
 * Every card has the same anatomy (Design, 2026-10-22): subject, the official
 * fact, one short supporting line, its graphic, the chance(s) with their phase,
 * then ONE "Sources" fold at the card's foot holding the providers, contributors
 * and recorded times. A closed card carries no provider or clock rows; the
 * series card alone keeps a visible recorded-day cue so its after-game number
 * cannot read as current. Cards stretch to the row and the fold sits at the
 * foot, so a short card has no blank pocket under it on the phone and its fold
 * lines up with its neighbours'. No clamp, truncation or fixed height: large
 * text grows the card.
 */

import {
  ALL_MARKETS_ANCHOR_ID,
  formatQuotePercent,
  formatRecordedAt,
  formatRecordedDays,
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
              <div className="mt-1 break-words text-[11px] leading-tight text-text-secondary">{visual.marks[i]}</div>
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

/**
 * One chance on the shared 0–100% scale, labelled with its phase. Provenance
 * lives in Sources. Its three cells join the card's one chance grid (the row
 * itself is `display: contents`), so paired bars share one track by
 * construction at every text size. When the card is too narrow for three
 * columns at the reader's text size, the phase moves onto its own line above
 * its bar and number — still visible, never squeezed out.
 */
function ChanceRow({ quote }: { quote: HighlightQuote }) {
  const pct = formatQuotePercent(quote.probability, quote.whole);
  return (
    <div data-when={quote.when} className="contents">
      <span className="text-xs font-medium text-text-secondary [@container(max-width:14rem)]:col-span-2">{quote.when}</span>
      <div className="h-1.5 rounded-full bg-surface-elevated" aria-hidden="true">
        <div
          className="h-1.5 rounded-full bg-accent-brand/60"
          style={{ width: `${Math.max(0, Math.min(1, quote.probability)) * 100}%` }}
        />
      </div>
      <span className="whitespace-nowrap text-right text-lg font-semibold tabular-nums text-text-primary">{pct}</span>
    </div>
  );
}

/** A recorded instant in the reader's zone; the exact UTC instant, labelled, on hover. */
function Recorded({ iso }: { iso: string }) {
  return (
    <time dateTime={iso} title={`${iso.replace("T", " ").slice(0, 19)} UTC`}>
      {formatRecordedAt(iso)}
    </time>
  );
}

/**
 * The card's one exact-source fold: each shown number with its source and
 * recorded time, and every contributor when a number combines more than one.
 */
function Sources({ quotes, note }: { quotes: readonly HighlightQuote[]; note?: string }) {
  return (
    <details className="mt-auto text-[11px] text-text-muted" data-sources>
      <summary className="cursor-pointer">Sources</summary>
      <ul className="mt-1 space-y-0.5">
        {note && <li>{note}</li>}
        {quotes.map((q) =>
          q.contributors.length > 1 ? (
            <li key={q.when}>
              {q.when} {formatQuotePercent(q.probability, q.whole)} combines:
              <ul className="pl-3">
                {q.contributors.map((c) => (
                  <li key={c.outcomeId}>
                    {c.source} {formatQuotePercent(c.probability)} · <Recorded iso={c.observedAt} />
                  </li>
                ))}
              </ul>
            </li>
          ) : (
            <li key={q.when}>
              {q.when} {formatQuotePercent(q.probability, q.whole)} · {sourceMark(q)} · <Recorded iso={q.observedAt} />
            </li>
          ),
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
      <div className="flex flex-col gap-2 [container-type:inline-size]" data-visual={after ? "paired" : "chance"}>
        <div className="text-xs font-medium text-text-primary">Chance of {before.question}</div>
        {/* One grid for every chance on the card: the label column wraps between words, the
            bar keeps a visible minimum, the number column fits the widest value. Narrower
            than 14rem (a width that grows with the reader's text size), the label takes
            its own line and the bar and number share the row beneath it. */}
        <div
          className="grid grid-cols-[minmax(min-content,5.5rem)_minmax(2.5rem,1fr)_auto] items-center gap-2 [@container(max-width:14rem)]:grid-cols-[minmax(2.5rem,1fr)_auto] [@container(max-width:14rem)]:gap-y-1"
          data-chance-grid
        >
          {quotes.map((q) => (
            <ChanceRow key={q.when} quote={q} />
          ))}
        </div>
        {after && (
          <div className="text-[11px] text-text-muted" data-recorded-days>
            Recorded {formatRecordedDays(quotes.map((q) => q.observedAt))}
          </div>
        )}
      </div>
      <Sources quotes={quotes} note={highlight.sourceNote} />
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
      <ol className="-mx-4 mt-3 flex items-stretch snap-x snap-mandatory gap-3 overflow-x-auto px-4 pb-1 md:mx-0 md:grid md:grid-cols-3 md:items-stretch md:overflow-visible md:px-0">
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
