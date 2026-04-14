from flask import Flask, render_template, jsonify, request, redirect, session, render_template_string
from cs50 import SQL
import re
import re
from werkzeug.security import generate_password_hash
from werkzeug.security import check_password_hash
import os
import random
import string
from dotenv import load_dotenv
from datetime import datetime
import pytz
import google.generativeai as genai
import hashlib
import requests
# Load the key from a .env file
load_dotenv()
#paystack key
PAYSTACK_SECRET_KEY = os.getenv("PAYSTACK_KEY")



# genai configuration
os.getenv("GEMINI_API_KEY")
genai.configure(api_key=os.getenv("GEMINI_API_KEY"))

app = Flask(__name__)
db = SQL(os.environ.get("DATABASE_URL"))
app.secret_key = 'super-secret-key-for-marketplace'

@app.route("/")
def index():
    # Fetch Top 3 Kiosks by popularity (visitations)
    # JOINing kiosks to visitations on the new kiosks_id column
    top_kiosks = db.execute("""
        SELECT k.kiosk_name, k.slug, COUNT(v.id) as visit_count 
        FROM kiosks k 
        LEFT JOIN visitations v ON k.id = v.kiosks_id 
        GROUP BY k.id 
        ORDER BY visit_count DESC 
        LIMIT 3
    """)
    
    # Global insights remain aggregated across all kiosks
    global_stats = {
        "visitors": db.execute("SELECT COUNT(*) as count FROM visitations")[0]["count"],
        "conversations": db.execute("SELECT COUNT(*) as count FROM leads")[0]["count"]
    }
    
    return render_template("index.html", kiosks=top_kiosks, stats=global_stats)


def slugify(text):
    """Convert store name to url-friendly slug."""
    text = text.lower()
    return re.sub(r'[\s\W_]+', '-', text).strip('-')

@app.route("/register", methods=["GET", "POST"])
def register():
    if request.method == "POST":
        name = request.form.get("name")
        phone = request.form.get("phone")
        password = request.form.get("password")
        # This slug identifies the Merchant (Master Account)
        merchant_slug = slugify(name)

        # Check if merchant slug already exists
        existing = db.execute("SELECT id FROM merchants WHERE slug = ?", merchant_slug)
        if existing:
            return render_template("taken.html")

        # Create the Master Merchant Account
        db.execute("""
            INSERT INTO merchants (name, slug, whatsapp_number, password) 
            VALUES (?, ?, ?, ?)
        """, name, merchant_slug, phone, password)

        return redirect("/login") # Better to send them to login first

    return render_template("register.html")

@app.route("/login", methods=["GET", "POST"])
def login():
    session.clear()

    if request.method == "POST":
        # Convert input name to slug for lookup
        target_slug = slugify(request.form.get("merchant_name"))
        password = request.form.get("password")

        # Verify Master Account
        user = db.execute("SELECT * FROM merchants WHERE slug = ?", target_slug)

        if not user or user[0]["password"] != password:
            return render_template("login.html", error="Invalid merchant name or secret key.")

        # Establish Global Session
        session["merchant_id"] = user[0]["id"]
        session["merchant_name"] = user[0]["name"]
        
        # Take them to their central command
        return redirect("/dashboard")

    return render_template("login.html")

@app.route("/dashboard")
def dashboard():
    if "merchant_id" not in session:
        return redirect("/login")

    # Fetch all kiosks owned by this merchant
    # We use a subquery to count visits and orders per kiosk
    kiosks = db.execute("""
        SELECT 
            k.*,
            (SELECT COUNT(*) FROM visitations v WHERE v.kiosks_id = k.id) as visit_count,
            (SELECT COUNT(*) FROM orders o WHERE o.kiosks_id = k.id) as order_count
        FROM kiosks k
        WHERE k.merchant_id = ?
    """, session["merchant_id"])

    return render_template("dashboard.html", kiosks=kiosks)

