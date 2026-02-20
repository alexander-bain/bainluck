"use client";

import { useState, useEffect, useCallback, useRef } from "react";
import { useRouter } from "next/navigation";
import { useAuthContext } from "@/components/AuthProvider";
import { searchTeamsByLocation, searchTeams, submitOnboarding } from "@/lib/api";
import { SPORT_CATEGORIES } from "@/lib/sportCategories";
import type { TeamSearchResult, OnboardingSubmission } from "@/lib/types";

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

// Sports to show in the grid — tier 1 + tier 2 from sportCategories.ts
const ONBOARDING_SPORTS = SPORT_CATEGORIES.filter(
  (s) => s.tier === 1 || s.tier === 2
);

// Default affinities — Big 3 US sports default to "Love it"
const DEFAULT_AFFINITIES: Record<string, SportLevel> = {};
for (const sport of ONBOARDING_SPORTS) {
  if (["football", "basketball", "baseball"].includes(sport.key)) {
    DEFAULT_AFFINITIES[sport.key] = 1.0;
  } else {
    DEFAULT_AFFINITIES[sport.key] = 0;
  }
}

// =============================================================================
// Main Component
// =============================================================================

export default function OnboardingPage() {
  const { isAuthenticated, isLoading } = useAuthContext();
  const router = useRouter();

  // Step state
  const [step, setStep] = useState(1);
  const TOTAL_STEPS = 4;

  // Step 1: Location
  const [locationQuery, setLocationQuery] = useState("");
  const [locationTeams, setLocationTeams] = useState<SelectedTeam[]>([]);
  const [selectedLocation, setSelectedLocation] = useState<string | null>(null);
  const [locationSearching, setLocationSearching] = useState(false);

  // Step 2: Alma maters
  const [schoolQuery, setSchoolQuery] = useState("");
  const [schoolResults, setSchoolResults] = useState<TeamSearchResult[]>([]);
  const [almaMaterTeams, setAlmaMaterTeams] = useState<SelectedTeam[]>([]);
  const [schoolSearching, setSchoolSearching] = useState(false);

  // Step 3: Sport affinities
  const [sportAffinities, setSportAffinities] = useState<Record<string, SportLevel>>(
    { ...DEFAULT_AFFINITIES }
  );

  // Step 4: Rivals
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
  // Step 2: School search
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
    // Check if this school (by location/name prefix) is already added
    const alreadyHas = almaMaterTeams.some(
      (t) => t.name === team.name || (team.location && t.name.startsWith(team.location))
    );
    if (alreadyHas) return;

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
  // Step 4: Rival search
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

    try {
      const data: OnboardingSubmission = {
        home_location: selectedLocation || locationQuery || null,
        local_teams: locationTeams
          .filter((t) => t.selected)
          .map((t) => ({ team_id: t.id })),
        alma_mater_teams: almaMaterTeams.map((t) => ({ team_id: t.id })),
        rival_teams: rivalTeams.map((t) => ({ team_id: t.id })),
        sport_affinities: Object.fromEntries(
          Object.entries(sportAffinities).filter(([, v]) => v > 0)
        ),
        raw_inputs: {
          location_query: locationQuery,
          school_selections: almaMaterTeams.map((t) => t.name),
          rival_selections: rivalTeams.map((t) => t.name),
        },
      };

      await submitOnboarding(data);
      router.push("/?onboarded=1");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Something went wrong");
    } finally {
      setSubmitting(false);
    }
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
    <div className="min-h-screen bg-snow">
      <div className="max-w-lg mx-auto px-4 py-8">
        {/* Progress indicator */}
        <div className="flex items-center justify-between mb-8">
          <div className="flex gap-2">
            {Array.from({ length: TOTAL_STEPS }, (_, i) => (
              <div
                key={i}
                className={`h-1.5 rounded-full transition-all ${
                  i + 1 <= step ? "w-8 bg-graphite" : "w-8 bg-slate-200"
                }`}
              />
            ))}
          </div>
          <button
            onClick={skip}
            className="text-xs text-slate hover:text-graphite transition-colors"
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

        {step === 3 && (
          <StepSports
            affinities={sportAffinities}
            onChange={(key, value) =>
              setSportAffinities((prev) => ({ ...prev, [key]: value }))
            }
          />
        )}

        {step === 4 && (
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

        {/* Error message */}
        {error && (
          <div className="mt-4 p-3 bg-red-50 text-red-700 rounded-lg text-sm">
            {error}
          </div>
        )}

        {/* Navigation buttons */}
        <div className="flex items-center justify-between mt-8">
          {step > 1 ? (
            <button
              onClick={goBack}
              className="text-sm text-slate hover:text-graphite transition-colors"
            >
              ← Back
            </button>
          ) : (
            <div />
          )}

          {step < TOTAL_STEPS ? (
            <button
              onClick={goNext}
              className="px-6 py-2.5 bg-graphite text-white rounded-xl text-sm font-medium hover:bg-graphite/90 transition-colors"
            >
              Continue
            </button>
          ) : (
            <button
              onClick={handleSubmit}
              disabled={submitting}
              className="px-6 py-2.5 bg-graphite text-white rounded-xl text-sm font-medium hover:bg-graphite/90 transition-colors disabled:opacity-50"
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
      <h1 className="text-2xl font-bold text-graphite mb-2">
        Where do you follow sports?
      </h1>
      <p className="text-sm text-slate mb-6">
        We&apos;ll boost your local teams in the feed.
      </p>

      <input
        type="text"
        value={query}
        onChange={(e) => onSearch(e.target.value)}
        placeholder="City or region (e.g., Boston, Bay Area)"
        className="w-full px-4 py-3 bg-white border border-mist rounded-xl text-sm text-graphite placeholder:text-silver focus:outline-none focus:ring-2 focus:ring-graphite/20"
        autoFocus
      />

      {searching && (
        <p className="text-xs text-slate mt-3">Searching...</p>
      )}

      {teams.length > 0 && (
        <div className="mt-4">
          <p className="text-xs text-slate mb-2 font-medium uppercase tracking-wide">
            {selectedLocation ? `Teams near ${selectedLocation}` : "Teams found"}
          </p>
          <div className="flex flex-wrap gap-2">
            {teams.map((team) => (
              <button
                key={team.id}
                onClick={() => onToggle(team.id)}
                className={`inline-flex items-center gap-2 px-3 py-2 rounded-xl text-sm border transition-all ${
                  team.selected
                    ? "bg-graphite text-white border-graphite"
                    : "bg-white text-slate border-mist hover:border-slate"
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
        <p className="text-sm text-slate mt-4">
          No teams found for &quot;{query}&quot;. Try a major city name.
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
      <h1 className="text-2xl font-bold text-graphite mb-2">Any alma maters?</h1>
      <p className="text-sm text-slate mb-6">
        We&apos;ll highlight your school&apos;s games and championship odds.
      </p>

      <div className="relative">
        <input
          type="text"
          value={query}
          onChange={(e) => onSearch(e.target.value)}
          placeholder="Search for a school (e.g., Duke, Stanford)"
          className="w-full px-4 py-3 bg-white border border-mist rounded-xl text-sm text-graphite placeholder:text-silver focus:outline-none focus:ring-2 focus:ring-graphite/20"
          autoFocus
        />

        {/* Dropdown results */}
        {results.length > 0 && (
          <div className="absolute z-10 mt-1 w-full bg-white border border-mist rounded-xl shadow-lg max-h-60 overflow-y-auto">
            {results.map((team) => (
              <button
                key={team.id}
                onClick={() => onAdd(team)}
                className="w-full flex items-center gap-3 px-4 py-3 hover:bg-snow transition-colors text-left border-b border-mist/50 last:border-0"
              >
                {team.logo_url && (
                  <img src={team.logo_url} alt="" className="w-5 h-5 object-contain" />
                )}
                <div className="min-w-0">
                  <p className="text-sm font-medium text-graphite truncate">{team.name}</p>
                  {team.sport_key && (
                    <p className="text-xs text-slate">{team.sport_key}</p>
                  )}
                </div>
              </button>
            ))}
          </div>
        )}
      </div>

      {searching && <p className="text-xs text-slate mt-3">Searching...</p>}

      {/* Selected schools */}
      {selected.length > 0 && (
        <div className="mt-4 flex flex-wrap gap-2">
          {selected.map((team) => (
            <span
              key={team.id}
              className="inline-flex items-center gap-2 px-3 py-2 bg-graphite text-white rounded-xl text-sm"
            >
              {team.logo_url && (
                <img src={team.logo_url} alt="" className="w-4 h-4 object-contain" />
              )}
              {team.name}
              <button
                onClick={() => onRemove(team.id)}
                className="ml-1 hover:text-white/70"
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
      <h1 className="text-2xl font-bold text-graphite mb-2">
        What sports do you care about?
      </h1>
      <p className="text-sm text-slate mb-6">
        This helps us show you the most relevant games and markets.
      </p>

      <div className="space-y-3">
        {ONBOARDING_SPORTS.map((sport) => {
          const currentLevel = affinities[sport.key] ?? 0;
          return (
            <div
              key={sport.key}
              className="flex items-center justify-between bg-white border border-mist rounded-xl px-4 py-3"
            >
              <div className="flex items-center gap-3">
                <span className="text-lg">{sport.emoji}</span>
                <span className="text-sm font-medium text-graphite">{sport.name}</span>
              </div>
              <div className="flex gap-1">
                {SPORT_LEVELS.map((level) => (
                  <button
                    key={level.value}
                    onClick={() => onChange(sport.key, level.value)}
                    title={level.description}
                    className={`px-2.5 py-1 rounded-lg text-xs font-medium transition-all ${
                      currentLevel === level.value
                        ? "bg-graphite text-white"
                        : "bg-snow text-slate hover:bg-slate-100"
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
      <h1 className="text-2xl font-bold text-graphite mb-2">Any rivals?</h1>
      <p className="text-sm text-slate mb-6">
        Teams you love to hate. We&apos;ll make sure you see it when they&apos;re losing.
      </p>

      <div className="relative">
        <input
          type="text"
          value={query}
          onChange={(e) => onSearch(e.target.value)}
          placeholder="Search for a team (e.g., Yankees, Lakers)"
          className="w-full px-4 py-3 bg-white border border-mist rounded-xl text-sm text-graphite placeholder:text-silver focus:outline-none focus:ring-2 focus:ring-graphite/20"
          autoFocus
        />

        {/* Dropdown results */}
        {results.length > 0 && (
          <div className="absolute z-10 mt-1 w-full bg-white border border-mist rounded-xl shadow-lg max-h-60 overflow-y-auto">
            {results.map((team) => (
              <button
                key={team.id}
                onClick={() => onAdd(team)}
                className="w-full flex items-center gap-3 px-4 py-3 hover:bg-snow transition-colors text-left border-b border-mist/50 last:border-0"
              >
                {team.logo_url && (
                  <img src={team.logo_url} alt="" className="w-5 h-5 object-contain" />
                )}
                <div className="min-w-0">
                  <p className="text-sm font-medium text-graphite truncate">{team.name}</p>
                  {team.location && (
                    <p className="text-xs text-slate">{team.location}</p>
                  )}
                </div>
              </button>
            ))}
          </div>
        )}
      </div>

      {searching && <p className="text-xs text-slate mt-3">Searching...</p>}

      {/* Selected rivals */}
      {selected.length > 0 && (
        <div className="mt-4 flex flex-wrap gap-2">
          {selected.map((team) => (
            <span
              key={team.id}
              className="inline-flex items-center gap-2 px-3 py-2 bg-red-50 text-red-700 border border-red-200 rounded-xl text-sm"
            >
              {team.logo_url && (
                <img src={team.logo_url} alt="" className="w-4 h-4 object-contain" />
              )}
              {team.name}
              <button
                onClick={() => onRemove(team.id)}
                className="ml-1 hover:text-red-400"
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
        <p className="text-xs text-slate mt-4">
          This step is totally optional. Skip if you don&apos;t have any rivals.
        </p>
      )}
    </div>
  );
}
