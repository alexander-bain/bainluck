"""#6215 — Fluminense stops being a Premier League club wearing Arsenal's badge.

**SHIP: searching "Deportivo" stops returning three Latin American clubs
captioned "· EPL" with Arsenal's, Chelsea's and Manchester City's initials and
records.** (Pillar: TRUTH.)

Filed by live/242 from a 390px production mystery shop on 2026-09-14, and the
stored rows are worse than the shot: ``teams`` holds 192 rows under
``soccer_epl`` — a league of twenty clubs — sharing 21 abbreviations, and 143 of
the borrowed ones are bound to real fixtures by ``events.home_team_id`` /
``away_team_id``, so the wrong badge travels to every surface that resolves a
team off an FK.

    id 4513  name 'Fluminense'  abbreviation 'ARS'  current_record '19-7-3'
             location 'Arsenal'  espn_id NULL  logo NULL  alternate_names NULL
    id  133  name 'Arsenal'     abbreviation 'ARS'  current_record '4-0-0'
             location 'Arsenal'  espn_id '359'   logo set

Measured here 2026-09-14 20:5xZ over the whole table, not just the league live
looked at: **1,077 rows carry ESPN identity fields with no ESPN id, and 937 of
the first 1,000 wear a name that does not correspond to their own** — MLS 581,
NCAAB 168, EPL 162, WNCAAB 26. "Marist Red Foxes" reads ``OSU · 18-11 · Ohio
State``; "Butler Bulldogs" reads ``OKST · 21-7 · Oklahoma State``.

TWO WRITERS, AND THE SECOND IS WHY THE ROWS LOOK HALF-CLEANED
══════════════════════════════════════════════════════════════

1. :func:`app.utils.espn_helpers.upsert_team` adopts the payload. Its guard —
   ``if team.espn_id and team.espn_id != espn_team.espn_id`` — is written to
   catch exactly this ("mismatched ESPN data, e.g. from a wrong event-level
   match", its own comment) and **cannot fire for a row with no espn_id**,
   which is the row created twelve lines above it.

2. ``espn_sync._cleanup_bad_espn_matches`` later DETECTED those bad matches and
   cleared ``espn_id``, logos, colours and ``alternate_names`` — and left
   ``abbreviation``, ``current_record`` and ``location``. That is the exact
   fingerprint of row 4513, and it is why the alarm went quiet while the lie
   stayed on the page.

So this file pins both halves: the payload is refused at the door, and a clear
that says "all ESPN-sourced data" covers the three fields a reader sees.

WHAT IS NOT CLAIMED HERE
════════════════════════

The ~1,010 rows already carrying a borrowed identity are NOT repaired by this
change: the cleanup only visits rows that still have an ``espn_id``, and these
no longer do. They are #6215's named remainder, measured and stated, not
quietly folded into a green test.

THE COST OF THE GUARD, MEASURED AND PINNED RATHER THAN HIDDEN
═══════════════════════════════════════════════════════════════

Run over the 1,000 production rows that DID adopt an ESPN identity legitimately
(``espn_id`` and ``alternate_names`` both set), the predicate accepts 991.
Of the nine it refuses, four are this very defect already in the data
("Ohio State Buckeyes" carrying Texas State's names). The remaining five are
genuine aliases, and :class:`TestTheMeasuredAliasCost` pins them — refused
without the alias, adopted once the row knows it.
"""

import pytest

# Imported inside the tests, not at module scope, so this file COLLECTS on the
# parent commit. A control run that dies at import proves only that a new symbol
# is new; the witness that matters is
# `TestTheGuardIsWiredIntoTheWriter::test_a_new_row_does_not_take_another_clubs_badge`
# FAILING on the parent with `abbreviation == 'ARS'` — a wrong VALUE, which an
# ImportError at line 64 would have hidden behind exit 2 (gotcha #124).


def espn_identity_corresponds(*args):
    from app.utils.espn_helpers import (
        espn_identity_corresponds as _impl,
    )

    return _impl(*args)


def clear_espn_sourced_identity(team):
    from app.tasks.espn_sync import clear_espn_sourced_identity as _impl

    return _impl(team)


