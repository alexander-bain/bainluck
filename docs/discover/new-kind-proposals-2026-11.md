# New Grouping Kind Proposals for Alex (#9937)

- **Generated at**: `2026-11-09T21:15:00Z`
- **Audience**: `alex_only` (private grading only; **nothing reaches readers without a licence**)
- **Spend receipt (Decide 61-A)**:
  `[grouping-kind-proposer] model=gpt-4o-mini families=2 est_run_cost=$0.0011 (cap=$5.00) projected_november=$0.0056 (cap=$30.00)`
- **Catalog admission & reader rule**:
  1. Each proposed kind presents **5 example cards** beside its strongest single-market alternative.
  2. A proposed kind joins the catalog only after **6+ graded cards with zero `"no"` verdicts** from Alex.
  3. **Nothing reaches readers without a licence** (`PASS` in `backend/data/grouping_licences.json`).

---

## Proposed Kind 1: `season_stat_leaders` — Season Stat Milestone Leaders

- **Relations**: `same_measure`, `same_window`, `sibling` · **Level**: `member` · **Card form**: `ladder`
- **Why**: Organizes 1,860 open, priced markets across the top uncovered families flagged by the Nov 7 grouping sentinel (`#12231`: NHL team/player point milestones, season win totals, and NFL receiving touchdowns/yards).
- **Licence status**: `UNLICENSED` (`reader_reachable: false`)

| # | Example Card Slug | Title | Rows (Independent Milestones) | Stronger Single Alternative |
|---|---|---|---|---|
| 1 | `nhl-2026-teams-100-points-benchmark` | NHL 2026–27: Which clubs reach 100+ regular-season points? | Carolina Hurricanes (86%), Minnesota Wild (78%), New Jersey Devils (76%), Edmonton Oilers (74%) | Will the Carolina Hurricanes record 100+ points? (`#63218573`, 86%) |
| 2 | `nhl-2026-teams-110-points-benchmark` | NHL 2026–27: Which clubs reach 110+ regular-season points? | Carolina Hurricanes (66%), Edmonton Oilers (47%), Minnesota Wild (46%), New Jersey Devils (42%) | Will the Carolina Hurricanes record 110+ points? (`#63218540`, 66%) |
| 3 | `nhl-2026-players-100-points-leaders` | NHL 2026–27: Which players reach 100+ regular-season points? | Connor McDavid (92%), Leon Draisaitl (88%), Nikita Kucherov (83%), Martin Necas (33%) | Will Connor McDavid record 100+ points? (`#63105212`, 92%) |
| 4 | `nfl-2026-receiving-td-8-leaders` | NFL 2026–27: Who catches 7.5+ regular-season receiving touchdowns? | CeeDee Lamb (92%), Brock Bowers (70%), Dalton Kincaid (28%), Puka Nacua (14%) | Pro Football: CeeDee Lamb 2026-27 Regular Season Receiving Touchdowns (7.5+ TDs) (`#58830297`, 92%) |
| 5 | `nfl-2026-teams-10-wins-benchmark` | NFL 2026: Which teams reach 9.5+ regular-season wins? | Buffalo Bills (93%), Chicago Bears (92%), New York Giants (38%), Baltimore Ravens (14%) | Pro Football: Bills 2026 Win Total (9.5+ Wins) (`#59566032`, 93%) |

---

## Proposed Kind 2: `qualification_stage_board` — Qualification & Stage Advancement Board

- **Relations**: `same_event`, `same_measure`, `path` · **Level**: `member` · **Card form**: `field`
- **Why**: Organizes 484 open, priced markets across the European soccer UEFA qualification and tournament stage advancement families flagged by the Nov 7 grouping sentinel (`#12231`), plus NHL/NFL/CFB playoff berth and seed races.
- **Licence status**: `UNLICENSED` (`reader_reachable: false`)

| # | Example Card Slug | Title | Rows (Multi-Berth Contenders) | Stronger Single Alternative |
|---|---|---|---|---|
| 1 | `laliga-2027-champions-league-qualifiers` | LaLiga: Who qualifies for the 2027–28 UEFA Champions League? | Atlético de Madrid (90%), Real Betis (72%), Athletic Club (14%), Real Sociedad (12%) | Will Atlético de Madrid qualify for the 2027-28 UEFA Champions League? (`#61366351`, 90%) |
| 2 | `epl-2027-conference-league-qualifiers` | Premier League: Who qualifies for the 2027–28 UEFA Conference League? | Liverpool (12%), Brighton & Hove Albion (10%), Manchester City (7%), Sunderland (6%) | Will Liverpool qualify for the 2027-28 UEFA Conference League? (`#61366366`, 12%) |
| 3 | `nhl-2027-second-round-advancement` | NHL Playoffs: Who advances to the 2027 Second Round? | Florida Panthers (62%), Buffalo Sabres (41%), Toronto Maple Leafs (32%), Pittsburgh Penguins (10%) | Will Florida Panthers advance to the Second Round of the 2027 Stanley Cup Playoffs? (`#61380677`, 62%) |
| 4 | `nfl-2027-playoff-berth-contenders` | NFL: Who makes the 2027 Playoffs? | Cincinnati Bengals (94%), Detroit Lions (78%), Houston Texans (39%), Carolina Panthers (30%) | Will the Cincinnati Bengals make the 2027 NFL Playoffs? (`#16630442`, 94%) |
| 5 | `cfb-2027-playoff-top-4-seed-board` | College Football Playoff: Who earns a 2027 Top-4 Seed? | Indiana (46%), Texas (14%), BYU (11%), Ole Miss (6%) | Will Indiana be a top 4 seed in the 2027 College Football Playoffs? (`#58427159`, 46%) |
