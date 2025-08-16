from typing import List, Tuple
import regex as rx
import yaml

def is_section_heading(line: str, section_rx) -> bool:
    return any(p.search(line.strip()) for p in section_rx)

def build_sections(lines: List[str], section_rx) -> List[Tuple[str,int]]:
    sections, cur = [], ("BODY", 0)
    for i, ln in enumerate(lines):
        if is_section_heading(ln, section_rx):
            cur = (ln.strip(), i)
            sections.append(cur)
    if not sections:
        sections = [("BODY", 0)]
    return sections

def section_for_index(sections, idx: int) -> str:
    cur = "BODY"
    for name, start in sections:
        if start <= idx: cur = name
        else: break
    return cur

def _uppercase_ratio(s: str) -> float:
    letters = [c for c in s if c.isalpha()]
    if not letters: 
        return 0.0
    caps = [c for c in letters if c.isupper()]
    return len(caps) / len(letters)

def is_section_heading(line: str, section_rx) -> bool:
    line = line.strip()
    if len(line) > 80:   # avoid long sentences as headings
        return False
    if _uppercase_ratio(line) < 0.6:  # prefer ALL CAPS-like headings
        return False
    return any(p.search(line) for p in section_rx)


def compile_rules(cfg_path: str):
    cfg = yaml.safe_load(open(cfg_path, "r", encoding="utf-8"))
    section_rx = [rx.compile(p, rx.I) for p in cfg["section_patterns"]]
    date_rx    = [rx.compile(p, rx.I) for p in cfg["date_patterns"]]
    event_map  = {k: [rx.compile(p, rx.I) for p in v] for k, v in cfg["events"].items()}
    dp_settings = {"languages": cfg.get("dateparser", {}).get("languages", ["en"]),
                   "settings": cfg.get("dateparser", {}).get("settings", {"DATE_ORDER":"DMY"})}
    line_as_boundary = cfg.get("line_break_is_boundary", True)
    delims = cfg.get("sentence_delimiters", ["."])
    return cfg, section_rx, date_rx, event_map, dp_settings, line_as_boundary, delims
