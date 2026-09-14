#!/usr/bin/env python3
"""native — read App Store Connect's own record of our builds.

WHY THIS EXISTS
---------------
`native-upload.sh` grades the DELIVERY (did altool produce an .ipa, did it
report product-errors). It cannot tell you what Apple then did with it: a
delivery that exits 0 and prints no error still leaves the build in
PROCESSING for minutes, and can land in INVALID an hour later with the reason
only visible here. The directive for this lane says to report the PROCESSING
state from /v1/builds, not the upload's exit code, and until now nothing in
the repo could read it.

It is also the only honest answer to "is build N already taken?" — Apple
refuses a re-used CFBundleVersion, and the project file's highest number is a
guess about our tree, not a fact about Apple's.

WHAT IT PRINTS
  every build Apple holds for the app, newest first:
  version · processingState · expired? · uploaded-at · the pre-release version
  it belongs to. Plus, for INVALID/FAILED builds, whatever reason Apple gives.

CREDENTIALS (the same three the uploader uses; never printed, never committed)
  ASC_KEY_ID  ASC_ISSUER_ID  ASC_KEY_PATH   — from ~/.claude/.env

TWO WAYS THE CREDENTIALS READ ABSENT WHILE BEING PERFECTLY FINE. Both were hit
in one session (native/159) and both used to end here with a wrong diagnosis:

  1. `~/.claude/.env` holds BARE assignments, no `export`. So `source
     ~/.claude/.env` sets shell variables that never reach a python child, and
     this tool printed "missing credential(s)" with `source ~/.claude/.env` as
     the remedy — an instruction that cannot work, so the reader runs it, sees
     the same line, and concludes the credentials are not on the machine. We
     now READ the file ourselves for whatever the environment did not supply,
     which makes the remedy real instead of instructional. (`set -a; source
     ~/.claude/.env; set +a` still works and still wins; this is the fallback.)
  2. ASC_KEY_PATH points into ~/Downloads, which this sandbox refuses with
     EPERM — a refusal that reads exactly like absence. The genuine readable
     copy is the one `native-upload.sh` itself stages to KEY_HOME, so we try
     that too, and when nothing opens we name every path tried WITH its own
     errno, because "permission denied" and "no such file" are different bugs.

EXIT
  0  Apple answered and the builds are listed (an empty list is an answer)
  1  Apple answered with an error status
  2  the rig is unusable — missing credential, unreadable key, no app found

  --self-check  offline assertions over the .env parser and the key-path
                chooser; no network, no credentials, no Apple.
"""
from __future__ import annotations

import json
import os
import sys
import time
import urllib.error
import urllib.request

BUNDLE_ID = "com.bainluck.Bain-Luck"
API = "https://api.appstoreconnect.apple.com/v1"
ENV_FILE = "~/.claude/.env"
# Where native-upload.sh stages the .p8 before handing it to altool. Apple's own
# tools look here by convention, so it is the one copy that is readable when the
# configured ASC_KEY_PATH is not.
KEY_HOME = "~/.appstoreconnect/private_keys"

CRED_NAMES = ("ASC_KEY_ID", "ASC_ISSUER_ID", "ASC_KEY_PATH")


def die(msg: str, code: int = 2) -> None:
    print(f"ASC: {msg}")
    sys.exit(code)


def parse_env_file(text: str) -> dict:
    """Pull `NAME=value` assignments out of a dotenv-shaped file.

    Deliberately small: this reads OUR file, not arbitrary shell. It tolerates
    the three things ~/.claude/.env actually contains — comments, blank lines,
    and an optional `export ` prefix — and strips one layer of matching quotes.
    Values are returned to the caller and never printed anywhere.
    """
    out = {}
    for raw in text.splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        if line.startswith("export "):
            line = line[len("export ") :].lstrip()
        name, _, value = line.partition("=")
        name = name.strip()
        if not name:
            continue
        value = value.strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in "\"'":
            value = value[1:-1]
        out[name] = value
    return out


def resolve_credentials() -> dict:
    """The three credentials: environment first, then ~/.claude/.env.

    The environment WINS — a caller who exported something meant it. The file
    is only consulted for names the environment left empty, which is the case
    the old code mis-reported as "missing".
    """
    found = {n: os.environ.get(n) or "" for n in CRED_NAMES}
    if all(found.values()):
        return found
    try:
        with open(os.path.expanduser(ENV_FILE)) as fh:
            from_file = parse_env_file(fh.read())
    except OSError:
        # No readable env file is not itself the error; the missing-name report
        # below is, and it stays accurate either way.
        from_file = {}
    for name in CRED_NAMES:
        if not found[name]:
            found[name] = from_file.get(name, "")
    return found


