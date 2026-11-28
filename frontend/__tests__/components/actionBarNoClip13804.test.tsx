import React from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { ActionBar } from "@/components/discover/shared";

describe("#13804 Discover ActionBar does not clip Share beside age and Pin", () => {
  it("wraps gracefully and keeps Share, Pin, PriceAgeMark, and Like inside narrow desktop cards", () => {
    const yesterdayIso = new Date(Date.now() - 26 * 3600 * 1000).toISOString();
    const html = renderToStaticMarkup(
      <ActionBar
        liked={false}
        setLiked={() => {}}
        shareUrl="https://bainluck.com/futures/123"
        shareTitle="FIFA Women's World Cup 2027 Winner"
        contentType="futures"
        itemId={123}
        onDismiss={() => {}}
        priceObservedAt={yesterdayIso}
        priceStatus="open"
        pin={{
          pinned: false,
          onToggle: () => {},
          atMax: false,
          noun: "market",
        }}
      />
    );

    expect(html).toContain('data-testid="action-bar"');
    expect(html).toContain("flex-wrap");
    expect(html).toContain("Like");
    expect(html).toContain("Pin");
    expect(html).toContain("Share");
    expect(html).toContain('data-testid="price-age-mark"');
    expect(html).toContain('data-testid="action-bar-dismiss"');
  });
});
