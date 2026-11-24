/**
 * #10090 — Team Championship Path live stream unit rules + timed DOM capture.
 */
import '../helpers/minimalDom';
import React, { act } from 'react';
import { createRoot, type Root } from 'react-dom/client';
import {
  adoptChampionshipPathResponse,
  championshipPathStreamMarketIds,
  overlayChampionshipPathPreview,
  type CommittedChampionshipState,
} from '@/lib/teamChampionshipStream';
import { useTeamChampionshipStream } from '@/hooks/useTeamChampionshipStream';
import { fetchTeamChampionshipPath, type ChampionshipPathEntry } from '@/lib/api';
import { teamHeadline } from '@/lib/teamHeadline';
import { applyMarketPreview, type MarketPreviewFrame } from '@/lib/discover/marketPreview';
import { TeamChampionshipPath } from '@/components/TeamChampionshipPath';

jest.mock('next/link', () => {
  const ReactLib = require('react');
  return {
    __esModule: true,
    default: ({ href, children, ...props }: { href: string; children: React.ReactNode }) =>
      ReactLib.createElement('a', { href, ...props }, children),
  };
});

jest.mock('@/lib/api', () => {
  const actual = jest.requireActual('@/lib/api');
  return {
    ...actual,
    API_URL: '',
    fetchTeamChampionshipPath: jest.fn(),
  };
});

class FakeEventSource {
  static instances: FakeEventSource[] = [];
  readyState = 1;
  closed = false;
  listeners: Record<string, ((event: unknown) => void)[]> = {};
  constructor(public url: string) {
    FakeEventSource.instances.push(this);
  }
  addEventListener(type: string, listener: (event: unknown) => void) {
    (this.listeners[type] ??= []).push(listener);
  }
  close() {
    this.closed = true;
    this.readyState = 2;
  }
  emit(type: string, data?: unknown) {
    act(() => (this.listeners[type] ?? []).forEach((listener) => listener({ data })));
  }
}

const wire = JSON.stringify;
const fetchPathMock = fetchTeamChampionshipPath as jest.Mock;
const realHrtimeNs = process.hrtime.bigint.bind(process.hrtime);

const STEP_1: ChampionshipPathEntry = {
  tier: 1,
  label: 'Championship',
  market_name: 'NBA Champion 2027',
  market_id: 501,
  market_ids: [501, 502],
  components: [
    {
      market_id: 501,
      outcome_id: 70,
      source: 'kalshi',
      probability: 0.2,
      observed_at: '2026-11-24T08:00:00Z',
    },
    {
      market_id: 502,
      outcome_id: 80,
      source: 'polymarket',
      probability: 0.24,
      observed_at: '2026-11-24T08:00:00Z',
    },
  ],
  probability: 0.22,
  rank: 2,
  movement: 0.01,
  season: '2026-27',
};

const STEP_4: ChampionshipPathEntry = {
  tier: 4,
  label: 'Division',
  market_name: 'Pacific Division Winner',
  market_id: 601,
  market_ids: [601],
  components: [{ market_id: 601, outcome_id: 90, source: 'kalshi', probability: 0.5 }],
  probability: 0.5,
  rank: 1,
  movement: null,
  season: '2026-27',
};

test('stream market IDs union withheld/multi-venue IDs and fall back to entry.market_id', () => {
  expect(championshipPathStreamMarketIds([STEP_1], [501, 502, 777])).toEqual([501, 502, 777]);
  const legacyEntry = { ...STEP_4, market_ids: undefined, components: undefined };
  expect(championshipPathStreamMarketIds([legacyEntry])).toEqual([601]);
});

test('preview overlay recomputes multi-venue mean, guards disagreement > 0.25, and ignores decided steps', () => {
  let previews = applyMarketPreview(
    {},
    {
      market_id: 501,
      source: 'kalshi',
      outcomes: [{ outcome_id: 70, p: 0.36, observed_at: '2026-11-24T08:00:01Z' }],
      seq: 1,
      ttl_ms: 10_000,
    } satisfies MarketPreviewFrame,
    100,
  );
  // (0.36 + 0.24) / 2 = 0.30; difference 0.12 <= 0.25 -> admitted
  const updated = overlayChampionshipPathPreview([STEP_1, STEP_4], previews, 150);
  expect(updated[0].probability).toBe(0.3);
  expect(updated[1]).toBe(STEP_4);

  // Disagreement beyond 0.25 -> keep committed
  previews = applyMarketPreview(
    previews,
    {
      market_id: 501,
      source: 'kalshi',
      outcomes: [{ outcome_id: 70, p: 0.70, observed_at: '2026-11-24T08:00:02Z' }],
      seq: 2,
      ttl_ms: 10_000,
    },
    160,
  );
  expect(overlayChampionshipPathPreview([STEP_1], previews, 170)).toEqual([STEP_1]);

  // Decided step stays untouched
  const decided: ChampionshipPathEntry = { ...STEP_4, state: 'eliminated', probability: 0.001 };
  const divPreview = applyMarketPreview(
    {},
    {
      market_id: 601,
      source: 'kalshi',
      outcomes: [{ outcome_id: 90, p: 0.25, observed_at: '2026-11-24T08:00:03Z' }],
      seq: 1,
      ttl_ms: 10_000,
    },
    180,
  );
  expect(overlayChampionshipPathPreview([decided], divPreview, 190)).toEqual([decided]);
});

