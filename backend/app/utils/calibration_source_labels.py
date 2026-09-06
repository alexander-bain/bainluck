"""Reader-facing names for the source keys ``/api/calibration`` publishes.

WHY THIS EXISTS (#3357, filed by CAL-P1024 as the half of #1865's source-naming
defect that could not be fixed from a client).

``by_source`` is keyed by an internal source key and, until this module, carried
no name. The key set is data-driven — it falls out of a ``GROUP BY source`` over
live rows — and there was **no source-key constant anywhere in the backend** to
hold a client against. So every surface kept its own hand-maintained translation
map, and each one silently fell behind whenever the data side added a source:
``datagolf`` reached readers on ``/calibration`` as a raw lowercase database key,
in the default view, for about three weeks.

This module is that missing constant. The name is owned once, where the payload
is produced, and every surface renders what it is given instead of guessing.

WHAT THIS MODULE DELIBERATELY DOES NOT DO — it holds no opinion about *provider
families*. Grouping ``odds_api``/``odds_api_spreads``/``odds_api_totals`` into
one "Sportsbooks (Odds API)" row is a presentation decision the calibration page
makes for its Source Comparison table, and the two genuinely disagree:
``odds_api`` is "Odds API" as a source while its family is "Sportsbooks (Odds
API)" as a provider. One key space per module.

Imports nothing, and must stay that way — the same rule ``sport_keys.py`` keeps,
for the same reason: a vocabulary that can import is a vocabulary that can
develop a circular dependency on the thing it names.
"""

#: The declared vocabulary: every source key ``/api/calibration`` can publish,
#: and the name a person calls it.
#:
#: **This is the gate, not a convenience.** ``tests/test_calibration_source_
#: vocabulary.py`` recovers the source keys the backend actually produces by
#: scanning the producers, and fails when one of them is missing from this map.
#: Adding a source to the data side without adding it here breaks CI at the
#: commit that introduced it, which is the whole point — the alternative is a
#: reader finding it, which is how ``datagolf`` was found.
#:
#: A curated entry is an *opinion* and that is why they are written by hand: the
#: brand is "DataGolf", never "Datagolf", and a generated name is a fabrication.
CALIBRATION_SOURCE_LABELS: dict[str, str] = {
    "kalshi": "Kalshi",
    "polymarket": "Polymarket",
    "odds_api": "Odds API",
    "odds_api_spreads": "Spreads (Odds API)",
    "odds_api_totals": "Totals (Odds API)",
    "odds_api_bookmaker": "Per-Bookmaker (Odds API)",
    "datagolf": "DataGolf",
}

#: Tokens inside a source key that are shouted rather than spelled.
#:
#: Deliberately a source-scoped set. The calibration page's *category* labeller
#: derives its acronyms from league names, so a source key that collided with a
#: league key would come back named after the league. Two key spaces, two sets.
SOURCE_ACRONYMS: frozenset[str] = frozenset(
    {"ai", "api", "espn", "mlb", "nba", "nfl", "nhl", "pga", "ufc", "wta"}
)

#: The top-level key the serving layer publishes the vocabulary under, and the
#: two fields inside each entry.
#:
#: A block beside the curve rather than a field on each ``by_source`` row,
#: because ``/api/calibration`` holds a contract that the route is a serving
#: tier and **not a second builder**: every *content* field it hands back is
#: byte-identical to what the producer published, and the only things the route
#: may add are enumerated serve-time keys (``availability``, ``producer``,
#: ``staged``, ``scorecard`` — see ``tests/test_calibration_field_completeness_
#: 257.py``). A name written into a measurement row would break that for a
#: presentation string. It also reads better: one dictionary a client can look
#: any source up in, including sources that appear somewhere other than
#: ``by_source``.
SOURCE_LABELS_FIELD = "source_labels"
LABEL_FIELD = "label"
LABEL_DECLARED_FIELD = "declared"


def prettify_source_key(raw: str) -> str:
    """A source key we hold no curated name for, made readable.

    **Never returns a raw payload key**: the result carries no underscore and
    never leads lowercase, so the state this function exists to close is
    unreachable for *any* input, not only the one that exposed it.

    A generated name is only ever the state of a source nobody has named yet.
    It is a floor, not a fix — which is why :data:`LABEL_DECLARED_FIELD` rides
    alongside it, so "nobody has named this" stays visible in the payload
    instead of being papered over by a plausible-looking string.
    """
    tokens = [t for t in raw.replace("-", "_").replace(" ", "_").split("_") if t]
    if not tokens:
        return raw
    out = []
    for token in tokens:
        lower = token.lower()
        out.append(lower.upper() if lower in SOURCE_ACRONYMS else lower.capitalize())
    return " ".join(out)


def is_declared(source: str) -> bool:
    """Is this source key's name curated, rather than generated from the key?"""
    return source in CALIBRATION_SOURCE_LABELS


def source_label(source: str) -> str:
    """A source key's reader-facing name. **Never returns a raw payload key.**"""
    return CALIBRATION_SOURCE_LABELS.get(source) or prettify_source_key(source)


def source_label_map(rows: object) -> dict[str, dict]:
    """The vocabulary for one payload: ``{source_key: {label, declared}}``.

    Reads ``by_source`` and writes nothing back to it — the caller holds a
    shallow ``dict(payload)`` over a banked artifact, and the route's standing
    contract is that content fields come back byte-identical.

    ``declared`` rides alongside ``label`` because a *generated* name is a
    floor, not a fix: it keeps "nobody has named this source" visible in the
    payload instead of papering it over with a plausible-looking string, so a
    client or a probe can tell the two apart.

    Total and non-raising by construction. It runs at the endpoint's single
    exit, where the standing rule (CAL-P017) is that a malformed corner degrades
    the claim rather than darkening the page — anything that is not a row with a
    usable ``source`` is skipped, never raised on, so naming can neither lose a
    measurement nor take the page down.
    """
    out: dict[str, dict] = {}
    if not isinstance(rows, list):
        return out
    for row in rows:
        if not isinstance(row, dict):
            continue
        source = row.get("source")
        if not isinstance(source, str) or not source or source in out:
            continue
        out[source] = {
            LABEL_FIELD: source_label(source),
            LABEL_DECLARED_FIELD: is_declared(source),
        }
    return out
