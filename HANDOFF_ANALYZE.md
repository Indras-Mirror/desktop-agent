# HANDOFF: `desktop-agent analyze` — Screen Understanding for AI Agents

**Date:** 2026-04-26  
**Branch:** `experimental-analyze`  
**Repo:** https://github.com/Indras-Mirror/desktop-agent/tree/experimental-analyze  
**Author:** Mal (malichcoory@gmail.com)

---

## UPDATE 2026-06-11 — v2 (branch `experimental-analyze-v2`)

Several P0/P2 items below are now DONE:

- **Persistent element refs** — analyze assigns `@e1..` to elements and `@t1..`
  to OCR text, persisted to `~/.cache/desktop-agent/elements.json` via the new
  `modular/element_cache.py`. `desktop-agent click @e3` now works from a
  *separate process* (previously ELEMENT_CACHE was in-memory only, so
  snapshot→click across two CLI invocations could never work). `snapshot -i`
  persists its refs too. New `desktop-agent refs` command lists the cache.
- **Detail levels** — `--quick` (AT-SPI only, no screenshot/OCR, ~0.7s),
  default, `--deep` (80 elements / 60 texts).
- **Change detection** — `analyze --diff` reports window/element/text changes
  vs the previous run (cached in `~/.cache/desktop-agent/last_analyze.json`).
- **Region targeting** — `--region top|bottom|left|right|center` or
  `--region x,y,w,h` filters AT-SPI elements and crops the screenshot before
  OCR (faster, less background noise).
- **Bugfix: RapidOCR coordinates** — `_ocr_rapidocr` upscaled the image 2x but
  never scaled coordinates back; every OCR coordinate was ~1.16x–2x off.
  Click-by-text was missing its targets because of this.
- **Bugfix: `click_element` called `click(x, y)`** — that signature passes y as
  the `verify` argument and always failed with "Invalid click target". Now uses
  `click_coords()`.

The agent loop is now:
```bash
desktop-agent analyze --json    # see (refs included)
desktop-agent click @e3         # act (resolves ref from disk cache)
desktop-agent analyze --diff    # verify (what changed?)
```

---

