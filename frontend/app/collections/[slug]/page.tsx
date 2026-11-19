import CollectionPageClient from "./CollectionPageClient";
import { loadServerCollection } from "./serverCollection";

type CollectionPageProps = { params: { slug: string } };

export default async function CollectionPage({ params }: CollectionPageProps) {
  const slug = typeof params?.slug === "string" ? params.slug : "";
  const initialHub = slug ? await loadServerCollection(slug) : null;
  return <CollectionPageClient slug={slug} initialHub={initialHub} />;
}
