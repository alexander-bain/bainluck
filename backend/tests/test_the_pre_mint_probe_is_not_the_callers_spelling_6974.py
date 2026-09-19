"""#6974 — a club is not minted a second time because we spell its city differently.

**SHIP: searching "clippers" stops returning two Clippers cards with two
different records.** (Pillar: MATCHING.)

Production, 2026-09-19, `GET /api/events/search?q=clippers`:

    537   'Los Angeles Clippers'  42-40  basketball_nba
    12649 'Los Angeles C'         39-36  basketball_nba

Five rows of this shape are in the table, and each one already has a correctly
named sibling. `upsert_team` is the writer. It resolves only by name, and before
it mints it narrows its DB candidate set with an ILIKE on the FIRST WORD of the
name it was handed:

    _first_word = team_name.split()[0]
    if len(_first_word) >= 3:
        ... Team.name.ilike(f"%{_first_word}%") ...
        if _canonical_names_match(team_name, candidate.name): team = candidate

That first word is the CALLER's spelling of the city, so the probe can never
reach a canonical row that spells the city the other way. Measured on the real
pairs:

    fragment         canonical               '%first word%' hits it?   names_match
    Los Angeles C    Los Angeles Clippers    yes                       True
    New York I       New York Islanders      yes                       True
    New York R       New York Rangers        yes                       True
    Los Angeles G    LA Galaxy               NO  ('%Los%')             True

`names_match` was willing to recognise LA Galaxy the whole time. It was never
shown the row. Three of the four fragments were saved only by sharing a first
word with their canonical, which is luck, not a guard — and the fourth is the
one that got minted.

WHAT IS NOT CLAIMED HERE
════════════════════════

The five rows already in the table are NOT repaired by this change, and the
repair is not the one #6974's framing implies: every event hanging off a
duplicate is a TWIN of a fixture that already exists on the canonical row at the
same minute, so repointing them would give each club two rows for one game.
`12716` is excluded from that repair entirely — its identity columns say
Islanders while its three events resolve to two different clubs. Both are stated
on the issue and neither is folded into a green test here.
"""

import pytest

# Imported inside the tests so this file COLLECTS on the parent commit: the
# witness that matters is `test_a_canonical_that_spells_the_city_differently_is
# _found` FAILING on the parent by MINTING a row, which an ImportError would
# have hidden behind exit 2 (gotcha #124).


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


#: ESPN's LA Galaxy payload. `location` is the club name on this endpoint, which
#: is real and is why the row adopted the identity once it was minted.
GALAXY = _EspnTeam(
    espn_id="187",
    name="Galaxy",
    display_name="LA Galaxy",
    short_name="LA Galaxy",
    abbreviation="LA",
    location="LA Galaxy",
    record="7-9-10",
)

