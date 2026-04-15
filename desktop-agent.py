#!/usr/bin/python3
"""desktop-agent - Desktop automation CLI for AI agents
Similar mechanics to agent-browser but for Linux desktop
WITH AT-SPI SUPPORT for element detection!
"""

import subprocess
import sys
import os
import json
import time
from pathlib import Path
from difflib import SequenceMatcher

try:
    from PIL import Image, ImageDraw, ImageFont

    PIL_AVAILABLE = True
except ImportError:
    PIL_AVAILABLE = False

try:
    import pyatspi

    ATSPI_AVAILABLE = True
except ImportError:
    ATSPI_AVAILABLE = False

try:
    import pytesseract

    OCR_AVAILABLE = True
except ImportError:
    OCR_AVAILABLE = False

# Task Recording System
import sqlite3
import threading
import requests
from datetime import datetime
import math

CACHE_DIR = Path.home() / ".cache" / "desktop-agent"
CACHE_DIR.mkdir(parents=True, exist_ok=True)
DB_PATH = CACHE_DIR / "tasks.db"

EMBED_URL = "http://localhost:9086/v1/embeddings"
EMBED_MODEL = "nomic"

RECORDING_FILE = CACHE_DIR / "recording.json"


def load_recording():
    if RECORDING_FILE.exists():
        try:
            with open(RECORDING_FILE, "r") as f:
                data = json.load(f)
                return data.get("active", False), data.get("steps", [])
        except:
            pass
    return False, []


def save_recording(active, steps):
    with open(RECORDING_FILE, "w") as f:
        json.dump({"active": active, "steps": steps}, f)


RECORDING_ACTIVE, RECORDING_BUFFER = load_recording()


def init_db():
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("""
        CREATE TABLE IF NOT EXISTS tasks (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT UNIQUE NOT NULL,
            description TEXT,
            purpose TEXT,
            context TEXT,
            app_context TEXT,
            steps_json TEXT,
            embedding BLOB,
            success_rate REAL DEFAULT 1.0,
            last_used TIMESTAMP,
            use_count INTEGER DEFAULT 0,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    c.execute("""
        CREATE TABLE IF NOT EXISTS task_runs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            task_id INTEGER,
            executed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            success INTEGER,
            notes TEXT,
            FOREIGN KEY (task_id) REFERENCES tasks(id)
        )
    """)
    conn.commit()
    conn.close()


def get_embedding(text):
    try:
        resp = requests.post(
            EMBED_URL, json={"input": [text], "model": "nomic"}, timeout=10
        )
        data = resp.json()
        return data["data"][0]["embedding"]
    except Exception as e:
        print(f"Warning: Embedding failed: {e}")
        return None


def cosine_similarity(a, b):
    dot = sum(x * y for x, y in zip(a, b))
    norm_a = math.sqrt(sum(x * x for x in a))
    norm_b = math.sqrt(sum(x * x for x in b))
    return dot / (norm_a * norm_b + 1e-8)


def start_recording():
    global RECORDING_ACTIVE, RECORDING_BUFFER
    RECORDING_ACTIVE = True
    RECORDING_BUFFER = []
    save_recording(True, [])
    print(
        "Recording started. Use desktop-agent commands normally, then 'save-task' to save."
    )


def stop_recording():
    global RECORDING_ACTIVE
    RECORDING_ACTIVE = False
    steps = list(RECORDING_BUFFER)
    save_recording(False, [])
    return steps


def record_step(command, args, description=""):
    global RECORDING_BUFFER
    if not RECORDING_ACTIVE:
        return
    step = {
        "command": command,
        "args": args,
        "description": description,
        "timestamp": time.time(),
    }
    RECORDING_BUFFER.append(step)
    save_recording(True, RECORDING_BUFFER)


def save_task(name, description="", purpose="", context="", app_context=""):
    steps = stop_recording()
    if not steps:
        print("No steps recorded.")
        return False

    steps_json = json.dumps(steps)
    embed_text = f"{name}. {description}. {purpose}"
    embedding = get_embedding(embed_text)

    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    try:
        c.execute(
            """
            INSERT INTO tasks (name, description, purpose, context, app_context, steps_json, embedding)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
            (
                name,
                description,
                purpose,
                context,
                app_context,
                steps_json,
                json.dumps(embedding) if embedding else None,
            ),
        )
        conn.commit()
        print(f"Task saved: {name}")
        return True
    except sqlite3.IntegrityError:
        print(f"Task '{name}' already exists. Use 'tasks update' to overwrite.")
        return False
    finally:
        conn.close()


def list_tasks():
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute(
        "SELECT name, description, purpose, use_count, created_at FROM tasks ORDER BY use_count DESC"
    )
    rows = c.fetchall()
    conn.close()
    if not rows:
        print("No tasks saved.")
        return
    print(f"\nSaved Tasks ({len(rows)}):")
    for name, desc, purpose, use_count, created in rows:
        print(f"  • {name}")
        if desc:
            print(f"    {desc}")
        if purpose:
            print(f"    Purpose: {purpose}")
        print(f"    Used: {use_count}x | Created: {created[:10]}")


def search_tasks(query, limit=5):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("SELECT name, description, purpose, steps_json FROM tasks")
    rows = c.fetchall()
    conn.close()

    if not rows:
        print("No tasks to search.")
        return

    query_emb = get_embedding(query)
    if not query_emb:
        print("Search failed - could not embed query.")
        return

    results = []
    for name, desc, purpose, steps_json in rows:
        if not desc:
            desc = ""
        stored_emb = get_embedding(f"{name}. {desc}. {purpose or ''}")
        if stored_emb:
            sim = cosine_similarity(query_emb, stored_emb)
            results.append((sim, name, desc, purpose, steps_json))

    results.sort(reverse=True)

    print(f"\nSearch results for '{query}':")
    for sim, name, desc, purpose, steps_json in results[:limit]:
        print(f"  [{int(sim * 100)}%] {name}")
        if desc:
            print(f"    {desc}")
        if purpose:
            print(f"    Purpose: {purpose}")


