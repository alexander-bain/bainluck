"use client";

import { Suspense } from "react";
import { usePathname, useSearchParams } from "next/navigation";
import { EMBED_PARAM, isEmbeddedAbout } from "@/lib/embed";

// #5914 — renders its children everywhere EXCEPT inside the native About embed.
//
// The three things this wraps in `app/layout.tsx` are the three defects in
// native/168's photograph, and all three come from the root layout rather than
// from `app/about/`: the site header (whose "Sign in" button would start the
// WEBSITE's session inside the app, unrelated to the app's own Apple/Google
// auth), `BottomNav` (which draws directly above the native tab bar and
// disagrees with it about which tab the reader is on), and the consent banner.
//
// ENFORCEMENT IS BY ABSENCE, WHICH IS THE WHOLE POINT FOR THE THIRD ONE.
// `TelemetryGate` is wrapped too, and codex's directive is explicit that the
// embed should OMIT the tracking rather than hide the banner that asks about
// it: a suppressed banner over a live GA4 rail would be the one outcome worse
// than shipping today's screen unchanged. Because a provider that is never
// rendered cannot load its script, wrapping the gate is the enforcement —
// there is no opt-out flag here to trust. `TelemetryGate.tsx` makes the same
// argument for the same reason one level down.
//
// ── WHY THE SUSPENSE BOUNDARY IS INSIDE THIS COMPONENT ──────────────────────
//
// `useSearchParams()` forces any statically-prerendered route containing it to
// bail out unless it sits under a Suspense boundary, and this component is
// mounted in the ROOT layout, so "any route" means the whole site. Putting the
// boundary at each of the four call sites would be the same four lines written
// four times and would make the fallback a call-site decision, which is exactly
// the thing that drifts. `NavigationProgress` already establishes this pattern
// in the same file, for the same reason.
//
// ── WHY THE FALLBACK IS THE CHILDREN, AND WHERE IT IS NOT ───────────────────
//
// While the boundary is suspended — which on a static route means the
// prerendered HTML itself — the fallback is what ships. For the site's CHROME
// the honest fallback is the chrome: every route but one is not an embed, so
// rendering it is right in the overwhelming case and there is no flash of a
// headerless site on an ordinary page load.
//
// For `TelemetryGate` the same default would be wrong in the one direction
// that matters, so the call site passes `fallback={null}`: mounting an
// analytics rail and unmounting it a moment later still loaded gtag.js and
// still set the cookie. Un-firing a beacon is not a thing. Deferring one is,
// and `TelemetryGate` is a client component that reads stored consent, so it
// could never have done anything before hydration anyway — the deferral costs
// nothing real.

function EmbedGateInner({ children }: { children: React.ReactNode }) {
  const pathname = usePathname();
  const embedValue = useSearchParams().get(EMBED_PARAM);
  return isEmbeddedAbout(pathname, embedValue) ? null : <>{children}</>;
}

export default function EmbedGate({
  children,
  fallback,
}: {
  children: React.ReactNode;
  /** What ships in the static shell. Defaults to `children`; pass `null` for anything with a side effect. */
  fallback?: React.ReactNode;
}) {
  return (
    <Suspense fallback={fallback === undefined ? children : fallback}>
      <EmbedGateInner>{children}</EmbedGateInner>
    </Suspense>
  );
}
