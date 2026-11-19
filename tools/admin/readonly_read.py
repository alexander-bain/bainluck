#!/usr/bin/env python3
"""Ruling 247: A — the single read-only admin-read script.

Reads the admin token from where it already lives (``ADMIN_TOKEN`` in the
process environment, or Heroku app ``bainluck`` config vars via ``~/.netrc``),
never prints, logs, or stores it, and allows ONLY ``GET`` on the short list of
addresses in ``tools/admin/readonly_allowlist.json``.

Each use prints one audit line (time in PT, lane, address, issue) for the lane
to post on the issue it serves.

Usage:
    python3 tools/admin/readonly_read.py \\
        --lane "Builder E" \\
        --issue 11937 \\
        /api/admin/ranking/grades?days=6 \\
        [--out /path/to/output.json]
"""

from __future__ import annotations

import argparse
import json
import netrc
import os
import re
import sys
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime
from pathlib import Path
from typing import Any, Callable, Optional
from zoneinfo import ZoneInfo

REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_ALLOWLIST_PATH = Path(__file__).resolve().with_name("readonly_allowlist.json")
DEFAULT_API = "https://api.bainluck.com"
HEROKU_APP = "bainluck"
PT = ZoneInfo("America/Los_Angeles")

_ISSUE_RE = re.compile(r"^#?([1-9][0-9]*)$")
_TEMPLATE_PARAM_RE = re.compile(r"\{[a-z_][a-z0-9_]*\}")


class ReadOnlyRefusedError(ValueError):
    """Raised when a request violates Ruling 247: A (non-GET or unlisted address)."""


class ReadOnlyRequestError(RuntimeError):
    """Raised on upstream HTTP/network failure, with any token scrubbed."""


def scrub_token(text: str, token: Optional[str]) -> str:
    """Remove any occurrence of ``token`` (raw or URL-encoded) from ``text``."""
    if not token:
        return text
    out = text.replace(token, "[REDACTED]")
    quoted = urllib.parse.quote(token, safe="")
    if quoted and quoted != token:
        out = out.replace(quoted, "[REDACTED]")
    return out


def load_allowlist(path: Path = DEFAULT_ALLOWLIST_PATH) -> list[dict[str, Any]]:
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(data, dict) or not isinstance(data.get("addresses"), list):
        raise ReadOnlyRefusedError("allowlist file is malformed")
    return data["addresses"]


def _template_to_regex(template: str) -> re.Pattern[str]:
    parts = template.split("/")
    regex_parts = []
    for part in parts:
        if _TEMPLATE_PARAM_RE.fullmatch(part):
            regex_parts.append(r"[A-Za-z0-9][A-Za-z0-9._-]{0,63}")
        else:
            regex_parts.append(re.escape(part))
    return re.compile("^" + "/".join(regex_parts) + "$")


def _path_matches_entry(path: str, entry: dict[str, Any]) -> bool:
    for denied in entry.get("deny_paths") or ():
        if isinstance(denied, str) and path == denied:
            return False
    exact = entry.get("path")
    if isinstance(exact, str) and path == exact:
        return True
    for template in entry.get("templates") or ():
        if isinstance(template, str) and _template_to_regex(template).fullmatch(path):
            return True
    return False


def validate_request(
    address: str,
    *,
    method: str = "GET",
    allowlist_path: Path = DEFAULT_ALLOWLIST_PATH,
) -> tuple[str, str]:
    """Validate method and address against Ruling 247: A.

    Returns ``(normalized_path, query)``. Raises :class:`ReadOnlyRefusedError`
    for any non-GET method, host override, traversal attempt, secret query
    parameter, or address not listed in ``allowlist_path``.
    """
    if not isinstance(method, str) or method.strip().upper() != "GET":
        raise ReadOnlyRefusedError(
            f"Refused non-GET method {method!r}: Ruling 247: A permits GET only."
        )
    if not isinstance(address, str) or not address.strip():
        raise ReadOnlyRefusedError("Refused empty address.")
    raw = address.strip()
    if any(ch.isspace() or ord(ch) < 0x20 for ch in raw):
        raise ReadOnlyRefusedError("Refused address containing whitespace or control characters.")
    if not raw.startswith("/") or raw.startswith("//") or "\\" in raw:
        raise ReadOnlyRefusedError(
            "Refused address: must be a relative path starting with a single '/'."
        )

    parsed = urllib.parse.urlsplit(raw)
    if parsed.scheme or parsed.netloc or parsed.fragment:
        raise ReadOnlyRefusedError(
            "Refused address: scheme, host, and fragments are not allowed."
        )

    raw_path = parsed.path
    decoded_path = urllib.parse.unquote(raw_path)
    for candidate in (raw_path, decoded_path):
        if "//" in candidate or "\\" in candidate:
            raise ReadOnlyRefusedError(f"Refused malformed path {raw_path!r}.")
        segments = candidate.split("/")[1:]
        if any(seg in ("", ".", "..") for seg in segments):
            raise ReadOnlyRefusedError(f"Refused traversal or empty segment in {raw_path!r}.")

    # Reject encoded slashes inside segments so %2f cannot smuggle extra segments.
    if "%2f" in raw_path.lower() or "%5c" in raw_path.lower():
        raise ReadOnlyRefusedError(f"Refused encoded separator in {raw_path!r}.")

    # Refuse secret/token query parameters (token belongs only in Authorization header).
    if parsed.query:
        for key, _ in urllib.parse.parse_qsl(parsed.query, keep_blank_values=True):
            if key.strip().lower() in ("secret", "token", "admin_token"):
                raise ReadOnlyRefusedError(
                    f"Refused query parameter {key!r}: credentials never travel in URLs."
                )

    entries = load_allowlist(allowlist_path)
    if not any(_path_matches_entry(raw_path, entry) for entry in entries):
        raise ReadOnlyRefusedError(
            f"Refused address {raw_path!r}: not listed in {allowlist_path.name} "
            "(adding an address needs Alex's yes once and a PR reviewed by Fable)."
        )

    return raw_path, parsed.query


