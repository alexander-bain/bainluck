"use client";

import { useState, useEffect, useCallback, useRef } from "react";
import { useRouter } from "next/navigation";
import { useAuthContext } from "@/components/AuthProvider";
import { searchTeamsByLocation, searchTeams, submitOnboarding, fetchUserPreferences } from "@/lib/api";
import { SPORT_CATEGORIES, getLeagueDisplay, getEmojiForLeague } from "@/lib/sportCategories";
import type { TeamSearchResult, OnboardingSubmission, UserFavoriteItem } from "@/lib/types";

// =============================================================================
// Types
// =============================================================================

interface SelectedTeam {
  id: number;
  name: string;
  sport_key: string | null;
  logo_url: string | null;
  selected: boolean; // For toggle-able chips (location teams)
}

type SportLevel = 1.0 | 0.3 | 0.1 | 0;

const SPORT_LEVELS: { label: string; value: SportLevel; description: string }[] = [
  { label: "Love it", value: 1.0, description: "Always show" },
  { label: "Playoffs", value: 0.3, description: "Playoffs only" },
  { label: "If wild", value: 0.1, description: "Only if exciting" },
  { label: "Nah", value: 0, description: "Not for me" },
];

// Non-sports categories from prediction markets (Polymarket, Kalshi)
const BEYOND_SPORTS_KEYS = new Set([
  "politics", "entertainment", "crypto", "economics", "tech", "weather",
  "geopolitics", "culture",
]);

// Sports to show in the grid — tier 1 + tier 2 from sportCategories.ts,
// excluding non-sports categories (those go in Beyond Sports section below).
const ONBOARDING_SPORTS = SPORT_CATEGORIES.filter(
  (s) => (s.tier === 1 || s.tier === 2) && !BEYOND_SPORTS_KEYS.has(s.key)
);
const ONBOARDING_BEYOND_SPORTS = SPORT_CATEGORIES.filter(
  (s) => BEYOND_SPORTS_KEYS.has(s.key)
);

/**
 * Format sport_key into a short readable league label.
 * e.g., "basketball_nba" → "NBA", "lacrosse_ncaa" → "NCAA Lacrosse"
 */
function sportLabel(sportKey: string | null): string | null {
  if (!sportKey) return null;
  return getLeagueDisplay(sportKey);
}

// Default affinities — Big 3 US sports default to "Love it"
const DEFAULT_AFFINITIES: Record<string, SportLevel> = {};
for (const sport of ONBOARDING_SPORTS) {
  if (["football", "basketball", "baseball"].includes(sport.key)) {
    DEFAULT_AFFINITIES[sport.key] = 1.0;
  } else {
    DEFAULT_AFFINITIES[sport.key] = 0;
  }
}
for (const cat of ONBOARDING_BEYOND_SPORTS) {
  DEFAULT_AFFINITIES[cat.key] = 0;
}

// =============================================================================
// Main Component
// =============================================================================

