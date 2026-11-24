import React from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { FormsLabBatch1Card } from "@/components/discover/forms/FormsLabBatch1Dispatcher";
import type { FormsLabCardEnvelope, MemberArtSpec } from "@/components/discover/forms/types_forms_lab_13551";

const makeArt = (name: string, pres: MemberArtSpec["presentation"] = "logo"): MemberArtSpec => ({
  url: `https://thumb.wikimedia.org/example/${encodeURIComponent(name)}.png`,
  kind: pres === "logo" ? "organization" : "person",
  presentation: pres,
  detail: name,
  accent_color: "",
  initials: name.slice(0, 2).toUpperCase(),
  short_label: name,
  canonical_name: name,
});

describe("FormsLabBatch1Card (#13551)", () => {
  it("renders places grid with % numbers and refuses invalid cards back to fallback rows", () => {
    const validCard: FormsLabCardEnvelope = {
      card_id: "places-ok",
      look_id: "grid_of_cells",
      form_variant: "places_grid",
      preview_only: true,
      is_refusal_demo: false,
      topic: "Tech",
      title: "Largest company at the end of 2026",
      subtitle: "Dec 31 ranks",
      footnote: "1st, 2nd, 3rd on Dec 31",
      source_label: "Polymarket",
      status: "draw",
      refusal_reasons: [],
      truth_checks: [],
      body: {
        columns: [
          { key: "first", label: "1st" },
          { key: "second", label: "2nd" },
          { key: "third", label: "3rd" },
        ],
        rows: [
          {
            name: "Apple",
            short_label: "Apple",
            art: makeArt("Apple"),
            cells: [
              { col_key: "first", col_label: "1st", pct: 86, pct_label: "86%", is_row_peak: true },
              { col_key: "second", col_label: "2nd", pct: 2, pct_label: "2%" },
              { col_key: "third", col_label: "3rd", pct: 2, pct_label: "2%" },
            ],
          },
        ],
        highlight_mode: "row_peak",
      },
      fallback_rows: [],
    };
    const html = renderToStaticMarkup(<FormsLabBatch1Card card={validCard} />);
    expect(html).toContain("86%");
    expect(html).toContain('alt="Apple"');

    const refusedCard: FormsLabCardEnvelope = {
      ...validCard,
      card_id: "nba-refused",
      form_variant: "scoreboard_grid",
      status: "refused_fallback_rows",
      refusal_reasons: ["NBA Scoring Leader adds to 184%, outside single-winner band"],
      body: {},
      fallback_rows: [
        {
          label: "MVP · Victor Wembanyama",
          short_label: "Wembanyama",
          role: null,
          pct: 51,
          pct_label: "51%",
          art: makeArt("Victor Wembanyama", "portrait"),
        },
      ],
    };
    const refusedHtml = renderToStaticMarkup(<FormsLabBatch1Card card={refusedCard} />);
    expect(refusedHtml).toContain("refusal-nba-refused");
    expect(refusedHtml).toContain("184%");
    expect(refusedHtml).toContain("51%");
  });

  it("enforces Decision 367 shaded-only tiles with zero per-day computed numbers on CalendarStripCard", () => {
    const calCard: FormsLabCardEnvelope = {
      card_id: "cal-wrapped",
      look_id: "calendar_strip",
      form_variant: "calendar_strip",
      preview_only: true,
      is_refusal_demo: false,
      topic: "Entertainment",
      title: "When will Spotify release 2026 Wrapped?",
      subtitle: "Nov 27 – Dec 5",
      footnote: "Decision 367 pending",
      source_label: "Polymarket",
      status: "draw",
      refusal_reasons: [],
      truth_checks: [],
      body: {
        art: makeArt("Spotify"),
        decision_367_daily_numbers_enabled: false,
        earlier_label: "3% before Nov 27",
        later_label: "89% by Dec 5",
        peak_summary: "Peak window: Dec 3",
        tiles: [
          { date_label: "Dec 2", month: "Dec", day_num: 2, intensity: 0.1, is_peak: false, daily_number_label: "+5%" },
          { date_label: "Dec 3", month: "Dec", day_num: 3, intensity: 1.0, is_peak: true, daily_number_label: "+67%" },
        ],
      },
      fallback_rows: [],
    };
    const calHtml = renderToStaticMarkup(<FormsLabBatch1Card card={calCard} />);
    expect(calHtml).not.toContain("+67%");
    expect(calHtml).not.toContain("+5%");
    expect(calHtml).toContain("Peak window: Dec 3");
    expect(calHtml).toContain('data-decision-367="shaded-only"');
  });

  it("renders CastingSheetCard ties and BubbleAndCutCard conference cut lines", () => {
    const castingCard: FormsLabCardEnvelope = {
      card_id: "bond",
      look_id: "casting_sheet",
      form_variant: "casting_sheet",
      preview_only: true,
      is_refusal_demo: false,
      topic: "Film",
      title: "Next James Bond",
      subtitle: "7 roles",
      footnote: "Tie shown",
      source_label: "Polymarket",
      status: "draw",
      refusal_reasons: [],
      truth_checks: [],
      body: {
        rows: [
          {
            role: "Felix Leiter",
            leader: "Boyd Holbrook",
            short_label: "Boyd Holbrook / Anthony Mackie",
            pct: 11,
            pct_label: "11%–11%",
            certainty: "Tie",
            is_tie: true,
            art: makeArt("Boyd Holbrook", "portrait"),
            co_leader: {
              name: "Anthony Mackie",
              pct: 11,
              pct_label: "11%",
              art: makeArt("Anthony Mackie", "portrait"),
            },
          },
        ],
      },
      fallback_rows: [],
    };
    const castHtml = renderToStaticMarkup(<FormsLabBatch1Card card={castingCard} />);
    expect(castHtml).toContain(">Tie<");
    expect(castHtml).toContain("11%–11%");
    expect(castHtml).toContain('alt="Anthony Mackie"');

    const cutCard: FormsLabCardEnvelope = {
      ...castingCard,
      card_id: "nhl-cut",
      look_id: "bubble_and_cut",
      form_variant: "the_cut",
      body: {
        conferences: [
          {
            conference: "Western",
            total_teams: 16,
            places: 8,
            cut_label: "8 places",
            has_cut_tie: true,
            tie_rule_note: "38% tie",
            teams: Array.from({ length: 10 }, (_, idx) => ({
              name: idx === 7 ? "Anaheim Ducks" : idx === 8 ? "St. Louis Blues" : `Team ${idx + 1}`,
              code: idx === 7 ? "ANA" : idx === 8 ? "STL" : `T${idx + 1}`,
              conference: "Western",
              pct: idx >= 7 ? 38 : 90 - idx * 5,
              pct_label: idx >= 7 ? "38%" : `${90 - idx * 5}%`,
              art: makeArt(`T${idx + 1}`),
              rank: idx + 1,
              above_cut: idx < 8,
              at_cut_tie: idx === 7 || idx === 8,
              likelihood_band: idx < 8 ? "bubble" : "chase",
            })),
          },
        ],
      },
    };
    const cutHtml = renderToStaticMarkup(<FormsLabBatch1Card card={cutCard} />);
    expect(cutHtml).toContain("Western");
    expect(cutHtml).toContain("8 places · 38% tie");
  });
});
