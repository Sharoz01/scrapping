import os
import sqlite3
import hashlib
import secrets
from datetime import datetime, date

# Load env for local development
def load_env():
    env_path = os.path.join(os.path.dirname(__file__), ".env")
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

if os.environ.get("VERCEL") or os.environ.get("AWS_LAMBDA_FUNCTION_NAME"):
    DB_PATH = "/tmp/leads.db"
else:
    DB_PATH = os.path.join(os.path.dirname(__file__), "leads.db")
_supabase_client = None

def get_db_connection():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

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

# ==========================================
# AUTHENTICATION & PASSWORD HELPERS
# ==========================================
def hash_password(password: str, salt: str = None) -> tuple:
    if not salt:
        salt = secrets.token_hex(16)
    pw_hash = hashlib.pbkdf2_hmac(
        'sha256',
        password.encode('utf-8'),
        salt.encode('utf-8'),
        100000
    ).hex()
    return pw_hash, salt

def verify_password(password: str, stored_hash: str, salt: str) -> bool:
    pw_hash, _ = hash_password(password, salt)
    return secrets.compare_digest(pw_hash, stored_hash)

# ==========================================
# DATABASE INITIALIZATION
# ==========================================
def init_db():
    conn = get_db_connection()
    cursor = conn.cursor()

    # Settings table
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS settings (
            key TEXT PRIMARY KEY,
            value TEXT
        )
    """)

    # Users table
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT UNIQUE NOT NULL,
            password_hash TEXT NOT NULL,
            salt TEXT NOT NULL,
            full_name TEXT,
            role TEXT NOT NULL DEFAULT 'user',
            is_active INTEGER NOT NULL DEFAULT 1,
            created_at TEXT NOT NULL
        )
    """)

    # User activity table (tracks daily scrapes & outreach)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS user_activity (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            username TEXT,
            action_type TEXT NOT NULL,
            count INTEGER NOT NULL DEFAULT 1,
            details TEXT,
            created_at TEXT NOT NULL
        )
    """)

    # Leads table
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS leads (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT,
            address TEXT,
            phone TEXT,
            website TEXT,
            website_status TEXT,
            category TEXT,
            query TEXT,
            google_maps_url TEXT UNIQUE,
            scraped_date TEXT,
            message_status TEXT DEFAULT 'New',
            sent_timestamp TEXT,
            custom_proposal TEXT,
            email TEXT,
            user_id INTEGER,
            user_name TEXT
        )
    """)

    # Check and add missing columns to leads table if upgrading
    cursor.execute("PRAGMA table_info(leads)")
    existing_cols = [row[1] for row in cursor.fetchall()]
    for col_name, col_type in [
        ("website_status", "TEXT"),
        ("email", "TEXT"),
        ("user_id", "INTEGER"),
        ("user_name", "TEXT")
    ]:
        if col_name not in existing_cols:
            try:
                cursor.execute(f"ALTER TABLE leads ADD COLUMN {col_name} {col_type}")
            except Exception as e:
                print(f"Error adding column {col_name} to leads: {e}")

    conn.commit()

    # Seed default admin user if none exists
    cursor.execute("SELECT id FROM users WHERE role = 'admin' LIMIT 1")
    admin_exists = cursor.fetchone()
    if not admin_exists:
        pw_hash, salt = hash_password("admin123")
        now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        cursor.execute("""
            INSERT OR IGNORE INTO users (username, password_hash, salt, full_name, role, is_active, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        """, ("admin", pw_hash, salt, "Super Administrator", "admin", 1, now_str))
        conn.commit()
        print("Default admin created: username='admin', password='admin123'")

    conn.close()

# Initialize DB on module load
init_db()

