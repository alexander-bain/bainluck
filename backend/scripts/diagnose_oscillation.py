"""Diagnose stat_model oscillation in win_prob_snapshots.

For events where stat_model probability swings wildly, inspect the
game_state JSONB to see what scores/clock data was being fed, and
trace which ESPN event was incorrectly matched.

Usage:
    heroku run -a bainluck python3 scripts/diagnose_oscillation.py
"""

import os
import json
import psycopg2
from collections import defaultdict

DATABASE_URL = os.environ.get("DATABASE_URL")
if not DATABASE_URL:
    print("ERROR: DATABASE_URL not set")
    exit(1)

conn = psycopg2.connect(DATABASE_URL)
cur = conn.cursor()

# Step 1: Find events with high stat_model volatility (std dev > 0.25)
print("=" * 70)
print("STEP 1: Finding events with stat_model oscillation")
print("=" * 70)

cur.execute("""
    SELECT
        wp.event_id,
        e.home_team_name,
        e.away_team_name,
        s.key AS sport,
        e.espn_id,
        e.home_score,
        e.away_score,
        e.commence_time,
        COUNT(*) AS snap_count,
        STDDEV(wp.home_win_probability::float) AS std_dev,
        MIN(wp.home_win_probability::float) AS min_prob,
        MAX(wp.home_win_probability::float) AS max_prob
    FROM win_prob_snapshots wp
    JOIN events e ON e.id = wp.event_id
    JOIN sports s ON s.id = e.sport_id
    WHERE wp.source = 'stat_model'
      AND e.status IN ('completed', 'closed')
      AND e.commence_time > NOW() - INTERVAL '3 months'
      AND wp.captured_at >= e.commence_time
    GROUP BY wp.event_id, e.home_team_name, e.away_team_name, s.key,
             e.espn_id, e.home_score, e.away_score, e.commence_time
    HAVING STDDEV(wp.home_win_probability::float) > 0.25
       AND COUNT(*) >= 20
    ORDER BY STDDEV(wp.home_win_probability::float) DESC
    LIMIT 20
""")

oscillating = cur.fetchall()
print(f"\nFound {len(oscillating)} events with stat_model oscillation (stddev > 0.25):\n")

event_ids = []
for row in oscillating:
    eid, home, away, sport, espn_id, h_score, a_score, commence, snaps, std, mn, mx = row
    event_ids.append(eid)
    print(f"  Event {eid}: {away} @ {home} ({sport})")
    print(f"    espn_id={espn_id}  score={h_score}-{a_score}  date={str(commence)[:10]}")
    print(f"    snaps={snaps}  stddev={std:.3f}  range=[{mn:.2f}, {mx:.2f}]")
    print()

if not event_ids:
    print("No oscillating events found.")
    conn.close()
    exit(0)

# Step 2: For each oscillating event, show the game_state progression
print("=" * 70)
print("STEP 2: Inspecting game_state data for score jumping")
print("=" * 70)

for eid in event_ids[:5]:
    cur.execute("""
        SELECT source, captured_at, home_win_probability, game_state
        FROM win_prob_snapshots
        WHERE event_id = %s AND source IN ('stat_model', 'espn')
        ORDER BY captured_at
    """, (eid,))
    rows = cur.fetchall()

    cur.execute("""
        SELECT home_team_name, away_team_name, espn_id, home_score, away_score
        FROM events WHERE id = %s
    """, (eid,))
    ev = cur.fetchone()
    print(f"\n--- Event {eid}: {ev[1]} @ {ev[0]} (espn_id={ev[2]}, final={ev[3]}-{ev[4]}) ---")

    prev_scores = None
    score_jumps = 0
    for src, ts, prob, gs in rows:
        gs = gs or {}
        h_s = gs.get("home_score")
        a_s = gs.get("away_score")
        clock = gs.get("clock")
        period = gs.get("period")
        time_src = gs.get("time_source", "")

        current_scores = (h_s, a_s)
        jumped = ""
        if prev_scores and current_scores != prev_scores and h_s is not None:
            # Check if scores went backwards (impossible in a real game)
            if prev_scores[0] is not None and h_s < prev_scores[0]:
                jumped = " *** SCORE WENT BACKWARDS ***"
                score_jumps += 1
            elif prev_scores[1] is not None and a_s is not None and a_s < prev_scores[1]:
                jumped = " *** SCORE WENT BACKWARDS ***"
                score_jumps += 1
        prev_scores = current_scores

    print(f"  Total snapshots: {len(rows)} ({sum(1 for r in rows if r[0]=='stat_model')} stat_model, {sum(1 for r in rows if r[0]=='espn')} espn)")
    print(f"  Score-backwards jumps: {score_jumps}")

    # Show a sample of score transitions
    print(f"  Score progression (first 15 stat_model readings):")
    stat_rows = [(ts, prob, gs) for src, ts, prob, gs in rows if src == 'stat_model']
    for ts, prob, gs in stat_rows[:15]:
        gs = gs or {}
        print(f"    {str(ts)[11:19]}  prob={prob:.3f}  score={gs.get('home_score')}-{gs.get('away_score')}  clock={gs.get('clock')}  period={gs.get('period')}  src={gs.get('time_source','?')}")

