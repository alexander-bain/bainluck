"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { fetchSportHierarchy } from "@/lib/api";
import type { SportHierarchy } from "@/lib/types";
import { usePageTracking, useScrollDepth, useEngagementTime } from "@/hooks";
import LoadingState from "@/components/LoadingState";
import ErrorState from "@/components/ErrorState";
// #7015 \u2014 the icon, subtitle and tint for every sport the authority serves.
// It lives in lib/ so a guard test can reach it; this page cannot be rendered
// by one (client component, useEffect load).
import { resolveSportCard } from "@/lib/sportDirectory";

export default function SportsIndexPage() {
  const [sports, setSports] = useState<SportHierarchy[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(false);

  usePageTracking({ pageType: "sport_hub", pageTitle: "All Sports - BainLuck" });
  useScrollDepth({ pageType: "sport_hub" });
  useEngagementTime({ pageType: "sport_hub" });

  const loadData = () => {
    setLoading(true);
    setError(false);
    fetchSportHierarchy()
      .then((data) => setSports(data.sports))
      .catch(() => setError(true))
      .finally(() => setLoading(false));
  };

  useEffect(() => {
    loadData();
  }, []);

  if (loading) {
    return (
      <div className="min-h-screen flex items-center justify-center">
        <LoadingState message="Loading sports..." />
      </div>
    );
  }

  if (error) {
    return (
      <div className="min-h-screen flex items-center justify-center">
        <ErrorState message="Failed to load sports" onRetry={loadData} />
      </div>
    );
  }

  return (
    <div className="min-h-screen">
      <div className="border-b border-surface-border">
        <div className="max-w-7xl mx-auto px-4 py-8">
          <div className="flex items-center gap-2 text-sm text-text-muted mb-4">
            <Link href="/" className="hover:text-text-primary transition-colors">Home</Link>
            <span>/</span>
            <span className="text-text-primary">Sports</span>
          </div>
          <h1 className="text-3xl font-bold text-text-primary">All Sports</h1>
          <p className="text-text-secondary mt-2">
            Win probabilities and odds across {sports.length} sports
          </p>
        </div>
      </div>

      <div className="max-w-7xl mx-auto px-4 py-8">
        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4">
          {sports.map((sport: SportHierarchy) => {
            const card = resolveSportCard(sport.slug, sport.leagues.length);
            return (
              <Link
                key={sport.slug}
                href={`/sport/${sport.slug}`}
                className={`${card.tintClass} rounded-xl p-6 border border-surface-border hover:shadow-md hover:-translate-y-0.5 transition-all group`}
              >
                <div className="flex items-start gap-4">
                  <span className="text-3xl">{card.icon}</span>
                  <div className="flex-1 min-w-0">
                    <h2 className="text-text-primary font-semibold text-lg group-hover:underline">
                      {sport.name}
                    </h2>
                    <p className="text-text-muted text-sm mt-1">
                      {card.subtitle}
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
      </div>
    </div>
  );
}
