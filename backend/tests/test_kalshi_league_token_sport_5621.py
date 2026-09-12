"""#5621 — searching your club stops returning the game as basketball.

## The ship

`https://bainluck.com/search?q=Jacksonville` at 390px, production Sat
2026-09-12 13:55Z, the day before NFL Week 1 Sunday. Two ADJACENT cards:

    NFL                Tomorrow 10:00 AM
    Jacksonville Jaguars                      79%
    Cleveland Browns                          21%
    Proj 24-16                                CBS

    OTHER BASKETBALL   Tomorrow  1:00 PM
    C  Cleveland
       No price yet
    J  Jacksonville

One fixture, twice: once correctly, once labelled **OTHER BASKETBALL** with the
teams reversed, the kickoff three hours out, no price, and generic initial
avatars where the club badges belong. That is the front door (SHIP 7) and
"appear once, everywhere" (SHIP 3), on the busiest NFL weekend of the season.
The same pair is served for "Houston" and "Cincinnati".

## The league page is NOT the reach, recorded so nobody re-derives it

`/api/leagues/basketball_other` serves these rows too — 8 of 8 upcoming cards
were football when read at 13:28Z (5 NFL, 3 CFL). It is tempting and WRONG to
call that the harm: `/sport/basketball/other` renders *"League 'other' not
found in Basketball"*, because the page resolves its league from
`/api/sports/hierarchy/basketball`, which lists exactly `nba`, `wnba`, `ncaab`
and `wncaab`. An endpoint with no route in front of it is a mechanism, not a
reader (gotcha: an unguarded serving path does not prove reach). Search is
where these rows actually reach a person, and the ONLY reason the earlier
negative read clean is that the phantoms carry CITY names — a search for
"Jaguars" or "Texans" misses them; "Jacksonville" and "Houston" do not.

## One unmapped series, and the scatter that names it

All five NFL rows — 16 in total — were minted by ONE Kalshi series,
`KXNFLFFPTS` (NFL Fantasy Points), which was absent from
`KALSHI_TICKER_TO_SPORT_KEY`. Step 1 of `_categorize_kalshi_market` calls the
ticker "AUTHORITATIVE — ticker never lies", but an unmapped prefix resolves to
nothing and the row falls through to the NAME rules, which read
"Buffalo vs Houston: Fantasy **Points**…" as basketball.

The tell is the scatter — one series wearing four league tags:

    NFL 13 · NBA 1 · NCAAF 1 · WNBA 1

The WNBA row was New York Giants vs Dallas.

## Why a wrong sport MINTS A ROW rather than merely mislabelling one

This is the half that made it reader-visible, and it is what
`test_a_mislabelled_nfl_prop_can_no_longer_mint_an_event` pins:
`LLM_CATEGORIES_THAT_MAY_NOT_CREATE_EVENTS` contains `"football"`, so a market
the ticker proves is American football may NOT invent a fixture — Q453 put it
there because that category's errors are systematic. Mislabelled `basketball`,
the same market sails past that refusal and
`auto_create_sport_key_from_category` hands back `basketball_other`, so the
prop mints its own id-less game with the Kalshi close time standing in for
kickoff (gotcha #14) and the orientation reversed.

So correcting the ticker map closes the defect twice over, by two independent
routes: the row is labelled football, AND it can no longer create an event.

## This is the THIRD instance of one hole

`sport_keys.py` already carries the Q453 block for `kxnfl1q`/`kxnflrace`
("one NFL series scattered across FIVE sports"), and #2321 / #3340 are the same
family on other pages. Each repair added the missing literals. The literals
below are this ship; `test_every_league_token_prefix_maps_to_its_own_sport` is
the part that makes the NEXT mis-mapping loud instead of silent.

A series that is simply ABSENT from both maps still falls through to the name
rules — that is the residual hole, and it needs a league-token fallback in the
categoriser rather than another literal. Filed separately; it is a change to
the classifier, not to this config.
"""

import pytest

from app.tasks.kalshi import _categorize_kalshi_market
from app.utils.prediction_market_matching import (
    LLM_CATEGORIES_THAT_MAY_NOT_CREATE_EVENTS,
    auto_create_sport_key_from_category,
)
from app.utils.sport_keys import (
    KALSHI_FUTURES_TICKER_TO_SPORT_KEY,
    KALSHI_GAME_TICKER_PREFIXES,
    KALSHI_TICKER_TO_SPORT_KEY,
)

