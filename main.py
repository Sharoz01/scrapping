import os
import queue
import threading
import concurrent.futures
import urllib.parse
import jwt
from datetime import datetime, timedelta, timezone
from fastapi import FastAPI, HTTPException, BackgroundTasks, Query, Header, Depends
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from typing import Optional, List

import database
import scraper
import generator

app = FastAPI(title="Lead Gen API")
thread_pool = concurrent.futures.ThreadPoolExecutor(max_workers=4)

from fastapi.middleware.cors import CORSMiddleware

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.get("/")
def root():
    return {
        "status": "online",
        "message": "LeadForge AI Backend API is running successfully 🚀",
        "docs": "/docs"
    }

@app.get("/api/health")
def health_check():
    return {"status": "healthy", "timestamp": datetime.now(timezone.utc).isoformat()}

# Initialize database
database.init_db()

JWT_SECRET = os.getenv("JWT_SECRET", "leadforge-secret-key-2026-auth-jwt-token")
JWT_ALGORITHM = "HS256"
JWT_EXPIRATION_DAYS = 30

def create_access_token(data: dict) -> str:
    to_encode = data.copy()
    expire = datetime.now(timezone.utc) + timedelta(days=JWT_EXPIRATION_DAYS)
    to_encode.update({"exp": expire})
    return jwt.encode(to_encode, JWT_SECRET, algorithm=JWT_ALGORITHM)

def get_current_user_optional(authorization: Optional[str] = Header(None)) -> Optional[dict]:
    if not authorization:
        return None
    token = authorization.replace("Bearer ", "").strip()
    if not token:
        return None
    try:
        payload = jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALGORITHM])
        user_id = payload.get("id")
        if not user_id:
            return None
        user = database.get_user_by_id(user_id)
        if not user or not user.get("is_active"):
            return None
        return {k: v for k, v in user.items() if k not in ("password_hash", "salt")}
    except Exception:
        return None

def get_current_user(authorization: Optional[str] = Header(None)) -> dict:
    user = get_current_user_optional(authorization)
    if not user:
        raise HTTPException(status_code=401, detail="Authentication required. Please log in.")
    return user

def get_current_admin(authorization: Optional[str] = Header(None)) -> dict:
    user = get_current_user(authorization)
    if user.get("role") != "admin":
        raise HTTPException(status_code=403, detail="Admin privileges required.")
    return user

# Pydantic Request Models
class LoginRequest(BaseModel):
    username: str
    password: str

class CreateUserRequest(BaseModel):
    username: str
    password: str
    role: str = "user"
    full_name: Optional[str] = ""

class UpdateUserRequest(BaseModel):
    full_name: Optional[str] = None
    role: Optional[str] = None
    is_active: Optional[bool] = None
    password: Optional[str] = None

class LeadStatusUpdate(BaseModel):
    status: str

class LeadProposalUpdate(BaseModel):
    proposal: str

class SettingsUpdate(BaseModel):
    daily_limit: int
    proposal_language: str
    playwright_headless: bool
    use_ai: bool
    ai_provider: str
    gemini_api_key: str
    openai_api_key: str
    proposal_template: str
    proposal_template_urdu: str

class ScrapeRequest(BaseModel):
    query: str
    limit: int
    source: Optional[str] = "auto"

# ==========================================
# AUTHENTICATION ENDPOINTS
# ==========================================
@app.post("/api/auth/login")
def login(payload: LoginRequest):
    user = database.authenticate_user(payload.username, payload.password)
    if not user:
        raise HTTPException(status_code=401, detail="Invalid username or password")
    
    token = create_access_token({
        "id": user["id"],
        "username": user["username"],
        "role": user["role"]
    })
    
    return {
        "success": True,
        "token": token,
        "user": user
    }

@app.get("/api/auth/me")
def get_me(user: dict = Depends(get_current_user)):
    return {"success": True, "user": user}

@app.post("/api/auth/logout")
def logout():
    return {"success": True, "message": "Logged out"}

