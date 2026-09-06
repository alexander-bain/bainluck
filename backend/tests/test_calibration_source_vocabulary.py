"""#3357 — a published calibration source with no name fails CI, not a reader.

WHY A SCAN AND NOT A LIST.

``/api/calibration``'s ``by_source`` key set is data-driven: it falls out of a
``GROUP BY source`` over live rows, and #3357 records the obstacle plainly —
there was no source-key constant anywhere in the backend to hold a client
against. `app/utils/calibration_source_labels.py` is now that constant, but a
constant checked against nothing is a second hand-maintained map with the same
rot. So the guard recovers the vocabulary from the **producers** and holds the
map against what the code actually emits.

Three rules, each measured against the live payload before being written
(CAL-P1025). Their union is exactly the seven keys production publishes today —
zero misses, zero false positives:

* **A** — a ``source`` string literal in a *FuturesMarket-shaped* construction.
  Recovers ``kalshi`` ``polymarket`` ``datagolf`` ``odds_api``.
* **B** — a ``"source"`` string literal in a *calibration-bucket-shaped* dict
  (one carrying ``bucket_idx``). Recovers ``odds_api_bookmaker``, which is
  produced by a bucket builder and never written to ``futures_markets.source``.
* **C** — ``'x' AS source`` inside a parsed string constant. Recovers
  ``odds_api`` ``odds_api_spreads`` ``odds_api_totals``.

The *unscoped* version of rule A was measured first and rejected: matching every
dict with a ``source`` key returns 33 strings including ``github``, ``csv_path``
and ``cached``. A guard that demands a reader-facing name for ``csv_path`` is
noise, and noise gets an allowlist bolted on until it stops being a gate.

Rule C reads the **parsed string constant**, never the file text, because a
substring scan over source text is defeated by a line break inside the SQL — the
failure mode recorded for source-scan guards generally.
"""

import ast
import re
from pathlib import Path

import pytest

from app.utils.calibration_source_labels import (
    CALIBRATION_SOURCE_LABELS,
    LABEL_DECLARED_FIELD,
    LABEL_FIELD,
    SOURCE_LABELS_FIELD,
    is_declared,
    prettify_source_key,
    source_label,
    source_label_map,
)

APP_ROOT = Path(__file__).resolve().parents[1] / "app"

#: Keys that mark a call/dict as describing a futures market rather than
#: anything else that happens to carry a field called ``source``.
_FM_MARKERS = frozenset(
    {"source_market_id", "market_type", "market_tier", "llm_sport_category", "group_id"}
)
_AS_SOURCE = re.compile(r"'([a-z0-9_]+)'\s+AS\s+source", re.IGNORECASE)


def _scan_producers() -> dict[str, list[str]]:
    """Every source key the backend can publish, mapped to where it is produced."""
    found: dict[str, list[str]] = {}

    def record(key: str, where: str) -> None:
        found.setdefault(key, []).append(where)

    def literal(node) -> str | None:
        if isinstance(node, ast.Constant) and isinstance(node.value, str):
            return node.value
        return None

    for path in sorted(APP_ROOT.rglob("*.py")):
        try:
            tree = ast.parse(path.read_text(encoding="utf-8"))
        except (SyntaxError, UnicodeDecodeError):  # pragma: no cover — defensive
            continue
        rel = path.relative_to(APP_ROOT.parent).as_posix()
        for node in ast.walk(tree):
            # A — FuturesMarket-shaped call.
            if isinstance(node, ast.Call):
                name = getattr(node.func, "id", None) or getattr(node.func, "attr", None)
                kwargs = {kw.arg for kw in node.keywords}
                if name == "FuturesMarket" or ("source" in kwargs and kwargs & _FM_MARKERS):
                    for kw in node.keywords:
                        if kw.arg == "source" and (val := literal(kw.value)):
                            record(val, f"{rel}:{node.lineno}")
            if isinstance(node, ast.Dict):
                keys = {k.value for k in node.keys if isinstance(k, ast.Constant)}
                # A — FuturesMarket-shaped dict. B — calibration-bucket-shaped dict.
                if "source" in keys and (keys & _FM_MARKERS or "bucket_idx" in keys):
                    for key_node, val_node in zip(node.keys, node.values):
                        if (
                            isinstance(key_node, ast.Constant)
                            and key_node.value == "source"
                            and (val := literal(val_node))
                        ):
                            record(val, f"{rel}:{node.lineno}")
            # C — ``'x' AS source`` inside a parsed string constant.
            if isinstance(node, ast.Constant) and isinstance(node.value, str):
                for match in _AS_SOURCE.finditer(node.value):
                    record(match.group(1), f"{rel}:{node.lineno}")
    return found


