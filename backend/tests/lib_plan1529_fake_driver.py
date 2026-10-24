"""The #847 fake `psycopg2`, re-keyed for the four #1529 phase-A statements.

Never a production test mode. Everything (actions, clock, meter, log) is
`lib_plan847_fake_driver`'s; only the EXPLAIN statement kinds differ, so a behaviour
dict here names explain_games, explain_markets, explain_source_split and
explain_fixture_days. The base module's cursor looks `_kind` up at call time, so
replacing it here re-keys every statement it sees.
"""
import lib_plan847_fake_driver as _base
from lib_plan847_fake_driver import install, meter  # noqa: F401  (the launcher's entry points)

_base_kind = _base._kind
# Checked in order; each marker appears in exactly one of the four sealed statements.
_MARKERS = (
    ('explain_fixture_days', 'FROM g GROUP BY 1, 2'),
    ('explain_games', 'FROM g GROUP BY sport_key'),
    ('explain_source_split', 'fm.source'),
    ('explain_markets', 'fm.name'),
)


def _kind(sql):
    kind = _base_kind(sql)
    if not kind.startswith('explain'):
        return kind
    for name, marker in _MARKERS:
        if marker in sql:
            return name
    return 'UNEXPECTED'


_base._kind = _kind
