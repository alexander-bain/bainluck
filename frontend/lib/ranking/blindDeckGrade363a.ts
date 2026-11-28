export interface BlindFormCardItem {
  item_id: string;
  image_url: string;
  width_px: number;
  height_px: number;
}

export interface BlindFormsPublicDeck {
  deck_id: string;
  created_at: string;
  ruling: string;
  blind: boolean;
  seed: number;
  sealed_checksum_sha256?: string;
  image_width_px: number;
  css_width_px: number;
  color_scheme: string;
  forms: BlindFormCardItem[];
}

export interface BlindContainerItem {
  item_id: string;
  card_image_url: string;
  page_image_url: string;
  card_width_px: number;
  card_height_px: number;
  page_width_px: number;
  page_height_px: number;
}

export interface BlindContainersDeck {
  deck_id: string;
  created_at: string;
  ruling: string;
  blind: boolean;
  seed: number;
  universe: string;
  universe_count: number;
  sealed_checksum_sha256: string;
  image_width_px: number;
  css_width_px: number;
  color_scheme: string;
  atlas_images_sha: string;
  grade_options: readonly ContainerGrade[];
  items: BlindContainerItem[];
}

export interface PileBucket {
  pile_id: string;
  label: string;
  item_ids: string[];
}

export type ContainerGrade = "Keep" | "Fix" | "Drop";

export interface ContainerGradeEntry {
  grade: ContainerGrade;
  note: string;
  updated_at: string;
}

export function mulberry32(seed: number): () => number {
  let state = seed >>> 0;
  return () => {
    state = (state + 0x6d2b79f5) >>> 0;
    let t = Math.imul(state ^ (state >>> 15), 1 | state);
    t = (t + Math.imul(t ^ (t >>> 7), 61 | t)) ^ t;
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
  };
}

export function shuffleBlindForms<T>(items: readonly T[], seed: number): T[] {
  const arr = [...items];
  const rand = mulberry32(seed);
  for (let i = arr.length - 1; i > 0; i--) {
    const j = Math.floor(rand() * (i + 1));
    const tmp = arr[i];
    arr[i] = arr[j];
    arr[j] = tmp;
  }
  return arr;
}

export function removeCardFromPiles(piles: PileBucket[], itemId: string): PileBucket[] {
  return piles
    .map((pile) => ({
      ...pile,
      item_ids: pile.item_ids.filter((id) => id !== itemId),
    }))
    .filter((pile) => pile.item_ids.length > 0);
}

export function assignCardToPile(
  piles: PileBucket[],
  itemId: string,
  targetPileId: string,
): PileBucket[] {
  const cleaned = removeCardFromPiles(piles, itemId);
  const exists = cleaned.some((p) => p.pile_id === targetPileId);
  if (!exists) {
    return [
      ...cleaned,
      {
        pile_id: targetPileId,
        label: `Pile ${cleaned.length + 1}`,
        item_ids: [itemId],
      },
    ];
  }
  return cleaned.map((pile) =>
    pile.pile_id === targetPileId
      ? { ...pile, item_ids: [...pile.item_ids, itemId] }
      : pile,
  );
}

export function createPileWithCard(piles: PileBucket[], itemId: string): PileBucket[] {
  const cleaned = removeCardFromPiles(piles, itemId);
  const nextIndex =
    cleaned.reduce((maxN, p) => {
      const m = /^pile-(\d+)$/.exec(p.pile_id);
      return m ? Math.max(maxN, Number(m[1])) : maxN;
    }, 0) + 1;
  return [
    ...cleaned,
    {
      pile_id: `pile-${nextIndex}`,
      label: `Pile ${cleaned.length + 1}`,
      item_ids: [itemId],
    },
  ];
}

export function buildCardToPileMap(piles: PileBucket[]): Record<string, string> {
  const map: Record<string, string> = {};
  for (const p of piles) {
    for (const id of p.item_ids) {
      map[id] = p.pile_id;
    }
  }
  return map;
}

/** Pre-fix grade_forms_deck clicks before the v2 UI rollout are void (filter by time, never delete). */
export const GRADE_FORMS_VALID_AFTER_ISO = "2026-11-24T22:00:00Z";

