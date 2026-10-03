"""#10208 — the /sports grouped feed makes ONE extra read: the current-slate
query (``routes.futures.grouped_feed_slate``). Route tests whose fake sessions
script the POOL read answer that one explicitly with "no slate", before their own
read counting, so their pool/fold assertions mean exactly what they meant
before. The slate read is the only grouped-feed statement with a window
function, which is how it is told apart.
"""


def is_slate_read(stmt) -> bool:
    return "row_number" in str(stmt).lower()


class _NoSlate:
    def all(self):
        return []


NO_SLATE = _NoSlate()