# ==========================================
# USER MANAGEMENT FUNCTIONS
# ==========================================
def create_user(username: str, password: str, role: str = "user", full_name: str = ""):
    username = username.strip().lower()
    if not username or not password:
        raise ValueError("Username and password are required")
    if role not in ("admin", "user"):
        role = "user"
        
    pw_hash, salt = hash_password(password)
    now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    
    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        cursor.execute("""
            INSERT INTO users (username, password_hash, salt, full_name, role, is_active, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        """, (username, pw_hash, salt, full_name.strip() or username, role, 1, now_str))
        conn.commit()
        user_id = cursor.lastrowid
        return get_user_by_id(user_id)
    except sqlite3.IntegrityError:
        raise ValueError(f"Username '{username}' is already taken")
    finally:
        conn.close()

def authenticate_user(username: str, password: str):
    user = get_user_by_username(username)
    if not user:
        return None
    if not user.get("is_active"):
        return None
    if verify_password(password, user["password_hash"], user["salt"]):
        # Remove sensitive password details before returning
        user_clean = {k: v for k, v in user.items() if k not in ("password_hash", "salt")}
        return user_clean
    return None

def get_user_by_id(user_id: int):
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM users WHERE id = ?", (user_id,))
    row = cursor.fetchone()
    conn.close()
    if row:
        return dict(row)
    return None

def get_user_by_username(username: str):
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM users WHERE LOWER(username) = LOWER(?)", (username.strip(),))
    row = cursor.fetchone()
    conn.close()
    if row:
        return dict(row)
    return None

def list_users():
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT id, username, full_name, role, is_active, created_at FROM users ORDER BY id ASC")
    rows = cursor.fetchall()
    conn.close()
    return [dict(r) for r in rows]

def update_user(user_id: int, full_name: str = None, role: str = None, is_active: bool = None, password: str = None):
    conn = get_db_connection()
    cursor = conn.cursor()
    
    updates = []
    params = []
    
    if full_name is not None:
        updates.append("full_name = ?")
        params.append(full_name.strip())
    if role is not None and role in ("admin", "user"):
        updates.append("role = ?")
        params.append(role)
    if is_active is not None:
        updates.append("is_active = ?")
        params.append(1 if is_active else 0)
    if password is not None and password.strip():
        pw_hash, salt = hash_password(password.strip())
        updates.append("password_hash = ?")
        params.append(pw_hash)
        updates.append("salt = ?")
        params.append(salt)
        
    if not updates:
        conn.close()
        return get_user_by_id(user_id)
        
    params.append(user_id)
    query = f"UPDATE users SET {', '.join(updates)} WHERE id = ?"
    cursor.execute(query, params)
    conn.commit()
    conn.close()
    return get_user_by_id(user_id)

def delete_user(user_id: int):
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("DELETE FROM users WHERE id = ?", (user_id,))
    conn.commit()
    conn.close()
    return True

# ==========================================
# USER ACTIVITY & STATS TRACKING
# ==========================================
def record_user_activity(user_id: int, username: str, action_type: str, count: int = 1, details: str = ""):
    now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("""
        INSERT INTO user_activity (user_id, username, action_type, count, details, created_at)
        VALUES (?, ?, ?, ?, ?, ?)
    """, (user_id, username, action_type, count, details, now_str))
    conn.commit()
    conn.close()

