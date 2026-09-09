import type { Metadata } from "next";

import { defaultShareCard } from "@/lib/shareCard";

export const metadata: Metadata = {
  title: "Weather Predictions",
  description:
    "Weather prediction markets from Kalshi and Polymarket — temperature, rain, hurricanes, and climate probabilities.",
  alternates: { canonical: "/weather" },
  openGraph: {
    title: "Weather Predictions — Bain Luck",
    description:
      "Weather prediction markets — temperature, rain, hurricanes, and climate probabilities.",
    url: "/weather",
    // LAT-P278: explicit, not inherited. `/discover/stats` proved the
    // root card does not reliably reach a route that declares its own
    // `openGraph` — see `lib/shareCard.ts`.
    images: defaultShareCard(),
  },
};

export default function WeatherLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return <>{children}</>;
}
