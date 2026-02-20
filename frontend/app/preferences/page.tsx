"use client";

import { useAuthContext } from "@/components/AuthProvider";
import { useRouter } from "next/navigation";
import { useEffect } from "react";
import useSWR from "swr";
import Link from "next/link";
import { fetchUserPreferences } from "@/lib/api";

const SPORT_LABELS: Record<string, string> = {
  football: "Football",
  basketball: "Basketball",
  baseball: "Baseball",
  hockey: "Hockey",
  soccer: "Soccer",
  golf: "Golf",
  tennis: "Tennis",
  mma: "MMA",
  boxing: "Boxing",
  cricket: "Cricket",
  rugby: "Rugby",
  motorsport: "Motorsport",
};

function getLevelLabel(value: number): string {
  if (value >= 0.8) return "Love it";
  if (value >= 0.2) return "Playoffs only";
  if (value > 0) return "If wild";
  return "Not interested";
}

export default function PreferencesPage() {
  const { user, isAuthenticated, isLoading, signOut } = useAuthContext();
  const router = useRouter();

  // Redirect to home if not authenticated
  useEffect(() => {
    if (!isLoading && !isAuthenticated) {
      router.push("/");
    }
  }, [isLoading, isAuthenticated, router]);

  // Fetch preferences
  const {
    data: prefs,
    isLoading: prefsLoading,
  } = useSWR(
    isAuthenticated ? "user-preferences" : null,
    fetchUserPreferences
  );

  if (isLoading || !isAuthenticated) {
    return null;
  }

  const localTeams = prefs?.favorites.filter((f) => f.relation_type === "local") ?? [];
  const almaMaterTeams = prefs?.favorites.filter((f) => f.relation_type === "alma_mater") ?? [];
  const rivalTeams = prefs?.favorites.filter((f) => f.relation_type === "rival") ?? [];
  const hasPreferences = prefs?.onboarding_completed;

  return (
    <div className="max-w-lg mx-auto px-4 py-8">
      <h1 className="text-2xl font-bold text-graphite mb-6">Preferences</h1>

      {/* Profile section */}
      <div className="bg-white rounded-xl border border-mist p-6 mb-6">
        <h2 className="text-sm font-semibold text-slate uppercase tracking-wide mb-4">
          Account
        </h2>
        <div className="flex items-center gap-4">
          {user?.photoURL ? (
            <img
              src={user.photoURL}
              alt=""
              className="w-12 h-12 rounded-full border border-mist"
              referrerPolicy="no-referrer"
            />
          ) : (
            <div className="w-12 h-12 rounded-full bg-graphite text-white flex items-center justify-center text-lg font-medium">
              {user?.displayName?.charAt(0)?.toUpperCase() || "?"}
            </div>
          )}
          <div>
            <p className="font-medium text-graphite">
              {user?.displayName || "User"}
            </p>
            <p className="text-sm text-slate">{user?.email}</p>
          </div>
        </div>
      </div>

      {/* Personalization section */}
      <div className="bg-white rounded-xl border border-mist p-6 mb-6">
        <div className="flex items-center justify-between mb-4">
          <h2 className="text-sm font-semibold text-slate uppercase tracking-wide">
            Personalization
          </h2>
          {hasPreferences && (
            <Link
              href="/onboarding"
              className="text-xs text-indigo-600 hover:text-indigo-800 font-medium transition-colors"
            >
              Edit
            </Link>
          )}
        </div>

        {prefsLoading ? (
          <div className="space-y-3">
            {[1, 2, 3].map((i) => (
              <div key={i} className="h-6 bg-mist/30 rounded animate-pulse" />
            ))}
          </div>
        ) : hasPreferences ? (
          <div className="space-y-5">
            {/* Home location */}
            {prefs?.home_location && (
              <div>
                <p className="text-xs text-slate font-medium mb-1.5">Home</p>
                <p className="text-sm text-graphite">{prefs.home_location}</p>
              </div>
            )}

            {/* Local teams */}
            {localTeams.length > 0 && (
              <div>
                <p className="text-xs text-slate font-medium mb-1.5">Local teams</p>
                <div className="flex flex-wrap gap-2">
                  {localTeams.map((team) => (
                    <span
                      key={team.team_id}
                      className="inline-flex items-center gap-1.5 bg-snow px-2.5 py-1 rounded-lg text-xs font-medium text-graphite border border-mist"
                    >
                      {team.logo_url && (
                        <img src={team.logo_url} alt="" className="w-4 h-4 object-contain" />
                      )}
                      {team.team_name}
                    </span>
                  ))}
                </div>
              </div>
            )}

            {/* Alma maters */}
            {almaMaterTeams.length > 0 && (
              <div>
                <p className="text-xs text-slate font-medium mb-1.5">Alma maters</p>
                <div className="flex flex-wrap gap-2">
                  {almaMaterTeams.map((team) => (
                    <span
                      key={team.team_id}
                      className="inline-flex items-center gap-1.5 bg-snow px-2.5 py-1 rounded-lg text-xs font-medium text-graphite border border-mist"
                    >
                      {team.logo_url && (
                        <img src={team.logo_url} alt="" className="w-4 h-4 object-contain" />
                      )}
                      {team.team_name}
                    </span>
                  ))}
                </div>
              </div>
            )}

            {/* Rivals */}
            {rivalTeams.length > 0 && (
              <div>
                <p className="text-xs text-slate font-medium mb-1.5">Rivals</p>
                <div className="flex flex-wrap gap-2">
                  {rivalTeams.map((team) => (
                    <span
                      key={team.team_id}
                      className="inline-flex items-center gap-1.5 bg-red-50 px-2.5 py-1 rounded-lg text-xs font-medium text-red-700 border border-red-200"
                    >
                      {team.logo_url && (
                        <img src={team.logo_url} alt="" className="w-4 h-4 object-contain" />
                      )}
                      {team.team_name}
                    </span>
                  ))}
                </div>
              </div>
            )}

            {/* Sport affinities */}
            {prefs?.sport_affinities && Object.keys(prefs.sport_affinities).length > 0 && (
              <div>
                <p className="text-xs text-slate font-medium mb-1.5">Sport interests</p>
                <div className="space-y-1">
                  {Object.entries(prefs.sport_affinities)
                    .sort(([, a], [, b]) => b - a)
                    .map(([sport, level]) => (
                      <div
                        key={sport}
                        className="flex items-center justify-between text-xs"
                      >
                        <span className="text-graphite font-medium">
                          {SPORT_LABELS[sport] || sport}
                        </span>
                        <span className="text-slate">
                          {getLevelLabel(level)}
                        </span>
                      </div>
                    ))}
                </div>
              </div>
            )}
          </div>
        ) : (
          <div className="text-center py-4">
            <p className="text-sm text-slate mb-3">
              Set up your preferences to personalize your feed.
            </p>
            <Link
              href="/onboarding"
              className="inline-block px-4 py-2 bg-graphite text-white rounded-xl text-sm font-medium hover:bg-graphite/90 transition-colors"
            >
              Set up personalization
            </Link>
          </div>
        )}
      </div>

      {/* Sign out */}
      <button
        onClick={async () => {
          await signOut();
          router.push("/");
        }}
        className="w-full py-3 text-sm text-slate hover:text-graphite border border-mist rounded-xl hover:bg-snow transition-colors"
      >
        Sign out
      </button>
    </div>
  );
}
