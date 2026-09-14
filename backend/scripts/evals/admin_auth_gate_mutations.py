"""Q332 Item 2 — the auth-removal / auth-weakening mutation class.

C271 built the *census* harness (``admin_destructive_boundary_contract``) and then
marked itself VENDOR-HALTED: per the 2026-08-11 routing rule in ``CODEX-LANE.md``,
mutations that remove or weaken an auth gate are not run by the Codex lane. This is
that remainder.

WHAT A MUTANT PROVES HERE
-------------------------
A passing test suite proves the gate works on the paths the suite walks. It does not
prove the suite would NOTICE if the gate stopped working — and that second property is
the whole reason a security test exists. So each mutant below deliberately breaks the
boundary, and the harness demands that the oracle FAIL. A mutant that survives is
either a missing test or a missing gate; the report must say which, per mutant.

Mutation is source-level and applied to an in-memory COPY of ``admin_utils.py``, exec'd
into a throwaway module. Nothing on disk is modified — this matters because a harness
that edits a real source file and restores it afterwards loses the file when the run
dies mid-way, and because a mutation left behind is a shipped vulnerability.

THE ONE MUTANT THAT CANNOT BE KILLED BEHAVIOURALLY
--------------------------------------------------
``weaken-constant-time-compare`` swaps ``hmac.compare_digest`` for ``==``. Those two
are behaviourally IDENTICAL — same accepts, same rejects. The difference is timing, and
a unit test that tried to measure it would be a flake generator, not a proof. It is
therefore killed by a SOURCE contract (the gate must call ``compare_digest``) and is
labelled as such rather than being quietly counted as a behavioural kill. Claiming a
behavioural kill there would be the kind of footnote this queue exists to refuse.
"""
from __future__ import annotations

import importlib.util
import os
from contextlib import contextmanager
from pathlib import Path

REPO = Path(__file__).resolve().parents[3]
ADMIN_UTILS = REPO / "backend/app/routes/admin_utils.py"

BASE_TOKEN = "q332-base-admin-token"
SECOND_TOKEN = "q332-destructive-token"
#: The identity the router-level dependency resolves for a signed-in admin (#5952).
ADMIN_EMAIL = "admin-account@example.com"


# --------------------------------------------------------------------------
# Mutants: (id, needle, replacement, why)
# --------------------------------------------------------------------------
MUTANTS: list[dict[str, str]] = [
    {
        "id": "accept-missing-second-token",
        "needle": "    if not presented:",
        "replacement": "    if False:",
        "why": "Drops the 'second token absent' rejection: ADMIN_TOKEN alone suffices.",
    },
    {
        "id": "accept-wrong-second-token",
        "needle": "    if not _tokens_match(presented, expected):",
        "replacement": "    if False:",
        "why": "Any non-empty value in the destructive header is accepted.",
    },
    {
        "id": "accept-base-token-as-second",
        "needle": '        presented = (request.headers.get(DESTRUCTIVE_TOKEN_HEADER, "") or "").strip()',
        "replacement": "        presented = bearer_credentials(request)",
        "why": "Reads the second token from the Authorization header, so the ordinary "
               "admin token satisfies both factors — the exact collapse Q315 exists to prevent.",
    },
    {
        "id": "drop-base-token-check-in-destructive",
        # Re-targeted for #5952, which added `allow_account=False` to this call.
        # The harness refused the stale anchor rather than silently skipping the
        # mutant, which is the whole reason it counts matches — see `apply_mutant`.
        "needle": "    _check_admin_secret(secret, request=request, allow_account=False)\n\n    expected = os.getenv(\"ADMIN_TOKEN_DESTRUCTIVE\")",
        "replacement": "    expected = os.getenv(\"ADMIN_TOKEN_DESTRUCTIVE\")",
        "why": "Removes the base-token precondition: the destructive token alone is enough.",
    },
    {
        "id": "destructive-accepts-an-account-session",
        "needle": "    _check_admin_secret(secret, request=request, allow_account=False)",
        "replacement": "    _check_admin_secret(secret, request=request, allow_account=True)",
        "why": "#5952 gave every admin route an account path. This is the mutant that "
               "lets a browser session run a DESTRUCTIVE mutation — the privilege "
               "increase the ship deliberately did not make.",
    },
    {
        "id": "account-identity-is-read-from-the-client",
        "needle": "    state = getattr(request, \"state\", None)\n    return getattr(state, ACCOUNT_ADMIN_STATE_ATTR, None)",
        "replacement": "    return (request.headers or {}).get(\"x-admin-account-email\")",
        "why": "#5952: takes the admin identity from a header instead of the server-side "
               "resolution, so anyone can name themselves an admin. The single most "
               "dangerous way to get this ship wrong.",
    },
    {
        "id": "account-path-grants-without-a-resolved-identity",
        "needle": "    if allow_account and account_admin_email(request):\n        return True",
        "replacement": "    if allow_account:\n        return True",
        "why": "#5952: the account branch stops checking whether anyone was actually "
               "resolved, so every admin route opens to the public.",
    },
    {
        "id": "unconfigured-server-accepts-everything",
        "needle": '        raise HTTPException(status_code=403, detail="Admin auth not configured")',
        "replacement": "        return True",
        "why": "Fail-OPEN when ADMIN_TOKEN is unset — the classic misconfiguration bypass.",
    },
    {
        "id": "accept-any-base-token",
        "needle": '    raise HTTPException(status_code=403, detail="Invalid admin secret")',
        "replacement": "    return True",
        "why": "Base gate never rejects: a wrong or absent Authorization header passes.",
    },
    {
        "id": "destructive-token-unset-is-ok",
        "needle": "    expected = os.getenv(\"ADMIN_TOKEN_DESTRUCTIVE\")\n    if not expected:",
        "replacement": "    expected = os.getenv(\"ADMIN_TOKEN_DESTRUCTIVE\")\n    if False:",
        "why": "An unset ADMIN_TOKEN_DESTRUCTIVE stops fail-closed; the gate degrades to "
               "comparing against None instead of refusing.",
    },
]

