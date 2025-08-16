```markdown
# Legal Events Pipeline

Hybrid, production-style parser that extracts **legal case events** from PDFs/DOCX/TXT and emits clean rows:

```

DATE, EVENT, DESCRIPTION, PAGE/SECTION, SOURCE

```

The pipeline is **fast-first, LLM-last**:
- **FAST**: PyMuPDF/pdfplumber + rules (regex + date parsing + section heuristics)
- **OCR (optional)**: PaddleOCR for scanned/image-only PDFs
- **LLM gate (optional, Gemini)**: Only low-confidence chunks are sent to Gemini for normalization

---

## ✨ Features

- 📄 Supports **PDF**, **DOCX**, **TXT** (OCR for scanned PDFs optional)
- 🧠 **Rules-first** extraction (deterministic, cheap, fast)
- 🔎 **Confidence gating** (send only uncertain chunks to LLM)
- 🧹 Robust **merging & deduping** (page-aware; prefers higher confidence/longer description)
- 🔒 **Strict date validation** (ISO `YYYY-MM-DD` only)
- 🧱 Section detection (avoids mislabeling long sentences as headings)
- ⚙️ Everything configurable via `src/rules.yaml` and `.env`

---

## 🗂️ Project Layout

```

legal-events-pipeline/
.env.example
requirements.txt
data/
samples/         # put your input docs here
out/             # outputs (CSV/JSON) go here
src/
cli.py
config.py
extract\_pdf.py
extract\_docx.py
extract\_txt.py
ocr.py
chunker.py
rules\_engine.py
merge.py
llm\_gate.py
rules.yaml
.vscode/
launch.json
settings.json
README.md

````

---

## 🚀 Quick Start (Windows, Python 3.12)

1) **Clone and open**
```powershell
git clone https://github.com/<your-username>/legal-events-pipeline.git
cd legal-events-pipeline
code .
````

2. **Create venv with Python 3.12**

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\Activate.ps1
```

3. **Install deps**

```powershell
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
```

4. **Create `.env`**

```ini
# .env
USE_OCR=false
USE_LLM=true
LLM_PROVIDER=gemini
LLM_MODEL=gemini-1.5-flash
LLM_MAX_CALL_RATE=5
CONFIDENCE_THRESHOLD=0.7
GEMINI_API_KEY=YOUR_KEY_HERE
```

> Keep `USE_LLM=false` if you want a rules-only run first.

5. **Add sample docs**
   Place a few test files in `data/samples/` (PDF/DOCX/TXT).

6. **Run**

```powershell
python -m src.cli --in data/samples --out data/out/events.json --workers 8
```

You’ll get `events.json` (or `events.csv` if you change the extension).

---

## 🧪 Output Schema

| Field          | Type   | Notes                                                                                                                                         |
| -------------- | ------ | --------------------------------------------------------------------------------------------------------------------------------------------- |
| `DATE`         | string | ISO `YYYY-MM-DD` only (invalid/missing dropped)                                                                                               |
| `EVENT`        | string | One of: Filing, Hearing, Order, Adjournment, Notice, Bail, Charge, Evidence, Judgment, Application, Service, Settlement, Lease, Appeal, Event |
| `DESCRIPTION`  | string | ≤ 400 chars; short, contextual, quotes key phrase(s)                                                                                          |
| `PAGE/SECTION` | string | e.g. `p.5 / FACTS`                                                                                                                            |
| `SOURCE`       | string | Full path to original file                                                                                                                    |

---

## ⚙️ How It Works

### 1) Ingestion

* **PDF** → `src/extract_pdf.py` (PyMuPDF). If page has no extractable text and `USE_OCR=true`, `src/ocr.py` (PaddleOCR) kicks in.
* **DOCX** → `src/extract_docx.py`
* **TXT** → `src/extract_txt.py`

### 2) Rule pass

* `src/rules_engine.py` + `src/chunker.py`:

  * finds **dates** (regex + `dateparser`)
  * detects **event triggers** (from `rules.yaml`)
  * detects **section headings** (ALL CAPS/short; avoids long lines)
  * emits candidate rows + `_confidence`, `_has_date`, `_has_event`

