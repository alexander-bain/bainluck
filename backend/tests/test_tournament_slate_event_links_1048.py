"""TODAY'S MATCHES OPEN, NOT JUST APPEAR.

ux/1048 · PILLAR: TRUTH · SHIP: a live US Open match on the hub's card takes you
to its match page instead of refusing the tap.

═══ WHAT WAS MEASURED ═══

ux/1033 (#2696) made the day's matches APPEAR: ``build_slate`` walks the order of
play and builds a row for every competition the ceremony register does not claim,
so a second-round match reaches a card that the draw-day register could never
have held. Replayed over the live ESPN scoreboards and production prices at
**2026-09-03T20:16Z**, against a production payload still serving ``count: 0``::

    count 40 · in_progress 8 · scoreboard_pairings 40 · scoreboard_priced 36

**And every one of those 40 rows carried ``event_id: None``.** Measured on the
same replay::

    rows 40  carrying event_id 0  dead-ended 40

``matchEventHref`` falls back to the published ``by_matchup`` map, which is keyed
by REGISTER matchup keys; a scoreboard row's key is ``espn:<competition id>``, so
the fallback could not fire either. The card was about to show a reader the live
match they were watching and then refuse to open it.

═══ THE FIX, AND WHY IT IS NOT A NEW CHANNEL ═══

``resolve_espn_competition_events`` already turns exactly this id into exactly
this row, and the FINISHED list has linked through it since #2693 step 2. It is
bounded by the tournament spec's own ``sport_keys``, and an id claimed by two
events resolves to NEITHER. ``apply_espn_event_links`` stamps the slate from that
same map, so today's rows and the finished list open through ONE rule.

Replayed at 2026-09-03T20:23Z: **39 of 40 rows linked, 8 of 8 live rows linked**,
one ``NO_EVENT_FOR_ESPN_ID`` — competition ``182727``, a fixture ESPN added after
the census was taken and for which no ``events`` row carries the id yet. Reported,
not invented. That gap is what the last two tests here are about.

═══ WHAT THESE GUARDS PIN, AND THE ONE THAT MATTERS MOST ═══

The load-bearing test is ``test_the_key_build_slate_writes_is_the_key_this_reads``.
Every other test in this file constructs a row and then takes it apart, so all of
them would stay green if ``build_slate`` and ``apply_espn_event_links`` agreed
with each other about a prefix that ``authority_match_row`` no longer writes. That
one runs the real builder and reads the real key, so the two-way contract on
``ESPN_MATCHUP_PREFIX`` is asserted against what actually runs.

═══ RED-FIRST ═══

Against the pre-fix tree ``slate_competition_ids`` and ``apply_espn_event_links``
do not exist and ``ESPN_MATCHUP_PREFIX`` does not exist, so the import fails and
every test in the file is red. ``test_an_authority_row_keeps_its_dead_end`` and
``test_the_register_channel_is_not_displaced`` are the CONTROLS: they assert
behaviour this change must NOT alter, so a fix that linked everything
indiscriminately — the obvious over-reach — goes red here rather than passing.
"""

from __future__ import annotations

from datetime import datetime, timezone

from app.utils.tournament_slate import (
    ESPN_MATCHUP_PREFIX,
    apply_espn_event_links,
    build_slate,
    slate_competition_ids,
)

from tests.test_tournament_slate_scoreboard_rows_1033 import (
    LIVE_COMP,
    SOON_COMP,
    _order_of_play,
    _register,
)

NOW = datetime(2026, 9, 3, 20, 16, tzinfo=timezone.utc)

#: The measured production pair: ESPN competition 182709 (Tabilo v Popyrin) is
#: `events` row 15299856. Straight off ARTIFACT-M-20260903-A's census table, and
#: reproduced by the 20:23Z replay through the real resolver.
REAL_COMP = "182709"
REAL_EVENT = 15299856


