import os
from datetime import datetime

# Load env for local development
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

load_env()

# Try streamlit secrets
try:
    import streamlit as st
    if hasattr(st, 'secrets'):
        for k, v in st.secrets.items():
            if k not in os.environ:
                os.environ[k] = str(v)
except:
    pass

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
        from supabase import create_client
        _supabase_client = create_client(url, key)
        return _supabase_client
    except Exception as e:
        print(f"Supabase init error: {e}")
        return None

def get_setting(key, default=None):
    supabase = get_supabase_client()
    if not supabase:
        return default
    try:
        result = supabase.table("settings").select("value").eq("key", key).execute()
        if result.data:
            return result.data[0]['value']
    except:
        pass
    return default

def save_setting(key, value):
    supabase = get_supabase_client()
    if not supabase:
        return
    try:
        supabase.table("settings").upsert({"key": key, "value": str(value)}).execute()
    except Exception as e:
        print(f"Save setting error: {e}")

def get_all_settings():
    supabase = get_supabase_client()
    if not supabase:
        return {}
    try:
        result = supabase.table("settings").select("*").execute()
        return {row['key']: row['value'] for row in result.data}
    except:
        return {}

def insert_lead(name, address, phone, website, category, query, google_maps_url=None):
    if website:
        cleaned = website.strip().lower()
        if cleaned not in ('none', 'null', ''):
            return None
    # Phone requirement removed for OSM

    supabase = get_supabase_client()
    if not supabase:
        return None
    try:
        data = {
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
        result = supabase.table("leads").upsert(data, on_conflict="google_maps_url").execute()
        if result.data:
            return result.data[0].get('id')
    except Exception as e:
        print(f"Insert lead error: {e}")
    return None

def lead_exists(name, address):
    supabase = get_supabase_client()
    if not supabase:
        return False
    try:
        result = supabase.table("leads").select("id").eq("name", name).eq("address", address).execute()
        return len(result.data) > 0
    except:
        return False

def url_exists(url):
    if not url:
        return False
    supabase = get_supabase_client()
    if not supabase:
        return False
    try:
        result = supabase.table("leads").select("id").eq("google_maps_url", url).execute()
        return len(result.data) > 0
    except:
        return False

def get_leads(filter_no_website=True, message_status=None):
    supabase = get_supabase_client()
    if not supabase:
        return []
    try:
        query = supabase.table("leads").select("*")
        if filter_no_website:
            query = query.is_("website", "null")
        if message_status:
            query = query.eq("message_status", message_status)
        result = query.order("scraped_date", desc=True).execute()
        return result.data
    except Exception as e:
        print(f"Get leads error: {e}")
        return []

def get_all_raw_leads():
    supabase = get_supabase_client()
    if not supabase:
        return []
    try:
        result = supabase.table("leads").select("*").order("scraped_date", desc=True).execute()
        return result.data
    except:
        return []

def update_lead_status(lead_id, status):
    supabase = get_supabase_client()
    if not supabase:
        return
    try:
        now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        supabase.table("leads").update({
            "message_status": status,
            "sent_timestamp": now_str if status == 'Sent' else None
        }).eq("id", lead_id).execute()
    except Exception as e:
        print(f"Update status error: {e}")

def update_custom_proposal(lead_id, proposal):
    supabase = get_supabase_client()
    if not supabase:
        return
    try:
        supabase.table("leads").update({"custom_proposal": proposal}).eq("id", lead_id).execute()
    except Exception as e:
        print(f"Update proposal error: {e}")

def get_daily_scraped_count():
    today_start = datetime.combine(datetime.today(), datetime.min.time()).isoformat()
    supabase = get_supabase_client()
    if not supabase:
        return 0
    try:
        result = supabase.table("leads").select("id", count="exact").gte("scraped_date", today_start).execute()
        return result.count or 0
    except:
        return 0

def trigger_limit_timer():
    from datetime import timedelta
    end_time = datetime.now() + timedelta(hours=12)
    save_setting('limit_timer_end', end_time.isoformat())

def delete_lead(lead_id):
    supabase = get_supabase_client()
    if not supabase:
        return
    try:
        supabase.table("leads").delete().eq("id", lead_id).execute()
    except Exception as e:
        print(f"Delete lead error: {e}")

def init_db():
    pass
