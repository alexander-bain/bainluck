"use client";

// L2-166 (Sunday dress rehearsal): the Discover-tab renderer for `concept` feed
// items (UFC cards, F1 Grands Prix, cycling grand tours — event:<domain>:<slug>).
// The backend emits these into the DEFAULT Discover feed (include_events defaults
// true, no sport filter → `_skip_concepts` is False in routes/feed.py), but the
// Discover card switch had no `concept` branch, so a settled marquee concept — the
// Tour de France WHAT-HIT card #241 crowns "Tadej Pogačar — Won" — rendered as an
// EMPTY card on the landing page. This card fixes that seam: it mirrors the
// Sports-tab ConceptFeedCard's result-first grammar (settled-means-settled) in the
// Discover visual system, modeled on the sibling discover/TournamentCard.

import Link from "next/link";
import { buildDiscoverShareUrl } from "@/lib/share";
import { eventPath } from "@/lib/eventKey";
import type { FeedConceptData } from "@/lib/types";
import { DismissBtn, ActionBar } from "./shared";
import { formatConceptMovement } from "./utils";

interface ConceptCardProps {
  data: FeedConceptData;
  liked: boolean;
  setLiked: (v: boolean) => void;
  onDismiss?: () => void;
  onDetailClick?: () => void;
  onShare?: () => void;
}

// Per-domain hero gradient. Honest/neutral chrome — no misleading golf ⛳ styling
// (the TournamentCard's hardcoded golf look). Unknown domains fall back to slate.
const DOMAIN_GRADIENT: Record<string, string> = {
  cycling: "linear-gradient(135deg, #d97706, #f59e0b)", // maillot jaune
  mma: "linear-gradient(135deg, #7f1d1d, #b91c1c)",
  motorsports: "linear-gradient(135deg, #111827, #374151)",
  f1: "linear-gradient(135deg, #111827, #374151)",
};

