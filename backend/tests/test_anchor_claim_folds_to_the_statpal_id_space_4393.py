"""A registry claim is keyed by StatPal's ID SPACE, not by our `sports.key` — #4393.

`statpal_anchor_key(fixture_id, sport_key)` is deliberately FAITHFUL to the
qualifier it is handed; picking the honest qualifier is the caller's job, and
`provider_anchor_keys` ships the function that does it — `statpal_id_space()`,
which folds every `tennis*` key to `tennis` and every `soccer*` key to `soccer`
because StatPal numbers each of those sports in ONE sequence while our
`sports.key` vocabulary splits them across ~30 and 59 keys respectively.

Every StatPal anchor writer folded. The registry did not:

    stamp_v1_statpal_fixtures.py:1240/1264/1318   statpal_id_space(spec.sport_key)   OK
    stamp_nfl_statpal_fixtures.py:448             statpal_id_space(NFL_SPORT_KEY)    OK
    link_tennis_statpal_fixtures.py:685/773       statpal_id_space(...)              OK
    admin_providers.py:2153                       statpal_id_space(sport_key)        OK
    event_registry.py:657  (_find_by_anchor)      identity.sport_key, RAW            <-
    event_registry.py:712  (_record_claim_anchor) identity.sport_key, RAW            <-

Both reach the key module through `anchor_channel.anchor_key_for_claim`, which is
where the fold now lives — the function whose one-line contract is *"map a
registry claim onto its namespace-qualified anchor key"*. `statpal_anchor_key`
itself is untouched, so `test_link_tennis_statpal_anchors.py::
test_the_control_the_raw_sport_key_would_fragment_it` — the control written to
fail if that builder ever becomes a folding pass-through — stays green, and this
file's own control below re-states it from the other side.

## WHAT THE FOLD ACTUALLY BUYS, stated narrowly on purpose

It is a WRITE-side property. Step 2's read is, for StatPal, largely subsumed by
Step 1 already: `find_event_by_anchor` refuses a cross-sport hit AND requires
`anchor_is_current` (the event still carries the id in `events.statpal_fixture_id`),
and a claim satisfying both would have been answered by Step 1's column read
first. Saying otherwise would overclaim, so this file does not test a read-side
absorption that the fold does not deliver.

What it delivers is that the StatPal id space stays ONE key per match:

  * `_record_claim_anchor` writes `soccer:9541493`, never
    `soccer_epl:9541493` beside `soccer_argentina_primera_division:9541493`.
    The unique index `(source, source_id, id_kind)` would have accepted all
    three, and `record_anchor`'s `COLLISION` — described in its own docstring as
    *"the first moment the system holds proof, keyed on an id rather than guessed
    from names and a time window, that two rows are one game"* — can only fire
    when both writers spell the key the same way.
  * So a second row minted for a match the hourly soccer stamper has already
    anchored CONFLICTS (logged, no second anchor row) instead of writing a clean
    key that makes two rows look like two games. That is `TestTheCollisionCanFire`.
  * And `anchor_is_current` re-derives the same key the stampers wrote, so a
    fragmented `soccer_epl:` row — of which production has zero — reads as STALE
    rather than authoritative.

## Blast radius, measured before the edit (production, 2026-09-09 ~10:0x PT)

All 1,040 StatPal anchors carry one of six qualifiers, and every one is already
its own id space, so the fold is the identity on every stored row:

    americanfootball_nfl 293 | soccer 256 | tennis 248
    baseball_mlb         175 | basketball_nba 41 | icehockey_nhl 27

`source_id LIKE 'soccer\\_%' OR LIKE 'tennis\\_%'` -> 0 rows. And the four sports
`_sync_statpal_schedules` has beats for (`app/tasks/__init__.py:5054-5073`) are
all 1:1, so no live claim changes either. `TestTheProductionRowsDoNotMove` and
`TestTheFourBeatSportsAreByteIdentical` are the both-arms half of gotcha #43:
a guard that only proves the new key appears is half a guard.
"""
from datetime import datetime, timezone

import pytest

