import os
import time
import random
import urllib.parse
import requests
import database

def check_lead_eligibility(name, address, phone, website):
    # Enforce quality filters: Must NOT have a website AND must HAVE a phone number
    if website:
        cleaned_website = website.strip().lower()
        if cleaned_website not in ('none', 'null', ''):
            return False, f"has website: {website}"
            
    if not phone or phone.strip().lower() in ('none', 'null', '', 'n/a'):
        return False, "no phone number found"
        
    if database.lead_exists(name, address):
        return False, "already exists in database"
        
    return True, ""

# OSM category tags mapping
OSM_TAGS = {
    'restaurant': ('amenity', 'restaurant'),
    'restaurants': ('amenity', 'restaurant'),
    'cafe': ('amenity', 'cafe'),
    'cafes': ('amenity', 'cafe'),
    'dentist': ('amenity', 'dentist'),
    'dentists': ('amenity', 'dentist'),
    'hotel': ('tourism', 'hotel'),
    'hotels': ('tourism', 'hotel'),
    'gym': ('leisure', 'fitness_centre'),
    'gyms': ('leisure', 'fitness_centre'),
    'salon': ('shop', 'hairdresser'),
    'salons': ('shop', 'hairdresser'),
    'barber': ('shop', 'hairdresser'),
    'bakery': ('shop', 'bakery'),
    'bakeries': ('shop', 'bakery'),
    'school': ('amenity', 'school'),
    'schools': ('amenity', 'school'),
    'hospital': ('amenity', 'hospital'),
    'hospitals': ('amenity', 'hospital'),
    'store': ('shop', 'yes'),
    'stores': ('shop', 'yes'),
    'pharmacy': ('amenity', 'pharmacy'),
    'pharmacies': ('amenity', 'pharmacy'),
    'supermarket': ('shop', 'supermarket'),
    'supermarkets': ('shop', 'supermarket'),
}

def extract_phone_number(page):
    selectors = [
        '[data-item-id^="phone:tel:"]',
        'a[href^="tel:"]',
        'button[aria-label^="Phone:"]',
        'button[aria-label*="Phone"]',
        'button[aria-label*="phone"]',
        '[data-tooltip*="phone"]',
        '[data-tooltip*="Phone"]'
    ]
    for sel in selectors:
        try:
            el = page.locator(sel)
            if el.count() > 0:
                first_el = el.first
                text = first_el.inner_text().strip()
                if text:
                    # Clean out copy labels or icons if any (e.g. "Copy phone number\n+92 300 123456")
                    if "\n" in text:
                        text = text.split("\n")[-1].strip()
                    return text
                
                # Check link href
                href = first_el.get_attribute("href")
                if href and href.startswith("tel:"):
                    return href.replace("tel:", "").strip()
                    
                # Check aria-label
                label = first_el.get_attribute("aria-label")
                if label:
                    if "Phone:" in label:
                        return label.split("Phone:", 1)[1].strip()
                    if ":" in label:
                        return label.split(":", 1)[1].strip()
                    return label.strip()
        except Exception:
            continue
            
    # Scanning all links on page as fallback
    try:
        links = page.locator('a').all()
        for link in links:
            href = link.get_attribute('href')
            if href and href.startswith('tel:'):
                return href.replace('tel:', '').strip()
    except Exception:
        pass
        
    return None

def parse_query(query):
    query_lower = query.lower()
    if " in " in query_lower:
        category, location = query_lower.split(" in ", 1)
        return category.strip(), location.strip()
    return query, ""

def geocode_location(location_name):
    url = f"https://nominatim.openstreetmap.org/search?q={urllib.parse.quote(location_name)}&format=json&limit=1"
    headers = {'User-Agent': 'LeadGeneratorApp/1.0 (hf@scrapping.local)'}
    try:
        resp = requests.get(url, headers=headers, timeout=10)
        if resp.status_code == 200:
            data = resp.json()
            if data:
                return float(data[0]['lat']), float(data[0]['lon'])
    except Exception as e:
        print(f"OSM Nominatim Geocoding error: {e}")
    return None, None

