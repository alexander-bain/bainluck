"""#10090 — one fast JSON decoder for the venue processes' hot paths.

Production 2026-10-30 23:23Z, worker-ws: both venue processes are CPU-saturated
(Polymarket loop cpu 0.96-0.97, Kalshi 0.94) and the worst user-visible delay
rises with that load. Polymarket's CPU sampler still finds ~7 % of its process
in stdlib ``json`` (``raw_decode`` 4.1 %, ``decode`` 0.7 %) plus asyncpg's JSONB
decoder (2.6 %), and Kalshi decodes every socket frame (~1,900/s) with
``json.loads``.

``pydantic_core.from_json`` is the parser Polymarket's frame path already uses
(``app.services.polymarket_ws._decode_message``): it parses arbitrary-size
integers exactly, and its string cache holds object KEYS only, never the
changing ids and prices. Inputs it refuses (e.g. lone surrogate escapes) go
through ``json.loads``, which also keeps stdlib's accepted values and its
exception contract (``json.JSONDecodeError`` / ``TypeError``).

Undo: ``WS_FAST_JSON=0`` makes ``loads`` exactly ``json.loads`` (read once per
process; a config change restarts worker-ws).
"""

import json
import os

from pydantic_core import from_json

FAST_JSON_ENV = "WS_FAST_JSON"

#: Object keys repeat on every frame and row; values stay uncached.
_STRING_CACHE = "keys"


def fast_json_enabled() -> bool:
    """False only when ``WS_FAST_JSON`` is set to ``0``."""
    return os.getenv(FAST_JSON_ENV, "1").strip() != "0"


def _fast_loads(raw):
    try:
        return from_json(raw, cache_strings=_STRING_CACHE)
    except (ValueError, TypeError):
        return json.loads(raw)


#: Bound once per process, so a frame pays one call and no switch read.
loads = _fast_loads if fast_json_enabled() else json.loads
