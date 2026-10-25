/** @jest-environment jsdom */
/**
 * #11567 — after Back on an NFL week hub the game card is in place from the
 * first frame.
 *
 * Before: on Back the browser restores the scroll position the reader left,
 * measured with the week links drawn, but the remounted hub drew no links until
 * their own read answered. For those frames every game sat 94px higher (card
 * top 26 instead of 120 at 390px on Week 5, under the header), then jumped down.
 * After: a week whose links were drawn holds their place — same grid, same
 * cells, invisible and link-free — while the read is in flight. A week last
 * drawn without links holds nothing.
 *
 * jsdom has no layout, so the page is modelled as in the #11555 guard: the game
 * card's document top moves down by the links' height while either the links or
 * their reserved place is in the DOM (the structural equality of the two is
 * asserted separately).
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
const NAV = 'nav[aria-label="Available NFL weeks"]';
const RESERVED = "[data-week-links-reserved]";

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
    const held = !!document.querySelector(`${NAV}, ${RESERVED}`);
    const top = this.id === collectionMemberDomId(GAME) ? GAME_DOC_TOP + (held ? LINKS : 0) - scrollY : 0;
    return { top, bottom: top + 200 } as DOMRect;
  });
  settleCollectionRead(slug, { hub: parseCollection(body, slug) });
  global.fetch = jest.fn((url: string) => String(url).endsWith("week-navigation")
    ? new Promise((resolve) => navigationAnswers.push(resolve))
    : Promise.resolve({ ok: true, status: 200, json: async () => body })) as unknown as typeof fetch;
  element = document.createElement("div"); document.body.append(element); root = createRoot(element);
});
afterEach(() => { act(() => root.unmount()); element.remove(); jest.restoreAllMocks(); forgetAcceptedCollections(); });

const mount = async () => { await act(async () => root.render(<CollectionHub slug={slug} />)); };
const answerNavigation = async (value: unknown) => {
  await act(async () => { navigationAnswers.splice(0).forEach((resolve) => resolve({ ok: true, json: async () => value })); });
};
// First visit: the week's links answer and draw; the reader scrolls the game to
// LEFT_AT and taps one of its attached markets (the hub unmounts).
const visitAndTap = async (navigation: unknown) => {
  await mount();
  await answerNavigation(navigation);
  scrollY = GAME_DOC_TOP + (document.querySelector(NAV) ? LINKS : 0) - LEFT_AT;
  sessionStorage.setItem(`collection-reading:${slug}`, JSON.stringify({ slug, memberKey: GAME, offset: LEFT_AT, expanded: [] }));
  act(() => root.unmount());
  root = createRoot(element);
  return scrollY;
};
// Back: the hub remounts and the browser puts back the scroll position it left.
const back = async (left: number) => { await mount(); scrollY = left; };

test("after Back the game card is at the reader's place before the week links answer", async () => {
  const left = await visitAndTap(withLinks);
  await back(left);
  expect(element.querySelector(NAV)).toBeNull(); // this read has not answered
  expect(cardTop()).toBe(LEFT_AT); // was LEFT_AT - 94 (26px, under the header)
  expect(element.querySelector(RESERVED)).not.toBeNull();
  await answerNavigation(withLinks);
  expect(element.querySelector(RESERVED)).toBeNull();
  expect(cardTop()).toBe(LEFT_AT);
});

test("the reserved place is the links' own grid and cells, invisible, with nothing to tap or read aloud", async () => {
  const left = await visitAndTap(withLinks);
  const nav = { grid: "", cells: [] as string[] };
  await mount(); // a second visit, to read the drawn links' shape
  await answerNavigation(withLinks);
  const drawn = element.querySelector(NAV)!;
  nav.grid = drawn.className; nav.cells = Array.from(drawn.children).map((cell) => cell.className.replace(" hover:bg-surface-elevated", ""));
  const drawnText = drawn.textContent;
  act(() => root.unmount()); root = createRoot(element);
  await back(left);
  const reserved = element.querySelector(RESERVED)!;
  expect(reserved.getAttribute("aria-hidden")).toBe("true");
  expect(reserved.className).toBe(`invisible ${nav.grid}`);
  expect(Array.from(reserved.children).map((cell) => cell.className)).toEqual(nav.cells);
  expect(reserved.textContent).toBe(drawnText);
  expect(reserved.querySelector("a")).toBeNull();
});

test("a week drawn without links reserves no gap on Back", async () => {
  const left = await visitAndTap(noLinks);
  await back(left);
  expect(element.querySelector(RESERVED)).toBeNull();
  expect(cardTop()).toBe(LEFT_AT);
  await answerNavigation(noLinks);
  expect(element.querySelector(RESERVED)).toBeNull();
  expect(cardTop()).toBe(LEFT_AT);
});

test("a week whose links read failed reserves no gap", async () => {
  await mount();
  await act(async () => { navigationAnswers.splice(0).forEach((resolve) => resolve({ ok: false })); });
  expect(element.textContent).toContain("Week navigation isn't available right now.");
  act(() => root.unmount()); root = createRoot(element);
  await mount();
  expect(element.querySelector(RESERVED)).toBeNull();
});

test("a refresh holds the links' place instead of collapsing it, and never draws the earlier read's links", async () => {
  await mount();
  await answerNavigation(withLinks);
  const before = cardTop();
  const refresh = Array.from(element.querySelectorAll("button")).find((button) => button.textContent === "Refresh")!;
  await act(async () => refresh.dispatchEvent(new MouseEvent("click", { bubbles: true })));
  expect(element.querySelector(NAV)).toBeNull();
  expect(element.querySelector(RESERVED)).not.toBeNull();
  expect(cardTop()).toBe(before);
  await answerNavigation(noLinks); // the week lost its links: nothing is held after the answer
  expect(element.querySelector(RESERVED)).toBeNull();
});

test("a first visit to a week holds nothing", async () => {
  await mount();
  expect(element.querySelector(RESERVED)).toBeNull();
});
