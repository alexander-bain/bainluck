"""LAT-P043: the interestingness blend fails DARK, not to 0.2.

Alex ruled on 2026-08-12 that the interestingness signal comes back dark until
he has seen a side-by-side at two weights and ratified one. The kill switch is
the Redis key ``interestingness:blend_weight``, set to ``0`` in production the
same day, verified by a direct read (``exists=true, raw="0", ttl=-1``).

The defect this pins: the reader defaulted to **0.2 whenever the key was absent
or unparsable**, so the ruled-off state depended on a cache entry continuing to
exist. Measured on production Redis 2026-08-12T20:38Z — 36.32 MB of 100 MB,
``maxmemory_policy allkeys-lru``, ``evicted_keys 0``, and the switch itself
written with ``ttl -1``. An eviction, a flush, or a plan migration would have
restored a 20% ranking blend that nobody had approved, silently, with nothing
anywhere reporting that it had happened.

A switch whose OFF position is "the key is missing" fails open. These assert it
fails dark instead: to turn the blend on, something must say so explicitly.

The weight itself is still UNCALIBRATED (memory
``project_discover_rank_desaturation``) — that is what the ratification
side-by-side is for. Nothing here argues for a value; it only insists that a
value be chosen out loud.
"""

import ast
import inspect
from pathlib import Path

import app.routes.admin_feed_config as cfg_module
import app.routes.feed as feed_module

_WEIGHT = "_interestingness_blend_weight"


def _weight_literals():
    """Every literal ever assigned to the blend weight in ``feed.py``.

    AST rather than string matching, because the thing that must not come back
    is any *constant* default — whatever its formatting, comment, or arm.
    """
    tree = ast.parse(Path(inspect.getfile(feed_module)).read_text())
    literals = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Assign):
            targets = node.targets
        elif isinstance(node, ast.AnnAssign):
            targets = [node.target]
        else:
            continue
        if not any(getattr(t, "id", None) == _WEIGHT for t in targets):
            continue
        if node.value is not None and isinstance(node.value, ast.Constant):
            literals.append((node.lineno, node.value.value))
    return literals


class TestAnAbsentKeyMeansDark:
    def test_no_nonzero_weight_is_ever_assigned_from_a_literal(self):
        # The only literal the reader may fall back to is zero. A real weight
        # can arrive one way only: by parsing the Redis key.
        nonzero = [(ln, v) for ln, v in _weight_literals() if v]
        assert not nonzero, (
            f"feed.py assigns a literal blend weight at {nonzero} — an evicted "
            "or absent kill switch would silently re-enable a ranking blend "
            "nobody ratified (LAT-P043, Alex 2026-08-12)"
        )

    def test_dark_is_the_state_before_redis_is_even_consulted(self):
        # The load-bearing half of fail-dark, and the reason deleting any one
        # fallback arm is harmless: the weight is initialised to 0.0 BEFORE the
        # lookup, so every path that does not successfully parse a key — absent,
        # corrupt, Redis down, an exception halfway through — is already dark
        # without needing an arm of its own to say so.
        #
        # Asserted with ordering, because an initialiser moved below the read
        # would restore the fail-open shape while still reading as `= 0.0`.
        src = Path(inspect.getfile(feed_module)).read_text()
        init = src.index(f"{_WEIGHT}: float = 0.0")
        read = src.index('get("interestingness:blend_weight")')
        assert init < read, (
            "the blend weight must be initialised dark before the Redis read, "
            "not after it"
        )

    def test_the_gate_that_makes_zero_mean_off_still_exists(self):
        src = Path(inspect.getfile(feed_module)).read_text()
        assert f"if {_WEIGHT} > 0:" in src, (
            "the `> 0` gate is what makes the kill switch a kill switch"
        )

    def test_a_real_weight_can_still_be_parsed_from_the_key(self):
        # Fail-dark must not become cannot-turn-on: the ratified weight needs a
        # path in, and it is this one.
        src = Path(inspect.getfile(feed_module)).read_text()
        anchor = src.index('get("interestingness:blend_weight")')
        window = src[anchor : anchor + 900]
        assert f"{_WEIGHT} = float(" in window, (
            "the key is read but never parsed into the weight — the blend "
            "could not be enabled even by ruling"
        )


class TestTheAdminSurfaceCannotLieAboutIt:
    def test_feed_config_reports_key_presence(self):
        src = Path(inspect.getfile(cfg_module)).read_text()
        assert "key_present" in src, (
            "GET /api/admin/feed-config must distinguish a defaulted read from "
            "a real value — otherwise one string means both 'set to this' and "
            "'no key at all', which is gotcha #53 on the switch itself"
        )

    def test_the_admin_default_matches_the_ranking_default(self):
        src = Path(inspect.getfile(cfg_module)).read_text()
        assert '"interestingness:blend_weight", "0"' in src, (
            "the admin default must match feed.py's, or the surface reports a "
            "weight the ranking code is not using"
        )

    def test_the_ratification_path_stays_open(self):
        src = Path(inspect.getfile(cfg_module)).read_text()
        assert "ALLOWED_KEYS" in src and "interestingness:blend_weight" in src, (
            "setting the weight Alex approves must remain a one-call operation"
        )
