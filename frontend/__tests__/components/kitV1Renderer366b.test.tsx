/**
 * Issue 13551 (Rulings 366: B, 367: A, and Fable's 7 rules) — Layout-generic Kit v1 renderer tests.
 */
import fs from "node:fs";
import path from "node:path";
import React from "react";
import { renderToStaticMarkup } from "react-dom/server";
import {
  KitCardRenderer,
  computeCountdownDaysLeft,
  parseKitCardV1,
} from "@/components/discover/kit/KitCardRenderer";
import type { KitV1CardSpec, KitV1StackBody } from "@/components/discover/kit/types";

describe("Kit v1 layout-generic web renderer & fail-closed envelope (366: B, 367: A, 7 rules)", () => {
  const goldenPath = path.resolve(
    process.cwd(),
    "..",
    "backend",
    "data",
    "discover",
    "kit_v1_golden_examples.json",
  );
  const golden = JSON.parse(fs.readFileSync(goldenPath, "utf-8")) as {
    kit_version: number;
    count: number;
    items: KitV1CardSpec[];
    refusals: Array<{ title: string; spec: KitV1CardSpec }>;
  };

  test("parseKitCardV1 decodes and renders all 8 golden examples with expected labels and percents", () => {
    expect(golden.kit_version).toBe(1);
    expect(golden.items).toHaveLength(8);
    const rendered = golden.items.map((item) => {
      const parsed = parseKitCardV1(item);
      expect(parsed).not.toBeNull();
      return renderToStaticMarkup(<KitCardRenderer spec={parsed!} />);
    });

    expect(rendered[0]).toContain("Georgia");
    expect(rendered[0]).toContain(">4<");
    expect(rendered[0]).toContain("Shaded cells show served chances");
    expect(rendered[1]).toContain("by Dec 31");
    expect(rendered[1]).toContain("81%");
    expect(rendered[2]).toContain("38");
    expect(rendered[2]).toContain("days left");
    expect(rendered[3]).toContain("at WSH");
    expect(rendered[4]).toContain("in doubt");
    expect(rendered[5]).toContain("1 in 8");
    expect(rendered[5]).toContain("12%");
    expect(rendered[6]).toContain("NBA");
    expect(rendered[6]).not.toContain("Rule 6");
    expect(rendered[6]).toContain("Live · 28–32");
    expect(rendered[7]).toContain("67%");
    expect(rendered[7]).toContain("Daily chance");
    expect(rendered[7]).not.toContain("367: A");
    expect(rendered[7]).toContain("Served ladder:");
    expect(rendered[7]).toContain("one rung of the ladder minus the rung before it");
  });

  test("defining kit test: renaming variant to an unknown string or null renders byte-for-byte identical output for all 8 examples", () => {
    for (const item of golden.items) {
      const baseParsed = parseKitCardV1(item);
      const unknownParsed = parseKitCardV1({
        ...item,
        variant: "unheard_of_future_bracket_2027",
      });
      const nullParsed = parseKitCardV1({
        ...item,
        variant: null,
      });

      expect(baseParsed).not.toBeNull();
      expect(unknownParsed).not.toBeNull();
      expect(nullParsed).not.toBeNull();

      const baseHtml = renderToStaticMarkup(<KitCardRenderer spec={baseParsed!} />);
      const unknownHtml = renderToStaticMarkup(<KitCardRenderer spec={unknownParsed!} />);
      const nullHtml = renderToStaticMarkup(<KitCardRenderer spec={nullParsed!} />);

      expect(unknownHtml).toBe(baseHtml);
      expect(nullHtml).toBe(baseHtml);
    }
  });

  test("parseKitCardV1 fails closed on unknown kit_version, unknown layout, unknown mark, empty body, and refusals", () => {
    const sample = golden.items[2];
    expect(parseKitCardV1({ ...sample, kit_version: 2 })).toBeNull();
    expect(parseKitCardV1({ ...sample, layout: "unknown" })).toBeNull();
    expect(parseKitCardV1({ ...sample, body: {} })).toBeNull();
    expect(parseKitCardV1({ ...sample, fallback_today: true })).toBeNull();
    expect(
      parseKitCardV1({
        ...sample,
        refusal_reason: "Refused",
      }),
    ).toBeNull();

    const stackBody = sample.body as KitV1StackBody;
    const withUnknownMark = {
      ...sample,
      body: {
        ...stackBody,
        items: [
          {
            ...stackBody.items[0],
            marks: [
              ...stackBody.items[0].marks,
              { mark: "sparkle", text: "unsupported" },
            ],
          },
        ],
      },
    };
    expect(parseKitCardV1(withUnknownMark)).toBeNull();

    const withBareHex = {
      ...golden.items[3],
      body: {
        ...(golden.items[3].body as KitV1StackBody),
        items: [
          {
            ...(golden.items[3].body as KitV1StackBody).items[0],
            marks: (golden.items[3].body as KitV1StackBody).items[0].marks.map((m) =>
              m.mark === "bar" ? { ...m, fill_color: "#008348" } : m,
            ),
          },
        ],
      },
    };
    expect(parseKitCardV1(withBareHex)).toBeNull();

    const html = renderToStaticMarkup(
      <KitCardRenderer
        spec={{
          kit_version: 1,
          id: "refusal-1",
          layout: null,
          variant: null,
          fallback_today: true,
          refusal_reason: "Slate mixes >1 sport_key; keep today's card.",
        }}
      />,
    );
    expect(html).toContain("Standard card fallback");
    expect(html).toContain("Slate mixes &gt;1 sport_key");
  });

  test("countdown marks compute live PT days left (1 day left, ends today) and row secondary_text renders", () => {
    const deadlineIso = "2026-11-30T23:59:00+00:00";
    expect(computeCountdownDaysLeft(deadlineIso, new Date("2026-11-24T17:20:00Z"))).toBe(6);
    expect(computeCountdownDaysLeft(deadlineIso, new Date("2026-11-29T17:20:00Z"))).toBe(1);
    expect(computeCountdownDaysLeft(deadlineIso, new Date("2026-11-30T17:20:00Z"))).toBe(0);

    const countdownCard: KitV1CardSpec = {
      ...golden.items[2],
      body: {
        ...(golden.items[2].body as KitV1StackBody),
        header_marks: [
          {
            mark: "number",
            value: 6,
            display: "6",
            unit: "days",
            deadline_iso: deadlineIso,
            tone: "accent",
            prominence: "hero",
            align: "left",
            width: "auto",
          },
          {
            mark: "word",
            text: "days left",
            style: "hero_label",
            deadline_iso: deadlineIso,
            tone: "primary",
            align: "left",
            width: "flex",
            bold: true,
            secondary_text: "all of these end on November 30",
          },
        ],
      },
    };

    jest.useFakeTimers();
    try {
      jest.setSystemTime(new Date("2026-11-29T17:20:00Z"));
      const oneDayHtml = renderToStaticMarkup(<KitCardRenderer spec={countdownCard} />);
      expect(oneDayHtml).toContain(">1<");
      expect(oneDayHtml).toContain("day left");
      expect(oneDayHtml).not.toContain("days left");

      jest.setSystemTime(new Date("2026-11-30T17:20:00Z"));
      const todayHtml = renderToStaticMarkup(<KitCardRenderer spec={countdownCard} />);
      expect(todayHtml).toContain("Today");
      expect(todayHtml).toContain("ends today");
    } finally {
      jest.useRealTimers();
    }

    const withSecondary = {
      ...golden.items[0],
      body: {
        ...(golden.items[0].body as any),
        rows: [
          {
            ...(golden.items[0].body as any).rows[0],
            leading: [
              ...(golden.items[0].body as any).rows[0].leading.slice(0, -1),
              { mark: "word", text: "Inde Navarrette", secondary_text: "Actor", style: "row", width: "flex", bold: true },
            ],
          },
        ],
      },
    } as KitV1CardSpec;
    const secHtml = renderToStaticMarkup(<KitCardRenderer spec={withSecondary} />);
    expect(secHtml).toContain("Inde Navarrette");
    expect(secHtml).toContain("Actor");
  });

  test("uses light-mode semantic tokens only with zero dark classes, zero raw hexes, and zero variant branches", () => {
    const src = fs.readFileSync(
      path.join(process.cwd(), "components", "discover", "kit", "KitCardRenderer.tsx"),
      "utf-8",
    );
    expect(src).not.toMatch(/\bdark:/);
    expect(src).not.toMatch(/#[0-9a-fA-F]{3,6}/);
    expect(src).not.toMatch(/\.variant\b/);
  });
});