@app.route("/<slug>/manage")
def manage_kiosk(slug):
    if "merchant_id" not in session:
        return redirect("/login")

    # 1. Verify this kiosk belongs to the logged-in merchant
    kiosk = db.execute("""
        SELECT * FROM kiosks 
        WHERE slug = ? AND merchant_id = ?
    """, slug, session["merchant_id"])

    if not kiosk:
        return "Unauthorized or Kiosk not found", 403

    k_id = kiosk[0]["id"]

    # 2. Fetch data specifically for this kiosk
    products = db.execute("SELECT * FROM products WHERE kiosks_id = ?", k_id)
    leads = db.execute("SELECT * FROM leads WHERE kiosks_id = ? ORDER BY captured_at DESC", k_id)
    orders = db.execute("SELECT * FROM orders WHERE kiosks_id = ? ORDER BY created_at DESC", k_id)
    
    # 3. Fetch Visitation Data 📊
    # We pull the total count and the raw list of recent visits
    visitations = db.execute("""
        SELECT * FROM visitations 
        WHERE kiosks_id = ? 
        ORDER BY timestamp DESC
    """, k_id)
    
    visit_count = len(visitations)

    # 4. Pass everything to the template
    return render_template(
        "kiosk_manage.html", 
        kiosk=kiosk[0], 
        products=products, 
        leads=leads, 
        orders=orders,
        visitations=visitations,
        visit_count=visit_count
    )

@app.route("/<slug>/product/new", methods=["GET", "POST"])
def add_product(slug):
    if "merchant_id" not in session:
        return redirect("/login")

    # Verify ownership of the kiosk
    kiosk = db.execute("SELECT * FROM kiosks WHERE slug = ? AND merchant_id = ?", slug, session["merchant_id"])
    if not kiosk:
        return "Unauthorized", 403

    if request.method == "POST":
        name = request.form.get("name")
        price = request.form.get("price")
        stock = request.form.get("stock")
        image_url = request.form.get("image_url")

        db.execute("""
            INSERT INTO products (kiosks_id, name, price, stock, image_url)
            VALUES (?, ?, ?, ?, ?)
        """, kiosk[0]["id"], name, price, stock, image_url)

        return redirect(f"/{slug}/manage")

    return render_template("add_product.html", kiosk=kiosk[0])

@app.route("/<slug>/product/edit/<int:product_id>", methods=["GET", "POST"])
def edit_product(slug, product_id):
    if "merchant_id" not in session:
        return redirect("/login")

    # 1. Verify ownership of the kiosk and find the product
    # We join kiosks to products to ensure this product belongs to a kiosk owned by this merchant
    product = db.execute("""
        SELECT p.*, k.slug as kiosk_slug, k.kiosk_name 
        FROM products p
        JOIN kiosks k ON p.kiosks_id = k.id
        WHERE p.id = ? AND k.slug = ? AND k.merchant_id = ?
    """, product_id, slug, session["merchant_id"])

    if not product:
        return "Unauthorized or Product not found", 403

    if request.method == "POST":
        name = request.form.get("name")
        price = request.form.get("price")
        stock = request.form.get("stock")
        image_url = request.form.get("image_url")

        db.execute("""
            UPDATE products 
            SET name = ?, price = ?, stock = ?, image_url = ?
            WHERE id = ?
        """, name, price, stock, image_url, product_id)

        return redirect(f"/{slug}/manage")

    return render_template("edit_product.html", product=product[0])



