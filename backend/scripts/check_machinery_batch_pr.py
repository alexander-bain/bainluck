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
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Mapping, Optional, Sequence

_BACKEND_DIR = Path(__file__).resolve().parents[1]
_REPO_ROOT = _BACKEND_DIR.parent
if str(_BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(_BACKEND_DIR))

from app.utils.agent_origin import tagged  # noqa: E402
from app.utils.container_machinery import (  # noqa: E402
    _load_snapshot_from_db,
    discover_machinery_candidate_paths,
    load_machinery_definition,
)
from app.utils.discover_fun_tags import load_fun_markets_registry  # noqa: E402
from app.utils.machinery_batch_gate import (  # noqa: E402
    PublicAssemblyResult,
    _definition_min_items,
    _load_curated_entries_by_sub_tag,
    audit_picture_policy_for_definition,
    audit_public_assembly_for_definition,
    check_machinery_form_rules,
    check_machinery_wording,
)


def discover_changed_machinery_slugs(
    base_ref: str = "origin/master",
    repo_root: Optional[Path] = None,
) -> tuple[str, ...]:
    """Return machinery definition slugs touched by a branch or working tree."""
    root = repo_root or _REPO_ROOT
    all_paths = discover_machinery_candidate_paths()
    by_slug = {p.stem: p for p in all_paths}

    changed_files: set[str] = set()
    for cmd in (
        ["git", "-C", str(root), "diff", "--name-only", f"{base_ref}...HEAD"],
        ["git", "-C", str(root), "diff", "--name-only"],
        ["git", "-C", str(root), "diff", "--name-only", "--cached"],
        ["git", "-C", str(root), "ls-files", "--others", "--exclude-standard"],
    ):
        proc = subprocess.run(cmd, capture_output=True, text=True, check=False)
        if proc.returncode == 0:
            changed_files.update(line.strip() for line in proc.stdout.splitlines() if line.strip())

    slugs: list[str] = []
    seen: set[str] = set()
    curated_tags_touched: set[str] = set()

    for rel in sorted(changed_files):
        p = Path(rel)
        if (
            "backend/data/groupings/candidates" in rel
            and p.name.startswith("machinery-")
            and p.suffix == ".json"
        ):
            stem = p.stem
            if stem in by_slug and stem not in seen:
                seen.add(stem)
                slugs.append(stem)
        elif rel.startswith("backend/data/groupings/batch") and rel.endswith("_curated_sets.json"):
            cur_path = root / rel
            if cur_path.exists():
                doc = json.loads(cur_path.read_text(encoding="utf-8"))
                curated_tags_touched.update(
                    str(k).strip().lower() for k in (doc.get("sets") or {})
                )

    if curated_tags_touched:
        for stem, path in sorted(by_slug.items()):
            if stem in seen:
                continue
            defn = load_machinery_definition(path)
            for sec in defn.get("rule", {}).get("sections") or ():
                sub_tag = str((sec.get("atom_query") or {}).get("fun_sub_tag") or "").strip().lower()
                if sub_tag and sub_tag in curated_tags_touched:
                    seen.add(stem)
                    slugs.append(stem)
                    break

    return tuple(slugs)


