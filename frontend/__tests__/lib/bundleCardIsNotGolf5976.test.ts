/**
 * #5976 — a theme bundle is not a golf tournament.
 *
 * WHY THIS FILE EXISTS. `getDiscoverItemAnalytics` branched on `event` /
 * `futures` / `concept` and then fell through to the TOURNAMENT shape for
 * everything else. A bundle carries `data.id` / `data.title`, never
 * `data.key` / `data.name`, so every theme bundle took that fall-through and
 * described itself as:
 *
 *   item_id  : `String(undefined)` — the literal seven-letter text "undefined"
 *   item_name: undefined (stored NULL)
 *   category : "golf", hardcoded in that branch
 *
 * Measured on production 2026-09-13: 1,360 rows with `item_id = 'undefined'`,
 * 526 distinct sessions, category `golf` on every single one, first row
 * 2026-06-11. One shape only.
 *
 * The reader-visible half is `applyLocalPersonalization`, which reads this
 * category through `getGroupedAnalytics` and adds
 * `getDiscoverCategoryAdjustment` — `clamp(bucket.score, -8, 12)` — to the
 * card's score inside each 5-card window. So "Awards Season" moved up or down
 * Discover according to how the reader felt about GOLF.
 *
 * The sibling rail `getItemCategory` (app/discover/page.tsx) already grew this
 * branch in #934 and its comment names the same fall-through; that fixed the
 * category-COOLDOWN half and left the ANALYTICS half behind. This file pins the
 * half that was left.
 *
 * `testEnvironment` is "node" here and this function is pure, so there is no
 * window/localStorage harness — the module is imported directly.
 */

export {}; // ensure module scope

import { getDiscoverItemAnalytics } from '@/lib/discoverInteractions';
import type { FeedItem } from '@/lib/types';

/**
 * The exact byte string that sat in 1,360 production rows. Written as a literal
 * rather than as `String(undefined)` so the assertion still means something if
 * someone ever changes how the id is coerced.
 */
const THE_DEFECT = 'undefined';

/** A futures member, the shape `assemble_*_theme_bundles` nests. */
function futuresMember(overrides: Record<string, unknown> = {}): FeedItem {
  return {
    type: 'futures',
    score: 71,
    data: {
      id: 6173044,
      name: 'Best Picture 2027',
      llm_sport_category: 'entertainment',
      top_outcomes: [],
      ...overrides,
    },
  } as unknown as FeedItem;
}

/**
 * Alex's own specimen, off the live payload of 2026-09-13: the "Awards Season"
 * theme bundle, `kind: "theme"`, two entertainment futures folded into it.
 */
function awardsSeasonBundle(dataOverrides: Record<string, unknown> = {}): FeedItem {
  return {
    type: 'bundle',
    score: 78,
    headline: 'Awards Season',
    data: {
      id: 'theme:story:major_entertainment_events:6173044-52755801',
      title: 'Awards Season',
      kind: 'theme',
      story_key: 'major_entertainment_events',
      item_count: 2,
      member_ids: [6173044, 52755801],
      items: [futuresMember(), futuresMember({ id: 52755801, name: 'Best Director 2027' })],
      ...dataOverrides,
    },
  } as unknown as FeedItem;
}

