"""#5881 — a finished MLB game frozen at `suspended` says Final, or says nothing.

59 finished MLB games print "No result reported" over a complete win-probability
curve because `0ee26b711` (Sep 2) correctly stopped the staleness net minting false
finals and left no replacement writer for the settled edge on a row with no
`espn_id`. `schedule_coverage.settle_frozen_mlb_suspended` supplies that edge from
the MLB Stats API.

These guards are about the two halves that can hurt a reader: the DECISION (what the
arm refuses, and it refuses more than it accepts) and the WRITE (which columns move,
under whose confirmation, and what happens when the row moves underneath it).
"""

from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy.dialects.postgresql import ARRAY, JSONB
from sqlalchemy.ext.compiler import compiles

from app.tasks.schedule_coverage import (
    FROZEN_FINAL_MATCH_WINDOW,
    MLB_NOMINAL_GAME_LENGTH,
    _repair_teams_match,
    choose_frozen_final,
    frozen_completed_at,
    frozen_final_orientation,
    frozen_settle_floor,
)

_UTC = timezone.utc


@compiles(JSONB, "sqlite")
def _jsonb_sqlite(type_, compiler, **kw):  # pragma: no cover - test rail
    return "JSON"


@compiles(ARRAY, "sqlite")
def _array_sqlite(type_, compiler, **kw):  # pragma: no cover - test rail
    return "JSON"


def _dt(y, mo, d, h=0, mi=0):
    return datetime(y, mo, d, h, mi, tzinfo=_UTC)


def _cand(home="Baltimore Orioles", away="Boston Red Sox", hs=1, aws=3,
          orientation="aligned", start=None):
    return {
        "start": start or _dt(2026, 9, 6, 17, 35),
        "home": home,
        "away": away,
        "home_score": hs,
        "away_score": aws,
        "orientation": orientation,
    }


