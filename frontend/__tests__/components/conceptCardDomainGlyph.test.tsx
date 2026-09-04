/**
 * UX-1052 item 1 — THE CONCEPT CARD'S GLYPH FOLLOWS ITS DOMAIN.
 *
 * Alex's 1:00pm 2026-09-03 shop of /sports, finding 1, verbatim:
 *
 *     "Cycling shows a boxing glove. 'Vuelta a España 2026 · 🥊 CYCLING'
 *      on /sports Live Now."
 *
 * `ConceptFeedCard` printed a literal `🥊` next to `data.domain.toUpperCase()`.
 * Not a lookup that missed — a hardcoded glove. Every concept card in the feed
 * wore it: the Vuelta, a golf major, a tennis draw, an election night.
 *
 * This file RENDERS. A unit test over `conceptDomainEmoji` would have passed on
 * the broken build, because the broken build never called it
 * (`reference_plant_must_hit_the_render`). Part 1 asserts the rendered markup;
 * Part 2 asserts the helper's refusal contract, which the render cannot show.
 *
 * The refusal matters as much as the mapping: an unmapped domain renders NO
 * glyph. A generic fallback (📊, or worse the old glove) is the same defect in
 * a quieter register — a glyph that is merely unrelated rather than wrong.
 */

import React from "react";
import { renderToStaticMarkup } from "react-dom/server";

jest.mock("next/link", () => {
  const ReactLib = require("react");
  return {
    __esModule: true,
    default: ({ href, children, ...props }: { href: string; children: React.ReactNode }) =>
      ReactLib.createElement("a", { href, ...props }, children),
  };
});

jest.mock("@/components/Analytics", () => ({
  useAnalyticsContext: () => ({ track: () => {} }),
}));

import FeedCard from "@/components/FeedCard";
import { conceptDomainEmoji } from "@/lib/eventConceptDisplay";
import type { FeedItem } from "@/lib/types";

const GLOVE = "🥊";

/** The exact card Alex was looking at: a live, marquee cycling grand tour. */
function conceptItem(domain: string, name: string): FeedItem {
  return {
    type: "concept",
    score: 90,
    reason: null,
    headline: null,
    data: {
      key: `event:${domain}:vuelta-2026`,
      name,
      domain,
      status: "live",
      is_major: true,
      leader: { name: "Tadej Pogacar", probability: 0.75, field_size: 30 },
    },
  } as unknown as FeedItem;
}

describe("UX-1052 item 1 — concept card domain glyph (render path)", () => {
  it("prints the CYCLING glyph, not a boxing glove, on the Vuelta card", () => {
    const html = renderToStaticMarkup(
      <FeedCard item={conceptItem("cycling", "Vuelta a España 2026")} />,
    );

    // The card is the one we meant to render — not a silent fall-through to
    // some other branch that would make the glove assertion vacuous.
    expect(html).toContain("CYCLING");
    expect(html).toContain("Vuelta a España 2026");

    expect(html).toContain("🚴");
    expect(html).not.toContain(GLOVE);
  });

  it.each([
    ["golf", "⛳"],
    ["tennis", "🎾"],
    ["soccer", "⚽"],
    ["election", "🗳"],
    ["f1", "🏎"],
    ["awards", "🏆"],
  ])("renders %s with its own glyph and never the glove", (domain, glyph) => {
    const html = renderToStaticMarkup(
      <FeedCard item={conceptItem(domain, `A ${domain} event`)} />,
    );
    expect(html).toContain(domain.toUpperCase());
    expect(html).toContain(glyph);
    expect(html).not.toContain(GLOVE);
  });

  it("renders boxing WITH the glove — the mapping is right, not merely glove-free", () => {
    const html = renderToStaticMarkup(
      <FeedCard item={conceptItem("boxing", "A title fight")} />,
    );
    expect(html).toContain("BOXING");
    expect(html).toContain(GLOVE);
  });

  it("renders an UNMAPPED domain's label with no glyph at all", () => {
    const html = renderToStaticMarkup(
      <FeedCard item={conceptItem("darts", "PDC World Championship")} />,
    );
    expect(html).toContain("DARTS");
    expect(html).not.toContain(GLOVE);
    // Nothing stood in for the missing glyph.
    expect(html).not.toContain("📊");
  });
});

describe("UX-1052 item 1 — conceptDomainEmoji refusal contract", () => {
  it("returns null rather than a fallback for unknown, empty and missing domains", () => {
    expect(conceptDomainEmoji("darts")).toBeNull();
    expect(conceptDomainEmoji("")).toBeNull();
    expect(conceptDomainEmoji(null)).toBeNull();
    expect(conceptDomainEmoji(undefined)).toBeNull();
  });

  it("is case- and whitespace-insensitive on the domain key", () => {
    expect(conceptDomainEmoji(" Cycling ")).toBe("🚴");
    expect(conceptDomainEmoji("GOLF")).toBe("⛳");
  });

  it("covers every domain the backend concept adapters register", () => {
    // `backend/app/utils/event_*.py` — each adapter's `domain` literal.
    for (const domain of ["soccer", "cycling", "election", "f1", "golf", "tennis", "awards"]) {
      expect(conceptDomainEmoji(domain)).not.toBeNull();
    }
  });
});
