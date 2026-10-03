// #10250 — the phone-width fullscreen chart shows its whole time axis, and
// its controls have names.
//
// Shopper walk, production `/events/15318028` (Pitt @ VT, live) at 390×844,
// 2026-10-02 23:24Z: with fullscreen open, the x-axis tick tops sat at y=778 and
// the bottom nav started at y=787; `elementFromPoint(195, 814)` hit "Browse
// categories". The modal was `fixed inset-0 z-50`. `BottomNav` is
// `fixed bottom-0 … z-50` and comes later in the DOM, so on a tie the nav won and
// covered the chart's bottom 57px. The close × had no accessible name, and
// Escape did nothing.
//
// Each layering arm has a CONTROL that reads the nav's own layer from its
// source. If someone raises the nav, this fails instead of passing on a
// number copied here.

import React from "react";
import { readFileSync } from "fs";
import { join } from "path";
import { renderToStaticMarkup } from "react-dom/server";
import ChartFullscreenDialog, {
  attachFullscreenDialog,
} from "@/components/event/ChartFullscreenDialog";

function zOf(className: string): number {
  const m = className.match(/(?:^|\s)z-(?:\[(\d+)\]|(\d+))(?:\s|$)/);
  if (!m) throw new Error(`no z-index in: ${className}`);
  return Number(m[1] ?? m[2]);
}

function classOf(html: string, marker: string): string {
  const at = html.indexOf(marker);
  if (at < 0) throw new Error(`marker not found: ${marker}`);
  const open = html.lastIndexOf("<", at);
  const tag = html.slice(open, html.indexOf(">", at) + 1);
  const m = tag.match(/class(?:Name)?="([^"]*)"/);
  if (!m) throw new Error(`no class on: ${tag}`);
  return m[1];
}

const html = renderToStaticMarkup(
  <ChartFullscreenDialog title="Win Probability" onClose={() => {}}>
    <div data-testid="chart-body">chart</div>
  </ChartFullscreenDialog>,
);

describe("#10250 the fullscreen chart sits above the phone bottom nav", () => {
  it("paints over the bottom nav: its layer is strictly higher than the nav's", () => {
    const nav = readFileSync(join(process.cwd(), "components/BottomNav.tsx"), "utf8");
    const navClass = nav.match(/className="(md:hidden fixed bottom-0[^"]*)"/);
    expect(navClass).not.toBeNull();
    const dialogZ = zOf(classOf(html, 'data-testid="chart-fullscreen-dialog"'));
    // Strictly greater. Equal z-indexes are the defect: DOM order decides,
    // and the nav comes later.
    expect(dialogZ).toBeGreaterThan(zOf(navClass![1]));
  });

  it("covers the whole viewport and clears the bottom safe area", () => {
    const cls = classOf(html, 'data-testid="chart-fullscreen-dialog"');
    expect(cls).toMatch(/(?:^|\s)fixed(?:\s|$)/);
    expect(cls).toMatch(/(?:^|\s)inset-0(?:\s|$)/);
    expect(cls).toContain("pb-[env(safe-area-inset-bottom,0px)]");
  });

  it("is a named modal dialog, and the chart renders inside it", () => {
    expect(html).toContain('role="dialog"');
    expect(html).toContain('aria-modal="true"');
    expect(html).toContain('aria-label="Win Probability"');
    expect(html).toContain('data-testid="chart-body"');
  });

  it("the close button has an accessible name and its glyph is hidden", () => {
    expect(html).toMatch(/<button[^>]*aria-label="Close fullscreen chart"/);
    expect(html).toMatch(/<button[^>]*type="button"/);
    expect(html).toMatch(/<svg aria-hidden="true"/);
  });

  it("the page uses the dialog, and its expand control is named and wired as the opener", () => {
    const page = readFileSync(join(process.cwd(), "app/events/[id]/page.tsx"), "utf8");
    // The old tied layer must not come back as an inline copy.
    expect(page).not.toContain('className="fixed inset-0 z-50 bg-surface-card flex flex-col"');
    expect(page).toContain("<ChartFullscreenDialog");
    expect(page).toContain("openerRef={chartFullscreenOpenerRef}");
    const opener = page.slice(page.indexOf("ref={chartFullscreenOpenerRef}") - 200, page.indexOf("ref={chartFullscreenOpenerRef}") + 400);
    expect(opener).toContain('aria-label="Open fullscreen chart"');
    expect(opener).toContain("setChartFullscreen(true)");
  });
});

describe("#10250 Escape closes the fullscreen chart and focus goes back", () => {
  function fakeTarget() {
    const listeners = new Map<string, Set<(e: KeyboardEvent) => void>>();
    return {
      addEventListener: (type: string, fn: (e: KeyboardEvent) => void) => {
        if (!listeners.has(type)) listeners.set(type, new Set());
        listeners.get(type)!.add(fn);
      },
      removeEventListener: (type: string, fn: (e: KeyboardEvent) => void) => {
        listeners.get(type)?.delete(fn);
      },
      press(key: string) {
        for (const fn of listeners.get("keydown") ?? []) fn({ key } as KeyboardEvent);
      },
      count: () => listeners.get("keydown")?.size ?? 0,
    };
  }

  it("Escape calls onClose; other keys do not", () => {
    const target = fakeTarget();
    const onClose = jest.fn();
    attachFullscreenDialog({ target: target as never, onClose, closeButton: null, opener: null });
    target.press("Enter");
    target.press("ArrowLeft");
    expect(onClose).not.toHaveBeenCalled();
    target.press("Escape");
    expect(onClose).toHaveBeenCalledTimes(1);
  });

  it("opening focuses the close button, and teardown returns focus to the opener", () => {
    const target = fakeTarget();
    const order: string[] = [];
    const teardown = attachFullscreenDialog({
      target: target as never,
      onClose: () => {},
      closeButton: { focus: () => order.push("close") },
      opener: { focus: () => order.push("opener") },
    });
    expect(order).toEqual(["close"]);
    teardown();
    expect(order).toEqual(["close", "opener"]);
  });

  it("teardown removes the key listener, so a closed dialog cannot be closed again", () => {
    const target = fakeTarget();
    const onClose = jest.fn();
    const teardown = attachFullscreenDialog({ target: target as never, onClose, closeButton: null, opener: null });
    expect(target.count()).toBe(1);
    teardown();
    expect(target.count()).toBe(0);
    target.press("Escape");
    expect(onClose).not.toHaveBeenCalled();
  });
});
