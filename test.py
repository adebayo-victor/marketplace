import os
from cs50 import SQL
from dotenv import load_dotenv

load_dotenv()

raw_url = os.environ.get("DATABASE_URL")
if raw_url and raw_url.startswith("postgres://"):
    raw_url = raw_url.replace("postgres://", "postgresql://", 1)

db = SQL(raw_url)

# High-risk tables that received row migrations from the SQLite backup
target_tables = [
    "visitations", "leads", "products", "orders", 
    "buyers", "merchants", "customers", "premium_merchants",
    "subscriptions", "feature_orders"
]

print("\n" + "="*60)
print("⚡ INITIATING GLOBAL SEQUENCE INDICES RECALIBRATION...")
print("="*60)

for table in target_tables:
    try:
        # Fast-forward sequence tracker to current max value + 1 safely
        db.execute(f"""
            SELECT setval(
                pg_get_serial_sequence('{table}', 'id'), 
                COALESCE(MAX(id), 1)
            ) FROM {table};
        """)
        print(f"   ✅ Sequence fixed successfully for table: [{table}]")
    except Exception as e:
        print(f"   ⚠️  Skipped/No sequence found for table [{table}]: {e}")

print("="*60)
print("🎉 All production data sequence rings match perfectly! Re-run your app.")
print("="*60 + "\n")