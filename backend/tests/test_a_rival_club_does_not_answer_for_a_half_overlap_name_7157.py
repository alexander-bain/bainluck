"""#7157 — a club that shares only its generic half stops adopting a rival's row.

**SHIP: no NEW fixture is bound to a club that merely shares the generic half of
its name — so a match card stops acquiring another club's crest, and a club page
stops acquiring fixtures it is not playing.** (Pillar: MATCHING.)

**NARROWED, and deliberately (CERT-3153, 2026-09-20 07:31Z).** This is FORWARD
PREVENTION ONLY. The three rows already wrong on `/api/teams/188` — events
15305209, 15305235 and 15297680 — are NOT drained by this change and this file
does not claim they are; see "WHAT IS NOT CLAIMED" below and #7410. The first
draft of this header said Manchester City's page "stops carrying" them, which
its own residual paragraph then contradicted. The grader was right; the claim is
withdrawn rather than defended.

Production, 2026-09-20, filed by the Schedule Sentinel as two `MISATTACHED /
critical` rows:

    event 15305235  Newcastle United  vs  'Hull City'      away_team_id=188 -> Manchester City
    event 15305209  Nottingham Forest vs  'Coventry City'  away_team_id=188 -> Manchester City

The row's OWN name field is right in both, so every name-based check passes them
(#1798's lesson). The id is wrong, and `teams` is the surface that carries the
crest, the colours and the club page's fixture list.

WHY 0.50 IS THE WHOLE STORY
═══════════════════════════

`names_match` is a RECALL instrument: stage 3 accepts any pair scoring >= 0.5
token overlap. A TWO-TOKEN club name that shares only its generic half scores
exactly 0.50, so it is accepted:

    token_overlap_score('Coventry City', 'Manchester City')  ==  0.50  -> match
    token_overlap_score('Air Force Falcons', 'Atlanta Falcons') == 0.33 -> no

`names_match`'s own docstring cites the Falcons pair as proof it is safe. It is
safe there only because those names have THREE tokens; at two, sharing the
mascot IS the threshold. Measured on the same production pass, every true
misattachment in the sentinel's open findings has this shape.

`shared_token_rivals` (#6215 / CERT-2881) already refuses all of them, and is
already the veto in front of `espn_identity_corresponds`. `upsert_team`'s two
pre-mint adoption scans are the rail it was never wired into — and in a league
holding exactly one club of that shape the scan returns ONE candidate, so the
`espn_identity_corresponds` disambiguation (which does carry the veto) never
runs. `soccer_epl` holds `Manchester City` and `New York City` and nothing else
with that word; `Coventry City` scores 0.33 against `New York City`, so Man City
is sole and is adopted whole.

WHAT THE REFUSAL COSTS, AND WHY THAT IS THE RIGHT TRADE
═══════════════════════════════════════════════════════

A refusal here falls through to the mint gate, which asks the ESPN payload
whether it names this club (#6215). For Coventry it does, so Coventry gets its
own row. That is a duplicate, and `_sole_candidate_the_payload_names` has
already ruled the trade in this file: *"a duplicate is a second card, a wrong
bind is another club's schedule on this club's page."*

THE EXISTING ROWS DO NOT HEAL, AND THIS FILE SAYS SO IN ONE PLACE
═════════════════════════════════════════════════════════════════

An earlier draft said "the live rows heal without a repair: the scheduled pass
rebinds `event.*_team_id` from `upsert_team` on every sync". That is false for
these three, and a fresh production read of `/api/teams/188` at CERT-3153 proved
it: the rebind's select passes rows MISSING A SCORE, and 15305209, 15305235 and
15297680 are completed WITH scores, so the scheduled pass never reaches them and
the completed backfill excludes scored rows. `repair_event_team_binding` (#1798)
cannot fix them either — it re-derives within the event's own `sport_id`, and
`Coventry City`/`Hull City` exist only under `soccer_efl_champ`, so it returns
`review`. The drain is **#7410**, filed with three options and a recommendation,
and it is not this change.

WHAT IS NOT CLAIMED
═══════════════════

* **No existing row is drained.** `/api/teams/188` still returns 15305209,
  15305235 and 15297680 after this change, and nothing here asserts otherwise.
  #7157 stays OPEN for that reason; #7410 owns the drain.
* The events' own league key is still wrong — these are cup ties stored under
  `soccer_epl`. Out of scope, and not folded into any green test here.
* The two COST rows below are real: they are one club, and this change refuses
  them. They are asserted as costs so the fall is provable when someone fixes
  the tokenisation, rather than deleted when it happens (the measured-cost list
  rule).
"""

