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
  path.join(__dirname, '..', 'components', 'event', 'EventPageHeadline199.tsx'),
  'utf8',
);

describe('#10252 — competitor rows in EventPageHeadline199 align each row independently so records never shift scores', () => {
  it('renders each competitor on its own items-center justify-between row', () => {
    expect(SRC).toContain('data-testid={`headline-12472-${row.role}-row`}');
    expect(SRC).toContain('className="flex items-center justify-between gap-2 min-w-0 max-[359px]:flex-wrap"');
  });

  it('aligns all numeric cells on a shared baseline per row', () => {
    expect(SRC).toContain('className="flex items-baseline shrink-0 max-[359px]:ml-auto"');
  });

  it('stacks the optional record cleanly inside the left name column', () => {
    expect(SRC).toContain('{row.record ? (');
    expect(SRC).toContain('{row.record}');
  });
});