from app.services.anchor_channel import anchor_key_for_claim
from app.services.event_registry import (
    EventClaim,
    EventIdentity,
    _sport_id_cache,
    find_or_create_event,
)
from app.utils.provider_anchor_keys import (
    ANCHOR_KIND_GAME,
    statpal_anchor_key,
    statpal_id_space,
    statpal_sport_from_source_id,
)
from tests.test_anchor_channel_consumer_2213 import _AnchorSession, _row

#: The specimen #3607 names by name: StatPal lists `Banfield v Dep. Riestra`
#: and we hold zero rows for it. Argentine Primera is a league we carry (424
#: rows), so this is a discovery gap in a bucket that exists — which is exactly
#: the claim that would come through the registry the day a soccer beat is
#: scheduled.
SOCCER_FIXTURE_ID = "9541493"
#: The tennis fixture #2879 used, in the id space that made tennis anchorable.
TENNIS_FIXTURE_ID = "2631673"
#: An NFL `contestid` — 6 digits, the token that made the digit rule wrong.
NFL_FIXTURE_ID = "280445"

#: Our soccer keys, drawn from production (59 `soccer%` keys on 2026-09-09).
#: Six of the seven `STATPAL_SPORT_MAPPING` names plus two that the map does NOT
#: carry, deliberately: the hourly soccer stamper writes `statpal_fixture_id`
#: across every `soccer%` sport (34 of them measured), so the keys a claim can
#: arrive under are not bounded by the schedule map.
SOCCER_SPORT_KEYS = (
    "soccer_epl",
    "soccer_usa_mls",
    "soccer_spain_la_liga",
    "soccer_germany_bundesliga",
    "soccer_italy_serie_a",
    "soccer_uefa_champs_league",
    "soccer_argentina_primera_division",
    "soccer_other",
)

#: Our tennis keys. The generic pair plus the per-tournament ones that are minted
#: per event — the split that makes a generic row and a tournament row for one
#: match look like two matches (#2937, #3644).
TENNIS_SPORT_KEYS = (
    "tennis_atp",
    "tennis_wta",
    "tennis_other",
    "tennis_atp_us_open",
    "tennis_wta_us_open",
)

#: The four sports `_sync_statpal_schedules` actually has beats for. For every
#: one of these `statpal_id_space(key) is key`, which is why nothing live moves.
BEAT_SPORT_KEYS = (
    "americanfootball_nfl",
    "baseball_mlb",
    "basketball_nba",
    "icehockey_nhl",
)

#: Every qualifier present in `event_provider_anchors` on 2026-09-09, with its
#: measured row count. Each must be a FIXED POINT of the fold or a stored row
#: would stop being findable by the key that wrote it.
PRODUCTION_QUALIFIERS = {
    "americanfootball_nfl": 293,
    "soccer": 256,
    "tennis": 248,
    "baseball_mlb": 175,
    "basketball_nba": 41,
    "icehockey_nhl": 27,
}

EPL_SPORT_ID = 71001
SOCCER_OTHER_SPORT_ID = 71002
NFL_SPORT_ID = 71003

INCUMBENT_ROW_ID = 15410001

GAME_TIME = datetime(2026, 9, 9, 22, 0, tzinfo=timezone.utc)


def _identity(source_id, *, sport_key, home, away):
    return EventIdentity(
        sport_key=sport_key,
        home_team_name=home,
        away_team_name=away,
        commence_time=GAME_TIME,
        claim=EventClaim("statpal", source_id),
        commence_time_source="statpal",
        status="scheduled",
    )


def _statpal_keys(session):
    return {
        source_id
        for (source, source_id, _kind) in session.anchors
        if source == "statpal"
    }


# ══════════════════════════════════════════════════════════════════════════
# The fold itself, at the claim boundary
# ══════════════════════════════════════════════════════════════════════════

