# element_cache.py — persistent element refs shared across CLI invocations
#
# Every desktop-agent command runs in a fresh process, so the in-memory
# ELEMENT_CACHE built by snapshot/analyze is gone before a later
# `desktop-agent click @e1` can use it. This module persists refs to disk
# so the analyze → click → verify loop works across separate commands.

import json
import time

from .config import CACHE_DIR

ELEMENTS_FILE = CACHE_DIR / "elements.json"

# Refs older than this likely describe a screen that no longer exists
STALE_AFTER_SEC = 120


def save_refs(elements, texts=None, active_window="", source="analyze"):
    """Persist refs to disk. Each entry needs ref, cx, cy (click point).

    elements: dicts with ref/name/role/cx/cy
    texts: OCR regions with ref/text/cx/cy (stored with role "ocr-text")
    """
    refs = {}
    for e in elements or []:
        refs[e["ref"]] = {
            "name": e.get("name", ""),
            "role": e.get("role", ""),
            "cx": int(e["cx"]),
            "cy": int(e["cy"]),
        }
    for t in texts or []:
        refs[t["ref"]] = {
            "name": t.get("text", ""),
            "role": "ocr-text",
            "cx": int(t["cx"]),
            "cy": int(t["cy"]),
        }

    data = {
        "timestamp": time.time(),
        "active_window": active_window,
        "source": source,
        "refs": refs,
    }
    ELEMENTS_FILE.write_text(json.dumps(data))
    return len(refs)


def load_all():
    """Load the full persisted ref cache, or None if absent/corrupt."""
    try:
        return json.loads(ELEMENTS_FILE.read_text())
    except Exception:
        return None


def load_ref(ref):
    """Load one persisted ref with age info, or None."""
    data = load_all()
    if not data:
        return None
    entry = data.get("refs", {}).get(ref)
    if entry is None:
        return None
    entry = dict(entry)
    entry["age_sec"] = time.time() - data.get("timestamp", 0)
    entry["source"] = data.get("source", "?")
    entry["active_window"] = data.get("active_window", "")
    return entry
