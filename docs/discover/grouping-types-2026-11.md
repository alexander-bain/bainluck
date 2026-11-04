# Grouping types catalog, Nov 2026

**PILLAR:** DISCOVER and FORMATTING, with TRUTH as the gate. **SHIP this serves:** each week through
Dec 13, a reader sees one new kind of comparison card on Discover: related numbers shown together in
one readable card that opens its own container, instead of the same template card after card. Today
10 of the feed's 95 standalone market cards are one template, "Senate Combo: …" (§0.3).

**Status:** brainstorm and research only. No product code, no ruling, no change to any workflow,
setting or NOW. Names, bands, rankings, definitions and card copy are recommendations; product,
ranking and copy calls stay Alex's (PRODUCT-BRAIN, "THE ONE RULE ABOVE ALL"). NOW #11852 is the order;
§3 is a proposal for it. Written by Argon at Alex's request, Tue Nov 3, 2026; at his further request
(3:45 PM PT) every type names its producer kind and five definitions that kind could instantiate from
today's data. Docs and code read at master `d979d1fdc9`. Production read anonymously from public
endpoints on **Tue Nov 3, 3:19–3:23 PM PT** (§0.3).

Contents: §0 grounding · §1 the ten types · §2 the ranking · §3 one type a week, Nov 2 – Dec 13 ·
§4 folded, shipping or rejected · §5 decisions for Alex · §6 observations from the reads.

---

## 0. Grounding

### 0.1 A type, its producer kind, its definitions

The container catalog (`docs/containers/catalog-2026-11.md`, #11905; decisions A–D ruled on NOW #11852
at 9:33 AM) says what a card opens and how its members are decided. This catalog says how a card
**groups and compares** its members: the shape a reader sees on Discover.

Each type names its **producer kind**: the reusable function a stored definition points at, as
`window_events_closest` and `field_band` are for #11915 and #11928. It then lists **five definitions**
the kind could instantiate from today's reads, each with its members and whether it would make a card
today. A definition is data (decision D: a later container of the same shape is a definition, not a
deploy), so the five show that a kind can be filled; they are not the five that ship. Each kind also
names its membership kind from the container catalog's §4.1 (decision A: `sibling-family` is the
seventh kind; decision B: the definition's field is `membership`).

Counted elsewhere, so not in the weekly list:

- **In flight** (catalog decision D): `window_events_closest`, the closest games tonight (#11915, merged
  to master at `17f8757e89` while this was written), and `field_band`, the CFP picture (#11928). Week 1
  (Nov 2–8) belongs to them.
- **Live in today's feed:** 11 theme bundles grouped by story key (Awards Season, IPOs, Middle East, AI,
  Congress, UFC, Grand Slam Tennis, Russia–Ukraine, Fed & Rates, State Races, World Wide Technology
  Championship) and 1 round-up (NFL division front-runners, seat 12).
- **Live in code, no card in today's feed:** the deadline-family card (#11864, Nov 2), the swings
  bundle ("Today's biggest swings", `assemble_swings_theme_bundles`) and the comparison bundles
  (`PUBLIC_COMPARISON_BUNDLE_THEMES`: ipo_valuation, commodity_ranges, rotten_tomatoes_scores,
  weather_distributions).

### 0.2 What binds the types

| Source | What it binds here |
|---|---|
| #10354, Oct 8 00:30 and 00:48 UTC (Alex's Oct 7 sibling rulings, recorded by Root) | Group only markets that differ in exactly one thing, the row subject. Rows keep their own numbers: "Do not normalize rows to 100." "Different deadlines, thresholds or stages must stay separate." "Positive equivalence is required for all fixed dimensions; a shared story key is insufficient." One group card per family at one common deadline; its container holds the family's other deadlines, unlike the round-up's exact membership. Which deadline leads is unruled: "Do not apply nearest-open implicitly." |
| #10354, Oct 6 (Root's preservation of Fable's handoff, `11-COMPARISON-WORKSTREAM-HANDOFF.md`) | Alex's grades of 98 cards in four slates, as relayed by Fable: "Movers" 7 of 7 "amazing", "Same deadline" 13 of 17, one market across several subjects 2 of 2, "Head to head" 1 of 1, "As likely as" 9 of 16, "Clock" 6 of 16, "New favorite" 1 of 3, "Reversal" ("guess which is likelier") 0 of 6 with 4 "no". One rater, venue numbers, not the blend, not a holdout. The movement truth rule (§4 of the handoff) and Root's review (`13-ROOT-REVIEW-20261006.md`) apply to every type that compares two times. |
| #10354, Oct 7 04:16 UTC (Alex ruling, recorded by Root) | A blend failure is a matching or data defect, not a reduced-card state: a required member failing means no card, the ordinary feed unchanged, the failure surfaced through the sentinel path. A clinched division is settled, not a defect; late-season wording is Alex's. |
| #10354, Oct 8 04:36 and 16:21 UTC | Congress uses two-sided rows (option A). Option A of the first-twenty review: three same-weekend golf tournaments are one card, three visible rows, no container when all three are visible. |
| #10357, Nov 2 contract and Amendment 1 (Alex ruled A, Nov 2, 5:19 PM PT) | One function decides card and container; refusal is a 404 `unavailable`, never an empty page; revision is the CRC32 of the ordered member ids; producers sit in a registry (`roundup_containers.py`, `RoundupProducer`) that becomes stored definitions in week 3. |
| PRODUCT-BRAIN, Jul 27 ("First presentation kernel: COHORT-COMPARE") and Aug 7 (mover headlines) | Same shape across peer sets (division races, movie thresholds, Fed meetings), with commentary "data-grounded or silent". A headline may name a mover instead of the leader only when the move is visible on click-through. |
| Standing rulings 1, 2, 3, 5, 7 | One number per market; settled means settled; no betting formats or volume; nothing beats unhelpful; the story is the ranking unit. |
| Rulings 016, 027, 047 | The comparison lives inside the story card, and no claim that a story is interesting without the temporal holdout. Chrome is earned by counts, and a cap is always counted. One card system: a new card type needs a design ruling first, and date ladders render as the heatmap card. |
| Rulings 097, 101, 103, 105, 111, 112 | No statistic rescues a bad pair. Group, don't cull; after the result, surprise is \|result − mark\| and no travel bar is drawn. A probability captured after the answer is not a probability. A structural rung is not a view, and the rail is movement first with one row per ladder. |
| Rulings 106, 107, 114, 138, 141, 142, 053 | Every row quotes the chance it happens. No unlabelled units. A settled card's quiet rows stay. Probability, never price. Venue names only as attribution of a number. Present tense, no promises. A binary leads with its Yes side. |
| Rulings 139, 143, 145, 146, 147 | A near-duplicate rule never collapses across subjects. Two rivals asked one thing are one card, its legs unnormalized, and "a comparison is complete or it is not presented as one" (CERT-430). The system finds a template family (`prop_template_family.py`: at least 2 shared tokens, the subject run no longer than the shared part, outcomes compared from their intersection). An illiquid market is still shown, with an honest age. The whole card is the target. |
| NOW #11852, today | Sparse history is the next bug category (#11929, Alex, 2:06 PM). Source attribution is a glyph on every number, the same on web and iOS (#11920, ruled 1:01 PM). |

### 0.3 The reads