def normalize_issue(issue: str) -> str:
    match = _ISSUE_RE.fullmatch(str(issue or "").strip())
    if not match:
        raise ReadOnlyRefusedError(
            f"Refused issue {issue!r}: pass a GitHub issue number like 11937 or #11937."
        )
    return f"#{match.group(1)}"


def format_audit_line(
    *,
    lane: str,
    address: str,
    issue: str,
    now: Optional[datetime] = None,
) -> str:
    """Format the one-line record each lane posts on the issue it serves."""
    lane_clean = " ".join(str(lane or "").split())
    if not lane_clean:
        raise ReadOnlyRefusedError("Refused empty --lane.")
    issue_tag = normalize_issue(issue)
    stamp = (now or datetime.now(PT)).astimezone(PT)
    time_str = stamp.strftime("%Y-%m-%d %-I:%M %p PT")
    return f"admin-read | {time_str} | lane={lane_clean} | GET {address} | issue={issue_tag}"


_ALLOWED_PROD_HOST = "api.bainluck.com"
_ALLOWED_LOCAL_HOSTS = frozenset({"localhost", "127.0.0.1"})


def _validate_api_base(api_base: str) -> tuple[str, bool]:
    """Return ``(normalized_base, is_prod)``.

    Production reads are strictly pinned to ``https://api.bainluck.com``.
    Local ``http://localhost`` / ``http://127.0.0.1`` bases are permitted only
    for local tests and must never fetch the production Heroku token.
    """
    parsed = urllib.parse.urlsplit(api_base.strip())
    host = (parsed.hostname or "").lower()
    if parsed.username or parsed.password:
        raise ReadOnlyRefusedError("Refused BAINLUCK_API base with embedded credentials.")
    if parsed.path not in ("", "/") or parsed.query or parsed.fragment:
        raise ReadOnlyRefusedError("Refused BAINLUCK_API base with path, query, or fragment.")
    if parsed.scheme == "https" and host == _ALLOWED_PROD_HOST and parsed.port in (None, 443):
        return f"https://{_ALLOWED_PROD_HOST}", True
    if parsed.scheme == "http" and host in _ALLOWED_LOCAL_HOSTS:
        return api_base.strip().rstrip("/"), False
    raise ReadOnlyRefusedError(
        f"Refused BAINLUCK_API base {api_base!r}: pinned to https://{_ALLOWED_PROD_HOST} "
        "(or http://localhost / http://127.0.0.1 for local tests)."
    )


class _NoRedirectHandler(urllib.request.HTTPRedirectHandler):
    """Refuse all 3xx redirects so the Authorization header can never leave api.bainluck.com."""

    def redirect_request(self, req, fp, code, msg, headers, newurl):
        raise urllib.error.HTTPError(
            req.full_url,
            code,
            f"Refused HTTP {code} redirect (redirects are disabled under Ruling 247: A)",
            headers,
            fp,
        )


def _default_no_redirect_urlopen(req, timeout=60):
    opener = urllib.request.build_opener(_NoRedirectHandler())
    return opener.open(req, timeout=timeout)