@pytest.fixture(scope="module")
def produced() -> dict[str, list[str]]:
    return _scan_producers()


# ---------------------------------------------------------------------------
# The scan itself has to work before its verdict means anything.
# ---------------------------------------------------------------------------


def test_the_scan_finds_datagolf_where_it_is_actually_produced(produced):
    """Prove-it-fires control for the key that caused #3357.

    ``datagolf`` is the source that reached readers raw. If the scan cannot see
    it, every assertion below passes vacuously and the guard is decoration — so
    this pins that rule A reaches the real producer file, not that the map has
    an entry (which the next test checks, and which would be trivially true).
    """
    assert "datagolf" in produced, (
        "rule A no longer reaches the DataGolf poller — the vocabulary guard is "
        "vacuous until it does"
    )
    assert any(
        w.startswith("app/tasks/datagolf.py:") for w in produced["datagolf"]
    ), f"expected app/tasks/datagolf.py, got {produced['datagolf']}"


def test_the_scan_recovers_every_rule(produced):
    """One key per rule, so a rule that silently stops matching is caught.

    Without this, deleting rule B or C leaves the suite green: the remaining
    rules still find keys, and every key they find is declared.
    """
    # A — futures_markets writers.
    assert "kalshi" in produced and "polymarket" in produced
    # B — a calibration bucket builder, never written to futures_markets.source.
    assert "odds_api_bookmaker" in produced, "rule B (bucket-shaped dict) stopped matching"
    assert any("backfill_winners.py" in w for w in produced["odds_api_bookmaker"])
    # C — a SQL alias, and one that only rule C can see.
    assert "odds_api_spreads" in produced, "rule C ('x' AS source) stopped matching"
    assert any("precompute_calibration.py" in w for w in produced["odds_api_spreads"])


def test_the_scan_stays_scoped(produced):
    """The rejected unscoped scan returned ``github``/``csv_path``/``cached``.

    If those come back, the scan has lost its scoping and the next engineer will
    fix the resulting failures with an allowlist instead of a name.
    """
    assert not ({"github", "csv_path", "cached", "fallback"} & produced.keys()), (
        f"scan is matching non-source strings again: {sorted(produced)}"
    )


# ---------------------------------------------------------------------------
# The gate.
# ---------------------------------------------------------------------------


def test_every_produced_source_has_a_declared_name(produced):
    """#3357's acceptance line: the gap fails in CI, not on a reader's screen."""
    unnamed = sorted(set(produced) - set(CALIBRATION_SOURCE_LABELS))
    assert not unnamed, (
        "these source keys can reach /api/calibration with no curated name — add "
        "each to CALIBRATION_SOURCE_LABELS in app/utils/calibration_source_labels"
        ".py: "
        + ", ".join(f"{k} ({produced[k][0]})" for k in unnamed)
    )


def test_the_declared_map_is_not_carrying_dead_entries(produced):
    """A name for a key nothing produces is the same rot, pointing the other way.

    Not an error — a source can be retired before its name is — but it must not
    accumulate silently, so the map is held to what the code emits.
    """
    orphans = sorted(set(CALIBRATION_SOURCE_LABELS) - set(produced))
    assert not orphans, (
        "CALIBRATION_SOURCE_LABELS names sources no producer emits: "
        + ", ".join(orphans)
    )


