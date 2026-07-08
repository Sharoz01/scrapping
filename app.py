import streamlit as st
import streamlit.components.v1 as components
import pandas as pd
import urllib.parse
import os
import time
import base64
from PIL import Image

# Automatically install Playwright Chromium when running on Streamlit Cloud
os.system("playwright install chromium")

import database
import scraper
import generator

# Load Logo Image & convert to Base64
def get_logo_data():
    logo_path = os.path.join(os.path.dirname(__file__), "logo.png")
    if os.path.exists(logo_path):
        try:
            pil_img = Image.open(logo_path)
            with open(logo_path, "rb") as f:
                b64_str = base64.b64encode(f.read()).decode()
            return pil_img, f"data:image/png;base64,{b64_str}"
        except Exception:
            pass
    return "🚀", None

logo_img, logo_b64 = get_logo_data()

# Initialize page configuration
st.set_page_config(
    page_title="Accelerator Lead Gen - Lead Generator",
    page_icon=logo_img,
    layout="wide",
    initial_sidebar_state="expanded"
)

# JavaScript handler for WhatsApp Web tab reuse (via invisible iframe)
components.html("""
<script>
if (!window.parent.openWhatsApp) {
    window.parent.openWhatsApp = function(url) {
        if (window.parent.whatsappWindow && !window.parent.whatsappWindow.closed) {
            window.parent.whatsappWindow.location.href = url;
            try {
                window.parent.whatsappWindow.focus();
            } catch(e) {}
        } else {
            window.parent.whatsappWindow = window.open(url, 'whatsapp_tab');
        }
    };
    
    window.parent.document.addEventListener('click', function(e) {
        var target = e.target;
        while (target && target !== window.parent.document) {
            if (target.classList && target.classList.contains('whatsapp-action-btn')) {
                e.preventDefault();
                var url = target.getAttribute('data-whatsapp-url');
                if (url) {
                    window.parent.openWhatsApp(url);
                }
                break;
            }
            target = target.parentNode;
        }
    });
}
</script>
""", height=0)

# Custom Premium Styling
st.markdown("""
<style>
    /* Main Layout */
    .stApp {
        background-color: #0b0f19;
        color: #e2e8f0;
    }
    
    /* Headers & Text */
    h1, h2, h3, h4, h5 {
        font-family: 'Inter', -apple-system, sans-serif;
        font-weight: 700;
        color: #ffffff !important;
        letter-spacing: -0.02em;
    }
    .main-title {
        background: linear-gradient(135deg, #00e676 0%, #00b0ff 100%);
        -webkit-background-clip: text;
        -webkit-text-fill-color: transparent;
        font-size: 2.8rem;
        margin-bottom: 5px;
        font-weight: 800;
    }
    .subtitle {
        color: #94a3b8;
        font-size: 1.1rem;
        margin-bottom: 25px;
    }
    
    /* Sidebar */
    [data-testid="stSidebar"] {
        background-color: #0f172a;
        border-right: 1px solid #1e293b;
    }
    
    /* Cards and Containers */
    .lead-card {
        background: #1e293b;
        border-radius: 12px;
        padding: 22px;
        margin-bottom: 20px;
        border: 1px solid #334155;
        transition: transform 0.2s ease, border-color 0.2s ease;
    }
    .lead-card:hover {
        border-color: #00e676;
        transform: translateY(-2px);
    }
    .lead-title {
        font-size: 1.3rem;
        font-weight: 600;
        color: #00e676;
        margin-bottom: 4px;
    }
    .lead-meta {
        font-size: 0.9rem;
        color: #94a3b8;
        margin-bottom: 12px;
    }
    
    /* Metrics */
    div[data-testid="stMetricValue"] {
        font-size: 2.2rem;
        font-weight: 700;
        color: #ffffff;
    }
    
    /* WhatsApp Button Link */
    .whatsapp-btn {
        display: inline-flex;
        align-items: center;
        justify-content: center;
        background-color: #25D366;
        color: #ffffff !important;
        padding: 8px 18px;
        font-size: 0.95rem;
        font-weight: 600;
        border-radius: 8px;
        text-decoration: none;
        transition: background-color 0.2s ease;
        border: none;
        cursor: pointer;
        box-shadow: 0 4px 6px -1px rgba(37, 211, 102, 0.2);
    }
    .whatsapp-btn:hover {
        background-color: #1bd75e;
        text-decoration: none;
    }
    
    /* Logs styling */
    .log-box {
        background-color: #020617;
        border: 1px solid #1e293b;
        border-radius: 8px;
        padding: 15px;
        font-family: 'Courier New', Courier, monospace;
        color: #38bdf8;
    }
</style>
""", unsafe_allow_html=True)

