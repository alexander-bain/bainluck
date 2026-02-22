"use client";

import { useAuthContext } from "@/components/AuthProvider";
import { useRouter } from "next/navigation";
import { useEffect, useState, useCallback, useRef } from "react";
import useSWR, { mutate as globalMutate } from "swr";
import Link from "next/link";
import {
  fetchUserPreferences,
  searchTeams,
  addFavorite,
  removeFavorite,
  updateSportAffinities,
} from "@/lib/api";
import type { TeamSearchResult, UserFavoriteItem } from "@/lib/types";

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

const AFFINITY_LEVELS: { label: string; value: number }[] = [
  { label: "Love it", value: 1.0 },
  { label: "Playoffs only", value: 0.3 },
  { label: "If wild", value: 0.1 },
  { label: "Not interested", value: 0.0 },
];

function getLevelLabel(value: number): string {
  if (value >= 0.8) return "Love it";
  if (value >= 0.2) return "Playoffs only";
  if (value > 0) return "If wild";
  return "Not interested";
}

function getLevelIndex(value: number): number {
  if (value >= 0.8) return 0;
  if (value >= 0.2) return 1;
  if (value > 0) return 2;
  return 3;
}

// ---------------------------------------------------------------------------
// Inline team autocomplete (shared by all sections)
// ---------------------------------------------------------------------------

function InlineTeamSearch({
  relationType,
  excludeTeamIds,
  onAdded,
  filterCollege,
}: {
  relationType: string;
  excludeTeamIds: Set<number>;
  onAdded: () => void;
  filterCollege?: boolean;
}) {
  const [query, setQuery] = useState("");
  const [results, setResults] = useState<TeamSearchResult[]>([]);
  const [isSearching, setIsSearching] = useState(false);
  const [isOpen, setIsOpen] = useState(false);
  const [adding, setAdding] = useState<number | null>(null);
  const debounceRef = useRef<NodeJS.Timeout>();
  const wrapperRef = useRef<HTMLDivElement>(null);

  // Close dropdown on click outside
  useEffect(() => {
    function handleClickOutside(e: MouseEvent) {
      if (wrapperRef.current && !wrapperRef.current.contains(e.target as Node)) {
        setIsOpen(false);
      }
    }
    document.addEventListener("mousedown", handleClickOutside);
    return () => document.removeEventListener("mousedown", handleClickOutside);
  }, []);

  const doSearch = useCallback(
    async (q: string) => {
      if (q.length < 2) {
        setResults([]);
        return;
      }
      setIsSearching(true);
      try {
        let teams = await searchTeams(q);
        // Filter out already-added teams
        teams = teams.filter((t) => !excludeTeamIds.has(t.id));
        // For alma maters, only show college teams
        if (filterCollege) {
          teams = teams.filter(
            (t) =>
              t.sport_key?.includes("ncaa") ||
              t.sport_key?.includes("wncaab")
          );
        }
        setResults(teams);
        setIsOpen(true);
      } catch {
        setResults([]);
      } finally {
        setIsSearching(false);
      }
    },
    [excludeTeamIds, filterCollege]
  );

  const handleInput = (value: string) => {
    setQuery(value);
    if (debounceRef.current) clearTimeout(debounceRef.current);
    debounceRef.current = setTimeout(() => doSearch(value), 300);
  };

  const handleSelect = async (team: TeamSearchResult) => {
    setAdding(team.id);
    try {
      await addFavorite(team.id, relationType);
      setQuery("");
      setResults([]);
      setIsOpen(false);
      onAdded();
    } catch (err) {
      console.error("Failed to add favorite:", err);
    } finally {
      setAdding(null);
    }
  };

  return (
    <div className="relative mt-2" ref={wrapperRef}>
      <input
        type="text"
        value={query}
        onChange={(e) => handleInput(e.target.value)}
        onFocus={() => results.length > 0 && setIsOpen(true)}
        placeholder="Search teams..."
        className="w-full px-3 py-1.5 text-xs border border-surface-border rounded-lg bg-surface-deep focus:outline-none focus:border-accent-brand/40 transition-colors"
      />
      {isSearching && (
        <div className="absolute right-2 top-1.5">
          <div className="w-4 h-4 border-2 border-surface-border border-t-slate rounded-full animate-spin" />
        </div>
      )}
      {isOpen && results.length > 0 && (
        <div className="absolute z-20 w-full mt-1 bg-surface-card border border-surface-border rounded-lg shadow-lg max-h-48 overflow-y-auto">
          {results.map((team) => (
            <button
              key={team.id}
              onClick={() => handleSelect(team)}
              disabled={adding === team.id}
              className="w-full flex items-center gap-2 px-3 py-2 text-xs text-text-primary hover:bg-surface-elevated transition-colors disabled:opacity-50"
            >
              {team.logo_url && (
                <img
                  src={team.logo_url}
                  alt=""
                  className="w-4 h-4 object-contain flex-shrink-0"
                />
              )}
              <span className="truncate">{team.name}</span>
              {team.sport_key && (
                <span className="text-text-muted ml-auto flex-shrink-0">
                  {team.sport_key.split("_")[0]}
                </span>
              )}
            </button>
          ))}
        </div>
      )}
      {isOpen && query.length >= 2 && results.length === 0 && !isSearching && (
        <div className="absolute z-20 w-full mt-1 bg-surface-card border border-surface-border rounded-lg shadow-lg p-3">
          <p className="text-xs text-text-secondary">
            No teams found. Try a city, abbreviation, or nickname.
          </p>
        </div>
      )}
    </div>
  );
}

