import type { OpenWinnerQuote } from '@/lib/gameMarketsStream';
import { formatProbabilityPercent } from '@/lib/probabilityDisplay';
import { renderedCardPercents, renderedPercent, cardSumReason } from '@/lib/renderedPercent';
import { formatSourceAge } from '@/lib/sourceAge';

/** An open contract remains separate from the game's final score and winner. */
export default function FinalGameWinnerQuote({ quote, eventId, finished, closedIds = [] }: {
  quote: OpenWinnerQuote | null | undefined; eventId: number; finished: boolean; closedIds?: number[];
}) {
  if (!finished || !quote || quote.event_id !== eventId || quote.status !== 'open' ||
      closedIds.includes(quote.market_id) || !['kalshi', 'polymarket'].includes(quote.source)) return null;
  const sides = new Set(quote.outcomes.map(row => row.side));
  if (sides.size !== quote.outcomes.length || !sides.has('home') || !sides.has('away') ||
      quote.outcomes.some(row => !['home', 'away', 'draw'].includes(row.side) ||
        !Number.isFinite(row.probability) || row.probability < 0 || row.probability > 1)) return null;
  const probabilities = quote.outcomes.map(row => row.probability);
  const unit = Math.abs(probabilities.reduce((sum, p) => sum + p, 0) - 1) < 1e-9;
  const percents = unit ? renderedCardPercents(probabilities) : probabilities.map(renderedPercent);
  const age = formatSourceAge(quote.observed_at);
  return <section aria-label="Still trading" className="rounded-xl border border-surface-border bg-surface-card p-4 mb-4">
    <h2 className="text-sm font-semibold text-text-primary">Still trading</h2>
    <p className="text-xs text-text-muted mt-1">{quote.source === 'kalshi' ? 'Kalshi' : 'Polymarket'}{age ? ` · ${age}` : ''}</p>
    <div className="flex flex-wrap gap-x-6 gap-y-2 mt-3">
      {quote.outcomes.map((row, index) => <div key={row.outcome_id} className="min-w-0 text-sm text-text-primary">
        <span className="break-words">{row.name}</span>{' '}
        <strong className="tabular-nums">{formatProbabilityPercent(row.probability, { rendered: percents[index] })}</strong>
      </div>)}
    </div>
    {!unit || cardSumReason(probabilities) ? <p className="text-xs text-text-muted mt-2">Individual venue prices</p> : null}
  </section>;
}
