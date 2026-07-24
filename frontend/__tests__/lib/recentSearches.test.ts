// L2-178 — recent-searches versioned parse + graceful reset. The search
// surfaces persist recent queries in localStorage; a stored value from an older
// or foreign shape must never crash the UI or surface non-string entries.

const localStorageMock = (() => {
  let store: Record<string, string> = {};
  return {
    getItem: jest.fn((key: string) => (key in store ? store[key] : null)),
    setItem: jest.fn((key: string, value: string) => {
      store[key] = value;
    }),
    removeItem: jest.fn((key: string) => {
      delete store[key];
    }),
    clear: jest.fn(() => {
      store = {};
    }),
    _set: (key: string, value: string) => {
      store[key] = value;
    },
  };
})();

// The module guards on `typeof window === "undefined"`, so both globals must exist.
Object.defineProperty(global, "window", { value: {}, writable: true });
Object.defineProperty(global, "localStorage", { value: localStorageMock });

import { getRecentSearches, saveRecentSearch } from "@/lib/recentSearches";

const KEY = "bainluck_recent_searches";

beforeEach(() => {
  localStorageMock.clear();
  jest.clearAllMocks();
});

describe("getRecentSearches", () => {
  it("returns [] when nothing is stored", () => {
    expect(getRecentSearches()).toEqual([]);
  });

  it("reads the versioned envelope", () => {
    localStorageMock._set(KEY, JSON.stringify({ v: 1, items: ["celtics", "open"] }));
    expect(getRecentSearches()).toEqual(["celtics", "open"]);
  });

  it("migrates a legacy bare string[] (pre-L2-178)", () => {
    localStorageMock._set(KEY, JSON.stringify(["pats", "world cup"]));
    expect(getRecentSearches()).toEqual(["pats", "world cup"]);
  });

  it("gracefully resets on an unknown/newer version", () => {
    localStorageMock._set(KEY, JSON.stringify({ v: 99, items: ["x"] }));
    expect(getRecentSearches()).toEqual([]);
  });

  it("does NOT crash and drops non-string entries in an old object shape", () => {
    // An old shape stored objects instead of strings — must not throw and must
    // not surface non-string entries downstream.
    localStorageMock._set(
      KEY,
      JSON.stringify([{ q: "celtics" }, "lakers", 42, null]),
    );
    expect(getRecentSearches()).toEqual(["lakers"]);
  });

  it("returns [] on malformed JSON without throwing", () => {
    localStorageMock._set(KEY, "{not json");
    expect(() => getRecentSearches()).not.toThrow();
    expect(getRecentSearches()).toEqual([]);
  });
});

describe("saveRecentSearch", () => {
  it("writes the versioned envelope and dedupes, newest-first", () => {
    saveRecentSearch("celtics");
    saveRecentSearch("lakers");
    saveRecentSearch("celtics"); // move to front, no dupe
    const stored = JSON.parse(localStorageMock.getItem(KEY) as string);
    expect(stored.v).toBe(1);
    expect(stored.items).toEqual(["celtics", "lakers"]);
  });

  it("ignores blank / too-short queries", () => {
    saveRecentSearch(" ");
    saveRecentSearch("a");
    expect(getRecentSearches()).toEqual([]);
  });

  it("caps at 5 entries", () => {
    for (const q of ["one", "two", "three", "four", "five", "six"]) {
      saveRecentSearch(q);
    }
    const items = getRecentSearches();
    expect(items).toHaveLength(5);
    expect(items[0]).toBe("six");
  });
});