### 3) Gate to LLM (optional)

* Only send rows failing the threshold or missing date/event (`src/merge.py::should_send_to_llm`).
* `src/llm_gate.py` uses **Gemini** with **structured JSON** (enforced by schema) to normalize/fill.

### 4) Merge & Dedupe

* `src/merge.py` unions rule + LLM rows:

  * key = `(SOURCE, DATE, EVENT, page_num)`
  * prefer **higher confidence**, then **longer description**
  * drop rows with invalid dates
  * final **dedupe** and **sort** happen in `src/cli.py`

---

## 🧩 Configuration

### `.env` toggles

* `USE_OCR` → `true` to OCR scanned PDFs
* `USE_LLM` → `true` to enable Gemini LLM gating
* `CONFIDENCE_THRESHOLD` → controls how many rows go to LLM (0.6–0.75 good)
* `LLM_MAX_CALL_RATE` → concurrent Gemini calls
* `GEMINI_API_KEY` → your Google Generative AI key

### `src/rules.yaml`

Tweak without touching code:

* `events:` → event trigger phrases (add court-specific terms)
* `date_patterns:` → support more date formats if needed
* `section_patterns:` → what counts as a heading
* `line_break_is_boundary:` → keep `true` for legal docs

---

## 🧠 LLM Details (Gemini)

* We **enforce JSON** using Gemini’s `response_mime_type` + `response_schema`.
* The prompt requires **explicit dates** in the text. No date → no row.
* We clamp description length in Python and normalize event labels.
* ENV:

  ```
  LLM_PROVIDER=gemini
  LLM_MODEL=gemini-1.5-flash
  GEMINI_API_KEY=...
  ```

> If you see “Unknown field for Schema: maxLength”, you’re on the updated version that **removed `maxLength`** from the schema and clamps length in Python instead.

---

## 🛠️ Troubleshooting

* **`ModuleNotFoundError: pydantic`**
  You installed deps into a different Python. Recreate venv with **3.12** and install:

  ```powershell
  py -3.12 -m venv .venv
  .\.venv\Scripts\Activate.ps1
  python -m pip install -r requirements.txt
  ```

* **OCR is slow or errors (`cv2`, `paddleocr`, `paddlepaddle`)**
  Keep `USE_OCR=false` unless you truly have scanned PDFs.
  For CPU:

  ```powershell
  python -m pip install paddlepaddle paddleocr opencv-python Pillow
  ```

* **Gemini JSON/validation errors**
  Ensure you have the **structured-output** `llm_gate.py` and no `maxLength` in the schema.

* **Dates like `1923-03-00` appear**
  Use the updated `merge.py`/`cli.py` that filter invalid dates (strict ISO check).

---

## 📈 Performance Tips

* Start **rules-only** (`USE_LLM=false`, `USE_OCR=false`) to verify extraction.
* Enable LLM only after your rules are decent; adjust `CONFIDENCE_THRESHOLD` for cost/latency.
* Use `--workers` ≈ CPU cores for faster page parsing.
* OCR only on pages where PyMuPDF returns empty text.

---

## 🔒 Privacy

* Only **low-confidence chunks** are sent to Gemini (not whole documents).
* Outputs include `SOURCE` and `PAGE/SECTION` for auditability.

---

## 🧪 Example Run

```powershell
python -m src.cli --in data/samples --out data/out/events.csv --workers 8
```

**`data/out/events.csv`**

```
DATE,EVENT,DESCRIPTION,PAGE/SECTION,SOURCE
1921-03-11,Lease,"Lease of underground coal in 5,800 bighas …",p.1 / FACTS,data/samples/case1.pdf
1923-03-06,Settlement,"Compromise decree terms …",p.2 / PROCEEDINGS,data/samples/case1.pdf
...
```

---

## 🤝 Contributing

PRs welcome:

1. Fork → branch → PR
2. For new event types, update `rules.yaml` and include a micro sample
3. Add tests (coming soon)

---

## 📜 License

Choose a license (e.g., MIT) and add a `LICENSE` file.

---

## 💬 Help

Open an issue with:

* OS & Python version
* Command you ran
* Error log
* Minimal sample document (if possible)

```
```