// ---------------------------------------------------------------------------
// Team chip with remove button
// ---------------------------------------------------------------------------

function TeamChip({
  team,
  variant = "default",
  onRemove,
}: {
  team: UserFavoriteItem;
  variant?: "default" | "rival" | "follow";
  onRemove: () => void;
}) {
  const [removing, setRemoving] = useState(false);

  const handleRemove = async () => {
    setRemoving(true);
    try {
      await removeFavorite(team.team_id, team.relation_type);
      onRemove();
    } catch (err) {
      console.error("Failed to remove:", err);
    } finally {
      setRemoving(false);
    }
  };

  const colorClasses =
    variant === "rival"
      ? "bg-red-500/150/15 text-red-400 border-red-500/30"
      : variant === "follow"
      ? "bg-accent-brand/15 text-accent-brand border-accent-brand/30"
      : "bg-surface-elevated text-text-primary border-surface-border";

  return (
    <span
      className={`inline-flex items-center gap-1.5 ${colorClasses} px-2.5 py-1 rounded-lg text-xs font-medium border transition-opacity ${
        removing ? "opacity-50" : ""
      }`}
    >
      {team.logo_url && (
        <img src={team.logo_url} alt="" className="w-4 h-4 object-contain" />
      )}
      {team.team_name}
      <button
        onClick={handleRemove}
        disabled={removing}
        className="ml-0.5 text-current opacity-40 hover:opacity-100 transition-opacity disabled:opacity-20"
        title="Remove"
      >
        ×
      </button>
    </span>
  );
}

// ---------------------------------------------------------------------------
// Sport affinity row (clickable level selector)
// ---------------------------------------------------------------------------

function SportAffinityRow({
  sport,
  label,
  level,
  onUpdate,
}: {
  sport: string;
  label: string;
  level: number;
  onUpdate: (sport: string, value: number) => void;
}) {
  const [isEditing, setIsEditing] = useState(false);
  const currentIndex = getLevelIndex(level);

  return (
    <div className="flex items-center justify-between text-xs py-0.5">
      <span className="text-text-primary font-medium">{label}</span>
      {isEditing ? (
        <div className="flex gap-1">
          {AFFINITY_LEVELS.map((opt, i) => (
            <button
              key={opt.value}
              onClick={() => {
                onUpdate(sport, opt.value);
                setIsEditing(false);
              }}
              className={`px-2 py-0.5 rounded text-[10px] transition-colors ${
                i === currentIndex
                  ? "bg-text-primary text-surface-deep"
                  : "bg-surface-elevated text-text-secondary hover:bg-surface-border"
              }`}
            >
              {opt.label}
            </button>
          ))}
        </div>
      ) : (
        <button
          onClick={() => setIsEditing(true)}
          className="text-text-secondary hover:text-text-primary transition-colors"
          title="Click to change"
        >
          {getLevelLabel(level)} ›
        </button>
      )}
    </div>
  );
}

