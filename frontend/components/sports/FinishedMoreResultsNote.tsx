"use client";

import React from "react";

import type { LeagueResultsLink } from "@/lib/sports/finishedSection";

/**
 * The line under the /sports Finished section: where the results this section
 * could not show are.
 *
 * ═══ WHY IT NO LONGER SAYS "THE 4 MOST RECENT" (#5860) ═══
 *
 * It used to read *"Showing the 4 most recent — more in NCAA Football, MLS and
 * MLB."* The second half is true; the first half is a claim about every
 * finished game in the world, and the section cannot make it.
 *
 * `buildFinishedSection` sorts by `ended_at` correctly — the ORDER inside the
 * section is recency and is not what changed here. The defect is the POOL it
 * sorts: page one plus the deferred `limit=40&mode=sports` lookup, both ordered
 * by feed SCORE. Measured on production 2026-09-13 08:55Z, that window's most
 * recently ended game was América–Cruz Azul at 05:44Z, while five games had
 * ended after it — Hawaii 07:24Z, USC 06:16Z, and Utah, Fresno State and Nevada
 * at 06:01Z — none of them in the window at all. So the caption named four
 * Saturday-afternoon finals "the most recent" on a Sunday morning whose whole
 * late college slate was missing.
 *
 * A caption that names an ORDER is only true if the POOL was selected by that
 * order, not merely sorted by it. Widening the window does not fix it: #4454
 * already went 20 → 40 for this reason and a score window buries finals again
 * the next night that produces enough high-scoring cards. The pool half — a
 * recency-ordered finals arm — is the backend arm of #5860 and is not this
 * lane's file set (notice 41).
 *
 * ═══ AND NO LINKS MEANS NO LINE ═══
 *
 * The note exists to lead somewhere (UX-P062 E5). With every capped-out league
 * missing from the register there is no destination left, and "there are more,
 * somewhere" is diagnostic prose on a reader's screen (notice 34). The count
 * it used to carry is already on the section's own badge.
 */
export function FinishedMoreResultsNote({
  cappedMore,
  links,
}: {
  /** Did the cap actually drop anything? */
  cappedMore: boolean;
  /** League pages holding the dropped results, in payload order. */
  links: LeagueResultsLink[];
}) {
  if (!cappedMore || links.length === 0) return null;

  return (
    <p className="text-micro text-text-muted mt-3" data-testid="finished-cap-note">
      {"More results in "}
      {links.map((link, i) => (
        <span key={link.href}>
          {i > 0 && (i === links.length - 1 ? " and " : ", ")}
          <a href={link.href} className="text-accent-brand hover:underline">
            {link.label}
          </a>
        </span>
      ))}
      .
    </p>
  );
}
