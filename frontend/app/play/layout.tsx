import type { Metadata } from "next";

export const metadata: Metadata = {
  title: "Play",
  description: "A fun, kid-safe rating game — swipe real predictions and guess the odds.",
  alternates: { canonical: "/play" },
  // Unlisted from nav; keep it out of search indexes too.
  robots: { index: false, follow: false },
  openGraph: {
    title: "Bain Luck Play",
    description: "A fun, kid-safe rating game — swipe real predictions and guess the odds.",
    url: "https://bainluck.com/play",
  },
};

export default function PlayLayout({ children }: { children: React.ReactNode }) {
  return <>{children}</>;
}
