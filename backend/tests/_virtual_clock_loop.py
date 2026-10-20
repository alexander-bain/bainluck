"""An event loop whose clock stands still while anything is runnable.

A wait for the next timer is not slept: the loop's clock jumps to that timer
and the poll returns. Deadlines and sleeps measure exactly, and a runner stall
(GC, a loaded CI machine) moves no clock. The recipe of
`test_kalshi_flush_wait_attribution_10090.py` (#10090, PR #10952).

Use: a module-scoped `event_loop_policy` fixture returning
`VirtualClockPolicy()`, with the code under test reading
`asyncio.get_running_loop().time()`.
"""

import asyncio


class _JumpingSelector:
    def __init__(self, selector, loop):
        self._selector, self._loop = selector, loop

    def select(self, timeout=None):
        if timeout is not None and timeout > 0:
            self._loop.virtual_now += timeout
            timeout = 0
        return self._selector.select(timeout)

    def __getattr__(self, name):
        return getattr(self._selector, name)


class VirtualClockLoop(asyncio.SelectorEventLoop):
    def __init__(self):
        super().__init__()
        self.virtual_now = 0.0
        self._selector = _JumpingSelector(self._selector, self)

    def time(self):
        return self.virtual_now


class VirtualClockPolicy(asyncio.DefaultEventLoopPolicy):
    def new_event_loop(self):
        return VirtualClockLoop()