# ----------------- SESSION STATE -----------------
if 'scraping_in_progress' not in st.session_state:
    st.session_state.scraping_in_progress = False

# ----------------- SIDEBAR -----------------------
with st.sidebar:
    if logo_b64:
        sidebar_logo_html = f"""
        <div style='text-align: center; padding: 10px 0;'>
            <img src='{logo_b64}' style='width: 90px; margin-bottom: 12px; filter: drop-shadow(0 0 8px rgba(0, 230, 118, 0.2));'>
            <h1 style='font-size: 1.45rem; margin-top: 0;'>Accelerator Lead Gen</h1>
            <p style='color: #64748b; font-size: 0.9rem; margin-top: -5px;'>Web & Marketing Lead Gen</p>
        </div>
        """
    else:
        sidebar_logo_html = "<div style='text-align: center; padding: 10px 0;'><h1>🚀 Accelerator Lead Gen</h1><p style='color: #64748b; font-size: 0.9rem;'>Web & Marketing Lead Gen</p></div>"
    st.markdown(sidebar_logo_html, unsafe_allow_html=True)
    st.markdown("---")
    
    # Load settings
    settings = database.get_all_settings()
    daily_limit = int(settings.get('daily_limit', 25))
    scraped_today = database.get_daily_scraped_count()
    
    # Daily Limit Metrics
    st.subheader("Daily Limits Tracker")
    col_a, col_b = st.columns(2)
    with col_a:
        st.metric("Scraped Today", f"{scraped_today}")
    with col_b:
        st.metric("Daily Limit", f"{daily_limit}")
        
    progress_val = min(1.0, scraped_today / daily_limit) if daily_limit > 0 else 0
    st.progress(progress_val)
    
    if scraped_today >= daily_limit:
        st.error("⚠️ Daily scraper limit reached. Increase limit in settings if needed.")
    else:
        st.info(f"You can scrape {daily_limit - scraped_today} more businesses today.")

    st.markdown("---")
    st.markdown("<p style='text-align: center; color: #475569; font-size: 0.8rem;'>Accelerator Lead Gen v1.0.0<br>Running Locally</p>", unsafe_allow_html=True)

# ----------------- MAIN PANEL --------------------
if logo_b64:
    main_title_html = f"""
    <div style='display: flex; align-items: center; gap: 16px; margin-bottom: 8px;'>
        <img src='{logo_b64}' style='width: 58px; height: 58px; filter: drop-shadow(0 0 10px rgba(0, 176, 255, 0.25));'>
        <h1 class='main-title' style='margin: 0; padding: 0;'>Accelerator Lead Gen</h1>
    </div>
    """
else:
    main_title_html = "<h1 class='main-title'>🚀 Accelerator Lead Gen</h1>"
st.markdown(main_title_html, unsafe_allow_html=True)
st.markdown("<div class='subtitle'>Find local businesses with no website and generate personalized outreach messages.</div>", unsafe_allow_html=True)

tab_scrape, tab_queue, tab_db, tab_settings = st.tabs([
    "🔍 Scrape Leads",
    "📋 Outreach Queue",
    "📊 Database & Export",
    "⚙️ Settings & Templates"
])

