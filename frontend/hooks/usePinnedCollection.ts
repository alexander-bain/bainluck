"use client";

import useSWR from "swr";
import { useEffect, useState } from "react";
import { activeCollectionPin, fetchCollection } from "@/lib/collections";

/** Discover and Politics share the same public read and refresh clock. */
export function usePinnedCollection() {
  const [now, setNow] = useState(() => Date.now());
  const { data } = useSWR("collection:midterms-2026", () => fetchCollection("midterms-2026"), {
    refreshInterval: 30000, shouldRetryOnError: false,
  });
  const deadline = data?.pin?.pin_until;
  useEffect(() => {
    if (!deadline) return;
    const remaining = Date.parse(deadline) - Date.now();
    if (remaining <= 0) { setNow(Date.now()); return; }
    const timer = window.setTimeout(() => setNow(Date.now()), remaining);
    return () => window.clearTimeout(timer);
  }, [deadline]);
  return activeCollectionPin(data, Math.max(now, Date.now()));
}
