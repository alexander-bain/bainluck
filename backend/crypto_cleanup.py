import os, psycopg2

conn = psycopg2.connect(os.environ['DATABASE_URL'])
conn.autocommit = True
cur = conn.cursor()

cur.execute("SELECT COUNT(*) FROM futures_markets WHERE llm_sport_category = 'crypto'")
mcount = cur.fetchone()[0]
print(f"Crypto markets: {mcount}")

if mcount == 0:
    print("Nothing to delete")
    conn.close()
    exit()

cur.execute("SELECT id FROM futures_markets WHERE llm_sport_category = 'crypto'")
market_ids = [r[0] for r in cur.fetchall()]

cur.execute("SELECT id FROM futures_outcomes WHERE market_id = ANY(%s)", (market_ids,))
outcome_ids = [r[0] for r in cur.fetchall()]
print(f"Crypto outcomes: {len(outcome_ids)}")

if outcome_ids:
    total = 0
    while True:
        cur.execute("""
            DELETE FROM futures_odds_snapshots
            WHERE id IN (
                SELECT id FROM futures_odds_snapshots
                WHERE outcome_id = ANY(%s)
                LIMIT 5000
            )
        """, (outcome_ids,))
        deleted = cur.rowcount
        total += deleted
        print(f"Deleted {total} snapshots...")
        if deleted < 5000:
            break

cur.execute("DELETE FROM futures_outcomes WHERE market_id = ANY(%s)", (market_ids,))
print(f"Deleted {cur.rowcount} outcomes")

cur.execute("DELETE FROM futures_markets WHERE llm_sport_category = 'crypto'")
print(f"Deleted {cur.rowcount} markets")

conn.close()
print("DONE")
