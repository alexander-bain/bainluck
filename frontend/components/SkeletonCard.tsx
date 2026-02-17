"use client";

/**
 * Skeleton placeholder that mirrors EventCard layout.
 * Renders instantly while API data loads, reducing perceived latency.
 */
export default function SkeletonCard() {
  return (
    <div className="h-full flex flex-col rounded-card shadow-card p-4 bg-white border border-mist animate-pulse">
      {/* Header */}
      <div className="flex justify-between items-start mb-3">
        <div className="h-5 w-20 bg-mist rounded-full" />
        <div className="h-5 w-14 bg-mist rounded-full" />
      </div>

      {/* Team rows + probability bar */}
      <div className="space-y-2 flex-grow">
        {/* Home team */}
        <div className="flex items-center justify-between gap-2">
          <div className="h-5 w-32 bg-mist rounded" />
          <div className="h-6 w-12 bg-mist rounded" />
        </div>

        {/* Probability bar */}
        <div className="h-1.5 w-full rounded-full bg-mist" />

        {/* Away team */}
        <div className="flex items-center justify-between gap-2">
          <div className="h-5 w-28 bg-mist rounded" />
          <div className="h-6 w-12 bg-mist rounded" />
        </div>
      </div>

      {/* Footer */}
      <div className="mt-3 pt-3 border-t border-mist/50">
        <div className="h-4 w-36 bg-mist rounded" />
      </div>
    </div>
  );
}

/**
 * Grid of skeleton cards for loading state.
 */
export function SkeletonGrid({ count = 6 }: { count?: number }) {
  return (
    <div className="space-y-8">
      {/* Fake section header */}
      <div className="animate-pulse">
        <div className="flex items-center gap-2 mb-4">
          <div className="h-6 w-6 bg-mist rounded" />
          <div className="h-6 w-28 bg-mist rounded" />
          <div className="h-5 w-10 bg-mist rounded" />
        </div>
        <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3 items-stretch">
          {Array.from({ length: count }).map((_, i) => (
            <SkeletonCard key={i} />
          ))}
        </div>
      </div>
    </div>
  );
}