def replay_task(query):
    # First try exact match
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("SELECT id, steps_json FROM tasks WHERE name = ?", (query,))
    row = c.fetchone()

    if not row:
        conn.close()
        # Try semantic search
        query_emb = get_embedding(query)
        if query_emb:
            conn = sqlite3.connect(DB_PATH)
            c = conn.cursor()
            c.execute("SELECT id, name, description, purpose, steps_json FROM tasks")
            rows = c.fetchall()
            conn.close()

            if not rows:
                print("No tasks found.")
                return None

            results = []
            for task_id, name, desc, purpose, steps_json in rows:
                if not desc:
                    desc = ""
                stored_emb = get_embedding(f"{name}. {desc}. {purpose or ''}")
                if stored_emb:
                    sim = cosine_similarity(query_emb, stored_emb)
                    results.append((sim, task_id, name, desc, purpose, steps_json))

            results.sort(reverse=True)

            if results:
                best = results[0]
                print(
                    f"Found task via semantic search: '{best[2]}' ({int(best[0] * 100)}% match)"
                )
                task_id, steps_json = best[1], best[5]
            else:
                print("No matching tasks found.")
                return None
        else:
            print("Could not embed query.")
            return None
    else:
        task_id, steps_json = row

    steps = json.loads(steps_json)

    # Update use count
    if task_id:
        conn = sqlite3.connect(DB_PATH)
        c = conn.cursor()
        c.execute(
            "UPDATE tasks SET use_count = use_count + 1, last_used = CURRENT_TIMESTAMP WHERE id = ?",
            (task_id,),
        )
        conn.commit()
        conn.close()

    return steps


def delete_task(name):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("DELETE FROM tasks WHERE name = ?", (name,))
    deleted = c.rowcount
    conn.commit()
    conn.close()
    if deleted:
        print(f"Deleted task: {name}")
    else:
        print(f"Task not found: {name}")


init_db()

SCREENSHOT_DIR = Path("/tmp/desktop-agent")
SCREENSHOT_DIR.mkdir(exist_ok=True)

# Stable element registry - persists across snapshots
# Key: stable_id, Value: selector that can re-locate element
STABLE_ELEMENT_REGISTRY = {}


def run_cmd(cmd):
    result = subprocess.run(cmd, shell=True, capture_output=True, text=True)
    return result.stdout.strip(), result.stderr.strip(), result.returncode


def screenshot(path=None):
    if path is None:
        path = SCREENSHOT_DIR / "screen.png"
    path = Path(path)

    run_cmd(f"scrot '{path}'")
    if path.exists():
        print(f"Screenshot saved to {path}")
        return str(path)
    else:
        print(f"Error: Screenshot failed")
        return None


def region_screenshot(x, y, width, height, path=None):
    if path is None:
        path = SCREENSHOT_DIR / "region.png"
    path = Path(path)

    run_cmd(f"scrot '{path}' -a {x},{y},{width},{height}")
    if path.exists():
        print(f"Region screenshot saved to {path}")
        return str(path)
    else:
        print(f"Error: Region screenshot failed")
        return None


def list_windows():
    stdout, _, _ = run_cmd("xdotool search --onlyvisible --name '.'")
    windows = []
    for wid in stdout.split("\n"):
        if wid.strip():
            name, _, _ = run_cmd(f"xdotool getwindowname {wid}")
            pid, _, _ = run_cmd(f"xdotool getwindowpid {wid}")
            geom, _, _ = run_cmd(f"xdotool getwindowgeometry {wid}")
            windows.append({"id": wid, "name": name, "pid": pid, "geometry": geom})
    return windows


def focus_window(name):
    run_cmd(f'xdotool search --onlyvisible --name "{name}" windowactivate')


def click(x, y):
    run_cmd(f"xdotool mousemove {x} {y} click 1")
    print(f"Clicked at ({x}, {y})")


def click_element(ref, force_confidence_threshold=0.5):
    """Click an element by its @eN reference

    Args:
        ref: Element reference like @e5
        force_confidence_threshold: Minimum confidence to proceed without warning (default 0.5)

    Returns:
        True if clicked, False otherwise
    """
    global ELEMENT_CACHE, STABLE_ELEMENT_REGISTRY

    # Try to find the ref - might be a pinned element that needs relinking
    if ref not in ELEMENT_CACHE:
        # Check if it's a stale ref that might need relinking
        # First try to relink any pinned elements
        if STABLE_ELEMENT_REGISTRY:
            results = relink_pinned_elements()

        # Try again after relinking
        if ref not in ELEMENT_CACHE:
            print(f"Error: Element {ref} not found. Run 'snapshot -i' first.")
            return False

    elem = ELEMENT_CACHE[ref]
    x, y = elem["x"], elem["y"]
    confidence = elem.get("confidence", 1.0)  # Default to 1.0 for fresh snapshots

    name_str = elem["name"][:30] if elem["name"] else "(unnamed)"

    # Show confidence warning if low
    if confidence < 1.0:
        conf_pct = int(confidence * 100)
        if confidence < force_confidence_threshold:
            print(
                f"⚠ Low confidence ({conf_pct}%) for {ref}: {name_str} [{elem['role']}]"
            )
            print(f"   Position: ({x}, {y})")

            # Show alternatives
            alternatives = elem.get("alternatives", [])
            if alternatives:
                print(f"   Alternatives:")
                for i, alt in enumerate(alternatives[:3], 1):
                    alt_name = alt["name"][:25] if alt["name"] else "(unnamed)"
                    alt_conf = int(alt["confidence"] * 100)
                    print(
                        f"     [{i}] {alt_name} @ ({alt['x']}, {alt['y']}) - {alt_conf}% confidence"
                    )
            return False  # Require explicit confirmation for low confidence
        else:
            print(
                f"? {ref}: {name_str} [{elem['role']}] at ({x}, {y}) - {conf_pct}% confidence (proceeding)"
            )

    print(f"Clicking {ref}: {name_str} [{elem['role']}] at ({x}, {y})")
    click(x, y)
    return True


