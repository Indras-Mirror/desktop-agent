# desktop-agent analyze — unified screen understanding for AI agents
#
# Combines AT-SPI tree + OCR text + spatial layout into one structured
# ~500-token output so local LLMs can "see" the screen without vision models.

from .config import ATSPI_AVAILABLE, PRIMARY_MONITOR, CACHE_DIR
from .window import get_active_window
from .input import screenshot as take_screenshot
from .element_cache import save_refs
import json
import re
import time
import os
import sys
import subprocess
from pathlib import Path
from collections import defaultdict, Counter

LAST_ANALYZE_FILE = CACHE_DIR / "last_analyze.json"


def clean_label(text: str) -> str:
    """Strip braille, PUA, zero-width, and other icon-font glyphs from labels.

    AT-SPI/OCR element names (and window titles) frequently carry icon-font
    glyphs (Claude Code's braille title), Private-Use-Area codepoints, and
    zero-width characters. These pollute fuzzy matching and pinned-element
    relink selectors, so strip them and collapse whitespace.
    """
    if not text:
        return text
    # Strip zero-width / BOM characters
    text = (
        text.replace("​", "")
        .replace("‌", "")
        .replace("‍", "")
        .replace("﻿", "")
    )
    # Strip braille pattern block (U+2800–U+28FF)
    text = re.sub(r"[\u2800-\u28FF]", "", text)
    # Strip Private Use Areas (U+E000–U+F8FF, U+F0000–U+FFFFD, U+100000–U+10FFFD)
    text = re.sub(r"[\uE000-\uF8FF\U000f0000-\U000ffffd\U00100000-\U0010fffd]", "", text)
    # Collapse whitespace
    text = re.sub(r"\s+", " ", text).strip()
    return text


# Element/text caps per detail level: (max_elements, max_texts, run_ocr)
_DETAIL_LEVELS = {
    "quick": (15, 0, False),   # AT-SPI only, skip OCR (~1s instead of ~4s)
    "normal": (40, 30, True),
    "deep": (80, 60, True),
}


# ---------------------------------------------------------------------------
# AT-SPI: full-tree walk → condensed element list
# ---------------------------------------------------------------------------

# Roles that are pure layout containers — skip unless they have a name
_CONTAINER_ROLES = frozenset({
    "panel", "filler", "layered pane", "page tab list",
    "scroll pane", "split pane", "root pane",
    "table cell", "unknown",
})

# Roles that are always worth keeping (interactive or info-bearing)
_INTERACTIVE_ROLES = frozenset({
    "push button", "toggle button", "link", "entry", "text",
    "combo box", "check box", "radio button", "slider",
    "menu item", "menu", "icon", "label", "heading",
    "list item", "table", "tree", "page tab",
})


def _get_active_pid():
    """Get PID of the currently active window via xdotool."""
    try:
        result = subprocess.run(
            ["xdotool", "getactivewindow", "getwindowpid"],
            capture_output=True, text=True, timeout=2
        )
        if result.returncode == 0:
            return int(result.stdout.strip())
    except Exception:
        pass
    return None


