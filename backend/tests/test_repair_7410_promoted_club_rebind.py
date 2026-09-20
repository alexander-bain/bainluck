"""#7410 — the repair may only mint a club ESPN's own directory names, and only by its FULL name.

THE CLASS THIS GUARDS. `repair_7410_promoted_clubs_absent_from_their_league.py`
rebinds ten event sides that carry Manchester City's team id while naming
Coventry City or Hull City, by CREATING the missing club under `soccer_epl`.
"Create a club and point rows at it" is the most dangerous shape a repair can
have, so the population is derived rather than typed, and the thing that keeps
it honest is a single clause: **ESPN's own league directory must name the club,
by its full name.**

Measured on production + ESPN, 2026-09-20:

    clauses 1-3 alone (in the league, cross-club, no club of its own name)
        -> 500+ distinct name pairs, nearly all junk: `soccer_epl` holds
           several hundred South American, youth and women's fixtures.
    clauses 1-4, matching ESPN full names
        -> exactly 10 sides, all Coventry City / Hull City -> 188.
    clauses 1-4, matching ESPN full names AND `short_name`
        -> 12 sides. The two extra are NOT defects.

That last line is the trap this file exists for. Event 6642197 stores the side
names `'Ipswich'` and `'Hull'`, bound to `Ipswich Town` (1819) and `Hull City`
(1804) — the RIGHT clubs, under their full names. Clause 2 sees a name
disagreement and clause 3 sees no `Ipswich` row in the league, so admitting
ESPN's `short_name` would make the repair mint a junk club literally named
`Ipswich` and move a correctly-bound side onto it.

So the tests below are two-sided on purpose. A guard that only proves refusals
passes trivially on "refuse everything", and a repair that refuses everything
leaves Manchester City's page showing three other clubs' games. Every refusal
arm here is paired with an ADMITTED control drawn from the same measurement.
"""
from types import SimpleNamespace

from scripts.repair_7410_promoted_clubs_absent_from_their_league import (
    espn_entry_for,
    league_name_tokens,
    plan_sides,
    reconcile_banked_plan,
    wrong_app_refusal,
)

EPL = 1298
CHAMPIONSHIP = 1294


def _espn(espn_id, display_name, name, short_name):
    return SimpleNamespace(
        espn_id=espn_id, display_name=display_name, name=name, short_name=short_name
    )


#: ESPN's live `eng.1` directory rows for every club these tests turn on, read
#: 2026-09-20. `short_name` is carried deliberately — it is the field the
#: tests below prove is NOT consulted.
ESPN_EPL = [
    _espn("388", "Coventry City", "Coventry City", "Coventry"),
    _espn("306", "Hull City", "Hull City", "Hull"),
    _espn("382", "Manchester City", "Manchester City", "Man City"),
    _espn("349", "Ipswich Town", "Ipswich Town", "Ipswich"),
    _espn("331", "Brighton & Hove Albion", "Brighton & Hove Albion", "Brighton"),
]


def _side(event_id, side, row_name, bound_id, bound_name, bound_sport_id=EPL, sport_id=EPL):
    """One row as `_CANDIDATE_SQL` returns it — clauses 1 and 3 already applied."""
    return SimpleNamespace(
        event_id=event_id,
        sport_id=sport_id,
        side=side,
        row_name=row_name,
        bound_id=bound_id,
        bound_name=bound_name,
        bound_sport_id=bound_sport_id,
        commence_time="2026-09-19",
        status="completed",
    )


#: The ten production sides, 2026-09-20. All bound to 188 Manchester City.
REAL_TEN = [
    _side(15305209, "away", "Coventry City", 188, "Manchester City"),
    _side(15305235, "away", "Hull City", 188, "Manchester City"),
    _side(15297680, "home", "Coventry City", 188, "Manchester City"),
    _side(15297675, "away", "Hull City", 188, "Manchester City"),
    _side(15291111, "home", "Hull City", 188, "Manchester City"),
    _side(15291105, "away", "Coventry City", 188, "Manchester City"),
    _side(15290889, "home", "Coventry City", 188, "Manchester City"),
    _side(15290889, "away", "Hull City", 188, "Manchester City"),
    _side(14961187, "home", "Hull City", 188, "Manchester City"),
    _side(14961186, "away", "Coventry City", 188, "Manchester City"),
]

#: The two production sides of event 6642197 that clauses 1-3 also select and
#: that must NEVER be repaired: the right club, under its full name.
REAL_FALSE_POSITIVES = [
    _side(6642197, "home", "Ipswich", 1819, "Ipswich Town"),
    _side(6642197, "away", "Hull", 1804, "Hull City", bound_sport_id=CHAMPIONSHIP),
]


