"""
Parses a PDF or DOCX file containing talent/passive node data into a structured
snapshot JSON.

Output shape
------------
{
  "generated_at": "ISO string",
  "source_file":  "filename",
  "trees": {
    "God of Might": {
      "nodes": [
        {"node_type": "medium", "stats": [{"text": "+18% damage"}]},
        ...
      ],
      "core_talents": [
        {"name": "Momentum", "stats": [{"text": "...", "max_divinity_effect": true}]},
        ...
      ]
    }
  },
  "new_god_talents": [
    {"name": "Dying Dragon", "stats": [{"text": "...", "max_divinity_effect": true}]},
    ...
  ]
}

Node-type detection
-------------------
  "Micro Talent", "Medium Talent", "Legendary Medium Talent", "Large Talent"
  → regular node; the remainder of the line is the tree name.

Core-talent detection (named talents locked behind point thresholds)
  Line ends with a known tree name AND the prefix is NOT a node-type token
  → core talent; prefix is the talent name.

New-God detection
  Line ends with "New God" AND prefix is not a node-type token
  → new-god talent; prefix is the talent name.

Max Divinity Effect
-------------------
  "(Max Divinity Effect: N)" is stripped from stat text and stored as
  `"max_divinity_effect": true` on the stat dict.
"""

from __future__ import annotations
import io
import re
from datetime import datetime

# ── Node-type tokens ────────────────────────────────────────────────────────
_NODE_TYPES = [
    "Legendary Medium Talent",
    "Medium Talent",
    "Micro Talent",
    "Large Talent",
]
_NODE_TYPE_RE = re.compile(
    r"(" + "|".join(re.escape(t) for t in _NODE_TYPES) + r")"
)
_TYPE_CANONICAL = {
    "Legendary Medium Talent": "legendary_medium",
    "Medium Talent":           "medium",
    "Micro Talent":            "micro",
    "Large Talent":            "large",
}

# ── Max Divinity Effect ─────────────────────────────────────────────────────
_MAX_DIV_RE = re.compile(r"\s*\(Max Divinity Effect:\s*\d+\)", re.IGNORECASE)


def _process_stat(raw: str) -> dict:
    """Return a stat dict, extracting the max_divinity_effect flag if present."""
    has_flag = bool(_MAX_DIV_RE.search(raw))
    text = _MAX_DIV_RE.sub("", raw).strip()
    result: dict = {"text": text}
    if has_flag:
        result["max_divinity_effect"] = True
    return result


# ── File extraction ─────────────────────────────────────────────────────────

def _extract_text_pdf(data: bytes) -> str:
    import pdfplumber
    pages = []
    with pdfplumber.open(io.BytesIO(data)) as pdf:
        for page in pdf.pages:
            text = page.extract_text()
            if text:
                pages.append(text)
    return "\n".join(pages)


def _extract_text_docx(data: bytes) -> str:
    import docx
    doc = docx.Document(io.BytesIO(data))
    return "\n".join(p.text.strip() for p in doc.paragraphs if p.text.strip())


# ── Parsing helpers ─────────────────────────────────────────────────────────

def _find_tree_suffix(line: str, known_trees: list[str]) -> tuple[str, str] | None:
    """
    If `line` ends with a known tree name, return (prefix, tree_name).
    Tries longest names first to avoid false partial matches.
    Returns None if no known tree name is found at the end.
    """
    for tree in sorted(known_trees, key=len, reverse=True):
        if line.endswith(tree):
            prefix = line[: -len(tree)].strip()
            return prefix, tree
    return None


def _preprocess(lines: list[str], known_trees: list[str]) -> list[str]:
    """
    Merge a standalone tree-name line into the previous line when that previous
    line looks like a talent name (not already a full node-type header).

    Handles DOCX documents where  "Momentum" and "God of Might" appear on
    separate paragraphs instead of concatenated as "MomentumGod of Might".
    """
    tree_set = set(known_trees)
    out: list[str] = []
    for raw in lines:
        line = raw.strip()
        if not line:
            continue
        if out and line in tree_set:
            prev = out[-1]
            # Only merge when the previous line is NOT already a complete header
            if not _NODE_TYPE_RE.search(prev) and not _find_tree_suffix(prev, known_trees):
                out[-1] = prev + line
                continue
        out.append(line)
    return out


