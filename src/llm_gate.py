# src/llm_gate.py
import json
import os
from typing import List, Dict, Any
from pydantic import BaseModel, Field
import dateparser
import google.generativeai as genai

# ---- Canonical event labels ----
EVENTS = {
    "Filing", "Hearing", "Order", "Adjournment", "Notice", "Bail", "Charge",
    "Evidence", "Judgment", "Application", "Service", "Settlement",
    "Lease", "Appeal", "Event"
}

# ---- Pydantic models ----
class Row(BaseModel):
    date: str
    event: str
    description: str = Field(max_length=400)
    page_section: str
    source: str

class Rows(BaseModel):
    rows: List[Row]

# ---- Internal: Gemini call with structured JSON output ----
def _llm_complete(prompt: str, provider: str, model: str, schema: dict) -> str:
    """
    Calls Gemini with structured JSON output enforced via response_mime_type/response_schema.
    Returns a JSON string.
    """
    if provider.lower() != "gemini":
        raise RuntimeError(f"Unsupported LLM provider: {provider}")

    api_key = os.environ.get("GEMINI_API_KEY")
    if not api_key:
        raise RuntimeError("Missing GEMINI_API_KEY in environment variables.")

    genai.configure(api_key=api_key)

    # Enforce JSON & schema at generation time (Gemini supports this config)
    generation_config = {
        "response_mime_type": "application/json",
        "response_schema": schema,
        "temperature": 0.0,
    }

    model_obj = genai.GenerativeModel(model, generation_config=generation_config)
    resp = model_obj.generate_content(prompt)
    return resp.text  # already JSON text by contract

# ---- Public API used by cli.py ----
def extract_with_llm(chunk_text: str, page_section: str, source: str,
                     provider: str, model: str) -> List[Dict[str, Any]]:
    """
    Ask the LLM to extract rows from chunk_text.
    - Enforces JSON schema at decode time.
    - Repairs/normalizes date & event.
    - Skips rows without a valid date (no crashes).
    """
    # NOTE: Gemini's schema doesn't accept "maxLength", so we keep it simple and clamp in Python later.
    schema = {
        "type": "object",
        "properties": {
            "rows": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "date": {"type": "string"},
                        "event": {"type": "string"},
                        "description": {"type": "string"},
                        "page_section": {"type": "string"},
                        "source": {"type": "string"}
                    },
                    "required": ["date", "event", "description", "page_section", "source"]
                }
            }
        },
        "required": ["rows"]
    }

    prompt = f"""
You extract legal case events. STRICT RULES:
- Return ONLY rows that have an explicit date in the text.
- Normalize dates to YYYY-MM-DD if possible; if uncertain, keep the original date string.
- Keep description <= 2 lines and quote key phrase(s).
- Do not invent information not present in the text.
- If no dated events are found, return: {{"rows":[]}}.

Meta:
source: {source}
page_section: {page_section}

Text:
\"\"\"{chunk_text[:6000]}\"\"\"
"""

    # ---- Call Gemini and parse JSON ----
    try:
        raw = _llm_complete(prompt, provider, model, schema)
        data = json.loads(raw)  # should be valid JSON
    except Exception as e:
        print(f"[LLM ERROR] JSON/LLM call failed: {e}")
        return []

    # ---- Repair & normalize before Pydantic validation ----
    rows = data.get("rows", []) if isinstance(data, dict) else []
    repaired: List[Dict[str, Any]] = []

    for r in rows:
        # Coerce all fields to strings to avoid None/int surprises
        def as_str(x) -> str:
            return "" if x is None else str(x)

        # Use our meta (page_section/source) as the single truth
        r_page_section = page_section
        r_source = source

        r_date = as_str(r.get("date", "")).strip()
        r_event = as_str(r.get("event", "")).strip() or "Event"
        r_desc = as_str(r.get("description", "")).strip()

        # If date missing/empty: try to parse a date from the description
        if not r_date:
            dt_guess = dateparser.parse(r_desc, settings={"DATE_ORDER": "DMY"})
            if dt_guess:
                r_date = dt_guess.date().isoformat()

        # If still no date, skip this row
        if not r_date:
            continue

        # Normalize date to ISO if possible
        dt = dateparser.parse(r_date, settings={"DATE_ORDER": "DMY"})
        if dt:
            r_date = dt.date().isoformat()

        # Clamp event to known set
        if r_event not in EVENTS:
            r_event = "Event"

        # Enforce description length limit here
        if len(r_desc) > 400:
            r_desc = r_desc[:400]

        repaired.append({
            "date": r_date,
            "event": r_event,
            "description": r_desc,
            "page_section": r_page_section,
            "source": r_source
        })

    # ---- Validate with Pydantic (defensive) ----
    try:
        valid = Rows(rows=repaired).model_dump()["rows"]
    except Exception as e:
        print(f"[LLM ERROR] Validation failed after repair: {e}")
        # Fallback: keep only minimally valid rows
        valid = []
        for r in repaired:
            if r.get("date") and r.get("description"):
                valid.append(r)

    return valid
