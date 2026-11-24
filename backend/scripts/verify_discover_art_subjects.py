"""Verify that TMDB and ESPN records in verified_discover_art.json match their declared subjects.

Usage:
    python3 scripts/verify_discover_art_subjects.py --scope new --base-ref origin/master
    python3 scripts/verify_discover_art_subjects.py --scope old --base-ref origin/master
    python3 scripts/verify_discover_art_subjects.py --scope all --json-out /tmp/art_verify.json
"""

from __future__ import annotations

import argparse
from concurrent.futures import ThreadPoolExecutor, as_completed
import html as html_lib
import json
from pathlib import Path
import re
import subprocess
import sys
import time
from typing import Any, Mapping, Optional
import unicodedata
import urllib.error
import urllib.parse
import urllib.request

BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from app.utils.agent_origin import curl_args, tagged  # noqa: E402

REPO_ROOT = Path(__file__).resolve().parents[2]
ART_JSON_PATH = REPO_ROOT / "backend" / "data" / "discover" / "verified_discover_art.json"

_TMDB_SOURCE_RE = re.compile(r"^https://www\.themoviedb\.org/(person|movie|tv)/(\d+)(?:-[^/?#]+)?/?$")
_ESPN_SOURCE_RE = re.compile(r"^https://www\.espn\.com/([a-z0-9_-]+)/player/_/id/(\d+)(?:/[^?#]+)?/?$")
_ESPN_IMG_RE = re.compile(r"https://a\.espncdn\.com/i/headshots/([a-z0-9_-]+)/players/full/(\d+)\.png", re.I)

_ESPN_SPORT_API_PATHS: dict[str, tuple[str, ...]] = {
    "nba": ("basketball/nba",),
    "wnba": ("basketball/wnba",),
    "nfl": ("football/nfl",),
    "nhl": ("hockey/nhl",),
    "mlb": ("baseball/mlb",),
    "mma": ("mma/ufc",),
    "ufc": ("mma/ufc",),
    "golf": ("golf/pga", "golf/lpga"),
}

_USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
)


def _fold(text: str) -> str:
    decomposed = "".join(
        c for c in unicodedata.normalize("NFKD", html_lib.unescape(text or "")) if not unicodedata.combining(c)
    )
    cleaned = re.sub(r"[^a-z0-9]+", " ", decomposed.lower()).strip()
    return cleaned


def _names_match(aliases: list[str], page_title: str) -> bool:
    pt = _fold(page_title)
    if not pt:
        return False
    for alias in aliases:
        af = _fold(alias)
        if not af:
            continue
        if af == pt or af in pt or pt in af:
            return True
        a_tokens = [t for t in af.split() if len(t) >= 2]
        p_tokens = set(pt.split())
        if a_tokens and all(t in p_tokens for t in a_tokens):
            return True
    return False


def _extract_filename(url: str) -> str:
    clean = (url or "").split("?", 1)[0].strip()
    return clean.rsplit("/", 1)[-1]


def _url_hostname(url: str) -> str:
    return (urllib.parse.urlparse(url).hostname or "").lower()


def _curl_fetch(url: str, *, retries: int = 3) -> tuple[int, str]:
    last_err = ""
    for attempt in range(retries + 1):
        proc = subprocess.run(
            [
                "curl",
                "-sL",
                "-m",
                "15",
                "-A",
                _USER_AGENT,
                "-H",
                "Accept-Language: en-US,en;q=0.9",
                *curl_args(url),
                "-w",
                "\n__HTTP_CODE__:%{http_code}",
                url,
            ],
            capture_output=True,
            text=True,
        )
        out = proc.stdout or ""
        if "__HTTP_CODE__:" in out:
            body, code_str = out.rsplit("\n__HTTP_CODE__:", 1)
            try:
                code = int(code_str.strip())
                if code == 429 and attempt < retries:
                    time.sleep(2.0 * (attempt + 1))
                    continue
                return code, body
            except ValueError:
                # Non-numeric HTTP code trailer falls through to retry/error return.
                last_err = f"invalid_http_code:{code_str.strip()}"
                continue
        last_err = proc.stderr.strip() or f"rc={proc.returncode}"
    return 0, last_err


