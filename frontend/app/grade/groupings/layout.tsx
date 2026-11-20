import type { Metadata } from "next";

import { selfCanonical } from "@/lib/routeMetadata";

// #12373 — private grouping grading page, never indexed by search engines.
export const metadata: Metadata = {
  ...selfCanonical("/grade/groupings"),
  title: "Grade Groupings",
  robots: { index: false, follow: false },
};

export default function GradeGroupingsLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return children;
}