export default function OnboardingPage() {
  const auth = useAuthContext();
  const { isAuthenticated, isLoading } = auth;
  const router = useRouter();

  // Step state — 5 steps now
  const [step, setStep] = useState(1);
  const TOTAL_STEPS = 5;

  // Step 1: Location
  const [locationQuery, setLocationQuery] = useState("");
  const [locationTeams, setLocationTeams] = useState<SelectedTeam[]>([]);
  const [selectedLocation, setSelectedLocation] = useState<string | null>(null);
  const [locationSearching, setLocationSearching] = useState(false);

  // Step 2: Follow (favorite teams, any location)
  const [followQuery, setFollowQuery] = useState("");
  const [followResults, setFollowResults] = useState<TeamSearchResult[]>([]);
  const [followTeams, setFollowTeams] = useState<SelectedTeam[]>([]);
  const [followSearching, setFollowSearching] = useState(false);

  // Step 3: Alma maters
  const [schoolQuery, setSchoolQuery] = useState("");
  const [schoolResults, setSchoolResults] = useState<TeamSearchResult[]>([]);
  const [almaMaterTeams, setAlmaMaterTeams] = useState<SelectedTeam[]>([]);
  const [schoolSearching, setSchoolSearching] = useState(false);

  // Step 4: Sport affinities
  const [sportAffinities, setSportAffinities] = useState<Record<string, SportLevel>>(
    { ...DEFAULT_AFFINITIES }
  );

  // Step 5: Rivals
  const [rivalQuery, setRivalQuery] = useState("");
  const [rivalResults, setRivalResults] = useState<TeamSearchResult[]>([]);
  const [rivalTeams, setRivalTeams] = useState<SelectedTeam[]>([]);
  const [rivalSearching, setRivalSearching] = useState(false);

  // Submission state
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // Redirect if not authenticated
  useEffect(() => {
    if (!isLoading && !isAuthenticated) {
      router.push("/");
    }
  }, [isLoading, isAuthenticated, router]);

  // Pre-populate from existing preferences when re-visiting onboarding
  const [prePopulated, setPrePopulated] = useState(false);
  useEffect(() => {
    if (!isAuthenticated || prePopulated) return;
    (async () => {
      try {
        const prefs = await fetchUserPreferences();
        if (!prefs.onboarding_completed) return;

        // Helper to convert favorites to SelectedTeam[]
        const toSelected = (items: UserFavoriteItem[]): SelectedTeam[] =>
          items.map((f) => ({
            id: f.team_id,
            name: f.team_name,
            sport_key: f.sport_key,
            logo_url: f.logo_url,
            selected: true,
          }));

        // Location
        if (prefs.home_location) {
          setLocationQuery(prefs.home_location);
          setSelectedLocation(prefs.home_location);
        }
        const locals = prefs.favorites.filter((f) => f.relation_type === "local");
        if (locals.length > 0) setLocationTeams(toSelected(locals));

        // Follow
        const follows = prefs.favorites.filter((f) => f.relation_type === "follow");
        if (follows.length > 0) setFollowTeams(toSelected(follows));

        // Alma maters
        const almas = prefs.favorites.filter((f) => f.relation_type === "alma_mater");
        if (almas.length > 0) setAlmaMaterTeams(toSelected(almas));

        // Rivals
        const rivals = prefs.favorites.filter((f) => f.relation_type === "rival");
        if (rivals.length > 0) setRivalTeams(toSelected(rivals));

        // Sport affinities
        if (prefs.sport_affinities && Object.keys(prefs.sport_affinities).length > 0) {
          const mapped: Record<string, SportLevel> = { ...DEFAULT_AFFINITIES };
          for (const [key, val] of Object.entries(prefs.sport_affinities)) {
            if (key in mapped) {
              // Snap to nearest level
              if (val >= 0.8) mapped[key] = 1.0;
              else if (val >= 0.2) mapped[key] = 0.3;
              else if (val > 0) mapped[key] = 0.1;
              else mapped[key] = 0;
            }
          }
          setSportAffinities(mapped);
        }

        setPrePopulated(true);
      } catch {
        // If fetch fails, just proceed with defaults
      }
    })();
  }, [isAuthenticated, prePopulated]);

  // =========================================================================
  // Step 1: Location search
  // =========================================================================

  const locationDebounce = useRef<ReturnType<typeof setTimeout>>();

  const handleLocationSearch = useCallback((value: string) => {
    setLocationQuery(value);
    setSelectedLocation(null);
    setLocationTeams([]);

    if (locationDebounce.current) clearTimeout(locationDebounce.current);

    if (value.length < 2) return;

    setLocationSearching(true);
    locationDebounce.current = setTimeout(async () => {
      try {
        const results = await searchTeamsByLocation(value);
        // Group by location and show as toggleable chips
        const teams: SelectedTeam[] = results.map((t) => ({
          id: t.id,
          name: t.name,
          sport_key: t.sport_key,
          logo_url: t.logo_url,
          selected: true, // All on by default
        }));
        setLocationTeams(teams);
        if (results.length > 0 && results[0].location) {
          setSelectedLocation(results[0].location);
        }
      } catch {
        // silently fail
      } finally {
        setLocationSearching(false);
      }
    }, 300);
  }, []);

  const toggleLocationTeam = (teamId: number) => {
    setLocationTeams((prev) =>
      prev.map((t) => (t.id === teamId ? { ...t, selected: !t.selected } : t))
    );
  };

  // =========================================================================
  // Step 2: Follow search (favorite teams, any location)
  // =========================================================================

  const followDebounce = useRef<ReturnType<typeof setTimeout>>();

  const handleFollowSearch = useCallback(
    (value: string) => {
      setFollowQuery(value);

      if (followDebounce.current) clearTimeout(followDebounce.current);

      if (value.length < 2) {
        setFollowResults([]);
        return;
      }

      setFollowSearching(true);
      followDebounce.current = setTimeout(async () => {
        try {
          const results = await searchTeams(value);
          // Filter out teams already selected as local or follow
          const localIds = new Set(
            locationTeams.filter((t) => t.selected).map((t) => t.id)
          );
          const followIds = new Set(followTeams.map((t) => t.id));
          setFollowResults(
            results.filter((t) => !localIds.has(t.id) && !followIds.has(t.id))
          );
        } catch {
          // silently fail
        } finally {
          setFollowSearching(false);
        }
      }, 300);
    },
    [locationTeams, followTeams]
  );

  const addFollowTeam = (team: TeamSearchResult) => {
    if (followTeams.some((t) => t.id === team.id)) return;

    setFollowTeams((prev) => [
      ...prev,
      {
        id: team.id,
        name: team.name,
        sport_key: team.sport_key,
        logo_url: team.logo_url,
        selected: true,
      },
    ]);
    setFollowQuery("");
    setFollowResults([]);
  };

  const removeFollowTeam = (teamId: number) => {
    setFollowTeams((prev) => prev.filter((t) => t.id !== teamId));
  };

  // =========================================================================
  // Step 3: School search
  // =========================================================================

  const schoolDebounce = useRef<ReturnType<typeof setTimeout>>();

  const handleSchoolSearch = useCallback((value: string) => {
    setSchoolQuery(value);

    if (schoolDebounce.current) clearTimeout(schoolDebounce.current);

    if (value.length < 2) {
      setSchoolResults([]);
      return;
    }

    setSchoolSearching(true);
    schoolDebounce.current = setTimeout(async () => {
      try {
        const results = await searchTeams(value);
        // Filter to college teams only (sport_key contains "ncaa" or "wncaab")
        const collegeResults = results.filter(
          (t) =>
            t.sport_key &&
            (t.sport_key.includes("ncaa") || t.sport_key.includes("wncaab"))
        );
        // Don't show teams already selected
        const selectedIds = new Set(almaMaterTeams.map((t) => t.id));
        setSchoolResults(collegeResults.filter((t) => !selectedIds.has(t.id)));
      } catch {
        // silently fail
      } finally {
        setSchoolSearching(false);
      }
    }, 300);
  }, [almaMaterTeams]);

  const addAlmaMater = (team: TeamSearchResult) => {
    // Check if this exact team is already added (by ID)
    if (almaMaterTeams.some((t) => t.id === team.id)) return;

    setAlmaMaterTeams((prev) => [
      ...prev,
      {
        id: team.id,
        name: team.name,
        sport_key: team.sport_key,
        logo_url: team.logo_url,
        selected: true,
      },
    ]);
    setSchoolQuery("");
    setSchoolResults([]);
  };

  const removeAlmaMater = (teamId: number) => {
    setAlmaMaterTeams((prev) => prev.filter((t) => t.id !== teamId));
  };

  // =========================================================================
  // Step 5: Rival search
  // =========================================================================

  const rivalDebounce = useRef<ReturnType<typeof setTimeout>>();

  const handleRivalSearch = useCallback((value: string) => {
    setRivalQuery(value);

    if (rivalDebounce.current) clearTimeout(rivalDebounce.current);

    if (value.length < 2) {
      setRivalResults([]);
      return;
    }

    setRivalSearching(true);
    rivalDebounce.current = setTimeout(async () => {
      try {
        const results = await searchTeams(value);
        const selectedIds = new Set(rivalTeams.map((t) => t.id));
        setRivalResults(results.filter((t) => !selectedIds.has(t.id)));
      } catch {
        // silently fail
      } finally {
        setRivalSearching(false);
      }
    }, 300);
  }, [rivalTeams]);

  const addRival = (team: TeamSearchResult) => {
    if (rivalTeams.some((t) => t.id === team.id)) return;

    setRivalTeams((prev) => [
      ...prev,
      {
        id: team.id,
        name: team.name,
        sport_key: team.sport_key,
        logo_url: team.logo_url,
        selected: true,
      },
    ]);
    setRivalQuery("");
    setRivalResults([]);
  };

  const removeRival = (teamId: number) => {
    setRivalTeams((prev) => prev.filter((t) => t.id !== teamId));
  };

  // =========================================================================
  // Submission
  // =========================================================================

  const handleSubmit = async () => {
    setSubmitting(true);
    setError(null);

    // Build submission data first (before any async ops)
    const data: OnboardingSubmission = {
      home_location: selectedLocation || locationQuery || null,
      local_teams: locationTeams
        .filter((t) => t.selected)
        .map((t) => ({ team_id: t.id })),
      follow_teams: followTeams.map((t) => ({ team_id: t.id })),
      alma_mater_teams: almaMaterTeams.map((t) => ({ team_id: t.id })),
      rival_teams: rivalTeams.map((t) => ({ team_id: t.id })),
      sport_affinities: Object.fromEntries(
        Object.entries(sportAffinities).filter(([, v]) => v > 0)
      ),
      raw_inputs: {
        location_query: locationQuery,
        follow_selections: followTeams.map((t) => t.name),
        school_selections: almaMaterTeams.map((t) => t.name),
        rival_selections: rivalTeams.map((t) => t.name),
      },
    };

    // Check auth token — Safari can silently lose tokens (ITP clears IndexedDB)
    const { getToken, signInWithGoogle } = auth;
    let token: string | null = null;
    try {
      token = await getToken();
    } catch {
      token = null;
    }

    // If no token, offer to re-sign-in inline rather than redirecting away
    if (!token) {
      try {
        console.log("[Onboarding] Token expired, attempting silent re-auth...");
        await signInWithGoogle();
        // Wait a moment for auth state to propagate
        await new Promise((r) => setTimeout(r, 500));
        token = await getToken();
      } catch {
        token = null;
      }

      if (!token) {
        setError(
          "Your session expired. Please sign in again from the homepage and return to finish onboarding — your selections are saved in the browser."
        );
        setSubmitting(false);
        return;
      }
    }

    // Submit with retry — first attempt may fail if token just refreshed
    let lastError: string = "Something went wrong";
    for (let attempt = 0; attempt < 2; attempt++) {
      try {
        await submitOnboarding(data);
        router.push("/?onboarded=1");
        return; // Success!
      } catch (err) {
        lastError = err instanceof Error ? err.message : "Something went wrong";
        console.error(`[Onboarding] Submit attempt ${attempt + 1} failed:`, lastError);

        // If auth error, try refreshing token before retry
        if (attempt === 0 && (lastError.includes("401") || lastError.includes("Authentication"))) {
          try {
            token = await getToken();
            if (!token) {
              await signInWithGoogle();
              await new Promise((r) => setTimeout(r, 500));
            }
            continue; // Retry
          } catch {
            break; // Give up
          }
        }
        break; // Non-auth error, don't retry
      }
    }

    // All attempts failed
    if (lastError.includes("Authentication") || lastError.includes("401")) {
      setError("Your session expired. Please sign in again from the homepage.");
    } else {
      setError(`Save failed: ${lastError}. Please try again.`);
    }
    setSubmitting(false);
  };

  // =========================================================================
  // Navigation
  // =========================================================================

  const goNext = () => setStep((s) => Math.min(s + 1, TOTAL_STEPS));
  const goBack = () => setStep((s) => Math.max(s - 1, 1));
  const skip = () => router.push("/");

  if (isLoading || !isAuthenticated) {
    return null;
  }

  return (
    <div className="min-h-screen bg-surface-deep">
      <div className="max-w-lg mx-auto px-4 py-8">
        {/* Progress indicator */}
        <div className="flex items-center justify-between mb-8">
          <div className="flex gap-2">
            {Array.from({ length: TOTAL_STEPS }, (_, i) => (
              <div
                key={i}
                className={`h-1.5 rounded-full transition-all ${
                  i + 1 <= step ? "w-8 bg-graphite" : "w-8 bg-surface-border"
                }`}
              />
            ))}
          </div>
          <button
            onClick={skip}
            className="text-xs text-text-secondary hover:text-text-primary transition-colors"
          >
            Skip for now
          </button>
        </div>

        {/* Step content */}
        {step === 1 && (
          <StepLocation
            query={locationQuery}
            onSearch={handleLocationSearch}
            teams={locationTeams}
            onToggle={toggleLocationTeam}
            searching={locationSearching}
            selectedLocation={selectedLocation}
          />
        )}

        {step === 2 && (
          <StepFollow
            query={followQuery}
            onSearch={handleFollowSearch}
            results={followResults}
            selected={followTeams}
            onAdd={addFollowTeam}
            onRemove={removeFollowTeam}
            searching={followSearching}
          />
        )}

        {step === 3 && (
          <StepAlmaMaters
            query={schoolQuery}
            onSearch={handleSchoolSearch}
            results={schoolResults}
            selected={almaMaterTeams}
            onAdd={addAlmaMater}
            onRemove={removeAlmaMater}
            searching={schoolSearching}
          />
        )}

        {step === 4 && (
          <StepSports
            affinities={sportAffinities}
            onChange={(key, value) =>
              setSportAffinities((prev) => ({ ...prev, [key]: value }))
            }
          />
        )}

        {step === 5 && (
          <StepRivals
            query={rivalQuery}
            onSearch={handleRivalSearch}
            results={rivalResults}
            selected={rivalTeams}
            onAdd={addRival}
            onRemove={removeRival}
            searching={rivalSearching}
          />
        )}

        {/* Summary before submit (on last step) */}
        {step === TOTAL_STEPS && (
          <OnboardingSummary
            location={selectedLocation || locationQuery}
            localTeams={locationTeams.filter((t) => t.selected)}
            followTeams={followTeams}
            almaMaterTeams={almaMaterTeams}
            rivalTeams={rivalTeams}
            sportAffinities={sportAffinities}
          />
        )}

        {/* Error message */}
        {error && (
          <div className="mt-4 p-3 bg-red-500/150/15 text-red-400 rounded-lg text-sm">
            {error}
          </div>
        )}

        {/* Navigation buttons */}
        <div className="flex items-center justify-between mt-8">
          {step > 1 ? (
            <button
              onClick={goBack}
              className="text-sm text-text-secondary hover:text-text-primary transition-colors"
            >
              &larr; Back
            </button>
          ) : (
            <div />
          )}

          {step < TOTAL_STEPS ? (
            <button
              onClick={goNext}
              className="px-6 py-2.5 bg-text-primary text-surface-deep rounded-xl text-sm font-medium hover:bg-text-primary/90 transition-colors"
            >
              Continue
            </button>
          ) : (
            <button
              onClick={handleSubmit}
              disabled={submitting}
              className="px-6 py-2.5 bg-text-primary text-surface-deep rounded-xl text-sm font-medium hover:bg-text-primary/90 transition-colors disabled:opacity-50"
            >
              {submitting ? "Saving..." : "Done"}
            </button>
          )}
        </div>
      </div>
    </div>
  );
}

