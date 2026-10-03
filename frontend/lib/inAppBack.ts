/**
 * #10265 — IS THE PAGE BEHIND THIS ONE OURS?
 *
 * The question page's back control was a hard link to /discover. A reader who
 * opened `/futures/231` from the Bigger Picture card on a live game page
 * (`/events/15318028`, Pitt @ Virginia Tech in the 4th) tapped "Back to
 * Discover" and lost the game and their place on it, while the browser's own
 * Back returned them to the card. Every way into a question page (event pages,
 * team pages, hubs, Discover cards) has the same need, so the control should do
 * what Back does when the entry behind it is one of our pages, and go to
 * Discover only when it is not: a fresh tab, a shared link, a search result.
 *
 * Two signals, either one enough:
 *
 *  1. THE PAGE WAS REACHED BY A CLIENT-SIDE NAVIGATION. Next's `<Link>` never
 *     reloads the document, so the document's own navigation entry still names
 *     the URL the tab first loaded. If that path is not the path on screen, the
 *     reader has moved inside the app since, and the entry behind this one was
 *     pushed by us.
 *  2. THE DOCUMENT WAS LOADED FROM ONE OF OUR PAGES (a same-origin referrer)
 *     and the tab has an entry behind it. The length check matters: a link
 *     opened in a new tab carries our referrer and has nothing to go back to.
 *
 * Neither signal ⇒ false, and the caller keeps the Discover link. Reading
 * nothing (no Performance API, an odd referrer) also lands there, which is the
 * old behaviour, so a wrong "no" costs what the bug cost and never sends the
 * reader off the site.
 */
export interface InAppBackEnv {
  /** `window.location` (only `origin` and `pathname` are read). */
  location: { origin: string; pathname: string };
  /** `window.history.length`. */
  historyLength: number;
  /** `document.referrer`. */
  referrer: string;
  /** The URL the document was loaded at (`PerformanceNavigationTiming.name`),
   *  or null when the browser does not expose it. */
  documentLoadUrl: string | null;
}

function pathOf(url: string, origin: string): string | null {
  try {
    const parsed = new URL(url, origin);
    return parsed.origin === origin ? parsed.pathname : null;
  } catch {
    return null;
  }
}

export function canGoBackInApp(env: InAppBackEnv): boolean {
  if (env.historyLength < 2) return false;
  const { origin, pathname } = env.location;

  if (env.documentLoadUrl) {
    const loadedPath = pathOf(env.documentLoadUrl, origin);
    if (loadedPath !== null && loadedPath !== pathname) return true;
  }

  return env.referrer !== "" && pathOf(env.referrer, origin) !== null;
}

/** The live browser's answer. Server-side (no window) it is always false. */
export function browserCanGoBackInApp(): boolean {
  if (typeof window === "undefined") return false;
  let documentLoadUrl: string | null = null;
  try {
    const entry = window.performance?.getEntriesByType?.("navigation")?.[0];
    documentLoadUrl = entry?.name || null;
  } catch {
    documentLoadUrl = null;
  }
  return canGoBackInApp({
    location: window.location,
    historyLength: window.history.length,
    referrer: document.referrer,
    documentLoadUrl,
  });
}

/**
 * The back control's click. Returns true when it took the click (went back in
 * history); false leaves the link to do its own navigation to Discover. A
 * modified or non-primary click is never taken: cmd/ctrl-click and middle-click
 * mean "open this link elsewhere", and a new tab has no history to go back to.
 */
export function followBackInApp(
  event: {
    button: number;
    metaKey: boolean;
    ctrlKey: boolean;
    shiftKey: boolean;
    altKey: boolean;
    preventDefault: () => void;
  },
  goesInApp: boolean,
  goBack: () => void,
): boolean {
  if (!goesInApp) return false;
  if (event.button !== 0 || event.metaKey || event.ctrlKey || event.shiftKey || event.altKey) {
    return false;
  }
  event.preventDefault();
  goBack();
  return true;
}
