"""#11148 — a state-qualified row label never borrows its stripped base's crest.

🔴 THIS FILE IS NOT THE PROOF. The proof is
``tests/integration/test_grid_miami_oh_row_identity_11148_pg.py``, which drives
the real route on real PostgreSQL and is red on base (two rows named "Miami
Hurricanes", both carrying ``team_id`` 15264's identity, one with Miami (OH)'s
0.0325). This file pins the lookup's refusals with a sentence attached.

Production, 2026-10-16: ``team_meta["miami"]`` is the Hurricanes (their
alternate name ``Miami``). The unbound ``Miami (OH)`` row looked itself up as
``miami`` and wore their crest, ``team_id`` and — through #11065's rename —
their name.
"""

import inspect

from app.routes import playoffs
from app.routes.playoffs import _grid_row_display_name, _team_meta_for_label

HURRICANES = {"team_id": 15264, "name": "Miami Hurricanes", "abbreviation": "MIA"}
REDHAWKS = {"team_id": 15332, "name": "Miami (OH) RedHawks", "abbreviation": "M-OH"}

# The keys `_get_team_metadata` writes on production: own names plus aliases.
META = {
    "miami hurricanes": HURRICANES,
    "miami": HURRICANES,
    "hurricanes": HURRICANES,
    "miami (oh) redhawks": REDHAWKS,
    "redhawks": REDHAWKS,
    "miami oh": REDHAWKS,
}


def test_miami_oh_finds_the_redhawks_by_its_own_text():
    assert _team_meta_for_label(META, "miami (oh)", "Miami (OH)", {"MOH"}) is REDHAWKS
    # The text alone is the anchor; it needs no ticker.
    assert _team_meta_for_label(META, "miami (oh)", "Miami (OH)") is REDHAWKS


def test_miami_oh_never_takes_the_hurricanes_crest():
    """The production defect: no RedHawks row in the lookup, only the base's
    owner. The OH row stays bare rather than wearing the Hurricanes."""
    no_redhawks = {k: v for k, v in META.items() if v is not REDHAWKS}
    assert _team_meta_for_label(no_redhawks, "miami (oh)", "Miami (OH)", {"MOH"}) == {}
    assert _team_meta_for_label(no_redhawks, "miami (oh)", "Miami (OH)") == {}


def test_miami_fl_keeps_the_hurricanes_by_its_own_ticker():
    """No team is NAMED ``Miami (FL)…``, so the textual rung finds nothing; the
    venue's ``MIA`` suffix names the base owner's abbreviation."""
    assert _team_meta_for_label(META, "miami (fl)", "Miami (FL)", {"MIA"}) is HURRICANES


def test_miami_fl_without_a_ticker_is_bare_not_guessed():
    """Polymarket's condition-id legs carry no suffix. Without one the base's
    owner is a guess — and the same guess put the RedHawks' row on the
    Hurricanes."""
    assert _team_meta_for_label(META, "miami (fl)", "Miami (FL)") == {}
    assert _team_meta_for_label(META, "miami (fl)", "Miami (FL)", {"MOH"}) == {}


def test_two_textual_hits_fail_closed():
    meta = dict(META)
    meta["miami (oh) redhawks club"] = {"team_id": 1, "name": "Miami (OH) RedHawks Club"}
    assert _team_meta_for_label(meta, "miami (oh)", "Miami (OH)") == {}


def test_unqualified_labels_resolve_exactly_as_before():
    assert _team_meta_for_label(META, "miami", "Miami") is HURRICANES
    assert _team_meta_for_label(META, "nope", "Miami Hurricanes") is HURRICANES
    assert _team_meta_for_label(META, "miami hurricanes", "anything") is HURRICANES
    # A reserve marker is not a state: still stripped, still resolves.
    assert _team_meta_for_label(META, "x", "Miami (W)") is HURRICANES


def test_the_rename_keeps_the_qualifier():
    """#11065's rename read ``Miami (OH)`` as ``miami``, a whole-word prefix of
    ``Miami Hurricanes``. With the qualifier kept it is not."""
    assert _grid_row_display_name("Miami (OH)", HURRICANES) == "Miami (OH)"
    assert _grid_row_display_name("Miami (OH)", REDHAWKS) == "Miami (OH) RedHawks"
    assert _grid_row_display_name("Miami (FL)", HURRICANES) == "Miami (FL)"
    # #11065's own specimens are unmoved.
    assert _grid_row_display_name("Dallas", {"name": "Dallas Wings"}) == "Dallas Wings"


def test_the_live_row_builder_passes_its_ticker_suffixes():
    """Wiring guard: without the suffixes every ``Miami (FL)`` row left unbound
    would go bare."""
    src = inspect.getsource(playoffs.get_playoff_grid)
    assert "team_meta, norm_name, display_name, ticker_suffixes.get(norm_name, ())" in src