'''def generate_kiosk_architecture(name, vibe, kiosk_id, whatsapp_number):
    """
    Calls the AI to generate a complete, responsive storefront.
    """
    model = genai.GenerativeModel('gemini-3-flash-preview') # Using Flash for speed/reliability
    
    prompt = f"""
        Act as a Full-Stack Web Designer. Generate a single-file HTML storefront for '{name}'.
        BRAND VIBE: {vibe}
        
        TECHNICAL REQUIREMENTS:
        1. STYLING:
        - Include a <style> block with CSS matching the '{vibe}' aesthetic.
        - Mobile-responsive, luxury feel, with a floating cart icon + badge.
        - Design a beautiful Modal/Overlay for the "Lead Capture" form.

        2. JAVASCRIPT LOGIC (THE FLOW):
        - FETCH: On load, POST to '/api/get_products' with {{ "kiosk_id": {kiosk_id} }}.
        - RENDER: Inject products into 'product-grid'.
        - CART: Use localStorage for 'addToCart' logic.
        - THE LEAD TRAP: When 'Checkout' is clicked, show a Modal asking for 'Name' and 'WhatsApp Number'.
        - SUBMISSION: 
                a) On form submit, POST the name, phone, and kiosk_id ({kiosk_id}) to '/api/capture_lead'.
                b) Use .then() to wait for success, then redirect to:
                https://wa.me/{whatsapp_number}?text=[Detailed_Order_Message]

        3. UI COMPONENTS:
        - Hero section, Product Grid, and a slide-out Cart.
        - The 'Lead Capture' Modal (Must look premium, not like a pop-up ad).

        Return ONLY raw HTML/CSS/JS. No markdown code blocks. Mobile friendly is priority.
        """
    
    try:
        response = model.generate_content(prompt)
        # We strip any accidentally included backticks from the AI response
        clean_html = response.text.replace("```html", "").replace("```", "").strip()
        return clean_html
    except Exception as e:
        # Fallback if the AI fails
        return f"""
        <div style='text-align:center; padding:50px; font-family:sans-serif;'>
            <h1>🏗️ Site Under Construction</h1>
            <p>Our AI Architect is currently busy. Please refresh to try again.</p>
            <small style='color:red;'>Error: {e}</small>
        </div>
        """  '''





@app.route("/kiosk/new", methods=["GET", "POST"])
def new_kiosk():
    if "merchant_id" not in session:
        return redirect("/login")
    
    if request.method == "POST":
        name = request.form.get("kiosk_name")
        vibe = request.form.get("vibe")
        
        # 🟢 COLLECT MODULES & SPECIFIC DETAILS
        module_data = {
            "hero": request.form.get("hero_text") if request.form.get("module_hero") else None,
            "faq": request.form.get("faq_focus") if request.form.get("module_faq") else None,
            "reviews": request.form.get("review_style") if request.form.get("module_reviews") else None
        }

        merchant = db.execute("SELECT whatsapp_number FROM merchants WHERE id = ?", session["merchant_id"])[0]
        whatsapp = merchant["whatsapp_number"]

        base_slug = slugify(name)
        slug = base_slug
        while True:
            existing = db.execute("SELECT id FROM kiosks WHERE slug = ?", slug)
            if not existing: break
            suffix = ''.join(random.choices(string.ascii_lowercase + string.digits, k=3))
            slug = f"{base_slug}-{suffix}"

        try:
            k_id = db.execute("""
                INSERT INTO kiosks (merchant_id, kiosk_name, slug, description, is_active)
                VALUES (?, ?, ?, ?, 0)
            """, session["merchant_id"], name, slug, vibe)

            # 🟢 PASS THE DATA BUNDLE TO THE ARCHITECT
            generated_html = generate_kiosk_architecture(name, vibe, k_id, whatsapp, module_data)
            
            db.execute("UPDATE kiosks SET generated_html = ? WHERE id = ?", generated_html, k_id)
            
            return redirect("/dashboard")

        except Exception as e:
            print(f"Database/AI Error: {e}")
            return f"Something went wrong: {e}", 500

    return render_template("create_kiosk.html")

