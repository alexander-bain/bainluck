/**
 * #12373 (Epic #12288, Plan #12221 row 6) — pure helpers and types for the
 * private grouping grading page (`/grade/groupings`), where Alex and 3+ friends
 * grade 20+ proposed grouping cards beside each card's best single member.
 *
 * Kid graders use pseudonyms only (`kid1`, `kid2`, `kid3`, `kid4`, or
 * `kid-<6hex>`), never real names.
 */

import { formatTally, normalizeGraderName, type TallyEntry } from "@/lib/ranking/gradeSession";

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
}

export interface ProposedCardPreview {
  kicker: string;
  tag: string;
  title: string;
  rows: ProposedCardRow[];
  count_line: string;
  footer: string;
  relations: string[];
  level: string;
  as_of_label?: string | null;
  proposed_kind?: string | null;
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
  trust_pass: boolean;
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

export { formatTally, type TallyEntry };
