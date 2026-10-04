"use client";

/**
 * #10476 — the "Collections" block at the top of the Browse menu, shared by the
 * desktop dropdown and the phone sheet so both offer the same hubs.
 *
 * It asks for the hubs while the menu is open (see `lib/browseCollections.ts`)
 * and renders only what that read admits. Nothing to show — none published,
 * the read failed or timed out — leaves no block at all, and the categories
 * below it are never held up waiting.
 */

import Link from "next/link";
import { useEffect, useId, useSyncExternalStore } from "react";
import {
  createBrowseCollectionsLoader,
  type BrowseCollectionsLoader,
} from "@/lib/browseCollections";

let sharedLoader: BrowseCollectionsLoader | null = null;

function defaultLoader(): BrowseCollectionsLoader {
  if (!sharedLoader) sharedLoader = createBrowseCollectionsLoader();
  return sharedLoader;
}

interface PublishedCollectionsMenuProps {
  open: boolean;
  pathname: string | null;
  variant: "desktop" | "mobile";
  /** Called with the hub's path when a reader follows one of its links. */
  onNavigate: (href: string) => void;
  loader?: BrowseCollectionsLoader;
}

export default function PublishedCollectionsMenu({
  open,
  pathname,
  variant,
  onNavigate,
  loader: injected,
}: PublishedCollectionsMenuProps) {
  const loader = injected ?? defaultLoader();
  const headingId = useId();
  const state = useSyncExternalStore(loader.subscribe, loader.getState, loader.getState);

  useEffect(() => {
    if (!open) return;
    loader.open();
    return () => loader.close();
  }, [open, loader]);

  if (!open) return null;
  if (state.status !== "loading" && state.entries.length === 0) return null;

  const rowPadding = variant === "mobile" ? "px-4 py-3" : "px-4 py-2.5";

  return (
    <div
      role="group"
      aria-labelledby={headingId}
      aria-busy={state.status === "loading" ? true : undefined}
      className="border-b border-surface-border pb-1 mb-1"
      data-browse-collections={state.status}
    >
      <p
        id={headingId}
        className="px-4 pt-2 pb-1 text-[11px] font-semibold uppercase tracking-wide text-text-muted"
      >
        Collections
      </p>
      {state.status === "loading" ? (
        <p role="status" className={`${rowPadding} text-sm text-text-muted`}>
          Loading…
        </p>
      ) : (
        <ul>
          {state.entries.map((entry) => {
            const current = pathname === entry.href;
            return (
              <li key={entry.slug}>
                <Link
                  href={entry.href}
                  aria-current={current ? "page" : undefined}
                  onClick={() => onNavigate(entry.href)}
                  className={`flex flex-col gap-0.5 ${rowPadding} text-sm transition-colors focus-visible:outline-none focus-visible:bg-surface-elevated ${
                    current
                      ? "text-accent-brand bg-accent-brand/5"
                      : "text-text-primary hover:bg-surface-elevated active:bg-surface-elevated"
                  }`}
                >
                  <span className="font-medium">{entry.name}</span>
                  {entry.subtitle && <span className="text-xs text-text-muted">{entry.subtitle}</span>}
                </Link>
              </li>
            );
          })}
        </ul>
      )}
    </div>
  );
}
