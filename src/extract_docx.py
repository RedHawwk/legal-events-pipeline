from typing import List, Dict, Any
from docx import Document

def extract_docx(path: str) -> List[Dict[str, Any]]:
    doc = Document(path)
    lines = []
    for p in doc.paragraphs:
        t = (p.text or "").strip()
        if t: lines.append(t)
    return [{"page": 1, "text": "\n".join(lines), "lines": lines, "is_scanned": False}]
