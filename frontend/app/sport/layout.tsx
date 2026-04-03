import type { Metadata } from "next";

export const metadata: Metadata = {
  title: "Sports - BainLuck",
  description:
    "Win probabilities and odds across all major sports. See betting markets translated into intuitive probabilities for golf, basketball, football, hockey, baseball, soccer, tennis, and MMA.",
  openGraph: {
    title: "All Sports - BainLuck",
    description: "Win probabilities and odds across all major sports.",
    url: "https://bainluck.com/sport",
  },
};

export default function SportLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return <>{children}</>;
}
