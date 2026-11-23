import React from "react";
import { renderToStaticMarkup } from "react-dom/server";
import MachinerySectionRenderer, {
  MachineryDiscoverCard,
  type MachineryCardContract,
} from "@/components/collections/MachinerySectionRenderer";
import type { MachineryVisualBlock } from "@/lib/collections";

describe("317: B White Christmas map image on card and set page", () => {
  const mapUrl =
    "https://api.bainluck.com/api/containers/machinery-white-christmas/map.png";

  it("renders the map image inside MachineryDiscoverCard when image_url is set", () => {
    const card: MachineryCardContract = {
      slug: "machinery-white-christmas",
      form_id: "benchmark_strip",
      kicker: "WEATHER · CHRISTMAS",
      title: "Pittsburgh is the likeliest white Christmas",
      subtitle: "Chance of measurable snow on Christmas Day across U.S. cities.",
      footer: "",
      section_count: 1,
      item_count: 11,
      item_noun: "cities",
      image_url: mapUrl,
      image_alt: "U.S. map showing 11 cities shaded by chance of a white Christmas",
      destination_href: "/collections/machinery-white-christmas",
      rows: [
        { outcome_id: 1, name: "Pittsburgh", rendered_percent: 44 },
        { outcome_id: 2, name: "Minneapolis", rendered_percent: 42 },
        { outcome_id: 3, name: "Milwaukee", rendered_percent: 40 },
      ],
    };

    const html = renderToStaticMarkup(<MachineryDiscoverCard card={card} />);
    expect(html).toContain('data-testid="machinery-card-hero-image"');
    expect(html).toContain(mapUrl);
    expect(html).toContain("See all 11 cities");
  });

  it("renders the map hero on the collection set page when visualBlock.hero_image_url is set", () => {
    const vb: MachineryVisualBlock = {
      form_id: "benchmark_strip",
      initial_visible_limit: 3,
      item_noun: "cities",
      hero_image_url: mapUrl,
      hero_image_alt: "U.S. map showing 11 cities shaded by chance of a white Christmas",
      items: [
        {
          market_id: 70170344,
          title: "Pittsburgh",
          href: "/futures/70170344",
          rendered_percent: 44,
        },
      ],
    };

    const html = renderToStaticMarkup(
      <MachinerySectionRenderer visualBlock={vb} members={[]} />,
    );
    expect(html).toContain('data-testid="machinery-section-hero-image"');
    expect(html).toContain(mapUrl);
  });
});