# --- the admitted control: the repair must still do its job -----------------

def test_the_ten_measured_sides_are_all_admitted():
    """The ship. If this fails, Man City's page keeps showing other clubs' games."""
    plan, _, _ = plan_sides(REAL_TEN, league_name_tokens(ESPN_EPL))
    assert len(plan) == 10
    assert {(p["event_id"], p["side"]) for p in plan} == {
        (15305209, "away"), (15305235, "away"), (15297680, "home"),
        (15297675, "away"), (15291111, "home"), (15291105, "away"),
        (15290889, "home"), (15290889, "away"), (14961187, "home"),
        (14961186, "away"),
    }
    assert {p["row_name"] for p in plan} == {"Coventry City", "Hull City"}
    assert {p["before_id"] for p in plan} == {188}


def test_both_sides_of_the_self_playing_event_are_admitted():
    """15290889 has home_team_id == away_team_id == 188 — Man City playing itself.

    Two sides of ONE event. Anything keyed on event id alone banks one and
    loses the other, which is also why the backup's unique index is
    (event_id, side) and not (event_id).
    """
    plan, _, _ = plan_sides(REAL_TEN, league_name_tokens(ESPN_EPL))
    sides = sorted(p["side"] for p in plan if p["event_id"] == 15290889)
    assert sides == ["away", "home"]


# --- refusal 1: the short_name trap -----------------------------------------

def test_short_name_is_not_a_league_token():
    """`Ipswich` and `Hull` are ESPN short names and must not be matchable."""
    tokens = league_name_tokens(ESPN_EPL)
    assert "coventrycity" in tokens
    assert "hullcity" in tokens
    assert "ipswichtown" in tokens
    assert "ipswich" not in tokens, "short_name would mint a club named after a truncation"
    assert "hull" not in tokens
    assert "mancity" not in tokens


def test_the_two_correctly_bound_sides_are_refused():
    """Event 6642197: the right clubs under their full names. Never a repair."""
    plan, _, not_in_directory = plan_sides(
        REAL_FALSE_POSITIVES, league_name_tokens(ESPN_EPL)
    )
    assert plan == []
    assert not_in_directory == {"Ipswich", "Hull"}


def test_admitting_short_names_would_break_the_correct_sides():
    """The strawman: prove the exclusion in `league_name_tokens` is load-bearing.

    Without it these tests would pass for the wrong reason — the guard would be
    resting on the fixture rather than on the code.
    """
    loose = league_name_tokens(ESPN_EPL) | {"ipswich", "hull"}
    plan, _, _ = plan_sides(REAL_FALSE_POSITIVES, loose)
    assert len(plan) == 2, "the exclusion is what keeps these two out, not the fixture"


def test_the_ten_and_the_two_together_yield_exactly_the_ten():
    """The real measurement: both populations arrive from one query."""
    plan, _, _ = plan_sides(REAL_TEN + REAL_FALSE_POSITIVES, league_name_tokens(ESPN_EPL))
    assert len(plan) == 10
    assert 6642197 not in {p["event_id"] for p in plan}


# --- refusal 2: clause 2, the binding is not actually wrong -----------------

def test_a_side_whose_bound_club_agrees_is_not_a_defect():
    """Clause 2. Punctuation and case are normalized away, so this is no defect."""
    rows = [_side(1, "home", "Coventry City", 999, "coventry city")]
    plan, not_cross_club, _ = plan_sides(rows, league_name_tokens(ESPN_EPL))
    assert plan == []
    assert not_cross_club == 1


def test_a_right_club_on_the_wrong_sport_is_left_to_the_1798_rail():
    """WRONG_SPORT is a different class with a different cause and a working rail.

    The name AGREES, so `binding_defect` returns WRONG_SPORT, not CROSS_CLUB.
    This repair mints clubs; sending it after a defect whose club already exists
    would have it create a second row for a club that has one.
    """
    rows = [_side(2, "away", "Hull City", 1804, "Hull City", bound_sport_id=CHAMPIONSHIP)]
    plan, not_cross_club, _ = plan_sides(rows, league_name_tokens(ESPN_EPL))
    assert plan == []
    assert not_cross_club == 1


# --- refusal 3: clause 4, the club is not in the league at all --------------

