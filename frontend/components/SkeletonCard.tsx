"use client";

/**
 * Skeleton placeholder that mirrors EventCard layout (dark theme).
 */
export default function SkeletonCard() {
  return (
    <div className="h-full flex flex-col rounded-card p-3 sm:p-4 bg-surface-card border border-surface-border animate-pulse">
      {/* Header */}
      <div className="flex justify-between items-start mb-2.5">
        <div className="h-4 w-16 bg-surface-elevated rounded" />
        <div className="h-4 w-14 bg-surface-elevated rounded" />
      </div>

      {/* Team rows + probability bar */}
      <div className="space-y-1.5 flex-grow">
        <div className="flex items-center justify-between gap-2">
          <div className="h-4 w-28 bg-surface-elevated rounded" />
          <div className="h-6 w-12 bg-surface-elevated rounded" />
        </div>

        <div className="h-1.5 w-full rounded-full bg-surface-elevated" />

        <div className="flex items-center justify-between gap-2">
          <div className="h-4 w-24 bg-surface-elevated rounded" />
          <div className="h-6 w-12 bg-surface-elevated rounded" />
        </div>
      </div>

      {/* Footer */}
      <div className="mt-2.5 pt-2 border-t border-surface-border/50">
        <div className="h-3 w-32 bg-surface-elevated rounded" />
      </div>
    </div>
  );
}

/**
 * Grid of skeleton cards for loading state.
 */
export function SkeletonGrid({ count = 6 }: { count?: number }) {
  return (
    <div className="space-y-6">
      <div className="animate-pulse">
        <div className="flex items-center gap-2 mb-3">
          <div className="h-4 w-4 bg-surface-elevated rounded" />
          <div className="h-4 w-24 bg-surface-elevated rounded" />
          <div className="h-4 w-8 bg-surface-elevated rounded" />
        </div>
        <div
          className="grid gap-3 items-stretch"
          style={{ gridTemplateColumns: "repeat(auto-fill, minmax(min(100%, 320px), 1fr))" }}
        >
          {Array.from({ length: count }).map((_, i) => (
            <SkeletonCard key={i} />
          ))}
        </div>
      </div>
    </div>
  );
}
