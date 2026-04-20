from flask import Flask, render_template, jsonify, request, redirect, session, render_template_string, url_for
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
import json
from datetime import datetime
import base64
import io
import cloudinary
import cloudinary.uploader
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

#cloudinary configuration
cloudinary.config( 
  cloud_name = os.environ.get("CLOUDINARY_NAME"), 
  api_key = os.environ.get("CLOUDINARY_API_KEY"), 
  api_secret = os.environ.get("CLOUDINARY_API_SECRET"),
  secure = True
)

def upload_bytes_to_cloudinary(file_bytes, folder_name="general"):
    """
    Takes raw bytes, wraps them in a buffer, and streams to Cloudinary.
    """
    try:
        # Wrap the bytes in a file-like buffer
        image_stream = io.BytesIO(file_bytes)
        
        response = cloudinary.uploader.upload(
            image_stream,
            folder=f"marketplace/{folder_name}",
            resource_type="auto" # Handles images, icons, or backgrounds
        )
        return response.get("secure_url")
    except Exception as e:
        print(f"❌ RAM-to-Cloudinary Error: {e}")
        return None

def extract_public_id(url):
    # Splits URL and grabs the part after '/upload/v123456789/'
    # This is a bit fragile but works if your folder structure is consistent
    parts = url.split('/')
    # Public ID is usually everything after the version number (starts with 'v')
    for i, part in enumerate(parts):
        if part.startswith('v') and part[1:].isdigit():
            # Join the remaining parts and strip the file extension (.jpg)
            return "/".join(parts[i+1:]).split('.')[0]
    return None

import cloudinary.uploader

def delete_cloudinary_image(public_id):
    """
    Deletes an image from Cloudinary using its Public ID.
    """
    try:
        response = cloudinary.uploader.destroy(public_id)
        if response.get("result") == "ok":
            print(f"✅ Deleted: {public_id}")
            return True
        else:
            print(f"⚠️ Cloudinary Error: {response}")
            return False
    except Exception as e:
        print(f"❌ Deletion failed: {e}")
        return False    

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

    # Verify ownership
    rows = db.execute("SELECT * FROM kiosks WHERE slug = ? AND merchant_id = ?", slug, session["merchant_id"])
    if not rows:
        return "Unauthorized", 403
    kiosk = rows[0]

    if request.method == "POST":
        name = request.form.get("name")
        price = request.form.get("price")
        stock = request.form.get("stock")
        
        # 🟢 Handle Product Image Upload
        file = request.files.get("product_image")
        image_url = None

        if file and file.filename != '':
            # Stream bytes directly to Cloudinary
            file_bytes = file.read()
            # Organizing by kiosk slug makes managing your Cloudinary dashboard easier
            image_url = upload_bytes_to_cloudinary(file_bytes, f"products_{slug}")
        
        # Fallback if no image was uploaded
        if not image_url:
            image_url = "https://via.placeholder.com/400x400?text=No+Image"

        # Insert into DB
        db.execute("""
            INSERT INTO products (kiosks_id, name, price, stock, image_url)
            VALUES (?, ?, ?, ?, ?)
        """, kiosk["id"], name, price, stock, image_url)

        return redirect(f"/{slug}/manage")

    return render_template("add_product.html", kiosk=kiosk)

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





import random
import string
from flask import request, session, redirect, render_template, jsonify

