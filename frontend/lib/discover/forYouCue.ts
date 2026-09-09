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
  /**
   * What the CHIP prints — #4429. One or two words, sentence case (the chip
   * uppercases in CSS), no article and no verb.
   *
   * Alex, on Discover 2026-09-09: the cue is "far too big — a small mark, not a
   * badge". The chip was already 10px type with 6px/2px padding, so it was never
   * the sizing: `A category you follow` is 21 characters set uppercase with
   * letter-spacing, and it ran as a bar across the card. Shrinking the type
   * further would have produced an unreadable long line instead of a readable
   * one.
   *
   * ⚠️ It is a SECOND field and not a shortened `label` because the two have
   * different jobs. The tooltip is built from `label`, so collapsing the label
   * to "Following" would have made the hover read "In your feed because:
   * following" — the fix taking the explanation away with the bar.
   */
  mark: string;
  /**
   * The reader-facing sentence fragment, sentence case, no trailing stop.
   *
   * Still the whole claim, and still what the chip's `title` says. The standing
   * feed rule is that deterministic explanations are first-class; the mark is
   * the mark, and this is what a reader who wonders gets.
   */
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
/**
 * #4429 — every entry carries BOTH forms: the `mark` the chip prints and the
 * `label` the tooltip says. The marks are one or two words with no article and
 * no verb, because an article is the difference between a mark and a sentence
 * and it is never the informative word.
 *
 * `A category you follow` -> `Following` is the one Alex named, but it was not
 * even the longest: `A player on one of your teams` is 29 characters and
 * `A rival of one of your teams` is 28. Fixing the one he saw would have left
 * the same bar on the next card.
 *
 * Marks may REPEAT where the distinction is one the chip cannot carry in two
 * words (`rival_losing` and `rival_playing` are both `Rival`). Nothing is lost:
 * precedence still picks the most specific reason, the tooltip still says which
 * one, and `data-for-you-reason` still carries the exact token for analytics.
 */
const UPRANK_VOCABULARY: { id: string; mark: string; label: string }[] = [
  { id: "pinned", mark: "Pinned", label: "You pinned this" },
  { id: "your_team", mark: "Your team", label: "One of your teams" },
  { id: "your_team_futures", mark: "Your team", label: "One of your teams" },
  { id: "roster_player", mark: "Your player", label: "A player on one of your teams" },
  { id: "alma_mater", mark: "Alma mater", label: "Your alma mater" },
  { id: "alma_mater_futures", mark: "Alma mater", label: "Your alma mater" },
  { id: "local_team", mark: "Nearby", label: "A team near you" },
  { id: "rival_losing", mark: "Rival", label: "A rival is losing" },
  { id: "rival_playing", mark: "Rival", label: "A rival of one of your teams" },
  { id: "rival_futures", mark: "Rival", label: "A rival of one of your teams" },
  { id: "sport_boost", mark: "Your sport", label: "A sport you follow" },
  { id: "discover_interest", mark: "Following", label: "A category you follow" },
  { id: "discover_feature_interest", mark: "Similar", label: "Like others you have opened" },
];

const UPRANK_BY_ID = new Map(UPRANK_VOCABULARY.map((entry) => [entry.id, entry.label]));

/** The vocabulary, exported so a guard can measure the marks rather than re-spell them. */
export const FOR_YOU_VOCABULARY: readonly { id: string; mark: string; label: string }[] =
  UPRANK_VOCABULARY;

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
  for (const { id, mark, label } of UPRANK_VOCABULARY) {
    for (const raw of reasons) {
      const parsed = parsePersonalizationReason(raw);
      if (!parsed || parsed.id !== id) continue;
      // A vocabulary id with a non-positive value is a token that shares its
      // name with a penalty arm. None does today; asserting it costs nothing
      // and means a future signed reason cannot invert a label.
      if (!(parsed.value > 0)) continue;
      return { mark, label, reasonId: id };
    }
  }
  return null;
}