import pytest

# Imported inside each test so this file COLLECTS on the parent commit: the
# witness that matters is `test_the_half_overlap_rival_is_refused` FAILING on the
# parent by returning Manchester City, which an ImportError would hide behind
# exit 2 (gotcha #124).


class _EspnTeam:
    """An ESPN payload; any field not named reads as absent, like the real one."""

    espn_id = None
    name = None
    abbreviation = None
    display_name = None
    short_name = None
    nickname = None
    location = None
    record = None
    primary_color = None
    secondary_color = None
    logo_url = None
    logo_url_dark = None

    def __init__(self, **fields):
        for key, value in fields.items():
            assert hasattr(type(self), key), f"{key} is not an ESPNTeam field"
            setattr(self, key, value)


#: ESPN's Coventry City payload — the away club of event 15305209.
COVENTRY = _EspnTeam(
    espn_id="326",
    name="Coventry City",
    display_name="Coventry City",
    short_name="Coventry",
    nickname="Sky Blues",
    abbreviation="COV",
    location="Coventry",
    record="5-1-0",
)

#: ESPN's Hull City payload — the away club of event 15305235.
HULL = _EspnTeam(
    espn_id="359",
    name="Hull City",
    display_name="Hull City",
    short_name="Hull City",
    nickname="Tigers",
    abbreviation="HUL",
    location="Hull",
    record="2-2-2",
)

#: The club the two events are wrongly bound to.
MAN_CITY = _EspnTeam(
    espn_id="382",
    name="Manchester City",
    display_name="Manchester City",
    short_name="Man City",
    abbreviation="MNC",
    location="Manchester",
    record="4-1-1",
)

#: The #7394 control: an abbreviation that IS the same club, at the same scale.
CLIPPERS = _EspnTeam(
    espn_id="12",
    name="Clippers",
    display_name="LA Clippers",
    short_name="LA Clippers",
    abbreviation="LAC",
    location="LA",
    record="42-40",
)

#: ESPN's LA Galaxy payload. `location` carries the club name on this endpoint.
GALAXY = _EspnTeam(
    espn_id="187",
    name="Galaxy",
    display_name="LA Galaxy",
    short_name="LA Galaxy",
    abbreviation="LA",
    location="LA Galaxy",
    record="7-9-10",
)

#: A one-token caller name against a fuller row — the ordinary adoption.
STANFORD = _EspnTeam(
    espn_id="24",
    name="Cardinal",
    display_name="Stanford Cardinal",
    short_name="Stanford",
    abbreviation="STAN",
    location="Stanford",
    record="3-1",
)


class _Row:
    """A `teams` row, with only the columns this writer reads or stamps."""

    def __init__(self, id, name, sport_id, espn_id=None, alternate_names=None):
        self.id = id
        self.name = name
        self.sport_id = sport_id
        self.espn_id = espn_id
        self.alternate_names = alternate_names
        self.abbreviation = None
        self.current_record = None
        self.location = None
        self.logo_url = None
        self.primary_color = None
        self.secondary_color = None


class _Result:
    def __init__(self, rows):
        self._rows = list(rows)

    def scalar_one_or_none(self):
        return self._rows[0] if self._rows else None

    def scalars(self):
        return iter(self._rows)


