"""#10090 — child entry point: the Polymarket open-contract socket receiver.

Started (and owned) only by `PolymarketOpenReceiverProcess` in the Polymarket
consumer's process. Loads the three stdlib-only modules it needs BY PATH so the
child never imports the `app.services` or `app.utils` packages and their
database/LLM stack.
Logs go to stderr; stdout is the frame pipe to the parent.
"""

import asyncio
import importlib.util
import logging
import os
import sys

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)

_APP = os.path.join(os.path.dirname(os.path.abspath(__file__)), "app")
_SERVICES = os.path.join(_APP, "services")
_UTILS = os.path.join(_APP, "utils")


def _load(name: str, filename: str, directory: str = _SERVICES):
    spec = importlib.util.spec_from_file_location(name, os.path.join(directory, filename))
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def main() -> int:
    client = _load("app.services.polymarket_ws", "polymarket_ws.py")
    process = _load("app.services.polymarket_ws_process", "polymarket_ws_process.py")
    # #10663: this child trims its C heap like the venue processes (#11218).
    heap = _load("app.utils.heap_trim", "heap_trim.py", _UTILS)
    return asyncio.run(process.serve_receiver(
        client.PolymarketWebSocket,
        release_free_heap=lambda: heap.release_free_heap("polymarket_open_receiver"),
    ))


if __name__ == "__main__":
    sys.exit(main())
