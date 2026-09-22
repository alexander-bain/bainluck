"""#8084 arm C — a college feed spelling "Ohio St." finds the key "Ohio State" holds.

Arms A and B were about the WRITE side: arm A (#8085) about which rows the
`ILIKE` loads, arm B (#8094) about a winning row that carries no crest. This is
the READ side, and it is a third mechanism with no code in common: the rows are
loaded, a correct row holds a correct key with a crest in it, and the grid asks
for a DIFFERENT STRING and gets nothing. Measured on production 2026-09-22,
`/playoffs/ncaa-women-basketball` serves 30 rows of which exactly two render as
bare text:

    Ohio St.   ->  grid key `ohio st`    ;  the crest sits under `ohio state`
    Iowa St.   ->  grid key `iowa st`    ;  the crest sits under `iowa state`

`normalize_team_name_for_matching` is the repo's canonical college form and has
expanded a non-leading "st" since #7559 — the market → event matcher,
`authority_name_forms` and the twin fold all use it. `playoffs.py` is the one
caller that never adopted it.

WHY THIS CANNOT WIDEN THE MATCH. The new rung fires only when the first two find
NOTHING, and it looks the label up in the SAME dict `_get_team_metadata` already
built. It cannot create a key, move one, or change which row won one:
`_alias_may_claim` and `_alias_contest_winner` ran first and a row they refused
was never written, so it is unreachable here. That is arm B's safety argument
run on the read side.

THE DANGEROUS ROW. `teams` row 14627 is NAMED `Ohio State` while carrying Penn
State's identity — espn_id 414, abbreviation `PSU`, alternates
`Penn State Nittany Lions`. It is therefore the canonical OWNER of the key this
rung reaches for, and serving it on an Ohio State row is #7727 exactly. It loses
on scope, not on luck, and `test_penn_state_row_named_ohio_state_never_wins_the_key`
is the reason this file exists at all. Half of these tests exist to hold the
line that the rung DECLINES — a bare row is a far smaller harm than a wrong
crest.
"""

import pytest

from app.routes.playoffs import _get_team_metadata, _team_meta_for_label

OSU_CREST = "https://a.espncdn.com/i/teamlogos/ncaa/500/194.png"
ISU_CREST = "https://a.espncdn.com/i/teamlogos/ncaa/500/66.png"
PSU_CREST = "https://a.espncdn.com/i/teamlogos/ncaa/500/213.png"
UNC_CREST = "https://a.espncdn.com/i/teamlogos/ncaa/500/153.png"

WNCAAB = "ncaa-women-basketball"


class _FakeSport:
    def __init__(self, key):
        self.key = key


class _FakeTeam:
    """Only the attributes `_get_team_metadata` reads."""

    def __init__(
        self,
        team_id,
        name,
        sport_key,
        espn_id=None,
        abbreviation=None,
        alternate_names=None,
        record=None,
        logo=None,
        primary_color=None,
    ):
        self.id = team_id
        self.name = name
        self.sport = _FakeSport(sport_key)
        self.espn_id = espn_id
        self.abbreviation = abbreviation
        self.alternate_names = list(alternate_names or [])
        self.current_record = record
        self.logo_url_small = logo
        self.logo_url_large = None
        self.primary_color = primary_color
        self.secondary_color = None
        self.standings_data = None


class _FakeScalars:
    def __init__(self, rows):
        self._rows = rows

    def all(self):
        return list(self._rows)


class _FakeResult:
    def __init__(self, rows):
        self._rows = rows

    def scalars(self):
        return _FakeScalars(self._rows)


class _FakeSession:
    def __init__(self, rows):
        self._rows = rows

    async def execute(self, _stmt):
        return _FakeResult(self._rows)


async def _lookup(rows, league_slug=WNCAAB):
    return await _get_team_metadata(
        _FakeSession(rows), {"probe"}, league_slug=league_slug
    )


# --- The production specimens, as production holds them ---------------------
#
# Verified against `teams` on 2026-09-22 via /api/admin/db-query: ids, sport
# keys, espn_ids, abbreviations and alternate_names are the real values.


