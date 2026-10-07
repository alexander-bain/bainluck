"""Read only the adapter/driver surfaces used by #10693, not production."""

import inspect
import json
from pathlib import Path
import sys
import asyncpg
import sqlalchemy
from sqlalchemy.dialects.postgresql import asyncpg as dialect

surfaces = {
    "cursor": dialect.AsyncAdapt_asyncpg_cursor,
    "adapter": dialect.AsyncAdapt_asyncpg_connection,
    "driver_fetchmany": asyncpg.Connection.fetchmany,
    "driver_executemany": asyncpg.Connection._executemany,
}
output = Path(sys.argv[1])
output.write_text(
    json.dumps(
        {
            "versions": [sqlalchemy.__version__, asyncpg.__version__],
            "module_paths": [sqlalchemy.__file__, asyncpg.__file__],
            "sources": {
                name: inspect.getsource(surface) for name, surface in surfaces.items()
            },
        },
        indent=2,
    )
    + "\n"
)
print(sqlalchemy.__version__, asyncpg.__version__)
