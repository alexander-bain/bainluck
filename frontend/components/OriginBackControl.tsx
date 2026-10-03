"use client";

import { useEffect, useRef, useState } from "react";
import Link from "next/link";
import { browserOriginEnv, type OriginStore } from "@/lib/futuresReturnOrigin";

/**
 * #10265 / #10317 — a page's back control that goes where the reader came from.
 *
 * A reader who tapped into this page from one of our pages (a live game's
 * Bigger Picture card, a league page, a team page, a hub) gets "Back", and it
 * traverses to that exact entry, query, hash and scroll position included, as
 * the browser's Back would. Everyone else gets the page's old fixed link. What
 * counts as proof, and why `history.length` and the referrer do not:
 * `lib/futuresReturnOrigin.ts`.
 *
 * The href stays the fallback in both cases, so a modified or middle click
 * opens it in a new tab rather than a history step that tab does not have.
 */
export default function OriginBackControl({
  store,
  fallbackHref,
  fallbackLabel,
  onNavigate,
}: {
  store: OriginStore;
  fallbackHref: string;
  fallbackLabel: string;
  /** Analytics: called with where the tap goes ("back" for a traversal). */
  onNavigate?: (to: string) => void;
}) {
  const [goesBack, setGoesBack] = useState(false);
  // One traversal per tap: a double tap must not go back two entries.
  const leaving = useRef(false);

  useEffect(() => {
    const refresh = () => {
      const env = browserOriginEnv();
      setGoesBack(!!env && store.canGoBack(env));
    };
    const env = browserOriginEnv();
    if (env) store.adopt(env);
    refresh();
    // The entry under the page can change without a remount (a range chip's
    // replaceState, Back/Forward between two entries of one page).
    const nav = (window as unknown as { navigation?: EventTarget }).navigation;
    const onEntryChange = () => {
      leaving.current = false;
      refresh();
    };
    nav?.addEventListener?.("currententrychange", onEntryChange);
    return () => nav?.removeEventListener?.("currententrychange", onEntryChange);
  }, [store]);

  const onClick = (e: React.MouseEvent<HTMLAnchorElement>) => {
    if (e.button !== 0 || e.metaKey || e.ctrlKey || e.shiftKey || e.altKey) {
      onNavigate?.(fallbackHref);
      return;
    }
    // Proof is checked again at the tap, never trusted from mount.
    const env = browserOriginEnv();
    if (!env || !store.canGoBack(env)) {
      onNavigate?.(fallbackHref);
      return;
    }
    e.preventDefault();
    if (leaving.current) return;
    leaving.current = true;
    onNavigate?.("back");
    // What Next's router.back() does; the app router restores the page and the
    // reader's scroll on the popstate.
    window.history.back();
  };

  return (
    <Link
      href={fallbackHref}
      onClick={onClick}
      className="inline-flex items-center text-caption text-text-secondary hover:text-text-primary transition-colors"
    >
      <svg className="w-4 h-4 mr-1" fill="none" stroke="currentColor" viewBox="0 0 24 24">
        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M15 19l-7-7 7-7" />
      </svg>
      {goesBack ? "Back" : fallbackLabel}
    </Link>
  );
}