def _row(comp_id, *, source="scoreboard", event_id=None, **overrides):
    """A slate row in the shape `authority_match_row` returns."""
    row = {
        "matchup_key": f"{ESPN_MATCHUP_PREFIX}{comp_id}",
        "event_id": event_id,
        "pairing_source": source,
        "live_state": "in_progress",
    }
    row.update(overrides)
    return row


def _slate(*rows):
    return {"matches": list(rows), "count": len(rows), "scoreboard_linked": 0}


# ═══════════════════════════════════════════════════════════════════════════
# slate_competition_ids — what gets handed to the resolver
# ═══════════════════════════════════════════════════════════════════════════


def test_it_recovers_the_competition_id_from_a_scoreboard_rows_key():
    assert slate_competition_ids(_slate(_row(REAL_COMP))) == [REAL_COMP]


def test_it_asks_only_about_rows_the_slate_actually_published():
    # Not `order_of_play`. `authority_match_row` already refused every doubles
    # competition and every TBD slot on purpose, and sending those refusals to
    # the resolver would bury its real `NO_EVENT_FOR_ESPN_ID` count under
    # absences we created ourselves.
    slate = _slate(_row("182709"), _row("182711"), _row("182752"))
    assert slate_competition_ids(slate) == ["182709", "182711", "182752"]


def test_an_authority_row_is_never_asked_about():
    # CONTROL. Q503 dead-ends an authority row deliberately — the register holds
    # that fixture and names it WRONG. This change must not enlarge the
    # population that decision covers.
    slate = _slate(_row("182709"), _row("182775", source="authority"))
    assert slate_competition_ids(slate) == ["182709"]


def test_an_empty_or_absent_match_list_asks_nothing():
    assert slate_competition_ids({"matches": []}) == []
    assert slate_competition_ids({}) == []


def test_a_row_whose_key_is_not_an_espn_key_is_skipped_not_mangled():
    # A register-keyed row can never carry `pairing_source: scoreboard` today,
    # but slicing a prefix off a string that does not have it is how a resolver
    # comes to be asked about `mens-singles:alcaraz-vs...`.
    slate = _slate(_row(REAL_COMP), _row("x", matchup_key="mens-singles:a-vs-b:2026-09-03"))
    assert slate_competition_ids(slate) == [REAL_COMP]


# ═══════════════════════════════════════════════════════════════════════════
# apply_espn_event_links — the stamp
# ═══════════════════════════════════════════════════════════════════════════


def test_the_measured_row_gets_the_measured_event():
    slate = _slate(_row(REAL_COMP))
    assert apply_espn_event_links(slate, {REAL_COMP: REAL_EVENT}) == 1
    assert slate["matches"][0]["event_id"] == REAL_EVENT
    assert slate["scoreboard_linked"] == 1


def test_a_live_row_opens():
    # The whole ship, stated as the reader's question: the match on TV right now.
    slate = _slate(_row(REAL_COMP, live_state="in_progress"))
    apply_espn_event_links(slate, {REAL_COMP: REAL_EVENT})
    assert slate["matches"][0]["event_id"] == REAL_EVENT


def test_an_unresolved_id_leaves_the_row_dead_ended_rather_than_guessing():
    # The measured `NO_EVENT_FOR_ESPN_ID` case (competition 182727 at 20:23Z).
    # An absent link is a gap; an invented one is wrong and looks right.
    slate = _slate(_row("182727"))
    assert apply_espn_event_links(slate, {REAL_COMP: REAL_EVENT}) == 0
    assert slate["matches"][0]["event_id"] is None
    assert slate["scoreboard_linked"] == 0


def test_an_authority_row_keeps_its_dead_end():
    # CONTROL, and the one this change is most likely to break by over-reaching:
    # a fix that stamped every row would light this up. Q503's reasoning is
    # about the register's refuted pairing and it still stands.
    slate = _slate(_row("182775", source="authority"))
    assert apply_espn_event_links(slate, {"182775": 15299999}) == 0
    assert slate["matches"][0]["event_id"] is None


