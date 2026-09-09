/**
 * Tests for sportCategories utility functions.
 *
 * Covers:
 * - getCategoryForLeague (prefix matching)
 * - getCategoryForFutures (multi-stage categorization)
 * - getLeagueTier
 * - getLeagueDisplay
 * - getLeagueDisplayWithEmoji
 * - getEmojiForLeague
 * - getCategoryName
 * - groupLeaguesByCategory
 * - getActiveCategoriesFromLeagues
 * - calculateExcitementScore
 * - formatTimeUntil
 */

import { readFileSync } from 'fs';
import { join } from 'path';
import {
  getCategoryForLeague,
  getCategoryForFutures,
  getLeagueTier,
  getLeagueDisplay,
  getLeagueDisplayWithEmoji,
  getEmojiForLeague,
  getCategoryName,
  getNameForCategory,
  groupLeaguesByCategory,
  getActiveCategoriesFromLeagues,
  calculateExcitementScore,
  formatTimeUntil,
  getFeatureReason,
  isFeaturedEvent,
  SPORT_CATEGORIES,
} from '@/lib/sportCategories';

// =============================================================================
// getCategoryForLeague
// =============================================================================
describe('getCategoryForLeague', () => {
  test('matches football prefix', () => {
    const cat = getCategoryForLeague('americanfootball_nfl');
    expect(cat?.key).toBe('football');
  });

  test('matches basketball prefix', () => {
    const cat = getCategoryForLeague('basketball_nba');
    expect(cat?.key).toBe('basketball');
  });

  test('matches baseball prefix', () => {
    const cat = getCategoryForLeague('baseball_mlb');
    expect(cat?.key).toBe('baseball');
  });

  test('matches hockey prefix', () => {
    const cat = getCategoryForLeague('icehockey_nhl');
    expect(cat?.key).toBe('hockey');
  });

  test('matches mma prefix', () => {
    const cat = getCategoryForLeague('mma_ufc');
    expect(cat?.key).toBe('mma');
  });

  test('matches boxing prefix', () => {
    const cat = getCategoryForLeague('boxing_boxing');
    expect(cat?.key).toBe('boxing');
  });

  test('matches golf prefix', () => {
    const cat = getCategoryForLeague('golf_pga_tour');
    expect(cat?.key).toBe('golf');
  });

  test('matches tennis prefix', () => {
    const cat = getCategoryForLeague('tennis_atp_us_open');
    expect(cat?.key).toBe('tennis');
  });

  test('matches soccer prefix', () => {
    const cat = getCategoryForLeague('soccer_epl');
    expect(cat?.key).toBe('soccer');
  });

  test('matches rugby league prefix', () => {
    const cat = getCategoryForLeague('rugbyleague_nrl');
    expect(cat?.key).toBe('rugby');
  });

  test('matches rugby union prefix', () => {
    const cat = getCategoryForLeague('rugbyunion_six_nations');
    expect(cat?.key).toBe('rugby');
  });

  test('matches aussie rules prefix', () => {
    const cat = getCategoryForLeague('aussierules_afl');
    expect(cat?.key).toBe('aussierules');
  });

  test('matches cricket prefix', () => {
    const cat = getCategoryForLeague('cricket_ipl');
    expect(cat?.key).toBe('cricket');
  });

  test('matches politics prefix', () => {
    const cat = getCategoryForLeague('politics_us_election');
    expect(cat?.key).toBe('politics');
  });

  test('matches esports prefix', () => {
    const cat = getCategoryForLeague('esports_lol');
    expect(cat?.key).toBe('esports');
  });

  test('returns undefined for unknown prefix', () => {
    expect(getCategoryForLeague('unknown_sport')).toBeUndefined();
  });

  test('returns undefined for empty string', () => {
    expect(getCategoryForLeague('')).toBeUndefined();
  });
});