- **Feed.** `GET /api/feed?event_pct=0.15&limit=200` at 3:19:46 PM PT returned 200 with 129 items
  (edition `f362743e4a1565e8`, cache `miss`, `live: true`): 95 futures, 12 bundles (11 theme, 1 round-up),
  12 concepts, 7 events, 3 tournaments. No comparison bundle. 24 of the 95 futures settle tonight; 55 of
  95 list exactly one source. By category: politics 45, sports (all leagues) 20, economics 13, tech 7,
  geopolitics 5, entertainment 4, weather 1.
- **Browse.** 27 reads of `GET /api/futures/browse?q=<term>&limit=200`, 3:21:25–3:22:56 PM PT, two seconds
  apart, all 200; 1,673 distinct markets. Terms: snow, Buffalo, Division Winner, AFC, NFC, sweep,
  Person of the Year, announce a presidential run, Next Team, shutdown, Starship, by December 31,
  before 2027, Senate Combo, Rotten Tomatoes, hit (HIGH), recession, Super Bowl, Heisman, Grand Slam,
  by November 30, by November 15, Gas prices, Fed decision, highest temperature, GTA, MVP.
- **What browse can show.** Open markets only, never game markets (`event_id IS NULL`), one venue per
  row, raw top-three outcomes (not blended, not normalized). Its `movement` field is
  `reader_change_24h`: a per-write delta for every source except DataGolf (Root review, Oct 6, §3a), not
  the blend at a dated time. The feed carries the blend where a card has one (the round-up rows).
- Every number below is that snapshot, and every id is a label from that moment (ruling 042, clause 3):
  the lane that builds re-derives from the live source. The reads finished at 3:23 PM PT, before Speed's
  4 PM election watcher. Two definitions cite the container catalog's 06:50 PT read (its P2 and #37).

### 0.4 What "waits on #11929" means

A type that compares a number now with a number at an earlier time needs both ends to be the same
displayed quantity (same sources, same scale), a dated observation at the stated distance, and enough
markets carrying one (handoff §4). Root's Oct 6 review found the current Movers path does not meet the
first, the dated bank covers 12–24 hours only, and coverage is unknown. NOW #10 ("is the price history
clean?") is that verdict; #11929 is the history it needs: today a futures chart can show one point
every two hours, and the live stream writes no history rows.

Four types wait on #11929 and say so in their entry: **Movers, every division since Sunday, the
biggest surprises, new favorite.** They are specified, ranked and given copy and definitions so they
can ship the week #11929 and NOW #10 clear. None of their twenty definitions makes a card today, by
design. They cannot be scheduled before #11929.

### 0.5 Copy rules used in "Card at 390 px"

