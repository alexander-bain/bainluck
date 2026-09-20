"""#7419 — a team row sealed around another club's ESPN id can be corrected.

THE READER'S DEFECT. `bainluck.com/sport/football/ncaaf/team/ohio-state-buckeyes-ncaaf`
is titled *Ohio State Buckeyes* and wears the Texas State bobcat crest, Texas
State maroon on every rail and figure, the abbreviation `TXST` and the location
`Texas State`; `wisconsin-badgers-ncaaf` wears Notre Dame's. Both rows carry ONLY
the other club's `alternate_names`, so search reaches them under the wrong club.

WHY THEY COULD NOT HEAL. `upsert_team`'s first guard read

    if team.espn_id and team.espn_id != espn_team.espn_id:
        return team           # "the existing ID is likely correct"

so the one payload that could fix the row — ESPN's own, under the RIGHT id — was
the only payload the rail was guaranteed to discard. The field was its own veto.

WHAT THIS FILE PINS, in both directions:

  * the correction FIRES on the two production specimens, and carries the whole
    identity with it — id, crest, colours, abbreviation, location AND aliases;
  * the refusal is UNCHANGED for a wrong event-level match (the reason the guard
    exists), for the #6974 fragment rows, and for a cross-town rival;
  * `alternate_names` are REPLACED on a correction and UNIONED on a fill;
  * `alternate_names` may not vouch for the payload — the corrupted field cannot
    arbitrate its own corruption;
  * the loose sibling predicate is the WRONG test here, asserted as a measured
    cost rather than described in prose.
"""

import pytest

from app.services.espn_api import ESPNTeam

# THE HELPERS ARE RESOLVED AT CALL TIME, NOT AT IMPORT.
# `espn_payload_renames_the_stored_id` is NEW in the fix commit, so importing it
# at module scope would make this file fail to COLLECT on the parent — pytest
# exit 2 on an ImportError, which is a story about the harness and not a result
# (gotcha #124). The witness that matters is these tests going RED on the parent
# by keeping the foreign identity, and a collection error hides every one of
# them behind a single import line. Same reason and same shape as the #7157
# guard beside this one. It also drops `py/import-of-mutable-attribute`.


def _helpers():
    from app.utils import espn_helpers

    return espn_helpers


def espn_identity_corresponds(*args, **kwargs):
    return _helpers().espn_identity_corresponds(*args, **kwargs)


def espn_payload_renames_the_stored_id(*args, **kwargs):
    return _helpers().espn_payload_renames_the_stored_id(*args, **kwargs)


async def upsert_team(*args, **kwargs):
    return await _helpers().upsert_team(*args, **kwargs)


# ---------------------------------------------------------------------------
# Payloads — the real field shapes ESPN's team directory serves, 2026-09-20.
# ---------------------------------------------------------------------------

def _payload(espn_id, display, name, short, nickname, location, abbr, color, logo):
    return ESPNTeam(
        espn_id=espn_id,
        name=name,
        abbreviation=abbr,
        display_name=display,
        short_name=short,
        nickname=nickname,
        primary_color=color,
        secondary_color="ffffff",
        logo_url=logo,
        logo_url_dark=None,
        record="3-0",
        location=location,
    )


