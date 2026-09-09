import type { Metadata } from "next";

import { defaultShareCard } from "@/lib/shareCard";

export const metadata: Metadata = {
  title: "Calibration",
  description:
    "How accurate are prediction markets? Calibration analysis across hundreds of thousands of resolved outcomes from Kalshi, Polymarket, and sportsbooks.",
  alternates: { canonical: "/calibration" },
  openGraph: {
    title: "Calibration — Bain Luck",
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
