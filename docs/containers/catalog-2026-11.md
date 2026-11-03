# Container catalog, Nov 2026

**PILLAR:** DISCOVER, with TRUTH as the gate. **SHIP this unblocks:** a reader sees new round-up
cards on Discover, each opening its own container, without a deploy per container. The stored
definitions of option C (week 3, #10357 Amendment 1) are the means; this catalog is the input that
says which definitions to write first and which kinds the model has to hold.

**Status:** research and design only. No product code, no ruling. Rankings, names and copy below are
recommendations; product, ranking and copy calls stay Alex's (PRODUCT-BRAIN, "THE ONE RULE ABOVE ALL").
Written by Argon at Alex's request, Nov 2–3, 2026. Code read at master `d52ca45a56`. Production read
anonymously from public endpoints on **Tue Nov 3, 2026, 06:50–06:58 PT** (§0.3).

Contents: §0 grounding · §1 the catalog (50, ranked) · §2 the ranking · §3 top 10 as draft definitions ·
§4 kinds for the stored-definition model · §5 ten rejected · §6 open decisions and observations.

---

## 0. Grounding

### 0.1 Rulings this catalog applies

| Source | What it binds here |
|---|---|
| #10357, Oct 7 (04:35 UTC), recorded by Root | Container = **exactly the opening card's members, in the card's order**; numbers on both surfaces from the same verified representation; no canonical hub, no completeness extras, no related section (a related section may come later). Members use the **existing field card**. |
| #10354, Oct 7 (04:16 UTC), recorded by Root | **Blend failures are matching/data defects, not reduced-card states.** Any required member failing → no card, ordinary feed unchanged, failure surfaced through the sentinel path. No partial subset, no single-source fallback. A clinched division is settled, not a defect. |
| #10357, Nov 2 contract §§1–6 (Fable) | Round-up identity: one slug shared by card and container, no date in the slug; computed, not stored; **one function decides both**; revision = CRC32 of the ordered member ids; refusal is a 404 `unavailable`, never an empty page. |
| #10357 Amendment 1 (Alex ruled A, Nov 2, 5:19 PM PT) | Alex: *"are we baking THIS SPECIFIC NFL container into our API?"* → producer registry now, **stored definitions in week 3** with fields: slug, kind, name, category, section title, footer, producer or member rule. |
| #10354, Oct 8 (00:30 and 00:48 UTC), Oct 7 PT D3 sibling rulings | Group only markets that differ in **exactly one thing, the row subject**; title is the shared market, rows keep independent probabilities (**no sum to 100**); different deadlines, thresholds or stages stay separate; a shared story key is not equivalence. **One group card per family at one common deadline; its container holds the family's other deadlines** (explicitly unlike the NFL exact-membership rule). |
| #5105, Oct 8 (00:25 UTC), Oct 7 PT ranking rulings | D1 golf weights unchanged; **D2 no weak variety-only promotion** on a cold-start first page; slice 1 national-winner preference. Oct 8 Option A: a live event without a major, marquee or playoff sign does not get a first-ten seat for being live; three same-weekend golf tournaments are one card. |
| #10354, Oct 8 (03:41 and 04:36 UTC) | Recorded by Root: Awards Season is the positive grouped-card example. Congress: Option A two-sided rows, Senate and House only, joint control separate. |
| Rulings 047, 145, 147 | One card system; a template family is one card **found by the system**; an event shows through **the** event card and the whole card is the target. |
| Rulings 114, 146 | A settled card keeps its quiet rows; an illiquid market is still shown, with an age that says what it is the age of. |
| Rulings 138, 141, 142 | Reader copy says probability, not price; venue names only as attribution of a number, never in narrative; a section states what it **is**, never what it will be. |
| Ruling 148 + standing ruling 1 | In live play Kalshi and Polymarket carry the books' base weight (3.0) in the hero, previews and chart (`app/utils/aggregation.py` `LIVE_MARKET_SOURCES`, `_live_base_weight`). A container showing a live game must show **the hero's number**. |
| Standing rulings 2, 3, 7 | Settled means settled; no betting formats, no dollar volume as social proof; the story is the ranking unit. |

### 0.2 The two reference kinds

**Curated-stored (Midterms 2026).** A committed manifest (`backend/data/collections/midterms-2026.json`,
14 market ids in four sections, `pin_until` 2026-11-07) plus an explicit twin register in code
(`app/utils/midterms_collection.py` `MIDTERMS_TWIN_REGISTER`, 14 entries, 11 paired, three with "no
Polymarket market exists"). The publisher (`backend/scripts/collection_publication.py --curated-manifest`,
`prepare_curated`) writes `contains` edges with the section key as class into a container stored as
`kind = "theme"`, and records the act in the correction ledger. The route reads published edges, hydrates
the cards (`app/services/midterms_collection.py` `load_midterms_cards`) and blends twins per outcome
(`blend_card`). The first official venue result (`resolution_source = "api_settlement"`) replaces the blend.

**Computed-produced (NFL division front-runners).** No row, no edges. `app/utils/nfl_division_register.py`
names eight Kalshi↔Polymarket pairs club by club. `compose_division` refuses on identity, status,
settlement window, outcome set or a fired divergence gate. `discover_bundles.nfl_division_roundup`
(:2888) returns `(feed_item, container_payload)` from one read, cached 60 s. The route branch in
`routes/containers.py` (:454) serves it or 404s. Today the refusal is a `log.warning("flow_sentinel
matching_defect: …")` line, not a filed issue (`tasks/sentinel_filing.py` `reconcile_issue` is the rail
it could use).

**Two meanings of "kind".** The storage vocabulary `container_graph.CONTAINER_KINDS` (:32) says what a
container **is**: tournament, award_show, card, draft, season, series, theme. This catalog's kind says how
**membership is decided**. Midterms is stored as `theme`, and the round-up's `kind: "roundup"` exists only
in its computed payload. See §6 decision B.

### 0.3 Evidence key

Every "we have it" claim below cites one of these.

**Files** (paths from repo root; `app/` = `backend/app/`):

| Key | File · symbol | What it shows |
|---|---|---|
| E1 | `backend/data/collections/midterms-2026.json` | 14 ids, 4 sections, layouts party/field/duel/auto |
| E2 | `app/utils/midterms_collection.py` `MIDTERMS_TWIN_REGISTER`, `blend_card`, `_official_result` | explicit twins; first official result overrides the blend |
| E3 | `backend/scripts/collection_publication.py` `validate_curated`, `prepare_curated` | curated publish path; container kind `theme`; ledger |
| E4 | `app/utils/nfl_division_register.py` `NFL_DIVISION_REGISTER`, `compose_division` | 8 pairs; refusal reasons |
| E5 | `app/utils/discover_bundles.py` :2605–2618 constants, :2655 `assemble_nfl_division_roundup`, :2888 `nfl_division_roundup`; :1820 `assemble_story_theme_bundles`; :2179 `assemble_awards_theme_bundles`; :2293 `assemble_deadline_family_bundles`; :2489–2491 + :2565 swings (`SWINGS_MIN_SWING = 0.15`, `SWINGS_EXTREME = 0.95`); :32 `PUBLIC_COMPARISON_BUNDLE_THEMES` (ipo_valuation, commodity_ranges, rotten_tomatoes_scores, weather_distributions) | every bundle shape that exists |
| E6 | `app/routes/containers.py` :110 `CONTAINERS_READ_ENABLED`, :418 `get_container`, :454 round-up branch | serving path |
| E7 | `app/utils/container_graph.py` :32 `CONTAINER_KINDS`, `CONTAINER_STATUSES`, :101 `EDGE_CLASSES` | storage vocabularies; status from the authority |
| E8 | `app/utils/container_nfl.py` :85 `_WEEK_RE`; `events.statpal_fixture_id` | NFL week comes from StatPal's round, never kickoff dates |
| E9 | `app/utils/container_tournaments.py` :160 `DECLARED_TOURNAMENTS = (US_OPEN_2026,)`, :227 `DECLARED_COLLECTIONS = (NFL_2026, MLB_2026_POSTSEASON)` | only one tournament is declared |
| E10 | `app/services/container_discovery.py` :77 `DISCOVERABLE_EDITIONS` = nfl_week, mlb_postseason, midterms | what Discover can offer today |
| E11 | `app/utils/theme_definitions.py` :867 `REGISTRY` = OSCARS_2027, AI, two departure subjects; AI rule `ai-subject@2` | rule-assembled theme subjects |
| E12 | `app/utils/event_awards.py` :20–30 | awards settle per category only; no ceremony-completion signal |
| E13 | `app/utils/tonights_games.py` `MAX_LEAD = 3`, `SOON_WINDOW_HOURS = 4`, `_is_eligible` | tonight eligibility (both crests, no pro_minor, no finished/suspended) |
| E14 | `app/utils/aggregation.py` :53 `SOURCE_WEIGHTS`, :69 `LIVE_MARKET_SOURCES`, :72 `_live_base_weight` | live blend (ruling 148) |
| E15 | `app/utils/sport_keys.py` :884–1411 game map; :1470–2085 futures map (NFL awards :1481–1497, divisions :1501–1508, `kxnflplayoff` :1509, coach-out :1573–1574, NCAAF conferences :1684–1709, `kxnextteammlb` :1680, `kxatpfinals` :1801, UFC :1824–1835, MLB awards :1862–1869, `kxheisman` :1916, F1 :2034–2036); ITF classification-only :1252–1255 | which venue series we ingest |
| E16 | `app/config/league_configs.py` :1203–1221 `LEAGUE_CONFIGS` (14 grids); NBA :111–202 (KXNBACUP excluded :121–131); NFL :485–563; NCAAF :767–840; EPL :842–908; UCL :958; GOLF :1143 (no `canonical_prefix`) | championship grids |
| E17 | `app/routes/hub.py` :211 `HUB_CONFIGS` = mma, boxing, golf, tennis, esports | event-concept hubs |
| E18 | `app/tasks/datagolf.py` :33–40 market types win/top5/top10/top20/make_cut | golf data |
| E19 | `app/utils/resolution_authority.py` :48 `AUTHORITATIVE_SOURCES` (api_settlement, datagolf_settlement, …), :70 `DETERMINISTIC_SOURCES` (game_score, …) | settlement authorities |
| E20 | `app/tasks/backfill_winners.py` :11–12 | Polymarket graded only when every outcome sits at 0 or 1 |
| E21 | `app/utils/venue_settlement.py` :64 `VENUE_SETTLEMENT_SOURCE = "api_settlement"` | the venue-stated result |
| E22 | `app/tasks/kalshi.py` :1852–1855 | crypto markets are skipped at ingest |
| E23 | `app/utils/futures_highlights.py` :482 `leader_change` → "New favorite", :573–605 `rank_claim_is_evidence` | new-favorite evidence gate |
| E24 | `app/tasks/futures_movers_warm.py`; `app/routes/futures.py` :1130 `/movers` | 24 h movers |
| E25 | `app/models/models.py` :514 `WinProbSnapshot`, :1230 `FuturesOddsSnapshot` (raw, vig-inclusive, per book), :2043 `DiscoverCandidateSnapshot` | history and seat history |
| E26 | `app/routes/economics.py` themes fed/inflation/jobs/recession/markets/energy/metals; `app/utils/inflation_release_identity.py` `fold_same_release`; `app/utils/economics_headline.py` `select_recession_headline` | economics grouping |
| E27 | `app/routes/weather.py` :1039 `/cities`; imports `group_markets_by_group_id` only (no `find_cross_source_markets`) | weather has no cross-venue pairing |
| E28 | `app/routes/entertainment.py` `_THEME_BY_TICKER` (awards, movies incl. RT, tv_streaming, music) | entertainment grouping |
| E29 | `app/routes/politics.py` themes presidential/congressional/gubernatorial/policy/scotus/international | politics grouping |
| E30 | `app/utils/departure_story_contract.py` (`NAME_ONLY_MENTION`); departure_* classes in E7 | departure stories |
| E31 | `app/routes/teams.py` :224 `GET /api/teams/{identifier}`; `docs/entity-page-templates.md` tiers T0–T3; `app/utils/entity_page_tiers.py` | entity pages |
| E32 | `app/utils/futures_source_merge.py` :121–183 `blend_with_verdict` | same-market blend and divergence gate |
| E33 | `app/utils/event_f1.py`, `app/utils/event_ufc.py`, `app/tasks/espn_combat_cards.py` | F1 and fight-card adapters |
| E34 | `app/utils/container_read_cache.py` :111–136 `payload_deadlines` | live TTLs on container reads |
| E35 | `app/utils/provider_event_collections.py` | Polymarket event hubs, non-sports, stored as `theme` |
| E36 | `app/tasks/sentinel_filing.py` `reconcile_issue` | the shared file-or-comment rail a producer refusal could use |

**Endpoints** (anonymous GETs to `https://api.bainluck.com`, Nov 3, 06:50–06:58 PT, ~45 reads, one
second apart):

| Key | Endpoint | What it returned |
|---|---|---|
| P1 | `/api/containers/roundup-nfl-division-front-runners` | `published`, revision 2122830944, 4 members (NFC East 53674, AFC West 53675, NFC North 53673, NFC South 53672), `source: "both"` |
| P2 | `/api/containers/midterms-2026` | `published` rev 1, 14 members, 0 withheld, twin report 11 `matched` / 3 `no_twin_found`, pin "Senate 77% D - House 94% D" |
| P3 | `/api/containers/discover` | nfl-2026-week-4, -5, -7, -8, every one with status `scheduled` |
| P4 | `/api/futures/movers?hours=24&limit=20` | top rows: "What will Trump say this week?", Doak Walker Award, "Gas prices on November 3?" (+88 pp), a posts-count market, an ITF set line, a ski-resort opening, an M15 match |
| P5 | `/api/politics`, `/api/economics`, `/api/entertainment`, `/api/weather/cities` | themes as in E26–E29; 47 weather cities |
| P6 | `/api/futures/browse?q=<term>&limit=50` | 41 terms; market ids are quoted inline as "(P6)" |

### 0.4 Vocabulary used in "Data today"

- **Twins.** *register* = explicit verified pairs in code (only E2 and E4 exist). *both list it* = each
  venue has a market in the read, pair **unverified**, and deadlines or rungs may differ. *one venue* =
  only one venue lists it. *event blend* = a game's `win_probability_sources` blend (E14).
- **Settlement.** *venue grade* = `api_settlement` (E19, E21); Polymarket only when every outcome sits at
  0 or 1 (E20). *game score* = deterministic (E19). *DataGolf* (E19). *per category* = awards (E12).
  *no path found* = sportsbook outright rows (`odds_api`), whose grading path was not found in
  `tasks/futures.py`.

---

## 1. The catalog: 50 containers, ranked

Ranked by the weighted score in §2. Each entry gives its kind, its score, and whether it is live already.

### 1. Midterms 2026 · curated-stored · 100 · **live**
- **Why open it:** tonight's results. Who controls Congress, the eight closest Senate races and three governors, settled race by race.
- **Member rule:** the 14 market ids in the committed manifest, in its four sections (E1, E3).
- **Data today:** markets 14/14 served, 0 withheld (P2) · twins: register, 11 of 14 matched; Alaska, the swing-state sweep and the closest-governor market have no Polymarket market (E2, P2) · settlement: first official venue grade replaces the blend (E2); the 30 s settle path is proven in #11894.
- **Membership changes:** never, except through a ledgered withdrawal. Card states change all night.
- **TRUTH risk:** a one-venue race reading as a blend; a winner shown from the first venue to grade while the other is still open (by design, E2, but the card must say whose result it is); the Discover pin outliving `pin_until`.

### 2. NFL division front-runners · computed-produced · 90 · **container live, card not yet in the feed**
- **Why open it:** the four tightest division races in one look.
- **Member rule:** all eight registered divisions must blend; the four with the lowest leader, shown highest first (E4, E5 :2655).
- **Data today:** markets 16 rows · twins: register (E4) · settlement: venue grade, but an unopened or clinched division refuses (`kalshi_not_open`, E4). Served `published` with four members at 06:51 PT (P1); it 404-refused on truncated Kalshi names the evening before (NOW #11852, 5:52 PM).
- **Membership changes:** when the bottom four reorder, which happens weekly after games. Revision = CRC32 of ids.
- **TRUTH risk:** the first clinch removes the whole card (settled handling is unruled); stored names truncated by width (`New York J`) need the serve-time repair on the producer's read; the 40-point divergence gate (E32) is the only blend guard.

### 3. Tonight's games · time-boxed-tonight · 87
- **Why open it:** every game on tonight, live or about to start, each with its one number.
- **Member rule:** events in tonight's sports day that are live or not yet started and pass `_is_eligible` (both crests, not pro_minor, not finished or suspended) (E13). Sections by league; a game that finishes stays as a settled card until the day closes.
- **Data today:** events with event blends (E14); Discover already leads with three of them (`MAX_LEAD`, E13) · settlement: game score (E19).
- **Membership changes:** every refresh (status transitions).
- **TRUTH risk:** the container number must be the hero's number under ruling 148's live weights; a finished game showing a live-looking number; read-cache TTLs must follow `payload_deadlines` (E34).

### 4. College Football Playoff picture · computed-produced · 84
- **Why open it:** who is in the 12-team field, a month before selection day.
- **Member rule:** the qualifiers field as spine; section "On the bubble" = teams between 20% and 80%, section "Title contenders" = the national-title field (E15 `kxncaaf`).
- **Data today:** Kalshi 227 "College Football Playoff Qualifiers" (54 teams, closes Dec 15); Polymarket per-team top-4-seed markets 58427164… (close Dec 21) (P6); grid `NCAA_FOOTBALL_CONFIG` (E16) · twins: none. Qualifying and seeding are different markets (ruling 139) · settlement: venue grade.
- **Membership changes:** weekly (Saturday results, Tuesday rankings).
- **TRUTH risk:** 12 winners out of 54, so rows must never be normalized to 100; the two venues' deadlines differ, so no blend.

### 5. Decided this week · time-boxed-tonight · 83
- **Why open it:** what just got settled, for everything a reader was following.
- **Member rule:** markets whose venue grade or game final arrived in the last 7 days **and** that held a Discover or collection seat in the 30 days before (seat history: `DiscoverCandidateSnapshot`, E25). Newest first, each as its settled card.
- **Data today:** `settled_at` first-observation stamps (E2 `_official_result`), venue grades (E21), seat history (E25) · twins per member.
- **Membership changes:** grows as results land; a member leaves after 7 days.
- **TRUTH risk:** this surface puts every wrong grade in front of readers: `is_winner` fragility (Hot List #21), Kalshi settled rows still `open` until the sweep (Hot List #33), and a Polymarket grade that waits for all-0/1 (E20). Quiet rows stay (ruling 114).

### 6. The closest games tonight · time-boxed-tonight · 83
- **Why open it:** tonight's coin-flip games.
- **Member rule:** from #3's eligible set, the four games with the lowest blended leader, shown highest first (the NFL display precedent). Fewer than four eligible means no card. The container holds exactly the card's four, pinned by revision (#10357 Oct 7).
- **Data today:** event blends (E14) · settlement: game score.
- **Membership changes:** fixed per revision; the revision moves when the four or their order change.
- **TRUTH risk:** the leader flips once play starts; ruling 148 changes the weights at kickoff, so "closest" moves; the pinned container must keep showing current numbers for the pinned four.

### 7. NFL week N · event-derived · 81 · **built; switching on is NOW #9**
- **Why open it:** every game of the week and its markets in one place.
- **Member rule:** events whose StatPal round is "Regular Season / Week N", joined on `statpal_fixture_id` (E8); each game's own winner market is excluded in favor of the event card.
- **Data today:** published week containers (P3) · settlement: game score.
- **Membership changes:** fixed by the schedule; flex moves and postponements only.
- **TRUTH risk:** at 06:51 PT on Nov 3, discovery listed Weeks 4, 5, 7 and 8 as `scheduled` (P3), past weeks carrying a pre-game status. Status must come from the authority (E7).

### 8. Thanksgiving football · time-boxed-tonight · 81
- **Why open it:** the Thanksgiving games and the Black Friday game, the most-watched NFL days of the year.
- **Member rule:** NFL events kicking off Thu Nov 26 to Fri Nov 27, 2026 (ET). This is #3's producer with a fixed window.
- **Data today:** game events and game markets (E15 `kxnflgame`); no futures market names Thanksgiving (P6: 0 rows), so this is games only · settlement: game score.
- **Membership changes:** fixed.
- **TRUTH risk:** as #3.

### 9. The December Fed meeting · event-derived · 81
- **Why open it:** what the Fed does on Dec 9, and where the dots and dissents land.
- **Member rule:** an explicit list of markets that resolve on the Dec 8–9 FOMC: Kalshi 109657 decision, 109658 rate after, 61484907 dot-plot median, 61484895 dot plot published; Polymarket 57574250 decision, 57574208 dissents (P6).
- **Data today:** markets yes · twins: both list the decision (Kalshi "Hike 25bps" vs Polymarket "25 bps increase"), unverified, so a register entry with outcome aliases is needed, as in E2 · settlement: venue grade.
- **Membership changes:** static.
- **TRUTH risk:** Polymarket 60084901 "Fed decisions (Sep–Dec)" is a path combination, a different market and never a twin; the two venues settle a day apart (Dec 9 vs Dec 10), so E4's settlement-window check applies.

### 10. A film's release week · entity · 80
- **Why open it:** everything on one big release: reviews, opening weekend, the soundtrack. The first instance is *The Hunger Games: Sunrise on the Reaping*, opening Nov 20.
- **Member rule:** markets anchored to one film (title plus release year): RT score, opening weekend, album first week. The window runs from release week minus 7 days to plus 7.
- **Data today:** Polymarket 65875241 opening weekend (closes Nov 22); Kalshi 61484910 and Polymarket 64783070 RT score; Kalshi 67804634–36 album first week (P6) · twins: both list RT, but the rungs never align (Kalshi strict "Above 45", Polymarket inclusive "50+"; #10357 Oct 22 reader check), so they must never blend · settlement: venue grade.
- **Membership changes:** fixed per film; members settle over about three days.
- **TRUTH risk:** a title used as an id; Polymarket's five "at least N" RT markets are one template family (one card, ruling 145), not five cards.

### 11. Heisman race · computed-produced · 78
- **Why open it:** who wins on Dec 12, and who makes the trip to New York.
- **Member rule:** the winner field, the finalists field and the side markets (conference, class).
- **Data today:** Kalshi 189 (50 names, closes Jan 1), Polymarket 57792807 (32, closes Dec 27), Kalshi 59172726 finalists, 58015866 and 58420259 conference (P6); `kxheisman` (E15) · twins: both list the winner, unverified, and they close on different dates · settlement: venue grade.
- **Membership changes:** static; finalists named in early December.
- **TRUTH risk:** an unverified pair blended without E4-style identity and window checks; name spelling across venues.

### 12. This weekend's UFC card · event-derived · 78
- **Why open it:** the whole fight card in one place.
- **Member rule:** the bouts on one ESPN card (`espn_combat_cards`, `event_ufc`, E33), served through the mma hub (E17). Storage already has kind `card` (E7), but no card assembler exists.
- **Data today:** bout markets (`kxufcfight`, E15) and sportsbook MMA lines; UFC 334 is the mid-November card (Kalshi 65536535 closes Nov 15, P6) · settlement: fight-winner grading in `backfill_winners`.
- **Membership changes:** on fight-week scratches.
- **TRUTH risk:** a scratched bout still showing; surname-only rows left unmatched to their siblings (#5602).

### 13. Awards season: nominations · event-derived · 77
- **Why open it:** who gets nominated: Golden Globes (Dec 9) and Critics Choice.
- **Member rule:** nomination and winner markets per ceremony, one section per ceremony, categories as rows (E5 :2179, E12).
- **Data today:** Kalshi Golden Globe nominations 61484896–61484901 (close Dec 9), Critics Choice 65536307 and nominations 65521940 (P6) · twins: mostly one venue · settlement: per category (E12).
- **Membership changes:** static until nominations.
- **TRUTH risk:** nominations have several winners, so never normalize them; a future category showing "Result unavailable" (#11334).

### 14. The AI race · entity · 77
- **Why open it:** everything the markets say about AI: models, companies, milestones.
- **Member rule:** theme rule `ai-subject@2` (AI terms or Kalshi stems KXCLAUDE/KXGEMINI/KXOPUS/KXOAIANTH/KXIPOOPENAI, plus a tech or economics second signal, 14-day retention), assembled into stored edges (E11).
- **Data today:** the subject is in `REGISTRY` (E11) but theme editions are not discoverable (E10), so it has no Discover entry today. Its publication state was not read · settlement: venue grade.
- **Membership changes:** continuous (rule).
- **TRUTH risk:** false positives (the Claude deny rule exists for exactly this); overlap with #33's TIME rows.

### 15. Where players land next · sibling-family · 77
- **Why open it:** trade and free-agent destinations in one view.
- **Member rule:** markets of the template "‹player›'s Next Team" from one venue sharing one deadline. Rows are players, each with its own leading destination. The card shows one deadline; the container holds the family's other deadlines (#10354 Oct 8).
- **Data today:** Kalshi 9512, 3452980, 3452987, 3648046, 12821421, 19529192 (32 outcomes, close Dec 1); Polymarket 68198505/06/09 (close Nov 11) (P6); MLB `kxnextteammlb` (E15) · twins: both list some players, but on different deadlines, so they stay separate families · settlement: venue grade.
- **Membership changes:** shrinks as players move.
- **TRUTH risk:** the "Stays with X or …" outcome means different things on each venue; a destination shown for a player already traded.

### 16. Today's high temperatures · time-boxed-tonight · 76
- **Why open it:** how hot it gets in your city today.
- **Member rule:** daily high-temperature distributions for today's date in the cities `/api/weather/cities` serves, sectioned by region.
- **Data today:** 47 cities (P5, E27); weather distributions are a comparison theme (E5 :32) · twins: none (the weather route does no cross-venue pairing, E27) · settlement: venue grade the next morning.
- **Membership changes:** rolls at local midnight.
- **TRUTH risk:** yesterday's distribution lingering after the rollover; bucket rows read as a sum.

### 17. Opening weekend at the box office · time-boxed-tonight · 75
- **Why open it:** how big this weekend's opening is.
- **Member rule:** opening-weekend markets for films opening that Friday; window Thursday to Monday.
- **Data today:** Polymarket 67906994 *Godzilla Minus Zero* (Nov 8), 65875241 *Hunger Games* (Nov 22), 68365230 *Avengers: Doomsday* and 68365233 *Dune: Part Three* (Dec 20) (P6); Kalshi box office series routed (E28) · twins: one venue in the read · settlement: venue grade.
- **Membership changes:** weekly.
- **TRUTH risk:** Sunday estimate vs Monday actual, so the card must say which one settles it; bucket ladders render as a heatmap (ruling 047), not a sum.

### 18. This week's economic data · time-boxed-tonight · 75
- **Why open it:** the numbers coming out this week: inflation, jobs, GDP.
- **Member rule:** economics markets (E26 themes) whose release falls in the next 7 days, one card per release (`fold_same_release`).
- **Data today:** `/api/economics` themes fed through government (P5); e.g. Chicago Fed index 67804596 (closes Nov 23, P6) · twins: `find_cross_source_markets` (E26) · settlement: venue grade.
- **Membership changes:** rolling 7 days.
- **TRUTH risk:** release dates slip (a shutdown delays them); two cards for one release.

### 19. NFL playoff picture · computed-produced · 74
- **Why open it:** who is in, who is out, who is on the bubble.
- **Member rule:** the playoff qualifiers field; "bubble" = teams between 20% and 80%, sectioned by conference.
- **Data today:** Kalshi 62679 "Pro Football Playoff Qualifiers" (32 teams, closes Jan 11) (P6); `NFL_CONFIG` make_playoffs (E16) · twins: one venue in the read · settlement: venue grade.
- **Membership changes:** weekly.
- **TRUTH risk:** 14 winners out of 32, so never normalize; clinched and eliminated rows stay as settled rows (ruling 114).

### 20. Oscars 2027 race · event-derived · 74
- **Why open it:** Best Picture and the big categories, months ahead.
- **Member rule:** theme subject `oscars-2027` (E11); categories as sections (E12).
- **Data today:** Kalshi 109551 Best Picture (19 nominees); Polymarket nomination markets 27988772… (close Jan 21) (P6) · settlement: per category, with no ceremony-completion signal (E12).
- **Membership changes:** at nominations (January).
- **TRUTH risk:** Kalshi's placeholder date (Dec 31) is not the ceremony (E12); #11334's "Result unavailable" on a future category.

### 21. Team hub · entity · 74
- **Why open it:** everything on your team: next game, season markets, awards, moves.
- **Member rule:** live markets naming the team, deduped by group id and canonical key; tier T0–T3 by answer count (E31).
- **Data today:** `GET /api/teams/{identifier}` (E31). The page exists; as a definition it is the template for the entity kind.
- **Membership changes:** continuous.
- **TRUTH risk:** name-fold joins catching the same-city sibling (#2010: truncated outcomes point at the wrong club).

### 22. Today's biggest swings · story-movement · 74
- **Why open it:** what moved most today, and how far.
- **Member rule:** the swings bundle: a sustained 24 h move of at least 15 pp, leader below 95%, at most six (E5 :2489–2491, :2565).
- **Data today:** `max_movement_24h` (E24); price history is raw per book (E25). The raw movers list at 06:51 PT was led by a mention market, a daily gas ladder, an ITF set line and a ski-resort opening (P4), which is the noise the bundle's filters exist for · settlement: venue grade.
- **Membership changes:** continuous.
- **TRUTH risk:** a settlement jump reading as movement; a raw book row compared with a blend (#1844). **Gate:** stays out of the top ten until NOW #10's "is the price history clean?" verdict.

### 23. Premier League title and top four · computed-produced · 73
- **Why open it:** the title race and the fight for the Champions League places.
- **Member rule:** the champion field, plus the top-four family (rows = clubs, one deadline), plus relegation.
- **Data today:** Kalshi 31834301 "English Premier League Champion" (20, closes May 30); Polymarket top-four markets 61373453… (P6); `EPL_CONFIG` (E16) · settlement: venue grade.
- **Membership changes:** weekly.
- **TRUTH risk:** top four is a four-winner family, so never normalize it.

### 24. This week in golf · event-derived · 73
- **Why open it:** the week's tournament leaderboard as chances: win, top 10, making the cut.
- **Member rule:** the week's tournaments from the golf hub (E17), DataGolf markets (E18); same-weekend tournaments are one card with three visible rows, and no container when all three are visible (#10354 Oct 8).
- **Data today:** DataGolf win/top5/top10/top20/make_cut (E18) · twins: the golf grid has no canonical key (E16) · settlement: DataGolf (E19).
- **Membership changes:** weekly.
- **TRUTH risk:** representation discrepancies (#2829/#5353); undated tours excluded until dated (#10354 Oct 8).

### 25. NFL title picture · computed-produced · 71
- **Why open it:** the Super Bowl and conference races.
- **Member rule:** the title field plus the AFC and NFC champion fields (E15).
- **Data today:** the Super Bowl row 86832 served `verified_title` with sportsbook, Kalshi and Polymarket contributors (#10354, Oct 6 read); Kalshi 40533 "2027 Pro Football Champion" (P6) · settlement: the sportsbook row has no path found; Kalshi grades.
- **Membership changes:** weekly.
- **TRUTH risk:** Polymarket's division events carry the title's canonical key (#10354, Oct 7), so division boards can contaminate the title.

### 26. Who runs in 2028 · sibling-family · 71
- **Why open it:** who announces a presidential run, and when.
- **Member rule:** Polymarket "Will ‹person› announce a presidential run before 2028?" (one template, rows = people, one deadline, Dec 31, 2026): 58335994, 58335996, 58336007, … (P6).
- **Data today:** one venue · settlement: venue grade.
- **Membership changes:** static.
- **TRUTH risk:** exclude 66077544 (which candidate leads the 2028 nominee markets on Nov 30), a market about other markets; announcement wording at settlement.

### 27. NFL awards race · computed-produced · 71
- **Why open it:** Coach of the Year, Super Bowl MVP and the season awards.
- **Member rule:** the award fields, one section per award.
- **Data today:** Coach of the Year Kalshi 8122712 / Polymarket 56933329; Super Bowl MVP Kalshi 479 (P6). The MVP/OPOY/DPOY/ROY series are mapped (E15), but **no NFL MVP row appeared** in the read (P6 "MVP": 27 rows, none NFL) · settlement: venue grade.
- **Membership changes:** static.
- **TRUTH risk:** unverified pairs; a missing headline award.

### 28. Shutdown watch · curated-stored · 71
- **Why open it:** whether the government shuts down again in December.
- **Member rule:** a hand list: Kalshi 62383608 "Government shutdown on Dec 12, 2026?", Polymarket 68064290 "…by December 12?" and 68064291 "…by December 31?", Kalshi 108577 count, Kalshi 109600 length (P6).
- **Data today:** markets yes · twins: none. "On Dec 12" and "by Dec 12" are different propositions, and the list must carry that note per member, as E2 does · settlement: venue grade.
- **Membership changes:** static.
- **TRUTH risk:** the on/by confusion blended into one number.

### 29. Rivalry Week · time-boxed-tonight · 71
- **Why open it:** the Saturday of college football's rivalry games (Nov 28).
- **Member rule:** NCAAF events on Nov 28 that pass #3's eligibility.
- **Data today:** `kxncaafgame` (E15) and sportsbook NCAAF lines · settlement: game score.
- **Membership changes:** fixed.
- **TRUTH risk:** as #3.

### 30. The chart race · time-boxed-tonight · 71
- **Why open it:** this week's No. 1, and how long the Christmas songs hold.
- **Member rule:** this chart week's Hot 100 No. 1 and No. 2 and the Billboard 200 No. 1, plus the weekly rank ladder for the season's returning song.
- **Data today:** Polymarket 68365226, 68365225, 68365224 (close Nov 11); Kalshi 67804598 Hot 100 No. 1 for November; Kalshi 67804504/478/457 weekly rank ladders (P6) · settlement: venue grade.
- **Membership changes:** weekly.
- **TRUTH risk:** a No. 1 at 99% says little; weekly rollover; the rank ladders are a date ladder (heatmap, ruling 047).

### 31. NBA Cup · event-derived · 70
- **Why open it:** the group races and the knockout bracket, through the final.
- **Member rule:** the Cup's markets: six group winners, knockout and finals qualifiers, champion, finals matchup, MVP.
- **Data today:** Kalshi 65536499–503 and 65536419 group winners (close Nov 28), 52755815/16 qualifiers, 52755817 champion, 67804430 matchup, 60629719 MVP (P6). The NBA grid excludes these on purpose (E16 :121–131), so this needs its own producer · twins: one venue · settlement: venue grade.
- **Membership changes:** after each group night.
- **TRUTH risk:** Kalshi names the league "Pro Basketball", so the name must be ours.

### 32. New favorites this week · story-movement · 70
- **Why open it:** where the leader changed this week.
- **Member rule:** futures whose printed leader changed in 7 days and pass `rank_claim_is_evidence` (E23).
- **Data today:** the leader-change scorer and gate (E23) · settlement: venue grade.
- **Membership changes:** continuous.
- **TRUTH risk:** a change claimed from an unpriced prior leg; #8784's refusals and the printed-leader rule (#5105 slice 2) apply.

### 33. TIME Person of the Year · sibling-family · 70
- **Why open it:** who the December cover goes to.
- **Member rule:** "Will ‹name› be TIME Person of the Year 2026?" (rows = names, one deadline): Polymarket 27467310… (P6).
- **Data today:** 29 Polymarket rows, 1 Kalshi (P6) · settlement: venue grade.
- **Membership changes:** static.
- **TRUTH risk:** independent rows read as a field that sums to 100.

### 34. MLB awards week · event-derived · 70
- **Why open it:** the MVP and Cy Young announcements.
- **Member rule:** the AL/NL MVP and Cy Young fields.
- **Data today:** Kalshi 209, 216, 212, 219 (close Dec 8); Polymarket 132768, 132777, 132810, 132847 (P6) · twins: both list it, unverified · settlement: venue grade. Leaders sit at 97.5–99.5% (P6).
- **Membership changes:** static.
- **TRUTH risk:** low; the reader value is low too, because these are decided in all but name.

### 35. Starship · entity · 69
- **Why open it:** when the next flight goes, and how many reach space this year.
- **Member rule:** markets anchored to SpaceX Starship.
- **Data today:** Polymarket 63727104 and 63355246 (Flight 15 by Nov 15 / Nov 30), Kalshi 65536482, 27559405, 52755901 (P6) · settlement: venue grade.
- **Membership changes:** per flight.
- **TRUTH risk:** "by" deadlines are a date ladder, one heatmap rather than separate cards.

### 36. Rotten Tomatoes this week · computed-produced · 69
- **Why open it:** how this week's films are reviewing.
- **Member rule:** the existing RT comparison theme (E5 :32), restricted to films whose score settles this week.
- **Data today:** *Wild Horse Nine* Kalshi 60481116 / Polymarket 64564200, *Godzilla Minus Zero* Kalshi 62383659 / Polymarket 65563521, *The Cat in the Hat* Kalshi 65536662 (close Nov 9) (P6). The renderer had no admitted specimen on Oct 22 (#10357) · settlement: venue grade.
- **Membership changes:** weekly.
- **TRUTH risk:** strict vs inclusive rungs never pair; stale rows.

### 37. Ballot measures 2026 · curated-stored · 68
- **Why open it:** what passed tonight beyond the candidates.
- **Member rule:** a hand list of tonight's notable measures; the noncitizen-voting measures in six states form one family card (Kansas 63522669, Arkansas 63522679, Arizona 63522680, Alaska 63522681, West Virginia 63528458, South Dakota 63528460).
- **Data today:** 17 Polymarket measures closing Nov 3–4 (P6) · twins: one venue · settlement: venue grade.
- **Membership changes:** static; settles overnight.
- **TRUTH risk:** a Polymarket grade waiting for all-0/1 (E20) while results are known.

### 38. Who leaves the administration next · computed-produced · 68
- **Why open it:** which cabinet-level officials are likeliest to go.
- **Member rule:** departure markets admitted by `departure_story_contract` across subjects (E30), with the departure classes as sections (E7).
- **Data today:** two departure subjects in `REGISTRY` (E11) · settlement: venue grade.
- **Membership changes:** on departures.
- **TRUTH risk:** mention markets (Kalshi 109258 "How many Cabinet members will Trump say he fired in 2026?", P6) are refused by `NAME_ONLY_MENTION` (E30); "announced" vs "vacated" are different markets.

### 39. House battlegrounds · curated-stored · 68
- **Why open it:** the House seats that decide the majority.
- **Member rule:** a hand list of district races (politics route district code, E29).
- **Data today:** district grouping exists (E29); district markets **not read** in this pass · settlement: venue grade.
- **Membership changes:** static; tonight only.
- **TRUTH risk:** too late to verify a twin register before tonight.

### 40. Latin Grammys · event-derived · 68
- **Why open it:** the Nov 14 ceremony, category by category.
- **Member rule:** the ceremony's category markets.
- **Data today:** about 50 Kalshi categories (e.g. 56775679 Album of the Year), many unpriced (P6) · settlement: per category (E12).
- **Membership changes:** static.
- **TRUTH risk:** unpriced rows (ruling 146 says show them with honest age).

### 41. Champions League league phase · computed-produced · 67
- **Why open it:** who reaches the round of 16.
- **Member rule:** the round-of-16 qualifiers field plus per-club families.
- **Data today:** Kalshi 59693605 (36 clubs), Polymarket 60087196 plus per-club markets (P6); `CHAMPIONS_LEAGUE_CONFIG` (E16) · settlement: venue grade.
- **Membership changes:** per matchday.
- **TRUTH risk:** a multi-winner field read as a sum.

### 42. NBA title race · computed-produced · 67
- **Why open it:** the championship and best-record races.
- **Member rule:** the title field plus best-record fields.
- **Data today:** Kalshi 52755651 (30 teams), 55674214 best record (P6); `NBA_CONFIG` (E16) · settlement: venue grade.
- **Membership changes:** weekly.
- **TRUTH risk:** low; slow-moving.

### 43. First snow by mid-November · sibling-family · 66
- **Why open it:** will your city see snow by the 15th.
- **Member rule:** "Will it snow in ‹city› by November 15?" (rows = cities, one deadline): Polymarket 60087426–30 (P6).
- **Data today:** one venue · settlement: venue grade.
- **Membership changes:** static per deadline; the container holds the other deadlines (Oct 31 rows also exist).
- **TRUTH risk:** a city already settled shown as open.

### 44. Recession watch · curated-stored · 65
- **Why open it:** the chance of a downturn, here and abroad.
- **Member rule:** a hand list: Kalshi 112807, 108622, 109488; Polymarket 113012, 58605173 (P6); headline by `select_recession_headline` (E26).
- **Data today:** markets yes · twins: both list "US recession by end of 2026", unverified · settlement: venue grade.
- **Membership changes:** static.
- **TRUTH risk:** "this year" vs "by end of 2026" vs "before 2027" wording.

### 45. League of Legends Worlds final · event-derived · 64
- **Why open it:** the Nov 15 final and its MVP.
- **Member rule:** the final's markets via the esports hub (E17).
- **Data today:** Finals MVP Kalshi 63135159 (closes Nov 15) / Polymarket 60552214 (closes Nov 29) (P6) · settlement: venue grade.
- **Membership changes:** static.
- **TRUTH risk:** the two venues close two weeks apart.

### 46. NFL coaching hot seat · sibling-family · 63
- **Why open it:** which head coach goes first.
- **Member rule:** the per-coach "out" markets (rows = coaches, one deadline) (E15 coach-out series).
- **Data today:** Polymarket 68198527 "Next Head Coach Fired" unpriced (0 outcomes); Kalshi 186 Las Vegas next coach (P6) · settlement: venue grade.
- **Membership changes:** on firings.
- **TRUTH risk:** unpriced rows; "next coach" vs "coach out" are different markets.

### 47. Netflix top 10 this week · time-boxed-tonight · 60
- **Why open it:** what everyone is watching this week.
- **Member rule:** the weekly No. 1 and No. 2, US and global, shows and films.
- **Data today:** Polymarket 68064184–191 (close Nov 4), leaders at 98% or higher (P6) · settlement: venue grade.
- **Membership changes:** weekly.
- **TRUTH risk:** low; low information.

### 48. Stanley Cup picture · computed-produced · 58
- **Why open it:** who gets past the first round in May.
- **Member rule:** the per-club "advance to the second round" family.
- **Data today:** Polymarket 60094213… (close May 5, 2027) (P6); `kxnhl` (E15) · settlement: venue grade.
- **Membership changes:** slow.
- **TRUTH risk:** unpriced rows.

### 49. ATP Finals · event-derived · 57
- **Why open it:** the season-ending eight in Turin.
- **Member rule:** the tournament's markets.
- **Data today:** 37 Polymarket markets (P6); `kxatpfinals` is mapped (E15), but no Kalshi row appeared; only the US Open is a declared tournament (E9) · settlement: venue grade.
- **Membership changes:** daily during the event.
- **TRUTH risk:** one venue; several rows unpriced.

### 50. Grand Prix weekend · event-derived · 56
- **Why open it:** the race weekend: head-to-heads, safety cars, the winner.
- **Member rule:** one Grand Prix's markets (`event_f1`, E33).
- **Data today:** Polymarket motorsport markets (63989329 head-to-head, 63989337 safety car) (P6); the drivers' title is Kalshi 229 at 99.5% (P6) · settlement: no path found.
- **Membership changes:** per race.
- **TRUTH risk:** no grading path read.

**Considered and folded or left below the line:** Supreme Court term (E29, scored under 56); NBA MVP (series mapped, no live row); F1 drivers' title (229 at 99.5%); conference championship weekend (folded into #4); MLB free agency (folded into #15); UFC year-end champions (a family inside #12's container).

---

## 2. The ranking

### 2.1 Criteria and weights

Each criterion is scored 1–5. **Score = Σ(weight × score) / 5**, so the range is 0–100.

| Criterion | Weight | 5 means | 1 means |
|---|---:|---|---|
| **R** Reader value | 30 | a casual fan opens it unprompted this month | only a specialist cares, or the answer is already known |
| **D** Data readiness | 25 | markets served today **and** a verified twin register or event blend | markets not seen in the read, or mapped only |
| **S** Settlement behaviour | 15 | a venue grade or game score settles every member, and the settled view is defined | no grading path found, or settlement only per part |
| **F** Freshness | 10 | members or numbers change within the day | nothing changes for months |
| **C** Cost to produce | 10 | exists, or is one registry entry on existing code | needs a new producer, adapter and register |
| **V** Variety added to Discover | 10 | a category or shape Discover lacks today | duplicates what Discover already leads with |

**The TRUTH gate sits outside the score.** A candidate with an open, unmitigated way to show a wrong number
cannot enter the top ten, whatever it scores. Today that removes only #22 (biggest swings), pending NOW #10,
and it ranks 22nd anyway.

### 2.2 Scores

| # | Container | Kind | R | D | S | F | C | V | Score |
|---:|---|---|:-:|:-:|:-:|:-:|:-:|:-:|---:|
| 1 | Midterms 2026 | curated-stored | 5 | 5 | 5 | 5 | 5 | 5 | 100 |
| 2 | NFL division front-runners | computed-produced | 5 | 5 | 3 | 4 | 5 | 4 | 90 |
| 3 | Tonight's games | time-boxed-tonight | 5 | 4 | 5 | 5 | 3 | 3 | 87 |
| 4 | College Football Playoff picture | computed-produced | 5 | 4 | 4 | 4 | 3 | 4 | 84 |
| 5 | Decided this week | time-boxed-tonight | 4 | 4 | 5 | 4 | 3 | 5 | 83 |
| 6 | The closest games tonight | time-boxed-tonight | 4 | 4 | 5 | 5 | 3 | 4 | 83 |
| 7 | NFL week N | event-derived | 4 | 4 | 5 | 4 | 4 | 3 | 81 |
| 8 | Thanksgiving football | time-boxed-tonight | 4 | 4 | 5 | 3 | 4 | 4 | 81 |
| 9 | The December Fed meeting | event-derived | 4 | 4 | 5 | 3 | 3 | 5 | 81 |
| 10 | A film's release week | entity | 4 | 4 | 4 | 4 | 3 | 5 | 80 |
| 11 | Heisman race | computed-produced | 4 | 4 | 4 | 3 | 4 | 4 | 78 |
| 12 | This weekend's UFC card | event-derived | 4 | 4 | 4 | 4 | 3 | 4 | 78 |
| 13 | Awards season: nominations | event-derived | 4 | 4 | 3 | 3 | 4 | 5 | 77 |
| 14 | The AI race | entity | 4 | 4 | 3 | 3 | 4 | 5 | 77 |
| 15 | Where players land next | sibling-family | 4 | 4 | 3 | 4 | 3 | 5 | 77 |
| 16 | Today's high temperatures | time-boxed-tonight | 3 | 4 | 4 | 5 | 4 | 4 | 76 |
| 17 | Opening weekend at the box office | time-boxed-tonight | 4 | 3 | 4 | 4 | 3 | 5 | 75 |
| 18 | This week's economic data | time-boxed-tonight | 3 | 4 | 5 | 4 | 3 | 4 | 75 |
| 19 | NFL playoff picture | computed-produced | 5 | 3 | 3 | 4 | 3 | 3 | 74 |
| 20 | Oscars 2027 race | event-derived | 4 | 4 | 2 | 3 | 4 | 5 | 74 |
| 21 | Team hub | entity | 4 | 4 | 4 | 4 | 3 | 2 | 74 |
| 22 | Today's biggest swings | story-movement | 4 | 3 | 3 | 5 | 3 | 5 | 74 |
| 23 | Premier League title and top four | computed-produced | 4 | 4 | 3 | 3 | 3 | 4 | 73 |
| 24 | This week in golf | event-derived | 3 | 4 | 5 | 4 | 3 | 3 | 73 |
| 25 | NFL title picture | computed-produced | 4 | 4 | 3 | 3 | 3 | 3 | 71 |
| 26 | Who runs in 2028 | sibling-family | 4 | 4 | 3 | 2 | 3 | 4 | 71 |
| 27 | NFL awards race | computed-produced | 4 | 3 | 4 | 3 | 4 | 3 | 71 |
| 28 | Shutdown watch | curated-stored | 4 | 3 | 4 | 3 | 3 | 4 | 71 |
| 29 | Rivalry Week | time-boxed-tonight | 3 | 4 | 5 | 3 | 3 | 3 | 71 |
| 30 | The chart race | time-boxed-tonight | 3 | 4 | 3 | 4 | 3 | 5 | 71 |
| 31 | NBA Cup | event-derived | 4 | 3 | 3 | 4 | 3 | 4 | 70 |
| 32 | New favorites this week | story-movement | 4 | 3 | 3 | 4 | 3 | 4 | 70 |
| 33 | TIME Person of the Year | sibling-family | 4 | 3 | 3 | 2 | 4 | 5 | 70 |
| 34 | MLB awards week | event-derived | 2 | 5 | 5 | 2 | 4 | 3 | 70 |
| 35 | Starship | entity | 3 | 4 | 3 | 3 | 3 | 5 | 69 |
| 36 | Rotten Tomatoes this week | computed-produced | 3 | 3 | 4 | 4 | 4 | 4 | 69 |
| 37 | Ballot measures 2026 | curated-stored | 4 | 3 | 3 | 4 | 2 | 4 | 68 |
| 38 | Who leaves the administration next | computed-produced | 4 | 3 | 3 | 3 | 3 | 4 | 68 |
| 39 | House battlegrounds | curated-stored | 4 | 2 | 4 | 5 | 3 | 3 | 68 |
| 40 | Latin Grammys | event-derived | 3 | 3 | 3 | 4 | 4 | 5 | 68 |
| 41 | Champions League league phase | computed-produced | 3 | 4 | 3 | 3 | 3 | 4 | 67 |
| 42 | NBA title race | computed-produced | 3 | 4 | 3 | 3 | 4 | 3 | 67 |
| 43 | First snow by mid-November | sibling-family | 3 | 3 | 3 | 3 | 4 | 5 | 66 |
| 44 | Recession watch | curated-stored | 3 | 4 | 3 | 2 | 4 | 3 | 65 |
| 45 | League of Legends Worlds final | event-derived | 3 | 3 | 3 | 3 | 3 | 5 | 64 |
| 46 | NFL coaching hot seat | sibling-family | 4 | 2 | 3 | 3 | 3 | 4 | 63 |
| 47 | Netflix top 10 this week | time-boxed-tonight | 2 | 3 | 3 | 5 | 3 | 4 | 60 |
| 48 | Stanley Cup picture | computed-produced | 3 | 3 | 3 | 2 | 3 | 3 | 58 |
| 49 | ATP Finals | event-derived | 3 | 2 | 3 | 4 | 2 | 4 | 57 |
| 50 | Grand Prix weekend | event-derived | 3 | 2 | 2 | 4 | 2 | 5 | 56 |

Ties are broken by R, then D. Kind mix of the 50: computed-produced 12, event-derived 12,
time-boxed-tonight 10, curated-stored 5, sibling-family 5, entity 4, story-movement 2.

### 2.3 What the ranking says

- **Data readiness is the binding constraint, not ideas.** Only two twin registers exist (E2, E4). Every
  other "both venues list it" is unverified, so most futures containers below #10 can show one venue
  honestly but cannot claim a blend until each gets a register like E4.
- **Time-boxed containers rank high because games settle cleanly** (game score, E19) and the event card
  already exists (ruling 147). Four of the top ten are time-boxed; together they need **one** window
  producer with three parameter sets (#3, #6, #8).
- **Story-movement waits on history quality.** The swings bundle exists (E5), but the raw movers feed is
  noise-led (P4), and NOW #10 is the verdict it needs.
- **Variety comes from non-sports**: the Fed, a film's release week, awards and families (TIME, snow, 2028)
  are new shapes for Discover. Most of them are one-venue today.

---

## 3. Top 10 as draft definitions (Amendment 1 fields)

Fields exactly as Amendment 1 lists them. The `rule` value shows what its params would carry (§4.2).
Copy follows rulings 138, 141 and 142. Footers claim a blend only where both venues verifiably
contribute. These are **drafts for Alex and Fable to correct**, not ruled copy.

```yaml
# 1 — exists; migration target for option C
slug: midterms-2026
kind: curated-stored
name: Midterms 2026
category: politics
section_title: [Congress control, Balance of power, The closest Senate races, Governors]  # four sections (§4.2 a)
footer: "Bain Luck blend · official results replace the blend as races are called"
rule:
  members: backend/data/collections/midterms-2026.json   # 14 ids by section
  twins: MIDTERMS_TWIN_REGISTER                           # 11 paired, 3 one venue
  relation: superset        # container = the manifest, not one card's rows
  refusal: per-member       # a missing member is withheld; the rest serve
  materialize: stored-edges
  pin_until: 2026-11-07T08:00:00Z
```

```yaml
# 2 — exists as code (Amendment 1 A1); unchanged values
slug: roundup-nfl-division-front-runners
kind: computed-produced
name: NFL division front-runners
category: nfl
section_title: The 4 closest races
footer: "Bain Luck blend · the 4 closest of 8 divisions"
rule:
  producer: nfl_division_roundup     # register → compose_register → 4 lowest leaders, highest first
  twins: NFL_DIVISION_REGISTER
  relation: exact                    # container = the card's four, in order (Oct 7)
  refusal: all-or-nothing            # any division refuses → no card, 404 unavailable
  materialize: read-time (60 s)
```

```yaml
# 3
slug: tonight-games
kind: time-boxed-tonight
name: Tonight's games
category: sports
section_title: "{league}"            # one section per league present, e.g. "NFL", "NBA"
footer: "Bain Luck blend · live and starting soon"
rule:
  producer: window_events
  window: sports-day                 # 6 AM–6 AM ET; Alex's call (§6 C)
  eligible: tonights_games._is_eligible
  order: live first, then start time
  settled: finished games stay as settled cards until the window closes
  relation: superset
  refusal: per-member
  materialize: read-time
```

```yaml
# 4
slug: roundup-cfp-picture
kind: computed-produced
name: College Football Playoff picture
category: ncaaf
section_title: [On the bubble, Title contenders]
footer: "Chance to make the 12-team field · teams between 20% and 80%"
rule:
  producer: field_band
  field: kalshi:227                  # CFP qualifiers (multi-winner: never normalized)
  band: [0.20, 0.80]
  second_section: national-title field (kxncaaf)
  relation: exact
  refusal: all-or-nothing            # an unpriced or stale spine → no card
  materialize: read-time
```

```yaml
# 5
slug: decided-this-week
kind: time-boxed-tonight
name: Decided this week
category: all
section_title: Settled in the last 7 days
footer: "Official results · newest first"
rule:
  producer: recent_settlements
  window: rolling-7d
  admit: venue grade (api_settlement) or game final, AND held a Discover/collection seat in the prior 30 d
  order: settled_at desc
  settled: the member IS its settled card (ruling 114: quiet rows stay)
  relation: superset
  refusal: per-member
  materialize: read-time
```

```yaml
# 6
slug: roundup-closest-games-tonight
kind: time-boxed-tonight
name: The closest games tonight
category: sports
section_title: The 4 closest games
footer: "Bain Luck blend · the 4 closest of {n} games tonight"
rule:
  producer: window_events_closest
  window: sports-day
  eligible: tonights_games._is_eligible
  select: 4 lowest leader probabilities; show highest first
  minimum: 4                         # fewer eligible → no card
  relation: exact                    # pinned by revision (CRC32 of ids)
  refusal: all-or-nothing
  materialize: read-time
```

```yaml
# 7 — exists (stored, assembled); switching on is NOW #9
slug: nfl-2026-week-{n}
kind: event-derived
name: "NFL 2026 · Week {n}"
category: nfl
section_title: "{game}"              # each game's event card, then its markets
footer: "Every game of Week {n}"
rule:
  authority: statpal round_info "Regular Season / Week {n}"
  join: events.statpal_fixture_id
  exclude: each game's own winner market (the event card carries it)
  status: from the authority, never from children
  relation: superset
  refusal: per-member
  materialize: stored-edges
```

```yaml
# 8
slug: thanksgiving-football-2026
kind: time-boxed-tonight
name: Thanksgiving football
category: nfl
section_title: [Thursday, Friday]
footer: "Bain Luck blend · Thursday Nov 26 and Friday Nov 27"
rule:
  producer: window_events
  window: 2026-11-26T06:00-05:00 / 2026-11-28T06:00-05:00
  league: nfl
  relation: superset
  refusal: per-member
  materialize: read-time
```

```yaml
# 9
slug: fed-december-2026
kind: event-derived
name: The December Fed meeting
category: economics
section_title: [The decision, The details]
footer: "Decision announced Dec 9"     # "Bain Luck blend" only once the decision pair is registered
rule:
  members: [kalshi:109657, kalshi:109658, kalshi:61484907, kalshi:61484895, polymarket:57574250, polymarket:57574208]
  twins: register to write — 109657 ↔ 57574250 with outcome aliases ("Hike 25bps" = "25 bps increase")
  never_twin: polymarket:60084901      # Sep–Dec path combination
  relation: superset
  refusal: per-member
  materialize: stored-edges (curated list) or read-time
```

```yaml
# 10
slug: film-hunger-games-sunrise-on-the-reaping
kind: entity
name: "The Hunger Games: Sunrise on the Reaping"
category: entertainment
section_title: [Reviews, Opening weekend, The album]
footer: "Opens Nov 20"
rule:
  anchor: film title + release year
  members: [polymarket:65875241, kalshi:61484910, polymarket:64783070, kalshi:67804634, kalshi:67804635, kalshi:67804636]
  never_blend: RT rows (strict vs inclusive rungs); each venue's RT rows render as their own card
  window: 2026-11-13 / 2026-11-27
  relation: superset
  refusal: per-member
  materialize: stored-edges
```

---

## 4. Kinds the stored-definition model must support (option C, week 3)

### 4.1 The seven kinds, one example each

| Kind | Example | Membership decided by | Materialized as |
|---|---|---|---|
| **curated-stored** | Midterms 2026 | an explicit list of (market, section) | stored edges via the publisher (E3) |
| **computed-produced** | NFL division front-runners | a named producer over a register or field | read time, cached (E5) |
| **event-derived** | NFL week N | an authority's event structure (round, card, ceremony, tournament) | stored edges via assembly (E8) |
| **entity** | Team hub | an anchor (a team, a film, a subject) plus scope | rule-assembled edges (E11) or read time (E31) |
| **time-boxed-tonight** | Tonight's games | a window plus an eligibility predicate | read time |
| **story-movement** | Today's biggest swings | movement over a window plus thresholds and a cap | read time, snapshot per revision |
| **sibling-family** *(added)* | First snow by mid-November | one template, fixed dimensions equal, exactly one varying subject | read time |

**Why `sibling-family` is added.** None of the six fits, for two reasons. Its container deliberately
differs from its card: the card shows one deadline and the container holds the family's other deadlines.
The #10354 Oct 8 record calls this "unlike NFL's exact-card-membership ruling". And its member rule is
structural equivalence that the system finds (ruling 145), not a list, a register, an authority, an anchor,
a window or a movement. NOW #11852 item 7 (the sibling-grouping rule, week 3) is this kind.

### 4.2 What the catalog shows the definition must also express

Amendment 1's seven fields hold, and moving them from code to data stays a storage change. Writing the top
ten exposed six things the `producer or member rule` value has to carry as parameters. The recommendation
is that they live **inside the rule's params** so the field list itself does not grow:

- **a. Sections.** Curated and event containers have several sections (Midterms has four), so
  `section title` must accept a list or a template (`{league}`).
- **b. Card↔container relation.** `exact` (round-up, pinned by revision), `family` (sibling: other
  deadlines), or `superset` (curated, event, entity, window).
- **c. Refusal policy.** `all-or-nothing` (round-up: 404, plus a sentinel line that should reach
  `reconcile_issue`, E36) or `per-member` (Midterms: `withheld[]`).
- **d. Window and pin.** `window` for time-boxed and entity kinds; `pin_until` for Discover pins (E2).
- **e. Settled behaviour.** Members stay as settled cards (ruling 114) until the window closes, or the whole
  container freezes as a record.
- **f. Twin source.** The named register a blend may use (E2, E4), or `none`. No other path may label a
  member a blend.

---

## 5. Ten rejected

1. **Crypto price ladders.** The Kalshi poller skips crypto at ingest (E22), so there are no rows to serve.
2. **Mention markets ("What will ‹person› say this week?").** The top 24 h mover at 06:51 PT was one (P4).
   They settle on transcript word counts, and the departure contract already refuses them as
   `NAME_ONLY_MENTION` (E30). The probability is real, but the market is trivia without a story, and it
   floods every movement surface.
3. **"Where the venues disagree."** Standing ruling 1: the blend is the product, and divergence is a data
   bug to fix, not a feature to show.
4. **Most-traded markets.** Standing ruling 3: never dollar volume as social proof.
5. **Upset watch / underdogs worth a look.** The framing invites value-hunting, close to the enticement
   standing ruling 3 forbids. #6 (the closest games tonight) carries the same information truthfully.
6. **Daily up/down and daily gas-price ladders.** Examples: "Netflix (NFLX) Up or Down on November 3?"
   (68764254) and "Gas prices on November 3?" (68776599, +88 pp in 24 h, P4). They expire within a day, are
   mostly structural rungs (ruling 105), and dominate movers.
7. **Minor-league and ITF tennis tonight.** pro_minor is ineligible for tonight (E13), ITF is
   classification-only (E15 :1252–1255), and the movers read was full of them (P4).
8. **Player hubs ("Everything on ‹player›").** There is no pinned player identity outside the tournament
   register. A player's face is pinned in a register and never resolved from a name (ruling 147's case),
   so a name used as an id is a matching defect waiting to happen. Revisit once a player register exists.
9. **Relegation battles worldwide.** 844 rows, mostly one-venue Polymarket boards for small leagues, with
   unpriced "survivor" rows (0 outcomes, P6). EPL relegation lives inside #23.
10. **Far-future golf majors (Masters 2027).** Kalshi 61056094 and a sportsbook row (P6), five months before
    the first shot. The sportsbook outright has no grading path found, and the field is flat. #24 carries
    golf.

---

## 6. Open decisions for Alex, and observations

**Decisions** (each with a recommendation and the default that holds until ruled):

- **A. Adopt `sibling-family` as a seventh kind?** Recommend **yes**, for the reasons in §4.1. *Default
  until ruled:* treat it as computed-produced with `relation: family`.
- **B. One `kind` or two?** The storage `containers.kind` (E7) says what a container is; this catalog's
  kind says how members are chosen. Recommend **keep both**: the stored definition carries the membership
  kind and `containers.kind` stays the subject type (Midterms stays `theme`). *Default:* definitions carry
  the membership kind.
- **C. What "tonight" means for a container.** `SOON_WINDOW_HOURS = 4` is the Discover lead's window (E13);
  a container needs the whole evening. Recommend **the sports day, 6 AM to 6 AM ET**. *Default:* live
  games plus the next 4 hours, as Discover does today.
- **D. Next producers after the NFL card reaches the feed.** Recommend **#6 the closest games tonight and
  #5 decided this week**: both reuse the round-up shape, settle by game score or venue grade, and add
  shapes Discover lacks. *Default:* none queued; NOW order stands.

**Observations from the reads, reported and not diagnosed:**

- The round-up container served `published` with four members at 06:51 PT (P1). On NOW #11852, the
  5:52 PM note the evening before recorded a 404 refusal on truncated Kalshi names.
- `/api/containers/discover` listed NFL Weeks 4, 5, 7 and 8 as `scheduled` on Nov 3 (P3). That matters for
  NOW #9.
- The raw `/api/futures/movers` list is led by mention, daily-ladder and minor-league rows (P4). That
  matters for NOW #10.
- Kalshi renames leagues ("Pro Football", "Pro Basketball", "Pro Basketball Cup"). Every container name in
  this catalog is ours, never the venue's.
