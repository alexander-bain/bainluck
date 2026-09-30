import '../helpers/minimalDom';
import React, { act } from 'react';
import { createRoot, type Root } from 'react-dom/client';
import { useDiscoverPriceStream } from '../../hooks/useDiscoverPriceStream';
import { fetchDiscoverPriceCards } from '../../lib/api';
import type { DiscoverGroupedItem } from '../../components/discover/types';
import type { FeedItem } from '../../lib/types';

jest.mock('../../lib/api', () => ({ API_URL: '', fetchDiscoverPriceCards: jest.fn() }));
jest.mock('../../hooks/useMarketStream', () => ({ useMarketStream: jest.fn() }));

const groups: DiscoverGroupedItem[] = [{
  type: 'single', item: { type: 'futures', data: { id: 112894, status: 'open' } } as FeedItem,
}];
const fetcher = fetchDiscoverPriceCards as jest.Mock;
let root: Root | undefined;
let held: ReturnType<typeof useDiscoverPriceStream>;
let visibilityListener: (() => void) | undefined;

function Harness({ principal = 'signed-out' }: { principal?: string }) {
  held = useDiscoverPriceStream(groups, principal);
  return null;
}
function mount(principal = 'signed-out') {
  const container = document.createElement('div');
  document.body.appendChild(container);
  root = createRoot(container);
  act(() => root!.render(<Harness principal={principal} />));
}
function unmount() {
  const current = root;
  root = undefined;
  act(() => current?.unmount());
}

beforeEach(() => {
  jest.useFakeTimers();
  fetcher.mockReset().mockResolvedValue({ items: [], dispositions: {}, built_at: 1 });
  Object.defineProperty(document, 'visibilityState', { configurable: true, value: 'visible' });
  visibilityListener = undefined;
  jest.spyOn(document, 'addEventListener').mockImplementation((type, callback) => {
    if (type === 'visibilitychange') visibilityListener = callback as () => void;
  });
  // Node/Jest timers accept any receiver; browser timers do not. Keep the
  // mounted production hook and dispatcher real, and enforce that browser
  // contract at the global timer boundary (not a copied dependency object).
  const cancel = globalThis.clearTimeout;
  jest.spyOn(globalThis, 'clearTimeout').mockImplementation(function (this: unknown, timer) {
    if (this !== undefined && this !== globalThis && this !== window) {
      throw new TypeError('Illegal invocation');
    }
    cancel(timer);
  });
});
afterEach(() => {
  // Restore the receiver guard before best-effort cleanup of a failing test.
  jest.restoreAllMocks();
  if (root) unmount();
  jest.useRealTimers();
});

test('leaving Discover cancels pending dispatch and fallback timers without crashing', () => {
  mount();
  act(() => held.setPriceVisibility('card', ['futures-112894'], true));
  expect(jest.getTimerCount()).toBe(2);
  expect(() => unmount()).not.toThrow();
  expect(jest.getTimerCount()).toBe(0);
  jest.advanceTimersByTime(120_000);
  expect(fetcher).not.toHaveBeenCalled();
});

test('leaving with a request in flight still cancels the fallback and aborts the read', async () => {
  fetcher.mockImplementation(() => new Promise(() => {}));
  mount();
  act(() => held.setPriceVisibility('card', ['futures-112894'], true));
  await act(async () => { await jest.advanceTimersByTimeAsync(0); });
  const signal = fetcher.mock.calls[0][2] as AbortSignal;
  expect(signal.aborted).toBe(false);
  expect(() => unmount()).not.toThrow();
  expect(signal.aborted).toBe(true);
  expect(jest.getTimerCount()).toBe(0);
});

test('repeated hide/show and principal changes retire each dispatcher safely', () => {
  mount();
  for (let i = 0; i < 2; i++) {
    Object.defineProperty(document, 'visibilityState', { configurable: true, value: 'hidden' });
    expect(() => act(() => visibilityListener?.())).not.toThrow();
    expect(jest.getTimerCount()).toBe(0);
    Object.defineProperty(document, 'visibilityState', { configurable: true, value: 'visible' });
    act(() => visibilityListener?.());
    expect(jest.getTimerCount()).toBe(1);
  }
  expect(() => act(() => root!.render(<Harness principal="new-principal" />))).not.toThrow();
  expect(jest.getTimerCount()).toBe(1);
  expect(() => unmount()).not.toThrow();
  expect(jest.getTimerCount()).toBe(0);
});