def dblclick(x, y):
    run_cmd(f"xdotool mousemove {x} {y} click 1 click 1")
    print(f"Double-clicked at ({x}, {y})")


def move(x, y):
    run_cmd(f"xdotool mousemove {x} {y}")
    print(f"Moved to ({x}, {y})")


def type_text(text):
    # Escape special characters for xdotool
    run_cmd(f'xdotool type --delay 50 "{text}"')
    print(f"Typed: {text}")


def press_key(key):
    run_cmd(f"xdotool key {key}")
    print(f"Pressed: {key}")


def get_active_window():
    wid, _, _ = run_cmd("xdotool getactivewindow")
    name, _, _ = run_cmd(f"xdotool getwindowname {wid}")
    pid, _, _ = run_cmd(f"xdotool getwindowpid {wid}")
    geom, _, _ = run_cmd(f"xdotool getwindowgeometry {wid}")

    return {"id": wid, "name": name, "pid": pid, "geometry": geom}


def get_mouse_position():
    loc, _, _ = run_cmd("xdotool getmouselocation")
    parts = loc.split()
    coords = {}
    for p in parts:
        if ":" in p:
            k, v = p.split(":")
            coords[k] = v
    return coords


def get_screen_size():
    """Get screen dimensions"""
    # Try xdotool first
    out, _, _ = run_cmd("xdotool getdisplaygeometry")
    if out:
        parts = out.split()
        if len(parts) >= 2:
            return int(parts[0]), int(parts[1])

    # Fallback to xrandr
    out, _, _ = run_cmd("xrandr | grep '*' | awk '{print $1}'")
    if out and "x" in out:
        parts = out.split("x")
        return int(parts[0]), int(parts[1])

    # Default
    return 1920, 1080


def find_text_on_screen(text, case_sensitive=False, return_all=False):
    """Find text on screen using OCR and return its location

    Args:
        text: Text to search for
        case_sensitive: Whether to match case exactly
        return_all: If True, return all matches as JSON; if False, return best match

    Returns:
        If return_all=True: List of all matches with positions
        If return_all=False: Best match (for backwards compatibility)
    """
    if not OCR_AVAILABLE:
        print("⚠️  OCR not available. Install with: pip3 install pytesseract")
        return None if not return_all else []

    if not PIL_AVAILABLE:
        print("⚠️  PIL not available. Install with: pip3 install Pillow")
        return None if not return_all else []

    # Take screenshot
    ss_path = SCREENSHOT_DIR / "ocr_search.png"
    screenshot(ss_path)

    # Run OCR
    img = Image.open(ss_path)

    # Get detailed OCR data with bounding boxes
    data = pytesseract.image_to_data(img, output_type=pytesseract.Output.DICT)

    # Search for text
    search_text = text if case_sensitive else text.lower()
    matches = []

    for i, word in enumerate(data["text"]):
        if word:
            compare_word = word if case_sensitive else word.lower()

            # Exact match or substring match
            if search_text in compare_word or compare_word in search_text:
                x, y, w, h = (
                    data["left"][i],
                    data["top"][i],
                    data["width"][i],
                    data["height"][i],
                )
                conf = data["conf"][i]

                # Only include confident matches
                if int(conf) > 30:
                    matches.append(
                        {
                            "text": word,
                            "x": x + w // 2,  # Center point
                            "y": y + h // 2,
                            "width": w,
                            "height": h,
                            "confidence": int(conf),
                            "bounds": (x, y, w, h),
                        }
                    )

    if matches:
        # Sort by confidence
        matches.sort(key=lambda m: m["confidence"], reverse=True)
        print(f"Found {len(matches)} match(es) for '{text}':")
        for i, match in enumerate(matches[:10], 1):
            print(
                f"  [{i}] '{match['text']}' at ({match['x']}, {match['y']}) - confidence: {match['confidence']}%"
            )

        if return_all:
            # Return ALL matches as JSON for AI reasoning
            print(f"\n[JSON_OUTPUT_START]")
            print(json.dumps(matches, indent=2))
            print(f"[JSON_OUTPUT_END]")
            return matches
        else:
            # Return best match (backwards compatible)
            return matches[0]
    else:
        print(f"Text '{text}' not found on screen")
        return [] if return_all else None


def get_element_bounds(element):
    """Get screen coordinates for an accessible element"""
    try:
        component = element.queryComponent()
        extents = component.getExtents(pyatspi.DESKTOP_COORDS)
        x, y, w, h = extents.x, extents.y, extents.width, extents.height

        # Return center point for clicking
        center_x = x + w // 2
        center_y = y + h // 2

        return {
            "x": center_x,
            "y": center_y,
            "width": w,
            "height": h,
            "bounds": (x, y, w, h),
        }
    except:
        return None


