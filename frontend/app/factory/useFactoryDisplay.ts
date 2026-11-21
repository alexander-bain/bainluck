import { useEffect, useRef, useState } from "react";
import { useRouter } from "next/navigation";
import { normalizeCommitSha } from "@/lib/buildInfo";

const REFRESH_MS = 60_000;
const VERSION_TIMEOUT_MS = 4_000;
const RELOAD_COOLDOWN_MS = 5 * 60_000;
const RELOAD_KEY = "factory-build-reload";

async function latestBuild(signal: AbortSignal) {
  const response = await fetch("/api/frontend-build", { cache: "no-store", signal });
  if (!response.ok) return null;
  const marker: { commit?: unknown } = await response.json();
  return typeof marker?.commit === "string" ? normalizeCommitSha(marker.commit) : null;
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
  canReload: boolean,
  rememberFloor: () => void,
) {
  const router = useRouter();
  const loadedBuild = useRef(buildCommit).current;
  const [now, setNow] = useState(renderedAt);
  const [tabVisible, setTabVisible] = useState(true);
  const [reducedMotion, setReducedMotion] = useState<boolean | null>(null);
  const lastRefresh = useRef(Date.parse(renderedAt));

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
      if (!loadedBuild || !canReload) {
        router.refresh();
        return;
      }

      const controller = new AbortController();
      inFlight = controller;
      deadline = window.setTimeout(() => controller.abort(), VERSION_TIMEOUT_MS);
      void latestBuild(controller.signal).catch(() => null).then((commit) => {
        if (disposed || document.visibilityState !== "visible") return;
        if (commit && commit !== loadedBuild && reloadAllowed(commit, Date.now())) {
          rememberFloor();
          window.location.reload();
        } else {
          router.refresh();
        }
      }).finally(() => {
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
  }, [canReload, loadedBuild, rememberFloor, router]);

  return { now, tabVisible, reducedMotion };
}
