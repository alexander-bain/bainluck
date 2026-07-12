"use client";

/**
 * Skeleton loading state for the competition hub (/hub/[competition]).
 * Matches the layout: hero, upcoming-cards rail, and market-card sections.
 */

export default function HubSkeleton() {
  return (
    <div className="-mx-3 md:-mx-6 -mt-4 bg-surface-deep min-h-screen">
      {/* Hero */}
      <div className="px-4 md:px-6 pt-10 pb-8" style={{ maxWidth: 1200, margin: "0 auto" }}>
        <div className="h-3 w-32 bg-gray-200 rounded animate-pulse mb-4" />
        <div className="h-12 md:h-14 w-[420px] max-w-full bg-gray-200 rounded animate-pulse mb-3" />
        <div className="h-4 w-96 max-w-full bg-gray-200 rounded animate-pulse" />
      </div>

      <div className="px-4 md:px-6 pb-20" style={{ maxWidth: 1200, margin: "0 auto" }}>
        {/* Upcoming rail */}
        <div className="mb-12">
          <div className="h-3 w-32 bg-gray-200 rounded animate-pulse mb-3" />
          <div className="flex gap-3 overflow-hidden">
            {Array.from({ length: 4 }).map((_, i) => (
              <div key={i} className="flex-shrink-0 w-64 bg-white rounded-2xl border border-surface-border p-4">
                <div className="h-3 w-16 bg-gray-200 rounded animate-pulse mb-3" />
                <div className="h-4 w-48 bg-gray-200 rounded animate-pulse mb-1.5" />
                <div className="h-4 w-32 bg-gray-200 rounded animate-pulse mb-4" />
                <div className="flex justify-between">
                  <div className="h-3 w-16 bg-gray-200 rounded animate-pulse" />
                  <div className="h-3 w-12 bg-gray-200 rounded animate-pulse" />
                </div>
              </div>
            ))}
          </div>
        </div>

        {/* Market sections */}
        {Array.from({ length: 2 }).map((_, s) => (
          <div key={s} className="mb-12">
            <div className="h-3 w-28 bg-gray-200 rounded animate-pulse mb-3" />
            <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
              {Array.from({ length: 3 }).map((_, i) => (
                <div key={i} className="bg-white rounded-2xl border border-surface-border p-4">
                  <div className="h-4 w-40 bg-gray-200 rounded animate-pulse mb-3" />
                  {Array.from({ length: 3 }).map((_, j) => (
                    <div key={j} className="flex items-center gap-2 py-1.5">
                      <div className="flex-1 h-3 bg-gray-200 rounded animate-pulse" />
                      <div className="w-20 h-1.5 bg-gray-200 rounded-full animate-pulse" />
                      <div className="w-10 h-3 bg-gray-200 rounded animate-pulse" />
                    </div>
                  ))}
                </div>
              ))}
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}