class TestOneStatPalMatchYieldsOneAnchorKey:

    def test_every_soccer_sports_key_folds_to_the_soccer_space(self):
        """59 of our keys, one StatPal sequence, one anchor key.

        A single `matches/live` board carried 195 matches across 113 leagues on
        2026-09-07 and its ids are unique across the whole board, not per league
        (`statpal_id_space`'s docstring, with the payload behind it). Qualifying
        by `sports.key` would therefore write one key per LEAGUE for one match.
        """
        keys = {
            anchor_key_for_claim(
                "statpal", SOCCER_FIXTURE_ID, sport_key=k
            ).source_id
            for k in SOCCER_SPORT_KEYS
        }
        assert keys == {f"soccer:{SOCCER_FIXTURE_ID}"}, (
            "one StatPal soccer match must yield exactly one anchor key across "
            f"every soccer sports.key; got {sorted(keys)}"
        )

    def test_every_tennis_sports_key_folds_to_the_tennis_space(self):
        """The same property for tennis, where the split is generic vs tournament."""
        keys = {
            anchor_key_for_claim(
                "statpal", TENNIS_FIXTURE_ID, sport_key=k
            ).source_id
            for k in TENNIS_SPORT_KEYS
        }
        assert keys == {f"tennis:{TENNIS_FIXTURE_ID}"}

    def test_the_control_the_unfolded_builder_still_fragments(self):
        """The arm that shows the two tests above can fail.

        `statpal_anchor_key` must stay faithful to its argument — the fold is the
        claim boundary's job, not the builder's. If a future edit moves the fold
        down into the builder, this test starts failing and
        `test_link_tennis_statpal_anchors.py::
        test_the_control_the_raw_sport_key_would_fragment_it` fails with it.
        """
        raw = {
            statpal_anchor_key(SOCCER_FIXTURE_ID, k).source_id
            for k in SOCCER_SPORT_KEYS
        }
        assert len(raw) == len(SOCCER_SPORT_KEYS)


class TestTheFourBeatSportsAreByteIdentical:
    """Both arms of gotcha #43: prove what MOVED and prove what did NOT."""

    @pytest.mark.parametrize("sport_key", BEAT_SPORT_KEYS)
    def test_the_claim_boundary_agrees_with_the_faithful_builder(self, sport_key):
        """For a 1:1 sport the fold is the identity, byte for byte.

        Asserted against `statpal_anchor_key`'s own answer rather than a retyped
        f-string, so this cannot pass by two copies of the same typo.
        """
        folded = anchor_key_for_claim(
            "statpal", NFL_FIXTURE_ID, sport_key=sport_key
        )
        faithful = statpal_anchor_key(NFL_FIXTURE_ID, sport_key)
        assert folded == faithful
        assert folded.source_id == f"{sport_key}:{NFL_FIXTURE_ID}"

    def test_nfl_and_mlb_still_do_not_share_a_key(self):
        """D55's actual property, unchanged: one 6-digit token, two sports."""
        nfl = anchor_key_for_claim(
            "statpal", NFL_FIXTURE_ID, sport_key="americanfootball_nfl"
        )
        mlb = anchor_key_for_claim(
            "statpal", NFL_FIXTURE_ID, sport_key="baseball_mlb"
        )
        assert nfl.source_id != mlb.source_id


class TestTheProductionRowsDoNotMove:

    @pytest.mark.parametrize("qualifier", sorted(PRODUCTION_QUALIFIERS))
    def test_every_stored_qualifier_is_a_fixed_point(self, qualifier):
        """A stored anchor must stay findable by the key that wrote it.

        The fold is applied on the READ path too (`_find_by_anchor`,
        `anchor_is_current`), so a qualifier that is not a fixed point would
        darken every row carrying it. All six in production are.
        """
        assert statpal_id_space(qualifier) == qualifier
        assert anchor_key_for_claim(
            "statpal", SOCCER_FIXTURE_ID, sport_key=qualifier
        ).source_id == f"{qualifier}:{SOCCER_FIXTURE_ID}"

    def test_a_stored_key_re_derives_to_itself(self):
        """`anchor_is_current`'s round trip, which is how a stale anchor is told
        from a live one. It reads the sport back OFF the key and asks for the key
        again; if the fold were not idempotent every soccer and tennis anchor in
        production would read as stale and stop corroborating.
        """
        stored = f"soccer:{SOCCER_FIXTURE_ID}"
        sport = statpal_sport_from_source_id(stored)
        re_derived = anchor_key_for_claim(
            "statpal", SOCCER_FIXTURE_ID, sport_key=sport, warn_unqualified=False
        )
        assert re_derived.source_id == stored


