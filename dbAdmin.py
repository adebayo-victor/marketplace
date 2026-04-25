from cs50 import SQL
from dotenv import load_dotenv
import os

load_dotenv()

# Connect to your Postgres Cloud DB
db = SQL(os.environ.get("DATABASE_URL"))

'''# 1. Merchants Table
db.execute("""
    CREATE TABLE IF NOT EXISTS merchants (
        id SERIAL PRIMARY KEY,
        name TEXT NOT NULL,
        slug TEXT NOT NULL UNIQUE,
        whatsapp_number TEXT NOT NULL,
        password TEXT NOT NULL,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )
""")

# 2. Kiosks Table
db.execute("""
    CREATE TABLE IF NOT EXISTS kiosks (
        id SERIAL PRIMARY KEY,
        merchant_id INTEGER NOT NULL,
        kiosk_name TEXT NOT NULL,
        slug TEXT NOT NULL UNIQUE,
        description TEXT,
        theme_color TEXT DEFAULT '#8d5b3e',
        
        -- The 5 Visual Slots 📸
        logo_url TEXT,
        banner_url TEXT,
        gallery_1 TEXT,
        gallery_2 TEXT,
        background_url TEXT,

        generated_html TEXT,
        is_active INTEGER DEFAULT 0,
        payment_ref TEXT,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (merchant_id) REFERENCES merchants(id) ON DELETE CASCADE
    )
""")
# 3. Products Table
db.execute("""
    CREATE TABLE IF NOT EXISTS products (
        id SERIAL PRIMARY KEY,
        kiosks_id INTEGER NOT NULL,
        name TEXT NOT NULL,
        price REAL NOT NULL,
        stock INTEGER NOT NULL DEFAULT 0,
        image_url TEXT,
        is_available INTEGER DEFAULT 1,
        FOREIGN KEY (kiosks_id) REFERENCES kiosks(id) ON DELETE CASCADE
    )
""")

# 4. Leads Table
db.execute("""
    CREATE TABLE IF NOT EXISTS leads (
        id SERIAL PRIMARY KEY,
        kiosks_id INTEGER NOT NULL,
        customer_name TEXT,
        whatsapp_number TEXT NOT NULL,
        captured_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (kiosks_id) REFERENCES kiosks(id) ON DELETE CASCADE
    )
""")

# 5. Visitations Table
db.execute("""
    CREATE TABLE IF NOT EXISTS visitations (
        id SERIAL PRIMARY KEY,
        kiosks_id INTEGER NOT NULL,
        ip_hash TEXT,
        user_agent TEXT,
        timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (kiosks_id) REFERENCES kiosks(id) ON DELETE CASCADE
    )
""")

# 6. Orders Table
db.execute("""
    CREATE TABLE IF NOT EXISTS orders (
        id SERIAL PRIMARY KEY,
        kiosks_id INTEGER NOT NULL,
        customer_name TEXT NOT NULL,
        product_name TEXT NOT NULL,
        product_id INTEGER NOT NULL,
        short_id TEXT NOT NULL UNIQUE,
        status TEXT CHECK(status IN ('Pending', 'Processing', 'Dispatched', 'Delivered')) DEFAULT 'Pending',
        amount REAL NOT NULL,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (kiosks_id) REFERENCES kiosks(id) ON DELETE CASCADE,
        FOREIGN KEY (product_id) REFERENCES products(id) ON DELETE CASCADE
    )
""")

print("Cloud Database checked/initialized successfully. ✅")'''

# --- SEEDER SECTION ---

'''def seed():
    print("🌱 Seeding database...")

    # 1. Add a Merchant
    merchant_id = db.execute("""
        INSERT INTO merchants (name, slug, whatsapp_number, password) 
        VALUES ('Victor Adebayo', 'victor-adebayo', '2348012345678', 'secret')
    """)

    # 2. Add two Kiosks
    kiosk_1_id = db.execute("""
        INSERT INTO kiosks (merchant_id, kiosk_name, slug, description, theme_color, is_active, generated_html) 
        VALUES (?, 'The Pottery Shed', 'pottery-shed', 'Handcrafted ceramic souls.', '#8d5b3e', 1, '<div>Pottery Shed Landing Page</div>')
    """, merchant_id)

    kiosk_2_id = db.execute("""
        INSERT INTO kiosks (merchant_id, kiosk_name, slug, description, theme_color, is_active, generated_html) 
        VALUES (?, 'Vintage Threads', 'vintage-threads', 'Curated aesthetic clothing.', '#2d4a3e', 1, '<div>Vintage Threads Landing Page</div>')
    """, merchant_id)

    # 3. Add Products to Kiosk 1
    product_1_id = db.execute("""
        INSERT INTO products (kiosks_id, name, price, stock, image_url, is_available) 
        VALUES (?, 'Terracotta Vase', 45.0, 10, 'https://images.unsplash.com/photo-1581783898377-1c85bf937427?w=500', 1)
    """, kiosk_1_id)

    db.execute("""
        INSERT INTO products (kiosks_id, name, price, stock, image_url, is_available) 
        VALUES (?, 'Minimalist Mug', 12.5, 25, 'https://images.unsplash.com/photo-1514228742587-6b1558fcca3d?w=500', 1)
    """, kiosk_1_id)

    # 4. Add Products to Kiosk 2
    db.execute("""
        INSERT INTO products (kiosks_id, name, price, stock, image_url, is_available) 
        VALUES (?, '90s Denim Jacket', 85.0, 2, 'https://images.unsplash.com/photo-1551537482-f2075a1d41f2?w=500', 1)
    """, kiosk_2_id)

    # 5. Add Visitations
    for _ in range(5):
        db.execute("INSERT INTO visitations (kiosks_id, user_agent) VALUES (?, 'Mozilla/5.0')", kiosk_1_id)
    for _ in range(2):
        db.execute("INSERT INTO visitations (kiosks_id, user_agent) VALUES (?, 'Mozilla/5.0')", kiosk_2_id)

    # 6. Add a Lead
    db.execute("""
        INSERT INTO leads (kiosks_id, customer_name, whatsapp_number) 
        VALUES (?, 'Christianah', '2349000000000')
    """, kiosk_1_id)

    # 7. Add an Order
    db.execute("""
        INSERT INTO orders (kiosks_id, customer_name, product_name, product_id, short_id, amount, status) 
        VALUES (?, 'Christianah', 'Terracotta Vase', ?, 'ORD-1234', 45.0, 'Pending')
    """, kiosk_1_id, product_1_id)

    print("✅ Database seeded with 1 Merchant, 2 Kiosks (Active), 3 Products (Available), and activity data.")

if __name__ == "__main__":
    seed()'''

#print(db.execute("UPDATE kiosks SET is_active = 1 WHERE kiosk_name = 'Otaku fashion corner '"))
#print(db.execute("SELECT kiosk_name, is_active FROM kiosks"))

print(db.execute("DELETE FROM leads WHERE customer_name = ?", "Vicade"))

