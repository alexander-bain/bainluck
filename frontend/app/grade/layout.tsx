import type { Metadata } from "next";

import { selfCanonical } from "@/lib/routeMetadata";

// #12095 Phase 2 — an admin tool, never a page for search engines.
// It names itself (never the home page, #4193) and is never indexed.
export const metadata: Metadata = {
  ...selfCanonical("/grade"),
  title: "Grade",
  robots: { index: false, follow: false },
};

export default function GradeLayout({ children }: { children: React.ReactNode }) {
  return children;
}
