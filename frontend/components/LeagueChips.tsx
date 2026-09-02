"use client";

import Link from "next/link";
import { useRef } from "react";

interface LeagueChip {
  slug: string;
  label: string;
  emoji: string;
}

/**
 * THE FILTER ROW HAS TO CONTAIN THE SPORT THE SITE IS TRADING ON (#2560).
 *
 * On 2026-09-01, day two of the US Open, this row read NBA · NFL · MLB · NHL ·
 * NCAAB · NCAAF · EPL · UCL · La Liga · Bundesliga · MLS · WNBA · Golf — and
 * the page under it was three-quarters tennis: all 20 of its prop cards were US
 * Open advance-to-round markets. The one sport a visitor was most likely to be
 * here for was the one sport they could not filter to, in the first 40px of the
 * browse surface.
 *
 * `/sport/tennis` and NOT `/tournaments/us-open`. The hub is where the chip
 * SHOULD land during a slam and it is one click on from here — the Grand Slam
 * tile on that page routes straight to it (see `app/sport/[sport]/page.tsx`).
 * But a chips array is a deploy, and a tournament is two weeks: hard-coding
 * `us-open` here buys three good days and then points the tennis chip at a
 * finished tournament until somebody notices. UX-P145 shipped that exact class
 * of bug on this same tournament — a weekday hard-coded in a component, live
 * and wrong the same afternoon — and the fix was to make being right a data
 * property. `/sport/tennis` is the durable address: it lists the tours and the
 * slams, and which slam is on is a data question it already answers.
 */
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
  { slug: "tennis", label: "Tennis", emoji: "\u{1F3BE}", path: "/sport/tennis" },
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
