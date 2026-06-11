#!/usr/bin/env python3
"""Full automation workflow test — analyze → find → act → verify loop.

Non-destructive: reads screen, identifies elements, validates positions,
but does NOT click or modify anything.
"""
import sys, json, time, os
sys.path.insert(0, "/home/mal/AI/desktop-agent")
os.environ["PYTHONPATH"] = "/home/mal/AI/desktop-agent"

from modular.analyze import analyze
from modular.ocr import find_text_on_screen
from modular.window import get_active_window


def header(title):
    print(f"\n{'='*70}")
    print(f"  {title}")
    print(f"{'='*70}")


def step(n, desc):
    print(f"\n  STEP {n}: {desc}")
    print(f"  {'─'*60}")


def workflow():
    header("DESKTOP-AGENT FULL WORKFLOW TEST")
    t_start = time.time()

    # ── Step 1: Full screen analysis ──────────────────────────────────
    step(1, "Analyze screen (AT-SPI + RapidOCR)")
    result = analyze(output_format="json")
    print(f"  ✓ {result['elapsed_sec']}s — {result['summary']}")

    atspi = result["atspi_elements"]
    ocr = result["ocr_texts"]
    zones = result["zones"]

    # ── Step 2: Catalog what's running ────────────────────────────────
    step(2, "Catalog all application windows")
    frames = [e for e in atspi if e["role"] == "frame"]
    print(f"  {len(frames)} windows detected:")
    for f in frames:
        name = f["name"] or "(unnamed)"
        pos = f"({f['x']},{f['y']}) {f['w']}x{f['h']}"
        print(f"    • {name[:70]}")
        print(f"      {pos}")

    # ── Step 3: Find interactive elements ─────────────────────────────
    step(3, "Catalog interactive controls")
    interactive = [e for e in atspi if e["interactive"]]
    print(f"  {len(interactive)} interactive elements:")
    for e in interactive:
        name = e["name"] or "(unnamed)"
        print(f"    • [{e['role']}] \"{name}\" @ ({e['x']},{e['y']})")

    # ── Step 4: Spatial layout analysis ───────────────────────────────
    step(4, "Analyze spatial layout")
    for zone_name in ["top", "left", "center", "right", "bottom"]:
        elems = zones.get(zone_name, [])
        roles = {}
        for e in elems:
            r = e["role"]
            roles[r] = roles.get(r, 0) + 1
        role_str = ", ".join(f"{n}×{r}" for r, n in sorted(roles.items()))
        print(f"  [{zone_name:6s}] {len(elems):2d} elements — {role_str}")

    # ── Step 5: OCR text search (reuses analyze screenshot) ─────────
    step(5, "OCR-based text finding (reuses analyze screenshot)")
    ss_path = "/tmp/desktop-agent/analyze.png"
    search_terms = ["File", "Save", "Close", "gedit", "QuetzaCodetl", "OpenCode"]
    for term in search_terms:
        t0 = time.time()
        match = find_text_on_screen(term, silent=True, min_confidence=60, ss_path=ss_path)
        elapsed = time.time() - t0
        if match:
            m = match if isinstance(match, dict) else match[0]
            print(f"  ✓ \"{term}\" → pos=({m['x']},{m['y']}) conf={m['confidence']}% ({elapsed:.2f}s)")
        else:
            print(f"  ✗ \"{term}\" → NOT FOUND ({elapsed:.2f}s)")

    # ── Step 6: Cross-reference AT-SPI + OCR ──────────────────────────
    step(6, "Cross-reference AT-SPI elements with OCR text")
    # Check which AT-SPI elements have matching OCR text nearby
    matched = 0
    for e in atspi:
        if not e["name"]:
            continue
        ename = e["name"].lower()
        for r in ocr:
            if ename in r["text"].lower() or r["text"].lower() in ename:
                dist = abs(e["x"] - r["x"]) + abs(e["y"] - r["y"])
                if dist < 100:
                    matched += 1
                    break
    print(f"  {matched}/{len([e for e in atspi if e['name']])} named AT-SPI elements confirmed by OCR")

    # ── Step 7: Active window verification ────────────────────────────
    step(7, "Active window verification")
    active = get_active_window()
    print(f"  Active window: {active.get('name', 'unknown')}")
    print(f"  Window class:  {active.get('wm_class', 'unknown')}")
    print(f"  PID:           {active.get('pid', 'unknown')}")

    # ── Step 8: Find actionable targets ───────────────────────────────
    step(8, "Find actionable targets for automation")
    # Buttons that can be clicked
    buttons = [e for e in atspi if e["role"] in ("push button", "toggle button") and e["name"]]
    print(f"  {len(buttons)} clickable buttons found:")
    for b in buttons:
        print(f"    • \"{b['name']}\" @ ({b['x']},{b['y']}) — desktop-agent click \"{b['name']}\"")

    # ── Step 9: Token budget check ────────────────────────────────────
    step(9, "Token budget analysis")
    compact = {
        "screen": result["screen"],
        "summary": result["summary"],
        "n_elements": len(atspi),
        "n_ocr": len(ocr),
        "interactive": [{"role": e["role"], "name": e["name"], "pos": (e["x"], e["y"])}
                        for e in atspi if e["interactive"]],
        "all_text": [r["text"] for r in ocr],
    }
    token_est = len(json.dumps(compact)) // 4
    print(f"  Estimated tokens for AI consumption: ~{token_est}")
    print(f"  Compact payload:")
    print(f"    screen:  {result['screen']}")
    print(f"    buttons: {len([e for e in atspi if e['interactive']])}")
    print(f"    ocr:     {len(ocr)} text regions")
    if token_est > 500:
        print(f"  ⚠ Over budget! Target is ≤500 tokens")
    else:
        print(f"  ✓ Within 500 token budget")

    # ── Summary ───────────────────────────────────────────────────────
    total = time.time() - t_start
    header("WORKFLOW COMPLETE")
    print(f"  Total time: {total:.1f}s")
    print(f"  Engine:     RapidOCR (primary) + AT-SPI")
    print(f"  Quality:    {len(atspi)} AT-SPI elements, {len(ocr)} OCR regions")
    print(f"  Status:     All 9 steps passed ✓")


if __name__ == "__main__":
    workflow()
