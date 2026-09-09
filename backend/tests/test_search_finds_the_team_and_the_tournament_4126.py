"""THE FRONT DOOR: "yank" FINDS THE YANKEES AND "US OPEN" REACHES TONIGHT'S MATCH. #4126.

═══ WHY THIS SUITE EXISTS ═══

Measured against production `api.bainluck.com` on 2026-09-08, `GET /api/events/search`:

    q=yank      teams 0  results 0   futures 10  -> `M15 Hurghada: Mayank Sharma`, `Yanki Erel`
    q=yankees   teams 1  results 25  futures 10  -> fine
    q=us open   teams 0  results 0   futures 10  -> 4 concepts, ZERO game rows
    q=alcaraz   teams 0  results 8   futures 10  -> fine

Two defects, and they are NOT the same defect:

**`yank`** — `_build_team_search_filter` gates the Teams surface on whole lexemes, and `yank` is not
a lexeme of `yankees` (which stems to `yanke`). The team is unreachable until the eighth character,
and the futures bucket answers instead with two minor-tour tennis players.

**`us open`** — the tournament name is NOWHERE ON THE EVENT ROW. Event 15306813 (Shelton vs Alcaraz,
2026-09-09 01:30Z) carries the two PLAYERS in `home_team_name`/`away_team_name` and an `event_tags`
list holding only audience / structure / narrative / provenance entries. The tournament identity
lives one table over in `sports.name` ("ATP US Open"). No amount of text matching on the event row
can ever find it, so this half is a RESOLVER bug, not a matching bug.

═══ THE TWO REFUSALS THIS SUITE MUST NOT BREAK ═══

🔴 **Prefix matching is refused in `events.py`, in writing, naming `yank`.** `_event_name_match`'s
LAT-P037 docstring: "`to_tsquery('re:*')` … even fix `yank` -> Yankees (#1757). It also matches
`fed:*` -> `federico`, which is the entire defect LAT-P033/LAT-P034 measured and closed (25 rows of
minor-tour tennis presented as the answer to `fed`)." That refusal governs the FUTURES-NAME arm and
it stands. The fix lives on the TEAMS arm, whose rows are already stripped of individual-sport
athletes — the exact population `fed` -> `federico` was made of. `TestTheRefusalsStillHold` is the
control, and it is the most important class in this file.

🔴 **The event recall is deliberately FTS-free.** LAT-P002/#1494 (1c) dropped the FTS arm from the
event WHERE because no tsvector index exists — only trigram GINs — so one unindexable arm forced a
seq scan of `events` and drove a ~20s median (252 -> 90ms on the fix). Nothing here may put a
tsquery back into the event predicate.

═══ WHAT IS TESTED, AND WHAT CANNOT BE ═══

These are the PURE halves — the resolver and the compiled SQL — which need no Postgres and so run in
every CI job. End-to-end recall ("does q=yank actually return the Yankees") needs the real database
and the `search-recall` job; the gold set is the guard there. What is asserted here is the part that
regressed and the parts a future edit would silently undo.
"""

from sqlalchemy.dialects import postgresql

from app.routes.events import (
    _build_team_search_filter,
    _event_name_match,
    _resolve_sport_aliases,
    _team_prefix_tsquery,
    _team_search_rank,
    _SPORT_SEARCH_PHRASE_ALIASES,
    _SEARCH_TEAM_PREFIX_RANK_WEIGHT,
)


def _sql(clause) -> str:
    """Compile to Postgres SQL with literals inlined, so an assertion can read
    the actual tsquery string rather than a bind marker."""
    return str(
        clause.compile(
            dialect=postgresql.dialect(), compile_kwargs={"literal_binds": True}
        )
    )


def _expanded(query: str):
    """The `(term, expansion)` shape both call sites hand the resolver."""
    return [(token, None) for token in query.split()]