class TestChooseFrozenFinal:
    """The decision boundary, on the real shapes the production population holds."""

    def test_our_score_agrees_with_the_authority_settles(self):
        # 48 of the measured 59: we already hold the true final, the status lies.
        verdict, cand = choose_frozen_final(1, 3, [_cand()])
        assert verdict == "settle"
        assert cand["home_score"] == 1

    def test_no_score_of_our_own_settles_on_the_authoritys(self):
        # 10 of the measured 59 (e.g. 15298326, Cardinals @ Rockies): nothing to
        # contradict, so the authority's score is the only one in the room.
        verdict, cand = choose_frozen_final(None, None, [_cand(hs=4, aws=1)])
        assert verdict == "settle"
        assert (cand["home_score"], cand["away_score"]) == (4, 1)

    def test_a_score_that_contradicts_the_authority_is_refused_not_overwritten(self):
        # Measured 0 of 59 today. Refusing leaves the row exactly as it is — the
        # status quo — where overwriting would publish a result this arm cannot
        # justify off a name-and-clock match (#6056's lesson).
        verdict, _ = choose_frozen_final(9, 9, [_cand(hs=1, aws=3)])
        assert verdict == "score_conflict"

    def test_a_doubleheader_is_ambiguous_when_we_hold_no_score(self):
        # 15294597, Tigers @ Guardians: two Finals 305 minutes apart. With no score
        # of our own there is nothing to separate them, and picking one would be a
        # coin toss dressed as ground truth.
        two = [_cand(hs=7, aws=6), _cand(hs=4, aws=3, start=_dt(2026, 9, 4, 23, 15))]
        assert choose_frozen_final(None, None, two)[0] == "ambiguous"

    def test_a_doubleheader_is_separated_by_our_own_score(self):
        two = [_cand(hs=7, aws=6), _cand(hs=4, aws=3, start=_dt(2026, 9, 4, 23, 15))]
        verdict, cand = choose_frozen_final(4, 3, two)
        assert verdict == "settle"
        assert cand["start"] == _dt(2026, 9, 4, 23, 15)

    def test_the_score_tiebreak_never_rescues_a_swapped_candidate(self):
        # The narrowing only considers `aligned` candidates: a swapped row that
        # happens to carry mirrored numbers must not be promoted by the tie-break.
        two = [
            _cand(hs=4, aws=3, orientation="swapped"),
            _cand(hs=9, aws=9, start=_dt(2026, 9, 4, 23, 15)),
        ]
        assert choose_frozen_final(4, 3, two)[0] == "ambiguous"

    def test_a_swapped_single_candidate_is_refused(self):
        verdict, _ = choose_frozen_final(1, 3, [_cand(orientation="swapped")])
        assert verdict == "orientation"

    def test_an_unresolvable_orientation_is_refused_under_its_own_name_cert2864(self):
        """Kept apart from `orientation` because they are different facts: that one
        knows the row is swapped, this one knows only that it cannot tell."""
        verdict, _ = choose_frozen_final(1, 3, [_cand(orientation="ambiguous")])
        assert verdict == "orientation_ambiguous"

    def test_a_partial_score_is_checked_on_the_half_we_hold_cert2864(self):
        """CERT-2864's follow-up. `ours_scored` demanded BOTH components, so a row
        holding one score skipped the conflict test entirely — the half we held was
        never compared to the authority and was then overwritten by the write. 0 of
        the 59 are partial today, which is why the shape has to be right first."""
        # The half we hold AGREES: confirmable, so the gap may be filled.
        assert choose_frozen_final(1, None, [_cand(hs=1, aws=3)])[0] == "settle"
        assert choose_frozen_final(None, 3, [_cand(hs=1, aws=3)])[0] == "settle"
        # The half we hold CONTRADICTS the authority: refused, exactly as a
        # fully-scored contradiction is.
        assert choose_frozen_final(9, None, [_cand(hs=1, aws=3)])[0] == "score_conflict"
        assert choose_frozen_final(None, 9, [_cand(hs=1, aws=3)])[0] == "score_conflict"

    def test_no_final_when_the_authority_reports_nothing(self):
        assert choose_frozen_final(1, 3, [])[0] == "no_final"

    def test_a_final_with_no_score_reports_nothing(self):
        verdict, _ = choose_frozen_final(None, None, [_cand(hs=None, aws=None)])
        assert verdict == "no_authority_score"

    def test_every_verdict_is_a_ledger_key(self):
        """A verdict the ledger has no counter for would raise mid-pass (the arm
        does `ledger[verdict] += 1`), so the two vocabularies are one thing.

        THE VERDICT LIST IS READ OFF THE FUNCTION, NOT RETYPED HERE. The first cut
        hard-coded five names, so `orientation_ambiguous` — added by CERT-2864's
        repair — was a verdict this guard could not see: the test that exists to
        catch a missing counter would have passed while the pass KeyError'd on the
        very row it was added to refuse.
        """
        import ast
        import inspect

        from app.tasks.schedule_coverage import (
            choose_frozen_final,
            settle_frozen_mlb_suspended,
        )

        tree = ast.parse(inspect.getsource(choose_frozen_final))
        verdicts = {
            node.value.elts[0].value
            for node in ast.walk(tree)
            if isinstance(node, ast.Return)
            and isinstance(node.value, ast.Tuple)
            and node.value.elts
            and isinstance(node.value.elts[0], ast.Constant)
            and isinstance(node.value.elts[0].value, str)
        }
        assert "settle" in verdicts, (
            "the AST read found no `settle` verdict — the extraction is broken, "
            "and a broken extraction asserts nothing about an empty set"
        )
        assert len(verdicts) >= 7, f"only {len(verdicts)} verdicts found: {verdicts}"

        src = inspect.getsource(settle_frozen_mlb_suspended)
        # `settle` is the one verdict that is NOT a refusal counter — it lands in
        # `settled`, written by the apply loop rather than incremented here.
        for verdict in sorted(verdicts - {"settle"}):
            assert f'"{verdict}": 0' in src, (
                f"`{verdict}` is a `choose_frozen_final` verdict with no counter "
                "initialised in the ledger — the pass would KeyError on it"
            )