def test_a_club_espn_does_not_list_is_refused():
    """`soccer_epl` holds hundreds of these. None of them are this repair's.

    The bound club here genuinely disagrees, so clause 2 admits it — only the
    directory keeps it out.
    """
    rows = [_side(3, "home", "Atletico La Paz", 2001, "Atlético Madrid")]
    plan, not_cross_club, not_in_directory = plan_sides(
        rows, league_name_tokens(ESPN_EPL)
    )
    assert plan == []
    assert not_cross_club == 0, "this IS cross-club; the directory is what refuses it"
    assert not_in_directory == {"Atletico La Paz"}


def test_an_empty_directory_admits_nothing():
    """Belt to `run`'s braces: a dark ESPN must not read as 'no club qualifies'."""
    plan, _, _ = plan_sides(REAL_TEN, set())
    assert plan == []


# --- the directory lookup ---------------------------------------------------

def test_espn_entry_is_found_by_full_name_only():
    assert espn_entry_for(ESPN_EPL, "Coventry City").espn_id == "388"
    assert espn_entry_for(ESPN_EPL, "Hull City").espn_id == "306"
    assert espn_entry_for(ESPN_EPL, "Ipswich") is None
    assert espn_entry_for(ESPN_EPL, "Hull") is None


def test_espn_entry_normalizes_punctuation():
    """Our row spells it `and`; ESPN spells it `&`. Same club, same token."""
    assert espn_entry_for(ESPN_EPL, "Brighton and Hove Albion") is None
    assert espn_entry_for(ESPN_EPL, "Brighton & Hove Albion").espn_id == "331"


def test_an_ambiguous_directory_entry_is_refused():
    """Two entries normalizing the same way is a directory we do not understand."""
    twins = ESPN_EPL + [_espn("999", "Hull  City", "Hull City", "Hull")]
    assert espn_entry_for(twins, "Hull City") is None


def test_an_unknown_club_has_no_entry():
    assert espn_entry_for(ESPN_EPL, "Nottingham Forest") is None
    assert espn_entry_for(ESPN_EPL, "") is None


# --- the banked plan: CERT-3166's repair ------------------------------------
#
# The fresh derivation is DELIBERATELY unable to see its own work. Clause 3
# selects sides with no club of their own name in the league; the first write
# creates exactly such a club. So the second runbook line minted Coventry and
# Hull, and the third line re-derived, matched nothing, and hit the empty-plan
# refusal — the apply could never happen, and no retry after the mint could
# either.
#
# The fix is to derive once and persist: the backup table already holds every
# field a plan needs, because it is what the undo reads. These tests are the
# reconstruction, and they are two-sided like the ones above — every refusal
# arm is paired with an admitted control on the same rows, because a
# reconstruction that returns an empty plan is indistinguishable from the bug.

COVENTRY_EPL = 9001  # the ids the mint produces under soccer_epl
HULL_EPL = 9002

MINTED = {"Coventry City": COVENTRY_EPL, "Hull City": HULL_EPL}


def _bank(event_id, side, row_name, before=188, after="minted"):
    """One row of `backup_7410_promoted_club_binding`.

    `after=None` is the row banked before the mint committed — the state a run
    that crashed mid-way leaves behind, and the one the old code could not
    resume from.
    """
    return SimpleNamespace(
        event_id=event_id,
        side=side,
        row_name=row_name,
        team_id_before=before,
        team_id_after=MINTED[row_name] if after == "minted" else after,
    )


#: The bank as the `--backup` run leaves it: the ten sides, targets resolved.
BANKED_TEN = [_bank(s.event_id, s.side, s.row_name) for s in REAL_TEN]

#: The live sides as they are BEFORE the apply — still bound to 188. Same shape
#: `_LIVE_SIDES_SQL` returns, which applies no clause of its own.
LIVE_BEFORE_APPLY = REAL_TEN


def _live_after_apply(sides=REAL_TEN):
    """The same sides once the repair has written them."""
    return [
        _side(s.event_id, s.side, s.row_name, MINTED[s.row_name], s.row_name)
        for s in sides
    ]


# --- the admitted control: the third runbook line must be able to run --------

def test_the_apply_run_rebuilds_the_whole_plan_from_the_bank():
    """THE SHIP. This is the run that could not happen before (CERT-3166).

    A fresh derivation at this point returns ZERO sides, because the clubs the
    `--backup` run minted now exist and clause 3 excludes them. The bank is
    what carries the plan across that boundary.
    """
    plan, already, anomalies = reconcile_banked_plan(
        BANKED_TEN, LIVE_BEFORE_APPLY, league_name_tokens(ESPN_EPL)
    )
    assert len(plan) == 10, "the apply run must still have all ten sides to write"
    assert already == [] and anomalies == []
    assert {(p["event_id"], p["side"]) for p in plan} == {
        (s.event_id, s.side) for s in REAL_TEN
    }
    assert {p["before_id"] for p in plan} == {188}
    assert {p["after_id"] for p in plan} == {COVENTRY_EPL, HULL_EPL}


