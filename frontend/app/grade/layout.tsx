import type { Metadata } from "next";

// #12095 Phase 2 — an admin tool, never a page for search engines.
export const metadata: Metadata = {
  title: "Grade",
  robots: { index: false, follow: false },
};

export default function GradeLayout({ children }: { children: React.ReactNode }) {
  return children;
}
