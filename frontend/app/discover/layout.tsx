import type { Metadata } from "next";

export const metadata: Metadata = {
  title: "Discover",
  description:
    "Explore trending prediction markets across politics, economics, sports, entertainment, and more. See probabilities, not odds.",
  alternates: { canonical: "/discover" },
  openGraph: {
    title: "Discover — Bain Luck",
    description:
      "Explore trending prediction markets across politics, economics, sports, entertainment, and more.",
    url: "https://bainluck.com/discover",
  },
};

export default function DiscoverLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return <>{children}</>;
}
