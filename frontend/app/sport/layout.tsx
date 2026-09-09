import type { Metadata } from "next";

import { defaultShareCard } from "@/lib/shareCard";

export const metadata: Metadata = {
  title: "Sports - BainLuck",
  description:
    "Win probabilities and odds across all major sports. See betting markets translated into intuitive probabilities for golf, basketball, football, hockey, baseball, soccer, tennis, and MMA.",
  openGraph: {
    title: "All Sports - BainLuck",
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