OHIO_STATE = _payload(
    "194", "Ohio State Buckeyes", "Buckeyes", "Ohio State", "Ohio State",
    "Ohio State", "OSU", "bb0000",
    "https://a.espncdn.com/i/teamlogos/ncaa/500/194.png",
)
TEXAS_STATE = _payload(
    "326", "Texas State Bobcats", "Bobcats", "Texas State", "Texas State",
    "Texas State", "TXST", "501214",
    "https://a.espncdn.com/i/teamlogos/ncaa/500/326.png",
)
WISCONSIN = _payload(
    "275", "Wisconsin Badgers", "Badgers", "Wisconsin", "Wisconsin",
    "Wisconsin", "WIS", "c5050c",
    "https://a.espncdn.com/i/teamlogos/ncaa/500/275.png",
)
NOTRE_DAME = _payload(
    "87", "Notre Dame Fighting Irish", "Fighting Irish", "Notre Dame",
    "Notre Dame", "Notre Dame", "ND", "062340",
    "https://a.espncdn.com/i/teamlogos/ncaa/500/87.png",
)
LAKERS = _payload(
    "13", "Los Angeles Lakers", "Lakers", "Lakers", "Lakers",
    "Los Angeles", "LAL", "552583",
    "https://a.espncdn.com/i/teamlogos/nba/500/lal.png",
)
CLIPPERS = _payload(
    "12", "LA Clippers", "Clippers", "Clippers", "Clippers", "LA", "LAC",
    "1d428a", "https://a.espncdn.com/i/teamlogos/nba/500/lac.png",
)
GALAXY = _payload(
    "187", "LA Galaxy", "Galaxy", "Galaxy", "Galaxy", "LA Galaxy", "LA",
    "00245d", "https://a.espncdn.com/i/teamlogos/soccer/500/187.png",
)
MAN_CITY = _payload(
    "382", "Manchester City", "Manchester City", "Man City", "Man City",
    "Manchester", "MNC", "6caee0",
    "https://a.espncdn.com/i/teamlogos/soccer/500/382.png",
)


# ---------------------------------------------------------------------------
# A Team stand-in and a session that cannot answer, so the cache decides.
# ---------------------------------------------------------------------------

class FakeTeam:
    def __init__(self, name, sport_id, espn_id=None, **kw):
        self.id = kw.pop("id", 1)
        self.name = name
        self.sport_id = sport_id
        self.espn_id = espn_id
        self.abbreviation = kw.pop("abbreviation", None)
        self.location = kw.pop("location", None)
        self.primary_color = kw.pop("primary_color", None)
        self.secondary_color = kw.pop("secondary_color", None)
        self.logo_url_small = kw.pop("logo_url_small", None)
        self.logo_url_large = kw.pop("logo_url_large", None)
        self.current_record = kw.pop("current_record", None)
        self.alternate_names = kw.pop("alternate_names", None)


class UnusedSession:
    """The cache answers every lookup, so a DB read here is a test bug.

    Not a silent no-op: a scan reaching this raises, which is how the fixture
    proves the specimen it built is the specimen the code read.
    """

    async def execute(self, *a, **kw):  # pragma: no cover - guard
        raise AssertionError(
            "upsert_team fell through to a DB scan; the cached row was not found"
        )

    def add(self, obj):  # pragma: no cover - guard
        raise AssertionError("upsert_team MINTED a row; it should have found the cache")

    async def flush(self):  # pragma: no cover - guard
        raise AssertionError("upsert_team flushed a mint")


async def _upsert(team, payload, sport_id=7, stats=None):
    cache = {(team.name, sport_id): team}
    returned = await upsert_team(
        UnusedSession(), team.name, payload, sport_id, cache, stats,
    )
    return returned


# ---------------------------------------------------------------------------
# THE SPECIMENS — the correction fires and carries the whole identity.
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
@pytest.mark.parametrize(
    "row_name, stored_id, foreign, correct",
    [
        ("Ohio State Buckeyes", "326", TEXAS_STATE, OHIO_STATE),
        ("Wisconsin Badgers", "87", NOTRE_DAME, WISCONSIN),
    ],
)
async def test_the_production_specimen_takes_back_its_own_identity(
    row_name, stored_id, foreign, correct,
):
    """Production rows 837 and 839, with the exact fields they hold today."""
    team = FakeTeam(
        row_name,
        7,
        espn_id=stored_id,
        abbreviation=foreign.abbreviation,
        location=foreign.location,
        primary_color=f"#{foreign.primary_color}",
        logo_url_small=foreign.logo_url,
        logo_url_large=foreign.logo_url,
        alternate_names=[foreign.display_name, foreign.name],
    )
    stats = {}

    await _upsert(team, correct, stats=stats)

    assert team.espn_id == correct.espn_id
    assert team.abbreviation == correct.abbreviation
    assert team.location == correct.location
    assert team.primary_color == f"#{correct.primary_color}"
    assert team.logo_url_small == correct.logo_url
    assert team.logo_url_large == correct.logo_url
    assert stats["teams_espn_id_corrected"] == 1

    # The aliases go with the id, or search still reaches this row under the
    # other club. Both directions: the foreign ones are GONE and the right ones
    # are THERE — a plain "not in" passes on an empty list.
    assert foreign.display_name not in (team.alternate_names or [])
    assert foreign.name not in (team.alternate_names or [])
    assert correct.name in (team.alternate_names or [])


