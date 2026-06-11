# ocr.py — hybrid OCR with Tesseract optimizations + RapidOCR supplement
#
# Engines: tesseract, rapidocr, hybrid (both, union), ensemble (multi-pass tesseract)
# Optimizations: 3x LANCZOS upscaling, word merging, PSM config tuning, ensemble voting

from .config import (
    OCR_AVAILABLE, PIL_AVAILABLE, RAPIDOCR_AVAILABLE,
    SCREENSHOT_DIR,
)
from PIL import Image
import json
import math
from collections import defaultdict


# ---------------------------------------------------------------------------
# Upscaling — single biggest Tesseract accuracy improvement
# ---------------------------------------------------------------------------

def _upscale_image(img, scale=3, max_px=4000):
    """Upscale image with LANCZOS for better OCR accuracy. Coordinates scaled back.

    Caps the longest side at max_px to avoid massive images on hi-res screens.
    """
    w, h = img.size
    target_w, target_h = w * scale, h * scale
    longest = max(target_w, target_h)
    if longest > max_px:
        ratio = max_px / longest
        target_w = int(target_w * ratio)
        target_h = int(target_h * ratio)
        scale = target_w / w  # actual scale factor used
    return img.resize((target_w, target_h), Image.LANCZOS), scale


def _scale_coords(regions, scale):
    """Scale coordinates back after upscaling."""
    for r in regions:
        r["x"] = int(r["x"] / scale)
        r["y"] = int(r["y"] / scale)
        r["w"] = int(r["w"] / scale)
        r["h"] = int(r["h"] / scale)


# ---------------------------------------------------------------------------
# Word merging — group adjacent words on same line into phrases
# ---------------------------------------------------------------------------

