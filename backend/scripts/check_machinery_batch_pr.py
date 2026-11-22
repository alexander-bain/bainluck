#!/usr/bin/env python3
"""One-command batch PR gate for Discover container machinery (#12288 Item 6).

Runs up to all four batch checks in a single command:
  (a) public-rule assembly (--live-db, --live-api, or deterministic synthetic CI snapshot),
      failing non-zero if any `"stage": "public"` set comes up short;
  (b) wording lint (doubled label/answer word, repeated name in row, banned words,
      > 5-line headline at 390 px);
  (c) picture policy & verified register check;
  (d) optional 390 px light+dark sheet generation via `tools/set-card-sheet.mjs`.

Usage:
  python3 scripts/check_machinery_batch_pr.py --changed-since origin/master
  python3 scripts/check_machinery_batch_pr.py --slugs machinery-long-shots --live-api https://api.bainluck.com
  python3 scripts/check_machinery_batch_pr.py --all --live-db --sheet-out /tmp/batch-sheet.png
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import subprocess
import sys
import tempfile
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping, Optional

_BACKEND_DIR = Path(__file__).resolve().parents[1]
_REPO_ROOT = _BACKEND_DIR.parent
if str(_BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(_BACKEND_DIR))

from app.utils.container_machinery import (  # noqa: E402
    _load_snapshot_from_db,
    discover_machinery_candidate_paths,
    load_machinery_definition,
)
from app.utils.machinery_batch_gate import (  # noqa: E402
    PublicAssemblyResult,
    _definition_min_items,
    audit_picture_policy_for_definition,
    audit_public_assembly_for_definition,
    build_synthetic_snapshot_for_definition,
    check_machinery_wording,
    discover_changed_machinery_slugs,
)


def _fetch_json(url: str, *, timeout: float = 20.0) -> tuple[int, Optional[dict[str, Any]]]:
    req = urllib.request.Request(url, headers={"Accept": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return int(resp.status), json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        try:
            body = json.loads(exc.read().decode("utf-8"))
        except Exception:
            body = None
        return int(exc.code), body


def _load_definitions_for_args(args: argparse.Namespace) -> dict[str, dict[str, Any]]:
    by_slug = {p.stem: p for p in discover_machinery_candidate_paths()}
    if args.slugs:
        missing = [s for s in args.slugs if s not in by_slug]
        if missing:
            raise SystemExit(f"Unknown machinery slug(s): {', '.join(missing)}")
        selected_slugs = list(dict.fromkeys(args.slugs))
    elif args.all:
        selected_slugs = sorted(by_slug.keys())
    else:
        selected_slugs = list(discover_changed_machinery_slugs(args.changed_since, _REPO_ROOT))

    definitions: dict[str, dict[str, Any]] = {}
    for slug in selected_slugs:
        defn = load_machinery_definition(by_slug[slug])
        if args.public_only and str(defn.get("stage") or "public") != "public":
            continue
        definitions[slug] = defn
    return definitions


class _ReadOnlyHistorySkipSession:
    """Thin read-only session wrapper skipping heavy 7d history scans inside `_load_snapshot_from_db`."""

    def __init__(self, inner: Any) -> None:
        self._inner = inner

    async def execute(self, stmt: Any, *args: Any, **kwargs: Any) -> Any:
        sql_txt = str(stmt)
        if "futures_odds_snapshots" in sql_txt.lower():

            class _EmptyResult:
                def all(self) -> list[Any]:
                    return []

                def scalars(self) -> "_EmptyResult":
                    return self

                def __iter__(self) -> Any:
                    return iter(())

            return _EmptyResult()
        return await self._inner.execute(stmt, *args, **kwargs)


async def _load_live_db_snapshot(db_url: str, now: datetime) -> dict[str, Any]:
    from sqlalchemy import text
    from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

    norm_url = db_url
    if norm_url.startswith("postgres://"):
        norm_url = "postgresql+asyncpg://" + norm_url[len("postgres://") :]
    elif norm_url.startswith("postgresql://") and "+asyncpg" not in norm_url:
        norm_url = "postgresql+asyncpg://" + norm_url[len("postgresql://") :]

    engine = create_async_engine(norm_url, isolation_level="AUTOCOMMIT", pool_pre_ping=True)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    try:
        async with factory() as session:
            await session.execute(text("SET default_transaction_read_only = on"))
            await session.execute(text("SET statement_timeout = '6000ms'"))
            return await _load_snapshot_from_db(_ReadOnlyHistorySkipSession(session), now=now)
    finally:
        await engine.dispose()


def _audit_live_api(
    definitions: Mapping[str, Mapping[str, Any]],
    base_url: str,
    *,
    require_preview_pass: bool = False,
) -> list[PublicAssemblyResult]:
    base = base_url.rstrip("/")
    feed_status, feed_doc = _fetch_json(f"{base}/api/feed?limit=150&offset=0&machinery=1")
    feed_by_slug: dict[str, tuple[int, dict[str, Any]]] = {}
    if feed_status == 200 and isinstance(feed_doc, Mapping):
        for idx, item in enumerate(feed_doc.get("items") or (), 1):
            ru = (item.get("data") or {}).get("roundup") or {}
            mc = ru.get("machinery_card")
            if isinstance(mc, Mapping) and mc.get("slug"):
                feed_by_slug[str(mc["slug"])] = (idx, dict(item))

    results: list[PublicAssemblyResult] = []
    for slug, defn in definitions.items():
        stage = str(defn.get("stage") or "public")
        min_items = _definition_min_items(defn)
        status_code, container = _fetch_json(f"{base}/api/containers/{slug}")
        pic_res = audit_picture_policy_for_definition(defn)
        if status_code != 200 or not isinstance(container, Mapping) or not container.get("assembled"):
            reason = (
                f"http_{status_code}"
                if status_code != 200
                else str((container or {}).get("reason") or "not_assembled")
            )
            wording_def = check_machinery_wording(definition=defn, slug=slug)
            fail = stage == "public" or require_preview_pass or not wording_def.ok or not pic_res.ok
            results.append(
                PublicAssemblyResult(
                    slug=slug,
                    stage=stage,
                    ok=not fail,
                    status=(
                        "FAIL_PUBLIC_SHORTFALL"
                        if (stage == "public" or require_preview_pass)
                        else "PREVIEW_SHORTFALL"
                    ),
                    min_items=min_items,
                    member_count=int((container or {}).get("member_count") or 0),
                    refusal_reasons=(reason,),
                    wording=wording_def,
                    picture=pic_res,
                )
            )
            continue

        seat_item = feed_by_slug.get(slug)
        feed_item = seat_item[1] if seat_item else None
        card = (
            ((feed_item.get("data") or {}).get("roundup") or {}).get("machinery_card")
            if feed_item
            else None
        )
        wording_res = check_machinery_wording(
            card=card,
            container=container,
            definition=defn,
            slug=slug,
        )
        pic_res = audit_picture_policy_for_definition(defn, card=card)
        member_count = int(container.get("member_count") or 0)
        ok = wording_res.ok and pic_res.ok and member_count >= max(1, min_items)
        results.append(
            PublicAssemblyResult(
                slug=slug,
                stage=stage,
                ok=ok,
                status=(
                    "PASS"
                    if ok
                    else (
                        "FAIL_PUBLIC_SHORTFALL"
                        if member_count < min_items and stage == "public"
                        else "FAIL_GATE"
                    )
                ),
                min_items=min_items,
                member_count=member_count,
                wording=wording_res,
                picture=pic_res,
                card=dict(card) if isinstance(card, Mapping) else None,
                container=dict(container),
                feed_item=feed_item,
            )
        )
    return results


async def _run_snapshot_audit(
    definitions: Mapping[str, Mapping[str, Any]],
    *,
    live_db_url: Optional[str],
    require_preview_pass: bool,
) -> list[PublicAssemblyResult]:
    now = datetime.now(timezone.utc)
    shared_snapshot: Optional[dict[str, Any]] = None
    if live_db_url:
        shared_snapshot = await _load_live_db_snapshot(live_db_url, now)

    results: list[PublicAssemblyResult] = []
    for slug, defn in definitions.items():
        snapshot = (
            shared_snapshot
            if shared_snapshot is not None
            else build_synthetic_snapshot_for_definition(defn, now=now)
        )
        results.append(
            await audit_public_assembly_for_definition(
                defn,
                snapshot,
                now=now,
                require_preview_pass=require_preview_pass,
            )
        )
    return results


def _build_sheet(results: list[PublicAssemblyResult], sheet_out: Path) -> None:
    items = [r.feed_item for r in results if isinstance(r.feed_item, dict)]
    slugs = [r.slug for r in results if isinstance(r.feed_item, dict)]
    if not items:
        raise RuntimeError("No assembled feed items available to render 390 px sheet")
    sheet_out.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False, encoding="utf-8") as tmp:
        json.dump({"items": items, "has_more": False, "total_count": len(items)}, tmp)
        tmp_path = Path(tmp.name)
    try:
        cmd = [
            "node",
            str(_REPO_ROOT / "tools" / "set-card-sheet.mjs"),
            "--out",
            str(sheet_out),
            "--feed-json",
            str(tmp_path),
            *slugs,
        ]
        subprocess.run(cmd, cwd=str(_REPO_ROOT), check=True)
    finally:
        tmp_path.unlink(missing_ok=True)


def _print_summary(results: list[PublicAssemblyResult]) -> None:
    if not results:
        print("No machinery definitions matched selection; nothing to check.")
        return
    for r in results:
        lines_str = f"{r.wording.estimated_lines_390px}L" if r.wording else "-"
        print(
            f"[{r.status}] {r.slug} (stage={r.stage}, members={r.member_count}/min={r.min_items}, "
            f"headline={lines_str})"
        )
        if r.surviving_titles:
            print(f"  surviving ({len(r.surviving_titles)}): {', '.join(r.surviving_titles)}")
        if r.refused_members:
            ref_txt = "; ".join(
                f"{m['market_id']}({m['reason']})" for m in r.refused_members
            )
            print(f"  refused ({len(r.refused_members)}): {ref_txt}")
        if r.refusal_reasons:
            print(f"  refusal_reasons: {', '.join(str(x) for x in r.refusal_reasons)}")
        if r.wording:
            for err in r.wording.errors:
                print(f"  WORDING_ERR [{err.rule}] @ {err.location}: {err.detail} ({err.text!r})")
        if r.picture:
            for err in r.picture.errors:
                print(f"  PICTURE_ERR [{err.rule}] @ {err.location}: {err.detail}")
        if r.parity_mismatches:
            print(f"  PARITY_ERR ({len(r.parity_mismatches)}): {r.parity_mismatches[0]}")


def main(argv: Optional[list[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="Machinery batch PR gate (#12288 Item 6)")
    parser.add_argument("--changed-since", default="origin/master", help="Git base ref for changed files")
    parser.add_argument("--slugs", nargs="*", help="Explicit machinery-<slug> names to check")
    parser.add_argument("--all", action="store_true", help="Check all candidate machinery definitions")
    parser.add_argument("--public-only", action="store_true", help="Restrict selection to stage='public'")
    parser.add_argument("--live-api", default=None, help="Verify live API URL instead of synthetic snapshot")
    parser.add_argument("--live-db", action="store_true", help="Run against read-only PostgreSQL DATABASE_URL")
    parser.add_argument("--db-url", default=None, help="Override PostgreSQL URL for --live-db")
    parser.add_argument(
        "--strict-preview",
        action="store_true",
        help="Fail even when a stage='preview' set comes up short of min_items",
    )
    parser.add_argument("--sheet-out", default=None, help="Optional output path for 390 px PNG sheet")
    parser.add_argument("--json-out", default=None, help="Optional JSON report path")
    args = parser.parse_args(argv)

    definitions = _load_definitions_for_args(args)
    if args.live_api:
        results = _audit_live_api(
            definitions, args.live_api, require_preview_pass=args.strict_preview
        )
    else:
        db_url = args.db_url or (os.environ.get("DATABASE_URL") if args.live_db else None)
        if args.live_db and not db_url:
            raise SystemExit("--live-db requires DATABASE_URL or --db-url")
        results = asyncio.run(
            _run_snapshot_audit(
                definitions,
                live_db_url=db_url,
                require_preview_pass=args.strict_preview,
            )
        )

    _print_summary(results)
    if args.sheet_out and results:
        _build_sheet(results, Path(args.sheet_out))
    if args.json_out:
        Path(args.json_out).write_text(
            json.dumps([r.to_dict() for r in results], indent=2),
            encoding="utf-8",
        )
    return 0 if all(r.ok for r in results) else 1


if __name__ == "__main__":
    raise SystemExit(main())