def scrape_osm(query, limit, on_progress):
    on_progress(f"Starting OpenStreetMap scraping for query: '{query}'...")
    category, location = parse_query(query)
    if not location:
        on_progress("Error: OSM scraping requires a location in the query (e.g. 'restaurants in Lahore').")
        return 0
        
    lat, lon = geocode_location(location)
    if not lat or not lon:
        on_progress(f"Error: Could not geocode location '{location}' using Nominatim.")
        return 0
        
    on_progress(f"Geocoded '{location}' to coordinates: ({lat:.4f}, {lon:.4f})")
    
    # Map category
    tag_key, tag_val = OSM_TAGS.get(category, ('amenity', category))
    on_progress(f"Searching OSM tags: [{tag_key}={tag_val}] within 10km radius...")
    
    overpass_url = "https://overpass-api.de/api/interpreter"
    query_ql = f"""
    [out:json];
    (
      node["{tag_key}"="{tag_val}"](around:10000, {lat}, {lon});
      way["{tag_key}"="{tag_val}"](around:10000, {lat}, {lon});
      relation["{tag_key}"="{tag_val}"](around:10000, {lat}, {lon});
    );
    out center;
    """
    
    try:
        headers = {'User-Agent': 'LeadForgeApp/1.0 (hf@scrapping.local)'}
        resp = requests.post(overpass_url, data={'data': query_ql}, headers=headers, timeout=30)
        if resp.status_code != 200:
            on_progress(f"Error from Overpass API (status code {resp.status_code})")
            return 0
        
        data = resp.json()
        elements = data.get('elements', [])
        on_progress(f"Found {len(elements)} total matches in region. Processing...")
        
        daily_scraped = database.get_daily_scraped_count()
        daily_limit = int(database.get_setting('daily_limit', 25))
        remaining = daily_limit - daily_scraped
        if remaining <= 0:
            on_progress(f"Daily limit of {daily_limit} already reached today. Stopping.")
            return 0
            
        saved_count = 0
        for el in elements:
            if saved_count >= limit or saved_count >= remaining:
                break
                
            tags = el.get('tags', {})
            name = tags.get('name')
            if not name:
                continue
                
            website = tags.get('website') or tags.get('contact:website')
            phone = tags.get('phone') or tags.get('contact:phone') or tags.get('contact:mobile')
            
            # Form address
            street = tags.get('addr:street', '')
            housenumber = tags.get('addr:housenumber', '')
            suburb = tags.get('addr:suburb', '')
            city = tags.get('addr:city', location.capitalize())
            addr_parts = [p for p in [housenumber, street, suburb, city] if p]
            address = ", ".join(addr_parts) if addr_parts else location.capitalize()
            
            # Check unique name & address and quality criteria
            eligible, reason = check_lead_eligibility(name, address, phone, website)
            if not eligible:
                on_progress(f"Skipped: **{name}** ({reason})")
                continue
                
            # SQLite insertion
            osm_url = f"https://www.openstreetmap.org/{el.get('type')}/{el.get('id')}"
            db_id = database.insert_lead(
                name=name,
                address=address,
                phone=phone,
                website=website,
                category=category.capitalize(),
                query=query,
                google_maps_url=osm_url
            )
            
            if db_id:
                saved_count += 1
                on_progress(f"[{saved_count}] Saved: **{name}** | Phone: {phone or 'N/A'} | Website: {website or 'None'}")
                
        on_progress(f"OSM scraping complete. Saved {saved_count} new leads.")
        return saved_count
        
    except Exception as e:
        on_progress(f"Error during OSM scraping: {str(e)}")
        return 0