def _merge_adjacent_words(regions, line_threshold=None, gap_threshold=None):
    """Merge adjacent words on the same line into phrases.

    Groups by y-coordinate, sorts by x, merges words with small x-gaps.
    Handles multi-font-size lines by using per-word height for line grouping.
    """
    if not regions:
        return []

    # Build line groups using per-word height to handle mixed font sizes
    # Sort by y first
    sorted_regions = sorted(regions, key=lambda r: (r["y"], r["x"]))

    # Use average height for thresholds if not specified
    if line_threshold is None:
        heights = [r["h"] for r in sorted_regions]
        line_threshold = sum(heights) // len(heights) if heights else 15
    if gap_threshold is None:
        gap_threshold = max(10, line_threshold)

    # Group into lines: a word belongs to the same line if their vertical
    # midpoints are within line_threshold of each other
    lines = []
    for r in sorted_regions:
        r_mid_y = r["y"] + r["h"] // 2
        placed = False
        for line in lines:
            line_avg_y = sum(w["y"] + w["h"] // 2 for w in line) // len(line)
            if abs(r_mid_y - line_avg_y) < line_threshold:
                line.append(r)
                placed = True
                break
        if not placed:
            lines.append([r])

    # Merge adjacent words within each line
    merged = []
    for line in lines:
        line.sort(key=lambda r: r["x"])
        current = None
        for r in line:
            if current is None:
                current = dict(r)
                continue
            # Gap between end of current word and start of next word
            gap = r["x"] - (current["x"] + current["w"])
            if gap <= gap_threshold:
                # Merge: extend bounding box, join text
                x2_new = max(r["x"] + r["w"], current["x"] + current["w"])
                y2_new = max(r["y"] + r["h"], current["y"] + current["h"])
                current["w"] = x2_new - current["x"]
                current["h"] = y2_new - current["y"]
                current["text"] = current["text"] + " " + r["text"]
                current["confidence"] = (current["confidence"] + r["confidence"]) // 2
                current["merged"] = True
            else:
                merged.append(current)
                current = dict(r)
        if current is not None:
            merged.append(current)

    return merged


# ---------------------------------------------------------------------------
# Tesseract with config tuning
# ---------------------------------------------------------------------------

_TESSERACT_PSM_MODES = {
    # psm: description
    3: "Fully automatic page segmentation (default)",
    6: "Assume uniform block of text",
    11: "Sparse text (good for UI elements scattered on screen)",
    12: "Sparse text with OSD",
}


def _ocr_tesseract_raw(img, psm=6, oem=3):
    """Run Tesseract on PIL image, return raw word-level regions."""
    import pytesseract

    config = f"--psm {psm} --oem {oem}"
    data = pytesseract.image_to_data(img, output_type=pytesseract.Output.DICT, config=config)

    regions = []
    for i, word in enumerate(data["text"]):
        word = word.strip()
        if not word:
            continue
        conf = int(data["conf"][i])
        if conf < 40:  # slightly relaxed from 60 to catch more in ensemble
            continue
        x, y, w, h = data["left"][i], data["top"][i], data["width"][i], data["height"][i]
        if w <= 1 or h <= 1:
            continue
        regions.append({
            "text": word,
            "x": x, "y": y, "w": w, "h": h,
            "confidence": conf,
            "source": f"tesseract-psm{psm}",
        })
    return regions


def _ocr_tesseract(img, psm=6):
    """Run Tesseract with upscaling, merge words, return clean regions."""
    upscaled, scale = _upscale_image(img, scale=3)
    regions = _ocr_tesseract_raw(upscaled, psm=psm)
    _scale_coords(regions, scale)
    regions = _merge_adjacent_words(regions)
    return regions


# ---------------------------------------------------------------------------
# Ensemble Tesseract — multi-pass voting
# ---------------------------------------------------------------------------

def _ensemble_tesseract(img, passes=None):
    """Run Tesseract with multiple PSM modes, vote on consistent words.

    A word is "confirmed" if found in >= 2 passes with similar position.
    Returns merged, deduplicated regions with averaged confidence.
    """
    if passes is None:
        passes = [3, 6, 11]

    upscaled, scale = _upscale_image(img, scale=3)

    # Collect all word detections across passes
    # Keyed by normalized position (snapped to grid) for cross-pass matching
    all_detections = defaultdict(list)
    for psm in passes:
        regions = _ocr_tesseract_raw(upscaled, psm=psm)
        for r in regions:
            # Snap to ~20px grid for cross-pass positional matching
            grid_key = (r["x"] // 20, r["y"] // 20)
            all_detections[grid_key].append(r)

    # Vote: keep words that appear in >= 2 passes
    voted = []
    for grid_key, detections in all_detections.items():
        if len(detections) < 2:
            continue
        # Average position and confidence
        texts = [d["text"] for d in detections]
        # Use the most common text variant
        text = max(set(texts), key=texts.count)
        avg_x = sum(d["x"] for d in detections) // len(detections)
        avg_y = sum(d["y"] for d in detections) // len(detections)
        avg_w = sum(d["w"] for d in detections) // len(detections)
        avg_h = sum(d["h"] for d in detections) // len(detections)
        avg_conf = sum(d["confidence"] for d in detections) // len(detections)
        # Boost confidence for multi-pass agreement
        boost = min(15, (len(detections) - 2) * 5)
        voted.append({
            "text": text,
            "x": avg_x, "y": avg_y, "w": avg_w, "h": avg_h,
            "confidence": min(100, avg_conf + boost),
            "passes": len(detections),
            "source": "ensemble",
        })

    _scale_coords(voted, scale)
    voted = _merge_adjacent_words(voted)
    return voted


# ---------------------------------------------------------------------------
# RapidOCR — lightweight ONNX-based PaddleOCR models
# ---------------------------------------------------------------------------

# Singleton to avoid reloading model on every call
_rapidocr_engine = None


def _get_rapidocr():
    global _rapidocr_engine
    if _rapidocr_engine is None and RAPIDOCR_AVAILABLE:
        from rapidocr_onnxruntime import RapidOCR
        _rapidocr_engine = RapidOCR()
    return _rapidocr_engine


def _ocr_rapidocr(img, upscale=True):
    """Run RapidOCR (PaddleOCR models via ONNX) on a PIL image.

    Upscaling helps RapidOCR with small text though the benefit is less
    dramatic than with Tesseract since PaddleOCR models handle varied scales.
    """
    engine = _get_rapidocr()
    if engine is None:
        return []

    if upscale:
        img, scale = _upscale_image(img, scale=2)

    # RapidOCR prefers numpy array; save to temp path for best compat
    import tempfile
    import os

    with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as f:
        tmp_path = f.name
        img.save(tmp_path)

    try:
        result, elapse = engine(tmp_path)
    finally:
        os.unlink(tmp_path)

    if result is None:
        return []

    regions = []
    for item in result:
        # item: [box_points, text, confidence]
        box, text, conf = item
        if not text or not text.strip():
            continue
        # box is [[x1,y1], [x2,y2], [x3,y3], [x4,y4]] (4 corners)
        xs = [p[0] for p in box]
        ys = [p[1] for p in box]
        x, w = min(xs), max(xs) - min(xs)
        y, h = min(ys), max(ys) - min(ys)
        regions.append({
            "text": text.strip(),
            "x": int(x), "y": int(y), "w": int(w), "h": int(h),
            "confidence": int(float(conf) * 100) if conf else 80,
            "source": "rapidocr",
        })

    regions = _merge_adjacent_words(regions)
    return regions


# ---------------------------------------------------------------------------
# Hybrid engine — Tesseract ensemble + RapidOCR union
# ---------------------------------------------------------------------------

def _deduplicate_overlapping(regions, iou_threshold=0.5):
    """Remove overlapping regions, keeping the one with higher confidence."""
    if not regions:
        return []

    regions = sorted(regions, key=lambda r: r["confidence"], reverse=True)
    kept = []

    for r in regions:
        overlaps = False
        for k in kept:
            # Compute intersection-over-union
            x1 = max(r["x"], k["x"])
            y1 = max(r["y"], k["y"])
            x2 = min(r["x"] + r["w"], k["x"] + k["w"])
            y2 = min(r["y"] + r["h"], k["y"] + k["h"])
            if x2 <= x1 or y2 <= y1:
                continue
            inter = (x2 - x1) * (y2 - y1)
            area_r = r["w"] * r["h"]
            area_k = k["w"] * k["h"]
            iou = inter / min(area_r, area_k)  # min is stricter than union
            if iou > iou_threshold:
                overlaps = True
                break
        if not overlaps:
            kept.append(r)

    return kept


def _ocr_hybrid(img):
    """RapidOCR primary. Tesseract only as emergency fallback.

    Tesseract is not run unless RapidOCR fails entirely.
    """
    if not RAPIDOCR_AVAILABLE and not OCR_AVAILABLE:
        return []

    all_regions = []

    if RAPIDOCR_AVAILABLE:
        try:
            all_regions.extend(_ocr_rapidocr(img))
        except Exception:
            pass

    # Tesseract fallback — only if RapidOCR gave nothing
    if not all_regions and OCR_AVAILABLE:
        try:
            all_regions.extend(_ocr_tesseract(img, psm=6))
        except Exception:
            pass

    if not all_regions:
        return []

    all_regions = _deduplicate_overlapping(all_regions)
    all_regions = _merge_adjacent_words(all_regions)
    all_regions.sort(key=lambda r: (r["y"], r["x"]))

    return all_regions


# ---------------------------------------------------------------------------
# Public API — ocr_screen
# ---------------------------------------------------------------------------

def ocr_screen(ss_path=None, engine="rapidocr", min_confidence=40, max_regions=60):
    """Run OCR on a screenshot and return text regions.

    Args:
        ss_path: Path to screenshot PNG. If None, takes a fresh screenshot.
        engine: "tesseract", "rapidocr", "hybrid", or "ensemble"
        min_confidence: Minimum confidence threshold
        max_regions: Cap on number of regions returned

    Returns:
        List of dicts: [{text, x, y, w, h, confidence, source?}, ...]
    """
    if not PIL_AVAILABLE:
        return []

    if ss_path is None:
        from .input import screenshot as take_screenshot
        ss_path = SCREENSHOT_DIR / "ocr_screen.png"
        take_screenshot(ss_path, primary_only=True)

    img = Image.open(ss_path)

    # Select engine
    if engine == "hybrid":
        regions = _ocr_hybrid(img)
    elif engine == "rapidocr":
        regions = _ocr_rapidocr(img)
    elif engine == "ensemble":
        regions = _ensemble_tesseract(img)
    elif engine == "tesseract":
        regions = _ocr_tesseract(img, psm=6)
    else:
        regions = _ocr_hybrid(img)

    # Filter by confidence
    regions = [r for r in regions if r["confidence"] >= min_confidence]

    # Sort by position
    regions.sort(key=lambda r: (r["y"], r["x"]))

    # Cap
    if max_regions and len(regions) > max_regions:
        regions = regions[:max_regions]

    return regions


# ---------------------------------------------------------------------------
# Public API — find_text_on_screen (backward-compatible)
# ---------------------------------------------------------------------------

def deduplicate_by_proximity(matches, threshold=50):
    """Remove near-duplicate matches within proximity threshold."""
    if not matches:
        return []

    filtered = []
    for match in matches:
        is_duplicate = False
        for existing in filtered:
            dist = math.sqrt(
                (match["x"] - existing["x"]) ** 2 + (match["y"] - existing["y"]) ** 2
            )
            if dist < threshold:
                if match["confidence"] > existing["confidence"]:
                    filtered.remove(existing)
                    break
                else:
                    is_duplicate = True
                    break
        if not is_duplicate:
            filtered.append(match)

    return filtered


def find_text_on_screen(
    text,
    case_sensitive=False,
    return_all=False,
    min_confidence=75,
    max_results=3,
    silent=False,
    exact_word=False,
    ss_path=None,  # reuse existing screenshot instead of taking new
):
    """Find text on screen using OCR. Optionally reuses an existing screenshot.

    If ss_path is provided, uses that image (avoids ~5s per call).
    Otherwise takes a fresh screenshot for backward compatibility.
    Uses RapidOCR if available, falls back to Tesseract.
    """
    if not PIL_AVAILABLE:
        if not silent:
            print("\u26a0\ufe0f  PIL not available. Install with: pip3 install Pillow")
        return [] if return_all else None

    from .input import screenshot as take_screenshot

    if ss_path is None:
        ss_path = SCREENSHOT_DIR / "ocr_search.png"
        take_screenshot(ss_path, primary_only=True)

    img = Image.open(ss_path)

    # Use RapidOCR if available (faster, better), else Tesseract with upscaling
    if RAPIDOCR_AVAILABLE:
        regions = _ocr_rapidocr(img, upscale=True)
    elif OCR_AVAILABLE:
        upscaled, scale = _upscale_image(img, scale=3)
        regions = _ocr_tesseract_raw(upscaled, psm=6)
        _scale_coords(regions, scale)
        regions = _merge_adjacent_words(regions)
    else:
        if not silent:
            print("\u26a0\ufe0f  No OCR engine available")
        return [] if return_all else None

    # Search for text in regions
    search_text = text if case_sensitive else text.lower()
    matches = []

    for r in regions:
        rtext = r["text"] if case_sensitive else r["text"].lower()

        if exact_word:
            is_match = rtext == search_text
        else:
            is_match = search_text in rtext

        if is_match and r["confidence"] >= min_confidence:
            matches.append({
                "text": r["text"],
                "x": r["x"] + r["w"] // 2,
                "y": r["y"] + r["h"] // 2,
                "width": r["w"],
                "height": r["h"],
                "confidence": r["confidence"],
                "bounds": (r["x"], r["y"], r["w"], r["h"]),
            })

    matches.sort(key=lambda m: m["confidence"], reverse=True)

    if not return_all:
        matches = matches[:max_results]

    if matches:
        if not silent:
            if return_all:
                print(f"\u2713 Found {len(matches)} match(es) for {text}:")
                print(json.dumps(matches, indent=2))
            else:
                print(f"\u2713 Found {text} ({len(matches)} match(es)):")
                for i, match in enumerate(matches, 1):
                    print(
                        f'  [{i}] "{match["text"]}" at ({match["x"]}, {match["y"]}) - {match["confidence"]}% confidence'
                    )
                if len(matches) > 0:
                    print(f'\nTo click: desktop-agent click "{text}"')

        return matches if return_all else matches[0]
    else:
        if not silent:
            print(f"\u2717 No matches found for {text} (min confidence: {min_confidence}%)")
            if min_confidence > 60:
                print(f"   Try: desktop-agent find-text \"{text}\" --min-confidence 60")
        return [] if return_all else None
