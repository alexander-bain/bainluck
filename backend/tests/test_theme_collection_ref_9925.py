"""#9925 — a Discover theme card's `collection_ref`: the producer and its gates.

SHIP: tap "View collection" on a genuinely eligible Discover theme and open its
complete, automatically maintained page. Pillars DISCOVER / MATCHING / TRUTH.

The target is chosen by ``resolve_collection_target`` (contract §5 steps 0–3)
and only then checked (step 4). Every refusal arm below has a sibling that
emits, so a test cannot pass by refusing everything.
"""

from __future__ import annotations

import ast
import asyncio
import copy
import inspect
import textwrap
from contextlib import asynccontextmanager
from pathlib import Path

import pytest

from app.utils import theme_collection_ref as tcr
from app.utils import theme_definitions as td
from app.utils.feed_cache import feed_response_cache_key

AI_IDS = [61461524, 13791997, 5550001]
OSCAR_IDS = [6173044, 6173045]
AI_CID, OSCARS_CID, IPOS_CID = 10, 9, 11


# ---------------------------------------------------------------------------
# Doubles
# ---------------------------------------------------------------------------


class _Rows:
    def __init__(self, rows):
        self._rows = rows

    def fetchall(self):
        return list(self._rows)


class _Session:
    """Answers the two statements this module issues, by their SQL, and
    records every statement and whether a SAVEPOINT held it."""

    def __init__(self, *, published=(), edges=(), error=None, delay=0.0):
        self.published = list(published)
        self.edges = list(edges)
        self.error = error
        self.delay = delay
        self.statements = []
        self.in_savepoint = []
        self.rollbacks = 0
        self._nested = False

    @asynccontextmanager
    async def begin_nested(self):
        self._nested = True
        try:
            yield
        finally:
            self._nested = False

    async def execute(self, statement, params=None):
        self.statements.append((str(statement), params))
        self.in_savepoint.append(self._nested)
        if self.delay:
            await asyncio.sleep(self.delay)
        if self.error:
            raise self.error
        sql = str(statement)
        if "FROM event_edges" in sql:
            ids = set(params["ids"])
            return _Rows([r for r in self.edges if r[5] in ids])
        return _Rows(self.published)

    async def rollback(self):
        self.rollbacks += 1


def edge(cid, slug, child, *, pub="published", rev=18, name=None):
    return (cid, slug, name or {"ai": "AI", "oscars-2027": "Oscars 2027"}.get(slug, slug),
            pub, rev, child)


def snapshot(cid, slug, rev, shown, *, folded=(), withheld=None, complete=True):
    return {
        "container_id": cid, "slug": slug, "name": "x", "revision": rev,
        "inventory_complete": complete, "shown_ids": list(shown),
        "folded_ids": list(folded), "withheld": withheld or {"row_missing": []},
        "shown_count": len(shown), "eligible_count": len(shown) + len(folded),
    }


class _Snapshots:
    def __init__(self, store):
        self.store = store
        self.calls = []

    async def __call__(self, cid, rev):
        self.calls.append((cid, rev))
        return copy.deepcopy(self.store.get((cid, rev)))


def story_bundle(story_key, ids, *, bundle_id=None):
    return {
        "type": "bundle",
        "score": 50,
        "data": {
            "id": bundle_id or f"theme:{story_key}:{'-'.join(map(str, ids))}",
            "title": "AI", "kind": "theme", "story_key": story_key,
            "shared_question": "What happens next in AI?",
            "item_count": len(ids), "member_ids": list(ids),
            "items": [{"type": "futures", "data": {"id": i}} for i in ids],
            "debug_bundles": {"grouped_by": "story_key", "member_ids": list(ids)},
        },
    }


def awards_bundle(group_id, ids):
    return {
        "type": "bundle",
        "score": 40,
        "data": {
            "id": f"theme:{group_id}:{'-'.join(map(str, ids))}",
            "title": "Best Picture", "kind": "theme", "group_id": group_id,
            "shared_question": "Oscars 2027: Best Picture Winner",
            "item_count": len(ids), "member_ids": list(ids),
            "items": [{"type": "futures", "data": {"id": i}} for i in ids],
            "debug_bundles": {"grouped_by": "group_id", "member_ids": list(ids)},
        },
    }


def published(*pairs):
    slugs = {AI_CID: "ai", OSCARS_CID: "oscars-2027", IPOS_CID: "ipos"}
    return tcr.PublishedThemes(tuple(tcr.PublishedTheme(c, slugs[c], r) for c, r in pairs))


