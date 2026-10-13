/** @jest-environment jsdom */
import React from "react";
import { createRoot, type Root } from "react-dom/client";
import { act } from "react-dom/test-utils";
jest.mock("@/lib/api", () => ({ API_URL: "http://fixture.invalid" }));
jest.mock("next/link", () => ({ __esModule: true, default: ({ href, children, ...props }: { href: string; children: React.ReactNode }) => <a href={href} {...props}>{children}</a> }));
import { CollectionWeekNavigation } from "@/components/collections/CollectionWeekNavigation";
let root: Root; let element: HTMLDivElement;
const pending: ((value: unknown) => void)[] = [];
const answer = (current: number, next: number) => ({ slug: `nfl-2026-week-${current}`, state: "available", previous: null, next: { slug: `nfl-2026-week-${next}`, label: `NFL 2026 · Week ${next}`, edition: { kind: "nfl_week", league: "nfl", season: 2026, stage: "Regular Season", week: next }, destination: { kind: "container", slug: `nfl-2026-week-${next}`, web: `/collections/nfl-2026-week-${next}`, api: `/api/containers/nfl-2026-week-${next}` } } });
beforeEach(() => {
  (globalThis as unknown as { IS_REACT_ACT_ENVIRONMENT: boolean }).IS_REACT_ACT_ENVIRONMENT = true;
  pending.length = 0; element = document.createElement("div"); document.body.append(element); root = createRoot(element);
  global.fetch = jest.fn(() => new Promise((resolve) => pending.push(resolve))) as unknown as typeof fetch;
});
afterEach(() => { act(() => root.unmount()); element.remove(); });
const draw = (week: number, read: number) => act(() => root.render(<CollectionWeekNavigation slug={`nfl-2026-week-${week}`} read={read} />));
const resolve = async (index: number, value: unknown) => { await act(async () => { pending[index]({ ok: true, json: async () => value }); }); };
test("slug change and later refresh reject slow earlier metadata", async () => {
  draw(4, 1); draw(5, 2); await resolve(1, answer(5, 6)); expect(element.textContent).toContain("Week 6");
  await resolve(0, answer(4, 9)); expect(element.textContent).not.toContain("Week 9");
  draw(5, 3); expect(element.querySelector("a")).toBeNull(); draw(5, 4);
  await resolve(3, { slug: "nfl-2026-week-5", state: "available", previous: null, next: null });
  await resolve(2, answer(5, 7)); expect(element.querySelector("a")).toBeNull();
});
test("withdrawn hub unmount rejects late optional answer", async () => {
  draw(4, 1); act(() => root.render(<p>Collection withdrawn</p>)); await resolve(0, answer(4, 5)); expect(element.textContent).toBe("Collection withdrawn");
});

jest.mock("@/components/collections/CollectionMemberCard", () => ({ CollectionMemberCard: ({ member }: { member: { href: string; key: string } }) => <a href={member.href}>{member.key}</a> }));
import CollectionHub from "@/components/collections/CollectionHub";
import { forgetAcceptedCollections, parseCollection, settleCollectionRead } from "@/lib/collections";
import { nflHub } from "./fixtures";

test("actual hub keeps ordinary members and saves reading context before week navigation", async () => {
  forgetAcceptedCollections(); sessionStorage.clear();
  const slug = "nfl-2026-week-4";
  const body = { ...nflHub(), slug, container: { ...nflHub().container, slug }, edition: { kind: "nfl_week", league: "nfl", season: 2026, stage: "Regular Season", week: 4 } };
  const hub = parseCollection(body, slug); settleCollectionRead(slug, { hub });
  global.fetch = jest.fn(async (url) => ({ ok: true, status: 200, json: async () => String(url).endsWith("week-navigation") ? answer(4, 6) : body })) as unknown as typeof fetch;
  await act(async () => root.render(<CollectionHub slug={slug} />));
  expect(element.querySelectorAll("[data-collection-member]")).toHaveLength(5);
  expect(element.textContent).toContain("Back to Discover");
  const first = document.getElementById(`collection-member-${hub.members[0].key}`)!;
  jest.spyOn(first, "getBoundingClientRect").mockReturnValue({ bottom: 100, top: 12 } as DOMRect);
  const next = element.querySelector('nav a[href="/collections/nfl-2026-week-6"]')!;
  next.addEventListener("click", (event) => event.preventDefault());
  act(() => next.dispatchEvent(new MouseEvent("click", { bubbles: true, cancelable: true })));
  expect(JSON.parse(sessionStorage.getItem(`collection-reading:${slug}`)!)).toMatchObject({ slug, memberKey: hub.members[0].key, offset: 12 });
  // Optional failure on the same mounted reader must leave the good cards.
  global.fetch = jest.fn(async (url) => String(url).endsWith("week-navigation") ? { ok: false } : { ok: true, status: 200, json: async () => body }) as unknown as typeof fetch;
  const refresh = Array.from(element.querySelectorAll("button")).find((button) => button.textContent === "Refresh")!;
  await act(async () => refresh.dispatchEvent(new MouseEvent("click", { bubbles: true })));
  expect(element.querySelectorAll("[data-collection-member]")).toHaveLength(5);
  expect(element.textContent).toContain("Week navigation isn't available right now.");
  expect(element.querySelector("nav")).toBeNull();
  forgetAcceptedCollections();
});
