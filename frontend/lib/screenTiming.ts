/**
 * SCREEN TIMING — the felt number, measured in the reader's own browser.
 *
 * WHAT THIS MEASURES AND WHY NOTHING ELSE DOES IT. Web Vitals already ship from
 * this app, and they cannot answer Alex's question. FCP fires when the SKELETON
 * paints — a grey placeholder grid is contentful — so Discover can post a 0.15 s
 * FCP while the reader is still looking at nothing. LCP names the largest
 * element, usually a hero photograph. The number a stranger actually waits for
 * is *when did a real card with a real number appear*, and until now no rail on
 * any surface reported it. `first_card_ms` is that number.
 *
 * MEASURED, NOT ASSUMED — why this is worth its own rail at all: the
 * `tools/felt-load.mjs` battery on 2026-09-02 found the felt number is BIMODAL.
 * Most cold loads of Discover reach a real card in ~0.4 s; a minority take 14 s,
 * 31 s, or never get there. A p50 alone would have reported that surface as
 * excellent. This packet exists so the p95 is visible without anyone holding a
 * stopwatch, which is the whole reason the charter asks for a table.
 *
 * 🔴 THE DEFINITION OF "REAL CARD", stated so it can be argued with rather than
 * discovered later. An element is a real card when it (a) matches a card-shaped
 * selector, (b) carries no `animate-pulse` skeleton on it or inside it, (c) is
 * not inside an `aria-hidden` placeholder subtree, (d) is at least 80x40 CSS px,
 * and (e) has at least 12 characters of text. This is character-for-character
 * the rule in `tools/felt-load.mjs`, deliberately: the lab rig and the field
 * rail must be measuring the same event or the two numbers cannot be compared,
 * and a definition that drifts between them is worse than having only one.
 *
 * 🔴 IT MUST NOT BECOME PART OF WHAT IT MEASURES. Three specific choices:
 *   - `textContent`, never `innerText` — `innerText` forces a synchronous layout
 *     on every element it touches, on every pass.
 *   - a MutationObserver coalesced into one `requestAnimationFrame`, never a
 *     free-running rAF loop, so an idle screen costs exactly nothing.
 *   - it STOPS. Once the first screen has been quiet for `QUIET_MS`, or the
 *     budget expires, the observer disconnects and the module is inert for the
 *     rest of the visit.
 */

import { trackEvent } from "@/lib/analytics";
import type { ScreenTimingParams } from "@/lib/analytics/types";

/** Card-shaped selectors, shared verbatim with `tools/felt-load.mjs`. */
export const CARD_SELECTOR = [
  '[data-testid="discover-card"]',
  'a[href^="/event/"]',
  'a[href^="/events/"]',
  'a[href^="/futures/"]',
  'a[href^="/sport/"]',
  'a[href^="/tournaments/"]',
  'a[href^="/categories/"]',
  'a[href^="/hub/"]',
  'a[href^="/playoffs/"]',
  "article",
].join(",");

/** The first screen is "settled" once no new above-the-fold card has appeared for this long. */
const QUIET_MS = 1500;
/**
 * Hard budget. A screen that has shown no card by now is reported as `no_card`
 * rather than left unreported — the silent case is the expensive one, because a
 * screen that renders nothing paints FAST and would otherwise be missing from
 * the table exactly when it is worst (LAT-P202).
 */
const BUDGET_MS = 30000;

/** `-1` means "not measurable / did not happen" — never `0`, a different claim. */
export const NOT_MEASURED = -1;

/**
 * Collapse a pathname into a bounded surface slug.
 *
 * Every dynamic segment is masked, so an event id, a market id or a search term
 * can never ride out inside `surface`. The masking is by SHAPE, not by a list of
 * known routes: a route added next month is masked correctly without anyone
 * remembering to update this, and the failure direction of an unknown route is
 * an over-masked slug rather than a leaked id.
 */
export function maskSurface(pathname: string): string {
  const clean = (pathname || "/").split("?")[0].split("#")[0];
  const parts = clean.split("/").filter(Boolean);
  if (parts.length === 0) return "discover";
  const masked = parts.map((seg, i) => {
    if (i === 0) return seg.toLowerCase().slice(0, 32);
    // Numeric ids, uuids, and anything long or with many separators is dynamic.
    if (/^\d+$/.test(seg)) return ":id";
    if (/^[0-9a-f]{8}-[0-9a-f]{4}/i.test(seg)) return ":id";
    if (seg.length > 40) return ":slug";
    return seg.toLowerCase().slice(0, 32);
  });
  return masked.slice(0, 3).join("/");
}

/** Coarse hardware class. Never a model string, never a fingerprint. */
export function deviceClass(): ScreenTimingParams["device_class"] {
  if (typeof window === "undefined" || typeof navigator === "undefined") return "unknown";
  const ua = (navigator.userAgent || "").toLowerCase();
  // iPadOS reports a desktop UA, so the touch-point count is what separates a
  // tablet from a laptop. Without it every iPad lands in the desktop row and
  // the tablet row reads as unused (#2606 P3 names exactly this hole on native).
  const touch = typeof navigator.maxTouchPoints === "number" ? navigator.maxTouchPoints : 0;
  if (/ipad/.test(ua) || (/macintosh/.test(ua) && touch > 1)) return "tablet";
  if (/tablet|playbook|silk/.test(ua)) return "tablet";
  if (/mobi|iphone|ipod|android.*mobile/.test(ua)) return "phone";
  if (/android/.test(ua)) return "tablet";
  return "desktop";
}