describe('#5976 a theme bundle describes itself, not a golf tournament', () => {
  it('reports the bundle id, never the literal text "undefined"', () => {
    const analytics = getDiscoverItemAnalytics(awardsSeasonBundle());

    expect(analytics.item_id).toBe('theme:story:major_entertainment_events:6173044-52755801');
    // The rail coerces with `String(...)` before it sends, so assert on the
    // coerced value too — that is the shape the 1,360 rows actually carried.
    expect(String(analytics.item_id)).not.toBe(THE_DEFECT);
  });

  it('reports the bundle title, not a null name', () => {
    expect(getDiscoverItemAnalytics(awardsSeasonBundle()).item_name).toBe('Awards Season');
  });

  it('reports the first member\'s category, not "golf"', () => {
    const analytics = getDiscoverItemAnalytics(awardsSeasonBundle());

    expect(analytics.category).toBe('entertainment');
    expect(analytics.category).not.toBe('golf');
  });

  it('takes the category from the member rather than re-deriving the vocabulary', () => {
    // An event member is keyed on the sport-key ROOT, a futures member on
    // `llm_sport_category`. Reading the member through the same function is
    // what keeps those two rules in one place; a hand-rolled copy in the bundle
    // branch would be a second place for them to drift.
    const withEventMember = awardsSeasonBundle({
      items: [
        {
          type: 'event',
          score: 64,
          data: {
            id: 901,
            sport: 'americanfootball_nfl',
            away_team: 'Jets',
            home_team: 'Bills',
          },
        } as unknown as FeedItem,
      ],
    });

    expect(getDiscoverItemAnalytics(withEventMember).category).toBe('americanfootball');
  });

  it('falls back to "other" — still not golf — when the bundle has no members', () => {
    const empty = getDiscoverItemAnalytics(awardsSeasonBundle({ items: [] }));

    expect(empty.category).toBe('other');
    // The id is the bundle's own even with nothing to read a category from:
    // the two are independent, and the id was the half that broke the row.
    expect(empty.item_id).toBe('theme:story:major_entertainment_events:6173044-52755801');
  });

  it('bounds the member read to one level when a member is itself a bundle', () => {
    // Cannot happen in today's payload. It is asserted because the alternative
    // to the bound is unbounded recursion inside an IntersectionObserver
    // callback, which is a hang rather than a wrong number.
    const nested = awardsSeasonBundle({ items: [awardsSeasonBundle()] });

    expect(getDiscoverItemAnalytics(nested).category).toBe('other');
  });

  it('keeps content_type "grid", so the existing series is not re-keyed', () => {
    // Deliberate: the backend learned the word `bundle` in #5951 but decides a
    // row id from a key by PARSING the id, so the label buys nothing here and
    // changing it would split every existing `grid` series in two.
    expect(getDiscoverItemAnalytics(awardsSeasonBundle()).content_type).toBe('grid');
  });
});

describe('#5976 the cards the fall-through was written for are untouched', () => {
  it('a tournament still reports its key, its name and golf', () => {
    const tournament = {
      type: 'tournament',
      score: 55,
      data: { key: 'amgen_irish_open', name: 'Amgen Irish Open' },
    } as unknown as FeedItem;

    const analytics = getDiscoverItemAnalytics(tournament);

    expect(analytics.item_id).toBe('amgen_irish_open');
    expect(analytics.item_name).toBe('Amgen Irish Open');
    expect(analytics.category).toBe('golf');
  });

  it('a concept still reports its key and its mapped domain', () => {
    const concept = {
      type: 'concept',
      score: 60,
      data: { key: 'event:f1:spanish-grand-prix-winner', name: 'Spanish GP winner', domain: 'f1' },
    } as unknown as FeedItem;

    const analytics = getDiscoverItemAnalytics(concept);

    expect(analytics.item_id).toBe('event:f1:spanish-grand-prix-winner');
    expect(analytics.category).toBe('motorsports');
  });

  it('an event and a futures card still report their row ids', () => {
    const event = {
      type: 'event',
      score: 80,
      data: { id: 4242, sport: 'baseball_mlb', away_team: 'Yankees', home_team: 'Red Sox' },
    } as unknown as FeedItem;

    expect(getDiscoverItemAnalytics(event).item_id).toBe(4242);
    expect(getDiscoverItemAnalytics(event).category).toBe('baseball');
    expect(getDiscoverItemAnalytics(futuresMember()).item_id).toBe(6173044);
    expect(getDiscoverItemAnalytics(futuresMember()).category).toBe('entertainment');
  });
});