def test_the_register_channel_is_not_displaced():
    # CONTROL. `by_matchup` — market -> `futures_markets.event_id` -> event — is
    # the upper rung and is register-owned. A second answer must not overwrite
    # the first; two answers to "which event is this" is how one match becomes
    # two.
    slate = _slate(_row(REAL_COMP, event_id=999))
    assert apply_espn_event_links(slate, {REAL_COMP: REAL_EVENT}) == 0
    assert slate["matches"][0]["event_id"] == 999


def test_no_map_at_all_is_a_zero_and_not_a_crash():
    # The route resolves this map from a database. A cold or failed resolve must
    # cost the links, never the card.
    slate = _slate(_row(REAL_COMP))
    assert apply_espn_event_links(slate, None) == 0
    assert apply_espn_event_links(slate, {}) == 0
    assert slate["matches"][0]["event_id"] is None
    assert slate["scoreboard_linked"] == 0


def test_the_count_is_the_number_of_rows_that_actually_open():
    slate = _slate(_row("182709"), _row("182711"), _row("182727"))
    linked = apply_espn_event_links(slate, {"182709": 1, "182711": 2})
    assert linked == 2
    assert slate["scoreboard_linked"] == 2
    assert sum(1 for r in slate["matches"] if r["event_id"]) == 2


def test_running_it_twice_does_not_double_count():
    # The route calls it once, but a counter that grows on re-entry is a monitor
    # that lies the first time anybody caches the payload and re-stamps it.
    slate = _slate(_row(REAL_COMP))
    apply_espn_event_links(slate, {REAL_COMP: REAL_EVENT})
    apply_espn_event_links(slate, {REAL_COMP: REAL_EVENT})
    assert slate["scoreboard_linked"] == 0  # nothing left to link the second time
    assert slate["matches"][0]["event_id"] == REAL_EVENT


# ═══════════════════════════════════════════════════════════════════════════
# The two-way contract, asserted against what actually runs
# ═══════════════════════════════════════════════════════════════════════════


def test_the_key_build_slate_writes_is_the_key_this_reads():
    """THE LOAD-BEARING GUARD — see this module's docstring.

    Every other test here builds its own row, so all of them would stay green if
    `authority_match_row` started writing `espn_<id>` tomorrow. This one runs the
    real `build_slate` over the real scoreboard fixture and takes the real key
    apart, so the prefix is pinned on both sides at once.
    """
    slate = build_slate(
        _register(),
        prices={},
        now=NOW,
        order_of_play=_order_of_play(),
        order_of_play_complete=True,
    )
    # ux/1033's own guarantee, restated so this test fails loudly rather than
    # vacuously if the scoreboard pass ever stops producing rows.
    assert slate["scoreboard_pairings"] >= 2, slate["scoreboard_pairings"]
    assert slate["scoreboard_linked"] == 0, "build_slate is pure; the route stamps"

    ids = slate_competition_ids(slate)
    assert sorted(ids) == sorted([LIVE_COMP, SOON_COMP])

    # And the round trip: resolve every id the slate asked about, and every
    # scoreboard row must open.
    linked = apply_espn_event_links(slate, {cid: 15000000 + int(cid) for cid in ids})
    assert linked == slate["scoreboard_pairings"]
    assert all(
        row["event_id"] == 15000000 + int(row["matchup_key"][len(ESPN_MATCHUP_PREFIX) :])
        for row in slate["matches"]
        if row.get("pairing_source") == "scoreboard"
    )


def test_build_slate_declares_the_counter_even_with_no_scoreboard_rows():
    # An absent key and a genuine zero are the same bytes to a reader, and this
    # module exists because that confusion shipped for a day (gotcha #53).
    slate = build_slate(_register(), prices={}, now=NOW, order_of_play={})
    assert slate["scoreboard_linked"] == 0
    assert "scoreboard_linked" in slate
