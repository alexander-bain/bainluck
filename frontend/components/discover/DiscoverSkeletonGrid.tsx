/**
 * DiscoverSkeletonGrid (L2-189, Item 3)
 *
 * Server-safe (no "use client", no hooks) card-placeholder grid for the
 * Discover feed. Shared by:
 *   - `app/discover/loading.tsx` — the App Router loading boundary (soft nav),
 *   - the Discover page's own `isLoading` state (cold-load SSR + hydration),
 * so the pre-hydration shell and the hydrated loading state are pixel-identical
 * and produce no layout jump. Purely presentational — emits no analytics and
 * fetches nothing, so no personalized data can enter the server HTML.
 *
 * Dimensions are fixed (h-44 media band + fixed text-line heights) to keep the
 * placeholders stable at both desktop and 375px.
 */

export default function DiscoverSkeletonGrid({ count = 9 }: { count?: number }) {
  return (
    <div
      className="columns-1 sm:columns-2 lg:columns-3 gap-4 space-y-4"
      aria-hidden="true"
      data-testid="discover-skeleton"
    >
      {Array.from({ length: count }).map((_, i) => (
        <div
          key={i}
          className="break-inside-avoid rounded-2xl bg-surface-card border border-surface-border animate-pulse mb-4"
        >
          <div className="h-44 bg-surface-elevated rounded-t-2xl" />
          <div className="p-4 space-y-3">
            <div className="h-5 bg-surface-elevated rounded w-3/4" />
            <div className="h-3 bg-surface-elevated rounded w-full" />
            <div className="h-3 bg-surface-elevated rounded w-5/6" />
          </div>
        </div>
      ))}
    </div>
  );
}