# ----------------- TAB 1: SCRAPE LEADS -----------
with tab_scrape:
    st.subheader("Scrape New Leads")
    
    col1, col2 = st.columns([2, 1])
    with col1:
        search_query = st.text_input(
            "Search Query",
            placeholder="e.g., restaurants in Lahore, dentists in Karachi, gyms in Islamabad",
            help="Type what business category and location you are targeting."
        )
    with col2:
        scrape_source = st.selectbox(
            "Scraping Source",
            ["Google Maps (Playwright)", "OpenStreetMap (Overpass API)"],
            help="Google Maps uses real browser simulation. OSM is direct API, faster but might have less phone numbers."
        )
        
    col3, col4 = st.columns(2)
    with col3:
        scrape_limit = st.slider(
            "Max results for this run",
            min_value=1,
            max_value=30,
            value=10,
            help="Limit this search execution results. Random delay (5-15s) applies between Google Maps items."
        )
    with col4:
        headless_mode = st.toggle(
            "Run browser in background (Headless)",
            value=(settings.get('playwright_headless', 'True') == 'True'),
            help="If disabled, you will see the Chrome browser window open and navigate (only for Google Maps)."
        )

    # Scrape Button Logic
    start_disabled = st.session_state.scraping_in_progress or (scraped_today >= daily_limit)
    
    if st.button("🚀 Run Today's Scrape", disabled=start_disabled, use_container_width=True):
        if not search_query:
            st.error("Please enter a search query.")
        else:
            st.session_state.scraping_in_progress = True
            
            # Create a log placeholder
            st.markdown("### Scraping Progress Logs")
            log_container = st.empty()
            logs = []
            
            def log_callback(msg):
                logs.append(msg)
                # Keep last 15 lines
                log_container.code("\n".join(logs[-15:]))
                
            try:
                if scrape_source == "Google Maps (Playwright)":
                    count = scraper.scrape_google_maps(
                        query=search_query,
                        limit=scrape_limit,
                        headless=headless_mode,
                        on_progress=log_callback
                    )
                else:
                    count = scraper.scrape_osm(
                        query=search_query,
                        limit=scrape_limit,
                        on_progress=log_callback
                    )
                
                if count > 0:
                    st.success(f"🎉 Scraping complete! Successfully imported {count} new leads without websites.")
                    time.sleep(2)
                    st.rerun()
                else:
                    st.info("Scraping finished. No new leads were saved (they may already exist in database or have websites).")
            except Exception as e:
                st.error(f"Scraper error occurred: {str(e)}")
            finally:
                st.session_state.scraping_in_progress = False
                st.rerun()

# ----------------- TAB 2: OUTREACH QUEUE ---------
with tab_queue:
    st.subheader("Business Leads Queue")
    
    # Filter Controls
    col_f1, col_f2 = st.columns([2, 1])
    with col_f1:
        search_kw = st.text_input("Search Leads Queue", placeholder="Search by name, address, or category...")
    with col_f2:
        status_filter = st.selectbox("Outreach Status", ["Unsent (New)", "Sent"])
        
    db_status = 'New' if status_filter == "Unsent (New)" else 'Sent'
    leads = database.get_leads(filter_no_website=True, message_status=db_status)
    
    # Filter matching keywords
    if search_kw:
        leads = [l for l in leads if (
            search_kw.lower() in l['name'].lower() or 
            (l['address'] and search_kw.lower() in l['address'].lower()) or
            (l['category'] and search_kw.lower() in l['category'].lower())
        )]
        
    st.markdown(f"Showing **{len(leads)}** leads with missing websites.")
    
    if not leads:
        st.info("No leads found in this view. Run a scrape or adjust filters!")
    else:
        for idx, lead in enumerate(leads):
            # Render custom lead card
            st.markdown(f"""
            <div class="lead-card">
                <div class="lead-title">{lead['name']}</div>
                <div class="lead-meta">
                    <b>Category:</b> {lead['category'] or 'N/A'} | 
                    <b>Address:</b> {lead['address'] or 'N/A'} | 
                    <b>Phone:</b> {lead['phone'] or 'N/A'} | 
                    <b>Scraped:</b> {lead['scraped_date']}
                </div>
            </div>
            """, unsafe_allow_html=True)
            
            # Setup columns inside the card for message generation & action
            col_m1, col_m2 = st.columns([3, 1])
            
            with col_m1:
                # Generate proposal text
                proposal = generator.get_proposal_for_lead(lead)
                
                # Editable proposal text area
                new_proposal = st.text_area(
                    "Outreach Proposal Message",
                    value=proposal,
                    key=f"prop_txt_{lead['id']}_{idx}",
                    height=180,
                    label_visibility="collapsed"
                )
                
                # Auto-update proposal in database on change
                if new_proposal != proposal:
                    database.update_custom_proposal(lead['id'], new_proposal)
                    
            with col_m2:
                # WhatsApp Action Link
                if lead['phone']:
                    # Clean phone number (keep digits only)
                    clean_phone = "".join([c for c in lead['phone'] if c.isdigit()])
                    
                    # Ensure country code is set correctly. Local PK formatting e.g. 0300... or +92
                    # IfPK number starts with 0, replace with 92
                    if clean_phone.startswith('0') and not clean_phone.startswith('00'):
                        clean_phone = '92' + clean_phone[1:]
                    
                    # Pre-fill URL query parameters
                    encoded_message = urllib.parse.quote(new_proposal)
                    whatsapp_web_url = f"https://web.whatsapp.com/send?phone={clean_phone}&text={encoded_message}"
                    whatsapp_app_url = f"whatsapp://send?phone={clean_phone}&text={encoded_message}"
                    
                    st.markdown(
                        f'<button data-whatsapp-url="{whatsapp_web_url}" class="whatsapp-btn whatsapp-action-btn" style="width:100%; margin-bottom:8px;">💬 WhatsApp Web</button>'
                        f'<a href="{whatsapp_app_url}" class="whatsapp-btn" style="width:100%; margin-bottom:10px; background-color: #075E54; box-shadow: 0 4px 6px -1px rgba(7, 94, 84, 0.2);">📱 WhatsApp Desktop</a>', 
                        unsafe_allow_html=True
                    )
                else:
                    st.warning("⚠️ No phone number")
                
                # Mark as Sent button
                if db_status == 'New':
                    if st.button("✅ Mark as Sent", key=f"btn_sent_{lead['id']}_{idx}", use_container_width=True):
                        database.update_lead_status(lead['id'], 'Sent')
                        st.success("Lead marked as sent!")
                        time.sleep(0.5)
                        st.rerun()
                else:
                    st.write(f"⏱️ Sent: {lead['sent_timestamp']}")
                    if st.button("↩️ Reset to New", key=f"btn_new_{lead['id']}_{idx}", use_container_width=True):
                        database.update_lead_status(lead['id'], 'New')
                        st.rerun()
                        
                # Delete lead button
                if st.button("🗑️ Delete Lead", key=f"btn_del_{lead['id']}_{idx}", use_container_width=True):
                    database.delete_lead(lead['id'])
                    st.warning("Lead deleted.")
                    time.sleep(0.5)
                    st.rerun()
            st.markdown("<hr style='border: 1px solid #1e293b; margin: 20px 0;'>", unsafe_allow_html=True)

