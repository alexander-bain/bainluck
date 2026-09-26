"use client";

/**
 * #993 L2-42: renders a backend-composed topical family on /search.
 * headline row prominent; members as inline answers (question · leader +
 * probability · 24h movement arrow ≥2pts · resolution date if <30d). One tap →
 * /futures/{id}. D1: probabilities only — NO odds, NO source/venue names.
 * Design-system tokens only (light mode). Leader-pick + #23 normalization are
 * applied server-side; we display top_outcomes as given — except that a
 * threshold ladder's row prints its rung nearest even (#8834, `leaderOutcome`).
 */

import Link from "next/link";
import type { FuturesFamily, FuturesMarket } from "@/lib/types";
import { formatProbabilityPercent } from "@/lib/probabilityDisplay";
import { outcomeRowVerdict } from "@/components/futures/OutcomeRow";
import {
  leaderOutcome,
  movementArrow,
  resolutionLabel,
  familyRowTitles,
  familySharedHead,
} from "@/components/searchFamilyDisplay";

function AnswerRow({
  market,
  title,
  subject,
  prominent,
  onClick,
}: {
  market: FuturesMarket;
  title: { head: string; tail: string };
  /** #4583: set only when the card hoisted a shared subject into its header, in
   *  which case this row's visible title no longer names the matchup. */
  subject?: string | null;
  prominent?: boolean;
  onClick?: () => void;
}) {
  const ld = leaderOutcome(market);
  // #8640: a leader the venue has already GRADED is a result, not a price.
  // Production 2026-09-25, `/search?q=Fed chair`: the headline read
  // `Kevin Warsh >99%` over a leg served `is_winner: true, resolution_source:
  // "api_settlement"` on a market that stays `open` — a settled question
  // printed as a live one. Asked through `outcomeRowVerdict`, the rule the
  // futures card and page already use, not a second copy: an open market earns
  // only the authoritative `won` arm, a retraction or a served-null source
  // earns nothing, and an absent `resolution_source` (an older payload) keeps
  // today's price.
  const verdict = ld ? outcomeRowVerdict(ld, market.status === "resolved") : null;
  const arrow = ld && verdict === null ? movementArrow(ld.movement) : null;
  const reso = resolutionLabel(market.resolution_date);
  const nameClass = prominent
    ? "text-sm font-medium text-text-primary"
    : "text-sm text-text-secondary";
  return (
    <Link
      href={`/futures/${market.id}`}
      onClick={onClick}
      className="flex flex-wrap sm:flex-nowrap items-center gap-x-2 gap-y-0.5 px-3 py-2 hover:bg-surface-elevated transition-colors"
    >
      {/* #4583: when the card lifted the shared matchup into its header, this
          link's visible text no longer says which game it is about. Sighted
          readers get that from the header directly above; a screen reader
          moving link-to-link does not, so the subject stays in the accessible
          name here. `sr-only` is position:absolute, so it is not a flex item
          and neither `gap-2` here nor `gap-1` below reserves any space for it —
          the rendered row is byte-for-byte what it would be without it. Not an
          `aria-label` on the Link: that would REPLACE the whole accessible
          name, dropping the probability the row exists to announce. */}
      {subject && <span className="sr-only">{subject} — </span>}
      {/* #4136: head truncates, tail does not. When `tail` is empty — the
          ordinary case, a row that shares no long prefix with a sibling — this
          is exactly the single truncating div it has always been.

          #4518: the tail used to be `flex-shrink-0` inside a `min-w-0` container
          whose overflow is VISIBLE, so on the one row where the head had already
          collapsed to nothing and the tail STILL did not fit, the tail had no
          room to shrink into and no clip to stop it — it painted straight
          through the outcome text (−26px at 390, −47px at 360, clean by 430).

          What is wanted is an ORDER, not a ratio: the head gives up everything
          before the tail gives up anything. CSS has no "shrink this one first",
          but shrinkage is distributed proportional to `basis × shrink-factor`
          and an item that reaches its min size freezes and hands the remaining
          deficit to the others — so a head factor several orders of magnitude
          above the tail's IS that order, expressed the one way the box model
          offers. The tail keeps `truncate` so that when it finally must give,
          it ellipsises inside its own box instead of over its neighbour.

          Not `overflow-hidden` on the container: that stops the overlap by
          hard-cutting the tail, which silently eats the bytes #4136 exists to
          preserve — a visible bug traded for an invisible one.

          #4545: the space that separates head from tail is a CHARACTER at the
          end of the head (`snapToBoundary` cuts at `sp + 1`), and the head
          truncates — so the moment it does, the space is inside the clipped
          region and the ellipsis lands against the tail: `Roc...8th Inning
          Winner`. What kept rows 2-5 legible was incidental slack between where
          the ellipsis stops and where the head box ends, which varies with the
          string and the font weight; the headline row is `font-medium`, its
          slack is ~0, and it read as one run-on token. `gap-1` makes the
          separation a property of the LAYOUT, which truncation cannot eat.

          On the container, not as a margin on either child, because gap applies
          only BETWEEN siblings: when `tail` is empty the second div is not
          rendered, the container has one child, and the row stays byte-for-byte
          what it is today — the guarantee #4136 rests on. The 4px is absorbed by
          the head (`shrink-[9999]`); if the head has already collapsed the tail
          gives it up by ellipsising inside its own box, which is the designed
          degradation and cannot reintroduce #4518's overlap.

          #7949: all of the above is the DESKTOP row. At phone width the answer
          column leaves the question ~20 characters. The head is what gives way,
          and on a mixed card the head is the subject: production printed
          "Wi… ALCS in the 2026 MLB Playoffs — No 76%" (Red Sox) and
          "Spread: New York … Baltimore Orioles 64%" (Yankees, -1.5 vs -2.5).
          No split point fixes a line that is 20 characters wide. So below `sm`
          the question gets its own full-width line, wrapping to two (~90
          characters at 390px, which covers the served names measured), and
          the answer wraps to a second line, right-aligned by `ml-auto`. head +
          tail are concatenated there, not split: the split only exists to
          choose which bytes a one-line truncation keeps. `hidden` is
          display:none, so a screen reader reads exactly one copy. */}
      <div className={`sm:hidden basis-full min-w-0 line-clamp-2 ${nameClass}`}>
        {title.head}
        {title.tail}
      </div>
      <div className="flex-1 min-w-0 flex items-center gap-1 max-sm:hidden">
        <div className={`truncate shrink-[9999] ${nameClass}`}>{title.head}</div>
        {title.tail && (
          <div className={`truncate shrink ${nameClass}`}>{title.tail}</div>
        )}
      </div>
      {ld && ld.probability != null ? (
        /* #4136: the outcome NAME may be arbitrarily long — production served an
           outcome called "Istanbul 3: Timofey Skatov vs Yanki Erel Set 2 O/U 9.5"
           — and this column used to be `flex-shrink-0`, so one row like that blew
           the name and the date clean off the card. Capped and truncatable, with
           the percentage itself pinned: the reader may lose the outcome's name,
           never the answer. */
        <div className="flex items-center gap-1 ml-auto min-w-0 max-w-[55%] max-sm:max-w-full text-sm">
          <span className="truncate text-text-primary font-medium">{ld.name}</span>
          {/* #7320: this span used to round `ld.probability * 100` inline — a
              second copy of the rounding rule, skipping the boundary clamp that
              UX-P046 owns. (Spelled without the call here on purpose: the
              inventory guard for this surface is a line scan, and a comment
              quoting the expression verbatim would read as a live site.)
              Production 2026-09-20 00:12Z, `/search?q=astros`: the ANSWERS card
              printed `NRFI 100%` over a served `0.9995` on a market that closes
              Sep 26 — certainty claimed for an open question, which is the exact
              render `probabilityDisplay` exists to refuse. The `0%` arm was live
              on the same expression. The `%` moves INSIDE the call because the
              marker and the sign are one string: handed `">99"` with a literal
              `%` after it this span would print `>99%` correctly by luck and
              `<1%` wrongly the moment the other arm fired. */}
          {verdict === "won" ? (
            <span className="flex-shrink-0 text-accent-live font-medium">Won</span>
          ) : verdict === "lost" ? (
            <span className="flex-shrink-0 text-text-muted">Lost</span>
          ) : (
            <span className="flex-shrink-0 text-text-primary font-medium">
              {formatProbabilityPercent(ld.probability)}
            </span>
          )}
          {arrow && (
            <span
              className={`flex-shrink-0 ${arrow.up ? "text-accent-live" : "text-accent-danger"}`}
            >
              {arrow.up ? "↑" : "↓"}
              {arrow.points}
            </span>
          )}
        </div>
      ) : (
        <span className="text-xs text-text-muted flex-shrink-0 ml-auto">
          {market.outcome_count} outcome{market.outcome_count !== 1 ? "s" : ""}
        </span>
      )}
      {reso && <span className="text-xs text-text-muted flex-shrink-0">{reso}</span>}
    </Link>
  );
}

