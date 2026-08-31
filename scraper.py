import os
import time
import random
import urllib.parse
import re
import requests
import urllib3
import database

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

def check_lead_eligibility(name, address, phone, email, website, require_no_website=False, website_status=None):
    # Enforce quality filters:
    # 1. If require_no_website is True, target leads must have No Website OR Unresponsive/Outdated Website
    if require_no_website and website and website_status not in ('No Website', 'Unresponsive Website', 'Outdated Website'):
        cleaned_website = website.strip().lower()
        if cleaned_website not in ('none', 'null', ''):
            return False, f"has fully responsive website: {website}"
            
    # 2. Must have AT LEAST ONE contact vector: phone, email, or website
    has_phone = phone and phone.strip().lower() not in ('none', 'null', '', 'n/a')
    has_email = email and email.strip().lower() not in ('none', 'null', '')
    has_website = website and website.strip().lower() not in ('none', 'null', '')
    
    if not has_phone and not has_email and not has_website:
        return False, "no phone, email, or website contact details found"
        
    if database.lead_exists(name, address):
        return False, "already exists in database"
        
    return True, ""

def evaluate_website_responsiveness(website, context=None, on_progress=None):
    if on_progress is None:
        on_progress = lambda m: None

    if not website or str(website).strip().lower() in ('none', 'null', '', 'n/a'):
        return "No Website"

    url = website if website.startswith(('http://', 'https://')) else 'http://' + website

    # HTTP scan check for viewport meta & responsive CSS
    try:
        headers = {'User-Agent': 'Mozilla/5.0 (iPhone; CPU iPhone OS 16_6 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/16.6 Mobile/15E148 Safari/604.1'}
        r = requests.get(url, headers=headers, timeout=8, verify=False)
        if r.status_code != 200:
            on_progress(f"Website reachability status {r.status_code} for {url} -> Unresponsive Website")
            return "Unresponsive Website"
        
        html = r.text
        html_lower = html.lower()
        
        has_viewport = bool(re.search(r'<meta[^>]+name=["\']viewport["\'][^>]*>', html, re.IGNORECASE))
        has_responsive_meta = 'width=device-width' in html_lower or 'initial-scale=1' in html_lower
        has_responsive_css = any(k in html_lower for k in ['@media', 'flex', 'grid', 'bootstrap', 'tailwind', 'viewport'])
        
        if not has_viewport and not has_responsive_meta:
            on_progress(f"Website {url} missing viewport meta tag -> Unresponsive Website")
            return "Unresponsive Website"
            
        if not has_responsive_css and len(html) > 500:
            return "Outdated Website"
            
    except Exception as e:
        on_progress(f"Website connection failed for {url}: {e} -> Unresponsive Website")
        return "Unresponsive Website"

    # Playwright layout width test if context provided
    if context:
        p_page = None
        try:
            p_page = context.new_page()
            p_page.set_viewport_size({"width": 375, "height": 667})
            p_page.goto(url, timeout=12000, wait_until="domcontentloaded")
            
            has_overflow = p_page.evaluate("() => document.documentElement.scrollWidth > window.innerWidth + 15")
            if has_overflow:
                on_progress(f"Website {url} has mobile layout horizontal overflow -> Unresponsive Website")
                return "Unresponsive Website"
        except Exception:
            pass
        finally:
            if p_page:
                try: p_page.close()
                except: pass

    return "Responsive Website"

def decode_cf_email(cfemail):
    try:
        r = int(cfemail[:2], 16)
        return ''.join([chr(int(cfemail[i:i+2], 16) ^ r) for i in range(2, len(cfemail), 2)])
    except Exception:
        return None

