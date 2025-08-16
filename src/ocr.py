from typing import Dict, Any, List
import numpy as np
import cv2
from paddleocr import PaddleOCR
import fitz

_ocr = None
def _get_ocr():
    global _ocr
    if _ocr is None:
        _ocr = PaddleOCR(lang='en', show_log=False)
    return _ocr

def ocr_pdf_pages_to_text(path: str) -> List[Dict[str, Any]]:
    """Render each page to image -> OCR -> text lines."""
    doc = fitz.open(path)
    pages = []
    ocr = _get_ocr()
    for i, page in enumerate(doc, start=1):
        pix = page.get_pixmap(matrix=fitz.Matrix(2,2))  # 2x zoom for OCR clarity
        img = np.frombuffer(pix.samples, dtype=np.uint8).reshape(pix.height, pix.width, pix.n)
        if pix.n == 4:
            img = cv2.cvtColor(img, cv2.COLOR_RGBA2RGB)
        res = ocr.ocr(img, cls=True)
        lines = []
        if res and res[0]:
            for det in res[0]:
                txt = det[1][0].strip()
                if txt:
                    lines.append(txt)
        pages.append({"page": i, "text": "\n".join(lines), "lines": lines, "is_scanned": True})
    doc.close()
    return pages
