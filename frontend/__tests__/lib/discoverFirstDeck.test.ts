import type { FeedItem } from "@/lib/types";
import { FIRST_DECK_KEY, FIRST_DECK_TTL_MS, firstDeckOwner, parseFirstDeck, readFirstDeck, writeFirstDeck } from "@/lib/discover/firstDeck";

const storage = () => {
  const values = new Map<string, string>();
  return { getItem: (key: string) => values.get(key) ?? null, setItem: (key: string, value: string) => values.set(key, value), removeItem: (key: string) => values.delete(key) };
};
const cards = (start: number, count = 2) => Array.from({ length: count }, (_, i) => ({ type: "futures", data: { id: start + i } } as FeedItem));
const now = 1_000_000;
let local: ReturnType<typeof storage>, session: ReturnType<typeof storage>;
beforeEach(() => {
  local = storage(); session = storage();
  Object.defineProperty(globalThis, "window", { value: { localStorage: local, sessionStorage: session }, configurable: true });
  jest.spyOn(Date, "now").mockReturnValue(now);
});
afterEach(() => { jest.restoreAllMocks(); Reflect.deleteProperty(globalThis, "window"); });

it("a reload can read a recent same-reader first deck before the network returns, without renewing its age", () => {
  writeFirstDeck({ items: cards(1), hasMore: true }, "user:alex");
  const raw = session.getItem(FIRST_DECK_KEY);
  expect(readFirstDeck("user:alex")?.items).toEqual(cards(1));
  expect(session.getItem(FIRST_DECK_KEY)).toBe(raw);
  expect(parseFirstDeck(raw, "user:alex", now + FIRST_DECK_TTL_MS + 1)).toBeNull();
  expect(parseFirstDeck(raw, "user:alex", now - 1)).toBeNull();
});
it("refuses another account/session, unknown identity, malformed or accidentally corrupted cards", () => {
  writeFirstDeck({ items: cards(1), hasMore: true }, "anonymous:one");
  const raw = session.getItem(FIRST_DECK_KEY)!;
  expect(parseFirstDeck(raw, "anonymous:two", now)).toBeNull();
  expect(parseFirstDeck(raw, "user:alex", now)).toBeNull();
  expect(parseFirstDeck(raw, null, now)).toBeNull();
  expect(parseFirstDeck("{", "anonymous:one", now)).toBeNull();
  const changed = JSON.parse(raw); changed.body = changed.body.replace('"id":1', '"id":999');
  expect(parseFirstDeck(JSON.stringify(changed), "anonymous:one", now)).toBeNull();
});
it("a current response replaces the saved deck wholesale and an accepted empty page clears it", () => {
  writeFirstDeck({ items: cards(1, 40), hasMore: true }, "user:alex");
  expect(readFirstDeck("user:alex")?.items).toHaveLength(20);
  writeFirstDeck({ items: cards(101), hasMore: false }, "user:alex");
  expect(readFirstDeck("user:alex")).toEqual({ items: cards(101), hasMore: false });
  writeFirstDeck({ items: [], hasMore: false }, "user:alex");
  expect(readFirstDeck("user:alex")).toBeNull();
});
it("uses persisted same-user identity while auth restores, and current auth wins after sign-out", () => {
  local.setItem("bainluck_session_id", "one");
  local.setItem("bainluck_previouslySignedIn", "true");
  expect(firstDeckOwner(null, true)).toBeNull();
  local.setItem("bainluck_backendAuth", JSON.stringify({ uid: "alex", expiresAt: now + 600_000 }));
  expect(firstDeckOwner(null, true)).toBe("user:alex");
  expect(firstDeckOwner("another", false)).toBe("user:another");
  expect(firstDeckOwner(null, false)).toBe("anonymous:one");
});
it("unavailable browser storage safely falls back to the ordinary feed", () => {
  Object.defineProperty(globalThis, "window", { value: { get localStorage() { throw new Error("blocked"); }, get sessionStorage() { throw new Error("blocked"); } }, configurable: true });
  expect(firstDeckOwner(null, true)).toBeNull();
  expect(readFirstDeck("user:alex")).toBeNull();
  expect(() => writeFirstDeck({ items: cards(1), hasMore: true }, "user:alex")).not.toThrow();
});
