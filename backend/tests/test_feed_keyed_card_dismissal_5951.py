"""#5951 — a swiped concept/tournament card must stay swiped.

## The defect these tests pin

Alex, on the installed native build, reported Discover as "consistently entirely
UFC/F1/Cycling event cards". He swiped them away. They came back. Production
``discover_interactions`` holds the proof, 2026-09-13 15:54:22Z and the twenty
seconds before it: **ten native ``unlike`` rows in 21 seconds, nine of them the
same card**, ``event:f1:spanish-grand-prix-winner``.

Three layers each dropped that swipe, and all three had to be repaired — any one
left in place keeps the card coming back:

1. **Ingest.** ``_DISCOVER_ITEM_TYPES`` had no ``concept``/``bundle``, and
   ``_normalize_discover_value`` coerces an unrecognized value to its FALLBACK,
   which for ``item_type`` is ``"futures"``. So the row was stored as a futures
   dismissal whose ``item_id`` is a concept key — a shape no reader can match.
2. **The read's WHERE.** The recent-items query asked only for
   ``item_type IN ('event','futures')``, so web's ``grid``-labelled concept
   swipes never reached the loop at all.
3. **The loop.** ``int(item_id_raw)`` raised on a key and ``continue``d, which
   discarded the whole row — taking the story-key and semantic-token suppression
   with it, so the card was not even softly penalised by name.

## Why the pre-existing tests stayed green

Every dismissal test in this suite uses a NUMERIC id, because events and futures
are rows. The card types whose identity is a key had no coverage, so all three
layers could be wrong at once and the suite stayed green. ``_load`` below drives
the real ``_load_personalization_context`` for the same reason #5453's file does:
a test that constructs the context by hand cannot catch a field nothing writes.

## Both directions

A suppression that runs away empties a surface (#1091, standing notice 35), so
the controls are as load-bearing as the suppression tests: a key nobody swiped
survives, ``my_teams_only`` is exempt, and a reader with no swipes gets the list
back unchanged.
"""

from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.routes.feed import (
    _DISCOVER_ITEM_TYPES,
    _drop_dismissed_keyed_items,
    _normalize_discover_value,
)
from app.utils.personalization import PersonalizationContext

_SESSION_ID = "keyed-dismissal-session-5951"

#: The specimen, verbatim from the production row Alex wrote.
_F1_KEY = "event:f1:spanish-grand-prix-winner"
_VUELTA_KEY = "event:cycling:vuelta-2026"


def _card(key: str, card_type: str = "concept") -> dict:
    return {"type": card_type, "score": 50, "data": {"key": key, "name": key}}


# ---------------------------------------------------------------------------
# Layer 1 — ingest: the swipe is recorded as what it is
# ---------------------------------------------------------------------------


def test_a_concept_swipe_is_not_silently_recorded_as_a_futures_swipe():
    """The silent-coercion half. This is the line that made the row unmatchable.

    ``_normalize_discover_value`` returning the fallback is correct behaviour for
    a typo; it is a data bug for a card type the clients genuinely send. Native
    sends ``concept`` (``DiscoverView.itemType``) and there is no numeric futures
    id anywhere in that card.
    """
    assert _normalize_discover_value("concept", _DISCOVER_ITEM_TYPES, "futures") == (
        "concept"
    ), "a concept swipe stored as 'futures' carries a key in a row-id column"


def test_the_client_sent_item_types_all_survive_ingest():
    """Every type either client labels a Discover card with."""
    for sent in ("event", "futures", "grid", "tournament", "concept", "bundle"):
        assert (
            _normalize_discover_value(sent, _DISCOVER_ITEM_TYPES, "futures") == sent
        ), f"{sent!r} is coerced away at ingest"


def test_an_unknown_item_type_still_falls_back():
    """The control: widening the allowlist must not disable it."""
    assert (
        _normalize_discover_value("wingding", _DISCOVER_ITEM_TYPES, "futures")
        == "futures"
    )


# ---------------------------------------------------------------------------
# Layer 2 + 3 — the real loader carries a keyed swipe into the context
# ---------------------------------------------------------------------------


