"use client";

import React from "react";
import { KitCardRenderer } from "@/components/discover/kit/KitCardRenderer";
import type { KitV1CardSpec } from "@/components/discover/kit/types";
import previewTheme from "./kitPreviewTheme.module.css";

export interface KitContainerPageSpec {
  kit_page_version: number;
  state: "preview" | "published";
  slug: string;
  family_fingerprint?: string | null;
  title: string;
  kicker: string;
  caption?: string;
  snapshot_captured_at: string;
  market_count: number;
  section_count: number;
  variants: string[];
  sections: KitV1CardSpec[];
}

export interface KitContainerPagesPreviewResponse {
  kit_page_version: number;
  snapshot_captured_at: string;
  count: number;
  pages: KitContainerPageSpec[];
}

export function KitContainerPageView({
  page,
  surfaceScheme = "light",
  showDebugMeta = true,
}: {
  page: KitContainerPageSpec;
  surfaceScheme?: "light" | "dark";
  showDebugMeta?: boolean;
}) {
  const wrapperClass =
    surfaceScheme === "dark"
      ? `${previewTheme.darkSurface} bg-surface-deep text-text-primary`
      : "bg-surface-deep text-text-primary";

  return (
    <section
      data-kit-page-slug={page.slug}
      data-kit-page-scheme={surfaceScheme}
      className={`${wrapperClass} rounded-2xl border border-surface-border p-3 space-y-3`}
    >
      <header className="rounded-xl border border-surface-border bg-surface-card p-3.5 shadow-sm">
        <div className="flex items-center justify-between gap-2 text-[10px] font-bold uppercase tracking-wider">
          <span className="text-accent-brand">{page.kicker}</span>
          <span className="rounded-full border border-surface-border bg-surface-elevated px-2 py-0.5 text-[10px] font-semibold text-text-secondary">
            {page.state} · {page.section_count} sections
          </span>
        </div>
        <h2 className="mt-1 text-xl font-extrabold tracking-tight text-text-primary">
          {page.title}
        </h2>
        {page.caption && (
          <p className="mt-1 text-xs leading-snug text-text-secondary">
            {page.caption}
          </p>
        )}
        {showDebugMeta && (
          <div className="mt-2 flex flex-wrap gap-1.5">
            {page.variants.map((variant) => (
              <span
                key={`${page.slug}-${variant}`}
                className="rounded border border-surface-border bg-surface-elevated px-1.5 py-0.5 text-[10px] font-medium text-text-muted"
              >
                {variant}
              </span>
            ))}
          </div>
        )}
      </header>

      <div className="space-y-3">
        {page.sections.map((section) => (
          <div key={section.id} className="space-y-1">
            {showDebugMeta && (
              <div className="flex items-center justify-between px-1 text-[10px] font-medium text-text-muted">
                <span>{section.layout}</span>
                <span>{section.variant ?? "default"}</span>
              </div>
            )}
            <KitCardRenderer spec={section} />
          </div>
        ))}
      </div>
    </section>
  );
}
