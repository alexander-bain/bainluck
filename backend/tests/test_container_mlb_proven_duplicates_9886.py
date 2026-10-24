"""A proven duplicate's questions reach the MLB postseason through its member. #9886.

**SHIP: an MLB postseason hub includes the questions attached to already-proven
duplicate game rows under their authoritative canonical member, without
admitting unproven matches.** (Pillars: MATCHING / TRUTH.)

Authority's first enabled pass (2026-10-24 01:49Z, retained under
`authority/artifacts-authority-5341-a2-20261023T2311Z/p2`) reported 157
questions on 9 rows with no ESPN id, eight of them second rows beside an
ESPN-stamped member. The assembly read never looked at `event_tags`, so even a
row the write side had already proven to be the member's game
(`provenance:duplicate-of:<member>`, ruling 048) stayed stranded.

The label is trusted exactly as `proven_duplicates` trusts it: one hop, the
write side's proof, never re-derived from names or kickoffs. Everything graded
here is the read side DECLINING what that proof does not cover — and, for each
refusal, that the row stays unidentified so the pass still says `partial`.

The rows are test doubles keyed on the v3 suite's real event ids
(`test_container_mlb_playoffs_v3`); the labelled ids (153xxxxx) are DERIVED.
"""

from __future__ import annotations

from dataclasses import replace
from datetime import datetime, timezone

import pytest

import app.tasks.container_mlb_playoffs_assembly as assembly
from app.tasks.container_mlb_playoffs_assembly import (
    MARKETS_FOR_EVENTS_SQL,
    UNIDENTIFIED_IN_SPAN_SQL,
    duplicates_of_members_sql,
    gather_mlb_postseason_candidates,
    run_mlb_postseason_assembly,
)
from app.utils.container_mlb_playoffs import (
    EXCLUDED_DUPLICATE_LABEL_REFUSED,
    EXCLUDED_GAME_WINNER_MARKET,
    INCOMPLETE_DUPLICATES_UNREAD,
    INCOMPLETE_MARKETS_TRUNCATED,
    INCOMPLETE_STRANDED_QUESTIONS,
    REFUSED_CONFLICTING_LABELS,
    REFUSED_MALFORMED_LABEL,
    REFUSED_OTHER_SEASON,
    REFUSED_OTHER_SPORT,
    REFUSED_ROW_HOLDS_ESPN_ID,
    REFUSED_SELF_LABEL,
    REFUSED_TARGET_IS_LABELLED,
    REFUSED_TARGET_NOT_A_MEMBER,
    DuplicateRow,
    EventRow,
    MarketRow,
    admit_proven_duplicates,
    duplicate_labels,
    postseason_member_rows,
    resolve_postseason_members,
    select_postseason_games,
)
from tests import test_container_mlb_playoffs_v3 as _v3
from tests.test_container_mlb_playoffs_v3 import (
    CWS_HOU_G2_EVENT,
    G1_EVENT,
    G2_EVENT,
    ODDS_TWIN,
    POST_2026,
    REGULAR_ESPN,
    _boards,
    _Container,
    _edge_rows,
    _markets,
    _rows,
    _Session,
)

corpus = _v3.corpus
g2 = _v3.g2

G2_START = datetime(2026, 9, 30, 18, 0, tzinfo=timezone.utc)

#: DERIVED: a StatPal pre-load row for Game 2 the write side proved to be it.
GHOST = DuplicateRow(15330001, None, "scheduled", G2_START, "Atlanta Braves", "Philadelphia Phillies",
                     "baseball_mlb", (str(G2_EVENT),))


def _ghost_markets(event_id=GHOST.id, start=80_000_000):
    return [
        MarketRow(start, event_id, "Braves total runs", "KXMLBTOTAL-G2", "kalshi", "binary", "open"),
        MarketRow(start + 1, event_id, "First inning run", "KXMLBF5-G2", "kalshi", "binary", "open"),
    ]


def _as_event_row(row: DuplicateRow) -> EventRow:
    """The same row as the in-span report reads it (no labels on that read)."""
    return EventRow(row.id, row.espn_id, row.status, row.commence_time, row.home, row.away)