# ==========================================
# ADMIN USER MANAGEMENT & ANALYTICS
# ==========================================
@app.get("/api/admin/users")
def get_users(admin: dict = Depends(get_current_admin)):
    users = database.list_users()
    return {"success": True, "users": users}

@app.post("/api/admin/users")
def add_user(payload: CreateUserRequest, admin: dict = Depends(get_current_admin)):
    try:
        user = database.create_user(
            username=payload.username,
            password=payload.password,
            role=payload.role,
            full_name=payload.full_name or ""
        )
        return {"success": True, "user": {k: v for k, v in user.items() if k not in ("password_hash", "salt")}}
    except ValueError as ve:
        raise HTTPException(status_code=400, detail=str(ve))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to create user: {str(e)}")

@app.put("/api/admin/users/{user_id}")
def edit_user(user_id: int, payload: UpdateUserRequest, admin: dict = Depends(get_current_admin)):
    target = database.get_user_by_id(user_id)
    if not target:
        raise HTTPException(status_code=404, detail="User not found")
    
    # Prevent demoting or deactivating the last admin
    if target["role"] == "admin" and (payload.role == "user" or payload.is_active is False):
        all_admins = [u for u in database.list_users() if u["role"] == "admin" and u["is_active"]]
        if len(all_admins) <= 1 and all_admins[0]["id"] == user_id:
            raise HTTPException(status_code=400, detail="Cannot deactivate or demote the only active administrator.")
            
    updated = database.update_user(
        user_id=user_id,
        full_name=payload.full_name,
        role=payload.role,
        is_active=payload.is_active,
        password=payload.password
    )
    return {"success": True, "user": {k: v for k, v in updated.items() if k not in ("password_hash", "salt")}}

@app.delete("/api/admin/users/{user_id}")
def remove_user(user_id: int, admin: dict = Depends(get_current_admin)):
    if user_id == admin["id"]:
        raise HTTPException(status_code=400, detail="You cannot delete your own admin account.")
    target = database.get_user_by_id(user_id)
    if not target:
        raise HTTPException(status_code=404, detail="User not found")
    database.delete_user(user_id)
    return {"success": True, "message": f"User '{target['username']}' deleted."}

@app.get("/api/admin/user-analytics")
def get_user_analytics(admin: dict = Depends(get_current_admin)):
    analytics = database.get_user_analytics()
    return {"success": True, "analytics": analytics}

# ==========================================
# LEADS & WORKSPACE (SCOPED BY ROLE)
# ==========================================
@app.get("/api/leads")
def get_leads(
    status: Optional[str] = None, 
    search: Optional[str] = None, 
    filter_type: Optional[str] = "all_target",
    user_id: Optional[int] = None,
    user: Optional[dict] = Depends(get_current_user_optional)
):
    # If standard user, enforce their own user_id
    scoped_user_id = None
    if user:
        if user.get("role") == "user":
            scoped_user_id = user["id"]
        elif user.get("role") == "admin" and user_id:
            scoped_user_id = user_id

    # Map friendly status to DB status
    db_status = None
    if status == "unsent":
        db_status = "New"
    elif status == "sent":
        db_status = "Sent"
        
    leads_list = database.get_leads(filter_type=filter_type, message_status=db_status, user_id=scoped_user_id)
    
    # Filter search keywords if provided
    if search:
        search_lower = search.lower()
        leads_list = [
            l for l in leads_list 
            if (
                search_lower in l["name"].lower() or 
                (l.get("address") and search_lower in l["address"].lower()) or
                (l.get("category") and search_lower in l["category"].lower())
            )
        ]
        
    # Fast proposal formatting (instant, zero network latency)
    settings = database.get_all_settings()
    lang = settings.get('proposal_language', 'English')
    tpl = settings.get('proposal_template_urdu') if lang == 'Urdu' else settings.get('proposal_template')
    
    for lead in leads_list:
        cp = lead.get('custom_proposal')
        if cp and not cp.startswith('Error generating') and not cp.startswith('[EMAIL:') and '404' not in cp:
            lead["proposal"] = cp
        else:
            lead["proposal"] = generator.generate_templated_proposal(lead, tpl)
        
    return leads_list