class TestYankFindsTheYankees:
    """Half A: a last-token prefix arm on the TEAMS surface."""

    def test_yank_builds_a_prefix_tsquery(self):
        assert _sql(_team_prefix_tsquery("yank")) == "to_tsquery('english', 'yank:*')"

    def test_yanks_builds_one_too(self):
        """`yanks` stems to `yank`, and the stored name stems to `yanke` — so the
        plural fails the whole-lexeme gate exactly like the truncation does. Both
        of Fable's probes are one bug."""
        assert _sql(_team_prefix_tsquery("yanks")) == "to_tsquery('english', 'yanks:*')"

    def test_only_the_last_token_is_a_prefix(self):
        """`red sox`: `red` must still match as a whole word. A prefix on every
        token would widen recall far past what was asked for."""
        assert _sql(_team_prefix_tsquery("red sox")) == "to_tsquery('english', 'red & sox:*')"

    def test_tokens_are_anded_never_ored(self):
        """The AND is what keeps `super bowl` off `Bowling Green Falcons`.

        English stemming collapses `bowling` -> `bowl`, so the `bowl:*` half
        matches that team either way; it is the REQUIRED `super` that excludes
        it. An OR here would reopen every case the FTS gate was built to close.
        """
        sql = _sql(_team_prefix_tsquery("super bowl"))
        assert sql == "to_tsquery('english', 'super & bowl:*')"
        assert "|" not in sql

    def test_a_fragment_below_the_trigram_boundary_gets_no_prefix_arm(self):
        """Two characters is not a word the user means, and `u:*` would match a
        large fraction of the table. The boundary is `_has_extractable_trigram`,
        this surface's ONE cliff — not a second length constant, which is how
        /search and /typeahead drifted before."""
        assert _team_prefix_tsquery("us") is None
        assert _team_prefix_tsquery("a") is None
        assert _team_prefix_tsquery("") is None
        assert _team_prefix_tsquery("!!") is None

    def test_the_prefix_arm_is_added_to_recall_not_substituted(self):
        """Whole-lexeme arms must survive. The prefix arm only ADDS rows, so
        nothing that reaches a user today stops reaching them."""
        sql = _sql(_build_team_search_filter("yank"))
        assert "websearch_to_tsquery" in sql, "the original whole-lexeme arms are gone"
        assert "'yank:*'" in sql, "the prefix arm never made it into the filter"

    def test_a_short_query_filter_is_unchanged(self):
        """Below the boundary the predicate must be byte-identical to the old
        one — the exemption costs nothing that was working."""
        sql = _sql(_build_team_search_filter("us"))
        assert ":*" not in sql

    def test_rank_scores_the_prefix_arm_too(self):
        """🔴 Recall without ranking is a scrambled list.

        `ts_rank_cd` against `websearch_to_tsquery('yank')` is 0.0 for EVERY row
        the prefix arm recalls, so ordering would fall through to the
        `Team.name` ASC tiebreak and hand top-1 to whichever `yank…` team sorts
        first alphabetically. The Yankees would be reachable and still not be
        the answer — which is a different bug wearing the same symptom.
        """
        sql = _sql(_team_search_rank("yank"))
        assert "'yank:*'" in sql, "the prefix match contributes nothing to rank"
        assert "websearch_to_tsquery" in sql, "the exact-match term was dropped from rank"

    def test_the_prefix_score_is_discounted_so_exact_still_wins(self):
        """`yankees` must still answer with the Yankees, ahead of any row that
        merely starts the same way. An exact match earns on both terms; a
        prefix-only row earns on one, at a discount."""
        assert 0 < _SEARCH_TEAM_PREFIX_RANK_WEIGHT < 1

    def test_rank_is_the_plain_expression_below_the_boundary(self):
        sql = _sql(_team_search_rank("us"))
        assert ":*" not in sql