# Mutants that are EQUIVALENT on the authorization axis: they change no accept/reject
# verdict, and an oracle that only asked "was it refused?" reports them as SURVIVORS.
#
# Both survived the first run of this harness, and the honest reading — required by the
# queue, which says a survivor is "either a missing test or a missing gate; resolve
# which" — is NEITHER. They survive because `_tokens_match` refuses falsy operands, so
# an empty presented token and an unset expected token are both rejected a second time
# one line further down. That is real defence in depth: the boundary fails closed twice,
# and deleting either early guard does not open it.
#
# What the early guards actually buy is the DIAGNOSTIC, which the gate's docstring calls
# a deliberate decision. So they are killed on the diagnostic contract (oracle checks 2
# and 8), and are recorded here as diagnostic kills rather than being counted as
# bypasses. Inflating an equivalent mutant into a "bypass caught" is precisely the
# footnote this queue refuses.
EQUIVALENT_ON_AUTHORIZATION = {
    "accept-missing-second-token",
    "destructive-token-unset-is-ok",
}

# Killed by source contract, not behaviour — see the module docstring.
TIMING_MUTANT = {
    "id": "weaken-constant-time-compare",
    "needle": 'return hmac.compare_digest(presented.encode("utf-8"), expected.encode("utf-8"))',
    "replacement": "return presented == expected",
    "why": "Reintroduces the short-circuiting compare, leaking a prefix-length timing oracle.",
}


def read_source() -> str:
    return ADMIN_UTILS.read_text()


def apply_mutant(source: str, mutant: dict[str, str]) -> str:
    needle, replacement = mutant["needle"], mutant["replacement"]
    count = source.count(needle)
    if count != 1:
        raise AssertionError(
            f"mutant {mutant['id']!r}: anchor matched {count} times, expected exactly 1. "
            "The gate was refactored — re-target the mutant rather than deleting it."
        )
    return source.replace(needle, replacement)


def load_module(source: str, name: str):
    """Exec ``source`` as a standalone module. Never touches disk."""
    spec = importlib.util.spec_from_loader(name, loader=None)
    module = importlib.util.module_from_spec(spec)
    module.__file__ = str(ADMIN_UTILS)
    exec(compile(source, str(ADMIN_UTILS), "exec"), module.__dict__)
    return module


@contextmanager
def env(**values: str | None):
    previous = {key: os.environ.get(key) for key in values}
    try:
        for key, value in values.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value
        yield
    finally:
        for key, value in previous.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value


def make_request(
    module,
    *,
    authorization: str | None,
    second: str | None = None,
    extra_headers: dict[str, str] | None = None,
    account: str | None = None,
):
    """Build a real Request for the gate.

    ``account`` stamps the server-side identity the way the router-level
    dependency does (#5952); ``extra_headers`` lets a mutant try to supply the
    same thing from the client, which is the case that must never work.
    """
    from starlette.requests import Request

    headers = []
    if authorization is not None:
        headers.append((b"authorization", authorization.encode()))
    if second is not None:
        headers.append((module.DESTRUCTIVE_TOKEN_HEADER.lower().encode(), second.encode()))
    for key, value in (extra_headers or {}).items():
        headers.append((key.lower().encode(), value.encode()))
    request = Request(
        {
            "type": "http",
            "method": "POST",
            "path": "/api/admin/test",
            "query_string": b"",
            "headers": headers,
            "state": {},
        }
    )
    if account is not None:
        setattr(request.state, module.ACCOUNT_ADMIN_STATE_ATTR, account)
    return request