@app.get("/api/all-leads")
def get_all_leads(
    user_id: Optional[int] = None,
    user: Optional[dict] = Depends(get_current_user_optional)
):
    scoped_user_id = None
    if user:
        if user.get("role") == "user":
            scoped_user_id = user["id"]
        elif user.get("role") == "admin" and user_id:
            scoped_user_id = user_id
            
    leads_list = database.get_all_raw_leads(user_id=scoped_user_id)
    settings = database.get_all_settings()
    lang = settings.get('proposal_language', 'English')
    tpl = settings.get('proposal_template_urdu') if lang == 'Urdu' else settings.get('proposal_template')

    for lead in leads_list:
        cp = lead.get('custom_proposal')
        if cp and not cp.startswith('Error generating') and not cp.startswith('[EMAIL:') and '404' not in cp:
            lead["proposal"] = cp
        else:
            lead["proposal"] = generator.generate_templated_proposal(lead, tpl)
            
    return leads_list


@app.post("/api/leads/enrich-emails")
def enrich_emails(limit: int = 25, user: Optional[dict] = Depends(get_current_user_optional)):
    scoped_user_id = user["id"] if user and user.get("role") == "user" else None
    leads = database.get_all_raw_leads(user_id=scoped_user_id)
    no_email_leads = [l for l in leads if not l.get("email")][:limit]
    
    enriched_count = 0
    enriched_leads = []
    
    for l in no_email_leads:
        try:
            email = scraper.find_business_email(
                context=None,
                website=l.get("website"),
                name=l.get("name"),
                address=l.get("address")
            )
            if email and l.get("id"):
                database.update_lead_email(l["id"], email)
                l["email"] = email
                enriched_count += 1
                enriched_leads.append({"id": l["id"], "name": l["name"], "email": email})
        except Exception as e:
            print(f"Error enriching lead {l.get('name')}: {e}")
            
    return {
        "success": True,
        "checked": len(no_email_leads),
        "enriched_count": enriched_count,
        "enriched": enriched_leads
    }

# Status endpoints
@app.put("/api/leads/{id}/status")
def update_lead_status_put(id: int, payload: LeadStatusUpdate, user: Optional[dict] = Depends(get_current_user_optional)):
    if payload.status not in ["New", "Sent"]:
        raise HTTPException(status_code=400, detail="Invalid status")
    uid = user["id"] if user else None
    uname = user["username"] if user else None
    database.update_lead_status(id, payload.status, user_id=uid, username=uname)
    return {"success": True}

@app.post("/api/leads/{id}/status")
def update_lead_status_post(id: int, payload: LeadStatusUpdate, user: Optional[dict] = Depends(get_current_user_optional)):
    return update_lead_status_put(id, payload, user)

@app.put("/api/leads/{lead_id}/status")
def update_lead_status_put_legacy(lead_id: int, payload: LeadStatusUpdate, user: Optional[dict] = Depends(get_current_user_optional)):
    return update_lead_status_put(lead_id, payload, user)

@app.post("/api/leads/{lead_id}/status")
def update_lead_status_post_legacy(lead_id: int, payload: LeadStatusUpdate, user: Optional[dict] = Depends(get_current_user_optional)):
    return update_lead_status_put(lead_id, payload, user)

# Proposal endpoints
@app.get("/api/leads/{id}/proposal")
def get_lead_proposal(id: int, force_refresh: bool = False):
    leads = database.get_all_raw_leads()
    lead = next((l for l in leads if l["id"] == id), None)
    if not lead:
        raise HTTPException(status_code=404, detail="Lead not found")
        
    if force_refresh:
        database.update_custom_proposal(id, None)
        lead["custom_proposal"] = None
        
    proposal = generator.get_proposal_for_lead(lead)
    return {"proposal": proposal}

@app.get("/api/leads/{lead_id}/proposal")
def get_lead_proposal_legacy(lead_id: int):
    return get_lead_proposal(lead_id)

@app.post("/api/leads/{id}/proposal")
def update_lead_proposal(id: int, payload: LeadProposalUpdate):
    database.update_custom_proposal(id, payload.proposal)
    return {"success": True}

