#!/usr/bin/env python3
"""Manus intake: parse sweep reports into structured findings, dedup, file digest.

Usage:
    python3 scripts/manus_intake.py                    # Process latest sweep
    python3 scripts/manus_intake.py --date 2026-06-10  # Process specific date
    python3 scripts/manus_intake.py --dry-run           # Print digest, don't file
"""

import argparse
import hashlib
import json
import os
import re
import subprocess
import sys
from pathlib import Path

AUDIT_DIR = Path(__file__).resolve().parent.parent.parent / "Manus" / "audit_results"

# Severity keywords → P-level
_SEVERITY_PATTERNS = [
    (re.compile(r"\b(critical|crash|broken|500|error|outage)\b", re.I), "P0"),
    (re.compile(r"\b(missing|empty|wrong|incorrect|stale|fail)\b", re.I), "P1"),
    (re.compile(r"\b(inconsistent|unclear|confusing|slow|degraded)\b", re.I), "P2"),
]


def _detect_severity(text: str) -> str:
    for pattern, level in _SEVERITY_PATTERNS:
        if pattern.search(text):
            return level
    return "P3"


def _fingerprint(surface: str, description: str) -> str:
    """Deterministic fingerprint for dedup: hash of normalized surface + description."""
    # NOTE: keep the regex out of the f-string expression — backslashes inside
    # f-string expressions are a SyntaxError on Python < 3.12 (CI runs 3.11).
    desc = re.sub(r"\s+", " ", description.lower().strip())
    normalized = f"{surface.lower().strip()}|{desc}"
    return hashlib.sha256(normalized.encode()).hexdigest()[:16]


def _parse_report(report_path: Path) -> list[dict]:
    """Parse a markdown report into structured findings."""
    findings = []
    text = report_path.read_text()
    module = report_path.stem

    # Split on heading patterns that look like individual findings
    sections = re.split(r"\n(?=#{1,3}\s)", text)

    for section in sections:
        lines = section.strip().split("\n")
        if not lines:
            continue

        heading = lines[0].lstrip("#").strip()
        body = "\n".join(lines[1:]).strip()

        if len(body) < 20:
            continue

        # Skip Manus progress-log headings (not findings)
        _PROGRESS_RE = re.compile(
            r"^(Starting|Progress|I'll|I've|I am|Let me|Now |Continuing|Completed|"
            r"Summary|Overview|Methodology|Audit Plan|Next Steps)", re.I
        )
        if _PROGRESS_RE.match(heading):
            # Try to extract a real finding title from the body instead
            body_lines = body.split("\n")
            finding_line = next(
                (l.lstrip("- *").strip() for l in body_lines
                 if len(l.strip()) > 20 and _detect_severity(l) in ("P0", "P1")),
                None,
            )
            if finding_line:
                heading = finding_line[:120]
            else:
                continue

        # Extract URLs
        urls = re.findall(r"https?://[^\s\)]+", body)
        surface = urls[0] if urls else f"module:{module}"

        severity = _detect_severity(body)
        fp = _fingerprint(surface, heading)

        findings.append({
            "module": module,
            "heading": heading[:120],
            "surface": surface,
            "severity": severity,
            "fingerprint": fp,
            "evidence": body[:500],
        })

    return findings


def _load_previous_fingerprints(n_sweeps: int = 3) -> set[str]:
    """Load fingerprints from previous N sweep digests to dedup against."""
    fingerprints = set()

    # Check recent digest issues
    try:
        result = subprocess.run(
            ["gh", "issue", "list", "--repo", "alexander-bain/bainluck",
             "--label", "manus-digest", "--state", "all", "--limit", str(n_sweeps),
             "--json", "body"],
            capture_output=True, text=True, timeout=15,
        )
        if result.returncode == 0:
            issues = json.loads(result.stdout)
            for issue in issues:
                body = issue.get("body", "")
                fps = re.findall(r"fingerprint: `([a-f0-9]+)`", body)
                fingerprints.update(fps)
    except Exception:
        pass

    return fingerprints


def _load_open_issue_fingerprints() -> set[str]:
    """Check open issues for finding fingerprints."""
    fingerprints = set()
    try:
        result = subprocess.run(
            ["gh", "issue", "list", "--repo", "alexander-bain/bainluck",
             "--state", "open", "--limit", "100", "--json", "body"],
            capture_output=True, text=True, timeout=15,
        )
        if result.returncode == 0:
            issues = json.loads(result.stdout)
            for issue in issues:
                body = issue.get("body", "")
                fps = re.findall(r"fingerprint: `([a-f0-9]+)`", body)
                fingerprints.update(fps)
    except Exception:
        pass

    return fingerprints


