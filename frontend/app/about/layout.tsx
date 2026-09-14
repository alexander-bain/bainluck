// #5914 — `/about` renders per request, and this file exists only to say so.
//
// MEASURED, NOT ASSUMED. With `/about` statically prerendered, the shell that
// ships is whatever `EmbedGate`'s Suspense fallback renders — the site chrome,
// which is correct for every reader outside the app and wrong for the one
// inside it. Served from this tree before adding this file:
//
//     /about            header=1  bottomnav=1
//     /about?embed=1    header=1  bottomnav=1     <- the embed, with the chrome
//     /calibration      header=1  bottomnav=1
//
// `useSearchParams()` cannot resolve at build time, so the embed got the header
// and the bottom tab bar in its HTML and removed them at hydration. That is a
// visible flash and a layout shift inside the native About screen — the content
// jumps up as the header disappears — which reads to a reviewer as a bug, and
// is precisely the "one coherent page" this ship is for.
//
// A route segment marked dynamic is rendered per request, so the client
// components in its tree see the real query string during SSR and the chrome is
// never in the embed's HTML at all.
//
// WHY THIS IS CHEAP, AND WHY IT IS SCOPED TO A DIRECTORY. The cost of dynamic
// rendering is a server render per request instead of a cached file. `/about`
// fetches nothing on the server — its one data call (`fetchCalibration`) is
// client-side SWR — so the work is rendering a static tree of prose. It is a
// low-traffic marketing page. And because this is `app/about/layout.tsx`, the
// cost falls on this segment ALONE: every other route on the site keeps exactly
// the rendering mode it had, which is the same property that made native/168
// reject a `headers()` read in the ROOT layout. That objection was right, and
// it applies to this file too — which is why it is not in the root.
//
// The alternative was to leave the flash and file it. Rejected: it is the
// defect the ship is named for, visible on the screen being reviewed.

export const dynamic = "force-dynamic";

export default function AboutLayout({ children }: { children: React.ReactNode }) {
  return <>{children}</>;
}