@app.post("/api/leads/{lead_id}/proposal")
def update_lead_proposal_legacy(lead_id: int, payload: LeadProposalUpdate):
    return update_lead_proposal(lead_id, payload)

@app.post("/api/whatsapp/{id}")
def record_whatsapp_outreach(id: int, user: Optional[dict] = Depends(get_current_user_optional)):
    uid = user["id"] if user else None
    uname = user["username"] if user else None
    database.update_lead_status(id, "Sent", user_id=uid, username=uname)
    return {"success": True, "message": "WhatsApp tracking recorded"}

@app.post("/api/whatsapp/{lead_id}")
def record_whatsapp_outreach_legacy(lead_id: int, user: Optional[dict] = Depends(get_current_user_optional)):
    return record_whatsapp_outreach(lead_id, user)

# Delete endpoints
@app.delete("/api/leads/{id}")
def delete_lead(id: int):
    database.delete_lead(id)
    return {"success": True}

@app.delete("/api/leads/{lead_id}")
def delete_lead_legacy(lead_id: int):
    return delete_lead(lead_id)

@app.get("/api/stats")
def get_stats(user: Optional[dict] = Depends(get_current_user_optional)):
    settings = database.get_all_settings()
    daily_limit = int(settings.get("daily_limit", 50))
    
    scoped_user_id = user["id"] if (user and user.get("role") == "user") else None
    scraped_today = database.get_daily_scraped_count(user_id=scoped_user_id)
    limit_timer_end_str = settings.get("limit_timer_end", "")
    
    if limit_timer_end_str:
        try:
            clean_str = limit_timer_end_str.replace("Z", "+00:00")
            limit_timer_end = datetime.fromisoformat(clean_str)
            now = datetime.now(limit_timer_end.tzinfo) if limit_timer_end.tzinfo else datetime.now()
            if now >= limit_timer_end:
                database.save_setting("limit_timer_end", "")
                limit_timer_end_str = ""
        except Exception as e:
            print(f"Error checking limit_timer_end expiry: {e}")

    return {
        "scraped_today": scraped_today,
        "daily_limit": daily_limit,
        "remaining": max(0, daily_limit - scraped_today),
        "limit_timer_end": limit_timer_end_str,
        "last_reset_timestamp": settings.get("last_reset_timestamp", "")
    }

@app.post("/api/reset-limit")
def reset_limit():
    database.save_setting("limit_timer_end", "")
    return {"success": True, "message": "Limit timer reset successfully."}

@app.get("/api/settings")
def get_settings():
    return database.get_all_settings()

@app.post("/api/settings")
def save_settings(payload: SettingsUpdate, admin: dict = Depends(get_current_admin)):
    database.save_setting("daily_limit", payload.daily_limit)
    database.save_setting("proposal_language", payload.proposal_language)
    database.save_setting("playwright_headless", "True" if payload.playwright_headless else "False")
    database.save_setting("use_ai", "True" if payload.use_ai else "False")
    database.save_setting("ai_provider", payload.ai_provider)
    database.save_setting("gemini_api_key", payload.gemini_api_key)
    database.save_setting("openai_api_key", payload.openai_api_key)
    database.save_setting("proposal_template", payload.proposal_template)
    database.save_setting("proposal_template_urdu", payload.proposal_template_urdu)
    return {"success": True}

@app.post("/api/sync-supabase")
def sync_supabase(admin: dict = Depends(get_current_admin)):
    supabase_configured = database.get_supabase_client() is not None
    if not supabase_configured:
        raise HTTPException(status_code=400, detail="Supabase not configured in .env")
        
    leads = database.get_all_raw_leads()
    return {"success": True, "total": len(leads), "synced": len(leads)}

@app.post("/api/delete-all")
def delete_all_leads(admin: dict = Depends(get_current_admin)):
    conn = database.get_db_connection()
    cursor = conn.cursor()
    cursor.execute("DELETE FROM leads")
    conn.commit()
    conn.close()
    
    supabase = database.get_supabase_client()
    if supabase:
        try:
            supabase.table("leads").delete().neq("id", -1).execute()
        except Exception as e:
            print(f"Supabase delete all error: {e}")
    return {"success": True}

