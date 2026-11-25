import type { Metadata } from "next";

import { selfCanonical } from "@/lib/routeMetadata";

export const metadata: Metadata = {
  ...selfCanonical("/grade/scout"),
  title: "Scout Morning Deck — Blind Review",
  robots: { index: false, follow: false },
};

export default function GradeScoutLayout({ children }: { children: React.ReactNode }) {
  return children;
}