// =============================================================================
// getCategoryForFutures
// =============================================================================
describe('getCategoryForFutures', () => {
  describe('LLM category (first priority)', () => {
    test('uses LLM category when available', () => {
      const cat = getCategoryForFutures(null, 'Some Market', [], 'basketball');
      expect(cat?.key).toBe('basketball');
    });

    test('ignores invalid LLM category', () => {
      const cat = getCategoryForFutures(null, 'NBA Championship', [], 'invalid_category');
      // Falls through to pattern matching
      expect(cat?.key).toBe('basketball');
    });
  });

  describe('prefix matching (second priority)', () => {
    test('matches sport key prefix', () => {
      const cat = getCategoryForFutures('americanfootball_nfl_super_bowl', null);
      expect(cat?.key).toBe('football');
    });
  });

  describe('regex pattern matching (third priority)', () => {
    test('MLB', () => {
      expect(getCategoryForFutures(null, 'MLB World Series Winner')?.key).toBe('baseball');
    });

    test('NFL', () => {
      expect(getCategoryForFutures(null, 'NFL MVP Winner')?.key).toBe('football');
    });

    test('Super Bowl', () => {
      expect(getCategoryForFutures(null, 'Super Bowl LX')?.key).toBe('football');
    });

    test('NBA', () => {
      expect(getCategoryForFutures(null, 'NBA Championship')?.key).toBe('basketball');
    });

    test('March Madness', () => {
      expect(getCategoryForFutures(null, 'March Madness Winner')?.key).toBe('basketball');
    });

    test('Stanley Cup', () => {
      expect(getCategoryForFutures(null, 'Stanley Cup Winner')?.key).toBe('hockey');
    });

    test('Hart Trophy', () => {
      expect(getCategoryForFutures(null, 'Hart Trophy Winner')?.key).toBe('hockey');
    });

    test('PGA Championship', () => {
      expect(getCategoryForFutures(null, 'PGA Championship Winner')?.key).toBe('golf');
    });

    test('Masters', () => {
      expect(getCategoryForFutures(null, '2026 Masters Tournament')?.key).toBe('golf');
    });

    test('Wimbledon', () => {
      expect(getCategoryForFutures(null, 'Wimbledon Winner')?.key).toBe('tennis');
    });

    test('Premier League', () => {
      expect(getCategoryForFutures(null, 'Premier League Winner')?.key).toBe('soccer');
    });

    test('Champions League', () => {
      expect(getCategoryForFutures(null, 'Champions League Winner')?.key).toBe('soccer');
    });

    test('UFC', () => {
      expect(getCategoryForFutures(null, 'UFC Heavyweight Champion')?.key).toBe('mma');
    });

    test('F1', () => {
      // Plural since #2627 — a category key is matched against
      // `llm_sport_category`, which stores `motorsports`.
      expect(getCategoryForFutures(null, 'F1 World Championship')?.key).toBe('motorsports');
    });

    test('Kentucky Derby', () => {
      expect(getCategoryForFutures(null, 'Kentucky Derby Winner')?.key).toBe('horse_racing');
    });

    test('Oscar', () => {
      expect(getCategoryForFutures(null, 'Oscar Best Picture')?.key).toBe('entertainment');
    });

    test('Presidential Election', () => {
      expect(getCategoryForFutures(null, 'Presidential Election Winner')?.key).toBe('politics');
    });

    test('Heisman Trophy', () => {
      expect(getCategoryForFutures(null, 'Heisman Trophy Winner')?.key).toBe('football');
    });

    test('College Football Playoff', () => {
      expect(getCategoryForFutures(null, 'College Football Playoff')?.key).toBe('football');
    });

    test('World Cup', () => {
      expect(getCategoryForFutures(null, 'World Cup Winner')?.key).toBe('soccer');
    });

    test('Ballon d\'Or', () => {
      expect(getCategoryForFutures(null, 'Ballon d\'Or Winner')?.key).toBe('soccer');
    });

    test('AL MVP (baseball)', () => {
      expect(getCategoryForFutures(null, 'AL MVP Award Winner')?.key).toBe('baseball');
    });

    test('Cy Young', () => {
      expect(getCategoryForFutures(null, 'Cy Young Award Winner')?.key).toBe('baseball');
    });

    test('Vezina Trophy', () => {
      expect(getCategoryForFutures(null, 'Vezina Trophy Winner')?.key).toBe('hockey');
    });
  });

  describe('athlete name detection (for ambiguous markets)', () => {
    test('golfer name → golf', () => {
      const cat = getCategoryForFutures(null, 'US Open Winner', ['Scottie Scheffler', 'Rory McIlroy']);
      expect(cat?.key).toBe('golf');
    });

    test('tennis player name → tennis', () => {
      // Note: avoid "Djokovic" as it contains "ko" matching golfer Lydia Ko
      const cat = getCategoryForFutures(null, 'US Open Winner', ['Taylor Fritz', 'Jannik Sinner']);
      expect(cat?.key).toBe('tennis');
    });

    test('golfer last name match → golf', () => {
      const cat = getCategoryForFutures(null, 'Open Winner', ['Scheffler', 'McIlroy']);
      expect(cat?.key).toBe('golf');
    });
  });

  describe('no match', () => {
    test('returns undefined for unknown market', () => {
      expect(getCategoryForFutures(null, 'Completely Unknown Thing')).toBeUndefined();
    });
  });
});