def extract_email_from_text(text):
    if not text:
        return None
    email_pattern = r'[a-zA-Z0-9][a-zA-Z0-9._%-]*@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}'
    emails = re.findall(email_pattern, text)
    for email in emails:
        email_clean = email.strip().strip('.')
        email_lower = email_clean.lower()
        
        if '%3a' in email_lower or '%2f' in email_lower or 'http' in email_lower or '%20' in email_lower or 'ajax.st' in email_lower or 'e.update' in email_lower or 'duckduckgo' in email_lower or 'h.round' in email_lower or 'window.' in email_lower or 'pointer' in email_lower or 'navig' in email_lower or 'transl' in email_lower or 'form.twitter' in email_lower:
            continue
            
        invalid_extensions = ['.png', '.jpg', '.jpeg', '.gif', '.svg', '.webp', '.css', '.js', '.ts', '.round']
        invalid_domains = ['example.com', 'sentry.io', 'w3.org', 'bootstrap.com', 'jquery.com', 'google.com', 'googleapis.com', 'github.com', 'schema.org', 'ion.href', 'location.href', 'domain.com', 'email.com', 'yourdomain.com', 'sitenow.com', 'duckduckgo.com', 'bing.com', 'microsoft.com', 'e.update', 'h.round', 'or.pointerenabled', 'microsofttransl', 'twitter.com', 'facebook.com', 'instagram.com', 'linkedin.com', 'youtube.com', 'form.twitter.com']
        
        parts = email_lower.split('@')
        if len(parts) != 2 or len(parts[0]) < 2 or len(parts[1]) < 3:
            continue
            
        u, d = parts[0], parts[1]
        if u in ('location', 'loc', 'window', 'href', 'script', 'document', 'st', 'm', 'navig', 'microsoft') or 'replace' in d or 'href' in d or 'location' in d or 'ion.' in d or 'update' in d or 'round' in d or 'pointer' in d or 'transl' in d or 'twitter' in d:
            continue
            
        if any(email_lower.endswith(ext) for ext in invalid_extensions):
            continue
        if any(domain in email_lower for domain in invalid_domains):
            continue
            
        return email_clean
    return None

def extract_phone_from_text(text):
    if not text:
        return None
    patterns = [
        r'(\+\d{1,3}[\s.-]?\(?\d{1,4}\)?[\s.-]?\d{3,4}[\s.-]?\d{3,4})',
        r'(\(?\d{3}\)?[\s.-]?\d{3}[\s.-]?\d{4})',
        r'(\+?\d{10,14})'
    ]
    for p in patterns:
        matches = re.findall(p, text)
        for m in matches:
            clean = re.sub(r'[^\d+]', '', m)
            if len(clean) >= 7:
                return m.strip()
    return None

def extract_email_from_raw_html(html):
    if not html:
        return None
    # 1. Cloudflare protected email decoding
    cf_matches = re.findall(r'data-cfemail=["\']([a-fA-F0-9]+)["\']', html)
    for cf in cf_matches:
        dec = decode_cf_email(cf)
        if dec and '@' in dec:
            clean = extract_email_from_text(dec)
            if clean:
                return clean
    # 2. Mailto links
    mailto_matches = re.findall(r'href=["\']mailto:([^"?\'\s]+)', html, re.IGNORECASE)
    for m in mailto_matches:
        clean = extract_email_from_text(m)
        if clean:
            return clean
    # 3. Obfuscated email patterns (e.g. info [at] domain.com, contact (at) domain.com)
    obf = re.findall(r'([a-zA-Z0-9._%+-]+)\s*\[?\s*(?:at|@|\(at\))\s*\]?\s*([a-zA-Z0-9.-]+\.[a-zA-Z]{2,})', html, re.IGNORECASE)
    for u, d in obf:
        clean = extract_email_from_text(f'{u}@{d}')
        if clean:
            return clean
    # 4. Standard text extract
    return extract_email_from_text(html)

import base64

def unwrap_search_url(url):
    if not url:
        return None
    if 'bing.com/ck/a' in url and '&u=a1' in url:
        try:
            b64_part = url.split('&u=a1')[1].split('&')[0]
            b64_part += '=' * (-len(b64_part) % 4)
            return base64.b64decode(b64_part).decode('utf-8', errors='ignore')
        except Exception:
            pass
    if '/url?q=' in url:
        try:
            return urllib.parse.unquote(url.split('/url?q=')[1].split('&')[0])
        except Exception:
            pass
    return url