def refusal_detail(module, **request_kwargs) -> str | None:
    """The 403 detail string, or None when the gate did not refuse.

    The gate's own docstring makes the wording a deliberate design decision, not
    incidental prose: the denial "will be met by Alex mid-operation, and a generic
    denial would tell him nothing about what to do next". Two of this harness's
    mutants are invisible to an accept/reject oracle and visible only here — see
    EQUIVALENT_ON_AUTHORIZATION below.
    """
    from fastapi import HTTPException

    try:
        module._check_admin_destructive(None, request=make_request(module, **request_kwargs))
    except HTTPException as exc:
        return str(exc.detail)
    return None


def _refuses(module, **request_kwargs) -> bool:
    """True when the destructive gate refuses. Any non-True return also counts as
    a refusal only if it raises — a gate that silently returns False would be a
    finding in itself, so it is reported as NOT refusing."""
    from fastapi import HTTPException

    try:
        result = module._check_admin_destructive(
            None, request=make_request(module, **request_kwargs)
        )
    except HTTPException as exc:
        return exc.status_code == 403
    return result is not True and result is not None


def _refuses_read(module, request) -> bool:
    """True when the ORDINARY admin gate refuses this request (#5952).

    `_refuses` asks the destructive gate. This asks `_check_admin_secret`, which
    is the one the ~400 read and write admin routes actually call, and therefore
    the one an account-path mistake would open.
    """
    from fastapi import HTTPException

    try:
        result = module._check_admin_secret(None, request=request)
    except HTTPException as exc:
        return exc.status_code == 403
    return result is not True


