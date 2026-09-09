import type { Metadata } from "next";

import { defaultShareCard } from "@/lib/shareCard";

export const metadata: Metadata = {
  title: "Play",
  description: "A fun, kid-safe rating game — swipe real predictions and guess the odds.",
  alternates: { canonical: "/play" },
  // Unlisted from nav; keep it out of search indexes too.
  robots: { index: false, follow: false },
  openGraph: {
    title: "Bain Luck Play",
    description: "A fun, kid-safe rating game — swipe real predictions and guess the odds.",
    url: "/play",
    // LAT-P278: explicit, not inherited. `/discover/stats` proved the
    // root card does not reliably reach a route that declares its own
    // `openGraph` — see `lib/shareCard.ts`.
    images: defaultShareCard(),
  },
};

export default function PlayLayout({ children }: { children: React.ReactNode }) {
  return <>{children}</>;
}
