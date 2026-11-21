import { useEffect, useRef, useState } from "react";
import { normalizeCommitSha } from "@/lib/buildInfo";
import type { FactoryDisplayReading } from "./displayReading";

const REFRESH_MS = 60_000;
const READING_TIMEOUT_MS = 12_000;
const RELOAD_COOLDOWN_MS = 5 * 60_000;
const RELOAD_KEY = "factory-build-reload";

async function readFloor(signal: AbortSignal): Promise<FactoryDisplayReading> {
  const response = await fetch("/factory/reading", { cache: "no-store", signal });
  if (!response.ok) throw new Error("Factory reading failed");
  const reading: FactoryDisplayReading = await response.json();
  if (typeof reading?.readFailed !== "boolean" || !Number.isFinite(Date.parse(reading.renderedAt))) {
    throw new Error("Factory reading was invalid");
  }
  return reading;
}

function reloadAllowed(commit: string, now: number) {
  try {
    const [previousCommit, previousAt] = (sessionStorage.getItem(RELOAD_KEY) ?? "").split("/");
    if (previousCommit === commit && now - Number(previousAt) < RELOAD_COOLDOWN_MS) return false;
    sessionStorage.setItem(RELOAD_KEY, `${commit}/${now}`);
  } catch {
    // A browser without storage can still check for a newer build next minute.
  }
  return true;
}

export function useFactoryDisplay(
  renderedAt: string,
  buildCommit: string | null,
  rememberFloor: () => void,
  onReading: (reading: FactoryDisplayReading) => void,
) {
  const loadedBuild = useRef(buildCommit).current;
  const remember = useRef(rememberFloor);
  const lastReading = useRef<FactoryDisplayReading>();
  const [now, setNow] = useState(renderedAt);
  const [tabVisible, setTabVisible] = useState(true);
  const [reducedMotion, setReducedMotion] = useState<boolean | null>(null);
  const lastRefresh = useRef(Date.parse(renderedAt));

  useEffect(() => {
    remember.current = rememberFloor;
  }, [rememberFloor]);

  useEffect(() => {
    const preference = window.matchMedia("(prefers-reduced-motion: reduce)");
    const preferenceChanged = () => setReducedMotion(preference.matches);
    let inFlight: AbortController | null = null;
    let deadline: number | undefined;
    let disposed = false;

    function refresh() {
      const visible = document.visibilityState === "visible";
      setTabVisible(visible);
      if (!visible) return;
      const current = Date.now();
      setNow(new Date(current).toISOString());
      if (current - lastRefresh.current < REFRESH_MS || inFlight) return;
      lastRefresh.current = current;
      const controller = new AbortController();
      inFlight = controller;
      deadline = window.setTimeout(() => controller.abort(), READING_TIMEOUT_MS);
      void readFloor(controller.signal).then(
        reading => {
          if (disposed || document.visibilityState !== "visible") return;
          const commit = typeof reading.buildCommit === "string"
            ? normalizeCommitSha(reading.buildCommit) : null;
          if (loadedBuild && commit && commit !== loadedBuild && reading.data &&
              !reading.readFailed && reloadAllowed(commit, Date.now())) {
            remember.current();
            window.location.reload();
            return;
          }
          const previous = lastReading.current;
          const next = reading.snapshotDigest && previous?.snapshotDigest === reading.snapshotDigest
            ? { ...reading, data: previous.data }
            : reading;
          lastReading.current = next;
          onReading(next);
        },
        () => {
          if (disposed || document.visibilityState !== "visible") return;
          onReading({
            data: null,
            lastGoodAt: null,
            readFailed: true,
            buildCommit: loadedBuild,
            snapshotDigest: null,
            renderedAt: new Date().toISOString(),
          });
        },
      ).finally(() => {
        window.clearTimeout(deadline);
        inFlight = null;
      });
    }

    preferenceChanged();
    refresh();
    preference.addEventListener("change", preferenceChanged);
    document.addEventListener("visibilitychange", refresh);
    const interval = window.setInterval(refresh, REFRESH_MS);
    return () => {
      disposed = true;
      inFlight?.abort();
      window.clearTimeout(deadline);
      window.clearInterval(interval);
      preference.removeEventListener("change", preferenceChanged);
      document.removeEventListener("visibilitychange", refresh);
    };
  }, [loadedBuild, onReading]);

  return { now, tabVisible, reducedMotion };
}
