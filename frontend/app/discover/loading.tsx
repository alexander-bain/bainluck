import DiscoverSkeletonGrid from "@/components/discover/DiscoverSkeletonGrid";

/**
 * App Router loading boundary for `/discover` (L2-189, Item 3).
 *
 * A Server Component — its HTML is emitted before client hydration and on soft
 * navigations into the route, so a stable-dimension shell (header + card
 * placeholders) appears immediately. It mirrors the Discover page's own chrome
 * so the transition to the hydrated page produces no layout jump. It runs no
 * feed request and contains no personalized data.
 *
 * Note: `/` (which re-exports the Discover client component) is covered by that
 * component's own cold-load SSR render of the same `DiscoverSkeletonGrid` — a
 * root `app/loading.tsx` is intentionally NOT added, as it would cascade this
 * skeleton onto every unrelated route.
 */
export default function DiscoverLoading() {
  return (
    <div className="min-h-screen bg-surface-deep">
      {/* Header — mirrors app/discover/page.tsx */}
      <header className="sticky top-0 z-20 bg-surface-card/80 backdrop-blur-lg border-b border-surface-border">
        <div className="max-w-7xl mx-auto px-4 py-3">
          <div className="flex items-center justify-between mb-2">
            <h1 className="text-lg font-black tracking-tight">Discover</h1>
            <span
              aria-hidden="true"
              className="h-[18px] w-[18px] rounded bg-surface-elevated animate-pulse"
            />
          </div>
        </div>
      </header>

      <main className="max-w-7xl mx-auto px-4 py-4">
        <DiscoverSkeletonGrid />
      </main>
    </div>
  );
}
