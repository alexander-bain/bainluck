"use client";

import { useState } from "react";
import Link from "next/link";
import useSWR from "swr";
import { useAuthContext } from "@/components/AuthProvider";
import { useRouter } from "next/navigation";
import {
  fetchUserPreferences,
  removeFavorite,
  fetchEventsByIds,
  fetchFuturesByIds,
} from "@/lib/api";
import { usePinnedEvents, usePinnedFutures, usePageTracking, useScrollDepth, useEngagementTime } from "@/hooks";
import { useCategoryInterests, getLevelLabel } from "@/hooks/useCategoryInterests";
import EventCard from "@/components/EventCard";
import FuturesCard from "@/components/FuturesCard";
import type { UserFavoriteItem } from "@/lib/types";

// All categories (sports + beyond)
const ALL_CATEGORIES: { key: string; label: string; emoji: string }[] = [
  // Sports — split pro vs college for football + basketball
  { key: "nfl", label: "NFL", emoji: "🏈" },
  { key: "college_football", label: "College Football", emoji: "🏈" },
  { key: "nba", label: "NBA", emoji: "🏀" },
  { key: "college_basketball", label: "College Basketball", emoji: "🏀" },
  { key: "baseball", label: "Baseball", emoji: "⚾" },
  { key: "hockey", label: "Hockey", emoji: "🏒" },
  { key: "soccer", label: "Soccer", emoji: "⚽" },
  { key: "golf", label: "Golf", emoji: "⛳" },
  { key: "tennis", label: "Tennis", emoji: "🎾" },
  { key: "mma", label: "MMA", emoji: "🥊" },
  { key: "boxing", label: "Boxing", emoji: "🥊" },
  { key: "motorsports", label: "Motorsports", emoji: "🏎️" },
  { key: "cricket", label: "Cricket", emoji: "🏏" },
  { key: "rugby", label: "Rugby", emoji: "🏉" },
  // Beyond sports
  { key: "politics", label: "Politics", emoji: "🏛️" },
  { key: "entertainment", label: "Entertainment", emoji: "🎬" },
  { key: "economics", label: "Economics", emoji: "📈" },
  { key: "tech", label: "Tech", emoji: "💻" },
  { key: "weather", label: "Weather", emoji: "🌤️" },
  { key: "geopolitics", label: "Geopolitics", emoji: "🌍" },
  { key: "culture", label: "Culture", emoji: "🎭" },
  { key: "esports", label: "Esports", emoji: "🎮" },
  { key: "lacrosse", label: "Lacrosse", emoji: "🥍" },
  { key: "chess", label: "Chess", emoji: "♟️" },
];

const LEVEL_OPTIONS = [
  { label: "Love it", value: 1.0 },
  { label: "Big moments", value: 0.3 },
  { label: "If wild", value: 0.1 },
  { label: "Nah", value: 0 },
];

