/**
 * #12577 / #12523 — Visual Forms Look Sheet (Sheet 1 + Sheet 2) & Oscars Container Diversity Tests.
 */

import React from "react";
import { renderToStaticMarkup } from "react-dom/server";
import {
  OSCARS_CONTAINER_LOOK_SHEET_OPTIONS,
  PAIRED_METRIC_REGISTER,
  TMDB_ATTRIBUTION_LINE,
  VISUAL_FORM_LIBRARY,
  VISUAL_FORM_LOOK_SHEET_CARDS,
  VISUAL_FORM_SHEET_2_CARDS,
  blendVenueProbabilities,
  formatStage1Display,
  formatStage2Display,
  resolveKidSafeVisualArt,
  sortPairedEntries,
  type PairedSubjectEntry,
} from "@/lib/discover/visualForms";
import {
  OscarsContainerLayoutPreview,
  VisualFormLookSheetGallery,
  renderLookSheetCardBySpec,
} from "@/components/discover/forms/VisualFormLookSheet";
import { renderedPercent } from "@/lib/renderedPercent";

describe("#12577 / #12523 Visual Form Library & Look Sheet (Sheet 1 + Sheet 2)", () => {
  it("defines 6 Sheet 1 cards, 6 Sheet 2 cards (3 shorter Card 1 variants + 3 wilder forms), and 3 Oscars container options", () => {
    expect(VISUAL_FORM_LOOK_SHEET_CARDS).toHaveLength(6);
    expect(VISUAL_FORM_SHEET_2_CARDS).toHaveLength(6);
    expect(OSCARS_CONTAINER_LOOK_SHEET_OPTIONS).toHaveLength(3);

    for (const card of [...VISUAL_FORM_LOOK_SHEET_CARDS, ...VISUAL_FORM_SHEET_2_CARDS]) {
      expect(card.form.domain_agnostic).toBe(true);
      expect(card.form.data_shape.length).toBeGreaterThan(10);
      expect(card.form.parts_vocabulary.length).toBeGreaterThan(0);
    }

    const nhlCard = VISUAL_FORM_LOOK_SHEET_CARDS.find(
      (c) => c.set_id === "nhl-2026-27-playoffs-and-cup",
    );
    expect(nhlCard).toBeDefined();
    expect(nhlCard?.form.form_id).toBe("paired_bars_with_art");
  });

  it("blends equivalent venue legs for Best Picture Nominee (#5165726 + #27988771) while never blending Nominee and Winner propositions", () => {
    const bpSet = PAIRED_METRIC_REGISTER["oscars-2027-best-picture"];
    expect(bpSet.stage_1_market.companion_polymarket_id).toBe(27988771);

    for (const entry of bpSet.entries) {
      const expectedBlend = blendVenueProbabilities(
        entry.stage_1_kalshi_probability,
        entry.stage_1_polymarket_probability,
      );
      expect(entry.stage_1_probability).toBeCloseTo(expectedBlend!, 6);
    }

    // The Black Ball pairs with "La Bola Negra" on Polymarket #27988771 (0.94 + 0.95 -> 0.945 -> 95%)
    const blackBall = bpSet.entries.find((e) => e.subject === "The Black Ball")!;
    expect(blackBall.stage_1_polymarket_outcome).toBe("La Bola Negra");
    expect(formatStage1Display(blackBall, bpSet).label).toBe("95%");

    // I Play Rocky blends 0.475 (Kalshi) and 0.50 (Polymarket) -> 0.4875 -> 49%
    const rocky = bpSet.entries.find((e) => e.subject === "I Play Rocky")!;
    expect(formatStage1Display(rocky, bpSet).label).toBe("49%");

    for (const set of Object.values(PAIRED_METRIC_REGISTER)) {
      expect(set.never_blend).toBe(true);
      expect(set.stage_1_market.id).not.toBe(set.stage_2_market.id);
      for (const entry of set.entries) {
        if (
          entry.stage_1_probability !== null &&
          entry.stage_2_probability !== null
        ) {
          const s1 = formatStage1Display(entry, set);
          const s2 = formatStage2Display(entry, set);
          expect(s1.percent).toBe(renderedPercent(entry.stage_1_probability));
          expect(s2.percent).toBe(renderedPercent(entry.stage_2_probability));
        }
      }
    }
  });

  it("uses renderedPercent so half-percents (Malkovich 0.955 -> 96%, Damon 0.935 -> 94%) always round half-up", () => {
    const actorSet = PAIRED_METRIC_REGISTER["oscars-2027-best-actor"];
    const malkovich = actorSet.entries.find(
      (e) => e.subject === "John Malkovich",
    )!;
    const damon = actorSet.entries.find((e) => e.subject === "Matt Damon")!;

    expect(malkovich.stage_1_probability).toBe(0.955);
    expect(damon.stage_1_probability).toBe(0.935);
    expect(formatStage1Display(malkovich, actorSet).label).toBe("96%");
    expect(formatStage1Display(damon, actorSet).label).toBe("94%");
  });

  it("sources film credits and verified TMDB person headshots (including Nathan Fielder #1212667 and Jesse Eisenberg on The Debut) and includes Dallas Stars in the NHL 5.2% tie", () => {
    const bpSet = PAIRED_METRIC_REGISTER["oscars-2027-best-picture"];
    const debut = bpSet.entries.find((e) => e.subject === "The Debut")!;
    expect(debut.detail).toBe("Jesse Eisenberg · Topic Studios");
    expect(debut.credit_source).toBe("tmdb:movie:1391239");

    const dirSet = PAIRED_METRIC_REGISTER["oscars-2027-best-director"];
    const fielder = dirSet.entries.find((e) => e.subject === "Nathan Fielder")!;
    expect(fielder.art?.tmdb_id).toBe(1212667);
    expect(fielder.art?.url).toBe(
      "https://image.tmdb.org/t/p/w185/x0UOcjml8WnBfnb89QOh0iXM0w0.jpg",
    );

    const nhlSet = PAIRED_METRIC_REGISTER["nhl-2026-27-playoffs-and-cup"];
    expect(nhlSet.entries).toHaveLength(9);
    const stars = nhlSet.entries.find((e) => e.subject === "Dallas Stars");
    const lightning = nhlSet.entries.find(
      (e) => e.subject === "Tampa Bay Lightning",
    );
    expect(stars).toBeDefined();
    expect(lightning).toBeDefined();

    // Tie-break orders Dallas Stars (83.5% playoffs) ahead of Tampa Bay Lightning (82% playoffs) when tied at 5.2% Cup
    const sortedNhl = sortPairedEntries(nhlSet.entries);
    const starsIdx = sortedNhl.findIndex((e) => e.subject === "Dallas Stars");
    const tbIdx = sortedNhl.findIndex(
      (e) => e.subject === "Tampa Bay Lightning",
    );
    expect(starsIdx).toBeLessThan(tbIdx);
  });

  it("explicitly reports when a row is not listed in one market or has no recent probability", () => {
    const bpSet = PAIRED_METRIC_REGISTER["oscars-2027-best-picture"];
    const rocky = bpSet.entries.find((e) => e.subject === "I Play Rocky");
    expect(rocky).toBeDefined();
    const s1 = formatStage1Display(rocky!, bpSet);
    const s2 = formatStage2Display(rocky!, bpSet);
    expect(s1.kind).toBe("percent");
    expect(s1.label).toBe("49%");
    expect(s2.kind).toBe("missing");
    expect(s2.label).toBe("Not listed to win");

    const dirSet = PAIRED_METRIC_REGISTER["oscars-2027-best-director"];
    const inarritu = dirSet.entries.find((e) =>
      e.subject.includes("Iñárritu"),
    );
    expect(inarritu).toBeDefined();
    expect(inarritu?.stage_1_outcome).toBe("Alejandro González Iñárritu");
    expect(formatStage1Display(inarritu!, dirSet)).toEqual({
      kind: "percent",
      percent: 21,
      label: "21%",
    });
    expect(formatStage2Display(inarritu!, dirSet)).toEqual({
      kind: "percent",
      percent: 1,
      label: "1%",
    });

    const actSet = PAIRED_METRIC_REGISTER["oscars-2027-best-actress"];
    const wilde = actSet.entries.find((e) => e.subject === "Olivia Wilde");
    expect(wilde).toBeDefined();
    expect(formatStage2Display(wilde!, actSet)).toEqual({
      kind: "percent",
      percent: 1,
      label: "1%",
    });
  });

  it("replaces the first number with ✓ or ✗ once step 1 settles ('settled means settled')", () => {
    const bpSet = PAIRED_METRIC_REGISTER["oscars-2027-best-picture"];
    const odyssey = bpSet.entries[0];
    const rocky = bpSet.entries.find((e) => e.subject === "I Play Rocky")!;

    const settledOdyssey = formatStage1Display(odyssey, bpSet, {
      simulateSettledStage1: true,
    });
    expect(settledOdyssey.kind).toBe("tick");
    expect(settledOdyssey.symbol).toBe("✓");
    expect(settledOdyssey.label).toBe("✓ Nominated");

    const settledRocky = formatStage1Display(rocky, bpSet, {
      simulateSettledStage1: true,
    });
    expect(settledRocky.kind).toBe("cross");
    expect(settledRocky.symbol).toBe("✗");
    expect(settledRocky.label).toBe("✗ Not nominated");
    expect(settledRocky.sublabel).toBe("was 49%");
  });

  it("enforces the #7461 kid-safe gate on posters, headshots, and logos", () => {
    const bpSet = PAIRED_METRIC_REGISTER["oscars-2027-best-picture"];
    const odyssey = bpSet.entries[0];
    expect(resolveKidSafeVisualArt(odyssey)).toBe(
      "https://image.tmdb.org/t/p/w342/krVa7rKCQb4OBfsr2LTJv4rTz5q.jpg",
    );

    // On kidSurface (/play or kid grader), external TMDB movie posters fail closed per #7461
    expect(resolveKidSafeVisualArt(odyssey, { kidSurface: true })).toBeNull();

    // Verified ESPN team logo passes both adult and kid surfaces
    const nhlSet = PAIRED_METRIC_REGISTER["nhl-2026-27-playoffs-and-cup"];
    const canes = nhlSet.entries[0];
    expect(resolveKidSafeVisualArt(canes, { kidSurface: false })).toBe(
      "https://a.espncdn.com/i/teamlogos/nhl/500/car.png",
    );
    expect(resolveKidSafeVisualArt(canes, { kidSurface: true })).toBe(
      "https://a.espncdn.com/i/teamlogos/nhl/500/car.png",
    );

    // Horror genre (27) poster (like #7461 Resident Evil) is refused even on adult surfaces
    const horrorSpecimen: PairedSubjectEntry = {
      ...odyssey,
      subject: "Resident Evil",
      art: {
        kind: "tmdb_poster",
        url: "https://image.tmdb.org/t/p/w342/1CIaRYKf3zg2Xyce1CSfCMg2Vfw.jpg",
        genre_ids: [27, 28],
        adult: false,
        kid_safe_vetted: true,
      },
    };
    expect(resolveKidSafeVisualArt(horrorSpecimen)).toBeNull();

    // Adult-flagged or unvetted or non-HTTPS assets are refused
    expect(
      resolveKidSafeVisualArt({
        ...odyssey,
        art: { ...odyssey.art!, adult: true },
      }),
    ).toBeNull();
    expect(
      resolveKidSafeVisualArt({
        ...odyssey,
        art: { ...odyssey.art!, url: "http://image.tmdb.org/t/p/w342/x.jpg" },
      }),
    ).toBeNull();
    expect(
      resolveKidSafeVisualArt({
        ...odyssey,
        art: { ...odyssey.art!, url: "https://evil.example.com/x.jpg" },
      }),
    ).toBeNull();
  });

  it("renders all Sheet 1 + Sheet 2 visual forms, TMDB attribution, and 3 Oscars containers", () => {
    const html = renderToStaticMarkup(<VisualFormLookSheetGallery />);

    expect(html).toContain('data-testid="visual-forms-look-sheet-gallery"');
    expect(html).toContain('data-testid="visual-forms-sheet-2-section"');
    expect(html).toContain('data-testid="visual-forms-sheet-1-section"');

    // Sheet 1 blocks (1–6) and Sheet 2 blocks (10–15)
    for (const pos of [1, 2, 3, 4, 5, 6, 10, 11, 12, 13, 14, 15]) {
      expect(html).toContain(`data-testid="look-sheet-card-block-${pos}"`);
    }

    // Sheet 2 testids
    expect(html).toContain(
      'data-testid="visual-form-card-paired-bars-top5-expandable"',
    );
    expect(html).toContain(
      'data-testid="visual-form-card-paired-bars-single-line"',
    );
    expect(html).toContain(
      'data-testid="visual-form-card-paired-bars-top3-plus-strip"',
    );
    expect(html).toContain('data-testid="visual-form-card-podium-and-tiers"');
    expect(html).toContain('data-testid="visual-form-card-barbell-race-track"');
    expect(html).toContain('data-testid="visual-form-card-ballot-quadrant-map"');

    // TMDB attribution line is visible
    expect(html).toContain('data-testid="tmdb-attribution-line"');
    expect(html).toContain(TMDB_ATTRIBUTION_LINE);

    for (const code of ["A", "B", "C"] as const) {
      expect(html).toContain(`data-testid="oscars-container-option-${code}"`);
      const containerHtml = renderToStaticMarkup(
        <OscarsContainerLayoutPreview
          spec={
            OSCARS_CONTAINER_LOOK_SHEET_OPTIONS.find(
              (c) => c.option_code === code,
            )!
          }
          simulateSettled={true}
        />,
      );
      expect(containerHtml).toContain("✓ Nominated");
    }

    // Missing probability notices render explicitly
    expect(html).toContain('data-testid="missing-probability-notice"');
    expect(html).toContain("Not listed to win");

    // Card 6 carries "Illustration: nominations aren't out" on the card itself
    expect(html).toContain('data-testid="settled-gate-illustration-banner"');
    expect(html).toContain("Illustration: nominations aren&#x27;t out");

    // Settled ✓ / ✗ state renders on Card 6 and when simulateSettled is true
    expect(html).toContain('data-testid="settled-stage-1-tick"');
    expect(html).toContain('data-testid="settled-stage-1-cross"');

    const settledCard1Html = renderToStaticMarkup(
      renderLookSheetCardBySpec(VISUAL_FORM_LOOK_SHEET_CARDS[0], {
        simulateSettled: true,
      }),
    );
    expect(settledCard1Html).toContain("✓ Nominated");
    expect(settledCard1Html).toContain("✗ Not nominated");

    // Verify all 11 visual forms in library
    expect(Object.keys(VISUAL_FORM_LIBRARY)).toHaveLength(11);
  });
});