def test_the_bank_is_read_before_the_fresh_derivation():
    """A TRIPWIRE, and it is one on purpose — the defect lives in SQL and in
    statement order, neither of which a pure-function test can execute.

    Two things have to stay true or CERT-3166's defect comes back:

    * clause 3 stays an ABSENCE test (`NOT EXISTS`). The tempting "fix" is to
      widen it to also admit a single name match, which would make the apply
      run work — and would silently make the population the #1798 rail's, the
      25-writes-to-make-10 shape this script exists to avoid;
    * and `run` consults the bank BEFORE it derives. Reading them the other way
      round puts the empty-plan refusal in front of the reconstruction, which
      is exactly the run that could not happen.
    """
    import inspect

    from scripts import repair_7410_promoted_clubs_absent_from_their_league as repair

    assert "NOT EXISTS" in repair._CANDIDATE_SQL, "clause 3 must stay an absence test"

    source = inspect.getsource(repair.run)
    assert source.index("_BANKED_SQL") < source.index("_CANDIDATE_SQL"), (
        "the bank must be read before the fresh derivation, or a resumed run "
        "hits the empty-plan refusal instead of its own plan"
    )


def test_a_run_that_crashed_before_the_mint_resumes():
    """`team_id_after IS NULL` — banked, never written. The plan survives it."""
    banked = [_bank(s.event_id, s.side, s.row_name, after=None) for s in REAL_TEN]
    plan, already, anomalies = reconcile_banked_plan(
        banked, LIVE_BEFORE_APPLY, league_name_tokens(ESPN_EPL)
    )
    assert len(plan) == 10 and already == [] and anomalies == []
    assert {p["after_id"] for p in plan} == {None}, "the mint has not named a target yet"


def test_both_sides_of_the_self_playing_event_survive_the_bank():
    """15290889 is banked twice. An event-keyed bank would lose one of them."""
    plan, _, _ = reconcile_banked_plan(
        BANKED_TEN, LIVE_BEFORE_APPLY, league_name_tokens(ESPN_EPL)
    )
    assert sorted(p["side"] for p in plan if p["event_id"] == 15290889) == ["away", "home"]


# --- re-running is a no-op, not a second write ------------------------------

def test_a_completed_repair_reads_as_done_and_not_as_empty():
    """Every side already carries the repair: ten done, nothing to write.

    This must be distinguishable from "the plan came back empty", which is the
    refusal case below — a repair that cannot tell finished from broken is how
    an operator ends up running it twice.
    """
    plan, already, anomalies = reconcile_banked_plan(
        BANKED_TEN, _live_after_apply(), league_name_tokens(ESPN_EPL)
    )
    assert plan == []
    assert len(already) == 10
    assert anomalies == []


def test_a_half_applied_run_writes_only_the_remainder():
    """The CAS wrote six and the process died. The retry owes exactly four."""
    done, remaining = REAL_TEN[:6], REAL_TEN[6:]
    live = _live_after_apply(done) + remaining
    plan, already, anomalies = reconcile_banked_plan(
        BANKED_TEN, live, league_name_tokens(ESPN_EPL)
    )
    assert len(already) == 6
    assert len(plan) == 4
    assert {(p["event_id"], p["side"]) for p in plan} == {
        (s.event_id, s.side) for s in remaining
    }
    assert anomalies == []


# --- the bank is evidence, not authority ------------------------------------

def test_a_side_something_else_moved_is_an_anomaly_not_a_write():
    """Bound to neither the banked before nor after. We do not know its story."""
    moved = _side(15305209, "away", "Coventry City", 7777, "Coventry City FC")
    live = [moved] + [s for s in REAL_TEN if (s.event_id, s.side) != (15305209, "away")]
    plan, already, anomalies = reconcile_banked_plan(
        BANKED_TEN, live, league_name_tokens(ESPN_EPL)
    )
    assert len(plan) == 9, "the other nine are untouched by one row's drift"
    assert len(anomalies) == 1 and "7777" in anomalies[0]
    assert (15305209, "away") not in {(p["event_id"], p["side"]) for p in plan}
    assert already == []


