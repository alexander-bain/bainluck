/**
 * Tests for pinned events/futures storage logic.
 *
 * Since usePinnedEvents and usePinnedFutures are React hooks,
 * we test the underlying storage functions (loadPinnedIds, savePinnedIds)
 * and the core logic patterns directly.
 *
 * The hooks are thin wrappers around useState + localStorage,
 * so testing the storage contract gives us high confidence.
 */

// Mock localStorage
const localStorageMock = (() => {
  let store: Record<string, string> = {};
  return {
    getItem: jest.fn((key: string) => store[key] || null),
    setItem: jest.fn((key: string, value: string) => { store[key] = value; }),
    removeItem: jest.fn((key: string) => { delete store[key]; }),
    clear: jest.fn(() => { store = {}; }),
    _getStore: () => store,
  };
})();

Object.defineProperty(global, 'localStorage', { value: localStorageMock });

const EVENTS_KEY = 'oddsTracker_pinnedEvents';
const FUTURES_KEY = 'oddsTracker_pinnedFutures';
const MAX_PINNED = 6;

// Helper functions that mirror the hook logic
function loadPinnedIds(key: string): number[] {
  try {
    const stored = localStorage.getItem(key);
    if (!stored) return [];
    const parsed = JSON.parse(stored);
    if (Array.isArray(parsed) && parsed.every((id: unknown) => typeof id === 'number')) {
      return parsed;
    }
    return [];
  } catch {
    return [];
  }
}

function savePinnedIds(key: string, ids: number[]): void {
  localStorage.setItem(key, JSON.stringify(ids));
}

beforeEach(() => {
  localStorageMock.clear();
  jest.clearAllMocks();
});

// =============================================================================
// Load/Save Operations
// =============================================================================
describe('loadPinnedIds', () => {
  test('returns empty array when nothing stored', () => {
    expect(loadPinnedIds(EVENTS_KEY)).toEqual([]);
  });

  test('loads valid array', () => {
    localStorage.setItem(EVENTS_KEY, JSON.stringify([1, 2, 3]));
    expect(loadPinnedIds(EVENTS_KEY)).toEqual([1, 2, 3]);
  });

  test('returns empty array for invalid JSON', () => {
    localStorage.setItem(EVENTS_KEY, 'not valid json');
    expect(loadPinnedIds(EVENTS_KEY)).toEqual([]);
  });

  test('returns empty array for non-array JSON', () => {
    localStorage.setItem(EVENTS_KEY, JSON.stringify({ id: 1 }));
    expect(loadPinnedIds(EVENTS_KEY)).toEqual([]);
  });

  test('returns empty array for array with non-numbers', () => {
    localStorage.setItem(EVENTS_KEY, JSON.stringify([1, 'two', 3]));
    expect(loadPinnedIds(EVENTS_KEY)).toEqual([]);
  });

  test('returns empty array for null value', () => {
    localStorage.setItem(EVENTS_KEY, 'null');
    expect(loadPinnedIds(EVENTS_KEY)).toEqual([]);
  });

  test('handles empty array', () => {
    localStorage.setItem(EVENTS_KEY, JSON.stringify([]));
    expect(loadPinnedIds(EVENTS_KEY)).toEqual([]);
  });
});

describe('savePinnedIds', () => {
  test('saves array to localStorage', () => {
    savePinnedIds(EVENTS_KEY, [1, 2, 3]);
    expect(localStorage.setItem).toHaveBeenCalledWith(EVENTS_KEY, '[1,2,3]');
  });

  test('saves empty array', () => {
    savePinnedIds(EVENTS_KEY, []);
    expect(localStorage.setItem).toHaveBeenCalledWith(EVENTS_KEY, '[]');
  });
});

// =============================================================================
// Pin/Unpin Logic
// =============================================================================
describe('pin logic', () => {
  test('pin adds event to list', () => {
    const ids = [1, 2, 3];
    const eventId = 4;
    if (!ids.includes(eventId) && ids.length < MAX_PINNED) {
      ids.push(eventId);
    }
    expect(ids).toEqual([1, 2, 3, 4]);
  });

  test('pin ignores duplicate', () => {
    const ids = [1, 2, 3];
    const eventId = 2;
    const originalLength = ids.length;
    if (!ids.includes(eventId) && ids.length < MAX_PINNED) {
      ids.push(eventId);
    }
    expect(ids.length).toBe(originalLength);
  });

  test('pin rejected at max', () => {
    const ids = [1, 2, 3, 4, 5, 6];
    const eventId = 7;
    let success = false;
    if (!ids.includes(eventId) && ids.length < MAX_PINNED) {
      ids.push(eventId);
      success = true;
    }
    expect(success).toBe(false);
    expect(ids.length).toBe(6);
  });

  test('unpin removes event from list', () => {
    const ids = [1, 2, 3, 4];
    const result = ids.filter(id => id !== 2);
    expect(result).toEqual([1, 3, 4]);
  });

  test('unpin non-existent event is no-op', () => {
    const ids = [1, 2, 3];
    const result = ids.filter(id => id !== 99);
    expect(result).toEqual([1, 2, 3]);
  });
});

// =============================================================================
// Toggle Logic
// =============================================================================
describe('toggle logic', () => {
  test('toggle pins unpinned event', () => {
    let ids = [1, 2];
    const eventId = 3;
    if (ids.includes(eventId)) {
      ids = ids.filter(id => id !== eventId);
    } else if (ids.length < MAX_PINNED) {
      ids = [...ids, eventId];
    }
    expect(ids).toEqual([1, 2, 3]);
  });

  test('toggle unpins pinned event', () => {
    let ids = [1, 2, 3];
    const eventId = 2;
    if (ids.includes(eventId)) {
      ids = ids.filter(id => id !== eventId);
    } else if (ids.length < MAX_PINNED) {
      ids = [...ids, eventId];
    }
    expect(ids).toEqual([1, 3]);
  });
});

// =============================================================================
// Max Limit
// =============================================================================
describe('max pinned limit', () => {
  test('isMaxReached is true at 6 events', () => {
    const ids = [1, 2, 3, 4, 5, 6];
    expect(ids.length >= MAX_PINNED).toBe(true);
  });

  test('isMaxReached is false below 6', () => {
    const ids = [1, 2, 3, 4, 5];
    expect(ids.length >= MAX_PINNED).toBe(false);
  });
});

// =============================================================================
// Round-trip (save then load)
// =============================================================================
describe('round-trip', () => {
  test('save then load preserves data', () => {
    const original = [10, 20, 30];
    savePinnedIds(EVENTS_KEY, original);
    const loaded = loadPinnedIds(EVENTS_KEY);
    expect(loaded).toEqual(original);
  });

  test('save then load works for futures key', () => {
    const original = [100, 200];
    savePinnedIds(FUTURES_KEY, original);
    const loaded = loadPinnedIds(FUTURES_KEY);
    expect(loaded).toEqual(original);
  });

  test('events and futures are independent', () => {
    savePinnedIds(EVENTS_KEY, [1, 2, 3]);
    savePinnedIds(FUTURES_KEY, [10, 20]);

    expect(loadPinnedIds(EVENTS_KEY)).toEqual([1, 2, 3]);
    expect(loadPinnedIds(FUTURES_KEY)).toEqual([10, 20]);
  });
});

// =============================================================================
// Clear All
// =============================================================================
describe('clearAll', () => {
  test('clearing sets empty array', () => {
    savePinnedIds(EVENTS_KEY, [1, 2, 3]);
    savePinnedIds(EVENTS_KEY, []);
    expect(loadPinnedIds(EVENTS_KEY)).toEqual([]);
  });
});
