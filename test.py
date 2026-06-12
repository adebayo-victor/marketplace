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
    
    prompt = f"""Act as a Senior Full-Stack Web Designer. Build a single-file HTML storefront for '{name}'.
        VIBE: {vibe}

        {visual_specs}

        ARCHITECTURE REQUIREMENTS:
        {extra_specs if extra_specs else "- Standard Product Grid only."}
        - DESIGN STYLE: Figma-inspired. Use 8px grid spacing, soft shadows (rgba 0,0,0,0.05), and Plus Jakarta Sans.
        - DYNAMICITY: Implement skeleton loaders (shimmer effect) while fetching data. Use a JS 'state' object to manage the UI.
        - ANIMATION STRATEGY: Select the most appropriate motion style from this list to match the vibe: 
        [Micro-Interactions, Cinematic Scrollytelling, Kinetic Typography, 3D Immersion (CSS-based), Organic Fluidity, or Neo-Brutalism].

        TECHNICAL SPECS:
        1. STYLING: Premium CSS in a <style> block. Use backdrop-filter for glassmorphism headers. mobile friendly.
        2. ASSETS: If an asset URL is 'none', use a CSS-only decorative fallback (like a gradient). Do NOT use placeholder.com.
        3. DATA: Fetch products from 'https://marketplace-ekhr.onrender.com/api/get_products' via POST {{ "kiosk_id": {kiosk_id} }}. The src can be gotten from the fetched data, the key is "image_url".
        4. CART: Implement a sliding 'Cart Drawer'. Users must be able to adjust quantities and see a subtotal.
        5. CHECKOUT & LEAD CAPTURE: [prices in naira]
        - Build a form for Customer Name and WhatsApp/Phone.
        - DISCREET ACTION: When the form is submitted, first send a background POST request to '/api/capture_lead' with {{ "kiosk_id": {kiosk_id}, "name": name, "phone": phone }}. 
        - DO NOT wait for this request to finish before proceeding to the WhatsApp redirect.
        6. WHATSAPP BRIDGE: After lead capture, redirect to: https://wa.me/{whatsapp}?text=... (Include Name, Itemized List, Total, and the link to the order form at {{ url_for('order_form', merchant_slug=merchant.slug) }}).
        7. LOGIC: Use standard 'if/else' statements. **DO NOT use ternary operators (?:)** in the code.
        8. Ensure the background is visible, but the styling remains unaffected.
        9. Add a dark/light theme toggle.
        10. Footnote: Marketplace project, powered by techlite.
        Return ONLY raw HTML/CSS/JS. No markdown, no preamble."""
    
    try:
        response = model.generate_content(prompt)
        return response.text.replace("```html", "").replace("```", "").strip()
    except Exception as e:
        return f"<div style='padding:20px; color:red;'>Architectural failure: {e}</div>"