"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { fetchSportHierarchy } from "@/lib/api";
import type { SportHierarchy } from "@/lib/types";
import { usePageTracking, useScrollDepth, useEngagementTime } from "@/hooks";

// Sport display metadata
const SPORT_META: Record<string, { icon: string; description: string }> = {
  golf: { icon: "\u26f3", description: "PGA Tour, DP World Tour, LPGA, LIV & more" },
  basketball: { icon: "\ud83c\udfc0", description: "NBA, WNBA, NCAA Men\u2019s & Women\u2019s" },
  football: { icon: "\ud83c\udfc8", description: "NFL, NCAA Football, CFL, UFL" },
  hockey: { icon: "\ud83c\udfd2", description: "NHL" },
  baseball: { icon: "\u26be", description: "MLB, College Baseball" },
  soccer: { icon: "\u26bd", description: "Premier League, La Liga, MLS, Champions League & more" },
  tennis: { icon: "\ud83c\udfbe", description: "ATP Tour, WTA Tour" },
  mma: { icon: "\ud83e\udd4a", description: "UFC" },
};

const SPORT_COLORS: Record<string, string> = {
  golf: "bg-emerald-50 hover:bg-emerald-100",
  basketball: "bg-orange-50 hover:bg-orange-100",
  football: "bg-green-50 hover:bg-green-100",
  hockey: "bg-sky-50 hover:bg-sky-100",
  baseball: "bg-red-50 hover:bg-red-100",
  soccer: "bg-purple-50 hover:bg-purple-100",
  tennis: "bg-lime-50 hover:bg-lime-100",
  mma: "bg-rose-50 hover:bg-rose-100",
};

export default function SportsIndexPage() {
  const [sports, setSports] = useState<SportHierarchy[]>([]);
  const [loading, setLoading] = useState(true);

  usePageTracking({ pageType: "sport_hub", pageTitle: "All Sports - BainLuck" });
  useScrollDepth({ pageType: "sport_hub" });
  useEngagementTime({ pageType: "sport_hub" });

  useEffect(() => {
    fetchSportHierarchy()
      .then((data) => setSports(data.sports))
      .catch(() => {})
      .finally(() => setLoading(false));
  }, []);

  if (loading) {
    return (
      <div className="min-h-screen flex items-center justify-center">
        <div className="animate-pulse text-text-muted">Loading...</div>
      </div>
    );
  }

  return (
    <div className="min-h-screen">
      <div className="border-b border-surface-border">
        <div className="max-w-5xl mx-auto px-4 py-8">
          <div className="flex items-center gap-2 text-sm text-text-muted mb-4">
            <Link href="/" className="hover:text-text-primary transition-colors">Home</Link>
            <span>/</span>
            <span className="text-text-primary">Sports</span>
          </div>
          <h1 className="text-3xl font-bold text-text-primary">Leagues</h1>
          <p className="text-text-secondary mt-2">
            Win probabilities and odds across {sports.length} sports
          </p>
        </div>
      </div>

      <div className="max-w-5xl mx-auto px-4 py-8">
        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4">
          {sports.map((sport: SportHierarchy) => {
            const meta = SPORT_META[sport.slug] || { icon: "\ud83c\udfc6", description: "" };
            const colorClass = SPORT_COLORS[sport.slug] || "bg-surface-elevated hover:bg-surface-card";
            return (
              <Link
                key={sport.slug}
                href={`/sport/${sport.slug}`}
                className={`${colorClass} rounded-xl p-6 border border-surface-border hover:shadow-md hover:-translate-y-0.5 transition-all group`}
              >
                <div className="flex items-start gap-4">
                  <span className="text-3xl">{meta.icon}</span>
                  <div className="flex-1 min-w-0">
                    <h2 className="text-text-primary font-semibold text-lg group-hover:underline">
                      {sport.name}
                    </h2>
                    <p className="text-text-muted text-sm mt-1">
                      {meta.description || `${sport.leagues.length} leagues`}
                    </p>
                    <div className="flex flex-wrap gap-1.5 mt-3">
                      {sport.leagues.slice(0, 4).map((league) => (
                        <span
                          key={league.slug}
                          className="text-xs text-text-secondary bg-white/60 px-2 py-0.5 rounded-full"
                        >
                          {league.name}
                        </span>
                      ))}
                      {sport.leagues.length > 4 && (
                        <span className="text-xs text-text-muted">
                          +{sport.leagues.length - 4} more
                        </span>
                      )}
                    </div>
                  </div>
                </div>
              </Link>
            );
          })}
        </div>

        {/* Beyond Sports */}
        <h2 className="text-xl font-semibold text-text-primary mt-10 mb-4">Beyond Sports</h2>
        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4">
          {[
            { href: "/categories/golf", icon: "\u26f3", label: "Golf", desc: "Tournament odds, leaderboards, progression charts", color: "bg-emerald-50 hover:bg-emerald-100" },
            { href: "/weather", icon: "\u{1F326}", label: "Weather", desc: "Temperature, rainfall, and climate prediction markets", color: "bg-sky-50 hover:bg-sky-100" },
            { href: "/economics", icon: "\ud83d\udcca", label: "Economics", desc: "Fed rates, inflation, GDP, recession probabilities", color: "bg-amber-50 hover:bg-amber-100" },
          ].map((cat) => (
            <Link
              key={cat.href}
              href={cat.href}
              className={`${cat.color} rounded-xl p-6 border border-surface-border hover:shadow-md hover:-translate-y-0.5 transition-all group`}
            >
              <div className="flex items-start gap-4">
                <span className="text-3xl">{cat.icon}</span>
                <div className="flex-1 min-w-0">
                  <h3 className="text-text-primary font-semibold text-lg group-hover:underline">{cat.label}</h3>
                  <p className="text-text-muted text-sm mt-1">{cat.desc}</p>
                </div>
              </div>
            </Link>
          ))}
        </div>

        {/* Championship Grids link */}
        <div className="mt-10 pt-6 border-t border-surface-border">
          <h2 className="text-xl font-semibold text-text-primary mb-4">Championship Grids</h2>
          <div className="flex flex-wrap gap-2">
            {[
              { slug: "nba", label: "NBA" },
              { slug: "nhl", label: "NHL" },
              { slug: "mlb", label: "MLB" },
              { slug: "ncaa-basketball", label: "NCAAB" },
            ].map((grid) => (
              <Link
                key={grid.slug}
                href={`/playoffs/${grid.slug}`}
                className="px-4 py-2 rounded-lg border border-surface-border bg-surface-card hover:bg-surface-elevated text-sm font-medium text-text-secondary hover:text-text-primary transition-colors"
              >
                {grid.label} Grid
              </Link>
            ))}
          </div>
        </div>
      </div>
    </div>
  );
}
