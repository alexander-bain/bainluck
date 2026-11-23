"""Full 106-library transitive lock contract for ``backend/requirements.txt`` (#13491).

``#13494`` (351: A) pinned the 33 direct declarations in ``backend/requirements.txt``.
Follow-up ``#13491`` locks all 73 remaining transitive packages installed by the
``41de6f5c`` (``v6586``) production build log so future ``pip install -r`` runs on
Heroku and CI resolve the exact same 106-package graph without unannounced drift.
"""

from __future__ import annotations

import importlib.metadata as importlib_metadata
import re
from pathlib import Path

from packaging.requirements import Requirement

REQUIREMENTS = Path(__file__).resolve().parent.parent / "requirements.txt"

_EXACT_PIN_RE = re.compile(
    r"^[A-Za-z0-9_.-]+(?:\[[A-Za-z0-9_.,-]+\])?==[A-Za-z0-9_.+-]+$"
)

# Exact 106 packages installed by the live 41de6f5c (v6586) Heroku deploy build.
EXPECTED_41DE6F5C_LOCK: dict[str, str] = {
    "alembic": "1.20.1",
    "amqp": "5.4.2",
    "annotated-doc": "0.0.7",
    "annotated-types": "0.8.0",
    "anthropic": "2.11.0",
    "anyio": "4.16.0",
    "asyncpg": "0.32.0",
    "billiard": "4.3.2",
    "black": "26.10.1",
    "cachecontrol": "0.15.0",
    "celery": "5.6.3",
    "certifi": "2026.11.20",
    "cffi": "2.1.1",
    "charset-normalizer": "3.5.3",
    "click": "8.5.1",
    "click-didyoumean": "0.3.1",
    "click-plugins": "1.1.1.2",
    "click-repl": "0.4.1",
    "cryptography": "50.0.2",
    "deprecated": "1.3.1",
    "docstring-parser": "0.18.0",
    "fastapi": "0.136.3",
    "firebase-admin": "7.8.0",
    "google-analytics-data": "0.23.3",
    "google-api-core": "2.44.0",
    "google-api-python-client": "2.202.0",
    "google-auth": "2.63.1",
    "google-auth-httplib2": "0.4.4",
    "google-cloud-core": "2.8.0",
    "google-cloud-firestore": "2.34.1",
    "google-cloud-storage": "3.17.1",
    "google-crc32c": "1.9.0",
    "google-resumable-media": "2.11.0",
    "googleapis-common-protos": "1.76.0",
    "greenlet": "3.5.6",
    "grpcio": "1.85.3",
    "grpcio-status": "1.85.3",
    "h11": "0.16.0",
    "h2": "4.4.1",
    "hpack": "4.2.0",
    "httpcore": "1.0.9",
    "httpcore2": "2.16.2",
    "httplib2": "0.32.1",
    "httptools": "0.9.0",
    "httpx": "0.28.1",
    "httpx2": "2.16.2",
    "hyperframe": "6.1.0",
    "idna": "3.20",
    "iniconfig": "2.3.1",
    "jiter": "0.19.0",
    "kombu": "5.7.0",
    "limits": "5.8.0",
    "mako": "1.4.3",
    "markupsafe": "3.0.4",
    "msgpack": "1.2.4",
    "mypy-extensions": "1.2.0",
    "openai": "3.55.1",
    "opentelemetry-api": "1.45.2",
    "orjson": "3.13.0",
    "packaging": "26.3",
    "pathspec": "1.1.1",
    "pillow": "12.3.0",
    "platformdirs": "4.14.8",
    "pluggy": "1.7.0",
    "prompt-toolkit": "3.0.53",
    "proto-plus": "1.29.0",
    "protobuf": "7.36.2",
    "psycopg2-binary": "2.9.13",
    "pyasn1": "0.6.5",
    "pyasn1-modules": "0.4.2",
    "pycparser": "3.12",
    "pydantic": "2.14.4",
    "pydantic-core": "2.50.5",
    "pydantic-settings": "2.16.3",
    "pygments": "2.21.0",
    "pyjwt": "2.15.1",
    "pyparsing": "3.3.3",
    "pytest": "9.2.0",
    "pytest-asyncio": "1.5.0",
    "python-dateutil": "4.0.0",
    "python-dotenv": "1.2.4",
    "python-json-logger": "4.2.0",
    "pytokens": "0.4.1",
    "pyyaml": "6.0.3",
    "redis": "8.1.0",
    "requests": "2.34.2",
    "ruff": "0.17.6",
    "sentry-sdk": "2.75.0",
    "sniffio": "1.3.1",
    "sqlalchemy": "2.0.58",
    "sqlglot": "30.33.0",
    "starlette": "1.1.0",
    "truststore": "0.10.5",
    "typing-extensions": "4.16.0",
    "typing-inspection": "0.4.5",
    "tzdata": "2026.6",
    "tzlocal": "5.4.5",
    "uritemplate": "4.2.0",
    "urllib3": "2.8.0",
    "uvicorn": "0.54.0",
    "uvloop": "0.23.0",
    "vine": "5.1.0",
    "watchfiles": "1.3.0",
    "wcwidth": "0.9.5",
    "websockets": "17.4",
    "wrapt": "2.5.2",
}