// =============================================================================
// getLeagueTier
// =============================================================================
describe('getLeagueTier', () => {
  test('tier 1 leagues', () => {
    expect(getLeagueTier('americanfootball_nfl')).toBe(1);
    expect(getLeagueTier('basketball_nba')).toBe(1);
    expect(getLeagueTier('baseball_mlb')).toBe(1);
    expect(getLeagueTier('icehockey_nhl')).toBe(1);
  });

  test('tier 2 leagues', () => {
    expect(getLeagueTier('americanfootball_ncaaf')).toBe(2);
    expect(getLeagueTier('basketball_ncaab')).toBe(2);
    expect(getLeagueTier('basketball_wnba')).toBe(2);
    expect(getLeagueTier('mma_ufc')).toBe(2);
  });

  test('unknown leagues default to tier 3', () => {
    expect(getLeagueTier('unknown_league')).toBe(3);
  });
});

// =============================================================================
// getLeagueDisplay
// =============================================================================
describe('getLeagueDisplay', () => {
  test('known leagues return display name', () => {
    expect(getLeagueDisplay('americanfootball_nfl')).toBe('NFL');
    expect(getLeagueDisplay('basketball_nba')).toBe('NBA');
    expect(getLeagueDisplay('baseball_mlb')).toBe('MLB');
    expect(getLeagueDisplay('icehockey_nhl')).toBe('NHL');
  });

  test('unknown leagues generate display from key', () => {
    const display = getLeagueDisplay('basketball_nba_playoffs');
    // Should strip first part and uppercase the rest
    expect(display).toBe('NBA PLAYOFFS');
  });

  test('single-part key uppercases', () => {
    expect(getLeagueDisplay('unknown')).toBe('UNKNOWN');
  });

  /**
   * #4247 — A CATCH-ALL BUCKET NAMES ITS FAMILY OR IT IS NOT A WORD.
   *
   * Production served `mma_other (24)` as a filter chip on
   * /search?q=Whittaker beside a correctly-labelled `🥊 Boxing (1)`.
   *
   * TWO defects, one visible and one behind it:
   *   1. The chip rendered the SERVED `sport.name`, and 15 rows in the `sports`
   *      table store the raw key in that column (census below).
   *   2. `getLeagueDisplay` — the map the chip should have used — answered
   *      "OTHER" for all fourteen `*_other` keys and "ESPORTS" for the bare one.
   *      So routing the chip through the map alone would have traded a key for
   *      a word that still names no sport.
   *
   * Asserting only "the label is not lowercase" is what the issue's own
   * verification line asked for and it is too weak to fail: "OTHER" passes it.
   * Every key below is therefore pinned to the exact string it must print.
   */
  describe('#4247 catch-all buckets name their family', () => {
    /**
     * Measured: `SELECT key, name FROM sports` where the name is the key,
     * production, 2026-09-09, 15 rows, truncated:false. Event counts are from
     * the same read. THIS LIST IS A SNAPSHOT — if a new bucket appears in the
     * table after ~2026-12 it will not be in here, and nothing below will
     * notice. Re-run the census, do not trust the list's age.
     */
    const PRODUCTION_BUCKETS: Array<[string, string]> = [
      ['americanfootball_other', 'Other Football'],
      ['baseball_other', 'Other Baseball'],
      ['basketball_other', 'Other Basketball'],
      ['boxing_other', 'Other Boxing'],
      ['cricket_other', 'Other Cricket'],
      ['esports', 'Esports'],
      ['esports_other', 'Other Esports'],
      ['golf_other', 'Other Golf'],
      ['icehockey_other', 'Other Hockey'],
      ['lacrosse_other', 'Other Lacrosse'],
      ['mma_other', 'Other MMA'],
      ['motorsport_other', 'Other Motorsport'],
      ['rugby_other', 'Other Rugby'],
      ['soccer_other', 'Other Soccer'],
      ['tennis_other', 'Other Tennis'],
    ];

    test.each(PRODUCTION_BUCKETS)('%s renders as "%s"', (key, expected) => {
      expect(getLeagueDisplay(key)).toBe(expected);
    });

    test('no bucket renders as a raw key or as the bare word OTHER', () => {
      for (const [key] of PRODUCTION_BUCKETS) {
        const display = getLeagueDisplay(key);
        expect(display).not.toBe(key);
        expect(display).not.toContain('_');
        expect(display).not.toMatch(/^[a-z_]+$/); // the issue's own line
        expect(display).not.toBe('OTHER'); // what the map answered before
      }
    });

    /**
     * The reason the label is "Other MMA" and not the "MMA" the issue asked
     * for. Both keys in each pair are populated in production (mma 1,704 vs
     * 375; boxing 888 vs 57; esports 89,588 vs 777), so the family word alone
     * would draw two identical chips that filter to different result sets —
     * worse for a reader than the raw key, which at least distinguished them.
     */
    test('a bucket never collides with its own named sibling', () => {
      const pairs: Array<[string, string]> = [
        ['mma_mixed_martial_arts', 'mma_other'],
        ['boxing_boxing', 'boxing_other'],
        ['esports', 'esports_other'],
      ];
      for (const [named, bucket] of pairs) {
        // Survival first: both sides must actually resolve to something.
        expect(getLeagueDisplay(named)).toBeTruthy();
        expect(getLeagueDisplay(bucket)).toBeTruthy();
        expect(getLeagueDisplay(bucket)).not.toBe(getLeagueDisplay(named));
      }
    });

    /**
     * `rugby_other` is the one bucket whose family was unreachable: the rugby
     * category listed only "rugbyleague_"/"rugbyunion_", so the key matched no
     * category and lost its emoji as well as its word.
     */
    test('rugby_other reaches the rugby category, emoji included', () => {
      expect(getCategoryForLeague('rugby_other')?.key).toBe('rugby');
      expect(getEmojiForLeague('rugby_other')).toBe('🏉');
      expect(getEmojiForLeague('rugby_other')).not.toBe('🏆'); // the fallback
      // The added prefix must not have stolen the two it sits beside.
      expect(getCategoryForLeague('rugbyleague_nrl')?.key).toBe('rugby');
      expect(getCategoryForLeague('rugbyunion_six_nations')?.key).toBe('rugby');
    });

    /**
     * Anchored on the code, because the chip is inside a `useSearchParams`
     * client page that `renderToStaticMarkup` cannot mount. `sport.name` now
     * appears nowhere in the file, so this is unambiguous.
     */
    test('the search chip reads the label map, not the served name', () => {
      const src = readFileSync(
        join(__dirname, '..', '..', 'app', 'search', 'page.tsx'),
        'utf8'
      );
      expect(src).toContain('getLeagueDisplay(sport.key)'); // survival
      expect(src).not.toContain('{sport.name}');
    });
  });
});

