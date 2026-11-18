import React from "react";
import { renderToStaticMarkup } from "react-dom/server";
import MachinerySectionRenderer, {
  MachineryDiscoverCard,
  type MachineryCardContract,
} from "@/components/collections/MachinerySectionRenderer";
import type { MachineryVisualBlock } from "@/lib/collections";

describe("#12288 Slice 3 — chart form, <=3 row cap + Show all, Direction 228 scale rows, no settlement footer", () => {
  it("renders probability_history_chart with SVG lines and Show all button when >3 charts", () => {
    const mkChart = (id: number, title: string) => ({
      market_id: id,
      title,
      href: `/futures/${id}`,
      start_iso: "2026-11-10T00:00:00Z",
      end_iso: "2026-11-17T00:00:00Z",
      y_min: 50,
      y_max: 95,
      series: [
        {
          outcome_id: id * 10 + 1,
          name: "4.25%",
          current_pct: 88,
          color: "#059669",
          points: [
            { t: "2026-11-10T00:00:00Z", pct: 82 },
            { t: "2026-11-17T00:00:00Z", pct: 88 },
          ],
        },
      ],
    });
    const vb: MachineryVisualBlock = {
      form_id: "probability_history_chart",
      initial_visible_limit: 3,
      items: [
        mkChart(1, "Fed Decision in December"),
        mkChart(2, "Fed rate cut by"),
        mkChart(3, "Predicted Fed rate under each Fed Chair"),
        mkChart(4, "Hidden fourth chart"),
      ],
    };
    const html = renderToStaticMarkup(<MachinerySectionRenderer visualBlock={vb} members={[]} />);
    expect(html).toContain('data-machinery-form="probability_history_chart"');
    expect(html).toContain("Fed Decision in December");
    expect(html).not.toContain("Hidden fourth chart");
    expect(html).toContain("Show all 4 charts (+1 more)");
  });

  it("renders scale-ordered contender_spotlight without #1/#2/#3 podium badges and caps at 3 rows initially", () => {
    const vb: MachineryVisualBlock = {
      form_id: "contender_spotlight",
      initial_visible_limit: 3,
      items: [
        {
          market_id: 57574217,
          title: "Fed Decision in January",
          href: "/futures/57574217",
          scale_ordered: true,
          leader_outcome_id: 301,
          outcomes: [
            { outcome_id: 303, name: "25 bps decrease", probability: 0.01, rendered_percent: 1, art: {} },
            { outcome_id: 302, name: "No change", probability: 0.37, rendered_percent: 37, art: {} },
            { outcome_id: 301, name: "25 bps increase", probability: 0.61, rendered_percent: 61, art: {} },
            { outcome_id: 304, name: "50+ bps increase", probability: 0.01, rendered_percent: 1, art: {} },
          ],
        },
      ],
    };
    const html = renderToStaticMarkup(<MachinerySectionRenderer visualBlock={vb} members={[]} />);
    expect(html).toContain('data-scale-ordered="true"');
    expect(html).not.toContain("#1");
    expect(html).toContain("25 bps decrease");
    expect(html).toContain("No change");
    expect(html).toContain("25 bps increase");
    expect(html).not.toContain("50+ bps increase");
    expect(html).toContain("Show all 4 outcomes (+1 more)");
  });

  it("renders MachineryDiscoverCard with mini_chart and omits empty settlement footer", () => {
    const card: MachineryCardContract = {
      slug: "machinery-fed-and-macro",
      form_id: "contender_spotlight",
      kicker: "ECONOMICS · FEDERAL RESERVE",
      title: "Fed Decision in January prices 25 bps increase at 61%",
      subtitle: "Priced probabilities along the policy-move scale from cut to hike.",
      footer: "",
      scale_ordered: true,
      section_count: 4,
      destination_href: "/collections/machinery-fed-and-macro",
      rows: [
        { outcome_id: 302, name: "No change", rendered_percent: 37, art: {} },
        { outcome_id: 301, name: "25 bps increase", rendered_percent: 61, art: {} },
      ],
      mini_chart: {
        market_id: 57574250,
        title: "Fed Decision in December",
        href: "/futures/57574250",
        start_iso: "2026-11-10T00:00:00Z",
        end_iso: "2026-11-17T00:00:00Z",
        y_min: 70,
        y_max: 95,
        series: [
          {
            outcome_id: 331,
            name: "25 bps increase",
            current_pct: 92,
            color: "#059669",
            points: [
              { t: "2026-11-10T00:00:00Z", pct: 84 },
              { t: "2026-11-17T00:00:00Z", pct: 92 },
            ],
          },
        ],
      },
    };
    const html = renderToStaticMarkup(<MachineryDiscoverCard card={card} />);
    expect(html).toContain('data-testid="machinery-card-mini-chart"');
    expect(html).toContain("Open all 4 sections");
    expect(html).not.toContain("settles from official");
  });
});
