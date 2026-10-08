import type { FeedItem } from "@/lib/types";

// A brief first-screen preview, separate from the reader's Back/scroll edition.
export const FIRST_DECK_KEY = "discover_first_deck_v1";
export const FIRST_DECK_TTL_MS = 60_000;
const MAX_ITEMS = 20;
export type FirstDeck = { items: FeedItem[]; hasMore: boolean };

/** Auth restore is async; only the same persisted principal may preview its deck. */
export function firstDeckOwner(uid: string | null | undefined, authLoading: boolean): string | null {
  if (typeof window === "undefined") return null;
  try {
    if (uid) return `user:${uid}`;
    if (authLoading) {
      const owners = new Set<string>();
      const backendRaw = window.localStorage.getItem("bainluck_backendAuth");
      if (backendRaw) {
        const backend = JSON.parse(backendRaw);
        if (typeof backend.uid === "string" && backend.expiresAt > Date.now() + 300_000) owners.add(backend.uid);
      }
      // The app uses browserLocalPersistence under Firebase's default app key.
      const apiKey = process.env.NEXT_PUBLIC_FIREBASE_API_KEY;
      const firebaseRaw = apiKey && window.localStorage.getItem(`firebase:authUser:${apiKey}:[DEFAULT]`);
      if (firebaseRaw) {
        const firebase = JSON.parse(firebaseRaw);
        if (typeof firebase.uid !== "string" || !firebase.uid) return null;
        owners.add(firebase.uid);
      }
      if (owners.size === 1) return `user:${Array.from(owners)[0]}`;
      if (owners.size > 1 || window.localStorage.getItem("bainluck_previouslySignedIn") === "true") return null;
    }
    // sessionStorage already confines this fallback to the same browser tab.
    return `anonymous:${window.localStorage.getItem("bainluck_session_id") ?? "tab"}`;
  } catch { return null; }
}

function checksum(body: string): number {
  let hash = 0;
  for (let i = 0; i < body.length; i++) hash = (Math.imul(hash, 31) + body.charCodeAt(i)) | 0;
  return hash;
}

export function parseFirstDeck(raw: string | null, owner: string | null, now: number): FirstDeck | null {
  if (!raw || !owner) return null;
  try {
    const saved = JSON.parse(raw);
    const age = now - saved.savedAt;
    if (saved.v !== 1 || saved.owner !== owner || !Number.isFinite(saved.savedAt) ||
        age < 0 || age > FIRST_DECK_TTL_MS || typeof saved.body !== "string" ||
        saved.body.length > 500_000 || saved.checksum !== checksum(saved.body)) return null;
    const deck = JSON.parse(saved.body);
    if (!Array.isArray(deck.items) || !deck.items.length || deck.items.length > MAX_ITEMS ||
        typeof deck.hasMore !== "boolean" || deck.items.some((item: FeedItem) =>
          !item || !["event", "futures", "bundle", "concept", "tournament", "collection"].includes(item.type) ||
          !item.data || typeof item.data !== "object")) return null;
    return deck;
  } catch { return null; }
}

export function readFirstDeck(owner: string | null): FirstDeck | null {
  if (typeof window === "undefined") return null;
  try { return parseFirstDeck(window.sessionStorage.getItem(FIRST_DECK_KEY), owner, Date.now()); }
  catch { return null; }
}

/** Only a current accepted response writes this; displaying a preview never renews its age. */
export function writeFirstDeck(deck: FirstDeck, owner: string | null): void {
  if (typeof window === "undefined" || !owner) return;
  try {
    if (!deck.items.length) { window.sessionStorage.removeItem(FIRST_DECK_KEY); return; }
    const body = JSON.stringify({ items: deck.items.slice(0, MAX_ITEMS), hasMore: deck.hasMore });
    if (body.length > 500_000) { window.sessionStorage.removeItem(FIRST_DECK_KEY); return; }
    window.sessionStorage.setItem(FIRST_DECK_KEY, JSON.stringify({ v: 1, owner, savedAt: Date.now(), body, checksum: checksum(body) }));
  } catch { /* Storage is optional; a failed read/write remains a normal cold load. */ }
}
