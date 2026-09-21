import type { Metadata } from "next";

import { defaultShareCard } from "@/lib/shareCard";

export const metadata: Metadata = {
  // #7738. The tab and share titles move with the footer label: they are the
  // only other place the word "Calibration" reached a reader, and a reader who
  // clicks "Accuracy" should not be told by the tab that they arrived somewhere
  // else. The route, the canonical and the sitemap entry are unchanged, and the
  // descriptions keep the term where it does search-result work in a sentence.
  title: "Accuracy",
  description:
    "How accurate are prediction markets? Calibration analysis across hundreds of thousands of resolved outcomes from Kalshi, Polymarket, and sportsbooks.",
  alternates: { canonical: "/calibration" },
  openGraph: {
    title: "Accuracy — Bain Luck",
    description:
      "How accurate are prediction markets? Calibration analysis across hundreds of thousands of resolved outcomes.",
    url: "/calibration",
    // LAT-P278: explicit, not inherited. `/discover/stats` proved the
    // root card does not reliably reach a route that declares its own
    // `openGraph` — see `lib/shareCard.ts`.
    images: defaultShareCard(),
  },
};

export default function CalibrationLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return <>{children}</>;
}
