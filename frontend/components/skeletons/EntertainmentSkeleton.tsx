"use client";

/**
 * Skeleton loading state for the Entertainment page.
 * Matches the actual layout: page header, filter chips, hero grid,
 * music section, and movies/TV section.
 */

export default function EntertainmentSkeleton() {
  return (
    <div className="-mx-3 md:-mx-6 -mt-4">
      {/* Page header */}
      <div style={{ maxWidth: 1200, margin: "0 auto", padding: "40px 20px 24px" }}>
        <div className="h-3 w-40 bg-gray-200 rounded animate-pulse mb-3" />
        <div className="h-9 w-[480px] max-w-full bg-gray-200 rounded animate-pulse mb-3" />
        <div className="h-4 w-96 max-w-full bg-gray-200 rounded animate-pulse mb-4" />
        <div className="flex gap-3">
          <div className="h-3 w-28 bg-gray-200 rounded animate-pulse" />
          <div className="h-3 w-24 bg-gray-200 rounded animate-pulse" />
        </div>
      </div>

      {/* Filter chips */}
      <div className="flex gap-2 px-5 py-3 overflow-x-auto" style={{ maxWidth: 1200, margin: "0 auto" }}>
        {["All", "Music", "Movies", "TV", "Internet", "Live"].map((label) => (
          <div key={label} className="h-9 bg-gray-200 rounded-full animate-pulse shrink-0" style={{ width: 50 + label.length * 7 }} />
        ))}
      </div>

      {/* Content */}
      <div style={{ maxWidth: 1200, margin: "0 auto", padding: "20px 20px" }}>
        {/* Trending hero grid */}
        <div className="grid md:grid-cols-[1.2fr_1fr_1fr] gap-3 mb-10">
          {/* Lead card */}
          <div className="bg-white rounded-2xl border border-surface-border p-5 md:row-span-2">
            <div className="flex gap-3 mb-4">
              <div className="w-[72px] h-[72px] bg-gray-200 rounded-xl animate-pulse shrink-0" />
              <div className="flex-1">
                <div className="h-3 w-16 bg-gray-200 rounded-full animate-pulse mb-2" />
                <div className="h-5 w-full bg-gray-200 rounded animate-pulse mb-1" />
                <div className="h-5 w-3/4 bg-gray-200 rounded animate-pulse" />
              </div>
            </div>
            <div className="h-7 w-20 bg-gray-200 rounded animate-pulse mb-2" />
            <div className="h-2 w-full bg-gray-200 rounded-full animate-pulse mb-4" />
            <div className="h-3 w-32 bg-gray-200 rounded animate-pulse" />
          </div>
          {/* Side cards */}
          {Array.from({ length: 4 }).map((_, i) => (
            <div key={i} className="bg-white rounded-2xl border border-surface-border p-4">
              <div className="flex gap-2 mb-3">
                <div className="w-11 h-11 bg-gray-200 rounded-lg animate-pulse shrink-0" />
                <div className="flex-1">
                  <div className="h-3 w-14 bg-gray-200 rounded-full animate-pulse mb-2" />
                  <div className="h-4 w-full bg-gray-200 rounded animate-pulse" />
                </div>
              </div>
              <div className="flex justify-between items-baseline">
                <div className="h-6 w-14 bg-gray-200 rounded animate-pulse" />
                <div className="h-3 w-16 bg-gray-200 rounded animate-pulse" />
              </div>
            </div>
          ))}
        </div>

        {/* Music section skeleton */}
        <div className="mb-10">
          <div className="flex items-start justify-between mb-4">
            <div>
              <div className="h-3 w-16 bg-gray-200 rounded animate-pulse mb-2" />
              <div className="h-6 w-64 bg-gray-200 rounded animate-pulse" />
            </div>
            <div className="flex gap-1">
              {["Spotify", "Billboard", "Albums", "Streaming"].map((t) => (
                <div key={t} className="h-8 w-20 bg-gray-200 rounded-full animate-pulse" />
              ))}
            </div>
          </div>
          <div className="bg-white rounded-2xl border border-surface-border p-5">
            {Array.from({ length: 5 }).map((_, i) => (
              <div key={i} className="flex items-center gap-3 py-3 border-t border-surface-border first:border-0">
                <div className="h-5 w-5 bg-gray-200 rounded animate-pulse" />
                <div className="w-9 h-9 bg-gray-200 rounded-lg animate-pulse" />
                <div className="flex-1">
                  <div className="h-4 bg-gray-200 rounded animate-pulse mb-2" style={{ width: `${120 + i * 15}px` }} />
                  <div className="h-1.5 bg-gray-200 rounded-full animate-pulse" style={{ width: `${200 - i * 30}px` }} />
                </div>
                <div className="h-5 w-12 bg-gray-200 rounded animate-pulse" />
              </div>
            ))}
          </div>
        </div>

        {/* Movies section skeleton */}
        <div className="mb-10">
          <div className="flex items-start justify-between mb-4">
            <div>
              <div className="h-3 w-20 bg-gray-200 rounded animate-pulse mb-2" />
              <div className="h-6 w-80 bg-gray-200 rounded animate-pulse" />
            </div>
          </div>
          <div className="grid md:grid-cols-3 gap-3">
            {Array.from({ length: 3 }).map((_, i) => (
              <div key={i} className="bg-white rounded-2xl border border-surface-border p-4">
                <div className="flex gap-3 mb-3">
                  <div className="w-14 h-14 bg-gray-200 rounded-xl animate-pulse shrink-0" />
                  <div className="flex-1">
                    <div className="h-4 w-full bg-gray-200 rounded animate-pulse mb-1" />
                    <div className="h-3 w-3/4 bg-gray-200 rounded animate-pulse" />
                  </div>
                </div>
                <div className="h-16 w-full bg-gray-200 rounded animate-pulse mb-3" />
                <div className="h-3 w-20 bg-gray-200 rounded-full animate-pulse" />
              </div>
            ))}
          </div>
        </div>
      </div>
    </div>
  );
}