def get_user_analytics():
    today_start = datetime.combine(date.today(), datetime.min.time()).strftime("%Y-%m-%d %H:%M:%S")
    conn = get_db_connection()
    cursor = conn.cursor()
    
    users = list_users()
    analytics = []
    
    total_scrapes_today = 0
    total_outreach_today = 0
    total_leads_all = 0
    
    for u in users:
        uid = u["id"]
        uname = u["username"]
        
        # Scrapes today for this user (from activity or leads created_at)
        cursor.execute("""
            SELECT COALESCE(SUM(count), 0) FROM user_activity 
            WHERE (user_id = ? OR LOWER(username) = LOWER(?)) 
            AND action_type = 'scrape' 
            AND created_at >= ?
        """, (uid, uname, today_start))
        scrapes_act = cursor.fetchone()[0]
        
        cursor.execute("""
            SELECT COUNT(id) FROM leads 
            WHERE (user_id = ? OR LOWER(user_name) = LOWER(?)) 
            AND scraped_date >= ?
        """, (uid, uname, today_start))
        scrapes_leads = cursor.fetchone()[0]
        scrapes_today = max(scrapes_act, scrapes_leads)
        
        # Outreach today for this user
        cursor.execute("""
            SELECT COALESCE(SUM(count), 0) FROM user_activity 
            WHERE (user_id = ? OR LOWER(username) = LOWER(?)) 
            AND action_type = 'outreach' 
            AND created_at >= ?
        """, (uid, uname, today_start))
        outreach_act = cursor.fetchone()[0]
        
        cursor.execute("""
            SELECT COUNT(id) FROM leads 
            WHERE (user_id = ? OR LOWER(user_name) = LOWER(?)) 
            AND message_status = 'Sent'
            AND sent_timestamp >= ?
        """, (uid, uname, today_start))
        outreach_leads = cursor.fetchone()[0]
        outreach_today = max(outreach_act, outreach_leads)
        
        # Total leads owned/scraped by user
        cursor.execute("""
            SELECT COUNT(id) FROM leads 
            WHERE user_id = ? OR LOWER(user_name) = LOWER(?)
        """, (uid, uname))
        user_total_leads = cursor.fetchone()[0]

        # Total outreach by user
        cursor.execute("""
            SELECT COUNT(id) FROM leads 
            WHERE (user_id = ? OR LOWER(user_name) = LOWER(?)) 
            AND message_status = 'Sent'
        """, (uid, uname))
        user_total_outreach = cursor.fetchone()[0]

        analytics.append({
            "id": uid,
            "username": uname,
            "full_name": u.get("full_name") or uname,
            "role": u.get("role", "user"),
            "is_active": bool(u.get("is_active", 1)),
            "scrapes_today": scrapes_today,
            "outreach_today": outreach_today,
            "total_leads": user_total_leads,
            "total_outreach": user_total_outreach,
            "created_at": u.get("created_at")
        })

    # Dynamically query true database totals
    cursor.execute("SELECT COUNT(id) FROM leads")
    total_leads_all = cursor.fetchone()[0]

    cursor.execute("""
        SELECT COUNT(id) FROM leads 
        WHERE scraped_date >= ?
    """, (today_start,))
    db_scrapes_today = cursor.fetchone()[0]
    cursor.execute("""
        SELECT COALESCE(SUM(count), 0) FROM user_activity
        WHERE action_type = 'scrape' AND created_at >= ?
    """, (today_start,))
    act_scrapes_today = cursor.fetchone()[0]
    total_scrapes_today = max(db_scrapes_today, act_scrapes_today)

    cursor.execute("""
        SELECT COUNT(id) FROM leads 
        WHERE message_status = 'Sent' AND sent_timestamp >= ?
    """, (today_start,))
    db_outreach_today = cursor.fetchone()[0]
    cursor.execute("""
        SELECT COALESCE(SUM(count), 0) FROM user_activity
        WHERE action_type = 'outreach' AND created_at >= ?
    """, (today_start,))
    act_outreach_today = cursor.fetchone()[0]
    total_outreach_today = max(db_outreach_today, act_outreach_today)

    cursor.execute("SELECT COUNT(id) FROM users WHERE is_active = 1")
    total_users_active = cursor.fetchone()[0]
        
    conn.close()
    
    return {
        "users": analytics,
        "totals": {
            "scrapes_today": total_scrapes_today,
            "outreach_today": total_outreach_today,
            "total_leads": total_leads_all,
            "total_users": total_users_active or len(users)
        }
    }

# ==========================================
# SETTINGS
# ==========================================
def get_setting(key, default=None):
    supabase = get_supabase_client()
    if supabase:
        try:
            result = supabase.table("settings").select("value").eq("key", key).execute()
            if result.data:
                return result.data[0]['value']
        except:
            pass
            
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT value FROM settings WHERE key = ?", (key,))
    row = cursor.fetchone()
    conn.close()
    if row:
        return row[0]
    return default

def save_setting(key, value):
    # Save to local SQLite
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("INSERT OR REPLACE INTO settings (key, value) VALUES (?, ?)", (key, str(value)))
    conn.commit()
    conn.close()
    
    # Save to Supabase if configured
    supabase = get_supabase_client()
    if supabase:
        try:
            supabase.table("settings").upsert({"key": key, "value": str(value)}).execute()
        except Exception as e:
            print(f"Save setting to Supabase error: {e}")

