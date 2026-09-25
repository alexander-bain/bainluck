"""The real-Postgres gates seed with raw INSERT — so their columns must be complete.

WHY THIS EXISTS. The `*_pg.py` gates under `tests/integration/` are skipped
unless a throwaway Postgres is reachable, and there is none in the agent sandbox
(`initdb` dies on `shmget`). So a seed statement that is missing a NOT NULL
column is invisible locally: the file collects, the tests skip, the run is
green, and the defect surfaces for the first time inside CI's `search-recall`
job — which `deploy` needs, so it turns a DEPLOY GATE red for a reason with
nothing to do with what the gate is guarding.

That is not hypothetical. CAL-P090 shipped
`test_calibration_mode_price_source_scope_pg.py` with `futures_markets.external_id`,
`futures_markets.name` and `futures_outcomes.external_id` absent from its
INSERTs — all three NOT NULL with no default. CAL-P090's own report recorded the
file as "COLLECTED but never EXECUTED", which is precisely why nobody found out.
CAL-P091 repaired it.

WHAT THIS CHECKS, and what it deliberately does not. It is a STATIC check: it
reads the INSERT statements out of the gate files and compares their column
lists against the ORM metadata. It cannot tell you the gate passes. It tells you
the gate will get far enough to fail for its own reasons — which is the entire
gap that let the last instance through.

A raw INSERT bypasses SQLAlchemy's Python-side `default=`, so a column carrying
one is NOT excused here the way it would be on an ORM insert; only a
`server_default` is. That asymmetry is the trap this file is named after.

CAL-P157 added the second half — `test_every_real_postgres_gate_is_wired_into_ci`.
A complete seed proves the gate CAN run; it says nothing about whether anything
ever runs it, and `search-recall` names its gate files one hand-written step at a
time. The discovery arm found `test_feed_static_tag_filter_pg.py`, which is
gated on `SEARCH_TEST_DATABASE_URL`, skips everywhere else, and is named by no
step — so it has never executed once. It is allowlisted rather than wired here
(turning on a gate that has never run belongs to whoever owns the feed, not to a
model-parity queue) and reported, but nothing NEW can join it.
"""

import re
from pathlib import Path

import pytest
import yaml

from app.models.models import Base