def _identity_fields():
    from app.tasks.espn_sync import ESPN_SOURCED_IDENTITY_FIELDS

    return ESPN_SOURCED_IDENTITY_FIELDS


class _EspnTeam:
    """An ESPN payload. Any field not named reads as absent, like the real one.

    Permissive on absent fields on purpose: several ESPN endpoints populate only
    a subset, and a fake that must enumerate twelve fields to run is a fake that
    stops being run.
    """

    espn_id = None
    name = None
    abbreviation = None
    display_name = None
    short_name = None
    nickname = None
    primary_color = None
    secondary_color = None
    logo_url = None
    logo_url_dark = None
    record = None
    location = None

    def __init__(self, **fields):
        for key, value in fields.items():
            assert hasattr(type(self), key), f"{key} is not an ESPNTeam field"
            setattr(self, key, value)


#: ESPN's real Arsenal payload, as `_parse_team` builds it from the scoreboard.
ARSENAL = _EspnTeam(
    espn_id="359",
    name="Arsenal",
    display_name="Arsenal",
    short_name="Arsenal",
    abbreviation="ARS",
    record="19-7-3",
    location="Arsenal",
    primary_color="#e20520",
    logo_url="https://a.espncdn.com/i/teamlogos/soccer/500/359.png",
)


class TestTheProductionSpecimens:
    """Every row in the table below is a real one, read on 2026-09-14."""

    @pytest.mark.parametrize(
        "our_name, espn",
        [
            # The four EPL cohorts live/242 measured (62 + 62 + 21 + 21 rows).
            ("Fluminense", ARSENAL),
            ("Colo Colo", ARSENAL),
            ("Argentinos Jrs", ARSENAL),
            (
                "Deportivo Maipú",
                _EspnTeam(
                    espn_id="363", name="Chelsea", display_name="Chelsea",
                    abbreviation="CHE", record="12-9-7", location="Chelsea",
                ),
            ),
            (
                "Deportivo Universitario",
                _EspnTeam(
                    espn_id="382", name="Manchester City",
                    display_name="Manchester City", abbreviation="MNC",
                    record="18-5-5", location="Manchester City",
                ),
            ),
            # Not a soccer problem: the same shape in two basketball leagues.
            (
                "Marist Red Foxes",
                _EspnTeam(
                    espn_id="194", name="Buckeyes", display_name="Ohio State Buckeyes",
                    abbreviation="OSU", record="18-11", location="Ohio State",
                ),
            ),
            (
                "Butler Bulldogs",
                _EspnTeam(
                    espn_id="197", name="Cowboys",
                    display_name="Oklahoma State Cowboys", abbreviation="OKST",
                    record="21-7", location="Oklahoma State",
                ),
            ),
            (
                "NJIT Highlanders",
                _EspnTeam(
                    espn_id="2579", name="Gamecocks",
                    display_name="South Carolina Gamecocks", abbreviation="SC",
                    record="12-18", location="South Carolina",
                ),
            ),
        ],
    )
    def test_a_club_does_not_answer_to_another_clubs_payload(self, our_name, espn):
        assert espn_identity_corresponds(our_name, None, espn) is False


class TestTheClubsThatDoCorrespond:
    """Controls. Each of these adopted correctly today and must keep doing so."""

    def test_the_real_arsenal_takes_arsenals_payload(self):
        assert espn_identity_corresponds("Arsenal", None, ARSENAL) is True

    @pytest.mark.parametrize(
        "our_name, espn_display",
        [
            # Production rows, all currently enriched and all correct.
            ("Leeds United", "Leeds"),
            ("Nottingham Forest", "Nottm Forest"),
            ("Virginia Cavaliers", "Virginia"),
            ("Stanford", "Stanford Cardinal"),
        ],
    )
    def test_a_shorter_or_longer_spelling_of_the_same_club_corresponds(
        self, our_name, espn_display
    ):
        espn = _EspnTeam(espn_id="1", display_name=espn_display, name=espn_display)
        assert espn_identity_corresponds(our_name, None, espn) is True

    def test_any_one_populated_field_is_enough(self):
        """Endpoints differ in which name they populate; one is enough."""
        for field in ("display_name", "name", "short_name", "nickname", "location"):
            espn = _EspnTeam(espn_id="359", **{field: "Arsenal"})
            assert espn_identity_corresponds("Arsenal", None, espn) is True, field

    def test_the_abbreviation_alone_is_not_a_name(self):
        """`ARS` is how the lie is spelled, so it may not be how it is proved.

        A three-letter code carries no name to compare; admitting it would let
        the very field the defect writes vouch for the payload that wrote it.
        """
        espn = _EspnTeam(espn_id="359", abbreviation="ARS", record="19-7-3")
        assert espn_identity_corresponds("ARS", None, espn) is False


