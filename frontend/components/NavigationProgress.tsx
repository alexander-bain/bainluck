"use client";

import { useEffect, useRef } from "react";
import { usePathname, useSearchParams } from "next/navigation";
import NProgress from "nprogress";
import { browserOriginEnv, gameOrigin, questionOrigin } from "@/lib/futuresReturnOrigin";

/**
 * Global top-of-page progress bar for Next.js App Router navigation.
 *
 * Uses NProgress with custom CSS injected inline (no external stylesheet).
 * Hooks into pathname + searchParams changes to show/hide the bar.
 * Wrapped in Suspense at the call site (useSearchParams requirement).
 */

NProgress.configure({ showSpinner: false, minimum: 0.15, trickleSpeed: 200 });

export default function NavigationProgress() {
  const pathname = usePathname();
  const searchParams = useSearchParams();
  const isFirstRender = useRef(true);

  useEffect(() => {
    if (isFirstRender.current) {
      isFirstRender.current = false;
      return;
    }
    NProgress.done();
  }, [pathname, searchParams]);

  useEffect(() => {
    const handleClick = (e: MouseEvent) => {
      const target = (e.target as HTMLElement).closest("a");
      if (!target) return;
      const href = target.getAttribute("href");
      // #10265 / #10317: a tap into a question or game page records which
      // history entry it left, so that page's Back control can prove where it
      // goes (`lib/futuresReturnOrigin.ts`). Each store refuses pages that are
      // not its own; bookkeeping only, it never changes what the progress bar
      // below does, and a failure here must never break the click.
      try {
        const env = browserOriginEnv();
        if (env) {
          const click = {
            href,
            button: e.button,
            metaKey: e.metaKey,
            ctrlKey: e.ctrlKey,
            shiftKey: e.shiftKey,
            altKey: e.altKey,
            target: target.getAttribute("target"),
            download: target.hasAttribute("download"),
          };
          questionOrigin.recordClick(click, env);
          gameOrigin.recordClick(click, env);
        }
      } catch {
        // Bookkeeping failed: the page's Back falls back to its fixed link.
      }
      if (!href || href.startsWith("#") || href.startsWith("http") || href.startsWith("mailto:")) return;
      if (target.getAttribute("target") === "_blank") return;
      if (e.metaKey || e.ctrlKey || e.shiftKey || e.altKey) return;
      if (href !== pathname) {
        NProgress.start();
      }
    };
    document.addEventListener("click", handleClick, { capture: true });
    return () => document.removeEventListener("click", handleClick, { capture: true });
  }, [pathname]);

  return null;
}