@app.route("/kiosk/new", methods=["GET", "POST"])
def new_kiosk():
    # 1. AUTH CHECK
    if "merchant_id" not in session:
        return redirect("/login")
    
    if request.method == "POST":
        # Pull basic info
        name = request.form.get("kiosk_name")
        vibe = request.form.get("vibe")
        # Ensure you have the merchant's whatsapp number (fallback to a dummy if not in session)
        whatsapp = session.get("merchant_phone", "2348000000000") 
        
        # 2. UNIQUE SLUG ENGINE
        base_slug = slugify(name)
        slug = base_slug
        while True:
            existing = db.execute("SELECT id FROM kiosks WHERE slug = ?", slug)
            if not existing:
                break 
            suffix = ''.join(random.choices(string.ascii_lowercase + string.digits, k=3))
            slug = f"{base_slug}-{suffix}"

        # 3. MEMORY-TO-CLOUDINARY UPLOAD
        image_slots = ["logo_url", "banner_url", "gallery_1", "gallery_2", "background_url"]
        uploaded_urls = {}

        for slot in image_slots:
            file = request.files.get(slot)
            if file and file.filename != '':
                file_bytes = file.read()
                # Use the function we built earlier
                url = upload_bytes_to_cloudinary(file_bytes, f"kiosk_{slug}")
                uploaded_urls[slot] = url
            else:
                uploaded_urls[slot] = None

        # 4. INITIAL DATABASE INSERT (The "Foundation")
        try:
            # We insert first to get the k_id (the primary key)
            k_id = db.execute("""
                INSERT INTO kiosks (
                    merchant_id, kiosk_name, slug, description, 
                    logo_url, banner_url, gallery_1, gallery_2, background_url, 
                    is_active
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 1)
            """, 
            session["merchant_id"], name, slug, vibe,
            uploaded_urls["logo_url"], uploaded_urls["banner_url"], 
            uploaded_urls["gallery_1"], uploaded_urls["gallery_2"], 
            uploaded_urls["background_url"])

            # 5. PREPARE MODULE DATA FOR AI
            module_data = {
                "hero": request.form.get("hero_text"),
                "faq": request.form.get("faq_focus"),
                "reviews": request.form.get("review_style")
            }

            # 6. TRIGGER THE AI ARCHITECT
            # Pass the freshly minted k_id and the uploaded URLs
            ai_html = generate_kiosk_architecture(
                name=name, 
                vibe=vibe, 
                kiosk_id=k_id, 
                whatsapp=whatsapp, 
                module_data=module_data, 
                images=uploaded_urls
            )

            # 7. THE FINAL BRICK: Update the row with the code
            if ai_html:
                db.execute("UPDATE kiosks SET generated_html = ? WHERE id = ?", ai_html, k_id)
            else:
                print(f"⚠️ Error: AI generated no code for Kiosk ID {k_id}")

            return redirect("/dashboard")

        except Exception as e:
            print(f"❌ Critical Failure in new_kiosk: {e}")
            return f"Construction Error: {e}", 500

    # GET request returns the form
    return render_template("create_kiosk.html")

# 🟢 UPDATE THE ARCHITECT FUNCTION
def generate_kiosk_architecture(name, vibe, kiosk_id, whatsapp, module_data, images):
    model = genai.GenerativeModel('gemini-3-flash-preview')
    
    # Constructing visual context
    visual_specs = f"""
    VISUAL ASSETS (MANDATORY: Use these URLs in the HTML):
    - Logo: {images.get('logo_url') or 'none'}
    - Hero Banner: {images.get('banner_url') or 'none'}
    - Gallery 1: {images.get('gallery_1') or 'none'}
    - Gallery 2: {images.get('gallery_2') or 'none'}
    - Page Background: {images.get('background_url') or 'none'}
    """
    
    extra_specs = ""
    if module_data.get('hero'):
        extra_specs += f"- HERO SECTION: Use this direction: '{module_data['hero']}'.\n"
    if module_data.get('faq'):
        extra_specs += f"- FAQ SECTION: Focus on: '{module_data['faq']}'.\n"
    if module_data.get('reviews'):
        extra_specs += f"- REVIEWS: Style them as: '{module_data['reviews']}'.\n"
    
    prompt = f"""
        Act as a Senior Full-Stack Web Designer. Build a single-file HTML storefront for '{name}'.
        VIBE: {vibe}
        
        {visual_specs}
        
        ARCHITECTURE REQUIREMENTS:
        {extra_specs if extra_specs else "- Standard Product Grid only."}
        - DESIGN STYLE: Figma-inspired. Use 8px grid spacing, soft shadows (rgba 0,0,0,0.05), and Plus Jakarta Sans.
        - DYNAMICITY: Implement skeleton loaders (shimmer effect) while fetching data. Use a JS 'state' object to manage the UI.
        - ANIMATION STRATEGY: Select the most appropriate motion style from this list to match the vibe: 
        [Micro-Interactions, Cinematic Scrollytelling, Kinetic Typography, 3D Immersion (CSS-based), Organic Fluidity, or Neo-Brutalism].
        
        TECHNICAL SPECS:
        1. STYLING: Premium CSS in a <style> block. Use backdrop-filter for glassmorphism headers.
        2. ASSETS: If an asset URL is 'none', use a CSS-only decorative fallback (like a gradient). Do NOT use placeholder.com.
        3. DATA: Fetch products from '/api/get_products' via POST {{ "kiosk_id": {kiosk_id} }}.The src can be gotten from the fetched data, the key is "image_url"
        4. CART: Implement a sliding 'Cart Drawer'. Users must be able to adjust quantities and see a subtotal.
        5. CHECKOUT & LEAD CAPTURE: [prices in naira]
        - Build a form for Customer Name and WhatsApp/Phone.
        - DISCREET ACTION: When the form is submitted, first send a background POST request to '/api/capture_lead' with {{ "kiosk_id": {kiosk_id}, "name": name, "phone": phone }}. 
        - DO NOT wait for this request to finish before proceeding to the WhatsApp redirect.
        6. WHATSAPP BRIDGE: After lead capture, redirect to: https://wa.me/{whatsapp}?text=... (Include Name, Itemized List, and Total).
        7. LOGIC: Use standard 'if/else' statements. **DO NOT use ternary operators (?:)** in the code.
        8. Ensure the background is visible, but the styling remains unaffected
        9.Add a dark/light theme toggle
        10.Footnote: Marketplace project, powered by  techlite.
        Return ONLY raw HTML/CSS/JS. No markdown, no preamble.
    """
    
    try:
        response = model.generate_content(prompt)
        return response.text.replace("```html", "").replace("```", "").strip()
    except Exception as e:
        return f"<div style='padding:20px; color:red;'>Architectural failure: {e}</div>"





