import os
import time  # New import for the delay
from dotenv import load_dotenv
from cs50 import SQL
import logging

load_dotenv()

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s | %(levelname)s | %(message)s',
    datefmt='%H:%M:%S'
)
logger = logging.getLogger("TechliteRestore")

def run_restore():
    logger.info("📡 [START] Throttled Restoration (2s delay per row)")
    
    new_uri = os.environ.get("DATABASE_URL")
    local_file = "techlite_backup.db"

    try:
        local_db = SQL(f"sqlite:///{local_file}")
        cloud_db = SQL(new_uri)
        logger.info("🔗 [CONN] Connected successfully.")
    except Exception as e:
        logger.error(f"❌ [CRITICAL] Connection Failed: {e}")
        return

    tables = local_db.execute("SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'")

    for row in tables:
        t_name = row['name']
        local_data = local_db.execute(f"SELECT * FROM {t_name}")
        total_rows = len(local_data)
        
        if total_rows == 0: continue

        cols = local_data[0].keys()
        placeholders = ":" + ", :".join(cols)
        insert_query = f"INSERT INTO {t_name} ({', '.join(cols)}) VALUES ({placeholders})"
        
        logger.info(f"📦 [TABLE] {t_name} ({total_rows} rows)")

        success_count = 0
        for i, record in enumerate(local_data, 1):
            try:
                cloud_db.execute(insert_query, **record)
                success_count += 1
                logger.info(f"   ↳ ✅ [ROW {i}/{total_rows}] Success.")
            except Exception as e:
                # Get the core error message
                err_msg = str(e).splitlines()[0]
                logger.error(f"   ↳ ❌ [ROW {i}/{total_rows}] ERROR: {err_msg}")
                
                # RECOVERY: Clear the failed state for Postgres
                try:
                    cloud_db.execute("ROLLBACK")
                    logger.info("      (Reset transaction state)")
                except:
                    pass 

            # --- THE 2 SECOND WAIT ---
            if i < total_rows: # Don't wait after the very last row
                time.sleep(2)

        logger.info(f"📊 [SUMMARY] {t_name}: {success_count}/{total_rows} synced.")

    logger.info("🏁 [FINISHED] Restoration Complete.")

if __name__ == "__main__":
    run_restore()