# ---------------------------------------------------------------------------
# The fallback closes the class, so no key can reach a reader raw.
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "raw,expected",
    [
        ("datagolf", "DataGolf"),          # curated: the brand, not "Datagolf"
        ("odds_api", "Odds API"),
        ("odds_api_bookmaker", "Per-Bookmaker (Odds API)"),
    ],
)
def test_curated_names_are_opinions_not_generated(raw, expected):
    assert source_label(raw) == expected
    assert is_declared(raw)
    # And the generated name really would have been wrong, which is why the
    # curated entry exists at all.
    if raw == "datagolf":
        assert prettify_source_key(raw) == "Datagolf"


@pytest.mark.parametrize(
    "raw",
    ["espn_bpi", "some_new_source", "weird-key", "a", "MiXeD_Api", "x_y_z"],
)
def test_an_unnamed_key_is_never_returned_raw(raw):
    """The class, not the instance — the state ``datagolf`` was in is unreachable."""
    label = source_label(raw)
    assert label != raw
    assert "_" not in label
    assert label[0].isupper()
    assert not is_declared(raw)


def test_the_acronym_set_is_shouted():
    assert source_label("espn_bpi") == "ESPN Bpi"
    assert source_label("nfl_model") == "NFL Model"


def test_prettify_survives_a_degenerate_key():
    """It runs at the endpoint's single exit; it may not raise on any input."""
    for raw in ["", "_", "__", "   "]:
        assert isinstance(prettify_source_key(raw), str)


# ---------------------------------------------------------------------------
# The vocabulary block, built without touching the banked artifact.
# ---------------------------------------------------------------------------


def test_the_vocabulary_names_each_source_and_keeps_the_gap_visible():
    rows = [{"source": "kalshi", "n": 5}, {"source": "espn_bpi", "n": 1}]
    vocab = source_label_map(rows)
    assert vocab["kalshi"] == {LABEL_FIELD: "Kalshi", LABEL_DECLARED_FIELD: True}
    # A generated name is a floor, not a fix — a client (or a probe) can tell.
    assert vocab["espn_bpi"] == {LABEL_FIELD: "ESPN Bpi", LABEL_DECLARED_FIELD: False}


def test_building_the_vocabulary_does_not_touch_the_rows():
    """``_serve`` holds a shallow ``dict(payload)`` over a cached artifact, and
    the route's standing contract is that content fields come back byte-
    identical (``test_calibration_field_completeness_257.py``). This is that
    contract at the unit level: a name is published BESIDE the measurements,
    never written into one."""
    rows = [{"source": "kalshi", "n": 5}]
    before = [dict(r) for r in rows]
    source_label_map(rows)
    assert rows == before, "the measurement rows were modified"


def test_the_vocabulary_never_raises_and_never_invents_a_source():
    """CAL-P017 stands: a malformed corner degrades, it does not darken."""
    vocab = source_label_map(
        [
            {"source": "kalshi", "n": 5},
            {"n": 3},                # no source at all
            {"source": "", "n": 2},  # empty source
            {"source": 7, "n": 1},   # wrong type
            "not-a-row",
        ]
    )
    assert set(vocab) == {"kalshi"}
    assert source_label_map(None) == {}
    assert source_label_map("nonsense") == {}


def test_a_repeated_source_is_named_once():
    vocab = source_label_map([{"source": "kalshi"}, {"source": "kalshi"}])
    assert list(vocab) == ["kalshi"]


# ---------------------------------------------------------------------------
# ...and it is actually wired to the endpoint.
# ---------------------------------------------------------------------------
#
# Everything above tests a pure function. A pure function nobody calls is what
# `sourceLabel` was for three weeks — correct, extracted, and not reached by the
# thing a reader loads. These exercise `public_calibration` itself, at the ONE
# exit (#1680) where `producer` and `scorecard` are also attached, so a future
# tier that forgets to route through `_serve` is caught here.