test('committed adoption is forward-only by built_at and drops withheld steps', () => {
  const initial: CommittedChampionshipState = {
    path: [STEP_1, STEP_4],
    streamMarketIds: [501, 502, 601],
    builtAt: 200,
  };
  const older = adoptChampionshipPathResponse(initial, {
    team_id: 42,
    championship_path: [STEP_1],
    stream_market_ids: [501, 502],
    built_at: 150,
  });
  expect(older).toBe(initial);

  const newer = adoptChampionshipPathResponse(initial, {
    team_id: 42,
    championship_path: [STEP_1],
    stream_market_ids: [501, 502, 777],
    built_at: 210,
  });
  expect(newer.path).toEqual([STEP_1]);
  expect(newer.streamMarketIds).toEqual([501, 502, 777]);
});

describe('timed DOM capture (< 0.5 s from SSE receipt)', () => {
  const origEventSource = global.EventSource;
  let root: Root | undefined;
  let container: HTMLElement | undefined;

  beforeEach(() => {
    FakeEventSource.instances = [];
    fetchPathMock.mockReset();
    (global as unknown as { EventSource: typeof EventSource }).EventSource =
      FakeEventSource as unknown as typeof EventSource;
    jest.useFakeTimers();
    jest.setSystemTime(new Date('2026-11-24T08:00:00Z'));
  });

  afterEach(() => {
    if (root) act(() => root!.unmount());
    root = undefined;
    if (container && container.parentNode) container.parentNode.removeChild(container);
    container = undefined;
    (global as unknown as { EventSource: typeof EventSource }).EventSource = origEventSource;
    jest.useRealTimers();
  });

  function Harness({
    teamId,
    served,
    streamIds,
  }: {
    teamId: number;
    served: ChampionshipPathEntry[];
    streamIds: number[];
  }) {
    const livePath = useTeamChampionshipStream(teamId, served, streamIds);
    const headline = teamHeadline(livePath, []);
    return (
      <div>
        <span>{`headline:${headline ? Math.round(headline.probability * 100) : 'none'}%`}</span>
        <TeamChampionshipPath entries={livePath} color="#552583" />
      </div>
    );
  }

  test('renders multi-venue market_preview within < 500 ms and drops withheld steps on committed invalidation', async () => {
    fetchPathMock.mockResolvedValueOnce({
      team_id: 42,
      championship_path: [STEP_1, STEP_4],
      stream_market_ids: [501, 502, 601],
      built_at: Date.now() / 1000,
    });
    container = document.createElement('div');
    document.body.appendChild(container);
    root = createRoot(container);

    act(() => {
      root!.render(
        <Harness teamId={42} served={[STEP_1, STEP_4]} streamIds={[501, 502, 601]} />,
      );
    });
    expect(container.textContent).toContain('headline:22%');
    expect(container.textContent).toContain('Win Division');

    const sse = FakeEventSource.instances.find((s) => s.url.startsWith('/api/markets/stream'));
    expect(sse).toBeDefined();
    expect(sse!.url).toContain('501,502,601');

    await act(async () => {
      sse!.emit('open', wire({ market_ids: [501, 502, 601], unavailable_market_ids: [] }));
      await Promise.resolve();
      await Promise.resolve();
    });
    expect(fetchPathMock).toHaveBeenCalledTimes(1);

    // 1. Provisional market_preview arrival -> (0.40 + 0.24)/2 = 32% without reload or extra fetch
    const tRecvNs = realHrtimeNs();
    sse!.emit(
      'market_preview',
      wire({
        type: 'market_preview',
        preview: true,
        market_id: 501,
        source: 'kalshi',
        outcomes: [{ outcome_id: 70, p: 0.4, observed_at: '2026-11-24T08:00:01Z' }],
        seq: 1,
        ttl_ms: 10_000,
      }),
    );
    const dtPreviewMs = Number(realHrtimeNs() - tRecvNs) / 1e6;
    expect(dtPreviewMs).toBeGreaterThan(0);
    expect(dtPreviewMs).toBeLessThan(500);
    // Capture timing for #10090 record
    console.info(`[capture:team-championship-preview] dt_ms=${dtPreviewMs.toFixed(2)}`);
    expect(container.textContent).toContain('headline:32%');
    expect(container.textContent).toContain('32%');
    expect(fetchPathMock).toHaveBeenCalledTimes(1);

    // Advance past 400 ms burst cooldown so committed invalidation leads immediately
    await act(async () => {
      await jest.advanceTimersByTimeAsync(450);
    });

    // 2. Committed invalidation removes disagreed STEP_4 and replaces older preview with newer commit (0.46 + 0.24)/2 = 35%
    fetchPathMock.mockResolvedValueOnce({
      team_id: 42,
      championship_path: [
        {
          ...STEP_1,
          probability: 0.35,
          components: [
            {
              market_id: 501,
              outcome_id: 70,
              source: 'kalshi',
              probability: 0.46,
              observed_at: '2026-11-24T08:00:02Z',
            },
            STEP_1.components![1],
          ],
        },
      ],
      stream_market_ids: [501, 502, 601],
      built_at: Date.now() / 1000,
    });
    const tInvNs = realHrtimeNs();
    await act(async () => {
      sse!.emit(
        'market',
        wire({ market_id: 601, source: 'kalshi', terminal: false, invalidation: true }),
      );
      await Promise.resolve();
      await Promise.resolve();
    });
    const dtInvMs = Number(realHrtimeNs() - tInvNs) / 1e6;
    expect(fetchPathMock).toHaveBeenCalledTimes(2);
    expect(dtInvMs).toBeGreaterThan(0);
    expect(dtInvMs).toBeLessThan(500);
    console.info(`[capture:team-championship-invalidation] dt_ms=${dtInvMs.toFixed(2)}`);
    expect(container.textContent).toContain('headline:35%');
    expect(container.textContent).toContain('35%');
    expect(container.textContent).not.toContain('Win Division');
  });
});
