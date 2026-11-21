import type { Metadata } from "next";
import type { ReactNode } from "react";
import {
  APP_CLIP_BUNDLE_ID,
  APP_STORE_APP_ID,
  APP_STORE_CAMPAIGNS,
  APP_STORE_PROVIDER_TOKEN,
  buildAppleItunesMetaContent,
} from "@/lib/brandCopy";
import { getSiteUrl } from "@/lib/siteUrl";
import { collectionPath } from "@/lib/collections";
import { loadServerCollection } from "./serverCollection";

type CollectionPageProps = { params: { slug: string } };

export async function generateMetadata({ params }: CollectionPageProps): Promise<Metadata> {
  const path = collectionPath(params.slug);
  let title = "Collection";
  let description = "This collection is temporarily unavailable. Please try again.";
  let unavailable = false;
  if (path) {
    // A shared link names only a fresh public collection. A transient read
    // failure keeps a neutral identity without claiming it does not exist.
    const hub = await loadServerCollection(params.slug);
    if (hub) {
      if (hub.title) title = hub.title;
      description = hub.state === "published"
        ? hub.subtitle ?? `${hub.edition}. ${hub.note ? `${hub.note} ` : ""}Explore games, results and related markets.`
        : hub.note ?? description;
      unavailable = hub.state !== "published";
    }
  } else unavailable = true;
  const socialTitle = `${title} | Bain Luck`;
  const images = path ? [{ url: `${path}/opengraph-image`, width: 1200, height: 630, alt: title }] : [];
  const collectionUrl = path ? `${getSiteUrl()}${path}` : null;
  return {
    title, description,
    ...(path ? { alternates: { canonical: path } } : {}),
    ...(collectionUrl
      ? APP_STORE_PROVIDER_TOKEN
        ? {
            other: {
              "apple-itunes-app": buildAppleItunesMetaContent(
                collectionUrl,
                APP_CLIP_BUNDLE_ID,
                APP_STORE_CAMPAIGNS.bannerCollectionPage,
              ),
            },
          }
        : { itunes: { appId: APP_STORE_APP_ID, appArgument: collectionUrl } }
      : {}),
    openGraph: { title: socialTitle, description, type: "website", images: images, ...(path ? { url: path } : {}) },
    twitter: { card: "summary_large_image", title: socialTitle, description, images: images },
    ...(unavailable ? { robots: { index: false, follow: true } } : {}),
  };
}

export default function CollectionLayout({ children }: { children: ReactNode }) {
  return <>{children}</>;
}
