/** @jest-environment jsdom */
/**
 * #11555 — Back from an attached market on an NFL week hub lands the game where
 * the reader left it.
 *
 * Before: the hub restored the remembered offset (#9982) on its first frame,
 * while the week links above the games had not drawn yet (they wait for their
 * own read). When they drew, the game moved down by their height — 94px at
 * 390px on Week 5 — so its card top no longer matched the remembered offset.
 * After: the remembered offset is applied once more when the week navigation
 * settles, unless the reader has already started moving the page.
 *
 * jsdom has no layout, so the page is modelled: the game card sits at a fixed
 * document position, pushed down by the week links' height once they draw.
 */
import React from "react";
import { createRoot, type Root } from "react-dom/client";
import { act } from "react-dom/test-utils";
jest.mock("@/lib/api", () => ({ API_URL: "http://fixture.invalid" }));
jest.mock("next/link", () => ({ __esModule: true, default: ({ href, children, ...props }: { href: string; children: React.ReactNode }) => <a href={href} {...props}>{children}</a> }));
jest.mock("@/components/collections/CollectionMemberCard", () => ({ CollectionMemberCard: ({ member }: { member: { href: string; key: string } }) => <a href={member.href}>{member.key}</a> }));
import CollectionHub from "@/components/collections/CollectionHub";
import { collectionMemberDomId, forgetAcceptedCollections, parseCollection, settleCollectionRead } from "@/lib/collections";
import { nflHub } from "./fixtures";

const slug = "nfl-2026-week-5";
const body = { ...nflHub(), slug, container: { ...nflHub().container, slug }, edition: { kind: "nfl_week", league: "nfl", season: 2026, stage: "Regular Season", week: 5 } };
const link = (week: number) => ({ slug: `nfl-2026-week-${week}`, label: `NFL 2026 · Week ${week}`, edition: { kind: "nfl_week", league: "nfl", season: 2026, stage: "Regular Season", week }, destination: { kind: "container", slug: `nfl-2026-week-${week}`, web: `/collections/nfl-2026-week-${week}`, api: `/api/containers/nfl-2026-week-${week}` } });
const withLinks = { slug, state: "available", previous: link(4), next: link(6) };
const noLinks = { slug, state: "available", previous: null, next: null };

const GAME = "event:7";
const GAME_DOC_TOP = 1641; // the game card's document top with the week links absent
const LINKS = 94; // week links (70) + the hub's 24px gap, measured at 390px
const LEFT_AT = 120; // card top in the viewport when the reader tapped the market

let root: Root; let element: HTMLDivElement; let scrollY: number;
const navigationAnswers: ((value: unknown) => void)[] = [];
const cardTop = () => document.getElementById(collectionMemberDomId(GAME))!.getBoundingClientRect().top;

beforeEach(() => {
  (globalThis as unknown as { IS_REACT_ACT_ENVIRONMENT: boolean }).IS_REACT_ACT_ENVIRONMENT = true;
  forgetAcceptedCollections(); sessionStorage.clear(); navigationAnswers.length = 0;
  scrollY = 0;
  Object.defineProperty(window, "scrollY", { configurable: true, get: () => scrollY });
  window.scrollTo = jest.fn((options: ScrollToOptions) => { scrollY = options.top ?? scrollY; }) as unknown as typeof window.scrollTo;
  jest.spyOn(HTMLElement.prototype, "getBoundingClientRect").mockImplementation(function (this: HTMLElement) {
    const drawn = !!document.querySelector('nav[aria-label="Available NFL weeks"]');
    const top = this.id === collectionMemberDomId(GAME) ? GAME_DOC_TOP + (drawn ? LINKS : 0) - scrollY : 0;
    return { top, bottom: top + 200 } as DOMRect;
  });
  // Back: the hub is accepted in memory and the reading context was saved on the tap.
  settleCollectionRead(slug, { hub: parseCollection(body, slug) });
  sessionStorage.setItem(`collection-reading:${slug}`, JSON.stringify({ slug, memberKey: GAME, offset: LEFT_AT, expanded: [] }));
  global.fetch = jest.fn((url: string) => String(url).endsWith("week-navigation")
    ? new Promise((resolve) => navigationAnswers.push(resolve))
    : Promise.resolve({ ok: true, status: 200, json: async () => body })) as unknown as typeof fetch;
  element = document.createElement("div"); document.body.append(element); root = createRoot(element);
});
afterEach(() => { act(() => root.unmount()); element.remove(); jest.restoreAllMocks(); forgetAcceptedCollections(); });

const back = async () => { await act(async () => root.render(<CollectionHub slug={slug} />)); };
// Every navigation read the hub has started gets the same answer; only the current read's draws.
const answerNavigation = async (value: unknown) => {
  await act(async () => { navigationAnswers.forEach((resolve) => resolve({ ok: true, json: async () => value })); });
};

test("the game card returns to where the reader left it after the week links draw", async () => {
  await back();
  expect(cardTop()).toBe(LEFT_AT); // first frame: restored, links not drawn yet
  await answerNavigation(withLinks);
  expect(element.querySelector('nav[aria-label="Available NFL weeks"]')).not.toBeNull();
  expect(cardTop()).toBe(LEFT_AT); // was LEFT_AT + 94 before #11555
});

test("a week with no links to draw leaves the restored position alone", async () => {
  await back();
  await answerNavigation(noLinks);
  expect(element.querySelector('nav[aria-label="Available NFL weeks"]')).toBeNull();
  expect(cardTop()).toBe(LEFT_AT);
});

test("a reader who has started scrolling is never moved when the links draw", async () => {
  await back();
  act(() => { window.dispatchEvent(new Event("wheel")); scrollY += 300; });
  const before = scrollY;
  await answerNavigation(withLinks);
  expect(scrollY).toBe(before);
});

test("the offset is applied once: a later refresh of the week links never scrolls", async () => {
  await back();
  await answerNavigation(withLinks);
  const calls = (window.scrollTo as jest.Mock).mock.calls.length;
  const refresh = Array.from(element.querySelectorAll("button")).find((button) => button.textContent === "Refresh")!;
  await act(async () => refresh.dispatchEvent(new MouseEvent("click", { bubbles: true })));
  await answerNavigation(withLinks);
  expect((window.scrollTo as jest.Mock).mock.calls.length).toBe(calls);
});
