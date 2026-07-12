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

class ScrapeRequest(BaseModel):
    query: str
    limit: int

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

@app.put("/api/leads/{lead_id}/status")
def update_lead_status_put(lead_id: int, payload: LeadStatusUpdate):
    if payload.status not in ["New", "Sent"]:
        raise HTTPException(status_code=400, detail="Invalid status")
    database.update_lead_status(lead_id, payload.status)
    return {"success": True}

@app.get("/api/leads/{lead_id}/proposal")
def get_lead_proposal(lead_id: int):
    leads = database.get_all_raw_leads()
    lead = next((l for l in leads if l["id"] == lead_id), None)
    if not lead:
        raise HTTPException(status_code=404, detail="Lead not found")
        
    proposal = f"Hi {lead['name']},\n\nWe noticed you're a great {lead['category']} in {lead['address']}. We specialize in helping local businesses like yours get more customers. Let's chat!"
    return {"proposal": proposal}

@app.post("/api/leads/{lead_id}/proposal")
def update_lead_proposal(lead_id: int, payload: LeadProposalUpdate):
    database.update_custom_proposal(lead_id, payload.proposal)
    return {"success": True}

@app.post("/api/whatsapp/{lead_id}")
def record_whatsapp_outreach(lead_id: int):
    database.update_lead_status(lead_id, "Sent")
    return {"success": True, "message": "WhatsApp tracking recorded"}

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
    return {"success": True, "total": len(leads), "synced": len(leads)}

@app.post("/api/delete-all")
def delete_all_leads():
    supabase = database.get_supabase_client()
    if supabase:
        try:
            supabase.table("leads").delete().neq("id", -1).execute()
        except Exception as e:
            raise HTTPException(status_code=500, detail=str(e))
    return {"success": True}

@app.post("/api/scrape")
def scrape_leads(payload: ScrapeRequest):
    try:
        logs_list = []
        def log_callback(msg):
            logs_list.append(msg)
            
        leads_saved = scraper.scrape_osm(
            query=payload.query,
            limit=payload.limit,
            on_progress=log_callback
        )
        
        # Determine the saved leads count and data
        if isinstance(leads_saved, list):
            count = len(leads_saved)
            leads_data = leads_saved
        else:
            count = leads_saved
            leads_data = []
            
        # Trigger daily limit checking in background/database
        settings = database.get_all_settings()
        daily_scraped = database.get_daily_scraped_count()
        daily_limit = int(settings.get("daily_limit", 25))
        if daily_scraped >= daily_limit and not settings.get("limit_timer_end"):
            database.trigger_limit_timer()
            
        return {
            "success": True,
            "count": count,
            "logs": logs_list,
            "leads": leads_data
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/scrape/stream")
def scrape_stream(query: str, limit: int, headless: bool = True):
    q = queue.Queue()
    
    def log_callback(msg):
        q.put(msg)
        
    def run_scraper():
        try:
            count = scraper.scrape_google_maps(
                query=query,
                limit=limit,
                headless=headless,
                on_progress=log_callback
            )
            q.put(f"SUCCESS: Successfully finished. Saved {count} leads.")
        except Exception as e:
            q.put(f"ERROR: {str(e)}")
        finally:
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
            yield f"data: {msg}\n\n"
            
    return StreamingResponse(event_generator(), media_type="text/event-stream")
