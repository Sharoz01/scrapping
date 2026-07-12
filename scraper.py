import os
import time
import random
import urllib.parse
import re
import requests
import database

def check_lead_eligibility(name, address, phone, email, website):
    # Enforce quality filters:
    # 1. Website MUST be empty/null (required)
    if website:
        cleaned_website = website.strip().lower()
        if cleaned_website not in ('none', 'null', ''):
            return False, f"has website: {website}"
            
    # 2. Must have AT LEAST ONE of: phone OR email
    has_phone = phone and phone.strip().lower() not in ('none', 'null', '', 'n/a')
    has_email = email and email.strip().lower() not in ('none', 'null', '')
    
    if not has_phone and not has_email:
        return False, "neither phone nor email found"
        
    if database.lead_exists(name, address):
        return False, "already exists in database"
        
    return True, ""

def extract_email_from_text(text):
    if not text:
        return None
    email_pattern = r'[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}'
    emails = re.findall(email_pattern, text)
    for email in emails:
        email_clean = email.strip().strip('.')
        email_lower = email_clean.lower()
        
        # Exclude common false positives
        invalid_extensions = ['.png', '.jpg', '.jpeg', '.gif', '.svg', '.webp', '.css', '.js']
        invalid_domains = ['example.com', 'sentry.io', 'w3.org', 'bootstrap.com', 'jquery.com', 'google.com', 'googleapis.com']
        
        if any(email_lower.endswith(ext) for ext in invalid_extensions):
            continue
        if any(domain in email_lower for domain in invalid_domains):
            continue
            
        return email_clean
    return None

def extract_email_from_website(context, url, on_progress):
    if not url or url.strip().lower() in ('none', 'null', ''):
        return None
    if not url.startswith('http://') and not url.startswith('https://'):
        url = 'http://' + url

    on_progress(f"Scanning website: {url}...")
    site_page = None
    try:
        site_page = context.new_page()
        site_page.set_default_timeout(15000)
        site_page.set_default_navigation_timeout(15000)
        
        # Open website homepage
        site_page.goto(url, wait_until="domcontentloaded", timeout=15000)
        site_page.wait_for_timeout(2000)
        
        # Check mailto: links
        mailto_el = site_page.locator('a[href^="mailto:"]')
        if mailto_el.count() > 0:
            href = mailto_el.first.get_attribute('href')
            if href:
                email = href.replace('mailto:', '').split('?')[0].strip()
                if email:
                    on_progress(f"Found email in mailto link: {email}")
                    return email
                    
        # Check homepage text content
        body_text = site_page.locator('body').inner_text()
        email = extract_email_from_text(body_text)
        if email:
            on_progress(f"Found email in page text: {email}")
            return email
            
        # Look for contact pages
        contact_links = site_page.locator('a[href*="contact"], a[href*="Contact"]').all()
        contact_urls = []
        for link in contact_links:
            try:
                href = link.get_attribute('href')
                if href:
                    resolved_url = urllib.parse.urljoin(url, href)
                    if resolved_url not in contact_urls:
                        contact_urls.append(resolved_url)
            except Exception:
                continue
                
        # Visit contact page
        for contact_url in contact_urls[:2]:
            try:
                on_progress(f"Scanning contact page: {contact_url}...")
                site_page.goto(contact_url, wait_until="domcontentloaded", timeout=10000)
                site_page.wait_for_timeout(1500)
                
                # Check mailto links on contact page
                mailto_el = site_page.locator('a[href^="mailto:"]')
                if mailto_el.count() > 0:
                    href = mailto_el.first.get_attribute('href')
                    if href:
                        email = href.replace('mailto:', '').split('?')[0].strip()
                        if email:
                            on_progress(f"Found email on contact page mailto: {email}")
                            return email
                            
                # Check text content of contact page
                body_text = site_page.locator('body').inner_text()
                email = extract_email_from_text(body_text)
                if email:
                    on_progress(f"Found email on contact page text: {email}")
                    return email
            except Exception as ce:
                on_progress(f"Could not load contact page {contact_url}: {ce}")
                
    except Exception as e:
        on_progress(f"Could not scan website {url}: {e}")
    finally:
        if site_page:
            try:
                site_page.close()
            except Exception:
                pass
    return None

