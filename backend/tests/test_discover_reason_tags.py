from app.utils.discover_reason_tags import canonical_reason_tag, canonical_reason_tags


def test_canonical_reason_tags_maps_legacy_aliases_and_dedupes():
    assert canonical_reason_tags("fun,needs-context,duplicate,fun") == [
        "fun_or_weird",
        "unclear",
        "duplicate",
    ]


def test_canonical_reason_tags_preserves_unknown_experimental_tags():
    assert canonical_reason_tag("Interesting If Fixed") == "interesting_if_fixed"
