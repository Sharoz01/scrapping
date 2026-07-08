import string
import os
import database

def load_env():
    env_path = "/Users/hf/Documents/scrapping/.env"
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

def generate_templated_proposal(lead, template):
    name = lead.get('name', 'Business Owner')
    category = lead.get('category', 'business')
    phone = lead.get('phone', '')
    address = lead.get('address', '')
    location = extract_location(address)
    
    # Safely format placeholders
    safe_data = SafeDict(
        name=name,
        category=category,
        location=location,
        phone=phone,
        address=address
    )
    
    if not template:
        template = "Hi {name},\n\nWe noticed your {category} business in {location} doesn't have a website yet. We'd love to help build one for you!\n\nBest,\nAccelerator Technologies"
        
    return template.format_map(safe_data)

def generate_ai_proposal(lead, api_key, provider="Gemini", language="English"):
    name = lead.get('name', 'Business Owner')
    category = lead.get('category', 'business')
    address = lead.get('address', '')
    location = extract_location(address)
    
    prompt = f"""You are a professional, friendly, and persuasive outreach copywriter working for "Accelerator Technologies".
Write a short, engaging, and highly personalized cold outreach message offering website design services to a local business that does NOT have a website yet.

Business Details:
- Name: {name}
- Category: {category}
- Location: {location}

Persuasive Message Structure (use this logic, but vary the wording slightly for each business to make every message unique and organic):
1. Greeting: A warm greeting (e.g. "Hi {name}!" or "Hello there,").
2. The Hook: Mention that you checked {category} online in {location} and noticed they don't have a website yet.
3. The Pain Point: Explain that customers searching Google for {category} in {location} are finding their competitors instead of them, meaning potential business is walking away every week for free.
4. The Solution: We build websites that fix exactly this. Offer to send a free mockup of what their website could look like, with no cost and no pressure.
5. Soft Call-to-Action: A brief, friendly question (e.g. "Interested?" or "Would you be open to seeing a quick concept?").
6. Sign-off: "Accelerator Technologies".

Requirements:
- Sound human-written, conversational, and helpful (NOT robotic or overly formal).
- Keep it short and concise (under 120 words), suitable for WhatsApp.
- Language: The response MUST be written entirely in {language}.
- WhatsApp formatting: Do NOT use markdown bolding (like **text**) or titles/headers. Keep it as plain text paragraphs. Emojis are allowed.
"""

    if provider == "Gemini":
        try:
            import google.generativeai as genai  # type: ignore
            genai.configure(api_key=api_key)
            model = genai.GenerativeModel('gemini-1.5-flash')
            response = model.generate_content(prompt)
            if response and response.text:
                return response.text.strip()
            raise Exception("Empty response from Gemini")
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
    
    # If the lead already has a custom proposal generated/saved, return it
    if lead.get('custom_proposal'):
        return lead['custom_proposal']
        
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
        
    return proposal_text
