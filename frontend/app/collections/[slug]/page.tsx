import { Suspense } from "react";
import CollectionPageClient from "./CollectionPageClient";
import { loadServerCollection } from "./serverCollection";

type CollectionPageProps = { params: { slug: string } };

async function CollectionPageContent({ slug }: { slug: string }) {
  const initialHub = slug ? await loadServerCollection(slug) : null;
  return <CollectionPageClient slug={slug} initialHub={initialHub} />;
}

export default function CollectionPage({ params }: CollectionPageProps) {
  const slug = typeof params?.slug === "string" ? params.slug : "";
  return (
    <Suspense
      fallback={
        <div className="mx-auto w-full max-w-4xl py-8" aria-busy="true" />
      }
    >
      <CollectionPageContent slug={slug} />
    </Suspense>
  );
}
