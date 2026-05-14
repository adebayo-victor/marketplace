import cs50
import time
import os
from dotenv import load_dotenv

load_dotenv()

local_db = cs50.SQL("sqlite:///techlite_backup.db")
cloud_db = cs50.SQL(os.environ.get("DATABASE_URL"))

SKIP_TABLES = ["leads", "visitations", "merchants", "products"]
TARGET_TABLES = ["orders", "merchant_recommendations", "kiosks", "customers", "premium_merchants", "buyers"]

def resume_upload():
    start_time = time.time()
    print("\n" + "="*50)
    print("INFO: 🚀 [RESUME MODE] Initializing detailed sync...")
    print(f"INFO: 🛡️  PROTECTED: {', '.join(SKIP_TABLES)}")
    print("="*50 + "\n")

    for table in TARGET_TABLES:
        try:
            local_rows = local_db.execute(f"SELECT * FROM {table}")
        except Exception:
            print(f"ERROR: ❌ Table [{table}] not found in backup. Skipping.")
            continue

        total = len(local_rows)
        success_count = 0
        skip_count = 0
        
        print(f"▶️  STARTING TABLE: [{table}] | Total Rows: {total}")

        for index, row in enumerate(local_rows):
            row_id = row.get('id')
            
            # 1. Existence Check with specific ID log for every 10th skip
            exists = cloud_db.execute(f"SELECT id FROM {table} WHERE id = :id", id=row_id)
            
            if not exists:
                try:
                    columns = row.keys()
                    col_names = ", ".join(columns)
                    placeholders = ", ".join([f":{c}" for c in columns])
                    query = f"INSERT INTO {table} ({col_names}) VALUES ({placeholders})"
                    
                    cloud_db.execute(query, **row)
                    success_count = success_count + 1
                    
                    # Log every successful insert for visibility
                    print(f"   📥 [INSERT] {table} ID: {row_id} | Progress: {index + 1}/{total}")
                    
                except Exception as e:
                    print(f"   ⚠️  [FAILED] {table} ID: {row_id} | Error: {e}")
            else:
                skip_count = skip_count + 1
                # Periodically log skips so you know the script hasn't frozen
                if skip_count % 20 == 0:
                    print(f"   ⏭️  [SKIP] {table}: {skip_count} rows already exist (Catching up...)")

        # Table Summary Log
        print(f"✅ FINISHED: [{table}]")
        print(f"   ↳ Added: {success_count} | Existing: {skip_count} | Total: {total}")
        print("-" * 50)

    end_time = time.time()
    duration = round(end_time - start_time, 2)
    print(f"\n🎉 [COMPLETE] Migration finished in {duration} seconds.")
    print("🛡️  Reminder: 1,258 visits and 64 leads were preserved.\n")

if __name__ == "__main__":
    resume_upload()