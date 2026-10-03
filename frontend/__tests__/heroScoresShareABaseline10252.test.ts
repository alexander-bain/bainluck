// #10252 follow-up — THE TWO HERO SCORES SAT AT DIFFERENT HEIGHTS.
//
// `bainluck.com/events/15322853` (WSH @ CAR, final 5-2), 390px, 2026-10-03:
// Carolina's record "0-0-1, #5 Metropolitan Division, 1 pt" wrapped onto a
// second line and Washington's "0-0, 0 pts" did not. The hero row centred its
// three columns vertically, so the taller Carolina column sat lower: its logo
// and its score of 2 were about 9px below Washington's logo and 5 (measured
// score tops 277 vs 268). The wrapped "Division, 1 pt" also hung left-aligned
// under a centred name.
//
// The fix: the row stretches its columns (`items-stretch`), each score is
// pushed to the foot of its column (`mt-auto`), the centre block keeps its own
// centring (`justify-center`), and the record line is `text-center`. Rendered
// after the fix: both score tops at 273. The server half (dropping the NHL's
// " Division" suffix) is pinned in
// backend/tests/test_nhl_overtime_loss_is_a_played_game_10252.py.
//
// A source scan, like #3427: these are layout classes inside a default-exported
// Next.js page that is too heavy to mount in jsdom, and jsdom does no layout.
import fs from 'node:fs';
import path from 'node:path';

const SRC = fs.readFileSync(
  path.join(__dirname, '..', 'app', 'events', '[id]', 'page.tsx'),
  'utf8',
);

const heroStart = SRC.indexOf('{/* Teams + Score + Giant Probability');
const hero = SRC.slice(heroStart, SRC.indexOf('{event.standings_context?.stakes', heroStart));

describe('#10252 — the hero scores share a baseline when one record wraps', () => {
  it('finds the hero block', () => {
    expect(heroStart).toBeGreaterThan(-1);
    expect(hero.length).toBeGreaterThan(1000);
  });

  it('stretches the three columns instead of centring them', () => {
    const row = hero.match(/<div className="flex (items-\w+) justify-between">/);
    expect(row?.[1]).toBe('items-stretch');
  });

  it('pushes BOTH scores to the foot of their columns', () => {
    for (const side of ['Home', 'Away']) {
      const score = hero.match(
        new RegExp(`<span className="([^"]*)">\\s*\\{best${side}Score\\}`),
      );
      expect(score).not.toBeNull();
      const classes = score![1].split(/\s+/);
      expect(classes).toContain('mt-auto');
      expect(classes).not.toContain('mt-1');
    }
  });

  it('keeps the centre block vertically centred', () => {
    expect(hero).toContain(
      '<div className="flex flex-col items-center justify-center px-1 sm:px-4 min-w-0">',
    );
  });

  it('centres a wrapped record line under its name, on both sides', () => {
    for (const side of ['home', 'away']) {
      const record = hero.match(
        new RegExp(
          `<span className="([^"]*)">\\s*\\{event\\.standings_context\\?\\.${side} \\|\\| event\\.${side}_team_data\\?\\.record\\}`,
        ),
      );
      expect(record).not.toBeNull();
      expect(record![1].split(/\s+/)).toContain('text-center');
    }
  });
});
