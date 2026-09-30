import type { Metadata } from "next";
import CollectionPageClient from "@/components/collections/CollectionPageClient";
import { collectionPath, fetchCollection } from "@/lib/collections";

type CollectionPageProps = { params: { slug: string } };

export async function generateMetadata({ params }: CollectionPageProps): Promise<Metadata> {
  const path = collectionPath(params.slug);
  let title = "Collection";
  let description = "This collection is temporarily unavailable. Please try again.";
  let unavailable = false;
  if (path) {
    try {
      // A shared link names only a fresh public collection. A transient read
      // failure keeps a neutral identity without claiming it does not exist.
      const hub = await fetchCollection(params.slug, AbortSignal.timeout(2500));
      if (hub.title) title = hub.title;
      description = hub.state === "published"
        ? `${hub.edition}. ${hub.note ? `${hub.note} ` : ""}Explore games, results and related questions.`
        : hub.note ?? description;
      unavailable = hub.state !== "published";
    } catch { /* metadata must not prevent the client from retrying its fresh read */ }
  } else unavailable = true;
  const socialTitle = `${title} | Bain Luck`;
  const images = path ? [{ url: `${path}/opengraph-image`, width: 1200, height: 630, alt: title }] : [];
  return {
    title, description,
    ...(path ? { alternates: { canonical: path } } : {}),
    openGraph: { title: socialTitle, description, type: "website", images: images, ...(path ? { url: path } : {}) },
    twitter: { card: "summary_large_image", title: socialTitle, description, images: images },
    ...(unavailable ? { robots: { index: false, follow: true } } : {}),
  };
}

export default function CollectionPage({ params }: CollectionPageProps) {
  return <CollectionPageClient slug={params.slug} />;
}
