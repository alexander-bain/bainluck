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

  const primaryCategories = useMemo(() => {
    return availableCategories.filter((c) => c.tier === 1);
  }, [availableCategories]);

  const secondaryCategories = useMemo(() => {
    return availableCategories.filter((c) => c.tier !== 1);
  }, [availableCategories]);

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

    return leagues.sort((a, b) => getLeagueTier(a) - getLeagueTier(b));
  }, [selectedCategory, allLeagueKeys]);

  const handleCategoryClick = useCallback((categoryKey: string | null) => {
    const isDeselecting = categoryKey === selectedCategory;
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
            className="h-8 w-20 bg-surface-elevated rounded-full animate-pulse flex-shrink-0"
          />
        ))}
      </div>
    );
  }

  const getCategoryDisplay = (key: string, emoji: string): { label: string; emoji: string } => {
    return { label: getNameForCategory(key), emoji };
  };

  return (
    <div className="space-y-2">
      {/* Primary category pills */}
      <div className="flex flex-wrap gap-1.5">
        {/* All button */}
        <button
          onClick={() => handleCategoryClick(null)}
          className={`px-3 py-1.5 rounded-full text-sm font-medium whitespace-nowrap transition-all flex items-center gap-1.5 ${
            selectedCategory === null
              ? "bg-text-primary text-surface-deep"
              : "bg-surface-elevated text-text-secondary hover:text-text-primary"
          }`}
        >
          All
        </button>

        {primaryCategories.map((category) => {
          const display = getCategoryDisplay(category.key, category.emoji);
          return (
            <button
              key={category.key}
              onClick={() => handleCategoryClick(category.key)}
              className={`px-3 py-1.5 rounded-full text-sm font-medium whitespace-nowrap transition-all flex items-center gap-1.5 ${
                selectedCategory === category.key
                  ? "bg-text-primary text-surface-deep"
                  : "bg-surface-elevated text-text-secondary hover:text-text-primary"
              }`}
            >
              <span className="text-sm">{display.emoji}</span>
              <span>{display.label}</span>
            </button>
          );
        })}

        {secondaryCategories.length > 0 && (
          <button
            onClick={handleMoreSportsToggle}
            className={`px-3 py-1.5 rounded-full text-xs font-medium whitespace-nowrap transition-all flex items-center gap-1 ${
              showMoreSports || secondaryCategories.some((c) => c.key === selectedCategory)
                ? "bg-surface-elevated text-text-primary"
                : "bg-surface-elevated/50 text-text-muted hover:text-text-secondary"
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

      {/* Secondary sports */}
      {(showMoreSports || secondaryCategories.some((c) => c.key === selectedCategory)) &&
        secondaryCategories.length > 0 && (
          <div className="flex flex-wrap gap-1.5">
            {secondaryCategories.map((category) => {
              const display = getCategoryDisplay(category.key, category.emoji);
              return (
                <button
                  key={category.key}
                  onClick={() => handleCategoryClick(category.key)}
                  className={`px-2.5 py-1 rounded-full text-xs font-medium whitespace-nowrap transition-all flex items-center gap-1 ${
                    selectedCategory === category.key
                      ? "bg-text-primary text-surface-deep"
                      : "bg-surface-elevated/50 text-text-muted hover:text-text-secondary"
                  }`}
                >
                  <span>{display.emoji}</span>
                  <span>{display.label}</span>
                </button>
              );
            })}
          </div>
        )}

      {/* League sub-filter */}
      {selectedCategory && availableLeagues.length > 1 && (
        <div className="flex flex-wrap gap-1.5 pt-1.5 border-t border-surface-border/50">
          <span className="text-[10px] text-text-muted self-center mr-1 uppercase tracking-wider">Leagues</span>
          <button
            onClick={() => onSelectSport(null)}
            className={`px-2.5 py-1 rounded text-xs whitespace-nowrap transition-colors ${
              selectedSport === null
                ? "bg-text-primary text-surface-deep"
                : "bg-surface-elevated text-text-secondary hover:text-text-primary"
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
                    ? "bg-text-primary text-surface-deep"
                    : tier === 1
                    ? "bg-surface-elevated text-text-primary font-medium"
                    : tier === 2
                    ? "bg-surface-elevated text-text-secondary"
                    : "bg-surface-elevated/50 text-text-muted"
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
