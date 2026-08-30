/**
 * UX-P182 — THE TENNIS HUB STOPS LISTING THE SAME TOURNAMENT TWICE.
 *
 * ═══ WHAT THIS IS ═══
 *
 * `/hub/tennis` is a primary nav item in BOTH `BottomNav.tsx:12` and
 * `DesktopNav.tsx:12`, so its `upcoming` rail is one tap from every page on
 * every device. Measured live on 2026-08-29 it served **12 cards for 10
 * tournaments**:
 *
 *   ATP Montreal Winner          ←┐ one tournament,
 *   ATP 1000 Montreal: Winner    ←┘ two cards
 *   WTA Toronto Winner           ←┐ one tournament,
 *   WTA 1000 Toronto: Winner     ←┘ two cards
 *
 * And all four keys, fetched from production the same day, resolved to just TWO
 * event pages — `atp-montreal-winner` and `atp-1000-montreal-winner` both served
 * "ATP 1000 Montreal: Winner". A reader who did not trust the first card could
 * tap the second and land exactly where they started.
 *
 * The cause was two layers answering one question differently. `select_winner_field`
 * matches a slug to a market by SUBSET, so it had always read the two renderings
 * as one tournament. `list_tennis_tournament_concepts` keys its groups on the
 * EXACT token set, so a stray `1000` split them. A tour tier is a property of a
 * tournament, never its identity.
 *
 * ═══ WHY THE FIXTURES ARE THE REAL RAILS ═══
 *
 * Both fixtures were produced by driving the REAL
 * `list_tennis_tournament_concepts` over the REAL production corpus (all 1,677
 * open tennis markets, db-query 2026-08-29, `truncated: false`) — BEFORE through
 * the parent commit's module loaded verbatim from `git show ad0c708f:…`, AFTER
 * through the current one. Neither side is a re-implementation, and neither is
 * hand-written: `artifacts-ux-p182/rails.py` regenerates both.
 *
 * ═══ WHY IT IS A RENDER AND NOT A PAYLOAD TEST ═══
 *
 * A guard that counts entries in a JSON array stays green if the component drops
 * or duplicates one on the way to the screen. These assertions run on the markup
 * that `UpcomingCard` — the shipped card, shared by every hub — actually emits.
 *
 *   cd frontend && TZ=UTC npx jest --testPathPatterns=tennisHubDuplicateTournament
 */

import React from "react";
import { renderToStaticMarkup } from "react-dom/server";
import fs from "node:fs";
import path from "node:path";

jest.mock("next/link", () => ({
  __esModule: true,
  default: ({ href, children }: { href: string; children: React.ReactNode }) => (
    <a href={href}>{children}</a>
  ),
}));

import { UpcomingCard } from "@/components/hub/UpcomingCard";
import type { HubUpcoming } from "@/lib/api";

const FIXTURES = path.join(__dirname, "..", "fixtures");

function rail(which: "before" | "after"): HubUpcoming[] {
  return JSON.parse(
    fs.readFileSync(path.join(FIXTURES, `uxp182_tennis_rail_${which}.json`), "utf8")
  ).upcoming;
}

function renderRail(cards: HubUpcoming[]): string {
  return renderToStaticMarkup(
    <div>
      {cards.map((c) => (
        <UpcomingCard key={c.key} card={c} />
      ))}
    </div>
  );
}

/** Cards a reader would read as naming the same tournament. */
function cardsNaming(html: string, city: string): string[] {
  const chunks = html.split("<a ").slice(1);
  return chunks.filter((c) => c.toLowerCase().includes(city.toLowerCase()));
}

