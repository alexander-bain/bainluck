import React from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { QuietFillPercentBox } from "@/components/discover/QuietFillPercentBox";
import { GroupCard } from "@/components/discover/GroupCard";
import { ThemeBundleCard } from "@/components/discover/ThemeBundleCard";
import {
  renderLookSheetCardBySpec,
} from "@/components/discover/forms/VisualFormLookSheet";
import { VISUAL_FORM_SHEET_2_CARDS } from "@/lib/discover/visualForms";
import type { FeedFuturesData, FeedItem } from "@/lib/types";

jest.mock("next/navigation", () => ({
  __esModule: true,
  useRouter: () => ({ push: jest.fn(), replace: jest.fn(), prefetch: jest.fn() }),
}));
jest.mock("next/link", () => ({
  __esModule: true,
  default: ({ href, children, ...rest }: { href: string; children: React.ReactNode }) => (
    <a href={href} {...rest}>
      {children}
    </a>
  ),
}));
jest.mock("@/components/Analytics", () => ({
  __esModule: true,
  useAnalyticsContext: () => ({ track: () => {} }),
}));

function makeMember(
  id: number,
  name: string,
  probability: number | null,
  winner?: string | null,
): FeedItem {
  return {
    type: "futures",
    score: 80,
    reason: "",
    headline: null,
    data: {
      id,
      name,
      llm_sport_category: "entertainment",
      winner: winner ?? null,
      status: winner ? "completed" : "active",
      top_outcomes:
        probability != null
          ? [{ id, name: "Yes", probability, movement: null }]
          : [],
      outcome_count: 2,
    } as unknown as FeedFuturesData,
  } as unknown as FeedItem;
}

describe("#12714 — quiet proportional fill behind website grouped-card numbers", () => {
  it("sizes QuietFillPercentBox fill proportionally (94% almost full, 36% a third, 0/null plain)", () => {
    const html94 = renderToStaticMarkup(
      <QuietFillPercentBox percent={94} tone="slate">
        <span>94%</span>
      </QuietFillPercentBox>,
    );
    expect(html94).toContain('data-quiet-fill-pct="94"');
    expect(html94).toContain('style="width:94%"');

    const html36 = renderToStaticMarkup(
      <QuietFillPercentBox percent={36} tone="emerald">
        <span>36%</span>
      </QuietFillPercentBox>,
    );
    expect(html36).toContain('data-quiet-fill-pct="36"');
    expect(html36).toContain('style="width:36%"');

    const htmlNull = renderToStaticMarkup(
      <QuietFillPercentBox percent={null} tone="emerald">
        <span>—</span>
      </QuietFillPercentBox>,
    );
    expect(htmlNull).toContain('data-quiet-fill-pct="0"');
    expect(htmlNull).not.toContain('data-testid="quiet-fill-bar"');
  });

  it("renders proportional quiet fills on GroupCard and ThemeBundleCard member rows while keeping resolved rows plain", () => {
    const items = [
      makeMember(101, "Dune: Part Three nominated for Best Picture", 0.94),
      makeMember(102, "Artificial nominated for Best Picture", 0.36),
      makeMember(103, "Settled award category", null, "Anora"),
    ];

    const groupHtml = renderToStaticMarkup(
      <GroupCard
        items={items}
        title="Oscars 2027"
        sharedQuestion="Which films make the Best Picture ballot?"
      />,
    );
    expect(groupHtml).toContain('data-quiet-fill-pct="94"');
    expect(groupHtml).toContain('style="width:94%"');
    expect(groupHtml).toContain('data-quiet-fill-pct="36"');
    expect(groupHtml).toContain('style="width:36%"');
    expect(groupHtml).toContain("Resolved · Anora");

    const themeHtml = renderToStaticMarkup(
      <ThemeBundleCard
        items={items}
        title="Oscars 2027"
        sharedQuestion="Which films make the Best Picture ballot?"
        storyKey="oscars_2027"
      />,
    );
    expect(themeHtml).toContain('data-quiet-fill-pct="94"');
    expect(themeHtml).toContain('data-quiet-fill-pct="36"');
  });

  it("renders proportional quiet fills across paired_bars_top5_expandable and podium_and_tiers while leaving unpriced Stage 2 plain", () => {
    const look1Spec = VISUAL_FORM_SHEET_2_CARDS.find(
      (c) => c.form.form_id === "paired_bars_top5_expandable",
    )!;
    const look1Html = renderToStaticMarkup(renderLookSheetCardBySpec(look1Spec));
    expect(look1Html).toContain('data-quiet-fill-pct="98"');
    expect(look1Html).toContain('data-quiet-fill-pct="57"');
    expect(look1Html).toContain('data-quiet-fill-pct="93"');
    expect(look1Html).toContain('data-quiet-fill-pct="8"');

    const podiumSpec = VISUAL_FORM_SHEET_2_CARDS.find(
      (c) => c.form.form_id === "podium_and_tiers",
    )!;
    const podiumHtml = renderToStaticMarkup(renderLookSheetCardBySpec(podiumSpec));
    expect(podiumHtml).toContain('data-quiet-fill-pct="98"');
    expect(podiumHtml).toContain('data-quiet-fill-pct="57"');
    expect(podiumHtml).toContain('data-quiet-fill-pct="93"');
    expect(podiumHtml).toContain('data-quiet-fill-pct="49"');
    expect(podiumHtml).toContain("Not listed to win");
  });
});
