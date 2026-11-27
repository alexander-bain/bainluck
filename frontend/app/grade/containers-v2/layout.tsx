import type { Metadata } from "next";

import { selfCanonical } from "@/lib/routeMetadata";

export const metadata: Metadata = {
  ...selfCanonical("/grade/containers-v2"),
  title: "Container Pages v2 — #12221",
  robots: { index: false, follow: false },
};

export default function GradeContainersV2Layout({ children }: { children: React.ReactNode }) {
  return children;
}
