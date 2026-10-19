"use client";

// #847 — /admin/correctness: "can we trust our numbers today?" on one page.
// Composes five EXISTING endpoints once per visit (and on Reload) — no polling,
// no retries, no bust/force parameters. Judgment lives in
// `lib/correctnessConsole.ts`; rendering in `components/admin/CorrectnessConsole`.

import { useCallback, useEffect, useMemo, useState } from "react";
import {
  usePageTracking,
  useScrollDepth,
  useEngagementTime,
} from "@/hooks";
import { useAdminAuth } from "@/components/admin/AdminAuthProvider";
import AdminAuthNotice from "@/components/admin/AdminAuthNotice";
import CorrectnessConsoleView from "@/components/admin/CorrectnessConsole";
import { adminFetch } from "@/lib/adminFetch";
import {
  ADMIN_READS,
  CORRECTNESS_ENDPOINTS,
  INITIAL_READS,
  evaluateAll,
  startCorrectnessReads,
  type CorrectnessReads,
} from "@/lib/correctnessConsole";

const API_URL = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

export default function CorrectnessConsolePage() {
  usePageTracking({ pageType: "admin_correctness", pageTitle: "Admin: Correctness Console" });
  useScrollDepth({ pageType: "admin_correctness" });
  useEngagementTime({ pageType: "admin_correctness" });

  const { secret } = useAdminAuth();
  const [reads, setReads] = useState<CorrectnessReads>(INITIAL_READS);
  const [settledMs, setSettledMs] = useState<number | null>(null);
  const [nowMs, setNowMs] = useState(() => Date.now());
  const [round, setRound] = useState(0);

  useEffect(() => {
    if (!secret) return;
    const ctrl = new AbortController();
    setReads(INITIAL_READS);
    setSettledMs(null);
    startCorrectnessReads(
      (key) => {
        const path = CORRECTNESS_ENDPOINTS[key];
        // Admin reads carry the credential in the Authorization header via
        // adminFetch; the public calibration read carries none.
        return ADMIN_READS.has(key)
          ? (signal) => adminFetch(path, secret, { signal, cache: "no-store" })
          : (signal) => fetch(`${API_URL}${path}`, { signal });
      },
      (key, result) => {
        setReads((prev) => ({ ...prev, [key]: result }));
        setNowMs(Date.now());
      },
      { signal: ctrl.signal },
    ).then((ms) => {
      if (!ctrl.signal.aborted) setSettledMs(ms);
    });
    return () => ctrl.abort();
  }, [secret, round]);

  const tiles = useMemo(() => evaluateAll(reads, nowMs), [reads, nowMs]);
  const reload = useCallback(() => setRound((r) => r + 1), []);

  return (
    <CorrectnessConsoleView
      tiles={tiles}
      nowMs={nowMs}
      settledMs={settledMs}
      authNotice={<AdminAuthNotice />}
      onReload={reload}
    />
  );
}
