import type { Metadata } from "next";

export const metadata: Metadata = {
  title: "Sports Odds",
  description:
    "Live game probabilities from 20+ sportsbooks, Kalshi, Polymarket, ESPN, and stat models — translated into simple percentages.",
  alternates: { canonical: "/sports" },
  openGraph: {
    title: "Sports Odds — Bain Luck",
    description:
      "Live game probabilities from 20+ sportsbooks, Kalshi, Polymarket, ESPN, and stat models.",
    url: "https://bainluck.com/sports",
  },
};

export default function SportsLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return <>{children}</>;
}