AI_EDGES = [edge(AI_CID, "ai", i) for i in AI_IDS]
OSCAR_EDGES = [edge(OSCARS_CID, "oscars-2027", i, rev=7) for i in OSCAR_IDS]
SNAPS = {
    (AI_CID, 18): snapshot(AI_CID, "ai", 18, [*AI_IDS, 777, 778]),
    (OSCARS_CID, 7): snapshot(OSCARS_CID, "oscars-2027", 7, [*OSCAR_IDS, 999]),
}


async def _attach(items, *, edges, pub, snaps=SNAPS, **kw):
    db = _Session(edges=edges)
    reader = _Snapshots(snaps)
    reports = []
    out = await tcr.attach_theme_collection_refs(
        db, items, published=pub, read_snapshot=reader, observe=reports.append, **kw
    )
    return out, (reports[0] if reports else None), db, reader


def ref_of(item):
    return item["data"].get("collection_ref")


def reason_of(item):
    return item["data"]["debug_bundles"][tcr.DEBUG_KEY]


# ---------------------------------------------------------------------------
# Eligible: AI (mapped story key) and Oscars (awards group, no map entry)
# ---------------------------------------------------------------------------


async def test_an_eligible_ai_theme_links_to_the_canonical_page_with_the_full_count():
    bundle = story_bundle("story:ai", AI_IDS)
    out, report, _, _ = await _attach(
        [bundle], edges=AI_EDGES, pub=published((AI_CID, 18))
    )
    assert ref_of(out[0]) == {
        "slug": "ai", "name": "AI", "revision": 18,
        # the page's shown_count, never the card's preview count
        "collection_count": 5,
    }
    assert out[0]["data"]["item_count"] == 3  # preview count is untouched
    assert out[0]["data"]["items"] == bundle["data"]["items"]
    assert report == {bundle["data"]["id"]: tcr.EMITTED}


async def test_an_eligible_awards_theme_links_to_its_edition():
    bundle = awards_bundle("polymarket:42", OSCAR_IDS)
    out, _, _, _ = await _attach(
        [bundle], edges=OSCAR_EDGES, pub=published((OSCARS_CID, 7))
    )
    assert ref_of(out[0]) == {
        "slug": "oscars-2027", "name": "Oscars 2027", "revision": 7, "collection_count": 3,
    }


async def test_the_name_is_the_containers_name_never_the_bundle_header():
    bundle = awards_bundle("polymarket:42", OSCAR_IDS)
    assert bundle["data"]["title"] == "Best Picture"
    out, _, _, _ = await _attach(
        [bundle], edges=OSCAR_EDGES, pub=published((OSCARS_CID, 7))
    )
    assert ref_of(out[0])["name"] == "Oscars 2027"


async def test_a_preview_member_the_page_folded_still_links():
    """R-5: shown ∪ folded — one question with two venues is not a refusal."""
    snaps = {(AI_CID, 18): snapshot(AI_CID, "ai", 18, AI_IDS[:2], folded=[AI_IDS[2]])}
    out, _, _, _ = await _attach(
        [story_bundle("story:ai", AI_IDS)], edges=AI_EDGES, pub=published((AI_CID, 18)),
        snaps=snaps,
    )
    assert ref_of(out[0])["collection_count"] == 2


# ---------------------------------------------------------------------------
# Steps 0–3: the target is determined, never searched for
# ---------------------------------------------------------------------------


async def test_a_mapped_key_whose_target_does_not_admit_the_preview_never_falls_back():
    """story:ai over Oscars members: oscars-2027 admits them and is published,
    but the map names ai, so there is no ref — never oscars-2027."""
    out, _, _, reader = await _attach(
        [story_bundle("story:ai", OSCAR_IDS)], edges=OSCAR_EDGES,
        pub=published((OSCARS_CID, 7)),
    )
    assert ref_of(out[0]) is None
    assert reason_of(out[0]) == td.MAPPED_TARGET_ABSENT
    assert reader.calls == []  # no step-4 read for a target that was never chosen


async def test_a_mapped_target_that_misses_one_preview_member_has_no_link():
    ids = [*AI_IDS, 4242]  # 4242 has no ai edge
    out, _, _, _ = await _attach(
        [story_bundle("story:ai", ids)], edges=AI_EDGES, pub=published((AI_CID, 18))
    )
    assert ref_of(out[0]) is None
    assert reason_of(out[0]) == td.MAPPED_TARGET_ABSENT