# ----------------- TAB 3: DATABASE & EXPORT ------
with tab_db:
    st.subheader("Database Overview")
    
    raw_leads = database.get_all_raw_leads()
    
    if not raw_leads:
        st.info("No leads in the database yet. Run the scraper first.")
    else:
        df = pd.DataFrame(raw_leads)
        
        # Format display dataframe columns
        display_cols = ['id', 'name', 'phone', 'website', 'address', 'category', 'query', 'scraped_date', 'message_status', 'sent_timestamp']
        df_display = df[[c for c in display_cols if c in df.columns]]
        
        st.markdown(f"Total Leads in Database: **{len(df_display)}**")
        st.dataframe(df_display, use_container_width=True)
        
        # Exports
        col_ex1, col_ex2 = st.columns(2)
        with col_ex1:
            csv_data = df.to_csv(index=False).encode('utf-8')
            st.download_button(
                "📥 Export to CSV",
                data=csv_data,
                file_name="leads_data.csv",
                mime="text/csv",
                use_container_width=True
            )
        with col_ex2:
            # Excel export using temporary openpyxl writer
            import io
            buffer = io.BytesIO()
            with pd.ExcelWriter(buffer, engine='openpyxl') as writer:
                df.to_excel(writer, index=False, sheet_name='Leads')
            excel_data = buffer.getvalue()
            st.download_button(
                "📥 Export to Excel",
                data=excel_data,
                file_name="leads_data.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                use_container_width=True
            )
            
        # Supabase Cloud Sync Section
        st.markdown("---")
        st.subheader("☁️ Supabase Cloud Sync")
        supabase_configured = database.get_supabase_client() is not None
        if supabase_configured:
            st.success("Supabase credentials detected in `.env`. Cloud integration is active.")
            
            col_sync1, col_sync2 = st.columns([2, 1])
            with col_sync1:
                st.write("Mirroring is enabled: New leads are synced automatically. Use this button to upload all existing local leads.")
            with col_sync2:
                if st.button("🔄 Sync All SQLite Leads to Supabase", use_container_width=True):
                    leads = database.get_all_raw_leads()
                    sync_success_count = 0
                    with st.spinner("Syncing leads..."):
                        for lead in leads:
                            if database.sync_lead_to_supabase(lead):
                                sync_success_count += 1
                    if sync_success_count == len(leads):
                        st.success(f"Successfully synced all {sync_success_count} leads to Supabase!")
                    else:
                        st.warning(f"Synced {sync_success_count} of {len(leads)} leads. Check if the table exists on Supabase.")
            

        else:
            st.warning("Supabase sync is disabled. Add `SUPABASE_URL` and `SUPABASE_KEY` to the `.env` file to enable.")
            
        # Dangerous actions inside helper
        st.markdown("---")
        st.subheader("Database Maintenance")
        if st.checkbox("Show Advanced Maintenance Options"):
            st.warning("These operations cannot be undone!")
            if st.button("🔥 Delete ALL Leads in Database", type="secondary"):
                conn = database.get_db_connection()
                conn.execute("DELETE FROM leads")
                conn.commit()
                conn.close()
                st.success("All leads deleted successfully!")
                time.sleep(1)
                st.rerun()

