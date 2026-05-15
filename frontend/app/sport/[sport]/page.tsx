"use client";

import { useEffect, useState } from "react";
import { useParams } from "next/navigation";
import Link from "next/link";
import { fetchSportHierarchyDetail, fetchGolfData } from "@/lib/api";
import type { SportHierarchy, SportLeague, SportShowcaseEvent, GolfTournament } from "@/lib/types";
import TournamentCard from "@/components/TournamentCard";
import { usePageTracking, useScrollDepth, useEngagementTime } from "@/hooks";

// Showcase event type groupings for display
const SHOWCASE_TYPE_ORDER = [
  { type: "major", label: "Men\u2019s Majors" },
  { type: "womens_major", label: "Women\u2019s Majors" },
  { type: "cup", label: "Cups & Team Events" },
  { type: "grand_slam", label: "Grand Slams" },
  { type: "tournament", label: "Tournaments" },
  { type: "championship", label: "Championships" },
];

// League accent colors for visual cards
const LEAGUE_COLORS: Record<string, { bg: string; accent: string; icon: string }> = {
  // Golf
  pga: { bg: "bg-emerald-50", accent: "text-emerald-700", icon: "\u26f3" },
  dpworld: { bg: "bg-blue-50", accent: "text-blue-700", icon: "\u26f3" },
  lpga: { bg: "bg-pink-50", accent: "text-pink-700", icon: "\u26f3" },
  liv: { bg: "bg-orange-50", accent: "text-orange-700", icon: "\u26f3" },
  kft: { bg: "bg-teal-50", accent: "text-teal-700", icon: "\u26f3" },
  // Basketball
  nba: { bg: "bg-orange-50", accent: "text-orange-700", icon: "\ud83c\udfc0" },
  wnba: { bg: "bg-orange-50", accent: "text-orange-700", icon: "\ud83c\udfc0" },
  ncaab: { bg: "bg-blue-50", accent: "text-blue-700", icon: "\ud83c\udfc0" },
  wncaab: { bg: "bg-blue-50", accent: "text-blue-700", icon: "\ud83c\udfc0" },
  // Football
  nfl: { bg: "bg-green-50", accent: "text-green-800", icon: "\ud83c\udfc8" },
  ncaaf: { bg: "bg-red-50", accent: "text-red-700", icon: "\ud83c\udfc8" },
  cfl: { bg: "bg-red-50", accent: "text-red-700", icon: "\ud83c\udfc8" },
  ufl: { bg: "bg-indigo-50", accent: "text-indigo-700", icon: "\ud83c\udfc8" },
  // Hockey
  nhl: { bg: "bg-sky-50", accent: "text-sky-700", icon: "\ud83c\udfd2" },
  // Baseball
  mlb: { bg: "bg-red-50", accent: "text-red-700", icon: "\u26be" },
  ncaa: { bg: "bg-blue-50", accent: "text-blue-700", icon: "\u26be" },
  // Soccer
  epl: { bg: "bg-purple-50", accent: "text-purple-700", icon: "\u26bd" },
  mls: { bg: "bg-blue-50", accent: "text-blue-700", icon: "\u26bd" },
  laliga: { bg: "bg-orange-50", accent: "text-orange-700", icon: "\u26bd" },
  bundesliga: { bg: "bg-red-50", accent: "text-red-700", icon: "\u26bd" },
  seriea: { bg: "bg-green-50", accent: "text-green-700", icon: "\u26bd" },
  ligue1: { bg: "bg-blue-50", accent: "text-blue-700", icon: "\u26bd" },
  ucl: { bg: "bg-indigo-50", accent: "text-indigo-700", icon: "\u26bd" },
  // Tennis
  atp: { bg: "bg-green-50", accent: "text-green-700", icon: "\ud83c\udfbe" },
  wta: { bg: "bg-purple-50", accent: "text-purple-700", icon: "\ud83c\udfbe" },
  // MMA
  ufc: { bg: "bg-red-50", accent: "text-red-700", icon: "\ud83e\udd4a" },
};

const DEFAULT_LEAGUE_COLOR = { bg: "bg-surface-elevated", accent: "text-text-primary", icon: "\ud83c\udfc6" };

