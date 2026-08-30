/**
 * UX-P185 — the tour badge a reader actually sees.
 *
 * `_classify_tour` used to end `return "pga"`, so a tournament no signal claimed
 * was announced as PGA Tour. The Omega European Masters — a DP World Tour event,
 * ticker `KXDPWORLDTOUR-OMEM26` — was badged **⛳ PGA Tour** and, because
 * `/categories/golf` sections on `tour`, filed under the PGA Tour heading one
 * section away from the Husqvarna British Masters, the other DP World Tour event
 * of the same week.
 *
 * The backend half is proved in `backend/tests/test_golf_tour_badge_uxp185.py`.
 * This file proves the two things only a RENDER can: that the corrected payload
 * prints the right badge, and that the new `tour: null` — which the type now
 * permits — degrades to `⛳ Golf` rather than printing "null" or crashing.
 *
 * The component is the shipped `TournamentCard`; nothing here is drawn by hand.
 */

import React from "react";
import { renderToStaticMarkup } from "react-dom/server";

jest.mock("next/navigation", () => ({
  __esModule: true,
  useRouter: () => ({ push: jest.fn(), replace: jest.fn(), prefetch: jest.fn() }),
}));
jest.mock("next/link", () => ({
  __esModule: true,
  default: ({ href, children }: { href: string; children: React.ReactNode }) => (
    <a href={href}>{children}</a>
  ),
}));

import TournamentCard from "@/components/TournamentCard";
import type { GolfTournament } from "@/lib/types";

/** The Omega European Masters as `/api/golf` serves it, tour varied per case. */
function omega(
  tour: string | null,
  tour_label: string | null,
): GolfTournament {
  return {
    key: "omega_european_masters",
    name: "Omega European Masters",
    slug: "omega-european-masters",
    is_major: false,
    is_tour_event: true,
    is_womens: false,
    tour,
    tour_label,
    commence_time: "2026-09-03T00:00:00+00:00",
    resolution_date: "2026-09-06T00:00:00+00:00",
    start_date: "2026-09-03T00:00:00+00:00",
    end_date: "2026-09-06T00:00:00+00:00",
    venue: null,
    location: null,
    market_ids: [59759220],
    market_sources: ["kalshi"],
    market_names: ["Omega European Masters Winner"],
    golfers: [
      { id: 1, name: "Adrian Meronk", probability: 0.1, rank: 1 },
      { id: 2, name: "Eddie Pepperell", probability: 0.1, rank: 2 },
    ],
  } as unknown as GolfTournament;
}

function badge(tournament: GolfTournament): string {
  const markup = renderToStaticMarkup(<TournamentCard tournament={tournament} />);
  const match = markup.match(/⛳\s*([^<]+)/);
  return match ? match[1].trim() : "<NO BADGE RENDERED>";
}

describe("UX-P185 — the badge on the card", () => {
  it("prints DP World Tour for the corrected payload", () => {
    expect(badge(omega("dp_world", "DP World Tour"))).toBe("DP World Tour");
  });

  it("is the fix: the same card used to print PGA Tour", () => {
    // Vacuity companion. If the badge no longer tracks `tour_label` at all, both
    // this and the assertion above would pass on a hard-coded string.
    expect(badge(omega("pga", "PGA Tour"))).toBe("PGA Tour");
  });

  it("degrades to Golf when the backend cannot evidence a tour", () => {
    expect(badge(omega(null, null))).toBe("Golf");
  });

  it("never prints null, undefined or an internal tour key to a reader", () => {
    for (const rendered of [
      badge(omega(null, null)),
      badge(omega("dp_world", "DP World Tour")),
    ]) {
      expect(rendered).not.toMatch(/null|undefined|dp_world/);
    }
  });

  it("still renders the card body when the tour is unknown", () => {
    // The degrade must un-badge the card, not blank it.
    const markup = renderToStaticMarkup(<TournamentCard tournament={omega(null, null)} />);
    expect(markup).toContain("Omega European Masters");
    expect(markup).toContain("Adrian Meronk");
  });
});