@pytest.mark.asyncio
async def test_a_correction_clears_foreign_aliases_even_when_espn_sends_none():
    """`if alt_names:` alone would leave the foreign aliases standing.

    A payload whose only club-naming field equals the row's own name contributes
    nothing to `alt_names`, so the union branch would never run and `Notre Dame`
    would survive the correction.
    """
    bare = _payload(
        "275", "Wisconsin Badgers", "Wisconsin Badgers", "Wisconsin Badgers",
        "Wisconsin Badgers", "Wisconsin", "WIS", "c5050c", None,
    )
    team = FakeTeam(
        "Wisconsin Badgers", 7, espn_id="87",
        alternate_names=["Notre Dame", "Fighting Irish"],
    )

    await _upsert(team, bare)

    assert team.espn_id == "275"
    assert team.alternate_names == []


# ---------------------------------------------------------------------------
# THE REFUSAL — unchanged for every shape the guard was built for.
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
@pytest.mark.parametrize(
    "row_name, stored_id, wrong_payload, why",
    [
        ("Ohio State Buckeyes", "194", TEXAS_STATE, "wrong event-level match"),
        ("Wisconsin Badgers", "275", NOTRE_DAME, "wrong event-level match"),
        ("Los Angeles C", "12", LAKERS, "#6974 fragment row, id is CORRECT"),
        ("Los Angeles G", "187", LAKERS, "#6974 fragment row, id is CORRECT"),
        ("Manchester United", "360", MAN_CITY, "cross-town rival"),
    ],
)
async def test_a_payload_that_does_not_name_this_club_still_cannot_take_the_id(
    row_name, stored_id, wrong_payload, why,
):
    team = FakeTeam(
        row_name, 7, espn_id=stored_id,
        abbreviation="KEEP", location="Keep", primary_color="#000000",
        alternate_names=["Keep Me"],
    )
    stats = {}

    await _upsert(team, wrong_payload, stats=stats)

    assert team.espn_id == stored_id, why
    assert team.abbreviation == "KEEP"
    assert team.location == "Keep"
    assert team.primary_color == "#000000"
    assert team.alternate_names == ["Keep Me"]
    assert "teams_espn_id_corrected" not in stats
    assert stats["teams_upserted"] == 1


@pytest.mark.asyncio
async def test_a_matching_id_still_unions_its_aliases_rather_than_replacing_them():
    """The fill path is untouched: a row keeps aliases it already earned."""
    team = FakeTeam(
        "LA Clippers", 7, espn_id="12", alternate_names=["Los Angeles Clippers"],
    )

    await _upsert(team, CLIPPERS)

    assert team.espn_id == "12"
    assert "Los Angeles Clippers" in team.alternate_names
    assert "Clippers" in team.alternate_names


# ---------------------------------------------------------------------------
# THE PREDICATE — pinned directly, including the measured cost of the loose one.
# ---------------------------------------------------------------------------

