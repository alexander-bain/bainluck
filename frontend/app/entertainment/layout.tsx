import type { Metadata } from "next";

import { defaultShareCard } from "@/lib/shareCard";

export const metadata: Metadata = {
  title: "Entertainment Markets",
  description:
    "Entertainment prediction markets — Spotify chart races, box office, Rotten Tomatoes scores, reality TV, and pop culture probabilities.",
  alternates: { canonical: "/entertainment" },
  openGraph: {
    title: "Entertainment Markets — Bain Luck",
    description:
      "Entertainment prediction markets — Spotify, box office, Rotten Tomatoes, reality TV, and pop culture probabilities.",
    url: "/entertainment",
    // LAT-P278: explicit, not inherited. `/discover/stats` proved the
    // root card does not reliably reach a route that declares its own
    // `openGraph` — see `lib/shareCard.ts`.
    images: defaultShareCard(),
  },
};

export default function EntertainmentLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return <>{children}</>;
}