def _market_ids(harvest_or_report):
    members = harvest_or_report.members
    return [c.child_id for c in members.candidates if c.child_type == "market"]


def _members(corpus):
    selection = select_postseason_games(_boards(corpus), POST_2026)
    return postseason_member_rows(selection, _rows())


# --- the label as a string ------------------------------------------------------


def test_labels_are_read_verbatim_from_either_driver_shape():
    tag = f"provenance:duplicate-of:{G2_EVENT}"
    assert duplicate_labels([tag, "tier:1"]) == (str(G2_EVENT),)
    assert duplicate_labels(f'["{tag}", "tier:1"]') == (str(G2_EVENT),)
    # A malformed tail and a second label are SEEN, so they can be refused.
    assert duplicate_labels([tag, "provenance:duplicate-of:12x"]) == (str(G2_EVENT), "12x")
    assert duplicate_labels(None) == () and duplicate_labels("not json") == () and duplicate_labels({}) == ()


# --- the pure rule --------------------------------------------------------------


def test_a_label_naming_a_member_directly_is_admitted_through_it(corpus):
    decision = admit_proven_duplicates(POST_2026, _members(corpus), [GHOST])
    assert decision.admitted == {GHOST.id: G2_EVENT}
    [receipt] = decision.receipts
    assert (receipt["event_id"], receipt["duplicate_of"]) == (GHOST.id, G2_EVENT)
    assert decision.refused == []


@pytest.mark.parametrize(
    "row, refusal",
    [
        (replace(GHOST, sport_key="americanfootball_nfl"), REFUSED_OTHER_SPORT),
        (replace(GHOST, sport_key=None), REFUSED_OTHER_SPORT),
        (replace(GHOST, duplicate_labels=(str(G2_EVENT), str(G1_EVENT))), REFUSED_CONFLICTING_LABELS),
        (replace(GHOST, duplicate_labels=(str(G2_EVENT), "15320701x")), REFUSED_CONFLICTING_LABELS),
        (replace(GHOST, duplicate_labels=("15320701x",)), REFUSED_MALFORMED_LABEL),
        (replace(GHOST, duplicate_labels=(str(GHOST.id),)), REFUSED_SELF_LABEL),
        # Not a member: a regular-season row, a missing row, any other id.
        (replace(GHOST, duplicate_labels=("15000001",)), REFUSED_TARGET_NOT_A_MEMBER),
        (replace(GHOST, espn_id=REGULAR_ESPN), REFUSED_ROW_HOLDS_ESPN_ID),
        (replace(GHOST, commence_time=datetime(2025, 9, 30, 18, 0, tzinfo=timezone.utc)), REFUSED_OTHER_SEASON),
        (replace(GHOST, commence_time=None), REFUSED_OTHER_SEASON),
    ],
)
def test_every_label_the_proof_does_not_cover_admits_nothing_and_is_named(corpus, row, refusal):
    decision = admit_proven_duplicates(POST_2026, _members(corpus), [row])
    assert decision.admitted == {}
    [receipt] = decision.refused
    assert (receipt["event_id"], receipt["refusal"]) == (row.id, refusal)


def test_a_member_labelled_as_its_own_duplicate_is_refused_and_stays_a_member(corpus):
    members = _members(corpus)
    me = DuplicateRow(G2_EVENT, "401907972", "scheduled", G2_START, "a", "b", "baseball_mlb", (str(G2_EVENT),))
    decision = admit_proven_duplicates(POST_2026, members, [me])
    assert decision.admitted == {} and decision.refused[0]["refusal"] == REFUSED_SELF_LABEL


def test_a_member_labelled_as_another_members_duplicate_is_refused(corpus):
    # Two members are two ESPN games; a label cannot fold one into the other.
    g1_as_dup = DuplicateRow(G1_EVENT, "401907965", "scheduled", G2_START, "a", "b", "baseball_mlb", (str(G2_EVENT),))
    decision = admit_proven_duplicates(POST_2026, _members(corpus), [g1_as_dup])
    assert decision.refused[0]["refusal"] == REFUSED_ROW_HOLDS_ESPN_ID