def get_all_settings():
    settings_dict = {}
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT key, value FROM settings")
    for row in cursor.fetchall():
        settings_dict[row[0]] = row[1]
    conn.close()
    
    supabase = get_supabase_client()
    if supabase:
        try:
            result = supabase.table("settings").select("*").execute()
            for row in (result.data or []):
                settings_dict[row['key']] = row['value']
        except:
            pass
    return settings_dict

# ==========================================
# LEADS OPERATIONS (WITH USER ATTRIBUTION)
# ==========================================
def format_lead_row(row):
    if not row:
        return row
    if isinstance(row, sqlite3.Row):
        row = dict(row)
    if not row.get("email") and row.get("custom_proposal") and "[EMAIL:" in str(row.get("custom_proposal", "")):
        try:
            em = row["custom_proposal"].split("[EMAIL:")[1].split("]")[0].strip()
            row["email"] = em
        except Exception:
            pass
            
    if not row.get("website_status"):
        w = row.get("website")
        if not w or str(w).strip().lower() in ('none', 'null', ''):
            row["website_status"] = "No Website"
        else:
            row["website_status"] = "Responsive Website"
            
    return row

def insert_lead(name, address, phone, website, category, query, google_maps_url=None, email=None, website_status=None, user_id=None, user_name=None):
    if not website_status:
        if not website or str(website).strip().lower() in ('none', 'null', ''):
            website_status = "No Website"
        else:
            website_status = "Responsive Website"
            
    now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    # 1. Insert/Upsert into SQLite
    conn = get_db_connection()
    cursor = conn.cursor()
    inserted_id = None
    try:
        cursor.execute("""
            INSERT INTO leads (name, address, phone, website, website_status, category, query, google_maps_url, scraped_date, message_status, custom_proposal, email, user_id, user_name)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 'New', NULL, ?, ?, ?)
            ON CONFLICT(google_maps_url) DO UPDATE SET
                name=excluded.name,
                address=excluded.address,
                phone=excluded.phone,
                website=excluded.website,
                website_status=excluded.website_status,
                category=excluded.category,
                query=excluded.query,
                email=COALESCE(excluded.email, leads.email),
                user_id=COALESCE(excluded.user_id, leads.user_id),
                user_name=COALESCE(excluded.user_name, leads.user_name)
        """, (name, address, phone, website, website_status, category, query, google_maps_url, now_str, email, user_id, user_name))
        conn.commit()
        inserted_id = cursor.lastrowid
    except Exception as e:
        print(f"SQLite insert lead error: {e}")
    finally:
        conn.close()

    # 2. Sync to Supabase if available
    supabase = get_supabase_client()
    if supabase:
        try:
            data = {
                "name": name,
                "address": address,
                "phone": phone,
                "website": website,
                "website_status": website_status,
                "category": category,
                "query": query,
                "google_maps_url": google_maps_url,
                "message_status": "New",
                "sent_timestamp": None,
                "custom_proposal": None,
                "email": email
            }
            res = supabase.table("leads").upsert(data, on_conflict="google_maps_url").execute()
            if res.data:
                return format_lead_row(res.data[0])
        except Exception as e:
            err_msg = str(e).lower()
            try:
                data_fallback = data.copy()
                if "website_status" in err_msg or "column" in err_msg:
                    data_fallback.pop("website_status", None)
                if "email" in err_msg or "column" in err_msg:
                    data_fallback.pop("email", None)
                    if email:
                        data_fallback["custom_proposal"] = f"[EMAIL: {email}]"
                res = supabase.table("leads").upsert(data_fallback, on_conflict="google_maps_url").execute()
                if res.data:
                    row = res.data[0]
                    row["email"] = email or row.get("email")
                    row["website_status"] = website_status
                    row["user_id"] = user_id
                    row["user_name"] = user_name
                    return format_lead_row(row)
            except Exception as retry_err:
                print(f"Supabase retry error: {retry_err}")

    # Fallback return SQLite row
    return {
        "id": inserted_id,
        "name": name,
        "address": address,
        "phone": phone,
        "website": website,
        "website_status": website_status,
        "category": category,
        "query": query,
        "google_maps_url": google_maps_url,
        "scraped_date": now_str,
        "message_status": "New",
        "custom_proposal": None,
        "email": email,
        "user_id": user_id,
        "user_name": user_name
    }

