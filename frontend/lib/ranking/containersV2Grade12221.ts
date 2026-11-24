import type { KitContainerPageSpec } from "@/components/collections/KitContainerPageView";
import type { ContainerGrade, ContainerGradeEntry } from "@/lib/ranking/blindDeckGrade363a";

export const CONTAINERS_V2_SURFACE = "grade_containers_v2";
export const CONTAINERS_V2_ITEM_TYPE = "kit_container_v2";
export const CONTAINERS_V2_DRAFT_STORAGE_KEY = "bainluck_12221_containers_v2_grades_v1";

export interface SavedContainerV2JudgmentRow {
  market_name?: string;
  label?: string;
  notes?: string | null;
  created_at?: string;
  label_metadata?: {
    ui_version?: number;
    slug?: string;
    family_fingerprint?: string | null;
    title?: string;
    kicker?: string;
    variants?: string[];
    grade?: ContainerGrade;
    note?: string;
    timestamp?: string;
  };
}

export interface ContainerV2JudgmentPayload {
  surface: string;
  item_type: string;
  market_name: string;
  label: ContainerGrade;
  notes: string | null;
  reviewer: string;
  label_metadata: {
    ui_version: 2;
    slug: string;
    family_fingerprint: string | null;
    title: string;
    kicker: string;
    variants: string[];
    grade: ContainerGrade;
    note: string;
    timestamp: string;
  };
}

export function buildContainerV2JudgmentPayload(
  page: KitContainerPageSpec,
  grade: ContainerGrade,
  note: string,
  timestampIso: string,
): ContainerV2JudgmentPayload {
  const trimmedNote = note.trim();
  return {
    surface: CONTAINERS_V2_SURFACE,
    item_type: CONTAINERS_V2_ITEM_TYPE,
    market_name: page.slug,
    label: grade,
    notes: trimmedNote || null,
    reviewer: "alex",
    label_metadata: {
      ui_version: 2,
      slug: page.slug,
      family_fingerprint: page.family_fingerprint ?? null,
      title: page.title,
      kicker: page.kicker,
      variants: [...(page.variants || [])],
      grade,
      note: trimmedNote,
      timestamp: timestampIso,
    },
  };
}

export function restoreContainerV2Grades(
  rows: readonly SavedContainerV2JudgmentRow[],
): Record<string, ContainerGradeEntry> {
  const restored: Record<string, ContainerGradeEntry> = {};
  for (const row of rows) {
    const slug = row.label_metadata?.slug || row.market_name;
    const grade = (row.label_metadata?.grade || row.label) as ContainerGrade | undefined;
    if (!slug || !grade || !["Keep", "Fix", "Drop"].includes(grade) || restored[slug]) {
      continue;
    }
    restored[slug] = {
      grade,
      note: (row.label_metadata?.note ?? row.notes ?? "").trim(),
      updated_at: row.label_metadata?.timestamp || row.created_at || "",
    };
  }
  return restored;
}
