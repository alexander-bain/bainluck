/**
 * UX-P177 artifact rig — renders `artifacts-ux-p177/related-by-tag-states.html`.
 *
 * Three panels, all from real components and one verbatim production payload:
 *
 *   BEFORE   `__tests__/fixtures/uxp177RelatedByTagLegacy.tsx` — the verbatim
 *            pre-fix `components/RelatedByTag.tsx`, extracted with
 *            `git show 1668221c:frontend/components/RelatedByTag.tsx`. This is a
 *            render of the code that shipped, NOT a drawing of it.
 *   AFTER    the shipped `components/RelatedByTag.tsx`, same payload.
 *   CONTROL  the shipped component on a futures-only payload — the ordinary row
 *            must still say what it always said. A repair that fixed concepts
 *            by disturbing the futures row would pass every other assertion in
 *            this queue.
 *
 * ⚠️ **THE CONTROL WAS A BYTE COMPARISON AND IS NOT ANY MORE (ux/1034 B6).**
 * `expect(control).toBe(controlBefore)` was the right test while the only change
 * on the table was a concept repair that had no business touching a futures row.
 * B6 restyles the ordinary row ON PURPOSE — Alex, on `/events/15293830`: this
 * section is *"formatted horribly"*, *"make it the same card grid the hub
 * uses"* — so byte-equality is now asserting that a ruling was not carried out.
 *
 * What the control is actually for survives the restyle and is what it tests
 * now: the ordinary futures row still names its subject, still prints its
 * probability, and still links to its own market. Those are the three things
 * UX-P177's repair could have broken; the chassis around them was never the
 * claim. The legacy render is still produced, because the artifact's third
 * panel is a before/after and needs both.
 *
 * The payload is `uxp177_related_mma_before.json`: a verbatim `/api/feed` body
 * read from production on 2026-08-29 through the exact URL the component builds
 * (`limit=9`, i.e. `limit + 5`). Nothing in it is assembled.
 *
 * The rig asserts its own output — an artifact that silently captured the wrong
 * thing is worse than no artifact.
 */

import React from "react";
import { renderToStaticMarkup } from "react-dom/server";
import fs from "fs";
import path from "path";

import SERVED from "../fixtures/uxp177_related_mma_before.json";

let swrPayload: unknown;

jest.mock("swr", () => ({
  __esModule: true,
  default: () => ({ data: swrPayload, error: undefined, isLoading: false }),
}));

// eslint-disable-next-line @typescript-eslint/no-var-requires
const RelatedByTag = require("@/components/RelatedByTag").default;
// eslint-disable-next-line @typescript-eslint/no-var-requires
const RelatedByTagLegacy =
  require("../fixtures/uxp177RelatedByTagLegacy").default;

function render(Component: unknown, payload: unknown, title: string): string {
  swrPayload = payload;
  return renderToStaticMarkup(
    React.createElement(Component as React.FC, {
      tags: ["sport:mma"],
      limit: 4,
      title,
    } as never)
  );
}