def _normalise(name: str) -> str:
    return re.sub(r"[-_.]+", "-", name).lower()


def _parse_locked_manifest(text: str) -> tuple[dict[str, tuple[str, set[str]]], list[str]]:
    pins: dict[str, tuple[str, set[str]]] = {}
    duplicates: list[str] = []
    for lineno, raw in enumerate(text.splitlines(), 1):
        code = raw.split("#", 1)[0].strip()
        if not code:
            continue
        assert _EXACT_PIN_RE.fullmatch(code) and "*" not in code, (
            f"line {lineno} is not an exact pin: {code!r}"
        )
        req = Requirement(code)
        norm = _normalise(req.name)
        ver = code.split("==", 1)[1]
        if norm in pins:
            duplicates.append(f"line {lineno}: {norm}")
        pins[norm] = (ver, set(req.extras))
    return pins, duplicates


def test_requirements_locks_all_106_libraries_to_41de6f5c_without_duplicates():
    assert len(EXPECTED_41DE6F5C_LOCK) == 106
    pins, duplicates = _parse_locked_manifest(REQUIREMENTS.read_text(encoding="utf-8"))
    assert duplicates == [], f"duplicate requirements entries: {duplicates}"
    assert len(pins) == 106, f"expected 106 locked distributions, got {len(pins)}"
    actual_versions = {k: ver for k, (ver, _) in pins.items()}
    assert actual_versions == EXPECTED_41DE6F5C_LOCK


def test_locked_packages_match_transitive_requires_dist_when_installed_at_pinned_version():
    """Verify every required dependency of an installed pinned distribution is also locked."""
    pins, duplicates = _parse_locked_manifest(REQUIREMENTS.read_text(encoding="utf-8"))
    assert duplicates == []

    missing_edges: list[str] = []
    for norm, (pinned_ver, extras) in sorted(pins.items()):
        try:
            dist = importlib_metadata.distribution(norm)
        except importlib_metadata.PackageNotFoundError:
            continue
        if dist.version != pinned_ver:
            continue
        envs: list[dict[str, str] | None] = [None] + [{"extra": e} for e in sorted(extras)]
        for raw_req in dist.requires or ():
            dep = Requirement(raw_req)
            if dep.marker and not any(dep.marker.evaluate(env) for env in envs):
                continue
            dep_norm = _normalise(dep.name)
            if dep_norm not in pins:
                missing_edges.append(f"{norm}=={pinned_ver} requires {dep_norm} ({raw_req})")
    assert missing_edges == [], f"unpinned transitive dependencies: {missing_edges}"
