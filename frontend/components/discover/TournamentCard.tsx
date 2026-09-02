"use client";

import Link from "next/link";
import { buildDiscoverShareUrl, formatShareProbability } from "@/lib/share";
import { tournamentEventKey, eventPath } from "@/lib/eventKey";
import { formatTournamentTimingLabel } from "@/lib/gameTimeLabel";
import { toTitleCaseAcronymSafe } from "@/lib/titleCase";
import type { FeedTournamentData } from "@/lib/types";
import { AnimatedProbability, DismissBtn, ActionBar, MovementBadge } from "./shared";

interface TournamentCardProps {
  data: FeedTournamentData;
  liked: boolean;
  setLiked: (v: boolean) => void;
  onDismiss?: () => void;
  onDetailClick?: () => void;
  onShare?: () => void;
}

export function TournamentCard({ data, liked, setLiked, onDismiss, onDetailClick, onShare }: TournamentCardProps) {
  // UX-P050: the feed derives this name by title-casing a snake_case tournament
  // key, which lowercases every acronym on the way — three of the eight cards on
  // the default landing page read "Golfers To Win A Pga Tour Major …". The
  // acronym-safe caser already existed (`lib/titleCase.ts`, PGA and LPGA already
  // in its allowlist) and no feed card had ever called it; the sixth instance of
  // the #1620 shape on this lane. It repairs the CASE only — the lost apostrophe
  // and duplicated suffix in "Aig Women S Open Womens" are damage baked into the
  // key upstream, and guessing them back client-side is not a display fix.
  const title = toTitleCaseAcronymSafe(data.name) || data.name;
  const leader = data.golfers?.[0];
  const leaderProbability = formatShareProbability(leader?.probability);
  // L2-159 / #235 Item 4: just-settled marquee tournament (T+36h WHAT-HIT window)
  // leads result-first — the leader is the CHAMPION, live movement is suppressed,
  // settled-means-settled grammar ("cards show results").
  const whatHit = data.marquee_whathit === true;
  const shareText = leader && whatHit
    ? `${leader.name} won ${title} on Bain Luck.`
    : leader && leaderProbability
    ? `${leader.name} is at ${leaderProbability} in ${title} on Bain Luck.`
    : `Track ${title} on Bain Luck.`;
  // L2-65: route into the event concept page (/event/[key]) — the richer surface
  // (race chart + leaderboard + matchups) — falling back to the sport page.
  const eventKey = tournamentEventKey(data);
  const href = eventKey ? eventPath(eventKey) : "/sport/golf";
  // UX-P049: this card carried no date in any branch, so a tournament three days
  // out and one that teed off two days ago read identically on the default
  // landing page. Suppressed ("") for a timestamp too stale to be a start date —
  // see the module for why that window exists. A settled marquee already leads
  // with its champion, so it does not also need a start date.
  //
  // UX-P050: and when there is no honest START date, the card falls back to when
  // the question is DECIDED. Three of the eight cards on the landing page said
  // nothing at all, two of them season-long markets resolving in Dec 2026 and
  // Jul 2030 — `resolution_date` was on the wire on 8 of 8 and read in no branch.
  //
  // UX-P267 (#2549): and `start_date` was on the wire too, unread, while this
  // card printed "Started Mon, Aug 31" over a payload that said
  // `start_date: 2026-09-03` and `schedule_status: "upcoming"`. The schedule now
  // leads; `commence_time` and its trust windows stay exactly as they were, for
  // the cards that have no schedule. See the module for the expired premise.
  const whenLabel = whatHit
    ? ""
    : formatTournamentTimingLabel(
        data.start_date,
        data.commence_time,
        data.resolution_date,
      );
  return (
    <div className="relative rounded-2xl overflow-hidden border border-surface-border bg-surface-card shadow-lg hover:shadow-xl transition-shadow">
      <DismissBtn onDismiss={onDismiss} />
      <div className="relative h-44 flex flex-col items-center justify-center" style={{ background: "linear-gradient(135deg, #14532d, #166534)" }}>
        <div className="absolute top-3 left-3 bg-lime-600/15 text-lime-700 text-[10px] font-bold uppercase tracking-wider px-2.5 py-1 rounded-full">⛳ Golf</div>
        {whatHit && (
          <div className="absolute top-3 right-3 bg-white/20 text-white text-[10px] font-bold uppercase tracking-wider px-2.5 py-1 rounded-full">🏁 Final</div>
        )}
        {leader && (
          <>
            {whatHit ? (
              <>
                <div className="text-white text-2xl font-black tracking-tight drop-shadow-lg text-center px-4">{leader.name}</div>
                <div className="mt-1.5 bg-white/20 text-white text-[11px] font-bold uppercase tracking-wider px-3 py-1 rounded-full">Champion · Won</div>
              </>
            ) : (
              <>
                <AnimatedProbability value={Math.round((leader.probability ?? 0) * 100)} className="text-5xl font-black text-white tabular-nums drop-shadow-lg" />
                <div className="text-white/70 text-sm mt-1">{leader.name}</div>
                <MovementBadge m={leader.movement_24h} />
              </>
            )}
          </>
        )}
      </div>
      <div className="p-4">
        <Link href={href} onClick={onDetailClick} className="block group">
          <h3 className="font-bold text-lg leading-tight mb-1 group-hover:text-accent-brand transition-colors">{title}</h3>
        </Link>
        {data.venue && <p className="text-sm text-text-secondary">{data.venue}</p>}
        {whenLabel && <p className="text-xs text-text-muted mt-0.5">{whenLabel}</p>}
        <ActionBar
          liked={liked}
          setLiked={setLiked}
          shareUrl={buildDiscoverShareUrl(href, "grid", title)}
          shareTitle={title}
          shareText={shareText}
          contentType="grid"
          // Deliberately the RAW name: `itemId` is the analytics identity for this
          // card, and re-casing it would silently split every existing GA4 series
          // on these tournaments in two. Display is repaired; identity is not.
          itemId={data.name}
          onShare={onShare}
        />
      </div>
    </div>
  );
}
