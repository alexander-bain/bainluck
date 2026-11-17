# Served opening-price correction, Nov 17

Public health served healthy `b62b1351`, which contains #12855 (`788f8c5060`). Master CI 44156509429 passed after the compiler-heap correction #12877.

The 9:46 AM PT before read found 27 opening-source games among 1,784 unique upcoming rows. At 12:18 PM PT the saved cohort had zero opening-source chances: 24 were unavailable and three had a blend. Twenty-five remained in the scheduled list; two were live and were checked through their detail endpoints. The new whole list had 1,779 unique games and no opening-source chance. This is a moving list, so the original 27 IDs are the comparison cohort.

Bills–Patriots 15184640 now has null home/away headline and current-odds probabilities. The first HTML response at 12:18:37 PM PT still carried the old 50% title; it is retained in after-summary.json. A normal GET at 12:20:00 returned “Buffalo Bills vs New England Patriots Odds | Bain Luck”. Both responses reported Vercel MISS; no CDN-hit claim is made.

The production browser at 390 by 844 pixels showed no current chance. Its Patriots link opened the correct team page, whose Bills row also had no chance. Back and Refresh retained the corrected game and title. Images are browser captures, not native-app proof.

No database/admin/worker command, cache purge or manual production repair was used.