## Table of Contents
1. [What It Is](#1-what-it-is)
2. [Design Philosophy](#2-design-philosophy)
3. [Implementation Details](#3-implementation-details)
4. [CLI Usage](#4-cli-usage)
5. [Demo Workflow: Spotify Playlist Extraction](#5-demo-workflow-spotify-playlist-extraction)
6. [Known Issues & Pain Points](#6-known-issues--pain-points)
7. [Priority Improvements](#7-priority-improvements)
8. [Long-Term Roadmap](#8-long-term-roadmap)
9. [Testing & Validation Patterns](#9-testing--validation-patterns)
10. [Architecture Diagrams](#10-architecture-diagrams)
11. [Appendix: Key Code](#11-appendix-key-code)

---

## 1. What It Is

`desktop-agent analyze` is a unified screen understanding command for AI agents. It replaces the need for vision models (which require VRAM/API cost) by combining three data sources into a compact ~250-token structured output:

| Source | What It Gives | Typical Count |
|--------|---------------|---------------|
| **AT-SPI** | Accessibility tree: frames, buttons, menus, inputs with positions | ~40 elements (capped) |
| **OCR** | Tesseract text extraction from screenshot | ~30 text regions (capped) |
| **Spatial Zones** | Top/center/left/right/bottom layout grouping | ~5 zones |

### Why It Exists
- **Local LLMs don't have vision** — Qwen, Gemma, DeepSeek can't process images
- **Vision APIs cost tokens** — ~1-4K tokens per image vs ~250 for analyze
- **ASCII art is too expensive** — ~16K tokens for a usable resolution
- **AT-SPI alone is incomplete** — misses canvas-rendered text, custom widgets
- **OCR alone lacks structure** — no element roles, no hierarchy

---

## 2. Design Philosophy

### Core Principles
1. **~500 token budget** — Everything must fit in a small context window
2. **Interactive elements first** — Buttons, links, inputs are prioritized over containers
3. **AT-SPI is primary, OCR is supplementary** — AT-SPI gives structure, OCR fills gaps
4. **Spatial context matters** — Not just what's there, but where it is
5. **JSON-for-AI first, human-readable second** — The `--json` flag must produce clean, parseable output

### Token Budget Allocation
```
Screen info (window, resolution):      ~20 tokens
AT-SPI elements (40 × 3 tokens):       ~120 tokens
OCR texts (30 × 2 tokens):             ~60 tokens
Zones + summary:                        ~50 tokens
---------------------------------------------
Total:                                 ~250 tokens
```

---

## 3. Implementation Details

### File: `/home/mal/AI/desktop-agent/modular/analyze.py`
(New file, 429 lines, created this session)

### Entry Point
```python
def analyze(output_format="text"):
    # 1. Screenshot (primary monitor only, ~100ms)
    # 2. Walk AT-SPI tree → collect meaningful elements (~1s)
    # 3. Deduplicate + sort by position
    # 4. Cap at 40 elements (interactive first)
    # 5. OCR the screenshot → text regions (~800ms)
    # 6. Cap at 30 texts
    # 7. Group elements into spatial zones
    # 8. Build + return structured dict
    # 9. If json: print clean JSON; else: human-readable
```

### AT-SPI Element Collection (`_collect_elements`)
- Walks the pyatspi accessibility tree recursively (max_depth=15)
- **Skips:** containers (panel, filler, scroll pane, etc.) unless they have names
- **Skips:** invisible elements (STATE_VISIBLE + STATE_SHOWING required)
- **Skips:** elements outside primary monitor bounds
- **Skips:** too-tiny elements (w <= 2 or h <= 2)
- **Includes:** interactive roles (buttons, links, entries, menus, etc.)
- **Includes:** structural parents (frame, window, dialog)
- **Includes:** elements with names or descriptions
- **Skips application-level** nodes (they're always invisible in AT-SPI)

Key issue discovered: **AT-SPI applications are always marked invisible** by pyatspi. The original code checked visibility on every element, which caused ALL elements to be filtered out. Fixed by skipping the visibility check for `role == "application"`.

### OCR Text Extraction (`_ocr_screen`)
- Uses pytesseract on the screenshot (no upscaling in current version)
- Filters: confidence >= 60, width > 1, height > 1
- Deduplicates by lowercase text (overly aggressive — "x" once means no more "x"s)
- Returns ~30 words maximum
- **No word merging** — adjacent words are not combined into phrases

### Spatial Zoning (`_group_by_zone`)
- 10% threshold zones: top row (< 10% height), bottom (> 90%), left (< 10% width), right (> 90%), center (everything else)
- Used for layout understanding — helps AI agents understand screen regions

### Multi-Monitor Handling
- `PRIMARY_MONITOR` is detected via `xrandr` (cached in `config.py`)
- Coordinates are adjusted to primary-relative (subtract primary monitor x, y)
- Screenshots are cropped to primary monitor only (`scrot -a`)
- Elements outside primary monitor bounds are filtered out

### JSON Output Suppression
- The `screenshot()` function prints "Screenshot saved to..." to stdout
- In `--json` mode, stdout is redirected to `/dev/null` during the screenshot call
- Clean JSON output is printed after restoring stdout

### CLI Integration (`modular/cli.py`)
```python
from .analyze import analyze as analyze_screen

elif cmd == "analyze":
    json_format = "--json" in args or "-j" in args
    analyze_screen(output_format="json" if json_format else "text")
```

---

## 4. CLI Usage

```bash
# Human-readable output (mixed format at end)
desktop-agent analyze

# Clean JSON for AI consumption
desktop-agent analyze --json

# Pipe JSON directly into an AI-friendly format
desktop-agent analyze --json | python3 -c "
import sys, json
data = json.load(sys.stdin)
print(json.dumps({
    'screen': data['screen'],
    'summary': data['summary'],
    'interactive': [e for e in data['atspi_elements'] if e['interactive']],
}, indent=2))
"
```

### Example Output Structure (JSON)
```json
{
  "screen": {
    "width": 3440,
    "height": 1440,
    "active_window": "Spotify Premium"
  },
  "atspi_elements": [
    {
      "role": "push button",
      "name": "Back",
      "desc": "Go to the previous visited location",
      "x": 1235, "y": 159, "w": 36, "h": 38,
      "depth": 8,
      "interactive": true
    }
  ],
  "ocr_texts": [
    {"text": "Aeternum", "x": 84, "y": 267, "w": 72, "h": 11, "confidence": 89}
  ],
  "zones": {
    "center": [...],
    "top": [...],
    "left": [...]
  },
  "summary": "3440×1440 screen | active: Spotify Premium | 23 UI elements | 16 buttons | 30 text regions",
  "elapsed_sec": 1.95
}
```

---

## 5. Demo Workflow: Spotify Playlist Extraction

This was a real end-to-end test that demonstrated the full see→act→verify loop:

### The Workflow
```
1. analyze                  → saw Spotify wasn't running
2. ensure-app "Spotify"     → launched Spotify via gnome-shell
3. screenshot + OCR         → found "Aeternum" playlist at (84, 267) in sidebar
4. click 84 267             → opened the Aeternum playlist
5. screenshot + OCR × 3    → multiple OCR passes to read track listing
6. write to ~/Desktop/      → saved first 5 songs to file
```

### What Worked Well
- **AT-SPI** correctly detected Spotify as the active window after launch
- **OCR** found "Aeternum" in the left sidebar at exact pixel coords (84, 267)
- **The feedback loop**: analyze → click → re-analyze is powerful
- **Multi-pass OCR**: Cross-referencing 3 passes gave better results than any single pass

### What Was Difficult
- **Spotify uses custom fonts** that Tesseract struggles with (inconsistent reads)
- **OCR word fragmentation**: "Clair Obscur: Expedition 33" read as separate tokens
- **Background window noise**: Terminals behind Spotify polluted the AT-SPI output
- **The analyze JSON had a stdout pollution bug** — "Screenshot saved" mixed into JSON output (FIXED)

### Result File: `/home/mal/Desktop/aeternum-playlist-first5.txt`
```
1. Easy Way Out — Low Roar (4:48)
2. Once in a Long, Long While... — Low Roar (2:03)
3. Don't Be So Serious — Low Roar (6:13)
4. Clair Obscur: Expedition 33 (OST) — Lorien Testard, Alice Duport-Percier (3:42)
5. October (Calendar Project) — Feverkin (4:08)
```

---

## 6. Known Issues & Pain Points

### Critical
- **No active-window filtering**: AT-SPI returns elements from ALL apps, not just the active one. Makes output noisy when windows overlap.
- **OCR dedup too aggressive**: Single-char texts ("x", "-", "|") are silently dropped after first occurrence. Also prevents seeing multiple "x" buttons.
- **OCR word fragmentation**: "Platfor" + "lls" should be "Platforms". No adjacent-word merging.

### Moderate
- **No OCR upscaling**: Tesseract accuracy improves 3-5x with 2-3x image upscaling (not implemented).
- **AT-SPI window overlap**: When one window is on top of another, both are still reported.
- **Spotify/custom fonts**: Apps with non-standard fonts produce unreliable OCR.
- **`_print_human` runs on every call**: Even `--json` processes human-readable path unnecessarily.
- **Variable `interactive` and `labels` are unused** in `_make_summary` and `_print_human` (minor lint).

### Minor
- **No detail levels**: Only one mode (medium detail). No `--quick` (summary only) or `--deep` (all raw data).
- **No region targeting**: Can't say "analyze just the top-left 300px".
- **No clickable refs**: Output has raw coordinates, not parsed element references.
- **`_token_estimate` is heuristic**: Uses 4 chars/token which is rough for JSON.
- **OCR config not optimized**: Using default Tesseract config instead of tuned settings.
- **Screenshot saved twice**: OCR takes its own screenshot via `find_text_on_screen` when used separately.

---

## 7. Priority Improvements

### P0: Active Window Focus
**Why:** Biggest quality jump. The Spotify demo had 23 AT-SPI elements but most were from background terminals.

**How:**
```python
def get_active_app_name():
    """Find the AT-SPI application matching the active window."""
    active = get_active_window()
    # Get PID of active window, match to AT-SPI application
    # Filter _walk_atspi() to only that app's tree
```

Alternatively, use `xdotool getactivewindow` to get the window PID, then find the corresponding AT-SPI app by matching PIDs.

### P0: OCR Word Merging
**Why:** "Clair Obscur: Expedition 33" is useless split into 5 words. Merged it's meaningful.

**How:** Group words by y-coordinate (same line), sort by x, merge adjacent words with small x-gaps:
```python
def _merge_words(data, line_threshold=15, gap_threshold=20):
    """Merge adjacent words on the same line into phrases."""
    words_by_line = {}
    for ...:
        line = word_y // line_threshold
        words_by_line.setdefault(line, []).append((word_x, word))
    # Sort each line by x, merge with gap detection
```

### P1: OCR Upscaling
**Why:** 3x upscaling improved Spotify OCR dramatically in testing but isn't in the code.

**How:** Before OCR, resize the screenshot region 2-3x with LANCZOS. Scale coordinates back.

### P1: Ensemble OCR
**Why:** Single OCR passes hallucinate words. Running 2-3 passes and voting for consistent words gives much better results.

**How:** Run OCR 2-3 times with different configs (--oem 1, --oem 3, different PSM values), keep words that appear in 2+ passes with average confidence.

### P2: Clickable Element Refs
**Why:** AI agents shouldn't do coordinate math. Each element should have a stable ref.

**How:**
```json
{"ref": "#e1", "role": "push button", "name": "Back", "pos": [1235, 159]}
```

### P2: Layout Deduplication (Z-Order)
**Why:** Elements from windows behind the active window shouldn't be reported.

**How:** Use window stacking information (xdotool or AT-SPI) to determine which window is topmost, filter elements from obscured windows.

### P2: Detail Levels
```bash
desktop-agent analyze --quick     # ~80 tokens: summary + active window only
desktop-agent analyze             # ~250 tokens: current
desktop-agent analyze --deep      # ~500 tokens: all raw data, no capping
```

---

## 8. Long-Term Roadmap

### Phase 1: Robustness (Current — ~80% done)
- [x] Basic analyze command working
- [x] AT-SPI tree walking + filtering
- [x] OCR text extraction
- [x] Spatial zone grouping
- [x] JSON output mode
- [x] Multi-monitor support
- [ ] Active window filtering
- [ ] OCR word merging
- [ ] OCR upscaling

### Phase 2: Intelligence
- [ ] Ensemble OCR (multi-pass voting)
- [ ] Window overlap detection (z-order)
- [ ] Clickable element refs (#e1, #e2, etc.)
- [ ] Detail levels (--quick, --deep)
- [ ] Region-specific analysis (--region sidebar)

### Phase 3: Advanced
- [ ] AST-based layout understanding (group elements into "toolbar", "content", "status bar")
- [ ] Icon detection (distinguish play buttons from close buttons)
- [ ] Change detection (diff two analyze outputs → "what changed?")
- [ ] Multi-modal fallback (if a vision model IS available, use it for ambiguous cases)
- [ ] Task-specific analysis (--task "find playlist" → optimize for that goal)

### Phase 4: Integration
- [ ] QuetzaCodetl native tool integration (LSP-style, not CLI)
- [ ] Auto-analyze before every action (like a robot's visual cortex)
- [ ] Persistent element tracking (element refs survive window moves/resizes)
- [ ] Learn from corrections ("that was a button, not a label")

---

## 9. Testing & Validation Patterns

### Quick Smoke Test
```bash
desktop-agent analyze --json | python3 -c "
import sys, json
d = json.load(sys.stdin)
assert 'screen' in d
assert 'atspi_elements' in d
assert 'ocr_texts' in d
print(f'OK: {d[\"screen\"][\"active_window\"]} — {len(d[\"atspi_elements\"])} elements, {len(d[\"ocr_texts\"])} texts')
"
```

### Test the See→Act→Verify Loop
```bash
# Step 1: See
desktop-agent analyze --json > /tmp/state1.json

# Step 2: Act
desktop-agent click 100 100

# Step 3: Verify
desktop-agent analyze --json > /tmp/state2.json
python3 -c "
import json
s1 = json.load(open('/tmp/state1.json'))
s2 = json.load(open('/tmp/state2.json'))
# Check if active window changed
if s1['screen']['active_window'] != s2['screen']['active_window']:
    print(f'Window changed: {s1[\"screen\"][\"active_window\"]} → {s2[\"screen\"][\"active_window\"]}')
else:
    print('Same window — check element position changes')
"
```

### Known Working Configurations
- **Cinnamon desktop** (Mint 22 / Ubuntu-like)
- **Single primary monitor** at x=1920, y=322 (multi-monitor with secondary left)
- **GNOME Terminal** — AT-SPI exposes frames, filler, menus
- **Nemo file manager** — AT-SPI exposes buttons, toggles, status bars
- **Spotify** — AT-SPI finds the window frame, but internal elements are custom-rendered (OCR needed)
- **Firefox** — Tab text readable via OCR, AT-SPI limited

---

## 10. Architecture Diagrams

### Data Flow
```
┌─────────────┐     ┌──────────────────┐     ┌──────────────┐
│  Screenshot │────▶│  Tesseract OCR   │────▶│  Text Regions│
│  (scrot)    │     │  (pytesseract)   │     │  + conf      │
└─────────────┘     └──────────────────┘     └──────┬───────┘
                                                    │
┌─────────────┐     ┌──────────────────┐            │
│  AT-SPI Bus │────▶│  Tree Walker     │────────────┤
│  (pyatspi)  │     │  (_collect_elem) │            │
└─────────────┘     └──────┬───────────┘            │
                           │                        │
                           ▼                        ▼
                    ┌──────────────────────────────────┐
                    │     analyze() — merge + cap      │
                    │     - dedup elements              │
                    │     - cap at 40 / 30              │
                    │     - spatial zoning              │
                    └──────────────┬───────────────────┘
                                   │
                                   ▼
                    ┌──────────────────────────────────┐
                    │     Output: JSON or Human        │
                    │     ~250 tokens for AI agents    │
                    └──────────────────────────────────┘
```

### Module Dependencies
```
analyze.py
  ├── .config: ATSPI_AVAILABLE, OCR_AVAILABLE, PIL_AVAILABLE, PRIMARY_MONITOR
  ├── .window: get_active_window()
  └── .input: screenshot()
```

### File Structure
```
/home/mal/AI/desktop-agent/
├── desktop-agent.py              # Entry point (from modular.cli import main)
├── modular/
│   ├── __init__.py               # Empty
│   ├── cli.py                    # CLI dispatcher (analyze command handler)
│   ├── config.py                 # Shared config: ATSPI_AVAILABLE, PRIMARY_MONITOR, etc.
│   ├── input.py                  # Screenshot, click, type, key, mouse
│   ├── window.py                 # List/focus windows, get active window
│   ├── atspi.py                  # AT-SPI element walking, pinning, matching
│   ├── ocr.py                    # OCR text finding (find_text_on_screen)
│   ├── snapshot.py               # UI snapshot (interactive element overlay)
│   ├── analyze.py                # ★ NEW: Unified screen analysis
│   ├── media.py                  # D-Bus MPRIS media control
│   ├── shortcuts.py              # App-specific keyboard shortcuts
│   ├── task_system.py            # Task recording, embedding search
│   └── media.py                  # Media player commands
└── HANDOFF_ANALYZE.md            # This file
```

---

## 11. Appendix: Key Code

### The Core Loop (analyze.py:228-324)
```python
def analyze(output_format="text"):
    start = time.time()
    mon = PRIMARY_MONITOR
    ss_path = Path("/tmp/desktop-agent") / "analyze.png"

    # Suppress "Screenshot saved" in JSON mode
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

    # AT-SPI walk → dedupe → sort → cap at 40
    elements = _walk_atspi()
    deduped = sorted(set(...), key=lambda e: (e["y"], e["x"]))
    if len(deduped) > 40:
        interactive = [e for e in deduped if e["interactive"]]
        others = [e for e in deduped if not e["interactive"]]
        deduped = (interactive + others)[:40]

    # OCR → sort → cap at 30
    text_regions = _ocr_screen(ss_path)
    if len(text_regions) > 30:
        text_regions = text_regions[:30]

    # Zones + summary + elapsed
    zones = _group_by_zone(deduped, mon["width"], mon["height"])
    result = { "screen": ..., "atspi_elements": ..., "ocr_texts": ..., "zones": ..., "summary": ... }

    if output_format == "json":
        print(json.dumps(result, indent=2))
    else:
        _print_human(result)
    return result
```

### AT-SPI Yield Condition (analyze.py:93-98)
```python
should_yield = (
    not is_container        # Skip panels, fillers, scroll panes
    and not is_app          # Skip application-level nodes
    and (is_interactive     # Buttons, links, entries, menus
         or has_content     # Has name or description
         or structural_parent)  # Frame, window, dialog
)
```

### OCR Extraction (analyze.py:178-221)
```python
def _ocr_screen(ss_path):
    img = Image.open(ss_path)
    data = pytesseract.image_to_data(img, output_type=pytesseract.Output.DICT)
    regions = []
    seen_texts = set()
    for i, word in enumerate(data["text"]):
        word = word.strip()
        if not word: continue
        if int(data["conf"][i]) < 60: continue
        if word.lower() in seen_texts: continue  # ← over-aggressive dedup
        seen_texts.add(word.lower())
        regions.append({
            "text": word, "x": data["left"][i], "y": data["top"][i],
            "w": data["width"][i], "h": data["height"][i],
            "confidence": int(data["conf"][i]),
        })
    return regions
```

### CLI Handler (cli.py)
```python
from .analyze import analyze as analyze_screen

elif cmd == "analyze":
    json_format = "--json" in args or "-j" in args
    analyze_screen(output_format="json" if json_format else "text")
```

---

## Git State (as of handoff)

**Branch:** `experimental-analyze`  
**Based on:** `main` (merged: smart-primitives branch)  
**Changes since main:**
- `modular/analyze.py` — NEW (429 lines)
- `modular/cli.py` — MODIFIED (added import + command handler + help text)

```bash
git log --oneline experimental-analyze
# ... (merge commit + smart-primitives history)
```

**Remote:** Pushed to origin/experimental-analyze

---

## Prompt to Resume Work

> You're working on `desktop-agent analyze` — a unified screen understanding command for AI agents. It combines AT-SPI accessibility tree + OCR + spatial layout into ~250 tokens.
>
> The code is at `/home/mal/AI/desktop-agent/modular/analyze.py` on the `experimental-analyze` branch.
>
> **Current state:**
> - Basic analyze works: AT-SPI tree walk, OCR text extraction, spatial zones
> - JSON output mode is clean (stdout pollution was fixed)
> - Multi-monitor support works (primary monitor only)
> - AT-SPI visibility bug was fixed (applications are always invisible)
>
> **Priority improvements needed:**
> 1. **Active window filtering** — Only show elements from the focused app (background windows are noise)
> 2. **OCR word merging** — Group adjacent words into phrases ("Clair Obscur: Expedition 33" not 5 separate words)
> 3. **OCR upscaling** — 2-3x upscale before OCR for 3-5x better accuracy
> 4. **Ensemble OCR** — Run 2-3 passes, vote for consistent words
> 5. **Clickable refs** — Assign @eN names to elements for direct clicking
>
> **Demo to try after fixes:**
> 1. `desktop-agent ensure-app "Spotify"`
> 2. `desktop-agent analyze --json` → find "Aeternum" playlist
> 3. Click at found coordinates
> 4. Re-analyze → read track listing via OCR
> 5. Write results to ~/Desktop/
>
> **Known bugs:**
> - OCR dedup is too aggressive (single chars block all future matches)
> - AT-SPI reports elements from all windows, not just the active one
> - No upscaling → poor accuracy on custom fonts (Spotify)
>
> Read the full HANDOFF at `HANDOFF_ANALYZE.md` for complete details.

---

**Last Updated:** 2026-04-26  
**Version:** 0.1 (Experimental)  
**Next Session Goal:** Active window filtering + OCR word merging