def lead_exists(name, address):
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT id FROM leads WHERE name = ? AND address = ?", (name, address))
    found = cursor.fetchone() is not None
    conn.close()
    if found:
        return True
        
    supabase = get_supabase_client()
    if supabase:
        try:
            result = supabase.table("leads").select("id").eq("name", name).eq("address", address).execute()
            return len(result.data) > 0
        except:
            pass
    return False

def url_exists(url):
    if not url:
        return False
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT id FROM leads WHERE google_maps_url = ?", (url,))
    found = cursor.fetchone() is not None
    conn.close()
    if found:
        return True
        
    supabase = get_supabase_client()
    if supabase:
        try:
            result = supabase.table("leads").select("id").eq("google_maps_url", url).execute()
            return len(result.data) > 0
        except:
            pass
    return False

def update_lead_email(lead_id, email):
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("UPDATE leads SET email = ? WHERE id = ?", (email, lead_id))
    conn.commit()
    conn.close()
    
    supabase = get_supabase_client()
    if supabase:
        try:
            supabase.table("leads").update({"email": email}).eq("id", lead_id).execute()
        except:
            pass
    return True

def get_leads(filter_type="all_target", message_status=None, filter_no_website=None, user_id=None):
    # Fetch from local SQLite or Supabase
    conn = get_db_connection()
    cursor = conn.cursor()
    
    query = "SELECT * FROM leads WHERE 1=1"
    params = []
    
    if user_id is not None:
        query += " AND user_id = ?"
        params.append(user_id)
        
    if message_status:
        query += " AND message_status = ?"
        params.append(message_status)
        
    if filter_no_website is True or filter_type == "no_website":
        query += " AND (website IS NULL OR website = '' OR LOWER(website) = 'none')"
    elif filter_type == "unresponsive":
        query += " AND website_status = 'Unresponsive Website'"
        
    query += " ORDER BY scraped_date DESC, id DESC"
    
    cursor.execute(query, params)
    rows = [format_lead_row(r) for r in cursor.fetchall()]
    conn.close()
    
    # Filter according to filter_type
    if filter_type == "all_target":
        filtered = [
            r for r in rows
            if not r.get("website") or str(r.get("website")).strip().lower() in ('none', 'null', '') or r.get("website_status") in ("No Website", "Unresponsive Website", "Outdated Website")
        ]
        return filtered
    return rows

def sync_leads_from_supabase():
    sb = get_supabase_client()
    if not sb:
        return
    try:
        res = sb.table("leads").select("*").execute()
        if res.data:
            conn = get_db_connection()
            cursor = conn.cursor()
            for r in res.data:
                g_url = r.get("google_maps_url")
                if not g_url:
                    continue
                cursor.execute("""
                    INSERT INTO leads (name, address, phone, website, website_status, category, query, google_maps_url, scraped_date, message_status, sent_timestamp, custom_proposal, email, user_id, user_name)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    ON CONFLICT(google_maps_url) DO UPDATE SET
                        name=COALESCE(excluded.name, leads.name),
                        address=COALESCE(excluded.address, leads.address),
                        phone=COALESCE(excluded.phone, leads.phone),
                        website=COALESCE(excluded.website, leads.website),
                        website_status=COALESCE(excluded.website_status, leads.website_status),
                        category=COALESCE(excluded.category, leads.category),
                        query=COALESCE(excluded.query, leads.query),
                        message_status=COALESCE(excluded.message_status, leads.message_status),
                        sent_timestamp=COALESCE(excluded.sent_timestamp, leads.sent_timestamp),
                        email=COALESCE(excluded.email, leads.email)
                """, (
                    r.get("name"), r.get("address"), r.get("phone"), r.get("website"),
                    r.get("website_status") or ("No Website" if not r.get("website") else "Responsive Website"),
                    r.get("category"), r.get("query"), g_url,
                    r.get("scraped_date") or datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                    r.get("message_status") or "New", r.get("sent_timestamp"),
                    r.get("custom_proposal"), r.get("email"),
                    r.get("user_id"), r.get("user_name")
                ))
            conn.commit()
            conn.close()
            print(f"Synced {len(res.data)} leads from Supabase into local database.")
    except Exception as e:
        print(f"Sync error from Supabase: {e}")

