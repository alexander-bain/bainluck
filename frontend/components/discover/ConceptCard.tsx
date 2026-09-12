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
import { conceptHeadlineBout } from "@/lib/eventConceptDisplay";
import { DismissBtn, ActionBar, dismissCornerBadge } from "./shared";
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
  // ux/1070 item 2: the main event of a fight card, as a bout — two names, two
  // numbers, the date. Same resolver as the Sports-tab card, so the two
  // surfaces cannot print one fight two ways.
  const bout = conceptHeadlineBout(data);
  const leader =
    !whatHit && !bout && data.leader && (data.leader.name ?? "").trim() &&
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
        {/* #3777: these two pills and `DismissBtn` both claimed `top-3 right-3`,
            and the button wins on `z-10` — the `● Live` pill rendered as `● L`
            with the word under the button. `dismissCornerBadge` steps them onto
            the same 48px line `TrendBadge` already uses. */}
        {whatHit && (
          <div className={`absolute top-3 ${dismissCornerBadge(onDismiss)} bg-white/20 text-white text-[10px] font-bold uppercase tracking-wider px-2.5 py-1 rounded-full`}>
            🏁 Final
          </div>
        )}
        {isLive && (
          <div className={`absolute top-3 ${dismissCornerBadge(onDismiss)} flex items-center gap-1 bg-white/20 text-white text-[10px] font-bold uppercase tracking-wider px-2.5 py-1 rounded-full`}>
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
            {/* #3989: the same duplicate as the unsettled branch below — the
                body <h3> already names the concept. `feedItemSuppressionReason`
                admits a settled card only on a winner OR a summary, and this is
                the winner-less arm, so `resultSummary` is what the hero has to
                say here; the name comes back only if that guarantee ever fails,
                so a fixed `h-44` hero can never go blank. */}
            {!resultSummary && (
              <div className="text-white text-xl font-black tracking-tight drop-shadow-lg">
                {data.name}
              </div>
            )}
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
                queue is already closing twice over.
                #3989: now the hero's main line rather than a footnote under a
                title, so it is sized to be read. */}
            {resultSummary && (
              <div className="text-white/90 text-sm mt-1.5 px-2">{resultSummary}</div>
            )}
          </>
        ) : (
          <>
            {/* #3989: this hero printed `data.name` and the body <h3> below
                printed it AGAIN, ~100px apart, on every unsettled concept the
                feed can admit — production read two leaf nodes both reading
                exactly `Vuelta a España 2026`. The sibling `TournamentCard`
                this card was modeled on never does that: its hero carries the
                NUMBER, its body carries the name, once. The hero now names the
                concept only when it has nothing else to say.
                `feedItemSuppressionReason` admits an unsettled concept ONLY on
                a usable bout or a usable leader, so this fallback is a backstop
                against this renderer reading the payload more strictly than the
                gate that let the card in — never the normal path — and it is
                what keeps a fixed `h-44` hero from rendering blank. */}
            {!bout && !leader && (
              <div className="text-white text-2xl font-black tracking-tight drop-shadow-lg">
                {data.name}
              </div>
            )}
            {/* #1939: the favourite, rendered ONLY on the unsettled branch. The
                WHAT-HIT arms above take precedence, so a result can never be
                displaced by a stale probability even if a future payload carried
                both — "settled means settled". Mirrors the native concept card's
                grammar (name · probability chip · movement · "of N") so the two
                surfaces print the same fact the same way. */}
            {bout && (
              <div className="mt-2 w-full max-w-[260px] space-y-1">
                {bout.sides.map((side) => (
                  <div
                    key={side.name}
                    className="flex items-center justify-between gap-3"
                  >
                    <span className="text-white text-sm font-bold drop-shadow truncate">
                      {side.name}
                    </span>
                    <span className="bg-white/20 text-white text-[11px] font-bold px-2 py-0.5 rounded-full flex-shrink-0 tabular-nums">
                      {side.percent}%
                    </span>
                  </div>
                ))}
                {bout.dateLabel && (
                  <div className="text-white/70 text-[11px] text-center pt-0.5">
                    {bout.dateLabel}
                  </div>
                )}
              </div>
            )}
            {leader && (
              <>
                {/* #3989: with the redundant title gone, the probability takes
                    the hero — `TournamentCard`'s grammar, and the right emphasis
                    for a probability-first product. Deliberately NOT
                    `AnimatedProbability`: that component prints an em-dash until
                    an IntersectionObserver fires (so "—" in SSR) and splits the
                    "%" into a child span, which would break both the reading and
                    every `toContain("75%")` assertion on this card. */}
                <div className="text-white text-5xl font-black tabular-nums tracking-tight drop-shadow-lg">
                  {Math.round(leader.probability * 100)}%
                </div>
                <div className="mt-1 flex items-center justify-center flex-wrap gap-1.5">
                  <span className="text-white text-sm font-bold drop-shadow">
                    {leader.name}
                  </span>
                  {movementLabel && (
                    <span className="text-white/85 text-[11px] font-bold">
                      {movementLabel}
                    </span>
                  )}
                  {/* A 52% favourite in a two-way fight and a 52% favourite in a
                      30-rider field are different facts. Only worth saying when
                      the field is bigger than a head-to-head.
                      #3989: the bare `of 30` read aloud as "seventy-five percent
                      OF THIRTY" — an arithmetic claim (22.5), not a field size.
                      The noun is the whole fix. */}
                  {typeof leader.field_size === "number" && leader.field_size > 2 && (
                    <span className="text-white/70 text-[11px]">
                      field of {leader.field_size}
                    </span>
                  )}
                </div>
              </>
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
          // #5778 — the same prop a futures card passes (#5752), from the same
          // path. `PriceAgeMark` decides whether to draw: nothing inside 30
          // minutes, nothing for a price we cannot date. The measured specimen
          // is this card: the Vuelta GC field led Discover at 96% under a LIVE
          // pill on a price 5h01m old.
          priceObservedAt={data.price_observed_at}
        />
      </div>
    </div>
  );
}