def find_business_email(context, website, name=None, address=None, on_progress=None):
    if on_progress is None:
        on_progress = lambda m: None

    # Layer 1: Fast HTTP Requests scan with SSL bypass & custom User Agent
    if website and website.strip().lower() not in ('none', 'null', ''):
        url = website if website.startswith(('http://', 'https://')) else 'http://' + website
        headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'}
        try:
            r = requests.get(url, headers=headers, timeout=8, verify=False)
            if r.status_code == 200:
                email = extract_email_from_raw_html(r.text)
                if email:
                    on_progress(f"Found email via website scan: {email}")
                    return email
                # Search contact subpages
                links = re.findall(r'href=["\']([^"\'\s]*(?:contact|about|touch|connect|reach|team)[^"\'\s]*)["\']', r.text, re.IGNORECASE)
                for link in links[:4]:
                    c_url = urllib.parse.urljoin(url, link)
                    try:
                        cr = requests.get(c_url, headers=headers, timeout=6, verify=False)
                        if cr.status_code == 200:
                            c_email = extract_email_from_raw_html(cr.text)
                            if c_email:
                                on_progress(f"Found email on contact page ({link}): {c_email}")
                                return c_email
                    except Exception:
                        pass
        except Exception:
            pass

    # Layer 2: Playwright scan fallback if website is present and HTTP scan didn't find it
    if context and website and website.strip().lower() not in ('none', 'null', ''):
        try:
            email = extract_email_from_website(context, website, on_progress)
            if email:
                return email
        except Exception:
            pass

    # Layer 3: Bing Web Search & Redirect Unwrapping Fallback for Business Email
    if name or website:
        try:
            domain = None
            if website and website.strip().lower() not in ('none', 'null', ''):
                domain = urllib.parse.urlparse(website if website.startswith('http') else 'http://' + website).netloc.replace('www.', '').strip()
            
            q_term = f'site:{domain} "@"' if domain else f'"{name}" email contact'
            b_url = f'https://www.bing.com/search?q={urllib.parse.quote(q_term)}'
            headers = {'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'}
            br = requests.get(b_url, headers=headers, timeout=8)
            if br.status_code == 200:
                e = extract_email_from_raw_html(br.text)
                if e:
                    on_progress(f"Found public email via web search snippet: {e}")
                    return e
                
                # Check candidate result URLs by unwrapping Bing redirect links
                raw_links = re.findall(r'href=["\'](https?://[^"\'\s]+)', br.text)
                for raw_l in raw_links[:8]:
                    clean_l = unwrap_search_url(raw_l)
                    if clean_l and not any(ign in clean_l.lower() for ign in ['bing.com', 'microsoft.com', 'msn.com', 'youtube.com', 'facebook.com', 'instagram.com', 'wikipedia.org', 'yelp.com']):
                        # Visit candidate website for contact details
                        c_email = find_business_email(context, clean_l, on_progress=on_progress)
                        if c_email:
                            on_progress(f"Found public email on candidate website ({clean_l}): {c_email}")
                            return c_email
        except Exception:
            pass

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
    'dental': ('amenity', 'dentist'),
    'clinic': ('amenity', 'clinic'),
    'clinics': ('amenity', 'clinic'),
    'doctor': ('amenity', 'doctors'),
    'doctors': ('amenity', 'doctors'),
    'hotel': ('tourism', 'hotel'),
    'hotels': ('tourism', 'hotel'),
    'gym': ('leisure', 'fitness_centre'),
    'gyms': ('leisure', 'fitness_centre'),
    'fitness': ('leisure', 'fitness_centre'),
    'salon': ('shop', 'hairdresser'),
    'salons': ('shop', 'hairdresser'),
    'beauty': ('shop', 'beauty'),
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
    'agency': ('office', 'company'),
    'agencies': ('office', 'company'),
    'lawyer': ('office', 'lawyer'),
    'lawyers': ('office', 'lawyer'),
    'accountant': ('office', 'accountant'),
    'accountants': ('office', 'accountant'),
    'real estate': ('office', 'estate_agent'),
    'car repair': ('shop', 'car_repair'),
    'auto repair': ('shop', 'car_repair'),
}

