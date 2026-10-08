"use client";

import { useEffect } from "react";
import { API_URL } from "@/lib/api";
import { eventIdFromHref, parkEventOpenIntent } from "@/lib/event/detailBoot";

/** Desktop hover must rest this long on an event link before it costs a request. */
const HOVER_DWELL_MS = 120;
/** At most this many hover-started parks per rolling minute (anonymous rate budget). */
const HOVER_PARKS_PER_MINUTE = 8;

/**
 * #1469 — starts an event page's hero + chart requests at the moment a reader commits to opening
 * it (a plain left click / tap, or a resting desktop hover), instead of after the route payload and
 * the page chunk arrive. One document-level listener covers every surface that links to
 * `/events/{id}` (Discover, Sports, search, team pages). See `parkEventOpenIntent`.
 */
export default function EventOpenIntent() {
  useEffect(() => {
    const eventIdFor = (target: EventTarget | null): number | null => {
      if (!(target instanceof Element)) return null;
      const anchor = target.closest("a[href]");
      if (!anchor) return null;
      const linkTarget = anchor.getAttribute("target");
      if (linkTarget && linkTarget !== "_self") return null;
      return eventIdFromHref(anchor.getAttribute("href"), window.location.origin);
    };

    const onClick = (e: MouseEvent) => {
      if (e.button !== 0 || e.metaKey || e.ctrlKey || e.shiftKey || e.altKey) return;
      const id = eventIdFor(e.target);
      if (id) parkEventOpenIntent(API_URL, id);
    };

    let hoverTimer: ReturnType<typeof setTimeout> | undefined;
    let hoverId: number | null = null;
    const hoverStarts: number[] = [];
    const onPointerOver = (e: PointerEvent) => {
      if (e.pointerType !== "mouse") return;
      const id = eventIdFor(e.target);
      if (id === hoverId) return;
      if (hoverTimer) clearTimeout(hoverTimer);
      hoverId = id;
      if (!id) return;
      hoverTimer = setTimeout(() => {
        const now = Date.now();
        while (hoverStarts.length && now - hoverStarts[0] > 60_000) hoverStarts.shift();
        if (hoverStarts.length >= HOVER_PARKS_PER_MINUTE) return;
        if (parkEventOpenIntent(API_URL, id)) hoverStarts.push(now);
      }, HOVER_DWELL_MS);
    };

    document.addEventListener("click", onClick, true);
    document.addEventListener("pointerover", onPointerOver, { passive: true });
    return () => {
      if (hoverTimer) clearTimeout(hoverTimer);
      document.removeEventListener("click", onClick, true);
      document.removeEventListener("pointerover", onPointerOver);
    };
  }, []);

  return null;
}
