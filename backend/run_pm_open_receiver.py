"""#10090 — child entry point: the Polymarket open-contract socket receiver.

Started (and owned) only by `PolymarketOpenReceiverProcess` in the Polymarket
consumer's process. Loads the two stdlib-only modules it needs BY PATH so the
child never imports the `app.services` package and its database/LLM stack.
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

_SERVICES = os.path.join(os.path.dirname(os.path.abspath(__file__)), "app", "services")


def _load(name: str, filename: str):
    spec = importlib.util.spec_from_file_location(name, os.path.join(_SERVICES, filename))
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def main() -> int:
    client = _load("app.services.polymarket_ws", "polymarket_ws.py")
    process = _load("app.services.polymarket_ws_process", "polymarket_ws_process.py")
    return asyncio.run(process.serve_receiver(client.PolymarketWebSocket))


if __name__ == "__main__":
    sys.exit(main())
