import type { KitContainerPageSpec } from "@/components/collections/KitContainerPageView";
import type { ContainerGrade, ContainerGradeEntry } from "@/lib/ranking/blindDeckGrade363a";

export const CONTAINERS_V2_SURFACE = "grade_containers_v2";
export const CONTAINERS_V2_ITEM_TYPE = "kit_container_v2";
export const CONTAINERS_V2_DRAFT_STORAGE_KEY = "bainluck_12221_containers_v2_grades_v1";

export interface SavedContainerV2JudgmentRow {
  market_name?: string;
  card_fingerprint?: string | null;
  reviewer?: string | null;
  label?: string;
  notes?: string | null;
  created_at?: string;
  label_metadata?: {
    ui_version?: number;
    deck_id?: string | null;
    slug?: string;
    family_fingerprint?: string | null;
    page_fingerprint?: string | null;
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
  card_fingerprint: string | null;
  label: ContainerGrade;
  notes: string | null;
  reviewer: string;
  label_metadata: {
    ui_version: 2;
    deck_id: string | null;
    slug: string;
    family_fingerprint: string | null;
    page_fingerprint: string | null;
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
  deckId?: string | null,
  reviewer?: string | null,
): ContainerV2JudgmentPayload {
  const trimmedNote = note.trim();
  const resolvedReviewer = (reviewer || "").trim() || "alex";
  const pageFingerprint = page.page_fingerprint ?? page.family_fingerprint ?? null;
  return {
    surface: CONTAINERS_V2_SURFACE,
    item_type: CONTAINERS_V2_ITEM_TYPE,
    market_name: page.slug,
    card_fingerprint: pageFingerprint,
    label: grade,
    notes: trimmedNote || null,
    reviewer: resolvedReviewer,
    label_metadata: {
      ui_version: 2,
      deck_id: deckId ?? null,
      slug: page.slug,
      family_fingerprint: page.family_fingerprint ?? null,
      page_fingerprint: pageFingerprint,
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
  options?: { deckId?: string | null; pages?: readonly KitContainerPageSpec[]; reviewer?: string | null },
): Record<string, ContainerGradeEntry> {
  const activeDeckId = options?.deckId ?? null;
  const activeReviewer = (options?.reviewer || "").trim() || null;
  const pageFpBySlug = new Map<string, string>();
  for (const p of options?.pages || []) {
    const fp = p.page_fingerprint ?? p.family_fingerprint ?? null;
    if (p.slug && fp) {
      pageFpBySlug.set(p.slug, fp);
    }
  }

  const restored: Record<string, ContainerGradeEntry> = {};
  for (const row of rows) {
    const slug = row.label_metadata?.slug || row.market_name;
    const grade = (row.label_metadata?.grade || row.label) as ContainerGrade | undefined;
    if (!slug || !grade || !["Keep", "Fix", "Drop"].includes(grade) || restored[slug]) {
      continue;
    }
    if (activeReviewer && row.reviewer && row.reviewer !== activeReviewer) {
      continue;
    }
    if (activeDeckId && row.label_metadata?.deck_id !== activeDeckId) {
      continue;
    }
    const expectedFp = pageFpBySlug.get(slug);
    if (expectedFp) {
      const savedFp = row.label_metadata?.page_fingerprint ?? row.card_fingerprint ?? null;
      if (savedFp && savedFp !== expectedFp) {
        continue;
      }
    }
    restored[slug] = {
      grade,
      note: (row.label_metadata?.note ?? row.notes ?? "").trim(),
      updated_at: row.label_metadata?.timestamp || row.created_at || "",
    };
  }
  return restored;
}