def _sample_outcomes_for_query(
    aq: Mapping[str, Any],
    base_id: int,
    now_iso: str,
    *,
    prob: float,
    with_opening_delta: float = 0.0,
) -> list[dict[str, Any]]:
    shape = str(aq.get("shape") or "any").strip().lower()
    open_p = max(0.02, min(0.98, round(prob - with_opening_delta, 4)))
    if shape == "binary":
        return [
            {
                "id": base_id * 10 + 1,
                "name": "Yes",
                "probability": prob,
                "opening_probability": open_p,
                "last_updated": now_iso,
            },
            {
                "id": base_id * 10 + 2,
                "name": "No",
                "probability": round(1.0 - prob, 4),
                "opening_probability": round(1.0 - open_p, 4),
                "last_updated": now_iso,
            },
        ]
    if shape == "two_way":
        return [
            {
                "id": base_id * 10 + 1,
                "name": "Democratic Party",
                "probability": prob,
                "opening_probability": open_p,
                "last_updated": now_iso,
            },
            {
                "id": base_id * 10 + 2,
                "name": "Republican Party",
                "probability": round(1.0 - prob, 4),
                "opening_probability": round(1.0 - open_p, 4),
                "last_updated": now_iso,
            },
        ]
    return [
        {
            "id": base_id * 10 + 1,
            "name": "Example Leader",
            "probability": prob,
            "opening_probability": open_p,
            "last_updated": now_iso,
        },
        {
            "id": base_id * 10 + 2,
            "name": "Runner Up",
            "probability": round(max(0.02, min(prob * 0.65, 1.0 - prob - 0.03)), 4),
            "opening_probability": round(max(0.02, min(open_p * 0.65, 1.0 - open_p - 0.03)), 4),
            "last_updated": now_iso,
        },
        {
            "id": base_id * 10 + 3,
            "name": "Third Option",
            "probability": round(max(0.01, min(prob * 0.30, 0.05)), 4),
            "opening_probability": round(max(0.01, min(open_p * 0.30, 0.05)), 4),
            "last_updated": now_iso,
        },
    ]


