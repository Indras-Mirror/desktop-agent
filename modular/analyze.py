# desktop-agent analyze — unified screen understanding for AI agents
#
# Combines AT-SPI tree + OCR text + spatial layout into one structured
# ~500-token output so local LLMs can "see" the screen without vision models.

from .config import ATSPI_AVAILABLE, PRIMARY_MONITOR
from .window import get_active_window
from .input import screenshot as take_screenshot
import json
import time
import os
import sys
import subprocess
from pathlib import Path
from collections import defaultdict


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

        name = element.name or ""
        desc = element.description or ""

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

def _ocr_screen(ss_path):
    """Run hybrid OCR on screenshot — Tesseract ensemble + RapidOCR union.

    Returns deduplicated, merged text regions with confidence scores.
    Uses upscaling, word merging, and multi-pass ensemble voting.
    """
    from .ocr import ocr_screen as do_ocr

    regions = do_ocr(ss_path, engine="rapidocr", min_confidence=40, max_regions=60)
    return regions


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

def analyze(output_format="text"):
    """Produce a unified screen analysis for AI consumption.

    Returns a dict (also printed to stdout) with:
        - screen: dimensions + active window
        - atspi_elements: condensed AT-SPI element list
        - ocr_text: OCR text regions
        - zones: spatial grouping
        - summary: human-readable one-liner
    """
    start = time.time()

    # -- Screenshot -----------------------------------------------------------
    mon = PRIMARY_MONITOR
    ss_path = Path("/tmp/desktop-agent") / "analyze.png"

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

    # Cap at 40 elements for token budget
    if len(deduped) > 40:
        # Keep interactive first, then closest to center
        interactive = [e for e in deduped if e["interactive"]]
        others = [e for e in deduped if not e["interactive"]]
        deduped = (interactive + others)[:40]

    # -- OCR text -------------------------------------------------------------
    text_regions = _ocr_screen(ss_path)
    text_regions.sort(key=lambda r: (r["y"], r["x"]))

    # Cap OCR results
    if len(text_regions) > 30:
        text_regions = text_regions[:30]

    # -- Zones ----------------------------------------------------------------
    zones = _group_by_zone(deduped, mon["width"], mon["height"])

    # -- Active window + PID for AT-SPI filtering ---------------------------
    try:
        active_win = get_active_window()
        active_name = active_win.get("name", "unknown")
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

    # AT-SPI elements
    if result["atspi_elements"]:
        print("--- UI Elements (AT-SPI) ---")
        for e in result["atspi_elements"]:
            marker = " ▸" if e["interactive"] else "  "
            name_str = f" \"{e['name']}\"" if e["name"] else ""
            print(f"  {marker} [{e['role']}]{name_str} @ ({e['x']}, {e['y']})")

    # OCR texts
    if result["ocr_texts"]:
        print()
        print("--- Text Regions (OCR) ---")
        for r in result["ocr_texts"]:
            print(f"  \"{r['text']}\" @ ({r['x']}, {r['y']}) [{r['confidence']}%]")

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
            {"role": e["role"], "name": e["name"], "pos": (e["x"], e["y"])}
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

