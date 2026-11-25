import type { Metadata } from "next";

import { selfCanonical } from "@/lib/routeMetadata";

export const metadata: Metadata = {
  ...selfCanonical("/grade/sets-v2"),
  title: "Sets Blind 40 v2 — #13544",
  robots: { index: false, follow: false },
};

export default function GradeSetsV2Layout({ children }: { children: React.ReactNode }) {
  return children;
}
