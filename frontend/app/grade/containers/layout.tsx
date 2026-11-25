import type { Metadata } from "next";

import { selfCanonical } from "@/lib/routeMetadata";

export const metadata: Metadata = {
  ...selfCanonical("/grade/containers"),
  title: "Containers Deck — Blind 20",
  robots: { index: false, follow: false },
};

export default function GradeContainersLayout({ children }: { children: React.ReactNode }) {
  return children;
}