def _ohio_state_wncaab():
    """Row 68 — the real Ohio State, in scope for the women's basketball grid."""
    return _FakeTeam(
        68,
        "Ohio State Buckeyes",
        "basketball_wncaab",
        espn_id="194",
        abbreviation="OSU",
        alternate_names=["Ohio State", "Buckeyes"],
        record="14-2",
        logo=OSU_CREST,
        primary_color="#ba0c2f",
    )


def _penn_state_row_named_ohio_state():
    """Row 14627 — NAMED `Ohio State`, but it is Penn State (espn 414, `PSU`).

    The canonical owner of the key `ohio state`, and the whole reason this rung
    needs a test rather than an argument.
    """
    return _FakeTeam(
        14627,
        "Ohio State",
        "baseball_ncaa",
        espn_id="414",
        abbreviation="PSU",
        alternate_names=["Nittany Lions", "Penn State Nittany Lions", "Penn State"],
        record="31-22",
        logo=PSU_CREST,
        primary_color="#29294a",
    )


def _ohio_state_ncaab():
    """Row 198 — the same club in men's basketball; out of scope here."""
    return _FakeTeam(
        198,
        "Ohio State Buckeyes",
        "basketball_ncaab",
        espn_id="194",
        abbreviation="OSU",
        alternate_names=["Ohio State", "Buckeyes"],
        logo=OSU_CREST,
        primary_color="#ba0c2f",
    )


def _iowa_state_wncaab():
    return _FakeTeam(
        2844,
        "Iowa State Cyclones",
        "basketball_wncaab",
        espn_id="66",
        abbreviation="ISU",
        alternate_names=["Cyclones", "Iowa State"],
        record="11-5",
        logo=ISU_CREST,
        primary_color="#ae192d",
    )


def _iowa_state_ncaab():
    return _FakeTeam(
        165,
        "Iowa State Cyclones",
        "basketball_ncaab",
        espn_id="66",
        abbreviation="ISU",
        alternate_names=["Cyclones", "Iowa State"],
        logo=ISU_CREST,
    )


def _unc_wncaab():
    """Row 71 — holds `north carolina`. NC State is a DIFFERENT school."""
    return _FakeTeam(
        71,
        "North Carolina Tar Heels",
        "basketball_wncaab",
        espn_id="153",
        abbreviation="UNC",
        alternate_names=["Tar Heels", "North Carolina"],
        logo=UNC_CREST,
    )


def _grambling_st_bare():
    """Row 1129 — matches its key and carries nothing. Arm B declines it too."""
    return _FakeTeam(1129, "Grambling St Tigers", "basketball_wncaab")


def _grambling_state_crested():
    """A crested row under the EXPANDED spelling. Must stay unreachable."""
    return _FakeTeam(
        13746,
        "Grambling State Tigers",
        "baseball_ncaa",
        espn_id="2755",
        logo="https://a.espncdn.com/i/teamlogos/ncaa/500/2755.png",
    )


# --- The ship ---------------------------------------------------------------


@pytest.mark.asyncio
async def test_ohio_st_label_reaches_the_ohio_state_key():
    """The reader's row stops being bare: `Ohio St.` finds row 68's crest."""
    meta = await _lookup(
        [_ohio_state_wncaab(), _penn_state_row_named_ohio_state(), _ohio_state_ncaab()]
    )

    # Rung 1 and rung 2 both miss — this is the defect, stated as a fact.
    assert meta.get("ohio st") is None

    served = _team_meta_for_label(meta, "ohio st", "Ohio St.")
    assert served.get("logo_url") == OSU_CREST
    assert served.get("team_id") == 68


@pytest.mark.asyncio
async def test_iowa_st_label_reaches_the_iowa_state_key():
    meta = await _lookup([_iowa_state_wncaab(), _iowa_state_ncaab()])

    assert meta.get("iowa st") is None

    served = _team_meta_for_label(meta, "iowa st", "Iowa St.")
    assert served.get("logo_url") == ISU_CREST
    assert served.get("team_id") == 2844


# --- #7727: the rung must never serve another school's crest ----------------


