/**
 * "FOR YOU" — WHY THIS CARD IS IN FRONT OF THIS READER.
 *
 * ═══ THE RULING ═══
 *
 * Alex, 2026-09-01 (D-D): personalization made VISIBLE. The feed has reordered
 * itself around a reader's teams, sports and pins since L2-79 and has never
 * once said so, which makes a good boost indistinguishable from a coincidence
 * and a bad one indistinguishable from a bug.
 *
 * ═══ 🔴 THE TRAP, AND IT IS THE WHOLE REASON THIS IS A FILE AND NOT A TERNARY ═══
 *
 * The payload's `personalized: true` is NOT "we boosted this". Its source is
 * `PersonalizationResult.is_personalized = bool(reasons)`
 * (`backend/app/utils/personalization.py`), and `reasons` collects PENALTIES
 * next to bonuses — `sport_nah`, `sport_suppress`, `minor_pro`,
 * `discover_dismiss`, `discover_feature_dislike`, the semantic-dismiss soft
 * penalty. A card the reader's own swipes pushed DOWN carries
 * `personalized: true` with a multiplier below 1.
 *
 * So `{item.personalized && <ForYou/>}` would stamp "for you" on the cards a
 * reader has been telling us to stop showing them. That is worse than no cue:
 * it is the feature saying the opposite of what happened, on the exact cards
 * where the reader is already unhappy.
 *
 * Two independent conditions are therefore required, and neither implies the
 * other:
 *
 *   1. **A positive reason we can NAME.** An uprank token from the vocabulary
 *      below. Unknown tokens do not qualify — a reason we cannot phrase is a
 *      reason we cannot show, and a new backend token appearing here silently
 *      produces no cue rather than a wrong one.
 *   2. **A net uprank.** `multiplier > 1`. A card with `your_team:+0.35` AND
 *      `sport_suppress:-0.50` finished lower than it started; the boost is real
 *      and the sentence "we put this in front of you" is still false.
 *
 * ═══ WHY IT NAMES THE REASON INSTEAD OF SAYING "FOR YOU" ═══
 *
 * The ruling asks for a "for you" cue. A bare "For you" is the version of this
 * that cannot be checked by the person reading it — and the standing feed rule
 * is that deterministic explanations are first-class (CLAUDE.md, Discover feed
 * ranking). "One of your teams" is the same badge with the claim attached, and
 * a reader who disagrees with it now has something specific to disagree with.
 *
 * The reason tokens carry no team NAME (`your_team:0.35`, not
 * `your_team:Lakers:0.35`), so the cue names the CLASS. Naming the class is
 * honest; inventing the name would not be.
 */

import type { FeedItem } from "@/lib/types";

export interface ForYouCue {
  /** The reader-facing sentence fragment, sentence case, no trailing stop. */
  label: string;
  /** The reason token that produced it, for analytics and for a failing test. */
  reasonId: string;
}

/**
 * The uprank vocabulary, in the order a card should prefer them.
 *
 * ORDER IS PRECEDENCE, NOT IMPORTANCE. A card can satisfy several at once —
 * your team, in a sport you follow, that you also pinned. The most SPECIFIC
 * true statement wins, because "you pinned this" tells the reader something
 * "a sport you follow" does not.
 *
 * ⚠️ Every id here must be a token the backend actually emits. The guard
 * `forYouCue.test.ts` pins the list against the reason strings in
 * `app/utils/personalization.py`; a rename there turns it red rather than
 * quietly retiring a cue.
 */
const UPRANK_VOCABULARY: { id: string; label: string }[] = [
  { id: "pinned", label: "You pinned this" },
  { id: "your_team", label: "One of your teams" },
  { id: "your_team_futures", label: "One of your teams" },
  { id: "roster_player", label: "A player on one of your teams" },
  { id: "alma_mater", label: "Your alma mater" },
  { id: "alma_mater_futures", label: "Your alma mater" },
  { id: "local_team", label: "A team near you" },
  { id: "rival_losing", label: "A rival is losing" },
  { id: "rival_playing", label: "A rival of one of your teams" },
  { id: "rival_futures", label: "A rival of one of your teams" },
  { id: "sport_boost", label: "A sport you follow" },
  { id: "discover_interest", label: "A category you follow" },
  { id: "discover_feature_interest", label: "Like others you have opened" },
];

const UPRANK_BY_ID = new Map(UPRANK_VOCABULARY.map((entry) => [entry.id, entry.label]));

/** The vocabulary, exported so a guard can iterate it rather than re-spell it. */
export const FOR_YOU_UPRANK_IDS: readonly string[] = UPRANK_VOCABULARY.map((e) => e.id);

/**
 * Split `your_team:0.35` / `discover_feature_interest:category:golf:0.12`.
 *
 * The id is the FIRST segment and the value the LAST, because the feature
 * tokens carry a variable number of middle segments (the strongest matching
 * feature token, which itself contains colons). Taking `[1]` as the value —
 * the obvious version — reads `category` as the number on exactly the reason
 * whose label is the vaguest, so it would be the last one anybody noticed.
 */
export function parsePersonalizationReason(
  reason: string
): { id: string; value: number } | null {
  const parts = reason.split(":");
  if (parts.length < 2) return null;
  const value = Number(parts[parts.length - 1]);
  if (!Number.isFinite(value)) return null;
  return { id: parts[0], value };
}

/**
 * The cue for a card, or null when there is nothing true to say.
 *
 * Null is the common case and the correct default: an anonymous reader, a card
 * nothing matched, and — the case this function exists for — a card the
 * reader's own behaviour pushed DOWN.
 */
export function forYouCue(item: Pick<FeedItem, "personalized" | "multiplier" | "personalization_reasons">): ForYouCue | null {
  if (!item.personalized) return null;

  // Condition 2 first: it is one comparison and it rejects every downranked
  // card before the vocabulary is consulted at all.
  //
  // ⚠️ `multiplier` is optional in the payload and is only written alongside
  // `personalized`. A missing one is treated as "no net uprank proven", not as
  // 1.0 — an absent number is not evidence of a boost.
  if (typeof item.multiplier !== "number" || !(item.multiplier > 1)) return null;

  const reasons = item.personalization_reasons ?? [];
  for (const { id, label } of UPRANK_VOCABULARY) {
    for (const raw of reasons) {
      const parsed = parsePersonalizationReason(raw);
      if (!parsed || parsed.id !== id) continue;
      // A vocabulary id with a non-positive value is a token that shares its
      // name with a penalty arm. None does today; asserting it costs nothing
      // and means a future signed reason cannot invert a label.
      if (!(parsed.value > 0)) continue;
      return { label, reasonId: id };
    }
  }
  return null;
}