def read_admin_token(
    *,
    allow_heroku: bool = True,
    urlopen: Optional[Callable[..., Any]] = None,
    netrc_loader: Callable[[], netrc.netrc] = netrc.netrc,
) -> str:
    """Read ADMIN_TOKEN in memory from env or Heroku Platform API (~/.netrc).

    Never opens any local secret file, and never prints, logs, or stores the token.
    When ``allow_heroku`` is False (any non-production/localhost base), the real
    Heroku token is never fetched.
    """
    token = os.environ.get("ADMIN_TOKEN")
    if token:
        return token
    if not allow_heroku:
        raise ReadOnlyRefusedError(
            "Refused reading production Heroku ADMIN_TOKEN for a non-production base; "
            "set ADMIN_TOKEN in the environment for localhost tests."
        )
    opener = urlopen or _default_no_redirect_urlopen
    auth = netrc_loader().authenticators("api.heroku.com")
    if not auth:
        raise ReadOnlyRequestError(
            "ADMIN_TOKEN unset and no api.heroku.com entry in ~/.netrc"
        )
    heroku_key = auth[2]
    req = urllib.request.Request(
        f"https://api.heroku.com/apps/{HEROKU_APP}/config-vars",
        headers={
            "Accept": "application/vnd.heroku+json; version=3",
            "Authorization": f"Bearer {heroku_key}",
        },
        method="GET",
    )
    try:
        with opener(req, timeout=30) as resp:
            payload = json.load(resp)
    except Exception as exc:
        raise ReadOnlyRequestError(
            f"Failed to read ADMIN_TOKEN from Heroku: {scrub_token(str(exc), heroku_key)}"
        ) from None
    token = payload.get("ADMIN_TOKEN") if isinstance(payload, dict) else None
    if not token:
        raise ReadOnlyRequestError("ADMIN_TOKEN is not set on the Heroku app")
    return str(token)


def readonly_get(
    address: str,
    *,
    lane: str,
    issue: str,
    method: str = "GET",
    api_base: Optional[str] = None,
    allowlist_path: Path = DEFAULT_ALLOWLIST_PATH,
    token_provider: Optional[Callable[[], str]] = None,
    urlopen: Optional[Callable[..., Any]] = None,
    now: Optional[datetime] = None,
) -> tuple[Any, str]:
    """Execute one allowlisted read-only admin GET and return ``(payload, audit_line)``."""
    path, query = validate_request(address, method=method, allowlist_path=allowlist_path)
    canonical_address = f"{path}?{query}" if query else path
    audit_line = format_audit_line(
        lane=lane, address=canonical_address, issue=issue, now=now
    )
    base, is_prod = _validate_api_base(api_base or os.environ.get("BAINLUCK_API") or DEFAULT_API)
    opener = urlopen or _default_no_redirect_urlopen
    token = (
        token_provider
        or (lambda: read_admin_token(allow_heroku=is_prod, urlopen=opener))
    )()

    req = urllib.request.Request(
        f"{base}{canonical_address}",
        headers={"Authorization": f"Bearer {token}"},
        method="GET",
    )
    try:
        with opener(req, timeout=60) as resp:
            status = getattr(resp, "status", None)
            if isinstance(status, int) and 300 <= status < 400:
                raise ReadOnlyRequestError(
                    f"GET {path}: refused HTTP {status} redirect"
                )
            raw_body = resp.read().decode("utf-8", errors="replace")
    except ReadOnlyRequestError:
        raise
    except urllib.error.HTTPError as exc:
        err_body = ""
        try:
            err_body = exc.read()[:300].decode("utf-8", errors="replace") if exc.fp else ""
        except Exception:
            err_body = ""
        safe_body = scrub_token(err_body, token)
        safe_reason = scrub_token(str(exc.reason or ""), token)
        detail = safe_body or safe_reason
        raise ReadOnlyRequestError(
            f"GET {path}: HTTP {exc.code} {detail}".strip()
        ) from None
    except Exception as exc:
        safe_err = scrub_token(str(exc), token)
        raise ReadOnlyRequestError(f"GET {path}: {safe_err}") from None

    safe_raw = scrub_token(raw_body, token)
    try:
        payload = json.loads(safe_raw)
    except json.JSONDecodeError as exc:
        raise ReadOnlyRequestError(
            f"GET {path}: invalid JSON response ({scrub_token(str(exc), token)})"
        ) from None

    return payload, audit_line


def main(argv: Optional[list[str]] = None) -> int:
    parser = argparse.ArgumentParser(
        description="Ruling 247: A read-only admin GET helper (allowlisted addresses only)."
    )
    parser.add_argument("address", help="Allowlisted relative admin path (plus optional query).")
    parser.add_argument("--lane", required=True, help="Lane name (e.g. 'Builder E').")
    parser.add_argument("--issue", required=True, help="GitHub issue number this read serves.")
    parser.add_argument(
        "--method",
        default="GET",
        help="HTTP method (only GET is allowed; anything else is refused).",
    )
    parser.add_argument(
        "--out",
        default=None,
        help="Optional path to write the JSON response body (audit line prints to stdout).",
    )
    args = parser.parse_args(argv)

    try:
        payload, audit_line = readonly_get(
            args.address,
            lane=args.lane,
            issue=args.issue,
            method=args.method,
        )
    except (ReadOnlyRefusedError, ReadOnlyRequestError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2

    if args.out:
        Path(args.out).write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
        print(audit_line)
    else:
        print(audit_line, file=sys.stderr)
        print(json.dumps(payload, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
