/** @jest-environment jsdom */

import React, { act } from 'react';
import { createRoot } from 'react-dom/client';
import { FuturesChart } from '../../components/FuturesChart';
import type { FuturesOutcomeHistory } from '../../lib/types';

function renderHtml(element: React.ReactElement): string {
  const container = document.createElement('div');
  const root = createRoot(container);
  act(() => {
    root.render(element);
  });
  const html = container.innerHTML;
  act(() => {
    root.unmount();
  });
  return html;
}

describe('Step F3 — Atlas chart marks on FuturesChart (#883)', () => {
  const openHistory: FuturesOutcomeHistory[] = [
    {
      outcome_id: 501,
      name: 'Florida',
      history: [
        {
          timestamp: '2026-09-01T16:00:00Z',
          probability: 0.22,
          american_odds: null,
          bookmaker: 'kalshi',
        },
        // 25-day gap: must still draw one continuous step path (#11929, NEVER_A_HOLE_MS)
        {
          timestamp: '2026-09-26T18:30:00Z',
          probability: 0.26,
          american_odds: null,
          bookmaker: 'kalshi',
        },
        {
          timestamp: '2026-10-15T20:15:00Z',
          probability: 0.29,
          american_odds: null,
          bookmaker: 'kalshi',
        },
      ],
    },
  ];

  const settledHistory: FuturesOutcomeHistory[] = [
    {
      outcome_id: 601,
      name: 'Yes',
      history: [
        {
          timestamp: '2026-10-01T14:00:00Z',
          probability: 0.38,
          american_odds: null,
          bookmaker: 'kalshi',
        },
        {
          timestamp: '2026-10-20T19:45:00Z',
          probability: 0.58,
          american_odds: null,
          bookmaker: 'kalshi',
        },
        // Synthetic settlement spike: must be stripped from the plotted line and shown as a word
        {
          timestamp: '2026-11-04T06:00:00Z',
          probability: 1.0,
          american_odds: null,
          bookmaker: 'settlement',
        },
      ],
    },
  ];

  it('keeps default FuturesChart markup unchanged when atlas is omitted', () => {
    const html = renderHtml(
      <FuturesChart
        historyData={openHistory}
        selectedOutcomes={new Set([501])}
        onToggleOutcome={() => {}}
        fixedYAxis
        fieldCeiling
      />,
    );

    expect(html).not.toContain('data-testid="atlas-chart-mark-key"');
    expect(html).not.toContain('data-testid="atlas-chart-opening-mark"');
    expect(html).not.toContain('data-testid="atlas-chart-result-word"');
  });

  it('draws hollow opening mark, solid recorded marks, and a continuous step line across gaps when atlas is enabled', () => {
    const html = renderHtml(
      <FuturesChart
        historyData={openHistory}
        selectedOutcomes={new Set([501])}
        onToggleOutcome={() => {}}
        fixedYAxis
        fieldCeiling
        atlas
      />,
    );

    expect(html).toContain('data-testid="atlas-chart-mark-key"');
    expect(html).toContain('>Opening<');
    expect(html).toContain('>Recorded reading<');
    expect(html).toContain('>Change<');
    expect(html).toContain('Tap any reading for exact time (PT)');
    expect(html).toContain('data-testid="atlas-chart-opening-mark"');
    expect(html).toContain('data-testid="atlas-chart-recorded-mark"');

    // Decision 11-A + #11929: one continuous step path (`H ... V ...`) with a single `M` command
    const pathMatches = Array.from(
      html.matchAll(/<path d="(M [^"]+)" fill="none" stroke="[^"]+" stroke-width="2"/g),
    );
    expect(pathMatches.length).toBe(1);
    const d = pathMatches[0][1];
    expect(d.match(/M /g)?.length).toBe(1);
    expect(d).toContain(' H ');
    expect(d).toContain(' V ');
  });

  it('shows exact PT timestamp and probability when a reader taps any real reading mark', async () => {
    const container = document.createElement('div');
    document.body.appendChild(container);
    const root = createRoot(container);
    try {
      await act(async () => {
        root.render(
          <FuturesChart
            historyData={openHistory}
            selectedOutcomes={new Set([501])}
            onToggleOutcome={() => {}}
            fixedYAxis
            fieldCeiling
            atlas
          />,
        );
      });

      const hits = container.querySelectorAll('[data-testid="atlas-chart-reading-hit"]');
      expect(hits.length).toBe(3);
      expect(container.querySelector('[data-testid="atlas-chart-selected-reading"]')).toBeNull();

      // Tap the opening reading
      await act(async () => {
        hits[0].dispatchEvent(new MouseEvent('click', { bubbles: true }));
      });

      const openingReadout = container.querySelector(
        '[data-testid="atlas-chart-selected-reading"]',
      );
      expect(openingReadout).not.toBeNull();
      expect(openingReadout?.textContent).toContain('Florida');
      expect(openingReadout?.textContent).toContain('22%');
      expect(openingReadout?.textContent).toContain('Opening');
      expect(openingReadout?.textContent).toContain('PT');
      expect(openingReadout?.innerHTML).toContain('bg-surface-card');
      expect(openingReadout?.innerHTML).not.toContain('#FFFFFF');

      // Tap a recorded reading
      await act(async () => {
        hits[2].dispatchEvent(new MouseEvent('click', { bubbles: true }));
      });

      const recordedReadout = container.querySelector(
        '[data-testid="atlas-chart-selected-reading"]',
      );
      expect(recordedReadout?.textContent).toContain('29%');
      expect(recordedReadout?.textContent).toContain('Recorded');
      expect(recordedReadout?.textContent).toContain('PT');
    } finally {
      await act(async () => {
        root.unmount();
      });
      container.remove();
    }
  });

  it('strips settlement rows from the chart line and renders the settled result as a word (✓ Won / ✗ Lost)', () => {
    const html = renderHtml(
      <FuturesChart
        historyData={settledHistory}
        selectedOutcomes={new Set([601])}
        onToggleOutcome={() => {}}
        fixedYAxis
        fieldCeiling
        settled
        atlas
      />,
    );

    expect(html).toContain('data-testid="atlas-chart-result-word"');
    expect(html).toContain('✓ Won');
    expect(html).toContain('Result as a word');
    // Only the 2 real pre-settlement readings are tappable marks; the 1.0 settlement row is excluded
    const hitMatches = html.match(/data-testid="atlas-chart-reading-hit"/g) ?? [];
    expect(hitMatches.length).toBe(2);
  });

  it('does not label the first point of a windowed or partial history as Opening', () => {
    const windowedHtml = renderHtml(
      <FuturesChart
        historyData={openHistory}
        selectedOutcomes={new Set([501])}
        onToggleOutcome={() => {}}
        fixedYAxis
        fieldCeiling
        atlas
        atlasIncludesOpening={false}
      />,
    );

    expect(windowedHtml).not.toContain('data-testid="atlas-chart-opening-mark"');
    expect(windowedHtml).not.toContain('Opening');
    const recordedMatches =
      windowedHtml.match(/data-testid="atlas-chart-recorded-mark"/g) ?? [];
    expect(recordedMatches.length).toBe(3);

    const withheldHtml = renderHtml(
      <FuturesChart
        historyData={openHistory}
        selectedOutcomes={new Set([501])}
        onToggleOutcome={() => {}}
        fixedYAxis
        fieldCeiling
        historyWithheld
        atlas
      />,
    );

    expect(withheldHtml).not.toContain('data-testid="atlas-chart-opening-mark"');
    expect(withheldHtml).not.toContain('Opening');
  });
});
