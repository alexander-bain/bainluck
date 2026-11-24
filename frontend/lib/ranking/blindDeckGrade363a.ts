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