async def test_an_unmapped_key_admitted_by_two_containers_is_ambiguous():
    edges = [*AI_EDGES, *(edge(IPOS_CID, "ipos", i, rev=3) for i in AI_IDS)]
    out, _, _, _ = await _attach(
        [story_bundle("story:ipo_markets", AI_IDS)], edges=edges,
        pub=published((AI_CID, 18), (IPOS_CID, 3)),
    )
    assert ref_of(out[0]) is None
    assert reason_of(out[0]) == td.NO_MAP_ENTRY_AMBIGUOUS


async def test_a_prior_edition_awards_group_has_no_link():
    """KXOSCAR-26 members hold no theme_rule edge into oscars-2027."""
    last_year = [5100001, 5100002]
    out, _, _, _ = await _attach(
        [awards_bundle("polymarket:26", last_year)], edges=OSCAR_EDGES,
        pub=published((OSCARS_CID, 7)),
    )
    assert ref_of(out[0]) is None
    assert reason_of(out[0]) == td.PREVIEW_SPANS_COLLECTIONS


async def test_a_mixed_awards_group_has_no_link():
    out, _, _, _ = await _attach(
        [awards_bundle("polymarket:77", [OSCAR_IDS[0], 8800001])], edges=OSCAR_EDGES,
        pub=published((OSCARS_CID, 7)),
    )
    assert ref_of(out[0]) is None


async def test_swings_is_never_a_collection_even_when_every_member_is_ai():
    out, _, _, _ = await _attach(
        [story_bundle("swings", AI_IDS)], edges=AI_EDGES, pub=published((AI_CID, 18))
    )
    assert ref_of(out[0]) is None
    assert reason_of(out[0]) == td.SWINGS_NOT_A_COLLECTION


async def test_a_mapped_target_that_is_unpublished_never_redirects():
    """ipos unpublished, ai published, both admit the pack: no ref, never ai."""
    fmap = {"story:ipo_markets": "ipos"}
    reg = {**td.REGISTRY, "ipos": td.AI.__class__(**{**td.AI.__dict__, "subject": "ipos",
                                                        "feed_keys": ()})}
    edges = [*AI_EDGES, *(edge(IPOS_CID, "ipos", i, pub="unpublished", rev=3) for i in AI_IDS)]
    candidates = tcr.candidates_for(tcr.CandidateRow(*e) for e in edges)
    target, reason = td.resolve_collection_target(
        "story:ipo_markets", AI_IDS, [c for c, _ in candidates.values()],
        registry=reg, feed_key_map=fmap,
    )
    assert target.slug == "ipos" and reason is None
    # …and step 4 then removes it; it does not choose ai.
    out, _, _, _ = await _attach(
        [story_bundle("story:ipo_markets", AI_IDS)], edges=edges, pub=published((AI_CID, 18)),
    )
    assert ref_of(out[0]) is None


# ---------------------------------------------------------------------------
# Step 4 on the target only
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("state", ["unpublished", "withdrawn"])
async def test_an_unpublished_or_withdrawn_target_has_no_link(state):
    edges = [edge(AI_CID, "ai", i, pub=state) for i in AI_IDS]
    out, _, _, reader = await _attach(
        [story_bundle("story:ai", AI_IDS)], edges=edges, pub=published((OSCARS_CID, 7))
    )
    assert ref_of(out[0]) is None
    assert reason_of(out[0]) == tcr.TARGET_UNPUBLISHED
    assert reader.calls == []


async def test_a_target_without_a_registry_definition_has_no_link():
    """`oscars-2031` parses as a theme slug, but no definition assembles it, so
    nothing keeps that page complete."""
    edges = [edge(12, "oscars-2031", i, rev=1) for i in OSCAR_IDS]
    out, _, _, reader = await _attach(
        [awards_bundle("polymarket:42", OSCAR_IDS)], edges=edges,
        pub=published((OSCARS_CID, 7)),
    )
    assert ref_of(out[0]) is None
    assert reason_of(out[0]) == tcr.TARGET_NOT_MAINTAINED
    assert reader.calls == []


async def test_a_non_theme_container_is_never_a_target():
    edges = [edge(IPOS_CID, "ipos", i, rev=3) for i in AI_IDS]
    out, _, _, _ = await _attach(
        [story_bundle("story:unmapped", AI_IDS)], edges=edges, pub=published((AI_CID, 18)),
    )
    assert ref_of(out[0]) is None
    assert reason_of(out[0]) == td.TARGET_SLUG_NOT_THEME


