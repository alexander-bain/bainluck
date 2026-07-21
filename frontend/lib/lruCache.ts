/**
 * localStorage LRU eviction + size cap for the client-side image/metadata
 * caches (lib/images.ts, lib/tmdb.ts).
 *
 * The old `cacheSet` implementations wrapped `localStorage.setItem` in a bare
 * try/catch that silently swallowed the QuotaExceededError. Once the store
 * filled up (posters + headshots accumulate fast), EVERY subsequent write
 * failed silently — the cache effectively froze at its first-full state and
 * every page thereafter re-fetched images it had "cached". This helper instead
 * evicts the oldest entries (by timestamp) for the given prefix and retries, so
 * the cache stays a bounded, self-trimming LRU.
 */

interface TsEntry {
  ts?: number;
}

/**
 * Remove the oldest `fraction` of entries under `prefix`, ranked by their
 * stored `ts` field (entries without a parseable ts sort oldest). Returns the
 * number of keys removed.
 */
function evictOldest(prefix: string, fraction: number): number {
  const keyed: { key: string; ts: number }[] = [];
  for (let i = 0; i < localStorage.length; i++) {
    const key = localStorage.key(i);
    if (!key || !key.startsWith(prefix)) continue;
    let ts = 0;
    try {
      const raw = localStorage.getItem(key);
      if (raw) {
        const parsed = JSON.parse(raw) as TsEntry;
        ts = typeof parsed.ts === "number" ? parsed.ts : 0;
      }
    } catch {
      ts = 0; // unparseable → evict first
    }
    keyed.push({ key, ts });
  }
  if (keyed.length === 0) return 0;
  keyed.sort((a, b) => a.ts - b.ts);
  const removeCount = Math.max(1, Math.floor(keyed.length * fraction));
  for (let i = 0; i < removeCount; i++) {
    localStorage.removeItem(keyed[i].key);
  }
  return removeCount;
}

/**
 * Write `serialized` to `localStorage[storageKey]`, evicting the oldest entries
 * under `prefix` and retrying if the quota is exceeded. Best-effort: if the
 * store is unavailable or still full after eviction, it fails silently (a
 * cache miss next time is harmless).
 */
export function lruSetItem(storageKey: string, serialized: string, prefix: string): void {
  if (typeof window === "undefined") return;
  try {
    localStorage.setItem(storageKey, serialized);
  } catch {
    // Likely QuotaExceededError — drop the oldest quarter of this prefix and
    // retry once. A second failure is swallowed (store unavailable / private
    // mode / still too large for one entry).
    try {
      evictOldest(prefix, 0.25);
      localStorage.setItem(storageKey, serialized);
    } catch {
      // give up — a re-fetch on the next visit is acceptable
    }
  }
}