def _head_status(url: str) -> int:
    req = urllib.request.Request(url, method="HEAD", headers=tagged(url, {"User-Agent": _USER_AGENT}))
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            return int(resp.status)
    except urllib.error.HTTPError as exc:
        if exc.code == 405:
            req_get = urllib.request.Request(url, method="GET", headers=tagged(url, {"User-Agent": _USER_AGENT}))
            with urllib.request.urlopen(req_get, timeout=10) as resp:
                return int(resp.status)
        return int(exc.code)
    except Exception:
        return 0


def _parse_tmdb_page(body: str) -> tuple[str, list[str]]:
    title = ""
    og_title = re.search(r'<meta[^>]+property=["\']og:title["\'][^>]+content=["\']([^"\']+)["\']', body, re.I)
    if og_title:
        title = html_lib.unescape(og_title.group(1)).strip()
    if not title:
        tag_title = re.search(r"<title>([^<]+)</title>", body, re.I)
        if tag_title:
            title = html_lib.unescape(tag_title.group(1)).split("—", 1)[0].split(" - ", 1)[0].strip()

    image_hashes: list[str] = []
    # Prefer primary og:image and main poster/profile element on the TMDB entity header.
    patterns = (
        r'<meta[^>]+property=["\']og:image["\'][^>]+content=["\']https?://(?:image\.tmdb|media\.themoviedb)\.org/t/p/[^/"\']+/([^"\'?#]+)["\']',
        r'<img[^>]+class=["\'](?:poster|profile)\s+w-full["\'][^>]+src=["\']https?://(?:image\.tmdb|media\.themoviedb)\.org/t/p/[^/"\']+/([^"\'?#]+)["\']',
    )
    for pat in patterns:
        for m in re.finditer(pat, body, re.I):
            fname = m.group(1).strip()
            if fname and fname not in image_hashes:
                image_hashes.append(fname)
    return title, image_hashes


def _infer_tmdb_source_page(entry: Mapping[str, Any]) -> Optional[str]:
    if entry.get("tmdb_person_id"):
        return f"https://www.themoviedb.org/person/{int(entry['tmdb_person_id'])}"
    if entry.get("tmdb_movie_id"):
        return f"https://www.themoviedb.org/movie/{int(entry['tmdb_movie_id'])}"
    if entry.get("tmdb_tv_id"):
        return f"https://www.themoviedb.org/tv/{int(entry['tmdb_tv_id'])}"
    return None


def _infer_espn_source_page(img_url: str) -> Optional[str]:
    m = _ESPN_IMG_RE.match(img_url or "")
    if not m:
        return None
    sport, aid = m.group(1).lower(), m.group(2)
    return f"https://www.espn.com/{sport}/player/_/id/{aid}"


def _verify_tmdb_entry(entry: Mapping[str, Any], *, infer_source: bool = False) -> dict[str, Any]:
    key = str(entry.get("entity_key") or "")
    aliases = [str(a) for a in (entry.get("aliases") or ()) if a]
    img_url = str(entry.get("url") or "")
    expected_file = _extract_filename(img_url)
    explicit_source = str(entry.get("source_page") or "").strip()
    inferred_source = _infer_tmdb_source_page(entry) if (not explicit_source and infer_source) else None
    source_page = explicit_source or inferred_source or ""

    result: dict[str, Any] = {
        "entity_key": key,
        "provider": "tmdb",
        "aliases": aliases,
        "source_page": explicit_source or None,
        "inferred_source_page": inferred_source,
        "url": img_url,
        "expected_file": expected_file,
        "page_subject": None,
        "page_file": None,
        "image_http": None,
        "ok": False,
        "inferred_ok": None,
        "error": None,
    }

    if not source_page:
        result["error"] = "missing_source_page_and_no_tmdb_id" if infer_source else "missing_source_page"
        return result

    m = _TMDB_SOURCE_RE.match(source_page)
    if not m:
        result["error"] = f"invalid_tmdb_source_page:{source_page}"
        return result

    img_status = _head_status(img_url)
    result["image_http"] = img_status
    if img_status != 200:
        result["error"] = f"image_http_{img_status}"
        return result

    code, body = _curl_fetch(source_page)
    if code != 200 or not body:
        result["error"] = f"source_page_http_{code}"
        return result

    page_title, page_hashes = _parse_tmdb_page(body)
    result["page_subject"] = page_title or None
    result["page_file"] = page_hashes[0] if page_hashes else None

    if not page_title or not _names_match(aliases, page_title):
        result["error"] = f"subject_mismatch:page={page_title!r}"
        return result

    if expected_file not in page_hashes:
        result["error"] = f"image_file_mismatch:expected={expected_file},page={page_hashes}"
        return result

    result["page_file"] = expected_file
    if explicit_source:
        result["ok"] = True
    else:
        result["inferred_ok"] = True
        result["error"] = "missing_source_page"
    return result