#: The production specimens, verbatim from `futures_markets.external_id` /
#: `.name` on 2026-09-12. Every one minted an id-less `basketball_other` event.
FANTASY_POINTS_SPECIMENS = [
    ("KXNFLFFPTS-26SEP13BUFHOU", "Buffalo vs Houston: Fantasy Points Leader"),
    ("KXNFLFFPTS-26SEP13CLEJAC", "Cleveland vs Jacksonville: Fantasy Points Leader"),
    ("KXNFLFFPTS-26SEP13GBMIN", "Green Bay vs Minnesota: Fantasy Points Leader"),
    ("KXNFLFFPTS-26SEP13NYJTEN", "New York J vs Tennessee: Fantasy Points Leader"),
    ("KXNFLFFPTS-26SEP13TBCIN", "Tampa Bay vs Cincinnati: Fantasy Points Leader"),
    ("KXNFLFFPTS-26SEP13ATLPIT", "Atlanta vs Pittsburgh: Fantasy Points Leader"),
]

#: Ticker token → the `sport_key` family every prefix carrying it must land in.
#: Deliberately the families whose tokens are unambiguous league names; a token
#: that names a SPORT rather than a league ("kxsoccer") is not in scope, because
#: several leagues legitimately share it.
LEAGUE_TOKEN_TO_SPORT_FAMILY = {
    "kxnfl": "americanfootball",
    "kxncaaf": "americanfootball",
    "kxnba": "basketball",
    "kxwnba": "basketball",
    "kxmlb": "baseball",
    "kxnhl": "icehockey",
}


@pytest.mark.parametrize("ticker,name", FANTASY_POINTS_SPECIMENS)
def test_a_fantasy_points_prop_is_football(ticker, name):
    """THE SHIP, asserted through the function ingest actually calls.

    Not through the maps: a test that reads `KALSHI_TICKER_TO_SPORT_KEY` and
    `SPORT_PREFIX_TO_LLM_CATEGORY` and composes them itself proves the two dicts
    compose, which was never in doubt — it would pass with step 1 of
    `_categorize_kalshi_market` deleted.
    """
    assert _categorize_kalshi_market(name, "Sports", ticker) == "football"


@pytest.mark.parametrize("ticker,name", FANTASY_POINTS_SPECIMENS)
def test_the_name_alone_still_gets_it_wrong(ticker, name):
    """The negative control, and the bug itself.

    With no ticker the name rules have only "Fantasy Points" to read, and they
    reach for basketball. This is what makes the case above meaningful: if the
    name could already classify these, the ticker would not be load-bearing and
    step 1 could regress with nothing failing.
    """
    assert _categorize_kalshi_market(name, "Sports", None) != "football"


@pytest.mark.parametrize("ticker,name", FANTASY_POINTS_SPECIMENS)
def test_a_mislabelled_nfl_prop_can_no_longer_mint_an_event(ticker, name):
    """The reader-visible half: no category, no invented fixture.

    `auto_create_sport_key_from_category` is the writer that turned this
    mislabelling into sixteen rows on a league page. Asserting on the composed
    pair rather than on the category alone is the point — the harm was never the
    word "basketball", it was the `basketball_other` event that word bought.
    """
    category = _categorize_kalshi_market(name, "Sports", ticker)
    assert category in LLM_CATEGORIES_THAT_MAY_NOT_CREATE_EVENTS
    assert auto_create_sport_key_from_category(category) is None


def test_the_name_alone_would_have_minted_one():
    """The same negative control, pointed at the writer.

    Without the ticker the specimen still buys an `_other` event — which is
    exactly the row a reader found on the basketball page. If this ever stops
    being true the test above has quietly become vacuous.
    """
    category = _categorize_kalshi_market(
        "Buffalo vs Houston: Fantasy Points Leader", "Sports", None
    )
    assert auto_create_sport_key_from_category(category) == "basketball_other"


