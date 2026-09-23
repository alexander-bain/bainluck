import type { Metadata } from "next";

import { defaultShareCard } from "@/lib/shareCard";

export const metadata: Metadata = {
  title: "My Prediction Scorecard | Bain Luck",
  description: "See how accurate my predictions are on Bain Luck - the probability-first prediction platform.",
  alternates: { canonical: "/discover/stats" },
  // #8187 — the same directive `/daily` got under #6445, for the same reason:
  // #6445's acceptance line is "no dead route promoted", and a page that sells
  // "See how accurate my predictions are" in a search result is promoting the
  // switched-off experience just as surely as the header icon was. Closing the
  // door in the app and leaving the route indexed only changes who opens it.
  //
  // The canonical above STAYS. #4193's lesson: dropping it makes the route tell
  // crawlers it is a duplicate of the home page, which is a different and worse
  // claim than "do not index me".
  robots: { index: false, follow: false },
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
