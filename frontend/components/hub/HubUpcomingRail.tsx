/**
 * The `upcoming` rail on a hub landing page (/hub/mma, /hub/boxing, /hub/golf,
 * /hub/tennis) — its heading and the cards under it.
 *
 * ── WHY THIS IS ITS OWN FILE (UX-P210, repairing CERT-525) ───────────────────
 *
 * The heading and the cards were both inline in `app/hub/[competition]/page.tsx`.
 * CERT-525 blocked the branch because the heading claims a phase the cards
 * underneath it may not be in, and asked for "a page/section-level render guard
 * with an `unknown` tennis card proving no visible Upcoming claim surrounds it".
 *
 * That guard is only meaningful if it renders the real section: heading and
 * cards composed the way production composes them. A route file exports only
 * the reserved names, so nothing inside one can be imported and rendered by a
 * test — the same reason `HubStatusPill` had to move out in UX-P209. Testing a
 * heading component in isolation would prove the heading's own text and say
 * nothing about what SURROUNDS the card, which is the finding.
 *
 * So the section is a component, `__tests__/components/hubUpcomingRail.test.tsx`
 * renders it, and the claim under test is the one a reader actually sees.
 *
 * The phase rule itself lives in `lib/hubUpcomingHeading.ts` — read its header
 * for why the client decides and what every failure path falls back to.
 */

import Link from "next/link";
import type { HubUpcoming } from "@/lib/api";
import { eventPath } from "@/lib/eventKey";
import { StatusPill } from "@/components/hub/HubStatusPill";
import { hubUpcomingHeading } from "@/lib/hubUpcomingHeading";

function formatDate(iso: string | null): string {
  if (!iso) return "";
  const d = new Date(iso);
  if (isNaN(d.getTime())) return "";
  return d.toLocaleDateString(undefined, { weekday: "short", month: "short", day: "numeric" });
}

export function UpcomingCard({ card }: { card: HubUpcoming }) {
  return (
    <Link
      href={eventPath(card.key)}
      className="group flex-shrink-0 w-64 bg-surface-card border border-surface-border rounded-2xl p-4 transition-colors hover:border-accent-brand/50 hover:bg-surface-elevated"
    >
      <div className="flex items-center justify-between mb-2">
        <StatusPill status={card.status} />
        {card.is_major && (
          <span className="text-[10px] font-bold uppercase tracking-wide text-accent-brand">★ Marquee</span>
        )}
      </div>
      <div className="text-[15px] font-semibold text-text-primary leading-snug line-clamp-2 min-h-[2.6em]">
        {card.name}
      </div>
      <div className="mt-3 flex items-center justify-between text-xs text-text-muted">
        <span>{formatDate(card.start_date) || "TBD"}</span>
        {typeof card.fight_count === "number" && card.fight_count > 0 && (
          <span className="font-mono">{card.fight_count} fights</span>
        )}
      </div>
    </Link>
  );
}

export function HubUpcomingRail({
  cards,
  label,
  neutralLabel,
}: {
  cards: HubUpcoming[];
  label?: string | null;
  neutralLabel?: string | null;
}) {
  if (!cards.length) return null;

  // Decided against the cards being RENDERED, not the payload — see the helper.
  const heading = hubUpcomingHeading(cards, { label, neutralLabel });

  return (
    <section className="mb-12" data-testid="hub-upcoming-rail">
      {/* UX-P167 (#2167): "Cards" is combat vocabulary. A slam and a major are
          tournaments, and this rail printed "Upcoming Cards" over 12 tennis and
          3 golf ones.
          UX-P210 (CERT-525): and the "Upcoming" half of it is a phase claim
          about every card below, so it is withheld unless every one of them is
          upcoming. `heading` is null when there is no honest word available;
          the rail then carries none, which is not a claim. */}
      {heading && (
        <h2
          className="text-[11px] font-bold tracking-[0.12em] text-text-muted uppercase mb-3"
          data-testid="hub-upcoming-heading"
        >
          {heading}
        </h2>
      )}
      <div className="flex gap-3 overflow-x-auto pb-2 -mx-1 px-1">
        {cards.map((c) => (
          <UpcomingCard key={c.key} card={c} />
        ))}
      </div>
    </section>
  );
}