async def test_a_revision_the_page_is_not_cached_under_has_no_link():
    """The published read (the cache key) says 17; the build reads 18."""
    out, _, _, reader = await _attach(
        [story_bundle("story:ai", AI_IDS)], edges=AI_EDGES, pub=published((AI_CID, 17))
    )
    assert ref_of(out[0]) is None
    assert reason_of(out[0]) == tcr.TARGET_REVISION_MOVED
    assert reader.calls == []


async def test_no_snapshot_at_the_live_revision_is_building_so_no_link():
    out, _, _, reader = await _attach(
        [story_bundle("story:ai", AI_IDS)], edges=AI_EDGES, pub=published((AI_CID, 18)),
        snaps={(AI_CID, 17): SNAPS[(AI_CID, 18)]},
    )
    assert ref_of(out[0]) is None
    assert reason_of(out[0]) == tcr.SNAPSHOT_STALE
    assert reader.calls == [(AI_CID, 18)]


async def test_a_partial_inventory_has_no_link():
    snaps = {(AI_CID, 18): snapshot(AI_CID, "ai", 18, AI_IDS, complete=False)}
    out, _, _, _ = await _attach(
        [story_bundle("story:ai", AI_IDS)], edges=AI_EDGES, pub=published((AI_CID, 18)),
        snaps=snaps,
    )
    assert reason_of(out[0]) == tcr.SNAPSHOT_PARTIAL and ref_of(out[0]) is None


async def test_a_withheld_preview_member_has_no_link():
    snaps = {(AI_CID, 18): snapshot(AI_CID, "ai", 18, AI_IDS[:2],
                                    withheld={"low_quality": [AI_IDS[2]]})}
    out, _, _, _ = await _attach(
        [story_bundle("story:ai", AI_IDS)], edges=AI_EDGES, pub=published((AI_CID, 18)),
        snaps=snaps,
    )
    assert reason_of(out[0]) == tcr.PREVIEW_MEMBER_WITHHELD and ref_of(out[0]) is None


async def test_a_preview_member_the_page_does_not_show_has_no_link():
    snaps = {(AI_CID, 18): snapshot(AI_CID, "ai", 18, AI_IDS[:2])}
    out, _, _, _ = await _attach(
        [story_bundle("story:ai", AI_IDS)], edges=AI_EDGES, pub=published((AI_CID, 18)),
        snaps=snaps,
    )
    assert reason_of(out[0]) == tcr.PREVIEW_MEMBER_NOT_ADMITTED and ref_of(out[0]) is None


@pytest.mark.parametrize(
    "mutate",
    [
        lambda s: s.update(slug="oscars-2027"),
        lambda s: s.update(folded_ids=["x"]),
        lambda s: s.update(folded_ids=None),
    ],
)
async def test_a_snapshot_that_does_not_describe_this_page_has_no_link(mutate):
    snap = snapshot(AI_CID, "ai", 18, AI_IDS)
    mutate(snap)
    out, _, _, _ = await _attach(
        [story_bundle("story:ai", AI_IDS)], edges=AI_EDGES, pub=published((AI_CID, 18)),
        snaps={(AI_CID, 18): snap},
    )
    assert reason_of(out[0]) == tcr.SNAPSHOT_STALE and ref_of(out[0]) is None


@pytest.mark.parametrize("ids", [[], [61461524, None], [61461524, "13791997"], [True]])
async def test_a_preview_without_integer_ids_has_no_link(ids):
    out, _, db, _ = await _attach(
        [story_bundle("story:ai", ids)], edges=AI_EDGES, pub=published((AI_CID, 18))
    )
    assert ref_of(out[0]) is None
    assert reason_of(out[0]) == tcr.PREVIEW_ID_INVALID


# ---------------------------------------------------------------------------
# Bounded, fail-closed, never mutating
# ---------------------------------------------------------------------------


async def test_nothing_published_means_no_read_and_the_same_list():
    items = [story_bundle("story:ai", AI_IDS)]
    for pub in (None, tcr.PublishedThemes()):
        out, report, db, reader = await _attach(items, edges=AI_EDGES, pub=pub)
        assert out is items and report is None
        assert db.statements == [] and reader.calls == []