def _collect_elements(element, depth=0, max_depth=15):
    """Walk AT-SPI tree and yield meaningful elements with position + role."""
    import pyatspi

    if depth > max_depth:
        return

    try:
        role_name = element.getRoleName()
        state = element.getState()

        # Applications (process-level) are always "invisible" in AT-SPI
        # but their child frames/windows ARE visible. Skip visibility
        # check for non-widget elements.
        is_app = role_name == "application"
        if not is_app:
            visible = state.contains(pyatspi.STATE_VISIBLE) and \
                state.contains(pyatspi.STATE_SHOWING)
            if not visible:
                return

        # Get bounds
        try:
            comp = element.queryComponent()
            ext = comp.getExtents(pyatspi.DESKTOP_COORDS)
            x, y, w, h = ext.x, ext.y, ext.width, ext.height
        except Exception:
            x, y, w, h = 0, 0, 0, 0

        if not is_app and (w <= 2 or h <= 2):
            return  # too tiny to matter

        name = clean_label(element.name or "")
        desc = clean_label(element.description or "")

        # Filter: anonymous containers (no name, structural-only role)
        is_container = role_name in _CONTAINER_ROLES
        is_interactive = role_name in _INTERACTIVE_ROLES
        has_content = bool(name) or bool(desc)

        # Structural roles worth including as context
        structural_parent = role_name in ("frame", "window", "application", "dialog")

        # Adjust coords to primary-relative
        mon = PRIMARY_MONITOR
        rel_x = x - mon["x"]
        rel_y = y - mon["y"]

        # Only keep elements on the primary monitor
        on_primary = (
            mon["x"] <= x < mon["x"] + mon["width"] and
            mon["y"] <= y < mon["y"] + mon["height"]
        )
        if not is_app and not on_primary:
            return

        # Yield this element if it's useful for understanding the screen
        should_yield = (
            not is_container
            and not is_app
            and (is_interactive or has_content or structural_parent)
        )
        if should_yield:
            yield {
                "role": role_name,
                "name": (name or "")[:60],
                "desc": (desc or "")[:60],
                "x": rel_x,
                "y": rel_y,
                "w": w,
                "h": h,
                "depth": depth,
                "interactive": role_name in _INTERACTIVE_ROLES,
            }

        # Recurse into children
        for i in range(element.childCount):
            try:
                child = element.getChildAtIndex(i)
                yield from _collect_elements(child, depth + 1, max_depth)
            except Exception:
                pass

    except Exception:
        return


def _group_by_zone(elements, screen_w, screen_h):
    """Group elements into top / bottom / left / right / center zones."""
    zones = defaultdict(list)
    threshold = 0.1  # 10% of dimension = zone boundary

    for e in elements:
        cx = e["x"] + e["w"] // 2
        cy = e["y"] + e["h"] // 2
        rel_x = cx / screen_w if screen_w else 0.5
        rel_y = cy / screen_h if screen_h else 0.5

        if rel_y < threshold:
            zone = "top"
        elif rel_y > 1 - threshold:
            zone = "bottom"
        elif rel_x < threshold:
            zone = "left"
        elif rel_x > 1 - threshold:
            zone = "right"
        else:
            zone = "center"

        zones[zone].append(e)

    return dict(zones)


def _walk_atspi(target_pid=None):
    """Walk AT-SPI tree and return condensed elements.

    If target_pid is provided, only walks apps with matching PID.
    Falls back to all apps if no matching PID is found.
    """
    if not ATSPI_AVAILABLE:
        return []

    import pyatspi
    desktop = pyatspi.Registry.getDesktop(0)
    all_elems = []
    matched_elems = []

    for i in range(desktop.childCount):
        try:
            app = desktop.getChildAtIndex(i)
            if not app.name:
                continue
            app_elems = list(_collect_elements(app))
            if not app_elems:
                continue

            all_elems.extend(app_elems)

            # Check if this app matches target PID
            if target_pid is not None:
                try:
                    if app.get_process_id() == target_pid:
                        matched_elems.extend(app_elems)
                except Exception:
                    pass
        except Exception:
            pass

    # Use filtered elements if we found a match, otherwise fall back to all
    if target_pid is not None and matched_elems:
        return matched_elems
    return all_elems


# ---------------------------------------------------------------------------
# OCR: full-screen text extraction
# ---------------------------------------------------------------------------

def _ocr_screen(ss_path, region_rect=None, max_regions=60):
    """Run OCR on screenshot (RapidOCR primary, Tesseract fallback).

    If region_rect (x, y, w, h) is given, only that crop is OCR'd —
    faster and less background noise. Coordinates in the returned
    regions are always full-screen (primary-relative).
    """
    from .ocr import ocr_screen as do_ocr

    if region_rect:
        try:
            from PIL import Image

            rx, ry, rw, rh = region_rect
            crop_path = Path("/tmp/desktop-agent") / "analyze_region.png"
            img = Image.open(ss_path)
            img.crop((rx, ry, rx + rw, ry + rh)).save(crop_path)
            regions = do_ocr(crop_path, engine="rapidocr",
                             min_confidence=40, max_regions=max_regions)
            for r in regions:
                r["x"] += rx
                r["y"] += ry
            return regions
        except Exception:
            pass  # fall through to full-screen OCR

    return do_ocr(ss_path, engine="rapidocr", min_confidence=40,
                  max_regions=max_regions)