def create_element_selector(element):
    """Create a stable selector from an AT-SPI element that can be used to re-locate it"""
    try:
        # Build a selector with multiple matching strategies
        selector = {
            "role": element.getRoleName(),
            "name": element.name if element.name else None,
            "description": element.description if element.description else None,
            "app_name": None,
            "index": None,
            "attrs": {},
        }

        # Get app name from parent
        try:
            parent = element.parent
            while parent:
                try:
                    if parent.getRole() == pyatspi.ROLE_APPLICATION:
                        selector["app_name"] = parent.name
                        break
                except:
                    break
                parent = parent.parent
        except:
            pass

        # Try to get unique index among siblings
        try:
            parent = element.parent
            if parent:
                index = 0
                for i in range(parent.childCount):
                    try:
                        sibling = parent.getChildAtIndex(i)
                        if sibling.getRole() == element.getRole():
                            if sibling == element:
                                selector["index"] = index
                                break
                            index += 1
                    except:
                        pass
        except:
            pass

        # Get useful attributes
        try:
            attrs = element.getAttributes()
            if attrs:
                selector["attrs"] = dict(attrs)
        except:
            pass

        return selector
    except:
        return None


def calculate_name_confidence(elem_name, selector_name):
    """Calculate confidence score for name matching using fuzzy matching"""
    if not selector_name:
        return 1.0  # No name constraint = match

    elem_name = elem_name or ""
    selector_name_lower = selector_name.lower()
    elem_name_lower = elem_name.lower()

    # Exact match
    if selector_name_lower == elem_name_lower:
        return 1.0

    # Substring matches get high scores
    if selector_name_lower in elem_name_lower:
        # Longer selector names within shorter elem names = better match
        return 0.85 + (len(selector_name) / max(len(elem_name), 1)) * 0.1
    if elem_name_lower in selector_name_lower:
        return 0.80

    # Fuzzy matching using SequenceMatcher
    ratio = SequenceMatcher(None, selector_name_lower, elem_name_lower).ratio()
    return ratio


def selector_matches(element, selector):
    """Check if an element matches a selector (basic check)"""
    try:
        # Must match role
        if selector.get("role") and element.getRoleName() != selector["role"]:
            return False

        return True
    except:
        return False


def calculate_match_confidence(element, selector):
    """Calculate overall confidence score for a selector match (0.0 to 1.0)"""
    confidence = 1.0

    # Role match is binary (already verified)
    # Name matching is weighted
    name_conf = calculate_name_confidence(
        element.name if element.name else "", selector.get("name")
    )
    confidence *= 0.5 + name_conf * 0.5  # Name contributes 50% to overall

    # Description similarity
    if selector.get("description"):
        desc_conf = calculate_name_confidence(
            element.description if element.description else "", selector["description"]
        )
        confidence *= 0.7 + desc_conf * 0.3  # Desc contributes 30%

    # App name exact match
    if selector.get("app_name"):
        try:
            parent = element.parent
            elem_app = None
            while parent:
                try:
                    if parent.getRole() == pyatspi.ROLE_APPLICATION:
                        elem_app = parent.name
                        break
                except:
                    break
                parent = parent.parent
            if elem_app and elem_app == selector["app_name"]:
                confidence *= 1.1  # Slight boost for app match (capped later)
            else:
                confidence *= 0.7  # Penalty for wrong app
        except:
            pass

    # Cap at 1.0
    return min(confidence, 1.0)


def find_all_elements_by_selector(desktop, selector, max_depth=15, min_confidence=0.3):
    """Find all elements matching selector with confidence scores, sorted by confidence"""
    all_matches = []

    try:
        for i in range(desktop.childCount):
            try:
                app = desktop.getChildAtIndex(i)
                if app.name:
                    # Check if this is the right app (soft check - still search if app_name is None)
                    if selector.get("app_name") and app.name != selector["app_name"]:
                        continue

                    # Search in this app's tree
                    matches = _search_tree_for_all_matches(
                        app, selector, 0, max_depth, min_confidence
                    )
                    all_matches.extend(matches)
            except:
                pass
    except:
        pass

    # Sort by confidence (highest first)
    all_matches.sort(key=lambda x: x["confidence"], reverse=True)
    return all_matches


def _search_tree_for_all_matches(element, selector, depth, max_depth, min_confidence):
    """Recursively search tree for ALL elements matching selector with confidence scores"""
    matches = []

    if depth > max_depth:
        return matches

    try:
        # Check if this element matches the basic criteria
        if selector_matches(element, selector):
            confidence = calculate_match_confidence(element, selector)

            if confidence >= min_confidence:
                bounds = get_element_bounds(element)
                if bounds:
                    matches.append(
                        {
                            "element": element,
                            "name": element.name
                            if element.name
                            else element.getRoleName(),
                            "role": element.getRoleName(),
                            "description": element.description
                            if element.description
                            else None,
                            "x": bounds["x"],
                            "y": bounds["y"],
                            "width": bounds["width"],
                            "height": bounds["height"],
                            "bounds": bounds["bounds"],
                            "confidence": confidence,
                        }
                    )

        # Search children
        for i in range(element.childCount):
            try:
                child = element.getChildAtIndex(i)
                child_matches = _search_tree_for_all_matches(
                    child, selector, depth + 1, max_depth, min_confidence
                )
                matches.extend(child_matches)
            except:
                pass
    except:
        pass

    return matches


def find_element_by_selector(desktop, selector, max_depth=15):
    """Re-locate an element using its selector (legacy function for compatibility)"""
    matches = find_all_elements_by_selector(
        desktop, selector, max_depth, min_confidence=0.5
    )
    return matches[0] if matches else None