def get_all_raw_leads(user_id=None):
    # Try local SQLite first (which has full records)
    conn = get_db_connection()
    cursor = conn.cursor()
    if user_id is not None:
        cursor.execute("SELECT * FROM leads WHERE user_id = ? ORDER BY scraped_date DESC, id DESC", (user_id,))
    else:
        cursor.execute("SELECT * FROM leads ORDER BY scraped_date DESC, id DESC")
    rows = [format_lead_row(r) for r in cursor.fetchall()]
    conn.close()
    
    # If SQLite has rows, return them
    if rows:
        return rows
        
    # Supabase fetch & fallback
    supabase = get_supabase_client()
    if supabase:
        try:
            sb_query = supabase.table("leads").select("*")
            if user_id is not None:
                sb_query = sb_query.eq("user_id", user_id)
            result = sb_query.order("scraped_date", desc=True).execute()
            sb_rows = [format_lead_row(r) for r in (result.data or [])]
            if sb_rows:
                return sb_rows
        except Exception as e:
            print(f"Supabase get all raw leads error: {e}")
            
    return rows or []


def update_lead_status(lead_id, status, user_id=None, username=None):
    now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    sent_time = now_str if status == 'Sent' else None
    
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("""
        UPDATE leads SET message_status = ?, sent_timestamp = ? WHERE id = ?
    """, (status, sent_time, lead_id))
    conn.commit()
    conn.close()
    
    supabase = get_supabase_client()
    if supabase:
        try:
            supabase.table("leads").update({
                "message_status": status,
                "sent_timestamp": sent_time
            }).eq("id", lead_id).execute()
        except Exception as e:
            print(f"Supabase update status error: {e}")
            
    if status == 'Sent' and user_id:
        record_user_activity(user_id, username or f"User-{user_id}", "outreach", 1, f"Sent outreach for lead #{lead_id}")

def update_custom_proposal(lead_id, proposal):
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("UPDATE leads SET custom_proposal = ? WHERE id = ?", (proposal, lead_id))
    conn.commit()
    conn.close()
    
    supabase = get_supabase_client()
    if supabase:
        try:
            supabase.table("leads").update({"custom_proposal": proposal}).eq("id", lead_id).execute()
        except Exception as e:
            print(f"Update proposal error: {e}")

def get_daily_scraped_count(user_id=None):
    today_start = datetime.combine(date.today(), datetime.min.time()).strftime("%Y-%m-%d %H:%M:%S")
    conn = get_db_connection()
    cursor = conn.cursor()
    if user_id is not None:
        cursor.execute("SELECT COUNT(id) FROM leads WHERE user_id = ? AND scraped_date >= ?", (user_id, today_start))
    else:
        cursor.execute("SELECT COUNT(id) FROM leads WHERE scraped_date >= ?", (today_start,))
    count = cursor.fetchone()[0]
    conn.close()
    return count or 0

def trigger_limit_timer():
    from datetime import timedelta
    end_time = datetime.now() + timedelta(hours=12)
    save_setting('limit_timer_end', end_time.isoformat())

def delete_lead(lead_id):
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("DELETE FROM leads WHERE id = ?", (lead_id,))
    conn.commit()
    conn.close()
    
    supabase = get_supabase_client()
    if supabase:
        try:
            supabase.table("leads").delete().eq("id", lead_id).execute()
        except Exception as e:
            print(f"Delete lead error: {e}")

