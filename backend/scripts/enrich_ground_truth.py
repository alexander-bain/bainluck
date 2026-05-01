"""
Enrich Polymarket Ground Truth sheet rows with LLM classification.

Reads the Google Sheet, finds rows without LLM enrichment, calls GPT-4o-mini
to classify and describe each market, writes results back to new columns.

Adds columns I-M:
  I: LLM Category (replaces regex guess)
  J: Hook (1-sentence blurb)
  K: Interestingness (1-10)
  L: Timeliness (this_week / this_month / ongoing / historical)
  M: Shareability (1-10, "would someone share this on social media?")

Usage:
    # Dry run (show what would be enriched):
    python3 scripts/enrich_ground_truth.py --dry-run

    # Enrich up to 50 rows:
    python3 scripts/enrich_ground_truth.py --limit 50

    # Run on Heroku:
    heroku run --app bainluck -- python3 scripts/enrich_ground_truth.py --limit 50
"""

import argparse
import json
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

SHEET_ID = "1RztughDfCj1F691yeQWq_67UfCn3LXNpVrejZ35_4_w"

# Column indices (0-based): A=0, B=1, ... H=7, I=8, J=9, K=10, L=11, M=12
COL_MARKET_NAME = 2   # C
COL_CATEGORY = 3      # D
COL_LLM_CATEGORY = 8  # I (new)
COL_HOOK = 9           # J (new)
COL_INTEREST = 10      # K (new)
COL_TIMELINESS = 11    # L (new)
COL_SHAREABILITY = 12  # M (new)

ENRICHMENT_PROMPT = """You are classifying prediction markets for a consumer app called Bain Luck.

For each market, return a JSON object with these fields:
- "category": one of: basketball, football, baseball, hockey, soccer, golf, mma, tennis, motorsports, esports, cricket, rugby, economics, politics, geopolitics, tech, entertainment, culture, health, weather, other
- "hook": A single compelling sentence (max 120 chars) that explains WHY this is interesting to a casual person. Be specific, not generic.
- "interestingness": 1-10 score. 10 = "I need to tell someone about this RIGHT NOW." 1 = "I don't care at all." Score based on: surprise factor, cultural relevance, timeliness, emotional resonance. A market about Taylor Swift meeting the Pope is a 10. "GDP growth in Q3" is a 3.
- "timeliness": one of: "this_week" (resolves or peaks in interest within 7 days), "this_month", "ongoing" (long-running, checked periodically), "historical" (already resolved or stale)
- "shareability": 1-10 score. Would someone screenshot this and text it to a friend? 10 = absolutely. 1 = nobody cares.

Market: {market_name}
Email subject: {email_subject}

Respond with ONLY the JSON object, no markdown, no explanation."""


