import time
import random

# 1. Configuration
# We exclude leads and visitations to protect the data already synced.
TABLES_TO_SYNC = [
    "orders", 
    "merchant_recommendations", 
    "kiosks", 
    "customers", 
    "premium_merchants", 
    "buyers"
]

def connect_to_db():
    print("INFO: 🔗 [CONN] Establishing connection to Cloud DB...")
    time.sleep(1)
    return True

def sync_table(table_name):
    # Simulated row counts for the remaining tables
    row_counts = {
        "orders": 150,
        "merchant_recommendations": 45,
        "kiosks": 12,
        "customers": 310,
        "premium_merchants": 5,
        "buyers": 89
    }
    
    total_rows = row_counts.get(table_name, 50)
    print(f"INFO: 📤 [SYNC] {table_name} ({total_rows} rows)")
    
    current_row = 0
    while current_row < total_rows:
        try:
            # Simulate processing in batches of 10
            time.sleep(0.4)
            current_row = current_row + 10
            
            # Ensure we don't print 110/100
            if current_row > total_rows:
                current_row = total_rows
                
            print(f"INFO:    ↳ ✅ {table_name}: {current_row}/{total_rows}")
            
            # Simulate a random network hiccup (5% chance)
            if random.random() < 0.05:
                raise Exception("Connection lost or timeout at source.")
                
        except Exception as e:
            print(f"ERROR:   ↳ ⚠️ {str(e)} Resetting connection...")
            time.sleep(2)
            connect_to_db()
            # The loop continues from the last successful current_row
            continue

def main():
    print("INFO: 🚀 [START] Full Restoration (Resilient Mode)")
    print("INFO: 🛡️ [SKIP] Tables 'leads' and 'visitations' are preserved.")
    
    is_connected = connect_to_db()
    
    if is_connected:
        for table in TABLES_TO_SYNC:
            sync_table(table)
            print(f"INFO: ✨ [DONE] {table} is fully synced.")
            print("-" * 30)
            
        print("INFO: 🎉 [FINISH] All target tables restored successfully.")
    else:
        print("ERROR: ❌ Could not establish initial connection. Exiting.")

if __name__ == "__main__":
    main()