def _search_tree_for_match(element, selector, depth, max_depth):
    """Recursively search tree for element matching selector (legacy, returns first match)"""
    if depth > max_depth:
        return None

    try:
        # Check if this element matches
        if selector_matches(element, selector):
            bounds = get_element_bounds(element)
            if bounds:
                return {
                    "element": element,
                    "name": element.name if element.name else element.getRoleName(),
                    "role": element.getRoleName(),
                    "x": bounds["x"],
                    "y": bounds["y"],
                    "width": bounds["width"],
                    "height": bounds["height"],
                    "bounds": bounds["bounds"],
                }

        # Search children
        for i in range(element.childCount):
            try:
                child = element.getChildAtIndex(i)
                result = _search_tree_for_match(child, selector, depth + 1, max_depth)
                if result:
                    return result
            except:
                pass
    except:
        pass

    return None


def pin_element(ref):
    """Pin an element so it survives across snapshots - returns stable_id"""
    global ELEMENT_CACHE, STABLE_ELEMENT_REGISTRY

    if ref not in ELEMENT_CACHE:
        print(f"Error: Element {ref} not found. Run 'snapshot -i' first.")
        return None

    elem = ELEMENT_CACHE[ref]

    # Create a selector for this element
    selector = create_element_selector(elem["element"]) if "element" in elem else None

    if not selector:
        print(f"Error: Could not create selector for {ref}")
        return None

    # Generate stable ID
    stable_id = f"pin_{len(STABLE_ELEMENT_REGISTRY) + 1}"

    # Store in registry with selector and last known position
    STABLE_ELEMENT_REGISTRY[stable_id] = {
        "selector": selector,
        "last_x": elem["x"],
        "last_y": elem["y"],
        "last_width": elem.get("width"),
        "last_height": elem.get("height"),
        "ref": ref,
    }

    print(f"Pinned {ref} as {stable_id}: {selector['name'] or selector['role']}")
    return stable_id


def relink_pinned_elements():
    """Re-locate all pinned elements and update their positions with confidence scores"""
    global STABLE_ELEMENT_REGISTRY, ELEMENT_CACHE

    if not STABLE_ELEMENT_REGISTRY:
        return []

    desktop = None
    try:
        desktop = pyatspi.Registry.getDesktop(0)
    except:
        print("Error: Could not access AT-SPI")
        return []

    results = []
    for stable_id, entry in list(STABLE_ELEMENT_REGISTRY.items()):
        selector = entry["selector"]

        # Find all matches with confidence scores
        matches = find_all_elements_by_selector(desktop, selector, min_confidence=0.3)

        if matches:
            best_match = matches[0]
            orig_ref = entry["ref"]

            # Update the cache entry with best match
            ELEMENT_CACHE[orig_ref] = best_match

            # Update registry with new position
            STABLE_ELEMENT_REGISTRY[stable_id]["last_x"] = best_match["x"]
            STABLE_ELEMENT_REGISTRY[stable_id]["last_y"] = best_match["y"]
            STABLE_ELEMENT_REGISTRY[stable_id]["stale"] = False
            STABLE_ELEMENT_REGISTRY[stable_id]["confidence"] = best_match["confidence"]

            # Store alternatives (next best matches)
            STABLE_ELEMENT_REGISTRY[stable_id]["alternatives"] = matches[1:6]

            results.append(
                {
                    "stable_id": stable_id,
                    "ref": orig_ref,
                    "confidence": best_match["confidence"],
                    "name": best_match["name"],
                    "x": best_match["x"],
                    "y": best_match["y"],
                    "alternatives": matches[1:6],
                }
            )
        else:
            # Element no longer found - mark as stale
            STABLE_ELEMENT_REGISTRY[stable_id]["stale"] = True
            STABLE_ELEMENT_REGISTRY[stable_id]["confidence"] = 0.0
            STABLE_ELEMENT_REGISTRY[stable_id]["alternatives"] = []

            results.append(
                {
                    "stable_id": stable_id,
                    "ref": entry["ref"],
                    "confidence": 0.0,
                    "name": selector.get("name") or selector.get("role", "unknown"),
                    "x": None,
                    "y": None,
                    "alternatives": [],
                }
            )

    # Print summary
    relinked = sum(1 for r in results if r["confidence"] > 0)
    stale = sum(1 for r in results if r["confidence"] == 0)

    if relinked > 0:
        print(f"Relinked {relinked} pinned element(s)")
        for r in results:
            if r["confidence"] > 0:
                conf_pct = int(r["confidence"] * 100)
                status = (
                    "✓"
                    if r["confidence"] >= 0.7
                    else "?"
                    if r["confidence"] >= 0.5
                    else "!"
                )
                print(
                    f"  {status} {r['ref']}: '{r['name']}' @ ({r['x']}, {r['y']}) - {conf_pct}% confidence"
                )
    if stale > 0:
        print(f"  ⚠ {stale} element(s) could not be found")

    return results


def list_pinned():
    """List all pinned elements with confidence scores"""
    global STABLE_ELEMENT_REGISTRY

    if not STABLE_ELEMENT_REGISTRY:
        print("No pinned elements")
        return

    print(f"Pinned Elements ({len(STABLE_ELEMENT_REGISTRY)}):")
    for stable_id, entry in STABLE_ELEMENT_REGISTRY.items():
        selector = entry["selector"]
        name = selector.get("name") or selector.get("role", "unknown")
        stale = " [STALE]" if entry.get("stale") else ""
        conf = entry.get("confidence", 0)
        if conf > 0:
            conf_str = f" ({int(conf * 100)}% confidence)"
        else:
            conf_str = ""
        print(
            f"  {stable_id}: {name} at ({entry['last_x']}, {entry['last_y']}){conf_str}{stale}"
        )


