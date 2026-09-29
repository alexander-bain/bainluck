import React from 'react';
import { renderToStaticMarkup } from 'react-dom/server';
import FinalGameWinnerQuote from '../../components/event/FinalGameWinnerQuote';
import type { OpenWinnerQuote } from '../../lib/gameMarketsStream';
const quote = (a=.505, b=.495): OpenWinnerQuote => ({ event_id: 7, market_id: 11, status: 'open', source: 'kalshi', market_name: 'Home vs Away', observed_at: null,
  outcomes: [{ outcome_id: 1, side: 'home', name: 'Home', probability: a, observed_at: null }, { outcome_id: 2, side: 'away', name: 'Away', probability: b, observed_at: null }] });
test('a final result stays separate from the complete open contract and honest rounded pair', () => {
  const html = renderToStaticMarkup(<><p>Final 7–3</p><FinalGameWinnerQuote quote={quote()} eventId={7} finished /></>);
  expect(html).toContain('Final 7–3');
  expect(html).toContain('aria-label="Still trading"');
  expect([...html.matchAll(/<strong[^>]*>([^<]+)<\/strong>/g)].map(match => match[1])).toEqual(['51%', '49%']);
  expect(html).not.toMatch(/just now|updated/i);
});
test('independent raw venue prices keep their values and explain non100 total', () => {
  const html = renderToStaticMarkup(<FinalGameWinnerQuote quote={quote(.65,.55)} eventId={7} finished />);
  expect(html).toContain('65%'); expect(html).toContain('55%');
  expect(html).toContain('Individual venue prices');
});
test.each(['unfinished','wrong event','closed','missing side'])('refuses %s quote', condition => {
  const q=quote(); if(condition==='closed') q.status='closed'; if(condition==='missing side') q.outcomes.pop();
  const html=renderToStaticMarkup(<FinalGameWinnerQuote quote={q} eventId={condition==='wrong event'?8:7} finished={condition!=='unfinished'} />);
  expect(html).toBe('');
});
test('terminal contract cannot show asopen after later stale snapshot', () => {
  const html=renderToStaticMarkup(<FinalGameWinnerQuote quote={quote()} eventId={7} finished closedIds={[11]} />);
  expect(html).toBe('');
});
test.each([[.50,.51,'50%','51%'],[.50,.49,'50%','49%']] as const)('near-unit raw venue pair %s/%s is not normalized', (a,b,pa,pb) => {
  const html = renderToStaticMarkup(<FinalGameWinnerQuote quote={quote(a,b)} eventId={7} finished />);
  expect([...html.matchAll(/<strong[^>]*>([^<]+)<\/strong>/g)].map(match => match[1])).toEqual([pa,pb]);
  expect(html).toContain('Individual venue prices');
});