def oracle(module) -> list[str]:
    """Run the boundary's security assertions. Returns the list of FAILURES.

    Empty list == the boundary holds. A mutant is KILLED when this returns at
    least one failure.
    """
    failures: list[str] = []
    good = f"Bearer {BASE_TOKEN}"

    with env(ADMIN_TOKEN=BASE_TOKEN, ADMIN_TOKEN_DESTRUCTIVE=SECOND_TOKEN, ADMIN_SECRET=None):
        # 1. The happy path must still work, or the gate is merely broken, not safe.
        try:
            if module._check_admin_destructive(
                None, request=make_request(module, authorization=good, second=SECOND_TOKEN)
            ) is not True:
                failures.append("correct two-token call was not accepted")
        except Exception as exc:  # noqa: BLE001 - any failure here is a failure
            failures.append(f"correct two-token call raised {exc!r}")

        # 2. Second token absent — and the denial must SAY the header is missing,
        #    not that it mismatched. See EQUIVALENT_ON_AUTHORIZATION.
        detail = refusal_detail(module, authorization=good, second=None)
        if detail is None:
            failures.append("missing second token was ACCEPTED")
        elif module.DESTRUCTIVE_TOKEN_HEADER not in detail or "does not match" in detail:
            failures.append(
                "missing second token was refused with the MISMATCH message; the "
                f"absent-header case must name the header to send: {detail!r}"
            )

        # 3. Second token wrong.
        if not _refuses(module, authorization=good, second="wrong-second-token"):
            failures.append("wrong second token was ACCEPTED")

        # 4. Base token replayed as the second token.
        if not _refuses(module, authorization=good, second=BASE_TOKEN):
            failures.append("base admin token was ACCEPTED as the second token")

        # 5. No Authorization header at all.
        if not _refuses(module, authorization=None, second=SECOND_TOKEN):
            failures.append("missing base token was ACCEPTED")

        # 6. Wrong base token.
        if not _refuses(module, authorization="Bearer not-the-admin-token", second=SECOND_TOKEN):
            failures.append("wrong base token was ACCEPTED")

    # 7. Server misconfigured: no ADMIN_TOKEN at all must fail CLOSED.
    with env(ADMIN_TOKEN=None, ADMIN_SECRET=None, ADMIN_TOKEN_DESTRUCTIVE=SECOND_TOKEN):
        if not _refuses(module, authorization=good, second=SECOND_TOKEN):
            failures.append("unset ADMIN_TOKEN failed OPEN")

    # 8. Destructive token unset must fail CLOSED — and must say the SERVER is
    #    unconfigured, so the operator fixes config instead of hunting a bad header.
    with env(ADMIN_TOKEN=BASE_TOKEN, ADMIN_SECRET=None, ADMIN_TOKEN_DESTRUCTIVE=None):
        detail = refusal_detail(module, authorization=good, second=SECOND_TOKEN)
        if detail is None:
            failures.append("unset ADMIN_TOKEN_DESTRUCTIVE failed OPEN")
        elif "not configured on the server" not in detail:
            failures.append(
                "unset ADMIN_TOKEN_DESTRUCTIVE was reported as a header mismatch; the "
                f"server-misconfiguration case must say so: {detail!r}"
            )

    # -----------------------------------------------------------------------
    # 9-12. The account path (#5952).
    #
    # /admin now opens on the Google account the reader is already signed in
    # with, which means the identity behind an admin request can come from
    # somewhere other than the token. These four assertions are the boundary of
    # that: where the identity may come from, what it is worth, and what it is
    # still not enough for.
    # -----------------------------------------------------------------------
    with env(ADMIN_TOKEN=BASE_TOKEN, ADMIN_SECRET=None, ADMIN_TOKEN_DESTRUCTIVE=SECOND_TOKEN):
        account_token = "Bearer a-google-account-id-token"

        # 9. A resolved admin account opens an ordinary admin route. This is the
        #    ship; without it the rest of these are satisfied by a broken gate.
        try:
            if module._check_admin_secret(
                None,
                request=make_request(module, authorization=account_token, account=ADMIN_EMAIL),
            ) is not True:
                failures.append("a resolved admin account was REFUSED an ordinary admin route")
        except Exception as exc:  # noqa: BLE001
            failures.append(f"a resolved admin account raised {exc!r}")

        # 10. ...and is still NOT enough to run a destructive mutation, even
        #     holding a correct second token. The deliberate line in
        #     `_check_admin_destructive`'s docstring.
        if not _refuses(
            module, authorization=account_token, second=SECOND_TOKEN, account=ADMIN_EMAIL
        ):
            failures.append("an account session was ACCEPTED for a DESTRUCTIVE route")

        # 11. The identity must come from server-side state. A client that names
        #     itself an admin in a header is just a client.
        forged = make_request(
            module,
            authorization="Bearer a-strangers-token",
            extra_headers={
                "x-admin-account-email": ADMIN_EMAIL,
                "admin-account-email": ADMIN_EMAIL,
                module.ACCOUNT_ADMIN_STATE_ATTR: ADMIN_EMAIL,
            },
        )
        if not _refuses_read(module, forged):
            failures.append("a client-supplied admin email was ACCEPTED as an identity")

        # 12. No resolved identity at all ⇒ refuse. Guards the case where the
        #     account branch stops checking and admits everyone.
        if not _refuses_read(
            module, make_request(module, authorization="Bearer a-strangers-token")
        ):
            failures.append("an unresolved caller was ACCEPTED on the account branch")

    return failures


def run_all() -> dict:
    """Apply every behavioural mutant and record whether the oracle killed it."""
    baseline_source = read_source()
    baseline = load_module(baseline_source, "admin_utils_baseline")
    rows = [{
        "id": "BASELINE (unmutated)",
        "killed": None,
        "failures": oracle(baseline),
        "why": "Control. Must report zero failures or every kill below is meaningless.",
    }]

    for mutant in MUTANTS:
        mutated = load_module(
            apply_mutant(baseline_source, mutant), f"admin_utils_{mutant['id'].replace('-', '_')}"
        )
        failures = oracle(mutated)
        rows.append({
            "id": mutant["id"],
            "killed": bool(failures),
            "kill_kind": (
                "diagnostic" if mutant["id"] in EQUIVALENT_ON_AUTHORIZATION else "authorization"
            ),
            "failures": failures,
            "why": mutant["why"],
        })

    return {
        "total": len(MUTANTS),
        "killed": sum(1 for row in rows[1:] if row["killed"]),
        "baseline_clean": not rows[0]["failures"],
        "rows": rows,
    }


if __name__ == "__main__":  # pragma: no cover - operator convenience
    result = run_all()
    print(f"baseline_clean={result['baseline_clean']}  killed={result['killed']}/{result['total']}")
    for row in result["rows"]:
        print(f"  {str(row['killed']):>5}  {row.get('kill_kind','-'):<13} {row['id']}")
        for failure in row["failures"]:
            print(f"           - {failure}")
