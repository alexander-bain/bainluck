"use client";

import Link from "next/link";
import { useRef } from "react";

interface LeagueChip {
  slug: string;
  label: string;
  emoji: string;
}

const LEAGUE_CHIPS: (LeagueChip & { path: string })[] = [
  { slug: "nba", label: "NBA", emoji: "\u{1F3C0}", path: "/sport/basketball/nba" },
  { slug: "nfl", label: "NFL", emoji: "\u{1F3C8}", path: "/sport/football/nfl" },
  { slug: "mlb", label: "MLB", emoji: "\u26BE", path: "/sport/baseball/mlb" },
  { slug: "nhl", label: "NHL", emoji: "\u{1F3D2}", path: "/sport/hockey/nhl" },
  { slug: "ncaa-basketball", label: "NCAAB", emoji: "\u{1F3C0}", path: "/sport/basketball/ncaab" },
  { slug: "ncaa-football", label: "NCAAF", emoji: "\u{1F3C8}", path: "/sport/football/ncaaf" },
  { slug: "epl", label: "EPL", emoji: "\u26BD", path: "/sport/soccer/epl" },
  { slug: "champions-league", label: "UCL", emoji: "\u26BD", path: "/sport/soccer/ucl" },
  { slug: "la-liga", label: "La Liga", emoji: "\u26BD", path: "/sport/soccer/laliga" },
  { slug: "bundesliga", label: "Bundesliga", emoji: "\u26BD", path: "/sport/soccer/bundesliga" },
  { slug: "mls", label: "MLS", emoji: "\u26BD", path: "/sport/soccer/mls" },
  { slug: "wnba", label: "WNBA", emoji: "\u{1F3C0}", path: "/sport/basketball/wnba" },
  { slug: "golf", label: "Golf", emoji: "\u26F3", path: "/categories/golf" },
];

interface LeagueChipsProps {
  /** Optional: highlight a specific league slug as active */
  activeSlug?: string;
}

export default function LeagueChips({ activeSlug }: LeagueChipsProps) {
  const scrollRef = useRef<HTMLDivElement>(null);

  return (
    <nav
      ref={scrollRef}
      className="flex gap-2 overflow-x-auto pb-1 scrollbar-hide -mx-1 px-1"
      aria-label="League navigation"
    >
      {LEAGUE_CHIPS.map((chip) => {
        const isActive = activeSlug === chip.slug;

        return (
          <Link
            key={chip.slug}
            href={chip.path}
            aria-current={isActive ? "page" : undefined}
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
    </nav>
  );
}