#: The raw-INSERT gate files this check covers. Add a file here when you add a
#: real-Postgres gate that seeds with `session.execute(text("INSERT ..."))` —
#: the discovery arm below fails if such a gate grows an INSERT and is not
#: listed, so this list cannot silently fall behind.
COVERED = (
    "test_bookmaker_count_real_postgres.py",
    "test_calibration_mode_price_source_scope_pg.py",
    "test_census_cap_real_postgres.py",
    "test_calibration_mode_price_source_scope_peers_pg.py",
    "test_calibration_vm_variant_join_pg.py",
    # #5305 / q270 (CAL-P1137). Added with the gate itself, and worth reading
    # for what it does NOT claim. The NOT-NULL arm below would not have caught
    # this gate's real seeding bug: `futures_odds_snapshots.yes_ask` is
    # NULLABLE, so omitting it is legal DDL — and illegal only against the q270
    # WRITER BAR, which needs a two-sided book (`yes_ask IS NOT NULL AND
    # (yes_ask - yes_bid) < 0.50`). A bid-only seed therefore publishes NOTHING
    # and every assertion reads a vacuous empty set. CI's own PG run is what
    # found that, in this gate's sibling; the enrolment here is the discovery
    # arm's, and it is what stops the NEXT raw INSERT added to this file from
    # reaching a runner unchecked.
    "test_calibration_threshold_ladder_pg.py",
    # #6211 (CAL-P1310). Seeds three DataGolf markets and their boards by raw
    # INSERT to prove `market_info` withholds an unverified market WHOLE —
    # winners and losers together. Two seeding hazards worth naming here rather
    # than leaving to be rediscovered, neither of which the NOT-NULL arm sees:
    #
    #   * `futures_markets.category` is NOT NULL with no server default, and
    #     `llm_sport_category` is the CELL key the population groups on. Omitting
    #     the first kills the gate outright; omitting the second leaves it green
    #     and vacuous, which is worse.
    #   * `market_metadata` is the whole subject — the three markets are
    #     identical except for it — so a seed that dropped it would compare a
    #     market against itself and pass.
    "test_calibration_datagolf_symmetric_exclusion_pg.py",
    # #2927. Added the same night this check would have saved the trip: the
    # containers gate seeded `INSERT INTO sports (key, name)` and died on
    # `NotNullViolation: null value in column "active"` in CI, because
    # `Sport.active` carries a CLIENT-SIDE ORM default and no server default —
    # the exact class this file is named after. It is in COVERED so the next
    # raw INSERT added to it is checked before a runner finds out.
    "test_container_assembly_real_postgres.py",
    "test_containers_migration_real_postgres.py",
    "test_create_wave_insert_bind_contract.py",
    "test_feed_static_tag_filter_pg.py",
    "test_futures_outcome_grade_schema_parity_pg.py",
    "test_kalshi_cliff_bind_contract.py",
    # #5918 (CERT-2805's required repair). Seeds `sports` and two `events` by
    # raw INSERT to prove the league rail's own query hydrates `Event.sport` —
    # the fold reads the sport off the relationship, so an unloaded one made
    # the whole soccer pass inert on the page it was built for. `sports.active`
    # is exactly the Python-side default this file exists to catch, and the
    # seed names it.
    "test_league_rail_sport_load_pg.py",
    "test_kalshi_fabricated_loss_bind_contract_pg.py",
    "test_kalshi_settlement_recency_band_pg.py",
    "test_kalshi_sweep_settlement_bind_pg.py",
    # #7035. Seeds `futures_markets` by raw INSERT to prove the void write
    # PREPARES — its bind sits inside `jsonb_build_object`, which is
    # `VARIADIC "any"`, so an untyped parameter there cannot be inferred. Two
    # seeding hazards the NOT-NULL arm cannot see, both about the one column
    # the gate is actually about:
    #
    #   * `market_metadata` is bound through `CAST(:metadata AS jsonb)`. An
    #     untyped NULL into a `jsonb` column is the SAME inference failure one
    #     layer down, so a seed written the obvious way dies in the fixture and
    #     reports the gate's own bug as a red deploy.
    #   * the merge arm's whole subject is metadata the row ALREADY carries. A
    #     seed that left it NULL would exercise only the empty case, and the
    #     assignment-vs-merge bug it exists to catch would pass.
    "test_kalshi_sweep_void_bind_pg.py",
    # #7035 / CERT-3324's required repair. Seeds `events`, `futures_markets` and
    # `futures_outcomes` by raw INSERT to run `RESOLVED_VOID_SELECT_SQL` — the
    # selection seam the BLOCK found untested — against a real server. Three
    # hazards live in this seed, and each one would turn a screen vacuous rather
    # than loud:
    #
    #   * `market_metadata` must be bound through `CAST(:metadata AS jsonb)`.
    #     Two of the predicate's screens ARE jsonb key tests, so an untyped NULL
    #     kills the fixture before the arms that matter run.
    #   * `events.status` is the played-game control's ONLY difference from the
    #     specimen. A seed that let it default would make the control and the
    #     subject the same row and the most important arm would prove nothing.
    #   * `futures_outcomes.is_winner` is named explicitly on both sides of the
    #     ungraded screen. Left to its default, the graded control is not graded
    #     and the screen is never exercised.
    "test_kalshi_resolved_void_selection_pg.py",
    # #8586. Seeds `sports.active` explicitly (NOT NULL, Python-side default)
    # and CASTs `market_metadata`; `events.status` + `commence_time` are the
    # only differences between each subject and its control, so both are named.
    "test_mark_resolved_spares_live_events_8586_pg.py",
    # #8615. Same seed discipline as #8586, plus `futures_outcomes.is_winner`
    # and `resolution_source` named on every leg — they are the evidence the
    # statement reads, so a default would make the controls vacuous.
    "test_mark_resolved_venue_winner_8615_pg.py",
    # #7035, CERT-3326's repair — the CONSUMER half of the gate above. Where
    # that one proves the capture reaches the fixture, this one runs the real
    # retirement arm over the fact it wrote and reads `events.status` back.
    # Enrolled the session it was written; both arms of this file found it
    # before CI did. Its seed carries four hazards of its own:
    #
    #   * `sports.active` is NOT NULL with a PYTHON-side default, which a raw
    #     INSERT bypasses and `server_default` scanning cannot see — the trap
    #     this file is named after, and it cost a full CI round trip on the
    #     sibling gate.
    #   * `events.status` is the PLAYED control's only difference from the
    #     specimen, exactly as above.
    #   * `events.home_score` / `away_score` / `completed_at` are named so the
    #     evidence-of-a-played-game refusals have controls at all.
    #   * `futures_markets.source` and `.status` are named because the screen's
    #     selective clause is "no market that is NOT kalshi+resolved" — a seed
    #     that let either default would make the foreign-market control
    #     indistinguishable from the subject.
    "test_venue_void_retirement_pg.py",
    "test_link_tennis_already_linked_pg.py",
    "test_link_tennis_statpal_real_postgres.py",
    # #5024. Seeds `sports`, `events`, `futures_markets` and `futures_outcomes`
    # by raw INSERT to run the live arm's own `RECENT_FINAL_SELECT_SQL` against
    # a real server. Enrolled the same session the gate was written, because the
    # discovery arm below found it before CI did and both hazards this file
    # names are live in that seed:
    #
    #   * `futures_markets.category` and `.mutually_exclusive` are NOT NULL with
    #     no server default, so omitting either kills the gate outright — the
    #     loud half.
    #   * the quiet half is the clock. Every row's `last_updated` IS the
    #     subject: the new clause reaches a market no leg has touched inside
    #     `LIVE_STALE_TOUCH_MINUTES`, so a seed that let that column take a
    #     default would hand the predicate the value it is being asked about and
    #     the gate would pass on a fact it invented. It is named explicitly on
    #     every seeded leg, on both sides of the boundary.
    "test_live_stale_touch_reach_5024_pg.py",
    "test_null_statpal_live_space_3094_real_postgres.py",
    # #6215 (CERT-2880's required gate). Seeds `sports` and one `teams` row by
    # raw INSERT to prove the repair's backup/restore round-trips a real JSONB
    # `alternate_names` — the script's first cut declared that backup column
    # `text[]`, so `--backup` raised and the whole repair was unrunnable.
    # `sports.active` is exactly the Python-side default this file is named
    # after, and the seed names it.
    "test_backup_round_trip_jsonb_6215_pg.py",
    "test_polymarket_resolved_candidate_sql_pg.py",
    # #7021. Seeds ten `events` rows by raw INSERT into a PRIVATE schema to run
    # the twin drain's own candidate SELECT. The gate builds a narrow `events`
    # rather than `Base.metadata.create_all`, because the question it asks is
    # whether PostgreSQL joins two rows by a folded name — but the seed still
    # carries the MODEL's NOT NULL set, not merely the columns the query reads.
    # `events.status` was the one this check caught, and enrolling with an
    # exemption ("the narrow DDL cannot violate it") would have been the wrong
    # answer twice over: the reasoning expires the moment anyone repoints the
    # fixture at `create_all`, and the column turned out to be worth seeding on
    # its own merits — the two Cardinals rows disagree about it (`suspended` vs
    # `completed`), which is the reader-visible half of the defect.
    #
    # It must never leak that impostor into `public`, where `create_all`'s
    # callers would silently keep it; hence the schema.
    #
    # The second hazard is vacuity, and it is the one to watch: every row is
    # dated `now() - interval`, from the SERVER's clock, because the shipped
    # query carries `commence_time > NOW() - INTERVAL '30 days'`. A literal
    # timestamp would be a correct seed today and an empty candidate set within
    # the month — at which point all five "is/is not a candidate" arms pass
    # against nothing at all.
    "test_twin_fold_candidate_sql_7021_pg.py",
    # #8308. Seeds `events` by raw INSERT into a narrow table in a private schema
    # (search_path pinned per pooled connection, since the repair under test
    # commits). Carries every NOT NULL column so the rows are real-shaped.
    "test_dangling_duplicate_tag_8308_pg.py",
    # #7345. Seeds narrow `events` + `futures_markets` tables by raw INSERT in a
    # private schema; kick-offs are dated from the server's `now()` because the
    # verdict carries `commence_time < :now`.
    "test_same_instant_refutation_7345_pg.py",
    # #6390. Enrolled with the gate itself, and this check earned its keep
    # immediately: the seed's first run died on
    # `NotNullViolation: null value in column "reading_count"` — `OddsSnapshot`
    # carries a client-side ORM default and no server default, which is exactly
    # the class this file is named after. Caught locally only because a real
    # Postgres was to hand; on a runner it would have read as "the #6390 gate is
    # broken" rather than "the seed is short a column".
    "test_price_table_fold_6390_pg.py",
    # #6073's stuck-status rescue. Seeds `sports` and four `events` by raw
    # INSERT, and `sports.active` plus `events.status` are both the Python-side
    # default this file is named after — the seed names them.
    #
    # It also carries a second seeding hazard this file's NOT-NULL arm cannot
    # see, so it is written down here rather than left to be rediscovered: the
    # rows are dated `now() + interval`, from the SERVER's clock, because the
    # band under test says `commence_time > now()`. A literal timestamp would be
    # a correct seed on the day it was written and an empty band a week later,
    # at which point every "declined" arm passes because nothing was selected.
    # A seed can be legal DDL and still be vacuous.
    "test_polymarket_stuck_status_atomicity_6073_pg.py",
    # #836/#837 (live/317). Seeds `sports` and one `events` row by raw INSERT to
    # drive two concurrent blend stampers. Both of this file's named traps are
    # present and named in the seed: `sports.active` and `events.created_at`
    # carry Python-side ORM defaults with no server default, so a raw INSERT
    # that omits either dies on a runner and reads as "the blend-race gate is
    # broken" rather than "the seed is short a column".
    #
    # A third hazard this file's NOT-NULL arm cannot see, written down rather
    # than left to be rediscovered: that gate does NOT drop its tables. CI's
    # `bl_searchtest` is shared by every real-Postgres step in `search-recall`,
    # and `events` has dependent tables whose foreign keys make a drop raise
    # `DependentObjectsStillExistError` — measured on this gate's first CI run.
    # It creates what is missing and deletes only the rows it seeded, keyed on a
    # marker in `sports.key`.
    "test_live_blend_concurrent_stamp_pg.py",
    "test_rekey_statpal_anchors_real_postgres.py",
    # #7640. Seeds three `futures_markets` and twelve `futures_outcomes` by raw
    # INSERT to grade the stale-rank repair's apply/restore round trip. Two
    # seeding hazards worth naming rather than leaving to be rediscovered:
    #
    #   * `futures_markets.mutually_exclusive` / `.category` / `.status` are the
    #     exact Python-side defaults this file exists to catch, and the seed
    #     names all three.
    #   * `futures_outcomes.last_updated` is NOT NULL with a `server_default` of
    #     `now()`, so omitting it is legal DDL and silently wrong here: it is the
    #     undo's witness, and a seed that let every leg take the INSERT's clock
    #     would leave the "a poller touched this row" assertion comparing two
    #     timestamps milliseconds apart. The NOT-NULL arm cannot see that.
    "test_repair_7640_rank_roundtrip_real_postgres.py",
    "test_repair_3672_bind_contract.py",
    # #5789. Seeds `sports`, `events` and `futures_markets` by raw INSERT with
    # production's own 20 events and 16 markets. Two of its NOT NULL columns
    # (`sports.active`, `futures_markets.mutually_exclusive`) carry Python-side
    # defaults only, so the seed had to name them — which is this file's whole
    # point, and it caught them.
    "test_repair_5621_population_excludes_real_games_pg.py",
    # #4788 (CAL-P1088). Seeds `futures_outcomes` by raw INSERT and names
    # `is_winner` on EVERY row, including the NULL ones — omitting it would let
    # the server default `false` seed this gate's own cohort by accident, so the
    # gate would find the defect it manufactured.
    "test_repair_pm_ungraded_loss_4788_pg.py",
    "test_restore_3026_jsonb_roundtrip_pg.py",
    "test_restore_4586_manifest_cas_pg.py",
    "test_soccer_statpal_manifest_restore_pg.py",
    "test_stand_in_event_starts_real_postgres.py",
    "test_tennis_commence_predicate_real_postgres.py",
    "test_tennis_twin_sweep_pg.py",
    # #2772. Seeds `sports` and 22 `events` by raw INSERT to prove the
    # illegal-settled-tennis-score RECALL returns exactly the rows the judgment
    # would withdraw — a fetch fails silently, so the id set is the assertion.
    #
    # It paid for BOTH of the shared-database hazards already written down in
    # this file, and paid for them in CI rather than by reading them here first,
    # which is the whole reason they are written down. Recorded again from the
    # other end so the next author meets them in the order they bite:
    #
    #   1. `drop_all()` over a SUBSET raises `DependentObjectsStillExistError`
    #      naming twelve foreign keys at `events` (the hazard
    #      `test_live_blend_concurrent_stamp_pg.py` records). A fresh local
    #      database cannot produce it. This gate creates with `checkfirst` and
    #      drops nothing, ever, deleting only its own rows by id.
    #   2. Any insert into `sports` that lets the sequence fire dies on
    #      `sports_pkey`, and `ON CONFLICT (key)` does not save it — the
    #      collision is on the PRIMARY key (the hazard
    #      `test_folded_market_sport_net_6221_pg.py` records). This gate needs
    #      three sports keys the shared database may or may not hold, so it
    #      SELECTs first and names its own ids for the ones it creates.
    #
    # Both are now reproduced locally before pushing — a foreign dependent table
    # with an FK at `events`, and a sequence left at 1 behind explicitly-idded
    # rows for two of the keys this gate seeds.
    "test_illegal_settled_tennis_score_recall_2772_pg.py",
    "test_typeahead_played_game_suppression_pg.py",
    "test_typeahead_final_seven_route_control_pg.py",
    # #5082. Seeds `sports`, `teams` (with production's `alternate_names`, the
    # only path by which `pats` resolves the Patriots), `futures_markets` and
    # `futures_outcomes` by raw INSERT; drops and recreates the schema like the
    # final-seven gate above.
    "test_typeahead_team_query_cross_sport_5082_pg.py",
    # #5779. Seeds `sports` and `events` by raw INSERT, including rows whose
    # `statpal_fixture_id` is deliberately NULL — the NOT-NULL arm is what keeps
    # a future column with a client-side default from making that seed illegal
    # without anybody noticing until a runner says so.
    "test_reconcile_lookback_reach_5779_pg.py",
    # #6073 (CERT-2834's required repair). Seeds `sports`, five `events` and
    # four `futures_markets` by raw INSERT. Every arm turns on the corpus being
    # INSIDE the repair band, so a `NotNullViolation` there would not read as a
    # broken seed — the band would simply come back empty and every "the repair
    # declined it" assertion would pass having declined nothing.
    "test_polymarket_redate_atomicity_6073_pg.py",
    # #6221's cross-sport net follow-up. Seeds `sports`, two `events` and three
    # `futures_markets` by raw INSERT, and it names both of the Python-side
    # defaults this file exists to catch — `sports.active` and
    # `futures_markets.mutually_exclusive`.
    #
    # Its seed also carries a vacuity hazard the NOT-NULL arm cannot see, so it
    # is written down rather than left to be rediscovered: the whole gate turns
    # on the ghost and the canonical holding DIFFERENT `sport_id`s. If both
    # `_sport_id` calls ever returned one row, the first arm of the net would
    # match on its own, every assertion would pass, and the arm under test
    # would never be reached. The seed asserts `kleague != other` in place for
    # that reason — legal DDL is not the same thing as a seed that can fail.
    #
    # It also paid for a hazard worth reading before writing the NEXT gate that
    # seeds a lookup table, because this file's arms cannot see it either:
    # `search-recall` shares ONE database across all ~55 gates, and the earlier
    # ones seed `sports` with EXPLICIT ids, which never advances the sequence.
    # `INSERT INTO sports (key, ...) ON CONFLICT (key) DO NOTHING` draws
    # `nextval` BEFORE it evaluates the conflict, so a genuinely new key dies on
    # `sports_pkey` — `Key (id)=(1) already exists` — a pkey collision reported
    # by a statement whose whole point was to tolerate a key collision. The
    # sibling gates survive it only because each inserts one sport the shared
    # database already holds. This gate needs three, so it names its own ids.
    "test_folded_market_sport_net_6221_pg.py",
    # #6275 (CERT-2902's required gate). Seeds `sports`, three `events`, three
    # `futures_markets` and their outcomes by raw INSERT, and it names both of
    # the Python-side defaults this file exists to catch — `sports.active` and
    # `futures_markets.mutually_exclusive`.
    #
    # Its seed also carries a vacuity hazard the NOT-NULL arm cannot see, so it
    # is written down rather than left to be rediscovered: every arm turns on
    # the three markets reaching `normalized`, and a book seeded bid-only fails
    # the q270 writer bar, publishes nothing, and makes "the quarantine held it"
    # true of a market the liquidity gate had already dropped. The gate asserts
    # the candidate set up front for that reason.
    "test_identity_quarantine_linked_event_date_6275_pg.py",
    # #5896's leg-grain withdrawal. Seeds `sports`, four `events`, five
    # `futures_markets` and seven `futures_outcomes` by raw INSERT, and it names
    # every Python-side default this file exists to catch — `sports.active`,
    # `events.status`, `futures_markets.category` / `.mutually_exclusive` /
    # `.status`.
    #
    # Its seed also carries a vacuity hazard the NOT-NULL arm cannot see, so it
    # is written down rather than left to be rediscovered: the statement under
    # test says `e.commence_time > NOW()`, so every event is dated from the
    # SERVER's clock with an interval. A literal timestamp would be a correct
    # seed on the day it was written and, once past, would put the whole corpus
    # outside the window — at which point the withdrawal arm passes having
    # withdrawn nothing and every "the sibling survived" assertion is true of a
    # row nothing could have reached.
    "test_prekickoff_leg_withdrawal_5896_pg.py",
    # #6511, the EVENT-row half of the gate above. Same server-clock discipline
    # for the same reason, plus one column that gate does not seed:
    # `events.win_probability_sources`. It is NULLABLE, so the NOT-NULL arm
    # below cannot require it — and a corpus that omitted it would leave every
    # event with no `kalshi` key at all, at which point `jsonb_exists` selects
    # nothing and the whole file passes having withdrawn nothing.
    "test_stranded_prekickoff_hero_6511_pg.py",
    # #6532. Seeds `futures_markets` and `futures_outcomes` by raw INSERT and
    # drives the whole playoff-grid route over them. Two columns carry the
    # lesson: `futures_markets.llm_sport_category`, which is NULLABLE and is
    # therefore invisible to the NOT-NULL arm below — yet la-liga configures no
    # Kalshi ticker prefix, so it is the ONLY way the corpus reaches the grid at
    # all, and a seed without it makes every "the refused leg is gone"
    # assertion true of rows nothing could have served; and
    # `futures_outcomes.last_updated`, taken from the server because the ingest
    # loop drops anything older than seven days before the arm under test ever
    # sees it.
    "test_grid_book_refuted_price_6532_pg.py",
    # #8220. The untaken-offer arm on the same grid loop as #6532 above, and it
    # seeds two `futures_markets` plus their legs by raw INSERT. Two hazards this
    # arm does see and one it does not, named so the next editor of that file
    # does not rediscover them: `futures_markets.category` / `.mutually_exclusive`
    # / `.status` and `sports.active` all carry CLIENT-SIDE ORM defaults a raw
    # INSERT skips; and the one this gate is blind to — every seeded team must be
    # in `NCAA_2026_BRACKET`, because step 4d drops the rest and a refused
    # specimen filtered for THAT reason makes the refusal assertion pass with the
    # fix reverted. That one is held by the gate's own anti-vacuity test.
    "test_grid_untaken_offer_8220_pg.py",
    # #7829 part 1. The Miami identity gate on the same grid route. Seeds
    # `sports`, `teams`, `futures_markets` and `futures_outcomes` by raw INSERT
    # (the `teams.abbreviation` column is the anchor under test, so the seed
    # must carry it) and reads the served NCAAF payload. Registered here so a
    # NOT NULL column added to any of those four tables fails this parse rather
    # than a red deploy.
    "test_grid_miami_identity_7829_pg.py",
    # #6975: seeds `sports` with an explicit reserved id (the #6221 sibling's
    # reason — the shared CI database's sequence is behind its explicit-id
    # rows); every other row goes through the ORM so Python-side defaults
    # apply.
    "test_event_subresources_resolve_twin_id_6975_pg.py",
    # #6955 (CERT-3074's named follow-up). Seeds `futures_markets` by raw
    # INSERT for both club-noun rails and drives their real apply / partial
    # compare-and-set / D51 undo. Two columns carry the lesson:
    # `llm_sport_category` is NULLABLE and so invisible to the NOT-NULL arm
    # below, yet it is the entire subject — a seed without it would leave every
    # row already agreeing with the venue and the rails would correctly plan
    # nothing, making every assertion true of rows that were never wrong; and
    # `market_metadata`, also nullable, which must be real JSONB because the
    # Polymarket rail reaches its container row through
    # `market_metadata->>'polymarket_event_id'`.
    "test_repair_club_noun_apply_restore_6955_pg.py",
    # #7147: seeds `sports` and ten `events` by raw INSERT and drives a real
    # `_poll_all_odds` scores pass over them. `sports` carries an explicit
    # reserved id for the #6221 sibling's reason — the shared CI database's
    # sequence is behind its explicit-id rows, so letting the serial fire raises
    # on `sports_pkey`, which an `ON CONFLICT (key)` clause does not cover.
    # Two seeded columns are nullable and so invisible to the NOT-NULL arm
    # below while being the whole subject: `espn_id`, which is the "authority"
    # the refusal protects (a seed without it leaves every row unanchored and
    # the guard never fires), and the stored `home_score`/`away_score` pair,
    # where a NULL half is the carve-out the ship had to keep intact.
    "test_completed_espn_final_is_not_repoisoned_7147_pg.py",
    # #837: seeds `sports`, `teams` and one live `events` row per sport by raw
    # INSERT and parks a real odds pass mid-way to probe the row lock. The
    # nullable `external_id` is the whole reach: without it the registry does
    # not resolve the payload to the seeded row, nothing writes `betting`, and
    # the probe finds a free row for the wrong reason.
    "test_a_poll_releases_its_event_rows_per_sport_837_pg.py",
    # #837 follow-up: seeds two invented sports, their teams and four `events`
    # rows by raw INSERT (two scheduled for the odds loops, two completed for
    # the scores loop). `external_id` is the reach: the lookup that stands in
    # for the registry dereferences it, and a game it cannot find is never
    # written, so the probe would read "free" for the wrong reason.
    "test_a_failed_sport_and_the_scores_loop_release_837_pg.py",
    # #7501: seeds `sports` and seven `teams` by raw INSERT to drive the slug
    # filler against the real UNIQUE index on `teams.slug`, which IS the
    # mechanism — 855 of the 4,004 slug-less clubs exist as a cohort only
    # because that index refuses their clean name.
    #
    # One seeded column is nullable, invisible to the NOT-NULL arm below, and
    # the entire subject: `teams.slug` itself. Three of the seven rows are
    # seeded WITH a slug and four with NULL, and both halves are load-bearing —
    # a seed that slugged everything would leave the filler nothing to do and
    # every assertion would pass having filled nothing, while a seed that
    # slugged nothing would remove the collisions and send all four rows to
    # rung 1, so the three arms that exist to prove rungs 2 and 3 would pass
    # while testing rung 1 three times.
    #
    # The `sports` rows let the serial fire rather than naming explicit ids
    # (the #6221/#7147 hazard above) because this gate's fixture drops and
    # recreates the whole schema first, which resets the sequence with it.
    "test_team_slug_fill_7501_pg.py",
    # #7867. Seeds `sports`, `teams`, `events`, `futures_markets` and
    # `futures_outcomes` by raw INSERT to put the sport FAMILY's roster behind
    # the real `/related-futures` handler — the one thing its mocked sibling
    # cannot see. Its fixture drops and recreates the schema, as #7501's does.
    "test_route_related_futures_team_paths_7867_pg.py",
    # #7021. Seeds `sports`, `teams`, `events`, `futures_outcomes` and
    # `entities` by raw INSERT, in a private schema with the real FK actions
    # (CASCADE / SET NULL), to drive the Cardinals fold's apply, re-run and undo.
    # Explicit ids in a `7021xxxx` band; the schema is dropped whole on teardown.
    "test_repair_7021_fold_apply_restore_pg.py",
    # #6974. Seeds `sports`, `teams`, `events`, `futures_outcomes`, `entities`
    # and `team_identity_mapping` by raw INSERT, in a private schema with the
    # real FK actions and production's two partial unique indexes, to drive the
    # MLS duplicate-club repair's strip, fold, re-run and undo. Explicit ids in a
    # `6974xxxx` band; the schema is dropped whole on teardown.
    "test_repair_6974_fold_mls_apply_restore_pg.py",
    # #8430. Seeds `sports`, `events` and `futures_markets` by raw INSERT to
    # put Polymarket game children in five groups behind the real
    # `_polymarket_group_sibling_event_id`. Torn down by its own name prefix,
    # home team and sport key — the `search-recall` database is shared.
    "test_polymarket_group_sibling_8430_pg.py",
    # #8440. Seeds `sports` and `events` by raw INSERT, in a private schema
    # built by `create_all`, to drive the matcher's venue-name-extension pass
    # (pass 1b) through real Postgres retrieval. Explicit ids; the schema is
    # dropped whole on teardown.
    "test_pm_venue_name_extension_8440_pg.py",
    # #8422. Seeds `sports`, `events` and `event_provider_anchors` by raw
    # INSERT, in a private schema built by `create_all`, to drive the
    # re-issued-id sweep's read, write, lift and restore. Explicit ids; the
    # schema is dropped whole on teardown.
    "test_odds_api_reissued_twin_8422_pg.py",
)

