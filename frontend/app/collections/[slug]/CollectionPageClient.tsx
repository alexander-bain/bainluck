"use client";

import { useEffect, useRef } from "react";
import { usePageTracking, useScrollDepth, useEngagementTime } from "@/hooks";
import { trackEvent } from "@/lib/analytics";
import CollectionHub from "@/components/collections/CollectionHub";
import type { CollectionHub as Hub } from "@/lib/collections";

export function trackCollectionSharedLinkOpen(
  slug: string,
  search: string,
): boolean {
  const params = new URLSearchParams(search);
  const utmSource = params.get("utm_source")?.trim() || undefined;
  const utmMedium = params.get("utm_medium")?.trim() || undefined;
  const utmCampaign = params.get("utm_campaign")?.trim() || undefined;
  const refParam = params.get("ref")?.trim() || undefined;
  const isShared = Boolean(utmSource || utmMedium || utmCampaign || refParam === "share");
  if (!isShared) return false;
  trackEvent("shared_link_open", {
    content_type: "collection",
    item_id: slug,
    source: utmSource ?? "share",
    medium: utmMedium,
    campaign: utmCampaign,
  });
  return true;
}

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

  // #13261 row 2: attribute shared / UTM arrivals on `/collections/[slug]`
  // behind the existing `trackEvent` "Allow" consent gate (181-C).
  const trackedSlugRef = useRef<string | null>(null);
  useEffect(() => {
    if (typeof window === "undefined" || trackedSlugRef.current === slug) return;
    if (trackCollectionSharedLinkOpen(slug, window.location.search)) {
      trackedSlugRef.current = slug;
    }
  }, [slug]);

  return <CollectionHub slug={slug} initialHub={initialHub} />;
}