class TestFailClosed:
    def test_a_payload_that_names_nobody_is_refused(self):
        """Silence is not correspondence.

        An ESPN object with no name field populated cannot be shown to be about
        this club, and identity is not a field to overwrite on a maybe.
        """
        espn = _EspnTeam(espn_id="359", abbreviation="ARS", record="19-7-3")
        assert espn_identity_corresponds("Fluminense", None, espn) is False

    def test_an_unnamed_row_is_refused(self):
        assert espn_identity_corresponds(None, None, ARSENAL) is False
        assert espn_identity_corresponds("", None, ARSENAL) is False


class TestTheMeasuredAliasCost:
    """The five legitimate pairs the predicate refuses, and their way back.

    Measured over the 1,000 production rows that carry both an ``espn_id`` and
    ``alternate_names``: 991 correspond, four of the nine refusals are this
    defect already stored, and these five are the real cost. They are written
    down rather than argued away, and each one is recoverable — the row's own
    aliases are the second half of the comparison.
    """

    ALIASES = [
        ("Rennes", "Stade Rennais"),
        ("FSV Mainz 05", "Mainz"),
        ("Inter Milan", "Internazionale"),
        ("Chelsea", "Blues"),
    ]

    @pytest.mark.parametrize("our_name, espn_name", ALIASES)
    def test_without_the_alias_the_payload_is_refused(self, our_name, espn_name):
        espn = _EspnTeam(espn_id="1", display_name=espn_name, name=espn_name)
        assert espn_identity_corresponds(our_name, None, espn) is False

    @pytest.mark.parametrize("our_name, espn_name", ALIASES)
    def test_a_row_that_knows_its_own_alias_adopts(self, our_name, espn_name):
        espn = _EspnTeam(espn_id="1", display_name=espn_name, name=espn_name)
        assert espn_identity_corresponds(our_name, [espn_name], espn) is True

    def test_an_alias_does_not_let_a_different_club_in(self):
        """Recoverability is not a hole: knowing one alias admits that alias."""
        espn = _EspnTeam(espn_id="1", display_name="Internazionale")
        assert espn_identity_corresponds("Fluminense", ["Internazionale"], espn) is True
        assert espn_identity_corresponds("Fluminense", ["Flu"], ARSENAL) is False


class _FakeResult:
    def __init__(self, rows=()):
        self._rows = list(rows)

    def scalar_one_or_none(self):
        return self._rows[0] if self._rows else None

    def scalars(self):
        return iter(self._rows)


class _FakeSession:
    """Enough session for `upsert_team`: two reads, an add and a flush.

    A real async session would need Postgres, and this assertion is about one
    `if` — a guard that can only be exercised against a live database is a guard
    that gets asserted by source scan instead, which is how #6215 survived.
    """

    def __init__(self, existing=()):
        self._existing = list(existing)
        self.added = []
        self.flushes = 0

    async def execute(self, _stmt):
        return _FakeResult(self._existing)

    def add(self, obj):
        self.added.append(obj)

    async def flush(self):
        self.flushes += 1