@app.route("/<slug>")
def view_kiosk(slug):
    # 1. Fetch the rows
    rows = db.execute("SELECT * FROM kiosks WHERE slug = ?", slug)
    
    # 2. Check if the list is empty first 
    if not rows or len(rows) == 0:
        return "<h1>404 - Kiosk Not Found</h1><p>The shop you're looking for doesn't exist yet.</p>", 404
        
    kiosk = rows[0]
    
    # 3. Check the lock status
    # Note: Use '==' or 'not' to ensure we capture the 0/1 integer from SQL
    if kiosk["is_active"] == 0:
        return render_template("locked_site.html", kiosk=kiosk)

    # 4. Final safety check: Does generated_html actually have content?
    if not kiosk['generated_html']:
        return "<h1>Site Under Construction</h1><p>The architect is still laying the bricks.</p>", 200

    # 5. Return the raw HTML string
    return kiosk["generated_html"]



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



def format_to_wat(utc_val):
    if not utc_val:
        return ""
    
    # If it's already a datetime object, use it. If it's a string, parse it.
    if isinstance(utc_val, str):
        utc_dt = datetime.strptime(utc_val, "%Y-%m-%d %H:%M:%S")
    else:
        utc_dt = utc_val

    # Define Timezones
    utc_tz = pytz.timezone('UTC')
    wat_tz = pytz.timezone('Africa/Lagos')
    
    # Ensure it has UTC info before converting to WAT
    if utc_dt.tzinfo is None:
        utc_dt = utc_tz.localize(utc_dt)
        
    wat_dt = utc_dt.astimezone(wat_tz)
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

    # 1. Fetch image URL and Verify ownership
    # We select image_url specifically so we can delete it from the cloud
    product = db.execute("""
        SELECT products.image_url FROM products
        JOIN kiosks ON products.kiosks_id = kiosks.id
        WHERE products.id = ? AND kiosks.slug = ? AND kiosks.merchant_id = ?
    """, product_id, slug, session["merchant_id"])

    if not product:
        return "Unauthorized action or product not found.", 403

    # 2. Extract Public ID and Kill the Cloud Image ☁️💀
    img_url = product[0]["image_url"]
    
    # We only try to delete if it's a Cloudinary link (not a placeholder)
    if img_url and "cloudinary.com" in img_url:
        public_id = extract_public_id(img_url)
        if public_id:
            delete_cloudinary_image(public_id)

    # 3. Delete from Local Database
    db.execute("DELETE FROM products WHERE id = ?", product_id)
    
    return redirect(f"/{slug}/manage")

@app.route("/<slug>/delete")
def delete_kiosk(slug):
    if "merchant_id" not in session:
        return redirect("/login")

    # 1. Fetch Kiosk Data and Assets
    kiosk = db.execute("""
        SELECT id, logo_url, banner_url, gallery_1, gallery_2, background_url 
        FROM kiosks WHERE slug = ? AND merchant_id = ?
    """, slug, session["merchant_id"])

    if not kiosk:
        return "Unauthorized or Kiosk not found.", 403

    k_id = kiosk[0]["id"]
    kiosk_data = kiosk[0]

    # 2. Gather ALL Image URLs to be purged
    urls_to_clean = [
        kiosk_data["logo_url"],
        kiosk_data["banner_url"],
        kiosk_data["gallery_1"],
        kiosk_data["gallery_2"],
        kiosk_data["background_url"]
    ]

    # Add all product images from this kiosk to the list
    product_rows = db.execute("SELECT image_url FROM products WHERE kiosks_id = ?", k_id)
    for row in product_rows:
        urls_to_clean.append(row["image_url"])

    # 3. The Cloudinary Clean-up ☁️💀
    for url in urls_to_clean:
        if url and "cloudinary.com" in url:
            p_id = extract_public_id(url)
            if p_id:
                delete_cloudinary_image(p_id)

    # 4. The Database Wipeout
    # Delete child records first to satisfy foreign key constraints
    db.execute("DELETE FROM products WHERE kiosks_id = ?", k_id)
    db.execute("DELETE FROM leads WHERE kiosks_id = ?", k_id)
    db.execute("DELETE FROM visitations WHERE kiosks_id = ?", k_id)
    db.execute("DELETE FROM orders WHERE kiosks_id = ?", k_id)
    
    # Finally, kill the kiosk itself
    db.execute("DELETE FROM kiosks WHERE id = ?", k_id)

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