def key_candidates(key_path: str, key_id: str) -> list:
    """Ordered, de-duplicated paths to try for the .p8, most-configured first.

    Pure so the ordering is assertable without touching a filesystem: the
    configured path is always attempted first, and the canonical staged copy is
    a fallback, never a silent override of what the operator set.
    """
    out = []
    for cand in (key_path, f"{KEY_HOME}/AuthKey_{key_id}.p8" if key_id else ""):
        if not cand:
            continue
        full = os.path.expanduser(cand)
        if full not in out:
            out.append(full)
    return out


def read_key(key_path: str, key_id: str) -> tuple:
    """Return (key text, path it came from), or die naming every path tried.

    Each failure carries its own errno text. A single merged "cannot read key"
    would collapse EPERM and ENOENT into one sentence, and those send a reader
    to two completely different places.
    """
    tried = []
    for cand in key_candidates(key_path, key_id):
        try:
            with open(cand) as fh:
                return fh.read(), cand
        except OSError as exc:
            tried.append(f"{cand}: {exc.strerror or exc}")
    die("cannot read the ASC private key — tried:\n  " + "\n  ".join(tried))


def token() -> str:
    try:
        import jwt
    except ImportError:
        die("PyJWT is not importable; `pip3 install pyjwt cryptography`")
    creds = resolve_credentials()
    key_id = creds["ASC_KEY_ID"]
    issuer = creds["ASC_ISSUER_ID"]
    key_path = creds["ASC_KEY_PATH"]
    missing = [n for n in CRED_NAMES if not creds[n]]
    if missing:
        die(
            f"missing credential(s): {', '.join(missing)} — not in the environment "
            f"and not in {ENV_FILE}. That file holds BARE assignments, so plain "
            "`source` does not reach this process; use "
            "`set -a; source ~/.claude/.env; set +a`."
        )
    private_key, _used = read_key(key_path, key_id)
    now = int(time.time())
    return jwt.encode(
        {"iss": issuer, "iat": now, "exp": now + 900, "aud": "appstoreconnect-v1"},
        private_key,
        algorithm="ES256",
        headers={"kid": key_id, "typ": "JWT"},
    )


def get(path: str, bearer: str) -> dict:
    req = urllib.request.Request(
        path if path.startswith("http") else f"{API}{path}",
        headers={"Authorization": f"Bearer {bearer}"},
    )
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            return json.loads(resp.read())
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", "replace")[:600]
        print(f"ASC: HTTP {exc.code} on {path}\n{body}")
        sys.exit(1)
    except urllib.error.URLError as exc:
        die(f"cannot reach App Store Connect: {exc.reason}")


def main() -> None:
    bearer = token()
    apps = get(f"/apps?filter[bundleId]={BUNDLE_ID}", bearer).get("data", [])
    if not apps:
        die(f"no app with bundleId {BUNDLE_ID} on this key's team")
    app = apps[0]
    app_id = app["id"]
    print(f"app     : {app['attributes'].get('name')}  ({BUNDLE_ID}, id {app_id})")

    # No `fields[builds]` here on purpose: restricting the sparse fieldset also
    # drops the `relationships` block, so the included preReleaseVersion can
    # never be joined back and every train prints as "?" — a silent hole that
    # reads like Apple not knowing which version a build belongs to.
    builds = get(
        f"/builds?filter[app]={app_id}&limit=20&sort=-version"
        "&include=preReleaseVersion",
        bearer,
    )
    rows = builds.get("data", [])
    pre = {
        item["id"]: item["attributes"].get("version")
        for item in builds.get("included", [])
        if item["type"] == "preReleaseVersions"
    }
    if not rows:
        print("builds  : NONE — Apple holds no build for this app")
        return
    print(f"builds  : {len(rows)} (newest first)")
    for row in rows:
        attrs = row["attributes"]
        rel = row.get("relationships", {}).get("preReleaseVersion", {}).get("data")
        train = pre.get(rel["id"]) if rel else "?"
        flags = " EXPIRED" if attrs.get("expired") else ""
        print(
            f"  {train} ({attrs.get('version')})"
            f"  {attrs.get('processingState')}{flags}"
            f"  uploaded {attrs.get('uploadedDate')}"
        )


