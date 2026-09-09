import type { Metadata } from "next";

import { defaultShareCard } from "@/lib/shareCard";

export const metadata: Metadata = {
  title: "Discover",
  description:
    "Explore trending prediction markets across politics, economics, sports, entertainment, and more. See probabilities, not odds.",
  alternates: { canonical: "/discover" },
  openGraph: {
    title: "Discover — Bain Luck",
    description:
      "Explore trending prediction markets across politics, economics, sports, entertainment, and more.",
    url: "/discover",
    // LAT-P278: explicit, not inherited. `/discover/stats` proved the
    // root card does not reliably reach a route that declares its own
    // `openGraph` — see `lib/shareCard.ts`.
    images: defaultShareCard(),
  },
};

export default function DiscoverLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return <>{children}</>;
}
