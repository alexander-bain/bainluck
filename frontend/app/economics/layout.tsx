import type { Metadata } from "next";

import { defaultShareCard } from "@/lib/shareCard";

export const metadata: Metadata = {
  title: "Economic Forecasts",
  description:
    "Economic prediction markets — Fed rate path, inflation, GDP, recession odds, jobs data, and market indices from Kalshi and Polymarket.",
  alternates: { canonical: "/economics" },
  openGraph: {
    title: "Economic Forecasts — Bain Luck",
    description:
      "Economic prediction markets — Fed rates, inflation, GDP, recession odds, and market indices.",
    url: "/economics",
    // LAT-P278: explicit, not inherited. `/discover/stats` proved the
    // root card does not reliably reach a route that declares its own
    // `openGraph` — see `lib/shareCard.ts`.
    images: defaultShareCard(),
  },
};

export default function EconomicsLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return <>{children}</>;
}
