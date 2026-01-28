"use client";

import { useState, useMemo } from "react";
import type { Sport } from "@/lib/types";
import {
  SPORT_CATEGORIES,
  getLeagueDisplay,
  getCategoryForLeague,
  getActiveCategoriesFromLeagues,
  type SportCategory,
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
 * Two-level sport filter: categories with emojis, then leagues.
 * Uses prefix-based matching to categorize sports dynamically.
 */
export default function SportFilter({
  sports,
  selectedSport,
  selectedCategory,
  onSelectSport,
  onSelectCategory,
  loading = false,
}: SportFilterProps) {
  // Get all league keys
  const allLeagueKeys = useMemo(() => sports.map((s) => s.key), [sports]);

  // Get available categories based on which sports we have
  const availableCategories = useMemo(() => {
    return getActiveCategoriesFromLeagues(allLeagueKeys);
  }, [allLeagueKeys]);

  // Get leagues for the selected category using prefix matching
  const availableLeagues = useMemo(() => {
    if (!selectedCategory) return [];

    const category = SPORT_CATEGORIES.find((c) => c.key === selectedCategory);
    if (category) {
      // Filter leagues that match this category's prefixes
      return allLeagueKeys.filter((leagueKey) =>
        category.prefixes.some((prefix) => leagueKey.startsWith(prefix))
      );
    } else if (selectedCategory === "other") {
      // "Other" category - sports that don't match any known prefix
      return allLeagueKeys.filter((leagueKey) => !getCategoryForLeague(leagueKey));
    }
    return [];
  }, [selectedCategory, allLeagueKeys]);

  // Get the selected category data
  const selectedCategoryData = useMemo(() => {
    if (!selectedCategory) return null;
    if (selectedCategory === "other") {
      return { key: "other", name: "Other", emoji: "🏆", prefixes: [] };
    }
    return SPORT_CATEGORIES.find((c) => c.key === selectedCategory) || null;
  }, [selectedCategory]);

  if (loading) {
    return (
      <div className="space-y-2">
        <div className="flex gap-2 overflow-x-auto pb-2">
          {[1, 2, 3, 4, 5].map((i) => (
            <div
              key={i}
              className="h-10 w-16 bg-gray-200 rounded-lg animate-pulse flex-shrink-0"
            />
          ))}
        </div>
      </div>
    );
  }

  const handleCategoryClick = (categoryKey: string | null) => {
    if (categoryKey === selectedCategory) {
      // Clicking same category again deselects it
      onSelectCategory(null);
      onSelectSport(null);
    } else {
      onSelectCategory(categoryKey);
      onSelectSport(null); // Reset league selection when changing category
    }
  };

  const handleLeagueClick = (leagueKey: string) => {
    if (leagueKey === selectedSport) {
      // Clicking same league deselects it (show all in category)
      onSelectSport(null);
    } else {
      onSelectSport(leagueKey);
    }
  };

  return (
    <div className="space-y-3">
      {/* Category buttons */}
      <div className="flex gap-2 overflow-x-auto pb-1 scrollbar-hide">
        {/* All Sports button */}
        <button
          onClick={() => handleCategoryClick(null)}
          className={`flex flex-col items-center justify-center px-4 py-2 rounded-lg text-sm font-medium whitespace-nowrap transition-all flex-shrink-0 min-w-[60px] ${
            selectedCategory === null
              ? "bg-gray-900 text-white shadow-md"
              : "bg-gray-100 text-gray-700 hover:bg-gray-200"
          }`}
        >
          <span className="text-lg mb-0.5">🏆</span>
          <span className="text-xs">All</span>
        </button>

        {/* Category buttons */}
        {availableCategories.map((category) => (
          <button
            key={category.key}
            onClick={() => handleCategoryClick(category.key)}
            className={`flex flex-col items-center justify-center px-4 py-2 rounded-lg text-sm font-medium whitespace-nowrap transition-all flex-shrink-0 min-w-[60px] ${
              selectedCategory === category.key
                ? "bg-gray-900 text-white shadow-md"
                : "bg-gray-100 text-gray-700 hover:bg-gray-200"
            }`}
          >
            <span className="text-lg mb-0.5">{category.emoji}</span>
            <span className="text-xs">{category.name}</span>
          </button>
        ))}
      </div>

      {/* League sub-filter (only show if category is selected and has multiple leagues) */}
      {selectedCategory && availableLeagues.length > 1 && (
        <div className="flex gap-2 overflow-x-auto pb-1 scrollbar-hide pl-2">
          <span className="text-xs text-gray-400 self-center mr-1">League:</span>

          {/* All leagues in category */}
          <button
            onClick={() => onSelectSport(null)}
            className={`px-3 py-1 rounded-full text-xs font-medium whitespace-nowrap transition-colors ${
              selectedSport === null
                ? "bg-gray-700 text-white"
                : "bg-gray-200 text-gray-600 hover:bg-gray-300"
            }`}
          >
            All {selectedCategoryData?.name}
          </button>

          {/* Individual league buttons */}
          {availableLeagues.map((leagueKey) => (
            <button
              key={leagueKey}
              onClick={() => handleLeagueClick(leagueKey)}
              className={`px-3 py-1 rounded-full text-xs font-medium whitespace-nowrap transition-colors ${
                selectedSport === leagueKey
                  ? "bg-gray-700 text-white"
                  : "bg-gray-200 text-gray-600 hover:bg-gray-300"
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