// =============================================================================
// Step Components
// =============================================================================

function StepLocation({
  query,
  onSearch,
  teams,
  onToggle,
  searching,
  selectedLocation,
}: {
  query: string;
  onSearch: (q: string) => void;
  teams: SelectedTeam[];
  onToggle: (teamId: number) => void;
  searching: boolean;
  selectedLocation: string | null;
}) {
  return (
    <div>
      <h1 className="text-2xl font-bold text-text-primary mb-2">
        Where do you follow sports?
      </h1>
      <p className="text-sm text-text-secondary mb-6">
        We&apos;ll boost your local teams in the feed.
      </p>

      <input
        type="text"
        value={query}
        onChange={(e) => onSearch(e.target.value)}
        placeholder="City or region (e.g., Boston, Bay Area)"
        className="w-full px-4 py-3 bg-surface-card border border-surface-border rounded-xl text-sm text-text-primary placeholder:text-text-muted focus:outline-none focus:ring-2 focus:ring-accent-brand/30"
        autoFocus
      />

      {searching && (
        <p className="text-xs text-text-secondary mt-3">Searching...</p>
      )}

      {teams.length > 0 && (
        <div className="mt-4">
          <p className="text-xs text-text-secondary mb-2 font-medium uppercase tracking-wide">
            {selectedLocation ? `Teams near ${selectedLocation}` : "Teams found"}
          </p>
          <div className="flex flex-wrap gap-2">
            {teams.map((team) => (
              <button
                key={team.id}
                onClick={() => onToggle(team.id)}
                className={`inline-flex items-center gap-2 px-3 py-2 rounded-xl text-sm border transition-all ${
                  team.selected
                    ? "bg-text-primary text-surface-deep border-text-primary"
                    : "bg-surface-card text-text-secondary border-surface-border hover:border-text-secondary"
                }`}
              >
                {team.logo_url && (
                  <img
                    src={team.logo_url}
                    alt=""
                    className="w-5 h-5 object-contain"
                  />
                )}
                <span className="font-medium">{team.name}</span>
                {team.sport_key && (
                  <span className="text-xs opacity-70">
                    {sportLabel(team.sport_key)}
                  </span>
                )}
                {team.selected && (
                  <svg className="w-3.5 h-3.5" fill="currentColor" viewBox="0 0 20 20">
                    <path
                      fillRule="evenodd"
                      d="M16.707 5.293a1 1 0 010 1.414l-8 8a1 1 0 01-1.414 0l-4-4a1 1 0 011.414-1.414L8 12.586l7.293-7.293a1 1 0 011.414 0z"
                      clipRule="evenodd"
                    />
                  </svg>
                )}
              </button>
            ))}
          </div>
        </div>
      )}

      {query.length >= 2 && !searching && teams.length === 0 && (
        <p className="text-sm text-text-secondary mt-4">
          No teams found for &quot;{query}&quot;. Try a major city name, abbreviation, or nickname.
        </p>
      )}
    </div>
  );
}

