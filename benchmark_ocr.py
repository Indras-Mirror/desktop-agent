#!/usr/bin/python3
"""Benchmark all OCR engines against the current screen.

Tests 4 engines: tesseract, rapidocr, ensemble, hybrid
Reports: speed, coverage, confidence, unique contributions
"""
import time, json, sys, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from modular.input import screenshot as take_screenshot
from modular.ocr import (
    ocr_screen,
    _ocr_tesseract,
    _ocr_rapidocr,
    _ensemble_tesseract,
    _ocr_hybrid,
)
from PIL import Image

SS_PATH = "/tmp/desktop-agent/benchmark_screen.png"

def benchmark():
    print("=" * 70)
    print("  OCR ENGINE BENCHMARK — Current Screen")
    print("=" * 70)

    # Take screenshot
    take_screenshot(SS_PATH, primary_only=True)
    img = Image.open(SS_PATH)
    w, h = img.size
    print(f"\n  Screenshot: {w}×{h}  |  Size: {os.path.getsize(SS_PATH)//1024} KB\n")

    engines = {
        "tesseract":  lambda: _ocr_tesseract(img),
        "rapidocr":    lambda: _ocr_rapidocr(img),
        "ensemble":    lambda: _ensemble_tesseract(img),
        "hybrid":      lambda: ocr_screen(SS_PATH, engine="hybrid"),
    }

    results = {}
    all_texts = {}  # engine -> set of lowercase texts

    for name, fn in engines.items():
        t0 = time.time()
        try:
            regions = fn()
            elapsed = time.time() - t0
        except Exception as e:
            print(f"  {name:12s}  ERROR: {e}")
            results[name] = {"error": str(e), "elapsed": 0}
            continue

        results[name] = {
            "regions": regions,
            "elapsed": elapsed,
            "count": len(regions),
        }
        all_texts[name] = {r["text"].lower().strip() for r in regions}
        confs = [r["confidence"] for r in regions]
        avg_conf = sum(confs) / len(confs) if confs else 0

        print(f"  {name:12s}  {len(regions):3d} regions  "
              f"avg_conf={avg_conf:5.1f}%  {elapsed:5.2f}s")

    # --- Cross-engine analysis ---
    print(f"\n{'─' * 70}")
    print("  CROSS-ENGINE ANALYSIS")
    print(f"{'─' * 70}")

    # Unique contributions (text only found by one engine)
    for name, texts in all_texts.items():
        others_texts = set()
        for other_name, other_texts in all_texts.items():
            if other_name != name:
                others_texts |= other_texts
        unique = texts - others_texts
        if unique:
            sample = sorted(unique)[:8]
            print(f"\n  Only {name} found ({len(unique)} unique):")
            for t in sample:
                print(f"    • \"{t}\"")

    # Overlap matrix
    print(f"\n{'─' * 70}")
    print("  OVERLAP MATRIX (% of engine A's texts also found by engine B)")
    print(f"{'─' * 70}")
    names = sorted(all_texts.keys())
    header = "        " + "".join(f"{n:>12s}" for n in names)
    print(header)
    for a in names:
        row = f"  {a:6s}"
        for b in names:
            if a == b:
                row += f"     {'100%':>7s}"
            else:
                overlap = all_texts[a] & all_texts[b]
                pct = len(overlap) / len(all_texts[a]) * 100 if all_texts[a] else 0
                row += f"     {pct:>5.1f}%"
        print(row)

    # --- Source breakdown for hybrid ---
    print(f"\n{'─' * 70}")
    print("  HYBRID SOURCE BREAKDOWN")
    print(f"{'─' * 70}")
    if "hybrid" in results and results["hybrid"]["regions"]:
        sources = {}
        for r in results["hybrid"]["regions"]:
            src = r.get("source", "unknown")
            sources[src] = sources.get(src, 0) + 1
        for src, count in sorted(sources.items()):
            pct = count / len(results["hybrid"]["regions"]) * 100
            print(f"  {src:20s}  {count:3d} regions ({pct:.0f}%)")

    # --- Recommendations ---
    print(f"\n{'─' * 70}")
    print("  RECOMMENDATIONS")
    print(f"{'─' * 70}")

    tess_count = results.get("tesseract", {}).get("count", 0)
    rapid_count = results.get("rapidocr", {}).get("count", 0)
    tess_time = results.get("tesseract", {}).get("elapsed", 999)
    rapid_time = results.get("rapidocr", {}).get("elapsed", 999)

    if rapid_count > tess_count and rapid_time < tess_time:
        print("\n  → RapidOCR wins on both speed AND coverage — use as primary")
    elif rapid_count > tess_count:
        print("\n  → RapidOCR has better coverage but Tesseract is faster")
        print("    Consider RapidOCR primary with Tesseract ensemble as supplement")
    elif rapid_time < tess_time:
        print("\n  → RapidOCR is faster but Tesseract has better coverage")
        print("    Consider Tesseract primary with RapidOCR filling gaps")
    else:
        print("\n  → Engines are complementary — hybrid gives best coverage")

    unique_rapid = len(all_texts.get("rapidocr", set()) - all_texts.get("tesseract", set()))
    unique_tess = len(all_texts.get("tesseract", set()) - all_texts.get("rapidocr", set()))
    print(f"  RapidOCR unique texts: {unique_rapid}")
    print(f"  Tesseract unique texts: {unique_tess}")

    # Save results
    out_path = "/tmp/desktop-agent/benchmark_results.json"
    with open(out_path, "w") as f:
        json.dump({
            "screen": f"{w}x{h}",
            "engines": {
                name: {
                    "count": r["count"],
                    "elapsed": round(r.get("elapsed", 0), 3),
                }
                for name, r in results.items()
            },
            "hybrid_sources": {
                r.get("source", "?"): 0
                for r in results.get("hybrid", {}).get("regions", [])
            },
        }, f, indent=2)

    print(f"\n  Full results saved to {out_path}")
    print("=" * 70)


if __name__ == "__main__":
    benchmark()