def test_one_hop_a_target_that_is_itself_labelled_admits_nothing(corpus):
    members = _members(corpus)
    # The member carries a label (here naming the ghost: a cycle). Neither
    # direction is walked; the member stays a member on ESPN's id.
    members[G2_EVENT] = replace(members[G2_EVENT], duplicate_labels=(str(GHOST.id),))
    decision = admit_proven_duplicates(POST_2026, members, [GHOST])
    assert decision.admitted == {} and decision.refused[0]["refusal"] == REFUSED_TARGET_IS_LABELLED


def test_only_a_member_that_survives_the_join_brings_questions(corpus):
    # Two rows holding Game 2's ESPN id: neither is a member, so a label naming
    # one of them admits nothing even if a decision said otherwise.
    selection = select_postseason_games(_boards(corpus), POST_2026)
    twin = EventRow(9000, "401907972", "scheduled", None, "Atlanta Braves", "Philadelphia Phillies")
    rows = _rows() + [twin]
    assert G2_EVENT not in postseason_member_rows(selection, rows)
    forged = admit_proven_duplicates(POST_2026, {G2_EVENT: _rows()[1]}, [GHOST])
    members = resolve_postseason_members(selection, rows, _ghost_markets(), forged)
    assert members.proven_duplicates == []
    assert not {m.id for m in _ghost_markets()} & set(_market_ids_of(members))


def _market_ids_of(members):
    return [c.child_id for c in members.candidates if c.child_type == "market"]


def test_each_admitted_question_is_counted_once_and_keeps_its_own_row(corpus):
    selection = select_postseason_games(_boards(corpus), POST_2026)
    decision = admit_proven_duplicates(POST_2026, _members(corpus), [GHOST])
    ghost_markets = _ghost_markets()
    members = resolve_postseason_members(
        selection, _rows(), _markets() + ghost_markets + ghost_markets[:1], decision
    )
    ids = _market_ids_of(members)
    assert ids.count(ghost_markets[0].id) == 1 and ids.count(ghost_markets[1].id) == 1
    assert [d["event_id"] for d in members.proven_duplicates] == [GHOST.id]
    assert members.proven_duplicates[0]["duplicate_of"] == G2_EVENT


def test_the_ghosts_own_winner_market_is_the_game_card_not_another_question(corpus):
    selection = select_postseason_games(_boards(corpus), POST_2026)
    decision = admit_proven_duplicates(POST_2026, _members(corpus), [GHOST])
    # The stored shape of Game 1's Kalshi winner (v3 `_game_one_board`, REAL),
    # moved to Game 2's ticker and hung on the ghost.
    winner = MarketRow(80_000_009, GHOST.id, "Game 2: Philadelphia vs Atlanta", "KXMLBGAME-26SEP301400PHIATL",
                       "kalshi", "duel", "open")
    members = resolve_postseason_members(selection, _rows(), _markets() + [winner], decision)
    assert winner.id not in _market_ids_of(members)
    [receipt] = [r for r in members.excluded[EXCLUDED_GAME_WINNER_MARKET] if r["market_id"] == winner.id]
    assert (receipt["event_id"], receipt["via_member"]) == (GHOST.id, G2_EVENT)


# --- through the harvest and the shared pipeline --------------------------------