INTEGRATION_DIR = Path(__file__).parent / "integration"

#: Adjacent Python string literals, so the source is un-concatenated ONCE up
#: front instead of the pattern below having to tolerate a `" "` join at each
#: place one might appear.
#:
#: 🔴 LAT-P163: it used to tolerate the join only INSIDE the column list, so
#: `"INSERT INTO t "` newline `"(a, b) VALUES ..."` — the join sitting between
#: the table name and the opening paren — matched nothing. That is not a
#: cosmetic miss. `test_bookmaker_count_real_postgres.py` was written that way
#: and this file parsed **1 of its 3 INSERTs**, silently skipping the two that
#: carried the client-side-default columns, which is exactly the defect class
#: this file is named after. The "no INSERT was parsed" tripwire could not fire,
#: because one statement HAD parsed. A guard that checks a subset is worse than
#: no guard: it is counted.
_LITERAL_JOIN_RE = re.compile(r'"\s*(?:\n\s*)?"')

#: `INSERT INTO <table> (<cols>) VALUES`, against already-joined source.
_INSERT_RE = re.compile(r"INSERT\s+INTO\s+(\w+)\s*\(([^()]*)\)\s*VALUES", re.IGNORECASE)

#: Every literal `INSERT INTO` in the source, matched or not. The count of these
#: must equal the count the pattern above extracts, or the pattern is reading a
#: subset and nothing else in this file can tell.
_INSERT_ANY_RE = re.compile(r"INSERT\s+INTO", re.IGNORECASE)

