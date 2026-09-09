import type { Metadata } from "next";

import { defaultShareCard } from "@/lib/shareCard";

export const metadata: Metadata = {
  title: "My Prediction Scorecard | Bain Luck",
  description: "See how accurate my predictions are on Bain Luck - the probability-first prediction platform.",
  alternates: { canonical: "/discover/stats" },
  openGraph: {
    title: "My Prediction Scorecard | Bain Luck",
    description: "See how accurate my predictions are on Bain Luck.",
    siteName: "Bain Luck",
    type: "website",
    url: "/discover/stats",
    // LAT-P278: this page rendered NO og:image even though its sibling
    // `/discover` inherited the root card, and it already asked for
    // `summary_large_image` — i.e. it was requesting a big card and supplying
    // no picture, which is the worst of both. Declared explicitly rather than
    // relying on inheritance, because the inheritance rule is exactly what
    // this page proved we cannot predict.
    images: defaultShareCard(),
  },
  twitter: {
    card: "summary_large_image",
    title: "My Prediction Scorecard | Bain Luck",
    description: "See how accurate my predictions are on Bain Luck.",
  },
};

export default function StatsLayout({ children }: { children: React.ReactNode }) {
  return children;
}
