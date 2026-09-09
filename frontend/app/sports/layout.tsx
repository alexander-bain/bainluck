import type { Metadata } from "next";

import { defaultShareCard } from "@/lib/shareCard";

export const metadata: Metadata = {
  title: "Sports Odds",
  description:
    "Live game probabilities from 20+ sportsbooks, Kalshi, Polymarket, ESPN, and stat models — translated into simple percentages.",
  alternates: { canonical: "/sports" },
  openGraph: {
    title: "Sports Odds — Bain Luck",
    description:
      "Live game probabilities from 20+ sportsbooks, Kalshi, Polymarket, ESPN, and stat models.",
    url: "/sports",
    // LAT-P278: explicit, not inherited. `/discover/stats` proved the
    // root card does not reliably reach a route that declares its own
    // `openGraph` — see `lib/shareCard.ts`.
    images: defaultShareCard(),
  },
};

export default function SportsLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return <>{children}</>;
}