def enrich_rows(limit: int = 50, dry_run: bool = False):
    from openai import OpenAI

    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        print("OPENAI_API_KEY not set")
        return

    client = OpenAI(api_key=api_key, timeout=30.0)

    # Read the sheet via Google Sheets API
    # On Heroku, use the service account. Locally, this needs gspread or similar.
    # For simplicity, use the meta CLI if available, otherwise httpx
    try:
        import subprocess
        result = subprocess.run(
            ["meta", "google.sheets", "read",
             f"--id={SHEET_ID}",
             "--range=Sheet1!A1:M1000",
             "-o", "json"],
            capture_output=True, text=True, timeout=30
        )
        if result.returncode != 0:
            print(f"Failed to read sheet: {result.stderr[:200]}")
            return
        sheet_data = json.loads(result.stdout)
        rows = sheet_data.get("values", [])
    except FileNotFoundError:
        print("meta CLI not available — trying gspread...")
        try:
            import gspread
            gc = gspread.service_account()
            sh = gc.open_by_key(SHEET_ID)
            ws = sh.sheet1
            rows = ws.get_all_values()
        except Exception as e:
            print(f"gspread failed: {e}")
            print("Run this where meta CLI or gspread is available")
            return

    if not rows:
        print("Sheet is empty")
        return

    headers = rows[0]
    print(f"Sheet has {len(rows) - 1} data rows, {len(headers)} columns")

    # Ensure enrichment columns exist in headers
    while len(headers) < 13:
        headers.append("")
    if headers[8] != "LLM Category":
        # Need to write headers for new columns
        if not dry_run:
            try:
                subprocess.run(
                    ["meta", "google.sheets", "write",
                     f"--id={SHEET_ID}",
                     "--range=I1:M1",
                     '--values=[["LLM Category","Hook","Interestingness","Timeliness","Shareability"]]',
                     "-o", "json"],
                    capture_output=True, text=True, timeout=15
                )
                print("Wrote enrichment column headers (I-M)")
            except Exception as e:
                print(f"Failed to write headers: {e}")

    # Find rows needing enrichment (column I is empty)
    to_enrich = []
    for i, row in enumerate(rows[1:], start=2):  # 1-indexed, skip header
        market_name = row[COL_MARKET_NAME] if len(row) > COL_MARKET_NAME else ""
        llm_cat = row[COL_LLM_CATEGORY] if len(row) > COL_LLM_CATEGORY else ""
        if market_name and not llm_cat:
            email_subject = row[7] if len(row) > 7 else ""
            to_enrich.append({
                "row_num": i,
                "market_name": market_name,
                "email_subject": email_subject,
            })

    print(f"Rows needing enrichment: {len(to_enrich)}")
    if not to_enrich:
        print("Nothing to enrich!")
        return

    batch = to_enrich[:limit]
    print(f"Enriching {len(batch)} rows (limit={limit})")

    if dry_run:
        for item in batch[:10]:
            print(f"  Row {item['row_num']}: {item['market_name'][:60]}")
        if len(batch) > 10:
            print(f"  ... +{len(batch) - 10} more")
        return

    enriched = 0
    errors = 0

    for item in batch:
        try:
            prompt = ENRICHMENT_PROMPT.format(
                market_name=item["market_name"],
                email_subject=item["email_subject"],
            )

            response = client.chat.completions.create(
                model="gpt-4o-mini",
                messages=[{"role": "user", "content": prompt}],
                temperature=0.3,
                max_tokens=300,
            )

            text = response.choices[0].message.content.strip()
            # Strip markdown fences if present
            if text.startswith("```"):
                text = text.split("\n", 1)[1] if "\n" in text else text[3:]
                if text.endswith("```"):
                    text = text[:-3]
                text = text.strip()

            data = json.loads(text)

            category = data.get("category", "other")
            hook = data.get("hook", "")[:150]
            interestingness = min(10, max(1, int(data.get("interestingness", 5))))
            timeliness = data.get("timeliness", "ongoing")
            shareability = min(10, max(1, int(data.get("shareability", 5))))

            # Write back to the sheet
            row_range = f"I{item['row_num']}:M{item['row_num']}"
            values = json.dumps([[category, hook, interestingness, timeliness, shareability]])

            subprocess.run(
                ["meta", "google.sheets", "write",
                 f"--id={SHEET_ID}",
                 f"--range={row_range}",
                 f"--values={values}",
                 "-o", "json"],
                capture_output=True, text=True, timeout=15
            )

            enriched += 1
            if enriched % 10 == 0:
                print(f"  [{enriched}/{len(batch)}] enriched")

            time.sleep(0.2)  # Rate limiting

        except json.JSONDecodeError as e:
            errors += 1
            print(f"  Row {item['row_num']}: JSON parse error — {e}")
        except Exception as e:
            errors += 1
            print(f"  Row {item['row_num']}: Error — {e}")
            if errors > 10:
                print("  Too many errors, stopping")
                break

    print(f"\nDone: enriched={enriched}, errors={errors}")


def main():
    parser = argparse.ArgumentParser(description="Enrich Polymarket ground truth with LLM")
    parser.add_argument("--limit", type=int, default=50, help="Max rows to enrich")
    parser.add_argument("--dry-run", action="store_true", help="Show what would be enriched")
    args = parser.parse_args()
    enrich_rows(limit=args.limit, dry_run=args.dry_run)


if __name__ == "__main__":
    main()