async def test_a_deck_without_theme_bundles_or_budget_performs_no_read():
    plain = [{"type": "futures", "data": {"id": 1}},
             {"type": "bundle", "data": {"kind": "comparison", "member_ids": AI_IDS}}]
    out, _, db, _ = await _attach(plain, edges=AI_EDGES, pub=published((AI_CID, 18)))
    assert out is plain and db.statements == []
    items = [story_bundle("story:ai", AI_IDS)]
    out, _, db, _ = await _attach(
        items, edges=AI_EDGES, pub=published((AI_CID, 18)), budget_seconds=0
    )
    assert out is items and db.statements == []


async def test_one_statement_keyed_by_the_page_preview_ids_and_one_snapshot_per_target():
    items = [
        {"type": "futures", "data": {"id": 31337}},
        story_bundle("story:ai", AI_IDS, bundle_id="a"),
        story_bundle("story:ai", AI_IDS[:2], bundle_id="b"),
        awards_bundle("polymarket:42", OSCAR_IDS),
    ]
    out, report, db, reader = await _attach(
        items, edges=[*AI_EDGES, *OSCAR_EDGES],
        pub=published((AI_CID, 18), (OSCARS_CID, 7)),
    )
    (sql, params), = db.statements
    assert "FROM event_edges" in sql and "child_id = ANY(:ids)" in sql
    assert params == {"ids": sorted({*AI_IDS, *OSCAR_IDS}), "source": "theme_rule"}
    assert "31337" not in str(params)  # a non-bundle card is never read
    assert sorted(reader.calls) == [(OSCARS_CID, 7), (AI_CID, 18)]
    assert set(report.values()) == {tcr.EMITTED}
    assert out[0] is items[0]


async def test_the_input_deck_is_never_mutated():
    items = [story_bundle("story:ai", AI_IDS)]
    before = copy.deepcopy(items)
    out, _, _, _ = await _attach(items, edges=AI_EDGES, pub=published((AI_CID, 18)))
    assert ref_of(out[0]) is not None
    assert items == before and "collection_ref" not in items[0]["data"]


async def test_a_stale_ref_on_an_input_bundle_is_removed_when_not_reconfirmed():
    item = story_bundle("story:ai", AI_IDS)
    item["data"]["collection_ref"] = {"slug": "ai", "revision": 3}
    out, _, _, _ = await _attach(
        [item], edges=[edge(AI_CID, "ai", i, pub="withdrawn") for i in AI_IDS],
        pub=published((OSCARS_CID, 7)),
    )
    assert "collection_ref" not in out[0]["data"]


@pytest.mark.parametrize("failure", ["error", "timeout"])
async def test_a_failed_or_slow_read_keeps_every_card_without_a_link(failure):
    db = (
        _Session(edges=AI_EDGES, error=RuntimeError("boom")) if failure == "error"
        else _Session(edges=AI_EDGES, delay=1.0)
    )
    items = [story_bundle("story:ai", AI_IDS)]
    out = await tcr.attach_theme_collection_refs(
        db, items, published=published((AI_CID, 18)), budget_seconds=0.05,
        read_snapshot=_Snapshots(SNAPS),
    )
    assert ref_of(out[0]) is None and reason_of(out[0]) == tcr.READ_FAILED
    assert db.rollbacks == 1
    assert out[0]["data"]["items"] == items[0]["data"]["items"]


# ---------------------------------------------------------------------------
# Published read + the cache key (publication/revision changes invalidate)
# ---------------------------------------------------------------------------


async def test_the_published_read_is_one_savepointed_statement_over_registry_slugs():
    tcr._reset_published_cache_for_tests()
    db = _Session(published=[(AI_CID, "ai", 18)])
    got = await tcr.read_published_themes(db)
    assert got == tcr.PublishedThemes((tcr.PublishedTheme(AI_CID, "ai", 18),))
    (sql, params), = db.statements
    assert db.in_savepoint == [True]
    assert "publication_state = :published" in sql and "membership_revision" in sql
    assert params == {"published": "published", "slugs": sorted(td.REGISTRY)}


async def test_a_failed_published_read_means_no_cache_and_no_links():
    tcr._reset_published_cache_for_tests()
    db = _Session(error=RuntimeError('column "publication_state" does not exist'))
    assert await tcr.read_published_themes(db) is None
    assert tcr.compose_collections_fingerprint("abc", None) == "abc"


