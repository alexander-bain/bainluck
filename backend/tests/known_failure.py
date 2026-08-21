"""The only vocabulary in which a test may declare an expected failure.

WHY THIS MODULE EXISTS — AND WHY IT IS A DELETION, NOT A THIRD RULE
--------------------------------------------------------------------

Exception laundering through ``xfail`` has now been found **twice** by adversarial
audit, and the second finding defeated the fix written for the first:

1. ``C-2049-2050-REVIEW`` — ``xfail(strict=True)`` with no ``raises=`` at all. An
   adversarial matcher that made **every** call raise ``RuntimeError`` still
   produced ``34 passed, 47 xfailed, exit 0`` — byte-for-byte the healthy headline.
   **Fix written: add** ``raises=AssertionError``.
2. ``C-2058-REVIEW`` — that fix does not work, because the test's OWN assertion and
   an ``AssertionError`` raised *inside* ``names_match`` are **the same exception
   class**. Codex replaced the matcher with one raising
   ``AssertionError("matcher implementation crashed")`` and got **56 xfailed,
   exit 0**. The marker cannot tell the intended known-failure from a crash,
   because nothing in the type distinguishes them.

The third rule in that sequence would be "``raises=`` something narrower", and it
would fail the same way the moment production code can raise the narrower thing.
**So the capability itself is deleted:** an ``xfail`` may admit exactly one
exception type, :class:`KnownFailure`, and **no production code can raise it**, because
it is defined here, in the test tree, and is raised by exactly one helper below.

The distinction the marker could never make is now made *structurally*, before the
marker is ever consulted:

* the characterised wrong ANSWER  → :func:`expect_known_failure` → ``KnownFailure``
  → admitted, reported ``xfailed``.
* any EXCEPTION out of production code → :func:`call_under_test` →
  :class:`ProductionCodeRaised` → **not** ``KnownFailure`` → reported as a failure.

`backend/tests/test_xfail_cannot_launder_exceptions.py` enforces this over the whole
test tree by AST, and proves the two outcomes above by running real pytest
subprocesses rather than reasoning about ``issubclass`` — which is the specific
weakness codex named in the negative control this replaces.

A NOTE ON THE OBVIOUS SHORTCUT
------------------------------

``KnownFailure`` deliberately does NOT subclass ``AssertionError``. Making it one
would let a bare ``assert`` keep working and would feel tidier — and would restore
the exact defect, because production code raises ``AssertionError`` too. The
inconvenience of :func:`expect_known_failure` IS the mechanism.
"""

from __future__ import annotations

from typing import Any, Callable, NoReturn, TypeVar

__all__ = [
    "KnownFailure",
    "ProductionCodeRaised",
    "call_under_test",
    "expect_known_failure",
    "expect_raises_known_failure",
    "known_failure",
]

T = TypeVar("T")


class KnownFailure(Exception):
    """The ONE exception an ``xfail`` marker is permitted to admit.

    Nothing under ``backend/app/`` can raise this — it is defined in the test tree
    and raised only by :func:`expect_known_failure`. That is the whole guarantee:
    an admitted exception is, by construction, one a test deliberately raised about
    a wrong ANSWER, never one that escaped the code under test.
    """


class ProductionCodeRaised(Exception):
    """Code under test raised. This is an ERROR and is never an expected failure.

    Carries the original as ``__cause__`` so the traceback still points at the real
    site — the point is to change how the outcome is CLASSIFIED, not to hide it.
    """


def call_under_test(fn: Callable[..., T], /, *args: Any, **kwargs: Any) -> T:
    """Call production code so that any exception becomes un-admittable.

    Use this for every call to the code a known-failure test characterises::

        result = call_under_test(names_match, a, b)
        expect_known_failure(result is False, "...")

    ``BaseException`` is caught deliberately, not ``Exception``: a matcher that
    raised ``KeyboardInterrupt`` or a bare ``BaseException`` subclass would
    otherwise sail past this and reach the marker.
    :class:`KnownFailure` is re-raised untouched so a nested helper still works.
    """
    try:
        return fn(*args, **kwargs)
    except KnownFailure:
        raise
    except BaseException as exc:  # noqa: BLE001 — re-raised, never swallowed
        name = getattr(fn, "__qualname__", None) or getattr(fn, "__name__", repr(fn))
        raise ProductionCodeRaised(
            f"{name} RAISED {type(exc).__name__}: {exc} — a crash in the code under "
            f"test is an error, not an expected failure (C-2058-REVIEW)"
        ) from exc


def expect_known_failure(condition: bool, reason: str) -> None:
    """Declare the characterised wrong answer.

    ``condition`` is what SHOULD be true. When it is false, the known defect is
    present and :class:`KnownFailure` is raised — the only thing an ``xfail`` admits.
    When it is true the defect is gone, the test passes, and ``strict=True`` turns
    that pass into a failure telling you to delete the marker. That promotion signal
    is preserved exactly as it was.
    """
    if not condition:
        raise KnownFailure(reason)


def expect_raises_known_failure(
    exc_type: type[BaseException],
    match: str,
    fn: Callable[..., Any],
    /,
    *args: Any,
    **kwargs: Any,
) -> None:
    """For the INVERTED shape: the correct behaviour is to RAISE, and it does not.

    ``pytest.raises`` cannot express this safely for the same reason
    ``raises=AssertionError`` could not: when the expected raise does not happen,
    ``pytest.raises`` itself raises ``Failed``, and a marker admitting ``Failed``
    would also admit a genuine crash. So the three outcomes are separated by hand:

    * raises ``exc_type`` with a matching message  → correct, the defect is FIXED,
      the test passes and ``strict=True`` reports XPASS. Delete the marker.
    * raises nothing, or the wrong message         → the characterised defect →
      :class:`KnownFailure`.
    * raises anything ELSE                         → :class:`ProductionCodeRaised`,
      an error, never an expected failure.
    """
    import re  # noqa: PLC0415 — local, this helper is the only caller

    name = getattr(fn, "__qualname__", None) or getattr(fn, "__name__", repr(fn))
    try:
        fn(*args, **kwargs)
    except exc_type as exc:
        if re.search(match, str(exc)):
            return  # the wanted behaviour — XPASS under strict=True
        raise KnownFailure(
            f"{name} raised {type(exc).__name__} but the message {str(exc)!r} does "
            f"not match {match!r}"
        ) from None
    except BaseException as exc:  # noqa: BLE001 — re-raised as an error
        raise ProductionCodeRaised(
            f"{name} RAISED {type(exc).__name__}: {exc} — expected {exc_type.__name__}; "
            "an unexpected exception class is an error, not an expected failure"
        ) from exc
    raise KnownFailure(
        f"{name} did not raise {exc_type.__name__} — it accepted the input"
    )


def known_failure(reason: str) -> NoReturn:
    """Unconditional form, for a characterisation with nothing boolean to test."""
    raise KnownFailure(reason)