def extract_phone_number(page):
    selectors = [
        '[data-item-id^="phone:tel:"]',
        '[data-item-id*="phone"]',
        'button[jsaction*="phone"]',
        'a[href^="tel:"]',
        'button[aria-label^="Phone:"]',
        'button[aria-label*="Phone"]',
        'button[aria-label*="phone"]',
        'div[aria-label*="Phone"]',
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
    query = query.strip()
    query_lower = query.lower()
    
    for prep in [" in ", " at ", " near ", " around ", " - "]:
        if prep in query_lower:
            parts = query_lower.split(prep, 1)
            return parts[0].strip(), parts[1].strip()
            
    words = query.split()
    if len(words) >= 2:
        category = " ".join(words[:-1]).strip()
        location = words[-1].strip()
        return category, location
        
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

def scrape_osm(query, limit, on_progress, user_id=None, user_name=None):
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
    
    # Map category (check full phrase first, then individual words)
    tag_key, tag_val = OSM_TAGS.get(category, (None, None))
    if not tag_key:
        for word in category.split():
            if word in OSM_TAGS:
                tag_key, tag_val = OSM_TAGS[word]
                break
    
    # Use 15km radius around geocoded coordinates for reliable local results
    query_parts = ""
    if tag_key and tag_val:
        query_parts = f"""
          node["{tag_key}"="{tag_val}"](around:15000, {lat}, {lon});
          way["{tag_key}"="{tag_val}"](around:15000, {lat}, {lon});
          relation["{tag_key}"="{tag_val}"](around:15000, {lat}, {lon});
        """
    else:
        # Fallback search checking multiple keys for all words in query
        words = list(set(category.split()))
        clauses = []
        for word in words:
            for key in ["amenity", "office", "shop", "craft", "healthcare", "tourism", "leisure"]:
                clauses.append(f'node["{key}"="{word}"](around:15000, {lat}, {lon});')
                clauses.append(f'way["{key}"="{word}"](around:15000, {lat}, {lon});')
                clauses.append(f'relation["{key}"="{word}"](around:15000, {lat}, {lon});')
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
            
        require_no_website = str(database.get_setting('filter_no_website', 'false')).lower() == 'true'
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
            
            website_status = evaluate_website_responsiveness(website, on_progress=on_progress)

            # Try to visit business website if email not in tags and website is listed
            if not email and website:
                email = find_email_from_website_requests(website)
                
            # Check unique name & address and quality criteria
            eligible, reason = check_lead_eligibility(name, address, phone, email, website, require_no_website=require_no_website, website_status=website_status)
            if not eligible:
                on_progress(f"Skipped: **{name}** ({reason})")
                continue
                
            # SQLite / Supabase insertion
            osm_url = f"https://www.openstreetmap.org/{el.get('type')}/{el.get('id')}"
            db_lead = database.insert_lead(
                name=name,
                address=address,
                phone=phone,
                website=website,
                website_status=website_status,
                category=category.capitalize(),
                query=query,
                google_maps_url=osm_url,
                email=email,
                user_id=user_id,
                user_name=user_name
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


def scrape_bing_maps(query, limit, headless, on_progress, user_id=None, user_name=None):
    on_progress("Launching Bing Maps scraper (Playwright)...")
    
    daily_scraped = database.get_daily_scraped_count()
    daily_limit = int(database.get_setting('daily_limit', 1000))
    remaining = daily_limit - daily_scraped
    if remaining <= 0:
        on_progress(f"Daily limit of {daily_limit} already reached today. Stopping.")
        return 0
        
    to_scrape_count = min(limit, remaining)
    require_no_website = str(database.get_setting('filter_no_website', 'false')).lower() == 'true'
    
    from playwright.sync_api import sync_playwright
    saved_count = 0
    
    with sync_playwright() as p:
        browser = p.chromium.launch(
            headless=headless,
            args=[
                "--disable-blink-features=AutomationControlled",
                "--no-sandbox",
                "--disable-infobars",
                "--window-size=1280,800"
            ]
        )
        
        context = browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            viewport={'width': 1280, 'height': 800}
        )
        
        context.set_default_timeout(45000)
        context.set_default_navigation_timeout(60000)
        
        page = context.new_page()
        page.evaluate("() => { Object.defineProperty(navigator, 'webdriver', { get: () => undefined }) }")
        
        bing_maps_url = f"https://www.bing.com/maps/search?q={urllib.parse.quote(query)}"
        on_progress(f"Navigating to Bing Maps search page: {bing_maps_url}...")
        
        try:
            page.goto(bing_maps_url, timeout=60000, wait_until="domcontentloaded")
            page.wait_for_timeout(4000)
        except Exception as e:
            on_progress(f"Navigation to Bing Maps search page failed ({e}), trying standard search...")
            bing_maps_url = f"https://www.bing.com/maps?q={urllib.parse.quote(query)}"
            try:
                page.goto(bing_maps_url, timeout=60000, wait_until="domcontentloaded")
                page.wait_for_timeout(4000)
            except Exception as ex:
                on_progress(f"Bing navigation failed: {ex}")
                browser.close()
                return 0
                
        on_progress("Scanning Bing Maps business listings...")
        
        valid_cards = []
        card_selectors = [
            '.overlay-task-item',
            'div[data-tag="task-item"]',
            'li.b_algo',
            '.b_place_item',
            'div.task-item',
            'div[role="listitem"]',
            'li[role="listitem"]',
            '.b_mop'
        ]
        
        for sel in card_selectors:
            try:
                els = page.locator(sel).all()
                for el in els:
                    txt = el.inner_text().strip()
                    if txt and len(txt) > 5:
                        first_line = txt.split('\n')[0].strip()
                        if first_line.lower() not in ('dentists', 'restaurants', 'search', 'bing', 'maps', 'directions', 'feedback', 'privacy', 'terms', 'help', 'results'):
                            valid_cards.append((first_line, el))
                if valid_cards:
                    break
            except Exception:
                continue
                
        if not valid_cards:
            headings = page.locator('h2, h3').all()
            ignored_titles = {'dentists', 'restaurants', 'search', 'bing', 'maps', 'directions', 'feedback', 'privacy', 'terms', 'help', 'results'}
            for h in headings:
                try:
                    title = h.inner_text().strip()
                    if not title or title.lower() in ignored_titles or len(title) < 2:
                        continue
                    parent = h.locator('xpath=ancestor::*[contains(@class, "task-item") or contains(@class, "b_algo") or contains(@class, "b_place_item")][1]')
                    if parent.count() > 0:
                        valid_cards.append((title, parent.first))
                except Exception:
                    continue

        if not valid_cards:
            on_progress("No business listings found on Bing Maps for this query.")
            browser.close()
            return 0
            
        on_progress(f"Found {len(valid_cards)} business candidates on Bing Maps. Processing up to {to_scrape_count} leads...")
        
        for i, (name, card) in enumerate(valid_cards):
            if saved_count >= to_scrape_count:
                break
                
            try:
                card_text = card.inner_text()
                lines = [line.strip() for line in card_text.split('\n') if line.strip()]
                
                # Extract address
                address = None
                try:
                    addr_el = card.locator('.overlay-task-address, [data-tag="address"], .b_address, address').first
                    if addr_el.count() > 0:
                        address = addr_el.inner_text().strip()
                    elif len(lines) > 1:
                        for line in lines[1:]:
                            if any(char.isdigit() for char in line) and (',' in line or 'st' in line.lower() or 'rd' in line.lower() or 'ave' in line.lower() or 'road' in line.lower()):
                                address = line
                                break
                except Exception:
                    pass
                    
                # Extract phone
                phone = None
                try:
                    phone_el = card.locator('a[href^="tel:"], .overlay-task-phone, [data-tag="phone"]').first
                    if phone_el.count() > 0:
                        phone = phone_el.inner_text().strip()
                        href = phone_el.get_attribute('href')
                        if href and href.startswith('tel:'):
                            phone = href.replace('tel:', '').strip()
                except Exception:
                    pass
                    
                if not phone:
                    phone = extract_phone_from_text(card_text)

                # Extract website URL
                website = None
                try:
                    links = card.locator('a[href^="http"]').all()
                    for link in links:
                        href = link.get_attribute('href')
                        if href and not any(ignored in href.lower() for ignored in ['bing.com', 'microsoft.com', 'msn.com', 'javascript:', 'maplibre.org']):
                            website = href
                            break
                except Exception:
                    pass
                    
                category = "Local Business"
                if len(lines) > 1 and len(lines[1]) < 25 and not any(char.isdigit() for char in lines[1]):
                    category = lines[1]

                website_status = evaluate_website_responsiveness(website, context=context, on_progress=on_progress)

                # Extract email
                email = extract_email_from_text(card_text)
                if not email:
                    email = find_business_email(context, website, name=name, address=address, on_progress=on_progress)

                # Quality filter check
                eligible, reason = check_lead_eligibility(name, address, phone, email, website, require_no_website=require_no_website, website_status=website_status)
                if not eligible:
                    on_progress(f"Skipped: **{name}** ({reason})")
                    continue

                card_url = f"https://www.bing.com/maps?q={urllib.parse.quote(name + ' ' + (address or ''))}"
                db_id = database.insert_lead(
                    name=name,
                    address=address,
                    phone=phone,
                    website=website,
                    website_status=website_status,
                    category=category,
                    query=query,
                    google_maps_url=card_url,
                    email=email,
                    user_id=user_id,
                    user_name=user_name
                )

                if db_id:
                    saved_count += 1
                    on_progress(f"[{saved_count}] Saved Bing Lead: **{name}** | Phone: {phone or 'N/A'} | Website: {website or 'None'} | Email: {email or 'None'}")

            except Exception as e:
                on_progress(f"Error parsing Bing listing item {i+1}: {e}")

        on_progress(f"Bing Maps scraping complete. Saved {saved_count} new leads.")
        browser.close()
        return saved_count


def scrape_google_maps(query, limit, headless, on_progress, user_id=None, user_name=None):
    on_progress("Launching Google Maps scraper (Playwright)...")
    
    daily_scraped = database.get_daily_scraped_count()
    daily_limit = int(database.get_setting('daily_limit', 1000))
    remaining = daily_limit - daily_scraped
    if remaining <= 0:
        on_progress(f"Daily limit of {daily_limit} already reached today. Stopping.")
        return 0
        
    to_scrape_count = min(limit, remaining)
    require_no_website = str(database.get_setting('filter_no_website', 'false')).lower() == 'true'
    
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
                        
                website_status = evaluate_website_responsiveness(website, context=context, on_progress=on_progress)

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

                # 3. Deep business email scan
                if not email:
                    email = find_business_email(context, website, name=name, address=address, on_progress=on_progress)
                    
                eligible, reason = check_lead_eligibility(name, address, phone, email, website, require_no_website=require_no_website, website_status=website_status)
                if not eligible:
                    on_progress(f"Skipped: **{name}** ({reason})")
                    browser.close()
                    return 0
                    
                db_id = database.insert_lead(
                    name=name,
                    address=address,
                    phone=phone,
                    website=website,
                    website_status=website_status,
                    category=category,
                    query=query,
                    google_maps_url=page.url,
                    email=email,
                    user_id=user_id,
                    user_name=user_name
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
        
        target_candidate_count = max(to_scrape_count * 3, 20)
        while len(place_urls) < target_candidate_count and no_new_urls_loops < 10:
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
                
            page.wait_for_timeout(1000)
            
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
                
            delay = random.randint(1, 3)
            on_progress(f"[{saved_count+1}/{to_scrape_count}] Loading business details ({i+1}/{len(new_urls)})...")
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
                        page.wait_for_timeout(2000)
                        
                # Wait for title
                page.wait_for_selector('h1', timeout=60000)
                page.wait_for_timeout(1000) # Render delay for sub-elements
                
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
                    
                website_status = evaluate_website_responsiveness(website, context=context, on_progress=on_progress)

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

                # 3. Deep email scan
                if not email:
                    email = find_business_email(context, website, name=name, address=address, on_progress=on_progress)

                eligible, reason = check_lead_eligibility(name, address, phone, email, website, require_no_website=require_no_website, website_status=website_status)
                if not eligible:
                    on_progress(f"Skipped: **{name}** ({reason})")
                    continue

                db_id = database.insert_lead(
                    name=name,
                    address=address,
                    phone=phone,
                    website=website,
                    website_status=website_status,
                    category=category,
                    query=query,
                    google_maps_url=url,
                    email=email,
                    user_id=user_id,
                    user_name=user_name
                )
                
                if db_id:
                    saved_count += 1
                    on_progress(f"[{saved_count}] Saved: **{name}** | Phone: {phone or 'N/A'} | Website: {website or 'None'} | Email: {email or 'None'}")
                    
            except Exception as e:
                on_progress(f"Error scraping details for business {i+1}: {str(e)}")
                
        on_progress(f"Google Maps scraping complete. Saved {saved_count} new leads.")
        browser.close()
        return saved_count