class TestTheRefusalLadderIsUnchangedAndRunsFirst:
    """The fold order is load-bearing, not stylistic."""

    @pytest.mark.parametrize("qualifier", [None, "", "   "])
    def test_an_absent_or_blank_qualifier_still_refuses(self, qualifier):
        assert anchor_key_for_claim(
            "statpal", SOCCER_FIXTURE_ID, sport_key=qualifier
        ) is None

    def test_a_separator_bearing_qualifier_still_refuses(self):
        """The trap that decides where the fold goes.

        `statpal_id_space` matches on a PREFIX, so
        `statpal_id_space("soccer:9541493")` is `"soccer"`. Folding BEFORE the
        refusal check would promote a `STATPAL_QUALIFIER_SEPARATOR` refusal into
        a perfectly well-formed key — silently, and for the one shape
        `anchor_is_current` cannot split back apart.
        """
        assert statpal_id_space("soccer:9541493") == "soccer"
        assert anchor_key_for_claim(
            "statpal", SOCCER_FIXTURE_ID, sport_key="soccer:9541493"
        ) is None

    def test_the_refusal_holds_with_the_warning_suppressed(self):
        """`warn_unqualified=False` turns off the LOG, never the refusal."""
        assert anchor_key_for_claim(
            "statpal", SOCCER_FIXTURE_ID, sport_key=None, warn_unqualified=False
        ) is None


class TestOnlyStatPalIsFolded:

    def test_kalshi_is_keyed_by_our_sport_key_and_must_not_fold(self):
        """Kalshi's id space is per-OUR-sport-key by Alex's 2026-08-21 ruling.

        Folding it would rewrite `tennis_atp:26AUG30BUBWOL` to
        `tennis:26AUG30BUBWOL` and orphan every Kalshi anchor — the exact
        opposite defect, in a provider whose namespace is correctly ours. The
        fold lives inside the `source == "statpal"` branch for this reason.
        """
        key = anchor_key_for_claim("kalshi", "KXATPMATCH-26AUG30BUBWOL")
        assert key is not None
        assert not key.source_id.startswith("tennis:")

    @pytest.mark.parametrize("source", ["espn", "odds_api"])
    def test_the_id_only_providers_ignore_the_sport_entirely(self, source):
        with_sport = anchor_key_for_claim(
            source, "401772510", sport_key="soccer_epl"
        )
        without = anchor_key_for_claim(source, "401772510")
        assert with_sport == without


# ══════════════════════════════════════════════════════════════════════════
# Behavioural, on the registry's own call site
# ══════════════════════════════════════════════════════════════════════════

@pytest.fixture(autouse=True)
def _seed_sport_cache():
    _sport_id_cache["soccer_epl"] = EPL_SPORT_ID
    _sport_id_cache["soccer_other"] = SOCCER_OTHER_SPORT_ID
    _sport_id_cache["americanfootball_nfl"] = NFL_SPORT_ID
    yield
    for key in ("soccer_epl", "soccer_other", "americanfootball_nfl"):
        _sport_id_cache.pop(key, None)