class TestTheGuardIsWiredIntoTheWriter:
    """The predicate is only worth having if `upsert_team` consults it.

    Every assertion below is on the row the writer returns, not on the helper,
    so deleting the arm in `upsert_team` reddens this class even though
    `espn_identity_corresponds` stays perfect.
    """

    @pytest.mark.asyncio
    async def test_a_new_row_is_not_minted_at_all(self):
        """CERT-2877: refusing the BADGE was not enough, because the caption
        is the SPORT.

        `sport_id` is the caller's — the EVENT's — so a wrong event-level match
        creates the club under the wrong league, and `Deportivo Achuapa · EPL`
        is `teams.sport_id`, not `abbreviation`. Clearing the badge on a row
        minted under `soccer_epl` leaves the caption exactly as wrong, which is
        the false ship the grader caught. So the row is not created.
        """
        from app.utils.espn_helpers import upsert_team

        session = _FakeSession()
        stats = {}
        team = await upsert_team(
            session, "Fluminense", ARSENAL, sport_id=1298, stats=stats
        )

        assert team is None
        assert session.added == [], "a club was created under the wrong league"
        assert session.flushes == 0
        assert stats["teams_espn_mint_refused"] == 1

    @pytest.mark.asyncio
    async def test_an_existing_row_survives_un_enriched(self):
        """Refusing the mint must not become refusing the row.

        A club we already hold keeps its id, its name and its sport; only the
        payload is declined. This is the arm that would be lost if "refuse"
        were implemented as a bare early return before the lookup.
        """
        from app.models.models import Team
        from app.utils.espn_helpers import upsert_team

        flu = Team(name="Fluminense", sport_id=1298)
        flu.id = 4513
        session = _FakeSession([flu])
        stats = {}

        team = await upsert_team(
            session, "Fluminense", ARSENAL, sport_id=1298, stats=stats
        )

        assert team is flu
        assert team.espn_id is None
        assert team.abbreviation is None
        assert team.current_record is None
        assert team.location is None
        assert not team.alternate_names
        assert stats["teams_espn_identity_refused"] == 1
        assert "teams_espn_mint_refused" not in stats

    @pytest.mark.asyncio
    async def test_the_real_club_still_gets_everything(self):
        from app.utils.espn_helpers import upsert_team

        session = _FakeSession()
        stats = {}
        team = await upsert_team(
            session, "Arsenal", ARSENAL, sport_id=1298, stats=stats
        )

        assert team.espn_id == "359"
        assert team.abbreviation == "ARS"
        assert team.current_record == "19-7-3"
        assert team.location == "Arsenal"
        assert team.logo_url_small == ARSENAL.logo_url
        assert "teams_espn_identity_refused" not in stats
        assert stats["teams_upserted"] == 1

    @pytest.mark.asyncio
    async def test_an_id_anchored_row_is_still_enriched_when_the_names_disagree(self):
        """The id is a better witness than the spelling, and it is unchanged.

        Inter Milan carries ESPN's id already, so `Internazionale` needs no
        alias to keep its crest — this is the arm that existed before #6215 and
        it must not narrow.
        """
        from app.models.models import Team
        from app.utils.espn_helpers import upsert_team

        inter = Team(name="Inter Milan", sport_id=1300)
        inter.espn_id = "110"
        session = _FakeSession([inter])
        espn = _EspnTeam(
            espn_id="110", name="Internazionale", display_name="Internazionale",
            abbreviation="INT", record="10-2-1",
        )

        team = await upsert_team(session, "Inter Milan", espn, sport_id=1300)

        assert team is inter
        assert team.abbreviation == "INT"
        assert team.current_record == "10-2-1"

    @pytest.mark.asyncio
    async def test_the_id_mismatch_arm_is_untouched(self):
        from app.models.models import Team
        from app.utils.espn_helpers import upsert_team

        arsenal = Team(name="Arsenal", sport_id=1298)
        arsenal.espn_id = "359"
        arsenal.abbreviation = "ARS"
        session = _FakeSession([arsenal])
        wrong = _EspnTeam(
            espn_id="363", name="Chelsea", display_name="Chelsea",
            abbreviation="CHE", record="12-9-7",
        )

        team = await upsert_team(session, "Arsenal", wrong, sport_id=1298)

        assert team.espn_id == "359"
        assert team.abbreviation == "ARS"