class TestOrientation:
    def test_the_production_name_shapes_match(self):
        # Our rows carry "St.Louis Cardinals" (no space) and the truncated
        # "San Francisco Giant"; MLB writes "St. Louis Cardinals" / "Giants".
        assert frozen_final_orientation(
            "St.Louis Cardinals", "Pittsburgh Pirates",
            "St. Louis Cardinals", "Pittsburgh Pirates",
        ) == "aligned"
        assert frozen_final_orientation(
            "Pittsburgh Pirates", "San Francisco Giant",
            "Pittsburgh Pirates", "San Francisco Giants",
        ) == "aligned"

    def test_swapped_is_named_not_accepted_as_aligned(self):
        assert frozen_final_orientation(
            "Boston Red Sox", "Baltimore Orioles",
            "Baltimore Orioles", "Boston Red Sox",
        ) == "swapped"

    def test_a_different_game_matches_neither_way(self):
        assert frozen_final_orientation(
            "Boston Red Sox", "Baltimore Orioles",
            "Seattle Mariners", "Athletics",
        ) == "none"

    @pytest.mark.parametrize(
        "city_pair",
        [("New York Mets", "New York Yankees"),
         ("Chicago Cubs", "Chicago White Sox"),
         ("Los Angeles Dodgers", "Los Angeles Angels"),
         # Not a same-city pair at all — "San" alone is enough to make the raw
         # intersection hold both ways, which is why the rule is "tokens the two
         # names SHARE", not a list of cities. All four families are in the table:
         # 9 of 628 MLB rows in the last 30 days (Subway Series Sep 11-13,
         # Crosstown Aug 18-19, Giants/Padres Sep 11-13).
         ("San Francisco Giants", "San Diego Padres")],
    )
    def test_a_swapped_same_city_game_is_never_read_as_aligned_cert2864(
        self, city_pair
    ):
        """🔴 CERT-2864's merits BLOCK. Both of a same-city game's teams carry the
        city, so the raw intersection holds in BOTH directions and the first cut —
        which asked `aligned` first and returned on it — called a SWAPPED row
        aligned. `choose_frozen_final` would then settle it and copy the
        authority's home score onto our away team, which is the one write this
        rail's `orientation` verdict exists to prevent.
        """
        one, other = city_pair
        assert frozen_final_orientation(one, other, other, one) == "swapped"
        assert frozen_final_orientation(other, one, one, other) == "swapped"

    @pytest.mark.parametrize(
        "city_pair",
        [("New York Mets", "New York Yankees"),
         ("Chicago Cubs", "Chicago White Sox"),
         ("Los Angeles Dodgers", "Los Angeles Angels"),
         # Not a same-city pair at all — "San" alone is enough to make the raw
         # intersection hold both ways, which is why the rule is "tokens the two
         # names SHARE", not a list of cities. All four families are in the table:
         # 9 of 628 MLB rows in the last 30 days (Subway Series Sep 11-13,
         # Crosstown Aug 18-19, Giants/Padres Sep 11-13).
         ("San Francisco Giants", "San Diego Padres")],
    )
    def test_a_correctly_sided_same_city_game_still_settles_cert2864(self, city_pair):
        """The repair must not buy its refusal by refusing the whole class — a
        same-city game the right way round is a row this arm is here to end."""
        one, other = city_pair
        assert frozen_final_orientation(one, other, one, other) == "aligned"
        assert frozen_final_orientation(other, one, other, one) == "aligned"

    def test_the_city_is_only_dropped_within_its_own_pair_cert2864(self):
        """`{new, york}` discriminates perfectly in Yankees @ Red Sox and must keep
        working there — the shared-token drop is scoped to the pair, never a global
        stop-list of city words."""
        assert frozen_final_orientation(
            "Boston Red Sox", "New York Yankees",
            "Boston Red Sox", "New York Yankees",
        ) == "aligned"
        assert frozen_final_orientation(
            "Boston Red Sox", "New York Yankees",
            "New York Yankees", "Boston Red Sox",
        ) == "swapped"

    def test_a_half_matched_row_is_refused_not_called_swapped_cert2864(self):
        """Our away name is truncated to the bare city — the shape this suite
        already carries for "San Francisco Giant". Our HOME matches the
        authority's away exactly, so a swap test that asked only about the home
        side would call this `swapped` and hand a confident side-mapping to a row
        where one of the two teams is not identified at all."""
        assert frozen_final_orientation(
            "New York Mets", "New York",
            "New York Yankees", "New York Mets",
        ) == "ambiguous"

    def test_a_single_possible_orientation_is_never_second_guessed_cert2864(self):
        """The repair is a STRICT REFINEMENT: the discriminating tokens may only
        speak where the raw pair fits both ways. Wherever exactly one orientation
        is possible at all, the answer must be that orientation, unchanged from
        before the repair — which is what keeps this change off the measured
        population (0 of the 59 frozen rows have two teams sharing a token).

        The list carries a cross-sport decoy on purpose: without one, every
        pairing that reaches a single orientation also survives the discriminating
        pass, and the assertion would hold for a version that ran the
        discriminating pass on everything.
        """
        from app.tasks.schedule_coverage import _repair_tokens

        names = ["Boston Red Sox", "Baltimore Orioles", "Chicago Cubs",
                 "Chicago White Sox", "New York Yankees", "New York Mets",
                 "Chicago Fire", "Athletics"]
        checked = 0
        for our_home in names:
            for our_away in names:
                for mlb_home in names:
                    for mlb_away in names:
                        raw_aligned = bool(
                            _repair_tokens(our_home) & _repair_tokens(mlb_home)
                        ) and bool(_repair_tokens(our_away) & _repair_tokens(mlb_away))
                        raw_swapped = bool(
                            _repair_tokens(our_home) & _repair_tokens(mlb_away)
                        ) and bool(_repair_tokens(our_away) & _repair_tokens(mlb_home))
                        if raw_aligned == raw_swapped:
                            continue  # both or neither: the repair's own ground
                        checked += 1
                        expected = "aligned" if raw_aligned else "swapped"
                        assert frozen_final_orientation(
                            our_home, our_away, mlb_home, mlb_away
                        ) == expected, (
                            f"{our_home}/{our_away} vs {mlb_home}/{mlb_away}: only "
                            f"{expected} was possible, so the repair must not "
                            "second-guess it"
                        )
        assert checked > 100, (
            f"only {checked} single-orientation pairings — the population this "
            "asserts over is too thin to mean anything"
        )

    def test_an_unbreakable_tie_is_named_not_guessed_cert2864(self):
        """When the authority names both its sides identically nothing can break
        the tie, so the answer is `ambiguous` — a refusal — and never a coin-flip
        in favour of `aligned`."""
        assert frozen_final_orientation(
            "New York Mets", "New York Yankees",
            "New York Mets", "New York Mets",
        ) == "ambiguous"

    def test_orientation_and_the_boolean_matcher_cannot_drift_5881(self):
        """`frozen_final_orientation` is `_repair_teams_match` decomposed, and the
        two must agree about MEMBERSHIP for every pairing — the new function only
        adds WHICH orientation, never a different answer to whether it matched.

        `ambiguous` is a MEMBER: the row is this game, we simply cannot say which
        way round. That is why the repair resolves the tie after membership is
        decided rather than inside it — a stricter membership test would have put
        this pin and the fix in conflict, and the pin is right.
        """
        names = ["Boston Red Sox", "Baltimore Orioles", "St.Louis Cardinals",
                 "San Francisco Giant", "Chicago Cubs", "Chicago White Sox",
                 "New York Yankees", "New York Mets", "Athletics"]
        for our_home in names:
            for our_away in names:
                for mlb_home in names:
                    for mlb_away in names:
                        matched = _repair_teams_match(
                            our_home, our_away, mlb_home, mlb_away
                        )
                        oriented = frozen_final_orientation(
                            our_home, our_away, mlb_home, mlb_away
                        ) != "none"
                        assert matched == oriented, (
                            f"{our_home}/{our_away} vs {mlb_home}/{mlb_away}: "
                            f"matcher={matched} orientation={oriented}"
                        )


