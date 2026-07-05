import sqlite3
from datetime import datetime
import os

DB_PATH = "/Users/hf/Documents/scrapping/leads.db"

def load_env():
    env_path = "/Users/hf/Documents/scrapping/.env"
    if os.path.exists(env_path):
        with open(env_path, 'r') as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith('#') and '=' in line:
                    key, val = line.split('=', 1)
                    val = val.strip().strip("'").strip('"')
                    os.environ[key.strip()] = val

# Load env variables
load_env()

_supabase_client = None

def get_supabase_client():
    global _supabase_client
    if _supabase_client is not None:
        return _supabase_client
    url = os.getenv("SUPABASE_URL")
    key = os.getenv("SUPABASE_KEY")
    if not url or not key:
        return None
    try:
        from supabase import create_client  # type: ignore
        _supabase_client = create_client(url, key)
        return _supabase_client
    except Exception as e:
        print(f"Failed to initialize Supabase client: {e}")
        return None

def sync_lead_to_supabase(lead_data):
    if not lead_data or not lead_data.get('google_maps_url'):
        return False
    supabase = get_supabase_client()
    if not supabase:
        return False
    try:
        data = {
            "name": lead_data.get('name'),
            "address": lead_data.get('address'),
            "phone": lead_data.get('phone'),
            "website": lead_data.get('website'),
            "category": lead_data.get('category'),
            "query": lead_data.get('query'),
            "google_maps_url": lead_data.get('google_maps_url'),
            "message_status": lead_data.get('message_status', 'New'),
            "sent_timestamp": lead_data.get('sent_timestamp'),
            "custom_proposal": lead_data.get('custom_proposal')
        }
        # Upsert by google_maps_url to avoid duplicates
        supabase.table("leads").upsert(data, on_conflict="google_maps_url").execute()
        return True
    except Exception as e:
        print(f"Supabase sync error: {e}")
        return False

def delete_lead_from_supabase(google_maps_url):
    if not google_maps_url:
        return False
    supabase = get_supabase_client()
    if not supabase:
        return False
    try:
        supabase.table("leads").delete().eq("google_maps_url", google_maps_url).execute()
        return True
    except Exception as e:
        print(f"Supabase delete error: {e}")
        return False


def get_db_connection():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    conn = get_db_connection()
    cursor = conn.cursor()
    
    # Create leads table
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS leads (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT NOT NULL,
        address TEXT,
        phone TEXT,
        website TEXT,
        category TEXT,
        query TEXT,
        google_maps_url TEXT UNIQUE,
        scraped_date TEXT DEFAULT (datetime('now', 'localtime')),
        message_status TEXT DEFAULT 'New',
        sent_timestamp TEXT,
        custom_proposal TEXT,
        UNIQUE(name, address)
    )
    """)
    
    # Create settings table
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS settings (
        key TEXT PRIMARY KEY,
        value TEXT
    )
    """)
    
    # Insert default settings if not exists
    default_settings = {
        'daily_limit': '25',
        'proposal_template': "Hi {name},\n\nWe noticed your business, {name}, is doing great in {location}! However, we couldn't find a website for your business. In today's digital world, having an online presence can help you attract more customers.\n\nWe specialize in building clean, modern, and mobile-friendly websites for local businesses like yours. Would you be open to a quick chat this week to discuss how we can help grow your business?\n\nBest regards,\nAccelerator Technologies",
        'proposal_template_urdu': "السلام علیکم {name}،\n\nہم نے دیکھا کہ آپ کا کاروبار، {name}، بہت اچھا چل رہا ہے! لیکن انٹرنیٹ پر آپ کی کوئی ویب سائٹ نہیں ملی۔ آج کل کے دور میں ویب سائٹ ہونے سے آپ مزید گاہک حاصل کر سکتے ہیں۔\n\nہم مقامی کاروباروں کے لیے خوبصورت اور آسان ویب سائٹس بنانے کا کام کرتے ہیں۔ کیا آپ اس سلسلے میں بات کرنے کے لیے دستیاب ہیں؟\n\nشکریہ،\nایکسلیریٹر ٹیکنالوجیز",
        'gemini_api_key': '',
        'openai_api_key': '',
        'ai_provider': 'Gemini',
        'use_ai': 'False',
        'proposal_language': 'English',
        'playwright_headless': 'True',
        'last_reset_timestamp': '',
        'limit_timer_end': ''
    }
    
    for key, value in default_settings.items():
        cursor.execute("INSERT OR IGNORE INTO settings (key, value) VALUES (?, ?)", (key, value))
        
    conn.commit()
    conn.close()

def get_setting(key, default=None):
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT value FROM settings WHERE key = ?", (key,))
    row = cursor.fetchone()
    conn.close()
    if row:
        return row['value']
    return default

def save_setting(key, value):
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("INSERT OR REPLACE INTO settings (key, value) VALUES (?, ?)", (key, str(value)))
    conn.commit()
    conn.close()

def get_all_settings():
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT key, value FROM settings")
    rows = cursor.fetchall()
    conn.close()
    return {row['key']: row['value'] for row in rows}

