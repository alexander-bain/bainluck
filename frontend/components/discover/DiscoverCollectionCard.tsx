"use client";

import Link from "next/link";
import { ChevronRight } from "lucide-react";
import type { DiscoverCollectionEntry } from "@/lib/discover/collectionFeed";

/**
 * #9905 — a published hub among the ordinary Discover cards. The tap is a
 * plain client-side link to the canonical `/collections/{slug}` page, so the
 * feed's existing snapshot + scroll mark (#7417) bring the reader back to this
 * spot on Back. No like, dismiss or learning write: collections carry no
 * personalization of their own.
 */
export default function DiscoverCollectionCard({ entry }: { entry: DiscoverCollectionEntry }) {
  return (
    <Link
      href={entry.href}
      data-testid="discover-collection-card"
      data-collection-slug={entry.slug}
      className="group block rounded-2xl border border-surface-border bg-surface-card px-4 py-4 shadow-sm hover:shadow-md transition-shadow"
    >
      <div className="flex items-start gap-3">
        <div className="min-w-0 flex-1">
          <p className="text-[10px] font-bold uppercase tracking-wider text-text-secondary">Collection</p>
          <p className="mt-1 text-base font-bold leading-snug text-text-primary">{entry.name}</p>
          {entry.subtitle && <p className="mt-1 text-sm text-text-secondary">{entry.subtitle}</p>}
        </div>
        <ChevronRight
          size={18}
          aria-hidden="true"
          className="mt-0.5 shrink-0 text-text-muted group-hover:text-text-primary transition-colors"
        />
      </div>
    </Link>
  );
}
