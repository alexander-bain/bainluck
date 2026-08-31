/**
 * The phase pill on a hub `upcoming` rail card (/hub/mma, /hub/boxing,
 * /hub/golf, /hub/tennis).
 *
 * ── WHY THIS IS ITS OWN FILE (UX-P209, repairing CERT-519) ───────────────────
 *
 * It used to be a local function inside `app/hub/[competition]/page.tsx`. Two
 * reasons it cannot stay there:
 *
 * 1. A Next.js route file may only export the reserved names, so nothing
 *    defined inside one can be imported by a test. The pill was the component
 *    with the false claim in it and it was the one component no guard could
 *    render.
 *
 * 2. `program/ux-148` extracts the same markup into `hub/UpcomingCard.tsx` — a
 *    DIFFERENT file, carrying a verbatim copy of the old catch-all. Two branches
 *    editing disjoint files is exactly the case where a fix disappears on merge
 *    without one conflict marker: whichever order they land in, the surviving
 *    render path is the copy. `__tests__/lib/hubStatusPillSingleHome.test.ts`
 *    is the tripwire — any component that discriminates on a card status and
 *    does not come through here reds the suite.
 *
 * ── THE RULE THE MAPPING ENCODES ─────────────────────────────────────────────
 *
 * Every branch is EXPLICIT and there is no default arm. The blocked version
 * ended `return <span>Upcoming</span>`, so every status the backend had not
 * taught it — including the `unknown` that the tennis rail now emits precisely
 * to say it cannot tell — rendered as a confident "Upcoming". The live US Open
 * announced itself as forthcoming on its third day.
 *
 * Doctrine 1: could-not-check never renders as nothing-to-report. An unrecognised
 * or unknown phase renders NO pill. The card keeps its name, its date and its
 * link; it just stops asserting something nobody established.
 */

/** Statuses this pill is willing to state out loud. Everything else is silence. */
export const AFFIRMATIVE_HUB_STATUSES = ["live", "settled", "upcoming"] as const;

export function StatusPill({ status }: { status: string }) {
  if (status === "live") {
    return (
      <span className="inline-flex items-center gap-1 text-[10px] font-bold uppercase tracking-wide text-accent-live">
        <span className="w-1.5 h-1.5 rounded-full bg-accent-live animate-pulse" />
        Live
      </span>
    );
  }
  if (status === "settled") {
    return <span className="text-[10px] font-semibold uppercase tracking-wide text-text-muted">Final</span>;
  }
  if (status === "upcoming") {
    return <span className="text-[10px] font-semibold uppercase tracking-wide text-accent-brand">Upcoming</span>;
  }
  // `unknown`, or anything a future lister emits that this file has not been
  // taught. Deliberately NOT a default label — see the header. The empty span
  // holds the flex slot so a marquee chip beside it stays where it was; it
  // prints nothing.
  return <span aria-hidden="true" />;
}
