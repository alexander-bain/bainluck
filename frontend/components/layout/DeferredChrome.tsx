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
