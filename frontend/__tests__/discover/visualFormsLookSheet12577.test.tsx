/**
 * #12577 / #12523 — Visual Forms Look Sheet & Oscars Container Diversity Tests.
 */

import React from "react";
import { renderToStaticMarkup } from "react-dom/server";
import {
  OSCARS_CONTAINER_LOOK_SHEET_OPTIONS,
  PAIRED_METRIC_REGISTER,
  VISUAL_FORM_LIBRARY,
  VISUAL_FORM_LOOK_SHEET_CARDS,
  formatStage1Display,
  formatStage2Display,
  resolveKidSafeVisualArt,
  type PairedSubjectEntry,
} from "@/lib/discover/visualForms";
import {
  OscarsContainerLayoutPreview,
  VisualFormLookSheetGallery,
  renderLookSheetCardBySpec,
} from "@/components/discover/forms/VisualFormLookSheet";

describe("#12577 / #12523 Visual Form Library & Look Sheet", () => {
  it("defines 6 look-sheet cards (including non-Oscars NHL) and 3 Oscars container options", () => {
    expect(VISUAL_FORM_LOOK_SHEET_CARDS).toHaveLength(6);
    expect(OSCARS_CONTAINER_LOOK_SHEET_OPTIONS).toHaveLength(3);

    for (const card of VISUAL_FORM_LOOK_SHEET_CARDS) {
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

  it("never blends nominee and winner propositions and pairs them in a hand-kept register", () => {
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
          expect(s1.percent).toBe(
            Math.floor(entry.stage_1_probability * 100 + 0.5 + 1e-9),
          );
          expect(s2.percent).toBe(
            Math.floor(entry.stage_2_probability * 100 + 0.5 + 1e-9),
          );
        }
      }
    }
  });

  it("explicitly reports when a row has no recent probability instead of zero-filling or dropping", () => {
    const bpSet = PAIRED_METRIC_REGISTER["oscars-2027-best-picture"];
    const rocky = bpSet.entries.find((e) => e.subject === "I Play Rocky");
    expect(rocky).toBeDefined();
    const s1 = formatStage1Display(rocky!, bpSet);
    const s2 = formatStage2Display(rocky!, bpSet);
    expect(s1.kind).toBe("percent");
    expect(s1.label).toBe("48%");
    expect(s2.kind).toBe("missing");
    expect(s2.label).toBe("No recent win %");

    const dirSet = PAIRED_METRIC_REGISTER["oscars-2027-best-director"];
    const inarritu = dirSet.entries.find((e) =>
      e.subject.includes("Iñárritu"),
    );
    expect(inarritu).toBeDefined();
    expect(formatStage1Display(inarritu!, dirSet)).toEqual({
      kind: "missing",
      percent: null,
      label: "No recent nom %",
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
    expect(settledRocky.sublabel).toBe("was 48%");
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

  it("renders all 6 visual forms and 3 Oscars containers with posters, logos, ✓/✗ ticks, and missing-price badges", () => {
    const html = renderToStaticMarkup(<VisualFormLookSheetGallery />);

    expect(html).toContain('data-testid="visual-forms-look-sheet-gallery"');
    for (let pos = 1; pos <= 6; pos += 1) {
      expect(html).toContain(`data-testid="look-sheet-card-block-${pos}"`);
    }
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
    expect(html).toContain("No recent win %");
    expect(html).toContain("No recent nom %");

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

    // Verify form library contract keys
    expect(Object.keys(VISUAL_FORM_LIBRARY)).toHaveLength(5);
  });
});