async def test_the_published_read_is_reused_for_at_most_five_seconds():
    tcr._reset_published_cache_for_tests()
    first = _Session(published=[(AI_CID, "ai", 18)])
    await tcr.read_published_themes(first, max_age_seconds=60)
    second = _Session(published=[(AI_CID, "ai", 19)])
    assert (await tcr.read_published_themes(second, max_age_seconds=5)).revision_of(AI_CID) == 18
    assert second.statements == []
    third = _Session(published=[(AI_CID, "ai", 19)])
    assert (await tcr.read_published_themes(third, max_age_seconds=0)).revision_of(AI_CID) == 19
    tcr._reset_published_cache_for_tests()


@pytest.mark.parametrize("collections", [None, "f00d"])
def test_nothing_published_keeps_the_cache_key_byte_identical(collections):
    for pub in (None, tcr.PublishedThemes()):
        assert tcr.compose_collections_fingerprint(collections, pub) == collections
    base = dict(limit=20, offset=0, event_pct=0.15)
    assert feed_response_cache_key(
        **base, collections=tcr.compose_collections_fingerprint(collections, tcr.PublishedThemes())
    ) == feed_response_cache_key(**base, collections=collections)


def test_every_publication_or_revision_change_is_a_different_cache_key():
    base = dict(limit=20, offset=0, event_pct=0.15)
    states = [
        tcr.PublishedThemes(),
        published((AI_CID, 18)),
        published((AI_CID, 19)),                    # assembly / correction bump
        published((AI_CID, 19), (OSCARS_CID, 7)),   # a second publish
        published((OSCARS_CID, 7)),                 # ai withdrawn
    ]
    keys = {
        feed_response_cache_key(
            **base, collections=tcr.compose_collections_fingerprint(c, s)
        )
        for s in states for c in (None, "f00d")
    }
    assert len(keys) == len(states) * 2


def test_enabled_only_on_discover_with_futures_while_the_reader_serves(monkeypatch):
    monkeypatch.setenv("CONTAINERS_READ_ENABLED", "true")
    assert tcr.theme_collection_refs_enabled(mode=None, include_futures=True)
    assert tcr.theme_collection_refs_enabled(mode="discover", include_futures=True)
    assert not tcr.theme_collection_refs_enabled(mode="sports", include_futures=True)
    assert not tcr.theme_collection_refs_enabled(mode=None, include_futures=False)
    monkeypatch.setenv("CONTAINERS_READ_ENABLED", "false")
    assert not tcr.theme_collection_refs_enabled(mode=None, include_futures=True)


# ---------------------------------------------------------------------------
# The route mount (structure the unit doubles cannot see)
# ---------------------------------------------------------------------------

FEED = Path(__file__).resolve().parents[1] / "app" / "routes" / "feed.py"


def _get_feed_source() -> str:
    from app.routes import feed

    return textwrap.dedent(inspect.getsource(feed.get_feed))


def test_the_mount_runs_on_the_full_deck_before_the_pin_and_the_slice():
    """After the hub cards are placed, before the build's pin/seating takes its
    bodies (`_served_items = feed_items`), before the edition token, and before
    the page base stores the deck every later page is cut from."""
    src = _get_feed_source()
    attach = src.index("attach_theme_collection_refs(\n")
    assert src.count("attach_theme_collection_refs(\n") == 1
    assert src.index("await add_feed_collections(") < attach
    assert attach < src.index("_served_items = feed_items")
    assert attach < src.rindex("feed_edition_token(feed_items")
    assert attach < src.index('_page_base_body["items"] = feed_items')


def test_the_cache_key_and_the_cache_gate_carry_the_published_themes():
    src = _get_feed_source()
    at = src.index("_cache_shape = dict(")
    shape = src[at: src.index(")", at)]
    assert "collections=_collections_key," in shape
    gate = src[:at]
    assert (
        "_collections_key = compose_collections_fingerprint(\n"
        "            _collections_fingerprint, _published_themes\n"
        "        )"
    ) in gate
    assert "(not _theme_refs_enabled or _published_themes is not None)" in gate


def test_the_route_never_imports_the_producer_or_calls_an_llm_here():
    tree = ast.parse(Path(tcr.__file__).read_text())
    imported = {
        (n.module or "") for n in ast.walk(tree) if isinstance(n, ast.ImportFrom)
    } | {a.name for n in ast.walk(tree) if isinstance(n, ast.Import) for a in n.names}
    assert not any("theme_assembly" in m or "openai" in m or "llm" in m for m in imported)