function StepFollow({
  query,
  onSearch,
  results,
  selected,
  onAdd,
  onRemove,
  searching,
}: {
  query: string;
  onSearch: (q: string) => void;
  results: TeamSearchResult[];
  selected: SelectedTeam[];
  onAdd: (team: TeamSearchResult) => void;
  onRemove: (teamId: number) => void;
  searching: boolean;
}) {
  return (
    <div>
      <h1 className="text-2xl font-bold text-text-primary mb-2">
        Any other favorite teams?
      </h1>
      <p className="text-sm text-text-secondary mb-6">
        Teams you root for, even if they&apos;re not local. These get the biggest
        boost in your feed.
      </p>

      <div className="relative">
        <input
          type="text"
          value={query}
          onChange={(e) => onSearch(e.target.value)}
          placeholder="Search for a team (e.g., Cowboys, Warriors)"
          className="w-full px-4 py-3 bg-surface-card border border-surface-border rounded-xl text-sm text-text-primary placeholder:text-text-muted focus:outline-none focus:ring-2 focus:ring-accent-brand/30"
          autoFocus
        />

        {/* Dropdown results */}
        {results.length > 0 && (
          <div className="absolute z-10 mt-1 w-full bg-surface-card border border-surface-border rounded-xl shadow-lg max-h-60 overflow-y-auto">
            {results.map((team) => (
              <button
                key={team.id}
                onClick={() => onAdd(team)}
                className="w-full flex items-center gap-3 px-4 py-3 hover:bg-surface-elevated transition-colors text-left border-b border-surface-border/50 last:border-0"
              >
                {team.logo_url && (
                  <img src={team.logo_url} alt="" className="w-5 h-5 object-contain" />
                )}
                <div className="min-w-0 flex-1">
                  <p className="text-sm font-medium text-text-primary truncate">{team.name}</p>
                  <p className="text-xs text-text-secondary">
                    {[sportLabel(team.sport_key), team.location].filter(Boolean).join(" · ")}
                  </p>
                </div>
              </button>
            ))}
          </div>
        )}
      </div>

      {searching && <p className="text-xs text-text-secondary mt-3">Searching...</p>}

      {/* Selected teams */}
      {selected.length > 0 && (
        <div className="mt-4 flex flex-wrap gap-2">
          {selected.map((team) => (
            <span
              key={team.id}
              className="inline-flex items-center gap-2 px-3 py-2 bg-text-primary text-surface-deep rounded-xl text-sm"
            >
              {team.logo_url && (
                <img src={team.logo_url} alt="" className="w-4 h-4 object-contain" />
              )}
              {team.name}
              {team.sport_key && (
                <span className="text-xs opacity-70">{sportLabel(team.sport_key)}</span>
              )}
              <button
                onClick={() => onRemove(team.id)}
                className="ml-1 hover:text-surface-deep/70"
              >
                <svg className="w-3.5 h-3.5" fill="currentColor" viewBox="0 0 20 20">
                  <path
                    fillRule="evenodd"
                    d="M4.293 4.293a1 1 0 011.414 0L10 8.586l4.293-4.293a1 1 0 111.414 1.414L11.414 10l4.293 4.293a1 1 0 01-1.414 1.414L10 11.414l-4.293 4.293a1 1 0 01-1.414-1.414L8.586 10 4.293 5.707a1 1 0 010-1.414z"
                    clipRule="evenodd"
                  />
                </svg>
              </button>
            </span>
          ))}
        </div>
      )}

      {selected.length === 0 && (
        <p className="text-xs text-text-secondary mt-4">
          This step is optional &mdash; skip if your local teams cover it.
        </p>
      )}
    </div>
  );
}

