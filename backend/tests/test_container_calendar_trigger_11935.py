"""#11935: a dated definition changes both presentations without a release.

The CFP successor and Awards Season's ceremony definitions ride this calendar
trigger. These fixtures exercise the real field_band kind; they do not claim
that the post-selection CFP rows or Awards Season reader have shipped.
"""

from copy import deepcopy
from datetime import datetime
from unittest.mock import Mock

import pytest

from app.utils.field_band import CFP_PICTURE_DEFINITION, build_field_band_producer
from app.utils.roundup_containers import (
    evaluate_roundup_producer,
    reset_roundup_cache_for_tests,
)
from tests.test_field_band import _make_cfp_qualifiers_market, _make_cfp_title_market


def _dated_picture(slug, **window):
    definition = deepcopy(CFP_PICTURE_DEFINITION)
    definition["slug"] = slug
    definition["rule"].update(window)
    loader = Mock(
        return_value=(
            {227: _make_cfp_qualifiers_market(), 181: _make_cfp_title_market()},
            {},
        )
    )
    return build_field_band_producer(definition, load_markets=loader), loader


async def test_a_calendar_boundary_replaces_both_presentations_even_with_a_warm_cache(
    monkeypatch,
):
    monkeypatch.setenv("CONTAINERS_READ_CACHE_ENABLED", "true")
    reset_roundup_cache_for_tests()
    boundary = "2026-12-06T00:00:00-08:00"  # test boundary, not a ceremony time
    stamp = datetime.fromisoformat(boundary).timestamp()
    before, load_before = _dated_picture(
        "roundup-cfp-before-fixture", valid_until=boundary
    )
    after, load_after = _dated_picture("roundup-cfp-after-fixture", valid_from=boundary)
    db = object()
    old_card, old_page = await evaluate_roundup_producer(before, db, now=stamp - 1)
    assert old_card["data"]["collection_ref"]["slug"] == old_page["slug"] == before.slug
    assert await evaluate_roundup_producer(after, db, now=stamp - 1) == (None, None)
    load_after.assert_not_called()
    # The old entry is cached and only one second old, but neither rendering
    # can return it after the definition's reviewed end instant.
    assert await evaluate_roundup_producer(before, db, now=stamp) == (None, None)
    load_before.assert_called_once()
    new_card, new_page = await evaluate_roundup_producer(after, db, now=stamp)
    assert new_card["data"]["collection_ref"]["slug"] == new_page["slug"] == after.slug
    assert new_page["member_count"] == old_page["member_count"]
    load_after.assert_called_once()
    reset_roundup_cache_for_tests()


@pytest.mark.parametrize(
    "window",
    [
        {"valid_from": "2026-12-06"},
        {"valid_until": "2026-12-06T00:00:00"},
        {"valid_from": 20261206},
        {"valid_from": "2026-12-07T00:00:00Z", "valid_until": "2026-12-06T00:00:00Z"},
        {"valid_from": "2026-12-06T00:00:00Z", "valid_until": "2026-12-06T00:00:00Z"},
    ],
)
def test_an_ambiguous_or_inverted_calendar_parameter_cannot_publish(window):
    with pytest.raises(ValueError):
        _dated_picture("roundup-cfp-bad-window", **window)


async def test_existing_undated_kinds_keep_the_same_members():
    producer, loader = _dated_picture("roundup-cfp-undated-fixture")
    card, page = await evaluate_roundup_producer(producer, [], now=0)
    assert card["data"]["collection_ref"]["slug"] == page["slug"] == producer.slug
    loader.assert_called_once()
