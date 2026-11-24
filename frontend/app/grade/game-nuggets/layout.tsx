import type { Metadata } from "next";

import { selfCanonical } from "@/lib/routeMetadata";

// #13511 Step 1 — private game-nuggets grading tool, never indexed.
export const metadata: Metadata = {
  ...selfCanonical("/grade/game-nuggets"),
  title: "Grade: game nuggets",
  robots: { index: false, follow: false },
};

export default function GameNuggetsLayout({ children }: { children: React.ReactNode }) {
  return children;
}