def test_a_side_that_healed_is_left_alone():
    """Same side, same banked name, still on the banked id — but that TEAM ROW
    now reads `Coventry City`, so the binding agrees.

    Whoever renamed team 188 is a separate problem; what matters here is that
    `binding_defect` no longer reads CROSS_CLUB, so this is not our defect any
    more and rebinding it would be the repair inventing work.
    """
    healed = _side(15305209, "away", "Coventry City", 188, "Coventry City")
    live = [healed] + [s for s in REAL_TEN if (s.event_id, s.side) != (15305209, "away")]
    plan, _, anomalies = reconcile_banked_plan(
        BANKED_TEN, live, league_name_tokens(ESPN_EPL)
    )
    assert len(plan) == 9
    assert len(anomalies) == 1 and "cross-club" in anomalies[0]


def test_a_side_whose_own_name_changed_is_an_anomaly():
    """The bank recorded a fact about `Coventry City`. This row is not that row."""
    renamed = _side(15305209, "away", "Coventry Sporting", 188, "Manchester City")
    live = [renamed] + [s for s in REAL_TEN if (s.event_id, s.side) != (15305209, "away")]
    plan, _, anomalies = reconcile_banked_plan(
        BANKED_TEN, live, league_name_tokens(ESPN_EPL)
    )
    assert len(plan) == 9
    assert len(anomalies) == 1 and "name changed" in anomalies[0]


def test_a_banked_side_that_no_longer_reads_back_is_an_anomaly():
    """Deleted event, or a team FK that stopped resolving. Never a silent drop."""
    live = [s for s in REAL_TEN if (s.event_id, s.side) != (14961186, "away")]
    plan, _, anomalies = reconcile_banked_plan(
        BANKED_TEN, live, league_name_tokens(ESPN_EPL)
    )
    assert len(plan) == 9
    assert len(anomalies) == 1 and "no live side reads back" in anomalies[0]


def test_the_directory_still_governs_the_banked_plan():
    """Clause 4 is re-applied on reconstruction, not inherited from the bank.

    A bank is a file we wrote; ESPN's directory is the independent authority
    (D27). If the club has left the league since, the repair does not proceed
    on the strength of its own earlier note.
    """
    plan, already, anomalies = reconcile_banked_plan(
        BANKED_TEN, LIVE_BEFORE_APPLY, set()
    )
    assert plan == [] and already == []
    assert len(anomalies) == 10
    assert all("no longer in ESPN's directory" in note for note in anomalies)


def test_a_bank_row_for_a_club_the_directory_dropped_does_not_stop_the_rest():
    """One club gone, the other still listed: nine writes, one anomaly each way."""
    tokens = {"hullcity", "manchestercity", "ipswichtown", "brightonhovealbion"}
    plan, _, anomalies = reconcile_banked_plan(BANKED_TEN, LIVE_BEFORE_APPLY, tokens)
    assert {p["row_name"] for p in plan} == {"Hull City"}
    assert len(plan) == 5 and len(anomalies) == 5


# --- the app gate -----------------------------------------------------------

def test_a_plan_only_run_needs_no_app(monkeypatch):
    monkeypatch.delenv("HEROKU_APP_NAME", raising=False)
    assert wrong_app_refusal(SimpleNamespace(backup=False, apply=False)) is None


def test_a_write_off_the_producer_app_is_refused(monkeypatch):
    monkeypatch.setenv("HEROKU_APP_NAME", "bainluck-heavy")
    assert wrong_app_refusal(SimpleNamespace(backup=True, apply=False)) is not None
    assert wrong_app_refusal(SimpleNamespace(backup=True, apply=True)) is not None


def test_an_unset_app_is_refused(monkeypatch):
    """Unset means a laptop pointed at the production database."""
    monkeypatch.delenv("HEROKU_APP_NAME", raising=False)
    refusal = wrong_app_refusal(SimpleNamespace(backup=False, apply=True))
    assert refusal is not None and "unset" in refusal


def test_the_producer_app_may_write(monkeypatch):
    monkeypatch.setenv("HEROKU_APP_NAME", "bainluck")
    assert wrong_app_refusal(SimpleNamespace(backup=True, apply=True)) is None


def test_the_undo_earns_the_same_gate(monkeypatch):
    """The restore's parser defines no --backup; the gate must not require one."""
    monkeypatch.setenv("HEROKU_APP_NAME", "bainluck-heavy")
    assert wrong_app_refusal(SimpleNamespace(apply=True)) is not None
    monkeypatch.setenv("HEROKU_APP_NAME", "bainluck")
    assert wrong_app_refusal(SimpleNamespace(apply=True)) is None
