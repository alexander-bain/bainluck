/**
 * #2560 — /sports gets a Tennis chip, and the chip goes somewhere alive.
 *
 * On 2026-09-01, day two of the US Open, the league filter row at the top of
 * `/sports` read, in full:
 *
 *     NBA · NFL · MLB · NHL · NCAAB · NCAAF · EPL · UCL · La Liga ·
 *     Bundesliga · MLS · WNBA · Golf
 *
 * No Tennis — on the browse surface whose own content below the fold was
 * three-quarters tennis: all 20 cards under "Player Props & Progressions" were
 * US Open advance-to-round markets, and two of the eight under "Just Happened"
 * were US Open matches. The one sport a visitor was most likely to be here for
 * was the one sport they could not filter to, visible in the first 40px.
 *
 * ═══ THE SECOND HALF: WHERE IT LANDS ═══
 *
 * A chip pointing at a dead page is the same defect one click further in, and
 * `/sport/tennis` WAS that page: it lists the two tours and four Grand Slams,
 * and the US Open tile read *"Date TBD — odds available closer to the event"*
 * during the US Open, linking nowhere. So this suite asserts both halves:
 *
 *   1. the chip exists and is a link,
 *   2. it points at `/sport/tennis` and NOT at a hard-coded tournament slug,
 *   3. `tournamentHubHref` gets a reader from there to the hub,
 *   4. and it will not route the GOLF US Open to the tennis draw.
 *
 * Point 2 is the one with a history. `/tournaments/us-open` is the destination
 * a reader wants THIS FORTNIGHT, and a chips array is a deploy. UX-P145 shipped
 * exactly this class of bug on exactly this tournament — a weekday hard-coded
 * in a component, live and wrong the same afternoon — and the ruling out of it
 * was that being right has to be a data property. A slug frozen in this array
 * would point the tennis chip at a finished tournament in two weeks.
 */

import React from "react";
import { renderToStaticMarkup } from "react-dom/server";

import LeagueChips from "@/components/LeagueChips";
import {
  TOURNAMENT_HUB_SLUGS,
  tournamentHubHref,
} from "@/lib/tournamentHubs";

function chips(): { href: string; label: string }[] {
  const html = renderToStaticMarkup(<LeagueChips />);
  return Array.from(
    html.matchAll(/<a[^>]*\shref="([^"]+)"[^>]*>([\s\S]*?)<\/a>/g)
  ).map((m) => ({
    href: m[1],
    // The emoji lives in its own `<span>` before the label. Take what follows
    // the last closing span rather than stripping tags, or every label comes
    // back as "🎾Tennis" and the assertions read as failures about the wrong
    // thing.
    label: m[2].slice(m[2].lastIndexOf("</span>") + "</span>".length).trim(),
  }));
}

describe("the /sports league filter row", () => {
  it("has a Tennis chip", () => {
    const labels = chips().map((c) => c.label);
    expect(labels).toContain("Tennis");
    // CONTROL: the row it joined is intact. A component that rendered one chip
    // would pass the assertion above.
    expect(labels).toEqual(
      expect.arrayContaining(["NBA", "NFL", "MLB", "NHL", "Golf"])
    );
  });

  it("sends Tennis to the durable sport page, not to a tournament slug", () => {
    const tennis = chips().find((c) => c.label === "Tennis");
    expect(tennis).toBeDefined();
    expect(tennis!.href).toBe("/sport/tennis");
    // The load-bearing negative: no chip in this row may name a tournament.
    // A slug here is a deploy-dated fact and it expires with the tournament.
    for (const chip of chips()) {
      expect(chip.href).not.toMatch(/^\/tournaments\//);
    }
  });

  it("gives every chip a real destination", () => {
    for (const chip of chips()) {
      expect(chip.href).toMatch(/^\/(sport|categories)\//);
      expect(chip.label.length).toBeGreaterThan(0);
    }
  });
});

describe("tournamentHubHref — the second click", () => {
  it("routes the tennis US Open showcase card to the hub", () => {
    expect(tournamentHubHref("tennis", "US Open")).toBe("/tournaments/us-open");
  });

  it("does NOT route the golf US Open to the tennis draw", () => {
    // "US Open" is a Grand Slam and a golf major. A name-only lookup would send
    // a golf reader to a tennis bracket — the same cross-sport mistake #2553 is
    // about, arrived at from the frontend.
    expect(tournamentHubHref("golf", "US Open")).toBeNull();
  });

  it("leaves a slam with no hub as the dated card it already was", () => {
    expect(tournamentHubHref("tennis", "Wimbledon")).toBeNull();
    expect(tournamentHubHref("tennis", "French Open")).toBeNull();
  });

  it("holds only slugs, never dates", () => {
    // The map's whole safety property. A value with a digit in it is a fact
    // with an expiry and belongs in the register, not in a component's import.
    for (const [name, slug] of Object.entries(TOURNAMENT_HUB_SLUGS)) {
      expect(name.length).toBeGreaterThan(0);
      expect(slug).toMatch(/^[a-z][a-z0-9-]*$/);
      expect(slug).not.toMatch(/\d{4}/);
    }
  });
});
