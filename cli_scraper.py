import sys
import argparse
import json
import scraper
import database

def main():
    parser = argparse.ArgumentParser(description="Standalone Lead Scraper CLI")
    parser.add_argument("--query", type=str, required=True, help="Search query")
    parser.add_argument("--limit", type=int, default=50, help="Max limit")
    parser.add_argument("--source", type=str, default="auto", help="Scraper source (bing, google_maps, osm, auto)")
    parser.add_argument("--headless", type=str, default="true", help="Headless mode (true/false)")
    parser.add_argument("--user-id", type=int, default=None, help="User ID initiating the scrape")
    parser.add_argument("--user-name", type=str, default=None, help="Username initiating the scrape")
    
    args = parser.parse_args()
    headless_bool = args.headless.lower() == "true"
    user_id = args.user_id
    user_name = args.user_name
    
    logs = []
    def log_callback(msg):
        logs.append(msg)
        print(f"[SCRAPER_LOG] {msg}", flush=True)

    source = args.source.lower()
    count = 0
    
    if source in ["bing", "bing_maps"]:
        log_callback("Launching Bing Maps scraper (Playwright)...")
        count = scraper.scrape_bing_maps(args.query, args.limit, headless_bool, log_callback, user_id=user_id, user_name=user_name)
    elif source in ["google_maps", "google"]:
        log_callback("Launching Google Maps scraper (Playwright)...")
        count = scraper.scrape_google_maps(args.query, args.limit, headless_bool, log_callback, user_id=user_id, user_name=user_name)
    elif source == "osm":
        res_osm = scraper.scrape_osm(args.query, args.limit, log_callback, user_id=user_id, user_name=user_name)
        count = len(res_osm) if isinstance(res_osm, list) else res_osm
    else: # auto
        log_callback("Launching Bing Maps primary scraper...")
        count = scraper.scrape_bing_maps(args.query, args.limit, headless_bool, log_callback, user_id=user_id, user_name=user_name)
        
    if count == 0 and source != "google_maps" and source != "google":
        log_callback("Primary scraper returned 0 leads. Auto-switching to Google Maps Playwright Scraper...")
        count = scraper.scrape_google_maps(args.query, args.limit, headless_bool, log_callback, user_id=user_id, user_name=user_name)
        
    if count > 0 and user_id:
        database.record_user_activity(user_id, user_name or f"User-{user_id}", "scrape", count, f"Scraped {count} leads for query '{args.query}'")

    all_leads = database.get_all_raw_leads(user_id=user_id)
    if count > 0:
        leads_data = all_leads[:count]
    else:
        q_words = [w.lower() for w in args.query.split() if len(w) > 2]
        leads_data = [
            l for l in all_leads
            if any(w in (l.get('query') or '').lower() or w in (l.get('name') or '').lower() or w in (l.get('category') or '').lower() for w in q_words)
        ][:args.limit]
        if leads_data:
            log_callback(f"Notice: Found {len(leads_data)} existing matching leads in database for '{args.query}'.")
    
    result = {
        "success": True,
        "count": count,
        "existing_count": len(leads_data) if count == 0 else 0,
        "logs": logs,
        "leads": leads_data
    }
    
    print(f"[SCRAPER_RESULT_JSON] {json.dumps(result)}", flush=True)

if __name__ == "__main__":
    main()