export default function PreferencesPage() {
  usePageTracking({ pageType: 'preferences', pageTitle: 'Preferences' });
  useScrollDepth({ pageType: 'preferences' });
  useEngagementTime({ pageType: 'preferences' });

  const { user, isAuthenticated, isLoading: authLoading, signOut } = useAuthContext();
  const router = useRouter();
  const { interests, setInterest } = useCategoryInterests();

  // Pinned events
  const { pinnedIds, isPinned, togglePin, isMaxReached } = usePinnedEvents();
  const {
    pinnedIds: pinnedFuturesIds,
    isPinned: isFuturesPinned,
    togglePin: toggleFuturesPin,
    isMaxReached: isFuturesMaxReached,
  } = usePinnedFutures();

  // Fetch pinned items data
  const { data: pinnedEvents } = useSWR(
    pinnedIds.length > 0 ? ["prefs-pinned-events", ...pinnedIds] : null,
    () => fetchEventsByIds(pinnedIds),
  );
  const { data: pinnedFutures } = useSWR(
    pinnedFuturesIds.length > 0 ? ["prefs-pinned-futures", ...pinnedFuturesIds] : null,
    () => fetchFuturesByIds(pinnedFuturesIds),
  );

  // Auth'd user preferences
  const {
    data: prefs,
    mutate: mutatePrefs,
  } = useSWR(
    isAuthenticated ? "user-preferences" : null,
    fetchUserPreferences,
  );

  const handleRefresh = () => mutatePrefs();

  const localTeams = prefs?.favorites.filter(f => f.relation_type === "local") ?? [];
  const followTeams = prefs?.favorites.filter(f => f.relation_type === "follow") ?? [];
  const almaMaterTeams = prefs?.favorites.filter(f => f.relation_type === "alma_mater") ?? [];
  const rivalTeams = prefs?.favorites.filter(f => f.relation_type === "rival") ?? [];

  return (
    <div className="max-w-lg mx-auto space-y-6">
      <h1 className="text-xl font-bold text-text-primary">Preferences</h1>

      {/* ================================================================
          Your Teams (auth'd only)
          ================================================================ */}
      {isAuthenticated && prefs && (
        <section className="bg-surface-card rounded-xl border border-surface-border p-4">
          <div className="flex items-center justify-between mb-3">
            <h2 className="text-sm font-semibold text-text-secondary uppercase tracking-wide">
              Your Teams
            </h2>
            <Link
              href="/onboarding"
              className="text-xs text-accent-brand hover:text-accent-brand font-medium transition-colors"
            >
              Edit
            </Link>
          </div>

          {[
            { label: "Following", teams: followTeams, variant: "follow" as const, type: "follow" },
            { label: "Local", teams: localTeams, variant: "default" as const, type: "local" },
            { label: "Alma maters", teams: almaMaterTeams, variant: "default" as const, type: "alma_mater" },
            { label: "Rivals", teams: rivalTeams, variant: "rival" as const, type: "rival" },
          ].map(section => (
            section.teams.length > 0 && (
              <div key={section.type} className="mb-3 last:mb-0">
                <p className="text-xs text-text-muted font-medium mb-1.5">{section.label}</p>
                <div className="flex flex-wrap gap-1.5">
                  {section.teams.map(team => (
                    <TeamChip
                      key={`${team.team_id}-${section.type}`}
                      team={team}
                      variant={section.variant}
                      onRemove={handleRefresh}
                    />
                  ))}
                </div>
              </div>
            )
          ))}

          {followTeams.length === 0 && localTeams.length === 0 && almaMaterTeams.length === 0 && rivalTeams.length === 0 && (
            <div className="text-center py-3">
              <p className="text-xs text-text-muted mb-2">No teams yet</p>
              <Link
                href="/onboarding"
                className="text-xs text-accent-brand font-medium"
              >
                Set up your teams
              </Link>
            </div>
          )}
        </section>
      )}

      {/* ================================================================
          Your Interests
          ================================================================ */}
      <section className="bg-surface-card rounded-xl border border-surface-border p-4">
        <h2 className="text-sm font-semibold text-text-secondary uppercase tracking-wide mb-3">
          Your Interests
        </h2>
        <p className="text-xs text-text-muted mb-3">
          Controls what shows up in your feed. Tap to change.
        </p>

        <div className="space-y-1">
          {ALL_CATEGORIES.map(cat => (
            <InterestRow
              key={cat.key}
              category={cat.key}
              label={cat.label}
              emoji={cat.emoji}
              value={interests[cat.key] ?? 0}
              onUpdate={setInterest}
            />
          ))}
        </div>
      </section>

      {/* ================================================================
          Pinned Items
          ================================================================ */}
      {(pinnedIds.length > 0 || pinnedFuturesIds.length > 0) && (
        <section className="bg-surface-card rounded-xl border border-surface-border p-4">
          <h2 className="text-sm font-semibold text-text-secondary uppercase tracking-wide mb-3">
            Pinned
          </h2>
          <div className="grid gap-3" style={{ gridTemplateColumns: "repeat(auto-fill, minmax(min(100%, 280px), 1fr))" }}>
            {(pinnedEvents ?? []).map((event, idx) => (
              <EventCard
                key={`pinned-${event.id}`}
                event={event}
                showSport
                sourceSection="pinned"
                positionIndex={idx}
                isPinned
                onPinToggle={togglePin}
                pinDisabled={isMaxReached}
              />
            ))}
            {(pinnedFutures ?? []).map((market) => (
              <FuturesCard
                key={`pinned-f-${market.id}`}
                market={market}
                showSport
                isPinned
                onPinToggle={toggleFuturesPin}
                pinDisabled={isFuturesMaxReached}
              />
            ))}
          </div>
        </section>
      )}

      {/* ================================================================
          Account (auth'd) or Sign In prompt (anon)
          ================================================================ */}
      {isAuthenticated && user ? (
        <section className="bg-surface-card rounded-xl border border-surface-border p-4">
          <h2 className="text-sm font-semibold text-text-secondary uppercase tracking-wide mb-3">
            Account
          </h2>
          <div className="flex items-center gap-3 mb-4">
            {user.photoURL ? (
              <img
                src={user.photoURL}
                alt=""
                className="w-10 h-10 rounded-full border border-surface-border"
                referrerPolicy="no-referrer"
              />
            ) : (
              <div className="w-10 h-10 rounded-full bg-text-primary text-surface-deep flex items-center justify-center text-sm font-medium">
                {user.displayName?.charAt(0)?.toUpperCase() || "?"}
              </div>
            )}
            <div>
              <p className="text-sm font-medium text-text-primary">{user.displayName || "User"}</p>
              <p className="text-xs text-text-secondary">{user.email}</p>
            </div>
          </div>

          <div className="flex gap-2">
            <Link
              href="/onboarding"
              className="flex-1 text-center py-2 text-xs font-medium text-text-secondary border border-surface-border rounded-lg hover:bg-surface-elevated transition-colors"
            >
              Redo onboarding
            </Link>
            <button
              onClick={async () => {
                await signOut();
                router.push("/");
              }}
              className="flex-1 py-2 text-xs font-medium text-text-secondary border border-surface-border rounded-lg hover:bg-surface-elevated transition-colors"
            >
              Sign out
            </button>
          </div>
        </section>
      ) : !authLoading && (
        <section className="bg-surface-card rounded-xl border border-surface-border p-6 text-center">
          <p className="text-sm text-text-secondary mb-1">
            Sign in to sync across devices
          </p>
          <p className="text-xs text-text-muted">
            Your interests are saved locally. Sign in to keep them everywhere.
          </p>
        </section>
      )}
    </div>
  );
}

