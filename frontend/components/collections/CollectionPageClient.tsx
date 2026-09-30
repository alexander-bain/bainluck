"use client";

import { usePageTracking, useScrollDepth, useEngagementTime } from "@/hooks";
import CollectionHub from "./CollectionHub";

export default function CollectionPageClient({ slug }: { slug: string }) {
  // Required analytics hooks precede every conditional rendering branch.
  usePageTracking({ pageType: "sport_hub", pageTitle: "Collection", additionalParams: { page_path: `/collections/${slug}` } });
  useScrollDepth({ pageType: "sport_hub" });
  useEngagementTime({ pageType: "sport_hub" });
  return <CollectionHub slug={slug} />;
}