def find_email_from_website_requests(url):
    if not url or url.strip().lower() in ('none', 'null', ''):
        return None
    if not url.startswith('http://') and not url.startswith('https://'):
        url = 'http://' + url
    try:
        headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'}
        resp = requests.get(url, headers=headers, timeout=10)
        if resp.status_code == 200:
            email = extract_email_from_text(resp.text)
            if email:
                return email
            # Simple fallback search for Contact page links
            links = re.findall(r'href=["\']([^"\']*(?:contact|Contact)[^"\']*)["\']', resp.text)
            for link in links[:2]:
                contact_url = urllib.parse.urljoin(url, link)
                try:
                    c_resp = requests.get(contact_url, headers=headers, timeout=8)
                    if c_resp.status_code == 200:
                        email = extract_email_from_text(c_resp.text)
                        if email:
                            return email
                except Exception:
                    continue
    except Exception:
        pass
    return None

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
    'visa agent': ('office', 'visa'),
    'visa agents': ('office', 'visa'),
    'visa agency': ('office', 'visa'),
    'visa agencies': ('office', 'visa'),
    'travel agent': ('shop', 'travel_agency'),
    'travel agents': ('shop', 'travel_agency'),
    'travel agency': ('shop', 'travel_agency'),
    'travel agencies': ('shop', 'travel_agency'),
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

def geocode_location(location_name, on_progress):
    url = f"https://nominatim.openstreetmap.org/search?q={urllib.parse.quote(location_name)}&format=json&limit=1"
    headers = {'User-Agent': 'LeadGeneratorApp/1.0 (hf@scrapping.local)'}
    try:
        resp = requests.get(url, headers=headers, timeout=10)
        if resp.status_code != 200:
            on_progress(f"Geocoding server returned HTTP status: {resp.status_code}")
            return None, None, None, None
        data = resp.json()
        if data:
            lat = float(data[0]['lat'])
            lon = float(data[0]['lon'])
            bbox = data[0].get('boundingbox')
            if bbox and len(bbox) == 4:
                bbox = [float(x) for x in bbox]
            
            osm_id = data[0].get('osm_id')
            osm_type = data[0].get('osm_type')
            area_id = None
            if osm_id and osm_type:
                if osm_type == 'relation':
                    area_id = 3600000000 + int(osm_id)
                elif osm_type == 'way':
                    area_id = 2400000000 + int(osm_id)
            return lat, lon, bbox, area_id
    except Exception as e:
        on_progress(f"Geocoding exception: {str(e)}")
    return None, None, None, None

def query_overpass(query_ql, on_progress):
    urls = [
        "https://overpass-api.de/api/interpreter",
        "https://lz4.overpass-api.de/api/interpreter",
        "https://z.overpass-api.de/api/interpreter",
        "https://overpass.kumi.systems/api/interpreter"
    ]
    
    headers = {'User-Agent': 'LeadForgeApp/1.0 (hf@scrapping.local)'}
    
    for url in urls:
        try:
            on_progress(f"Sending query to Overpass API mirror: {url}...")
            resp = requests.post(url, data={'data': query_ql}, headers=headers, timeout=60)
            if resp.status_code == 200:
                return resp.json()
            elif resp.status_code == 429:
                on_progress(f"Rate limit hit on {url}, trying next mirror...")
            else:
                on_progress(f"Error status code {resp.status_code} from {url}, trying next mirror...")
        except requests.exceptions.Timeout:
            on_progress(f"Timeout on mirror {url} (60s limit), trying next mirror...")
        except Exception as e:
            on_progress(f"Error connecting to mirror {url}: {str(e)}, trying next mirror...")
            
    return None

