from fastapi import FastAPI, HTTPException, BackgroundTasks
from pydantic import BaseModel
from supabase import create_client, Client
import os
import subprocess
from typing import Optional, Dict, Any
from dotenv import load_dotenv  # pyrefly: ignore [missing-import]

load_dotenv()

app = FastAPI(title="Scraping Backend")

SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")

if not SUPABASE_URL or not SUPABASE_KEY:
    raise ValueError("Supabase credentials must be set in .env")

supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)

class StatusUpdate(BaseModel):
    status: str

class ProposalUpdate(BaseModel):
    proposal: str

class SettingsUpdate(BaseModel):
    settings: Dict[str, Any]

def run_scraper_task():
    try:
        # Assuming scraper.py is the entry point for scraping
        subprocess.run(["python", "scraper.py"], check=True)
    except subprocess.CalledProcessError as e:
        print(f"Scraper failed: {e}")

@app.get("/api/leads")
def get_leads():
    try:
        response = supabase.table("leads").select("*").execute()
        return {"data": response.data}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/scrape")
def run_scraper(background_tasks: BackgroundTasks):
    # Run the scraper in the background so we don't block the HTTP response
    background_tasks.add_task(run_scraper_task)
    return {"message": "Scraper started in background"}

@app.put("/api/leads/{lead_id}/status")
def update_status(lead_id: str, payload: StatusUpdate):
    try:
        response = supabase.table("leads").update({"status": payload.status}).eq("id", lead_id).execute()
        if not response.data:
            raise HTTPException(status_code=404, detail="Lead not found")
        return {"data": response.data[0]}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.put("/api/leads/{lead_id}/proposal")
def update_proposal(lead_id: str, payload: ProposalUpdate):
    try:
        response = supabase.table("leads").update({"proposal": payload.proposal}).eq("id", lead_id).execute()
        if not response.data:
            raise HTTPException(status_code=404, detail="Lead not found")
        return {"data": response.data[0]}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/settings")
def get_settings():
    try:
        response = supabase.table("settings").select("*").limit(1).execute()
        if not response.data:
            return {"data": {}}
        return {"data": response.data[0]}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/settings")
def save_settings(payload: SettingsUpdate):
    try:
        # Assuming single row for settings, could use upsert or update depending on schema
        # Doing a basic insert/upsert assuming an id=1 for global settings
        data_to_save = payload.settings.copy()
        if "id" not in data_to_save:
            data_to_save["id"] = 1
            
        response = supabase.table("settings").upsert(data_to_save).execute()
        return {"data": response.data[0] if response.data else {}}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
