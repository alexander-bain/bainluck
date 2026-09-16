"""#5657 — the API stops serving a sport's machine key as its display name.

Alex met this on a physical phone on 2026-09-15 (#6444 intake, *"Search shows
raw `baseball_other`"*).  Reproduced on production v4601 at 23:2xZ:

    GET /api/events/search?q=Red Sox
      sports: [{"key": "baseball_mlb",   "name": "MLB",            "count": 21},
               {"key": "baseball_other", "name": "baseball_other", "count": 1},
               {"key": "baseball_milb",  "name": "MiLB",           "count": 1}]

    GET /api/events/15310222  ->  "sport_name": "baseball_other"

15 of 177 `sports` rows store the raw key as their display `name`, and the
payload hands it straight to a reader.

WHY THE SERVER AND NOT A CLIENT.  Native's `sportKeyDisplayName` is "the served
name when the page has it, otherwise the app's own shared rule" (#5723/#5780) —
a deliberate decision, and a correct one, so the non-empty served name wins and
the raw key prints.  The web never reads the name at all: `getLeagueDisplay`
derives `Other ${family}` from the KEY, and its own comment says *"the server
has no word for those"*.  Same payload, two answers — the web chip reads "Other
Baseball" while the app reads `baseball_other`.  Giving the server the word is
what makes the two tiers print one thing, which is why
`test_the_family_words_are_webs_own_not_ours` reads the frontend constant rather
than restating it.

BOTH ARMS, EVERY GUARD.  "No underscore in the output" alone passes for a
formatter reduced to serving `None`, and "the brand survives" alone passes for
one that changed nothing.  Each test below carries the positive and the control.
"""

from __future__ import annotations

import ast
import re
from datetime import datetime, timezone
from pathlib import Path

import pytest

from app.models import Event, Sport
from app.routes.events import _format_event, _sport_facet_labels
from app.utils.sport_keys import (
    SPORT_PREFIX_TO_DISPLAY_FAMILY,
    sport_display_name,
)

#: Every `sports` row on production whose `name` equals its `key`, read
#: 2026-09-15 23:3xZ (`SELECT key, name FROM sports WHERE name = key`).  Pinned
#: as data rather than derived so this guard keeps testing the real population
#: and not whatever rule the helper happens to implement.
RAW_NAMED_KEYS = (
    "americanfootball_other",
    "baseball_other",
    "basketball_other",
    "boxing_other",
    "cricket_other",
    "esports",
    "esports_other",
    "golf_other",
    "icehockey_other",
    "lacrosse_other",
    "mma_other",
    "motorsport_other",
    "rugby_other",
    "soccer_other",
    "tennis_other",
)

#: The control arm: real brands from the same table.  If a repair "fixes" the 15
#: by rewriting everything, these are what catch it.  `Tennis Atp` is included
#: deliberately — it is clumsy, it is the server's, and it is NOT this ship's to
#: improve (native's `properTitleCase` owns that).
BRANDED = {
    "baseball_mlb": "MLB",
    "baseball_milb": "MiLB",
    "americanfootball_nfl": "NFL",
    "icehockey_sweden_hockey_league": "SHL",
    "tennis_atp": "Tennis Atp",
    "soccer_epl": "EPL",
}

_FRONTEND_CATEGORIES = (
    Path(__file__).resolve().parents[2] / "frontend" / "lib" / "sportCategories.ts"
)


def _sport_event(key: str, name: str | None) -> Event:
    return Event(
        id=15310222,
        sport_id=1,
        sport=Sport(id=1, key=key, name=name),
        home_team_name="Boston Red Sox",
        away_team_name="Texas Rangers",
        commence_time=datetime(2026, 9, 18, 0, 5, tzinfo=timezone.utc),
        status="scheduled",
        home_score=None,
        away_score=None,
    )


# ── the ship ────────────────────────────────────────────────────────────────


@pytest.mark.parametrize("key", RAW_NAMED_KEYS)
def test_no_sport_serves_its_own_key_as_a_name(key):
    """The defect itself, on all 15 rows that carry it."""
    served = sport_display_name(key, key)

    assert served is not None, key
    assert served != key, key
    assert "_" not in served, f"{key} -> {served!r} still wears a machine key"


@pytest.mark.parametrize("key", RAW_NAMED_KEYS)
def test_a_reader_gets_real_words_not_a_shortened_key(key):
    """#5780's lesson: filing the family off a key is not naming it.

    `baseball_other` -> "Other" or "OTHER" would pass a no-underscore check and
    put two identical chips on one page, which is the failure `getLeagueDisplay`
    records in its own comment.
    """
    served = sport_display_name(key, key)

    assert served not in {"Other", "OTHER", "other"}, key
    # Every word is a word, not a token: no leftover casing from the enum.
    assert served == served.strip()
    assert not any(part.isupper() and part.islower() for part in served)
    assert re.fullmatch(r"[A-Za-z&' ]+", served), f"{key} -> {served!r}"