def build_synthetic_snapshot_for_definition(
    definition: Mapping[str, Any],
    *,
    now: Optional[datetime] = None,
) -> dict[str, Any]:
    """Build an in-memory snapshot satisfying a definition's structural queries for CI."""
    from app.services.paired_metric_register import load_paired_metric_register
    from app.utils.draw_priced_winner import printable_away
    from app.utils.graded_card import rendered_duel_percents

    cur_now = now or datetime.now(timezone.utc)
    now_iso = cur_now.isoformat()
    res_future = (cur_now + timedelta(days=240)).isoformat()
    hist_old_iso = (cur_now - timedelta(hours=120)).isoformat()
    rule = definition.get("rule") if isinstance(definition.get("rule"), Mapping) else {}
    curated_by_tag = _load_curated_entries_by_sub_tag()
    fun_reg = load_fun_markets_registry()
    paired_reg = load_paired_metric_register()

    events: list[dict[str, Any]] = []
    seen_eids: set[int] = set()
    markets: list[dict[str, Any]] = []
    paired_sets: dict[str, Any] = dict(paired_reg.get("sets") or {})
    market_histories: dict[int, list[dict[str, Any]]] = {}
    seen_mids: set[int] = set()
    category = str(definition.get("category") or "other")

    for sidx, sec in enumerate(rule.get("sections") or ()):
        if not isinstance(sec, Mapping):
            continue
        aq = sec.get("atom_query") if isinstance(sec.get("atom_query"), Mapping) else {}
        kind = str(aq.get("kind") or "markets")

        if kind == "events":
            sport_key = str(
                aq.get("sport_key")
                or ((aq.get("sport_keys") or ["basketball_nba"])[0])
            )
            sport_name = "NFL" if "nfl" in sport_key else ("NBA" if "nba" in sport_key else sport_key)
            needed = max(int(aq.get("min_items") or 3), 4)
            teams = [
                ("Lakers", "Celtics"),
                ("Knicks", "Heat"),
                ("Nuggets", "Suns"),
                ("Warriors", "Mavericks"),
                ("Bucks", "76ers"),
                ("Chiefs", "Bills"),
            ]
            band = aq.get("probability_band")
            for eidx in range(needed):
                away, home = teams[eidx % len(teams)]
                hp = round(0.51 + eidx * 0.02, 4) if (isinstance(band, Sequence) and len(band) == 2) else round(0.52 + eidx * 0.05, 4)
                ap = round(1.0 - hp, 4)
                c_ap = printable_away(ap, hp, sport_key)
                a_pct, h_pct = rendered_duel_percents(c_ap, hp)
                eid = 910000 + sidx * 100 + eidx
                if eid in seen_eids:
                    continue
                seen_eids.add(eid)
                events.append(
                    {
                        "id": eid,
                        "sport": sport_key,
                        "sport_name": sport_name,
                        "away_team": away,
                        "home_team": home,
                        "commence_time": (cur_now + timedelta(hours=3 + eidx * 4)).isoformat(),
                        "status": "scheduled",
                        "hero_probability": hp,
                        "hero_probability_away": ap,
                        "current_odds": {
                            "away_probability": ap,
                            "home_probability": hp,
                            "away_rendered_percent": int(a_pct),
                            "home_rendered_percent": int(h_pct),
                        },
                    }
                )
            continue

        if kind == "paired_stage":
            continue

        sub_tag = str(aq.get("fun_sub_tag") or "").strip().lower()
        row_specs: list[tuple[int, str]] = []
        if sub_tag and sub_tag in curated_by_tag:
            for e in curated_by_tag[sub_tag]:
                row_specs.append((int(e["id"]), str(e.get("short_label") or f"Market {e['id']}")))
        elif sub_tag:
            for mid in fun_reg.ordered_market_ids:
                meta = fun_reg.markets[mid]
                if any(st.lower() == sub_tag for st in meta.sub_tags):
                    row_specs.append((int(mid), meta.title))
        elif isinstance(aq.get("market_ids"), Sequence):
            for mid_raw in aq["market_ids"]:
                mid = int(mid_raw)
                row_specs.append((mid, f"Configured market {mid}"))
        else:
            all_tokens = [str(t) for t in (aq.get("title_all_tokens") or ())]
            any_tokens = [str(t) for t in (aq.get("any_tokens") or ())]
            count = max(int(aq.get("min_items") or 3), 3)
            base_tokens = " ".join(all_tokens)
            cities = ["Pittsburgh", "Milwaukee", "Minneapolis", "Chicago", "Boston", "Denver"]
            couples = ["Alex & Jordan", "Sam and Taylor", "Riley & Casey", "Morgan and Jamie"]
            if "engaged" in [t.lower() for t in all_tokens]:
                for i in range(max(count, 4)):
                    mid = 930000 + sidx * 100 + i
                    row_specs.append((mid, f"{couples[i % len(couples)]} engaged"))
            elif any_tokens:
                for i in range(max(count, min(len(any_tokens), int(aq.get("max_items") or count)))):
                    tok = any_tokens[i % len(any_tokens)].strip()
                    missing_tokens = [t for t in all_tokens if t.lower() not in tok.lower()]
                    title = " ".join([tok, *missing_tokens]).strip()
                    mid = 930000 + sidx * 100 + i
                    row_specs.append((mid, title))
            else:
                for i in range(count):
                    mid = 930000 + sidx * 100 + i
                    suffix = cities[i % len(cities)]
                    title = f"{base_tokens or sec.get('title') or 'Item'} {suffix}".strip()
                    row_specs.append((mid, title))

        prob_band = aq.get("prob_band")
        is_single_duel = (
            int(aq.get("max_items") or 0) == 1 and int(aq.get("max_outcomes") or 0) == 2
        )
        high_prob = (
            0.22
            if isinstance(prob_band, Sequence) and len(prob_band) == 2
            else (0.58 if is_single_duel else 0.78)
        )
        low_prob = 0.08 if isinstance(prob_band, Sequence) and len(prob_band) == 2 else 0.32
        max_lead = aq.get("max_lead_probability")
        if isinstance(max_lead, (int, float)) and not isinstance(max_lead, bool):
            high_prob = min(high_prob, max(0.06, float(max_lead) - 0.02))
            low_prob = min(low_prob, max(0.03, high_prob - 0.06))
        req_vol = aq.get("min_lifetime_volume")
        if req_vol is None:
            req_vol = aq.get("min_volume")
        span = max(1, len(row_specs) - 1)
        is_history = kind == "market_history"
        content_kind = str(aq.get("content_kind") or "futures")
        for idx, (mid, title) in enumerate(row_specs):
            if mid in seen_mids:
                continue
            seen_mids.add(mid)
            prob = round(high_prob - (high_prob - low_prob) * (idx / span), 4)
            outs = _sample_outcomes_for_query(
                aq,
                mid,
                now_iso,
                prob=prob,
                with_opening_delta=0.14 if is_history else 0.0,
            )
            markets.append(
                {
                    "id": mid,
                    "name": title,
                    "title": title,
                    "status": "open",
                    "source": "kalshi",
                    "content_kind": content_kind,
                    "category": category,
                    "llm_sport_category": category,
                    "market_tier": 1,
                    "volume": float(max(50000.0, (req_vol or 1000) * 5)),
                    "resolution_date": res_future,
                    "newest_outcome_updated_at": now_iso,
                    "top_outcomes": outs,
                    "outcomes": outs,
                }
            )
            if is_history:
                lead_oid = int(outs[0]["id"])
                market_histories[lead_oid] = [
                    {"outcome_id": lead_oid, "probability": max(0.05, prob - 0.14), "captured_at": hist_old_iso},
                    {"outcome_id": lead_oid, "probability": prob, "captured_at": now_iso},
                ]

    return {
        "events": events,
        "markets": markets,
        "paired_sets": paired_sets,
        "market_histories": market_histories,
    }