def _recent_items_session(recent_rows):
    """A DB stand-in answering the three ``discover_interactions`` reads.

    Routed on the projection, exactly as #5453's harness is: the recent-items
    read is the 6-column one and the only one these tests feed. It also captures
    every statement so the WHERE clause itself can be asserted — layer 2 is a
    filter, and a mock that ignores WHERE cannot see a filter that excludes the
    rows.
    """
    seen_statements: list[str] = []

    def _result(rows):
        result = MagicMock()
        result.all.return_value = rows
        result.fetchall.return_value = rows
        result.scalars.return_value.all.return_value = rows
        result.scalars.return_value.first.return_value = None
        result.scalar_one_or_none.return_value = None
        return result

    async def mock_execute(stmt, *args, **kwargs):
        rendered = str(stmt)
        # `str(stmt)` renders an `IN` as `IN (__[POSTCOMPILE_item_type_1])` — the
        # values are bind parameters and simply are not in that string, so an
        # assertion about WHICH item types are selected has to compile the binds
        # in. Kept best-effort: the dialect-free compile can raise on some
        # constructs, and this capture is diagnostic, never the query itself.
        try:
            rendered = str(stmt.compile(compile_kwargs={"literal_binds": True}))
        except Exception:
            # Keep the un-compiled render rather than dropping the statement:
            # this capture is diagnostic, and a statement missing from the list
            # would make the WHERE assertion below fail for the wrong reason.
            rendered = str(stmt)
        seen_statements.append(rendered)
        lowered = rendered.lower()
        if "discover_interactions" not in lowered:
            return _result([])
        if "max(" in lowered:
            return _result(list(recent_rows))
        return _result([])

    session = AsyncMock()
    session.execute = AsyncMock(side_effect=mock_execute)
    session.rollback = AsyncMock()
    return session, seen_statements


async def _load(recent_rows):
    from app.routes.feed import _load_personalization_context

    session, statements = _recent_items_session(recent_rows)
    ctx = await _load_personalization_context(
        session, None, session_id=_SESSION_ID, config=None
    )
    return ctx, statements


def _row(item_type, item_id, action="unlike", name="Spanish Grand Prix Winner"):
    """One grouped recent-items row, in the loader's own column order."""
    return (
        item_type,
        item_id,
        action,
        datetime.now(timezone.utc) - timedelta(minutes=5),
        name,
        "motorsports",
    )


@pytest.mark.asyncio
async def test_the_real_loader_carries_a_native_concept_swipe_into_the_context():
    """The whole defect in one line, on Alex's own specimen.

    Pre-repair this row arrived labelled ``futures`` (layer 1's coercion) and
    died on the ``int()`` parse, so the set below was empty and the card was
    served again on the next build.
    """
    ctx, _ = await _load([_row("concept", _F1_KEY)])

    assert _F1_KEY in ctx.recent_dismissed_keys, (
        "a swiped concept card must reach the context; an empty set here means "
        "the card is served again on the very next feed build"
    )


@pytest.mark.asyncio
async def test_a_legacy_row_mislabelled_futures_is_still_honoured():
    """``discover_interactions`` is append-only.

    Every swipe Alex made before this repair is on disk labelled ``futures``
    with a key in ``item_id``. The loop decides row-id-vs-key by PARSING the id
    rather than by trusting the label, so those rows start working too — which
    is the difference between the fix helping him today and helping him after he
    swipes everything a second time.
    """
    ctx, _ = await _load([_row("futures", _F1_KEY)])

    assert _F1_KEY in ctx.recent_dismissed_keys
    assert ctx.recent_dismissed_futures_ids == set(), (
        "a key must never be counted as a futures row id"
    )


@pytest.mark.asyncio
async def test_a_web_grid_swipe_reaches_the_context_too():
    """Web labels the same card ``grid`` (``ConceptCard``'s ``contentType``).

    Layer 2: these rows were excluded by the query's own WHERE, so they never
    reached the loop no matter what the loop did.
    """
    ctx, _ = await _load([_row("grid", _VUELTA_KEY, name="Vuelta a España 2026")])

    assert _VUELTA_KEY in ctx.recent_dismissed_keys


@pytest.mark.asyncio
async def test_the_recent_items_query_asks_for_the_keyed_card_types():
    """Layer 2, asserted on the compiled statement rather than the source.

    The loop can be perfect and still see nothing if the WHERE never selects
    these rows — and a mock that returns rows regardless of WHERE cannot fail on
    that. So the query itself is the artifact under test here.
    """
    _, statements = await _load([])
    recent = [s for s in statements if "discover_interactions" in s and "max(" in s]
    assert recent, "the recent-items read did not run"
    compiled = recent[0].lower()
    for keyed_type in ("concept", "grid", "tournament", "bundle"):
        assert keyed_type in compiled, (
            f"the recent-items query does not select {keyed_type!r} rows, so a "
            f"swipe on that card type can never be read back"
        )


@pytest.mark.asyncio
async def test_a_numeric_dismissal_still_lands_in_its_own_set():
    """The control for the parse: rows are still rows.

    The repair replaced a ``continue`` with a branch. If that branch ever
    swallows the numeric path, every game and market dismissal silently stops
    working — a far bigger regression than the one being fixed.
    """
    ctx, _ = await _load([_row("futures", "4815162342")])

    assert 4815162342 in ctx.recent_dismissed_futures_ids
    assert ctx.recent_dismissed_keys == set()


