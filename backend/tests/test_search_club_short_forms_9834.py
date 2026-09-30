"""A CLUB'S SHORT FORM FINDS THE CLUB. #9834.

Production web `018f0217`, 2026-09-30 ~13:30Z, `/api/events/search`:

    query          teams               games   markets
    man utd        0                   0       0
    man u          0                   0       7   (row 1: a Le Mans Europa League market)
    man united     Manchester United   7       0
    man city       Manchester City     7       0
    bvb            0                   0       0

`manchester united`, `manchester city` and `borussia dortmund` each serve the team,
their games and 10 markets. The short form shares no word with any name a rail
matches (or only `united`/`city`, which dozens of clubs share), so the fix rewrites
the query's IDENTITY — the string every rail reads — and leaves `q`, which is echoed
and logged, as the reader typed it.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.config.team_aliases import CLUB_QUERY_SHORT_FORMS, expand_club_short_forms
from app.routes import events as ev


@pytest.mark.parametrize(
    "typed, club",
    [
        ("man utd", "Manchester United"),
        ("man united", "Manchester United"),
        ("man u", "Manchester United"),
        ("man city", "Manchester City"),
        ("bvb", "Borussia Dortmund"),
        ("Man Utd", "Manchester United"),
        ("BVB", "Borussia Dortmund"),
    ],
)
def test_each_short_form_reads_as_the_clubs_full_name(typed, club) -> None:
    assert expand_club_short_forms(typed) == club


def test_the_surrounding_words_are_kept() -> None:
    assert expand_club_short_forms("man utd today") == "Manchester United today"
    assert expand_club_short_forms("bvb vs bayern") == "Borussia Dortmund vs bayern"
    assert (
        expand_club_short_forms("man city vs man utd")
        == "Manchester City vs Manchester United"
    )


def test_the_longest_span_wins() -> None:
    """`man united` must not read as `man u` + `nited`: whole words, longest first."""
    assert expand_club_short_forms("man united today") == "Manchester United today"


@pytest.mark.parametrize("typed", ["man", "manu", "batman u", "human city", "bvbx", "liverpool"])
def test_a_substring_or_a_lone_word_is_not_a_short_form(typed) -> None:
    assert expand_club_short_forms(typed) == typed


def test_a_query_with_no_short_form_is_returned_untouched() -> None:
    """The overwhelmingly common path: the SAME string, whitespace and all."""
    for typed in ("  red sox ", "patriots playoffs", "lazio today"):
        assert expand_club_short_forms(typed) is typed


def test_every_short_form_is_lowercase_whole_words() -> None:
    """The lookup lowercases the reader's words, so an entry with a capital or a
    space inside one word could never fire."""
    for key in CLUB_QUERY_SHORT_FORMS:
        assert all(word == word.lower() and " " not in word for word in key), key


# ---------------------------------------------------------------------------
# THE ROUTES — driven, with every bound value recorded.
# ---------------------------------------------------------------------------


def _bound_values(stmt) -> list[str]:
    try:
        params = stmt.compile().params
    except Exception:
        return []
    return [str(v).lower() for v in params.values() if isinstance(v, str)]


def _recording_db(seen: list[tuple[str, list[str]]]):
    db = AsyncMock()

    def empty():
        r = MagicMock()
        r.scalars.return_value.all.return_value = []
        r.fetchall.return_value = []
        r.all.return_value = []
        r.scalar.return_value = 0
        r.scalar_one_or_none.return_value = None
        r.first.return_value = None
        r.mappings.return_value.all.return_value = []
        return r

    async def execute(stmt, *a, **k):
        seen.append((str(stmt).lower(), _bound_values(stmt)))
        return empty()

    db.execute = AsyncMock(side_effect=execute)
    return db


async def _search(q: str, seen: list) -> dict:
    rc = MagicMock()
    rc.get.return_value = None  # a cache miss, so the route does the work
    with (
        patch("app.tasks.redis_state.get_redis_client", return_value=rc),
        patch("app.routes.events._load_gei_percentiles", new=AsyncMock(return_value={})),
        patch("app.routes.events._build_team_lookup", new=AsyncMock(return_value={})),
        patch(
            "app.routes.events.folded_probability_sources_batch",
            new=AsyncMock(return_value={}),
        ),
        patch("app.routes.events._record_trending", new=MagicMock()),
    ):
        return await ev.search_events(
            request=MagicMock(),
            response=MagicMock(),
            q=q,
            db=_recording_db(seen),
            sport=None,
            tags=None,
            page=1,
            per_page=25,
            days_back=30,
            include_upcoming=True,
            debug_timing=False,
            current_user=None,
        )


def _tables_asked_for(seen, needle: str) -> set[str]:
    """Which of the three rails bound `needle` into a statement."""
    rails = {"teams": "from teams", "events": "from events", "futures": "futures_markets"}
    return {
        rail
        for rail, marker in rails.items()
        for sql, values in seen
        if marker in sql and any(needle in v for v in values)
    }


@pytest.mark.asyncio
async def test_search_asks_every_rail_for_the_club_and_echoes_what_was_typed() -> None:
    seen: list = []
    payload = await _search("man utd", seen)
    assert payload["query"] == "man utd", "`q` is echoed as typed, never rewritten"
    assert _tables_asked_for(seen, "manchester") == {"teams", "events", "futures"}
    assert _tables_asked_for(seen, "utd") == set()


@pytest.mark.asyncio
async def test_search_without_the_rewrite_never_asks_for_the_club(monkeypatch) -> None:
    """The control: the same route with the rewrite made a no-op binds no
    `manchester` anywhere — so the test above measures the rewrite, not the rig."""
    monkeypatch.setattr(ev, "expand_club_short_forms", lambda text: text)
    seen: list = []
    await _search("man utd", seen)
    assert _tables_asked_for(seen, "manchester") == set()
    assert _tables_asked_for(seen, "utd"), "the control must still have run the rails"


async def _typeahead(q: str, seen: list):
    rc = MagicMock()
    rc.get.return_value = None
    request = MagicMock()
    request.headers = {}
    with (
        patch("app.tasks.redis_state.get_redis_client", return_value=rc),
        patch("app.routes.events._record_trending", new=MagicMock()),
    ):
        try:
            return await ev.typeahead_search(
                q=q,
                debug_evidence=False,
                debug_timing=False,
                db=_recording_db(seen),
                request=request,
            )
        except Exception:  # a MagicMock row late in the build; the recall ran first
            return None


@pytest.mark.asyncio
async def test_typeahead_asks_for_the_club_too() -> None:
    seen: list = []
    await _typeahead("man utd", seen)
    asked = _tables_asked_for(seen, "manchester")
    assert {"teams", "events"} <= asked, asked
    # Two readers keep the raw query on purpose, and neither decides which rows
    # exist: the "did you mean" fallback (`similarity(...)`, which fires only when
    # nothing matched — always on this empty rig, never on production once the
    # club is found) and the futures pool's prefix ORDER key (`… & utd:*`, which
    # the route documents as reading the raw query). Every RECALL arm reads the
    # club's name.
    recall = [
        (sql, [v for v in values if not v.endswith(":*")])
        for sql, values in seen
        if "similarity(" not in sql
    ]
    assert _tables_asked_for(recall, "utd") == set()


@pytest.mark.asyncio
async def test_typeahead_without_the_rewrite_never_asks_for_the_club(monkeypatch) -> None:
    monkeypatch.setattr(ev, "expand_club_short_forms", lambda text: text)
    seen: list = []
    await _typeahead("man utd", seen)
    assert _tables_asked_for(seen, "manchester") == set()
    assert _tables_asked_for(seen, "utd"), "the control must still have run the rails"