/**
 * The complete `effectiveType` domain from the Network Information API spec.
 * Exported so the guard test asserts the exact rule rather than a paraphrase
 * of it — the same reason `isRealCard` is exported below.
 */
export const EFFECTIVE_TYPES = ["slow-2g", "2g", "3g", "4g"] as const;

/** Coarse network label from the Network Information API, where it exists. */
export function networkClass(): string {
  if (typeof navigator === "undefined") return "unknown";
  const conn = (navigator as unknown as { connection?: { effectiveType?: string } }).connection;
  const t = conn?.effectiveType;
  // A LENGTH CHECK IS NOT A DOMAIN CHECK. This read `t.length <= 12`, which
  // admits any short string the browser cares to hand over — the domain had
  // been restated from the spec rather than read off the producer. That is a
  // dimension, not a log line: every distinct value becomes a row in the GA4
  // `network_class` breakdown, so one vendor extension or a future spec value
  // silently splits every cold-load comparison this rail exists to make, and
  // does it retroactively across a dimension nobody thinks to re-check.
  //
  // `unknown` is already the value for "the API is absent", and an unrecognised
  // reading belongs with it: both mean "no usable network class", which is the
  // honest reading and the one that keeps the breakdown closed.
  return (EFFECTIVE_TYPES as readonly string[]).includes(t as string) ? (t as string) : "unknown";
}

interface WatchOptions {
  surface: string;
  entry: "cold" | "warm";
  /** Injected for tests; defaults to the real clock/DOM/emitter. */
  now?: () => number;
  root?: Document;
  emit?: (params: ScreenTimingParams) => void;
  appBuild?: string;
  viewportHeight?: () => number;
}

/**
 * Is this element a real card? Exported so the guard test asserts the exact rule
 * rather than a paraphrase of it.
 */
export function isRealCard(el: Element): boolean {
  if (el.classList && el.classList.contains("animate-pulse")) return false;
  if (typeof el.closest === "function") {
    if (el.closest(".animate-pulse")) return false;
    if (el.closest('[aria-hidden="true"]')) return false;
  }
  if (el.querySelector(".animate-pulse")) return false;
  const text = (el.textContent || "").trim();
  if (text.length < 12) return false;
  const rect = typeof el.getBoundingClientRect === "function" ? el.getBoundingClientRect() : null;
  if (rect && (rect.width < 80 || rect.height < 40)) return false;
  return true;
}

export interface ScreenTimingWatcher {
  /** Run one detection pass. Called by the observer; exported for tests. */
  scan(): void;
  /** Emit now with whatever has been observed, and stop. Idempotent. */
  finish(outcome?: ScreenTimingParams["outcome_class"]): void;
  /** Stop without emitting — the reader navigated away mid-measurement. */
  cancel(): void;
}

/**
 * Start measuring one screen arrival. Returns a handle; the caller is
 * responsible for calling `cancel()` when the screen is torn down, so a rapid
 * tab-switch does not leave two watchers scanning the same document.
 */
