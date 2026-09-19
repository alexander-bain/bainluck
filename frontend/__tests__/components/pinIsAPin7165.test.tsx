/**
 * #7165 — THE UNPINNED PIN WAS A TROPHY, AND THAT IS WHY A LANE READ A WINNER.
 *
 * ═══ WHAT WAS ON PRODUCTION ═══
 *
 * `/events/15312403` (Port Adelaide v Sydney, AFL) at 390px, 2026-09-19: the hero's
 * meta row read — icon, then the words — "No result reported", over a match with
 * `status=suspended`, both scores null, `venue_settled=false`, and a venue that
 * still had it trading at 0.36/0.64. Nobody had graded it, including Polymarket.
 *
 * The issue was filed as *settled chrome on an ungraded game*: a trophy saying the
 * match finished and we lost the winner. The icon is not settled chrome. It is the
 * PIN BUTTON in its unpinned state, and it was drawn as a goblet — four strokes
 * (capped bar, inverted trapezoid, stem, foot) that at 14–16px is a trophy and
 * nothing else. Rendered side by side at 48px it is not arguable.
 *
 * So the framing in the issue is corrected here rather than inherited: the copy
 * "No result reported" is right for a match whose clock ran out ungraded, the
 * state model is right, and the only thing lying on that hero was the icon. It was
 * lying on every surface with a pin — it just took a page whose text says "no
 * result" for the lie to become a sentence a reader could finish.
 *
 * ═══ WHAT THE FIX IS, AND WHAT THESE TESTS HOLD ═══
 *
 * One `PIN_PATH`, drawn filled when pinned and stroked when not, so the two states
 * are one object in two treatments. No new artwork: the outline is the silhouette
 * that was already shipping in the filled state.
 *
 * 🔴 THE ASSERTION THAT MATTERS is not "the goblet is gone" — that is true of any
 * tree where somebody deleted four lines. It is that the two states SHARE a path.
 * A future edit can only reintroduce a second object by making these disagree, and
 * the byte-level "goblet gone" check below cannot see a *new* wrong shape at all.
 * Both are here; only one of them is load-bearing.
 *
 * ⚠️ SOURCE ASSERTIONS RUN THROUGH `codeOnly`. `pinAffordance.test.tsx` records
 * this trap twice in its own history: an assertion of the form "this must no longer
 * appear" goes red on the change that removes it, because the change quotes what it
 * replaced in the comment explaining itself. These comments name the goblet in
 * prose for exactly that reason and never reproduce its path data.
 */

import React from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { readdirSync, readFileSync } from "fs";
import { join } from "path";

import { PinIcon, PIN_PATH, PinButton } from "../../components/PinButton";

