/**
 * Issue 13551 (Rulings 366: B, 367: A, and Fable's 7 rules) — Layout-generic Kit v1 renderer tests.
 */
import fs from "node:fs";
import path from "node:path";
import React from "react";
import { renderToStaticMarkup } from "react-dom/server";
import {
  computeCountdownDaysLeft,
  COSMETIC_KIT_V1_FIELDS,
  KitCardRenderer,
  MEANING_CARRYING_KIT_V1_FIELDS,
  parseKitCardV1,
} from "@/components/discover/kit/KitCardRenderer";
import type { KitV1CardSpec, KitV1GridBody, KitV1StackBody } from "@/components/discover/kit/types";

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

  test("parseKitCardV1 decodes and renders all worked examples with expected labels and percents", () => {
    expect(golden.kit_version).toBe(1);
    expect(golden.items).toHaveLength(17);
    const rendered = golden.items.map((item) => {
      const parsed = parseKitCardV1(item);
      expect(parsed).not.toBeNull();
      return renderToStaticMarkup(<KitCardRenderer spec={parsed!} />);
    });

    expect(rendered[0]).toContain("Georgia");
    expect(rendered[0]).toContain(">4<");
    expect(rendered[0]).toContain("Shaded cells show each team&#x27;s chance");
    expect(rendered[1]).toContain("by Dec 31");
    expect(rendered[1]).toContain("81%");
    expect(rendered[1]).toContain("US–Iran ceasefire");
    expect(rendered[1]).not.toContain("US x Iran");
    expect(rendered[2]).toContain("days left");
    expect(rendered[3]).toContain("at WSH");
    expect(rendered[4]).toContain("in doubt");
    expect(rendered[5]).toContain("1 in 8");
    expect(rendered[5]).toContain("12%");
    expect(rendered[6]).toContain("NBA");
    expect(rendered[6]).toContain("POR");
    expect(rendered[6]).not.toContain("PTB");
    expect(rendered[6]).not.toContain("Rule 6");
    expect(rendered[6]).toContain("Live · 28–32");
    expect(rendered[7]).toContain("67%");
    expect(rendered[7]).toContain("&lt;1%");
    expect(rendered[7]).toContain("Daily chance");
    expect(rendered[7]).not.toContain("367: A");
    expect(rendered[7]).toContain("Chance it is out before each day:");
    expect(rendered[7]).toContain("Dec 4 or later, 10%");
    expect(rendered[7]).not.toContain("Served ladder");
    expect(rendered[8]).toContain("Largest company at the end of 2026");
    expect(rendered[9]).toContain("&lt;1%");
    expect(rendered[9]).not.toContain(">0%<");
    expect(rendered[10]).toContain("Luka Dončić");
    expect(rendered[10]).toContain("&lt;1%");
    expect(rendered[10]).not.toContain(">0%<");
    expect(rendered[10]).toContain("Shai Gilgeous-Alexander");
    expect(rendered[10]).toContain("Giannis Antetokounmpo");
    expect(rendered[12]).not.toContain("<img");
    expect(rendered[14]).toContain("Boyd Holbrook");
    expect(rendered[14]).toContain("Anthony Mackie");
    expect(rendered[14]).not.toContain("Boyd Holbrook &amp; Anthony Mackie");
    expect(rendered[16]).toContain("38% each");
    expect(rendered[16]).toContain("→");
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

  test("countdown marks compute live PT days left (1 day left, ends today) and unknown top-level keys are ignored", () => {
    const deadlineIso = "2026-12-31T23:59:59-08:00";
    expect(computeCountdownDaysLeft(deadlineIso, new Date("2026-12-30T17:20:00Z"))).toBe(1);
    expect(computeCountdownDaysLeft(deadlineIso, new Date("2026-12-31T17:20:00Z"))).toBe(0);

    const parsedExtra = parseKitCardV1({
      ...golden.items[2],
      some_future_field: { version: 2 },
    });
    expect(parsedExtra).not.toBeNull();
    const baseHtml = renderToStaticMarkup(<KitCardRenderer spec={golden.items[2]} />);
    const extraHtml = renderToStaticMarkup(<KitCardRenderer spec={parsedExtra!} />);
    expect(extraHtml).toBe(baseHtml);
  });

  test("cosmetic fields render defaults while meaning-carrying fields fail closed", () => {
    expect(COSMETIC_KIT_V1_FIELDS).toContain("picture.subject_kind");
    expect(MEANING_CARRYING_KIT_V1_FIELDS).toContain("bar.bar_style");
    expect(MEANING_CARRYING_KIT_V1_FIELDS).toContain("number.unit");

    const sample = golden.items[2];
    const stackBody = sample.body as KitV1StackBody;
    const cosmeticMutated = {
      ...sample,
      some_future_field: "ignored_top_level_value",
      variant: "unknown_future_variant",
      body: {
        ...stackBody,
        header_layout: "ticker" as KitV1StackBody["header_layout"],
        items: stackBody.items.map((it, idx) =>
          idx === 0
            ? {
                ...it,
                marks: it.marks.map((m) => {
                  if (m.mark === "picture") return { ...m, size: "xxl" as never, subject_kind: "planet" };
                  if (m.mark === "word") return { ...m, style: "future" as never, tone: "neon" as never, width: "giant" as never };
                  if (m.mark === "bar") return { ...m, width: "giant" as never };
                  if (m.mark === "number") return { ...m, prominence: "mega" as never };
                  return m;
                }),
              }
            : it,
        ),
      },
    };
    const parsedCosmetic = parseKitCardV1(cosmeticMutated);
    expect(parsedCosmetic).not.toBeNull();
    const cosmeticHtml = renderToStaticMarkup(<KitCardRenderer spec={parsedCosmetic!} />);
    expect(cosmeticHtml).toContain("By December 31");
    expect(cosmeticHtml).toContain("days left");
    expect(cosmeticHtml).toContain("all of these end on Dec 31");

    // Meaning-carrying unknowns fail closed
    const badBarStyle = {
      ...sample,
      body: {
        ...stackBody,
        items: [
          {
            ...stackBody.items[0],
            marks: stackBody.items[0].marks.map((m) =>
              m.mark === "bar" ? { ...m, bar_style: "stacked3" } : m,
            ),
          },
        ],
      },
    };
    expect(parseKitCardV1(badBarStyle)).toBeNull();

    const badNumberUnit = {
      ...sample,
      body: {
        ...stackBody,
        items: [
          {
            ...stackBody.items[0],
            marks: stackBody.items[0].marks.map((m) =>
              m.mark === "number" ? { ...m, unit: "points" } : m,
            ),
          },
        ],
      },
    };
    expect(parseKitCardV1(badNumberUnit)).toBeNull();

    const gridSample = golden.items[0];
    const gridBody = gridSample.body as KitV1GridBody;
    expect(
      parseKitCardV1({
        ...gridSample,
        body: { ...gridBody, row_layout: "carousel" },
      }),
    ).toBeNull();

    const axisSample = golden.items[4];
    const axisBody = axisSample.body as unknown as Record<string, unknown>;
    expect(
      parseKitCardV1({
        ...axisSample,
        body: {
          ...axisBody,
          scale: {
            ...(axisBody.scale as Record<string, unknown>),
            scale_kind: "logarithmic",
          },
        },
      }),
    ).toBeNull();
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

  test("renders 387:A initials circle, film 2:3 poster, person 1:1 circle, 389:C bubble % badges, and range outline", () => {
    const partialSpec: KitV1CardSpec = {
      kit_version: 1,
      id: "kit-387a-web",
      layout: "stack",
      variant: "casting_sheet",
      kicker: "FILM",
      common_headline: "Casting and delays",
      stat_caption: "Dune: Part Three leads at 81%.",
      source_mark: { label: "2 sources", count: 2 },
      route: { kind: "collection", id: 1, slug: "casting" },
      refusal_reason: null,
      body: {
        header_layout: "none",
        items: [
          {
            id: "r1",
            marks: [
              { mark: "picture", url: null, initials: "HJ", alt: "Hugh Jackman", subject_kind: "person", size: "sm" },
              { mark: "word", text: "Hugh Jackman", style: "row", width: "flex" },
              { mark: "number", value: 94, display: "94%", unit: "%" },
            ],
          },
          {
            id: "r2",
            marks: [
              { mark: "picture", url: "https://image.tmdb.org/t/p/w342/glt0v4I89rMWstDNCaFXc5SNyO1.jpg", alt: "Dune: Part Three", subject_kind: "film", size: "sm" },
              { mark: "word", text: "Dune: Part Three", style: "row", width: "flex" },
              { mark: "number", value: 81, display: "81%", unit: "%" },
            ],
          },
          {
            id: "r3",
            marks: [
              { mark: "picture", url: "https://image.tmdb.org/t/p/w185/sample.jpg", alt: "Matthew Rhys", subject_kind: "person", size: "sm" },
              { mark: "word", text: "Matthew Rhys", style: "row", width: "flex" },
              { mark: "number", value: 73, display: "73%", unit: "%" },
            ],
          },
        ],
      },
    };
    const parsedPartial = parseKitCardV1(partialSpec);
    expect(parsedPartial).not.toBeNull();
    const htmlPartial = renderToStaticMarkup(<KitCardRenderer spec={parsedPartial!} />);
    expect(htmlPartial).toContain(">HJ<");
    expect(htmlPartial).toContain("w-[22px]"); // 2:3 film poster
    expect(htmlPartial).toContain("aspect-square shrink-0 rounded-full"); // 1:1 person circle

    // Bubble line: % under crest + one-line end summaries + sr-only readable list
    const nhlSpec: KitV1CardSpec = {
      ...(golden.items[4] as KitV1CardSpec),
      body: {
        ...(golden.items[4].body as any),
        marks: (golden.items[4].body as any).marks.map((m: any) =>
          m.in_band ? { ...m, badge_text: `${Math.round(m.x)}%` } : m,
        ),
        summary_marks: [
          { mark: "word", text: "25% or less (9): Canucks, Blackhawks, Red Wings +6", style: "sub", tone: "secondary" },
          { mark: "word", text: "75% or more (11): Oilers, Wild, Hurricanes +8", style: "sub", tone: "secondary" },
        ],
        footer_marks: undefined,
      },
    };
    const nhlHtml = renderToStaticMarkup(<KitCardRenderer spec={parseKitCardV1(nhlSpec)!} />);
    expect(nhlHtml).toContain("38%");
    expect(nhlHtml).toContain("Canucks, Blackhawks, Red Wings +6");
    expect(nhlHtml).toContain("sr-only");

    const largeTextNhlHtml = renderToStaticMarkup(
      <KitCardRenderer spec={parseKitCardV1(nhlSpec)!} forceLargeText />,
    );
    expect(largeTextNhlHtml).toContain('data-testid="axis-large-text-list"');
    expect(largeTextNhlHtml).toContain("Utah Mammoth");
    expect(largeTextNhlHtml).toContain("73%");
  });
});