def _build_digest(findings: list[dict], date: str, mode: str) -> str:
    """Build a markdown digest issue body from deduplicated findings."""
    body = f"## Manus Sweep Digest — {date} ({mode})\n\n"
    body += f"**{len(findings)} new findings** (deduplicated against previous 3 sweeps + open issues)\n\n"

    by_severity = {}
    for f in findings:
        by_severity.setdefault(f["severity"], []).append(f)

    for sev in ["P0", "P1", "P2", "P3"]:
        items = by_severity.get(sev, [])
        if not items:
            continue
        body += f"### {sev} ({len(items)})\n\n"
        for f in items:
            body += f"#### {f['heading']}\n"
            body += f"- Module: `{f['module']}` | Surface: {f['surface']}\n"
            body += f"- fingerprint: `{f['fingerprint']}`\n"
            body += f"- Evidence: {f['evidence'][:300]}\n\n"
            body += "<details><summary>Promote to issue</summary>\n\n"
            body += f"```\ngh issue create --title \"{f['heading'][:80]}\" "
            body += f"--label \"type:bug,priority:{sev.lower()},needs-agent\"\n```\n\n"
            body += "</details>\n\n"

    return body


def main():
    parser = argparse.ArgumentParser(description="Manus intake: parse + dedup + digest")
    parser.add_argument("--date", help="Process specific date (YYYY-MM-DD)")
    parser.add_argument("--dry-run", action="store_true", help="Print digest, don't file")
    args = parser.parse_args()

    if args.date:
        sweep_dir = AUDIT_DIR / args.date
    else:
        latest = AUDIT_DIR / "latest"
        if latest.is_symlink() or latest.is_dir():
            sweep_dir = latest.resolve()
        else:
            print("No latest sweep found")
            sys.exit(1)

    manifest_path = sweep_dir / "manifest.json"
    if not manifest_path.exists():
        print(f"No manifest at {manifest_path}")
        sys.exit(1)

    manifest = json.loads(manifest_path.read_text())
    date = manifest.get("date", sweep_dir.name)
    mode = manifest.get("mode", "unknown")

    # Parse all report files
    all_findings = []
    for report_file in sweep_dir.glob("*.md"):
        if report_file.name in ("combined_report.md", "manifest.json"):
            continue
        findings = _parse_report(report_file)
        all_findings.extend(findings)

    print(f"Parsed {len(all_findings)} raw findings from {date} ({mode})")

    # Dedup against previous sweeps and open issues
    known_fps = _load_previous_fingerprints()
    known_fps |= _load_open_issue_fingerprints()

    new_findings = [f for f in all_findings if f["fingerprint"] not in known_fps]
    print(f"After dedup: {len(new_findings)} new findings ({len(all_findings) - len(new_findings)} suppressed)")

    # Update manifest with new_findings_count
    manifest["new_findings_count"] = len(new_findings)
    manifest_path.write_text(json.dumps(manifest, indent=2))

    if not new_findings:
        print("No new findings — no digest to file")
        return

    digest = _build_digest(new_findings, date, mode)

    if args.dry_run:
        print("\n" + "=" * 60)
        print("DRY RUN — would file this digest:")
        print("=" * 60)
        print(digest)
        return

    # File the digest issue
    try:
        # Create manus-digest label if needed
        subprocess.run(
            ["gh", "label", "create", "manus-digest", "--repo", "alexander-bain/bainluck",
             "--description", "Automated Manus sweep digest", "--color", "d4c5f9"],
            capture_output=True, timeout=10,
        )
    except Exception:
        pass

    result = subprocess.run(
        ["gh", "issue", "create", "--repo", "alexander-bain/bainluck",
         "--title", f"Manus digest — {date} ({mode}): {len(new_findings)} findings",
         "--label", "alert-intake,type:ops,manus-digest",
         "--body", digest],
        capture_output=True, text=True, timeout=15,
    )
    if result.returncode == 0:
        print(f"Filed: {result.stdout.strip()}")
    else:
        print(f"Failed to file: {result.stderr[:200]}")


if __name__ == "__main__":
    main()