# 🟢 UPDATE THE ARCHITECT FUNCTION
def generate_kiosk_architecture(name, vibe, kiosk_id, whatsapp, module_data):
    model = genai.GenerativeModel('gemini-3-flash-preview')
    
    # Constructing deep-dive instructions for the AI
    extra_specs = ""
    if module_data.get('hero'):
        extra_specs += f"- HERO BANNER: Use this specific direction: '{module_data['hero']}'.\n"
    if module_data.get('faq'):
        extra_specs += f"- FAQ SECTION: Create 3 Q&As focusing on: '{module_data['faq']}'.\n"
    if module_data.get('reviews'):
        extra_specs += f"- TESTIMONIALS: Generate reviews in this style: '{module_data['reviews']}'.\n"
    
    prompt = f"""
        Act as a Senior Full-Stack Web Designer. Build a single-file HTML storefront for '{name}'.
        VIBE: {vibe}
        
        ARCHITECTURE REQUIREMENTS:
        {extra_specs if extra_specs else "- Standard Product Grid only."}
        
        TECHNICAL SPECS:
        1. STYLING: Premium CSS in a <style> block. Must reflect the '{vibe}'. Mobile-first, glassmorphism, or high-end minimal UI.
        2. DATA LOGIC: 
           - Fetch products from '/api/get_products' via POST {{ "kiosk_id": {kiosk_id} }}.
           - Manage a shopping cart using localStorage.
           - Redirect orders to: https://wa.me/{whatsapp}?text=Hello, I want to order...
        3. MANDATORY:
           - A clean, functional Product Grid.
           - All requested sections from the 'ARCHITECTURE REQUIREMENTS' must be fully styled and populated with AI-generated content based on the provided details.

        Return ONLY raw HTML/CSS/JS. No markdown code blocks, no preamble.
    """
    
    try:
        response = model.generate_content(prompt)
        # Clean up any potential markdown garbage just in case
        clean_html = response.text.replace("```html", "").replace("```", "").strip()
        return clean_html
    except Exception as e:
        return f"<div style='padding:20px; color:red;'>Architectural failure: {e}</div>"





@app.route("/<slug>")
def view_kiosk(slug):
    # Fetch the kiosk and check if it's active
    kiosk = db.execute("SELECT * FROM kiosks WHERE slug = ?", slug)
    
    if not kiosk:
        return "Kiosk not found", 404
        
    # THE GATEKEEPER 🔒
    if kiosk[0]["is_active"] == 0:
        return render_template("locked_site.html", kiosk=kiosk[0])

    # If active, continue to render the AI-generated site
    return kiosk[0]["generated_html"]



@app.route("/api/get_products", methods=["POST"])
def get_products():
    data = request.get_json()
    k_id = data.get("kiosk_id")
    
    if not k_id:
        return jsonify({"error": "No Kiosk ID provided"}), 400
        
    # Fetch only available products for this specific kiosk
    products = db.execute("""
        SELECT id, name, price, stock, image_url 
        FROM products 
        WHERE kiosks_id = ? AND is_available = 1
    """, k_id)
    
    return jsonify(products)



def format_to_wat(utc_time_str):
    if not utc_time_str:
        return ""
    # 1. Parse the string from SQLite
    utc_dt = datetime.strptime(utc_time_str, "%Y-%m-%d %H:%M:%S")
    # 2. Define Timezones
    utc_tz = pytz.timezone('UTC')
    wat_tz = pytz.timezone('Africa/Lagos')
    # 3. Convert
    wat_dt = utc_tz.localize(utc_dt).astimezone(wat_tz)
    return wat_dt.strftime("%b %d, %I:%M %p")

# Add this to your Flask app so the template can use it
app.jinja_env.filters['wat'] = format_to_wat


@app.route("/api/capture_lead", methods=["POST"])
def capture_lead():
    data = request.get_json()
    k_id = data.get("kiosk_id")
    name = data.get("name")
    phone = data.get("phone")

    if not all([k_id, name, phone]):
        return jsonify({"status": "error", "message": "Missing info"}), 400

    # Store in the leads table
    db.execute("""
        INSERT INTO leads (kiosks_id, customer_name, whatsapp_number)
        VALUES (?, ?, ?)
    """, k_id, name, phone)

    return jsonify({"status": "success", "message": "Lead captured"}), 200