@pytest.mark.asyncio
async def test_a_proven_duplicates_questions_make_the_postseason_whole(corpus):
    ghost_markets = _ghost_markets()
    session = _Session(_rows(), _markets() + ghost_markets, unidentified=[_as_event_row(GHOST)], labelled=[GHOST])
    report = await run_mlb_postseason_assembly(session, _Container(), _boards(corpus), POST_2026, apply=True)
    # Before #9886 this was `partial` with 2 stranded questions.
    assert report["terminal"] == "complete", report["incomplete"]
    assert report["unidentified_in_span"] == []
    assert report["harvest"]["proven_duplicates"] == 1 and report["harvest"]["stranded_questions"] == 0
    [proven] = report["proven_duplicates"]
    assert (proven["event_id"], proven["duplicate_of"], proven["markets"]) == (GHOST.id, G2_EVENT, 2)
    edges = _edge_rows(session)
    assert {m.id for m in ghost_markets} <= {e["child_id"] for e in edges if e["child_type"] == "market"}
    # The ghost row is never a member and nothing moves: only edges are written.
    assert GHOST.id not in {e["child_id"] for e in edges if e["child_type"] == "event"}
    assert {getattr(w, "table", None).name for w in session.writes if getattr(w, "table", None) is not None} <= {
        "event_edges", "market_match_receipts"
    }
    # The ghost's questions share the members' keyset read.
    [market_read] = [p for s, p in session.reads if s == MARKETS_FOR_EVENTS_SQL]
    assert GHOST.id in market_read["event_ids"]


@pytest.mark.asyncio
async def test_a_proven_duplicate_outside_the_span_still_brings_its_questions(corpus):
    # A rescheduled game's ghost keeps its old start (mlb_reschedule_ghost_sweep).
    early = replace(GHOST, commence_time=datetime(2026, 9, 20, 18, 0, tzinfo=timezone.utc))
    session = _Session(_rows(), _markets() + _ghost_markets(), labelled=[early])
    harvest = await gather_mlb_postseason_candidates(session, _boards(corpus), POST_2026)
    assert {m.id for m in _ghost_markets()} <= set(_market_ids(harvest))
    assert harvest.incomplete == []


@pytest.mark.parametrize(
    "row",
    [
        replace(GHOST, duplicate_labels=(str(G2_EVENT), str(G1_EVENT))),
        replace(GHOST, duplicate_labels=(str(G2_EVENT), "15320701x")),
        replace(GHOST, espn_id=REGULAR_ESPN),
        replace(GHOST, sport_key="americanfootball_nfl"),
        replace(GHOST, commence_time=datetime(2025, 9, 30, 18, 0, tzinfo=timezone.utc)),
    ],
    ids=["two-labels", "malformed-second", "own-espn-id", "other-sport", "other-season"],
)
@pytest.mark.asyncio
async def test_a_refused_label_leaves_its_row_stranded_and_the_pass_partial(corpus, row):
    in_span = [_as_event_row(row)] if row.sport_key == "baseball_mlb" else []
    session = _Session(_rows(), _markets() + _ghost_markets(), unidentified=in_span, labelled=[row])
    report = await run_mlb_postseason_assembly(session, _Container(), _boards(corpus), POST_2026, apply=True)
    assert not {m.id for m in _ghost_markets()} & {e["child_id"] for e in _edge_rows(session)}
    assert report["proven_duplicates"] == []
    [refused] = report["excluded"][EXCLUDED_DUPLICATE_LABEL_REFUSED]
    assert refused["event_id"] == row.id
    if in_span:
        assert [u["event_id"] for u in report["unidentified_in_span"]] == [row.id]
        assert report["terminal"] == "partial" and INCOMPLETE_STRANDED_QUESTIONS in report["incomplete"]


@pytest.mark.parametrize(
    "label",
    ["15000001", str(CWS_HOU_G2_EVENT)],
    ids=["not-a-postseason-row", "member-missing-this-pass"],
)
@pytest.mark.asyncio
async def test_a_label_naming_no_member_is_never_read_and_its_row_stays_stranded(corpus, label):
    row = replace(GHOST, duplicate_labels=(label,))
    # CWS@HOU Game 2's own row is absent, so it is a gap and not a member.
    session = _Session(_rows(include=(G1_EVENT, G2_EVENT)), _markets() + _ghost_markets(),
                       unidentified=[_as_event_row(row)], labelled=[row])
    report = await run_mlb_postseason_assembly(session, _Container(), _boards(corpus), POST_2026, apply=True)
    assert report["proven_duplicates"] == [] and EXCLUDED_DUPLICATE_LABEL_REFUSED not in report["excluded"]
    assert [u["event_id"] for u in report["unidentified_in_span"]] == [row.id]
    assert INCOMPLETE_STRANDED_QUESTIONS in report["incomplete"]


