"""The Kalshi match-market linker (Q466).

Alex, on the US Open page: *"It's weird that there's no pre-match probabilities
in the finished matches."*  The page's own footnote blamed absence — "matches
nobody ran a market on".  Measured on production 2026-08-31, that was false in
the most embarrassing direction available:

    main draw R1 finished matches with a pre-match figure   0 / 28
    qualifying    finished matches with a pre-match figure  25 / 96

The better-covered half was the half nobody quotes, and Kalshi held 5,048
``KXATPMATCH``/``KXWTAMATCH`` markets — newest created that same day.  The draw
ingest had written ``status: "missing"`` on all 96 main-draw fixtures on
2026-08-27, correctly, and nothing ever revisited it.

These guards cover the two halves of the fix: the census that decides which
market prices which fixture, and the pass that applies it.  The refusals get
more attention than the successes, because a wrong pin is a real number wearing
the wrong player's name and it looks perfectly plausible on the page.
"""

from __future__ import annotations

import importlib.util
import json
import os
from datetime import datetime, timezone
from pathlib import Path

import pytest

BACKEND = Path(__file__).resolve().parents[1]


def _script(name: str):
    """Import a `scripts/` module by path — they are not an importable package."""
    spec = importlib.util.spec_from_file_location(name, BACKEND / "scripts" / f"{name}.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


census_mod = _script("fetch_kalshi_match_census")
pin_mod = _script("pin_kalshi_match_markets")


# ---------------------------------------------------------------------------
# THE TICKER'S DATE — the only honest one on a Kalshi tennis row
# ---------------------------------------------------------------------------

class TestTheTickerDate:
    def test_it_reads_the_date_the_ticker_encodes(self):
        assert census_mod.ticker_date("KXATPMATCH-26AUG30BUBWOL") == datetime(
            2026, 8, 30, tzinfo=timezone.utc
        )
        assert census_mod.ticker_date("KXWTAMATCH-26SEP02SHAVAN") == datetime(
            2026, 9, 2, tzinfo=timezone.utc
        )

    def test_it_refuses_a_ticker_it_cannot_read_rather_than_guessing(self):
        for bad in ("KXATPMATCH", "KXATPMATCH-BOGUS", "KXATPMATCH-26XXX30AAA", ""):
            assert census_mod.ticker_date(bad) is None, bad

    def test_the_resolution_date_column_is_not_used_and_here_is_why(self):
        """`KXATPMATCH-26AUG30TIRMAN` was played on 30 Aug and its
        `resolution_date` reads 2026-09-13 — the tournament's END. That is
        gotcha #14, and a date filter built on the column would have refused
        every correct pin in this census."""
        played = census_mod.ticker_date("KXATPMATCH-26AUG30TIRMAN")
        resolution = datetime(2026, 9, 13, 15, 0, tzinfo=timezone.utc)
        assert (resolution - played).days == 14


# ---------------------------------------------------------------------------
# THE JOIN, AND EVERY WAY IT IS ALLOWED TO REFUSE
# ---------------------------------------------------------------------------

def _register(matchups=None, players=None):
    return {
        "players": players or [
            {"entity_key": "alexander-bublik", "display_name": "Alexander Bublik",
             "draw": "mens-singles"},
            {"entity_key": "j-j-wolf", "display_name": "Jeffrey John Wolf",
             "draw": "mens-singles"},
        ],
        "matchups": matchups if matchups is not None else [{
            "matchup_key": "mens-singles:alexander-bublik-vs-j-j-wolf:2026-08-30",
            "draw": "mens-singles",
            "round": "R128",
            "scheduled_date": "2026-08-30T04:00:00+00:00",
            "players": ["alexander-bublik", "j-j-wolf"],
            "sources": [],
        }],
    }


def _rows(ticker="KXATPMATCH-26AUG30BUBWOL", a="Alexander Bublik",
          b="Jeffrey John Wolf", market_id=1, opening=("0.695", "0.295")):
    return [
        {"market_id": market_id, "market_ext": ticker, "market_name": "Bublik vs Wolf",
         "status": "open", "resolution_date": "2026-09-13 15:00:00+00:00",
         "outcome_id": 100 + i, "outcome_name": name,
         "outcome_ext": f"{ticker}-{name.split()[-1][:3].upper()}",
         "current_probability": "0.5", "opening_probability": opening[i]}
        for i, name in enumerate((a, b))
    ]


def _build(rows, register=None, window=None):
    kwargs = {} if window is None else {"match_window_days": window}
    return census_mod.build_census(
        rows, register or _register(), draw="mens-singles",
        observed_at="2026-08-31T04:00:00+00:00", **kwargs,
    )


def test_a_registered_pair_is_pinned_with_the_sides_the_register_names():
    matches, rejected = _build(_rows())
    assert rejected == []
    assert len(matches) == 1
    sides = matches[0]["sides"]
    # Keyed by OUR entity keys, and each side carries the source's own label —
    # so the mapping stays checkable later without re-parsing a title.
    assert set(sides) == {"alexander-bublik", "j-j-wolf"}
    assert sides["alexander-bublik"]["source_label"] == "Alexander Bublik"
    assert sides["j-j-wolf"]["source_label"] == "Jeffrey John Wolf"
    assert sides["alexander-bublik"]["outcome_id"] != sides["j-j-wolf"]["outcome_id"]


def test_the_sides_follow_the_NAMES_when_the_two_orderings_disagree():
    """THE INVERSION GUARD.

    The register names Wolf first; Kalshi's rows come back Bublik first. If the
    mapping were positional the card would print Bublik's 69% under Wolf's name
    — a real number, a real player, and completely wrong. Nothing downstream can
    catch that, which is why the repo already carries an inversion backstop for
    the Polymarket path.
    """
    register = _register()
    register["matchups"][0]["players"] = ["j-j-wolf", "alexander-bublik"]

    matches, rejected = _build(_rows(opening=("0.695", "0.295")), register=register)
    assert rejected == []
    sides = matches[0]["sides"]
    assert sides["alexander-bublik"]["source_label"] == "Alexander Bublik"
    assert sides["alexander-bublik"]["opening_probability"] == "0.695"
    assert sides["j-j-wolf"]["source_label"] == "Jeffrey John Wolf"
    assert sides["j-j-wolf"]["opening_probability"] == "0.295"


def test_a_pair_the_register_does_not_carry_is_refused_not_helpfully_paired():
    """The ticker window is every ATP/WTA match on earth. Only fixtures the
    register already names may be pinned — the same rule that keeps a stale
    Cincinnati market from becoming a slate row."""
    matches, rejected = _build(_rows(a="Carlos Alcaraz", b="Jannik Sinner"))
    assert matches == []
    assert [r["reason"] for r in rejected] == ["PAIR_NOT_A_REGISTERED_FIXTURE"]


def test_the_same_two_players_at_a_different_tournament_are_refused_on_the_date():
    """THE DISCRIMINATOR WITH TEETH.

    Bublik and Wolf may also have met a fortnight earlier, and that market is
    in this window. Same names, same draw, different date — refused.

    ⚠️ WIDENED, NOT REWRITTEN (CERT-534). This test asserted the condemned
    contract: it proved a refusal SIXTEEN DAYS out and never went near the
    boundary, so it stayed green while everything from four days before the
    fixture onward was being pinned. Its original fortnight case is kept below
    as the far negative control — only the reason string moved, because the
    two directions are now refused under different names.
    """
    matches, rejected = _build(_rows(ticker="KXATPMATCH-26AUG14BUBWOL"))
    assert matches == []
    assert [r["reason"] for r in rejected] == ["DATE_PRECEDES_THE_FIXTURE"]

    # ...and the correct date still passes, so the rule is a discriminator and
    # not a blanket refusal.
    matches, _ = _build(_rows(ticker="KXATPMATCH-26AUG30BUBWOL"))
    assert len(matches) == 1


def test_a_same_pair_market_THREE_DAYS_BEFORE_the_fixture_is_refused():
    """CERT-534, AND IT IS THE WHOLE POINT OF THE DISCRIMINATOR.

    The blocked version compared the ticker date to the fixture with a
    SYMMETRIC ±96h tolerance, so an otherwise-valid same-player market dated
    Aug 27 was pinned onto the Aug 30 US Open fixture. That is a real Kalshi
    price, for a real match between these two players, under the wrong one —
    and on the page it looks perfectly plausible, which is exactly why the
    census has a date rule at all.

    Reproduced on the blocked bytes before the fix: PINNED.
    """
    matches, rejected = _build(_rows(ticker="KXATPMATCH-26AUG27BUBWOL"))
    assert matches == []
    assert [r["reason"] for r in rejected] == ["DATE_PRECEDES_THE_FIXTURE"]


def test_the_backward_boundary_is_the_fixtures_own_DAY_and_has_no_slack():
    """ONE DAY EARLY IS STILL ANOTHER TOURNAMENT.

    The backward direction gets zero room, because measured over all 177
    registered-pair candidates on production not one legitimate market is
    ticker-dated after its fixture's stamp — the whole real population sits
    between -24h and 0. A backward window describes nothing that exists and
    admits everything that must be refused.
    """
    matches, rejected = _build(_rows(ticker="KXATPMATCH-26AUG29BUBWOL"))
    assert matches == []
    assert [r["reason"] for r in rejected] == ["DATE_PRECEDES_THE_FIXTURE"]

    # The fixture's own day is the first accepted value, not the last refused.
    matches, rejected = _build(_rows(ticker="KXATPMATCH-26AUG30BUBWOL"))
    assert rejected == []
    assert len(matches) == 1


def test_the_stamp_is_read_as_a_DAY_so_a_ticker_hours_BEFORE_it_still_pins():
    """THE 88 PINS DEPEND ON THIS AND A NAIVE FLOOR WOULD DESTROY THEM ALL.

    The ticker names a day at 00:00Z; the stamp is an instant later that day —
    04:00Z for the main draw, and as late as 23:45Z for a qualifying evening
    match. So EVERY real pin's ticker sits 4 to 24 hours BEFORE its own
    fixture's stamp. A floor placed at the stamp rather than at the stamp's
    day would refuse all 88 committed pins while looking strictly safer.
    """
    register = _register()
    # A qualifying-shaped stamp: a real per-match evening start, the widest
    # legitimate gap measured on production (-23.8h).
    register["matchups"][0]["scheduled_date"] = "2026-08-30T23:45:00Z"

    matches, rejected = _build(_rows(ticker="KXATPMATCH-26AUG30BUBWOL"),
                               register=register)
    assert rejected == []
    assert len(matches) == 1


def test_a_first_round_played_AFTER_the_ceremony_stamp_is_still_pinned():
    """FIXING ONLY OPENING DAY IS NOT THE SHIP (CERT-544, sibling queue).

    All 96 main-draw fixtures carry ONE stamp — the draw ceremony — so the
    stamp names the tournament's opening day, not each match's day. A first
    round is played across several days. A day-equality rule would price
    opening day and refuse every day-two and day-three market, re-creating the
    blank the queue exists to fill.
    """
    for ticker in ("KXATPMATCH-26AUG31BUBWOL", "KXATPMATCH-26SEP01BUBWOL"):
        matches, rejected = _build(_rows(ticker=ticker))
        assert rejected == [], ticker
        assert len(matches) == 1, ticker


def test_the_forward_window_is_bounded_and_the_boundary_is_where_it_says():
    """The forward half has room, not licence. Both sides of the edge are
    asserted, so widening or narrowing the constant fails this test."""
    window = census_mod.MATCH_WINDOW_DAYS
    assert window == 7

    # The last accepted day...
    matches, rejected = _build(_rows(ticker="KXATPMATCH-26SEP06BUBWOL"))
    assert rejected == []
    assert len(matches) == 1

    # ...and the first refused one.
    matches, rejected = _build(_rows(ticker="KXATPMATCH-26SEP07BUBWOL"))
    assert matches == []
    assert [r["reason"] for r in rejected] == ["DATE_DISAGREES_WITH_FIXTURE"]


def test_the_window_flag_actually_REACHES_the_rule(tmp_path, monkeypatch):
    """A NEW PARAMETER THAT NEVER ARRIVES IS A REAL BUG, NOT A HYPOTHETICAL.

    Q467 shipped one on this same board — a pre-warm beat that omitted its new
    argument, so the `Query` object itself was used as the value. And this
    flag cannot be proven from production data: every real candidate is dated
    on or before its fixture's day, so the forward bound is not exercised and
    `--match-window-days 0` and the default return the identical 88 pins. The
    wiring has to be asserted directly or it is not asserted at all.
    """
    seen = {}

    def fake_build_census(rows, register, *, draw, observed_at, match_window_days):
        seen[draw] = match_window_days
        return [], []

    monkeypatch.setattr(census_mod, "fetch_candidates", lambda series, **kw: [])
    monkeypatch.setattr(census_mod, "build_census", fake_build_census)

    register = tmp_path / "register.json"
    register.write_text(json.dumps(_register()))
    out = tmp_path / "census.json"
    monkeypatch.setattr("sys.argv", [
        "fetch_kalshi_match_census.py",
        "--register", str(register),
        "--observed-at", "2026-08-31T04:00:00+00:00",
        "--out", str(out),
        "--match-window-days", "3",
    ])

    assert census_mod.main() == 0
    assert seen and set(seen.values()) == {3}, f"the flag did not arrive: {seen}"

    # ...and the default is the constant, not a second copy of the number.
    seen.clear()
    monkeypatch.setattr("sys.argv", [
        "fetch_kalshi_match_census.py",
        "--register", str(register),
        "--observed-at", "2026-08-31T04:00:00+00:00",
        "--out", str(out),
    ])
    assert census_mod.main() == 0
    assert set(seen.values()) == {census_mod.MATCH_WINDOW_DAYS}


def test_an_offsetless_stamp_is_read_as_UTC_and_NOT_as_the_machines_local_time():
    """THE MUTANT THAT SURVIVED THE FIRST BATTERY, AND WHY IT MATTERS.

    Deleting the explicit ``replace(tzinfo=utc)`` does not crash and does not
    even fail: ``astimezone`` reads a naive datetime as MACHINE-LOCAL time and
    converts it happily. So the register's offset-less stamp would silently
    mean a different instant on a machine in a different timezone — and the
    end-to-end test below could not see it, because this machine's offset does
    not happen to move the day.

    The zone is therefore PINNED rather than inherited. A test whose answer
    depends on where it runs is not a guard (gotcha #44's family): at UTC+9 a
    naive ``02:00`` read as local is the PREVIOUS UTC day, which moves the
    floor a whole day and would re-admit exactly the markets CERT-534 blocked.
    """
    import time

    previous = os.environ.get("TZ")
    os.environ["TZ"] = "Asia/Tokyo"
    time.tzset()
    try:
        naive = datetime(2026, 8, 30, 2, 0, 0)
        assert census_mod._utc_day(naive) == datetime(
            2026, 8, 30, tzinfo=timezone.utc
        ), "a naive stamp was read as local time, not UTC"

        # ...and the same instant written with its offset agrees, which is the
        # whole claim: the two spellings are the same day.
        aware = datetime(2026, 8, 30, 2, 0, 0, tzinfo=timezone.utc)
        assert census_mod._utc_day(naive) == census_mod._utc_day(aware)
    finally:
        if previous is None:
            os.environ.pop("TZ", None)
        else:
            os.environ["TZ"] = previous
        time.tzset()


def test_an_offsetless_register_stamp_is_read_as_UTC_rather_than_crashing():
    """CERT-527's class, one script over: the register's own validator accepts
    an offset-less instant, so comparing it with an aware ticker date raised a
    TypeError and took the whole census down on data the register called
    well-formed."""
    register = _register()
    register["matchups"][0]["scheduled_date"] = "2026-08-30T04:00:00"

    matches, rejected = _build(_rows(ticker="KXATPMATCH-26AUG30BUBWOL"),
                               register=register)
    assert rejected == []
    assert len(matches) == 1


def test_an_unreadable_ticker_date_REFUSES_rather_than_skipping_the_check():
    """CERT-529. A discriminator that cannot run has not passed.

    The first version compared dates only when BOTH parsed, so a ticker whose
    date could not be read skipped the check entirely and the market was pinned
    anyway. That is absence-as-permission, and it is worst exactly here: this
    check is the only thing standing between a US Open fixture and an
    identically-named market from another tournament.
    """
    matches, rejected = _build(_rows(ticker="KXATPMATCH-BOGUSXX"))
    assert matches == []
    assert [r["reason"] for r in rejected] == ["DATE_UNREADABLE_SO_UNVERIFIABLE"]


def test_a_fixture_with_no_scheduled_date_is_also_unverifiable():
    """The other half of the same hole — the register side rather than the
    market side. Same refusal, same reason."""
    register = _register()
    register["matchups"][0]["scheduled_date"] = None
    matches, rejected = _build(_rows(), register=register)
    assert matches == []
    assert [r["reason"] for r in rejected] == ["DATE_UNREADABLE_SO_UNVERIFIABLE"]


def test_two_markets_for_one_fixture_refuse_BOTH_rather_than_taking_the_first():
    """Taking the first would pin a plausible number from the wrong market."""
    rows = _rows(market_id=1) + _rows(ticker="KXATPMATCH-26AUG31BUBWOL", market_id=2)
    matches, rejected = _build(rows)
    assert matches == []
    assert [r["reason"] for r in rejected] == ["AMBIGUOUS_TWO_MARKETS_ONE_FIXTURE"] * 2


def test_a_market_with_no_opening_price_is_refused():
    """The pre-match figure IS the opening quote — the only stored price
    guaranteed to pre-date the match. A pin without one buys the page nothing."""
    rows = _rows()
    rows[0]["opening_probability"] = None
    matches, rejected = _build(rows)
    assert matches == []
    assert [r["reason"] for r in rejected] == ["NO_OPENING_PRICE"]


def test_a_one_sided_market_is_refused():
    matches, rejected = _build(_rows()[:1])
    assert matches == []
    assert [r["reason"] for r in rejected] == ["NOT_TWO_SIDED"]


# ---------------------------------------------------------------------------
# THE APPLY PASS
# ---------------------------------------------------------------------------

def _fixture_with_block(status="missing"):
    register = _register()
    register["matchups"][0]["sources"] = [{
        "source": "kalshi", "kind": "match", "market_id": None, "outcome_id": None,
        "status": status, "terminal_result": None,
        "evidence": {"kind": "draw-fixture-census-absent"},
    }]
    return register


def _census_for(register):
    matches, _ = _build(_rows(), register=register)
    return {"matches": matches}


def test_a_missing_block_is_filled_in_place():
    register = _fixture_with_block("missing")
    result = pin_mod.apply_census(register, _census_for(register), repin=False)
    assert result["stats"]["pinned"] == 1
    block = register["matchups"][0]["sources"][0]
    assert block["status"] == "live"
    assert block["market_external_id"] == "KXATPMATCH-26AUG30BUBWOL"
    assert set(block["sides"]) == {"alexander-bublik", "j-j-wolf"}
    assert block["evidence"]["kind"] == "kalshi-match-market-census"


def test_a_SETTLED_block_is_never_overwritten():
    """CERT-529. The first version refused only `live`, so a `settled` block —
    a real status carrying a `terminal_result` this pass does not hold — was
    overwritten and its banked answer silently dropped. That is how a decided
    fixture starts quoting again.
    """
    register = _fixture_with_block("settled")
    block = register["matchups"][0]["sources"][0]
    block["terminal_result"] = "won"
    block["market_external_id"] = "THE-SETTLED-ONE"

    result = pin_mod.apply_census(register, _census_for(register), repin=False)
    assert result["stats"]["not_missing"] == 1
    assert result["stats"]["pinned"] == 0
    after = register["matchups"][0]["sources"][0]
    assert after["status"] == "settled"
    assert after["terminal_result"] == "won"
    assert after["market_external_id"] == "THE-SETTLED-ONE"


def test_a_block_that_is_already_live_is_left_alone():
    """Silently repointing a priced fixture at a different market is how a page
    starts showing a real number from the wrong match. Re-pinning is deliberate.
    """
    register = _fixture_with_block("live")
    register["matchups"][0]["sources"][0]["market_external_id"] = "SOMETHING-ELSE"
    result = pin_mod.apply_census(register, _census_for(register), repin=False)
    assert result["stats"] == {
        "pinned": 0, "already_pinned": 1, "not_missing": 0, "repinned": 0,
        "no_such_fixture": 0, "no_kalshi_block": 0,
    }
    assert register["matchups"][0]["sources"][0]["market_external_id"] == "SOMETHING-ELSE"

    # ...and --repin is the deliberate act that does change it.
    result = pin_mod.apply_census(register, _census_for(register), repin=True)
    assert result["stats"]["repinned"] == 1
    assert register["matchups"][0]["sources"][0]["market_external_id"] == (
        "KXATPMATCH-26AUG30BUBWOL"
    )


def test_a_census_naming_a_fixture_the_register_lost_is_counted_not_crashed():
    register = _fixture_with_block("missing")
    census = _census_for(register)
    census["matches"][0]["matchup_key"] = "mens-singles:nobody-vs-nobody:2026-08-30"
    result = pin_mod.apply_census(register, census, repin=False)
    assert result["stats"]["no_such_fixture"] == 1
    assert register["matchups"][0]["sources"][0]["status"] == "missing"


# ---------------------------------------------------------------------------
# THE SHIP, on the real committed file
# ---------------------------------------------------------------------------

def _committed_register():
    return json.loads(
        (BACKEND / "data" / "tournament_registers" / "us-open-2026.json").read_text()
    )


def test_the_committed_register_prices_the_main_draw_it_used_to_leave_empty():
    """THE SHIP. Before this queue: 0 of 96 main-draw fixtures had a priced
    match market. The page said "matches nobody ran a market on" about a draw
    Kalshi had quoted for days."""
    register = _committed_register()
    r128 = [m for m in register["matchups"] if m.get("round") == "R128"]
    assert len(r128) == 96

    def priced(matchup):
        return any(
            isinstance(b, dict) and b.get("status") == "live"
            and isinstance(b.get("sides"), dict) and len(b["sides"]) == 2
            for b in matchup.get("sources") or []
        )

    covered = [m for m in r128 if priced(m)]
    assert len(covered) >= 88, f"main-draw coverage regressed to {len(covered)}/96"


def test_every_pinned_side_agrees_with_kalshis_own_outcome_id():
    """AN INDEPENDENT CHECK ON THE MAPPING.

    The join is made on normalized player names, so a guard that re-does the
    name match proves nothing. Kalshi's outcome id carries its own abbreviation
    of the player it belongs to (``...-26AUG30VALMON-VAL``), which is a SECOND,
    independently-authored statement of the same fact. All 176 sides on the
    committed register agree with it.
    """
    import unicodedata

    register = _committed_register()
    display = {p["entity_key"]: p.get("display_name") or "" for p in register["players"]}

    def fold(value: str) -> str:
        return "".join(
            ch for ch in unicodedata.normalize("NFKD", value)
            if not unicodedata.combining(ch)
        ).upper().replace("-", " ")

    checked = 0
    for matchup in register["matchups"]:
        for block in matchup.get("sources") or []:
            if not isinstance(block, dict) or block.get("source") != "kalshi":
                continue
            if (block.get("evidence") or {}).get("kind") != "kalshi-match-market-census":
                continue
            for entity_key, side in (block.get("sides") or {}).items():
                abbreviation = str(side["outcome_external_id"]).rsplit("-", 1)[-1]
                words = fold(display.get(entity_key, entity_key)).split()
                words += fold(str(side.get("source_label") or "")).split()
                assert any(w.startswith(abbreviation) for w in words), (
                    f"{matchup['matchup_key']}: Kalshi's id says {abbreviation!r} but "
                    f"we mapped it to {display.get(entity_key)!r}"
                )
                checked += 1
    assert checked >= 176, f"only {checked} pinned sides found — did the pins vanish?"


def test_the_pinned_fixtures_render_a_coherent_pre_match_pair():
    """The number has to survive `normalize_pair`, or the card shows nothing.

    An incoherent pair yields NOTHING rather than a tidy fabricated split, so a
    pin that does not normalize is a pin that bought the page no figure at all.
    """
    from app.utils.tournament_register import TournamentRegister
    from app.utils.tournament_slate import _prematch_by_pair

    register = _committed_register()
    # Price every pinned outcome with a plausible complementary pair.
    prices: dict[int, dict[str, float]] = {}
    for matchup in register["matchups"]:
        for block in matchup.get("sources") or []:
            sides = (block or {}).get("sides") or {}
            if len(sides) != 2:
                continue
            for offset, side in enumerate(sides.values()):
                oid = side.get("outcome_id")
                if isinstance(oid, int):
                    prices[oid] = {"opening_probability": 0.6 if offset == 0 else 0.4}

    pairs = _prematch_by_pair(TournamentRegister(register), prices)
    r128 = [
        m for m in register["matchups"]
        if m.get("round") == "R128"
        and (m.get("draw"), tuple(sorted(m["players"]))) in pairs
    ]
    assert len(r128) >= 88, f"only {len(r128)} main-draw fixtures yield a pre-match pair"


@pytest.mark.parametrize("script", ["fetch_kalshi_match_census", "pin_kalshi_match_markets"])
def test_neither_script_runs_anything_at_request_time(script):
    """Both are agent-run, by charter. A route importing either would put a
    db-query round trip inside a page render."""
    source = (BACKEND / "scripts" / f"{script}.py").read_text()
    assert "__main__" in source
    for route in (BACKEND / "app" / "routes").glob("*.py"):
        assert script not in route.read_text(), f"{route.name} imports {script}"