// =============================================================================
// getLeagueDisplayWithEmoji
// =============================================================================
describe('getLeagueDisplayWithEmoji', () => {
  test('known category includes emoji', () => {
    const display = getLeagueDisplayWithEmoji('basketball_nba');
    expect(display).toContain('NBA');
    expect(display).toContain('🏀');
  });

  test('unknown category uses trophy emoji', () => {
    const display = getLeagueDisplayWithEmoji('unknown_sport');
    expect(display).toContain('🏆');
  });
});

// =============================================================================
// getEmojiForLeague
// =============================================================================
describe('getEmojiForLeague', () => {
  test('football emoji', () => {
    expect(getEmojiForLeague('americanfootball_nfl')).toBe('🏈');
  });

  test('basketball emoji', () => {
    expect(getEmojiForLeague('basketball_nba')).toBe('🏀');
  });

  test('unknown returns trophy', () => {
    expect(getEmojiForLeague('unknown')).toBe('🏆');
  });
});

// =============================================================================
// getCategoryName
// =============================================================================
describe('getCategoryName', () => {
  test('known categories', () => {
    expect(getCategoryName('americanfootball_nfl')).toBe('Football');
    expect(getCategoryName('basketball_nba')).toBe('Basketball');
    expect(getCategoryName('baseball_mlb')).toBe('Baseball');
  });

  test('unknown returns Other', () => {
    expect(getCategoryName('unknown_sport')).toBe('Other');
  });
});

