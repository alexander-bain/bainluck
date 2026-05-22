import type { Metadata } from "next";

export const metadata: Metadata = {
  title: "Weather Predictions",
  description:
    "Weather prediction markets from Kalshi and Polymarket — temperature, rain, hurricanes, and climate probabilities.",
  alternates: { canonical: "/weather" },
  openGraph: {
    title: "Weather Predictions — Bain Luck",
    description:
      "Weather prediction markets — temperature, rain, hurricanes, and climate probabilities.",
    url: "https://bainluck.com/weather",
  },
};

export default function WeatherLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return <>{children}</>;
}
