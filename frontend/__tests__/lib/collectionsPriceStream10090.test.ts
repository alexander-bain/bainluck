/**
 * #10090 — a collection's members re-price from the price stream.
 *
 * `CollectionHub` runs `useDiscoverPriceStream` over its members and draws each
 * card from the streamed item with the same price key. The served hub is never
 * rewritten: `pricedCollectionMember` only swaps the item a card draws.
 */
import { pricedCollectionMember, type CollectionMember } from '@/lib/collections';
import type { FeedItem } from '@/lib/types';

const futures = (id: number, p: number) => ({ type: 'futures', data: { id, top_outcomes: [{ id: 1, probability: p }] } }) as unknown as FeedItem;
const event = (id: number) => ({ type: 'event', data: { id } }) as unknown as FeedItem;
const member = (item: FeedItem, key = 'm1'): CollectionMember => ({
  key, id: (item.data as { id: number }).id, type: item.type === 'event' ? 'event' : 'market',
  href: '/x', item, questionIds: [], eventId: null,
});

test('a member draws the streamed item that carries its price key', () => {
  const served = member(futures(57574250, 0.71));
  const fresh = futures(57574250, 0.7);
  const shown = pricedCollectionMember(served, new Map([['futures-57574250', fresh]]));
  expect(shown.item).toBe(fresh);
  expect(shown.key).toBe('m1');
  expect(served.item).not.toBe(fresh); // the served member is never mutated
});

test('a member the stream holds nothing for is returned as is', () => {
  const served = member(futures(1, 0.5));
  expect(pricedCollectionMember(served, new Map([['futures-2', futures(2, 0.4)]]))).toBe(served);
});

test('the same item is not a change, so memoised cards do not re-render', () => {
  const served = member(futures(1, 0.5));
  expect(pricedCollectionMember(served, new Map([['futures-1', served.item]]))).toBe(served);
});

test('an event and a market with the same id never trade prices', () => {
  const game = member(event(42), 'g');
  expect(pricedCollectionMember(game, new Map([['futures-42', futures(42, 0.9)]]))).toBe(game);
  const fresh = event(42);
  expect(pricedCollectionMember(game, new Map([['event-42', fresh]])).item).toBe(fresh);
});