def scrape_google_maps(query, limit, headless, on_progress):
    on_progress("Launching Google Maps scraper (Playwright)...")
    
    daily_scraped = database.get_daily_scraped_count()
    daily_limit = int(database.get_setting('daily_limit', 25))
    remaining = daily_limit - daily_scraped
    if remaining <= 0:
        on_progress(f"Daily limit of {daily_limit} already reached today. Stopping.")
        return 0
        
    to_scrape_count = min(limit, remaining)
    
    from playwright.sync_api import sync_playwright
    with sync_playwright() as p:
        # Launch browser
        browser = p.chromium.launch(
            headless=headless,
            args=[
                "--disable-blink-features=AutomationControlled",
                "--no-sandbox",
                "--disable-infobars",
                "--window-size=1280,800"
            ]
        )
        
        # New context with realistic User Agent
        context = browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            viewport={'width': 1280, 'height': 800}
        )
        
        page = context.new_page()
        
        # Inject standard stealth variables
        page.evaluate("() => { Object.defineProperty(navigator, 'webdriver', { get: () => undefined }) }")
        
        search_url = f"https://www.google.com/maps/search/{urllib.parse.quote_plus(query)}"
        on_progress(f"Navigating to search page...")
        page.goto(search_url)
        
        # Wait for results panel or single business view
        try:
            page.wait_for_selector('h1, a[href*="/maps/place/"]', timeout=20000)
        except Exception as e:
            on_progress("Error: Timeout waiting for search results page to load.")
            browser.close()
            return 0
            
        # Check if redirected directly to a single business page
        if "/maps/place/" in page.url:
            on_progress("Redirected directly to a single business page. Extracting...")
            try:
                page.wait_for_timeout(2000) # Render delay
                name = page.locator('h1').first.inner_text().strip()
                address = None
                address_el = page.locator('[data-item-id="address"]')
                if address_el.count() > 0:
                    address = address_el.first.inner_text().strip()
                    
                phone = extract_phone_number(page)
                    
                website = None
                website_el = page.locator('a[data-item-id="authority"]')
                if website_el.count() > 0:
                    website = website_el.first.get_attribute('href')
                    
                category = "Local Business"
                category_el = page.locator('button[data-item-id="category"]')
                if category_el.count() > 0:
                    category = category_el.first.inner_text().strip()
                else:
                    category_el = page.locator('button[jsaction*="pane.rating.category"]')
                    if category_el.count() > 0:
                        category = category_el.first.inner_text().strip()
                        
                eligible, reason = check_lead_eligibility(name, address, phone, website)
                if not eligible:
                    on_progress(f"Skipped: **{name}** ({reason})")
                    browser.close()
                    return 0
                    
                db_id = database.insert_lead(
                    name=name,
                    address=address,
                    phone=phone,
                    website=website,
                    category=category,
                    query=query,
                    google_maps_url=page.url
                )
                if db_id:
                    on_progress(f"Saved: **{name}** | Phone: {phone or 'N/A'} | Website: {website or 'None'}")
                    browser.close()
                    return 1
                else:
                    on_progress(f"Lead **{name}** could not be saved.")
                    browser.close()
                    return 0
            except Exception as ex:
                on_progress(f"Error scraping single business: {str(ex)}")
                browser.close()
                return 0

        # It's a list. Locate the feed container
        feed_selector = 'div[role="feed"]'
        try:
            page.wait_for_selector(feed_selector, timeout=15000)
        except Exception as e:
            on_progress("Could not find results feed. Trying to extract visible elements anyway...")
            
        on_progress("Scrolling results panel to collect business links...")
        
        place_urls = []
        feed_el = page.locator(feed_selector)
        
        no_new_urls_loops = 0
        last_urls_count = 0
        
        # Scroll the list to find elements
        # We need to collect a larger pool of candidates because many will be filtered out (having websites or lacking phone numbers)
        target_candidate_count = max(to_scrape_count * 5, 50)
        while len(place_urls) < target_candidate_count and no_new_urls_loops < 15:
            links = page.locator('a[href*="/maps/place/"]').all()
            for link in links:
                try:
                    href = link.get_attribute('href')
                    if href and href not in place_urls:
                        place_urls.append(href)
                except Exception:
                    continue
            
            if len(place_urls) == last_urls_count:
                no_new_urls_loops += 1
            else:
                no_new_urls_loops = 0
                
            last_urls_count = len(place_urls)
            
            if feed_el.count() > 0:
                feed_el.first.evaluate("el => el.scrollBy(0, 3000)")
            else:
                page.mouse.wheel(0, 1000)
                
            page.wait_for_timeout(1500)
            
        on_progress(f"Found {len(place_urls)} total business candidates. Filtering duplicates...")
        
        # Filter URLs that are already in database
        new_urls = [url for url in place_urls if not database.url_exists(url)]
        on_progress(f"{len(new_urls)} of these are new and haven't been scraped yet.")
        
        if len(new_urls) == 0:
            on_progress("No new businesses to scrape.")
            browser.close()
            return 0
            
        saved_count = 0
        for i, url in enumerate(new_urls):
            if saved_count >= to_scrape_count:
                break
                
            # Delay to avoid blocking
            delay = random.randint(5, 15)
            on_progress(f"[{saved_count+1}/{to_scrape_count}] Waiting {delay} seconds before loading next details...")
            time.sleep(delay)
            
            try:
                page.goto(url)
                # Wait for title
                page.wait_for_selector('h1', timeout=15000)
                page.wait_for_timeout(2000) # Render delay for sub-elements
                
                name = page.locator('h1').first.inner_text().strip()
                
                address = None
                address_el = page.locator('[data-item-id="address"]')
                if address_el.count() > 0:
                    address = address_el.first.inner_text().strip()
                    
                phone = extract_phone_number(page)
                    
                website = None
                website_el = page.locator('a[data-item-id="authority"]')
                if website_el.count() > 0:
                    website = website_el.first.get_attribute('href')
                    
                category = "Local Business"
                category_el = page.locator('button[data-item-id="category"]')
                if category_el.count() > 0:
                    category = category_el.first.inner_text().strip()
                else:
                    category_el = page.locator('button[jsaction*="pane.rating.category"]')
                    if category_el.count() > 0:
                        category = category_el.first.inner_text().strip()
                
                if not name:
                    continue
                    
                eligible, reason = check_lead_eligibility(name, address, phone, website)
                if not eligible:
                    on_progress(f"Skipped: **{name}** ({reason})")
                    continue
                    
                db_id = database.insert_lead(
                    name=name,
                    address=address,
                    phone=phone,
                    website=website,
                    category=category,
                    query=query,
                    google_maps_url=url
                )
                
                if db_id:
                    saved_count += 1
                    on_progress(f"[{saved_count}] Saved: **{name}** | Phone: {phone or 'N/A'} | Website: {website or 'None'}")
                    
            except Exception as e:
                on_progress(f"Error scraping details for business {i+1}: {str(e)}")
                
        on_progress(f"Google Maps scraping complete. Saved {saved_count} new leads.")
        browser.close()
        return saved_count
