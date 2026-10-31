import pytest
from app.utils import busy_db_defer


class _Reached(Exception):
    pass


def _raise(*_a, **_k):
    raise _Reached()


@pytest.mark.asyncio
async def test_calibration_main_is_never_busy_deferred(monkeypatch):
    """#11842 R1: the accuracy page republishes every beat; a 14 h deferral stalls it."""
    from app.tasks import precompute_calibration

    monkeypatch.setenv(busy_db_defer.SWITCH_ENV, "1")
    monkeypatch.setattr(busy_db_defer, "in_busy_window", lambda now=None: True)
    monkeypatch.setattr(precompute_calibration, "_main_input_fingerprint", _raise)
    with pytest.raises(_Reached):
        await precompute_calibration._precompute_calibration_main()
