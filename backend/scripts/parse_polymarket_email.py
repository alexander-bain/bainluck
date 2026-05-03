#!/usr/bin/env python3
"""Parse Polymarket marketing email HTML and extract market blurbs.

Usage:
    # From clipboard (macOS):
    pbpaste | python3 scripts/parse_polymarket_email.py

    # From file:
    python3 scripts/parse_polymarket_email.py < email.html

    # With date override:
    pbpaste | python3 scripts/parse_polymarket_email.py --date 2026-05-01

Appends extracted blurbs to backend/data/polymarket_blurbs.json.
"""
import argparse
import json
import sys
from datetime import date
from pathlib import Path

try:
    from bs4 import BeautifulSoup
except ImportError:
    print("pip install beautifulsoup4", file=sys.stderr)
    sys.exit(1)

DATA_FILE = Path(__file__).parent.parent / "data" / "polymarket_blurbs.json"


def extract_blurbs(html: str) -> list[dict]:
    soup = BeautifulSoup(html, "html.parser")
    blurbs = []

    # Polymarket emails use table-based layouts with market cards.
    # Each card typically has: a bold title, a paragraph of context,
    # and probability/outcome data. We look for these patterns.

    # Strategy 1: Look for <td> blocks with a bold headline + paragraph
    for td in soup.find_all("td"):
        # Find bold/strong text (market name)
        title_el = td.find(["strong", "b", "h2", "h3"])
        if not title_el:
            continue
        title = title_el.get_text(strip=True)
        if len(title) < 5 or len(title) > 200:
            continue

        # Find the paragraph context (sibling or child text)
        paragraphs = td.find_all("p")
        context = ""
        for p in paragraphs:
            text = p.get_text(strip=True)
            if len(text) > 30 and text != title and "%" not in text[:10]:
                context = text
                break

        if not context:
            # Try getting text directly from the td, excluding the title
            all_text = td.get_text(" ", strip=True)
            remaining = all_text.replace(title, "").strip()
            if len(remaining) > 30:
                context = remaining[:500]

        if context and len(context) > 20:
            blurbs.append({
                "market_name": title,
                "blurb": context[:500],
            })

    # Strategy 2: Look for div-based layouts
    if not blurbs:
        for div in soup.find_all("div", class_=True):
            title_el = div.find(["h2", "h3", "strong"])
            if not title_el:
                continue
            title = title_el.get_text(strip=True)
            if len(title) < 5:
                continue

            p = div.find("p")
            if p:
                text = p.get_text(strip=True)
                if len(text) > 20:
                    blurbs.append({
                        "market_name": title,
                        "blurb": text[:500],
                    })

    # Deduplicate by market name
    seen = set()
    unique = []
    for b in blurbs:
        if b["market_name"] not in seen:
            seen.add(b["market_name"])
            unique.append(b)

    return unique


def main():
    parser = argparse.ArgumentParser(description="Parse Polymarket email HTML")
    parser.add_argument("--date", default=date.today().isoformat(), help="Date for the email (YYYY-MM-DD)")
    args = parser.parse_args()

    html = sys.stdin.read()
    if not html.strip():
        print("No input. Pipe HTML via stdin.", file=sys.stderr)
        sys.exit(1)

    blurbs = extract_blurbs(html)
    if not blurbs:
        print("No market blurbs found in the email HTML.", file=sys.stderr)
        sys.exit(1)

    for b in blurbs:
        b["date"] = args.date
        b.setdefault("category", None)

    # Load existing data
    existing = []
    if DATA_FILE.exists():
        existing = json.loads(DATA_FILE.read_text())

    existing.extend(blurbs)
    DATA_FILE.write_text(json.dumps(existing, indent=2, ensure_ascii=False) + "\n")

    print(f"Extracted {len(blurbs)} blurbs, total now {len(existing)}")
    for b in blurbs:
        print(f"  {b['market_name'][:50]}: {b['blurb'][:80]}...")


if __name__ == "__main__":
    main()