@app.route("/<slug>/product/delete/<int:product_id>")
def delete_product(slug, product_id):
    if "merchant_id" not in session:
        return redirect("/login")

    # 1. Verify ownership (Join product -> kiosk -> merchant)
    check = db.execute("""
        SELECT products.id FROM products
        JOIN kiosks ON products.kiosks_id = kiosks.id
        WHERE products.id = ? AND kiosks.slug = ? AND kiosks.merchant_id = ?
    """, product_id, slug, session["merchant_id"])

    if not check:
        return "Unauthorized action or product not found.", 403

    # 2. Delete the product
    db.execute("DELETE FROM products WHERE id = ?", product_id)
    
    # 3. Flash back to the management page
    return redirect(f"/{slug}/manage")

@app.route("/<slug>/delete")
def delete_kiosk(slug):
    if "merchant_id" not in session:
        return redirect("/login")

    # 1. Verify the merchant actually owns this kiosk
    kiosk = db.execute("SELECT id FROM kiosks WHERE slug = ? AND merchant_id = ?", 
                       slug, session["merchant_id"])

    if not kiosk:
        return "Unauthorized or Kiosk not found.", 403

    k_id = kiosk[0]["id"]

    # 2. The Great Wipeout 😈
    # Remove everything linked to this kiosk ID
    db.execute("DELETE FROM products WHERE kiosks_id = ?", k_id)
    db.execute("DELETE FROM leads WHERE kiosks_id = ?", k_id)
    db.execute("DELETE FROM visitations WHERE kiosks_id = ?", k_id)
    db.execute("DELETE FROM orders WHERE kiosks_id = ?", k_id)
    
    # Finally, kill the kiosk itself
    db.execute("DELETE FROM kiosks WHERE id = ?", k_id)

    # 3. Send them back to the main dashboard
    return redirect("/dashboard")





@app.route("/pay/<slug>")
def initialize_payment(slug):
    if "merchant_id" not in session:
        return redirect("/login")

    # 1. Get Kiosk & Merchant Details
    kiosk = db.execute("SELECT kiosk_name FROM kiosks WHERE slug = ?", slug)
    if not kiosk:
        return "Kiosk not found", 404

    # Paystack requires an email. We'll use a placeholder since we don't store merchant emails yet
    email = f"merchant_{session['merchant_id']}@marketplace.com"
    amount = 10000 * 100  # ₦10,000 in Kobo 💰

    # 2. Setup Paystack Payload
    url = "https://api.paystack.co/transaction/initialize"
    headers = {
        "Authorization": f"Bearer {PAYSTACK_SECRET_KEY}",
        "Content-Type": "application/json"
    }
    data = {
        "email": email,
        "amount": amount,
        "callback_url": f"http://127.0.0.1:2000/verify_payment/{slug}",
        "metadata": {
            "kiosk_slug": slug,
            "merchant_id": session["merchant_id"]
        }
    }

    # 3. Request Authorization URL
    try:
        response = requests.post(url, json=data, headers=headers)
        res_data = response.json()

        if res_data["status"]:
            # Send them to the Paystack checkout page
            return redirect(res_data["data"]["authorization_url"])
        else:
            return f"Paystack Init Failed: {res_data['message']}, {PAYSTACK_SECRET_KEY}", 400
    except Exception as e:
        return f"Connection Error: {e}, ", 500


@app.route("/verify_payment/<slug>")
def verify_payment(slug):
    reference = request.args.get('reference')
    if not reference:
        return "No transaction reference found.", 400

    # 1. Verify with Paystack
    url = f"https://api.paystack.co/transaction/verify/{reference}"
    headers = {"Authorization": f"Bearer {PAYSTACK_KEY}"}

    try:
        response = requests.get(url, headers=headers)
        res_data = response.json()

        if res_data["status"] and res_data["data"]["status"] == "success":
            # 2. SUCCESS: Unlock the Kiosk 🔓
            db.execute("UPDATE kiosks SET is_active = 1 WHERE slug = ?", slug)
            # You might want to log the payment reference in a 'payments' table later
            return redirect("/dashboard")
        else:
            return "Payment verification failed. Please contact support.", 400
    except Exception as e:
        return f"Verification Error: {e}", 500


if __name__ == "__main__":
    app.run(port=2000, host="0.0.0.0")