import string
import os
import requests
import database

def load_env():
    base_dir = os.path.dirname(os.path.abspath(__file__))
    env_path = os.path.join(base_dir, ".env")
    if os.path.exists(env_path):
        with open(env_path, 'r') as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith('#') and '=' in line:
                    key, val = line.split('=', 1)
                    # Clean quotes if any
                    val = val.strip().strip("'").strip('"')
                    os.environ[key.strip()] = val

# Load environment variables on module import
load_env()

class SafeDict(dict):
    def __missing__(self, key):
        return '{' + key + '}'

def extract_location(address):
    if not address:
        return "your area"
    parts = [p.strip() for p in address.split(',') if p.strip()]
    # Typically the structure is: Street, Suburb, City, Country
    # Let's try to get city (often second to last or last component)
    if len(parts) >= 2:
        # Ignore postcode-only parts or country-only parts at the end if possible
        last = parts[-1].lower()
        if last in ('pakistan', 'pk', 'india', 'in', 'usa', 'us', 'uk', 'canada'):
            return parts[-2]
        return parts[-1]
    return parts[0] if parts else "your area"

def extract_category_from_query(query, default_category):
    if not query:
        return default_category
    query_lower = query.strip().lower()
    if " in " in query_lower:
        return query_lower.split(" in ")[0].strip()
    if " near " in query_lower:
        return query_lower.split(" near ")[0].strip()
    return query_lower

def generate_templated_proposal(lead, template):
    name = lead.get('name', 'Business Owner')
    category = lead.get('category', 'business')
    query = lead.get('query', '')
    website_status = lead.get('website_status', 'No Website')
    
    if category.lower() in ["local business", "business"]:
        category = extract_category_from_query(query, category)
        
    phone = lead.get('phone', '')
    address = lead.get('address', '')
    location = extract_location(address)
    
    safe_data = SafeDict(
        name=name,
        category=category,
        location=location,
        phone=phone,
        address=address,
        website_status=website_status
    )
    
    if not template:
        if website_status in ("Unresponsive Website", "Outdated Website"):
            template = "Hi {name},\n\nWe checked your {category} website in {location} on mobile devices and noticed it's not fully responsive or mobile-friendly. A smooth mobile redesign could double your client inquiries!\n\nBest,\nAccelerator Technologies"
        else:
            template = "Hi {name},\n\nWe noticed your {category} business in {location} doesn't have a website yet. We'd love to help build one for you!\n\nBest,\nAccelerator Technologies"
        
    return template.format_map(safe_data)

