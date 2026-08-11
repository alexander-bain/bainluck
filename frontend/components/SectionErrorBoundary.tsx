"use client";

import React from "react";
import ErrorBoundary from "./ErrorBoundary";

interface Props {
  children: React.ReactNode;
  /**
   * Names the missing part in the fallback ("Player props couldn't be shown").
   * Omit it and the fallback stays generic rather than guessing.
   */
  label?: string;
  /** Forwarded to ErrorBoundary — changing it retries a section that failed. */
  resetKey?: unknown;
}

/**
 * UX-P055 (#1722's class) — one section's bad data must not take the page.
 *
 * The event page opened ONE boundary around its entire body, so a throw
 * anywhere inside replaced the hero, the chart, the props and the route with a
 * single "Something went wrong". #1722 proved that is reachable from ordinary
 * production data: an unpriced prop row killed `/events/15191146` outright.
 * This is gotcha #42 one level up — one bad ITEM wiping a whole PASS, where the
 * pass is the page.
 *
 * Deliberately a DELEGATION, not a second boundary implementation. This lane
 * has filed the same drift nine times (#1620): the moment two components both
 * implement catching, they diverge. `ErrorBoundary` stays the only class that
 * catches; this supplies the section-scale fallback and nothing else.
 *
 * The fallback is quiet and HONEST. It does not borrow the route-level alarm
 * language, because a missing props table is not a dead page — but it also
 * never renders a plausible-looking empty state, which would tell the reader
 * "there is nothing here" when the truth is "we could not show it".
 */
export default function SectionErrorBoundary({ children, label, resetKey }: Props) {
  return (
    <ErrorBoundary
      resetKey={resetKey}
      fallback={
        <div className="py-6 text-center">
          <p className="text-text-secondary text-sm">
            {label ? `${label} couldn't be shown.` : "This section couldn't be shown."}
          </p>
          <p className="text-text-muted text-xs mt-1">
            The rest of the page is unaffected.
          </p>
        </div>
      }
    >
      {children}
    </ErrorBoundary>
  );
}