function visibleText(markup: string): string {
  return markup
    .replace(/<[^>]*>/g, " ")
    .replace(/&#x27;|&apos;/g, "'")
    .replace(/&amp;/g, "&")
    .replace(/\s+/g, " ")
    .trim();
}

/** A plain futures payload — the row this fix must leave completely alone. */
const FUTURES_ONLY = {
  items: [
    {
      type: "futures",
      data: {
        id: 196,
        name: "Middleweight Title Holder on Dec 31, 2026?",
        top_outcomes: [{ name: "Khamzat Chimaev", probability: 0.62 }],
      },
    },
    {
      type: "futures",
      data: {
        id: 197,
        name: "Lightweight Title Holder on Dec 31, 2026?",
        top_outcomes: [{ name: "Islam Makhachev", probability: 0.55 }],
      },
    },
  ],
};

describe("UX-P177 artifact", () => {
  it("renders the three panels and asserts what each one must show", () => {
    const before = render(RelatedByTagLegacy, SERVED, "More Mma");
    const after = render(RelatedByTag, SERVED, "More Mma");
    const control = render(RelatedByTag, FUTURES_ONLY, "More Mma");

    // ── BEFORE must show the defect, or the artifact is a strawman ──
    expect(before).toContain("/futures/undefined");
    expect(before.match(/href="\/futures\/undefined"/g)).toHaveLength(4);
    // …and three of the four rows are the wrong sport.
    expect(visibleText(before)).toContain("Vuelta a España");
    expect(visibleText(before)).toContain("Dutch Grand Prix");
    // …with no probability beside any of them.
    expect(visibleText(before)).not.toContain("Tadej Pogacar");

    // ── AFTER must show neither the dead link nor an empty section ──
    expect(after).not.toContain("/futures/undefined");
    expect(after).toContain("/event/ufc/26aug29");
    expect(after.match(/href="/g)).toHaveLength(4);
    expect(visibleText(after)).toContain("Tadej Pogacar");

    // ── CONTROL: the ordinary futures row still SAYS what it always said ──
    //
    // Not byte-for-byte any more — see the ⚠️ at the top of this file. Every
    // fact the legacy row published is required to survive into the new one,
    // and the assertion is written that way round (legacy is the source of the
    // expectation) so it cannot be satisfied by a row that prints something
    // else and happens to contain the right substring.
    const controlBefore = render(RelatedByTagLegacy, FUTURES_ONLY, "More Mma");
    const hrefs = (markup: string) => markup.match(/href="[^"]*"/g) ?? [];
    expect(hrefs(control)).toEqual(hrefs(controlBefore));
    for (const fact of ["Khamzat Chimaev", "62%", "Islam Makhachev", "55%"]) {
      expect(visibleText(controlBefore)).toContain(fact);
      expect(visibleText(control)).toContain(fact);
    }
    expect(control).toContain("/futures/196");
    // And the restyle is real, not a no-op the assertions above would tolerate.
    expect(control).not.toBe(controlBefore);

    const panel = (title: string, note: string, markup: string) => `
      <section>
        <h2>${title}</h2>
        <p class="note">${note}</p>
        <div class="frame">${markup}</div>
      </section>`;

    const html = `<!doctype html>
<html><head><meta charset="utf-8">
<title>UX-P177 — "More MMA" stops sending readers to dead links for the wrong sport</title>
<script src="https://cdn.tailwindcss.com"></script>
<style>
  body { background:#f6f7f9; font-family:ui-sans-serif,system-ui,sans-serif; margin:0; padding:24px; }
  h1 { font-size:20px; margin:0 0 4px; }
  .sub { color:#555; font-size:13px; margin:0 0 24px; max-width:940px; }
  section { margin-bottom:28px; }
  h2 { font-size:15px; margin:0 0 4px; }
  .note { color:#666; font-size:12px; margin:0 0 8px; max-width:940px; }
  .frame { background:#fff; border:1px solid #dcdfe4; border-radius:10px; padding:12px; max-width:560px; }
  code { background:#eceef1; padding:1px 4px; border-radius:3px; }
</style></head>
<body>
<h1>UX-P177 — the &ldquo;More MMA&rdquo; section stops sending readers to dead links for the wrong sport</h1>
<p class="sub">Every panel is a real React render. BEFORE is
<code>__tests__/fixtures/uxp177RelatedByTagLegacy.tsx</code>, the verbatim pre-fix
<code>components/RelatedByTag.tsx</code>; AFTER and CONTROL are the shipped component. The payload is a
verbatim production <code>/api/feed?limit=9&amp;tags=["sport:mma"]</code> body read 2026-08-29 —
the exact request the component builds. Nothing here is assembled.</p>
${panel(
  "BEFORE — bainluck.com/futures/195, today",
  'Four rows. Three are not MMA (Vuelta a España, two Grands Prix). All four link to <code>/futures/undefined</code>, because a concept has no numeric id and the component treated every non-event, non-tournament item as a futures market. None carries a probability.',
  before
)}
${panel(
  "AFTER — the same payload, the shipped fix",
  'Every row links to its concept page (<code>/event/ufc/26aug29</code>), and each carries its leader and probability. The foreign rows are still here because this panel isolates the RENDER fix — the backend filter that stops F1 and cycling reaching an MMA surface is proven separately in <code>backend/tests/test_feed_concept_tag_filter.py</code>, and after deploy this list is UFC-only.',
  after
)}
${panel(
  "CONTROL — an ordinary futures payload, restyled by ux/1034 B6",
  "Every fact the legacy row published — subject, probability, link — is asserted to survive into this one. The chassis is deliberately different: Alex ruled this section &ldquo;formatted horribly&rdquo; and asked for the hub&rsquo;s card grid.",
  control
)}
</body></html>`;

    const out = path.join(__dirname, "../../../artifacts-ux-p177");
    fs.mkdirSync(out, { recursive: true });
    fs.writeFileSync(path.join(out, "related-by-tag-states.html"), html);
  });
});