export default function SearchFamilyCard({
  family,
  onRowClick,
}: {
  family: FuturesFamily;
  onRowClick?: (type: "family_headline" | "family_member", marketId: number) => void;
}) {
  // #4136: computed over the WHOLE card, headline included. "Do these two rows
  // look the same?" is a property of the set, so it cannot be decided inside a
  // row — the same market name is fine alone and unreadable beside its sibling.
  const rows = [family.headline, ...family.members];
  const titles = familyRowTitles(rows.map((m) => m.name));
  // #4583: if every row split at the same point, the head is the CARD's subject,
  // not the row's. Show it once above the rows and give each row its whole width
  // for the bytes that tell it apart. `familySharedHead` returns null unless that
  // is unambiguously true, and then this is a no-op and the rows are untouched.
  const sharedHead = familySharedHead(titles);
  const rowTitles = sharedHead
    ? titles.map((t) => ({ head: t.tail, tail: "" }))
    : titles;
  return (
    <div className="bg-surface-card border border-surface-border rounded-lg overflow-hidden">
      <div className="px-3 pt-2 text-xs font-medium text-accent-brand uppercase tracking-wide">
        {family.label}
      </div>
      {sharedHead && (
        <div className="px-3 text-sm font-medium text-text-primary truncate">
          {sharedHead}
        </div>
      )}
      <AnswerRow
        market={family.headline}
        title={rowTitles[0]}
        subject={sharedHead}
        prominent
        onClick={() => onRowClick?.("family_headline", family.headline.id)}
      />
      {family.members.length > 0 && (
        <div className="border-t border-surface-border divide-y divide-surface-border">
          {family.members.map((m, i) => (
            <AnswerRow
              key={m.id}
              market={m}
              title={rowTitles[i + 1]}
              subject={sharedHead}
              onClick={() => onRowClick?.("family_member", m.id)}
            />
          ))}
        </div>
      )}
      {family.more_count > 0 && (
        <div className="px-3 py-1.5 text-xs text-text-muted border-t border-surface-border">
          +{family.more_count} more market{family.more_count !== 1 ? "s" : ""} below
        </div>
      )}
    </div>
  );
}
