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
  { type: "major", label: "Men's Majors" },
  { type: "womens_major", label: "Women's Majors" },
  { type: "cup", label: "Cups & Team Events" },
  { type: "grand_slam", label: "Grand Slams" },
  { type: "tournament", label: "Tournaments" },
  { type: "championship", label: "Championships" },
];

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
      <div className="min-h-screen bg-gray-950 text-white flex items-center justify-center">
        <div className="animate-pulse text-gray-400">Loading...</div>
      </div>
    );
  }

  if (error || !hierarchy) {
    return (
      <div className="min-h-screen bg-gray-950 text-white flex items-center justify-center">
        <div className="text-center">
          <p className="text-gray-400 mb-4">{error || "Sport not found"}</p>
          <Link href="/" className="text-blue-400 hover:text-blue-300">
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

  // For golf, match showcase events to tournament data for richer cards
  function findGolfTournament(eventName: string): GolfTournament | undefined {
    const nameLower = eventName.toLowerCase();
    return golfTournaments.find((t: GolfTournament) => {
      const tName = t.name.toLowerCase();
      // Fuzzy match: "The Masters" matches "Masters Tournament", etc.
      return tName.includes(nameLower) || nameLower.includes(tName)
        || (nameLower.includes("masters") && tName.includes("masters"))
        || (nameLower.includes("open") && tName.includes("open") && !tName.includes("women"))
        || (nameLower.includes("pga championship") && tName.includes("pga championship"))
        || (nameLower.includes("u.s. open") && tName.includes("u.s. open"));
    });
  }

  return (
    <div className="min-h-screen bg-gray-950 text-white">
      {/* Header */}
      <div className="bg-gradient-to-b from-gray-900 to-gray-950 border-b border-gray-800">
        <div className="max-w-5xl mx-auto px-4 py-8">
          <div className="flex items-center gap-2 text-sm text-gray-400 mb-4">
            <Link href="/" className="hover:text-white transition-colors">Home</Link>
            <span>/</span>
            <span className="text-white">{hierarchy.name}</span>
          </div>
          <h1 className="text-3xl font-bold">{hierarchy.name}</h1>
          <p className="text-gray-400 mt-2">
            {hierarchy.leagues.length} league{hierarchy.leagues.length !== 1 ? "s" : ""}
          </p>
        </div>
      </div>

      <div className="max-w-5xl mx-auto px-4 py-8 space-y-10">
        {/* Leagues */}
        <section>
          <h2 className="text-lg font-semibold text-gray-300 mb-4">Leagues</h2>
          <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4">
            {hierarchy.leagues.map((league: SportLeague) => (
              <Link
                key={league.slug}
                href={`/sport/${sportSlug}/${league.slug}`}
                className="bg-gray-900 border border-gray-800 rounded-xl p-5 hover:border-gray-600 hover:bg-gray-800/50 transition-all group"
              >
                <h3 className="text-white font-semibold text-lg group-hover:text-blue-400 transition-colors">
                  {league.name}
                </h3>
                <p className="text-gray-500 text-sm mt-1">
                  View schedule & odds
                </p>
              </Link>
            ))}
          </div>
        </section>

        {/* Showcase Events (Majors, Cups, etc.) */}
        {showcaseGroups.map((group) => (
          <section key={group.type}>
            <h2 className="text-lg font-semibold text-gray-300 mb-4">{group.label}</h2>
            <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
              {group.events.map((event: SportShowcaseEvent) => {
                const tournament = sportSlug === "golf" ? findGolfTournament(event.name) : undefined;

                if (tournament && tournament.golfers && tournament.golfers.length > 0) {
                  const slug = tournament.slug || tournament.key.replace(/_/g, "-");
                  // Rich card with odds data
                  return (
                    <TournamentCard
                      key={event.name}
                      tournament={tournament}
                      href={`/sport/${sportSlug}/pga/${slug}`}
                    />
                  );
                }

                // Fallback: simple card
                return (
                  <div
                    key={event.name}
                    className="bg-gray-900 border border-gray-800 rounded-xl p-5"
                  >
                    <h3 className="text-white font-medium">{event.name}</h3>
                    <p className="text-gray-500 text-sm mt-1 capitalize">
                      {event.type.replace(/_/g, " ")}
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
