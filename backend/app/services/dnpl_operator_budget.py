"""Explicit operator network budgets; never live producer or SQL lock budgets."""

from dataclasses import dataclass

from app.services.dnpl_authority import AuthorityStore


@dataclass(frozen=True)
class OperatorBudgets:
    io_ms: int = 150
    preview_ms: int = 1000

    def __post_init__(self):
        if type(self.io_ms) is not int or not 1 <= self.io_ms <= 5000:
            raise ValueError("operator I/O budget must be 1..5000 milliseconds")
        if (
            type(self.preview_ms) is not int
            or not self.io_ms <= self.preview_ms <= 30000
        ):
            raise ValueError("preview budget must cover I/O and be at most 30000ms")

    @property
    def io_s(self):
        return self.io_ms / 1000

    @property
    def preview_s(self):
        return self.preview_ms / 1000


class OperatorAuthorityStore(AuthorityStore):
    """Recovery transactions may include laptop connection/round-trip latency.

    The inherited SQL statement/lock limits stay unchanged. The normal store's
    150ms constructor limit stays intact, and producer sampling delegates to a normal store with its original bound.
    """

    def __init__(self, sessions, budgets: OperatorBudgets):
        super().__init__(sessions)
        self.budget_s = budgets.io_s

    async def read_for_producer(self):
        return await AuthorityStore(self.sessions).read_for_producer()