#: `INSERT INTO <table> (<cols>) SELECT ...` — an insert whose values come from
#: a query, not from a literal row. EXCLUDED from the count above, and it is an
#: exclusion rather than a hole (#6215):
#:
#: this file exists because `text("INSERT ...")` does not run a Python-side
#: `default=`, so a hand-written VALUES row can omit a NOT NULL column and only
#: find out on a runner. An `INSERT ... SELECT` writes whatever its SELECT
#: produced, so it cannot omit a column the source row had — and if the source
#: itself is short of one, the SELECT is the bug and the NOT NULL violation is
#: the correct, immediate report of it. There is no silent class here to guard.
#:
#: Narrow on purpose: the `SELECT` must follow the column list directly, so a
#: `VALUES` statement can never be waved through by this arm.
_INSERT_SELECT_RE = re.compile(
    r"INSERT\s+INTO\s+[\w{}]+\s*\(([^()]*)\)\s*(?:\"\s*\n?\s*\")?\s*SELECT",
    re.IGNORECASE,
)


def _columns(raw: str) -> set[str]:
    """Column names out of an INSERT's column list."""
    return {c.strip() for c in raw.split(",") if c.strip()}


def _joined_source(path: Path) -> str:
    return _LITERAL_JOIN_RE.sub("", path.read_text())