# Helper to handle dates
def json_serial(obj):
    if isinstance(obj, datetime):
        return obj.isoformat()
    raise TypeError(f"Type {type(obj)} not serializable")

# Main Explorer Route
@app.route("/overlord/explorer/<view>")
def db_explorer(view="merchants"):
    # Add "products" here so the KeyError vanishes
    table_map = {
        "merchants": "merchants", 
        "kiosks": "kiosks",
        "products": "products" 
    }
    
    # Safety check: if the view isn't in our map, default to merchants
    if view not in table_map:
        return redirect(url_for('db_explorer', view='merchants'))
    
    rows = db.execute(f"SELECT * FROM {table_map[view]}")
    
    processed_rows = []
    for row in rows:
        row_dict = dict(row)
        json_str = json.dumps(row_dict, default=json_serial)
        row_dict['b64_data'] = base64.b64encode(json_str.encode()).decode()
        processed_rows.append(row_dict)
        
    return render_template("overlord.html", view=view, rows=processed_rows)

# API: Get Kiosks for a Merchant
@app.route("/overlord/api/kiosks/<int:merchant_id>")
def get_merchant_kiosks(merchant_id):
    kiosks = db.execute("SELECT * FROM kiosks WHERE merchant_id = ?", (merchant_id,))
    return jsonify([dict(k) for k in kiosks])

# API: Get Products for a Kiosk
@app.route("/overlord/api/products/<int:kiosk_id>")
def get_kiosk_products(kiosk_id):
    products = db.execute("SELECT * FROM products WHERE kiosks_id = ?", (kiosk_id,))
    return jsonify([dict(p) for p in products])

# Action: Create Entry
@app.route("/overlord/create/<view>", methods=["POST"])
def create_entry(view):
    # Logic for insertion based on view goes here
    return redirect(url_for('db_explorer', view=view))

# Action: Update Generic Entry
@app.route("/overlord/update/<view>/<int:id>", methods=["POST"])
def update_entry(view, id):
    # This remains for general field updates
    return redirect(url_for('db_explorer', view=view))

# Action: Delete Entry (Handles Merchants, Kiosks, and Products)
@app.route("/overlord/delete/<view>/<int:id>")
def delete_entry(view, id):
    db.execute(f"DELETE FROM {view} WHERE id = ?", (id,))
    return redirect(request.referrer or url_for('db_explorer', view=view))

# Action: Toggle Kiosk Status
@app.route("/overlord/toggle/kiosks/<int:id>/<int:status>")
def toggle_kiosk(id, status):
    db.execute("UPDATE kiosks SET is_active = ? WHERE id = ?", (status, id))
    return redirect(url_for('db_explorer', view='kiosks'))

# Action: Update Kiosk HTML (Specialized Editor)
@app.route("/overlord/update/kiosks/html/<int:id>", methods=["POST"])
def update_kiosk_html(id):
    new_html = request.form.get("generated_html")
    db.execute("UPDATE kiosks SET generated_html = ? WHERE id = ?", new_html, id)
    return redirect(url_for('db_explorer', view='kiosks'))

# Action: Update Kiosk Properties
@app.route("/overlord/update/kiosks/props/<int:id>", methods=["POST"])
def update_kiosk_properties(id):
    name = request.form.get('kiosk_name')
    slug = request.form.get('slug')
    desc = request.form.get('description')
    color = request.form.get('theme_color')
    
    db.execute("""
        UPDATE kiosks 
        SET kiosk_name = ?, slug = ?, description = ?, theme_color = ? 
        WHERE id = ?
    """, (name, slug, desc, color, id))
    return redirect(url_for('db_explorer', view='kiosks'))
@app.route("/overlord/update/kiosks/html/<int:id>", methods=["POST"])
def update_kiosk_gen_html(id):
    new_html = request.form.get("generated_html")
    # Update the generated_html column for this specific kiosk
    db.execute("UPDATE kiosks SET generated_html = ? WHERE id = ?", (new_html, id))
    return redirect(url_for('db_explorer', view='kiosks'))
if __name__ == "__main__":
    app.run(port=2000, host="0.0.0.0")