describe("UX-P182 — one tournament, one card", () => {
  it("the rail used to print two cards for one tournament", () => {
    const html = renderRail(rail("before"));
    // The control that makes every assertion below meaningful: if this ever
    // reads 1, the BEFORE fixture has lost the defect and the AFTER assertions
    // are passing vacuously.
    expect(cardsNaming(html, "Montreal")).toHaveLength(2);
    expect(cardsNaming(html, "Toronto")).toHaveLength(2);
  });

  it("now it prints one", () => {
    const html = renderRail(rail("after"));
    expect(cardsNaming(html, "Montreal")).toHaveLength(1);
    expect(cardsNaming(html, "Toronto")).toHaveLength(1);
  });

  it("the rail loses exactly the duplicates and nothing else", () => {
    expect(rail("before")).toHaveLength(12);
    expect(rail("after")).toHaveLength(10);
    const after = new Set(rail("after").map((c) => c.name));
    const gone = rail("before")
      .map((c) => c.name)
      .filter((n) => !after.has(n));
    expect(gone.sort()).toEqual(["ATP Montreal Winner", "WTA Toronto Winner"]);
    // Nothing appeared that was not already there.
    const before = new Set(rail("before").map((c) => c.name));
    expect(rail("after").filter((c) => !before.has(c.name))).toEqual([]);
  });

  it("every other card renders byte-identically", () => {
    const b = new Map(rail("before").map((c) => [c.key, renderRail([c])]));
    for (const c of rail("after")) {
      if (!b.has(c.key)) continue;
      // Montreal/Toronto are the two that legitimately change (they gain the
      // date and the live pill their sibling knew). Everything else must not.
      if (/montreal|toronto/i.test(c.name)) continue;
      expect(renderRail([c])).toBe(b.get(c.key));
    }
  });
});

describe("UX-P182 — the merge does not subtract the date", () => {
  /**
   * `winner` is chosen for the fullest DRAW, and the fullest draw is not the row
   * that knows the most. "ATP 1000 Montreal: Winner" has 69 outcomes and no
   * resolution_date; "ATP Montreal Winner" has 46 and knows the tournament ends
   * 2026-09-13. A merge that read the date off `winner` alone would have traded a
   * visible duplicate for a silent subtraction.
   */
  const survivor = (name: RegExp) => {
    const card = rail("after").find((c) => name.test(c.name));
    if (!card) throw new Error(`no surviving card matching ${name}`);
    return renderToStaticMarkup(<UpcomingCard card={card} />);
  };

  it("the survivor still prints the end date its sibling knew", () => {
    expect(survivor(/Montreal/)).toContain("Ends Sun, Sep 13");
    expect(survivor(/Toronto/)).toContain("Ends Sat, Sep 12");
  });

  it("the survivor still prints the LIVE pill", () => {
    expect(survivor(/Montreal/)).toContain("Live");
    expect(survivor(/Toronto/)).toContain("Live");
  });

  it("BEFORE, the rendering that survived printed neither", () => {
    // The tiered rendering is the one that wins the draw tie-break, and on the
    // parent commit it carried no date and no live pill. This is what the fix
    // had to avoid shipping.
    const tiered = rail("before").filter((c) => /1000/.test(c.name));
    expect(tiered).toHaveLength(2);
    for (const c of tiered) {
      const html = renderToStaticMarkup(<UpcomingCard card={c} />);
      expect(html).toContain("TBD");
      expect(html).not.toContain("Live");
    }
  });
});

describe("UX-P182 — the artifact", () => {
  it("writes the rendered before/after rail", () => {
    const out = path.join(__dirname, "..", "..", "..", "artifacts-ux-p182");
    if (!fs.existsSync(out)) return; // artifacts dir is scratch, not required
    const page = (title: string, html: string, n: number) => `
      <section style="margin:0 0 40px">
        <h2 style="font:600 18px system-ui;margin:0 0 4px">${title}</h2>
        <p style="font:13px system-ui;color:#6B7280;margin:0 0 14px">${n} cards</p>
        <div style="display:flex;flex-wrap:wrap;gap:12px">${html}</div>
      </section>`;
    const doc = `<!doctype html><meta charset="utf-8">
      <title>UX-P182 — /hub/tennis upcoming rail</title>
      <script src="https://cdn.tailwindcss.com"></script>
      <body style="padding:32px;background:#F9FAFB;font-family:system-ui">
      <h1 style="font:600 22px system-ui">UX-P182 — the tennis hub stops listing the same tournament twice</h1>
      <p style="font:13px system-ui;color:#6B7280;max-width:60em">
        Rendered from the shipped <code>UpcomingCard</code>. Both rails were produced by the
        real <code>list_tennis_tournament_concepts</code> over all 1,677 open tennis markets —
        BEFORE through the parent commit's module, AFTER through this one.
      </p>
      ${page("BEFORE — 12 cards for 10 tournaments", renderRail(rail("before")), 12)}
      ${page("AFTER — 10 cards for 10 tournaments", renderRail(rail("after")), 10)}
      </body>`;
    const dest = path.join(out, "tennis-hub-rail.html");
    fs.writeFileSync(dest, doc);
    // The rig asserts its own artifact — a capture that silently wrote nothing
    // is a capture that proves nothing.
    expect(fs.statSync(dest).size).toBeGreaterThan(2000);
  });
});