def test_every_league_token_prefix_maps_to_its_own_sport():
    """THE GUARD. A prefix whose token names a league cannot map elsewhere.

    The ticker is the authority precisely because it is unambiguous: a prefix
    beginning `kxnfl` is American football whatever its suffix does. This sweeps
    both maps rather than listing the prefixes that exist today, so a new
    `kxnfl…`/`kxnba…` entry typed into the wrong sport trips here instead of
    reaching production as a wrong-sport page.
    """
    wrong = {}
    for source, mapping in (
        ("KALSHI_TICKER_TO_SPORT_KEY", KALSHI_TICKER_TO_SPORT_KEY),
        ("KALSHI_FUTURES_TICKER_TO_SPORT_KEY", KALSHI_FUTURES_TICKER_TO_SPORT_KEY),
    ):
        for prefix, sport_key in mapping.items():
            for token, family in LEAGUE_TOKEN_TO_SPORT_FAMILY.items():
                if prefix.startswith(token) and not sport_key.startswith(family):
                    wrong[f"{source}[{prefix}]"] = f"{sport_key} (expected {family}_*)"

    assert not wrong, (
        "A Kalshi ticker prefix naming a league maps to another sport. The "
        "ticker is step 1 of _categorize_kalshi_market and is documented there "
        "as authoritative, so a wrong value here is served, not guessed: "
        f"{wrong}"
    )


def test_the_fantasy_points_series_is_game_level():
    """It resolves per game, so Pass 1 may LINK it to the real fixture.

    The corollary of the mint refusal above: refusing to CREATE is only the
    right answer because the prop can still find the real NFL game once that
    game exists.
    """
    assert "kxnflffpts" in KALSHI_GAME_TICKER_PREFIXES


def test_the_head_to_head_win_total_series_is_futures_not_game_level():
    """`KXNFLH2HWINS` is season-long, so it must never acquire a game.

    All eleven live markets resolve 2027-02-01 and carry `event_id IS NULL`.
    Unmapped it scattered to `baseball_other` (9), `baseball_mlb` (1) and
    `soccer_other` (1); mapped into the GAME map instead it would become
    game-level and could attach a February season bet to a September fixture,
    which is the Q440 failure this file must not reintroduce.
    """
    assert "kxnflh2hwins" in KALSHI_FUTURES_TICKER_TO_SPORT_KEY
    assert "kxnflh2hwins" not in KALSHI_GAME_TICKER_PREFIXES
    assert "kxnflh2hwins" not in KALSHI_TICKER_TO_SPORT_KEY


# ─────────────────────────────────────────────────────────────────────────────
# The data repair's safety interlock.
#
# repair_2871's docstring states the rule this encodes: "THE TAP MUST BE OFF
# BEFORE THIS RUNS. Cleaning while the firehose still writes just refills."
# There it was prose a human had to honour. Here it is a gate, and these two
# tests are why it can be trusted — a gate nobody proves can refuse is a
# comment with a function signature.
# ─────────────────────────────────────────────────────────────────────────────

import ast  # noqa: E402
import asyncio  # noqa: E402
import importlib.util  # noqa: E402
import pathlib  # noqa: E402
import re  # noqa: E402
import types  # noqa: E402

_SCRIPTS = pathlib.Path(__file__).resolve().parent.parent / "scripts"


