"""#11935: ceremony instances are discovered, never a typed seasonal roster."""

from copy import deepcopy

import pytest

from app.utils.awards_occasion_finder import (
    find_awards_occasions,
    select_awards_occasion,
)


def event(ticker="KXGGNOM-SCR26", label="84th Golden Globe Awards", **extra):
    return {
        "provider": "kalshi",
        "event_ticker": ticker,
        "title": "Golden Globe Nominations: Best Screenplay",
        "markets": [
            {
                "rules_primary": f"If The Odyssey is on the list of nominees for Best Screenplay at the {label}, then the market resolves to Yes."
            }
        ],
        **extra,
    }


def test_a_venue_listing_finds_its_ceremony_with_unknown_schedule_and_completion():
    # The primary rule is from KXGGNOM-SCR26, read Nov 6. Its stored deadline
    # and ticker suffix do not name the ceremony's year or date.
    result = find_awards_occasions([event(close_time="2027-12-08T15:00:00Z")])
    (occasion,) = result.occasions
    assert occasion.label == "84th Golden Globe Awards"
    assert occasion.ceremony_date is None and occasion.completed_at is None
    assert (occasion.relation, occasion.level, occasion.state) == (
        "same_event",
        "member",
        "proposed",
    )
    assert occasion.trigger == "market_availability"
    assert result.refused == ()


def test_a_new_category_joins_a_reproducible_selector_without_editing_it():
    first = event()
    original = find_awards_occasions([first]).occasions[0]
    selector = original.selector
    second = event("KXGGNOM-DIR26")
    updated = select_awards_occasion(selector, [second, first])
    assert updated.selector == selector
    assert [(member.provider, member.event_id) for member in updated.events] == [
        ("kalshi", "KXGGNOM-DIR26"),
        ("kalshi", "KXGGNOM-SCR26"),
    ]
    assert select_awards_occasion(selector, [first, second]) == updated
    assert select_awards_occasion(selector, [second]).events == (updated.events[0],)


def test_a_ceremony_never_listed_in_code_is_found_the_same_way():
    result = find_awards_occasions([event("KXNEW-PIC42", "17th New Film Awards")])
    assert result.occasions[0].label == "17th New Film Awards"
    assert result.occasions[0].selector["label"] == "17th New Film Awards"


def test_different_editions_and_different_ceremonies_stay_separate():
    events = [
        event(),
        event("KXGGNOM-SCR27", "85th Golden Globe Awards"),
        event("KXOTHER-PIC26", "84th Other Film Awards"),
    ]
    assert len(find_awards_occasions(events).occasions) == 3


def test_provider_events_establish_membership_without_claiming_equivalent_markets():
    other = event(provider="polymarket", id="12345")
    occasion = find_awards_occasions([event(), other]).occasions[0]
    assert len(occasion.events) == 2
    assert occasion.level == "member"
    assert all(member.evidence for member in occasion.events)


def test_case_and_optional_annual_keep_one_ceremony_and_a_stable_selector():
    from app.utils.awards_ceremony import awards_ceremony_slug

    labels = (
        "69th Annual GRAMMY Awards",
        "69th Annual Grammy Awards",
        "69th Grammy Awards",
    )
    candidates = [
        event(f"KXGRAMMY-CATEGORY{index}", label) for index, label in enumerate(labels)
    ]
    result = find_awards_occasions(candidates)
    assert result.refused == () and len(result.occasions) == 1
    occasion = result.occasions[0]
    assert len(occasion.events) == 3
    assert {quote for member in occasion.events for quote in member.evidence} == {
        candidate["markets"][0]["rules_primary"] for candidate in candidates
    }
    assert len({awards_ceremony_slug(label) for label in labels}) == 1
    assert find_awards_occasions(reversed(candidates)) == result
    for label in labels:
        selector = {"evidence": "primary_rules_ordinal_awards", "label": label}
        assert select_awards_occasion(selector, candidates) == occasion


def test_one_event_can_use_both_spellings_of_the_same_ordinal_ceremony():
    candidate = event("KXGRAMMY-27", "69th Annual GRAMMY Awards")
    candidate["markets"].extend(event("KXGRAMMY-27", "69th Grammy Awards")["markets"])
    found = find_awards_occasions([candidate])
    assert found.refused == () and len(found.occasions) == 1
    assert len(found.occasions[0].events[0].evidence) == 2


def test_ceremony_spelling_rules_keep_different_ordinals_and_names_separate():
    candidates = [
        event("KXGRAMMY-27", "69th Annual GRAMMY Awards"),
        event("KXGRAMMY-28", "70th Grammy Awards"),
        event("KXOTHER-27", "69th Other Music Awards"),
    ]
    assert len(find_awards_occasions(candidates).occasions) == 3


@pytest.mark.parametrize(
    "change",
    [
        lambda e: e.update(markets=[]),
        lambda e: e["markets"][0].update(
            rules_primary="If The Odyssey is nominated, Yes."
        ),
        lambda e: e["markets"][0].update(
            rules_primary=None, rules_secondary="The 84th Golden Globe Awards."
        ),
    ],
)
def test_titles_ticker_years_and_secondary_boilerplate_cannot_fill_missing_identity(
    change,
):
    candidate = event()
    change(candidate)
    result = find_awards_occasions([candidate])
    assert result.occasions == ()
    assert result.refused == (("kalshi", "KXGGNOM-SCR26", "ceremony_identity_unknown"),)


def test_a_cross_ceremony_comparison_is_refused_instead_of_majority_voted():
    candidate = event()
    candidate["markets"].append(event(label="99th Academy Awards")["markets"][0])
    result = find_awards_occasions([candidate])
    assert result.occasions == ()
    assert result.refused[0][2] == "ambiguous_ceremony"


def test_conflicting_duplicate_observations_refuse_the_whole_event_in_either_order():
    first, conflicting = event(), event(label="85th Golden Globe Awards")
    result = find_awards_occasions([first, conflicting])
    assert result == find_awards_occasions([conflicting, first])
    assert result.occasions == ()
    assert result.refused[0][2] == "conflicting_event_evidence"
    assert len(find_awards_occasions([first, deepcopy(first)]).occasions[0].events) == 1


@pytest.mark.parametrize(
    "candidate",
    [
        None,
        {},
        event(provider="other"),
        event(event_ticker=""),
        event(event_ticker="KXGGNOM-SCR26?x"),
        event(provider="polymarket", id=True),
        event(provider="polymarket", id="01"),
    ],
)
def test_invalid_provider_identity_is_a_refusal(candidate):
    result = find_awards_occasions([candidate])
    assert result.occasions == () and result.refused


def test_a_selector_cannot_be_replaced_by_a_hand_list_or_a_fuzzy_name():
    for selector in [
        {"market_ids": [1, 2]},
        {"evidence": "primary_rules_ordinal_awards", "label": "Golden Globes"},
    ]:
        with pytest.raises(ValueError):
            select_awards_occasion(selector, [event()])
    assert (
        select_awards_occasion(
            find_awards_occasions([event()]).occasions[0].selector, []
        )
        is None
    )