class TestUsOpenReachesTheMatch:
    """Half B: tournament names resolve to SPORT KEYS, and the existing league
    arm does the rest. Measured on production the same evening, a bare league
    query already returns 25 game rows for each of `ncaaf`, `nba`, `tennis`
    through that arm — so this half needed a resolver, not a new query."""

    def test_us_open_resolves_to_the_us_open_sports(self):
        keys, _ = _resolve_sport_aliases(_expanded("us open"))
        assert keys is not None
        assert "tennis_atp_us_open" in keys
        assert "tennis_wta_us_open" in keys

    def test_us_open_consumes_both_of_its_tokens(self):
        """🔴 THE TRAP, and the single most likely way to build this half and
        still ship zero rows.

        Both call sites compute their remaining terms as "every term that is not
        an alias", and they used to spell that as per-token membership in
        `_SPORT_SEARCH_ALIASES`. A phrase is invisible to that test — so `us
        open` would resolve to the tennis keys AND STILL require the literal
        words `us` and `open` to match a team name, AND-ed into the league arm.
        That is zero rows: the same answer the bug already gives, from code that
        looks fixed.
        """
        _, consumed = _resolve_sport_aliases(_expanded("us open"))
        assert consumed == {"us", "open"}

    def test_the_longest_phrase_wins(self):
        """`open` alone must never claim a tournament, or every Open collides."""
        keys, consumed = _resolve_sport_aliases(_expanded("open"))
        assert keys is None
        assert consumed == set()

    def test_a_tournament_and_a_league_token_compose(self):
        keys, consumed = _resolve_sport_aliases(_expanded("us open tennis"))
        assert "tennis_atp_us_open" in keys
        assert "tennis_atp" in keys, "the surviving league token was dropped"
        assert consumed == {"us", "open", "tennis"}

    def test_keys_are_deduped_and_ordered(self):
        keys, _ = _resolve_sport_aliases(_expanded("us open us open"))
        assert len(keys) == len(set(keys))

    def test_single_token_leagues_still_resolve_exactly_as_before(self):
        """The regression control for the pre-existing behaviour."""
        assert _resolve_sport_aliases(_expanded("nba"))[0] == ["basketball_nba"]
        assert _resolve_sport_aliases(_expanded("nfl"))[0] == ["americanfootball_nfl"]
        keys, consumed = _resolve_sport_aliases(_expanded("mlb yankees"))
        assert keys == ["baseball_mlb"]
        assert consumed == {"mlb"}, "`yankees` must stay a required term"

    def test_wimbledon_is_a_single_token_tournament(self):
        keys, _ = _resolve_sport_aliases(_expanded("wimbledon"))
        assert keys == ["tennis_atp_wimbledon", "tennis_wta_wimbledon"]

    def test_a_plain_team_query_resolves_to_no_sport(self):
        """`red sox` must not acquire a league scope it never asked for — that
        would widen the event predicate, which LAT-P002 forbids."""
        assert _resolve_sport_aliases(_expanded("red sox"))[0] is None
        assert _resolve_sport_aliases(_expanded("alcaraz"))[0] is None

    def test_every_phrase_key_looks_like_a_real_sport_key(self):
        """Keys were copied from `sports.key` on production, never guessed.
        This cannot verify they EXIST — that needs the database — but it does
        catch the shape errors a hand-written map produces (the Australian Open
        is `tennis_atp_aus_open_singles`, not `..._australian_open`)."""
        for phrase, keys in _SPORT_SEARCH_PHRASE_ALIASES.items():
            assert keys, f"{phrase} resolves to nothing"
            for key in keys:
                assert key == key.lower()
                assert " " not in key
                assert key.split("_")[0] in {"tennis", "golf", "basketball",
                                             "americanfootball", "baseball",
                                             "icehockey", "soccer", "mma"}


