import type { Metadata } from "next";

import { selfCanonical } from "@/lib/routeMetadata";

/**
 * #4193. `generateMetadata` rather than a static `metadata` export, because the
 * canonical has to name THIS category — a static one would hand every hub the
 * same URL, which is the duplicate claim the fix is removing, just aimed
 * somewhere new.
 *
 * These are content pages: `/categories/politics` measured on production
 * 2026-09-09 declared `canonical: https://www.bainluck.com`, i.e. "index the
 * home page instead of me".
 */
export async function generateMetadata({
  params,
}: {
  params: Promise<{ slug: string }>;
}): Promise<Metadata> {
  const { slug } = await params;
  return selfCanonical(`/categories/${encodeURIComponent(slug)}`);
}

export default function CategorySlugLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return <>{children}</>;
}