function StepAlmaMaters({
  query,
  onSearch,
  results,
  selected,
  onAdd,
  onRemove,
  searching,
}: {
  query: string;
  onSearch: (q: string) => void;
  results: TeamSearchResult[];
  selected: SelectedTeam[];
  onAdd: (team: TeamSearchResult) => void;
  onRemove: (teamId: number) => void;
  searching: boolean;
}) {
  return (
    <div>
      <h1 className="text-2xl font-bold text-text-primary mb-2">Any alma maters?</h1>
      <p className="text-sm text-text-secondary mb-6">
        We&apos;ll highlight your school&apos;s games and championship odds.
      </p>

      <div className="relative">
        <input
          type="text"
          value={query}
          onChange={(e) => onSearch(e.target.value)}
          placeholder="Search for a school (e.g., Duke, Stanford)"
          className="w-full px-4 py-3 bg-surface-card border border-surface-border rounded-xl text-sm text-text-primary placeholder:text-text-muted focus:outline-none focus:ring-2 focus:ring-accent-brand/30"
          autoFocus
        />

        {/* Dropdown results */}
        {results.length > 0 && (
          <div className="absolute z-10 mt-1 w-full bg-surface-card border border-surface-border rounded-xl shadow-lg max-h-60 overflow-y-auto">
            {results.map((team) => (
              <button
                key={team.id}
                onClick={() => onAdd(team)}
                className="w-full flex items-center gap-3 px-4 py-3 hover:bg-surface-elevated transition-colors text-left border-b border-surface-border/50 last:border-0"
              >
                {team.logo_url && (
                  <img src={team.logo_url} alt="" className="w-5 h-5 object-contain" />
                )}
                <div className="min-w-0 flex-1">
                  <p className="text-sm font-medium text-text-primary truncate">{team.name}</p>
                  {team.sport_key && (
                    <p className="text-xs text-text-secondary">{sportLabel(team.sport_key)}</p>
                  )}
                </div>
              </button>
            ))}
          </div>
        )}
      </div>

      {searching && <p className="text-xs text-text-secondary mt-3">Searching...</p>}

      {/* Selected schools */}
      {selected.length > 0 && (
        <div className="mt-4 flex flex-wrap gap-2">
          {selected.map((team) => (
            <span
              key={team.id}
              className="inline-flex items-center gap-2 px-3 py-2 bg-text-primary text-surface-deep rounded-xl text-sm"
            >
              {team.logo_url && (
                <img src={team.logo_url} alt="" className="w-4 h-4 object-contain" />
              )}
              {team.name}
              {team.sport_key && (
                <span className="text-xs opacity-70">{sportLabel(team.sport_key)}</span>
              )}
              <button
                onClick={() => onRemove(team.id)}
                className="ml-1 hover:text-surface-deep/70"
              >
                <svg className="w-3.5 h-3.5" fill="currentColor" viewBox="0 0 20 20">
                  <path
                    fillRule="evenodd"
                    d="M4.293 4.293a1 1 0 011.414 0L10 8.586l4.293-4.293a1 1 0 111.414 1.414L11.414 10l4.293 4.293a1 1 0 01-1.414 1.414L10 11.414l-4.293 4.293a1 1 0 01-1.414-1.414L8.586 10 4.293 5.707a1 1 0 010-1.414z"
                    clipRule="evenodd"
                  />
                </svg>
              </button>
            </span>
          ))}
        </div>
      )}
    </div>
  );
}