@pytest.mark.parametrize(
    "row_name, payload, expected",
    [
        ("Ohio State Buckeyes", OHIO_STATE, True),
        ("Wisconsin Badgers", WISCONSIN, True),
        ("Ohio State Buckeyes", TEXAS_STATE, False),
        ("Wisconsin Badgers", NOTRE_DAME, False),
        ("Los Angeles C", LAKERS, False),
        ("Los Angeles C", CLIPPERS, False),
        ("Los Angeles G", GALAXY, False),
        ("Manchester United", MAN_CITY, False),
        ("", OHIO_STATE, False),
        (None, OHIO_STATE, False),
    ],
)
def test_the_override_predicate_answers_by_identity_not_resemblance(
    row_name, payload, expected,
):
    assert espn_payload_renames_the_stored_id(row_name, payload) is expected


def test_a_payload_with_no_club_naming_field_is_refused_on_silence():
    silent = ESPNTeam(
        espn_id="999", name=None, abbreviation="OSU", display_name=None,
        short_name=None, nickname=None, primary_color=None, secondary_color=None,
        logo_url=None, logo_url_dark=None, record=None, location="Ohio State",
    )
    # `location` names a CITY and is excluded on purpose: it is the one field the
    # rival veto cannot protect (see `_ESPN_IDENTITY_LOCATION_FIELD`).
    assert espn_payload_renames_the_stored_id("Ohio State Buckeyes", silent) is False
    assert espn_payload_renames_the_stored_id("Ohio State", silent) is False


def test_the_loose_sibling_predicate_is_the_wrong_test_here():
    """A MEASURED COST, asserted rather than described (2026-09-20).

    This is why the override arm does not reuse `espn_identity_corresponds`: on
    the #6974 fragment rows the loose predicate says yes, and saying yes there
    hands a correct Clippers anchor to the Lakers. If a future change makes
    these agree, the carve-out has stopped paying for itself and this test
    should be re-derived, not deleted.
    """
    assert espn_identity_corresponds("Los Angeles C", None, LAKERS) is True
    assert espn_payload_renames_the_stored_id("Los Angeles C", LAKERS) is False

    assert espn_identity_corresponds("Los Angeles C", None, CLIPPERS) is True
    assert espn_payload_renames_the_stored_id("Los Angeles C", CLIPPERS) is False


def test_poisoned_aliases_may_not_vouch_for_the_payload_that_wrote_them():
    """The corrupted field cannot arbitrate its own corruption.

    Production row 839 carries Notre Dame's names and no Wisconsin alias. The
    loose predicate, handed those aliases, calls a Notre Dame payload a match —
    which is precisely the write that would have to be refused. The override
    predicate never reads them, so there is nothing to poison.
    """
    poisoned = ["Fighting Irish", "Notre Dame Fighting Irish", "Notre Dame"]

    assert espn_identity_corresponds("Wisconsin Badgers", poisoned, NOTRE_DAME) is True
    assert espn_payload_renames_the_stored_id("Wisconsin Badgers", NOTRE_DAME) is False


@pytest.mark.asyncio
async def test_the_seal_is_what_this_fixes_so_prove_the_seal_existed():
    """Before #7419 the correct payload was discarded. Pin the mechanism.

    Not a strawman: this asserts the SHAPE of the old behaviour is gone by
    showing the correct payload now lands, on a row whose every other identity
    field says the other club — the exact state production is in.
    """
    team = FakeTeam(
        "Ohio State Buckeyes", 7, espn_id="326",
        abbreviation="TXST", location="Texas State", primary_color="#501214",
        logo_url_small="https://a.espncdn.com/i/teamlogos/ncaa/500/326.png",
        alternate_names=["Texas State Bobcats", "Bobcats", "Texas St"],
    )

    # Arriving repeatedly changes nothing after the first correction.
    for _ in range(3):
        await _upsert(team, OHIO_STATE)

    assert team.espn_id == "194"
    assert team.abbreviation == "OSU"
    assert "Texas St" not in team.alternate_names
    assert "Bobcats" not in team.alternate_names
