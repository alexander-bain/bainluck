import type { Metadata } from "next";

export const metadata: Metadata = {
  title: "Economic Forecasts",
  description:
    "Economic prediction markets — Fed rate path, inflation, GDP, recession odds, jobs data, and market indices from Kalshi and Polymarket.",
  alternates: { canonical: "/economics" },
  openGraph: {
    title: "Economic Forecasts — Bain Luck",
    description:
      "Economic prediction markets — Fed rates, inflation, GDP, recession odds, and market indices.",
    url: "https://bainluck.com/economics",
  },
};

export default function EconomicsLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return <>{children}</>;
}
