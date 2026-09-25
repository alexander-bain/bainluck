"""#8640 — a graded rung on a still-open ladder stops headlining search as a live 100%.

WHAT A READER SAW, production 2026-09-25 15:2xZ, ``/search?q=Fed rate`` at 390px,
ANSWERS card "FED & RATES"::

    What will Fed Rate hit before 2027        ↓ 3.5%  100%

Market 113427 (polymarket, ``status=open``, ``mutually_exclusive=false``) is a
multi-winner ladder. Its ``↓ 3.5%`` rung is already graded — ``is_winner TRUE``,
``resolution_source='api_settlement'`` — so its price is pinned at 1.0 and it
outsorted every live rung, reading as "the market is 100% sure" one row above
the same card's ``↑ 4.25%`` 90%.

THE FIXTURE IS THE SPECIMEN'S STORED ROWS, read off production via ``db-query``
the same morning (the ``Yes``/``No`` Q480 duplicate legs included — they are
the builder's to drop, not this test's).

THE CONTROL: the same rows on a ONE-winner board. There a graded winner is the
answer to the whole question, so it must keep the headline (#8615's population).
"""

from types import SimpleNamespace

from app.routes.events import _build_search_top_outcomes

#: ``(id, name, external_id, prob, bid, ask, is_winner, resolution_source)`` —
#: all 23 stored legs of 113427, verbatim, production 2026-09-25 ~16:00Z.
SPECIMEN_LEGS = [
    (1648536, "↓ 3.5%", "0xe7091caf215aa1f10f263476a4dea92e7532ecd178ad8ddc82a1136ffc07c8cc", 1.0, 0.999, 1.0, True, "api_settlement"),
    (1648537, "↓ 3.25%", "0x70d8f4e6079e98fd9a34a8f6ce00a7dd3a73a924c9d9fab0664d516f38c6f280", 0.032, 0.016, 0.048, False, None),
    (1648538, "↓ 3.0%", "0xdab002228af15d1cb3a161b3a584165eac9010d4419582c3c7d5d07d847c4256", 0.013, 0.003, 0.023, False, None),
    (1648539, "↓ 2.75%", "0x2bb4294142c311763ca6be27ceffcef132f5ac8281f98a62abe02f6e6a8c0107", 0.022, 0.021, 0.023, False, None),
    (1648540, "↓ 2.5%", "0xaa6145fb75147c5dda9bda894ed80353b14f23149b285893dd41e1edc8c0d4c2", 0.0135, 0.008, 0.019, False, None),
    (1648541, "↓ 2.25%", "0x0bbbcca922e19937c88530c715742a6c4c5d951e3e91e2c37d3053ed6e820c81", 0.021, 0.016, 0.026, False, None),
    (1648542, "↓ 2.0%", "0xbfc96144ac92b856a86dfde02939ccb9ec4bd997c424aa2f68b35dce0651f99f", 0.028, 0.027, 0.029, False, None),
    (1648543, "↓ 1.5%", "0xe8a621e745e7f05a582102109b45bb0fb23ce5d90848d977f75172eca041d448", 0.0175, 0.016, 0.019, False, None),
    (1648544, "↓ 1.75%", "0x0c37533837ed4d3378494fcd9ea7043d03cc3af9443d68dfa0414984efcbaff9", 0.013, 0.009, 0.017, False, None),
    (1648545, "↓ 0.5%", "0x4e15f0f425d28b87024ba9f19504e074da257e3d231d3222618a67c5c0f600ba", 0.0255, 0.021, 0.030, False, None),
    (1648546, "↓ 1.25%", "0x803d1018e9b81b886b3ef242de57f0d6ebee3313d0728c57eed0a146d56a3bff", 0.0185, 0.006, 0.031, False, None),
    (1648547, "↓ 1.0%", "0x9ee5565296fbc49e0a2965c48a04c04a80a2cfd966d4eee60504602c63c4e02b", 0.0275, 0.022, 0.033, False, None),
    (1648548, "↓ 0%", "0x3983cda71404c649fd93c5efb200b83835bd67feb4593deab909417c93be5b5d", 0.0225, 0.021, 0.024, False, None),
    (1648549, "↓ 0.25%", "0x8be4f92d8396e675e220e15c1ca5bca527bc22dba01d586e2118096c1fe8a4a3", 0.027, 0.026, 0.028, False, None),
    (1648550, "↓ 0.75%", "0x58c9cde78e3a468af321f5a3d1063885a8f1e6635b0455a1ea9f211c018f5b83", 0.0185, 0.017, 0.020, False, None),
    (1648551, "↑ 4.25%", "0x69f7294fab44b1a63575fcdff9b683d3c48a7f92a160aa274af8e2837a356e63", 0.9025, 0.900, 0.905, False, None),
    (1648552, "↑ 4.5%", "0x4f330fc689830668acf7d6e6e24dcd7450dc0387855f63aecbfac64b6d458650", 0.457, 0.395, 0.519, False, None),
    (1648553, "↑ 4.75%", "0x784b640e50d8db8ff5b36904fe9ecd1b3a261f4d3a0cd20adcfb7156e066ca78", 0.1095, 0.035, 0.184, False, None),
    (1648554, "↑ 5.0%", "0x0a95717208bdb1c1167877eb5b19085494f68ed9b074d8dfc7d76b549fcbe7bb", 0.027, 0.022, 0.032, False, None),
    (1648555, "↑ 5.5%", "0x360247ba6b67009d19be741be7187abd59c5005e14be0914eb4e485f3b342c40", 0.0285, 0.026, 0.031, False, None),
    (1648556, "↑ 5.25%", "0x728246cda497e10289a7145245675e2baece6561ba784760b0914108e6e42c04", 0.026, 0.025, 0.027, False, None),
    (84290491, "Yes", "0xe8a621e745e7f05a582102109b45bb0fb23ce5d90848d977f75172eca041d448_yes", 0.05, 0.04, 0.06, False, None),
    (84290492, "No", "0xe8a621e745e7f05a582102109b45bb0fb23ce5d90848d977f75172eca041d448_no", 0.95, None, None, False, None),
]

