import React from "react";
import { renderToStaticMarkup } from "react-dom/server";

jest.mock("next/link", () => {
  const ReactLib = require("react");
  return { __esModule: true, default: ({ href, children, ...props }: { href: string; children: React.ReactNode }) => ReactLib.createElement("a", { href, ...props }, children) };
});
jest.mock("@/components/Analytics", () => ({ useAnalyticsContext: () => ({ track: () => {} }) }));

import { CollectionMemberCard } from "@/components/collections/CollectionMemberCard";
import { parseCollection } from "@/lib/collections";
import { nflHub, mlbHub } from "./fixtures";

describe("collection readers see the supplied card facts", () => {
  test("ordinary game and question keep their canonical member destinations", () => {
    const hub = parseCollection(nflHub(), "nfl-2026-week-4");
    const scheduled = renderToStaticMarkup(<CollectionMemberCard member={hub.members[0]} />);
    expect(scheduled).toContain('href="/events/7"');
    expect(scheduled).toContain("60%");
    expect(scheduled).toContain("40%");
    const prop = renderToStaticMarkup(<CollectionMemberCard member={hub.related["event:7"][0]} />);
    expect(prop).toContain('href="/futures/70"');
    expect(prop).toContain("Josh Allen");
    expect(prop).toContain("65%");
  });
  test("settled question says Won while missing price never becomes zero", () => {
    const hub = parseCollection(mlbHub(), "mlb-2026-postseason");
    const settled = renderToStaticMarkup(<CollectionMemberCard member={hub.members[1]} />);
    expect(settled).toContain('href="/futures/81"');
    expect(settled).toContain("Dodgers");
    expect(settled).toContain("Won");
    expect(settled).not.toContain("100%");
    const absent = renderToStaticMarkup(<CollectionMemberCard member={hub.members[2]} />);
    expect(absent).toContain("Price unavailable");
    expect(absent).not.toContain("0%");
  });
  test("final without an authoritative grade remains explicitly unavailable", () => {
    const raw = mlbHub();
    delete ((raw.sections[1].members[0] as ReturnType<typeof import("./fixtures").question>).card.top_outcomes[0] as { is_winner?: boolean }).is_winner;
    const hub = parseCollection(raw, raw.slug);
    const markup = renderToStaticMarkup(<CollectionMemberCard member={hub.members[1]} />);
    expect(markup).toContain("Result unavailable");
    expect(markup).not.toContain(">Won<");
  });
});
