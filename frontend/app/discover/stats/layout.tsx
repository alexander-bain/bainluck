import type { Metadata } from "next";

export const metadata: Metadata = {
  title: "My Prediction Scorecard | Bain Luck",
  description: "See how accurate my predictions are on Bain Luck - the probability-first prediction platform.",
  openGraph: {
    title: "My Prediction Scorecard | Bain Luck",
    description: "See how accurate my predictions are on Bain Luck.",
    siteName: "Bain Luck",
    type: "website",
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