# ── Main parser ─────────────────────────────────────────────────────────────

def _parse_lines(lines: list[str], known_trees: list[str]) -> tuple[dict, list]:
    """
    Returns (trees_dict, new_god_list).

    trees_dict  = { tree_name: {"nodes": [...], "core_talents": [...]} }
    new_god_list = [ {"name": ..., "stats": [...]} ]
    """
    lines = _preprocess(lines, known_trees)
    all_trees: dict[str, dict] = {}
    new_god_talents: list[dict] = []

    # Current accumulator
    kind: str | None = None        # "node" | "core_talent" | "new_god"
    node_type_str: str | None = None
    talent_name: str | None = None
    current_tree: str | None = None
    body: list[str] = []

    def _flush():
        nonlocal body
        if kind is None:
            body = []
            return

        if kind == "node":
            stats = [_process_stat(s) for s in body if s.startswith(("+", "-"))]
            if stats and current_tree is not None and node_type_str is not None:
                bucket = all_trees.setdefault(current_tree, {"nodes": [], "core_talents": []})
                bucket["nodes"].append({"node_type": node_type_str, "stats": stats})

        elif kind == "core_talent":
            stats = [_process_stat(s) for s in body if s]
            if stats and current_tree is not None and talent_name is not None:
                bucket = all_trees.setdefault(current_tree, {"nodes": [], "core_talents": []})
                bucket["core_talents"].append({"name": talent_name, "stats": stats})

        elif kind == "new_god":
            stats = [_process_stat(s) for s in body if s]
            if stats and talent_name is not None:
                new_god_talents.append({"name": talent_name, "stats": stats})

        body = []

    for line in lines:
        # ── Standard node-type header ────────────────────────────────────────
        m = _NODE_TYPE_RE.search(line)
        if m:
            _flush()
            token = m.group(1)
            node_type_str = _TYPE_CANONICAL[token]
            after = line[m.end():].strip()
            kind = "node"
            talent_name = None
            if after:
                current_tree = after
            continue

        # ── Named-talent header (core talent or new-god) ─────────────────────
        found = _find_tree_suffix(line, known_trees)
        if found:
            prefix, tree_name = found
            if prefix:  # prefix is the talent name; empty means just a tree label line
                _flush()
                talent_name = prefix
                current_tree = tree_name if tree_name != "New God" else current_tree
                kind = "new_god" if tree_name == "New God" else "core_talent"
                if tree_name != "New God":
                    current_tree = tree_name
                continue

        # ── Body line (stat or description) ─────────────────────────────────
        body.append(line)

    _flush()
    return all_trees, new_god_talents


def parse_document(data: bytes, filename: str, known_tree_names: list[str] | None = None) -> dict:
    """
    Parse a PDF or DOCX file and return a snapshot dict.

    Pass ``known_tree_names`` (from the TREES registry) so the parser can
    distinguish core-talent headers from regular body text.
    """
    ext = filename.rsplit(".", 1)[-1].lower() if "." in filename else ""

    if ext == "pdf":
        raw_text = _extract_text_pdf(data)
    elif ext in ("docx", "doc"):
        raw_text = _extract_text_docx(data)
    else:
        raise ValueError(f"Unsupported file type: .{ext}  (expected pdf, docx, or doc)")

    trees_in_doc = list(known_tree_names or [])
    if "New God" not in trees_in_doc:
        trees_in_doc.append("New God")

    lines = raw_text.splitlines()
    all_trees, new_god_talents = _parse_lines(lines, trees_in_doc)

    return {
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "source_file": filename,
        "trees": all_trees,
        "new_god_talents": new_god_talents,
    }