@pytest.mark.parametrize("key,brand", sorted(BRANDED.items()))
def test_a_real_brand_passes_through_byte_for_byte(key, brand):
    """The control.  162 of 177 rows must be untouched by this change."""
    assert sport_display_name(key, brand) == brand


def test_the_only_rejected_value_is_the_key_itself():
    """The contract that keeps ~18 test modules' bare `Sport(key=…)` stubs green.

    `_format_event` degrades `sport_name` to `None` on purpose so a caller with
    no stored name serves nothing and the clients fall back to their own maps.
    Widening the helper to "derive whenever the name is missing" is a different
    ship; this asserts it did not happen by accident.
    """
    assert sport_display_name("baseball_mlb", None) is None
    assert sport_display_name("baseball_mlb", "") is None
    assert sport_display_name("baseball_mlb", "   ") is None
    assert sport_display_name(None, None) is None
    # …and a key with no name is still not a licence to invent one.
    assert sport_display_name("soccer_other", None) is None


def test_a_sport_we_have_no_word_for_yet_is_still_not_a_raw_key():
    """A reader may meet an unmapped sport; they may never meet an underscore."""
    assert sport_display_name("pickleball_other", "pickleball_other") == (
        "Other Pickleball"
    )
    assert sport_display_name("kabaddi", "kabaddi") == "Kabaddi"


# ── the payload, not just the helper ────────────────────────────────────────


def test_format_event_serves_the_derived_name_for_the_specimen():
    """`15310222`'s own shape — the row on Alex's phone."""
    payload = _format_event(_sport_event("baseball_other", "baseball_other"))

    assert payload["sport"] == "baseball_other", "the machine key still travels"
    assert payload["sport_name"] == "Other Baseball"


def test_format_event_still_degrades_to_none_for_a_nameless_stub():
    """The control for the arm above — the documented pre-existing contract."""
    assert _format_event(_sport_event("baseball_mlb", None))["sport_name"] is None


def test_format_event_leaves_a_branded_sport_alone():
    payload = _format_event(_sport_event("baseball_mlb", "MLB"))

    assert payload["sport_name"] == "MLB"


# ── the filter pill, which is a SECOND call site ────────────────────────────
#
# The pill is built in `search_events`'s own loop, not by `_format_event`, so
# every assertion above can pass while a reader still taps a chip reading
# `baseball_other`.  That is the exact shape of Alex's screenshot: the chip AND
# the row label, two call sites, one defect.


@pytest.mark.parametrize("key", RAW_NAMED_KEYS)
def test_the_filter_pill_never_reads_a_raw_key(key):
    _, label = _sport_facet_labels(Sport(id=1, key=key, name=key))

    assert label != key
    assert "_" not in label


def test_the_filter_pill_keeps_the_brand_and_the_key_apart():
    """The control: the pill's KEY stays the machine key (the filter needs it)
    while only its label is humanised."""
    facet_key, label = _sport_facet_labels(Sport(id=1, key="baseball_mlb", name="MLB"))

    assert facet_key == "baseball_mlb"
    assert label == "MLB"


def test_the_filter_pill_reproduces_alexs_three_chips():
    """`q=Red Sox`, 2026-09-15 23:2xZ — the payload that put the raw key on a
    phone, now read as a reader would see the row of chips."""
    served = [
        _sport_facet_labels(Sport(id=1, key=key, name=name))[1]
        for key, name in (
            ("baseball_mlb", "MLB"),
            ("baseball_other", "baseball_other"),
            ("baseball_milb", "MiLB"),
        )
    ]

    assert served == ["MLB", "Other Baseball", "MiLB"]


def test_a_sportless_row_still_answers_unknown():
    """Pre-#5657 behaviour, pinned so the extraction did not change it."""
    assert _sport_facet_labels(None) == ("unknown", "Unknown")
    assert _sport_facet_labels(Sport(id=1, key=None, name=None)) == (
        "unknown",
        "Unknown",
    )


# ── the cross-tier guard ────────────────────────────────────────────────────


def _web_family_names() -> dict[str, str]:
    """`{prefix without trailing underscore: display name}` from web's constant.

    Read, never restated: the whole point of this ship is that both tiers print
    one word, and a guard that hard-codes our copy of web's table cannot notice
    the day web renames a family.
    """
    src = _FRONTEND_CATEGORIES.read_text()
    block = re.search(
        r"export const SPORT_CATEGORIES: SportCategory\[\] = \[(.*?)\n\];",
        src,
        re.S,
    )
    assert block, "web's SPORT_CATEGORIES could not be located — guard is blind"

    out: dict[str, str] = {}
    for obj in re.finditer(r"\{(.*?)\},?\n", block.group(1), re.S):
        body = obj.group(1)
        name = re.search(r'name:\s*"([^"]+)"', body)
        prefixes = re.search(r"prefixes:\s*\[([^\]]*)\]", body, re.S)
        if not (name and prefixes):
            continue
        for prefix in re.findall(r'"([^"]+)"', prefixes.group(1)):
            out[prefix.rstrip("_")] = name.group(1)
    return out


