"""The static tag filter must reach SQL, on both candidate sides, correctly bound.

## The defect

`/api/feed?tags=["sport:soccer"]` served **zero** events and **zero** futures for
every static tag in every namespace (`sport:`, `tier:`, `source:`), while the
identical predicate typed by hand returned 1,719 rows. The cause was a
double-encoded JSONB bind — see `tests/test_jsonb_containment_bind.py` and
`app/utils/jsonb_containment` for the mechanism.

Reader cost: all 29 `/categories/<slug>` pages were empty under a `/categories`
index card advertising up to 9,191 markets for the same tag, and the
"More Like This" section never rendered on any event or futures detail page.

## Why this file exists SEPARATELY from the bind guard

The bind guard is a pure-lib test of a helper. It stays perfectly green if
somebody deletes the two call sites that USE the helper — at which point the
filter silently stops being applied at all and the feed goes back to ignoring
`tags`. So this file asserts the predicate is present in the statements the
production builders actually produce, and that its bind still round-trips.

`_discover_candidate_pool_specs` is the single source of truth for the futures
pools (the production builder and the admin trace both read it), and
`_score_events` is driven here through a recording session double, so both arms
sit on the real code path rather than on a restatement of it.

The real-Postgres half — proving rows actually come back — is
`tests/integration/test_feed_static_tag_filter_pg.py`.
"""

import json
from datetime import datetime, timezone

import pytest
from sqlalchemy.dialects.postgresql import asyncpg as pg_asyncpg

import app.routes.feed as feed_mod

NOW = datetime(2026, 8, 29, 12, 0, tzinfo=timezone.utc)
DIALECT = pg_asyncpg.dialect()


def _wire_binds(statement):
    """Post-bind-processor values for a statement, as asyncpg would send them."""
    compiled = statement.compile(dialect=DIALECT)
    out = []
    for key, bindparam in compiled.binds.items():
        value = compiled.params.get(key)
        if value is None:
            continue
        processor = bindparam.type.bind_processor(DIALECT)
        out.append(processor(value) if processor else value)
    return out


def _tag_arrays(statement):
    """Every bind on `statement` that arrives as a JSON array of tag strings."""
    found = []
    for value in _wire_binds(statement):
        if not isinstance(value, str) or not value.startswith("["):
            continue
        try:
            parsed = json.loads(value)
        except ValueError:
            continue
        if isinstance(parsed, list) and all(isinstance(x, str) for x in parsed):
            found.append(parsed)
    return found


class TestTheFuturesPoolsCarryTheTagFilter:
    def test_every_pool_query_contains_the_containment_predicate(self):
        _filters, specs = feed_mod._discover_candidate_pool_specs(
            NOW, None, ["sport:soccer"]
        )
        assert specs, "the builder must produce pools to guard"
        for name, query, _limit in specs:
            sql = str(query.compile(dialect=DIALECT))
            assert "market_tags" in sql and "@>" in sql, (
                f"pool {name!r} lost the static tag filter — a tag-filtered feed "
                f"request would serve that pool unfiltered"
            )

    def test_the_bind_arrives_as_an_array_not_a_string(self):
        _filters, specs = feed_mod._discover_candidate_pool_specs(
            NOW, None, ["sport:soccer"]
        )
        for name, query, _limit in specs:
            arrays = _tag_arrays(query)
            assert ["sport:soccer"] in arrays, (
                f"pool {name!r} does not send the tag filter as a JSON array — "
                f"this is the double-encoding defect. Wire values: "
                f"{_wire_binds(query)}"
            )

    @pytest.mark.parametrize(
        "tags",
        [
            ["sport:soccer"],
            ["sport:politics"],
            ["tier:1"],
            ["source:kalshi"],
            ["sport:soccer", "tier:1"],
        ],
    )
    def test_it_holds_for_every_static_namespace(self, tags):
        _filters, specs = feed_mod._discover_candidate_pool_specs(NOW, None, tags)
        for _name, query, _limit in specs:
            assert tags in _tag_arrays(query)

    def test_no_tag_filter_means_no_containment_predicate(self):
        """The other direction: an unfiltered request must not be narrowed."""
        _filters, specs = feed_mod._discover_candidate_pool_specs(NOW, None, None)
        for name, query, _limit in specs:
            sql = str(query.compile(dialect=DIALECT))
            # `@>` is the containment operator and nothing else on this path
            # uses it, so its absence is the precise statement of "unfiltered".
            # (`market_tags` alone would be too loose the day a pool selects the
            # whole row rather than the id.)
            assert "@>" not in sql, (
                f"pool {name!r} applies a tag predicate with no tag filter"
            )


class _RecordingResult:
    def scalars(self):
        return self

    def all(self):
        return []

    def first(self):
        return None

    def __iter__(self):
        return iter(())


class _RecordingSession:
    """Captures the statements `_score_events` builds, then starves it out."""

    def __init__(self):
        self.statements = []

    async def execute(self, statement, *args, **kwargs):
        self.statements.append(statement)
        return _RecordingResult()


class TestTheEventCandidateQueryCarriesTheTagFilter:
    @pytest.mark.asyncio
    async def test_the_event_query_contains_a_correctly_bound_containment(self):
        db = _RecordingSession()
        ctx = feed_mod.PersonalizationContext()
        await feed_mod._score_events(
            db, NOW, None, ctx, static_tag_filter=["sport:soccer"]
        )
        assert db.statements, "_score_events issued no statement to inspect"
        tagged = [
            s
            for s in db.statements
            if "event_tags" in str(s.compile(dialect=DIALECT)) and "@>" in str(
                s.compile(dialect=DIALECT)
            )
        ]
        assert tagged, (
            "the event candidate query lost its static tag filter — a "
            "tag-filtered feed request would score every event"
        )
        assert any(["sport:soccer"] in _tag_arrays(s) for s in tagged), (
            "the event tag filter is not bound as a JSON array — this is the "
            "double-encoding defect"
        )

    @pytest.mark.asyncio
    async def test_no_tag_filter_leaves_the_event_query_unnarrowed(self):
        db = _RecordingSession()
        ctx = feed_mod.PersonalizationContext()
        await feed_mod._score_events(db, NOW, None, ctx, static_tag_filter=None)
        assert db.statements
        for statement in db.statements:
            # `event_tags` is a selected COLUMN on every one of these
            # statements, so its presence says nothing. The containment
            # operator is the predicate.
            assert "@>" not in str(statement.compile(dialect=DIALECT))