GRADED_ID = 1648536
LIVE_LEADER = "↑ 4.25%"


def _leg(oid, name, ext, prob, bid, ask, is_winner, resolution_source):
    return SimpleNamespace(
        id=oid,
        name=name,
        external_id=ext,
        current_probability=prob,
        current_american_odds=None,
        rank=None,
        probability_change_24h=None,
        is_winner=is_winner,
        resolution_source=resolution_source,
        current_yes_bid=bid,
        current_yes_ask=ask,
        price_changed_at=None,
        last_updated=None,
    )


def _market(*, mutually_exclusive=False, status="open", legs=SPECIMEN_LEGS):
    return SimpleNamespace(
        id=113427,
        name="What will Fed Rate hit before 2027",
        source="polymarket",
        status=status,
        mutually_exclusive=mutually_exclusive,
        outcomes=[_leg(*row) for row in legs],
    )


def test_live_rung_headlines_the_open_ladder_not_the_graded_one():
    out = _build_search_top_outcomes(_market())
    assert out, "the ladder must still draw"
    assert out[0]["name"] == LIVE_LEADER, [o["name"] for o in out]


def test_lean_typeahead_headline_is_the_live_rung_too():
    # #993: the dropdown and the card are one pair — both must move.
    out = _build_search_top_outcomes(_market(), limit=3, lean=True)
    assert out[0]["name"] == LIVE_LEADER, [o["name"] for o in out]


def test_graded_rung_is_demoted_not_deleted_and_carries_its_grade():
    # A SHORT ladder, so the demoted rung is still inside the slice. On the full
    # specimen twenty live rungs outrank it and it leaves the five-row card
    # entirely — the same "demotion moves it off the card" #6993 accepts; the
    # result stays on the market's own page.
    legs = [row for row in SPECIMEN_LEGS if row[0] in (GRADED_ID, 1648551, 1648552)]
    out = _build_search_top_outcomes(_market(legs=legs))
    graded = [o for o in out if o["id"] == GRADED_ID]
    assert graded, "settled means settled: the result stays on the card (#6532)"
    row = graded[0]
    assert row["probability"] == 1.0
    assert row["is_winner"] is True
    assert row["resolution_source"] == "api_settlement"
    # It sits below every live rung.
    idx = out.index(row)
    assert idx == len(out) - 1, [o["name"] for o in out]
    assert all(o["resolution_source"] is None for o in out[:idx])


def test_live_rungs_serve_as_ungraded():
    out = _build_search_top_outcomes(_market())
    leader = out[0]
    assert leader["is_winner"] is False
    assert leader["resolution_source"] is None


def test_control_one_winner_board_keeps_its_graded_winner_as_headline():
    out = _build_search_top_outcomes(_market(mutually_exclusive=True))
    assert out[0]["id"] == GRADED_ID


def test_control_graded_loss_badge_alone_also_demotes():
    # `is_winner` False is the column default; the badge is what makes it a
    # verdict (`leg_is_graded`). A graded-LOSS rung with a stale high price
    # must not headline either.
    legs = [
        (1, "↓ 3.0%", "0xa", 0.97, 0.96, 0.98, False, "api_settlement"),
        (2, "↑ 4.0%", "0xb", 0.40, 0.39, 0.41, False, None),
    ]
    out = _build_search_top_outcomes(_market(legs=legs))
    assert [o["name"] for o in out] == ["↑ 4.0%", "↓ 3.0%"]


def test_control_ungraded_default_false_is_not_demoted():
    legs = [
        (1, "↓ 3.0%", "0xa", 0.97, 0.96, 0.98, False, None),
        (2, "↑ 4.0%", "0xb", 0.40, 0.39, 0.41, False, None),
    ]
    out = _build_search_top_outcomes(_market(legs=legs))
    assert [o["name"] for o in out] == ["↓ 3.0%", "↑ 4.0%"]


def test_a_withheld_or_unpriced_live_rung_never_headlines_over_a_result():
    # Three tiers, not two: "graded last" alone would put a refused (#6993) or
    # never-priced ungraded rung above every result, and the card would lead
    # with a dash.
    legs = [
        (1, "↓ 3.0%", "0xa", 0.99, 0.98, 1.0, True, "api_settlement"),
        (2, "↑ 4.0%", "0xb", 0.60, 0.0, 1.0, False, None),  # refused below
        (3, "↑ 4.5%", "0xc", None, None, None, False, None),  # never priced
    ]
    out = _build_search_top_outcomes(_market(legs=legs), withheld={2})
    assert out[0]["id"] == 1, [o["name"] for o in out]


def test_one_winner_board_order_is_price_alone():
    # Off the #8640 path the sort is exactly what it was: a one-winner board's
    # order is decided by price alone.
    legs = [
        (1, "↓ 3.0%", "0xa", 0.30, 0.29, 0.31, False, "api_settlement"),
        (2, "↑ 4.0%", "0xb", 0.60, 0.59, 0.61, False, None),
    ]
    out = _build_search_top_outcomes(_market(legs=legs, mutually_exclusive=True))
    assert [o["id"] for o in out] == [2, 1]
