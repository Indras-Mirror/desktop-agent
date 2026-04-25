from .config import OCR_AVAILABLE, PIL_AVAILABLE, SCREENSHOT_DIR, PRIMARY_MONITOR
from PIL import Image
import json
import math
from pathlib import Path


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
    exact_word=False,
):
    if not OCR_AVAILABLE:
        if not silent:
            print("⚠️  OCR not available. Install with: pip3 install pytesseract")
        return [] if return_all else None

    if not PIL_AVAILABLE:
        if not silent:
            print("⚠️  PIL not available. Install with: pip3 install Pillow")
        return [] if return_all else None

    from .input import screenshot as take_screenshot

    ss_path = SCREENSHOT_DIR / "ocr_search.png"
    take_screenshot(ss_path, primary_only=True)

    import pytesseract

    img = Image.open(ss_path)
    data = pytesseract.image_to_data(img, output_type=pytesseract.Output.DICT)

    search_text = text if case_sensitive else text.lower()
    search_words = search_text.split()
    is_phrase = len(search_words) > 1
    matches = []

    if is_phrase:
        for i in range(len(data["text"]) - len(search_words) + 1):
            consecutive = []
            for j, sw in enumerate(search_words):
                idx = i + j
                word = data["text"][idx]
                if not word:
                    break
                cw = word if case_sensitive else word.lower()
                if exact_word:
                    if cw != sw:
                        break
                else:
                    if cw != sw and sw not in cw and cw not in sw:
                        break
                consecutive.append(idx)
            else:
                if len(consecutive) == len(search_words):
                    first, last = consecutive[0], consecutive[-1]
                    x1 = data["left"][first]
                    y1 = min(data["top"][idx] for idx in consecutive)
                    x2 = data["left"][last] + data["width"][last]
                    y2 = max(data["top"][idx] + data["height"][idx] for idx in consecutive)
                    confs = [int(data["conf"][idx]) for idx in consecutive]
                    avg_conf = sum(confs) // len(confs)

                    if avg_conf >= min_confidence:
                        matched_text = " ".join(data["text"][idx] for idx in consecutive)
                        matches.append({
                            "text": matched_text,
                            "x": (x1 + x2) // 2,
                            "y": (y1 + y2) // 2,
                            "width": x2 - x1,
                            "height": y2 - y1,
                            "confidence": min(100, int(avg_conf * 1.2)) if matched_text.lower() == search_text else avg_conf,
                            "original_confidence": avg_conf,
                            "bounds": (x1, y1, x2 - x1, y2 - y1),
                        })
    else:
        for i, word in enumerate(data["text"]):
            if word:
                compare_word = word if case_sensitive else word.lower()

                is_match = False
                if exact_word:
                    is_match = compare_word == search_text
                elif compare_word == search_text:
                    is_match = True
                elif len(search_text) >= 3:
                    is_match = compare_word == search_text
                else:
                    is_match = search_text in compare_word or compare_word in search_text

                if is_match:
                    x, y, w, h = (
                        data["left"][i],
                        data["top"][i],
                        data["width"][i],
                        data["height"][i],
                    )
                    conf = data["conf"][i]

                    if int(conf) >= min_confidence:
                        match_quality = 1.0
                        if compare_word == search_text:
                            match_quality = 1.2
                        elif len(compare_word) >= len(search_text):
                            match_quality = 1.1

                        adjusted_conf = min(100, int(conf * match_quality))

                        matches.append(
                            {
                                "text": word,
                                "x": x + w // 2,
                                "y": y + h // 2,
                                "width": w,
                                "height": h,
                                "confidence": adjusted_conf,
                                "original_confidence": int(conf),
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