export function startScreenTiming(options: WatchOptions): ScreenTimingWatcher {
  const now = options.now ?? (() => (typeof performance !== "undefined" ? performance.now() : Date.now()));
  const root = options.root ?? (typeof document !== "undefined" ? document : null);
  const emit = options.emit ?? ((p: ScreenTimingParams) => trackEvent("screen_timing", p));
  const viewportHeight = options.viewportHeight ?? (() => (typeof window !== "undefined" ? window.innerHeight : 0));
  const origin = now();

  // Cards already present belong to the PREVIOUS screen. On a warm tab-switch
  // React unmounts the old tree a frame or two after the URL changes, so without
  // this snapshot every warm row would report the outgoing tab's cards as the
  // incoming tab's first card — a hard zero, and a lie.
  const seen = new WeakSet<Element>();
  const counted = new Set<Element>();

  let firstCardMs: number | null = null;
  let foldMs: number | null = null;
  let foldCount = 0;
  let lastFoldAt: number | null = null;
  let done = false;
  let observer: MutationObserver | null = null;
  let rafHandle: number | null = null;
  let quietTimer: ReturnType<typeof setTimeout> | null = null;
  let budgetTimer: ReturnType<typeof setTimeout> | null = null;

  // 🔴 THE SNAPSHOT IS A WARM-ONLY DEVICE, and getting that wrong breaks a
  // different surface each way.
  //
  // On a WARM transition the outgoing tab's cards are still mounted for a frame
  // or two while React unmounts them; without a snapshot every warm row reports
  // ~0 ms, which is a lie in the flattering direction.
  //
  // On a COLD load there is no previous screen, and a server-rendered surface
  // already has its real cards in the DOM when this effect first runs. Snapshot
  // there and those cards are excluded forever — the screen reports `no_card`
  // while the reader is looking at a complete page. That is the same flattering
  // direction wearing the opposite disguise, and it would have hit exactly the
  // SSR'd surfaces (the fast ones) hardest.
  //
  // Skeletons are never snapshotted even on a warm arm: React upgrades the node
  // in place, so a skeleton in this set hides the very card being timed.
  if (root && options.entry === "warm") {
    for (const el of Array.from(root.querySelectorAll(CARD_SELECTOR))) {
      if (isRealCard(el)) seen.add(el);
    }
  }

  function hasCountedAncestor(el: Element): boolean {
    for (let p = el.parentElement; p; p = p.parentElement) if (counted.has(p)) return true;
    return false;
  }

  function shellMs(): number {
    // Only meaningful for a document load. On a warm in-app transition the
    // paint entry belongs to the screen the reader came FROM, and reporting it
    // here would credit this screen with the previous screen's paint.
    if (options.entry !== "cold") return NOT_MEASURED;
    if (typeof performance === "undefined" || !performance.getEntriesByType) return NOT_MEASURED;
    const paint = performance.getEntriesByType("paint").find((p) => p.name === "first-contentful-paint");
    return paint ? Math.round(paint.startTime) : NOT_MEASURED;
  }

  function scan(): void {
    if (done || !root) return;
    const t = now() - origin;
    const nodes = root.querySelectorAll(CARD_SELECTOR);
    for (const el of Array.from(nodes)) {
      if (seen.has(el)) continue;
      // NOT marked seen when it fails: a skeleton becomes a real card in place,
      // and marking it here would make that card permanently invisible to us.
      if (!isRealCard(el)) continue;
      // Only the OUTERMOST match counts. A discover card contains an <a> and an
      // <article>, so counting every match inflates `card_count` ~2.5x.
      if (hasCountedAncestor(el)) { seen.add(el); continue; }
      seen.add(el);
      counted.add(el);
      if (firstCardMs === null) firstCardMs = t;
      const rect = typeof el.getBoundingClientRect === "function" ? el.getBoundingClientRect() : null;
      const vh = viewportHeight();
      if (!rect || (rect.top < vh && rect.bottom > 0)) {
        foldMs = t;
        foldCount += 1;
        lastFoldAt = t;
      }
    }
    if (firstCardMs !== null && lastFoldAt !== null) armQuiet();
  }

  function armQuiet(): void {
    if (quietTimer) clearTimeout(quietTimer);
    quietTimer = setTimeout(() => finish("ok"), QUIET_MS);
  }

  function onMutate(): void {
    if (done) return;
    // Coalesce a burst of mutations into ONE pass on the next frame. React
    // commits a feed page as many mutations; scanning per mutation would run the
    // detector dozens of times for one visual change.
    if (rafHandle !== null) return;
    const raf =
      typeof requestAnimationFrame === "function"
        ? requestAnimationFrame
        : (cb: FrameRequestCallback) => setTimeout(() => cb(0), 16) as unknown as number;
    rafHandle = raf(() => {
      rafHandle = null;
      scan();
    }) as unknown as number;
  }

  function stop(): void {
    done = true;
    if (observer) { observer.disconnect(); observer = null; }
    if (quietTimer) { clearTimeout(quietTimer); quietTimer = null; }
    if (budgetTimer) { clearTimeout(budgetTimer); budgetTimer = null; }
  }

  function finish(outcome?: ScreenTimingParams["outcome_class"]): void {
    if (done) return;
    stop();
    const resolved: ScreenTimingParams["outcome_class"] =
      outcome ?? (firstCardMs !== null ? "ok" : "no_card");
    emit({
      surface: options.surface,
      entry: options.entry,
      shell_ms: shellMs(),
      first_card_ms: firstCardMs === null ? NOT_MEASURED : Math.round(firstCardMs),
      fold_ms: foldMs === null ? NOT_MEASURED : Math.round(foldMs),
      // Time to interactive, honestly scoped: the moment the first screen stopped
      // changing under the reader. This app hydrates before its data arrives, so
      // a hydration-based TTI would report a screen as usable while it is still
      // grey — the number would be true and useless.
      interactive_ms: foldMs === null ? NOT_MEASURED : Math.round(foldMs),
      card_count: foldCount,
      device_class: deviceClass(),
      network_class: networkClass(),
      app_build: options.appBuild ?? "web",
      outcome_class: firstCardMs === null && resolved === "ok" ? "no_card" : resolved,
    });
  }

  if (root && typeof MutationObserver !== "undefined") {
    observer = new MutationObserver(onMutate);
    observer.observe(root.documentElement ?? (root as unknown as Node), {
      childList: true,
      subtree: true,
    });
  }
  budgetTimer = setTimeout(() => finish(), BUDGET_MS);
  // One immediate pass: a server-rendered screen may already be complete, and a
  // detector that only reacts to mutations would never report it at all.
  scan();

  return { scan, finish, cancel: stop };
}