# ----------------- TAB 4: SETTINGS --------------
with tab_settings:
    st.subheader("Configuration Settings")
    
    # Save settings trigger
    with st.form("settings_form"):
        col_s1, col_s2 = st.columns(2)
        with col_s1:
            form_limit = st.number_input(
                "Daily Scrape Limit",
                min_value=1,
                max_value=100,
                value=int(settings.get('daily_limit', 25)),
                help="Maximum number of leads you can scrape per day."
            )
            
            form_lang = st.selectbox(
                "Proposal Language",
                ["English", "Urdu"],
                index=0 if settings.get('proposal_language', 'English') == 'English' else 1,
                help="Default language for generated messages."
            )
            
            form_headless = st.toggle(
                "Playwright Headless Browser Mode",
                value=(settings.get('playwright_headless', 'True') == 'True'),
                help="Run Playwright Chromium browser invisibly in the background."
            )
            
        with col_s2:
            form_use_ai = st.toggle(
                "Enable AI-Generated Proposals",
                value=(settings.get('use_ai', 'False') == 'True'),
                help="Use Google Gemini or OpenAI to generate proposals instead of standard text templates."
            )
            
            form_provider = st.selectbox(
                "AI Provider",
                ["Gemini", "OpenAI"],
                index=0 if settings.get('ai_provider', 'Gemini') == 'Gemini' else 1
            )
            
            form_gemini_key = st.text_input(
                "Google Gemini API Key",
                value=settings.get('gemini_api_key', ''),
                type="password",
                placeholder="AIzaSy..."
            )
            
            form_openai_key = st.text_input(
                "OpenAI API Key",
                value=settings.get('openai_api_key', ''),
                type="password",
                placeholder="sk-..."
            )
            
        st.markdown("---")
        st.subheader("Cold Proposal Message Templates (Fallback Mode)")
        st.markdown("These templates are used when AI generation is disabled or fails. Placeholders available: `{name}`, `{category}`, `{location}`, `{phone}`, `{address}`")
        
        form_tpl_en = st.text_area(
            "English Template",
            value=settings.get('proposal_template', ''),
            height=150
        )
        
        form_tpl_ur = st.text_area(
            "Urdu Template",
            value=settings.get('proposal_template_urdu', ''),
            height=150
        )
        
        if st.form_submit_button("💾 Save All Settings", use_container_width=True):
            database.save_setting('daily_limit', form_limit)
            database.save_setting('proposal_language', form_lang)
            database.save_setting('playwright_headless', 'True' if form_headless else 'False')
            database.save_setting('use_ai', 'True' if form_use_ai else 'False')
            database.save_setting('ai_provider', form_provider)
            database.save_setting('gemini_api_key', form_gemini_key)
            database.save_setting('openai_api_key', form_openai_key)
            database.save_setting('proposal_template', form_tpl_en)
            database.save_setting('proposal_template_urdu', form_tpl_ur)
            
            st.success("Settings saved successfully!")
            time.sleep(1)
            st.rerun()