class TestCompletedAt:
    def test_the_invariant_holds_when_our_kickoff_is_the_later_one(self):
        """gotcha #46: `completed_at >= commence_time`. The two starts are only
        guaranteed to sit inside the match window of each other, so anchoring on
        the authority's alone can stamp a row as ending before it began."""
        final_start = _dt(2026, 9, 6, 17, 35)
        commence = final_start + timedelta(hours=5)  # inside the 6h window
        end = frozen_completed_at(final_start, commence)
        assert end > commence
        assert end == commence + MLB_NOMINAL_GAME_LENGTH

    def test_the_authoritys_start_is_the_anchor_when_it_is_later(self):
        final_start = _dt(2026, 9, 6, 17, 35)
        commence = final_start - timedelta(hours=1)
        assert frozen_completed_at(final_start, commence) == (
            final_start + MLB_NOMINAL_GAME_LENGTH
        )

    def test_a_row_with_no_kickoff_still_gets_an_end(self):
        final_start = _dt(2026, 9, 6, 17, 35)
        assert frozen_completed_at(final_start, None) == (
            final_start + MLB_NOMINAL_GAME_LENGTH
        )

    def test_the_nominal_length_is_shared_with_the_fix_end_arm(self):
        """Two rails compute a completed_at for the same sport; a row's end time
        must not depend on which pass reached it first."""
        import inspect

        from app.tasks import schedule_coverage

        src = inspect.getsource(schedule_coverage.repair_inverted_mlb_events)
        assert "MLB_NOMINAL_GAME_LENGTH" in src
        assert "timedelta(hours=3, minutes=15)" not in src


class TestFloor:
    def test_the_floor_is_derived_from_both_doors_never_restated(self):
        from app.tasks.espn_sync import AUTHORITY_STRAGGLER_LOOKBACK
        from app.utils.event_completion import UNREACHABLE_SUSPENDED_MARGIN

        assert frozen_settle_floor() == (
            AUTHORITY_STRAGGLER_LOOKBACK + UNREACHABLE_SUSPENDED_MARGIN
        )

    def test_the_floor_clears_the_resume_window(self):
        """The arm must never end a row the `suspended → live` door can still
        re-open — that door is the one that puts a resumed game back on the
        live shelf."""
        from app.tasks.espn_sync import SUSPENDED_RESUME_WINDOW

        assert frozen_settle_floor() > SUSPENDED_RESUME_WINDOW

    def test_the_selection_does_not_key_on_espn_id(self):
        """0 of the 59 carry one, but the column can be BACKFILLED — a row that
        acquires an `espn_id` past the floor would leave this arm for a door that
        can no longer select it either, and re-strand itself."""
        from app.tasks.schedule_coverage import _FROZEN_SUSPENDED_SQL

        assert "espn_id" not in _FROZEN_SUSPENDED_SQL


# ---------------------------------------------------------------------------
# The write, driven end to end against a real (sqlite) events table.
# ---------------------------------------------------------------------------