# Step 3: Check if any of these events have ESPN data from wrong games
print("\n" + "=" * 70)
print("STEP 3: Checking for ESPN source contamination")
print("=" * 70)

for eid in event_ids[:5]:
    cur.execute("""
        SELECT home_team_name, away_team_name, commence_time, home_score, away_score
        FROM events WHERE id = %s
    """, (eid,))
    ev = cur.fetchone()

    # Get distinct score pairs from espn snapshots
    cur.execute("""
        SELECT DISTINCT
            (game_state->>'home_score')::int AS h,
            (game_state->>'away_score')::int AS a
        FROM win_prob_snapshots
        WHERE event_id = %s AND source = 'espn'
          AND game_state->>'home_score' IS NOT NULL
        ORDER BY h, a
    """, (eid,))
    espn_scores = cur.fetchall()

    # Get distinct score pairs from stat_model snapshots
    cur.execute("""
        SELECT DISTINCT
            (game_state->>'home_score')::int AS h,
            (game_state->>'away_score')::int AS a
        FROM win_prob_snapshots
        WHERE event_id = %s AND source = 'stat_model'
          AND game_state->>'home_score' IS NOT NULL
        ORDER BY h, a
    """, (eid,))
    model_scores = cur.fetchall()

    print(f"\n  Event {eid}: {ev[1]} @ {ev[0]}")
    print(f"  Final score: {ev[3]}-{ev[4]}")
    print(f"  ESPN snapshot scores: {espn_scores[:10]}")
    print(f"  Model snapshot scores: {model_scores[:10]}")

    # Check if ESPN scores match the final score progression
    if espn_scores:
        max_espn_home = max(s[0] for s in espn_scores if s[0] is not None)
        max_espn_away = max(s[1] for s in espn_scores if s[1] is not None)
        final_h, final_a = ev[3], ev[4]
        if final_h and (max_espn_home > final_h + 5 or max_espn_away > final_a + 5):
            print(f"  *** ESPN scores exceed final by >5: max ESPN=({max_espn_home},{max_espn_away}) vs final=({final_h},{final_a}) — WRONG GAME ***")
        elif max_espn_home < final_h - 20 and max_espn_away < final_a - 20:
            print(f"  *** ESPN scores much lower than final: max ESPN=({max_espn_home},{max_espn_away}) vs final=({final_h},{final_a}) — POSSIBLY WRONG GAME ***")

# Step 4: Summary — are these all espn_id=None events?
print("\n" + "=" * 70)
print("STEP 4: Pattern analysis")
print("=" * 70)

null_espn = sum(1 for row in oscillating if row[4] is None)
has_espn = sum(1 for row in oscillating if row[4] is not None)
print(f"\n  Events with espn_id=None: {null_espn}")
print(f"  Events with espn_id set:  {has_espn}")

sports = defaultdict(int)
for row in oscillating:
    sports[row[3]] += 1
print(f"\n  By sport:")
for sport, count in sorted(sports.items(), key=lambda x: -x[1]):
    print(f"    {sport}: {count}")

# Step 5: Check how many well-covered events SHOULD have espn_id but don't
print("\n" + "=" * 70)
print("STEP 5: Tier 1 events missing espn_id (coverage gaps)")
print("=" * 70)

TIER1_SPORTS = ['basketball_nba', 'icehockey_nhl', 'baseball_mlb',
                'americanfootball_nfl', 'basketball_ncaab']

for sport in TIER1_SPORTS:
    cur.execute("""
        SELECT COUNT(*) FROM events e
        JOIN sports s ON s.id = e.sport_id
        WHERE s.key = %s
          AND e.status IN ('completed', 'closed')
          AND e.commence_time > NOW() - INTERVAL '3 months'
          AND e.home_score IS NOT NULL
    """, (sport,))
    total = cur.fetchone()[0]

    cur.execute("""
        SELECT COUNT(*) FROM events e
        JOIN sports s ON s.id = e.sport_id
        WHERE s.key = %s
          AND e.status IN ('completed', 'closed')
          AND e.commence_time > NOW() - INTERVAL '3 months'
          AND e.home_score IS NOT NULL
          AND e.espn_id IS NULL
    """, (sport,))
    missing = cur.fetchone()[0]

    pct = (missing / total * 100) if total else 0
    flag = " *** INVESTIGATE ***" if pct > 10 else ""
    print(f"  {sport:30s} {missing:>4}/{total:>4} missing espn_id ({pct:.0f}%){flag}")

conn.close()
print("\nDone.")
