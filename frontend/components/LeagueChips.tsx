"use client";

import Link from "next/link";
import { useRef } from "react";

interface LeagueChip {
  slug: string;
  label: string;
  emoji: string;
}

const LEAGUE_CHIPS: LeagueChip[] = [
  { slug: "nba", label: "NBA", emoji: "\u{1F3C0}" },
  { slug: "nfl", label: "NFL", emoji: "\u{1F3C8}" },
  { slug: "mlb", label: "MLB", emoji: "\u26BE" },
  { slug: "nhl", label: "NHL", emoji: "\u{1F3D2}" },
  { slug: "ncaa-basketball", label: "NCAAB", emoji: "\u{1F3C0}" },
  { slug: "ncaa-football", label: "NCAAF", emoji: "\u{1F3C8}" },
  { slug: "epl", label: "EPL", emoji: "\u26BD" },
  { slug: "champions-league", label: "UCL", emoji: "\u26BD" },
  { slug: "la-liga", label: "La Liga", emoji: "\u26BD" },
  { slug: "bundesliga", label: "Bundesliga", emoji: "\u26BD" },
  { slug: "mls", label: "MLS", emoji: "\u26BD" },
  { slug: "wnba", label: "WNBA", emoji: "\u{1F3C0}" },
  { slug: "golf", label: "Golf", emoji: "\u26F3" },
];

interface LeagueChipsProps {
  /** Optional: highlight a specific league slug as active */
  activeSlug?: string;
}

export default function LeagueChips({ activeSlug }: LeagueChipsProps) {
  const scrollRef = useRef<HTMLDivElement>(null);

  return (
    <div
      ref={scrollRef}
      className="flex gap-2 overflow-x-auto pb-1 scrollbar-hide -mx-1 px-1"
    >
      {LEAGUE_CHIPS.map((chip) => {
        const isActive = activeSlug === chip.slug;

        return (
          <Link
            key={chip.slug}
            href={chip.slug === "golf" ? `/categories/golf` : `/playoffs/${chip.slug}`}
            className={`
              flex items-center gap-1.5 px-3 py-1.5 rounded-full text-xs font-medium
              whitespace-nowrap transition-colors shrink-0
              ${
                isActive
                  ? "bg-text-primary text-surface-deep"
                  : "bg-surface-elevated text-text-secondary hover:bg-surface-border"
              }
            `}
          >
            <span className="text-sm leading-none">{chip.emoji}</span>
            {chip.label}
          </Link>
        );
      })}
    </div>
  );
}
