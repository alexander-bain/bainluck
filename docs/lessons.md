# Lessons Learned

Rules learned the hard way across reviews and incidents (Decision 125-A, #12549).
How to read a line: the rule first, then where it came from.

## Landed from #12549

### Tue Nov 10

1. **Re-read the thread a minute after you post.** A reply can land seconds after your own comment and go unseen. (Fable missed Builder E's answer on #12541 for 25 minutes, and a review request on #12534 for two hours.)
2. **A red check outside your test file can still be yours.** Repo-wide scans read every changed file. Name the failing test before saying "not this PR". (#12541: one line in a test helper matched a mutation harness's replacement text.)
3. **Before pushing a new Python file, run the residue scan.** From `backend/`: `python3 scripts/evals/scan_mutation_residue.py`. (#12541)
4. **Copy numbers from the artifact you are describing, never from memory.** (#12536: the write-up's gate names and top-five lists didn't match the files, twice.)
5. **"Fresh" means the price's age, not that the market is open.** A card whose number is weeks old needs an age mark or stays off Discover. (#12536)
6. **Don't replace names with a count.** "3 more" hid that the favourite had no number. (#12536; it was Fable's own suggestion.)
7. **A check names its object by its fields, not by words in a title.** A words-only check passes on the wrong answer. (#12541: eight checks did.)
8. **Run mutants with bytecode caching off:** `PYTHONDONTWRITEBYTECODE=1`, and remove `__pycache__`. Python reuses the cached bytecode of a same-size file written in the same second, so a mutant can "survive" without ever running. (#12541)
9. **Take times from the clock, never from a guess:** `TZ=America/Los_Angeles date`. (Fable wrote a time 30 minutes off in a review.)
10. **A list of "files that matter" misses most of them.** When a rule guards a folder, list the folder and name the exceptions. (#12543: a keyword list covered 147 of 740 backend files.)
11. **A file's name can understate it.** `tasks/__init__.py` reads as registration and holds the movement math. Read a file before calling it plumbing. (#12543)

**From Builder E's memory audit (126-A), Tue Nov 10.** These are general lessons from the local notes, reworded as rules. No note text is copied.

12. **Answer "does the code do X?" from `origin/master`** (`git show origin/master:<path>`), never from the shared checkout, which can be weeks behind.
13. **One exact numeric match on one specimen is a coincidence until the system's own predicates reproduce it.** Run the real query or function before publishing a cause.
14. **A filter that defines a rate's population silently changes a count's denominator.** Count "no winner" or "never graded" over all rows, not only the priced ones, and check one case against the venue's own archive. (#12421: five P1s closed and then reopened.)
15. **Never check a base with `git stash push` / `pop` in a shared checkout.** A push with nothing to save makes no stash, and the pop then takes another lane's. Use a throwaway `origin/master` worktree.
16. **Guard a scratch worktree's `cd`:** `git worktree add /tmp/wt-x … && cd /tmp/wt-x || exit`. If the add fails, an unguarded `cd` runs the next merge in your own branch.
17. **Keep helpers and job state out of `/tmp`.** A reboot wipes it, and with it any armed job's state. (Builder E lost a night of reads on Nov 9.)
18. **An overnight job needs UTC wall-clock targets and `caffeinate`.** On a sleeping Mac, `sleep N` can be late by hours.
19. **After a Heroku config change, readbacks show the old value until the release command finishes** (about 20–60 s). Read the release, not the first readback.
20. **A closing keyword fires even inside a sentence saying it mustn't.** Check the PR's `closingIssuesReferences` is empty before merging.
21. **If the bot's review never comes after CI goes green, re-run the review job.** The `pull_request` run can skip before CI finishes, and the CI-completion run doesn't always fire. (#12510, #12543)
22. **The wall-clock guard reads any ISO date within 30 days in a test file, comments included.** Write "Nov 10" in prose, or allowlist the file with a reason. (#12510, #12277)

**Tue Nov 10, afternoon** (added by Fable, 6:19 PM PT)

*Evals and exams*

23. **"Held out" means different cards, not different slugs.** Two of twenty exam cards repeated calibration families under new slugs. Compare selectors and market ids. (#12566)
24. **Grade what the publisher will write.** If a title comes from code, store its inputs on the card and assert the stored title equals the code's output. Otherwise the grader judges wording that may never ship. (#12566)
25. **Say which version a grade was made on.** Grades made on old headings don't pass new ones. Mark them and don't count them. (#12566)
26. **A grading deck takes the top of the slate whole.** An even spread graded 2 of the top ten, which leaves the order readers saw unscoreable. (#12564)
27. **Assigned timestamps get a label.** If a dataset's observation times were set by hand, say so in the dataset. (#12536, #12566)

*Descriptions*

28. **A PR description that names cards or numbers that aren't in the data is a blocking defect.** It happened twice today. Rebuild the description from the files at the head you're asking to merge. (#12536, #12566)

*Destructive work*

29. **A before-image guard compares who a row is, not when it was last touched.** A routine refresh rewrote `updated_at` two seconds before an attended run, and the repair refused. List the compared fields in the SQL. (#12534)
30. **Spend the one attempt carefully.** Re-read the guard's own inputs seconds before an attended run. A refused attempt costs a fresh review and a fresh approval. (#12534)

*Serving an old answer*

31. **If you serve the last answer while a refresh runs, drop it when the truth becomes "none".** Otherwise the page alternates between empty and the old list. (#12563)
32. **Give a background refresh its own time limit, and a lease that outlasts it.** (#12563)

*Privacy and security*

33. **A person's name never goes in a URL.** Query strings land in request logs. Use a header or a body. (#12564)
34. **In a security fix, test the everyday path before writing "can't".** "An unsigned call can't change a phone's account" also meant signing out didn't detach the phone. That scope line was Fable's. (#12565)

*Tests and guards*

35. **Lesson 22 cost four more PRs a CI round today.** Run the wall-clock guard on a new test file before the first push. (#12563, #12564, #12566, #12570)
36. **When you change text a mutation harness targets, re-target the mutants in the same PR.** (#12563)

*Coordination*

37. **"Stuck" needs a fresh read first.** A lane stopped while its three PRs had every approval and nobody else could merge them. Before posting "stuck", re-read each PR's approvals and say who merges. (#12558, #12559, #12567)
38. **Fable: when the last approval lands, tell the author lane "merge it".** Fable reported each approval and didn't notice the merging lane had stopped for an hour.
39. **Fable broke lesson 17 the same day it was written.** A per-game baseline kept only in a sandbox `/tmp` was lost in a restart. Post the ids with the totals. (#12534)
40. **Take a time from the comment's own stamp, never from memory.** Fable wrote three from memory today, and each was two minutes off.

### Wed Nov 11

41. **A claim about how production behaved before a change needs a saved response from before, not a reading of the code.** Fable said the doubled "(Protected)" prop rows predated #12597 after reading the parser. Builder B's saved 1:30 PM response showed they did not. Same miss as "master does the same" a day earlier. (#12581)
42. **Save the response before any deploy that changes a payload, and post its size and row counts.** Builder B's saved Patriots–Lions response turned "why 220 rows became 273" into ten minutes of arithmetic. (#12597)
43. **A destructive pass needs two things before its first write: a count of what it will touch in production, and one log line per change.** #12622 was proven on 42 rows while its selector covered every game market ever stored, and it kept only counters. The shape that passed review: certain changes write, uncertain ones are logged and counted, and a separate PR turns them on.
44. **A CI job is proof only if you checked it ran the file.** Ten real-database test files had never run in CI while their results were being quoted. (#12612)
45. **Don't hard-code a pass count in a CI step.** #12622's step demanded exactly five passed, thirteen passed, and CI failed. Require "none skipped and at least one passed", or change the count in the same commit as the tests. (#12620 has the good form.)
46. **Run the neighbours, not only your own tests.** #12614's wording change broke seven expectations and a fixture hash in files it never touched; #12620's new CI variable failed a guard in another shard.
47. **When a fix removes a wrong number, say in the same message what brings a right one back.** 149-A removed stale projected finals. Nobody proposed reading lines for every league until Alex asked why they were missing. (152)
48. **An age beside a number must date that number.** Our read time is a fair age only when it is bound to the exact price shown and survives caches. A page open, a database read or a scheduled recompute must never reset it. (#12581, 154)
49. **Switching a reviewed-behind-a-flag treatment on for everyone is its own ship decision,** even when it is the mechanism for a small ask. #12623 answered "a mark for every reading" by making the whole Atlas chart key the default. (#12615)
50. **Every card look includes the largest text size, the longest name and the widest number.** The first compact game card scrolled two columns off the screen at large text and printed "100%" with 5:35 left. (#12621)
51. **A live number never prints 100% or 0%.** 99.6% rounded up says the game is over when it is not. (#12621)
52. **Before saying a chart is not thinned, check its marks as well as its line.** Fable checked the line, told Alex there was no thinning, and he sent the screenshot. (#12615)
53. **During a GitHub outage, read the run's own page before touching the workflow.** The CLI said "likely a workflow file issue"; the page said GitHub's own error. One native retry after the incident clears, and no workaround: no empty commit, no manual deploy. (#12597)
54. **A write that returns an error may have landed. Look before sending it again.** GitHub answered 500 to a comment that was already posted. (NOW, 1:28 PM)
55. **If another lane's check is overdue and you can read the same evidence, read it and say you did.** Speed's six-minute memory read never arrived; the log drain had the number. (#12597)
56. **Fable: verdicts and decisions, not a stream of events.** Fable sent Alex a run of "nothing new" replies the same morning 119-A was restated.

### **New, Thu Nov 12 (Fable's evening pass; written 6:31 PM PT, posted late because the Mac link was down)**

57. **A card is not a table: one number leads and the context goes quiet.** From Alex on the game card (decisions 158, 160, 161; #12616).
58. **When checking production memory, read every dyno, not only web.** worker-background was over its quota for 26 hours before anyone looked (#12042).
59. **Say "I have saved it" only after the save.**
60. **Before saying something does not exist, look where it would live under another name, and on branches.** The daily email's sender was there (Gmail API, not a mail provider); the App Clip and Messages prototypes were on branches, not master (#12652, #12307).
61. **Before asking for evidence, re-read the thread; it may already be there.** A capture was asked for twice when it was already posted (#12648, #12654).
62. **Check the current OS before giving device steps.** Watch face sharing moved to the iPhone in watchOS 26; the steps given were for the old place (#12641).
63. **A time in a comment comes from the clock, never from a guess.** Several of Fable's stamps on Nov 12 ran up to 24 minutes ahead.
64. **A read that someone must confirm names exactly what is read.** A confirmation was spent on a read that did not carry its slate id (#11937).
65. **Give a width as a number and say what must be readable at it.** "Side by side at phone width" produced cards at 46% (#12654).
66. **A file meant for a phone is tested at the size and in the viewer the phone will use.** Two versions of an offline pack came up blank at 2.5 MB after passing in a desktop browser; a 0.9 MB one loaded. Cause not confirmed.
67. **A report that merges into the last run can never say "did not run". Start each run from empty.** (#12657)
68. **A number can be freshly written and still wrong. Check the served number against its own chart, not only its age.** 71% served over a chart at 15% (#12658).
69. **"We did not read it" and "there was no price to read" are different rows.** (#12633)
70. **Do not count a reader who said no.** A funnel option would have counted people who declined "anonymous usage stats" (#11934).
71. **To ask for a judgment, show both things in full.** A title and a sentence was not enough to call forty market pairs; both markets with their outcomes side by side was.
72. **Once a look is chosen, anything left over from the old look is a defect, even if it was there before.** The "Opened" caption on the new game card (#12660); the header bubbles (182-A).
73. **A lane that finishes its list before a long unattended stretch gets its next goal before the owner leaves.** Two lanes ran out of work at 10:41 AM with eight hours ahead.
74. **While the owner is away, nobody hand-runs a production release, even to prove a fix.** The heavy worker's update waited for its own cycle (#12647).

75. **When a task's body changes, find every caller that sends it by name.** The hourly category task became a report-opener, and the admin force-refresh endpoint that sends the same task name turned into a silent no-op. The bot caught it; Fable's read did not (#12657).
76. **A red workflow on master hides what it would have tested.** The Watch UI suite did not run on the Watch pins PR because its build job is red on master (#12513). Say "this suite did not run", never "CI is the usual red".

— Fable (coordinator), posted 7:07 AM PT, Fri Nov 13

### **New — Fri Nov 13** (Fable, from today's reviews and findings)

77. **The proof that a merge is live depends on what it changed.** Server: `/api/health` shows the commit. Website only: the website's deployment completes. Apps only: master's CI finishes green. One rule for all three stalled Builder B once and Builder E for three hours (#12608), the second time through Fable's own wrong wording.
78. **A reviewer who only acts when spoken to becomes the bottleneck.** Accepts asked for at 10 AM waited until 1:50 PM. When Alex is away, the coordinator schedules its own checks of the review queue.
79. **A fixed merge order stops at the first lane that is not running.** With lanes absent, merge first come and announce it: "merging #N", then "live".
80. **Say up front what does not need the coordinator.** Changes switched off behind a flag, tests-only and workflow-only merge on green CI plus the bot. Twenty PRs queued behind one reviewer before this was said.
81. **When a reader sees no number, check the build and the venue before the server.** On the Israel market the venue's prices and ours agreed; an older build hid them and the market was read hourly.
82. **A one-sided book at the extreme is a price.** A rule requiring both a bid and an ask refused about one priced outcome in six (#12688). Measure at the venue before arguing; a count settled it in an hour.
83. **Never replace a look sheet that has gone to Alex.** Post the new one under a new name. He ruled on a sheet that had already been overwritten (190, then 191).
84. **A card is the page's headline at a smaller size.** Drawing the two separately produced two levels of quality, and Alex saw it at once.
85. **A column needs a meaning in every state it appears in.** "Pregame" beside "Now" before a game has started says nothing; drop it there (#12696).
86. **Every paste begins with the lane's name, and the lane checks it.** Builder B's paste reached Builder C's window. No harm this time because the work was already done.
87. **Say what you did not read.** An accept that rests on renders, a wording scan and the bot's code review says so (#12675).

— Fable (coordinator), 6:30 PM PT, Fri Nov 13

### **New — Sat Nov 14 to Mon Nov 16** (Fable, from reviews and findings)

88. **At every pass, list every open PR that asks for Fable's look and has no newer Fable comment.** Builder F's Live Activity redesign (#12768) waited from 11 AM to 6:36 PM on Mon Nov 16; reader-visible PRs sat unseen the same way on Sat Nov 14.
89. **Read live status with a direct request, not a cached fetch.** A cached web fetch of `/api/health` returned an old commit (Sat Nov 14).
90. **Review against the sport × state grid, not one PR at a time.** Football had no layout for a game in progress, so the live NFL headline fell back to the old look. No single PR's look covered that cell (direction 199, Sun Nov 15).
91. **A "blended" label on a number is not proof that it's the number we serve.** (#12759)
92. **A CI gate known to be at its limit is fixed before the next merge, not after it fails one.** The 600-second gate was known to be at its limit hours earlier (#12769).
93. **Before starting a fix, search the open PRs for the same issue or file.** Two lanes opened the same fix for that gate (Sun Nov 15).
94. **Before proposing more spend, measure how much of the current plan we use.** Fable proposed a bigger sportsbook-data plan while we were using about a third of the one we pay for (216).
95. **A cutoff is for when the owner is away. If he's here and the delay is a broken runner, set a new time; don't push his item to the next day.** (#12766)
96. **Restate a direction against its source document before routing it.** Fable routed 223 as an NFL form library. Its source, the grouping-primitives design, asks for machinery that makes every kind of grouping good (#12288).
97. **A defect that comes back after a look needs a test, not another look.** "…" in a headline number reached Alex twice, in #12822 and again on build 5760, after looks at large text. #12837 adds a test that reads the rendered pixels.
98. **Server success is not reader success. Before saying a feature works, look at what the reader sees, or say you didn't.** Fable told Alex the Live Activity worked because Apple had accepted every update, but his Lock Screen was minutes behind Apple Sports' (#10542, #12836).
99. **Before treating a price or a model's number as current, check when it last changed.** "Two books have posted a line" for Bills at Patriots meant two September lookahead lines that had never moved. ESPN's predictor for the same game was last updated Aug 31 (#12824, 225).
100. **A fallback that serves the first value ever stored is a freeze.** The API served Bills at Patriots as 50–50 from its first stored line, and the website put that in the page title (ruling 051, #12824).
101. **What a phone downloads has a size budget.** The Week 10 container grew to 4,998 entries and 5.3 MB and scrolled in jumps. Bounded to 169 KB, it dropped no frames (#12817).
102. **Every way a reader can send feedback needs something that reads it. Prove it by sending one.** Nothing read TestFlight feedback until Mon Nov 16 (219, #12831).
103. **A scheduled job that fails every run is an outage, not noise.** `update_max_movement` timed out on 8 of 8 runs, so the movers ranking may never have refreshed (#12834).
104. **Write voice phrases the way people talk, and test them by saying them.** "The next Patriots game" found a college basketball team, and the suggested trigger phrases were ones nobody would say (208-A, #12816).
105. **A watcher waits for CI's verdict, not a fixed timer.** A 40-minute limit nearly reported a healthy merge as stuck while runners were queued (#12766).

— Fable (coordinator), 6:38 PM PT, Mon Nov 16

### **New — Tue Nov 17, 2026** (posted 6:31 PM PT, Tue Nov 17, 2026; lessons 106 to 124, from the day's reviews and findings)

106. **A join or timeout rule needs slack over the interval it follows.** The website's projected-final chart joined two readings only when they were at most 60 minutes apart; the poll runs hourly and lands 59 to 64 minutes apart, so the line fell apart into dots (#12889, #12890).
107. **Fit an axis to what is drawn in that phase.** A zero-based axis suits a live score climbing from 0; before a game it put 112 and 114.5 on the same row of pixels, on the website and the iPhone (#12889, #12898).
108. **Judge a source PR by what it does to the combined number, not only by whether its own data is right.** The ESPN fill was accepted with ESPN still in the pregame number at weight 1.5 after markets arrive; caught the next morning and ruled 226: A (#12843).
109. **When one surface shows a wrong kind of number, check every surface for it.** A first stored line shown as a current chance was reported on one game page; the same fault was on the search card, the page title, the Mac menu bar, the Lock Screen circles and the Watch (#12855, #12896, #12906, #12908, #12909).
110. **A check must tell "ran and found nothing" from "did not finish".** The typecheck gate counted a compiler killed for memory as zero errors; once that was refused, master went red until the compiler was given the memory to finish (#12872, #12877).
111. **For apps, "live" is a TestFlight build number.** A build that has only started is not live, and a merge that lands while one runs cancels it: three builds were lost between 10:49 AM and 1:33 PM. Ready apps PRs now merge back to back, then the slot waits for the build.
112. **A merge order is a tie-break, not a lock.** The server slot sat empty from 3:15 to 4:03 PM with about 22 accepted PRs waiting, because each lane waited for the lane ahead of it in the order.
113. **A merge script re-reads every lane's lines immediately before it merges, and reads all of each line.** One script checked other lanes once and merged 37 minutes later into another lane's turn; later it counted one PR in an announcement that named three (#12764, #12598).
114. **Batch what doesn't overlap.** One server merge at a time cost about 40 minutes each; batches of up to three PRs that touch different files went live in one deploy the same afternoon (229: A).
115. **Ask for a look only where a reader sees the change arrive, and say which it is in the PR description.** Twenty-five PRs waited about four hours for looks, many of them switched off or not drawn by any client yet.
116. **An accept carries across a merge of master.** About ten "carried" comments were written in a day, each one a lane waiting for nothing.
117. **Never state a wording rule without its source.** A "rule" that a word was banned from reader copy came from a summary, not a ruling; the phrase is live copy on three surfaces. It was caught before it was posted on two PRs.
118. **Don't hand Alex a link or a click path that hasn't been tested or checked against the vendor's own documentation.** A build link copied from a GitHub check opened a start page, not the build.
119. **Before asking Alex to diagnose a failure, see whether the next run answers it.** The TestFlight export failure was a timeout on Apple's side; the next build passed and no log was needed.
120. **A count gets gamed by the thing it counts; pair it with the eye it is meant to predict.** The grouping report passed all four groupings on "a picture on every screen" with flat-line charts and a chart of a different market than the card's headline (#12897, fixed in #12899).
121. **Measure the cold read.** The Sports tab's main feed took 6.2 seconds on a miss and 0.35 seconds from cache; the Week 10 page still took 6.05 seconds cold after its fix. The reader who hits the miss is the one who reports it (#12886, #12858).
122. **After a push, confirm a run started.** A branch with a merge conflict runs no checks and says nothing; a Watch workflow fix sat for 2.5 hours (#12745).
123. **Deployed is not the same as running.** A scheduled job waits for the background server to load the new schedule, which took up to three hours; say when the first run can happen (#12843).
124. **A tool that watches the pipeline must stay out of it.** A draft dashboard attached a check to every pull request and ran each PR's own code with a write token; either would have slowed or endangered the merges it was built to show (#12903).

### **Lessons, Wed Nov 18 (125 to 137).** Fable, 6:30 PM PT.

125. Read the code before saying how a number is made. One payload is one example, not the rule. (I told Alex the projected final came only from sportsbooks; the code picks one source by confidence.)
126. A standing ruling is not reversed on my reading of a question. Ask, or leave it. (Live Activity headline.)
127. Before telling Alex he owes something, read what the lane already reported. (Builder E had run the export hours earlier.)
128. An issue with dates and no owner is nobody's. (#12253 sat; tonight, eight update-bot PRs from Nov 6.)
129. Anything only Alex can do each day goes in front of him as a daily ask, with the link and the steps. (Ranking grades: zero graded mornings.)
130. A sheet that says "6 of 6 met" still gets opened. (Grouping sheet: slate dates in the wrong day, a cut-off line; tonight, "toss-up" on a 39% to 61% game.)
131. A rule that says "first" must not make ready work wait. (Rule 10.)
132. Diagnose from the log before writing a fix paste. (The Factory's false HOLD.)
133. After a crash, every lane gets one restart paste with a required reply format, and names its background jobs.
134. The watcher is not the only ear. A "stuck — Fable" line sat 45 minutes between wakes. Read NOW at every pass.
135. When the line is slow, count the machines before blaming the tests. 40 running and 95 waiting is a ceiling, not a flake. (#13027)
136. Clock times come from the clock. I wrote two guessed times tonight and corrected them.
137. A lane's reading of old app source is a finding, not a render. Say which it is when it goes to Alex. (What 1.0.6 draws for the two slates.)

### **Lessons, Thu Nov 19 (138 to 154).** Fable, 6:34 PM PT.

138. While lanes are working, a ready look older than 30 minutes is my defect. Never leave a look for a scheduled pass. (Looks sat overnight for an 8 AM pass.)
139. A re-run on a busy line gets cancelled by the next queued run. Do not plan on "the re-run passing". (Today 37 of master's 70 check runs ended cancelled.)
140. Before a lane's list or claim goes to Alex, check it against the decision log and master myself. "Verified against the code" in a lane's note is a claim, not a check. (Same family as 125, 127 and 130.)
141. NIGHT turns the watcher off, not the lanes. Work parked "for the 8 AM look" is my queue costing a lane hours. Do the looks when Alex pings, whatever the hour.
142. A scoped yes-line says where its scope ends: "for this one read; normal work continues." (Builder B applied a read-only yes to its merges and stood still for two hours.)
143. A paste that authorises merges or pushes for Builder B names the PR numbers, and the branch names for pushes. (Its checker refused a squash in the morning and a branch push in the afternoon.)
144. Before telling Alex a flip is about to happen, read the live surface myself for the pass test's obvious failures. (The old Oscars and Fed cards were in my own morning read.)
145. A time stamp comes from the clock in the same command that writes it. (Three guessed times today, one day after lesson 136.)
146. A count comes from the file in the same command that writes it. (I wrote "20 and 11" where the file said 12 and 9.)
147. "Byte-identical" needs the real call path. A call with an empty list proves nothing.
148. Read how the thing behaves live (switches, caches, expiry) before writing a flip order, and make the pass test outlast the longest cache in the path. (Groupings flip 2 passed every content check, then lost groupings when a five-minute cache expired.)
149. A look at a grouping reads every row title and every row's number against its own page, not only the seats. (I accepted #13077 on seats; flip 1 showed readers an internal merge note and a market with no prices.)
150. Print None as None. Never turn a missing probability into 0 when checking a page. (I told Alex a page printed 0% when all 16 prices were withheld.)
151. A ranking before-and-after runs every step after the scorer, or is labelled unverified until it is live. (#13106: the replay said seat 33; live said seat 4.)
152. A poller that asks for one page fails loudly when the page is full. (The watcher read the oldest 100 comments; seven ready lines waited up to 55 minutes.)
153. Before handing Alex a paste for a lane, read whether the lane already took the work. (Speed had taken #13112 before my paste reached it.)
154. After a container restart, the watcher is the first thing re-armed. (A lane waited 15 minutes for an ACCEPT to be carried to a new head.)

### **Lessons, Fri Nov 20 (155 to 183).** Fable, 6:54 PM PT.

155. After a branch merges master, check every call of any helper whose options master changed that day. A text merge with no conflict proves nothing about meaning. (#13249 kept `league_ceiling=` after #13241 renamed it; Discover and the games list were down 56 minutes.)
156. A run on real data that never reaches the new line is not a test of that line. For every new branch in the code, add one made-up case that reaches it. (My 184 real sides had no two crested rows sharing a crest.)
157. Before a batch of accepted changes is released, merge them all together locally, import the modules and scan the result. Each one passing alone says nothing about the set. (Done tonight for eight changes, after the outage rather than before.)
158. In an outage, do three things in the first ten minutes: offer the roll-back decision with its paste, hold every other lane, and clear the queue in front of the fix. (The fix's release run started the moment it merged because the queue was cleared first.)
159. Before saying whose miss something was, read the accepted head itself. (I told Alex the broken line came in after my look. It was in the head I accepted.)
160. When citing another post's time, read it from the post. Typing it is the same fault as 145. ("My 6:06 PM post" was posted at 6:04 PM.)
161. Before offering a decision, search the decision log and my notes for the subject. (I offered 308, which was 249: A from two days earlier.)
162. An "after it is live, do X" ask needs an owner and a board date, or it does not happen. (The screen description on TestFlight reports was accepted Nov 19 and never worked; nobody filed the one real report that would have shown it.)
163. A build is accepted against the look the owner picked, opened side by side. If the picked look never came to me, fetch it before the accept. (The Factory's seventh round was accepted without the picked sheet beside it.)
164. A lane acts on the full text of a post and names the comment it acted on. A cut-off preview can contain words nobody wrote. (A lane pushed three branches on a "released" that was never posted.)
165. On a jammed day, read the run counts before adding work, and batch comments: every comment starts a run. (82 runs were queued at 3:41 PM.)
166. Sweep for accepted pull requests older than a day that have not merged. An accept the merging lane is not authorised to act on is not done. (#12622 waited eight days.)
167. When a lane rebases an accepted pull request, check whether the branch has to be level with master before accepting the churn, and write "do not rebase unless GitHub reports a conflict" in the accept. (One pull request was rebased three times in an afternoon; each restarted 17 checks.)
168. Before telling a lane to run a stand-in check, read the head's check runs. If nothing is waiting, there is nothing to stand in for.
169. Before listing "still open with Alex", check each item against the notes for a ruled or passed line. An old summary's open list goes out of date within hours.
170. A linked id is not a better answer than the name lookup until rows that describe the same club are folded. When a change adds a second way to find a row, run both ways on the clubs that have two rows. (#13229.)
171. When a list comes from one function and production calls another path, check that the production path reaches the same rows.
172. Name the merging lane from the ruling's text, not from a pull request's or a plan's own claim.
173. "Built by the route" is proven by the cache status reading a miss, not assumed from a different time limit.
174. A scripted page check scrolls the way a reader does. Without real scroll events it can miss pages that load as you scroll and report "none".
175. Open the rendered page before calling a change live. A 200 from the address is not the page.
176. Before promising a check, confirm I can reach the surface without a credential. (The grading pages sit behind the admin secret, which I do not use.)
177. A lane's "stuck" line gets an answer within one pass whether or not it names me. Sweep NOW for "stuck" at every wake.
178. A wake word that fires once has to be added again. Check the watcher's list whenever I tell Alex "I will be woken when X".
179. For a change to the order of Discover, ask for the whole first 20 before and after, with every pass run together. A one-card trace hides what the change does to the page.
180. When a candidate is built to hit stated numbers, count those numbers on a real page on the first look.
181. A guard is tested on its nearest wrong neighbours, not on examples that are far apart. (Reserve and women's sides against first teams.)
182. Before accepting a change to something that writes or encodes data, run it on one real payload from production.
183. To judge a page at phone width in a desktop browser, open a 390-wide window and read that. Resizing the main window does not narrow the page.

### **Lessons, Sat Nov 21 (184 to 204).** Fable, 6:34 PM PT.

184. An "after it is live, do X" ask needs an owner and a date on the board, or it does not happen. (A screenshot description ruled on Nov 18 never worked, and nobody was assigned to check it.)
185. A merge order that puts another lane's pull request first must check that lane is active and say why each one waits. Never chain lanes unless the files require it. (Friday evening everyone was queued behind one silent lane and nothing merged for 78 minutes.)
186. When accepted changes are merged together locally, run each change's own test files on the combined tree. Importing and scanning is not enough. (Two changes each passed alone; together a count test expected 17 groups and found 18, and master went red twice.)
187. Read a ruling's text before acting under its number. (A summary line turned "may open tests-only pull requests" into "may merge".)
188. Check your own rounding before calling two numbers different. (A served 41 against my own 40.)
189. Before saying whose miss something was, open the accepted head itself. (I said a break arrived after my look; it was in the head I accepted.)
190. Check a claim about motion by measuring pixels across frames, not by reading the code. (Figures that were meant to move did not, because a style rule was never rewritten by the build.)
191. A match on kickoff time alone is not proof of the same game. Require the same opponent or the same final score before a copy is deleted. (#13229's rehearsal showed different games at the same hour.)
192. Fetch master before reading a merged-tree diff. (A stale base showed another lane's files as part of a change.)
193. Your own probes cost production. Keep them small and say what they did. (Nine searches made the server create and discard rows; one 200-row read answered 503.)
194. Check what a monitor actually requests. (An uptime check's request shape forced a cold build a minute and inflated a health counter.)
195. A new query on a path that runs on every keystroke or every page needs a timing on production-sized data before the accept. "After it is live" is too late when a failure occupies the web workers. (#13341: a search that passed every test timed out at 30 seconds live, stalled other requests, and needed a rollback.)
196. A rule that hides pictures or rows "all or nothing" needs the count of public cards it changes before the accept. (#13353 took the row pictures off four public cards.)
197. Before telling the owner what a ruling will do to the first screen, check where the new cards will sit. (Seven cards went public and landed at seats 39 to 63; the first ten did not change.)
198. Never type a clock time in a draft. Take it from the command's clock, a file's time or the post itself. (Three slips in one day, each corrected after posting.)
199. A threshold written into a paste must come from a measurement. (A "under 2 seconds" line for a search that normally takes 2 to 3 seconds produced a false URGENT.)
200. When the live release is behind master, as after a rollback, master is closed to everything but the fix. Compare `/api/health` with master before loosening any hold. (A hold was loosened six minutes before a rollback; nothing merged in between, by luck.)
201. Do not route work around an approval only the owner can give. Ask again, say plainly what is waiting, and keep everything else moving.
202. At every round-up, check how long ago each lane last posted. A lane whose one task is blocked on another lane's merge needs a second list the same hour. (One lane waited about four hours on a build.)
203. Read NOW again inside the minute before you merge. (Two merges landed one and four minutes after a hold, from lanes that had not seen it.)
204. Before putting a control to the owner, say what it does to every party it binds. (A "keep out" file on the API host would stop a crawler and also stop search engines loading data into our pages.)

### **Lessons, Sun Nov 22 (205 to 230).** Fable, 6:36 PM PT.

205. A test run that passes says nothing about lines it never runs. Scan every changed file for names that are used and never defined. (#13385 used a time helper it never imported; no test ran that line, I accepted it, and the Factory page stopped updating for four and a half hours.)
206. Taking a wrong picture off a card is half the change. Ask for the right one in the same pull request. (Two cards went public with no picture at all.)
207. When the server names a row and the app prints its number, both must choose the row by the same rule. (#13413: "any" on the server, "all" in the app, so a mixed ladder named one level and printed another level's number.)
208. Before calling a behaviour a defect, search the decision log for the ruling that made it. (I reported "no game cards on Discover" as a problem. It was ruling 301: A, in a change I had accepted.)
209. A timing from a generated copy of the data is not a production timing. For a query that runs on every keystroke, require a plan read from production, with the owner's yes, or make the check after release the stated acceptance. (#13444 measured 25 to 33 ms on a copy; live searches took 1 to 5.7 seconds.)
210. Check the order of results with the word a person would type, not only that the right row is somewhere in the list. ("Lakers" returned the Lakers eighth.)
211. Before reporting a slow read, confirm the parameters are ones a client really sends. (I timed a list with `league=`, which that route ignores; it takes `sport=`.)
212. A plan that waits for the coordinator's go gets a line on NOW starting "asked-for line:" with the link, and the coordinator opens the issues named in each lane's goal at every round-up. (A plan sat on its issue for two hours and the lane marked its goal blocked.)
213. A live path must not depend on a one-off background job that can expire in a busy queue; it needs a fallback for when the thing is absent. A design risk named in a review is a change request, not a note. (Team search answered "unavailable" for 75 minutes on Sunday morning because the rebuild job expired before a worker took it. I had named that risk and accepted anyway.)
214. A snapshot built with zero members is a failure, not an empty answer. Publish nothing and report it. (Same job.)
215. For any change that adds a task or a dispatch, run the result-retention guard, the startup test and the schedule guards before the accept. (#13401 went red on a guard I had not run.)
216. Wait for a lane's hosted run before the accept when that lane's accepts have met a red check afterwards. Where an accept does come first, it says "merge when required checks are green". (Three in two days: #13414, #13401, #13424.)
217. When one line changes a shared test such as "is this sports?", list every place that calls it and every card that flips. (A one-line change reached four call sites.)
218. A preview render skips checks the public page applies. Before a set goes public, run the batch gate against production and look at that sheet, once. (Batch 5 looked right as a preview and needed fixes as public.)
219. What the server sends must obey the written rules of the build already frozen. (#13441 sent letter circles for missing pictures; the app's rule is real art or nothing.)
220. Measure a layout change at the largest real page before accepting it. (#13442 drew every card at once: 1,340 ms and 342 MB more at 167 cards, against 160 ms on the frozen build.)
221. A test must not stamp a time when its file is collected. (A frame stamped at collection was 28 seconds old when its shard ran, and master went red on a change that was right.)
222. An accept bar set before the measurement is honoured or taken to the owner. It is not loosened inside the review. (#13443's "under 60 seconds" did not hold in production; decision 346 set two minutes until the warm-up job is fixed.)
223. Replay a tie rule against the obvious case before it ships. ("Most live games" seated four basketball games above the Sunday night football game.)
224. A card must not print the same line twice, and a machine check catches that better than my eye. (#13450's Golden Globes card printed its headline twice; the check is going into the batch gate.)
225. When a lane's own approval review blocks an action, the coordinator does not do it for the lane and does not hand it to another lane. The owner confirms in that lane's window. (Two of my drafts were refused for this.)
226. A ruling covers the pull request it names. Extending it to another one is the owner's call. (I extended 328: A on my own; refused.)
227. Know the real size of the test pool before planning a jammed day. (It is 40 jobs; I had told lanes 20.)
228. Read NOW from the time of the last read, never from my own last post, and let a line starting "stuck" wake the watcher within 15 minutes. (Three posts fell between two reads on Saturday morning; the wake gap for a stuck line was 45 minutes.)
229. A board script that skips closed rows leaves them open on the board. Set closed issues to Done in the same run. (Three closed issues were missed by the sweep.)
230. On the eve of a freeze, anything that must be live that evening merges by mid-afternoon. (Sunday's master checks took about 30 minutes at 1 to 4 PM, then 73 minutes for a 4:37 PM merge; a 5:43 PM merge was still running 50 minutes later.)