function StepSports({
  affinities,
  onChange,
}: {
  affinities: Record<string, SportLevel>;
  onChange: (key: string, value: SportLevel) => void;
}) {
  return (
    <div>
      <h1 className="text-2xl font-bold text-text-primary mb-2">
        What do you care about?
      </h1>
      <p className="text-sm text-text-secondary mb-6">
        This helps us show you the most relevant games and markets.
      </p>

      <div className="space-y-3">
        {ONBOARDING_SPORTS.map((sport) => {
          const currentLevel = affinities[sport.key] ?? 0;
          return (
            <div
              key={sport.key}
              className="flex items-center justify-between bg-surface-card border border-surface-border rounded-xl px-4 py-3"
            >
              <div className="flex items-center gap-3">
                <span className="text-lg">{sport.emoji}</span>
                <span className="text-sm font-medium text-text-primary">{sport.name}</span>
              </div>
              <div className="flex gap-1">
                {SPORT_LEVELS.map((level) => (
                  <button
                    key={level.value}
                    onClick={() => onChange(sport.key, level.value)}
                    title={level.description}
                    className={`px-2.5 py-1 rounded-lg text-xs font-medium transition-all ${
                      currentLevel === level.value
                        ? "bg-text-primary text-surface-deep"
                        : "bg-surface-elevated text-text-secondary hover:bg-surface-elevated"
                    }`}
                  >
                    {level.label}
                  </button>
                ))}
              </div>
            </div>
          );
        })}
      </div>

      {/* Beyond Sports — prediction market categories */}
      {ONBOARDING_BEYOND_SPORTS.length > 0 && (
        <>
          <p className="text-xs font-semibold text-text-secondary uppercase tracking-wide mt-6 mb-3">
            Beyond Sports
          </p>
          <p className="text-xs text-text-secondary mb-3">
            We also track prediction markets for these categories.
          </p>
          <div className="space-y-3">
            {ONBOARDING_BEYOND_SPORTS.map((cat) => {
              const currentLevel = affinities[cat.key] ?? 0;
              return (
                <div
                  key={cat.key}
                  className="flex items-center justify-between bg-surface-card border border-surface-border rounded-xl px-4 py-3"
                >
                  <div className="flex items-center gap-3">
                    <span className="text-lg">{cat.emoji}</span>
                    <span className="text-sm font-medium text-text-primary">{cat.name}</span>
                  </div>
                  <div className="flex gap-1">
                    {SPORT_LEVELS.map((level) => (
                      <button
                        key={level.value}
                        onClick={() => onChange(cat.key, level.value)}
                        title={level.description}
                        className={`px-2.5 py-1 rounded-lg text-xs font-medium transition-all ${
                          currentLevel === level.value
                            ? "bg-text-primary text-surface-deep"
                            : "bg-surface-elevated text-text-secondary hover:bg-surface-elevated"
                        }`}
                      >
                        {level.label}
                      </button>
                    ))}
                  </div>
                </div>
              );
            })}
          </div>
        </>
      )}
    </div>
  );
}