class TestTheClearCoversWhatAReaderSees:
    """The second half: a detected bad match may not leave the badge behind."""

    class _Team:
        def __init__(self):
            self.espn_id = "359"
            self.logo_url_small = "logo"
            self.logo_url_large = "logo"
            self.primary_color = "#e20520"
            self.secondary_color = "#003399"
            self.alternate_names = ["Arsenal"]
            self.abbreviation = "ARS"
            self.current_record = "19-7-3"
            self.location = "Arsenal"
            self.name = "Fluminense"
            self.sport_id = 1298

    @pytest.mark.parametrize(
        "field", ["abbreviation", "current_record", "location"]
    )
    def test_the_three_a_reader_sees_are_cleared(self, field):
        """These three were omitted, and they are the whole of row 4513."""
        team = self._Team()
        clear_espn_sourced_identity(team)
        assert getattr(team, field) is None

    def test_the_fields_that_were_always_cleared_still_are(self):
        team = self._Team()
        clear_espn_sourced_identity(team)
        for field in (
            "logo_url_small",
            "logo_url_large",
            "primary_color",
            "secondary_color",
            "alternate_names",
        ):
            assert getattr(team, field) is None, field

    def test_the_clear_leaves_the_rows_own_identity_alone(self):
        """A clear is not a delete: the club's NAME and SPORT are not ESPN's."""
        team = self._Team()
        clear_espn_sourced_identity(team)
        assert team.name == "Fluminense"
        assert team.sport_id == 1298

    def test_espn_id_is_not_in_this_helper(self):
        """Deliberate: its write stays at the call site.

        The #2693 espn_id write census keys on the qualname that performs the
        write, and moving it here would have silently rewritten that map.
        """
        assert "espn_id" not in _identity_fields()

    def test_the_cleanup_still_clears_the_id_itself(self):
        """The half this helper does not own is still done by its caller."""
        import inspect

        from app.tasks import espn_sync

        source = inspect.getsource(espn_sync._cleanup_bad_espn_matches)
        assert "team.espn_id = None" in source
        assert "clear_espn_sourced_identity(team)" in source


# =============================================================================
# CERT-2881 — the shared-token rival class, over BOTH rails.
#
# The BLOCK, in one line: both the writer's admission and the repair's selection
# reused the house `names_match`, and `names_match` is a RECALL instrument whose
# stage 3 accepts any pair with >=0.5 token overlap. So the guard that exists to
# stop a club wearing another club's ESPN identity accepted Manchester United's
# row as Manchester City, and the repair built to clean that up classified the
# stored borrowed location as legitimate. A guard and a repair that are both
# wrong in the same direction leave the defect untouched and look correct.
#
# The pairs below are not invented. Every "must refuse" line is True under
# `names_match` today; every "must keep" line is a real row from the 1,000-row
# holdout measured 2026-09-14.
# =============================================================================

# Deferred exactly like the module-scope helpers above, and for the same reason
# this file records at line 64: a control that dies at IMPORT proves only that a
# symbol is new. `shared_token_rivals` does not exist on the parent commit, so a
# module-level import here would turn every witness below into exit 2 instead of
# the failing VALUE that shows the defect.


def shared_token_rivals(*args):
    from app.utils.name_normalization import shared_token_rivals as _impl

    return _impl(*args)


def names_match(*args):
    from app.utils.name_normalization import names_match as _impl

    return _impl(*args)


def _location_corresponds(*args):
    from scripts.repair_6215_borrowed_espn_identity import (
        location_corresponds as _impl,
    )

    return _impl(*args)


# Pairs the house matcher accepts and that are DIFFERENT CLUBS.
_RIVALS = [
    ("Manchester United", "Manchester City"),
    ("Manchester City", "Manchester United"),
    ("Real Madrid", "Real Sociedad"),
    ("New York Jets", "New York Giants"),
    ("Los Angeles Lakers", "Los Angeles Clippers"),
    ("Inter Milan", "AC Milan"),
    ("Qarabag FK", "Viking FK"),
    ("Morehead State", "Illinois State"),
]