async def _run_frozen_settle(monkeypatch, *, rows, games, interloper=None,
                             apply=True):
    """Drive the real `settle_frozen_mlb_suspended` and return (rows, ledger).

    `interloper(engine, ids)` is hung on the MLB schedule fetch — the call the
    pass makes between reading a row and writing it, which is where the race this
    arm has to survive actually lives.
    """
    from sqlalchemy import create_engine, select
    from sqlalchemy.orm import Session

    import app.services.mlb_api as mlb_api
    import app.tasks.base as task_base
    import app.tasks.schedule_coverage as schedule_coverage
    from app.models.models import Base, Event, Sport

    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine, tables=[Event.__table__, Sport.__table__])
    sync_session = Session(engine, expire_on_commit=False)
    sport = Sport(key="baseball_mlb", name="baseball_mlb")
    sync_session.add(sport)
    sync_session.flush()

    ids = []
    for home, away, commence, scores, status in rows:
        row = Event(
            sport_id=sport.id,
            home_team_name=home,
            away_team_name=away,
            commence_time=commence,
            status=status,
            home_score=scores[0],
            away_score=scores[1],
        )
        sync_session.add(row)
        sync_session.flush()
        ids.append(row.id)
    sync_session.commit()

    class _AsyncShim:
        def __init__(self, session):
            self._s = session

        async def execute(self, statement, params=None):
            if params is None:
                return self._s.execute(statement)
            return self._s.execute(statement, params)

        def add(self, obj):
            self._s.add(obj)

        async def commit(self):
            self._s.commit()

        async def flush(self):
            self._s.flush()

    class _Ctx:
        async def __aenter__(self_inner):
            return _AsyncShim(sync_session)

        async def __aexit__(self_inner, *exc):
            sync_session.commit()
            return False

    monkeypatch.setattr(task_base, "get_task_session", lambda: _Ctx())

    fired = []

    class _Service:
        async def get_todays_games(self, date=None):
            if interloper is not None and not fired:
                fired.append(True)
                interloper(engine, ids)
            return games.get(date, [])

        async def close(self):
            pass

    monkeypatch.setattr(mlb_api, "MLBAPIService", _Service)

    # A raw `text()` SELECT carries no type information, so sqlite hands back
    # `commence_time` as a string where Postgres hands back a datetime. Rail
    # fidelity gap, not a production shape.
    _real_as_utc = schedule_coverage._repair_as_utc
    monkeypatch.setattr(
        schedule_coverage,
        "_repair_as_utc",
        lambda dt: _real_as_utc(
            datetime.fromisoformat(dt) if isinstance(dt, str) else dt
        ),
    )

    ledger = await schedule_coverage.settle_frozen_mlb_suspended(apply=apply)

    # EXPIRE BEFORE READING (#6056): a conditional UPDATE that matched zero rows
    # reads identically to one that landed.
    sync_session.expire_all()
    out = [
        sync_session.execute(select(Event).where(Event.id == i)).scalar_one()
        for i in ids
    ]
    if interloper is not None:
        assert fired, "the interloper never ran — this rail proved nothing"
    return out, ledger


def _mlb_game(pk, start, home, away, hs, aws, state="Final"):
    return {
        "gamePk": pk,
        "gameDate": start.isoformat().replace("+00:00", "Z"),
        "status": {"detailedState": state},
        "teams": {
            "home": {"team": {"name": home}, "score": hs},
            "away": {"team": {"name": away}, "score": aws},
        },
    }


def _slate(start, *games):
    return {start.strftime("%Y-%m-%d"): list(games),
            (start - timedelta(days=1)).strftime("%Y-%m-%d"): [],
            (start + timedelta(days=1)).strftime("%Y-%m-%d"): []}


@pytest.mark.asyncio
async def test_the_frozen_game_says_final_with_the_score_it_was_holding_5881(
    monkeypatch,
):
    """🔴 THE SHIP. `/events/15298127`'s shape: Red Sox 3 @ Orioles 1, Sep 6,
    `suspended` with the true score already on the row and a complete curve above
    a header that says no result was reported."""
    start = datetime.now(timezone.utc) - timedelta(days=8)
    rows = [("Baltimore Orioles", "Boston Red Sox", start, (1, 3), "suspended")]
    games = _slate(start, _mlb_game(1, start, "Baltimore Orioles", "Boston Red Sox",
                                    1, 3))
    out, ledger = await _run_frozen_settle(monkeypatch, rows=rows, games=games)

    assert ledger["settled"] == 1 and ledger["applied"] is True
    assert out[0].status == "completed"
    assert (out[0].home_score, out[0].away_score) == (1, 3)
    assert out[0].completed_at is not None
    end = out[0].completed_at
    if end.tzinfo is None:
        end = end.replace(tzinfo=timezone.utc)
    assert end >= start, "gotcha #46: completed_at must not precede first pitch"


@pytest.mark.asyncio
async def test_a_frozen_game_with_no_score_takes_the_authoritys_5881(monkeypatch):
    """`15298326`'s shape: Cardinals @ Rockies, no score of any kind on the row."""
    start = datetime.now(timezone.utc) - timedelta(days=8)
    rows = [("Colorado Rockies", "St.Louis Cardinals", start, (None, None),
             "suspended")]
    games = _slate(start, _mlb_game(2, start, "Colorado Rockies",
                                    "St. Louis Cardinals", 2, 8))
    out, ledger = await _run_frozen_settle(monkeypatch, rows=rows, games=games)

    assert ledger["settled"] == 1
    assert out[0].status == "completed"
    assert (out[0].home_score, out[0].away_score) == (2, 8)


