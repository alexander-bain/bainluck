"use client";

import { usePageTracking, useScrollDepth, useEngagementTime } from "@/hooks";
import CollectionHub from "@/components/collections/CollectionHub";
import type { CollectionHub as Hub } from "@/lib/collections";

export default function CollectionPageClient({
  slug,
  initialHub,
}: {
  slug: string;
  initialHub: Hub | null;
}) {
  // Required analytics hooks precede every conditional rendering branch.
  usePageTracking({
    pageType: "sport_hub",
    pageTitle: initialHub?.title ?? "Collection",
    additionalParams: { page_path: `/collections/${slug}` },
  });
  useScrollDepth({ pageType: "sport_hub" });
  useEngagementTime({ pageType: "sport_hub" });
  return <CollectionHub slug={slug} initialHub={initialHub} />;
}
