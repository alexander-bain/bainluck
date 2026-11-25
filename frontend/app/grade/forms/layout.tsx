import type { Metadata } from "next";

import { selfCanonical } from "@/lib/routeMetadata";

export const metadata: Metadata = {
  ...selfCanonical("/grade/forms"),
  title: "Forms Deck — Pile Sort",
  robots: { index: false, follow: false },
};

export default function GradeFormsLayout({ children }: { children: React.ReactNode }) {
  return children;
}
