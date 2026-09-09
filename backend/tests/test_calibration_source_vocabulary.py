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
        # Notice 33 / D92 = B (Alex, 2026-09-08): "bookmaker" is banned from
        # everything a reader sees, so the curated name for this key moved to the
        # approved word. The KEY is untouched — `odds_api_bookmaker` is what the
        # producer emits and what `test_every_produced_source_is_named` above
        # holds this map to; only the opinion about how to say it changed.
        ("odds_api_bookmaker", "Per-sportsbook (Odds API)"),
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


# ---------------------------------------------------------------------------
# STANDING NOTICE 33, THE BACKEND HALF (#4096, after #4067/CERT-2290)
#
# #4067 swept the reader surfaces and both clients' label maps, and taught the
# FRONTEND prettifier to respell the banned supplier word
# (`houseStyleSupplierWords` in `calibrationProviders.ts`). Two things on this
# side were out of that ship's reach, and this section is exactly those two:
#
#   1. THE PUBLISHED PROSE. `precompute_calibration` serves ~38 `*_RULE_TEXT`
#      constants and a corrections log on `/api/calibration`. #4067 stopped the
#      WEB PAGE printing them (notice 34), which is right — but the strings are
#      still served, iOS reads the same payload, and notice 33 covers "API
#      strings the clients print". Five occurrences survived that sweep, all of
#      them the word in the SINGULAR ("from a real book", "grades half a book",
#      "a fabricated wide-book midpoint"), which a grep for `books`/`bookmaker`
#      walks straight past. The scan below is what found them.
#
#   2. THE GENERATED NAME. This module's `prettify_source_key` had no equivalent
#      of the frontend's rewrite, so an uncurated `odds_api_bookmaker_v2` would
#      be published in `source_labels` as "Odds API Bookmaker V2" — to iOS and
#      every other client — with #4067's whole guard suite green.
#
# Discovered, not listed, in both: the prose is recovered BY SHAPE off the
# imported module, so a rule text added next month is covered without anyone
# remembering this file exists.
# ---------------------------------------------------------------------------

#: `\b` in both directions: "sportsbook(s)" is the APPROVED word (D91) and has
#: no word boundary inside it, so it is not matched; the possessive "the books'
#: number" IS matched, because an apostrophe is a boundary. Both apostrophe
#: spellings, since the codebase uses typographic punctuation in prose.
_BANNED_SUPPLIER_WORD = re.compile(r"\bbookmakers?\b|\bbooks?['’]?\b", re.IGNORECASE)


def _published_prose() -> dict[str, str]:
    """Every string this producer publishes as prose, recovered by shape.

    Names ending ``_RULE_TEXT`` are the exclusion notes; ``CALIBRATION_
    CORRECTIONS`` is the corrections log. Read off the IMPORTED MODULE rather
    than the file text, so a constant built by concatenation is measured as the
    reader receives it rather than as the source happens to wrap it.
    """
    from app.tasks import precompute_calibration as pc

    prose: dict[str, str] = {
        name: value
        for name in dir(pc)
        if name.endswith("_RULE_TEXT") and isinstance(value := getattr(pc, name), str)
    }
    for i, correction in enumerate(pc.CALIBRATION_CORRECTIONS):
        for field in ("title", "description"):
            text = correction.get(field)
            if isinstance(text, str):
                prose[f"CALIBRATION_CORRECTIONS[{i}].{field}"] = text
    return prose


def test_no_published_label_says_bookmaker():
    """The whole map, not the one pair pinned above.

    `test_curated_names_are_opinions_not_generated` pins `odds_api_bookmaker`
    by name; this is the class over every entry, including ones added later.
    """
    offenders = [
        f"{key} = {label!r}"
        for key, label in CALIBRATION_SOURCE_LABELS.items()
        if _BANNED_SUPPLIER_WORD.search(label)
    ]
    assert offenders == []
    # The KEYS are deliberately not held to the ban, and `\b` is what exempts
    # them: `_` is a word character, so there is no boundary before "bookmaker"
    # in `odds_api_bookmaker` and the pattern cannot see it. Structural rather
    # than an allowlist, and asserted so a future tightening argues with it.
    assert not _BANNED_SUPPLIER_WORD.search("odds_api_bookmaker")
    assert not _BANNED_SUPPLIER_WORD.search("bookmaker_count")


def test_the_generated_name_cannot_invent_a_banned_word_either():
    """THE NEXT KEY — the hazard a pin on today's labels cannot see.

    #4067 closed this on the frontend and could not close it here. An
    uncurated key falls through :func:`prettify_source_key` straight into the
    published ``source_labels`` vocabulary.
    """
    for key in (
        "odds_api_bookmaker_v2",
        "some_new_bookmaker_feed",
        "books_consensus",
        "sharp_book",
    ):
        name = prettify_source_key(key)
        assert not _BANNED_SUPPLIER_WORD.search(name), f"{key} -> {name}"

    # A respelling, not a deletion: the generated name still describes the
    # source, or the CAL-P1024 floor has been traded for a blank.
    assert prettify_source_key("odds_api_bookmaker_v2") == "Odds API Sportsbook V2"
    # Whole tokens only, so an unrelated name is never mangled.
    assert prettify_source_key("bookings_feed") == "Bookings Feed"


def test_no_published_rule_text_or_correction_says_bookmaker():
    """The prose `/api/calibration` serves — which iOS reads even though #4067
    stopped the web page printing it."""
    prose = _published_prose()
    # The recovery must actually find the strings; an empty dict would make
    # this pass vacuously, the failure mode a shape-based scan is prone to.
    assert len(prose) >= 15, sorted(prose)
    assert "SOCCER_2WAY_RULE_TEXT" in prose

    offenders = [
        f"{name}: ...{text[max(0, m.start() - 40):m.end() + 40]}..."
        for name, text in prose.items()
        if (m := _BANNED_SUPPLIER_WORD.search(text))
    ]
    assert offenders == []


def test_the_ban_fires_on_the_real_pre_fix_strings():
    """Verbatim from master before #4096 — a guard is proven by what it catches.

    The last two are the ones #4067's sweep left behind: the word in the
    SINGULAR, inside prose that is still served on ``/api/calibration``.
    """
    pre_fix = [
        "in BOTH the events aggregate and the per-bookmaker curve. ",
        "events aggregate (odds_api) and the per-bookmaker (odds_api_bookmaker) sources. ",
        "side from a real book and publishing the survivor alone grades half a book. ",
        "whose captured price is a fabricated wide-book midpoint: a book with ",
    ]
    for text in pre_fix:
        assert _BANNED_SUPPLIER_WORD.search(text), text

    # The inverse hazard: the approved word must not fire, or the guard becomes
    # a nuisance and the next person suppresses it.
    for text in [
        "in BOTH the events aggregate and the per-sportsbook curve. ",
        "events aggregate and the per-sportsbook sources. ",
        "side from a real sportsbook and publishing the survivor alone grades half a pair. ",
        "a fabricated wide-spread midpoint: a quote with yes_ask - yes_bid >= 0.50 ",
        "Per-sportsbook (Odds API)",
    ]:
        assert not _BANNED_SUPPLIER_WORD.search(text), text
