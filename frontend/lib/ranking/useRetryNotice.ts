"use client";

/**
 * #11937: the grade pages' "saving again in N s" line, counting down once a
 * second while a rate-limited save waits for its one retry. Neutral, not an
 * error: nothing has failed yet.
 */

import { useCallback, useEffect, useState } from "react";
import { retryNoticeText } from "@/lib/ranking/gradeSession";

export function useRetryNotice(): { notice: string | null; startWait: (ms: number) => void; clearNotice: () => void } {
  const [until, setUntil] = useState<number | null>(null);
  const [now, setNow] = useState(() => Date.now());

  useEffect(() => {
    if (until == null) return;
    const timer = setInterval(() => setNow(Date.now()), 1000);
    return () => clearInterval(timer);
  }, [until]);

  const startWait = useCallback((ms: number) => {
    setNow(Date.now());
    setUntil(Date.now() + ms);
  }, []);
  const clearNotice = useCallback(() => setUntil(null), []);

  const notice = until == null ? null : retryNoticeText((until - now) / 1000);
  return { notice, startWait, clearNotice };
}