def _fetch_espn_athletes(sport_token: str, athlete_id: str) -> list[tuple[dict[str, Any], str]]:
    paths = _ESPN_SPORT_API_PATHS.get(sport_token.lower(), ())
    found: list[tuple[dict[str, Any], str]] = []
    for api_path in paths:
        api_url = f"https://site.web.api.espn.com/apis/common/v3/sports/{api_path}/athletes/{athlete_id}"
        req = urllib.request.Request(api_url, headers=tagged(api_url, {"User-Agent": _USER_AGENT}))
        try:
            with urllib.request.urlopen(req, timeout=12) as resp:
                data = json.loads(resp.read().decode("utf-8"))
                athlete = data.get("athlete")
                if isinstance(athlete, dict) and str(athlete.get("id") or "") == str(athlete_id):
                    found.append((athlete, api_url))
        except Exception:
            continue
    return found


def _verify_espn_entry(entry: Mapping[str, Any], *, infer_source: bool = False) -> dict[str, Any]:
    key = str(entry.get("entity_key") or "")
    aliases = [str(a) for a in (entry.get("aliases") or ()) if a]
    img_url = str(entry.get("url") or "")
    explicit_source = str(entry.get("source_page") or "").strip()
    inferred_source = _infer_espn_source_page(img_url) if (not explicit_source and infer_source) else None
    source_page = explicit_source or inferred_source or ""

    result: dict[str, Any] = {
        "entity_key": key,
        "provider": "espn",
        "aliases": aliases,
        "source_page": explicit_source or None,
        "inferred_source_page": inferred_source,
        "url": img_url,
        "expected_file": _extract_filename(img_url),
        "page_subject": None,
        "page_file": None,
        "image_http": None,
        "ok": False,
        "inferred_ok": None,
        "error": None,
    }

    if not source_page:
        result["error"] = "missing_source_page"
        return result

    m_src = _ESPN_SOURCE_RE.match(source_page)
    if not m_src:
        result["error"] = f"invalid_espn_source_page:{source_page}"
        return result
    src_sport, src_id = m_src.group(1), m_src.group(2)

    m_img = _ESPN_IMG_RE.match(img_url)
    if not m_img:
        result["error"] = f"unexpected_espn_image_url:{img_url}"
        return result
    img_sport, img_id = m_img.group(1), m_img.group(2)
    if img_id != src_id:
        result["error"] = f"athlete_id_mismatch:source={src_id},url={img_id}"
        return result

    img_status = _head_status(img_url)
    result["image_http"] = img_status
    if img_status != 200:
        result["error"] = f"image_http_{img_status}"
        return result

    candidates = _fetch_espn_athletes(src_sport or img_sport, src_id)
    if not candidates:
        result["error"] = f"espn_api_lookup_failed:{src_sport}/{src_id}"
        return result

    matched_athlete: Optional[dict[str, Any]] = None
    for athlete, _api_url in candidates:
        cand_names = [
            str(x).strip()
            for x in (athlete.get("displayName"), athlete.get("fullName"), athlete.get("shortName"))
            if x
        ]
        if any(_names_match(aliases, nm) for nm in cand_names):
            matched_athlete = athlete
            break

    if matched_athlete is None:
        first_athlete = candidates[0][0]
        display_name = str(first_athlete.get("displayName") or first_athlete.get("fullName") or "").strip()
        result["page_subject"] = display_name or None
        result["error"] = f"subject_mismatch:espn={display_name!r}"
        return result

    display_name = str(matched_athlete.get("displayName") or matched_athlete.get("fullName") or "").strip()
    headshot_href = str((matched_athlete.get("headshot") or {}).get("href") or "").strip()
    result["page_subject"] = display_name or None
    result["page_file"] = _extract_filename(headshot_href) if headshot_href else f"{src_id}.png"

    if headshot_href and _extract_filename(headshot_href) != result["expected_file"]:
        result["error"] = f"headshot_file_mismatch:expected={result['expected_file']},espn={headshot_href}"
        return result

    if explicit_source:
        result["ok"] = True
    else:
        result["inferred_ok"] = True
        result["error"] = "missing_source_page"
    return result


