import type { OpenWinnerQuote } from '@/lib/gameMarketsStream';
import { formatProbabilityPercent } from '@/lib/probabilityDisplay';
import { renderedCardPercents, renderedPercent, cardSumReason } from '@/lib/renderedPercent';
import { formatSourceAge } from '@/lib/sourceAge';

/** #9484: the result is the hero's; this is compact secondary contract context,
 *  never a second headline. Same copy as iPhone's FinalGameWinnerQuoteView. */
export const FINAL_QUOTE_CAPTION = 'Last market price. The result is the score above.';

/** The market's own name, only when it says more than the two team names
 *  (Kalshi's "Game 2: …" does; Polymarket's bare matchup repeats the title). */
export function finalQuoteContextName(quote: Pick<OpenWinnerQuote, 'market_name' | 'outcomes'>): string | null {
  const name = (quote.market_name ?? '').trim();
  if (!name) return null;
  const words = (text: string) => text.toLowerCase().split(/[^\p{L}\p{N}]+/u).filter(Boolean);
  const teams = new Set(quote.outcomes.flatMap(row => words(row.name)));
  const connectors = new Set(['vs', 'v', 'at', 'versus']);
  return words(name).every(word => connectors.has(word) || teams.has(word)) ? null : name;
}

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
  const venue = quote.source === 'kalshi' ? 'Kalshi' : 'Polymarket';
  const context = finalQuoteContextName(quote);
  return <section aria-label={`${venue} winner market`} data-testid="final-game-open-winner-quote"
    className="rounded-xl border border-surface-border bg-surface-card px-3 py-2.5 mb-4">
    <h2 className="text-xs font-semibold text-text-secondary">{venue} winner market{age ? ` · ${age}` : ''}</h2>
    {context ? <p className="text-xs text-text-secondary mt-0.5 break-words">{context}</p> : null}
    <div className="flex flex-wrap gap-x-6 gap-y-1 mt-1.5">
      {quote.outcomes.map((row, index) => <div key={row.outcome_id} className="min-w-0 text-sm text-text-primary">
        <span className="break-words">{row.name}</span>{' '}
        <strong className="tabular-nums">{formatProbabilityPercent(row.probability, { rendered: percents[index] })}</strong>
      </div>)}
    </div>
    {!unit || cardSumReason(probabilities) ? <p className="text-xs text-text-muted mt-1">Individual venue prices</p> : null}
    <p className="text-xs text-text-secondary mt-1">{FINAL_QUOTE_CAPTION}</p>
  </section>;
}
