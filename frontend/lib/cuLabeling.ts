/** Types and pure validation/draft helpers for /admin/cu-labeling (#13900). */

export type CuSplit = "sealed" | "dev";
export type CuRole = "primary" | "second" | "tiebreak";
export type CuScope = "shared_100" | "all";
export type CuStructure = "ladder" | "dated_bucket" | "neither";
export type CuSubjectMode = "candidate" | "custom" | "none_of_these" | "not_sure";

export interface CuClaimFrameDraft {
  measure: string;
  comparison: string;
  value: string;
  unit: string;
  deadline: string;
}

export interface CuFactLabelDraft {
  subjectMode: CuSubjectMode;
  selectedCandidates: string[];
  customSubject: string;
  eventDate: string;
  noSingleDay: boolean;
  geography: string;
  structure: CuStructure | "";
  claim: CuClaimFrameDraft;
  stakes: number | null;
  breadth: number | null;
  evidenceNote: string;
}

export interface CuQueueOutcome {
  name: string;
  prob?: number | null;
}

export interface CuPeerFactAnswer {
  rater: string;
  role: CuRole;
  subjects_answer: { selection_kind: CuSubjectMode; selected: string[] } | null;
  event_date_answer: string | null;
  no_single_day: boolean;
  geography_answer: string | null;
  structure_answer: CuStructure | null;
  claim_frame: Partial<CuClaimFrameDraft> | null;
}

export interface CuQueueItem {
  market_id: number;
  title: string;
  source: string;
  category: string;
  draw_bucket?: string | null;
  rules_text: string;
  resolution_date?: string | null;
  outcomes: CuQueueOutcome[];
  outcome_names: string[];
  subject_candidates: string[];
  own_label: Record<string, unknown> | null;
  pair_complete: boolean;
  peer_labels: CuPeerFactAnswer[];
  disagreeing_fact_fields: string[];
}

export interface CuQueueResponse {
  split: CuSplit;
  role: CuRole;
  scope: CuScope;
  rater: string;
  total_in_scope: number;
  completed_by_rater: number;
  remaining: number;
  items: CuQueueItem[];
}

export interface CuAgreementFieldRow {
  field: string;
  metric: "exact" | "within_1";
  agreed: number;
  total: number;
  agreement_rate: number | null;
  below_80_pct: boolean;
  tiebreak_allowed: boolean;
}

export interface CuAgreementResponse {
  split: CuSplit;
  paired_markets: number;
  needs_tiebreak: number;
  resolved_tiebreaks: number;
  below_80_fields: string[];
  fields: CuAgreementFieldRow[];
}

export const RATER_STORAGE_KEY = "bainluck_cu_fact_rater_name";

export function emptyCuDraft(): CuFactLabelDraft {
  return {
    subjectMode: "candidate",
    selectedCandidates: [],
    customSubject: "",
    eventDate: "",
    noSingleDay: false,
    geography: "",
    structure: "",
    claim: {
      measure: "",
      comparison: "",
      value: "",
      unit: "",
      deadline: "",
    },
    stakes: null,
    breadth: null,
    evidenceNote: "",
  };
}

export function normalizeRaterName(raw: string): string {
  return raw.trim().replace(/\s+/g, " ");
}

export function buildSubmissionPayload(params: {
  split: CuSplit;
  role: CuRole;
  rater: string;
  marketId: number;
  draft: CuFactLabelDraft;
}): { ok: true; payload: Record<string, unknown> } | { ok: false; error: string } {
  const rater = normalizeRaterName(params.rater);
  if (!rater || rater.length > 64) {
    return { ok: false, error: "Type your labeler name (1-64 characters) first." };
  }

  const { draft, role, split, marketId } = params;

  let selected: string[] = [];
  if (draft.subjectMode === "candidate") {
    selected = draft.selectedCandidates.map((s) => s.trim()).filter(Boolean);
    if (selected.length === 0) {
      return { ok: false, error: "Select at least one subject candidate, custom entry, or 'None of these' / 'Not sure'." };
    }
  } else if (draft.subjectMode === "custom") {
    selected = draft.customSubject
      .split(",")
      .map((s) => s.trim())
      .filter(Boolean);
    if (selected.length === 0) {
      return { ok: false, error: "Enter at least one custom subject name." };
    }
  }

  if (!draft.noSingleDay && !/^\d{4}-\d{2}-\d{2}$/.test(draft.eventDate.trim())) {
    return { ok: false, error: "Enter YYYY-MM-DD for the event's own day or select 'No single day'." };
  }

  const geography = draft.geography.trim();
  if (!geography) {
    return { ok: false, error: "Select Where (`us`, `global`, `local`) or enter a country." };
  }

  if (!draft.structure) {
    return { ok: false, error: "Select the market structure (`ladder`, `dated_bucket`, or `neither`)." };
  }

  if (role === "tiebreak") {
    if (!draft.evidenceNote.trim()) {
      return { ok: false, error: "Write the textual evidence note for tiebreak before saving." };
    }
  } else {
    if (draft.stakes === null || draft.stakes < 1 || draft.stakes > 5) {
      return { ok: false, error: "Rate stakes from 1 to 5." };
    }
    if (draft.breadth === null || draft.breadth < 1 || draft.breadth > 5) {
      return { ok: false, error: "Rate breadth from 1 to 5." };
    }
  }

  const claimEntries = Object.entries(draft.claim)
    .map(([k, v]) => [k, v.trim()])
    .filter(([, v]) => v.length > 0);
  const claim_frame = claimEntries.length > 0 ? Object.fromEntries(claimEntries) : null;

  return {
    ok: true,
    payload: {
      dataset_split: split,
      market_id: marketId,
      rater,
      role,
      subjects_answer: {
        selection_kind: draft.subjectMode,
        selected,
      },
      event_date_answer: draft.noSingleDay ? null : draft.eventDate.trim(),
      no_single_day: draft.noSingleDay,
      geography_answer: geography,
      structure_answer: draft.structure,
      claim_frame,
      // Taste is never submitted or tie-broken in tiebreak role (#13900).
      stakes: role === "tiebreak" ? null : draft.stakes,
      breadth: role === "tiebreak" ? null : draft.breadth,
      evidence_note: draft.evidenceNote.trim() || null,
    },
  };
}