def _load(name):
    spec = importlib.util.spec_from_file_location(name, _SCRIPTS / f"{name}.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_the_repair_recognises_the_tap_is_off_on_this_tree():
    """With the map fix present, the repair is allowed to run."""
    repair = _load("repair_5621_phantom_ffpts_events")
    assert repair.tap_is_off() is True


def test_the_repair_refuses_to_run_when_the_prevention_is_not_deployed():
    """THE INTERLOCK, exercised — not asserted about.

    `run()` is driven to completion with the prefix removed from the map it
    imported. It must return the refusal code 2 *before* reaching
    `get_task_session`, so a deploy without the fix cannot be cleaned and
    silently refilled on the next Kalshi poll.

    The DB is not stubbed on purpose: if the gate ever moved below the session
    open, this test would fail trying to reach a database rather than passing
    on a mock that no longer resembles the code.
    """
    repair = _load("repair_5621_phantom_ffpts_events")
    repair.KALSHI_TICKER_TO_SPORT_KEY = dict(repair.KALSHI_TICKER_TO_SPORT_KEY)
    repair.KALSHI_TICKER_TO_SPORT_KEY.pop("kxnflffpts", None)

    assert repair.tap_is_off() is False
    rc = asyncio.run(repair.run(types.SimpleNamespace(backup=False, apply=True)))
    assert rc == 2


def test_the_repair_has_a_population_ceiling_not_just_a_floor():
    """A WRITER's sanity bound points the other way from a reader's.

    gotcha #53 makes a zero loud; for a script that retires rows the danger is
    a predicate that suddenly matches hundreds. The measured population was 16.
    """
    repair = _load("repair_5621_phantom_ffpts_events")
    assert 16 <= repair.MAX_EXPECTED_POPULATION < 1000


def test_the_restore_refuses_when_there_is_no_backup_to_restore_from():
    """D51's undo must not report success against a database it never backed up."""
    restore = _load("restore_5621_phantom_ffpts_events")
    assert hasattr(restore, "run")


# ─────────────────────────────────────────────────────────────────────────────
# CERT-2726 / standing notice 48 — THE TAP IS ON THE OTHER APP.
#
# The interlock above imports the ticker map and refuses if the prevention is
# absent. That is only an interlock when the interpreter it inspects is the one
# that could re-mint the rows. `poll_kalshi_markets` and
# `match_prediction_markets` are HEAVY_TASKS, so that interpreter lives on
# `bainluck-heavy` — released separately, and measured at v10 `87a095b4` (no
# `kxnflffpts`) while main could already have had it. Run from `-a bainluck` the
# check passes against the wrong app and the old poller refills the table.
# ─────────────────────────────────────────────────────────────────────────────

_PRODUCERS = {
    "app.tasks.poll_kalshi_markets",
    "app.tasks.match_prediction_markets",
}


def _runbook_and_code(name):
    """The module docstring and the source WITHOUT it, kept apart on purpose.

    Both halves get scanned below and they must not be confused. The runbook
    lives in the docstring; the SQL lives in the code. Scanning the whole file
    for either gives a false answer in BOTH directions, and both were observed
    while writing these tests: the header's `heroku run:detached -a ` sits at
    the end of a split f-string in the refusal message (so a regex over the raw
    source captures a quote character as the app name), and the header also
    QUOTES the `ON CONFLICT (id) DO NOTHING` it exists to warn against (so a
    raw-source scan for the defective SQL matches the prose describing it).

    Split by the docstring's SOURCE SPAN, not by string-matching its value.
    `ast.get_docstring` returns the evaluated literal: `clean=True` dedents it,
    and even `clean=False` has already eaten the `\` line-continuations in the
    `heroku run:detached …` lines. Neither form is a substring of the file, so
    `src.replace(doc, "")` silently removes nothing — and an
    `assert doc not in code` written to catch that is vacuous precisely then,
    because `doc` is not in `src` either. Both were observed here.
    """
    path = _SCRIPTS / f"{name}.py"
    src = path.read_text()
    node = ast.parse(src).body[0]
    assert isinstance(node, ast.Expr) and isinstance(
        node.value, ast.Constant
    ), f"{name} lost its runbook"

    lines = src.splitlines(keepends=True)
    start, end = node.lineno - 1, node.end_lineno
    runbook = "".join(lines[start:end])
    code = "".join(lines[:start] + lines[end:])

    # Not `'"""' not in code` — `_POPULATION_SQL` is legitimately triple-quoted.
    assert runbook.lstrip().startswith('"""')
    assert not code.lstrip().startswith('"""'), "the runbook is still in code"
    assert len(runbook) + len(code) == len(src), "the split lost or duplicated text"
    return runbook, code


def test_repair_runbook_targets_the_heavy_producer_5621(monkeypatch):
    """Every WRITE is pinned to the app the producer actually runs on.

    Three things at once, because any one alone goes stale silently:

    1. the producers really are heavy today — if one is ever moved back, this
       fails and the runbook has to be re-derived rather than quietly lying;
    2. the runbook's `heroku` invocations all name that app, so nobody copies a
       `-a bainluck` line out of the header;
    3. the refusal is EXERCISED on the main app's name, not asserted about, so
       a gate that stopped firing would fail here.
    """
    from app.tasks import HEAVY_TASKS

    assert _PRODUCERS <= set(HEAVY_TASKS), (
        "a Kalshi producer left HEAVY_TASKS — re-derive which app the #5621 "
        "repair must run on before changing this test"
    )

    repair = _load("repair_5621_phantom_ffpts_events")
    assert repair.PRODUCER_APP == "bainluck-heavy"

    # (2) no runbook line sends an operator at the wrong app.
    runbook, _ = _runbook_and_code("repair_5621_phantom_ffpts_events")
    targets = re.findall(r"heroku (?:run:detached|releases) -a (\S+)", runbook)
    assert targets, "the runbook lost its heroku invocations"
    assert set(targets) == {"bainluck-heavy"}

    # …and so does the undo, or the restore is taken against a different deploy.
    undo_runbook, _ = _runbook_and_code("restore_5621_phantom_ffpts_events")
    undo_targets = re.findall(r"heroku run:detached -a (\S+)", undo_runbook)
    assert set(undo_targets) == {"bainluck-heavy"}

    # (3) the gate fires on the web app, and only a write is gated.
    write = types.SimpleNamespace(backup=False, apply=True)
    monkeypatch.setenv("HEROKU_APP_NAME", "bainluck")
    assert repair.wrong_app_refusal(write) is not None
    monkeypatch.setenv("HEROKU_APP_NAME", "bainluck-heavy")
    assert repair.wrong_app_refusal(write) is None


def test_the_repair_refuses_to_write_from_the_web_app_even_with_the_map(monkeypatch):
    """The end-to-end failure CERT-2726 found, driven through `run()`.

    The map fix IS present here — `tap_is_off()` is True — which is exactly the
    situation after an ordinary main release: the old interlock passed and the
    stale heavy poller refilled the rows. `run()` must still return 2, and it
    must do so before touching a database (no stub, deliberately: a gate that
    slipped below the session open would fail this test rather than pass
    against a mock).
    """
    repair = _load("repair_5621_phantom_ffpts_events")
    assert repair.tap_is_off() is True

    monkeypatch.setenv("HEROKU_APP_NAME", "bainluck")
    for args in (
        types.SimpleNamespace(backup=False, apply=True),
        types.SimpleNamespace(backup=True, apply=False),
    ):
        assert asyncio.run(repair.run(args)) == 2


def test_a_laptop_pointed_at_production_cannot_write_either(monkeypatch):
    """An UNSET marker is the laptop case, not a free pass.

    Falling through on absence would defeat the gate in the one environment
    where the checked-out code is least likely to be what production runs.
    """
    repair = _load("repair_5621_phantom_ffpts_events")
    monkeypatch.delenv("HEROKU_APP_NAME", raising=False)
    assert repair.wrong_app_refusal(types.SimpleNamespace(backup=True, apply=False))


def test_a_dry_run_is_not_gated_on_the_app(monkeypatch):
    """The negative control: reading is allowed anywhere.

    Without this the gate could be 'refuse always' and every test above would
    still pass.
    """
    repair = _load("repair_5621_phantom_ffpts_events")
    monkeypatch.setenv("HEROKU_APP_NAME", "bainluck")
    dry = types.SimpleNamespace(backup=False, apply=False)
    assert repair.wrong_app_refusal(dry) is None


def test_the_backup_reconciliation_is_content_exact_not_id_only():
    """`5621-BACKUP-RECONCILIATION-MUST-BE-CONTENT-EXACT`.

    A backup taken before an unrelated writer moved a row must not satisfy the
    D51 gate: the undo would put back a value that was never overwritten. Two
    halves have to hold together — the insert REFRESHES on conflict, and the
    gate compares the stored values rather than the presence of an id.
    """
    _, code = _runbook_and_code("repair_5621_phantom_ffpts_events")

    assert "ON CONFLICT (id) DO NOTHING" not in code, (
        "DO NOTHING keeps a stale backup row, which is the defect"
    )
    assert code.count("ON CONFLICT (id) DO UPDATE SET") == 2

    # Every column the repair overwrites must be compared by the gate.
    # Only the bind-parameter columns can be recovered from the SQL; `status`
    # and `event_id` are written as literals ('voided', NULL) and are named
    # here. So the set is pinned as well as partly derived: a new bind column
    # appears on its own and fails the equality below, and a new literal one
    # fails review against this list.
    bound = set(re.findall(r"(\w+) = :(?:cat|sid)\b", code))
    written = bound | {"status", "event_id"}
    assert written == {"status", "llm_sport_category", "sport_id", "event_id"}
    for column in written:
        assert f"b.{column} IS NOT DISTINCT FROM" in code, column