# ---------------------------------------------------------------------------
# Region targeting — analyze only part of the screen
# ---------------------------------------------------------------------------

def _parse_region(region, mon):
    """Parse --region value into a primary-relative (x, y, w, h) rect.

    Accepts zone names (top/bottom/left/right/center) or "x,y,w,h".
    Returns None if unparseable.
    """
    if not region:
        return None

    w, h = mon["width"], mon["height"]
    zones = {
        "top": (0, 0, w, h // 4),
        "bottom": (0, h * 3 // 4, w, h // 4),
        "left": (0, 0, w // 4, h),
        "right": (w * 3 // 4, 0, w // 4, h),
        "center": (w // 4, h // 4, w // 2, h // 2),
    }
    if region in zones:
        return zones[region]

    parts = region.split(",")
    if len(parts) == 4 and all(p.strip().lstrip("-").isdigit() for p in parts):
        return tuple(int(p) for p in parts)

    return None


def _in_rect(e, rect):
    """True if the element's center falls inside rect (x, y, w, h)."""
    rx, ry, rw, rh = rect
    cx = e["x"] + e.get("w", 0) // 2
    cy = e["y"] + e.get("h", 0) // 2
    return rx <= cx < rx + rw and ry <= cy < ry + rh


# ---------------------------------------------------------------------------
# Change detection — diff against the previous analyze run
# ---------------------------------------------------------------------------

def _load_last_analysis():
    try:
        return json.loads(LAST_ANALYZE_FILE.read_text())
    except Exception:
        return None


def _save_last_analysis(result):
    try:
        slim = {
            "screen": result["screen"],
            "atspi_elements": result["atspi_elements"],
            "ocr_texts": result["ocr_texts"],
            "timestamp": time.time(),
        }
        LAST_ANALYZE_FILE.write_text(json.dumps(slim))
    except Exception:
        pass


def _compute_diff(prev, current):
    """Compare current analysis to the previous one → what changed."""
    if not prev:
        return {"changed": None, "note": "no previous analysis to compare against"}

    diff = {}
    prev_win = prev.get("screen", {}).get("active_window")
    cur_win = current["screen"]["active_window"]
    if prev_win != cur_win:
        diff["active_window"] = {"before": prev_win, "after": cur_win}

    def elem_sig(e):
        return f"{e['role']}:{e['name']}"

    prev_elems = Counter(elem_sig(e) for e in prev.get("atspi_elements", []))
    cur_elems = Counter(elem_sig(e) for e in current["atspi_elements"])
    diff["elements_added"] = sorted((cur_elems - prev_elems).elements())
    diff["elements_removed"] = sorted((prev_elems - cur_elems).elements())

    prev_texts = Counter(t["text"] for t in prev.get("ocr_texts", []))
    cur_texts = Counter(t["text"] for t in current["ocr_texts"])
    diff["texts_added"] = sorted((cur_texts - prev_texts).elements())
    diff["texts_removed"] = sorted((prev_texts - cur_texts).elements())

    age = time.time() - prev.get("timestamp", 0)
    diff["compared_to_sec_ago"] = round(age, 1)
    diff["changed"] = bool(
        "active_window" in diff
        or diff["elements_added"] or diff["elements_removed"]
        or diff["texts_added"] or diff["texts_removed"]
    )
    return diff


# ---------------------------------------------------------------------------
# Menu bar dedup — collapse identical menus from multiple windows
# ---------------------------------------------------------------------------

def _dedupe_menubars(elements):
    """Collapse identical menu bars from multiple windows.

    Multiple terminal windows each expose File/Edit/View/Search/Terminal/Help.
    Keep one representative bar + note the rest as duplicates.
    """
    if not elements:
        return elements

    menus = [e for e in elements if e["role"] == "menu"]
    if len(menus) < 12:  # need at least 2 full bars (6×2=12) to bother
        return elements

    # Cluster menus into bars by y-coordinate proximity (20px)
    y_groups = []
    for m in menus:
        placed = False
        for group in y_groups:
            if abs(m["y"] - group[0]["y"]) < 20:
                group.append(m)
                placed = True
                break
        if not placed:
            y_groups.append([m])

    # Get the name signature for each bar
    bars = []
    for group in y_groups:
        names = tuple(sorted(m["name"] for m in group))
        bars.append({"names": names, "group": group, "y": group[0]["y"]})

    if len(bars) <= 1:
        return elements

    # Find bars with identical name signatures
    sig_to_bars = defaultdict(list)
    for bar in bars:
        sig_to_bars[bar["names"]].append(bar)

    # For duplicate signatures, keep only the first occurrence
    to_remove_ids = set()
    for sig, dupes in sig_to_bars.items():
        if len(dupes) > 1:
            # Keep the first bar, remove the rest
            for bar in dupes[1:]:
                for m in bar["group"]:
                    to_remove_ids.add(id(m))

    if not to_remove_ids:
        return elements

    return [e for e in elements if id(e) not in to_remove_ids]


# ---------------------------------------------------------------------------
# Main analyze entry point
# ---------------------------------------------------------------------------

def analyze(output_format="text", detail="normal", diff=False, region=None):
    """Produce a unified screen analysis for AI consumption.

    Args:
        output_format: "text" or "json"
        detail: "quick" (AT-SPI only, no OCR), "normal", or "deep" (uncapped)
        diff: also report what changed since the previous analyze run
        region: restrict analysis to a zone name (top/bottom/left/right/center)
                or a "x,y,w,h" pixel rect (primary-relative)

    Returns a dict (also printed to stdout) with:
        - screen: dimensions + active window
        - atspi_elements: condensed AT-SPI element list (with @e refs)
        - ocr_texts: OCR text regions (with @t refs)
        - zones: spatial grouping
        - summary: human-readable one-liner
        - diff: changes vs previous run (when diff=True)

    Refs are persisted to ~/.cache/desktop-agent/elements.json so a
    follow-up `desktop-agent click @e3` works from a separate process.
    """
    start = time.time()
    max_elements, max_texts, run_ocr = _DETAIL_LEVELS.get(
        detail, _DETAIL_LEVELS["normal"])
    region_rect = _parse_region(region, PRIMARY_MONITOR)
    previous = _load_last_analysis() if diff else None

    # -- Screenshot (only needed for OCR — quick mode skips it) ---------------
    mon = PRIMARY_MONITOR
    ss_path = Path("/tmp/desktop-agent") / "analyze.png"

    if run_ocr:
        # Suppress noisy "Screenshot saved" in JSON mode
        if output_format == "json":
            old_stdout = sys.stdout
            sys.stdout = open(os.devnull, "w")
            try:
                take_screenshot(ss_path, primary_only=True)
            finally:
                sys.stdout.close()
                sys.stdout = old_stdout
        else:
            take_screenshot(ss_path, primary_only=True)

    # -- AT-SPI elements ------------------------------------------------------
    active_pid = _get_active_pid()
    elements = _walk_atspi(target_pid=active_pid)

    # Deduplicate + sort by position (top-to-bottom, left-to-right)
    seen = set()
    deduped = []
    for e in elements:
        key = (e["role"], e["x"], e["y"], e["name"][:20])
        if key not in seen:
            seen.add(key)
            deduped.append(e)

    deduped.sort(key=lambda e: (e["y"], e["x"]))

    # Collapse duplicate menu bars (same menu names in multiple terminal windows)
    deduped = _dedupe_menubars(deduped)

    # Restrict to requested region
    if region_rect:
        deduped = [e for e in deduped if _in_rect(e, region_rect)]

    # Cap for token budget — keep interactive first, then the rest
    if len(deduped) > max_elements:
        interactive = [e for e in deduped if e["interactive"]]
        others = [e for e in deduped if not e["interactive"]]
        deduped = (interactive + others)[:max_elements]

    # Assign stable refs (@e1, @e2 ...) and click points
    for i, e in enumerate(deduped, 1):
        e["ref"] = f"@e{i}"
        e["cx"] = e["x"] + e["w"] // 2
        e["cy"] = e["y"] + e["h"] // 2

    # -- OCR text -------------------------------------------------------------
    if run_ocr:
        text_regions = _ocr_screen(ss_path, region_rect=region_rect,
                                   max_regions=max_texts)
        text_regions.sort(key=lambda r: (r["y"], r["x"]))
        if len(text_regions) > max_texts:
            text_regions = text_regions[:max_texts]
    else:
        text_regions = []

    # OCR regions get refs too (@t1 ...) so text is directly clickable
    for i, r in enumerate(text_regions, 1):
        r["ref"] = f"@t{i}"
        r["cx"] = r["x"] + r.get("w", 0) // 2
        r["cy"] = r["y"] + r.get("h", 0) // 2

    # -- Zones ----------------------------------------------------------------
    zones = _group_by_zone(deduped, mon["width"], mon["height"])

    # -- Active window + PID for AT-SPI filtering ---------------------------
    try:
        active_win = get_active_window()
        active_name = clean_label(active_win.get("name", "unknown"))
    except Exception:
        active_name = "unknown"

    # Check if active window has an AT-SPI application (for reporting)
    filtering_active = False
    if active_pid and ATSPI_AVAILABLE:
        import pyatspi
        try:
            desktop = pyatspi.Registry.getDesktop(0)
            for i in range(desktop.childCount):
                try:
                    if desktop.getChildAtIndex(i).get_process_id() == active_pid:
                        filtering_active = True
                        break
                except Exception:
                    pass
        except Exception:
            pass

    # -- Build output ---------------------------------------------------------
    result = {
        "screen": {
            "width": mon["width"],
            "height": mon["height"],
            "active_window": active_name,
            "active_pid": active_pid,
            "atspi_filtered": filtering_active,
        },
        "atspi_elements": deduped,
        "ocr_texts": text_regions,
        "zones": {
            zone: [
                {"role": e["role"], "name": e["name"],
                 "x": e["x"], "y": e["y"]}
                for e in elems
            ]
            for zone, elems in zones.items()
        },
        "summary": _make_summary(deduped, text_regions, active_name, mon),
    }
    result["detail"] = detail
    if region_rect:
        result["region"] = list(region_rect)

    if diff:
        result["diff"] = _compute_diff(previous, result)

    # Persist refs + analysis so later commands (click @e3, --diff) can use them
    save_refs(deduped, texts=text_regions,
              active_window=active_name, source="analyze")
    _save_last_analysis(result)

    elapsed = time.time() - start
    result["elapsed_sec"] = round(elapsed, 2)

    if output_format == "json":
        out = json.dumps(result, indent=2)
        print(out)
    else:
        _print_human(result)

    return result


def _make_summary(elements, text_regions, active_window, mon):
    """One-liner describing the screen layout for quick AI understanding."""
    count = len(elements)
    interactive_count = sum(1 for e in elements if e.get("interactive"))
    text_count = len(text_regions)

    # Categorise roles
    buttons = sum(1 for e in elements if e["role"] in ("push button", "toggle button"))
    links = sum(1 for e in elements if e["role"] == "link")
    entries = sum(1 for e in elements if e["role"] == "entry")
    menus = sum(1 for e in elements if e["role"] == "menu")

    parts = [
        f"{mon['width']}×{mon['height']} screen",
        f"active: {active_window[:60]}",
    ]

    parts.append(f"{count} UI elements ({interactive_count} interactive)")
    if buttons:
        parts.append(f"{buttons} button{'s' if buttons != 1 else ''}")
    if menus:
        parts.append(f"{menus} menu{'s' if menus != 1 else ''}")
    if entries:
        parts.append(f"{entries} input{'s' if entries != 1 else ''}")
    if links:
        parts.append(f"{links} link{'s' if links != 1 else ''}")

    parts.append(f"{text_count} text regions")

    return " | ".join(parts)


def _print_human(result):
    """Pretty human-readable output."""
    s = result["screen"]
    print(f"=== Screen Analysis ===")
    print(f"Resolution: {s['width']}×{s['height']}  |  Active: {s['active_window']}")
    print(f"Fetched in {result['elapsed_sec']}s")
    print()

    # Summary
    print(f"Summary: {result['summary']}")
    print()

    # Diff vs previous run
    if result.get("diff"):
        d = result["diff"]
        print("--- Changes Since Last Analyze ---")
        if d.get("changed") is None:
            print(f"  {d.get('note', 'no previous data')}")
        elif not d["changed"]:
            print(f"  No changes (compared to {d['compared_to_sec_ago']}s ago)")
        else:
            if "active_window" in d:
                aw = d["active_window"]
                print(f"  Window: \"{aw['before']}\" → \"{aw['after']}\"")
            for label, key in (("+ elements", "elements_added"),
                               ("- elements", "elements_removed"),
                               ("+ text", "texts_added"),
                               ("- text", "texts_removed")):
                if d.get(key):
                    shown = ", ".join(d[key][:8])
                    extra = f" (+{len(d[key]) - 8} more)" if len(d[key]) > 8 else ""
                    print(f"  {label}: {shown}{extra}")
        print()

    # AT-SPI elements
    if result["atspi_elements"]:
        print("--- UI Elements (AT-SPI) ---")
        for e in result["atspi_elements"]:
            marker = " ▸" if e["interactive"] else "  "
            name_str = f" \"{e['name']}\"" if e["name"] else ""
            print(f"  {marker} {e.get('ref', '')} [{e['role']}]{name_str} @ ({e['x']}, {e['y']})")

    # OCR texts
    if result["ocr_texts"]:
        print()
        print("--- Text Regions (OCR) ---")
        for r in result["ocr_texts"]:
            print(f"  {r.get('ref', '')} \"{r['text']}\" @ ({r['x']}, {r['y']}) [{r['confidence']}%]")

    # Zones
    if result["zones"]:
        print()
        print("--- Layout Zones ---")
        for zone, elems in result["zones"].items():
            labels = ", ".join(
                f"{e['role']}:{e['name'][:20]}" if e['name'] else e['role']
                for e in elems[:5]
            )
            if len(elems) > 5:
                labels += f" (+{len(elems) - 5} more)"
            print(f"  [{zone}] {labels}")

    print()
    print(f"Token estimate: ~{_token_estimate(result)} tokens")
    print()

    # JSON version for AI consumption
    print("--- Machine-readable (JSON) ---")
    compact = {
        "screen": result["screen"],
        "summary": result["summary"],
        "n_elements": len(result["atspi_elements"]),
        "n_ocr": len(result["ocr_texts"]),
        "interactive": [
            {"ref": e.get("ref"), "role": e["role"], "name": e["name"],
             "pos": (e["x"], e["y"])}
            for e in result["atspi_elements"] if e["interactive"]
        ],
        "all_text": [r["text"] for r in result["ocr_texts"]],
    }
    print(json.dumps(compact, indent=2))


def _token_estimate(result):
    """Rough token estimate for the structured output."""
    total = 0
    total += len(json.dumps(result.get("screen", {})))
    for e in result.get("atspi_elements", []):
        total += len(e.get("name", "")) + len(e.get("role", ""))
    for r in result.get("ocr_texts", []):
        total += len(r.get("text", ""))
    total += len(result.get("summary", ""))
    # Rough: ~4 chars per token for structured JSON
    return total // 4

