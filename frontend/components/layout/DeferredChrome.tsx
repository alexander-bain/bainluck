"use client";

/**
 * LAT-P200 — the layout's `next/dynamic` calls were declared and never split.
 *
 * `app/layout.tsx` is a Server Component. It declared three pieces of header
 * chrome with `dynamic(() => import(...), { ssr: false })`, which reads as
 * "keep this off the first load". Measured against the deployed bundle
 * (2026-09-02, master 04f6cc6f): all three landed in the EAGER
 * `app/layout-*.js` entry chunk anyway, together with the whole typeahead
 * subsystem they pull in — 41.8 kB of the chunk's own weight, on the critical
 * path of every route in the app.
 *
 * The mechanism: a Server Component cannot lazily reference a Client
 * Component. Every client module a server layout names becomes a client
 * *reference* of that layout, and Next bundles the layout's client references
 * into its entry chunk. `dynamic()` wraps the module in `React.lazy`, but the
 * module is already in the graph by then, so webpack has nothing left to split
 * out. The declaration was honest about the intent and inert in effect.
 *
 * Moving the same three `dynamic()` calls behind THIS client boundary is what
 * makes them real: `import()` inside a client module is a genuine split point,
 * so webpack emits async chunks and the entry chunk stops carrying them.
 *
 * Guarded by `__tests__/lib/serverLayoutDynamicImports.test.ts`, which fails if
 * `next/dynamic` reappears in any Server Component — the regression is silent
 * (the code still works, it is just eagerly bundled again) and shows up in
 * nothing but a bundle nobody re-measures.
 *
 * The `loading` placeholders are not decoration. With `ssr: false` these slots
 * are already empty in the server HTML; deferring the chunk lengthens the
 * window before they fill, so each placeholder reproduces the final element's
 * box exactly to keep that window from becoming a layout shift.
 */

import dynamic from "next/dynamic";

const NavigationProgressImpl = dynamic(
  () => import("@/components/NavigationProgress"),
  { ssr: false },
);

const SearchBarImpl = dynamic(() => import("@/components/SearchBar"), {
  ssr: false,
  loading: SearchBarBox,
});

const MobileSearchTriggerImpl = dynamic(
  () => import("@/components/MobileSearchTrigger"),
  { ssr: false, loading: MobileSearchBox },
);

/**
 * LAT-P207 — the account menu, moved by the same mechanism and NOT by the same
 * rule.
 *
 * The three above are `ssr: false`: they are chrome the server cannot usefully
 * render, so their slots are empty in the HTML either way and the only question
 * was which chunk carries them. `UserMenu` is the opposite case. It renders
 * during SSR today, and what it renders is the "Sign in" button — because
 * `useAuth` starts with `user === null` on the server AND on the first client
 * render, and a first-run reader never leaves that state (no
 * `bainluck_previouslySignedIn` marker, so the hook returns before it ever
 * asks Firebase). The signed-out button is not a placeholder for the real
 * header on a cold load. It IS the real header, for essentially every cold
 * load the site gets.
 *
 * So `ssr: false` would be the wrong trade here: it would take a control that
 * is correct in the very first paint and replace it with a reserved box that
 * has to pop into text later — a visible flash bought with bytes that do not
 * leave the wire anyway. Keeping `ssr: true` means the HTML is unchanged
 * (verified with the Firebase env vars set, which is the only configuration
 * where this component renders at all) and React holds the server markup until
 * the chunk arrives instead of blanking it.
 *
 * What moves is the PRE-HYDRATION CRITICAL PATH, and ONLY that: as a client
 * reference of the Server Component root layout, this module was compiled into
 * the eager `app/layout-*.js` of all 40 routes, where it had to be downloaded
 * and parsed before anything hydrated. `import()` from inside this client
 * module is a real split point, so it becomes an async chunk instead.
 *
 * ═══ WHAT THIS COST, MEASURED — IT IS NOT A FREE WIN ════════════════════════
 *
 * LAT-P205's rule is that a deferral is only a cut if the branch is unreachable
 * on a cold load. This branch IS reachable: the chunk was fetched on 12 of 12
 * treatment cold runs with no interaction, because a server-rendered component
 * must hydrate. So unlike `lib/firebase.ts` or the challenge screens, nothing
 * leaves the wire — one more request is added to it. Measured on `/`,
 * deterministic to the byte across all 24 runs:
 *
 *   eager entry set   621,136 → 616,048 raw   ·   166,781 → 165,524 brotli
 *   `app/layout-*.js`  30,050 →  24,938 raw   ·     7,594 →   6,325 brotli
 *   wire per cold load  233,044 → 233,939 B   ·   +895 B, i.e. WORSE
 *
 * The net was still favourable but was NOT resolved in milliseconds: ttfc
 * −28.3 ms mean / −17.1 ms median at n=12+12, U = 103/144 (72 %), p ≈ 0.073.
 * Do not quote those milliseconds as the result — 1.26 kB brotli is a third of
 * this rig's resolving floor and no affordable n fixes that. The bytes and the
 * direction are the claim; the number is not.
 *
 * The other real cost: the account menu becomes CLICKABLE slightly later, since
 * it is now interactive when its own chunk lands rather than when the layout
 * chunk does. It is visible and correct throughout — only the click is late.
 *
 * Guarded in `__tests__/lib/emittedEntryGraph.test.ts`. Its marker is
 * `UserMenu`'s own dropdown aria-label and is deliberately not repeated here —
 * control 5 requires each marker to appear in exactly one source file.
 */
const UserMenuImpl = dynamic(() => import("@/components/UserMenu"));

/**
 * Same box as SearchBar's `compact` input: `px-4 py-1.5 text-sm` inside a
 * rounded-full bordered field. Renders the field, not its contents — nothing
 * here is focusable, so a keyboard user is never handed a dead input.
 */
function SearchBarBox() {
  return (
    <div className="relative" aria-hidden="true">
      <div className="w-full bg-surface-elevated border border-surface-border rounded-full px-4 py-1.5 text-sm text-transparent select-none">
        &nbsp;
      </div>
    </div>
  );
}

/** Same box as MobileSearchTrigger's button: `px-3 py-1.5 text-sm`, pill. */
function MobileSearchBox() {
  return (
    <div
      aria-hidden="true"
      className="w-full bg-surface-elevated/80 rounded-full px-3 py-1.5 text-sm text-transparent select-none"
    >
      &nbsp;
    </div>
  );
}

export function DeferredNavigationProgress() {
  return <NavigationProgressImpl />;
}

export function DeferredSearchBar({ compact }: { compact?: boolean }) {
  return <SearchBarImpl compact={compact} />;
}

export function DeferredMobileSearchTrigger() {
  return <MobileSearchTriggerImpl />;
}

export function DeferredUserMenu() {
  return <UserMenuImpl />;
}
