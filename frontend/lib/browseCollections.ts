/**
 * #10476 — web Browse lists the published NFL-week / MLB-postseason hubs.
 *
 * Browse used to open a categories-only menu, so a reader could reach the
 * published NFL week only by guessing its URL. The menu now asks
 * the existing discovery read (`GET /api/containers/discover`, the same one
 * native Browse uses) when it opens, and links each hub it may show.
 *
 * Nothing here decides eligibility on its own. Every served card goes through
 * Discover's `admitCollection` — published, the edition's canonical slug, a
 * non-empty count, the canonical `/collections/{slug}` destination — and a card
 * it refuses is dropped alone; its siblings still render. No week, slug or
 * season is written down here: whatever the read serves today is what shows.
 *
 * The loader is a plain object so the menu's lifecycle can be tested without a
 * DOM: `open()` starts one bounded request, `close()` aborts it, and an answer
 * that arrives after a close (or after a newer request) is ignored.
 */

import { API_URL } from "@/lib/api";
import { admitCollection, type DiscoverCollectionEntry } from "@/lib/discover/collectionFeed";
import type { FeedItem } from "@/lib/types";

/** The read's own cap; more than this is never shown. */
export const BROWSE_COLLECTIONS_LIMIT = 20;
/** A menu that cannot answer in this long gives up and shows categories only. */
export const BROWSE_COLLECTIONS_TIMEOUT_MS = 8_000;
/** How long one good answer is reused across opens before asking again. */
export const BROWSE_COLLECTIONS_FRESH_MS = 5 * 60_000;

export type BrowseCollectionsState =
  | { status: "idle"; entries: DiscoverCollectionEntry[] }
  | { status: "loading"; entries: DiscoverCollectionEntry[] }
  | { status: "ready"; entries: DiscoverCollectionEntry[] }
  | { status: "failed"; entries: DiscoverCollectionEntry[] };

const IDLE: BrowseCollectionsState = { status: "idle", entries: [] };
const LOADING: BrowseCollectionsState = { status: "loading", entries: [] };
const FAILED: BrowseCollectionsState = { status: "failed", entries: [] };

export function browseCollectionsUrl(base: string = API_URL): string {
  return `${base}/api/containers/discover?limit=${BROWSE_COLLECTIONS_LIMIT}`;
}

/**
 * The hubs a reader may open, in served order, or null when the body is not
 * the read's shape at all (that is a failure, not "nothing published").
 */
export function admitBrowseCollections(body: unknown): DiscoverCollectionEntry[] | null {
  if (!body || typeof body !== "object" || Array.isArray(body)) return null;
  const cards = (body as { collections?: unknown }).collections;
  if (!Array.isArray(cards)) return null;
  const entries: DiscoverCollectionEntry[] = [];
  const seen = new Set<string>();
  for (const card of cards) {
    let entry: DiscoverCollectionEntry | null = null;
    try {
      entry = admitCollection({ type: "collection", data: card } as FeedItem);
    } catch {
      entry = null;
    }
    if (!entry || seen.has(entry.slug)) continue;
    seen.add(entry.slug);
    entries.push(entry);
    if (entries.length >= BROWSE_COLLECTIONS_LIMIT) break;
  }
  return entries;
}

export interface BrowseCollectionsLoader {
  open(): void;
  close(): void;
  getState(): BrowseCollectionsState;
  subscribe(listener: () => void): () => void;
}

export interface BrowseCollectionsLoaderOptions {
  fetchImpl?: typeof fetch;
  url?: string;
  now?: () => number;
  timeoutMs?: number;
  freshMs?: number;
}

export function createBrowseCollectionsLoader(
  options: BrowseCollectionsLoaderOptions = {},
): BrowseCollectionsLoader {
  const fetchImpl = options.fetchImpl ?? ((...args: Parameters<typeof fetch>) => fetch(...args));
  const url = options.url ?? browseCollectionsUrl();
  const now = options.now ?? Date.now;
  const timeoutMs = options.timeoutMs ?? BROWSE_COLLECTIONS_TIMEOUT_MS;
  const freshMs = options.freshMs ?? BROWSE_COLLECTIONS_FRESH_MS;

  let state: BrowseCollectionsState = IDLE;
  let controller: AbortController | null = null;
  let timer: ReturnType<typeof setTimeout> | null = null;
  let generation = 0;
  let loadedAt = 0;
  const listeners = new Set<() => void>();

  function stopTimer() {
    if (timer !== null) clearTimeout(timer);
    timer = null;
  }

  function set(next: BrowseCollectionsState) {
    state = next;
    listeners.forEach((listener) => listener());
  }

  function open() {
    if (controller) return;
    if (state.status === "ready" && now() - loadedAt < freshMs) return;
    const mine = ++generation;
    const ac = new AbortController();
    controller = ac;
    stopTimer();
    timer = setTimeout(() => ac.abort(), timeoutMs);
    // A refresh does not keep showing the old answer: a hub withdrawn since
    // then must not stay a link while the new answer is on its way.
    set(LOADING);
    Promise.resolve()
      .then(() => fetchImpl(url, { signal: ac.signal, headers: { Accept: "application/json" } }))
      .then((response) => {
        if (!response.ok) return null;
        return response.json().then(admitBrowseCollections);
      })
      .then(
        (entries) => {
          if (mine !== generation) return;
          if (entries === null) {
            set(FAILED);
            return;
          }
          loadedAt = now();
          set({ status: "ready", entries });
        },
        () => {
          if (mine !== generation) return;
          set(FAILED);
        },
      )
      .finally(() => {
        if (controller === ac) {
          stopTimer();
          controller = null;
        }
      });
  }

  function close() {
    if (!controller) return;
    generation++;
    stopTimer();
    controller.abort();
    controller = null;
    set(IDLE);
  }

  return {
    open,
    close,
    getState: () => state,
    subscribe(listener) {
      listeners.add(listener);
      return () => {
        listeners.delete(listener);
      };
    },
  };
}
