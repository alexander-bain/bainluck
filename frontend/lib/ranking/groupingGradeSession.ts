/**
 * #12373 (Epic #12288, Plan #12221 row 6) — pure helpers and types for the
 * private grouping grading page (`/grade/groupings`), where Alex and 3+ friends
 * grade 20+ proposed grouping cards beside each card's best single member.
 *
 * Kid graders use pseudonyms only (`kid1`, `kid2`, `kid3`, `kid4`, or
 * `kid-<6hex>`), never real names.
 */

import {
  formatTally,
  handleGradeDeckReadError,
  normalizeGraderName,
  type TallyEntry,
} from "@/lib/ranking/gradeSession";
import type { FeedRoundupContract, FeedRoundupRow } from "@/lib/types";

export const GROUPING_GRADES = ["amazing", "fine", "no"] as const;
export type GroupingGrade = (typeof GROUPING_GRADES)[number];

export const GROUPING_GRADE_LABELS: Record<GroupingGrade, string> = {
  amazing: "Amazing — beats the single",
  fine: "Fine — adds context",
  no: "No — single is enough",
};

export const KID_PSEUDONYMS = ["kid1", "kid2", "kid3", "kid4"] as const;
export type KidPseudonym = (typeof KID_PSEUDONYMS)[number];

export interface ProposedCardRow {
  label: string;
  value: string;
  market_id: number;
  probability?: number | null;
  rendered_percent?: number | null;
  observed_at?: string | null;
}

export interface ProposedCardPreview {
  kicker: string;
  tag: string;
  title: string;
  subtitle?: string | null;
  rows: ProposedCardRow[];
  count_line: string;
  footer: string;
  relations: string[];
  level: string;
  as_of_label?: string | null;
  proposed_kind?: string | null;
  selection_type?: string | null;
}

/**
 * Convert a `/grade/groupings` `ProposedCardPreview` into the canonical
 * `FeedRoundupContract` consumed by `RoundupCard`, so `/grade/groupings` and
 * Discover share one card renderer (#9937).
 */
export function buildRoundupContractForProposedCard(
  card: ProposedCardPreview,
): FeedRoundupContract {
  const rows: FeedRoundupRow[] = (card.rows || []).map((r, idx) => {
    let prob = typeof r.probability === "number" ? r.probability : NaN;
    let pct = typeof r.rendered_percent === "number" ? r.rendered_percent : undefined;
    if (!Number.isFinite(prob) && typeof r.value === "string") {
      const cleaned = r.value.trim().replace(/^[<>]/, "");
      if (cleaned.endsWith("%")) {
        const parsed = Number.parseFloat(cleaned.slice(0, -1));
        if (Number.isFinite(parsed)) {
          prob = parsed / 100;
          pct = Math.round(parsed);
        }
      }
    }
    const marketId =
      typeof r.market_id === "number" && r.market_id > 0 ? r.market_id : idx + 1;
    return {
      market_id: marketId,
      label: r.label,
      probability: prob,
      rendered_percent: pct,
      ...(r.observed_at ? { observed_at: r.observed_at } : {}),
    };
  });

  return {
    kicker: card.kicker || "PROPOSED CARD",
    tag: card.tag || null,
    subtitle: card.subtitle || null,
    complete_group: card.selection_type === "complete_group",
    count_line: card.count_line || null,
    footer:
      card.footer || "Each row is its own market. They don't add up to 100%.",
    relations: card.relations,
    level: card.level,
    rows,
  };
}

export interface BestSingleMember {
  id: number;
  name: string;
  subject: string;
  source: string;
  category: string;
  yes_probability: number | null;
  rendered_percent: number | null;
  resolution_date: string | null;
  rule_quote: string;
}

export interface GroupingDeckItem {
  position: number;
  item_key: string;
  title: string;
  source: string;
  category: string;
  template_key: string;
  member_count: number;
  kind_verdict: "serve" | "refuse";
  refusal_reasons: string[];
  trust_pass?: boolean | null;
  proposed_kind?: string | null;
  as_of?: string | null;
  as_of_label?: string | null;
  proposed_card: ProposedCardPreview;
  best_single: BestSingleMember;
}

export interface GroupingGradeDeck {
  slate_id: string;
  surface: string;
  generated_at: string | null;
  model: string | null;
  question: string;
  items: GroupingDeckItem[];
}

export interface GroupingGradeSummary {
  total_grades: number;
  distinct_graders: number;
  distinct_cards_graded: number;
  by_grade: Record<GroupingGrade, number>;
  by_grader: Array<{
    grader: string;
    kid: boolean;
    count: number;
    amazing: number;
    fine: number;
    no: number;
  }>;
}

/**
 * Resolve the grader identifier to store.
 * When `kid` is true, returns ONLY a pseudonym (`kid1`..`kid4`), never a name.
 */
export function resolveGroupingGraderId(
  nameInput: string,
  kid: boolean,
  kidPseudonym: KidPseudonym = "kid1",
): string {
  if (kid) {
    return KID_PSEUDONYMS.includes(kidPseudonym) ? kidPseudonym : "kid1";
  }
  return normalizeGraderName(nameInput).toLowerCase();
}

export { formatTally, handleGradeDeckReadError, type TallyEntry };