// ---------------------------------------------------------------------------
// Main preferences page
// ---------------------------------------------------------------------------

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
    mutate: mutatePrefs,
  } = useSWR(
    isAuthenticated ? "user-preferences" : null,
    fetchUserPreferences
  );

  // Track local sport affinities for optimistic updates
  const [localAffinities, setLocalAffinities] = useState<Record<string, number> | null>(null);
  const affinities = localAffinities ?? prefs?.sport_affinities ?? {};

  // Sync when prefs load
  useEffect(() => {
    if (prefs?.sport_affinities && !localAffinities) {
      setLocalAffinities(prefs.sport_affinities);
    }
  }, [prefs?.sport_affinities, localAffinities]);

  const handleAffinityUpdate = async (sport: string, value: number) => {
    const updated = { ...affinities, [sport]: value };
    setLocalAffinities(updated);
    try {
      await updateSportAffinities(updated);
      mutatePrefs();
    } catch (err) {
      console.error("Failed to update affinities:", err);
      // Revert on error
      setLocalAffinities(prefs?.sport_affinities ?? {});
    }
  };

  const handleRefresh = () => {
    mutatePrefs();
  };

  if (isLoading || !isAuthenticated) {
    return null;
  }

  const localTeams =
    prefs?.favorites.filter((f) => f.relation_type === "local") ?? [];
  const followTeams =
    prefs?.favorites.filter((f) => f.relation_type === "follow") ?? [];
  const almaMaterTeams =
    prefs?.favorites.filter((f) => f.relation_type === "alma_mater") ?? [];
  const rivalTeams =
    prefs?.favorites.filter((f) => f.relation_type === "rival") ?? [];
  const hasPreferences = prefs?.onboarding_completed;

  // Build set of all currently-favorited team IDs (per-section exclusion uses this)
  const allFavTeamIds = new Set(prefs?.favorites.map((f) => f.team_id) ?? []);

  return (
    <div className="max-w-lg mx-auto px-4 py-8">
      <h1 className="text-2xl font-bold text-text-primary mb-6">Preferences</h1>

      {/* Profile section */}
      <div className="bg-surface-card rounded-xl border border-surface-border p-6 mb-6">
        <h2 className="text-sm font-semibold text-text-secondary uppercase tracking-wide mb-4">
          Account
        </h2>
        <div className="flex items-center gap-4">
          {user?.photoURL ? (
            <img
              src={user.photoURL}
              alt=""
              className="w-12 h-12 rounded-full border border-surface-border"
              referrerPolicy="no-referrer"
            />
          ) : (
            <div className="w-12 h-12 rounded-full bg-text-primary text-surface-deep flex items-center justify-center text-lg font-medium">
              {user?.displayName?.charAt(0)?.toUpperCase() || "?"}
            </div>
          )}
          <div>
            <p className="font-medium text-text-primary">
              {user?.displayName || "User"}
            </p>
            <p className="text-sm text-text-secondary">{user?.email}</p>
          </div>
        </div>
      </div>

      {/* Personalization section */}
      <div className="bg-surface-card rounded-xl border border-surface-border p-6 mb-6">
        <div className="flex items-center justify-between mb-4">
          <h2 className="text-sm font-semibold text-text-secondary uppercase tracking-wide">
            Personalization
          </h2>
          {hasPreferences && (
            <Link
              href="/onboarding"
              className="text-xs text-accent-brand hover:text-accent-brand font-medium transition-colors"
            >
              Redo onboarding
            </Link>
          )}
        </div>

        {prefsLoading ? (
          <div className="space-y-3">
            {[1, 2, 3].map((i) => (
              <div key={i} className="h-6 bg-surface-border/30 rounded animate-pulse" />
            ))}
          </div>
        ) : hasPreferences ? (
          <div className="space-y-5">
            {/* Home location */}
            {prefs?.home_location && (
              <div>
                <p className="text-xs text-text-secondary font-medium mb-1.5">Home</p>
                <p className="text-sm text-text-primary">{prefs.home_location}</p>
              </div>
            )}

            {/* Local teams */}
            <div>
              <p className="text-xs text-text-secondary font-medium mb-1.5">
                Local teams
              </p>
              {localTeams.length > 0 ? (
                <div className="flex flex-wrap gap-2">
                  {localTeams.map((team) => (
                    <TeamChip
                      key={`${team.team_id}-local`}
                      team={team}
                      onRemove={handleRefresh}
                    />
                  ))}
                </div>
              ) : (
                <p className="text-xs text-text-muted italic">None yet</p>
              )}
              <InlineTeamSearch
                relationType="local"
                excludeTeamIds={allFavTeamIds}
                onAdded={handleRefresh}
              />
            </div>

            {/* Followed teams */}
            <div>
              <p className="text-xs text-text-secondary font-medium mb-1.5">
                Followed teams
                <span className="text-text-muted font-normal ml-1">
                  (biggest feed boost)
                </span>
              </p>
              {followTeams.length > 0 ? (
                <div className="flex flex-wrap gap-2">
                  {followTeams.map((team) => (
                    <TeamChip
                      key={`${team.team_id}-follow`}
                      team={team}
                      variant="follow"
                      onRemove={handleRefresh}
                    />
                  ))}
                </div>
              ) : (
                <p className="text-xs text-text-muted italic">None yet</p>
              )}
              <InlineTeamSearch
                relationType="follow"
                excludeTeamIds={allFavTeamIds}
                onAdded={handleRefresh}
              />
            </div>

            {/* Alma maters */}
            <div>
              <p className="text-xs text-text-secondary font-medium mb-1.5">
                Alma maters
              </p>
              {almaMaterTeams.length > 0 ? (
                <div className="flex flex-wrap gap-2">
                  {almaMaterTeams.map((team) => (
                    <TeamChip
                      key={`${team.team_id}-alma`}
                      team={team}
                      onRemove={handleRefresh}
                    />
                  ))}
                </div>
              ) : (
                <p className="text-xs text-text-muted italic">None yet</p>
              )}
              <InlineTeamSearch
                relationType="alma_mater"
                excludeTeamIds={allFavTeamIds}
                onAdded={handleRefresh}
                filterCollege
              />
            </div>

            {/* Rivals */}
            <div>
              <p className="text-xs text-text-secondary font-medium mb-1.5">Rivals</p>
              {rivalTeams.length > 0 ? (
                <div className="flex flex-wrap gap-2">
                  {rivalTeams.map((team) => (
                    <TeamChip
                      key={`${team.team_id}-rival`}
                      team={team}
                      variant="rival"
                      onRemove={handleRefresh}
                    />
                  ))}
                </div>
              ) : (
                <p className="text-xs text-text-muted italic">None yet</p>
              )}
              <InlineTeamSearch
                relationType="rival"
                excludeTeamIds={allFavTeamIds}
                onAdded={handleRefresh}
              />
            </div>

            {/* Sport affinities */}
            <div>
              <p className="text-xs text-text-secondary font-medium mb-1.5">
                Sport interests
                <span className="text-text-muted font-normal ml-1">
                  (tap to change)
                </span>
              </p>
              <div className="space-y-1">
                {Object.entries(SPORT_LABELS).map(([sport, label]) => (
                  <SportAffinityRow
                    key={sport}
                    sport={sport}
                    label={label}
                    level={affinities[sport] ?? 0}
                    onUpdate={handleAffinityUpdate}
                  />
                ))}
              </div>
            </div>
          </div>
        ) : (
          <div className="text-center py-4">
            <p className="text-sm text-text-secondary mb-3">
              Set up your preferences to personalize your feed.
            </p>
            <Link
              href="/onboarding"
              className="inline-block px-4 py-2 bg-text-primary text-surface-deep rounded-xl text-sm font-medium hover:bg-text-primary/90 transition-colors"
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
        className="w-full py-3 text-sm text-text-secondary hover:text-text-primary border border-surface-border rounded-xl hover:bg-surface-elevated transition-colors"
      >
        Sign out
      </button>
    </div>
  );
}