def _payload_with_sources(*sources: str) -> dict:
    from app.tasks.precompute_calibration import CALIBRATION_POPULATION_VERSION

    from datetime import datetime, timedelta, timezone

    # Gotcha #44: offset FIRST. Nothing here may branch on the wall clock.
    stamp = (datetime.now(timezone.utc) - timedelta(minutes=5)).isoformat()
    return {
        "buckets": [{"bucket_idx": 0, "n": 1000, "winners": 500}],
        "by_category": [{"category": "politics", "outcomes": 1000}],
        "by_source": [{"source": s, "outcomes": 1000, "n": 1000} for s in sources],
        "total_outcomes": 1000,
        "total_markets": 250,
        "total_winners": 500,
        "liquidity_filter": {"applies_to": "kalshi"},
        "mex_normalization": {"applies_to": "all"},
        "truth_evidence": {"contract_ok": True},
        "population_version": CALIBRATION_POPULATION_VERSION,
        "generated_at": stamp,
    }


@pytest.fixture
def served(monkeypatch):
    """Serve a payload through the real endpoint, no Redis and no rebuild."""
    from unittest.mock import AsyncMock, MagicMock

    from app.routes import calibration
    from app.tasks import precompute_calibration
    from app.utils import durable_state as ds
    from app.utils import request_cache as rc

    async def _serve_it(payload: dict):
        from datetime import datetime

        class _NoRedis:
            async def get(self, key):
                return None

        async def _getter():
            return _NoRedis()

        async def _boom(db):
            raise AssertionError("the request path must never build")

        monkeypatch.setattr(rc, "get_shared_async_redis", _getter)
        monkeypatch.setattr(precompute_calibration, "compute_calibration_payload", _boom)

        stamp = datetime.fromisoformat(payload["generated_at"])
        row = {
            "identity": "calibration:main",
            "schema_version": payload["population_version"],
            "generation": ds.generation_for(stamp),
            "generated_at": stamp,
            "payload": payload,
            "checksum": ds.checksum_payload(payload),
            "complete": True,
            "source": "precompute_calibration",
        }
        db = AsyncMock()
        result = MagicMock()
        result.mappings.return_value.first.return_value = row
        db.execute.return_value = result
        return await calibration.public_calibration(db=db)

    calibration._cache["data"] = None
    calibration._cache["timestamp"] = 0
    rc._reset_last_good_for_tests()
    yield _serve_it
    calibration._cache["data"] = None
    calibration._cache["timestamp"] = 0
    rc._reset_last_good_for_tests()


async def test_the_endpoint_names_every_source_it_publishes(served):
    """FAILS-FIRST against the pre-#3357 route, which published no name at all."""
    out = await served(_payload_with_sources("kalshi", "polymarket", "datagolf"))

    vocab = out[SOURCE_LABELS_FIELD]
    assert {k: v[LABEL_FIELD] for k, v in vocab.items()} == {
        "kalshi": "Kalshi",
        "polymarket": "Polymarket",
        "datagolf": "DataGolf",
    }
    assert all(v[LABEL_DECLARED_FIELD] is True for v in vocab.values())


async def test_the_endpoint_flags_a_source_nobody_has_named(served):
    """The next `datagolf`: named well enough to render, marked as a guess."""
    out = await served(_payload_with_sources("kalshi", "espn_bpi"))

    entry = out[SOURCE_LABELS_FIELD]["espn_bpi"]
    assert entry[LABEL_FIELD] == "ESPN Bpi"
    assert entry[LABEL_DECLARED_FIELD] is False
    # Never the raw key, on the wire, whatever the client does with it.
    assert entry[LABEL_FIELD] != "espn_bpi"


async def test_the_curve_is_unchanged_by_being_named(served):
    """Naming adds words; it may not touch a measurement or lose a row."""
    payload = _payload_with_sources("kalshi", "polymarket")
    out = await served(payload)

    assert out["total_outcomes"] == 1000
    # The measurement rows are byte-identical to what the producer published:
    # the route is a serving tier, not a second builder. `source_labels` sits
    # beside them, and every source in them is in it.
    assert out["by_source"] == payload["by_source"]
    assert set(out[SOURCE_LABELS_FIELD]) == {"kalshi", "polymarket"}
