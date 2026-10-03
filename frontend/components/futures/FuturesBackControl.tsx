"use client";

import { useEffect, useRef, useState } from "react";
import Link from "next/link";
import { browserOriginEnv, questionOrigin } from "@/lib/futuresReturnOrigin";

/**
 * #10265 — the question page's back control.
 *
 * A reader who tapped into this question from one of our pages (a live game's
 * Bigger Picture card, a team page, a hub, another question) gets "Back", and
 * it traverses to that exact entry, query, hash and scroll position included,
 * as the browser's Back would. Everyone else gets "Back to Discover", the old
 * link. What counts as proof, and why `history.length` and the referrer do
 * not: `lib/futuresReturnOrigin.ts`.
 *
 * The href stays /discover in both cases, so a modified or middle click opens
 * Discover in a new tab rather than a history step that tab does not have.
 */
export default function FuturesBackControl() {
  const [goesBack, setGoesBack] = useState(false);
  // One traversal per tap: a double tap must not go back two entries.
  const leaving = useRef(false);

  useEffect(() => {
    const refresh = () => {
      const env = browserOriginEnv();
      setGoesBack(!!env && questionOrigin.canGoBack(env));
    };
    const env = browserOriginEnv();
    if (env) questionOrigin.adopt(env);
    refresh();
    // The entry under the page can change without a remount (a range chip's
    // replaceState, Back/Forward between two entries of one question).
    const nav = (window as unknown as { navigation?: EventTarget }).navigation;
    const onEntryChange = () => {
      leaving.current = false;
      refresh();
    };
    nav?.addEventListener?.("currententrychange", onEntryChange);
    return () => nav?.removeEventListener?.("currententrychange", onEntryChange);
  }, []);

  const onClick = (e: React.MouseEvent<HTMLAnchorElement>) => {
    if (e.button !== 0 || e.metaKey || e.ctrlKey || e.shiftKey || e.altKey) return;
    // Proof is checked again at the tap, never trusted from mount.
    const env = browserOriginEnv();
    if (!env || !questionOrigin.canGoBack(env)) return;
    e.preventDefault();
    if (leaving.current) return;
    leaving.current = true;
    // What Next's router.back() does; the app router restores the page and the
    // reader's scroll on the popstate.
    window.history.back();
  };

  return (
    <Link
      href="/discover"
      onClick={onClick}
      className="inline-flex items-center text-caption text-text-secondary hover:text-text-primary transition-colors"
    >
      <svg className="w-4 h-4 mr-1" fill="none" stroke="currentColor" viewBox="0 0 24 24">
        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M15 19l-7-7 7-7" />
      </svg>
      {goesBack ? "Back" : "Back to Discover"}
    </Link>
  );
}
