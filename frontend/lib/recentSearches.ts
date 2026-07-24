// Persisted "recent searches" for the search surfaces (SearchBar +
// MobileSearchOverlay). Single shared source so the two components can't drift
// (they previously kept independent copies with subtly different limits).
//
// L2-178 — versioned parse with graceful reset. A stored value from an older or
// foreign shape (an array of objects, a bare string, null, a future version)
// must NEVER crash the search UI or render non-string entries. We wrap writes in
// a `{ v: 1, items: string[] }` envelope, validate on read, and silently drop
// anything unexpected — degrading to a clean empty list instead of throwing.

const RECENT_SEARCHES_KEY = "bainluck_recent_searches";
const MAX_RECENT = 5;
const CURRENT_VERSION = 1;

interface RecentSearchesEnvelope {
  v: number;
  items: string[];
}

/** Keep only well-formed, non-empty string entries. */
function coerceStringList(value: unknown): string[] {
  if (!Array.isArray(value)) return [];
  return value.filter(
    (s): s is string => typeof s === "string" && s.trim().length > 0,
  );
}

export function getRecentSearches(): string[] {
  if (typeof window === "undefined") return [];
  try {
    const raw = localStorage.getItem(RECENT_SEARCHES_KEY);
    if (!raw) return [];
    const parsed: unknown = JSON.parse(raw);
    // Current shape: the versioned envelope { v: 1, items: string[] }.
    if (parsed && typeof parsed === "object" && !Array.isArray(parsed)) {
      const env = parsed as Partial<RecentSearchesEnvelope>;
      if (env.v === CURRENT_VERSION) {
        return coerceStringList(env.items).slice(0, MAX_RECENT);
      }
      // Unknown / newer version we don't understand → graceful reset.
      return [];
    }
    // Legacy shape: a bare string[] (pre-L2-178). Read it, and it migrates to the
    // envelope on the next saveRecentSearch.
    return coerceStringList(parsed).slice(0, MAX_RECENT);
  } catch {
    return [];
  }
}

export function saveRecentSearch(q: string): void {
  if (typeof window === "undefined") return;
  const cleaned = q.trim();
  if (!cleaned || cleaned.length < 2) return;
  const recent = getRecentSearches().filter((s) => s !== cleaned);
  recent.unshift(cleaned);
  try {
    const payload: RecentSearchesEnvelope = {
      v: CURRENT_VERSION,
      items: recent.slice(0, MAX_RECENT),
    };
    localStorage.setItem(RECENT_SEARCHES_KEY, JSON.stringify(payload));
  } catch {
    // localStorage can throw (private mode / quota) — recents are best-effort.
  }
}
