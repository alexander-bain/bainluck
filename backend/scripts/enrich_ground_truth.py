"""
Enrich Polymarket Ground Truth sheet rows with LLM classification.

Reads the Google Sheet via service account, finds rows without LLM enrichment,
calls GPT-4o-mini to classify each market, writes results back.

Usage:
    heroku run --app bainluck -- python3 scripts/enrich_ground_truth.py --dry-run
    heroku run --app bainluck -- python3 scripts/enrich_ground_truth.py --limit 50
"""

import argparse
import json
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

SHEET_ID = "1RztughDfCj1F691yeQWq_67UfCn3LXNpVrejZ35_4_w"
SCOPES = ["https://www.googleapis.com/auth/spreadsheets"]

COL_MARKET_NAME = 2   # C
COL_LLM_CATEGORY = 8  # I

ENRICHMENT_PROMPT = """You are classifying prediction markets for a consumer app.

For this market, return a JSON object with these fields:
- "category": one of: basketball, football, baseball, hockey, soccer, golf, mma, tennis, motorsports, esports, cricket, rugby, economics, politics, geopolitics, tech, entertainment, culture, health, weather, other
- "hook": A single compelling sentence (max 120 chars) explaining WHY this is interesting to a casual person. Be specific.
- "interestingness": 1-10. 10 = "tell someone RIGHT NOW." 1 = "don't care." Based on: surprise, cultural relevance, timeliness, emotional resonance.
- "timeliness": one of: "this_week", "this_month", "ongoing", "historical"
- "shareability": 1-10. Would someone screenshot this and text it to a friend?

Market: {market_name}
Email subject: {email_subject}

Respond with ONLY valid JSON, no markdown."""


def _get_sheets_service():
    """Build Google Sheets API client from Firebase service account credentials."""
    import google.auth
    from google.oauth2 import service_account
    from googleapiclient.discovery import build

    # Heroku stores Firebase service account as FIREBASE_SERVICE_ACCOUNT_JSON
    creds_json = os.getenv("FIREBASE_SERVICE_ACCOUNT_JSON")
    if not creds_json:
        creds_json = os.getenv("GOOGLE_APPLICATION_CREDENTIALS_JSON")
    if not creds_json:
        # Try reading from file
        creds_file = os.getenv("GOOGLE_APPLICATION_CREDENTIALS")
        if creds_file and os.path.exists(creds_file):
            creds_json = open(creds_file).read()

    if not creds_json:
        raise RuntimeError(
            "No Google credentials found. Set GOOGLE_APPLICATION_CREDENTIALS_JSON, "
            "FIREBASE_CONFIG, or GOOGLE_APPLICATION_CREDENTIALS"
        )

    creds_dict = json.loads(creds_json)
    credentials = service_account.Credentials.from_service_account_info(
        creds_dict, scopes=SCOPES
    )
    return build("sheets", "v4", credentials=credentials)


def _read_sheet(service):
    """Read all rows from the sheet."""
    result = service.spreadsheets().values().get(
        spreadsheetId=SHEET_ID,
        range="Sheet1!A1:M1000",
    ).execute()
    return result.get("values", [])


def _write_headers(service):
    """Write enrichment column headers if not present."""
    service.spreadsheets().values().update(
        spreadsheetId=SHEET_ID,
        range="I1:M1",
        valueInputOption="RAW",
        body={"values": [["LLM Category", "Hook", "Interestingness", "Timeliness", "Shareability"]]},
    ).execute()


def _write_row(service, row_num, values):
    """Write enrichment data to a single row."""
    service.spreadsheets().values().update(
        spreadsheetId=SHEET_ID,
        range=f"I{row_num}:M{row_num}",
        valueInputOption="RAW",
        body={"values": [values]},
    ).execute()


def enrich_rows(limit: int = 50, dry_run: bool = False):
    from openai import OpenAI

    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        print("OPENAI_API_KEY not set")
        return

    client = OpenAI(api_key=api_key, timeout=30.0)

    print("Connecting to Google Sheets...")
    try:
        service = _get_sheets_service()
    except Exception as e:
        print(f"Failed to connect: {e}")
        return

    rows = _read_sheet(service)
    if not rows:
        print("Sheet is empty")
        return

    print(f"Sheet has {len(rows) - 1} data rows")

    # Check if enrichment headers exist
    headers = rows[0]
    if len(headers) < 9 or headers[8] != "LLM Category":
        if not dry_run:
            _write_headers(service)
            print("Wrote enrichment column headers (I-M)")

    # Find rows needing enrichment
    to_enrich = []
    for i, row in enumerate(rows[1:], start=2):
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
    print(f"Enriching {len(batch)} rows...")

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
            if text.startswith("```"):
                text = text.split("\n", 1)[1] if "\n" in text else text[3:]
                if text.endswith("```"):
                    text = text[:-3]
                text = text.strip()

            data = json.loads(text)

            category = data.get("category", "other")
            hook = data.get("hook", "")[:150]
            interestingness = str(min(10, max(1, int(data.get("interestingness", 5)))))
            timeliness = data.get("timeliness", "ongoing")
            shareability = str(min(10, max(1, int(data.get("shareability", 5)))))

            _write_row(service, item["row_num"], [category, hook, interestingness, timeliness, shareability])

            enriched += 1
            print(f"  [{enriched}/{len(batch)}] {item['market_name'][:40]:40s} → {category} (int={interestingness}, share={shareability})")

            time.sleep(0.3)

        except json.JSONDecodeError as e:
            errors += 1
            print(f"  Row {item['row_num']}: JSON parse error — {text[:100]}")
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