# Pairs that are ONE club spelled two ways and must survive the veto. Each is a
# shape that broke an earlier draft of the rule, and each is a real row from the
# 1,000-row holdout.
#
# 🔴 THE TWO RAILS DISAGREE ABOUT SOME OF THESE, AND THE SPLIT IS THE POINT.
# `names_match("Duke Blue Devils", "Duke")` is FALSE — it refuses prefix
# containment on purpose — so on the WRITER rail those pairs never reach the
# veto at all; they are carried on the repair rail's own prefix arm. Asserting
# them through `espn_identity_corresponds` would be asserting pre-existing
# behaviour this change does not touch, and it would go red for a reason that
# has nothing to do with the veto. So `_SAME_CLUB_BOTH_RAILS` is the subset the
# house matcher accepts, and the prefix-only shapes are pinned on the repair
# rail alone.
_SAME_CLUB_BOTH_RAILS = [
    ("Seattle Seahawks", "Seattle Seahawks"),           # identical
    ("Leeds United", "Leeds United"),                   # identical
    ("Kansas St Wildcats", "Kansas State"),             # St / State abbreviation
    ("Michigan St Spartans", "Michigan State"),         # St / State abbreviation
    ("New York Red Bulls", "Red Bull New York"),        # word order + plural
    ("Hobart Statesmen", "Hobart College"),             # institution-type word
    ("Johns Hopkins Blue Jays", "Johns Hopkins University"),
    ("Athletic Bilbao", "Athletic Club"),               # institution-type word
    ("Nottingham Forest", "Nottm Forest"),              # truncation, drops the MIDDLE
]

#: One club, but a pair the house matcher declines — repair rail only.
_SAME_CLUB_REPAIR_RAIL_ONLY = [
    ("Duke Blue Devils", "Duke"),                       # mascot suffix
    ("Evansville Purple Aces", "Evansville"),           # mascot suffix
    ("Seattle Seahawks", "Seattle"),                    # city prefix, the US norm
    ("SE Missouri St Redhawks", "Southeast Missouri State"),
]


class _Payload:
    """The ESPN team shape `upsert_team` is handed."""

    def __init__(self, display_name=None, name=None, short_name=None,
                 nickname=None, location=None, abbreviation=None, record=None):
        self.display_name = display_name
        self.name = name
        self.short_name = short_name
        self.nickname = nickname
        self.location = location
        self.abbreviation = abbreviation
        self.record = record


@pytest.mark.parametrize("ours,theirs", _RIVALS)
def test_shared_token_rivals_never_share_espn_identity_6215(ours, theirs):
    """🔴 THE CERT-2881 SHIP, asserted on both rails from one table.

    The `names_match` assertion is not decoration: it pins that each pair really
    is one the house matcher accepts, so if `names_match` is ever tightened this
    test says so instead of passing vacuously on pairs that no longer reach the
    veto at all.
    """
    assert names_match(ours, theirs), (
        f"{ours!r}/{theirs!r} is no longer a names_match pair — this row has "
        "stopped testing the defect and must be re-chosen"
    )
    assert shared_token_rivals(ours, theirs)

    # Rail 1 — the WRITER. Their club-naming field carries the rival's name.
    assert not espn_identity_corresponds(
        ours, None, _Payload(display_name=theirs, name=theirs)
    ), f"upsert would stamp {theirs!r}'s ESPN identity onto {ours!r}"

    # Rail 2 — the REPAIR's selection.
    assert not _location_corresponds(ours, theirs), (
        f"the repair calls {ours!r} wearing {theirs!r}'s location legitimate, "
        "so it would skip the very rows it exists to clean"
    )


@pytest.mark.parametrize(
    "ours,theirs", _SAME_CLUB_BOTH_RAILS + _SAME_CLUB_REPAIR_RAIL_ONLY
)
def test_a_legitimate_alias_survives_the_rival_veto_6215(ours, theirs):
    """The control. A veto that refuses everything would pass the test above.

    Each pair is one club spelled two ways, and on the repair rail a false
    refusal is not a missing crest — it is a destructive UPDATE clearing a real
    club's identity. The naive form of this rule failed 86 of these.
    """
    assert not shared_token_rivals(ours, theirs)
    assert _location_corresponds(ours, theirs), (
        f"the repair would CLEAR {ours!r}, a real club, because its location "
        f"reads {theirs!r}"
    )


@pytest.mark.parametrize("ours,theirs", _SAME_CLUB_BOTH_RAILS)
def test_a_legitimate_alias_still_enriches_on_the_writer_rail_6215(ours, theirs):
    """...and the writer still adopts it, for the pairs that reach the veto."""
    assert names_match(ours, theirs), (
        f"{ours!r}/{theirs!r} no longer reaches the veto on the writer rail — "
        "move it to _SAME_CLUB_REPAIR_RAIL_ONLY rather than deleting it"
    )
    assert espn_identity_corresponds(
        ours, None, _Payload(display_name=theirs, name=theirs)
    ), f"{ours!r} would lose its ESPN identity to the rival veto"