@pytest.mark.asyncio
async def test_a_swapped_same_city_final_writes_nothing_and_is_counted_cert2864(
    monkeypatch,
):
    """🔴 CERT-2864's merits BLOCK, end to end. Our row has the Mets at home; the
    authority's Final has the Yankees at home and won 7-2. Under the first cut the
    shared `{new, york}` made this read `aligned`, so the pass settled the row and
    wrote the YANKEES' 7 onto the METS — a side-mapping defect published as a
    result. Nothing may move, and the refusal must be counted under its own name.
    """
    start = datetime.now(timezone.utc) - timedelta(days=8)
    rows = [("New York Mets", "New York Yankees", start, (None, None), "suspended")]
    games = _slate(start, _mlb_game(7, start, "New York Yankees", "New York Mets",
                                    7, 2))
    out, ledger = await _run_frozen_settle(monkeypatch, rows=rows, games=games)

    assert ledger["orientation"] == 1, ledger
    assert ledger["settled"] == 0
    assert out[0].status == "suspended", "a swapped row must not be ended"
    assert (out[0].home_score, out[0].away_score) == (None, None), (
        "the authority's home score landed on our away team — the exact write "
        "this rail's orientation refusal exists to prevent"
    )
    assert out[0].completed_at is None


@pytest.mark.asyncio
async def test_an_unresolvable_orientation_writes_nothing_and_is_counted_cert2864(
    monkeypatch,
):
    """The tie the club names cannot break: the authority names both its sides
    "New York Mets". Refused under `orientation_ambiguous`, never guessed."""
    start = datetime.now(timezone.utc) - timedelta(days=8)
    rows = [("New York Mets", "New York Yankees", start, (None, None), "suspended")]
    games = _slate(start, _mlb_game(8, start, "New York Mets", "New York Mets", 5, 4))
    out, ledger = await _run_frozen_settle(monkeypatch, rows=rows, games=games)

    assert ledger["orientation_ambiguous"] == 1, ledger
    assert ledger["settled"] == 0
    assert out[0].status == "suspended"
    assert (out[0].home_score, out[0].away_score) == (None, None)


@pytest.mark.asyncio
async def test_a_correctly_sided_same_city_final_still_settles_cert2864(monkeypatch):
    """The repair must not buy its refusal by refusing the whole same-city class."""
    start = datetime.now(timezone.utc) - timedelta(days=8)
    rows = [("Chicago Cubs", "Chicago White Sox", start, (None, None), "suspended")]
    games = _slate(start, _mlb_game(9, start, "Chicago Cubs", "Chicago White Sox",
                                    6, 1))
    out, ledger = await _run_frozen_settle(monkeypatch, rows=rows, games=games)

    assert ledger["settled"] == 1, ledger
    assert out[0].status == "completed"
    assert (out[0].home_score, out[0].away_score) == (6, 1)


@pytest.mark.asyncio
async def test_a_partial_score_keeps_the_half_we_already_held_cert2864(monkeypatch):
    """CERT-2864's follow-up, end to end. The old write was `if either is None:
    write BOTH`, so a row holding one score had it overwritten by a pass that had
    never checked it. Only the gap may be filled."""
    start = datetime.now(timezone.utc) - timedelta(days=8)
    rows = [("Baltimore Orioles", "Boston Red Sox", start, (1, None), "suspended")]
    games = _slate(start, _mlb_game(10, start, "Baltimore Orioles",
                                    "Boston Red Sox", 1, 3))
    out, ledger = await _run_frozen_settle(monkeypatch, rows=rows, games=games)

    assert ledger["settled"] == 1, ledger
    assert out[0].status == "completed"
    assert (out[0].home_score, out[0].away_score) == (1, 3)


@pytest.mark.asyncio
async def test_a_partial_score_that_contradicts_the_authority_is_refused_cert2864(
    monkeypatch,
):
    """The half we hold disagrees, so the row is not the confirmed game — refused
    under `score_conflict`, which the old `ours_scored` gate could never reach."""
    start = datetime.now(timezone.utc) - timedelta(days=8)
    rows = [("Baltimore Orioles", "Boston Red Sox", start, (9, None), "suspended")]
    games = _slate(start, _mlb_game(11, start, "Baltimore Orioles",
                                    "Boston Red Sox", 1, 3))
    out, ledger = await _run_frozen_settle(monkeypatch, rows=rows, games=games)

    assert ledger["score_conflict"] == 1, ledger
    assert ledger["settled"] == 0
    assert out[0].status == "suspended"
    assert (out[0].home_score, out[0].away_score) == (9, None)


