/**
 * UX-1035 / #2711 — a concept card's icon is about the concept.
 *
 * `FeedCard`'s concept arm hardcoded 🥊 and printed `data.domain.toUpperCase()`
 * beside it, so on the banked payload the Vuelta a España read "🥊 CYCLING" and
 * the Dutch Grand Prix read "🥊 F1". The component was built for UFC and boxing
 * and never generalised when the other concept adapters landed.
 *
 * The payload is not hand-written: the 14 concept cards from production
 * `GET /api/feed?mode=sports&limit=200` on 2026-09-02.
 */
import fs from "fs";
import path from "path";

import { conceptDomainIcon } from "@/lib/conceptDomainIcon";

const FIXTURE = path.join(
  __dirname,
  "..",
  "fixtures",
  "conceptCards2711.json",
);

const banked: { items: { data: { domain: string; name: string } }[] } =
  JSON.parse(fs.readFileSync(FIXTURE, "utf8"));

const GLOVE = "🥊";

describe("#2711 — the icon follows the domain", () => {
  it("🔴 the banked payload is the one with the wrong glove on it", () => {
    // Three domains, one icon. If this fixture ever holds only combat cards the
    // assertions below stop proving anything.
    const domains = new Set(banked.items.map((i) => i.data.domain));
    expect(domains).toEqual(new Set(["cycling", "f1", "ufc"]));
  });

  it("🟢 no non-combat concept in the real payload wears a boxing glove", () => {
    const wrong = banked.items
      .filter((i) => !["ufc", "boxing", "mma"].includes(i.data.domain))
      .filter((i) => conceptDomainIcon(i.data.domain) === GLOVE)
      .map((i) => `${i.data.domain}: ${i.data.name}`);
    expect(wrong).toEqual([]);
  });

  it("🟢 combat cards keep the glove — this is a mapping, not a removal", () => {
    // The control. The old icon was right for the cards the component was
    // written for, and a fix that took it away from them would be a regression
    // dressed as a repair.
    expect(conceptDomainIcon("ufc")).toBe(GLOVE);
    expect(conceptDomainIcon("boxing")).toBe(GLOVE);
  });

  it("aliases the domains whose names differ from their category", () => {
    // `domain` is an event-key namespace, not a category: the combat adapter
    // says `ufc` where the category map says `mma`, and the F1 adapter says
    // `f1` where it says `motorsports`. Without the alias both fall to the
    // default and the fix looks like it worked while telling you nothing.
    expect(conceptDomainIcon("f1")).toBe("🏎");
    expect(conceptDomainIcon("cycling")).toBe("🚴");
    expect(conceptDomainIcon("golf")).toBe("⛳");
    expect(conceptDomainIcon("soccer")).toBe("⚽");
    expect(conceptDomainIcon("tennis")).toBe("🎾");
  });

  it("every distinct icon is distinct — an alias that collapses is not a fix", () => {
    const icons = ["ufc", "f1", "cycling", "golf", "soccer", "tennis"].map(
      conceptDomainIcon,
    );
    expect(new Set(icons).size).toBe(icons.length);
  });

  it("an unknown domain falls to the generic chart, not to a wrong sport", () => {
    // 📊 says nothing; a glove says something false. Between the two, say
    // nothing.
    for (const unknown of ["darts", "", null, undefined, "SNOOKER"]) {
      const icon = conceptDomainIcon(unknown);
      expect(icon).not.toBe(GLOVE);
    }
    expect(conceptDomainIcon("darts")).toBe("📊");
  });

  it("is case-insensitive, because a domain is data", () => {
    expect(conceptDomainIcon("F1")).toBe(conceptDomainIcon("f1"));
    expect(conceptDomainIcon("Cycling")).toBe(conceptDomainIcon("cycling"));
  });
});
