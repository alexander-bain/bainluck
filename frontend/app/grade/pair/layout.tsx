import type { Metadata } from "next";

import { selfCanonical } from "@/lib/routeMetadata";

// #11937 (171-A): an admin grading tool, never indexed.
export const metadata: Metadata = {
  ...selfCanonical("/grade/pair"),
  title: "Grade: side by side",
  robots: { index: false, follow: false },
};

export default function PairLayout({ children }: { children: React.ReactNode }) {
  return children;
}