export function createInitialEmptyPiles(): PileBucket[] {
  return [{ pile_id: "pile-1", label: "Pile 1", item_ids: [] }];
}

function nextPileId(piles: PileBucket[]): string {
  const maxN = piles.reduce((acc, p) => {
    const m = /^pile-(\d+)$/.exec(p.pile_id);
    return m ? Math.max(acc, Number(m[1])) : acc;
  }, 0);
  return `pile-${maxN + 1}`;
}

export function addEmptyPile(piles: PileBucket[]): PileBucket[] {
  const id = nextPileId(piles);
  return [...piles, { pile_id: id, label: `Pile ${piles.length + 1}`, item_ids: [] }];
}

export function removeCardPreservingEmptyPiles(
  piles: PileBucket[],
  itemId: string,
): PileBucket[] {
  const base = piles.length > 0 ? piles : createInitialEmptyPiles();
  return base.map((pile) => ({
    ...pile,
    item_ids: pile.item_ids.filter((id) => id !== itemId),
  }));
}

export function moveCardToPilePreservingEmpty(
  piles: PileBucket[],
  itemId: string,
  targetPileId: string,
): PileBucket[] {
  const cleaned = removeCardPreservingEmptyPiles(piles, itemId);
  if (!cleaned.some((p) => p.pile_id === targetPileId)) {
    return [
      ...cleaned,
      { pile_id: targetPileId, label: `Pile ${cleaned.length + 1}`, item_ids: [itemId] },
    ];
  }
  return cleaned.map((pile) =>
    pile.pile_id === targetPileId
      ? { ...pile, item_ids: [...pile.item_ids, itemId] }
      : pile,
  );
}

export function pruneEmptyPilesForSave(piles: PileBucket[]): PileBucket[] {
  return piles
    .filter((p) => p.item_ids.length > 0)
    .map((p, idx) => ({ ...p, label: `Pile ${idx + 1}` }));
}

export function isPostFixFormsJudgmentRow(
  row: {
    label?: string | null;
    created_at?: string | null;
    label_metadata?: {
      ui_version?: number;
      timestamp?: string;
      piles?: unknown;
      deck_id?: string;
      void?: boolean;
      sort_state?: string;
    } | null;
  },
  resetAfterIso?: string | null,
  expectedDeckId?: string | null,
): boolean {
  if (row?.label === "void") return false;
  const meta = row?.label_metadata;
  if (!meta || !Array.isArray(meta.piles) || meta.piles.length === 0) return false;
  if (meta.void === true || meta.sort_state === "void") return false;
  if (expectedDeckId && meta.deck_id !== expectedDeckId) return false;
  if (typeof meta.ui_version !== "number" || meta.ui_version < 2) return false;
  const rawTs = row.created_at || meta.timestamp || "";
  const ms = Date.parse(rawTs);
  if (Number.isNaN(ms) || ms < Date.parse(GRADE_FORMS_VALID_AFTER_ISO)) return false;
  if (resetAfterIso) {
    const resetMs = Date.parse(resetAfterIso);
    if (!Number.isNaN(resetMs) && ms <= resetMs) return false;
  }
  return true;
}

export function canonicalContainerGradesString(
  deckId: string,
  grades: Record<string, ContainerGradeEntry>,
): string {
  const orderedIds = Object.keys(grades).sort();
  const payload = {
    deck_id: deckId,
    grades: orderedIds.map((id) => ({
      item_id: id,
      grade: grades[id].grade,
      note: grades[id].note.trim(),
    })),
  };
  return JSON.stringify(payload);
}

export async function computeSha256Hex(text: string): Promise<string> {
  const bytes = new TextEncoder().encode(text);
  if (typeof globalThis.crypto !== "undefined" && globalThis.crypto.subtle) {
    const digest = await globalThis.crypto.subtle.digest("SHA-256", bytes);
    return Array.from(new Uint8Array(digest))
      .map((b) => b.toString(16).padStart(2, "0"))
      .join("");
  }
  // Minimal deterministic FNV-1a fallback strictly for non-crypto Node jsdom tests
  let h = 2166136261;
  for (let i = 0; i < bytes.length; i++) {
    h ^= bytes[i];
    h = Math.imul(h, 16777619);
  }
  return `fallback-${(h >>> 0).toString(16).padStart(8, "0")}`;
}
