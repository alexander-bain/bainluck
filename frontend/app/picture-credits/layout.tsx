import type { Metadata } from "next";

import { selfCanonical } from "@/lib/routeMetadata";

// #4193 / Ruling 195-A: state `/picture-credits` canonical and `og:url` identity so
// the prerendered HTML does not inherit the root's `/`.
export const metadata: Metadata = selfCanonical("/picture-credits");

export default function PictureCreditsLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return <>{children}</>;
}
