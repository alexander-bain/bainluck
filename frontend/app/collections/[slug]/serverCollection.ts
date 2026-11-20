import * as React from "react";
import { collectionPath, fetchCollection, type CollectionHub } from "@/lib/collections";

type CacheFn = <T extends (...args: never[]) => unknown>(fn: T) => T;
const reactCache = (React as unknown as { cache?: CacheFn }).cache;
const withRequestCache: CacheFn = (fn) => (typeof reactCache === "function" ? reactCache(fn) : fn);

/**
 * #13103: One server-side collection read per request, shared between
 * `layout.tsx` (`generateMetadata`) and `page.tsx` so a stranger tapping a
 * shared set link gets the full set in the initial HTML without a second
 * round-trip or "Loading collection…" flash.
 */
export const loadServerCollection = withRequestCache(
  async (slug: string): Promise<CollectionHub | null> => {
    if (!collectionPath(slug)) return null;
    try {
      return await fetchCollection(slug, AbortSignal.timeout(2500));
    } catch {
      return null;
    }
  },
);