class _QueryingSession:
    """A session that ANSWERS THE QUERY instead of returning a canned list.

    Same fake as `test_the_pre_mint_probe_is_not_the_callers_spelling_6974`, and
    for the same reason: a result that ignores the statement passes for every
    possible candidate set, so it cannot tell "the predicate accepted this row"
    from "the predicate was never shown it". Here the distinction is the whole
    test — the defect is reached through the PROBE scan (`%city%` from the ESPN
    payload), not through the caller's own first word (`%coventry%`), so a fake
    that hands back the table would prove nothing about which scan found it.
    """

    def __init__(self, rows=()):
        self.rows = list(rows)
        self.added = []
        self.flushes = 0
        self.queries = []

    async def execute(self, stmt):
        compiled = stmt.compile()
        sql = str(compiled)
        params = compiled.params
        self.queries.append((sql, params))

        sport_id = params.get("sport_id_1")
        candidates = [r for r in self.rows if r.sport_id == sport_id]

        patterns = [
            v
            for k, v in params.items()
            if k.startswith("name_") and isinstance(v, str) and v.startswith("%")
        ]
        # `ilike` compiles to `lower(x) LIKE lower(y)` — the string "ILIKE" is
        # never in the SQL.
        if patterns:
            assert "LIKE" in sql.upper(), sql
            needles = [p.strip("%").lower() for p in patterns]
            return _Result(
                [r for r in candidates if any(n in (r.name or "").lower() for n in needles)]
            )

        exact = [
            v
            for k, v in params.items()
            if k.startswith("name_") and isinstance(v, str) and not v.startswith("%")
        ]
        if exact:
            return _Result([r for r in candidates if r.name == exact[0]])
        # FAIL CLOSED. A fake that answers an unrecognised query with every row
        # it holds cannot fail.
        raise AssertionError(f"unrecognised query, refusing to guess: {sql} {params}")

    def add(self, obj):
        self.added.append(obj)

    async def flush(self):
        self.flushes += 1


EPL = 1298
NBA = 43
NCAAF = 44
MLS = 45


def _epl_table():
    """`soccer_epl` as production holds it: the only two clubs with that word."""
    return [
        _Row(188, "Manchester City", EPL, espn_id="382", alternate_names=["Man City"]),
        _Row(4602, "New York City", EPL),
    ]


class TestTheProductionSpecimens:
    """The two rows the Schedule Sentinel filed, driven through the writer."""

    @pytest.mark.asyncio
    @pytest.mark.parametrize(
        "incoming,payload",
        [("Coventry City", COVENTRY), ("Hull City", HULL)],
        ids=["coventry-15305209", "hull-15305235"],
    )
    async def test_the_half_overlap_rival_is_refused(self, incoming, payload):
        """THE WITNESS. On the parent this returns `Manchester City` (id 188).

        The route is the PROBE scan: the caller's own first word (`%coventry%`)
        reaches nothing, then `_espn_name_probes` offers `city` from the
        payload, which matches `Manchester City` and nothing else at >= 0.5.
        """
        from app.utils.espn_helpers import upsert_team

        session = _QueryingSession(_epl_table())

        team = await upsert_team(session, incoming, payload, sport_id=EPL)

        assert team is not None, "the payload names this club, so it may be minted"
        assert team.id != 188, (
            f"{incoming!r} adopted Manchester City's row — this is the bind the "
            "sentinel filed as MISATTACHED/critical"
        )
        assert team.name == incoming
        assert [r.name for r in session.added] == [incoming], (
            "the club the payload names should get its own row"
        )

    @pytest.mark.asyncio
    async def test_the_rival_is_refused_on_the_warm_cache_path_too(self):
        """CERT-3136's lesson: both real callers pass a full-sport cache.

        The cache loop runs BEFORE either DB scan, so a fix that only reaches
        the scans is fully inert on every warm run.
        """
        from app.utils.espn_helpers import upsert_team

        rows = _epl_table()
        cache = {(r.name, EPL): r for r in rows}
        session = _QueryingSession(rows)

        team = await upsert_team(
            session, "Coventry City", COVENTRY, sport_id=EPL, team_cache=cache
        )

        assert team is not None
        assert team.id != 188, "the cache path bound Coventry to Manchester City"

    @pytest.mark.asyncio
    async def test_manchester_city_itself_still_adopts_its_own_row(self):
        """The refusal is about the OTHER club, not about the word `City`."""
        from app.utils.espn_helpers import upsert_team

        rows = _epl_table()
        session = _QueryingSession(rows)

        team = await upsert_team(session, "Manchester City", MAN_CITY, sport_id=EPL)

        assert team is rows[0], "Manchester City was refused its own row"
        assert session.added == []


