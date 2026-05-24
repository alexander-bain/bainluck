"use client";

/**
 * Skeleton loading state for the Politics page.
 * Matches the actual layout: page header, sub-nav chips, presidential hero,
 * congressional section, and market card grid.
 */

export default function PoliticsSkeleton() {
  return (
    <div className="-mx-3 md:-mx-6 -mt-4">
      {/* Page header */}
      <div style={{ maxWidth: 1200, margin: "0 auto", padding: "32px 20px 20px" }}>
        <div className="flex items-start justify-between flex-wrap gap-4">
          <div>
            <div className="h-10 w-40 bg-gray-200 rounded animate-pulse mb-3" />
            <div className="h-4 w-80 bg-gray-200 rounded animate-pulse" />
          </div>
          <div className="flex gap-4">
            <div className="h-4 w-20 bg-gray-200 rounded animate-pulse" />
            <div className="h-4 w-16 bg-gray-200 rounded animate-pulse" />
            <div className="h-4 w-24 bg-gray-200 rounded animate-pulse" />
          </div>
        </div>
      </div>

      {/* Sub-nav chips */}
      <div className="border-y border-surface-border bg-white sticky top-14 overflow-x-auto">
        <div className="flex gap-2 px-5 py-3" style={{ maxWidth: 1200, margin: "0 auto" }}>
          {["All", "Presidential", "Congressional", "Gubernatorial", "Policy", "SCOTUS", "Intl"].map((label) => (
            <div key={label} className="h-8 bg-gray-200 rounded-full animate-pulse shrink-0" style={{ width: 60 + label.length * 6 }} />
          ))}
        </div>
      </div>

      {/* Content */}
      <div style={{ maxWidth: 1200, margin: "0 auto", padding: "24px 20px" }}>
        {/* Presidential hero skeleton */}
        <div className="bg-white rounded-2xl border border-surface-border p-5 mb-8">
          <div className="flex items-start justify-between mb-5">
            <div>
              <div className="h-6 w-96 bg-gray-200 rounded animate-pulse mb-2" />
              <div className="h-3 w-52 bg-gray-200 rounded animate-pulse" />
            </div>
            <div className="flex gap-2">
              <div className="h-8 w-20 bg-gray-200 rounded-full animate-pulse" />
              <div className="h-8 w-20 bg-gray-200 rounded-full animate-pulse" />
            </div>
          </div>
          {/* Candidate rows */}
          {Array.from({ length: 6 }).map((_, i) => (
            <div key={i} className="flex items-center gap-3 py-3 border-t border-surface-border first:border-0">
              <div className="h-5 w-5 bg-gray-200 rounded animate-pulse" />
              <div className="h-5 w-8 bg-gray-200 rounded animate-pulse" />
              <div className="h-4 bg-gray-200 rounded animate-pulse" style={{ width: `${100 + i * 10}px` }} />
              <div className="flex-1 h-4 bg-gray-200 rounded-full animate-pulse" style={{ maxWidth: `${300 - i * 40}px` }} />
              <div className="h-5 w-12 bg-gray-200 rounded animate-pulse" />
            </div>
          ))}
        </div>

        {/* Chamber control cards skeleton */}
        <div className="grid md:grid-cols-2 gap-4 mb-8">
          {[0, 1].map((i) => (
            <div key={i} className="bg-white rounded-2xl border border-surface-border p-5">
              <div className="h-3 w-28 bg-gray-200 rounded animate-pulse mb-3" />
              <div className="flex items-baseline gap-4 mb-3">
                <div className="h-8 w-16 bg-gray-200 rounded animate-pulse" />
                <div className="h-3 w-6 bg-gray-200 rounded animate-pulse" />
                <div className="h-8 w-16 bg-gray-200 rounded animate-pulse" />
              </div>
              <div className="h-1.5 w-full bg-gray-200 rounded-full animate-pulse" />
            </div>
          ))}
        </div>

        {/* Market cards grid skeleton */}
        <div className="grid md:grid-cols-2 lg:grid-cols-3 gap-4">
          {Array.from({ length: 6 }).map((_, i) => (
            <div key={i} className="bg-white rounded-2xl border border-surface-border p-4" style={{ borderTop: "2px solid #E5E7EB" }}>
              <div className="h-3 w-16 bg-gray-200 rounded-full animate-pulse mb-3" />
              <div className="h-4 w-full bg-gray-200 rounded animate-pulse mb-1" />
              <div className="h-4 w-3/4 bg-gray-200 rounded animate-pulse mb-4" />
              <div className="flex items-baseline justify-between mb-3">
                <div className="h-7 w-16 bg-gray-200 rounded animate-pulse" />
                <div className="h-4 w-20 bg-gray-200 rounded animate-pulse" />
              </div>
              <div className="h-1.5 w-full bg-gray-200 rounded-full animate-pulse" />
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}