def walk_tree(element, depth=0, max_depth=10, elements=None):
    """Recursively walk the accessibility tree"""
    if elements is None:
        elements = []

    if depth > max_depth:
        return elements

    try:
        # Filter for interactive elements
        role = element.getRole()
        state_set = element.getState()

        # Roles we care about (buttons, links, text fields, etc.)
        interactive_roles = [
            pyatspi.ROLE_PUSH_BUTTON,
            pyatspi.ROLE_LINK,
            pyatspi.ROLE_TEXT,
            pyatspi.ROLE_ENTRY,
            pyatspi.ROLE_MENU_ITEM,
            pyatspi.ROLE_MENU,
            pyatspi.ROLE_CHECK_BOX,
            pyatspi.ROLE_RADIO_BUTTON,
            pyatspi.ROLE_TOGGLE_BUTTON,
            pyatspi.ROLE_LIST_ITEM,
            pyatspi.ROLE_PAGE_TAB,  # FIXED: was ROLE_TAB
            pyatspi.ROLE_COMBO_BOX,
            pyatspi.ROLE_LABEL,
            pyatspi.ROLE_ICON,
            pyatspi.ROLE_MENU_BAR,
        ]

        # Check if element is visible and showing
        is_visible = state_set.contains(pyatspi.STATE_VISIBLE) and state_set.contains(
            pyatspi.STATE_SHOWING
        )

        if role in interactive_roles and is_visible:
            bounds = get_element_bounds(element)
            if bounds and bounds["width"] > 5 and bounds["height"] > 5:
                name = element.name if element.name else element.getRoleName()
                description = element.description if element.description else ""

                elements.append(
                    {
                        "element": element,
                        "name": name,
                        "role": element.getRoleName(),
                        "description": description,
                        "x": bounds["x"],
                        "y": bounds["y"],
                        "width": bounds["width"],
                        "height": bounds["height"],
                        "bounds": bounds["bounds"],
                    }
                )

        # Recurse through children
        for i in range(element.childCount):
            try:
                child = element.getChildAtIndex(i)
                walk_tree(child, depth + 1, max_depth, elements)
            except:
                pass

    except:
        pass

    return elements


def snapshot(interactive=False):
    """Get comprehensive UI snapshot"""
    global ELEMENT_CACHE

    print("=== Desktop UI Snapshot ===\n")

    # Active window
    active = get_active_window()
    print(f"Active Window:")
    print(f"  ID: {active['id']}")
    print(f"  Name: {active['name']}")
    print(f"  PID: {active['pid']}")

    # Mouse position
    mouse = get_mouse_position()
    print(f"\nMouse Position: x={mouse.get('x', '?')}, y={mouse.get('y', '?')}")

    # Take screenshot first
    ss_path = SCREENSHOT_DIR / "snapshot.png"
    screenshot(ss_path)

    # Interactive mode: Use AT-SPI to find elements
    if interactive:
        if not ATSPI_AVAILABLE:
            print(
                "\n⚠️  AT-SPI not available. Install with: sudo apt install python3-pyatspi"
            )
            print("Falling back to coordinate-based interaction.")
            return {"active_window": active, "mouse": mouse, "elements": []}

        print(f"\nScanning for interactive elements (AT-SPI)...")

        # Clear cache
        ELEMENT_CACHE.clear()

        # Get all accessible applications
        desktop = pyatspi.Registry.getDesktop(0)
        all_elements = []

        # Walk the tree for all apps
        for i in range(desktop.childCount):
            try:
                app = desktop.getChildAtIndex(i)
                if app.name:  # Skip unnamed apps
                    elements = walk_tree(app, max_depth=12)
                    all_elements.extend(elements)
            except:
                pass

        # Get screen size for filtering
        screen_w, screen_h = get_screen_size()

        # Filter to visible, reasonable size, on-screen
        visible_elements = []
        for elem in all_elements:
            # Filter out very small or offscreen elements
            if elem["width"] > 5 and elem["height"] > 5:
                if 0 <= elem["x"] < screen_w and 0 <= elem["y"] < screen_h:
                    visible_elements.append(elem)

        # Sort by y position (top to bottom), then x (left to right)
        visible_elements.sort(key=lambda e: (e["y"], e["x"]))

        # Limit to most relevant elements
        MAX_ELEMENTS = 50
        if len(visible_elements) > MAX_ELEMENTS:
            print(f"Found {len(visible_elements)} elements, showing top {MAX_ELEMENTS}")
            visible_elements = visible_elements[:MAX_ELEMENTS]

        # Assign refs
        if visible_elements:
            print(f"\nInteractive Elements ({len(visible_elements)} found):")
            for i, elem in enumerate(visible_elements, 1):
                ref = f"@e{i}"
                ELEMENT_CACHE[ref] = elem

                # Print element info
                name = elem["name"][:40] if elem["name"] else "(unnamed)"
                role = elem["role"]
                desc = f" - {elem['description'][:20]}" if elem["description"] else ""
                print(f"  {ref}: {name} [{role}]{desc} at ({elem['x']}, {elem['y']})")

            # Annotate screenshot
            if PIL_AVAILABLE and ss_path.exists():
                try:
                    img = Image.open(ss_path)
                    draw = ImageDraw.Draw(img)

                    for i, elem in enumerate(visible_elements, 1):
                        x, y = elem["x"], elem["y"]
                        w, h = elem["width"], elem["height"]

                        # Draw bounding box
                        x1, y1 = elem["bounds"][0], elem["bounds"][1]
                        x2, y2 = x1 + w, y1 + h
                        draw.rectangle([x1, y1, x2, y2], outline="cyan", width=2)

                        # Draw center point
                        draw.ellipse([x - 5, y - 5, x + 5, y + 5], fill="red")

                        # Draw ref label
                        draw.text((x + 10, y - 10), f"@e{i}", fill="cyan")

                    ann_path = SCREENSHOT_DIR / "snapshot_interactive.png"
                    img.save(ann_path)
                    print(f"\n📸 Annotated screenshot: {ann_path}")
                except Exception as e:
                    print(f"Warning: Could not annotate screenshot: {e}")
        else:
            print(
                "\nNo interactive elements found. Active window may not expose accessibility tree."
            )

    # All windows
    print(f"\nVisible Windows:")
    windows = list_windows()
    for i, win in enumerate(windows[:10], 1):
        print(f"  [{i}] {win['name'][:50]} (ID: {win['id']})")
    if len(windows) > 10:
        print(f"  ... and {len(windows) - 10} more")

    return {
        "active_window": active,
        "mouse": mouse,
        "windows": windows,
        "elements": list(ELEMENT_CACHE.keys()) if interactive else [],
    }