def _inserts(path: Path):
    return [
        (m.group(1).lower(), _columns(m.group(2)))
        for m in _INSERT_RE.finditer(_joined_source(path))
    ]


def _insert_keywords(path: Path) -> int:
    """Literal `INSERT INTO`s this file is responsible for reading.

    `INSERT ... SELECT` is subtracted rather than left to fail the
    parse-everything tripwire — see `_INSERT_SELECT_RE` for why that is an
    exclusion and not a hole.
    """
    source = _joined_source(path)
    return len(_INSERT_ANY_RE.findall(source)) - len(
        _INSERT_SELECT_RE.findall(source)
    )


def _required(table_name: str) -> set[str]:
    """NOT NULL columns a raw INSERT must supply itself.

    Excused: anything with a `server_default` (the database fills it) and
    primary keys the database can autoincrement. NOT excused: a Python-side
    `default=`, because `text("INSERT ...")` never runs it.
    """
    table = Base.metadata.tables[table_name]
    required = set()
    for col in table.columns:
        if col.nullable or col.server_default is not None:
            continue
        if col.primary_key and col.autoincrement is not False:
            continue
        required.add(col.name)
    return required


@pytest.mark.parametrize("filename", COVERED)
def test_pg_gate_inserts_supply_every_not_null_column(filename):
    path = INTEGRATION_DIR / filename
    assert path.exists(), f"{filename} is listed in COVERED but does not exist"

    statements = _inserts(path)
    assert statements, (
        f"{filename} is listed as a raw-INSERT gate but no INSERT was parsed out "
        "of it. Either it stopped seeding that way (drop it from COVERED) or the "
        "regex stopped matching (fix the regex) — silently checking nothing is "
        "the one outcome this file exists to prevent."
    )

    # LAT-P163: and silently checking SOME of it is the outcome the assertion
    # above cannot see. Parsing one statement out of three satisfies "not empty"
    # while leaving the other two unchecked, which is how this file was green
    # over `test_bookmaker_count_real_postgres.py` while two of its INSERTs were
    # invisible to it.
    keywords = _insert_keywords(path)
    assert len(statements) == keywords, (
        f"{filename} contains {keywords} `INSERT INTO` statements but only "
        f"{len(statements)} parsed. The unparsed ones are NOT being checked and "
        "nothing else here can tell. Fix the pattern rather than the file — a "
        "seed that this check cannot read is a seed it is not guarding."
    )

    missing = []
    unknown = []
    for table, provided in statements:
        assert table in Base.metadata.tables, (
            f"{filename} inserts into unknown table {table!r}"
        )
        # #4914: a column that does not EXIST is the mirror of the omitted-column
        # check below, and this file could not see it. `UndefinedColumnError` and
        # `NotNullViolationError` both kill the gate before its first assertion,
        # both are invisible without a Postgres, and both surface only in CI on a
        # job `deploy` needs — the exact cost this file was written to avoid.
        # Measured: `INSERT INTO sports (key, name, title, active)`, copied from a
        # neighbouring gate, spent a full CI round trip proving that `sports` has
        # no `title` column. The check below was green on that INSERT, because
        # every NOT NULL column WAS supplied.
        strays = provided - set(Base.metadata.tables[table].columns.keys())
        if strays:
            unknown.append((table, sorted(strays)))
        gap = _required(table) - provided
        if gap:
            missing.append((table, sorted(gap)))

    assert not unknown, (
        f"{filename} seeds with raw INSERT and names columns that do not exist: "
        f"{unknown}. Same failure mode as the NOT NULL check below — the gate "
        "dies before its first assertion and, being skipped without a Postgres, "
        "reports it only in CI."
    )

    assert not missing, (
        f"{filename} seeds with raw INSERT and omits NOT NULL columns with no "
        f"server default: {missing}. This gate cannot run — it dies on "
        "NotNullViolationError before reaching its assertion, and because it is "
        "skipped without a Postgres you will only find out in CI, on a job "
        "`deploy` needs."
    )


