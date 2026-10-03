/**
 * #10265 — WHERE THE QUESTION PAGE'S BACK CONTROL MAY GO.
 *
 * The question page's only back control was a hard link to /discover, so a
 * reader who opened `/futures/231` from the Bigger Picture card on a live game
 * page (`/events/15318028`) lost the game. The control should do what the
 * browser's Back does when the entry immediately behind the question is the
 * page the reader tapped from, and go to Discover in every other case.
 *
 * WHAT COUNTS AS PROOF. `history.length` and `document.referrer` cannot say
 * what the immediately preceding entry is, and neither can "the path changed
 * since the document loaded": a client REPLACE into a question page leaves
 * whatever came before the replaced entry, possibly another site, behind it.
 * The proof here is the browser's own Navigation API, which lists only
 * same-origin entries and gives each entry an `id` that a replace does not
 * keep:
 *
 *  1. CLICK. `NavigationProgress` already sees every anchor click in the
 *     capture phase. A plain, same-tab click on a same-origin link to a
 *     question records the CURRENT entry's id as the pending source.
 *  2. ARRIVAL. When the question page mounts, the pending source is consumed
 *     (once, whatever the outcome). It is adopted only if it is fresh, the
 *     page is the question the click named, and the entry immediately before
 *     the current one IS the recorded source entry. After a push the source
 *     entry is still there; after a replace it is gone. The adopted proof is
 *     bound to the current entry's `key` and path, so a range chip's
 *     `replaceState` (same entry, new query) keeps it and a different question
 *     entry never inherits it.
 *  3. CLICK ON BACK. The immediate predecessor's id is checked again, so a
 *     proof whose source has since been replaced or truncated does not
 *     authorize anything.
 *
 * No Navigation API, no click, a reload (module memory is per document), a
 * duplicated tab, a redirect to another path, a modified or middle click, a
 * stale or mismatched click: no proof, and the control stays the Discover
 * link. Nothing here writes `history.state` or patches `history`.
 */

/** The parts of a Navigation API history entry this module reads. */
export interface OriginEntry {
  readonly id: string;
  readonly key: string;
  readonly index: number;
}

/** The parts of `window.navigation` this module reads. */
export interface OriginNavigation {
  readonly currentEntry: OriginEntry | null;
  entries(): readonly OriginEntry[];
}

export interface OriginEnv {
  /** `location.origin`. */
  origin: string;
  /** `location.href`, the base relative links resolve against. */
  href: string;
  /** `location.pathname`. */
  pathname: string;
  /** `window.navigation`, or null where the browser has none. */
  navigation: OriginNavigation | null;
  /** `Date.now()`. */
  now: number;
}

/** The anchor click as `NavigationProgress` sees it. */
export interface OriginClick {
  href: string | null;
  button: number;
  metaKey: boolean;
  ctrlKey: boolean;
  shiftKey: boolean;
  altKey: boolean;
  /** The anchor's `target` attribute. */
  target: string | null;
  /** Whether the anchor carries a `download` attribute. */
  download: boolean;
}

/** A click older than this when the question page mounts proves nothing. */
export const ORIGIN_CLICK_TTL_MS = 30_000;

const QUESTION_PATH = /^\/futures\/[^/]+\/?$/;

function normalizedPath(pathname: string): string {
  return pathname.length > 1 && pathname.endsWith("/") ? pathname.slice(0, -1) : pathname;
}

/** The question path a link points at, or null if it is not a same-origin question link. */
export function questionPathOf(href: string | null, env: Pick<OriginEnv, "origin" | "href">): string | null {
  if (!href) return null;
  let url: URL;
  try {
    url = new URL(href, env.href);
  } catch {
    return null;
  }
  if (url.origin !== env.origin) return null;
  if (url.protocol !== "http:" && url.protocol !== "https:") return null;
  return QUESTION_PATH.test(url.pathname) ? normalizedPath(url.pathname) : null;
}

function predecessorOf(nav: OriginNavigation, current: OriginEntry): OriginEntry | null {
  if (current.index < 1) return null;
  const entries = nav.entries();
  const prev = entries[current.index - 1];
  return prev ?? null;
}

interface Pending {
  sourceId: string;
  destPath: string;
  at: number;
}

interface Proof {
  sourceId: string;
  path: string;
}

export interface QuestionOriginStore {
  /** Step 1. True when the click was recorded as a pending source. */
  recordClick(click: OriginClick, env: OriginEnv): boolean;
  /** Step 2. True when the current entry gained a proof. */
  adopt(env: OriginEnv): boolean;
  /** Step 3. True when Back may traverse to the entry behind this one. */
  canGoBack(env: OriginEnv): boolean;
}

export function createQuestionOriginStore(): QuestionOriginStore {
  let pending: Pending | null = null;
  const proofs = new Map<string, Proof>();

  return {
    recordClick(click, env) {
      if (click.button !== 0 || click.metaKey || click.ctrlKey || click.shiftKey || click.altKey) {
        return false;
      }
      if (click.download) return false;
      const target = (click.target ?? "").trim().toLowerCase();
      if (target !== "" && target !== "_self") return false;
      const destPath = questionPathOf(click.href, env);
      if (!destPath) return false;
      const current = env.navigation?.currentEntry;
      if (!current) return false;
      // A link to the question already on screen is not a move.
      if (destPath === normalizedPath(env.pathname)) return false;
      pending = { sourceId: current.id, destPath, at: env.now };
      return true;
    },

    adopt(env) {
      const p = pending;
      pending = null;
      if (!p) return false;
      if (env.now - p.at > ORIGIN_CLICK_TTL_MS || env.now < p.at) return false;
      const path = normalizedPath(env.pathname);
      if (p.destPath !== path) return false;
      const nav = env.navigation;
      const current = nav?.currentEntry;
      if (!nav || !current || current.id === p.sourceId) return false;
      const prev = predecessorOf(nav, current);
      if (!prev || prev.id !== p.sourceId) return false;
      proofs.set(current.key, { sourceId: p.sourceId, path });
      return true;
    },

    canGoBack(env) {
      const nav = env.navigation;
      const current = nav?.currentEntry;
      if (!nav || !current) return false;
      const proof = proofs.get(current.key);
      if (!proof || proof.path !== normalizedPath(env.pathname)) return false;
      const prev = predecessorOf(nav, current);
      return !!prev && prev.id === proof.sourceId;
    },
  };
}

/** The page's one store: module memory, so it lives exactly as long as the document. */
export const questionOrigin = createQuestionOriginStore();

/** The live browser's env, or null on the server. Never throws. */
export function browserOriginEnv(): OriginEnv | null {
  if (typeof window === "undefined") return null;
  try {
    const nav = (window as unknown as { navigation?: OriginNavigation }).navigation;
    return {
      origin: window.location.origin,
      href: window.location.href,
      pathname: window.location.pathname,
      navigation: nav && typeof nav.entries === "function" ? nav : null,
      now: Date.now(),
    };
  } catch {
    return null;
  }
}
