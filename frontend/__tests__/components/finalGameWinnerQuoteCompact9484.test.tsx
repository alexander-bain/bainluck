import React from 'react';
import { renderToStaticMarkup } from 'react-dom/server';
import FinalGameWinnerQuote, { FINAL_QUOTE_CAPTION, finalQuoteContextName } from '../../components/event/FinalGameWinnerQuote';
import type { OpenWinnerQuote } from '../../lib/gameMarketsStream';

// #9484 specimen: event 15323743, ALDS G2 CLE 3 – CWS 4, Polymarket 63624759 open
// after the final at CWS b .999 / CLE b 0 — the typical postgame endpoint shape.
const specimen = (over: Partial<OpenWinnerQuote> = {}): OpenWinnerQuote => ({
  event_id: 15323743, market_id: 63624759, status: 'open', source: 'polymarket',
  market_name: 'Chicago White Sox vs. Cleveland Guardians', observed_at: null,
  outcomes: [
    { outcome_id: 1, side: 'home', name: 'Cleveland Guardians', probability: 0.001, observed_at: null },
    { outcome_id: 2, side: 'away', name: 'Chicago White Sox', probability: 0.999, observed_at: null },
  ],
  ...over,
});
const render = (quote: OpenWinnerQuote) =>
  renderToStaticMarkup(<FinalGameWinnerQuote quote={quote} eventId={15323743} finished />);
const strongs = (html: string) => [...html.matchAll(/<strong[^>]*>([^<]+)<\/strong>/g)].map(m => m[1]);

test('a finished page reads the quote as secondary venue context, not a second headline', () => {
  const html = render(specimen());
  expect(html).not.toContain('Still trading');
  expect(html).toMatch(/<h2 class="[^"]*text-xs[^"]*">Polymarket winner market<\/h2>/);
  expect(html.split(FINAL_QUOTE_CAPTION)).toHaveLength(2);
});

test('the endpoint postgame quote keeps <1% / >99%; only the result can claim certainty', () => {
  expect(strongs(render(specimen()))).toEqual(['&lt;1%', '&gt;99%']);
});

test("Polymarket's bare matchup repeats the title and is dropped", () => {
  expect(finalQuoteContextName(specimen())).toBeNull();
  expect(render(specimen())).not.toContain('Chicago White Sox vs. Cleveland Guardians');
});

test("Kalshi's game-numbered name says more than the teams and is kept", () => {
  const kalshi = specimen({ source: 'kalshi', market_name: 'Game 2: Chicago WS vs Cleveland' });
  expect(finalQuoteContextName(kalshi)).toBe('Game 2: Chicago WS vs Cleveland');
  const html = render(kalshi);
  expect(html).toContain('Kalshi winner market');
  expect(html).toContain('Game 2: Chicago WS vs Cleveland');
});

test.each(['', '   '])('blank market name %j prints no context line', name => {
  expect(finalQuoteContextName(specimen({ market_name: name }))).toBeNull();
  expect(render(specimen({ market_name: name })).match(/<p /g)).toHaveLength(1);
});
