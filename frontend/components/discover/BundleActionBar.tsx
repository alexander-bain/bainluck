"use client";

import { useState } from "react";
import { trackEvent } from "@/lib/analytics";
import { getDiscoverItemAnalytics, recordDiscoverInteraction, sendDiscoverInteraction } from "@/lib/discoverInteractions";
import { heroOutcome } from "@/lib/discover/heroOutcome";
import { formatProbabilityPercent } from "@/lib/probabilityDisplay";
import { renderedLeaderPercent } from "@/lib/renderedPercent";
import { buildBundleShareText, buildDiscoverShareUrl, type BundleShareMember } from "@/lib/share";
import type { FeedItem, FeedFuturesData } from "@/lib/types";
import { ActionBar } from "./shared";

interface BundleActionBarProps {
  items: FeedItem[];
  /** The theme/category chip's text — the header's first line. */
  title: string;
  /** The header's second line: the question the members all answer (D1 clause c, #4066). */
  sharedQuestion?: string | null;
  /** Stable id for the fold, when the backend served one. Theme bundles have it; client-side groups do not. */
  storyKey?: string | null;
  positionIndex?: number;
}

/**
 * The action bar a BUNDLE never had — #4428.
 *
 * Alex, reading Discover on 2026-09-09: grouped cards "have no share". Measured
 * on production page one at 390px that morning: **0 of 5 bundles carried a Share
 * or a Like, against 13 of 14 single cards.** Collapsed, a bundle mounts no
 * member card at all — only `FuturesCompactRow` peek rows — so there was no
 * `ActionBar` anywhere in its subtree. Expanded, each member brought its own, so
 * a reader could share *a member* but never the group the header names, which is
 * the thing they are actually reading.
 *
 * ONE component, rendered by both bundle shapes, rather than a copy in each.
 * #4425 shipped three days of a dead row for exactly the opposite reason: four
 * sibling render branches, three wired and one not. `ThemeBundleCard` and
 * `GroupCard` are the same two-sibling hazard, and the guard pins both.
 *
 * WHAT IT SHARES (issue #4428 option A, the recommended one). A bundle has no
 * detail page, so the URL is `/discover` and the CONTENT is the text: the shared
 * question and how its members currently answer it. `GuessCard` already shares
 * `/discover` this way, so this is the established shape for a card with no
 * permalink, not a new one. Option B — a real `/discover/bundle/{id}` surface —
 * changes where this button POINTS, not whether the bundle has one; it would
 * reuse this component and swap the one `shareUrl` line.
 *
 * The percents are read through the SAME pair of helpers `FuturesCompactRow`
 * prints with (`heroOutcome` then `renderedLeaderPercent`), so a share cannot
 * quote a number the reader is unable to find on the row above it, and an
 * inverted binary is not shared as its No side (UX-P238).
 */
export function BundleActionBar({ items, title, sharedQuestion, storyKey, positionIndex }: BundleActionBarProps) {
  const [liked, setLiked] = useState(false);
  const primary = items[0];
  if (!primary) return null;

  const analytics = getDiscoverItemAnalytics(primary);
  // The header's own sentence, so the share says what the card says. Falls back to
  // the theme chip only on a payload built before the backend carried the question.
  const question = sharedQuestion || title;
  // No id of its own: the fold's story key when the backend served one, else the
  // primary member's, which is what every other rail already keys this fold on.
  const shareId = storyKey || analytics.item_id;
  const shareUrl = buildDiscoverShareUrl("/discover", "futures", shareId);
  const shareText = buildBundleShareText(question, items.map(bundleShareMember), items.length);

  // `story_key` + `member_count` are what separate a BUNDLE's own like/share
  // from a member's: `FuturesCard` logs the same event name and never sends
  // either. They are not decoration and not a new param — both already survive
  // the sanitation boundary (`analytics/sanitize.ts`, `ALLOWED_PARAM_KEYS`),
  // which a `card_scope: "bundle"` of my own would NOT have: an unregistered key
  // is stripped there silently, which is how every My Stuff latency packet was
  // dropped for the life of the surface (L2-217).
  const track = (action: "like" | "unlike" | "share") => {
    trackEvent("feed_card_action", {
      action,
      ...analytics,
      story_key: storyKey ?? undefined,
      member_count: items.length,
      position: positionIndex,
      surface: "discover",
    });
    recordDiscoverInteraction(analytics.category, action);
    sendDiscoverInteraction(analytics, action, positionIndex, "bundle");
  };

  return (
    <div className="px-4 pb-3" data-testid="bundle-action-bar">
      <ActionBar
        liked={liked}
        setLiked={(next) => {
          setLiked(next);
          track(next ? "like" : "unlike");
        }}
        shareUrl={shareUrl}
        shareTitle={question}
        shareText={shareText}
        contentType="futures"
        itemId={shareId}
        onShare={() => track("share")}
      />
    </div>
  );
}

/** A member reduced to what the share sentence can say about it. */
function bundleShareMember(member: FeedItem): BundleShareMember {
  if (member.type !== "futures") {
    return { name: member.headline || "Market", leaderLabel: null, percent: null };
  }
  const data = member.data as FeedFuturesData;
  const leader = heroOutcome(data.top_outcomes);
  const prob = leader?.probability;
  // `> 0` and not just non-null: the row itself renders an em dash for a zero
  // (FuturesCard.tsx, `FuturesCompactRow`), and an em dash is not a share sentence.
  if (!leader || prob == null || !(prob > 0)) {
    return { name: data.name, leaderLabel: null, percent: null };
  }
  return {
    name: data.name,
    leaderLabel: leader.name,
    percent: formatProbabilityPercent(prob, { rendered: renderedLeaderPercent(data.top_outcomes, leader) }),
  };
}