def generate_ai_proposal(lead, api_key, provider="Gemini", language="English"):
    name = lead.get('name', 'Business Owner')
    category = lead.get('category', 'business')
    query = lead.get('query', '')
    website_status = lead.get('website_status', 'No Website')
    website = lead.get('website', '')
    
    if category.lower() in ["local business", "business"]:
        category = extract_category_from_query(query, category)
        
    address = lead.get('address', '')
    location = extract_location(address)
    
    if website_status in ("Unresponsive Website", "Outdated Website") and website:
        status_context = f"The business has an existing website ({website}), BUT it is NOT mobile-responsive and has bad mobile usability. Offer a fast, mobile-friendly redesign that turns mobile visitors into calling customers."
    else:
        status_context = "The business currently has NO website. Offer to build their very first modern, high-converting website."

    prompt = f"""Write a short, highly creative, organic, and human-written cold outreach WhatsApp message offering web design / redesign services to {name} (Category: {category}, Location: {location}).

WEBSITE AUDIT CONTEXT:
{status_context}

IMPORTANT CREATIVE REQUIREMENTS:
- Make this message completely UNIQUE, organic, and tailored specifically to a {category} business in {location}.
- DO NOT use generic robotic template structures or numbered bullet steps.
- Focus on how a modern mobile-responsive website brings in more local {category} calls, jobs, or clients every week.
- Vary the opening line, tone, and specific niche references (e.g. mention emergency calls for plumbers/electricians, direct loads for trucking, online booking for dentists/salons).
- Keep it under 100 words, friendly conversational tone, with a soft casual question at the end.
- Language: The response MUST be written entirely in {language}.
- Sign off as "Accelerator Technologies".
- WhatsApp formatting: Do NOT use markdown headers or bolding (**text**). Keep as natural plain text paragraphs with emojis.
"""

    if provider == "Gemini":
        try:
            models_to_try = ['gemini-3.5-flash', 'gemini-3.6-flash', 'gemini-flash-latest']
            last_err = None
            for m in models_to_try:
                try:
                    url = f"https://generativelanguage.googleapis.com/v1beta/models/{m}:generateContent?key={api_key}"
                    payload = {
                        "contents": [{"parts": [{"text": prompt}]}],
                        "generationConfig": {
                            "temperature": 0.9,
                            "topP": 0.95
                        }
                    }
                    resp = requests.post(url, json=payload, timeout=8)
                    if resp.status_code == 200:
                        res_json = resp.json()
                        if "candidates" in res_json and len(res_json["candidates"]) > 0:
                            parts = res_json["candidates"][0]["content"]["parts"]
                            if parts and "text" in parts[0]:
                                return parts[0]["text"].strip()
                    else:
                        err_msg = resp.json().get("error", {}).get("message", f"HTTP {resp.status_code}")
                        last_err = f"{m}: {err_msg}"
                except Exception as ex:
                    last_err = str(ex)
                    continue
            raise Exception(f"All Gemini models failed ({last_err})")
        except Exception as e:
            return f"Error generating Gemini proposal: {str(e)}\n\n(Fallback Template Message):\n"
            
    elif provider == "OpenAI":
        try:
            from openai import OpenAI  # type: ignore
            client = OpenAI(api_key=api_key)
            completion = client.chat.completions.create(
                model="gpt-4o-mini",
                messages=[
                    {"role": "system", "content": "You are a professional marketing copywriter writing WhatsApp outreach messages."},
                    {"role": "user", "content": prompt}
                ],
                max_tokens=250,
                temperature=0.7
            )
            if completion.choices and completion.choices[0].message.content:
                return completion.choices[0].message.content.strip()
            raise Exception("Empty response from OpenAI")
        except Exception as e:
            return f"Error generating OpenAI proposal: {str(e)}\n\n(Fallback Template Message):\n"
            
    return ""

def get_proposal_for_lead(lead):
    # Fetch settings
    settings = database.get_all_settings()
    use_ai = settings.get('use_ai', 'False') == 'True'
    lang = settings.get('proposal_language', 'English')
    
    # If the lead already has a user-edited custom proposal (and not an error or tag), return it
    cp = lead.get('custom_proposal')
    if cp and not cp.startswith('Error generating') and not cp.startswith('[EMAIL:') and '404' not in cp:
        return cp
        
    proposal_text = ""
    if use_ai:
        provider = settings.get('ai_provider', 'Gemini')
        api_key = settings.get('gemini_api_key', '') if provider == 'Gemini' else settings.get('openai_api_key', '')
        
        # Fallback to env variable if not found in db settings
        if not api_key:
            env_var_name = 'GEMINI_API_KEY' if provider == 'Gemini' else 'OPENAI_API_KEY'
            api_key = os.getenv(env_var_name, '')
            
        if api_key:
            ai_msg = generate_ai_proposal(lead, api_key, provider, lang)
            if "Error generating" in ai_msg:
                # If AI fails, use templated fallback
                tpl = settings.get('proposal_template_urdu') if lang == 'Urdu' else settings.get('proposal_template')
                proposal_text = ai_msg + generate_templated_proposal(lead, tpl)
            else:
                proposal_text = ai_msg
        else:
            # Fallback if AI enabled but no API key configured
            tpl = settings.get('proposal_template_urdu') if lang == 'Urdu' else settings.get('proposal_template')
            proposal_text = "AI API key missing in settings/environment. " + generate_templated_proposal(lead, tpl)
    else:
        # Standard Template Mode
        tpl = settings.get('proposal_template_urdu') if lang == 'Urdu' else settings.get('proposal_template')
        proposal_text = generate_templated_proposal(lead, tpl)
        
    if proposal_text and lead.get('id') and not proposal_text.startswith('Error generating'):
        try:
            database.update_custom_proposal(lead['id'], proposal_text)
        except Exception:
            pass
            
    return proposal_text