def insert_lead(name, address, phone, website, category, query, google_maps_url=None):
    # Enforce quality filters: Must NOT have a website AND must HAVE a phone number
    if website:
        cleaned_website = website.strip().lower()
        if cleaned_website not in ('none', 'null', ''):
            return None
            
    if not phone or phone.strip().lower() in ('none', 'null', '', 'n/a'):
        return None

    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        # Standardize empty website to None/Empty string
        if website:
            website = website.strip()
            if website.lower() in ('none', 'null', ''):
                website = None
        else:
            website = None
            
        cursor.execute("""
        INSERT INTO leads (name, address, phone, website, category, query, google_maps_url)
        VALUES (?, ?, ?, ?, ?, ?, ?)
        """, (name, address, phone, website, category, query, google_maps_url))
        conn.commit()
        lead_id = cursor.lastrowid
        conn.close()
        
        # Mirror to Supabase in the background
        lead_data = {
            "name": name,
            "address": address,
            "phone": phone,
            "website": website,
            "category": category,
            "query": query,
            "google_maps_url": google_maps_url,
            "message_status": "New",
            "sent_timestamp": None,
            "custom_proposal": None
        }
        sync_lead_to_supabase(lead_data)
        
        return lead_id
    except sqlite3.IntegrityError:
        # Duplicate lead based on (name, address) or google_maps_url
        conn.close()
        return None

def lead_exists(name, address):
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT id FROM leads WHERE name = ? AND address = ?", (name, address))
    row = cursor.fetchone()
    conn.close()
    return row is not None

def url_exists(url):
    if not url:
        return False
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT id FROM leads WHERE google_maps_url = ?", (url,))
    row = cursor.fetchone()
    conn.close()
    return row is not None

def get_leads(filter_no_website=True, message_status=None):
    conn = get_db_connection()
    cursor = conn.cursor()
    
    query_str = "SELECT * FROM leads WHERE 1=1"
    params = []
    
    if filter_no_website:
        query_str += " AND (website IS NULL OR website = '' OR LOWER(website) = 'none')"
        query_str += " AND (phone IS NOT NULL AND phone != '' AND LOWER(phone) != 'none')"
        
    if message_status:
        query_str += " AND message_status = ?"
        params.append(message_status)
        
    query_str += " ORDER BY scraped_date DESC"
    
    cursor.execute(query_str, params)
    rows = cursor.fetchall()
    conn.close()
    return [dict(row) for row in rows]

def get_all_raw_leads():
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM leads ORDER BY scraped_date DESC")
    rows = cursor.fetchall()
    conn.close()
    return [dict(row) for row in rows]

def update_lead_status(lead_id, status):
    conn = get_db_connection()
    cursor = conn.cursor()
    now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    cursor.execute("""
    UPDATE leads 
    SET message_status = ?, sent_timestamp = ? 
    WHERE id = ?
    """, (status, now_str if status == 'Sent' else None, lead_id))
    conn.commit()
    
    # Sync updated lead to Supabase
    cursor.execute("SELECT * FROM leads WHERE id = ?", (lead_id,))
    row = cursor.fetchone()
    conn.close()
    if row:
        sync_lead_to_supabase(dict(row))

def update_custom_proposal(lead_id, proposal):
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("""
    UPDATE leads 
    SET custom_proposal = ? 
    WHERE id = ?
    """, (proposal, lead_id))
    conn.commit()
    
    # Sync updated lead to Supabase
    cursor.execute("SELECT * FROM leads WHERE id = ?", (lead_id,))
    row = cursor.fetchone()
    conn.close()
    if row:
        sync_lead_to_supabase(dict(row))

def get_daily_scraped_count():
    from datetime import datetime
    
    # Check if timer has expired
    timer_end_str = get_setting('limit_timer_end', '')
    if timer_end_str:
        try:
            end_time = datetime.fromisoformat(timer_end_str)
            if datetime.now() >= end_time:
                # Timer finished! Reset the cycle
                save_setting('last_reset_timestamp', datetime.now().isoformat())
                save_setting('limit_timer_end', '')
        except ValueError:
            pass
            
    last_reset = get_setting('last_reset_timestamp', '')
    if not last_reset:
        # initialize it
        last_reset = datetime.now().isoformat()
        save_setting('last_reset_timestamp', last_reset)

    conn = get_db_connection()
    cursor = conn.cursor()
    # count leads scraped after last_reset
    cursor.execute("""
    SELECT COUNT(*) FROM leads 
    WHERE datetime(scraped_date) >= datetime(?)
    """, (last_reset,))
    count = cursor.fetchone()[0]
    conn.close()
    return count

def trigger_limit_timer():
    from datetime import datetime, timedelta
    end_time = datetime.now() + timedelta(hours=12)
    save_setting('limit_timer_end', end_time.isoformat())

def delete_lead(lead_id):
    conn = get_db_connection()
    cursor = conn.cursor()
    
    # Get maps URL to delete from Supabase
    cursor.execute("SELECT google_maps_url FROM leads WHERE id = ?", (lead_id,))
    row = cursor.fetchone()
    google_maps_url = row['google_maps_url'] if row else None
    
    cursor.execute("DELETE FROM leads WHERE id = ?", (lead_id,))
    conn.commit()
    conn.close()
    
    if google_maps_url:
        delete_lead_from_supabase(google_maps_url)

# Initialize DB on import if file does not exist
if not os.path.exists(DB_PATH):
    init_db()