// =============================================================================
// getNameForCategory — L2-183: the unknown-key fallback must be acronym-safe
// (was first-char-only, which produced "Pga tour" / "Wnba draft").
// =============================================================================
describe('getNameForCategory', () => {
  test('acronym-safe fallback for unknown keys', () => {
    expect(getNameForCategory('wnba_draft')).toBe('WNBA Draft');
    expect(getNameForCategory('cpi_release')).toBe('CPI Release');
  });

  test('ordinary unknown keys still title-case', () => {
    expect(getNameForCategory('horse_racing')).toBe('Horse Racing');
  });
});

// =============================================================================
// groupLeaguesByCategory
// =============================================================================
describe('groupLeaguesByCategory', () => {
  test('groups leagues correctly', () => {
    const groups = groupLeaguesByCategory([
      'americanfootball_nfl',
      'americanfootball_ncaaf',
      'basketball_nba',
      'unknown_league',
    ]);

    expect(groups.get('football')).toContain('americanfootball_nfl');
    expect(groups.get('football')).toContain('americanfootball_ncaaf');
    expect(groups.get('basketball')).toContain('basketball_nba');
    expect(groups.get('other')).toContain('unknown_league');
  });

  test('empty input returns empty map', () => {
    const groups = groupLeaguesByCategory([]);
    expect(groups.size).toBe(0);
  });
});

// =============================================================================
// getActiveCategoriesFromLeagues
// =============================================================================
describe('getActiveCategoriesFromLeagues', () => {
  test('returns active categories', () => {
    const categories = getActiveCategoriesFromLeagues([
      'americanfootball_nfl',
      'basketball_nba',
    ]);

    const keys = categories.map(c => c.key);
    expect(keys).toContain('football');
    expect(keys).toContain('basketball');
  });

  test('includes "other" for unknown leagues', () => {
    const categories = getActiveCategoriesFromLeagues([
      'americanfootball_nfl',
      'unknown_league',
    ]);

    const keys = categories.map(c => c.key);
    expect(keys).toContain('other');
  });

  test('empty input returns empty array', () => {
    expect(getActiveCategoriesFromLeagues([])).toEqual([]);
  });
});

// =============================================================================
// calculateExcitementScore
// =============================================================================
describe('calculateExcitementScore', () => {
  test('live game gets 50+ points', () => {
    const score = calculateExcitementScore({
      status: 'live',
      commence_time: new Date(Date.now() - 3600000).toISOString(),
      sport: 'basketball_nba',
    });
    expect(score).toBeGreaterThanOrEqual(50);
  });

  test('close live game scores higher', () => {
    const score = calculateExcitementScore({
      status: 'live',
      commence_time: new Date(Date.now() - 3600000).toISOString(),
      sport: 'basketball_nba',
      current_odds: { home_probability: 0.50 },
    });
    expect(score).toBeGreaterThan(70);
  });

  test('blowout live game scores lower', () => {
    const blowout = calculateExcitementScore({
      status: 'live',
      commence_time: new Date(Date.now() - 3600000).toISOString(),
      sport: 'basketball_nba',
      current_odds: { home_probability: 0.95 },
    });
    const close = calculateExcitementScore({
      status: 'live',
      commence_time: new Date(Date.now() - 3600000).toISOString(),
      sport: 'basketball_nba',
      current_odds: { home_probability: 0.50 },
    });
    expect(blowout).toBeLessThan(close);
  });

  test('tier 1 league gets boost', () => {
    const tier1 = calculateExcitementScore({
      status: 'scheduled',
      commence_time: new Date(Date.now() + 7200000).toISOString(),
      sport: 'basketball_nba',
    });
    const tier3 = calculateExcitementScore({
      status: 'scheduled',
      commence_time: new Date(Date.now() + 7200000).toISOString(),
      sport: 'cricket_ipl',
    });
    expect(tier1).toBeGreaterThan(tier3);
  });

  test('score capped at 100', () => {
    const score = calculateExcitementScore({
      status: 'live',
      commence_time: new Date(Date.now() - 3600000).toISOString(),
      sport: 'basketball_nba',
      current_odds: { home_probability: 0.50 },
    });
    expect(score).toBeLessThanOrEqual(100);
  });

  test('completed game has low score', () => {
    const score = calculateExcitementScore({
      status: 'completed',
      commence_time: new Date(Date.now() - 86400000).toISOString(),
      sport: 'basketball_nba',
    });
    expect(score).toBeLessThan(50);
  });
});

