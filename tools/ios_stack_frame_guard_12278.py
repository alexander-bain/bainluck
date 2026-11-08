#!/usr/bin/env python3
"""
#12278 — Release arm64 stack-frame prologue guard for EventDetailView.o.

Reads each function's prologue `sub sp, sp, #...` allocations from the compiled
Release arm64 `EventDetailView.o` via `xcrun objdump -d` and exits non-zero if
any function in `EventDetailView.o` allocates more than 64 KB (65,536 bytes) on
the stack in its prologue.

Before #12278 (build 5670, commit d8f7c15e59):
  - EventDetailView.body.getter:        176,192 B (0x2b040)  > 65,536 B  [FAIL]
  - EventDetailView.contentView.getter: 338,912 B (0x52be0)  > 65,536 B  [FAIL]
  - EventDetailView.heroSection(_:):    246,720 B (0x3c3c0)  > 65,536 B  [FAIL]
  Combined main-thread stack along body -> contentView -> heroSection: 761,824 B,
  plus SwiftUI NavigationStack + generic metadata instantiation (~260+ KB) > 1 MB
  iOS main-thread stack limit -> EXC_BAD_ACCESS (SIGSEGV) in Stack Guard.

Usage:
  python3 tools/ios_stack_frame_guard_12278.py <path-to-EventDetailView.o-or-DerivedData>
  python3 tools/ios_stack_frame_guard_12278.py --self-check
"""

from __future__ import annotations

import argparse
import re
import subprocess
import sys
from pathlib import Path

MAX_PROLOGUE_BYTES = 65_536  # 64 KB hard ceiling per function in EventDetailView.o

FUNC_HEADER_RE = re.compile(r"^[0-9a-fA-F]{8,16}\s+<([^>]+)>:")
SUB_SP_HEX_RE = re.compile(r"\bsub\s+sp,\s*sp,\s*#0x([0-9a-fA-F]+)(?:,\s*lsl\s*#(\d+))?")
SUB_SP_DEC_RE = re.compile(r"\bsub\s+sp,\s*sp,\s*#(\d+)(?:,\s*lsl\s*#(\d+))?")


def parse_objdump_prologues(disassembly: str) -> list[tuple[int, str]]:
    """Return (prologue_sub_sp_bytes, symbol_name) for every function in objdump -d output."""
    results: list[tuple[int, str]] = []
    cur_symbol: str | None = None
    cur_bytes = 0
    in_prologue = False

    for line in disassembly.splitlines():
        m_hdr = FUNC_HEADER_RE.match(line)
        if m_hdr:
            if cur_symbol is not None:
                results.append((cur_bytes, cur_symbol))
            cur_symbol = m_hdr.group(1)
            cur_bytes = 0
            in_prologue = True
            continue

        if not in_prologue:
            continue

        if "\tsub\tsp, sp, #" in line or " sub sp, sp, #" in line:
            m_hex = SUB_SP_HEX_RE.search(line)
            if m_hex:
                val = int(m_hex.group(1), 16)
                shift = int(m_hex.group(2)) if m_hex.group(2) else 0
                cur_bytes += val << shift
                continue
            m_dec = SUB_SP_DEC_RE.search(line)
            if m_dec:
                val = int(m_dec.group(1), 10)
                shift = int(m_dec.group(2)) if m_dec.group(2) else 0
                cur_bytes += val << shift
                continue
        elif "\tbl\t" in line or "\tb\t" in line or "\tret" in line:
            in_prologue = False

    if cur_symbol is not None:
        results.append((cur_bytes, cur_symbol))

    return results


def resolve_object_file(target: Path) -> Path:
    if target.is_file():
        return target
    if not target.is_dir():
        raise FileNotFoundError(f"Path not found: {target}")

    candidates = [
        p
        for p in target.rglob("EventDetailView.o")
        if "Objects-normal/arm64/" in p.as_posix() and "Release" in p.as_posix()
    ]
    if not candidates:
        candidates = [
            p for p in target.rglob("EventDetailView.o") if "Objects-normal/arm64/" in p.as_posix()
        ]
    if not candidates:
        raise FileNotFoundError(f"No arm64 EventDetailView.o found under {target}")

    candidates.sort(key=lambda p: p.stat().st_mtime, reverse=True)
    return candidates[0]