function StepRivals({
  query,
  onSearch,
  results,
  selected,
  onAdd,
  onRemove,
  searching,
}: {
  query: string;
  onSearch: (q: string) => void;
  results: TeamSearchResult[];
  selected: SelectedTeam[];
  onAdd: (team: TeamSearchResult) => void;
  onRemove: (teamId: number) => void;
  searching: boolean;
}) {
  return (
    <div>
      <h1 className="text-2xl font-bold text-text-primary mb-2">Any rivals?</h1>
      <p className="text-sm text-text-secondary mb-6">
        Teams you love to hate. We&apos;ll make sure you see it when they&apos;re losing.
      </p>

      <div className="relative">
        <input
          type="text"
          value={query}
          onChange={(e) => onSearch(e.target.value)}
          placeholder="Search for a team (e.g., Yankees, Lakers)"
          className="w-full px-4 py-3 bg-surface-card border border-surface-border rounded-xl text-sm text-text-primary placeholder:text-text-muted focus:outline-none focus:ring-2 focus:ring-accent-brand/30"
          autoFocus
        />

        {/* Dropdown results */}
        {results.length > 0 && (
          <div className="absolute z-10 mt-1 w-full bg-surface-card border border-surface-border rounded-xl shadow-lg max-h-60 overflow-y-auto">
            {results.map((team) => (
              <button
                key={team.id}
                onClick={() => onAdd(team)}
                className="w-full flex items-center gap-3 px-4 py-3 hover:bg-surface-elevated transition-colors text-left border-b border-surface-border/50 last:border-0"
              >
                {team.logo_url && (
                  <img src={team.logo_url} alt="" className="w-5 h-5 object-contain" />
                )}
                <div className="min-w-0 flex-1">
                  <p className="text-sm font-medium text-text-primary truncate">{team.name}</p>
                  <p className="text-xs text-text-secondary">
                    {[sportLabel(team.sport_key), team.location].filter(Boolean).join(" · ")}
                  </p>
                </div>
              </button>
            ))}
          </div>
        )}
      </div>

      {searching && <p className="text-xs text-text-secondary mt-3">Searching...</p>}

      {/* Selected rivals */}
      {selected.length > 0 && (
        <div className="mt-4 flex flex-wrap gap-2">
          {selected.map((team) => (
            <span
              key={team.id}
              className="inline-flex items-center gap-2 px-3 py-2 bg-red-500/150/15 text-red-400 border border-red-500/30 rounded-xl text-sm"
            >
              {team.logo_url && (
                <img src={team.logo_url} alt="" className="w-4 h-4 object-contain" />
              )}
              {team.name}
              {team.sport_key && (
                <span className="text-xs opacity-70">{sportLabel(team.sport_key)}</span>
              )}
              <button
                onClick={() => onRemove(team.id)}
                className="ml-1 hover:text-red-300"
              >
                <svg className="w-3.5 h-3.5" fill="currentColor" viewBox="0 0 20 20">
                  <path
                    fillRule="evenodd"
                    d="M4.293 4.293a1 1 0 011.414 0L10 8.586l4.293-4.293a1 1 0 111.414 1.414L11.414 10l4.293 4.293a1 1 0 01-1.414 1.414L10 11.414l-4.293 4.293a1 1 0 01-1.414-1.414L8.586 10 4.293 5.707a1 1 0 010-1.414z"
                    clipRule="evenodd"
                  />
                </svg>
              </button>
            </span>
          ))}
        </div>
      )}

      {selected.length === 0 && (
        <p className="text-xs text-text-secondary mt-4">
          This step is totally optional. Skip if you don&apos;t have any rivals.
        </p>
      )}
    </div>
  );
}