@pytest.mark.asyncio
async def test_a_keyed_swipe_also_reaches_the_by_name_suppression():
    """The cost the ``continue`` hid.

    It discarded the row BEFORE the story-key and semantic-token work below it,
    so a dismissed concept was not even softly penalised by name. This is the
    half nobody would have noticed from the symptom.

    Asserted on the TOKENS rather than the story key: ``_story_key`` returns
    ``None`` for both of Alex's specimens (it fires for recognised story
    families, and "Spanish Grand Prix Winner" is not one), so a story-key
    assertion here would be pinning a coincidence of this name rather than the
    repair. The token set is what these rows actually contribute.
    """
    ctx, _ = await _load([_row("concept", _F1_KEY)])

    assert ctx.recent_dismissed_feature_token_sets, (
        "a keyed swipe must still feed the by-name suppression it used to skip"
    )
    assert "term:prix" in set().union(*ctx.recent_dismissed_feature_token_sets)


# ---------------------------------------------------------------------------
# The apply half, and its controls
# ---------------------------------------------------------------------------


def test_a_dismissed_concept_card_is_dropped_from_the_tier():
    ctx = PersonalizationContext(recent_dismissed_keys={_F1_KEY})
    items = [_card(_F1_KEY), _card(_VUELTA_KEY)]

    kept = _drop_dismissed_keyed_items(items, ctx=ctx, my_teams_only=False)

    assert [i["data"]["key"] for i in kept] == [_VUELTA_KEY]


def test_a_dismissed_tournament_card_is_dropped_from_the_tier():
    """Tournaments are keyed the same way and were broken the same way."""
    ctx = PersonalizationContext(recent_dismissed_keys={"the_open"})
    items = [_card("the_open", "tournament"), _card("3m_open", "tournament")]

    kept = _drop_dismissed_keyed_items(items, ctx=ctx, my_teams_only=False)

    assert [i["data"]["key"] for i in kept] == ["3m_open"]


def test_a_web_tournament_swipe_matches_on_the_name_it_actually_sends():
    """Web's tournament card sends the RAW NAME as ``itemId``, not the key.

    Deliberately, and it stays that way: that field doubles as the GA4 identity
    for those cards (``TournamentCard.tsx:108``). So the server matches both
    identities, or "swiped stays swiped" is false on exactly one surface and one
    card type — the kind of hole that reads as fixed and is not.
    """
    ctx = PersonalizationContext(recent_dismissed_keys={"The Open Championship"})
    items = [
        {"type": "tournament", "data": {"key": "the_open", "name": "The Open Championship"}},
        {"type": "tournament", "data": {"key": "3m_open", "name": "3M Open"}},
    ]

    kept = _drop_dismissed_keyed_items(items, ctx=ctx, my_teams_only=False)

    assert [i["data"]["key"] for i in kept] == ["3m_open"]


def test_a_card_nobody_swiped_survives():
    """#1091's lesson: the guard must not empty the tier."""
    ctx = PersonalizationContext(recent_dismissed_keys={"event:ufc:26aug23"})
    items = [_card(_F1_KEY), _card(_VUELTA_KEY)]

    kept = _drop_dismissed_keyed_items(items, ctx=ctx, my_teams_only=False)

    assert len(kept) == 2


def test_a_reader_with_no_swipes_gets_the_tier_back_untouched():
    """The identity case, and it is the common one — every anonymous reader."""
    items = [_card(_F1_KEY), _card(_VUELTA_KEY)]

    kept = _drop_dismissed_keyed_items(
        items, ctx=PersonalizationContext(), my_teams_only=False
    )

    assert kept is items, "the no-dismissal path should not rebuild the list"


def test_my_teams_only_is_exempt():
    """Matches both siblings: that surface is filtered by follows, not swipes."""
    ctx = PersonalizationContext(recent_dismissed_keys={_F1_KEY})
    items = [_card(_F1_KEY)]

    kept = _drop_dismissed_keyed_items(items, ctx=ctx, my_teams_only=True)

    assert len(kept) == 1


def test_an_item_with_no_key_is_never_dropped():
    """A malformed card is a rendering question, not a suppression one.

    Guards the `or ""` in the helper: an empty key must not collide with an
    empty-string entry a future writer could put in the set.
    """
    ctx = PersonalizationContext(recent_dismissed_keys={""})
    items = [{"type": "concept", "score": 50, "data": {}}, {"type": "concept"}]

    kept = _drop_dismissed_keyed_items(items, ctx=ctx, my_teams_only=False)

    assert len(kept) == 2
