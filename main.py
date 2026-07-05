import os
import queue
import threading
import urllib.parse
from fastapi import FastAPI, HTTPException, BackgroundTasks, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from typing import Optional, List

import database
import scraper
import generator

app = FastAPI(title="Lead Gen API")

# Enable CORS for frontend development
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Allows all origins (e.g. http://localhost:5173)
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Initialize database
database.init_db()

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

@app.get("/api/leads")
def get_leads(status: Optional[str] = None, search: Optional[str] = None):
    # Map friendly status to DB status
    db_status = None
    if status == "unsent":
        db_status = "New"
    elif status == "sent":
        db_status = "Sent"
        
    leads_list = database.get_leads(filter_no_website=True, message_status=db_status)
    
    # Filter search keywords if provided
    if search:
        search_lower = search.lower()
        leads_list = [
            l for l in leads_list 
            if (
                search_lower in l["name"].lower() or 
                (l["address"] and search_lower in l["address"].lower()) or
                (l["category"] and search_lower in l["category"].lower())
            )
        ]
        
    # Generate proposal on the fly for leads that do not have one yet
    for lead in leads_list:
        lead["proposal"] = generator.get_proposal_for_lead(lead)
        
    return leads_list

@app.get("/api/all-leads")
def get_all_leads():
    leads_list = database.get_all_raw_leads()
    for lead in leads_list:
        lead["proposal"] = generator.get_proposal_for_lead(lead)
    return leads_list

@app.post("/api/leads/{lead_id}/status")
def update_lead_status(lead_id: int, payload: LeadStatusUpdate):
    if payload.status not in ["New", "Sent"]:
        raise HTTPException(status_code=400, detail="Invalid status")
    database.update_lead_status(lead_id, payload.status)
    return {"success": True}

@app.post("/api/leads/{lead_id}/proposal")
def update_lead_proposal(lead_id: int, payload: LeadProposalUpdate):
    database.update_custom_proposal(lead_id, payload.proposal)
    return {"success": True}

@app.delete("/api/leads/{lead_id}")
def delete_lead(lead_id: int):
    database.delete_lead(lead_id)
    return {"success": True}

@app.get("/api/stats")
def get_stats():
    settings = database.get_all_settings()
    daily_limit = int(settings.get("daily_limit", 25))
    scraped_today = database.get_daily_scraped_count()
    return {
        "scraped_today": scraped_today,
        "daily_limit": daily_limit,
        "remaining": max(0, daily_limit - scraped_today),
        "limit_timer_end": settings.get("limit_timer_end", ""),
        "last_reset_timestamp": settings.get("last_reset_timestamp", "")
    }

@app.get("/api/settings")
def get_settings():
    return database.get_all_settings()

@app.post("/api/settings")
def save_settings(payload: SettingsUpdate):
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
def sync_supabase():
    supabase_configured = database.get_supabase_client() is not None
    if not supabase_configured:
        raise HTTPException(status_code=400, detail="Supabase not configured in .env")
        
    leads = database.get_all_raw_leads()
    success_count = 0
    for lead in leads:
        if database.sync_lead_to_supabase(lead):
            success_count += 1
            
    return {"success": True, "total": len(leads), "synced": success_count}

@app.post("/api/delete-all")
def delete_all_leads():
    conn = database.get_db_connection()
    conn.execute("DELETE FROM leads")
    conn.commit()
    conn.close()
    return {"success": True}

@app.get("/api/scrape/stream")
def scrape_stream(query: str, source: str, limit: int, headless: bool = True):
    q = queue.Queue()
    
    def log_callback(msg):
        q.put(msg)
        
    def run_scraper():
        try:
            if source == "Google Maps (Playwright)":
                count = scraper.scrape_google_maps(
                    query=query,
                    limit=limit,
                    headless=headless,
                    on_progress=log_callback
                )
            else:
                count = scraper.scrape_osm(
                    query=query,
                    limit=limit,
                    on_progress=log_callback
                )
            q.put(f"SUCCESS: Successfully finished. Saved {count} leads.")
        except Exception as e:
            q.put(f"ERROR: {str(e)}")
        finally:
            # Check limit
            settings = database.get_all_settings()
            daily_scraped = database.get_daily_scraped_count()
            daily_limit = int(settings.get("daily_limit", 25))
            if daily_scraped >= daily_limit and not settings.get("limit_timer_end"):
                database.trigger_limit_timer()
                q.put("LIMIT_REACHED: Reached limit, timer started.")
            q.put(None)  # Sentinel to close stream
            
    threading.Thread(target=run_scraper, daemon=True).start()
    
    def event_generator():
        while True:
            msg = q.get()
            if msg is None:
                break
            # Format as Server-Sent Event
            yield f"data: {msg}\n\n"
            
    return StreamingResponse(event_generator(), media_type="text/event-stream")
