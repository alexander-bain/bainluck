# Bain Luck Product Scoreboard, week of 2026-08-03

First edition of the weekly sweep. Measured Monday from a fresh browser, signed out, on bainluck.com and bainluck.com/sports. Note on method: this run came from Claude's cloud sandbox, not Alex's desktop, so the seconds are best treated as a consistent yardstick rather than exact desk feel. Same method will be used every week. Lane report files were not reachable from the cloud, so ships were read from the week's commit history instead.

## This week's four numbers

1. Cold load (page shell appears): about 2 to 3 seconds on both pages.
2. Time to first real card (skeletons replaced by content): Discover 17s and 22s on two runs. Sports 17s and 12s. Call it roughly 15 to 20 seconds. This is the number that hurts.
3. Jank count from the standard sweep: 23 distinct defects (details below). Zero gambling price formats found anywhere, which is a clean pass.
4. User-visible ships this week: about 13 of the 100+ commits since Jul 27 changed something Alex can see. The rest were plumbing, tests, and process rails.

## What the jank looks like

Discover (9): a trending card where dates already in the past (Jun 27, Jul 18, Jul 25) still show 1 to 3 percent chances, with the dates in scrambled order. The Taylor Swift bridesmaids card calls its favorite "No: Who will Taylor Swift's bridesmai..." and lists every name at 0 percent. The Grammy Best New Artist card shows only two outcomes, both at 1 percent, with no leader anywhere. The Fed September card's options add to 47 percent because the likely leader is missing from the list. The CPI ladder contradicts itself (92, then 50, then 93 percent as the bar rises) and sorts 0.0 before minus 0.1. Hero numbers disagree with their own subtitles (23 vs 22, 11 vs 10). A deal-before-2027 card says 96 percent while the broader deal-by-2029 card next to it says 59. Category chips print truncated question text like "WILL THE U.S." and "DDR5 16GB (2GX8)". One spinner never stops.

Sports (14): two golf events dated May 17 and Jun 22 still sit under Upcoming. Seven old Europa League fixtures show every outcome, including Draw, at 100 percent. The Jersey Jerry ladders show all buckets at 100 percent at once, and a rung at 2 percent directly above one at 100. An exact-score card labels every rung ">= 0". The Stanley Cup table ranks placeholder names Team A, Team D, and Team E at 50 percent above the real Panthers. The US Open Women's Singles is led by Jannik Sinner and Carlos Alcaraz. MLB managers appear inside the Japan NPB market, NFL teams inside the halftime show market, and Big Ten and Big 12 schools inside the Sun Belt market. Exclusive markets sum far past 100 (the MMA title adds to about 320). "New favorite" lines contradict the list below them. Outcome labels collapse to "Cup?", "D", "Y", "F", and "Rica". Titles read "Aig Women S Open Womens" and one event is just called "New York". Five straight MLB games sit at exactly 50/50. The FIFA World Cup winner market is still live at Spain 59 percent two weeks after the final, and the US Open and PGA Championship golf markets are still live months after those majors ended. Two skeleton tiles never finish loading.

## Compared to last time

No previous scoreboard file exists, so this is the baseline. Against the informal Jul 30 sweep that triggered the product-first reset (10 second cold load, a settled event under Upcoming, 0 percent heroes, a broken sort, mangled titles): every one of those five failure classes is still on the site today, and time to real cards measured worse, not better.

## Verdict

Not faster yet: the shell is quick but real cards still take 15 to 20 seconds, despite two speed queues shipping this week.
Slightly better looking: settled-card and chart-axis fixes shipped on native, and empty states got honest, but the web feed still shows every failure class from last week.
Not more usable yet: 23 visible defects in one scroll-through is the same app Alex complained about on Jul 30; the lanes' work has not reached what a user sees.

## Top 3 user-visible fixes for next week

1. Make real cards appear in under 3 seconds on Discover and Sports. The shell is already fast; the wait is the feed data. This is the single most felt number in the product.
2. One settled-means-settled purge: remove or grade everything past-dated (the 100 percent Europa League fixtures, the finished World Cup and golf majors, the expired "Before Jul 18" options, the May and June events under Upcoming).
3. Make every card's outcome list trustworthy: always show the actual leader (Grammy at 1 percent, Fed summing to 47), keep ladders in order, and stop cross-contamination like Sinner leading the women's draw and NFL teams headlining the halftime show.
