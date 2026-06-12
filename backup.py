'''import os
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
    run_restore()'''


#backup program
import os
import logging
from dotenv import load_dotenv
from cs50 import SQL

load_dotenv()

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s | %(levelname)s | %(message)s',
    datefmt='%H:%M:%S'
)
logger = logging.getLogger("TechliteDynamicBackup")

def run_backup():
    logger.info("📡 [START] Initiating dynamic cloud-to-local schema backup workflow...")
    
    cloud_uri = os.environ.get("DATABASE_URL")
    local_file = "techlite_backup.db"

    # 1. Purge the old backup if it exists
    if os.path.exists(local_file):
        logger.info(f"🧹 [CLEANUP] Found existing local file '{local_file}'. Purging for fresh snapshot.")
        os.remove(local_file)
    
    # 2. Force-create a fresh, blank file so cs50.SQL doesn't crash
    logger.info(f"📝 [FILE] Creating a fresh, empty '{local_file}' baseline file...")
    with open(local_file, "w") as f:
        pass 

    try:
        logger.info("🔗 [CONN] Establishing cloud database handshake...")
        cloud_db = SQL(cloud_uri)
        
        logger.info("🔗 [CONN] Establishing local SQLite file engine handshake...")
        local_db = SQL(f"sqlite:///{local_file}")
        logger.info("✅ [CONN] Both database engines connected successfully.")
    except Exception as e:
        logger.error(f"❌ [CRITICAL] Database connection handshake failed: {e}")
        return

    try:
        logger.info("🔍 [SCHEMA] Querying cloud information_schema for user tables...")
        tables = cloud_db.execute(
            "SELECT table_name FROM information_schema.tables WHERE table_schema='public'"
        )
        logger.info(f"🔎 [SCHEMA] Found {len(tables)} target tables in cloud public schema.")
    except Exception as e:
        logger.error(f"❌ [CRITICAL] Failed to extract database schema tables: {e}")
        return

    for idx, row in enumerate(tables, 1):
        t_name = row['table_name']
        logger.info(f"--------------------------------------------------")
        logger.info(f"📦 [TABLE {idx}/{len(tables)}] Processing target: '{t_name}'")

        try:
            logger.info(f"  ↳ 📥 Fetching all rows live from cloud table '{t_name}'...")
            cloud_data = cloud_db.execute(f"SELECT * FROM {t_name}")
            total_rows = len(cloud_data)
            logger.info(f"  ↳ 📥 Retreived {total_rows} rows from cloud source.")
        except Exception as e:
            logger.error(f"  ↳ ❌ [ERROR] Failed to extract data from cloud table '{t_name}': {e}")
            continue

        if total_rows == 0:
            logger.info(f"  ↳ 📭 Table '{t_name}' is empty. Skipping generation structure.")
            continue 

        cols = list(cloud_data[0].keys())
        logger.info(f"  ↳ 🛠️ Detected Schema Columns: {', '.join(cols)}")
        
        col_defs = ", ".join([f"{col} TEXT" for col in cols])
        try:
            local_db.execute(f"CREATE TABLE IF NOT EXISTS {t_name} ({col_defs})")
            logger.info(f"  ↳ 🏗️ Local SQLite mirror table '{t_name}' verified/created.")
        except Exception as e:
            logger.error(f"  ↳ ❌ [ERROR] Failed local table structure execution: {e}")
            continue

        placeholders = ":" + ", :".join(cols)
        insert_query = f"INSERT INTO {t_name} ({', '.join(cols)}) VALUES ({placeholders})"

        success_count = 0
        logger.info(f"  ↳ 🚀 Commencing data stream pipeline ingestion...")
        
        for i, record in enumerate(cloud_data, 1):
            try:
                sanitized_record = {k: (str(v) if v is not None else None) for k, v in record.items()}
                local_db.execute(insert_query, **sanitized_record)
                success_count += 1
                logger.info(f"    ↳ [ROW {i}/{total_rows}] ✅ Local mirror storage verified.")
            except Exception as e:
                err_msg = str(e).splitlines()[0]
                logger.error(f"    ↳ [ROW {i}/{total_rows}] ❌ Sync rejection error: {err_msg}")

        logger.info(f"📊 [SUMMARY] Finished '{t_name}': Successfully mirrored {success_count} of {total_rows} records.")

    logger.info(f"--------------------------------------------------")
    logger.info("🏁 [FINISHED] Total dynamic local backup runtime complete.")

if __name__ == "__main__":
    run_backup()