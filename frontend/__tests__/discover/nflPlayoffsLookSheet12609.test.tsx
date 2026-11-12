/**
 * #12609 — NFL Playoffs & Super Bowl Container Look Sheet tests.
 */

import React from "react";
import { renderToStaticMarkup } from "react-dom/server";
import {
  NFL_PLAYOFFS_LOOK_SHEET_ITEMS,
  NFL_PLAYOFFS_LOOK_SHEET_SLATE_ID,
  NFL_PLAYOFFS_TO_SUPER_BOWL_CLUBS,
  STEELERS_BENGALS_PROP_BOARD,
  resolveNflKidSafeArt,
} from "@/lib/discover/nflPlayoffsLookSheet";
import {
  NflPlayoffsLookSheetGallery,
  NflPlayoffsToSuperBowlSectionCard,
  NflTooManyPropsSectionCard,
  renderNflPlayoffsLookSheetDeckItem,
} from "@/components/discover/forms/NflPlayoffsLookSheet";

describe("#12609 NFL Playoffs & Super Bowl Container Look Sheet", () => {
  test("defines 7 look-sheet items where adjacent sections never share a form", () => {
    expect(NFL_PLAYOFFS_LOOK_SHEET_SLATE_ID).toBe("nfl-playoffs-look-sheet-2026-11");
    expect(NFL_PLAYOFFS_LOOK_SHEET_ITEMS).toHaveLength(7);

    for (let i = 1; i < NFL_PLAYOFFS_LOOK_SHEET_ITEMS.length; i += 1) {
      expect(NFL_PLAYOFFS_LOOK_SHEET_ITEMS[i].form.form_id).not.toBe(
        NFL_PLAYOFFS_LOOK_SHEET_ITEMS[i - 1].form.form_id,
      );
    }
  });

  test("Section 1 shows top 6 Super Bowl contenders by default and expands to all 12 clubs", () => {
    const collapsedHtml = renderToStaticMarkup(<NflPlayoffsToSuperBowlSectionCard />);
    expect(collapsedHtml).toContain("nfl-section-1-playoffs-super-bowl");
    expect(collapsedHtml).toContain("San Francisco 49ers");
    expect(collapsedHtml).toContain("Buffalo Bills");
    expect(collapsedHtml).toContain("Jacksonville Jaguars");
    expect(collapsedHtml).toContain("Show all 12 clubs in the hunt (+6 more)");
    expect(collapsedHtml).not.toContain("Minnesota Vikings");

    const expandedHtml = renderToStaticMarkup(
      <NflPlayoffsToSuperBowlSectionCard defaultExpanded />,
    );
    expect(expandedHtml).toContain("Minnesota Vikings");
    expect(expandedHtml).toContain("Green Bay Packers");
    expect(expandedHtml).toContain("Collapse to top 6 clubs");
  });

  test("Section 1 flips Make Playoffs % to ✓ Clinched / ✗ Missed when settled preview is enabled", () => {
    const settledHtml = renderToStaticMarkup(
      <NflPlayoffsToSuperBowlSectionCard simulateSettled defaultExpanded />,
    );
    expect(settledHtml).toContain("nfl-settled-clinched");
    expect(settledHtml).toContain("✓ Clinched playoff berth");
    expect(settledHtml).toContain("nfl-settled-eliminated");
    expect(settledHtml).toContain("✗ Missed playoffs");
  });

  test("Section 6 ('too many props') shows 3 scannable lenses on Steelers at Bengals and renders the category Milestone Ladder drawer when open", () => {
    expect(STEELERS_BENGALS_PROP_BOARD.total_raw_markets).toBe(681);
    expect(STEELERS_BENGALS_PROP_BOARD.total_player_prop_lines).toBe(394);

    const firstScreenHtml = renderToStaticMarkup(<NflTooManyPropsSectionCard />);
    expect(firstScreenHtml).toContain("nfl-section-6-too-many-props");
    expect(firstScreenHtml).toContain("1. THE SCRIPT (50%+ BENCHMARKS)");
    expect(firstScreenHtml).toContain("2. 50/50 COIN-FLIPS");
    expect(firstScreenHtml).toContain("3. FIRST TD &amp; SPECIALS");
    expect(firstScreenHtml).not.toContain("nfl-too-many-props-drawer-content");

    const drawerOpenHtml = renderToStaticMarkup(
      <NflTooManyPropsSectionCard defaultDrawerOpen />,
    );
    expect(drawerOpenHtml).toContain("nfl-too-many-props-drawer-content");
    expect(drawerOpenHtml).toContain("Receiving Yards (7 milestones)");
    expect(drawerOpenHtml).toContain("nfl-prop-tab-passing");
  });

  test("kid-safe gate allows verified ESPN logos & headshots and rejects unverified hosts", () => {
    const club = NFL_PLAYOFFS_TO_SUPER_BOWL_CLUBS[0];
    expect(
      resolveNflKidSafeArt(club.team, club.division, club.logo, { kidSurface: true }),
    ).toBe(club.logo.url);

    expect(
      resolveNflKidSafeArt("Bad Host", "NFC", {
        ...club.logo,
        url: "https://untrusted.example.com/logo.png",
      }),
    ).toBeNull();
  });

  test("renders the full NflPlayoffsLookSheetGallery and never prints raw market IDs or 'question' on card faces", () => {
    const html = renderToStaticMarkup(<NflPlayoffsLookSheetGallery />);
    expect(html).toContain("nfl-playoffs-look-sheet-gallery");
    for (const item of NFL_PLAYOFFS_LOOK_SHEET_ITEMS) {
      const node = renderNflPlayoffsLookSheetDeckItem(item.item_key);
      expect(node).not.toBeNull();
      const itemHtml = renderToStaticMarkup(<>{node}</>).toLowerCase();
      expect(itemHtml).not.toContain("question");
      expect(itemHtml).not.toContain("#62679");
      expect(itemHtml).not.toContain("#86832");
    }
  });
});
