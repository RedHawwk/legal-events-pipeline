from typing import List, Dict, Any
import re
from pathlib import Path

def extract_txt(path: str) -> List[Dict[str, Any]]:
    txt = Path(path).read_text(encoding="utf-8", errors="ignore")
    raw_lines = [ln.strip() for ln in txt.splitlines() if ln.strip()]
    page_mark = re.compile(r"^\s*(\d{3,4})\b")
    pages, cur_page, cur_lines = [], 1, []
    for ln in raw_lines:
        m = page_mark.match(ln)
        if m:
            if cur_lines:
                pages.append({"page": cur_page, "text": "\n".join(cur_lines), "lines": cur_lines, "is_scanned": False})
                cur_lines = []
            try: cur_page = int(m.group(1))
            except: cur_page += 1
            ln = ln[m.end():].strip()
            if not ln: continue
        cur_lines.append(ln)
    if cur_lines:
        pages.append({"page": cur_page, "text": "\n".join(cur_lines), "lines": cur_lines, "is_scanned": False})
    if not pages:
        pages = [{"page": 1, "text": txt, "lines": raw_lines, "is_scanned": False}]
    return pages
