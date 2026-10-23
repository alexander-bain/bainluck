"use client";

import { useLayoutEffect, useState } from "react";
import { trackEvent } from "@/lib/analytics";
import { getDiscoverItemAnalytics, recordDiscoverInteraction, sendDiscoverInteraction } from "@/lib/discoverInteractions";
import type { FeedItem, FeedFuturesData, FeedThemeCollectionRef } from "@/lib/types";
import { BundleActionBar } from "./BundleActionBar";
import { BundleHeader } from "./BundleHeader";
import { bundleExpandLabel, bundleSeatCount } from "./constants";
import { FuturesCard, FuturesCompactRow } from "./FuturesCard";
import { PartyControlRow } from "./PartyControlRow";
import { isCongressControlStoryKey } from "@/lib/discover/partyControlRow";
import {
  CollectionEntryLink,
  admitCollectionRef,
  consumeThemeCollectionReturn,
  rememberThemeCollectionReturn,
} from "./shared";

interface ThemeBundleCardProps {
  items: FeedItem[];
  title: string;
  /**
   * The one sentence saying why these members belong together (D1 clause c,
   * #4066) — "Who wins in 2028?", not "2 related". Absent only on a cached
   * payload built before the backend served it; the header then falls back to
   * the old count rather than rendering a blank line.
   */
  sharedQuestion?: string | null;
  storyKey?: string | null;
  positionIndex?: number;
  /** The served bundle id: names this card when the reader comes Back. */
  bundleId?: string;
  /**
   * #9925: the collection page this theme belongs to, when the server proved
   * it. Absent ⇒ no link, and the card is exactly what it was.
   */
  collectionRef?: FeedThemeCollectionRef | null;
}

// Members shown in the collapsed mini-ranked-peek come from `bundleSeatCount`,
// shared with the comparison sibling since #7492 — see `BUNDLE_PEEK_COUNT`.

/**
 * Theme bundle (geopolitics archetype — Phase 1, slice 1).
 *
 * Collapsed: a header (theme label + the group's shared question) over a tight
 * mini-ranked peek of the top members. Expanded: the real member market cards
 * (reuses FuturesCard — no reinvented card). Folds same-conflict scatter into
 * one slot.
 *
 * D1 clause c (#4066): the header's second line used to read "· 2 related".
 * Seven of the twenty items served on 2026-09-08 were bundles and all seven said
 * exactly that — a count of what is behind the chevron, which is navigation, not
 * a reason to read. It now carries the question the members are all answers to.
 * The count has not been lost: the peek rows beneath are the members, and
 * the footer ("All N markets", #10877) still prints it.
 */
export function ThemeBundleCard({ items, title, sharedQuestion, storyKey, positionIndex, bundleId, collectionRef }: ThemeBundleCardProps) {
  const [expanded, setExpanded] = useState(false);
  const collection = admitCollectionRef(collectionRef);

  // #9925: a reader who opened the collection from this card and came Back
  // finds it as they left it. A layout effect (not a lazy initializer, which
  // would mismatch the server render) so the card is at full height before the
  // page lands the restored scroll offset.
  useLayoutEffect(() => {
    if (bundleId && consumeThemeCollectionReturn(bundleId)) setExpanded(true);
  }, [bundleId]);
  const primary = items[0];
  const cat = primary?.type === "futures" ? (primary.data as FeedFuturesData).llm_sport_category : null;
  const analytics = primary ? getDiscoverItemAnalytics(primary) : { category: "geopolitics" };
  const peek = items.slice(0, bundleSeatCount(items.length));

  const toggleExpanded = () => {
    const next = !expanded;
    setExpanded(next);
    if (next) {
      trackEvent("theme_bundle_expand", {
        ...analytics,
        story_key: storyKey,
        member_count: items.length,
        position: positionIndex,
        surface: "discover",
      });
      recordDiscoverInteraction(analytics.category, "group_expand");
      sendDiscoverInteraction(analytics, "group_expand", positionIndex);
    }
  };

  // No analytics event of its own, like the hub card it mirrors
  // (`DiscoverCollectionCard`): a new event name needs the typed map and the
  // sanitizer allowlist, or its keys are stripped in silence.
  const openCollection = () => {
    if (bundleId) rememberThemeCollectionReturn(bundleId, expanded);
  };

  return (
    <div className="rounded-2xl border border-surface-border bg-surface-card shadow-lg overflow-hidden">
      <BundleHeader
        title={title}
        sharedQuestion={sharedQuestion}
        fallbackCount={`· ${items.length} related`}
        category={cat}
        expanded={expanded}
        canExpand
        onToggle={toggleExpanded}
      />

      {/* Collapsed: mini-ranked-peek */}
      {!expanded && (
        <>
          <div className="divide-y divide-surface-border border-t border-surface-border">
            {peek.map((member, i) => (
              <div key={i} className="px-4 py-3">
                {member.type === "futures" ? (
                  isCongressControlStoryKey(storyKey) ? (
                    <PartyControlRow member={member} data={member.data as FeedFuturesData} />
                  ) : (
                    <FuturesCompactRow item={member} data={member.data as FeedFuturesData} />
                  )
                ) : (
                  <div className="text-sm font-semibold text-text-primary line-clamp-2">{member.headline || "Market"}</div>
                )}
              </div>
            ))}
          </div>
          <button
            onClick={toggleExpanded}
            className="w-full text-center py-2.5 text-xs font-medium text-accent-brand hover:text-accent-brand/80 border-t border-surface-border"
          >
            {items.length > peek.length ? bundleExpandLabel(items) : "Expand"}
          </button>
        </>
      )}

      {/* Expanded: the real member cards */}
      {expanded && (
        <div className="p-3 space-y-3 bg-surface-elevated/30 border-t border-surface-border">
          {items.map((member, i) => (
            <ThemeBundleMember key={i} member={member} />
          ))}
        </div>
      )}

      {/* #9925 — outside both branches too: the whole collection is one tap
          away whether the reader is peeking or reading every member. */}
      {collection && <CollectionEntryLink entry={collection} onOpen={openCollection} />}

      {/* #4428 — OUTSIDE both branches, so the bundle has a Like and a Share in
          either state. Collapsed it was the only thing in the subtree that could
          have carried one (no member card is mounted); expanded, the members'
          own bars can only act on a member, never on the group the header names.
          It sits on the card's own background rather than inside the expanded
          block's tint, which is what makes it read as the bundle's footer and
          not as a sixth member's. */}
      <BundleActionBar
        items={items}
        title={title}
        sharedQuestion={sharedQuestion}
        storyKey={storyKey}
        positionIndex={positionIndex}
      />
    </div>
  );
}

// Renders a single member as its real market card (reuses FuturesCard with local
// like state; non-futures members fall back to a compact row).
function ThemeBundleMember({ member }: { member: FeedItem }) {
  const [liked, setLiked] = useState(false);
  if (member.type === "futures") {
    return (
      <FuturesCard
        item={member}
        data={member.data as FeedFuturesData}
        liked={liked}
        setLiked={setLiked}
        trending={false}
      />
    );
  }
  return (
    <div className="rounded-xl border border-surface-border bg-surface-card px-4 py-3">
      <div className="text-sm font-semibold text-text-primary line-clamp-2">{member.headline || "Market"}</div>
    </div>
  );
}
