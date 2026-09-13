import type { Metadata } from "next";

import { defaultShareCard } from "@/lib/shareCard";

export const metadata: Metadata = {
  // ⚠️ A PLAIN STRING, and load-bearing as one: it replaces the root's
  // `%s | Bain Luck` template for every route beneath `/sport`, which is why
  // `app/sport/[sport]/layout.tsx` and its `[league]` child carry the suffix
  // themselves. `__tests__/collectionUnfurlCard.test.tsx` asserts that split
  // against this file, so changing this to `{ default, template }` fails there
  // rather than shipping "NFL | Bain Luck | Bain Luck" in a tab.
  //
  // The wordmark is spaced. "BainLuck" was in this tab and in the `og:title`
  // below, and it is not the brand — the same rule
  // `chartFooterOneSourceLegend4083.test.tsx` asserts one surface over.
  title: "Sports | Bain Luck",
  description:
    "Win probabilities and odds across all major sports. See betting markets translated into intuitive probabilities for golf, basketball, football, hockey, baseball, soccer, tennis, and MMA.",
  // #4193: LAT-P278 gave this route its own `og:url` but not its own
  // `canonical`, so it still inherited the root's `"/"` — the one page on the
  // site that named itself correctly for sharing and incorrectly for search.
  alternates: { canonical: "/sport" },
  openGraph: {
    title: "All Sports | Bain Luck",
    description: "Win probabilities and odds across all major sports.",
    url: "/sport",
    // LAT-P278: explicit, not inherited. `/discover/stats` proved the
    // root card does not reliably reach a route that declares its own
    // `openGraph` — see `lib/shareCard.ts`.
    images: defaultShareCard(),
  },
};

export default function SportLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return <>{children}</>;
}
