/**
 * UX-P235 — THE FALLBACK LOOKS LIKE A FALLBACK (board item 14, second half).
 *
 * `__tests__/lib/brandLogoRefusal.test.ts` covers which pictures we refuse. This
 * covers what a reader sees when we have none.
 *
 * ═══ THE DEFECT ═══
 *
 * The old fallback was a SOLID slate disc with bold white initials. On a row of
 * real brand marks that reads as a designed logo tile: Alex saw *"Amazon renders a
 * generic grey 'A'"* and read it as Amazon's mark being wrong, not as us not
 * knowing. Item 14's rule is *a wrong logo is worse than no logo* — and a fallback
 * that impersonates a logo is the quiet version of the same lie.
 *
 * ═══ THE LINE THIS FILE DEFENDS, IN BOTH DIRECTIONS ═══
 *
 * The over-correction is just as real: `RelatedFutures` and `TeamPropFamilies` pass
 * a TEAM colour. That disc is not impersonating anything — the colour IS
 * information, and a reader recognises it. So the placeholder treatment applies to
 * the DEFAULT slate only, and the coloured path must survive untouched.
 */

import React from "react";
import { renderToStaticMarkup } from "react-dom/server";

import EntityImage from "../../components/EntityImage";

/** Text a reader actually sees — a character scan, never a tag-stripping regex. */
function visibleText(html: string): string {
  let out = "";
  let inTag = false;
  for (const ch of html) {
    if (ch === "<") inTag = true;
    else if (ch === ">") inTag = false;
    else if (!inTag) out += ch;
  }
  return out.trim();
}

function attrs(html: string): Record<string, string> {
  const out: Record<string, string> = {};
  for (const m of html.matchAll(/([a-zA-Z-]+)="([^"]*)"/g)) out[m[1]] = m[2];
  return out;
}

// SSR renders before the async Wikipedia lookup resolves, so every render below is
// the fallback path by construction — which is exactly the path under test.
const render = (props: Parameters<typeof EntityImage>[0]) =>
  renderToStaticMarkup(<EntityImage {...props} />);

describe("UX-P235: no logo reads as no logo", () => {
  test("the default fallback is a PLACEHOLDER, not a filled brand tile", () => {
    const html = render({ type: "wikipedia", name: "Amazon" });
    expect(html).toContain('data-testid="entity-image-placeholder"');
    // Outlined and muted, not a solid coloured disc.
    expect(html).toContain("border-dashed");
    expect(html).not.toContain("background-color");
    expect(html).not.toContain("text-white/90");
  });

  test("it still carries the initials, so the row is still scannable", () => {
    // The placeholder is quieter, not empty — a blank circle is worse than "A".
    expect(visibleText(render({ type: "wikipedia", name: "Amazon" }))).toBe("A");
    expect(visibleText(render({ type: "wikipedia", name: "Paramount Plus" }))).toBe("PP");
  });

  test("it SAYS it is a placeholder to assistive tech", () => {
    // The initials alone are not an accessible name, and a screen reader must not
    // be told "A" as though that were the brand.
    const a = attrs(render({ type: "wikipedia", name: "Amazon" }));
    expect(a["role"]).toBe("img");
    expect(a["aria-label"]).toBe("Amazon (no logo available)");
    expect(a["title"]).toBe("Amazon");
  });

  test("the geometry is unchanged, so nothing shifts when a logo does resolve", () => {
    const html = render({ type: "wikipedia", name: "Amazon", size: 24 });
    expect(html).toContain("width:24px");
    expect(html).toContain("height:24px");
    expect(html).toContain("rounded-full");
  });
});

describe("UX-P235: a real colour is information and survives", () => {
  test("an explicit team colour still renders the solid disc", () => {
    const html = render({ type: "wikipedia", name: "Boston Celtics", fallbackColor: "#007A33" });
    expect(html).toContain('data-testid="entity-image-initials"');
    expect(html).toContain("#007A33");
    expect(html).toContain("text-white/90");
    expect(html).not.toContain("border-dashed");
  });

  test("a coloured chip is named plainly — it is not claiming to be a placeholder", () => {
    const a = attrs(render({ type: "wikipedia", name: "Boston Celtics", fallbackColor: "#007A33" }));
    expect(a["aria-label"]).toBe("Boston Celtics");
  });

  test("the two paths are DISTINGUISHABLE — that is the whole point", () => {
    const plain = render({ type: "wikipedia", name: "Amazon" });
    const coloured = render({ type: "wikipedia", name: "Amazon", fallbackColor: "#007A33" });
    expect(plain).not.toBe(coloured);
  });

  test("passing the default colour EXPLICITLY is still the placeholder", () => {
    // The rule is about whether we know a colour, not about who typed it.
    const html = render({ type: "wikipedia", name: "Amazon", fallbackColor: "#6B7280" });
    expect(html).toContain('data-testid="entity-image-placeholder"');
  });
});