def test_the_insert_select_exclusion_cannot_wave_through_a_values_seed():
    """The #6215 exclusion is narrow, asserted rather than asserted-about.

    `_insert_keywords` subtracts `INSERT ... SELECT` so a gate whose SUBJECT is
    such a statement can satisfy the parse-everything tripwire. The risk of any
    subtraction is that it grows and starts excusing the very seeds this file
    exists for, so both directions are pinned here, and the fired-count is
    measured rather than hoped: the exclusion currently matches in exactly ONE
    covered file — the one it was written for.
    """
    assert not _INSERT_SELECT_RE.search(
        'INSERT INTO teams (name, sport_id) VALUES (:n, :s)'
    ), "a VALUES seed is being excused — the exclusion has stopped being narrow"
    assert _INSERT_SELECT_RE.search(
        'INSERT INTO bak (team_id, name) SELECT id, name FROM teams'
    )

    fired = {
        name: len(_INSERT_SELECT_RE.findall(_joined_source(path)))
        for name in COVERED
        if (path := INTEGRATION_DIR / name).exists()
    }
    assert {k: v for k, v in fired.items() if v} == {
        "test_backup_round_trip_jsonb_6215_pg.py": 1
    }, (
        "the INSERT...SELECT exclusion now fires somewhere new. That is not "
        "automatically wrong, but it means another gate's statements stopped "
        f"being read by the column check — say why here: {fired}"
    )


