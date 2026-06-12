import cs50
import os
from dotenv import load_dotenv
load_dotenv()
# Connect to your V1 SQLite database instance
db = cs50.SQL("sqlite:///marketplace.db")

# 1. Create the Subscriptions Table from scratch
db.execute("""
    CREATE TABLE IF NOT EXISTS subscriptions (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        merchant_id INTEGER NOT NULL,
        kiosk_id INTEGER NOT NULL,
        status TEXT DEFAULT 'active', -- 'active', 'expired', 'pending_payment'
        amount_paid REAL NOT NULL,
        starts_at DATETIME DEFAULT CURRENT_TIMESTAMP,
        expires_at DATETIME NOT NULL,
        FOREIGN KEY(merchant_id) REFERENCES users(id),
        FOREIGN KEY(kiosk_id) REFERENCES kiosks(id)
    )
""")

# 2. Create the Premium Features Table from scratch
db.execute("""
    CREATE TABLE IF NOT EXISTS feature_orders (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        kiosk_id INTEGER NOT NULL,
        merchant_id INTEGER NOT NULL,
        feature_key TEXT NOT NULL,       -- e.g., 'whatsapp_automation', 'payment_gateway'
        amount_paid REAL NOT NULL,
        status TEXT DEFAULT 'pending_build', -- 'pending_build', 'completed'
        created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY(kiosk_id) REFERENCES kiosks(id),
        FOREIGN KEY(merchant_id) REFERENCES users(id)
    )
""")

# 3. Add an unlocked_features tracking column to your existing kiosks table
try:
    db.execute("ALTER TABLE kiosks ADD COLUMN unlocked_features TEXT DEFAULT ''")
except Exception:
    # Safe fallback if you already ran the alter command previously
    pass