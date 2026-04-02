export default function Loading() {
  return (
    <div className="min-h-screen bg-background">
      <div className="max-w-7xl mx-auto px-4 py-6">
        {/* Header skeleton */}
        <div className="flex items-center gap-3 mb-4">
          <div className="w-10 h-10 rounded-full bg-surface-card animate-pulse" />
          <div>
            <div className="h-6 w-48 bg-surface-card rounded animate-pulse" />
            <div className="h-4 w-16 bg-surface-card rounded animate-pulse mt-1" />
          </div>
        </div>

        {/* League tabs skeleton */}
        <div className="flex gap-2 mb-6 overflow-x-auto">
          {Array.from({ length: 10 }).map((_, i) => (
            <div key={i} className="h-8 w-16 rounded-full bg-surface-card animate-pulse shrink-0" />
          ))}
        </div>

        {/* Chart skeleton */}
        <div className="bg-surface-card rounded-xl border border-white/10 p-4 mb-5">
          <div className="h-4 w-48 bg-white/5 rounded animate-pulse mb-3" />
          <div className="h-[180px] bg-white/5 rounded animate-pulse" />
        </div>

        {/* Movers skeleton */}
        <div className="flex gap-2 mb-6 overflow-x-auto">
          {Array.from({ length: 6 }).map((_, i) => (
            <div key={i} className="h-8 w-24 rounded-full bg-surface-card animate-pulse shrink-0" />
          ))}
        </div>

        {/* Grid table skeleton */}
        <div className="bg-surface-card rounded-xl border border-white/10 p-4">
          <div className="h-5 w-32 bg-white/5 rounded animate-pulse mb-4" />
          {/* Header row */}
          <div className="flex gap-4 mb-3 pb-3 border-b border-white/10">
            <div className="h-4 w-8 bg-white/5 rounded animate-pulse" />
            <div className="h-4 w-32 bg-white/5 rounded animate-pulse" />
            {Array.from({ length: 4 }).map((_, i) => (
              <div key={i} className="h-4 w-20 bg-white/5 rounded animate-pulse" />
            ))}
          </div>
          {/* Team rows */}
          {Array.from({ length: 12 }).map((_, i) => (
            <div key={i} className="flex items-center gap-4 py-2.5">
              <div className="h-4 w-4 bg-white/5 rounded animate-pulse" />
              <div className="flex items-center gap-2 w-32">
                <div className="w-6 h-6 rounded-full bg-white/5 animate-pulse" />
                <div className="h-4 w-20 bg-white/5 rounded animate-pulse" />
              </div>
              {Array.from({ length: 4 }).map((_, j) => (
                <div key={j} className="h-4 w-16 bg-white/5 rounded animate-pulse" />
              ))}
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}
