# ARTIFACT-AUTHORITY-001 — NFL: StatPal vs production, first dark read (2026-09-03)

**Lane:** authority (D50). **Program:** #2867 step 1. **Read-only.** Probes 2026-09-03
18:30–19:05Z: `GET /v1/nfl/season-schedule` (374 games, key in a shell var only),
`POST /api/admin/db-query` (321 NFL rows, `commence_time > now - 40d`), and ESPN's public
summary API for the five disputed ids.

## Bus bucket M-R-AUTHORITY, first reading (NFL, hand-run)

Matched on (away_team_name, home_team_name), nearest kickoff. StatPal's 53 TBD playoff
placeholders are excluded from the denominator — we correctly do not create those rows,
so counting them as absences would make the bar unreachable by design.

| bucket | n | share of 272 real matchups |
|---|---|---|
| kickoff agrees within 1h | 243 | 89.3% |
| same calendar day, different time | 24 | 8.8% |
| **wrong week (>1.2d apart)** | **5** | **1.8%** |
| in StatPal, absent from our DB | 0 | 0% |
| in our DB, unknown to StatPal | 0 | 0% |

**Identity agreement: 100%. Scheduling agreement: 98.2%.**

The 24 same-day rows are not defects: they are Weeks 16–18, whose kickoff times are not
yet set. StatPal stamps those 00:00Z, we stamp 05:00Z. A daily job must bucket them
separately or the number will sit permanently ~9% below the bar for a reason that is
nobody's bug. The same trap runs the other way: an unbucketed reverse comparison reports
"82 StatPal fixtures missing from our DB" when the honest count of missing real
matchups is **zero**.

## The five

All five were checked against ESPN's own summary API. **ESPN agreed with StatPal in all
five** — our row is the outlier, so this is not a StatPal-vs-ESPN judgement call.

| espn_id | our kickoff | ESPN says | StatPal says |
|---|---|---|---|
| 401873124 SF 49ers @ LA Chargers | 2026-09-11 00:35Z | 2026-12-18 01:15Z | W15, contestid 280730 |
| 401873004 Arizona @ LA Rams | 2026-09-13 20:25Z | 2026-10-18 20:05Z | W6, contestid 280610 |
| 401873006 LA Chargers @ KC Chiefs | 2026-08-15 20:00Z | 2026-10-18 20:25Z | W6, contestid 280611 |
| 401873163 Minnesota @ NY Jets | 2026-08-15 17:00Z | 2027-01-03 18:00Z | W17, contestid 280772 |
| (no espn_id) Dallas @ Seattle | 2026-08-16 00:00Z | not re-queried | W13, contestid 280714 |

Two of the five land inside the Week 1 window, so the site's 16-game Week 1 slate lists
**18** games — each phantom sitting beside the correct row with the home team swapped
between the two Los Angeles clubs. Filed to lane1 as #2869 under D35 (filed, not fixed).

The teams on the bad rows are right and the ESPN id is a real event — a real December or
October game stamped into September. A ±28h time-window guard cannot see this class.

## What this says about the program

The ship is "every game exists before a market lists it, and nothing goes blank when ESPN
does". Before a single row is written, the second authority has already paid for itself:
it found five wrong dates that neither our own data nor a time-window check could surface,
six days ahead of the games. The identity number (100%) is the one that governs a flip;
the scheduling number (98.2%) is the one that has to hold ≥99.5% for seven days, and
those five rows are the whole gap.

## Owed next (step 2)

The daily job publishes these five buckets, not one ratio. A single blended "agreement %"
would have read 89.3% today and buried the five real findings inside 24 non-findings.
