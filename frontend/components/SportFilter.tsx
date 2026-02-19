"use client";

import { useMemo, useState, useCallback } from "react";
import type { Sport } from "@/lib/types";
import {
  SPORT_CATEGORIES,
  getLeagueDisplay,
  getCategoryForLeague,
  getActiveCategoriesFromLeagues,
  getLeagueTier,
  getNameForCategory,
} from "@/lib/sportCategories";
import { useAnalytics } from "@/hooks";

interface SportFilterProps {
  sports: Sport[];
  selectedSport: string | null;
  selectedCategory: string | null;
  onSelectSport: (sportKey: string | null) => void;
  onSelectCategory: (categoryKey: string | null) => void;
  loading?: boolean;
}

/**
 * Filter pills for sports with emoji.
 * Hierarchical design with primary sports (Football, Basketball, Baseball) prominent.
 */
export default function SportFilter({
  sports,
  selectedSport,
  selectedCategory,
  onSelectSport,
  onSelectCategory,
  loading = false,
}: SportFilterProps) {
  const [showMoreSports, setShowMoreSports] = useState(false);
  const allLeagueKeys = useMemo(() => sports.map((s) => s.key), [sports]);
  const { trackCategoryFilter, trackLeagueFilter, trackMoreSportsToggle } = useAnalytics();

  const availableCategories = useMemo(() => {
    return getActiveCategoriesFromLeagues(allLeagueKeys);
  }, [allLeagueKeys]);

  // Split categories into primary (tier 1) and secondary/tertiary
  const primaryCategories = useMemo(() => {
    return availableCategories.filter((c) => c.tier === 1);
  }, [availableCategories]);

  const secondaryCategories = useMemo(() => {
    return availableCategories.filter((c) => c.tier !== 1);
  }, [availableCategories]);

  // Sort leagues by tier (major leagues first)
  const availableLeagues = useMemo(() => {
    if (!selectedCategory) return [];

    const category = SPORT_CATEGORIES.find((c) => c.key === selectedCategory);
    let leagues: string[];
    if (category) {
      leagues = allLeagueKeys.filter((leagueKey) =>
        category.prefixes.some((prefix) => leagueKey.startsWith(prefix))
      );
    } else if (selectedCategory === "other") {
      leagues = allLeagueKeys.filter((leagueKey) => !getCategoryForLeague(leagueKey));
    } else {
      leagues = [];
    }

    // Sort by tier (major leagues first)
    return leagues.sort((a, b) => getLeagueTier(a) - getLeagueTier(b));
  }, [selectedCategory, allLeagueKeys]);

  // Must define all hooks before any conditional returns
  const handleCategoryClick = useCallback((categoryKey: string | null) => {
    const isDeselecting = categoryKey === selectedCategory;

    // Track analytics
    trackCategoryFilter(
      isDeselecting ? null : categoryKey,
      isDeselecting ? 'deselect' : 'select',
      selectedCategory
    );

    if (isDeselecting) {
      onSelectCategory(null);
      onSelectSport(null);
    } else {
      onSelectCategory(categoryKey);
      onSelectSport(null);
    }
  }, [selectedCategory, onSelectCategory, onSelectSport, trackCategoryFilter]);

  const handleLeagueClick = useCallback((leagueKey: string) => {
    const isDeselecting = leagueKey === selectedSport;

    // Track analytics
    trackLeagueFilter(
      isDeselecting ? null : leagueKey,
      isDeselecting ? 'deselect' : 'select',
      selectedCategory || 'unknown',
      selectedSport
    );

    if (isDeselecting) {
      onSelectSport(null);
    } else {
      onSelectSport(leagueKey);
    }
  }, [selectedSport, selectedCategory, onSelectSport, trackLeagueFilter]);

  const handleMoreSportsToggle = useCallback(() => {
    const newExpanded = !showMoreSports;
    const visibleCategories = newExpanded
      ? [...primaryCategories, ...secondaryCategories].map(c => c.key)
      : primaryCategories.map(c => c.key);

    trackMoreSportsToggle(newExpanded, visibleCategories);
    setShowMoreSports(newExpanded);
  }, [showMoreSports, primaryCategories, secondaryCategories, trackMoreSportsToggle]);

  if (loading) {
    return (
      <div className="flex gap-2 overflow-x-auto pb-2 scrollbar-hide">
        {[1, 2, 3, 4, 5, 6].map((i) => (
          <div
            key={i}
            className="h-9 w-20 bg-mist rounded-full animate-pulse flex-shrink-0"
          />
        ))}
      </div>
    );
  }

  // Map category keys to display with emoji — uses central SPORT_CATEGORIES
  const getCategoryDisplay = (key: string, emoji: string): { label: string; emoji: string } => {
    return { label: getNameForCategory(key), emoji };
  };

  return (
    <div className="space-y-3">
      {/* Primary category pills - prominent display */}
      <div className="flex flex-wrap gap-2">
        {/* All button */}
        <button
          onClick={() => handleCategoryClick(null)}
          className={`px-4 py-2 rounded-full text-sm font-medium whitespace-nowrap transition-all flex items-center gap-1.5 ${
            selectedCategory === null
              ? "bg-graphite text-white shadow-sm"
              : "bg-white text-slate border border-mist hover:bg-mist/50 hover:border-slate/30"
          }`}
        >
          🏆 All
        </button>

        {/* Primary sports (Football, Basketball, Baseball) - larger, more prominent */}
        {primaryCategories.map((category) => {
          const display = getCategoryDisplay(category.key, category.emoji);
          return (
            <button
              key={category.key}
              onClick={() => handleCategoryClick(category.key)}
              className={`px-4 py-2 rounded-full text-sm font-semibold whitespace-nowrap transition-all flex items-center gap-1.5 ${
                selectedCategory === category.key
                  ? "bg-graphite text-white shadow-sm"
                  : "bg-white text-graphite border-2 border-graphite/20 hover:border-graphite/40 hover:bg-mist/30"
              }`}
            >
              <span className="text-base">{display.emoji}</span>
              <span>{display.label}</span>
            </button>
          );
        })}

        {/* More Sports toggle - only show if there are secondary categories */}
        {secondaryCategories.length > 0 && (
          <button
            onClick={handleMoreSportsToggle}
            className={`px-3 py-2 rounded-full text-xs font-medium whitespace-nowrap transition-all flex items-center gap-1 ${
              showMoreSports || secondaryCategories.some((c) => c.key === selectedCategory)
                ? "bg-slate/20 text-graphite"
                : "bg-slate/10 text-slate hover:bg-slate/20"
            }`}
          >
            <span>{showMoreSports ? "Less" : "More"}</span>
            <svg
              className={`w-3 h-3 transition-transform ${showMoreSports ? "rotate-180" : ""}`}
              fill="none"
              stroke="currentColor"
              viewBox="0 0 24 24"
            >
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 9l-7 7-7-7" />
            </svg>
          </button>
        )}
      </div>

      {/* Secondary sports - shown when expanded or when one is selected */}
      {(showMoreSports || secondaryCategories.some((c) => c.key === selectedCategory)) &&
        secondaryCategories.length > 0 && (
          <div className="flex flex-wrap gap-1.5 pt-1">
            {secondaryCategories.map((category) => {
              const display = getCategoryDisplay(category.key, category.emoji);
              return (
                <button
                  key={category.key}
                  onClick={() => handleCategoryClick(category.key)}
                  className={`px-3 py-1.5 rounded-full text-xs font-medium whitespace-nowrap transition-all flex items-center gap-1 ${
                    selectedCategory === category.key
                      ? "bg-slate text-white"
                      : "bg-slate/10 text-slate hover:bg-slate/20"
                  }`}
                >
                  <span>{display.emoji}</span>
                  <span>{display.label}</span>
                </button>
              );
            })}
          </div>
        )}

      {/* League sub-filter - sorted by tier */}
      {selectedCategory && availableLeagues.length > 1 && (
        <div className="flex flex-wrap gap-1.5 pt-1 border-t border-mist/50">
          <span className="text-xs text-silver self-center mr-1">Leagues:</span>
          <button
            onClick={() => onSelectSport(null)}
            className={`px-2.5 py-1 rounded text-xs whitespace-nowrap transition-colors ${
              selectedSport === null
                ? "bg-graphite text-white"
                : "bg-white text-slate border border-mist hover:bg-mist/50"
            }`}
          >
            All
          </button>

          {availableLeagues.map((leagueKey) => {
            const tier = getLeagueTier(leagueKey);
            return (
              <button
                key={leagueKey}
                onClick={() => handleLeagueClick(leagueKey)}
                className={`px-2.5 py-1 rounded text-xs whitespace-nowrap transition-colors ${
                  selectedSport === leagueKey
                    ? "bg-graphite text-white"
                    : tier === 1
                    ? "bg-white text-graphite border border-graphite/30 font-medium hover:bg-mist/50"
                    : tier === 2
                    ? "bg-white text-slate border border-mist hover:bg-mist/50"
                    : "bg-slate/5 text-silver border border-transparent hover:bg-slate/10"
                }`}
              >
                {getLeagueDisplay(leagueKey)}
              </button>
            );
          })}
        </div>
      )}
    </div>
  );
}
