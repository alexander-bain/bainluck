import type { Metadata } from "next";

export const metadata: Metadata = {
  title: "Political Markets",
  description:
    "Political prediction markets — presidential races, congressional control, policy, and Supreme Court probabilities from Kalshi and Polymarket.",
  alternates: { canonical: "/politics" },
  openGraph: {
    title: "Political Markets — Bain Luck",
    description:
      "Political prediction markets — presidential races, congressional control, policy, and Supreme Court probabilities.",
    url: "https://bainluck.com/politics",
  },
};

export default function PoliticsLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return <>{children}</>;
}
