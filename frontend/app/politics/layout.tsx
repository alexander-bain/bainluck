import type { Metadata } from "next";

import { defaultShareCard } from "@/lib/shareCard";

export const metadata: Metadata = {
  title: "Political Markets",
  description:
    "Political prediction markets — presidential races, congressional control, policy, and Supreme Court probabilities from Kalshi and Polymarket.",
  alternates: { canonical: "/politics" },
  openGraph: {
    title: "Political Markets — Bain Luck",
    description:
      "Political prediction markets — presidential races, congressional control, policy, and Supreme Court probabilities.",
    url: "/politics",
    // LAT-P278: explicit, not inherited. `/discover/stats` proved the
    // root card does not reliably reach a route that declares its own
    // `openGraph` — see `lib/shareCard.ts`.
    images: defaultShareCard(),
  },
};

export default function PoliticsLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return <>{children}</>;
}
