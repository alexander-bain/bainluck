"""Run the three original historical fixture selections and retain their full output."""
import asyncio
from dataclasses import asdict
import json
from pathlib import Path
import sys

from tests import test_yardstick_pair as fixtures

records = []
produce = fixtures.produce_yardstick_pair


async def record(markets, **kwargs):
    result = await produce(markets, **kwargs)
    records.append({"inputs": markets, "output": asdict(result)})
    return result


fixtures.produce_yardstick_pair = record
cases = fixtures.TestYardstickPairSelection()
for name in sorted(n for n in dir(cases) if n.startswith("test_for_scale_")):
    asyncio.run(getattr(cases, name)())
assert len(records) == 3
path = Path(__file__).with_name("yardstick-" + sys.argv[1] + ".json")
path.write_text(json.dumps(records, indent=2, ensure_ascii=False) + "\n")