def test_the_guard_can_actually_read_webs_constant():
    """Anti-vacuity.  Every assertion below is free if the parse returns {}."""
    assert _FRONTEND_CATEGORIES.exists(), _FRONTEND_CATEGORIES
    web = _web_family_names()

    assert len(web) >= 25, web
    assert web["baseball"] == "Baseball"
    assert web["icehockey"] == "Hockey"


def test_the_family_words_are_webs_own_not_ours():
    """Where both tiers name a family, they must name it the same.

    Not "our table is a superset" — that would pass while disagreeing.  This
    compares values on the intersection, which is where a reader could see two
    different words for one sport.
    """
    web = _web_family_names()
    shared = sorted(set(web) & set(SPORT_PREFIX_TO_DISPLAY_FAMILY))

    assert len(shared) >= 20, f"only {len(shared)} families in common: {shared}"

    disagree = {
        prefix: (SPORT_PREFIX_TO_DISPLAY_FAMILY[prefix], web[prefix])
        for prefix in shared
        if SPORT_PREFIX_TO_DISPLAY_FAMILY[prefix] != web[prefix]
    }
    assert not disagree, f"server/web disagree (ours, theirs): {disagree}"


def test_every_raw_named_key_resolves_through_a_family_web_also_knows():
    """The 15 are exactly the population web already had a word for.

    If a future catch-all appears whose family web cannot name, this fails and
    the next lane adds the word to BOTH tiers rather than shipping two labels.
    """
    web = _web_family_names()

    for key in RAW_NAMED_KEYS:
        prefix = key[: -len("_other")] if key.endswith("_other") else key
        assert prefix in web, f"{key}: web has no family word for {prefix!r}"
        expected = f"Other {web[prefix]}" if key.endswith("_other") else web[prefix]
        assert sport_display_name(key, key) == expected, key


# ── the one surface that must KEEP serving a raw name ───────────────────────


def test_the_sports_detail_route_still_signals_raw():
    """🔴 A raw name is load-bearing on exactly one surface. Do not "finish" this.

    `getSportGroupLabel` (`frontend/lib/sportCategories.ts`) reads "is the served
    name raw?" as its signal that the served `group` is machine-derived too, and
    corrects it.  The signal is real: the same 15 rows carry `Americanfootball`,
    `Icehockey` and `Mma` in `sports.group` (measured on production
    2026-09-15) while their branded siblings carry "Ice Hockey" and
    "Aussie Rules".

    `GET /api/sports/{key}` is the only route that serves that `group`, and it
    is therefore the only one where humanising the name SILENTLY BREAKS a label
    — web would start trusting "Mma".  #5657 changed `_format_event` and the
    search facet, neither of which serves a group, and deliberately left this
    route alone.

    So this guard fails the day someone extends the helper to `sports.py`
    without fixing `group` in the same ship.  If you are that person: fix both,
    then change this test on purpose.
    """
    source = (
        Path(__file__).resolve().parents[1] / "app" / "routes" / "sports.py"
    ).read_text()
    tree = ast.parse(source)

    detail = next(
        node
        for node in ast.walk(tree)
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
        and node.name == "get_sport"
    )
    returned = ast.dump(detail)

    assert '"group"' in source, "the group field vanished — re-read this guard"
    assert "sport_display_name" not in returned, (
        "app/routes/sports.py::get_sport now humanises the sport name. It also "
        "serves `group`, whose machine-derived values ('Mma', 'Icehockey') web "
        "only corrects while the NAME reads raw. Fix `group` in the same ship."
    )


# ── gotcha #3 ───────────────────────────────────────────────────────────────


def test_sport_keys_still_imports_nothing():
    """`sport_keys.py` is the zero-circular-import module and must stay that way."""
    tree = ast.parse(
        (Path(__file__).resolve().parents[1] / "app" / "utils" / "sport_keys.py")
        .read_text()
    )
    imported = {
        node.module.split(".")[0]
        for node in ast.walk(tree)
        if isinstance(node, ast.ImportFrom) and node.module
    } | {
        alias.name.split(".")[0]
        for node in ast.walk(tree)
        if isinstance(node, ast.Import)
        for alias in node.names
    }

    assert imported <= {"typing"}, f"sport_keys.py grew an import: {imported}"