def demangle(symbol: str) -> str:
    try:
        return subprocess.check_output(
            ["xcrun", "swift-demangle", "--compact", symbol],
            text=True,
            stderr=subprocess.DEVNULL,
        ).strip()
    except Exception:
        return symbol


def find_named_symbol_bytes(functions: list[tuple[int, str]], needle: str) -> int | None:
    for size, sym in functions:
        if needle == "body.getter" and sym.endswith("15EventDetailViewV4bodyQrvg"):
            return size
        if needle == "contentView.getter" and "15EventDetailViewV07contentE0" in sym and sym.endswith("Vvg"):
            return size
        if needle == "heroSection" and "15EventDetailViewV11heroSection" in sym and (
            sym.endswith("VF") or sym.endswith("VAA0cD0VF")
        ):
            return size
    return None


def format_bytes(size: int) -> str:
    if size >= 4096 and (size & 0xFFF) != 0:
        page_part = size & ~0xFFF
        rem_part = size & 0xFFF
        return f"{size:,} B (0x{size:x}; lsl #12 page sub sp = {page_part:,} B + {rem_part:,} B)"
    return f"{size:,} B (0x{size:x})"


def evaluate_prologues(
    functions: list[tuple[int, str]],
    budget_bytes: int = MAX_PROLOGUE_BYTES,
    source_label: str = "EventDetailView.o",
) -> tuple[bool, str]:
    if not functions:
        return False, f"FAIL: no functions parsed from {source_label}"

    ranked = sorted(functions, key=lambda item: item[0], reverse=True)
    largest_bytes, largest_sym = ranked[0]
    over_budget = [(sz, sym) for sz, sym in ranked if sz > budget_bytes]

    body_bytes = find_named_symbol_bytes(functions, "body.getter")
    content_bytes = find_named_symbol_bytes(functions, "contentView.getter")
    hero_bytes = find_named_symbol_bytes(functions, "heroSection")

    lines = [
        f"EventDetailView stack frame guard (#12278) — source: {source_label}",
        f"  budget per function : {budget_bytes:,} B ({budget_bytes // 1024} KB)",
        f"  functions scanned   : {len(functions)}",
        f"  body.getter         : {format_bytes(body_bytes) if body_bytes is not None else 'n/a'}",
        f"  contentView.getter  : {format_bytes(content_bytes) if content_bytes is not None else 'n/a'}",
        f"  heroSection(_:)     : {format_bytes(hero_bytes) if hero_bytes is not None else 'n/a'}",
        f"  largest function    : {format_bytes(largest_bytes)} ({demangle(largest_sym)})",
    ]

    if over_budget:
        lines.append(f"RESULT: FAIL ({len(over_budget)} function(s) exceed {budget_bytes:,} B):")
        for sz, sym in over_budget[:10]:
            lines.append(f"  OVER: {format_bytes(sz)} > {budget_bytes:,} B — {demangle(sym)} [{sym}]")
        return False, "\n".join(lines)

    lines.append(
        f"RESULT: PASS (largest prologue sub sp = {format_bytes(largest_bytes)} <= {budget_bytes:,} B)"
    )
    return True, "\n".join(lines)


