"use client";

import { useMemo } from "react";
import type { Sport } from "@/lib/types";
import {
  SPORT_CATEGORIES,
  getLeagueDisplay,
  getCategoryForLeague,
  getActiveCategoriesFromLeagues,
} from "@/lib/sportCategories";

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
 * Horizontally scrolling on mobile.
 */
export default function SportFilter({
  sports,
  selectedSport,
  selectedCategory,
  onSelectSport,
  onSelectCategory,
  loading = false,
}: SportFilterProps) {
  const allLeagueKeys = useMemo(() => sports.map((s) => s.key), [sports]);

  const availableCategories = useMemo(() => {
    return getActiveCategoriesFromLeagues(allLeagueKeys);
  }, [allLeagueKeys]);

  const availableLeagues = useMemo(() => {
    if (!selectedCategory) return [];

    const category = SPORT_CATEGORIES.find((c) => c.key === selectedCategory);
    if (category) {
      return allLeagueKeys.filter((leagueKey) =>
        category.prefixes.some((prefix) => leagueKey.startsWith(prefix))
      );
    } else if (selectedCategory === "other") {
      return allLeagueKeys.filter((leagueKey) => !getCategoryForLeague(leagueKey));
    }
    return [];
  }, [selectedCategory, allLeagueKeys]);

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

  const handleCategoryClick = (categoryKey: string | null) => {
    if (categoryKey === selectedCategory) {
      onSelectCategory(null);
      onSelectSport(null);
    } else {
      onSelectCategory(categoryKey);
      onSelectSport(null);
    }
  };

  const handleLeagueClick = (leagueKey: string) => {
    if (leagueKey === selectedSport) {
      onSelectSport(null);
    } else {
      onSelectSport(leagueKey);
    }
  };

  // Map category keys to display with emoji
  const getCategoryDisplay = (key: string, emoji: string): { label: string; emoji: string } => {
    const labels: Record<string, string> = {
      football: "Football",
      basketball: "Basketball",
      baseball: "Baseball",
      hockey: "Hockey",
      mma: "MMA",
      boxing: "Boxing",
      golf: "Golf",
      tennis: "Tennis",
      cricket: "Cricket",
      rugby: "Rugby",
      aussierules: "AFL",
      politics: "Politics",
      esports: "Esports",
      lacrosse: "Lacrosse",
      motorsport: "Racing",
      other: "Other",
    };
    return { label: labels[key] || key, emoji };
  };

  return (
    <div className="space-y-3">
      {/* Category pills */}
      <div className="flex gap-2 overflow-x-auto pb-1 scrollbar-hide">
        {/* All button */}
        <button
          onClick={() => handleCategoryClick(null)}
          className={`px-4 py-2 rounded-full text-sm font-medium whitespace-nowrap transition-all flex-shrink-0 flex items-center gap-1.5 ${
            selectedCategory === null
              ? "bg-graphite text-white shadow-sm"
              : "bg-white text-slate border border-mist hover:bg-mist/50 hover:border-slate/30"
          }`}
        >
          🏆 All Sports
        </button>

        {/* Category buttons */}
        {availableCategories.map((category) => {
          const display = getCategoryDisplay(category.key, category.emoji);
          return (
            <button
              key={category.key}
              onClick={() => handleCategoryClick(category.key)}
              className={`px-4 py-2 rounded-full text-sm font-medium whitespace-nowrap transition-all flex-shrink-0 flex items-center gap-1.5 ${
                selectedCategory === category.key
                  ? "bg-graphite text-white shadow-sm"
                  : "bg-white text-slate border border-mist hover:bg-mist/50 hover:border-slate/30"
              }`}
            >
              <span>{display.emoji}</span>
              <span>{display.label}</span>
            </button>
          );
        })}
      </div>

      {/* League sub-filter */}
      {selectedCategory && availableLeagues.length > 1 && (
        <div className="flex gap-2 overflow-x-auto pb-1 scrollbar-hide">
          <button
            onClick={() => onSelectSport(null)}
            className={`px-3 py-1.5 rounded-full text-xs whitespace-nowrap transition-colors flex-shrink-0 ${
              selectedSport === null
                ? "bg-slate text-white"
                : "bg-slate/10 text-slate hover:bg-slate/20"
            }`}
          >
            All Leagues
          </button>

          {availableLeagues.map((leagueKey) => (
            <button
              key={leagueKey}
              onClick={() => handleLeagueClick(leagueKey)}
              className={`px-3 py-1.5 rounded-full text-xs whitespace-nowrap transition-colors flex-shrink-0 ${
                selectedSport === leagueKey
                  ? "bg-slate text-white"
                  : "bg-slate/10 text-slate hover:bg-slate/20"
              }`}
            >
              {getLeagueDisplay(leagueKey)}
            </button>
          ))}
        </div>
      )}
    </div>
  );
}