@pytest.mark.asyncio
async def test_mixed_labelled_and_unlabelled_rows_admit_only_the_proven_one(corpus):
    twin_market = MarketRow(81_000_000, ODDS_TWIN.id, "x", "X", "kalshi", "binary", "open")
    session = _Session(
        _rows(), _markets() + _ghost_markets() + [twin_market],
        unidentified=[_as_event_row(GHOST), ODDS_TWIN], labelled=[GHOST],
    )
    report = await run_mlb_postseason_assembly(session, _Container(), _boards(corpus), POST_2026, apply=True)
    assert [u["event_id"] for u in report["unidentified_in_span"]] == [ODDS_TWIN.id]
    assert report["harvest"]["stranded_questions"] == 1
    assert report["terminal"] == "partial" and report["reason"] == INCOMPLETE_STRANDED_QUESTIONS
    market_edges = {e["child_id"] for e in _edge_rows(session) if e["child_type"] == "market"}
    assert {m.id for m in _ghost_markets()} <= market_edges and twin_market.id not in market_edges


@pytest.mark.asyncio
async def test_an_overflowing_duplicate_read_admits_nothing(corpus, monkeypatch):
    monkeypatch.setattr(assembly, "DUPLICATE_READ_LIMIT", 1)
    second = replace(GHOST, id=15330002, duplicate_labels=(str(G1_EVENT),))
    session = _Session(_rows(), _markets() + _ghost_markets(), unidentified=[_as_event_row(GHOST)],
                       labelled=[GHOST, second])
    report = await run_mlb_postseason_assembly(session, _Container(), _boards(corpus), POST_2026, apply=True)
    assert report["harvest"]["duplicates_skipped"] == "duplicate_read_overflow"
    assert report["proven_duplicates"] == []
    assert [u["event_id"] for u in report["unidentified_in_span"]] == [GHOST.id]
    assert report["terminal"] == "partial"
    [(_, params)] = [(s, p) for s, p in session.reads if s.startswith(assembly.DUPLICATES_OF_MEMBERS_SQL_HEAD)]
    assert params["limit"] == 2


@pytest.mark.asyncio
async def test_too_many_members_skip_the_read_rather_than_widen_it(corpus, monkeypatch):
    monkeypatch.setattr(assembly, "DUPLICATE_READ_MAX_ARMS", 2)
    session = _Session(_rows(), _markets() + _ghost_markets(), unidentified=[_as_event_row(GHOST)], labelled=[GHOST])
    report = await run_mlb_postseason_assembly(session, _Container(), _boards(corpus), POST_2026, apply=True)
    assert report["harvest"]["duplicates_skipped"] == "too_many_members"
    assert not [s for s, _ in session.reads if s.startswith(assembly.DUPLICATES_OF_MEMBERS_SQL_HEAD)]
    assert report["terminal"] == "partial"


#: A rescheduled game's ghost: labelled, but outside the span, so it is in no
#: in-span report and only the duplicate read can see its questions.
EARLY_GHOST = replace(GHOST, commence_time=datetime(2026, 9, 20, 18, 0, tzinfo=timezone.utc))


