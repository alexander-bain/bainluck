"use client";

/**
 * Skeleton loading state for the Economics page.
 * Matches the actual layout: hero header, Fed heatmap section,
 * inflation section, and market sections.
 */

export default function EconomicsSkeleton() {
  return (
    <div className="-mx-3 md:-mx-6 -mt-4 bg-surface-deep">
      {/* Hero */}
      <div className="px-4 md:px-6 pt-10 pb-8" style={{ maxWidth: 1440, margin: "0 auto" }}>
        <div className="flex items-center gap-3 mb-4">
          <div className="h-6 w-44 bg-gray-200 rounded-full animate-pulse" />
          <div className="h-3 w-64 bg-gray-200 rounded animate-pulse" />
        </div>
        <div className="h-12 md:h-14 w-[520px] max-w-full bg-gray-200 rounded animate-pulse mb-3" />
        <div className="h-4 w-96 max-w-full bg-gray-200 rounded animate-pulse" />
      </div>

      <div className="px-4 md:px-6 pb-16" style={{ maxWidth: 1440, margin: "0 auto" }}>
        {/* Fed Rates section */}
        <div className="mb-12">
          <div className="mb-4">
            <div className="h-3 w-28 bg-gray-200 rounded animate-pulse mb-2" />
            <div className="h-6 w-96 bg-gray-200 rounded animate-pulse mb-1" />
            <div className="h-3 w-56 bg-gray-200 rounded animate-pulse" />
          </div>
          <div className="grid md:grid-cols-[1.6fr_1fr] gap-3.5">
            {/* Heatmap card */}
            <div className="bg-white rounded-2xl border border-surface-border p-5">
              <div className="flex justify-between items-start mb-4">
                <div>
                  <div className="h-5 w-36 bg-gray-200 rounded animate-pulse mb-2" />
                  <div className="h-3 w-64 bg-gray-200 rounded animate-pulse" />
                </div>
                <div className="h-5 w-14 bg-gray-200 rounded-full animate-pulse" />
              </div>
              {/* Heatmap grid */}
              <div className="grid gap-0.5" style={{ gridTemplateColumns: "70px repeat(6, 1fr)" }}>
                <div />
                {Array.from({ length: 6 }).map((_, i) => (
                  <div key={i} className="text-center pb-2">
                    <div className="h-3 w-8 mx-auto bg-gray-200 rounded animate-pulse mb-1" />
                    <div className="h-2 w-12 mx-auto bg-gray-200 rounded animate-pulse" />
                  </div>
                ))}
                {Array.from({ length: 5 }).map((_, row) => (
                  <div key={row} className="contents">
                    <div className="h-9 flex items-center justify-end pr-2">
                      <div className="h-3 w-12 bg-gray-200 rounded animate-pulse" />
                    </div>
                    {Array.from({ length: 6 }).map((_, col) => (
                      <div key={col} className="h-9 bg-gray-100 rounded animate-pulse border border-surface-border" />
                    ))}
                  </div>
                ))}
              </div>
            </div>
            {/* Side cards */}
            <div className="flex flex-col gap-3.5">
              <div className="bg-white rounded-2xl border border-surface-border p-5">
                <div className="h-3 w-40 bg-gray-200 rounded animate-pulse mb-3" />
                {Array.from({ length: 4 }).map((_, i) => (
                  <div key={i} className="flex items-center gap-2 mb-3">
                    <div className="h-3 w-12 bg-gray-200 rounded animate-pulse" />
                    <div className="flex-1 h-2 bg-gray-200 rounded-full animate-pulse" />
                    <div className="h-3 w-10 bg-gray-200 rounded animate-pulse" />
                  </div>
                ))}
              </div>
              <div className="bg-white rounded-2xl border border-surface-border p-5">
                <div className="h-3 w-24 bg-gray-200 rounded animate-pulse mb-3" />
                {Array.from({ length: 3 }).map((_, i) => (
                  <div key={i} className="flex items-center justify-between py-2.5 border-t border-surface-border first:border-0">
                    <div className="h-3 bg-gray-200 rounded animate-pulse" style={{ width: `${180 - i * 20}px` }} />
                    <div className="h-4 w-12 bg-gray-200 rounded animate-pulse" />
                  </div>
                ))}
              </div>
            </div>
          </div>
        </div>

        {/* Inflation section */}
        <div className="mb-12">
          <div className="mb-4">
            <div className="h-3 w-40 bg-gray-200 rounded animate-pulse mb-2" />
            <div className="h-6 w-72 bg-gray-200 rounded animate-pulse" />
          </div>
          <div className="grid md:grid-cols-[1.6fr_1fr] gap-3.5">
            <div className="bg-white rounded-2xl border border-surface-border p-5">
              {Array.from({ length: 2 }).map((_, i) => (
                <div key={i} className="py-3 border-b border-surface-border last:border-0">
                  <div className="h-3 w-20 bg-gray-200 rounded animate-pulse mb-3" />
                  <div className="flex gap-1 items-end" style={{ height: 56 }}>
                    {Array.from({ length: 6 }).map((_, j) => (
                      <div key={j} className="flex-1 bg-gray-200 rounded animate-pulse" style={{ height: `${20 + Math.random() * 60}%` }} />
                    ))}
                  </div>
                </div>
              ))}
            </div>
            <div className="bg-white rounded-2xl border border-surface-border p-5">
              <div className="h-3 w-28 bg-gray-200 rounded animate-pulse mb-3" />
              {Array.from({ length: 4 }).map((_, i) => (
                <div key={i} className="flex items-center justify-between py-2.5 border-t border-surface-border first:border-0">
                  <div className="h-3 bg-gray-200 rounded animate-pulse" style={{ width: `${160 - i * 15}px` }} />
                  <div className="h-4 w-12 bg-gray-200 rounded animate-pulse" />
                </div>
              ))}
            </div>
          </div>
        </div>

        {/* GDP & Recession section */}
        <div className="mb-12">
          <div className="mb-4">
            <div className="h-3 w-28 bg-gray-200 rounded animate-pulse mb-2" />
            <div className="h-6 w-56 bg-gray-200 rounded animate-pulse" />
          </div>
          <div className="grid md:grid-cols-[1fr_1.4fr] gap-3.5">
            <div className="bg-white rounded-2xl border border-surface-border p-5">
              <div className="h-3 w-44 bg-gray-200 rounded animate-pulse mb-3" />
              <div className="h-16 w-24 bg-gray-200 rounded animate-pulse mb-4" />
              {Array.from({ length: 2 }).map((_, i) => (
                <div key={i} className="flex items-center justify-between py-2.5 border-t border-surface-border">
                  <div className="h-3 bg-gray-200 rounded animate-pulse" style={{ width: `${140 - i * 20}px` }} />
                  <div className="h-4 w-12 bg-gray-200 rounded animate-pulse" />
                </div>
              ))}
            </div>
            <div className="bg-white rounded-2xl border border-surface-border p-5">
              <div className="h-3 w-56 bg-gray-200 rounded animate-pulse mb-3" />
              <div className="grid grid-cols-2 gap-2.5">
                {Array.from({ length: 4 }).map((_, i) => (
                  <div key={i} className="border border-surface-border rounded-xl p-3">
                    <div className="h-3 w-16 bg-gray-200 rounded animate-pulse mb-2" />
                    <div className="flex gap-1 items-end" style={{ height: 40 }}>
                      {Array.from({ length: 4 }).map((_, j) => (
                        <div key={j} className="flex-1 bg-gray-200 rounded animate-pulse" style={{ height: `${20 + Math.random() * 60}%` }} />
                      ))}
                    </div>
                  </div>
                ))}
              </div>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