def scrape_osm(query, limit, on_progress):
    on_progress(f"Starting OpenStreetMap scraping for query: '{query}'...")
    category, location = parse_query(query)
    if not location:
        on_progress("Error: OSM scraping requires a location in the query (e.g. 'restaurants in Lahore').")
        return []
        
    lat, lon, bbox, area_id = geocode_location(location, on_progress)
    if not lat or not lon:
        on_progress(f"Error: Could not geocode location '{location}' using Nominatim.")
        return []
        
    on_progress(f"Geocoded '{location}' to coordinates: ({lat:.4f}, {lon:.4f})")
    
    # Map category
    tag_key, tag_val = OSM_TAGS.get(category, (None, None))
    
    if area_id:
        on_progress(f"Searching OSM tags inside area ID: {area_id}...")
        overpass_bbox = None
    elif bbox:
        overpass_bbox = f"{bbox[0]},{bbox[2]},{bbox[1]},{bbox[3]}"
        on_progress(f"Searching OSM tags within area boundary: {overpass_bbox}...")
    else:
        overpass_bbox = None
        on_progress(f"Searching OSM tags within 10km radius of ({lat:.4f}, {lon:.4f})...")

    if tag_key and tag_val:
        if area_id:
            query_parts = f"""
              node(area:{area_id})["{tag_key}"="{tag_val}"];
              way(area:{area_id})["{tag_key}"="{tag_val}"];
              relation(area:{area_id})["{tag_key}"="{tag_val}"];
            """
        elif overpass_bbox:
            query_parts = f"""
              node["{tag_key}"="{tag_val}"]({overpass_bbox});
              way["{tag_key}"="{tag_val}"]({overpass_bbox});
              relation["{tag_key}"="{tag_val}"]({overpass_bbox});
            """
        else:
            query_parts = f"""
              node["{tag_key}"="{tag_val}"](around:10000, {lat}, {lon});
              way["{tag_key}"="{tag_val}"](around:10000, {lat}, {lon});
              relation["{tag_key}"="{tag_val}"](around:10000, {lat}, {lon});
            """
    else:
        # Fallback multi-tag search for unmapped categories
        cat_underscored = category.replace(" ", "_")
        search_terms = list(set([category, cat_underscored]))
        
        clauses = []
        for term in search_terms:
            for key in ["amenity", "office", "shop", "craft"]:
                if area_id:
                    clauses.append(f'node(area:{area_id})["{key}"="{term}"];')
                    clauses.append(f'way(area:{area_id})["{key}"="{term}"];')
                    clauses.append(f'relation(area:{area_id})["{key}"="{term}"];')
                elif overpass_bbox:
                    clauses.append(f'node["{key}"="{term}"]({overpass_bbox});')
                    clauses.append(f'way["{key}"="{term}"]({overpass_bbox});')
                    clauses.append(f'relation["{key}"="{term}"]({overpass_bbox});')
                else:
                    clauses.append(f'node["{key}"="{term}"](around:10000, {lat}, {lon});')
                    clauses.append(f'way["{key}"="{term}"](around:10000, {lat}, {lon});')
                    clauses.append(f'relation["{key}"="{term}"](around:10000, {lat}, {lon});')
        query_parts = "\n".join(clauses)

    out_limit = max(150, limit * 10)
    query_ql = f"""
    [out:json][timeout:60];
    (
      {query_parts}
    );
    out center {out_limit};
    """
    
    try:
        data = query_overpass(query_ql, on_progress)
        if not data:
            on_progress("Error: All Overpass API mirrors failed or timed out. If you are searching in a very large region (like an entire country), please try narrowing down your query to a city or a more specific area (e.g., 'salons in London, UK' instead of 'salons in UK').")
            return []
        
        elements = data.get('elements', [])
        on_progress(f"Found {len(elements)} total matches in region. Processing...")
        
        daily_scraped = database.get_daily_scraped_count()
        daily_limit = int(database.get_setting('daily_limit', 25))
        remaining = daily_limit - daily_scraped
        if remaining <= 0:
            on_progress(f"Daily limit of {daily_limit} already reached today. Stopping.")
            return []
            
        saved_count = 0
        saved_leads = []
        for el in elements:
            if saved_count >= limit or saved_count >= remaining:
                break
                
            tags = el.get('tags', {})
            name = tags.get('name')
            if not name:
                continue
                
            website = tags.get('website') or tags.get('contact:website')
            phone = tags.get('phone') or tags.get('contact:phone') or tags.get('contact:mobile')
            email = tags.get('email') or tags.get('contact:email')
            
            # Form address
            street = tags.get('addr:street', '')
            housenumber = tags.get('addr:housenumber', '')
            suburb = tags.get('addr:suburb', '')
            city = tags.get('addr:city', location.capitalize())
            addr_parts = [p for p in [housenumber, street, suburb, city] if p]
            address = ", ".join(addr_parts) if addr_parts else location.capitalize()
            
            # Check website early to skip if not empty
            if website:
                cleaned_website = website.strip().lower()
                if cleaned_website not in ('none', 'null', ''):
                    on_progress(f"Skipped: **{name}** (has website: {website})")
                    continue

            # Try to visit business website if email not in tags and website is listed
            if not email and website:
                email = find_email_from_website_requests(website)
                
            # Check unique name & address and quality criteria
            eligible, reason = check_lead_eligibility(name, address, phone, email, website)
            if not eligible:
                on_progress(f"Skipped: **{name}** ({reason})")
                continue
                
            # SQLite insertion
            osm_url = f"https://www.openstreetmap.org/{el.get('type')}/{el.get('id')}"
            db_lead = database.insert_lead(
                name=name,
                address=address,
                phone=phone,
                website=website,
                category=category.capitalize(),
                query=query,
                google_maps_url=osm_url,
                email=email
            )
            
            if db_lead:
                saved_count += 1
                saved_leads.append(db_lead)
                on_progress(f"[{saved_count}] Saved: **{name}** | Phone: {phone or 'N/A'} | Website: {website or 'None'} | Email: {email or 'None'}")
                
        on_progress(f"OSM scraping complete. Saved {saved_count} new leads.")
        return saved_leads
        
    except Exception as e:
        on_progress(f"Error during OSM scraping: {str(e)}")
        return []


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
            headless=True,
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
        
        context.set_default_timeout(60000)
        context.set_default_navigation_timeout(90000)
        
        def route_intercept(route):
            # Unblocked "stylesheet" because Google Maps relies on it to render the feed container
            if route.request.resource_type in ["image", "font", "media"]:
                route.abort()
            else:
                route.continue_()
                
        context.route("**/*", route_intercept)
        
        page = context.new_page()
        
        # Inject standard stealth variables
        page.evaluate("() => { Object.defineProperty(navigator, 'webdriver', { get: () => undefined }) }")
        
        search_url = f"https://www.google.com/maps/search/{urllib.parse.quote_plus(query)}"
        on_progress(f"Navigating to search page...")
        
        for attempt in range(3):
            try:
                page.goto(search_url, timeout=90000)
                break
            except Exception as e:
                if attempt == 2:
                    raise e
                on_progress(f"Navigation failed, retrying ({attempt+1}/3)...")
                page.wait_for_timeout(3000)
        
        # Wait for results panel or single business view
        try:
            page.wait_for_selector('h1, a[href*="/maps/place/"]', timeout=60000)
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
                        
                # Check website early to skip if not empty
                if website:
                    cleaned_website = website.strip().lower()
                    if cleaned_website not in ('none', 'null', ''):
                        on_progress(f"Skipped: **{name}** (has website: {website})")
                        browser.close()
                        return 0

                # Try to extract email
                email = None
                try:
                    # 1. Check Google Maps page for mailto
                    mailto_el = page.locator('a[href^="mailto:"]')
                    if mailto_el.count() > 0:
                        href = mailto_el.first.get_attribute('href')
                        if href:
                            email = href.replace('mailto:', '').split('?')[0].strip()
                    # 2. Check page body text
                    if not email:
                        body_text = page.locator('body').inner_text()
                        email = extract_email_from_text(body_text)
                except Exception as e:
                    on_progress(f"Error checking Maps listing for email: {e}")

                # 3. Check website if listed and email not found yet
                if not email and website:
                    email = extract_email_from_website(context, website, on_progress)
                    
                eligible, reason = check_lead_eligibility(name, address, phone, email, website)
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
                    google_maps_url=page.url,
                    email=email
                )
                if db_id:
                    on_progress(f"Saved: **{name}** | Phone: {phone or 'N/A'} | Website: {website or 'None'} | Email: {email or 'None'}")
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
            page.wait_for_selector(feed_selector, timeout=60000)
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
                for attempt in range(3):
                    try:
                        page.goto(url, timeout=90000)
                        break
                    except Exception as e:
                        if attempt == 2:
                            raise e
                        on_progress(f"Navigation failed, retrying ({attempt+1}/3)...")
                        page.wait_for_timeout(3000)
                        
                # Wait for title
                page.wait_for_selector('h1', timeout=60000)
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
                    
                # Check website early to skip if not empty
                if website:
                    cleaned_website = website.strip().lower()
                    if cleaned_website not in ('none', 'null', ''):
                        on_progress(f"Skipped: **{name}** (has website: {website})")
                        continue

                # Try to extract email
                email = None
                try:
                    # 1. Check Google Maps page for mailto
                    mailto_el = page.locator('a[href^="mailto:"]')
                    if mailto_el.count() > 0:
                        href = mailto_el.first.get_attribute('href')
                        if href:
                            email = href.replace('mailto:', '').split('?')[0].strip()
                    # 2. Check page body text
                    if not email:
                        body_text = page.locator('body').inner_text()
                        email = extract_email_from_text(body_text)
                except Exception as e:
                    on_progress(f"Error checking Maps listing for email: {e}")

                # 3. Check website if listed and email not found yet
                if not email and website:
                    email = extract_email_from_website(context, website, on_progress)

                eligible, reason = check_lead_eligibility(name, address, phone, email, website)
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
                    google_maps_url=url,
                    email=email
                )
                
                if db_id:
                    saved_count += 1
                    on_progress(f"[{saved_count}] Saved: **{name}** | Phone: {phone or 'N/A'} | Website: {website or 'None'} | Email: {email or 'None'}")
                    
            except Exception as e:
                on_progress(f"Error scraping details for business {i+1}: {str(e)}")
                
        on_progress(f"Google Maps scraping complete. Saved {saved_count} new leads.")
        browser.close()
        return saved_count