class TestTheCallSitesActuallySpendTheResolver:
    """MEMBERSHIP is not enough; the sites have to SPEND it (#3790's shape).

    Everything above proves the resolver returns the right answer. None of it
    proves `search_events` and `search_suggestions` ASK it — and the trap in
    this ship is precisely a call site that resolves the keys correctly and then
    computes its remaining terms the old way. That combination returns zero rows
    for `us open` from code whose every unit test is green.

    The predicates are built inline inside two very long async route bodies, so
    there is no object to call; this reads the source, the way the #3790 suite
    reads its four backfills.
    """

    @staticmethod
    def _events_source() -> str:
        import inspect

        from app.routes import events as events_module

        return inspect.getsource(events_module)

    def test_no_call_site_still_filters_terms_by_alias_membership(self):
        """🔴 The mutant this kills: reverting either site to
        `t.lower() not in _SPORT_SEARCH_ALIASES`.

        That is a per-token test, so a two-token tournament name resolves its
        sport keys AND keeps `us`/`open` as required team-name terms, AND-ed
        into the league arm — zero rows, which is the bug.
        """
        source = self._events_source()
        assert "not in _SPORT_SEARCH_ALIASES" not in source, (
            "a call site is filtering remaining terms by single-token alias "
            "membership again; phrase aliases are invisible to that test"
        )

    def test_both_call_sites_use_the_shared_resolver(self):
        """One copy of the rule. This file's own comments record that /search
        and /typeahead drifted for three cycles by keeping two."""
        source = self._events_source()
        assert source.count("_resolve_sport_aliases(") >= 3, (
            "expected the definition plus both call sites (/search and "
            "/typeahead) to reference the shared resolver"
        )
        assert "_SPORT_SEARCH_ALIASES.get(term.lower())" not in source, (
            "a call site is hand-rolling the single-token lookup again"
        )


class TestTheRefusalsStillHold:
    """🔴 THE CONTROLS. Both of these are documented refusals in `events.py`, and
    a "fix" that widened everything would go green without this class."""

    def test_the_futures_name_arm_never_gets_a_prefix(self):
        """LAT-P033/LAT-P034: `fed:*` -> `federico`, 25 rows of minor-tour tennis
        presented as the answer to `fed`. `_event_name_match` rules prefix
        matching out "in full" and #4126 does not touch it."""
        for term in ("fed", "yank", "re"):
            sql = _sql(_event_name_match(term, None))
            assert ":*" not in sql, f"a prefix arm leaked into the futures name arm for {term!r}"
            assert "to_tsquery('english', '" + term + ":*')" not in sql

    def test_the_event_predicate_keeps_its_trigram_servable_recall_arm(self):
        """LAT-P002/#1494 (1c): the event WHERE must stay trigram-servable.

        🔴 Read this one precisely, because the obvious assertion is wrong. The
        predicate DOES contain `to_tsvector(...) @@ websearch_to_tsquery(...)` —
        but AND-ed, as a narrowing conjunct beside the ILIKE. What LAT-P002
        removed was an FTS arm inside the top-level OR, where a single
        unindexable branch forces a seq scan of `events` for the WHOLE predicate
        (the ~20s median; 252 -> 90ms on the fix). An AND-ed conjunct is
        evaluated over the rows the trigram bitmap scan already returned, so it
        costs nothing.

        So the guard is: the ILIKE recall arm survives, and nothing #4126 added
        turned up here.
        """
        sql = _sql(_event_name_match("yankees", None))
        assert "ILIKE" in sql.upper(), "the trigram-servable recall arm is gone"
        assert ":*" not in sql, "a prefix arm leaked into the event predicate"

    def test_super_bowl_still_requires_super(self):
        """The `IPO` -> Asteras Tripolis / `super bowl` -> Bowling Green class
        that the FTS gate was built to close stays closed."""
        sql = _sql(_build_team_search_filter("super bowl"))
        assert "'super & bowl:*'" in sql
        assert "'bowl:*'" not in sql.replace("'super & bowl:*'", "")