@pytest.mark.asyncio
async def test_a_row_inside_the_floor_is_left_alone_5881(monkeypatch):
    """A game that finished an hour ago still has two open doors; ending it here
    would race the pass that can do it properly."""
    start = datetime.now(timezone.utc) - timedelta(hours=4)
    rows = [("Baltimore Orioles", "Boston Red Sox", start, (1, 3), "suspended")]
    games = _slate(start, _mlb_game(3, start, "Baltimore Orioles",
                                    "Boston Red Sox", 1, 3))
    out, ledger = await _run_frozen_settle(monkeypatch, rows=rows, games=games)

    assert ledger["candidates"] == 0 and ledger["settled"] == 0
    assert out[0].status == "suspended"


@pytest.mark.asyncio
async def test_a_settled_row_is_not_a_candidate_5881(monkeypatch):
    """The arm ends `suspended` rows. A game already `completed` is nobody's
    business here — re-stamping it would move a completed_at the settle path
    owns."""
    start = datetime.now(timezone.utc) - timedelta(days=8)
    rows = [("Baltimore Orioles", "Boston Red Sox", start, (1, 3), "completed")]
    games = _slate(start, _mlb_game(4, start, "Baltimore Orioles",
                                    "Boston Red Sox", 1, 3))
    _out, ledger = await _run_frozen_settle(monkeypatch, rows=rows, games=games)
    assert ledger["candidates"] == 0


@pytest.mark.asyncio
async def test_the_authority_saying_in_progress_ends_nothing_5881(monkeypatch):
    """A suspended row whose game the authority has NOT finished stays suspended —
    the arm's warrant is the Final, not the age."""
    start = datetime.now(timezone.utc) - timedelta(days=8)
    rows = [("Baltimore Orioles", "Boston Red Sox", start, (1, 3), "suspended")]
    games = _slate(start, _mlb_game(5, start, "Baltimore Orioles",
                                    "Boston Red Sox", 1, 3, state="In Progress"))
    out, ledger = await _run_frozen_settle(monkeypatch, rows=rows, games=games)

    assert ledger["no_final"] == 1 and ledger["settled"] == 0
    assert out[0].status == "suspended"


@pytest.mark.asyncio
async def test_a_final_outside_the_match_window_is_not_this_game_5881(monkeypatch):
    """Same clubs, same board day, seven hours apart: a different game of the
    series, and matching it would stamp this row with another game's result."""
    start = datetime.now(timezone.utc) - timedelta(days=8)
    rows = [("Baltimore Orioles", "Boston Red Sox", start, (None, None),
             "suspended")]
    other = start + FROZEN_FINAL_MATCH_WINDOW + timedelta(hours=1)
    games = _slate(start, _mlb_game(6, other, "Baltimore Orioles",
                                    "Boston Red Sox", 9, 0))
    out, ledger = await _run_frozen_settle(monkeypatch, rows=rows, games=games)

    assert ledger["no_final"] == 1
    assert out[0].status == "suspended"
    assert out[0].home_score is None


@pytest.mark.asyncio
async def test_the_settle_cannot_land_on_a_row_that_moved_under_it_5881(
    monkeypatch,
):
    """🔴 THE RACE WITNESS. The pass goes out to the MLB API between reading a row
    and writing it. If a real writer resumes the game in that window — the
    `suspended → live` door, or a score write — this arm must not stamp `completed`
    over a game that is being played again.

    The interloper writes a state the producer was NOT offering (live, 2–3), so a
    no-op write cannot pass for a refusal.
    """
    from sqlalchemy import update
    from sqlalchemy.orm import Session

    from app.models.models import Event

    start = datetime.now(timezone.utc) - timedelta(days=8)
    rows = [("Baltimore Orioles", "Boston Red Sox", start, (1, 3), "suspended")]
    games = _slate(start, _mlb_game(7, start, "Baltimore Orioles",
                                    "Boston Red Sox", 1, 3))

    def _resume(engine, ids):
        other = Session(engine, expire_on_commit=False)
        try:
            other.execute(
                update(Event).where(Event.id == ids[0]).values(
                    status="live", home_score=2, away_score=3
                )
            )
            other.commit()
        finally:
            other.close()

    out, ledger = await _run_frozen_settle(
        monkeypatch, rows=rows, games=games, interloper=_resume
    )

    assert ledger["refused_row_moved"] == 1, (
        "the compare-and-write did not refuse a row that moved between the "
        "diagnosis and the write (#6056)"
    )
    assert ledger["settled"] == 0
    assert out[0].status == "live"
    assert (out[0].home_score, out[0].away_score) == (2, 3)