/** Source with comments stripped, so a comment cannot satisfy or break a claim. */
function codeOnly(src: string): string {
  return src.replace(/\/\*[\s\S]*?\*\//g, "").replace(/^\s*\/\/.*$/gm, "");
}

/** Every `d="…"` in a fragment of SSR markup, in document order. */
function paths(html: string): string[] {
  return [...html.matchAll(/\sd="([^"]*)"/g)].map((m) => m[1]);
}

/**
 * The four surfaces that drew a pin when this was written — the population the
 * byte-level check below sweeps.
 *
 * ⚠️ IT IS A LIST AND A LIST CANNOT SEE A FIFTH SURFACE, which is the only way the
 * defect returns. That is why the copy-counting test below walks the tree instead
 * and this list is used only where the claim is about these four specifically.
 */
const PIN_SURFACES = [
  "app/events/[id]/page.tsx",
  "components/EventCard.tsx",
  "components/FuturesCard.tsx",
  "components/PinButton.tsx",
] as const;

const read = (rel: string) => readFileSync(join(__dirname, "../../", rel), "utf8");

/** Every `.tsx`/`.ts` under `app/` and `components/`, repo-relative, tests excluded. */
function sourceFiles(): string[] {
  const out: string[] = [];
  const walk = (rel: string) => {
    for (const e of readdirSync(join(__dirname, "../../", rel), { withFileTypes: true })) {
      const next = rel ? `${rel}/${e.name}` : e.name;
      if (e.isDirectory()) {
        if (e.name === "node_modules" || e.name === "__tests__") continue;
        walk(next);
      } else if (/\.tsx?$/.test(e.name)) {
        out.push(next);
      }
    }
  };
  walk("app");
  walk("components");
  return out;
}

describe("#7165: the pin is one object in two treatments", () => {
  test("🔴 pinned and unpinned draw the SAME path — the states cannot be two objects", () => {
    // THE ASSERTION THIS FILE EXISTS FOR. The defect was not a bad path, it was
    // TWO paths: a pushpin for `filled` and a goblet for the outline. Anything
    // that re-splits them fails here, whatever the second shape happens to be.
    const off = paths(renderToStaticMarkup(<PinIcon filled={false} className="w-4 h-4" />));
    const on = paths(renderToStaticMarkup(<PinIcon filled className="w-4 h-4" />));

    expect(off).toEqual([PIN_PATH]);
    expect(on).toEqual([PIN_PATH]);
  });

  test("the unpinned state is still visibly DISTINCT — hollow, not merely paler", () => {
    // Sharing the path must not cost the state its legibility: a reader tells the
    // two apart by fill, and `pinAffordance.test.tsx` already guards that contract
    // at the button. Held here at the icon too, because this change is what could
    // break it.
    const off = renderToStaticMarkup(<PinIcon filled={false} className="w-4 h-4" />);
    const on = renderToStaticMarkup(<PinIcon filled className="w-4 h-4" />);

    expect(off).toContain('fill="none"');
    expect(off).toContain('stroke="currentColor"');
    expect(on).toContain('fill="currentColor"');
    expect(on).not.toContain('stroke="currentColor"');
    expect(off).not.toBe(on);
  });

  test("the outline is stroked thin enough to stay a pin at 14px", () => {
    // Not a taste assertion: at strokeWidth 2 the notch between the pin's head and
    // its shaft closes at these sizes and the icon fills in to a blob, which is how
    // a hollow pushpin becomes an unreadable smudge rather than a pin.
    const off = renderToStaticMarkup(<PinIcon filled={false} className="w-3.5 h-3.5" />);
    expect(off).toContain('stroke-width="1.5"');
  });

  test("the goblet is drawn by no surface, and the shared icon is what they draw", () => {
    // The byte-level half. Weaker than the path-identity test above — it can only
    // see THIS wrong shape — but it is the one that proves the three copies are
    // actually gone rather than merely corrected in place.
    for (const rel of PIN_SURFACES) {
      const code = codeOnly(read(rel));
      // The goblet's stem and foot. Two of its four strokes are enough: no pushpin
      // silhouette contains a bare vertical line segment.
      expect(code).not.toContain("M12 11v6");
      expect(code).not.toContain("M9 17h6");
    }
  });

  test("🔴 no surface defines its own PinIcon — the shared one is the only one", () => {
    // The copies are the mechanism, not the icon. Three byte-identical definitions
    // are why one wrong shape shipped on four surfaces at once and why correcting
    // `PinButton.tsx` alone would have changed nothing a reader sees.
    //
    // 🔴 SWEPT, NOT LISTED. A hard-coded list is blind to the only thing that can
    // bring the defect back — a FIFTH surface — which is the same mistake as
    // enumerating the renderings inside one component. The whole of `app/` and
    // `components/` is read.
    const all = sourceFiles();
    expect(all.length).toBeGreaterThan(100); // the walk found a tree, not nothing

    const owners = all.filter((rel) => /function PinIcon\b/.test(codeOnly(read(rel))));
    expect(owners).toEqual(["components/PinButton.tsx"]);

    // And every surface that DRAWS one gets it from there.
    const drawers = all.filter((rel) => /<PinIcon\b/.test(codeOnly(read(rel))));
    expect(drawers.length).toBeGreaterThanOrEqual(4);
    for (const rel of drawers) {
      if (rel === "components/PinButton.tsx") continue;
      expect(codeOnly(read(rel))).toContain('from "@/components/PinButton"');
    }
  });

  test("the button that ships to readers carries the shared path, both ways", () => {
    // Rendered through `PinButton`, not the icon alone: the icon being right is not
    // the same claim as the icon reaching the markup a surface serves.
    for (const pinned of [false, true]) {
      const html = renderToStaticMarkup(<PinButton pinned={pinned} onToggle={() => {}} />);
      expect(paths(html)).toContain(PIN_PATH);
    }
  });
});

describe("#7165: what the hero's icon sat beside is NOT changed", () => {
  const PAGE = read("app/events/[id]/page.tsx");

  test("the suspended badge keeps its sentence and its one state answer", () => {
    // The issue asked for the copy to change too — "No result reported" being the
    // wrong sentence for a game that is not over. It is the RIGHT sentence for this
    // specimen: the AFL match kicked off at 04:35Z and was read four hours later,
    // so its clock had long run out with nobody reporting an end, which is exactly
    // the state `eventState.ts` defines and the words it chose for it.
    //
    // Held as a test because the descope has to survive me: a later pass reading
    // #7165 and finding the icon fixed must not "finish the job" by editing shared
    // card vocabulary that four other consumers of `isSuspended` depend on (#4015).
    const code = codeOnly(PAGE);
    expect(code).toContain('data-testid="event-hero-suspended"');
    expect(code).toContain("hasNoReportedResult(event?.status, event?.commence_time)");
    expect(code).toContain("venueSettledSentence ??");
  });
});
