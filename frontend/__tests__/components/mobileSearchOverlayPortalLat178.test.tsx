/**
 * LAT-P178 — the mobile search overlay must escape the header's containing block.
 *
 * THE BUG THIS PINS (measured on production 2026-09-06, phone width 390px):
 * Alex typed a search on his phone and "typeahead never appeared". The API was
 * healthy the whole time — `/api/events/typeahead?q=red%20sox` answered 200 with
 * 7 suggestions in 0.14s, and the browser received them: the rows were in the
 * DOM with `data-testid="search-suggestion"`.
 *
 * They were still invisible, because `MobileSearchTrigger` renders the overlay
 * as a sibling of the search button — i.e. INSIDE
 *   `app/layout.tsx` → <header class="... backdrop-blur-lg ...">
 * and a non-`none` `backdrop-filter` makes that element the CONTAINING BLOCK
 * for every `position: fixed` descendant. So the overlay's root
 * `fixed inset-0` sized itself against the 57px header instead of the viewport:
 *
 *   div.fixed.inset-0.z-[100]   height  56   <- should be the viewport
 *   div.flex-1.overflow-y-auto  height   0   <- the results list
 *   button[data-testid=search-suggestion] at y=59, clipped outside both
 *
 * `elementFromPoint()` at the first suggestion's centre returned the page
 * header, not the suggestion — so it was neither readable nor tappable. Note
 * that Playwright's `state: 'visible'` reported it VISIBLE (non-zero box, not
 * `display:none`), which is why an automated pass can miss this entirely; only
 * the screenshot and the hit test caught it.
 *
 * THE GUARD: the overlay is portalled to `document.body`, which leaves the
 * header subtree — and therefore the header's containing block — behind.
 * Removing the blur would also "fix" it, but that is a design-system change;
 * the portal is invisible to the design system, so the portal is the fix.
 *
 * These run under `testEnvironment: 'node'` like the rest of the suite (there
 * is no jsdom in this repo), so the behavioural assertion is made through the
 * SERVER renderer, which is exactly the discriminating case: the portal target
 * is resolved in an effect, effects do not run during SSR, so a portalled
 * overlay emits nothing while an inline one emits its `fixed inset-0` root.
 */

import { renderToStaticMarkup } from "react-dom/server";
import React from "react";
import { readFileSync } from "fs";
import path from "path";

// The component is a client component that reaches for the app-router and the
// analytics context on its first line. Neither exists under the server
// renderer, and neither is what this file is about, so both are stubbed — the
// assertions below are about WHERE the markup lands, not about navigation.
jest.mock("next/navigation", () => ({
  useRouter: () => ({ push: jest.fn() }),
  usePathname: () => "/",
}));
jest.mock("@/components/Analytics", () => ({
  useAnalyticsContext: () => ({ track: jest.fn() }),
}));

import MobileSearchOverlay from "@/components/MobileSearchOverlay";

const repoFile = (rel: string) =>
  readFileSync(path.join(__dirname, "..", "..", rel), "utf8");

describe("LAT-P178 mobile search overlay portal", () => {
  it("never emits its fixed root inline, even when open", () => {
    // Before the fix this rendered the full overlay markup straight into
    // whatever subtree the trigger sits in — the header. That inline render IS
    // the bug, so its absence is the thing worth pinning.
    const markup = renderToStaticMarkup(
      <MobileSearchOverlay isOpen onClose={() => {}} />
    );
    expect(markup).toBe("");
    expect(markup).not.toMatch(/fixed inset-0/);
  });

  it("closed is still closed", () => {
    const markup = renderToStaticMarkup(
      <MobileSearchOverlay isOpen={false} onClose={() => {}} />
    );
    expect(markup).toBe("");
  });

  it("portals to document.body rather than rendering in place", () => {
    const src = repoFile("components/MobileSearchOverlay.tsx");
    expect(src).toMatch(/createPortal/);
    expect(src).toMatch(/document\.body/);
    // The root must be an ARGUMENT to createPortal, not a plain `return (`.
    expect(src).toMatch(/return createPortal\(/);
  });

  it("stays required for as long as the header carries a backdrop-filter", () => {
    // Conditional on purpose: if the blur is ever removed the portal stops
    // being load-bearing and this must NOT fail spuriously. What it refuses is
    // the combination that produced the bug — a blurred header that mounts the
    // trigger, with an overlay that does not portal out of it.
    const layout = repoFile("app/layout.tsx");
    const headerIsBlurred = /<header[^>]*backdrop-blur/.test(layout);
    const headerMountsTrigger = /MobileSearchTrigger/.test(layout);
    if (headerIsBlurred && headerMountsTrigger) {
      const src = repoFile("components/MobileSearchOverlay.tsx");
      expect(src).toMatch(/return createPortal\(/);
    }
  });
});
