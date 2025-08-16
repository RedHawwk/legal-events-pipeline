from typing import List, Dict, Any
import regex as rx
import dateparser
from .chunker import build_sections, section_for_index

def find_dates(unit: str, date_rx, dp_settings) -> List[str]:
    hits = set()
    for pat in date_rx:
        for m in pat.finditer(unit):
            s = m.group(0)
            dt = dateparser.parse(s,
                languages=dp_settings.get("languages", ["en"]),
                settings=dp_settings.get("settings", {"DATE_ORDER":"DMY"})
            )
            if dt:
                hits.add(dt.date().isoformat())
    return sorted(hits)

_STATUTE_CUES = ("act", "amendment", "section", "sub-section", "clause", "with effect from")

def detect_event_type(text: str, event_map) -> str | None:
    low = text.lower()
    # if it's clearly statutory context and not a court step, avoid mislabeling as Hearing/Order
    if any(k in low for k in _STATUTE_CUES) and not ("hearing" in low or "order" in low or "decree" in low or "judgment" in low):
        return None  # treat as non-event context
    for label, patterns in event_map.items():
        for pat in patterns:
            if pat.search(low):
                return label
    return None



def confidence_for(unit: str, event: str | None, dates: List[str], in_proceedings_section: bool) -> float:
    score = 0.0
    if event: score += 0.5
    if dates: score += 0.2
    if in_proceedings_section: score += 0.2
    if len(dates) > 1: score -= 0.1
    return max(0.0, min(1.0, score))

def parse_page(page: Dict[str,Any], cfg, section_rx, date_rx, event_map, dp_settings, line_as_boundary, delims) -> List[Dict[str,Any]]:
    out = []
    lines = page["lines"]
    sections = build_sections(lines, section_rx)
    for i, ln in enumerate(lines):
        units = [ln] if line_as_boundary else rx.split("["+rx.escape("".join(delims))+"]", ln)
        for u in [x.strip() for x in units if x.strip()]:
            dates = find_dates(u, date_rx, dp_settings)
            event = detect_event_type(u, event_map)
            if not dates and not event:
                continue
            section = section_for_index(sections, i)
            conf = confidence_for(u, event, dates, "proceeding" in section.lower() or "hearing" in section.lower())
            out.append({
                "DATE": (dates[0] if dates else ""),
                "EVENT": (event or "Event"),
                "DESCRIPTION": u,
                "PAGE/SECTION": f"p.{page['page']} / {section}",
                "SOURCE": "",
                "_confidence": conf,
                "_has_date": bool(dates),
                "_has_event": bool(event)
            })
    return out