class TestTheAdoptionsThatMustSurvive:
    """CONTROLS — every one of these is green on the parent and must stay green.

    A veto in front of a matcher earns its place only by refusing the pairs it
    was built for and NOTHING else, so each shape the writer legitimately
    adopts is pinned here.
    """

    @pytest.mark.asyncio
    async def test_a_shorter_name_still_adopts_its_fuller_row(self):
        """`Stanford` -> `Stanford Cardinal`: one side has no distinctive token."""
        from app.utils.espn_helpers import upsert_team

        row = _Row(24, "Stanford Cardinal", NCAAF, espn_id="24")
        session = _QueryingSession([row])

        team = await upsert_team(session, "Stanford", STANFORD, sport_id=NCAAF)

        assert team is row
        assert session.added == []

    @pytest.mark.asyncio
    async def test_an_abbreviated_city_still_adopts_the_spelled_out_row(self):
        """#7394's pair. The veto expands abbreviations, so this is not a rival.

        If this reddens, the veto and the matcher have drifted onto different
        scales again and the writer is refusing a club its own name.
        """
        from app.utils.espn_helpers import upsert_team

        row = _Row(537, "Los Angeles Clippers", NBA, espn_id="12")
        session = _QueryingSession([row])

        team = await upsert_team(session, "LA Clippers", CLIPPERS, sport_id=NBA)

        assert team is row
        assert session.added == []

    @pytest.mark.parametrize(
        "order",
        [
            ["Los Angeles FC", "LA Galaxy"],
            ["LA Galaxy", "Los Angeles FC"],
        ],
    )
    @pytest.mark.asyncio
    async def test_a_city_plus_initial_fragment_is_still_decided_by_its_letter(self, order):
        """🔴 THE ARM THAT MADE THIS AN `elif`, ON THE FRAGMENT THAT PROVES IT.

        `_token_stems_agree` requires two characters, so a trailing single
        letter reads as DISTINCTIVE and the veto calls `Los Angeles G` a rival
        of `LA Galaxy` — a club against itself, and #6974's duplicate mint
        straight back.

        THE OBVIOUS CONTROL HERE IS VACUOUS, which is why it is not the one
        used: `shared_token_rivals('Los Angeles C', 'Los Angeles Clippers')` is
        FALSE, because `c` sits in `_RESERVE_SUFFIX_RE` and `normalize_name`
        deletes the letter before the veto sees it. Written with the Clippers
        the test passes with the carve-out REMOVED — the mutant survives. `g`,
        `i` and `r` are not in that list, so `Los Angeles G`, `New York I` and
        `New York R` are the three of #6974's four fragments that actually turn
        on this branch.

        Both row orders, because one order passing is what heap-order looks
        like.
        """
        from app.utils.espn_helpers import upsert_team

        rows = [_Row(100 + i, name, MLS) for i, name in enumerate(order)]
        session = _QueryingSession(rows)

        team = await upsert_team(session, "Los Angeles G", GALAXY, sport_id=MLS)

        assert team is not None, "the fragment was refused its own club"
        assert team.name == "LA Galaxy", f"bound to {team.name!r}"
        assert session.added == [], "a duplicate Galaxy row was minted"

    @pytest.mark.parametrize(
        "ours,theirs",
        [
            ("Los Angeles G", "LA Galaxy"),
            ("New York I", "New York Islanders"),
            ("New York R", "New York Rangers"),
        ],
    )
    def test_the_veto_would_refuse_these_fragments_if_it_ran_on_them(self, ours, theirs):
        """The unit behind the carve-out, pinned so the reason cannot go stale.

        If one of these ever reads False the branch may be reconsidered — but
        only by re-measuring, never by deleting the row.
        """
        from app.utils.name_normalization import names_match, shared_token_rivals

        assert names_match(ours, theirs)
        assert shared_token_rivals(ours, theirs), (
            f"{ours!r}/{theirs!r} is no longer a rival, so it no longer explains "
            "the fragment carve-out"
        )

    @pytest.mark.asyncio
    async def test_a_fragment_whose_letter_is_a_reserve_suffix_also_resolves(self):
        """`Los Angeles C` — green before and after, and green under the mutant.

        Kept as a SECOND fragment shape, not as the witness: `normalize_name`
        strips its letter, so the veto is inert here either way.
        """
        from app.utils.espn_helpers import upsert_team

        row = _Row(537, "Los Angeles Clippers", NBA, espn_id="12")
        session = _QueryingSession([row])

        team = await upsert_team(session, "Los Angeles C", CLIPPERS, sport_id=NBA)

        assert team is row
        assert session.added == []


