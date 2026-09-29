"""
OCR Extraction — template persistence + transient upload handling.

Templates (named sets of annotation boxes) are saved as JSON files under
`templates/` INSIDE this package — deliberately in the code folder, not a
DB row and not a per-user profile location, so they get checked into the
repo alongside the code that reads them (same convention as
release_pend_macro/rule_code_ref_template.csv).

Uploaded PDFs are the opposite: NEVER written under the repo. Each upload
gets its own directory under the OS temp folder, identified by a random
doc_id, and is expected to be short-lived — discarded explicitly by the UI
(`discard_upload`), or left for the OS to reclaim eventually. The whole
reason this feature exists is that the source PDFs are sensitive and must
never leave the user's machine, let alone land in a git-tracked folder —
a template JSON only ever holds box coordinates and cell labels, never any
document content.
"""

from __future__ import annotations

import json
import shutil
import tempfile
import uuid
from pathlib import Path

TEMPLATES_DIR = Path(__file__).resolve().parent / "templates"
TEMPLATES_DIR.mkdir(exist_ok=True)

UPLOADS_ROOT = Path(tempfile.gettempdir()) / "rule_engine_ocr_uploads"
UPLOADS_ROOT.mkdir(exist_ok=True)


def _safe_template_name(name: str) -> str:
    name = (name or "").strip()
    if not name or any(c in name for c in r'\/:*?"<>|'):
        raise ValueError("Template name must be non-empty and contain no path characters")
    return name


def _safe_doc_id(doc_id: str) -> str:
    """Validates doc_id is a real UUID we generated (see new_upload_dir) before
    it's ever used to build a filesystem path — doc_id round-trips through the
    browser/API, so this guards against a crafted value walking the path
    outside UPLOADS_ROOT."""
    try:
        return str(uuid.UUID(str(doc_id)))
    except (ValueError, AttributeError, TypeError):
        raise ValueError(f"Invalid doc_id: {doc_id!r}")


def list_templates() -> list[str]:
    return sorted(p.stem for p in TEMPLATES_DIR.glob("*.json"))


def load_template(name: str) -> dict:
    path = TEMPLATES_DIR / f"{_safe_template_name(name)}.json"
    if not path.exists():
        raise FileNotFoundError(f"No template named {name!r}")
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def save_template(name: str, data: dict) -> str:
    path = TEMPLATES_DIR / f"{_safe_template_name(name)}.json"
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)
    return str(path)


def delete_template(name: str) -> None:
    path = TEMPLATES_DIR / f"{_safe_template_name(name)}.json"
    if path.exists():
        path.unlink()


def new_upload_dir() -> tuple[str, Path]:
    doc_id = uuid.uuid4().hex
    # store with hyphens so _safe_doc_id's UUID round-trip is exact either way
    d = UPLOADS_ROOT / str(uuid.UUID(doc_id))
    d.mkdir(parents=True, exist_ok=True)
    return str(uuid.UUID(doc_id)), d


def upload_dir(doc_id: str) -> Path:
    doc_id = _safe_doc_id(doc_id)
    d = UPLOADS_ROOT / doc_id
    if not d.exists():
        raise FileNotFoundError(f"No such upload {doc_id!r} (it may have already been discarded)")
    return d


def discard_upload(doc_id: str) -> None:
    doc_id = _safe_doc_id(doc_id)
    d = UPLOADS_ROOT / doc_id
    if d.exists():
        shutil.rmtree(d, ignore_errors=True)