class TestTheCollisionCanFire:
    """The write-side property, end to end through `find_or_create_event`.

    The scenario is the one #3607 step 3 walks into on its first pass: the hourly
    soccer stamper has already anchored a match under `soccer:<id>` on a row in
    one of our soccer keys, and the ingest claims the same StatPal fixture under
    a DIFFERENT soccer key (StatPal serves all 113 leagues from one board; our
    side splits them across 59 keys, and `STATPAL_SPORT_MAPPING` names only 7).

    Step 1 refuses the cross-sport absorption and logs it (`_find_statpal_row_in_sport`).
    Step 2 refuses it too (`find_event_by_anchor`'s `expected_sport_id`). So a row
    IS created — that part the fold does not change and this test does not pretend
    otherwise. What changes is whether the second row gets its own clean anchor
    key, i.e. whether the duplicate leaves a trace.
    """

    @staticmethod
    def _incumbent():
        """The row the soccer stamper already anchored, in another soccer key."""
        return _row(
            event_id=INCUMBENT_ROW_ID,
            sport_id=SOCCER_OTHER_SPORT_ID,
            home="Banfield",
            away="Dep. Riestra",
            commence=GAME_TIME,
            status="scheduled",
            statpal_fixture_id=SOCCER_FIXTURE_ID,
            commence_time_source="statpal",
        )

    def _session(self):
        incumbent = self._incumbent()
        return _AnchorSession(
            sport_id=EPL_SPORT_ID,
            source_matches={SOCCER_FIXTURE_ID: incumbent},
            structured_candidates=[incumbent],
            anchors={
                ("statpal", f"soccer:{SOCCER_FIXTURE_ID}", ANCHOR_KIND_GAME):
                    INCUMBENT_ROW_ID
            },
            event_sports={INCUMBENT_ROW_ID: SOCCER_OTHER_SPORT_ID},
        )

    @pytest.mark.asyncio
    async def test_the_second_row_does_not_get_a_second_namespace(self):
        session = self._session()

        event, created = await find_or_create_event(
            session,
            _identity(
                SOCCER_FIXTURE_ID, sport_key="soccer_epl",
                home="Banfield", away="Dep. Riestra",
            ),
        )

        assert created and event.id != INCUMBENT_ROW_ID

        assert _statpal_keys(session) == {f"soccer:{SOCCER_FIXTURE_ID}"}, (
            "one StatPal fixture must occupy exactly one slot in the "
            "(source, source_id, id_kind) index no matter which of our soccer "
            "keys claimed it"
        )
        assert session.anchors[
            ("statpal", f"soccer:{SOCCER_FIXTURE_ID}", ANCHOR_KIND_GAME)
        ] == INCUMBENT_ROW_ID, "first writer wins; the incumbent is never repointed"

    @pytest.mark.asyncio
    async def test_the_write_was_attempted_against_the_stampers_key(self):
        """The collision is only proof if the second writer reached the same key.

        Asserted on `anchor_writes` — what the registry TRIED — rather than on
        `anchors`, which records only what survived `ON CONFLICT DO NOTHING`. An
        assertion on the survivor alone would pass just as well if the registry
        had written nothing at all.
        """
        session = self._session()

        event, _created = await find_or_create_event(
            session,
            _identity(
                SOCCER_FIXTURE_ID, sport_key="soccer_epl",
                home="Banfield", away="Dep. Riestra",
            ),
        )

        attempted = {(key[1], event_id) for key, event_id in session.anchor_writes}
        assert (f"soccer:{SOCCER_FIXTURE_ID}", event.id) in attempted

    @pytest.mark.asyncio
    async def test_the_control_the_league_qualified_key_is_never_written(self):
        """The arm that fails without the fold.

        Before #4393 this run wrote `soccer_epl:9541493` cleanly beside the
        stamper's `soccer:9541493`: two keys, one match, `WROTE` instead of
        `COLLISION`, and no signal anywhere that two of our rows are one game.
        """
        session = self._session()

        await find_or_create_event(
            session,
            _identity(
                SOCCER_FIXTURE_ID, sport_key="soccer_epl",
                home="Banfield", away="Dep. Riestra",
            ),
        )

        assert f"soccer_epl:{SOCCER_FIXTURE_ID}" not in _statpal_keys(session)
        assert all(
            key[1] != f"soccer_epl:{SOCCER_FIXTURE_ID}"
            for key, _event_id in session.anchor_writes
        )


class TestTheBeatSportsRunUnchangedEndToEnd:
    """The healthy-sibling arm: the four sports that DO run must not move."""

    @pytest.mark.asyncio
    async def test_an_nfl_claim_still_writes_its_own_sport_key(self):
        session = _AnchorSession(sport_id=NFL_SPORT_ID)

        event, created = await find_or_create_event(
            session,
            _identity(
                NFL_FIXTURE_ID, sport_key="americanfootball_nfl",
                home="Los Angeles Rams", away="San Francisco 49ers",
            ),
        )

        assert created
        assert session.anchors == {
            ("statpal", f"americanfootball_nfl:{NFL_FIXTURE_ID}", ANCHOR_KIND_GAME):
                event.id
        }
