"use client";

import Link from "next/link";
import {
  usePageTracking,
  useScrollDepth,
  useEngagementTime,
} from "@/hooks";

interface LeagueCard {
  slug: string;
  label: string;
  fullName: string;
  emoji: string;
  group: string;
}

const LEAGUES: LeagueCard[] = [
  { slug: "nba", label: "NBA", fullName: "National Basketball Association", emoji: "\u{1F3C0}", group: "Major US Leagues" },
  { slug: "nfl", label: "NFL", fullName: "National Football League", emoji: "\u{1F3C8}", group: "Major US Leagues" },
  { slug: "mlb", label: "MLB", fullName: "Major League Baseball", emoji: "\u26BE", group: "Major US Leagues" },
  { slug: "nhl", label: "NHL", fullName: "National Hockey League", emoji: "\u{1F3D2}", group: "Major US Leagues" },
  { slug: "ncaa-basketball", label: "NCAAB", fullName: "NCAA Men's Basketball", emoji: "\u{1F3C0}", group: "College" },
  { slug: "ncaa-women-basketball", label: "WNCAAB", fullName: "NCAA Women's Basketball", emoji: "\u{1F3C0}", group: "College" },
  { slug: "ncaa-football", label: "NCAAF", fullName: "NCAA Football", emoji: "\u{1F3C8}", group: "College" },
  { slug: "wnba", label: "WNBA", fullName: "Women's NBA", emoji: "\u{1F3C0}", group: "Other US Leagues" },
  { slug: "mls", label: "MLS", fullName: "Major League Soccer", emoji: "\u26BD", group: "Other US Leagues" },
  { slug: "epl", label: "EPL", fullName: "English Premier League", emoji: "\u26BD", group: "Soccer" },
  { slug: "la-liga", label: "La Liga", fullName: "Spanish La Liga", emoji: "\u26BD", group: "Soccer" },
  { slug: "champions-league", label: "UCL", fullName: "UEFA Champions League", emoji: "\u26BD", group: "Soccer" },
  { slug: "bundesliga", label: "Bundesliga", fullName: "German Bundesliga", emoji: "\u26BD", group: "Soccer" },
  { slug: "golf", label: "Golf", fullName: "PGA Tour & Majors", emoji: "\u26F3", group: "Individual" },
];

const GROUPS = ["Major US Leagues", "College", "Other US Leagues", "Soccer", "Individual"];

export default function LeaguesIndexPage() {
  usePageTracking({ pageType: "leagues_index", pageTitle: "Championship Grids" });
  useScrollDepth({ pageType: "leagues_index" });
  useEngagementTime({ pageType: "leagues_index" });

  return (
    <div className="space-y-8">
      <div>
        <h1 className="text-xl font-bold text-text-primary">
          Championship Grids
        </h1>
        <p className="text-sm text-text-secondary mt-1">
          Title odds across every stage — from regular season to championship
        </p>
      </div>

      {GROUPS.map((group) => {
        const leagues = LEAGUES.filter((l) => l.group === group);
        if (leagues.length === 0) return null;

        return (
          <section key={group}>
            <h2 className="text-xs font-semibold text-text-muted uppercase tracking-wider mb-3">
              {group}
            </h2>
            <div className="grid gap-3 grid-cols-2 sm:grid-cols-3 md:grid-cols-4">
              {leagues.map((league) => (
                <Link
                  key={league.slug}
                  href={`/playoffs/${league.slug}`}
                  className="flex items-center gap-3 p-4 rounded-xl bg-surface-card border border-surface-border hover:border-text-muted/30 transition-colors group"
                >
                  <span className="text-2xl">{league.emoji}</span>
                  <div className="min-w-0">
                    <div className="text-sm font-semibold text-text-primary group-hover:text-accent-brand transition-colors">
                      {league.label}
                    </div>
                    <div className="text-[11px] text-text-muted truncate">
                      {league.fullName}
                    </div>
                  </div>
                </Link>
              ))}
            </div>
          </section>
        );
      })}
    </div>
  );
}
