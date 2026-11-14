"use client";

/* eslint-disable @next/next/no-img-element */

import { useState } from "react";
import Link from "next/link";
import { usePageTracking, useScrollDepth, useEngagementTime } from "@/hooks";
import verifiedDiscoverArt from "@/lib/discover/verifiedDiscoverArt.json";

interface VerifiedArtEntry {
  entity_key: string;
  kind: string;
  aliases?: string[];
  url: string;
  presentation?: string;
  verified_subject?: string;
  credit?: string;
  author?: string;
  license?: string;
  source_page?: string;
}

interface CreditedEntry {
  entity_key: string;
  subject: string;
  url: string;
  author: string;
  license: string;
  source_page: string;
}

function getCreditedEntries(): CreditedEntry[] {
  const rawEntries = (verifiedDiscoverArt.entries || []) as VerifiedArtEntry[];
  return rawEntries
    .filter(
      (entry) =>
        Boolean(entry.url?.trim()) &&
        Boolean(entry.author?.trim()) &&
        Boolean(entry.license?.trim()) &&
        Boolean(entry.source_page?.trim()),
    )
    .map((entry) => ({
      entity_key: entry.entity_key,
      subject:
        entry.verified_subject?.trim() ||
        entry.aliases?.[0]?.trim() ||
        entry.entity_key,
      url: entry.url.trim(),
      author: (entry.author || "").trim(),
      license: (entry.license || "").trim(),
      source_page: (entry.source_page || "").trim(),
    }));
}

const CREDITED_ENTRIES: CreditedEntry[] = getCreditedEntries();

function CreditRow({ item }: { item: CreditedEntry }) {
  const [failed, setFailed] = useState(false);
  const initials = item.subject
    .split(/\s+/)
    .filter(Boolean)
    .slice(0, 2)
    .map((part) => part[0]?.toUpperCase() || "")
    .join("");

  return (
    <li
      data-testid="picture-credit-item"
      className="flex items-start gap-3.5 bg-surface-card border border-surface-border rounded-xl p-3.5"
    >
      {failed ? (
        <div
          aria-hidden="true"
          className="w-16 h-16 rounded-lg bg-surface-elevated border border-surface-border flex items-center justify-center text-caption-strong text-text-secondary flex-shrink-0"
        >
          {initials}
        </div>
      ) : (
        <img
          src={item.url}
          alt={item.subject}
          loading="lazy"
          referrerPolicy="no-referrer"
          onError={() => setFailed(true)}
          className="w-16 h-16 rounded-lg object-cover bg-surface-elevated border border-surface-border flex-shrink-0"
        />
      )}

      <div className="min-w-0 flex-1 space-y-1">
        <p className="text-body-strong text-text-primary leading-snug">
          {item.subject}
        </p>
        <p className="text-caption text-text-secondary leading-snug">
          <span className="text-text-muted">Author:</span> {item.author}
        </p>
        <div className="flex flex-wrap items-center gap-x-2.5 gap-y-1 pt-0.5 text-caption">
          <span className="inline-flex items-center rounded-md bg-surface-elevated border border-surface-border px-2 py-0.5 text-micro font-medium text-text-secondary">
            {item.license}
          </span>
          <a
            href={item.source_page}
            target="_blank"
            rel="noopener noreferrer"
            className="text-accent-brand hover:underline font-medium whitespace-nowrap"
          >
            Source page ↗
          </a>
        </div>
      </div>
    </li>
  );
}

export default function PictureCreditsPage() {
  usePageTracking({ pageType: "picture_credits", pageTitle: "Picture credits" });
  useScrollDepth({ pageType: "picture_credits" });
  useEngagementTime({ pageType: "picture_credits" });

  return (
    <div className="max-w-3xl mx-auto space-y-6 px-4 py-6 pb-16">
      <header className="space-y-2 pb-5 border-b border-surface-border">
        <h1 className="text-title-1 text-text-primary">Picture credits</h1>
        <p className="text-body text-text-secondary leading-relaxed">
          Photographs and release artwork used across Discover that carry
          creator attribution and licence terms, generated directly from our
          verified art register.
        </p>
      </header>

      <ul className="space-y-3" aria-label="Credited pictures">
        {CREDITED_ENTRIES.map((item) => (
          <CreditRow key={item.entity_key} item={item} />
        ))}
      </ul>

      <footer className="pt-4 border-t border-surface-border flex flex-wrap items-center justify-between gap-3 text-caption text-text-muted">
        <span>
          {CREDITED_ENTRIES.length} credited pictures from the verified art
          register.
        </span>
        <Link href="/about" className="text-accent-brand hover:underline font-medium">
          About Bain Luck
        </Link>
      </footer>
    </div>
  );
}