#: ESPN's Clippers payload — the control. This fragment DOES share a first word
#: with its canonical, so it must keep resolving exactly as it does today.
CLIPPERS = _EspnTeam(
    espn_id="12",
    name="Clippers",
    display_name="LA Clippers",
    short_name="LA Clippers",
    abbreviation="LAC",
    location="LA",
    record="42-40",
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

    This is the whole point of the file. A fake whose result ignores the
    statement passes for every possible candidate set, so it cannot tell "the
    predicate accepted the row" from "the predicate was never shown the row" —
    and the second is the defect. So the WHERE clause is actually evaluated:
    `name = :x` exactly, `name ILIKE %p%` by containment, `sport_id` always.
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
        # `ilike` COMPILES TO `lower(x) LIKE lower(y)` — the string "ILIKE" is
        # never in the SQL. Matching on it sent every pattern query to the
        # fall-through below, which returned the whole table, and the witness
        # passed on the parent by being handed the row the defect hides.
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
        # it holds cannot fail, which is the whole failure mode above.
        raise AssertionError(f"unrecognised query, refusing to guess: {sql} {params}")

    def add(self, obj):
        self.added.append(obj)

    async def flush(self):
        self.flushes += 1


MLS = 42
NBA = 43


class TestTheProbeDoesNotDependOnTheCallersSpelling:
    """The writer's own behaviour, asserted on the row it returns."""

    @pytest.mark.asyncio
    async def test_a_canonical_that_spells_the_city_differently_is_found(self):
        """THE WITNESS. `Los Angeles G` must resolve to the existing LA Galaxy.

        On the parent this mints: `%Los%` does not match `LA Galaxy`, so the
        candidate set is empty and `names_match` — which says True for this
        pair — is never consulted. Row `12617` is that mint.
        """
        from app.utils.espn_helpers import upsert_team

        galaxy = _Row(2325, "LA Galaxy", MLS, espn_id="187")
        session = _QueryingSession([galaxy])

        team = await upsert_team(session, "Los Angeles G", GALAXY, sport_id=MLS)

        assert team is galaxy, "the canonical was in the table and was not found"
        assert session.added == [], "a second LA Galaxy was minted"
        assert session.flushes == 0

    @pytest.mark.asyncio
    async def test_the_shared_first_word_case_still_resolves(self):
        """CONTROL — green on the parent too.

        `Los Angeles C` is saved by sharing a first word with its canonical.
        That path is untouched, so this passes before and after; it is here so
        that a change which trades the old probe for the new one is red.
        """
        from app.utils.espn_helpers import upsert_team

        clippers = _Row(537, "Los Angeles Clippers", NBA, espn_id="12")
        session = _QueryingSession([clippers])

        team = await upsert_team(session, "Los Angeles C", CLIPPERS, sport_id=NBA)

        assert team is clippers
        assert session.added == []

    @pytest.mark.asyncio
    async def test_widening_the_candidates_does_not_widen_what_is_accepted(self):
        """A wider net is only safe if the acceptance test is unchanged.

        The probe puts LA Galaxy in front of the predicate for a name that is
        not LA Galaxy. `names_match('Portland Timbers', 'LA Galaxy')` is False,
        so it must be refused — and because the payload does not correspond to
        the incoming name either, the mint is refused too (#6215).
        """
        from app.utils.espn_helpers import upsert_team

        galaxy = _Row(2325, "LA Galaxy", MLS, espn_id="187")
        session = _QueryingSession([galaxy])
        stats = {}

        team = await upsert_team(
            session, "Portland Timbers", GALAXY, sport_id=MLS, stats=stats
        )

        assert team is not galaxy, "a club was bound to another club's row"
        assert team is None
        assert session.added == [], "and it was not minted under the wrong identity"
        assert stats.get("teams_espn_mint_refused") == 1

    @pytest.mark.asyncio
    async def test_the_probe_does_not_reach_across_sports(self):
        """`sport_id` still bounds the search — the widening is within a league."""
        from app.utils.espn_helpers import upsert_team

        galaxy = _Row(2325, "LA Galaxy", MLS, espn_id="187")
        session = _QueryingSession([galaxy])

        team = await upsert_team(session, "Los Angeles G", GALAXY, sport_id=NBA)

        assert team is not galaxy, "an MLS row answered a lookup under the NBA"


class TestACrossTownRivalDoesNotAnswerForTheFragment:
    """CERT-3134's repair: `6974-ESPN-PROBE-REFUSES-CROSS-TOWN-RIVALS`.

    Widening the candidate set is only safe if the acceptance test can tell two
    clubs in one city apart, and NEITHER house predicate can:

        names_match('Los Angeles FC', 'LA Galaxy')            -> True
        shared_token_rivals('Los Angeles FC', 'LA Galaxy')    -> False
        espn_identity_corresponds('Los Angeles FC', …Galaxy)  -> True

    So the first row the scan happens to return decides identity by heap order.
    Measured on the PARENT, before any of this file existed, `Los Angeles G`
    carrying the Galaxy payload resolved to `Los Angeles FC` under BOTH row
    orders — this is not a regression the widening introduced, it is a hole the
    widening would have inherited and made louder.

    The fragment names its club by one letter, so the letter is honoured: `G` is
    Galaxy, not FC. Same rule this lane shipped for `resolve_team` in #7230.

    BOTH ORDERS are pinned on every case, because one order passing is exactly
    what a heap-order bug looks like.
    """

    ORDERS = [
        ["Los Angeles FC", "LA Galaxy"],
        ["LA Galaxy", "Los Angeles FC"],
    ]

    @pytest.mark.parametrize("order", ORDERS)
    @pytest.mark.asyncio
    async def test_the_initial_picks_the_club_not_the_row_order(self, order):
        from app.utils.espn_helpers import upsert_team

        rows = [_Row(100 + i, name, MLS) for i, name in enumerate(order)]
        session = _QueryingSession(rows)

        team = await upsert_team(session, "Los Angeles G", GALAXY, sport_id=MLS)

        assert team is not None, "the Galaxy row was present and was refused"
        assert team.name == "LA Galaxy", (
            f"bound to {team.name!r} — a cross-town rival answered for the fragment"
        )
        assert session.added == []

    NBA_ORDERS = [
        ["Los Angeles Lakers", "Los Angeles Clippers"],
        ["Los Angeles Clippers", "Los Angeles Lakers"],
    ]

    @pytest.mark.parametrize("order", NBA_ORDERS)
    @pytest.mark.asyncio
    async def test_the_same_holds_where_both_rivals_share_the_city_spelling(self, order):
        """`Los Angeles C` must not be answered by the Lakers.

        Here both clubs spell the city the same way, so the ORIGINAL first-word
        probe returns both and `names_match` accepts both — the heap decides.
        """
        from app.utils.espn_helpers import upsert_team

        rows = [_Row(200 + i, name, NBA) for i, name in enumerate(order)]
        session = _QueryingSession(rows)

        team = await upsert_team(session, "Los Angeles C", CLIPPERS, sport_id=NBA)

        assert team is not None
        assert team.name == "Los Angeles Clippers", (
            f"bound to {team.name!r} — the Lakers answered for a Clippers fragment"
        )
        assert session.added == []

    def test_the_fragment_split_only_fires_on_a_trailing_single_letter(self):
        from app.utils.espn_helpers import _city_plus_initial

        assert _city_plus_initial("Los Angeles G") == ("Los Angeles", "g")
        assert _city_plus_initial("New York I") == ("New York", "i")
        # A whole name is not a fragment, and neither is a bare city.
        assert _city_plus_initial("Los Angeles Clippers") == (None, None)
        assert _city_plus_initial("Galaxy") == (None, None)
        assert _city_plus_initial("") == (None, None)
        assert _city_plus_initial(None) == (None, None)


class TestTheProbes:
    """`_espn_name_probes` — the unit, kept honest about what it may probe."""

    def test_it_offers_the_club_words_the_caller_did_not_have(self):
        from app.utils.espn_helpers import _espn_name_probes

        assert "galaxy" in _espn_name_probes(GALAXY)

    def test_one_and_two_letter_fragments_are_never_probes(self):
        """A one-letter fragment is the defect; `%C%` would match everything."""
        from app.utils.espn_helpers import _espn_name_probes

        assert all(len(p) >= 3 for p in _espn_name_probes(GALAXY))
        assert "la" not in _espn_name_probes(GALAXY)

    def test_the_city_field_is_not_a_probe(self):
        """`location` names a city, not a club (the constant above it says why).

        ESPN's Manchester City payload carries `location = 'Manchester'`, which
        sits inside `Manchester United` with nothing left over.
        """
        from app.utils.espn_helpers import _espn_name_probes

        city = _EspnTeam(espn_id="382", location="Manchester")
        assert _espn_name_probes(city) == []

    def test_the_word_already_tried_is_not_tried_again(self):
        from app.utils.espn_helpers import _espn_name_probes

        assert "galaxy" not in _espn_name_probes(GALAXY, exclude_word="Galaxy")

    def test_an_absent_payload_offers_nothing(self):
        from app.utils.espn_helpers import _espn_name_probes

        assert _espn_name_probes(None) == []