"Market", never "question" (CLAUDE.md); quoted records keep their own words. Card copy says
probability, never price (138); names no venue in a sentence, because attribution is the glyph on
every number (141, #11920); stays in the present tense (142); quotes the chance the thing happens (106);
writes a change as "from 41% to 50%", never "+9" (107); leads a binary with its Yes side (053); prints
whole numbers through `renderedPercent` (half up; an open market never prints 0% or 100%); counts any
cap (027). Each card lists its words in reading order: kicker, title, rows, count line, footer, and what
a tap opens. At 390 px a card shows at most five rows (§1.2's eight one-line rows are the exception),
and a title longer than about 26 characters wraps to a second line.

---

## 1. The ten types

Alex's five first, in the order he named them, then the five found in the rulings and their records.
Each entry ends with its rank and score from §2.

### 1.1 Movers (waits on #11929)

*Where the numbers moved since yesterday, each row showing where it was.*

- **Producer kind:** `dated_movers` (story-movement; new). Parameters: scope (all, a category, or a
  theme subject), window (20–24 hours, or 7 days), two to four rows, one row per ladder, both ends the
  same displayed quantity. It sits on the existing swings bundle (`assemble_swings_theme_bundles`,
  `SWINGS_MIN_SWING = 0.15`, `SWINGS_EXTREME = 0.95`) and the dated bank (`dated_movement_basis`).
- **Member rule:** two to four markets whose displayed number moved most between an observation 20–24
  hours old and now, both ends the same displayed quantity, the market at least three days older than
  the span, with no settlement jump, no deadline running out, and no two rows from one market or one
  ladder (ruling 111; a structural rung counts only if it moved, ruling 112). This is Root's smallest
  truthful slice (Oct 6 review §4).
- **Data today:** the swings bundle produced no card in the feed. Of the 231 outcomes shown on the 95
  standalone futures cards, 18 carry a movement number (on 15 cards), and 15 cards carry a "moved today"
  headline, led by Titled Tuesday Top 5 (67861996, "Hans Niemann up 83 points today", three players
  shown at 90.5% in a five-winner market), three Trump statement markets (68806011 +36.5, 68851041 +34.5,
  68846417 +24) and three stock-hit ladders (67583141 −27, 68881352 +23.5, 68881291 +15.5). In browse, 1 of
  the 48 outcomes shown on the 16 NFL division markets carries a movement number. Alex's 7 of 7 was graded
  on venue history, not on the product's blend.
- **Five definitions from today's data** (all refuse today: no dated basis):

  | Definition | Members today | Today |
  |---|---|---|
  | `movers-since-yesterday` | the feed's 95 standalone futures; 15 carry a movement number | refuses |
  | `movers-politics-since-yesterday` | 45 politics cards; 9 with a movement number | refuses |
  | `movers-economics-this-week` | 13 economics cards; 3 with a movement number | refuses |
  | `movers-ai-since-yesterday` | the AI collection (`collection_ref` count 563; feed members 68859564, 60607595, 60635344) | refuses |
  | `movers-sports-futures-this-week` | 20 sports futures cards; 1 with a movement number | refuses |

- **Waits on:** #11929 and NOW #10, with #4079's dated baseline.
- **Refusal rule:** no card with fewer than two qualifying rows, and never a forced slot. No "biggest"
  while coverage is partial (Root §4). No row from a mention or statement market, a daily or financial
  ladder, a multi-winner field near settlement, or a market whose earlier end is its opening
  probability. No row where the sources changed between the two ends (#5440).
- **Card at 390 px:** kicker "SINCE YESTERDAY" · title "Where the numbers moved" · two to four rows,
  each "‹now›% ‹market›" with a grey line "from ‹then›% yesterday at 3 PM" and a tick on its bar at the
  earlier value (the slate design Alex liked) · footer "Each row is the same number, 24 hours apart." ·
  tap opens the container of those rows. No row qualifies today, so no numbers are shown.
- **TRUTH risk:** a settlement jump or an opening probability read as a move (about one in five "big
  weekly moves" was an artifact in slate v4); a raw book row compared with a blend (#1844); a per-write
  delta narrated as a day's change, which is what today's 15 headlines do.
- **Rank 4 · 75.** TRUTH gate: out until #11929 and NOW #10.

### 1.2 Every division since Sunday: a comparison of comparisons (waits on #11929)

*All eight NFL division races on one card, each with how far it moved after Sunday's games.*

- **Producer kind:** `register_since_slate` (computed-produced; new, the round-up registry's next kind).
  Parameters: a declared set (a twin register or a list of market ids), the slate whose first start
  dates the earlier observation, all-or-nothing refusal, rows sorted by the size of the change.
- **Member rule:** every division in `NFL_DIVISION_REGISTER`, each row showing its leader now and the same
  leader's blended number at a dated observation before Sunday's first kickoff; all eight or no card
  (#10354, Oct 7 04:16 UTC). The same shape fits any declared set after a slate ("what last night
  changed", handoff §9).
- **Data today:** all 16 registered rows are served: Kalshi 53671–53678 and Polymarket 2248388, 2248389,
  2248391, 2248392, 2248395, 2279147, 2279151, 2279152. The four-division round-up is live at seat 12
  (revision 2122830944: NFC East Giants 51%, AFC West Broncos 49.75%, NFC North Bears 36.5%, NFC South
  Panthers 31.75%). Neither endpoint holds a dated pre-Sunday value: 1 of the 48 division outcomes in
  browse carries a movement number (Browns −0.1 on 2248389). The NFC South is a tie in the blend
  (Panthers and Buccaneers both 31.75), and the venues disagree on its leader (Kalshi Carolina
  32.5–31.5, Polymarket Tampa Bay 32.0–31.0). The NFC East row was observed at 09:29 UTC, about 14 hours
  before the read.
- **Five definitions from today's data** (all refuse today: no dated pre-slate value):

  | Definition | Members today | Today |
  |---|---|---|
  | `roundup-nfl-divisions-since-sunday` | `NFL_DIVISION_REGISTER`, the 16 rows above, both venues | refuses |
  | `roundup-nba-divisions-since-the-weekend` | Kalshi 52755683–86, 52755688, 52755689 (six divisions, one venue in the read) | refuses |
  | `roundup-nhl-divisions-since-the-weekend` | Kalshi 59164859–62; Polymarket lists two of the four (65682566, 65682569), unverified, so one venue | refuses |
  | `roundup-ufc-champions-after-ufc-334` | 114171, 114173, 114175 (the feed's UFC theme); slate UFC 334, Nov 14 (`event:ufc:26nov14`, Ciryl Gane vs Josh Hokit, the heavyweight row's top two at 69.5% and 30.25%) | refuses |
  | `roundup-congress-after-election-night` | Senate 108620, House 108621 (joint control 108619 stays separate, Oct 8) | refuses; the election is tonight |

- **Waits on:** #11929 and NOW #10, plus an observation bracketing the slate (Root §5: say "after Game N",
  not "because of Game N"). Also on settled handling: the first clinch (AFC South: Jaguars 84.5% on
  Kalshi, 86.5% on Polymarket) refuses the register today, and December is when clinches start
  (decision E).
- **Refusal rule:** no card unless every member blends (or is declared one-venue) and both observations
  exist for each. A row whose leader changed names both teams and passes `rank_claim_is_evidence`. A tie
  at either end prints as a tie, never as a leader.
- **Card at 390 px:** kicker "NFL · AFTER SUNDAY" · title "How every division moved" · eight one-line
  rows, largest change first, each "AFC West · Broncos 50% · from ‹then›%" · footer "Bain Luck blend ·
  Sunday morning and now" · tap opens the eight divisions as field cards in the same order. No "then"
  value exists today.
- **TRUTH risk:** a leader named on a tie (the live round-up already labels the NFC South "Panthers" at a
  blended tie); a blend now compared with a one-source number then; one row 14 hours old inside a "since
  Sunday" card.
- **Rank 1 · 78.** TRUTH gate: out until #11929.

### 1.3 Same market, many subjects: the Oct 7 sibling rule

*One market asked about many subjects, one row each: "Will it snow by November 15?", a row per city.*

- **Producer kind:** `sibling_family` (sibling-family, the seventh kind of decision A; new). Parameters:
  the template (found by the system, ruling 145; the key folds case and spacing), the fixed dimensions
  (deadline from the venue's terms, rung, stage), the leading-deadline rule (decision A), at least three
  members with a number, and a container holding the family's other deadlines.
- **Member rule:** markets from one venue whose titles share one template and differ in exactly one
  contiguous run, the row subject, with every fixed dimension proven equal, shown at one deadline (#10354,
  Oct 8; ruling 145's detector bars).
- **Data today:**
  - Snow (Polymarket), by Nov 15: 10 cities (60084869, 60087426–31, 60087433–35), 7 with a number, 3
    without (Detroit 60087430, Minneapolis 60087433, Pittsburgh 60087434). By Nov 30: 17 cities
    (60084870–76, 60087436, 60087438–42, 60087445–46, 60087449, 60104328), 16 with a number; Cincinnati
    60087439 has none. By Oct 31: Denver 60084867 and Salt Lake City 60084868, deadline passed, still
    open at 2.3% and 3.8%. The provider's combined market 60084865, "First snow of the 2026 season"
    (31 outcomes), repeats the binaries' numbers (Denver by Nov 30 is 97.1 in both).
  - December snow totals (Kalshi): 12 city ladders, "Snow in ‹city› in Dec 2026?" (65536370–74,
    65536386–87, 65536392, 65536396–98, 67804410), share the rung "Above 4 inches": Minneapolis 81.5,
    Pittsburgh 59.5, Denver 59.5, Milwaukee 59.0, Detroit 56.0, Chicago 52.5, Boston 49.0, Trenton 37.0,
    New York City 27.0, Philadelphia 25.0, Washington DC 11.5, Seattle 10.5. Denver's own ladder
    (65536371) prints Above 6 at 64.0, over Above 4 at 59.5.
  - GTA VI album features (Polymarket): 12 markets, "Will ‹artist› be featured on GTA VI: The Album?"
    (ids 61321729 to 61363937), one stored deadline (Nov 26), 2 without a number (Drake 61341730,
    Nettspend 61363931); highest Kodak Black 83.5 (61353752) and Don Toliver 78.5 (61361196).
  - Families the rule must refuse as served today. **TIME Person of the Year 2026:** 28 per-person
    binaries carry three stored resolution dates for one title year (20 on Dec 31, 2026; 3 on Jan 1,
    2027: 64176469, 64176470, 66179158; 5 on Jul 1, 2027: 27467307–09, 27467312–13). **"Announce a
    presidential run before 2028":** 71 markets split four ways by "Presidential" against "presidential"
    and by stored date, Dec 31, 2026 against Jan 1, 2028 (34 / 15 / 17 / 5). **Kalshi "‹player› Next
    Team" (Dec 1):** 25 markets, 4 with no number (68163519, 68173983, 68505542, 68843561), 4 whose shown
    top three alone pass 105% (Saquon Barkley 67541294 at 181.5, Josh Downs 67877054 at 158.0, Kayvon
    Thibodeaux 12821421 at 126.0, Rashid Shaheed 3452980 at 105.5).
  - Feed: no family card. 10 of the 95 standalone futures are "Senate Combo: …" (seats 68, 71, 72, 74,
    75, 80, 81, 82, 90, 91), all settling tonight; five are stock-hit markets whose thresholds differ
    (seats 28, 33, 55, 106, 107), so they are not one family. Alex graded this shape 2 of 2 in the
    October slates; cohort-compare has been the first presentation kernel since Jul 27.
- **Five definitions from today's data:**

  | Definition | Members today | Today |
  |---|---|---|
  | `snow-first-flakes-2026` | "Will it snow in ‹city› by ‹date›?": Nov 15 (10 cities, 7 numbered), Nov 30 (17, 16 numbered) | card under decision A (Nov 15 leads); refuses under the default (two open deadlines) |
  | `gta-vi-album-features` | the 12 markets above, one deadline (Nov 26), 10 numbered | card |
  | `who-announces-before-2027` | 71 Polymarket markets with one stored date (Jan 1, 2027), split 39 / 32 by "Presidential" against "presidential"; the same template also runs to Mar 31, Jun 30 and before 2028 | card under decision A with a key that folds case; refuses under the default (other deadlines open) or without case folding (one family read as two) |
  | `rt-scores-this-week` | Kalshi 60481116, 62383659, 65536662 at the shared rung "Above 50" (99.5, 99.5, 58.0), one deadline (Nov 9) | card (three members, the floor) |
  | `december-snow-4-inches` | the 12 Kalshi city ladders above, at "Above 4 inches" | refuses: Denver's ladder is incoherent |

- **Refusal rule:** no card when any fixed dimension cannot be proven equal from the venue's own terms
  (a stored date that disagrees with the title's deadline counts, as with TIME and 2028); when fewer than
  three members at the card's deadline have a number; when any member's own ladder or field is
  incoherent (Denver 65536371; a one-winner field over 100%, as with Next Team); when the differing run
  is longer than the shared part (ruling 145's US Open / Australian Open specimen); when the row
  subjects overlap, as state sets that share states do (recommended, decision D); when a provider's
  combined market and its binaries would both supply rows. A member with no number is never hidden
  (ruling 146): it is named on a "No number yet" line. A member past its deadline shows only its graded
  result.
- **Card at 390 px:** kicker "SNOW · NOV 15" · title "Will it snow by November 15?" (two lines) · rows,
  highest first, each with its own bar on a fixed 0–100 scale: "45% Buffalo", "40% Denver", "34% Salt
  Lake City", "32% Boston", "28% Chicago" · count line "Showing 5 of 10 cities · No number yet:
  Detroit, Minneapolis, Pittsburgh" · footer "Each city is its own market. They don't add up to 100%." ·
  tap opens the container: all ten cities, then Nov 30 as its own section. Nov 15 leads here only under
  decision A's recommendation; the default shows single-deadline families only (GTA VI album today).
- **TRUTH risk:** independent rows read as a race that sums to 100 (the footer carries it, as ruling 143
  requires); a stored date taken for the venue's deadline (the TIME and 2028 splits); one subject's
  incoherent field printed as its view (Next Team); a passed deadline shown as open (Denver and Salt Lake
  City by Oct 31).
- **Rank 3 · 77.**

### 1.4 The yardstick: Alex's cross-topic card

*An unfamiliar market set beside a familiar one. Alex's example (chat, Nov 3): "a Democratic sweep is
less likely than snow in Buffalo".*

- **Producer kind:** `yardstick_pair` (computed-produced over a curated anchor list; new). Parameters:
  the anchor (one familiar market), the bands (within 2 whole points prints "as likely as"; 10 or more
  apart prints "less likely than", decision C), the target pool (fresh binaries from another category),
  no member within 48 hours of its deciding event, the sentence recomputed on every serve. One
  definition per anchor.
- **Member rule:** one market paired with one anchor from a short curated list of familiar markets
  (snow by a date in a named city, GTA 6 on time, a US recession by year end, a December Fed hike), from
  different categories, both fresh, whose whole-number probabilities fall inside a band.
- **Data today:** Alex's sentence is false as served this afternoon. "Democrats sweep" in 2026 Midterms:
  Congress Balance of Power (108619, feed seat 32) is 73.5%; snow in Buffalo is 45.0% by Nov 15
  (60087427) and 67.3% by Nov 30 (60084870). It holds for a different sweep: "Will Democrats sweep the
  New England House and Senate races?" (67804794) at 35.5%, against Buffalo by Nov 15 at 45.0%. The read
  also served "core four" Senate races 66.5% (109685), Republicans sweep the Great Plains 32.0% (67804787)
  and eight Polymarket combinations "Dem sweep & …" (68691899–901, 68691942–46), which are never members.
  Graded: "As likely as" 9 of 16; the "which is likelier" quiz 0 of 6, with 4 "no".
- **Five definitions from today's data:**

  | Definition | Anchor · today's pair | Today |
  |---|---|---|
  | `for-scale-snow-in-dc` | snow in Washington, DC by Nov 30, 39% (60104328) · Pete Hegseth out as Secretary of Defense by Dec 31, 39% (8422080) | card |
  | `for-scale-snow-in-buffalo` | snow in Buffalo by Nov 15, 45% (60087427) · Banksy creates a new mural or street artwork by Dec 31, 45% (30587891) | card |
  | `for-scale-gta-6-on-time` | GTA 6 released on time, 96% (67804637) · next Fable model (5.2+) released by Dec 31, 96% (61380906) | card |
  | `for-scale-us-recession-2026` | US recession by end of 2026, 5.5%, prints 6% (113012) · the Iranian regime falls before 2027, 4.5%, prints 5% (113200) | card |
  | `for-scale-december-fed-hike` | a quarter-point Fed hike in December, 74.5% on both venues, prints 75% (Kalshi 109657, Polymarket 57574250) · next GPT Image model (2.6+) released by Dec 31, 74% (65087988) | card |

  A sixth shows the refusal working: snow in Boston by Nov 30 (60087436) and Democrats sweep the "core
  four" (109685) both sit at 66.5%, and the pair refuses because the sweep is decided tonight.
- **Refusal rule:** no card when the whole numbers sit between the bands (3–9 points apart: no claim
  either way); when either member has no number or is older than its freshness bound; when either
  member's deciding event is within 48 hours (tonight's election markets, although 108619's stored
  resolution date is Feb 1, 2027); when either is a combination, path, mention or daily-ladder market;
  when both come from one category (then it is not cross-topic); when the anchor's deadline has passed.
  The sentence is recomputed from the two live numbers on every serve, never cached as text.
- **Card at 390 px:** kicker "FOR SCALE" · title, computed: "Pete Hegseth out by Dec 31: as likely as
  snow in DC by Nov 30" (three lines) · rows: "39% Pete Hegseth out as Secretary of Defense by Dec 31",
  "39% Snow in Washington, DC by Nov 30" · footer "Two unrelated markets with the same chance." · tap
  opens a two-member container. The computed headline is a new card element, so ruling 047's design
  ruling comes first.
- **TRUTH risk:** the sentence is a claim that a move of a few points can falsify, and Alex's own example
  is false today; it implies a link between unrelated things (the footer denies one); "familiar" is
  regional (snow in Buffalo means little in Phoenix); a market's deciding night can sit months before its
  stored resolution date (108619).
- **Rank 5 · 68.** TRUTH gate: passes only with serve-time recomputation and the refusal bands; a
  cached sentence is an open way to print a false one.

### 1.5 The deadline ladder

*One proposition at several deadlines: Starship Flight Test 15 launches by Nov 15 (10%), by Nov 30
(85%).*

- **Producer kind:** `deadline_family` (shipped, #11864; `deadline_family_story.verify_and_select_deadline_family`).
  Parameters: one provider group, rule equivalence proven from the rule text stamped at ingest
  (`deadline_rule_contract`), cumulative "by" deadlines, and a representative rung chosen by
  `largest_supported_dated_move` or `nearest_50_pct_fallback`. A single market's dated rungs already
  render as the heatmap card (ruling 047).
- **Member rule:** the rungs of one proposition, from one venue, that differ only in a cumulative "by
  ‹date›" deadline (never "on"), with rule equivalence proven from the venue's terms, in date order on
  one card.
- **Data today:** the deadline-family card made no bundle in today's feed; all 11 theme bundles are
  grouped by story key. One-market date ladders already render as one card: 30 markets in the reads
  show at least two dated rungs (feed examples: Russia x Ukraine ceasefire 20569379, US imports Russian
  diesel 65080963, Trump declares a national emergency 59693686, Houthis enter Aden 60710686, Putin out
  112896). Across markets, the reads hold 122 same-venue, same-title families with two or more deadlines,
  106 of them with at least two numbers. One of the 106 is a single deadline written two ways (Trump
  resign "before 2027" 2.05%, 113291, against "by December 31, 2026" 1.85%, 112927). Of the other 105, 104
  run in order and one runs backwards: Barack Obama announces a run before 2027 2.95% (13792241), before
  2028 2.25% (58336017), so 3% and then 2% in whole numbers. Inside one market, "Kansas Governor loser concedes?" (68845561) prints November 3
  at 90.0% over November 4 at 81.5%; the feed serves it at seat 93 under "Big odds movement". Graded:
  "Clock" 6 of 16, 2 of 10 in v2 ("use sparingly").
- **Five definitions from today's data** (provider groups are not visible in browse, so admission is
  the shipped verifier's call):

  | Definition | Rungs today | Today |
  |---|---|---|
  | `starship-flight-15` | by Nov 15, 9.5% (63727104) → by Nov 30, 84.5% (63355246); combined market 63097616 | candidate |
  | `government-shutdown-december` | by Dec 12, 31.5% (68064290) → by Dec 31, 43.5% (68064291); combined market 68056249 | candidate |
  | `gta-vi-on-pc` | Dec 31, 2026: 7% (67903133) → Mar 31, 2027: no number (67903132) → Jun 30, 2027: 68% (63404463) → Dec 31, 2027: 82% (63404464) | candidate |
  | `next-claude-opus` | by Nov 30, 59.5% (62141888) → by Dec 31, 88.5% (62162058) | candidate |
  | `russia-ukraine-ceasefire` | by Nov 30, 6.5% (61340822) → by Dec 31, 2026, 16.5% (20569380); combined market 20569379 (19 rungs, up to Dec 31, 2027 at 70.5%) | candidate |

- **Refusal rule:** no card when a later rung is lower than an earlier one at whole-number precision
  (Obama, Kansas); when rungs mix "on" and "by" (Kalshi's "Government shutdown on Dec 12, 2026?",
  62383608 at 38.5%, is a different proposition and reads above the "by Dec 12" rung); when one rung
  could come from two representations (the combined market 63097616 shows Flight 15 by Nov 30 at 83.0,
  its binary 63355246 at 84.5); when fewer than two future rungs have numbers. A rung past its deadline
  shows only its graded result, and no "falling" language in a dated market's last 30 days (handoff §4).
- **Card at 390 px:** kicker "BY WHEN" · title "Starship Flight Test 15 launches" (two lines) · rows in date
  order: "by Nov 15 · 10%", "by Nov 30 · 85%" (a strip, as the heatmap card draws it) · footer "Each date is
  its own market. A later date includes the earlier ones." · tap opens the family, each rung's own market
  one tap further.
- **TRUTH risk:** a backwards ladder printed as one (two found today, one already a feed card); "on" and
  "by" read as one curve. The Oct 7 rule keeps deadlines apart for siblings; a ladder is the other axis
  (fixed subject, varying deadline), and outside #11864's verified path that is unruled (decision B).
- **Rank 8 · 63.** It is shipped: its slot would widen supply, not add a type.

### 1.6 Same deadline, different worlds (found: #10354, Oct 6 grades)

*Unrelated markets that settle on the same day, ranked: "By December 31". Alex's grades on #10354: 13 of 17
"amazing", the strongest cross-topic shape tested.*

- **Producer kind:** `same_deadline_board` (computed-produced; new). Parameters: the deadline (one calendar
  day), four to six members, at least three categories, numbers between 5% and 95%, one member per
  template, subject or story, the exclusion classes, highest first.
- **Member rule:** four to six binary markets from at least three categories whose stated deadline is
  the same day, each with a number between 5% and 95%, no two from one template, subject or story,
  highest first (handoff §2 and §5's standing filters).
- **Data today:** browse returns 802 results for "by December 31" and 563 for "before 2027". Of the 400
  read (all stored Dec 31, 2026 or Jan 1, 2027), 355 are binaries with a number, 184 sit between 5% and
  95%, and 132 remain after one-per-template (a coarse pass; a strict one drops about a dozen "attend a
  US x Iran diplomatic meeting" rows): 124 from one venue (Polymarket), 8 from Kalshi. Categories of the
  400: politics 118, geopolitics 103, economics 92, tech 55, entertainment 19.
- **Five definitions from today's data:**

  | Definition | Members today (examples) | Today |
  |---|---|---|
  | `by-november-15` | all 39 listed read; 25 binaries in the band, 4 categories (seven are one snow family): Gemini Carbon released 80% (67817888), Riyadh airport reopens 46% (67811387), snow in Buffalo 45% (60087427), US imports Russian diesel 28% (67917560), Starship Flight Test 15 launches 9.5% (63727104) | card |
  | `by-november-30` | 200 of 265 listed read; 113 binaries in the band, 9 categories: Anthropic IPO 85% (61341170), Trump meets with Putin 83.5% (62611724), a 7.0+ earthquake worldwide 66% (68320839), next Claude Opus 59.5% (62141888), another GTA VI trailer 17% (66907859), Novak Djokovic announces his retirement 5.25% (63790740) | card |
  | `by-december-31` | the 132 above: next Claude Opus (5.6+) 88.5% (62162058), Trump meets with Putin 84% (27594137), a new Banksy mural 45% (30587891), Starship fully reusable 44% (113322), Pete Hegseth out 39% (8422080), Samuel Alito announces his retirement 17% (13794660) | card |
  | `by-end-of-2027` | across all 27 reads, 75 binaries in the band, 68 of them one template; one per template and subject leaves PC version of GTA VI 82% (63404464), Starship fully reusable 77% (34753769), US recession 33% (58605173), Scottie Scheffler wins the grand slam 5.5% (Kalshi 176) and one "announce a run" row | card |
  | `settles-tonight` | 24 feed futures settle Nov 3: 22 politics (among them 60605472, 60527868, 61307343, 61149421, 60008834) and two 15-minute gold and silver markets (68836827, 68836828), an excluded class | refuses: one category |

- **Refusal rule:** no card with fewer than four members or three categories; a member whose deadline
  wording differs from the board's ("on", "in 2026") or whose stored date disagrees with its title; a
  member from the excluded classes (mention, statement, daily, financial, combination or path markets;
  foreign elections; a named person's death, health or crime); a member without a number or past its
  deadline; two members that are one claim (the two Trump-resign markets in §1.5).
- **Card at 390 px:** kicker "SAME DEADLINE" · title "By December 31" · rows, highest first, each the
  market's own words with "Will … by December 31?" dropped: "89% Next Claude Opus (5.6+) released",
  "84% Trump meets with Putin", "45% Banksy creates a new mural or street artwork", "44% SpaceX Starship
  fully reusable", "39% Pete Hegseth out as Secretary of Defense" · count line "Showing 5 of 6" · footer
  "Separate markets that settle by the same day." · tap opens all six.
- **TRUTH risk:** a plain-English restatement that changes the terms (the slates' checker rewrote 31 of
  101; rows therefore use the market's own words, ruling 145 item 3); "by", "on" and "in" read as one
  deadline; one venue read as a blend (124 of 132 candidates are one venue, and the glyph has to say so);
  unrelated rows read as related.
- **Rank 2 · 78.**

### 1.7 Two rivals, one market (found: ruling 143)

*Two named subjects asked the same thing, both numbers on one card: "Who wins a second major this
year?"*

- **Producer kind:** `sibling_family` with `closed_world: true` and exactly two members: §1.3's kind, not
  a new one.
- **Member rule:** exactly two markets of one template about two subjects in a set that is closed by
  construction (ruling 143's approved-final reading), both with a number, the card naming no answer and
  printing both legs unnormalized.
- **Data today:** the ruling's own template has a 2027 edition, Kalshi "Carlos Alcaraz: Grand Slam wins in
  2027" (66937562) and "Jannik Sinner: Grand Slam wins in 2027" (66937563), and both are served with no
  number on any rung. Graded: one market across several subjects 2 of 2 and "Head to head" 1 of 1, scarce
  then and now.
- **Five definitions from today's data:** today's reads hold one closed pair. Four near misses show why
  the list stops there rather than inventing closed worlds:

  | Definition | Members today | Today |
  |---|---|---|
  | `alcaraz-sinner-two-majors-2027` | Kalshi 66937562, 66937563 | refuses: no number on either leg |
  | `nba-mvp-doncic-wembanyama` | one field market per venue (52755650, 66031970), not two markets | not this kind: the field card shows both |
  | `texas-senate-talarico-paxton` | one two-outcome market (109065) | not this kind: the existing card shows both |
  | `sweeps-core-four-vs-great-plains` | 109685 and 67804787: two different races | refuses: not one market |
  | `gta-album-kodak-black-vs-don-toliver` | 61353752 and 61361196, with ten more artists in the family | refuses: not closed, so §1.3 |

- **Refusal rule:** no card while either leg has no reading (CERT-430), with the missing subject named in
  the payload (`unpriced_legs`); legs never normalized; no card when a third subject could join (then it
  is §1.3).
- **Card at 390 px:** kicker "HEAD TO HEAD" · title "Who wins a second major in 2027?" (two lines) ·
  rows "Alcaraz ‹n›%", "Sinner ‹n›%" (no numbers today) · hook "Separate markets: both could do it, or
  neither." (ruling 143 item 4) · tap opens both ladders.
- **TRUTH risk:** a one-legged comparison reading as an answer, the defect CERT-430 caught after ship; a
  renamed row without its recorded rename (ruling 143 item 3).
- **Rank 7 · 63.** Recommended as a variant of §1.3, not its own week.

### 1.8 The biggest surprises (found: rulings 101, 103, 107, 114; waits on #11929)

*Settled markets ranked by how far the result landed from the last number before it.*

- **Producer kind:** `settled_surprise` (time-boxed-tonight, rolling 7 days; new). Parameters: the
  population (a collection, a theme or a family), the window, the mark (the last blended number captured
  before the result, ruling 103), 30 days of seat history, quiet rows kept.
- **Member rule:** markets settled by a venue grade or a final score in the last seven days that held a
  Discover seat in the 30 days before, ranked by |result − the last blended number captured before the
  result| (ruling 101's surprise key). That number must predate the answer (ruling 103), and rows graded
  without a verdict are not ranked (ruling 101's WITHHOLD residual).
- **Data today:** browse lists open markets only, and the feed carried no settled futures card at 3:19 PM.
  The 22 politics cards in the feed settling tonight are the first natural population. The last number before
  the result is #11929's problem: Kalshi legs off the stream were charted every two hours, and #11924
  restores the live number but not the history (#11929, cause 3).
- **Five definitions from today's data** (all refuse today: nothing graded yet, and the mark needs
  #11929):

  | Definition | Population today | Today |
  |---|---|---|
  | `surprises-election-night-2026` | the Midterms collection's 14 (catalog P2) and the 22 politics futures in the feed settling Nov 3 | refuses |
  | `surprises-ballot-measures-2026` | feed 60527868, 60605472, 61307343, 61149421; catalog #37's 63522669, 63522679, 63522680, 63522681, 63528458, 63528460 | refuses |
  | `surprises-first-snow-nov-15` | the 10-city Nov 15 family (§1.3) | refuses until graded |
  | `surprises-worlds-2026` | Worlds 2026 Champion (Kalshi 63135157), Finals MVP (Kalshi 63135159, Polymarket 60552214) | refuses until graded (stored Nov 15 and Nov 29) |
  | `surprises-rt-this-week` | Kalshi 60481116, 62383659, 65536662; Polymarket 64564200, 65563521, 67734827 | refuses until Nov 9 |

- **Waits on:** #11929 for the pre-result number, and a clean week of settlement sentinels (Fable's note
  on #11905 about "Decided this week").
- **Refusal rule:** no row without a venue grade or a final score; no row whose last pre-result number
  was captured after the result or was past its freshness bound when the result came; no surprise number
  printed, because the order is the explanation (ruling 107); quiet rows stay (ruling 114).
- **Card at 390 px:** kicker "SETTLED THIS WEEK" · title "The biggest surprises" · rows in ruling 107's
  shape, "‹market› · Marked ‹n›% — and it passed", using the settled words of standing ruling 2 · footer
  "Ordered by how far each result landed from the last number before it." · tap opens the settled cards.
- **TRUTH risk:** a wrong grade at the top of the card (Hot List #21 and #33; a Polymarket market grades
  only when every outcome sits at 0 or 1); a number captured after the answer posing as the mark (ruling
  103).
- **Rank 6 · 67.** TRUTH gate: out until #11929 and the settlement sentinels.

### 1.9 New favorite (found: PRODUCT-BRAIN Aug 7 mover headlines, catalog #32; waits on #11929)

*Where the leader of a field changed this week.*

- **Producer kind:** `leader_change` (story-movement; new as a producer, named for the highlight signal it
  reuses: `futures_highlights.py` weights `leader_change` and labels it "New favorite"). Parameters: the
  field (one market, or a register of twins), a 7-day window, a margin of at least 2 whole points at both
  ends, and the evidence gate `rank_claim_is_evidence` in the same file.
- **Member rule:** field markets whose printed leader changed within seven days, both leaders' numbers
  dated observations of the same displayed quantity, the change passing the evidence gate, and the new
  leader ahead by at least 2 whole points.
- **Data today:** neither endpoint carries a prior leader. Graded 1 of 3, "promising for sports" (the
  Rays overtaking the Yankees).
- **Five definitions from today's data** (all refuse today: no prior leader):

  | Definition | Field today | Today |
  |---|---|---|
  | `new-favorite-nfl-mvp` | Kalshi 40532 (Josh Allen 29.5, Joe Burrow 20.5); Polymarket 7585490 (32.0, 14.9) | refuses |
  | `new-favorite-nba-mvp` | Kalshi 52755650 (Luka Doncic 31.0, Victor Wembanyama 28.5); Polymarket 66031970 (34.75, 30.5) | refuses |
  | `new-favorite-heisman` | Kalshi 189 (Darian Mensah 35.0, Jeremiah Smith 24.5); Polymarket 57792807 (32.5, 25.0) | refuses |
  | `new-favorite-time-person-of-the-year` | Kalshi 109264 (Zohran Mamdani 30.5, Pope Leo XIV 19.5); Polymarket 27467306 (32.5, with Mark Carney second at 18.5) | refuses |
  | `new-favorite-stanley-cup` | Kalshi 52755659 (Carolina and Colorado 9.77 each: a tie the seat-16 headline, "Carolina Hurricanes at 10%", gives to Carolina) | refuses |

- **Waits on:** #11929.
- **Refusal rule:** no row with a margin under 2 whole points at either end, a change caused by a source
  entering or leaving the blend (#5440), or a prior leader with no number (#8784).
- **Card at 390 px:** kicker "NEW FAVORITE" · title "‹market›" · rows "‹new leader› ‹n›%", the italic
  connector "has overtaken", then "‹old leader› ‹m›%" (the slate's two-outcome design) · footer "Leader
  on ‹date› and now." · tap opens the field.
- **TRUTH risk:** a flip on a near-tie reported as news (NFC South, the Stanley Cup); a change made by the
  blend's sources, not the market.
- **Rank 10 · 59.** TRUTH gate: out until #11929.

### 1.10 This week's tournaments (found: #10354, Oct 8 16:21 UTC, option A)

*Every tournament of one sport this week on one card: golf's this week, tennis's when dated.*

- **Producer kind:** `week_events` (event-derived; new, the weekly sibling of `window_events_closest`).
  Parameters: the sport, the play week, two to four rows, dates from the tournament's `start_date` and
  `end_date` (never `commence_time`), one row per tournament.
- **Member rule:** the tournaments of one sport whose play overlaps the same week, one row each with its
  leader, number and dates, and no container when all rows are visible (Alex's option A, part 3,
  recorded by Root).
- **Data today:** golf in the feed: Abu Dhabi Aldar Championship (seat 78, "Rory McIlroy leads at
  10.3%") and World Wide Technology Championship (seat 79, "Ben Griffin leads at 4.7%", plus its theme
  bundle at seat 66), both dated Nov 5–8; TOTO Japan Classic Winner (68977820, seat 104) prints Andrea
  Lee, Aihi Takano and Yealimi Noh at 50.0 each and has no dated tournament card. Tennis: WTA Chennai
  twice (68662981 at seat 84, 68660446 at seat 105), WTA Hong Kong (68660445, seat 95) and ATP Paris
  (68356564, seat 96), winner markets with no play dates in either endpoint.
- **Five definitions from today's data:**

  | Definition | Members today | Today |
  |---|---|---|
  | `golf-this-week` | Abu Dhabi Aldar Championship and World Wide Technology Championship (Nov 5–8); TOTO's row refused | card with two rows |
  | `tennis-this-week` | WTA Chennai (68662981, 68660446), WTA Hong Kong (68660445), ATP Paris (68356564) | refuses: no dates |
  | `ufc-this-weekend` | `event:ufc:26nov06` and `event:ufc:26nov07ufcfightnight`, both Nov 7 22:00 UTC, likely one event twice | refuses: one event |
  | `motorsport-this-weekend` | MotoGP Grand Prix of Malaysia, Nov 8 (66764078: Marc Marquez 80.0) | refuses: one event |
  | `esports-this-week` | Worlds 2026 (63135157), IEM Beijing 2026 (68781893), 1win Essence III (68788272) | refuses: no dates |

- **Refusal rule:** no row for a field whose leaders cannot all be true (three players at 50.0 is not a
  field) and, below two valid rows, no card; no row without published dates (Korn Ferry, Oct 8); one row
  per tournament when two venues list it.
- **Card at 390 px:** kicker "GOLF · THIS WEEK" · title "Two tournaments" · rows "Abu Dhabi Aldar
  Championship · Nov 5–8 · Rory McIlroy 10%", "World Wide Technology Championship · Nov 5–8 · Ben Griffin
  5%" · no count line, all rows shown · each row opens its tournament page, as theme-bundle members do
  today; whether the card itself is a tap target is part of ruling 047's design ruling (ruling 147).
- **TRUTH risk:** a date read from `commence_time` (16:10:46 and 16:01:03 UTC on today's two golf cards,
  not whole minutes, which is ruling 042's sign of an invented time) instead of `start_date`/`end_date`;
  placeholder fields (TOTO); one tournament or card shown twice (Chennai; the two Nov 7 UFC cards).
- **Rank 9 · 60.**

---

## 2. The ranking

### 2.1 Criteria, unchanged from the container catalog (§2.1 there)

Each criterion is scored 1–5; **score = Σ(weight × score) / 5**, range 0–100. **R** reader value 30 ·
**D** data readiness 25 · **S** settlement behaviour 15 · **F** freshness 10 · **C** cost to produce 10 ·
**V** variety added to Discover 10. **The TRUTH gate sits outside the score:** a type with an open,
unmitigated way to show a wrong number does not ship, whatever it scores. Alex's slate grades inform R;
they are one rater on venue numbers. The five definitions inform D. Ties break by R, then D (the
catalog's rule), then S (added here).

### 2.2 Scores

| Rank | Type | Producer kind | R | D | S | F | C | V | Score | Definitions making a card today | Gate |
|---:|---|---|:-:|:-:|:-:|:-:|:-:|:-:|---:|---|---|
| 1 | Every division since Sunday | `register_since_slate` | 5 | 3 | 3 | 4 | 3 | 5 | 78 | 0 of 5 | waits on #11929 |
| 2 | Same deadline, different worlds | `same_deadline_board` | 4 | 4 | 4 | 3 | 3 | 5 | 78 | 4 of 5 | none |
| 3 | Same market, many subjects | `sibling_family` | 4 | 4 | 3 | 4 | 3 | 5 | 77 | 2 of 5; 4 with decision A and case folding | none |
| 4 | Movers | `dated_movers` | 5 | 2 | 3 | 5 | 3 | 5 | 75 | 0 of 5 | waits on #11929 and NOW #10 |
| 5 | The yardstick | `yardstick_pair` | 3 | 4 | 2 | 5 | 2 | 5 | 68 | 5 of 5 | serve-time recomputation |
| 6 | The biggest surprises | `settled_surprise` | 4 | 2 | 3 | 4 | 3 | 5 | 67 | 0 of 5 | waits on #11929 and settlement sentinels |
| 7 | Two rivals, one market | `sibling_family` (closed pair) | 4 | 2 | 3 | 2 | 4 | 4 | 63 | 0 of 1 | none |
| 8 | The deadline ladder | `deadline_family` (shipped) | 3 | 3 | 4 | 3 | 4 | 2 | 63 | 5 candidates; none in today's feed | none |
| 9 | This week's tournaments | `week_events` | 3 | 2 | 4 | 4 | 3 | 3 | 60 | 1 of 5 | none |
| 10 | New favorite | `leader_change` | 3 | 2 | 3 | 4 | 3 | 4 | 59 | 0 of 5 | waits on #11929 |

Membership kinds (catalog §4.1): `register_since_slate`, `same_deadline_board` and `yardstick_pair` are
computed-produced; `sibling_family` is sibling-family; `dated_movers` and `leader_change` are
story-movement; `settled_surprise` is time-boxed-tonight; `week_events` is event-derived; `deadline_family`
is a feed bundle today, sibling-family on the deadline axis if decision B makes it a container.

### 2.3 What the ranking says

- **#11929 gates half the value.** Three of the top six compare two times, and none of their fifteen
  definitions can make a card before #11929 and NOW #10. The best of them (every division since Sunday)
  also meets clinch season in December.
- **The two ungated leaders are one-venue and make no blend claim.** The board and the sibling family
  run on markets one venue lists, so neither needs a twin register (only two exist). Both fit the
  existing theme-bundle path, and their definitions fill today: 4 of 5 boards, 2 of 5 families (4 of 5
  with decision A and a case-folding key).
- **The yardstick fills easily and fails easily.** All five anchors found a pair today, and Alex's own
  sentence is false this afternoon. Its supply is not the risk; its sentence is.
- **Supply, not shape, limits the shipped and event types.** The deadline-family card and the swings
  bundle are in code and made no card today; `week_events` fills one definition of five because only golf
  carries published dates.
- **The cross-topic idea is better served by the board than by the sentence.** The board's 13 of 17 beats
  the yardstick's 9 of 16, and the board carries no claim that a few points of movement can falsify.

---

## 3. One type a week, Nov 2 – Dec 13 (a proposal for NOW #11852)

| Week | Dates | Type and first definitions | Condition to start | If the condition fails |
|---|---|---|---|---|
| 1 | Nov 2–8 | In flight: closest games tonight (#11915), CFP picture (#11928) | — | — |
| 2 | Nov 9–15 | Same deadline, different worlds: `by-november-30`, `by-december-31` | the existing group card carries five rows of market words; otherwise a design ruling first (047) | `golf-this-week` (`week_events`) |
| 3 | Nov 16–22 | Same market, many subjects (NOW #7's slot): `gta-vi-album-features`, then `snow-first-flakes-2026` at Nov 30, by then its one open deadline, so it qualifies under either answer to A | decision A, or its default (single-deadline families only) | the GTA VI album family alone |
| 4 | Nov 23–29 | The yardstick, reusing week 2's pool and filters | decision C, and a design ruling for the computed headline (047) | widen `deadline_family` supply |
| 5 | Nov 30–Dec 6 | Movers: `movers-since-yesterday` | #11929 and NOW #10 clear by Nov 27 | `golf-this-week` |
| 6 | Dec 7–13 | Every division since Sunday: `roundup-nfl-divisions-since-sunday` | #11929 clear and decision E ruled | the biggest surprises, after a clean week of settlement sentinels; else two rivals folded into week 3's kind |

Definitions are data, so each week instantiates its kind on that week's markets: several of today's
definitions (`rt-scores-this-week`, `by-november-15`) settle before their week comes. New favorite is held
until Movers has run, since it reads the same dated history.

---

## 4. Folded, shipping, or rejected

- **Story themes** (11 in today's feed; Congress uses two-sided rows, Oct 8): shipping, not new.
- **Round-ups by producer kind** (closest N, field band): in flight, week 1.
- **The line** (one subject's threshold ladder shown at its pivot rung; rulings 105, 111, 112): a
  formatting rule inside a card, already ruled for the props rail. Across subjects it is `sibling_family`
  at a shared rung, as `december-snow-4-inches` and `rt-scores-this-week` show.
- **Shared-rung comparison bundles** (`PUBLIC_COMPARISON_BUNDLE_THEMES`): in code, no card today. The
  Rotten Tomatoes renderer had no admitted specimen on Oct 22 (#10357), and two of this week's three
  Kalshi films (60481116, 62383659) print 99.5% on every shown rung. `sibling_family` covers the shape.
- **Cohort-compare** (Jul 27 kernel): §1.3.
- **The swing** (one market, one outcome up and one down; 1 of 2 graded) and **dead heat** (1 of 3): fold
  into Movers and §1.3's ordering.
- **Series state / what last night changed** (handoff §9): `register_since_slate` is its kind.
- **Rejected by the slates themselves:** reversal ("guess which is likelier", 0 of 6, 4 "no"), dossier
  (0 of 6), trading places (0 of 2), the path (0 of 3, 3 "no"; it lives on team pages); checklist (1 of 4)
  and same odds (3 of 7, fading) as filler only.
- **Excluded from every type:** mention and statement markets, daily and financial ladders, combination
  and path markets (catalog §5, items 2 and 6). Today they lead the feed's movement headlines.

---

## 5. Decisions for Alex

Each has a recommendation and the default that holds until ruled.

- **A. Which deadline leads a sibling family?** Unruled since #10354 (Oct 8 00:48 UTC). *Recommend* the
  nearest open deadline with at least three members that have a number (snow: Nov 15, 7 of 10).
  *Default:* only families with a single open deadline get a card (the GTA VI album qualifies; snow
  waits).
- **B. Deadline ladders across separate markets.** The Oct 7 rule keeps deadlines apart for siblings, and
  a ladder is the other axis. *Recommend* one card only through #11864's rule-equivalence proof, never
  by title match. *Default:* only the shipped path.
- **C. The yardstick's sentence.** *Recommend* "as likely as" only (whole numbers within 2 points), and
  "less likely than" only after one reader check, because the nearest tested format ("which is likelier")
  graded 0 of 6. *Default:* no yardstick card.
- **D. Row subjects that overlap** (state sets sharing states, as in "Senate Combo"). *Recommend* refuse.
  *Default:* refuse.
- **E. A clinched NFL division.** Late-season wording is reserved to Alex (#10354, Oct 7). *Recommend*:
  on "every division since Sunday", a clinched division stays as a settled row showing its winner; on the
  four-closest round-up, it leaves the selection and the footer counts open divisions. *Default:* both
  cards refuse once any division clinches, as the register does today.

---

## 6. Observations from the reads (reported, not diagnosed)

Measurement belongs to the measurement lane (ruling 134); these are listed for whoever owns each, not
filed.

- "Kansas Governor loser concedes?" (68845561) prints November 3 at 90.0% above November 4 at 81.5% and is
  served at feed seat 93 under "Big odds movement".
- "Snow in Denver in Dec 2026?" (65536371) prints Above 6 inches at 64.0% above Above 4 inches at 59.5%.
- TIME Person of the Year binaries carry three stored resolution dates for one title year; "announce a
  presidential run before 2028" carries two stored dates and two spellings of "presidential".
- WTA Chennai is served as two standalone cards (68662981, 68660446), and two UFC concept cards
  (`event:ufc:26nov06`, `event:ufc:26nov07ufcfightnight`) share one start, Nov 7 22:00 UTC.
- TOTO Japan Classic Winner (68977820) prints three players at 50.0% each.
- Today's golf tournament cards carry `commence_time` values that are not whole minutes (16:10:46 and
  16:01:03 UTC) beside whole-day `start_date`/`end_date` values (Nov 5–8).
- The deadline-family card and the swings bundle produced no card in today's feed.
- Two NFL MVP fields were served at 3:22 PM (Kalshi 40532 "MVP Winner?", Polymarket 7585490); the container
  catalog's 06:50 read reported none (its #27).
- Two leaders are named on ties: the live round-up labels the NFC South "Panthers" (31.75 each in the
  blend), and the seat-16 headline names Carolina in the Stanley Cup field (52755659, Carolina and
  Colorado both 9.77).
