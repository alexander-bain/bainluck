"use client";

// #847 — /admin/correctness: "can we trust our numbers today?" on one page.
// Composes six endpoints once per visit (and on Reload) — no polling, no
// retries, no bust/force parameters. Coverage, link rate and snapshot sparsity
// come from saved-only reads, so opening or reloading starts no computation. A local clock re-judges the evidence
// already fetched, so a tab left open ages into stale without a new request.
// Judgment lives in `lib/correctnessConsole.ts`; rendering in
// `components/admin/CorrectnessConsole`.
//
// The Matching and Source Intelligence tabs (`?tab=`, so Back and Refresh keep
// the view) read their own saved-only routes, LAZILY: a tab's reads start the
// first time it is shown in a round, never on page open, and Reload starts a
// new round. Matching reuses the overview's link-rate read rather than sending
// a second one. Tab judgment: `lib/correctnessConsoleTabs.ts`.

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import {
  usePageTracking,
  useScrollDepth,
  useEngagementTime,
} from "@/hooks";
import { useAdminAuth } from "@/components/admin/AdminAuthProvider";
import AdminAuthNotice from "@/components/admin/AdminAuthNotice";
import CorrectnessConsoleView from "@/components/admin/CorrectnessConsole";
import { MatchingTabPanel, SourceIntelligenceTabPanel } from "@/components/admin/CorrectnessConsoleTabs";
import { adminFetch } from "@/lib/adminFetch";
import {
  ADMIN_READS,
  CORRECTNESS_ENDPOINTS,
  INITIAL_READS,
  evaluateAll,
  startCorrectnessReads,
  startUiClock,
  type CorrectnessReads,
} from "@/lib/correctnessConsole";
import {
  INITIAL_TAB_READS,
  TAB_READ_ENDPOINTS,
  consoleTabSearch,
  linkRateSection,
  maturedLinkageSection,
  parseConsoleTab,
  sourceIntelligenceSection,
  sportCardsSection,
  startTabReads,
  tabKeysToStart,
  type ConsoleTab,
  type TabReadKey,
  type TabReads,
} from "@/lib/correctnessConsoleTabs";

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
  // The admin layout mounts this page only after the credential check, on the
  // client, so reading the URL here cannot mismatch a server render.
  const [tab, setTab] = useState<ConsoleTab>(() =>
    typeof window === "undefined" ? "overview" : parseConsoleTab(window.location.search),
  );
  const [visited, setVisited] = useState<ReadonlySet<ConsoleTab>>(() => new Set([tab]));
  const [tabReads, setTabReads] = useState<TabReads>(INITIAL_TAB_READS);
  // One controller and one started-set per round: Reload, a new credential or
  // unmount aborts every tab read in flight, and its late answer is dropped.
  const tabRound = useRef<{ ctrl: AbortController; started: Set<TabReadKey> } | null>(null);

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

  // Local time only: makes no request (Root 002).
  useEffect(() => startUiClock(setNowMs), []);

  // Back/Forward move between tabs; the URL is the source of truth.
  useEffect(() => {
    const onPop = () => setTab(parseConsoleTab(window.location.search));
    window.addEventListener("popstate", onPop);
    return () => window.removeEventListener("popstate", onPop);
  }, []);

  useEffect(() => {
    setVisited((prev) => (prev.has(tab) ? prev : new Set([...prev, tab])));
  }, [tab]);

  // A new round: drop every tab answer and abort what is still in flight.
  useEffect(() => {
    const next = { ctrl: new AbortController(), started: new Set<TabReadKey>() };
    tabRound.current = next;
    setTabReads(INITIAL_TAB_READS);
    return () => next.ctrl.abort();
  }, [secret, round]);

  // The shown tab's reads, once per round. Declared after the round reset so a
  // Reload resets first and then restarts only the tab on screen.
  useEffect(() => {
    const current = tabRound.current;
    if (!secret || !current || current.ctrl.signal.aborted) return;
    const keys = tabKeysToStart(tab, current.started);
    if (keys.length === 0) return;
    keys.forEach((k) => current.started.add(k));
    void startTabReads(
      keys,
      (key) => (signal) => adminFetch(TAB_READ_ENDPOINTS[key], secret, { signal, cache: "no-store" }),
      (key, result) => {
        setTabReads((prev) => ({ ...prev, [key]: result }));
        setNowMs(Date.now());
      },
      { signal: current.ctrl.signal },
    );
  }, [secret, tab, round]);

  // One history entry per tab change, so Back returns to the previous view.
  const selectTab = useCallback(
    (next: ConsoleTab) => {
      if (next === tab) return;
      const url = `${window.location.pathname}${consoleTabSearch(window.location.search, next)}${window.location.hash}`;
      window.history.pushState(window.history.state, "", url);
      setTab(next);
    },
    [tab],
  );

  const tiles = useMemo(() => evaluateAll(reads, nowMs), [reads, nowMs]);
  const reload = useCallback(() => setRound((r) => r + 1), []);

  // Parsed once per answer, not on every clock tick.
  const matured = useMemo(() => maturedLinkageSection(tabReads.maturedLinkage), [tabReads.maturedLinkage]);
  const sportCards = useMemo(() => sportCardsSection(tabReads.sportCards), [tabReads.sportCards]);
  const linkRate = useMemo(() => linkRateSection(reads.linkRate), [reads.linkRate]);
  const si = useMemo(() => sourceIntelligenceSection(tabReads.sourceIntelligence), [tabReads.sourceIntelligence]);

  // A panel mounts the first time its tab is shown and then stays mounted
  // (hidden), so its filters and expanded sections survive a tab switch.
  const shown = (t: ConsoleTab) => t === tab || visited.has(t);
  const panels = {
    matching: shown("matching") ? (
      <MatchingTabPanel
        matured={matured}
        sportCards={sportCards}
        linkRate={linkRate}
        nowMs={nowMs}
        authNotice={<AdminAuthNotice />}
      />
    ) : null,
    source_intelligence: shown("source_intelligence") ? (
      <SourceIntelligenceTabPanel si={si} nowMs={nowMs} authNotice={<AdminAuthNotice />} />
    ) : null,
  };

  return (
    <CorrectnessConsoleView
      tiles={tiles}
      nowMs={nowMs}
      settledMs={settledMs}
      authNotice={<AdminAuthNotice />}
      onReload={reload}
      tabs={{ active: tab, onSelect: selectTab, panels }}
    />
  );
}
