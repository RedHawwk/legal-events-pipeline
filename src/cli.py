# src/cli.py
import argparse, csv, json, pathlib, os, re
from datetime import date
from concurrent.futures import ThreadPoolExecutor, as_completed

from .config import settings
from .chunker import compile_rules
from .rules_engine import parse_page
from .merge import should_send_to_llm, dedupe_rows, merge_preferring_confidence
from .extract_pdf import extract_pdf
from .extract_docx import extract_docx
from .extract_txt import extract_txt
from .ocr import ocr_pdf_pages_to_text
from .llm_gate import extract_with_llm


# -------- helpers (local strict date + page parsing) --------
_ISO = re.compile(r"^\d{4}-\d{2}-\d{2}$")
_PNUM = re.compile(r"p\.(\d+)")

def _valid_iso(d: str) -> bool:
    if not d or not isinstance(d, str) or not _ISO.match(d):
        return False
    y, m, d2 = map(int, d.split("-"))
    try:
        date(y, m, d2)
        return True
    except Exception:
        return False

def _page_num(page_section: str) -> int:
    m = _PNUM.search(page_section or "")
    return int(m.group(1)) if m else -1


# -------- loader --------
def load_pages(path: pathlib.Path):
    sfx = path.suffix.lower()
    if sfx == ".pdf":
        pages = extract_pdf(str(path))
        # OCR only for scanned pages and only if enabled
        if settings.USE_OCR and any(p.get("is_scanned") for p in pages):
            return ocr_pdf_pages_to_text(str(path))
        return pages
    elif sfx == ".docx":
        return extract_docx(str(path))
    elif sfx == ".txt":
        return extract_txt(str(path))
    else:
        return []


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--in", dest="inp", required=True, help="File or folder (.pdf/.docx/.txt)")
    ap.add_argument("--out", dest="out", required=True, help=".csv or .json path")
    ap.add_argument("--rules", default=str(pathlib.Path(__file__).with_name("rules.yaml")))
    ap.add_argument("--workers", default="8")  # kept for compatibility
    args = ap.parse_args()

    cfg, section_rx, date_rx, event_map, dp_settings, line_as_boundary, delims = compile_rules(args.rules)

    in_path = pathlib.Path(args.inp)
    files = [in_path] if in_path.is_file() else list(in_path.glob("**/*"))
    files = [f for f in files if f.suffix.lower() in (".pdf", ".docx", ".txt")]

    all_rows = []
    for f in files:
        pages = load_pages(f)
        if not pages:
            continue

        file_rows = []
        for pg in pages:
            rows = parse_page(pg, cfg, section_rx, date_rx, event_map, dp_settings, line_as_boundary, delims)
            for r in rows:
                r["SOURCE"] = str(f)
            file_rows.extend(rows)

        if settings.USE_LLM:
            # gather low-confidence/suspicious chunks for LLM
            to_llm = [r for r in file_rows if should_send_to_llm(r, settings.CONFIDENCE_THRESHOLD)]
            if to_llm:
                # build minimal chunk text (use DESCRIPTION context)
                uniq = {(r["DESCRIPTION"], r["PAGE/SECTION"], r["SOURCE"]) for r in to_llm}
                uniq = list(uniq)

                llm_rows = []
                with ThreadPoolExecutor(max_workers=settings.LLM_MAX_CALL_RATE) as ex:
                    futs = [
                        ex.submit(
                            extract_with_llm,
                            desc,
                            page_section,
                            source,
                            settings.LLM_PROVIDER,
                            settings.LLM_MODEL,
                        )
                        for (desc, page_section, source) in uniq
                    ]
                    for fu in as_completed(futs):
                        try:
                            llm_rows.extend(fu.result())
                        except Exception:
                            # swallow per-chunk LLM errors; continue
                            pass

                merged = merge_preferring_confidence(file_rows, llm_rows)
                all_rows.extend(merged)
            else:
                all_rows.extend(file_rows)
        else:
            all_rows.extend(file_rows)

    # finalize: dedupe → filter invalid dates → stable sort
    all_rows = dedupe_rows(all_rows)
    all_rows = [r for r in all_rows if _valid_iso(r.get("DATE", ""))]

    # Sort by SOURCE, page number, DATE, EVENT (stable for deterministic outputs)
    all_rows.sort(key=lambda r: (
        r.get("SOURCE", ""),
        _page_num(r.get("PAGE/SECTION", "")),
        r.get("DATE", ""),
        r.get("EVENT", "")
    ))

    outp = pathlib.Path(args.out)
    outp.parent.mkdir(parents=True, exist_ok=True)
    if outp.suffix.lower() == ".json":
        outp.write_text(json.dumps(all_rows, indent=2, ensure_ascii=False), encoding="utf-8")
        print(f"Wrote {len(all_rows)} rows -> {outp}")
    else:
        fieldnames = ["DATE", "EVENT", "DESCRIPTION", "PAGE/SECTION", "SOURCE"]
        with outp.open("w", newline="", encoding="utf-8") as fh:
            wr = csv.DictWriter(fh, fieldnames=fieldnames)
            wr.writeheader()
            wr.writerows([{k: v for k, v in r.items() if k in fieldnames} for r in all_rows])
        print(f"Wrote {len(all_rows)} rows -> {outp}")


if __name__ == "__main__":
    main()