def test_every_raw_insert_gate_is_covered():
    """No real-Postgres gate may seed with raw INSERT and escape the check above.

    A gate is identified by its `*TEST_DATABASE_URL` env gate, NOT by filename —
    `*_pg.py` is a convention several of these gates predate. Do NOT widen this
    to every file containing an INSERT: `test_route_admin_db_query.py` carries
    `"INSERT INTO events (id) VALUES (1)"` as a rejection fixture, an INSERT
    that is SUPPOSED to be invalid, and flagging it would be a false red on a
    test doing its job.
    """
    uncovered = sorted(
        p.name
        for p in INTEGRATION_DIR.glob("test_*.py")
        if p.name not in COVERED
        and "TEST_DATABASE_URL" in p.read_text()
        and _inserts(p)
    )
    assert not uncovered, (
        f"these real-Postgres gates seed with raw INSERT but are not in COVERED: "
        f"{uncovered}. Add them — a gate whose seed is unchecked is a gate that "
        "will first report its own bug as a red deploy."
    )


#: Real-Postgres gates that exist, cannot run outside CI, and that no CI step
#: invokes. Every name here has NEVER EXECUTED. This is a disclosure, not a
#: permission: it is frozen at the set CAL-P157 measured, so a new gate cannot
#: join it silently.
#:
#: `test_feed_static_tag_filter_pg.py` — found by the arm below, owned by the
#: feed, not wired here because switching on a never-run gate is a change whose
#: blast radius belongs to the lane that can read its failures.
_NEVER_WIRED = {"test_feed_static_tag_filter_pg.py"}

