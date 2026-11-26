import type { Metadata } from "next";

import { defaultShareCard } from "@/lib/shareCard";

const DESCRIPTION = "Fifteen cards in three steps. Guess what the world thinks will happen, then send it to your group.";

export const metadata: Metadata = {
  title: "Guess the Chance",
  description: DESCRIPTION,
  alternates: { canonical: "/guess" },
  // Unlisted: reached only by a link someone sends. Kept out of search indexes
  // while it is being tried with a few groups.
  robots: { index: false, follow: false },
  openGraph: {
    title: "Guess the Chance · Bain Luck",
    description: DESCRIPTION,
    url: "/guess",
    // Explicit, not inherited: the root card does not reliably reach a route
    // that declares its own `openGraph` (see `lib/shareCard.ts`).
    images: defaultShareCard(),
  },
};

export default function GuessLayout({ children }: { children: React.ReactNode }) {
  return <>{children}</>;
}
