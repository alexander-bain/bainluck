// #10404 — the phone-width fullscreen chart is not covered by the privacy banner.
//
// Production `/events/15322620` at 390px, 2026-10-04 02:52Z, first visit: with
// fullscreen open, "We value your privacy" · Learn more · Decline · Accept sat
// over the 25% axis label, the time axis and the legend. The dialog was
// `fixed inset-0 z-[100]`; `ConsentBanner` is `fixed bottom-20 … z-[100]` and is
// mounted later in the layout, so on the tie the banner won.
//
// Like #10250's arms, the CONTROL reads the banner's layer from its own source,
// so raising the banner fails this instead of passing on a copied number.

import React from "react";
import { readFileSync } from "fs";
import { join } from "path";
import { renderToStaticMarkup } from "react-dom/server";
import ChartFullscreenDialog from "@/components/event/ChartFullscreenDialog";

function zOf(className: string): number {
  const m = className.match(/(?:^|\s)z-(?:\[(\d+)\]|(\d+))(?:\s|$)/);
  if (!m) throw new Error(`no z-index in: ${className}`);
  return Number(m[1] ?? m[2]);
}

const html = renderToStaticMarkup(
  <ChartFullscreenDialog title="Win Probability" onClose={() => {}}>
    <div>chart</div>
  </ChartFullscreenDialog>,
);

function dialogClass(): string {
  const tag = html.slice(0, html.indexOf(">") + 1);
  expect(tag).toContain('data-testid="chart-fullscreen-dialog"');
  return tag.match(/class="([^"]*)"/)![1];
}

describe("#10404 the fullscreen chart sits above the first-visit privacy banner", () => {
  it("its layer is strictly higher than the banner's, read from the banner's source", () => {
    const banner = readFileSync(join(process.cwd(), "components/Analytics/ConsentBanner.tsx"), "utf8");
    const bannerClass = banner.match(/className="(fixed bottom-20[^"]*)"/);
    expect(bannerClass).not.toBeNull();
    // Strictly greater: an equal layer is the defect, because DOM order then
    // decides and the banner is mounted later.
    expect(zOf(dialogClass())).toBeGreaterThan(zOf(bannerClass![1]));
  });

  it("CONTROL — the banner itself is untouched: it still shows, at its own layer, once the dialog closes", () => {
    const banner = readFileSync(join(process.cwd(), "components/Analytics/ConsentBanner.tsx"), "utf8");
    expect(banner).toContain('className="fixed bottom-20 md:bottom-4 left-0 right-0 z-[100] p-2 sm:p-4 animate-slide-up"');
  });
});