// =============================================================================
// formatTimeUntil
// =============================================================================
describe('formatTimeUntil', () => {
  test('past time returns "Started"', () => {
    const past = new Date(Date.now() - 3600000).toISOString();
    expect(formatTimeUntil(past)).toBe('Started');
  });

  test('less than 60 minutes shows minutes', () => {
    const future = new Date(Date.now() + 30 * 60 * 1000).toISOString();
    const result = formatTimeUntil(future);
    expect(result).toMatch(/^\d+m$/);
  });

  test('1-3 hours shows hours and minutes', () => {
    const future = new Date(Date.now() + 90 * 60 * 1000).toISOString();
    const result = formatTimeUntil(future);
    expect(result).toMatch(/^\d+h(\s\d+m)?$/);
  });

  test('more than 3 hours shows just hours', () => {
    const future = new Date(Date.now() + 5 * 3600 * 1000).toISOString();
    const result = formatTimeUntil(future);
    expect(result).toMatch(/^\d+h$/);
  });
});

// =============================================================================
// getFeatureReason & isFeaturedEvent
// =============================================================================
describe('getFeatureReason', () => {
  test('live game returns "live"', () => {
    expect(getFeatureReason({
      status: 'live',
      commence_time: new Date(Date.now() - 3600000).toISOString(),
    })).toBe('live');
  });

  test('completed game returns null', () => {
    expect(getFeatureReason({
      status: 'completed',
      commence_time: new Date(Date.now() - 86400000).toISOString(),
    })).toBeNull();
  });

  test('close game starting soon returns "close_game"', () => {
    expect(getFeatureReason({
      status: 'scheduled',
      commence_time: new Date(Date.now() + 3600000).toISOString(),
      current_odds: { home_probability: 0.50 },
    })).toBe('close_game');
  });

  test('game starting very soon returns "starting_soon"', () => {
    expect(getFeatureReason({
      status: 'scheduled',
      commence_time: new Date(Date.now() + 30 * 60 * 1000).toISOString(),
      current_odds: { home_probability: 0.80 },
    })).toBe('starting_soon');
  });
});

describe('isFeaturedEvent', () => {
  test('live game is featured', () => {
    expect(isFeaturedEvent({
      status: 'live',
      commence_time: new Date(Date.now() - 3600000).toISOString(),
    })).toBe(true);
  });

  test('far future game is not featured', () => {
    expect(isFeaturedEvent({
      status: 'scheduled',
      commence_time: new Date(Date.now() + 48 * 3600 * 1000).toISOString(),
      current_odds: { home_probability: 0.80 },
    })).toBe(false);
  });
});

// =============================================================================
// SPORT_CATEGORIES structure
// =============================================================================
describe('SPORT_CATEGORIES', () => {
  test('all categories have required fields', () => {
    for (const cat of SPORT_CATEGORIES) {
      expect(cat.key).toBeTruthy();
      expect(cat.name).toBeTruthy();
      expect(cat.emoji).toBeTruthy();
      expect(Array.isArray(cat.prefixes)).toBe(true);
      expect([1, 2, 3]).toContain(cat.tier);
    }
  });

  test('no duplicate category keys', () => {
    const keys = SPORT_CATEGORIES.map(c => c.key);
    expect(new Set(keys).size).toBe(keys.length);
  });

  test('no overlapping prefixes', () => {
    const allPrefixes = SPORT_CATEGORIES.flatMap(c => c.prefixes);
    expect(new Set(allPrefixes).size).toBe(allPrefixes.length);
  });
});