@pytest.mark.asyncio
async def test_a_re_dated_row_is_refused_even_though_status_and_score_held_5881(
    monkeypatch,
):
    """🔴 THE SECOND RACE, and the one a score-only predicate cannot see.

    `commence_time` is what chose this Final out of a three-game series and what
    the `completed_at` being written is computed from — but a re-date sweep
    (`reconcile_anchor_schedule`, the #6073 kickoff sweep) moves it without
    touching `status` or either score. A predicate over the score half alone
    would match a row whose kickoff has moved a day and stamp it with the old
    game's end time while reporting that it refused nothing.
    """
    from sqlalchemy import update
    from sqlalchemy.orm import Session

    from app.models.models import Event

    start = datetime.now(timezone.utc) - timedelta(days=8)
    rows = [("Baltimore Orioles", "Boston Red Sox", start, (1, 3), "suspended")]
    games = _slate(start, _mlb_game(9, start, "Baltimore Orioles",
                                    "Boston Red Sox", 1, 3))

    def _redate(engine, ids):
        other = Session(engine, expire_on_commit=False)
        try:
            other.execute(
                update(Event).where(Event.id == ids[0]).values(
                    commence_time=start - timedelta(days=1)
                )
            )
            other.commit()
        finally:
            other.close()

    out, ledger = await _run_frozen_settle(
        monkeypatch, rows=rows, games=games, interloper=_redate
    )

    assert ledger["refused_row_moved"] == 1, (
        "the predicate did not arbitrate `commence_time` — the column the "
        "decision read to pick this Final and to compute the end time it writes"
    )
    assert ledger["settled"] == 0
    assert out[0].status == "suspended"


@pytest.mark.asyncio
async def test_a_row_settled_by_someone_else_first_is_refused_5881(monkeypatch):
    """`completed_at` is a column this write SETS, and a column that is written
    but never arbitrated is where a compare-and-write still destroys another
    writer's work while reporting that it refused nothing."""
    from sqlalchemy import update
    from sqlalchemy.orm import Session

    from app.models.models import Event

    start = datetime.now(timezone.utc) - timedelta(days=8)
    theirs = start + timedelta(hours=2, minutes=48)
    rows = [("Baltimore Orioles", "Boston Red Sox", start, (1, 3), "suspended")]
    games = _slate(start, _mlb_game(10, start, "Baltimore Orioles",
                                    "Boston Red Sox", 1, 3))

    def _settle_first(engine, ids):
        other = Session(engine, expire_on_commit=False)
        try:
            other.execute(
                update(Event).where(Event.id == ids[0]).values(completed_at=theirs)
            )
            other.commit()
        finally:
            other.close()

    out, ledger = await _run_frozen_settle(
        monkeypatch, rows=rows, games=games, interloper=_settle_first
    )

    assert ledger["refused_row_moved"] == 1
    landed = out[0].completed_at
    if landed.tzinfo is None:
        landed = landed.replace(tzinfo=timezone.utc)
    assert landed == theirs, "another writer's end time was overwritten"


@pytest.mark.asyncio
async def test_a_dry_run_writes_nothing_and_still_reports_the_count_5881(
    monkeypatch,
):
    start = datetime.now(timezone.utc) - timedelta(days=8)
    rows = [("Baltimore Orioles", "Boston Red Sox", start, (1, 3), "suspended")]
    games = _slate(start, _mlb_game(8, start, "Baltimore Orioles",
                                    "Boston Red Sox", 1, 3))
    out, ledger = await _run_frozen_settle(
        monkeypatch, rows=rows, games=games, apply=False
    )

    assert ledger["applied"] is False
    assert ledger["settled"] == 1, "a dry run must say what it would end"
    assert out[0].status == "suspended"


@pytest.mark.asyncio
async def test_every_ledger_key_is_present_on_a_nothing_to_do_pass_5881(
    monkeypatch,
):
    """gotcha #53: a 0 must be a reading, not an absence. A counter that only
    appears when it fires is indistinguishable from a build that never counts."""
    _out, ledger = await _run_frozen_settle(monkeypatch, rows=[], games={})
    assert set(ledger) == {
        "candidates", "settled", "ambiguous", "no_final", "orientation",
        "orientation_ambiguous", "score_conflict", "no_authority_score",
        "refused_row_moved", "applied",
    }
    assert ledger["candidates"] == 0


@pytest.mark.asyncio
async def test_the_daily_beat_runs_the_arm_and_survives_its_failure_5881(
    monkeypatch,
):
    """The arm is wired into the beat entry point, and a failure in it never
    suppresses its two siblings."""
    import app.tasks.schedule_coverage as schedule_coverage

    async def _boom(*a, **k):
        raise RuntimeError("statsapi down")

    async def _ok_repair(*a, **k):
        return {"candidates": 0}

    async def _ok_coverage(*a, **k):
        return {"checked": True}

    monkeypatch.setattr(schedule_coverage, "settle_frozen_mlb_suspended", _boom)
    monkeypatch.setattr(schedule_coverage, "repair_inverted_mlb_events", _ok_repair)
    monkeypatch.setattr(schedule_coverage, "run_mlb_schedule_coverage", _ok_coverage)

    result = await schedule_coverage.run_mlb_schedule_coverage_and_repair()
    assert "error" in result["frozen_settle"]
    assert result["repair"] == {"candidates": 0}
    assert result["coverage"] == {"checked": True}
