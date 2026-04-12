from flask import Flask, render_template, jsonify, request, redirect, session
from cs50 import SQL
from werkzeug.security import generate_password_hash
from werkzeug.security import check_password_hash
app = Flask(__name__)
db = SQL("sqlite:///marketplace.db")
app.secret_key = 'super-secret-key-for-marketplace'

@app.route("/")
def index():
    # Fetch Top 3 Merchants by popularity (visitations)
    top_merchants = db.execute("""
        SELECT m.name, m.slug, COUNT(v.id) as visit_count 
        FROM merchants m 
        LEFT JOIN visitations v ON m.id = v.merchant_id 
        GROUP BY m.id 
        ORDER BY visit_count DESC 
        LIMIT 3
    """)
    
    # Global insights for the executive overview
    global_stats = {
        "visitors": db.execute("SELECT COUNT(*) as count FROM visitations")[0]["count"],
        "conversations": db.execute("SELECT COUNT(*) as count FROM leads")[0]["count"]
    }
    
    return render_template("index.html", merchants=top_merchants, stats=global_stats)
@app.route("/register/customer", methods=["GET", "POST"])
def register_customer():
    if request.method == "POST":
        name = request.form.get("name")
        whatsapp = request.form.get("whatsapp")
        email = request.form.get("email")

        # Basic check to see if they already exist
        exists = db.execute("SELECT id FROM customers WHERE whatsapp_number = ?", whatsapp)
        
        if not exists:
            db.execute(
                "INSERT INTO customers (name, whatsapp_number, email) VALUES (?, ?, ?)",
                name, whatsapp, email
            )
        
        # After registration, send them straight to the marketplace
        return redirect("/marketplace")

    return render_template("customer_reg.html")


@app.route("/register/merchant", methods=["GET", "POST"])
def register_merchant():
    if request.method == "POST":
        name = request.form.get("name")
        whatsapp = request.form.get("whatsapp")
        email = request.form.get("email")
        password = request.form.get("password")
        
        # Hash the password for security
        hashed_pw = generate_password_hash(password)

        # Insert the Merchant identity
        # In your model, a 'Shop' is created separately later
        try:
            db.execute(
                "INSERT INTO merchants (name, whatsapp_number, email, password) VALUES (?, ?, ?, ?)",
                name, whatsapp, email, hashed_pw
            )
            # Redirect to a 'Success' or 'Pending' page
            return redirect("/login")
        except:
            return "This WhatsApp number is already registered as a Merchant."

    return render_template("merchant_reg.html")

@app.route("/login/merchant", methods=["GET", "POST"])
def login_merchant():
    if request.method == "POST":
        whatsapp = request.form.get("whatsapp")
        password = request.form.get("password")

        # Verify the Merchant exists
        merchant = db.execute("SELECT * FROM merchants WHERE whatsapp_number = ?", whatsapp)
        
        if merchant and check_password_hash(merchant[0]['password'], password):
            session["user_id"] = merchant[0]['id']
            session["role"] = "merchant"
            # Send them straight to their sales tools
            return redirect("/dashboard")
        
        return "Invalid credentials. Please check your WhatsApp number and password. ❌"

    return render_template("login_merchant.html")

@app.route("/login/customer", methods=["GET", "POST"])
def login_customer():
    if request.method == "POST":
        whatsapp = request.form.get("whatsapp")

        # Search for the customer by their unique WhatsApp number
        customer = db.execute("SELECT id, name FROM customers WHERE whatsapp_number = ?", whatsapp)

        if customer:
            # Save to session so they stay "logged in" during their visit
            session["user_id"] = customer[0]['id']
            session["role"] = "customer"
            session["user_name"] = customer[0]['name']
            
            return redirect("/marketplace")
        
        # If not found, we don't just error out—we invite them to join
        return "Account not found. <a href='/register/customer'>Click here to join the Marketplace!</a>"

    return render_template("login_customer.html")

@app.route("/login-choice")
def login_choice():
    return render_template("login_choice.html")
@app.route("/marketplace")
def marketplace():
    # 1. PUBLIC DATA: Active shops and products for the Feed
    shops = db.execute("SELECT * FROM shops WHERE is_active = 1")
    products = db.execute("""
        SELECT p.*, s.shop_name, s.shop_slug 
        FROM products p 
        JOIN shops s ON p.shop_id = s.id 
        WHERE s.is_active = 1 
        ORDER BY p.visit_count DESC
    """)

    # 2. PRIVATE DATA: User-specific info (if logged in)
    user_data = {"user": None, "orders": [], "subs": []}
    
    if "user_id" in session and session.get("role") == "customer":
        user_id = session["user_id"]
        # Basic user info
        user_rows = db.execute("SELECT * FROM customers WHERE id = ?", user_id)
        if user_rows:
            user_data["user"] = user_rows[0]
            
            # Orders (The "Wallet")
            user_data["orders"] = db.execute("""
                SELECT o.short_id, o.status, p.name as product_name, s.shop_name, p.display_price
                FROM orders o 
                JOIN products p ON o.product_id = p.id 
                JOIN shops s ON p.shop_id = s.id 
                WHERE o.customer_id = ? 
                ORDER BY o.created_at DESC
            """, user_id)
            
            # Subscriptions (The "Following" list)
            user_data["subs"] = db.execute("""
                SELECT s.shop_name, s.shop_slug 
                FROM subscriptions sub 
                JOIN shops s ON sub.shop_id = s.id 
                WHERE sub.customer_id = ?
            """, user_id)

    return render_template("marketplace.html", 
                           shops=shops, 
                           products=products, 
                           **user_data)
@app.route("/profile")
def profile():
    if "user_id" not in session or session.get("role") != "customer":
        return redirect("/login/customer")

    customer_id = session["user_id"]

    # 1. Get Customer Info
    user = db.execute("SELECT * FROM customers WHERE id = ?", customer_id)[0]

    # 2. Get Followed Shops (Subscriptions)
    # We join with shops to get the names and slugs for the UI
    subscriptions = db.execute("""
        SELECT s.shop_name, s.shop_slug 
        FROM subscriptions sub
        JOIN shops s ON sub.shop_id = s.id
        WHERE sub.customer_id = ?
    """, customer_id)

    # 3. Get Orders (The "Wallet" of Codes)
    # We fetch the order status and product info
    orders = db.execute("""
        SELECT o.short_id, o.status, o.is_unlocked, p.name as product_name, p.display_price, s.shop_name 
        FROM orders o
        JOIN products p ON o.product_id = p.id
        JOIN shops s ON p.shop_id = s.id
        WHERE o.customer_id = ?
        ORDER BY o.created_at DESC
    """, customer_id)

    return render_template("profile.html", user=user, subs=subscriptions, orders=orders)
app.run(port=2000)