def main():
    if len(sys.argv) < 2:
        print("Usage: desktop-agent <command> [args]")
        print("Run 'desktop-agent --help' for full usage")
        sys.exit(1)

    cmd = sys.argv[1]
    args = sys.argv[2:]

    if cmd == "--help" or cmd == "-h":
        print("""
desktop-agent - Desktop automation CLI for AI agents

COMMANDS:
    screenshot [path]              Take full screenshot
    region <x,y,w,h> [path]      Screenshot of region
    windows                        List visible windows
    focus <name>                   Focus window by name
    click <x> <y>                 Click at coordinates
    click @eN                     Click element by ref (after snapshot -i)
    dblclick <x> <y>              Double click
    move <x> <y>                 Move mouse
    type "<text>"                 Type text
    key <keyname>                 Press key (Enter, Ctrl+c, etc.)
    active                         Get active window info
    mouse                          Get mouse position
    snapshot                       Full UI snapshot
    snapshot -i                   Interactive snapshot with AT-SPI elements
    find-text [--all] "<text>"    Find text using OCR (--all for JSON with all matches)
    pin @eN                      Pin element for stable refs
    pinned                        List pinned elements
    unpin [id]                   Unpin element(s)
    relink                        Re-search for pinned elements

TASK RECORDING (AI-curated):
    record                        Start recording task steps
    save-task <name> [options]   Save recorded task with metadata
                                  --description "what it does"
                                  --purpose "why useful"
                                  --context "when to use"
                                  --app-context "requirements"
    tasks                         List saved tasks
    tasks search <query>          Semantic search tasks
    replay [--run] <query>        Find and show/execute task
    forget <name>                 Delete a task

EXAMPLES:
    desktop-agent screenshot
    desktop-agent snapshot -i         # Find interactive elements
    desktop-agent click @e1           # Click element by ref
    desktop-agent click 100 200       # Click by coordinates
    desktop-agent find-text "Submit"  # Find text using OCR
    desktop-agent type "Hello World"
    desktop-agent key Ctrl+l
    desktop-agent windows
    desktop-agent pin @e5            # Pin element for stability
    desktop-agent pinned             # List pinned elements
    desktop-agent relink             # Refresh pinned element positions
    desktop-agent record             # Start recording
    desktop-agent save-task play-spotify-aeternum --description "Play Aeternum playlist" --purpose "Gaming background music"
    desktop-agent tasks search "play music"
    desktop-agent replay --run "play music"

AT-SPI ELEMENT DETECTION:
    Run 'snapshot -i' to scan for interactive UI elements
    Elements are assigned refs like @e1, @e2, @e3...
    Click elements with 'click @e1' instead of coordinates
    Similar to agent-browser mechanics!

STABLE ELEMENT REFS (PINNING):
    Elements become stale after UI changes. Use 'pin' to make them stable.
    Pinned elements auto-relink when clicked - coordinates update automatically.
    Use 'pinned' to see all pins, 'unpin' to remove them.

OCR TEXT FINDING:
    Use 'find-text' to locate text on screen using OCR
    Useful when AT-SPI doesn't expose elements
    Returns coordinates of the text for clicking
""")
        sys.exit(0)

    elif cmd in ["screenshot", "ss"]:
        path = args[0] if args else None
        screenshot(path)
        record_step("screenshot", args, f"Screenshot: {args[0] if args else 'default'}")

    elif cmd == "region":
        if len(args) < 1:
            print("Usage: region <x,y,w,h> [path]")
            sys.exit(1)
        coords = args[0].split(",")
        x, y, w, h = map(int, coords)
        path = args[1] if len(args) > 1 else None
        region_screenshot(x, y, w, h, path)
        record_step("region", args, f"Region screenshot: {args[0]}")

    elif cmd in ["windows", "win"]:
        for win in list_windows():
            print(f"{win['id']} | {win['pid']} | {win['name']}")

    elif cmd == "focus":
        if not args:
            print("Usage: focus <window-name>")
            sys.exit(1)
        focus_window(args[0])
        record_step("focus", args, f"Focus window: {args[0]}")

    elif cmd == "click":
        if len(args) < 1:
            print("Usage: click <x> <y> OR click @eN")
            sys.exit(1)

        # Check if it's an element ref
        if args[0].startswith("@e"):
            click_element(args[0])
            record_step("click", args, f"Click element: {args[0]}")
        else:
            if len(args) < 2:
                print("Usage: click <x> <y> OR click @eN")
                sys.exit(1)
            click(int(args[0]), int(args[1]))
            record_step("click", args, f"Click at ({args[0]}, {args[1]})")

    elif cmd == "dblclick":
        if len(args) < 2:
            print("Usage: dblclick <x> <y>")
            sys.exit(1)
        dblclick(int(args[0]), int(args[1]))

    elif cmd == "move":
        if len(args) < 2:
            print("Usage: move <x> <y>")
            sys.exit(1)
        move(int(args[0]), int(args[1]))

    elif cmd == "type":
        if not args:
            print("Usage: type <text>")
            sys.exit(1)
        type_text(" ".join(args))
        record_step("type", args, f"Type: {' '.join(args)[:50]}")

    elif cmd == "key":
        if not args:
            print("Usage: key <keyname>")
            sys.exit(1)
        press_key(args[0])
        record_step("key", args, f"Press key: {args[0]}")

    elif cmd == "active":
        active = get_active_window()
        print(json.dumps(active, indent=2))

    elif cmd == "mouse":
        print(json.dumps(get_mouse_position(), indent=2))

    elif cmd == "snapshot":
        interactive = "-i" in args or "--interactive" in args
        snapshot(interactive=interactive)

    elif cmd == "find-text":
        return_all = "--all" in args or "-a" in args
        if return_all:
            args = [a for a in args if a not in ("--all", "-a")]
        if not args:
            print("Usage: find-text [--all] <text>")
            print("  --all    Return all matches as JSON (for AI reasoning)")
            sys.exit(1)
        text = " ".join(args)
        result = find_text_on_screen(text, return_all=return_all)
        if not return_all and result:
            print(f"\nBest match: '{result['text']}' at ({result['x']}, {result['y']})")
            print(f"To click it: desktop-agent click {result['x']} {result['y']}")

    elif cmd == "pin":
        if not args:
            print("Usage: pin @eN")
            sys.exit(1)
        ref = args[0]
        stable_id = pin_element(ref)
        if stable_id:
            print(f"Use 'pinned' to list all pinned elements")
            print(
                f"Note: Pinned elements are automatically relinked when you click them"
            )

    elif cmd == "unpin":
        global STABLE_ELEMENT_REGISTRY
        if not args:
            # Unpin all
            count = len(STABLE_ELEMENT_REGISTRY)
            STABLE_ELEMENT_REGISTRY.clear()
            print(f"Unpinned {count} element(s)")
        else:
            stable_id = args[0]
            if stable_id in STABLE_ELEMENT_REGISTRY:
                del STABLE_ELEMENT_REGISTRY[stable_id]
                print(f"Unpinned {stable_id}")
            else:
                print(f"Unknown pinned element: {stable_id}")

    elif cmd == "pinned":
        list_pinned()

    elif cmd == "relink":
        relink_pinned_elements()

    elif cmd == "record":
        start_recording()
        print(
            "Recording enabled. Execute your task steps, then use 'save-task' to save."
        )

    elif cmd == "save-task":
        if not args:
            print(
                'Usage: save-task <name> [--description "..."] [--purpose "..."] [--context "..."] [--app-context "..."]'
            )
            sys.exit(1)
        name = args[0]
        description = ""
        purpose = ""
        context = ""
        app_context = ""
        i = 1
        while i < len(args):
            if args[i] == "--description" and i + 1 < len(args):
                description = args[i + 1]
                i += 2
            elif args[i] == "--purpose" and i + 1 < len(args):
                purpose = args[i + 1]
                i += 2
            elif args[i] == "--context" and i + 1 < len(args):
                context = args[i + 1]
                i += 2
            elif args[i] == "--app-context" and i + 1 < len(args):
                app_context = args[i + 1]
                i += 2
            else:
                i += 1
        save_task(name, description, purpose, context, app_context)

    elif cmd == "tasks":
        if len(args) > 0 and args[0] == "search":
            query = " ".join(args[1:]) if len(args) > 1 else ""
            if query:
                search_tasks(query)
            else:
                print("Usage: tasks search <query>")
        else:
            list_tasks()

    elif cmd == "replay":
        if not args:
            print("Usage: replay [--run] <task-name-or-query>")
            print("  --run    Actually execute the steps (default is dry-run)")
            sys.exit(1)

        run_mode = False
        query_args = args
        if "--run" in args:
            run_mode = True
            query_args = [a for a in args if a != "--run"]

        query = " ".join(query_args)
        steps = replay_task(query)

        if not steps:
            print("Task not found. Use 'tasks search <query>' to find similar tasks.")
            sys.exit(1)

        print(f"Found task with {len(steps)} steps:")
        for i, step in enumerate(steps, 1):
            print(f"  [{i}] {step['command']} {step.get('args', [])}")
            if step.get("description"):
                print(f"      → {step['description']}")

        if run_mode:
            print(f"\nExecuting {len(steps)} steps...")
            for i, step in enumerate(steps, 1):
                cmd_name = step.get("command", "")
                step_args = step.get("args", [])
                print(f"\nStep {i}/{len(steps)}: {cmd_name} {step_args}")

                if cmd_name == "focus":
                    if step_args:
                        focus_window(step_args[0])
                elif cmd_name == "click":
                    if len(step_args) >= 2:
                        click(int(step_args[0]), int(step_args[1]))
                elif cmd_name == "type":
                    if step_args:
                        type_text(" ".join(step_args))
                elif cmd_name == "key":
                    if step_args:
                        press_key(step_args[0])
                elif cmd_name == "find-text":
                    if step_args:
                        result = find_text_on_screen(" ".join(step_args))
                        if result:
                            click(result["x"], result["y"])
                elif cmd_name == "snapshot":
                    snapshot(interactive=True)
                elif cmd_name == "move":
                    if len(step_args) >= 2:
                        move(int(step_args[0]), int(step_args[1]))
                elif cmd_name == "dblclick":
                    if len(step_args) >= 2:
                        dblclick(int(step_args[0]), int(step_args[1]))

                time.sleep(0.5)

            print("\n✓ Replay complete!")
        else:
            print("\nDry-run mode. Use 'replay --run <task>' to execute.")

    elif cmd == "forget":
        if not args:
            print("Usage: forget <task-name>")
            sys.exit(1)
        delete_task(args[0])

    else:
        print(f"Unknown command: {cmd}")
        print("Run 'desktop-agent --help' for usage")
        sys.exit(1)


if __name__ == "__main__":
    main()