def test_the_city_alone_can_never_establish_identity_6215():
    """The hole the rival rule cannot close, and the reason `location` is special.

    Manchester City's payload carries `location = "Manchester"`, and `Manchester`
    sits inside `Manchester United` with nothing left over — a strict subset, not
    a rival, so no token-rivalry test can refuse it. If the city is allowed to
    vouch by containment, United's row takes City's badge however good the rule
    above it is.
    """
    city_only = _Payload(location="Manchester")
    assert not espn_identity_corresponds("Manchester United", None, city_only)
    assert not espn_identity_corresponds("Manchester City", None, city_only)

    # ...but an exact city field still corroborates, which is how ESPN spells
    # several clubs, and the club-naming fields still answer first for the
    # ordinary US shape.
    assert espn_identity_corresponds(
        "Leeds United", None, _Payload(location="Leeds United")
    )
    assert espn_identity_corresponds(
        "Seattle Seahawks", None,
        _Payload(display_name="Seattle Seahawks", location="Seattle"),
    )


def test_the_veto_only_refuses_and_never_admits_6215():
    """`shared_token_rivals` is a veto, not a matcher.

    Two names with no shared token are not its question — answering True there
    would make it a second, disagreeing matcher, which is the failure ruling 048
    exists to end.
    """
    assert not shared_token_rivals("Fluminense", "Arsenal")
    assert not shared_token_rivals("", "Manchester City")
    assert not shared_token_rivals("Manchester City", None)


# ═══ The THIRD rail, and why the veto stops at two ═══════════════════════════

#: Real alias pairs the score backfill depends on, every one of them measured
#: as a pair `shared_token_rivals` WOULD refuse (2026-09-15, over 1,060 pairs
#: from 500 ESPN-anchored teams: `names_match` accepts 943, the veto would
#: refuse 10 — these nine plus one true rival).
_BACKFILL_ALIASES_THE_VETO_WOULD_COST = [
    ("New York Red Bulls", "NY Red Bulls"),
    ("New York Red Bulls", "Red Bull NY"),
    ("Crystal Palace", "C Palace"),
    ("Los Angeles Clippers", "LA Clippers"),
    ("Grand Canyon Antelopes", "Grand Canyon Lopes"),
    ("North Dakota St Bison", "N Dakota St"),
    ("Army Knights", "Black Knights"),
    ("Albany Great Danes", "UAlbany Great Danes"),
    ("Mt. St. Mary's Mountaineers", "Mount St. Mary's Mountaineers"),
]


@pytest.mark.parametrize("ours,theirs", _BACKFILL_ALIASES_THE_VETO_WOULD_COST)
def test_the_backfill_rail_keeps_its_aliases_6215(ours, theirs):
    """🔴 THE COST STILL DOES NOT TRANSFER — and this is the THIRD rail.

    `backfill_missing_scores` imported `shared_token_rivals` and never used it.
    Deleting a dead import is the obvious sweep, and it would have thrown away
    the finding: those imports marked an UNCONVERTED CALL SITE, which is usually
    a live bug. Here it is the opposite, and only measuring says which.

    That rail RECALLS a candidate ESPN game and then requires BOTH teams to
    agree; it does not decide an identity and write it down. Wiring the veto in
    would refuse nine real clubs' score backfill to refuse one true rival pair.
    So the veto stops at two rails ON PURPOSE, and this test is what a future
    "surely this one too" change runs into.

    Each pair below is asserted through the SAME predicate the backfill's local
    `names_match` closure calls, so if the import ever comes back, this reddens
    with the club that would have lost its score.
    """
    assert names_match(ours, theirs), (
        f"{ours!r}/{theirs!r} no longer matches — the score backfill has "
        "stopped recognising a real alias"
    )
    assert shared_token_rivals(ours, theirs), (
        f"{ours!r}/{theirs!r} is no longer a pair the veto would refuse, so "
        "this row has stopped documenting the cost and must be re-measured"
    )
