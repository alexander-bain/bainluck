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
 * Filter pills for sports - text only, no emojis per design brief.
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
            className="h-9 w-16 bg-mist rounded-full animate-pulse flex-shrink-0"
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

  // Map category keys to display abbreviations
  const getCategoryLabel = (key: string): string => {
    const labels: Record<string, string> = {
      football: "NFL",
      basketball: "NBA",
      baseball: "MLB",
      hockey: "NHL",
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
    return labels[key] || key;
  };

  return (
    <div className="space-y-3">
      {/* Category pills */}
      <div className="flex gap-2 overflow-x-auto pb-1 scrollbar-hide">
        {/* All button */}
        <button
          onClick={() => handleCategoryClick(null)}
          className={`px-4 py-2 rounded-full text-caption font-medium whitespace-nowrap transition-all flex-shrink-0 ${
            selectedCategory === null
              ? "bg-ink text-white"
              : "bg-transparent text-slate border border-mist hover:bg-mist/50"
          }`}
        >
          All
        </button>

        {/* Category buttons */}
        {availableCategories.map((category) => (
          <button
            key={category.key}
            onClick={() => handleCategoryClick(category.key)}
            className={`px-4 py-2 rounded-full text-caption font-medium whitespace-nowrap transition-all flex-shrink-0 ${
              selectedCategory === category.key
                ? "bg-ink text-white"
                : "bg-transparent text-slate border border-mist hover:bg-mist/50"
            }`}
          >
            {getCategoryLabel(category.key)}
          </button>
        ))}
      </div>

      {/* League sub-filter */}
      {selectedCategory && availableLeagues.length > 1 && (
        <div className="flex gap-2 overflow-x-auto pb-1 scrollbar-hide">
          <button
            onClick={() => onSelectSport(null)}
            className={`px-3 py-1.5 rounded-full text-micro whitespace-nowrap transition-colors ${
              selectedSport === null
                ? "bg-charcoal text-white"
                : "bg-mist text-slate hover:bg-fog"
            }`}
          >
            All
          </button>

          {availableLeagues.map((leagueKey) => (
            <button
              key={leagueKey}
              onClick={() => handleLeagueClick(leagueKey)}
              className={`px-3 py-1.5 rounded-full text-micro whitespace-nowrap transition-colors ${
                selectedSport === leagueKey
                  ? "bg-charcoal text-white"
                  : "bg-mist text-slate hover:bg-fog"
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