def self_check() -> None:
    """Offline guard for the two things that made good credentials read absent.

    It lives in the script rather than backend/tests/ on purpose: a file under
    backend/tests/ forces a Heroku release (notice 10's tests-only clause) and
    this tool is never imported by the app. One command, no network, no key.
    """
    global ENV_FILE
    import contextlib
    import tempfile

    failures = []
    ran = 0

    def check(name, got, want):
        # The summary line reports a COUNT, so count it here rather than typing
        # a number into the string that nothing keeps honest.
        nonlocal ran
        ran += 1
        if got != want:
            failures.append(f"{name}: got {got!r}, want {want!r}")

    # --- the parser: every shape ~/.claude/.env actually contains -------------
    parsed = parse_env_file(
        "\n".join(
            [
                "# a comment",
                "",
                "ASC_KEY_ID=PLAIN",
                "export ASC_ISSUER_ID=EXPORTED",
                'ASC_KEY_PATH="~/quoted/path.p8"',
                "SINGLE='sq'",
                "EQUALS=a=b",
                "NOT_AN_ASSIGNMENT",
                "  SPACED  =  trimmed  ",
            ]
        )
    )
    check("bare assignment", parsed.get("ASC_KEY_ID"), "PLAIN")
    # The `export ` prefix must be stripped from the NAME, not kept as part of
    # it — otherwise the name never matches and the credential reads absent.
    check("export prefix stripped", parsed.get("ASC_ISSUER_ID"), "EXPORTED")
    check("double quotes stripped", parsed.get("ASC_KEY_PATH"), "~/quoted/path.p8")
    check("single quotes stripped", parsed.get("SINGLE"), "sq")
    # Split on the FIRST `=` only; a value may legitimately contain one.
    check("value keeps inner =", parsed.get("EQUALS"), "a=b")
    check("comment not a key", "# a comment" in parsed, False)
    check("no-equals line skipped", "NOT_AN_ASSIGNMENT" in parsed, False)
    check("name and value trimmed", parsed.get("SPACED"), "trimmed")

    # --- the chooser: configured path first, canonical as a fallback ----------
    cands = key_candidates("~/Downloads/AuthKey_ABC.p8", "ABC")
    check("configured path is tried first", cands[0].endswith("/Downloads/AuthKey_ABC.p8"), True)
    check("canonical copy is tried too", len(cands), 2)
    check(
        "canonical is the staged location",
        cands[1] == os.path.expanduser(f"{KEY_HOME}/AuthKey_ABC.p8"),
        True,
    )
    # Configured path ALREADY the canonical one must not be opened twice — a
    # duplicate would report the same errno twice and read as two failures.
    check("no duplicate when they coincide", len(key_candidates(f"{KEY_HOME}/AuthKey_ABC.p8", "ABC")), 1)
    # Without a key id there is no canonical name to build, so do not invent one.
    check("no key id, no canonical guess", len(key_candidates("~/x.p8", "")), 1)
    check("no paths at all", key_candidates("", ""), [])

    # --- resolution order: the environment wins, the file fills the gaps ------
    saved = {n: os.environ.get(n) for n in CRED_NAMES}
    saved_env_file = ENV_FILE
    try:
        with tempfile.NamedTemporaryFile("w", suffix=".env", delete=False) as fh:
            fh.write("ASC_KEY_ID=FROMFILE\nASC_ISSUER_ID=FROMFILE\nASC_KEY_PATH=/tmp/f.p8\n")
            ENV_FILE = fh.name
        for n in CRED_NAMES:
            os.environ.pop(n, None)
        # Nothing exported: this is the case the old code called "missing".
        check("file fills an empty environment", resolve_credentials()["ASC_KEY_ID"], "FROMFILE")
        os.environ["ASC_KEY_ID"] = "FROMENV"
        got = resolve_credentials()
        check("environment wins", got["ASC_KEY_ID"], "FROMENV")
        check("file still fills the rest", got["ASC_ISSUER_ID"], "FROMFILE")
        ENV_FILE = "~/definitely/no/such/file.env"
        os.environ.pop("ASC_KEY_ID", None)
        # An unreadable env file is not a crash; it just supplies nothing.
        check("unreadable env file yields empties", resolve_credentials()["ASC_KEY_ID"], "")
    finally:
        # suppress() rather than `except OSError: pass` — the bare form is a
        # CodeQL py/empty-except finding, and a note-level alert on a temp-file
        # unlink is pure noise in every later notice-32 read.
        with contextlib.suppress(OSError):
            os.unlink(fh.name)
        ENV_FILE = saved_env_file
        for n, v in saved.items():
            if v is None:
                os.environ.pop(n, None)
            else:
                os.environ[n] = v

    if failures:
        print("SELF-CHECK FAILED")
        for f in failures:
            print(f"  {f}")
        sys.exit(1)
    print(
        f"SELF-CHECK PASS — {ran} assertions over "
        "parse_env_file/key_candidates/resolve_credentials"
    )
    sys.exit(0)


if __name__ == "__main__":
    if "--self-check" in sys.argv:
        self_check()
    main()