// ---------------------------------------------------------------------------
// Interest row with 4-level selector
// ---------------------------------------------------------------------------

function InterestRow({
  category,
  label,
  emoji,
  value,
  onUpdate,
}: {
  category: string;
  label: string;
  emoji: string;
  value: number;
  onUpdate: (category: string, value: number) => void;
}) {
  const [isEditing, setIsEditing] = useState(false);

  const currentLabel = getLevelLabel(value);

  return (
    <div className="flex items-center justify-between text-xs py-1">
      <span className="flex items-center gap-1.5 text-text-primary font-medium">
        <span>{emoji}</span>
        {label}
      </span>
      {isEditing ? (
        <div className="flex gap-1">
          {LEVEL_OPTIONS.map((opt) => (
            <button
              key={opt.value}
              onClick={() => {
                onUpdate(category, opt.value);
                setIsEditing(false);
              }}
              className={`px-2 py-0.5 rounded text-[10px] transition-colors ${
                Math.abs(value - opt.value) < 0.05
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
        >
          {currentLabel} ›
        </button>
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
      ? "bg-red-500/15 text-red-400 border-red-500/30"
      : variant === "follow"
      ? "bg-accent-brand/15 text-accent-brand border-accent-brand/30"
      : "bg-surface-elevated text-text-primary border-surface-border";

  return (
    <span
      className={`inline-flex items-center gap-1 ${colorClasses} px-2 py-0.5 rounded-lg text-[11px] font-medium border transition-opacity ${
        removing ? "opacity-50" : ""
      }`}
    >
      {team.logo_url && (
        <img src={team.logo_url} alt="" className="w-3.5 h-3.5 object-contain" />
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