def _load_base_keys(base_ref: str) -> set[str]:
    raw = subprocess.check_output(
        ["git", "show", f"{base_ref}:backend/data/discover/verified_discover_art.json"],
        cwd=REPO_ROOT,
        text=True,
    )
    return {str(e.get("entity_key") or "") for e in json.loads(raw).get("entries") or ()}


def verify_records(
    entries: list[dict[str, Any]],
    *,
    scope: str = "new",
    base_ref: str = "origin/master",
    max_workers: int = 8,
    infer_source: bool = False,
) -> dict[str, Any]:
    base_keys = _load_base_keys(base_ref) if scope in {"new", "old"} else set()
    targets: list[dict[str, Any]] = []
    for entry in entries:
        url = str(entry.get("url") or "")
        host = _url_hostname(url)
        is_tmdb = host == "image.tmdb.org"
        is_espn = host == "a.espncdn.com"
        if not (is_tmdb or is_espn):
            continue
        key = str(entry.get("entity_key") or "")
        if scope == "new" and key in base_keys:
            continue
        if scope == "old" and key not in base_keys:
            continue
        targets.append(entry)

    results: list[dict[str, Any]] = []
    with ThreadPoolExecutor(max_workers=max_workers) as pool:
        futs = {}
        for idx, entry in enumerate(targets):
            fn = (
                _verify_tmdb_entry
                if _url_hostname(str(entry.get("url") or "")) == "image.tmdb.org"
                else _verify_espn_entry
            )
            futs[pool.submit(fn, entry, infer_source=infer_source)] = idx
        ordered: dict[int, dict[str, Any]] = {}
        for fut in as_completed(futs):
            ordered[futs[fut]] = fut.result()
        results = [ordered[i] for i in range(len(targets))]

    passed = sum(1 for r in results if r["ok"])
    failed = [r for r in results if not r["ok"]]
    return {
        "scope": scope,
        "total": len(results),
        "passed": passed,
        "failed": len(failed),
        "results": results,
        "failures": failed,
    }


def main(argv: Optional[list[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="Verify TMDB and ESPN subjects in verified_discover_art.json")
    parser.add_argument("--scope", choices=("new", "old", "all"), default="new")
    parser.add_argument("--base-ref", default="origin/master")
    parser.add_argument("--workers", type=int, default=8)
    parser.add_argument("--infer-missing-source-page", action="store_true")
    parser.add_argument("--json-out", type=Path, default=None)
    args = parser.parse_args(argv)

    data = json.loads(ART_JSON_PATH.read_text(encoding="utf-8"))
    summary = verify_records(
        list(data.get("entries") or ()),
        scope=args.scope,
        base_ref=args.base_ref,
        max_workers=args.workers,
        infer_source=args.infer_missing_source_page,
    )
    if args.json_out is not None:
        args.json_out.parent.mkdir(parents=True, exist_ok=True)
        args.json_out.write_text(json.dumps(summary, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")

    print(
        f"[{summary['scope']}] total={summary['total']} passed={summary['passed']} failed={summary['failed']}"
    )
    for row in summary["failures"]:
        print(f"  FAIL {row['entity_key']} ({row['provider']}): {row['error']}")
    return 0 if summary["failed"] == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
