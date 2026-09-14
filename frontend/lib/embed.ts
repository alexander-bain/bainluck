// #5914 — the embed contract, in one greppable place.
//
// Native loads `https://bainluck.com/about?embed=1` in the one `InAppWebView`
// the app has (its only caller is `AboutView`), so the About screen is a web
// page inside a native screen. Without a signal it draws the whole website
// inside that screen: the site header with its own "Sign in" button, a bottom
// tab bar directly above the native one and disagreeing with it, and a cookie
// consent banner for tracking the app never asked for.
//
// WHY A QUERY PARAMETER AND NOT A USER-AGENT MARKER (the issue offered both,
// and native/168 argued this out before building):
//
//   * A UA marker has to be read with `headers()`, and a `headers()` read in
//     the ROOT layout makes every route on the site dynamic — a latency cost
//     paid by every reader of every page to fix one screen.
//   * A parameter is reproducible outside the app. `bainluck.com/about?embed=1`
//     opens in any browser, `tools/look.sh` can photograph it, and a session
//     with no iPhone can still see the defect. A UA-only signal is invisible to
//     every rig we have.
//   * `git grep embed=1` finds both halves of the contract.
//
// THE PATH IS PART OF THE PREDICATE, NOT DECORATION. `?embed=1` suppresses
// chrome on `/about` and nowhere else. If the flag were honoured site-wide, one
// tap from About onto a link would leave a chromeless Discover sitting under a
// native title bar that still says "About" — a different wrong screen, and one
// nobody would think to look for. Scoping it to the path makes "scoped to
// About" literally true rather than true by convention, and it means a stray
// `?embed=1` pasted onto any other URL is inert.
//
// Kept as a PURE function of two strings, deliberately: the interesting part of
// this contract is a decision, and a decision that needs React mounted to be
// tested is a decision nobody tests at its edges.

/** The query parameter native appends. Half of the contract; native holds the other. */
export const EMBED_PARAM = "embed";

/** Its only honoured value. Anything else is not an embed. */
export const EMBED_VALUE = "1";

/** The one path on which the flag means anything. */
export const EMBED_PATH = "/about";

/**
 * Is this request the native About embed?
 *
 * @param pathname the current path, as `usePathname()` reports it (no query).
 * @param value    the raw `?embed=` value, or null when the parameter is absent.
 *
 * Both arguments are nullable because both of their React sources are: a client
 * component can render before either resolves, and "not yet known" must read as
 * NOT an embed. Defaulting the other way would blank the site's chrome for a
 * frame on every page load.
 */
export function isEmbeddedAbout(
  pathname: string | null | undefined,
  value: string | null | undefined
): boolean {
  return pathname === EMBED_PATH && value === EMBED_VALUE;
}
