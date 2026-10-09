"""Public probability-source serialization shared by detail and folded SSE quotes."""


def format_probability_sources(sources: dict) -> dict:
    from app.config.win_prob_sources import WIN_PROB_SOURCES
    from app.utils.aggregation import parse_source_entry
    from app.utils.probability_eligibility import (
        from_entry as _eligibility_of,
        grade_entry as _grade_entry,
        is_refused as _is_refused,
    )
    wp_sources = {}
    for src_key, src_value in sources.items():
        if src_key.startswith("_"):
            continue
        # #1829: `value` stays a bare NUMBER on the wire. The column
        # now holds `{"value": x, "updated_at": ...}`, and assigning
        # the raw entry here would double-nest it —
        # `{"value": {"value": x, ...}}` — silently breaking every
        # reader that does `sources[k].value` (web Models page, the
        # #1640 untraded-placeholder suppression) and hard-failing
        # the iOS decoder. The write time is exposed as a SIBLING,
        # never inside `value`.
        numeric, updated_at = parse_source_entry(src_value)
        # #4120 — AND THE `else src_value` FALLBACK BELOW WAS DOING
        # EXACTLY WHAT THE PARAGRAPH ABOVE FORBIDS.
        #
        # `parse_source_entry` returns None for anything that is not
        # a number or a `{"value": number}` wrapper, and this line
        # then shipped the RAW entry. This column is a grab-bag:
        # `statpal_injuries` is an ARRAY of injury dicts (89 events)
        # and `statpal_injuries_updated` is an ISO STRING (89), so
        # both went onto the wire as a "source" whose probability was
        # an array or a date, labelled with their own snake_case key.
        #
        # For iOS that is not cosmetic, it is fatal, and the comment
        # above predicted it. `WinProbValue` accepts Double or String
        # and THROWS on anything else; `decodeIfPresent` only swallows
        # an ABSENT key, so a present-but-wrong-type value propagates
        # out through `[String: WinProbSource]` and fails the whole
        # `EventDetail`. Reproduced against the shipped model
        # definitions: the served payload for event 15296356 throws
        # `typeMismatch at winProbabilitySources.statpal_injuries.value`
        # and the same payload minus that entry decodes. **The iOS
        # event page could not render those 89 events at all.**
        #
        # So the gate is the SHAPE, not the key. `betting_book_count`
        # is numeric and stays on the wire deliberately: it is not a
        # source, but iOS consumes it to label the sportsbook row
        # "Sportsbooks (14)" (`WinProbSourceCatalog`), and both
        # clients already keep it out of their source LISTS with
        # their own allowlists (`PROBABILITY_SOURCE_KEYS` #3914,
        # `realSourceKeys`). Filtering it here would silently take
        # that count away from the app.
        if numeric is None:
            continue
        # CU-4 (#5311): a reading the hero REFUSED must not be served
        # as a source row. This loop reads the JSONB directly rather
        # than through `_tier1_readings`, so without this the two
        # halves of one screen would disagree — the hero computed
        # without the entry while the source list printed it, with a
        # number nothing on the page stands behind. That is the
        # ticket's own "one screen fixes the failure while another
        # reintroduces it", inside a single response.
        if _is_refused(src_value):
            continue
        source_config = WIN_PROB_SOURCES.get(src_key, {})
        wp_sources[src_key] = {
            "value": numeric,
            "display_name": source_config.get("display_name", src_key),
            "type": source_config.get("source_type", "model"),
            "color": source_config.get("color", "#6b7280"),
        }
        if updated_at is not None:
            wp_sources[src_key]["updated_at"] = updated_at.isoformat()
        # The additive eligibility fields. SIBLINGS of `value`, never
        # inside it, for the reason the #1829/#4120 paragraphs above
        # spell out: iOS `WinProbValue` throws on an unexpected type
        # inside `value`, while an unknown sibling key is ignored by
        # every Swift `Decodable` struct — which is exactly how
        # `updated_at` was added safely.
        #
        # `evidence_status` is emitted for EVERY source, including
        # the five that can never carry a record. An absent key would
        # be ambiguous between "this server predates CU-4" and "this
        # source is not applicable", and collapsing those is how a
        # census counts a deployment gap as a clean result.
        wp_sources[src_key]["evidence_status"] = _grade_entry(
            src_key, src_value
        )
        _record = _eligibility_of(src_value)
        if _record is not None:
            if _record.scope:
                wp_sources[src_key]["verified_scope"] = _record.scope
            if _record.rule:
                wp_sources[src_key]["contract_version"] = _record.rule
    return wp_sources
