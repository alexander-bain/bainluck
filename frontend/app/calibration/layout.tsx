import type { Metadata } from "next";

export const metadata: Metadata = {
  title: "Calibration",
  description:
    "How accurate are prediction markets? Calibration analysis across hundreds of thousands of resolved outcomes from Kalshi, Polymarket, and sportsbooks.",
  alternates: { canonical: "/calibration" },
  openGraph: {
    title: "Calibration — Bain Luck",
    description:
      "How accurate are prediction markets? Calibration analysis across hundreds of thousands of resolved outcomes.",
    url: "https://bainluck.com/calibration",
  },
};

export default function CalibrationLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return <>{children}</>;
}
