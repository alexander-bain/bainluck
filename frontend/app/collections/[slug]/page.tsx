"use client";

import { useParams } from "next/navigation";
import { usePageTracking, useScrollDepth, useEngagementTime } from "@/hooks";
import CollectionHub from "@/components/collections/CollectionHub";

export default function CollectionPage() {
  const params = useParams();
  const slug = typeof params?.slug === "string" ? params.slug : "";
  // Required analytics hooks precede every conditional rendering branch.
  usePageTracking({ pageType: "sport_hub", pageTitle: "Collection", additionalParams: { page_path: `/collections/${slug}` } });
  useScrollDepth({ pageType: "sport_hub" });
  useEngagementTime({ pageType: "sport_hub" });
  return <CollectionHub slug={slug} />;
}