def _fetch_json(url: str, *, timeout: float = 20.0) -> tuple[int, Optional[dict[str, Any]]]:
    req = urllib.request.Request(url, headers=tagged(url, {"Accept": "application/json"}))
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


async def _run_live_db_audit(
    definitions: Mapping[str, Mapping[str, Any]],
    db_url: str,
    now: datetime,
    *,
    require_preview_pass: bool,
) -> list[PublicAssemblyResult]:
    from sqlalchemy import text
    from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

    norm_url = db_url
    if norm_url.startswith("postgres://"):
        norm_url = "postgresql+asyncpg://" + norm_url[len("postgres://") :]
    elif norm_url.startswith("postgresql://") and "+asyncpg" not in norm_url:
        norm_url = "postgresql+asyncpg://" + norm_url[len("postgresql://") :]

    engine = create_async_engine(norm_url, isolation_level="AUTOCOMMIT", pool_pre_ping=True)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    results: list[PublicAssemblyResult] = []
    try:
        async with factory() as session:
            await session.execute(text("SET default_transaction_read_only = on"))
            await session.execute(text("SET statement_timeout = '8000ms'"))
            skip_session = _ReadOnlyHistorySkipSession(session)
            for _slug, defn in definitions.items():
                has_hist = any(
                    ((sec.get("atom_query") or {}).get("kind") == "market_history")
                    for sec in ((defn.get("rule") or {}).get("sections") or ())
                    if isinstance(sec, Mapping)
                )
                if has_hist:
                    await session.execute(text("SET statement_timeout = '25000ms'"))
                snapshot = await _load_snapshot_from_db(
                    session if has_hist else skip_session,
                    defn,
                    now,
                )
                if has_hist:
                    await session.execute(text("SET statement_timeout = '8000ms'"))
                results.append(
                    await audit_public_assembly_for_definition(
                        defn,
                        snapshot,
                        now=now,
                        require_preview_pass=require_preview_pass,
                        check_tile_pictures=True,
                    )
                )
    finally:
        await engine.dispose()
    return results


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
            feed_item=feed_item,
            slug=slug,
        )
        pic_res = audit_picture_policy_for_definition(defn, card=card)
        form_res = check_machinery_form_rules(
            card=card,
            container=container,
            slug=slug,
            check_tile_pictures=True,
        )
        member_count = int(container.get("member_count") or 0)
        ok = wording_res.ok and pic_res.ok and form_res.ok and member_count >= max(1, min_items)
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
                form_rules=form_res,
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
    if live_db_url:
        return await _run_live_db_audit(
            definitions,
            live_db_url,
            now,
            require_preview_pass=require_preview_pass,
        )

    results: list[PublicAssemblyResult] = []
    for _slug, defn in definitions.items():
        snapshot = build_synthetic_snapshot_for_definition(defn, now=now)
        results.append(
            await audit_public_assembly_for_definition(
                defn,
                snapshot,
                now=now,
                require_preview_pass=require_preview_pass,
                check_tile_pictures=False,
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
        if r.form_rules:
            for err in r.form_rules.errors:
                print(f"  FORM_ERR [{err.rule}] @ {err.location}: {err.detail} ({err.text!r})")
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
