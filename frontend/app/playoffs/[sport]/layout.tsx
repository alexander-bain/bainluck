import type { Metadata } from "next";

import { selfCanonical } from "@/lib/routeMetadata";

/**
 * #4193. Same shape as `app/categories/[slug]/layout.tsx`: the canonical has to
 * name THIS sport's bracket, so it is computed from the segment rather than
 * declared once.
 *
 * `/playoffs/nfl` measured on production 2026-09-09 declared
 * `canonical: https://www.bainluck.com` — a bracket page asking to be indexed
 * as the home page.
 */
export async function generateMetadata({
  params,
}: {
  params: Promise<{ sport: string }>;
}): Promise<Metadata> {
  const { sport } = await params;
  return selfCanonical(`/playoffs/${encodeURIComponent(sport)}`);
}

export default function PlayoffsSportLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return <>{children}</>;
}