@pytest.mark.parametrize(
    "skip, patch",
    [
        (None, {}),
        ("too_many_members", {"DUPLICATE_READ_MAX_ARMS": 2}),
        ("duplicate_read_overflow", {"DUPLICATE_READ_LIMIT": 1}),
    ],
    ids=["read-whole", "too-many-members", "read-overflow"],
)
@pytest.mark.asyncio
async def test_a_skipped_duplicate_read_never_earns_complete(corpus, monkeypatch, skip, patch):
    # Otherwise whole: every board day read, every game a member, no question
    # cap, and NOTHING stranded in the span — the skip is the only gap.
    for name, value in patch.items():
        monkeypatch.setattr(assembly, name, value)
    second = replace(EARLY_GHOST, id=15330002, duplicate_labels=(str(G1_EVENT),))
    session = _Session(_rows(), _markets() + _ghost_markets(), unidentified=[], labelled=[EARLY_GHOST, second])
    report = await run_mlb_postseason_assembly(session, _Container(), _boards(corpus), POST_2026, apply=True)
    assert report["unidentified_in_span"] == [] and report["harvest"]["stranded_questions"] == 0
    assert report["harvest"]["markets_truncated"] is False
    # The skip reason stays visible beside the verdict.
    assert report["harvest"]["duplicates_skipped"] == skip
    market_edges = {e["child_id"] for e in _edge_rows(session) if e["child_type"] == "market"}
    if skip is None:
        assert report["terminal"] == "complete" and report["incomplete"] == []
        assert {m.id for m in _ghost_markets()} <= market_edges
    else:
        assert report["proven_duplicates"] == []
        assert not {m.id for m in _ghost_markets()} & market_edges
        assert report["incomplete"] == [INCOMPLETE_DUPLICATES_UNREAD]
        assert report["terminal"] == "partial" and report["reason"] == INCOMPLETE_DUPLICATES_UNREAD


@pytest.mark.asyncio
async def test_admitted_questions_spend_the_same_page_budget(corpus):
    # 4 member questions + 2 ghost questions over pages of 2, at most 2 pages.
    session = _Session(_rows(), _markets() + _ghost_markets(), labelled=[GHOST])
    harvest = await gather_mlb_postseason_candidates(session, _boards(corpus), POST_2026, limit=2, max_pages=2)
    assert harvest.markets_truncated is True
    assert INCOMPLETE_MARKETS_TRUNCATED in harvest.incomplete
    assert len([s for s, _ in session.reads if s == MARKETS_FOR_EVENTS_SQL]) == 2


@pytest.mark.asyncio
async def test_no_member_means_no_duplicate_read(corpus):
    session = _Session([], [], labelled=[GHOST])
    await gather_mlb_postseason_candidates(session, _boards(corpus), POST_2026)
    assert not [s for s, _ in session.reads if s.startswith(assembly.DUPLICATES_OF_MEMBERS_SQL_HEAD)]


@pytest.mark.asyncio
async def test_the_in_span_report_is_told_which_rows_were_admitted(corpus):
    session = _Session(_rows(), _markets() + _ghost_markets(), unidentified=[_as_event_row(GHOST)], labelled=[GHOST])
    await gather_mlb_postseason_candidates(session, _boards(corpus), POST_2026)
    [(_, params)] = [(s, p) for s, p in session.reads if s == UNIDENTIFIED_IN_SPAN_SQL]
    assert params["admitted_ids"] == [GHOST.id]


# --- the statement --------------------------------------------------------------


def test_the_duplicate_read_is_element_containment_the_gin_index_serves():
    sql = duplicates_of_members_sql(3)
    assert sql.count("e.event_tags @> jsonb_build_array(CAST(:tag_") == 3
    for n in range(3):
        assert f":tag_{n} " in sql
    # A prefix LIKE or `?|` is a sequential scan of `events` (proven_duplicates).
    assert "LIKE" not in sql.upper() and "?|" not in sql
    # The bound sits outside a MATERIALIZED CTE and nothing orders the scan: a
    # LIMIT (or `ORDER BY e.id LIMIT`) on the scan itself let a generic plan
    # trade the GIN index for a full scan (module note; the real-Postgres gate
    # pins the custom and the generic plan).
    assert sql.startswith("WITH labelled AS MATERIALIZED (")
    assert sql.endswith(") SELECT * FROM labelled LIMIT :limit")
    assert "ORDER BY" not in sql.upper() and sql.count("LIMIT") == 1
    # Every sport is read so a label on another sport is named, not invisible.
    assert "LEFT JOIN sports" in sql and ":sport_key" not in sql


@pytest.mark.parametrize("arms", [0, assembly.DUPLICATE_READ_MAX_ARMS + 1])
def test_the_statement_refuses_an_unbounded_arm_count(arms):
    with pytest.raises(ValueError):
        duplicates_of_members_sql(arms)
