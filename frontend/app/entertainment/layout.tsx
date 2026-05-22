import type { Metadata } from "next";

export const metadata: Metadata = {
  title: "Entertainment Markets",
  description:
    "Entertainment prediction markets — Spotify chart races, box office, Rotten Tomatoes scores, reality TV, and pop culture probabilities.",
  alternates: { canonical: "/entertainment" },
  openGraph: {
    title: "Entertainment Markets — Bain Luck",
    description:
      "Entertainment prediction markets — Spotify, box office, Rotten Tomatoes, reality TV, and pop culture probabilities.",
    url: "https://bainluck.com/entertainment",
  },
};

export default function EntertainmentLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return <>{children}</>;
}