// Showcase event estimated dates (approximate, for display when no odds yet)
const SHOWCASE_DATES: Record<string, string> = {
  "The Masters": "April 2026",
  "PGA Championship": "May 2026",
  "U.S. Open": "June 2026",
  "The Open Championship": "July 2026",
  "Chevron Championship": "April 2026",
  "KPMG Women's PGA Championship": "June 2026",
  "U.S. Women's Open": "June 2026",
  "AIG Women's Open": "August 2026",
  "The Evian Championship": "July 2026",
  "Ryder Cup": "September 2027",
  "Presidents Cup": "September 2026",
  "Walker Cup": "September 2027",
  "Solheim Cup": "September 2027",
};

export default function SportHubPage() {
  const params = useParams();
  const sportSlug = params.sport as string;

  const [hierarchy, setHierarchy] = useState<SportHierarchy | null>(null);
  const [golfTournaments, setGolfTournaments] = useState<GolfTournament[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  // Analytics — must be before any conditional return
  usePageTracking({ pageType: "sport_hub", pageTitle: `${sportSlug} - BainLuck` });
  useScrollDepth({ pageType: "sport_hub" });
  useEngagementTime({ pageType: "sport_hub" });

  useEffect(() => {
    let cancelled = false;
    async function load() {
      setLoading(true);
      setError(null);
      try {
        const data = await fetchSportHierarchyDetail(sportSlug);
        if (!cancelled) setHierarchy(data);

        // For golf, also fetch tournament data for showcase event cards
        if (sportSlug === "golf") {
          try {
            const golfData = await fetchGolfData();
            if (!cancelled) setGolfTournaments(golfData.tournaments);
          } catch {
            // Golf data is supplementary — don't block the page
          }
        }
      } catch {
        if (!cancelled) setError(`Sport "${sportSlug}" not found`);
      } finally {
        if (!cancelled) setLoading(false);
      }
    }
    load();
    return () => { cancelled = true; };
  }, [sportSlug]);

  if (loading) {
    return (
      <div className="min-h-screen flex items-center justify-center">
        <div className="animate-pulse text-text-muted">Loading...</div>
      </div>
    );
  }

  if (error || !hierarchy) {
    return (
      <div className="min-h-screen flex items-center justify-center">
        <div className="text-center">
          <p className="text-text-muted mb-4">{error || "Sport not found"}</p>
          <Link href="/" className="text-accent-brand hover:underline">
            Back to home
          </Link>
        </div>
      </div>
    );
  }

  // Group showcase events by type
  const showcaseGroups = SHOWCASE_TYPE_ORDER
    .map((group) => ({
      ...group,
      events: hierarchy.showcase_events.filter((e: SportShowcaseEvent) => e.type === group.type),
    }))
    .filter((group) => group.events.length > 0);

  // For golf, match showcase events to tournament data for richer cards.
  // Uses strict keyword matching to avoid cross-contamination (e.g., men's odds on women's majors).
  function findGolfTournament(eventName: string): GolfTournament | undefined {
    const nameLower = eventName.toLowerCase();

    // Women's events must match women's tournaments only
    const isWomens = nameLower.includes("women") || nameLower.includes("kpmg")
      || nameLower.includes("chevron") || nameLower.includes("evian")
      || nameLower.includes("aig");

    return golfTournaments.find((t: GolfTournament) => {
      const tName = t.name.toLowerCase();
      const tIsWomens = t.is_womens === true || tName.includes("women") || tName.includes("lpga")
        || tName.includes("kpmg") || tName.includes("chevron") || tName.includes("evian")
        || tName.includes("aig");

      // Gender must match
      if (isWomens !== tIsWomens) return false;

      // Exact name containment (strict)
      if (tName === nameLower) return true;

      // Specific keyword matches
      if (nameLower === "the masters" && tName.includes("masters") && !tName.includes("women")) return true;
      if (nameLower === "pga championship" && tName.includes("pga championship")) return true;
      if (nameLower === "u.s. open" && tName.includes("u.s. open") && !tIsWomens) return true;
      if (nameLower === "the open championship" && (tName.includes("the open") || tName.includes("open championship")) && !tName.includes("women") && !tName.includes("u.s.")) return true;
      if (nameLower === "ryder cup" && tName.includes("ryder")) return true;
      if (nameLower === "presidents cup" && tName.includes("presidents")) return true;
      if (nameLower === "walker cup" && tName.includes("walker")) return true;
      if (nameLower === "solheim cup" && tName.includes("solheim")) return true;

      // Women's specific
      if (nameLower.includes("chevron") && tName.includes("chevron")) return true;
      if (nameLower.includes("kpmg") && tName.includes("kpmg")) return true;
      if (nameLower === "u.s. women's open" && tName.includes("u.s. women")) return true;
      if (nameLower.includes("aig") && tName.includes("aig")) return true;
      if (nameLower.includes("evian") && tName.includes("evian")) return true;

      return false;
    });
  }

  return (
    <div className="min-h-screen">
      {/* Header */}
      <div className="border-b border-surface-border">
        <div className="max-w-7xl mx-auto px-4 py-8">
          <div className="flex items-center gap-2 text-sm text-text-muted mb-4">
            <Link href="/" className="hover:text-text-primary transition-colors">Home</Link>
            <span>/</span>
            <Link href="/sport" className="hover:text-text-primary transition-colors">Sports</Link>
            <span>/</span>
            <span className="text-text-primary">{hierarchy.name}</span>
          </div>
          <h1 className="text-3xl font-bold text-text-primary">{hierarchy.name}</h1>
          <p className="text-text-secondary mt-2">
            {hierarchy.leagues.length} league{hierarchy.leagues.length !== 1 ? "s" : ""}
          </p>
        </div>
      </div>

      <div className="max-w-7xl mx-auto px-4 py-8 space-y-10">
        {/* Leagues */}
        <section>
          <h2 className="text-xs font-medium text-text-secondary uppercase tracking-wide mb-4">Leagues</h2>
          <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4">
            {hierarchy.leagues.map((league: SportLeague) => {
              const colors = LEAGUE_COLORS[league.slug] || DEFAULT_LEAGUE_COLOR;
              return (
                <Link
                  key={league.slug}
                  href={`/sport/${sportSlug}/${league.slug}`}
                  className={`${colors.bg} rounded-xl p-5 border border-surface-border hover:shadow-md hover:-translate-y-0.5 transition-all group`}
                >
                  <div className="flex items-center gap-3">
                    <span className="text-2xl">{colors.icon}</span>
                    <div>
                      <h3 className={`${colors.accent} font-semibold text-lg group-hover:underline`}>
                        {league.name}
                      </h3>
                      <p className="text-text-muted text-sm">
                        View schedule & odds
                      </p>
                    </div>
                  </div>
                </Link>
              );
            })}
          </div>
        </section>

        {/* Showcase Events (Majors, Cups, etc.) */}
        {showcaseGroups.map((group) => (
          <section key={group.type}>
            <h2 className="text-xs font-medium text-text-secondary uppercase tracking-wide mb-4">{group.label}</h2>
            <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
              {group.events.map((event: SportShowcaseEvent) => {
                const tournament = sportSlug === "golf" ? findGolfTournament(event.name) : undefined;

                if (tournament && tournament.golfers && tournament.golfers.length > 0) {
                  const slug = tournament.slug || tournament.key.replace(/_/g, "-");
                  return (
                    <TournamentCard
                      key={event.name}
                      tournament={tournament}
                      href={`/sport/${sportSlug}/pga/${slug}`}
                    />
                  );
                }

                // Fallback card for events without odds yet
                const estimatedDate = SHOWCASE_DATES[event.name];
                return (
                  <div
                    key={event.name}
                    className="bg-surface-card border border-surface-border rounded-xl p-5"
                  >
                    <h3 className="text-text-primary font-medium">{event.name}</h3>
                    <p className="text-text-muted text-sm mt-1">
                      {estimatedDate || "Date TBD"}
                    </p>
                    <p className="text-text-muted text-xs mt-2">
                      Odds available closer to the event
                    </p>
                  </div>
                );
              })}
            </div>
          </section>
        ))}
      </div>
    </div>
  );
}
