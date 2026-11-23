import type { Metadata } from "next";

import { selfCanonical } from "@/lib/routeMetadata";

// 227-A point 6: an admin grading tool, never indexed.
export const metadata: Metadata = {
  ...selfCanonical("/grade/screens"),
  title: "Grade: ten screens",
  robots: { index: false, follow: false },
};

export default function ScreensLayout({ children }: { children: React.ReactNode }) {
  return children;
}