// =============================================================================
// Summary Component (shown on last step before submit)
// =============================================================================

function OnboardingSummary({
  location,
  localTeams,
  followTeams,
  almaMaterTeams,
  rivalTeams,
  sportAffinities,
}: {
  location: string | null | undefined;
  localTeams: SelectedTeam[];
  followTeams: SelectedTeam[];
  almaMaterTeams: SelectedTeam[];
  rivalTeams: SelectedTeam[];
  sportAffinities: Record<string, SportLevel>;
}) {
  const activeSports = Object.entries(sportAffinities)
    .filter(([, v]) => v > 0)
    .sort(([, a], [, b]) => b - a);

  const hasAnything =
    location ||
    localTeams.length > 0 ||
    followTeams.length > 0 ||
    almaMaterTeams.length > 0 ||
    rivalTeams.length > 0 ||
    activeSports.length > 0;

  if (!hasAnything) return null;

  const sportLabel = (key: string) =>
    ONBOARDING_SPORTS.find((s) => s.key === key)?.name ||
    ONBOARDING_BEYOND_SPORTS.find((s) => s.key === key)?.name ||
    key;

  const levelEmoji = (val: number) => {
    if (val >= 0.8) return "❤️";
    if (val >= 0.2) return "👀";
    return "🤏";
  };

  return (
    <div className="mt-6 p-4 bg-surface-card border border-surface-border rounded-xl">
      <p className="text-xs font-semibold text-text-secondary uppercase tracking-wide mb-3">
        Your selections
      </p>
      <div className="space-y-2 text-xs text-text-primary">
        {location && (
          <p>
            <span className="text-text-secondary">Home:</span> {location}
          </p>
        )}
        {localTeams.length > 0 && (
          <p>
            <span className="text-text-secondary">Local:</span>{" "}
            {localTeams.map((t) => t.name).join(", ")}
          </p>
        )}
        {followTeams.length > 0 && (
          <p>
            <span className="text-text-secondary">Following:</span>{" "}
            {followTeams.map((t) => t.name).join(", ")}
          </p>
        )}
        {almaMaterTeams.length > 0 && (
          <p>
            <span className="text-text-secondary">Alma maters:</span>{" "}
            {almaMaterTeams.map((t) => t.name).join(", ")}
          </p>
        )}
        {rivalTeams.length > 0 && (
          <p>
            <span className="text-text-secondary">Rivals:</span>{" "}
            {rivalTeams.map((t) => t.name).join(", ")}
          </p>
        )}
        {activeSports.length > 0 && (
          <p>
            <span className="text-text-secondary">Sports:</span>{" "}
            {activeSports.map(([key, val]) => `${levelEmoji(val)} ${sportLabel(key)}`).join(", ")}
          </p>
        )}
      </div>
      <p className="text-[10px] text-text-muted mt-2">
        You can update these anytime from Preferences.
      </p>
    </div>
  );
}
