# src/merge.py
from typing import List, Dict, Any, Tuple
from datetime import date
import re

# ---------- constants ----------
EVENTS = {
    "Filing","Hearing","Order","Adjournment","Notice","Bail","Charge","Evidence",
    "Judgment","Application","Service","Settlement","Lease","Appeal","Event"
}

# ---------- helpers ----------
_ISO = re.compile(r"^\d{4}-\d{2}-\d{2}$")
_PNUM = re.compile(r"p\.(\d+)")
_WS = re.compile(r"\s+")
_ANALYSIS_CUES = (
    "it is observed", "it may be mentioned", "question whether",
    "we are unable to", "held that", "in our view", "it is obvious",
    "therefore", "consequently", "accordingly", "it follows that"
)

def _valid_iso(d: str) -> bool:
    if not d or not isinstance(d, str) or not _ISO.match(d):
        return False
    y, m, d2 = map(int, d.split("-"))
    try:
        date(y, m, d2)
        return True
    except Exception:
        return False

def _looks_like_analysis(text: str) -> bool:
    low = (text or "").lower()
    return any(k in low for k in _ANALYSIS_CUES)

def _page_num(page_section: str) -> int:
    m = _PNUM.search(page_section or "")
    return int(m.group(1)) if m else -1

def _norm_event(ev: str) -> str:
    ev = (ev or "").strip().title()
    return ev if ev in EVENTS else "Event"

def _clean_text(s: str, limit: int | None = None) -> str:
    s = (s or "").strip()
    s = _WS.sub(" ", s)
    if limit and len(s) > limit:
        s = s[:limit]
    return s

def _better(a: Dict[str, Any], b: Dict[str, Any]) -> Dict[str, Any]:
    """
    Choose the better row:
      1) higher _confidence wins (>= by 0.05)
      2) else longer DESCRIPTION wins
    """
    ca = float(a.get("_confidence", 0.0))
    cb = float(b.get("_confidence", 0.0))
    if abs(ca - cb) >= 0.05:
        return a if ca > cb else b
    return a if len(a.get("DESCRIPTION", "")) >= len(b.get("DESCRIPTION", "")) else b

# ---------- gating ----------
def should_send_to_llm(row: Dict[str, Any], threshold: float) -> bool:
    """
    Send to LLM only if:
      - row is NOT an analysis paragraph, AND
      - confidence < threshold OR (has_date XOR has_event)
    """
    if _looks_like_analysis(row.get("DESCRIPTION", "")):
        return False
    if row.get("_confidence", 0.0) < threshold:
        return True
    if bool(row.get("_has_date")) ^ bool(row.get("_has_event")):
        return True
    return False

# ---------- dedupe ----------
def dedupe_rows(rows: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """
    De-dup by (SOURCE, DATE, EVENT, page_num, first 100 chars of DESCRIPTION).
    Keeps first occurrence.
    """
    seen, out = set(), []
    for r in rows:
        key = (
            r.get("SOURCE", ""),
            r.get("DATE", ""),
            _norm_event(r.get("EVENT", "")),
            _page_num(r.get("PAGE/SECTION", "")),
            (r.get("DESCRIPTION", "") or "")[:100],
        )
        if key in seen:
            continue
        seen.add(key)
        out.append(r)
    return out

# ---------- merge ----------
def merge_preferring_confidence(rule_rows: List[Dict[str, Any]],
                                llm_rows: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """
    Merge rule + LLM rows:
      - Key = (SOURCE, DATE, EVENT, page_num)
      - Pick by confidence first, then by longer DESCRIPTION
      - Clean/normalize fields
      - Drop invalid dates at the end
    """
    def k_rule(r: Dict[str, Any]) -> Tuple[str, str, str, int]:
        return (
            r.get("SOURCE", ""),
            r.get("DATE", ""),
            _norm_event(r.get("EVENT", "")),
            _page_num(r.get("PAGE/SECTION", "")),
        )

    def k_llm(l: Dict[str, Any]) -> Tuple[str, str, str, int]:
        return (
            l.get("source", ""),
            l.get("date", ""),
            _norm_event(l.get("event", "")),
            _page_num(l.get("page_section", "")),
        )

    out: Dict[Tuple[str, str, str, int], Dict[str, Any]] = {}

    # Seed with rules
    for r in rule_rows:
        row = {
            "SOURCE": _clean_text(r.get("SOURCE", "")),
            "DATE": _clean_text(r.get("DATE", "")),
            "EVENT": _norm_event(r.get("EVENT", "")),
            "DESCRIPTION": _clean_text(r.get("DESCRIPTION", ""), 400),
            "PAGE/SECTION": _clean_text(r.get("PAGE/SECTION", "")),
            "_confidence": float(r.get("_confidence", 0.0)),
        }
        key = k_rule(row)
        cur = out.get(key)
        out[key] = row if cur is None else _better(cur, row)

    # Fold in LLM rows
    for l in llm_rows:
        row = {
            "SOURCE": _clean_text(l.get("source", "")),
            "DATE": _clean_text(l.get("date", "")),
            "EVENT": _norm_event(l.get("event", "")),
            "DESCRIPTION": _clean_text(l.get("description", ""), 400),
            "PAGE/SECTION": _clean_text(l.get("page_section", "")),
            "_confidence": 0.75,  # LLM default confidence
        }
        key = k_llm(l)
        cur = out.get(key)
        out[key] = row if cur is None else _better(cur, row)

    # Final pass: keep only valid ISO dates
    merged = [r for r in out.values() if _valid_iso(r.get("DATE", ""))]

    return merged