import subprocess
import sys

active_scraper_proc = None

@app.post("/api/scrape/stop")
def stop_scrape():
    global active_scraper_proc
    if active_scraper_proc:
        try:
            active_scraper_proc.terminate()
            active_scraper_proc.kill()
            active_scraper_proc = None
            return {"success": True, "message": "Scraper process terminated by user request."}
        except Exception as e:
            return {"success": False, "message": f"Could not stop process: {e}"}
    return {"success": True, "message": "No active scraper process running."}

@app.post("/api/scrape")
def scrape_leads(payload: ScrapeRequest, user: Optional[dict] = Depends(get_current_user_optional)):
    global active_scraper_proc
    try:
        user_id_str = str(user["id"]) if user else "1"
        user_name_str = user["username"] if user else "system"
        user_role_str = user.get("role", "admin") if user else "admin"
        
        base_dir = os.path.dirname(os.path.abspath(__file__))
        cli_path = os.path.join(base_dir, "cli_scraper.py")

        cmd = [
            sys.executable, cli_path,
            "--query", payload.query,
            "--limit", str(payload.limit),
            "--source", payload.source or "auto",
            "--headless", "true",
            "--user-id", user_id_str,
            "--user-name", user_name_str,
            "--user-role", user_role_str
        ]
        
        proc = subprocess.Popen(
            cmd,
            cwd=base_dir,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True
        )
        active_scraper_proc = proc
        
        try:
            stdout, stderr = proc.communicate(timeout=600)
        except subprocess.TimeoutExpired:
            proc.kill()
            stdout, stderr = proc.communicate()
        finally:
            active_scraper_proc = None
        
        result_json = None
        logs = []
        for line in stdout.splitlines():
            if line.startswith("[SCRAPER_LOG] "):
                logs.append(line.replace("[SCRAPER_LOG] ", "").strip())
            elif line.startswith("[SCRAPER_RESULT_JSON] "):
                json_str = line.replace("[SCRAPER_RESULT_JSON] ", "").strip()
                try:
                    import json
                    result_json = json.loads(json_str)
                except Exception:
                    pass
                    
        if result_json:
            return result_json
            
        return {
            "success": True,
            "count": 0,
            "logs": logs or [f"Scraper execution completed: {stderr[:200]}"],
            "leads": []
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Scraper error: {str(e)}")

@app.get("/api/scrape/stream")
def scrape_stream(
    query: str, 
    limit: int, 
    headless: bool = True,
    user: Optional[dict] = Depends(get_current_user_optional)
):
    q = queue.Queue()
    uid = user["id"] if user else None
    uname = user["username"] if user else None
    
    def log_callback(msg):
        q.put(msg)
        
    def run_scraper():
        try:
            count = scraper.scrape_google_maps(
                query=query,
                limit=limit,
                headless=headless,
                on_progress=log_callback,
                user_id=uid,
                user_name=uname
            )
            if count > 0 and uid:
                database.record_user_activity(uid, uname or f"User-{uid}", "scrape", count, f"Google Maps Scraped {count} leads")
            q.put(f"SUCCESS: Successfully finished. Saved {count} leads.")
        except Exception as e:
            q.put(f"ERROR: {str(e)}")
        finally:
            settings = database.get_all_settings()
            daily_scraped = database.get_daily_scraped_count(user_id=uid)
            daily_limit = int(settings.get("daily_limit", 50))
            if daily_scraped >= daily_limit and not settings.get("limit_timer_end"):
                database.trigger_limit_timer()
                q.put("LIMIT_REACHED: Reached limit, timer started.")
            q.put(None)
            
    threading.Thread(target=run_scraper, daemon=True).start()
    
    def event_generator():
        while True:
            msg = q.get()
            if msg is None:
                break
            yield f"data: {msg}\n\n"
            
    return StreamingResponse(event_generator(), media_type="text/event-stream")