CI_WORKFLOW = Path(__file__).resolve().parents[2] / ".github" / "workflows" / "ci.yml"


def test_every_real_postgres_gate_is_wired_into_ci():
    """A gate no CI step names is a gate that has never once run.

    These files skip on every machine a human or an agent uses — `initdb` dies on
    `shmget` in the sandbox — so `search-recall` is their only reader, and it
    names each file in a hand-written step. Adding the file is therefore not
    adding the gate, and the difference is invisible: the suite goes green either
    way, and "0 skipped" is only asserted inside the step that does not exist.

    `test_search_latency_contract.py` already makes this check, parametrized over
    two hardcoded search gates. Hardcoding is what let a third slip past, so this
    one DISCOVERS instead.
    """
    workflow = yaml.safe_load(CI_WORKFLOW.read_text())
    job = workflow["jobs"]["search-recall"]
    invoked = "\n".join(s.get("run") or "" for s in job["steps"])

    unwired = sorted(
        p.name
        for p in INTEGRATION_DIR.glob("test_*.py")
        if p.name not in _NEVER_WIRED
        and "TEST_DATABASE_URL" in p.read_text()
        and f"tests/integration/{p.name}" not in invoked
    )
    assert not unwired, (
        f"these gates require a real Postgres and no `search-recall` step runs "
        f"them: {unwired}. They skip everywhere else, so they have never "
        f"executed — add a step (with the all-skipped detector its neighbours "
        f"carry) rather than letting the file's existence read as coverage."
    )


def test_the_never_wired_allowlist_has_not_grown_stale():
    """An allowlist that outlives its entries is the next silent gap.

    If a name here gets wired, or deleted, this fails and the disclosure comes
    out with it.
    """
    workflow = yaml.safe_load(CI_WORKFLOW.read_text())
    invoked = "\n".join(
        s.get("run") or "" for s in workflow["jobs"]["search-recall"]["steps"]
    )
    stale = sorted(
        name
        for name in _NEVER_WIRED
        if not (INTEGRATION_DIR / name).exists()
        or f"tests/integration/{name}" in invoked
    )
    assert not stale, (
        f"these names are allowlisted as never-wired but are now wired or gone: "
        f"{stale}. Remove them from _NEVER_WIRED."
    )


def test_every_search_recall_step_that_runs_something_has_a_name():
    """An unnamed gate step is unreadable in the only place it ever reports.

    `- name: #3672 …` is a YAML COMMENT, not a name: the `#` after the space
    starts one, `name:` resolves to null, and the step runs anonymously. It does
    not fail the build — which is the problem. `search-recall` is a wall of
    hand-written gate steps whose entire diagnostic value is which NAME went
    red, and an anonymous one reports as a bare "Run" in the UI.

    The repo already writes these correctly — `"#1852 fabricated-loss drain bind
    contract (real Postgres)"` and `"#2722 …"` are both quoted. This exists so
    the next person who forgets the quotes finds out in the sandbox.
    """
    workflow = yaml.safe_load(
        (Path(__file__).resolve().parents[2] / ".github" / "workflows" / "ci.yml").read_text()
    )
    anonymous = [
        step
        for step in workflow["jobs"]["search-recall"]["steps"]
        if "run" in step and not step.get("name")
    ]
    assert not anonymous, (
        f"{len(anonymous)} search-recall step(s) run something under no name — "
        f"a `#`-leading name must be QUOTED or YAML eats it as a comment. "
        f"First command: {anonymous[0]['run'].strip().splitlines()[0]!r}"
    )