# Synthetic disassembly fixtures for offline parser self-check (--self-check on Linux CI).
# Real object-file verification runs against the compiled Release arm64 EventDetailView.o
# in tools/watch-companion-archive.sh and tools/native-release-check.sh.
SYNTHETIC_PRE_FIX_D8F7C15E59_FIXTURE = """\
0000000000000000 <_$s9Bain_Luck15EventDetailViewV4bodyQrvg>:
       0: d140acff     \tsub\tsp, sp, #0x2b, lsl #12
       4: d10103ff     \tsub\tsp, sp, #0x40
       8: 94000000     \tbl\t0x0
0000000000001000 <_$s9Bain_Luck15EventDetailViewV07contentE033_C07271C5E1D705FF0167165B1ACA4D2ELL7SwiftUI03AnyE0Vvg>:
    1000: d1414bff     \tsub\tsp, sp, #0x52, lsl #12
    1004: d12f83ff     \tsub\tsp, sp, #0xbe0
    1008: 94000000     \tbl\t0x1000
0000000000002000 <_$s9Bain_Luck15EventDetailViewV11heroSection33_C07271C5E1D705FF0167165B1ACA4D2ELLyQrAA0cD0VF>:
    2000: d140f3ff     \tsub\tsp, sp, #0x3c, lsl #12
    2004: d10f03ff     \tsub\tsp, sp, #0x3c0
    2008: 94000000     \tbl\t0x2000
"""

SYNTHETIC_POST_FIX_12278_FIXTURE = """\
0000000000000000 <_$s9Bain_Luck15EventDetailViewV4bodyQrvg>:
       0: d101c3ff     \tsub\tsp, sp, #0x70
       4: 94000000     \tbl\t0x0
0000000000001000 <_$s9Bain_Luck15EventDetailViewV07contentE033_C07271C5E1D705FF0167165B1ACA4D2ELL7SwiftUI03AnyE0Vvg>:
    1000: d1400bff     \tsub\tsp, sp, #0x3, lsl #12
    1004: 94000000     \tbl\t0x1000
0000000000002000 <_$s9Bain_Luck15EventDetailViewV11heroSection33_C07271C5E1D705FF0167165B1ACA4D2ELLyQrAA0cD0VF>:
    2000: d10283ff     \tsub\tsp, sp, #0xa0
    2004: 94000000     \tbl\t0x2000
"""


def run_self_check() -> int:
    pre_funcs = parse_objdump_prologues(SYNTHETIC_PRE_FIX_D8F7C15E59_FIXTURE)
    ok_pre, report_pre = evaluate_prologues(
        pre_funcs,
        budget_bytes=MAX_PROLOGUE_BYTES,
        source_label="synthetic pre-fix parser fixture (d8f7c15e59 prologue instruction values)",
    )
    if ok_pre or "338,912 B" not in report_pre:
        print("SELF-CHECK FAIL: expected synthetic pre-fix fixture to fail with 338,912 B", file=sys.stderr)
        print(report_pre, file=sys.stderr)
        return 1

    post_funcs = parse_objdump_prologues(SYNTHETIC_POST_FIX_12278_FIXTURE)
    ok_post, report_post = evaluate_prologues(
        post_funcs,
        budget_bytes=MAX_PROLOGUE_BYTES,
        source_label="synthetic post-fix parser fixture (#12278 prologue instruction values)",
    )
    if not ok_post or "12,288 B" not in report_post:
        print("SELF-CHECK FAIL: expected synthetic post-fix fixture to pass with 12,288 B", file=sys.stderr)
        print(report_post, file=sys.stderr)
        return 1

    print("=== Synthetic pre-fix parser fixture (expected FAIL) ===")
    print(report_pre)
    print()
    print("=== Synthetic post-fix parser fixture (expected PASS) ===")
    print(report_post)
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="Check Release arm64 EventDetailView.o prologue stack sizes.")
    parser.add_argument("target", nargs="?", help="Path to EventDetailView.o or DerivedData directory")
    parser.add_argument("--budget-bytes", type=int, default=MAX_PROLOGUE_BYTES)
    parser.add_argument("--self-check", action="store_true", help="Run built-in pre/post fixture verification")
    args = parser.parse_args()

    if args.self_check:
        return run_self_check()

    if not args.target:
        parser.error("Provide a path to EventDetailView.o / DerivedData, or pass --self-check")

    obj_path = resolve_object_file(Path(args.target))
    disasm = subprocess.check_output(["xcrun", "objdump", "-d", str(obj_path)], text=True)
    functions = parse_objdump_prologues(disasm)
    ok, report = evaluate_prologues(functions, budget_bytes=args.budget_bytes, source_label=str(obj_path))
    print(report)
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
