import type { Metadata } from "next";

export const metadata: Metadata = {
  title: "What is Bain Luck? Probability, not betting",
  description:
    "Every game, election, and premiere has a number — the world's honest guess at what happens next. Bain Luck finds it, blends six sources into one, and shows it clean. No odds formats, nothing to buy — and we grade ourselves in public.",
  alternates: { canonical: "/about" },
  openGraph: {
    type: "website",
    title: "What is Bain Luck? Probability, not betting",
    description:
      "Six sources, one number — the world's honest guess at what happens next, graded in public.",
    url: "https://bainluck.com/about",
  },
  twitter: {
    card: "summary_large_image",
    title: "What is Bain Luck? Probability, not betting",
    description: "Six sources, one number. Graded in public.",
  },
};

export default function AboutLayout({ children }: { children: React.ReactNode }) {
  return <>{children}</>;
}