@pytest.mark.asyncio
async def test_penn_state_row_named_ohio_state_never_wins_the_key():
    """Scope, not `id`, decides — so the rung reaches row 68 and not row 14627.

    Row 14627 is the canonical owner of `ohio state` and has the higher `id`,
    which is the pair of facts that would decide it if scope did not. If this
    ever fails, the women's basketball grid is printing a PENN STATE crest,
    `PSU` and a 31-22 baseball record on Ohio State's row.
    """
    meta = await _lookup(
        [_ohio_state_wncaab(), _penn_state_row_named_ohio_state(), _ohio_state_ncaab()]
    )

    served = _team_meta_for_label(meta, "ohio st", "Ohio St.")

    assert served.get("espn_id") == "194"
    assert served.get("espn_id") != "414"
    assert served.get("abbreviation") != "PSU"
    assert served.get("logo_url") != PSU_CREST
    assert "Penn State" not in (served.get("name") or "")


@pytest.mark.asyncio
async def test_north_carolina_st_declines_rather_than_taking_the_tar_heels():
    """`North Carolina St.` expands to a key nobody holds, and that is the answer.

    Ours is `NC State Wolfpack`, so nothing in the loaded set answers to
    `north carolina state`. The crested `North Carolina Tar Heels` row IS
    loaded and holds `north carolina` — a rung that reached for the nearest
    similar name would serve UNC's crest on NC State's row. The row stays bare.
    """
    meta = await _lookup([_unc_wncaab()])

    served = _team_meta_for_label(meta, "north carolina st", "North Carolina St.")

    assert served == {}
    assert served.get("logo_url") is None


def test_a_leading_st_is_never_expanded_into_a_state_school():
    """"St. Louis" is Saint Louis, not a state school, so the rung must miss it.

    The label is given NOTHING to match at rungs 1 and 2, so rung 3 is the only
    one that can answer — and a `state louis` key is sitting right there for it.
    An expansion that treated a LEADING "st" like a trailing one would serve
    that row on the Cardinals', the Blues' and St. Louis City SC's rows alike.
    """
    wrong = {"team_id": 9999, "logo_url": "https://example.invalid/state-louis.png"}

    assert _team_meta_for_label({"state louis": wrong}, "absent", "St. Louis") == {}
    assert _team_meta_for_label({"state louis": wrong}, "absent", "St Louis") == {}

    # The trailing case is the one that DOES expand — same helper, same call.
    right = {"team_id": 1, "logo_url": OSU_CREST}
    assert _team_meta_for_label({"ball state": right}, "absent", "Ball St.") == right


# --- The rung is MISS-ONLY, which is what stops it widening anything --------


@pytest.mark.asyncio
async def test_a_row_that_already_resolves_never_consults_the_college_form():
    """`Grambling St Tigers` matches its own key and carries nothing.

    A crested `Grambling State Tigers` row is loaded. If the rung fired on a
    row that merely lacks a CREST rather than one that resolves to NOTHING, it
    would reach across to a different key and guess. Arm B already declined
    this row for the same reason; the read side must decline it too.
    """
    meta = await _lookup([_grambling_st_bare(), _grambling_state_crested()])

    served = _team_meta_for_label(meta, "grambling st tigers", "Grambling St Tigers")

    assert served.get("team_id") == 1129
    assert served.get("logo_url") is None


def test_the_three_rungs_are_tried_in_order():
    """Grid key beats label beats college form, and each only on the miss."""
    team_meta = {
        "by key": {"team_id": 1},
        "by label": {"team_id": 2},
        "by college form": {"team_id": 3},
    }

    # Rung 1 answers.
    assert _team_meta_for_label(
        {"grid key": {"team_id": 1}}, "grid key", "Grid Key"
    ) == {"team_id": 1}

    # Rung 1 misses, rung 2 answers on the normalized label.
    assert _team_meta_for_label(
        {"ball st": {"team_id": 2}}, "absent", "Ball St."
    ) == {"team_id": 2}

    # Rungs 1 and 2 miss, rung 3 answers on the expanded college form.
    assert _team_meta_for_label(
        {"ball state": {"team_id": 3}}, "absent", "Ball St."
    ) == {"team_id": 3}

    # Nothing answers.
    assert _team_meta_for_label(team_meta, "absent", "Also Absent") == {}

    # No label to fall back on: rung 1 is the whole chain.
    assert _team_meta_for_label({"ball state": {"team_id": 3}}, "absent", None) == {}