export function ConceptCard({
  data,
  liked,
  setLiked,
  onDismiss,
  onDetailClick,
  onShare,
}: ConceptCardProps) {
  // L2-159 / #235 Item 4: `marquee_whathit` is true only in the T+36h
  // post-settlement window — the card leads with THE RESULT and wins over any live
  // framing. winner/result_summary are surfaced only where the payload provides
  // them (#1219) — never fabricated.
  const whatHit = data.marquee_whathit === true;
  const isLive = !whatHit && data.status === "live";
  const winner = data.winner?.trim() || null;
  const resultSummary = data.result_summary?.trim() || null;
  // #1939: only read on the unsettled branch (see the render below). Guarded the
  // same way `feedItemSuppressionReason` guards it — the classifier admitted this
  // card on exactly this test, so the renderer must not be laxer than the gate
  // that let it in, or an admitted card can still paint "undefined%".
  const leader =
    !whatHit && data.leader && (data.leader.name ?? "").trim() &&
    typeof data.leader.probability === "number"
      ? data.leader
      : null;
  const movementLabel = formatConceptMovement(leader?.movement_24h);
  const href = eventPath(data.key);
  const domainLabel = (data.domain || "event").toUpperCase();
  const gradient =
    DOMAIN_GRADIENT[(data.domain || "").toLowerCase()] ??
    "linear-gradient(135deg, #1f2937, #374151)";
  const shareText =
    whatHit && winner
      ? `${winner} won ${data.name} on Bain Luck.`
      : `Track ${data.name} on Bain Luck.`;

  return (
    <div className="relative rounded-2xl overflow-hidden border border-surface-border bg-surface-card shadow-lg hover:shadow-xl transition-shadow">
      <DismissBtn onDismiss={onDismiss} />
      <div
        className="relative h-44 flex flex-col items-center justify-center px-4 text-center"
        style={{ background: gradient }}
      >
        <div className="absolute top-3 left-3 bg-white/20 text-white text-[10px] font-bold uppercase tracking-wider px-2.5 py-1 rounded-full">
          {domainLabel}
        </div>
        {whatHit && (
          <div className="absolute top-3 right-3 bg-white/20 text-white text-[10px] font-bold uppercase tracking-wider px-2.5 py-1 rounded-full">
            🏁 Final
          </div>
        )}
        {isLive && (
          <div className="absolute top-3 right-3 flex items-center gap-1 bg-white/20 text-white text-[10px] font-bold uppercase tracking-wider px-2.5 py-1 rounded-full">
            <span className="w-1.5 h-1.5 rounded-full bg-white animate-pulse" />
            Live
          </div>
        )}
        {whatHit && winner ? (
          <>
            <div className="text-white text-2xl font-black tracking-tight drop-shadow-lg">
              {winner}
            </div>
            <div className="mt-1.5 bg-white/20 text-white text-[11px] font-bold uppercase tracking-wider px-3 py-1 rounded-full">
              Champion · Won
            </div>
            {resultSummary && (
              <div className="text-white/80 text-xs mt-1.5">{resultSummary}</div>
            )}
          </>
        ) : whatHit ? (
          <>
            <div className="text-white text-xl font-black tracking-tight drop-shadow-lg">
              {data.name}
            </div>
            <div className="mt-1.5 bg-white/20 text-white text-[11px] font-bold uppercase tracking-wider px-3 py-1 rounded-full">
              Final result
            </div>
            {/* #1935: the summary was only rendered inside the winner branch
                above, so an ungraded-but-summarised concept printed a title and
                a "Final result" chip and nothing else. `result_summary` is a
                real, authoritative answer when the crown could not be graded —
                the one thing this branch can honestly say. Rendering it here is
                also what lets BOTH surfaces share one admit rule
                (`feedItemSuppressionReason`: winner OR summary); without it web
                would have to encode a narrower rule than native, and a
                divergence between the two classifiers is the defect class this
                queue is already closing twice over. */}
            {resultSummary && (
              <div className="text-white/80 text-xs mt-1.5">{resultSummary}</div>
            )}
          </>
        ) : (
          <>
            <div className="text-white text-2xl font-black tracking-tight drop-shadow-lg">
              {data.name}
            </div>
            {/* #1939: the favourite, rendered ONLY on the unsettled branch. The
                WHAT-HIT arms above take precedence, so a result can never be
                displaced by a stale probability even if a future payload carried
                both — "settled means settled". Mirrors the native concept card's
                grammar (name · probability chip · movement · "of N") so the two
                surfaces print the same fact the same way. */}
            {leader && (
              <div className="mt-2 flex items-center justify-center flex-wrap gap-1.5">
                <span className="text-white text-sm font-bold drop-shadow">
                  {leader.name}
                </span>
                <span className="bg-white/20 text-white text-[11px] font-bold px-2 py-0.5 rounded-full">
                  {Math.round(leader.probability * 100)}%
                </span>
                {movementLabel && (
                  <span className="text-white/85 text-[11px] font-bold">
                    {movementLabel}
                  </span>
                )}
                {/* A 52% favourite in a two-way fight and a 52% favourite in a
                    30-rider field are different facts. Only worth saying when
                    the field is bigger than a head-to-head. */}
                {typeof leader.field_size === "number" && leader.field_size > 2 && (
                  <span className="text-white/70 text-[11px]">
                    of {leader.field_size}
                  </span>
                )}
              </div>
            )}
          </>
        )}
      </div>
      <div className="p-4">
        <Link href={href} onClick={onDetailClick} className="block group">
          <h3 className="font-bold text-lg leading-tight mb-1 group-hover:text-accent-brand transition-colors">
            {data.name}
          </h3>
        </Link>
        <ActionBar
          liked={liked}
          setLiked={setLiked}
          shareUrl={buildDiscoverShareUrl(href, "grid", data.name)}
          shareTitle={data.name}
          shareText={shareText}
          contentType="grid"
          itemId={data.key}
          onShare={onShare}
        />
      </div>
    </div>
  );
}
