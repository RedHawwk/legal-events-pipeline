from typing import List, Dict, Any
import fitz  # PyMuPDF

def is_scanned(page: fitz.Page) -> bool:
    # Heuristic: if text extraction is empty, assume image-only (needs OCR)
    return len(page.get_text("text").strip()) == 0

def extract_pdf(path: str) -> List[Dict[str, Any]]:
    doc = fitz.open(path)
    pages = []
    for i, page in enumerate(doc, start=1):
        text = page.get_text("text") or ""
        lines = [ln.strip() for ln in text.splitlines() if ln.strip()]
        pages.append({"page": i, "text": text, "lines": lines, "is_scanned": is_scanned(page)})
    doc.close()
    return pages
