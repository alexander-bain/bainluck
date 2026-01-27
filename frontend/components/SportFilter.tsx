"use client";

import type { Sport } from "@/lib/types";

interface SportFilterProps {
  sports: Sport[];
  selectedSport: string | null;
  onSelectSport: (sportKey: string | null) => void;
  loading?: boolean;
}

/**
 * Filter component for selecting a sport.
 */
export default function SportFilter({
  sports,
  selectedSport,
  onSelectSport,
  loading = false,
}: SportFilterProps) {
  if (loading) {
    return (
      <div className="flex gap-2 overflow-x-auto pb-2">
        {[1, 2, 3, 4].map((i) => (
          <div
            key={i}
            className="h-8 w-20 bg-gray-200 rounded-full animate-pulse"
          />
        ))}
      </div>
    );
  }

  return (
    <div className="flex gap-2 overflow-x-auto pb-2 scrollbar-hide">
      {/* All Sports button */}
      <button
        onClick={() => onSelectSport(null)}
        className={`px-4 py-1.5 rounded-full text-sm font-medium whitespace-nowrap transition-colors ${
          selectedSport === null
            ? "bg-gray-900 text-white"
            : "bg-gray-100 text-gray-700 hover:bg-gray-200"
        }`}
      >
        All Sports
      </button>

      {/* Individual sport buttons */}
      {sports.map((sport) => (
        <button
          key={sport.key}
          onClick={() => onSelectSport(sport.key)}
          className={`px-4 py-1.5 rounded-full text-sm font-medium whitespace-nowrap transition-colors ${
            selectedSport === sport.key
              ? "bg-gray-900 text-white"
              : "bg-gray-100 text-gray-700 hover:bg-gray-200"
          }`}
        >
          {sport.name}
        </button>
      ))}
    </div>
  );
}
