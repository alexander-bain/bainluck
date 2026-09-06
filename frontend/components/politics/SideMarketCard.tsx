/** The "Other markets" side card on /politics.
 *
 *  Lifted out of `app/politics/page.tsx` by #3700, following the UX-P187
 *  precedent and for the same reason: a Next.js route file may only export the
 *  reserved names, so nothing declared inside one can be driven by a test.
 *  Exporting it in place fails `npm run typecheck` at
 *  `.next/types/app/politics/page.ts`.
 *
 *  Moved verbatim apart from the label, which is the fix.
 */
import Link from "next/link";
import type { PoliticsMarketRow } from "@/lib/api";
import { SourceBadge } from "@/components/politics/atoms";
import s from "@/app/politics/politics.module.css";

export function SideMarketCard({ market }: { market: PoliticsMarketRow }) {
  const leader = market.top_outcomes?.[0];

  // #3700 — the label names the outcome the NUMBER beside it belongs to, and
  // it comes from the payload rather than from a threshold.
  //
  // This used to be `isBinary ? (market.prob >= 50 ? "Yes" : "No") : leader.name`,
  // deriving the label from `prob >= 50` and then printing `prob` unchanged,
  // never taking the complement. The label therefore always claimed the
  // majority side while the number could be the minority one:
  //
  //     Trump goes to space in 2026?
  //     No                                    2%
  //
  // which tells a reader there is a 98% chance he does. The market said 2% Yes.
  // It broke both directions — a genuine "No 71%" rendered as "Yes 71%" too.
  //
  // `market.prob === top_outcomes[0].prob`, so the number is the LEADER's and
  // the leader already carries its own name. The threshold also swept up
  // single-outcome ladder rungs (`outcome_count <= 2`), relabelling
  // "December 31, 2026" as "No" and discarding the only informative thing on
  // the card.
  const label = leader?.name || "—";

  return (
    <Link href={`/futures/${market.market_id}`}>
      <div className={s.sideCard}>
        <div className={s.sideQ}>{market.q}</div>
        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "baseline" }}>
          <span style={{ fontSize: 13, fontWeight: 500, color: "var(--text-secondary)", overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
            {label}
          </span>
          <span className={s.probNum} style={{ fontSize: 16, color: "var(--text-primary)" }}>
            {Math.round(market.prob)}%
          </span>
        </div>
        <SourceBadge source={market.src} />
      </div>
    </Link>
  );
}