#: Pairs the sentinel's open findings and the 2026-09-20 census say are two
#: DIFFERENT clubs, each scoring >= 0.5 against `names_match`. These are the
#: refusals this change exists for.
_DIFFERENT_CLUBS = [
    ("Coventry City", "Manchester City"),
    ("Hull City", "Manchester City"),
    ("BYU Cougars", "Houston Cougars"),
    ("Kentucky Wildcats", "Bethune-Cookman Wildcats"),
    ("Utah State Aggies", "New Mexico State Aggies"),
    ("Bury Town", "Shrewsbury Town"),
    ("Eindhoven FC", "PSV Eindhoven"),
    ("Jong Utrecht", "FC Utrecht"),
    ("Newport City", "Newport County"),
    ("Manchester United", "Newcastle United"),
    ("Real Betis", "Real Madrid"),
    ("Le Mans", "Le Havre"),
    ("Rice Owls", "Temple Owls"),
    ("Towson Tigers", "LSU Tigers"),
    ("UConn Huskies", "Washington Huskies"),
]

#: 🔴 THE MEASURED COST. Each of these is ONE club under two spellings, and this
#: change refuses it — the refusal falls through to the mint gate, so the cost
#: is a duplicate row, which this file has ruled the lesser evil against a wrong
#: bind. Asserted as costs rather than omitted so that a later fix to the
#: tokenisation is PROVABLE: when one starts matching, move it up to
#: `_DIFFERENT_CLUBS`' sibling list, never delete the row.
#:
#: `Atl. San Luis`  — `atl.` keeps its period, so `_token_stems_agree` cannot
#:                    reach `atletico`. Not fixed here: the same tokenisation is
#:                    the veto on the writer and repair rails, measured at
#:                    CERT-2881, and loosening it needs those rails re-measured.
#: `Cal State …`    — `cal`/`csu` is an abbreviation in neither map. The
#:                    docstring of `shared_token_rivals` names this class as
#:                    KNOWN RESIDUE and says the fix is a map entry.
_ONE_CLUB_THIS_STILL_REFUSES = [
    ("Atl. San Luis", "Atlético San Luis"),
    ("Cal State Northridge Matadors", "CSU Northridge Matadors"),
]


class TestTheVetoReadsThePairsTheCensusFound:
    """The predicate itself, on the production pairs — no session, no writer."""

    @pytest.mark.parametrize("ours,theirs", _DIFFERENT_CLUBS)
    def test_two_different_clubs_are_rivals(self, ours, theirs):
        from app.utils.name_normalization import names_match, shared_token_rivals

        assert names_match(ours, theirs), (
            f"{ours!r}/{theirs!r} no longer reaches the matcher, so this row no "
            "longer measures anything — re-derive it from production"
        )
        assert shared_token_rivals(ours, theirs), f"{ours!r} would adopt {theirs!r}"

    @pytest.mark.parametrize("ours,theirs", _ONE_CLUB_THIS_STILL_REFUSES)
    def test_the_measured_cost_is_still_paid(self, ours, theirs):
        """These are one club and are refused anyway. See the list's comment."""
        from app.utils.name_normalization import shared_token_rivals

        assert shared_token_rivals(ours, theirs), (
            f"{ours!r}/{theirs!r} is no longer refused — the cost fell, which is "
            "good news: move this row to a list that asserts it MATCHES, and say "
            "in the commit which rails were re-measured"
        )
