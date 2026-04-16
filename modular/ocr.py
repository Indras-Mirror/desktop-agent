from .config import run_cmd, OCR_AVAILABLE, PIL_AVAILABLE, SCREENSHOT_DIR
from PIL import Image
import json
import math


def deduplicate_by_proximity(matches, threshold=50):
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
):
    if not OCR_AVAILABLE:
        if not silent:
            print("⚠️  OCR not available. Install with: pip3 install pytesseract")
        return [] if return_all else None

    if not PIL_AVAILABLE:
        if not silent:
            print("⚠️  PIL not available. Install with: pip3 install Pillow")
        return [] if return_all else None

    ss_path = SCREENSHOT_DIR / "ocr_search.png"
    screenshot(ss_path) if not silent else run_cmd(f"scrot '{ss_path}'")

    import pytesseract

    img = Image.open(ss_path)
    data = pytesseract.image_to_data(img, output_type=pytesseract.Output.DICT)

    search_text = text if case_sensitive else text.lower()
    matches = []

    for i, word in enumerate(data["text"]):
        if word:
            compare_word = word if case_sensitive else word.lower()

            if search_text in compare_word or compare_word in search_text:
                x, y, w, h = (
                    data["left"][i],
                    data["top"][i],
                    data["width"][i],
                    data["height"][i],
                )
                conf = data["conf"][i]

                if int(conf) >= min_confidence:
                    matches.append(
                        {
                            "text": word,
                            "x": x + w // 2,
                            "y": y + h // 2,
                            "width": w,
                            "height": h,
                            "confidence": int(conf),
                            "bounds": (x, y, w, h),
                        }
                    )

    matches = deduplicate_by_proximity(matches, threshold=50)
    matches.sort(key=lambda m: m["confidence"], reverse=True)

    if not return_all:
        matches = matches[:max_results]

    if matches:
        if not silent:
            if return_all:
                print(f"✓ Found {len(matches)} match(es) for {text}:")
                print(json.dumps(matches, indent=2))
            else:
                print(f"✓ Found {text} ({len(matches)} match(es)):")
                for i, match in enumerate(matches, 1):
                    print(
                        f'  [{i}] "{match["text"]}" at ({match["x"]}, {match["y"]}) - {match["confidence"]}% confidence'
                    )
                if len(matches) > 0:
                    print(f'\nTo click: desktop-agent click "{text}"')

        return matches if return_all else matches[0]
    else:
        if not silent:
            print(f"✗ No matches found for {text} (min confidence: {min_confidence}%)")
            if min_confidence > 60:
                print(f'   Try: desktop-agent find-text "{text}" --min-confidence 60')
        return [] if return_all else None


def screenshot(path=None):
    if path is None:
        path = SCREENSHOT_DIR / "screen.png"
    path = Path(path)

    run_cmd(f"scrot '{path}'")
    if path.exists():
        return str(path)
    return None


from pathlib import Path
