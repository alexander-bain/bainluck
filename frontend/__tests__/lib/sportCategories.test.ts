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
      expect(getCategoryForFutures(null, 'F1 World Championship')?.key).toBe('motorsport');
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
