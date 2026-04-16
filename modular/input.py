from .config import (
    run_cmd,
    SCREENSHOT_DIR,
    ELEMENT_CACHE,
    STABLE_ELEMENT_REGISTRY,
    ATSPI_AVAILABLE,
)
import time


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


def focus_window(name):
    run_cmd(f'xdotool search --onlyvisible --name "{name}" windowactivate')


def click_coords(x, y):
    run_cmd(f"xdotool mousemove {x} {y} click 1")
    print(f"✓ Clicked at ({x}, {y})")
    return True


def dblclick(x, y):
    run_cmd(f"xdotool mousemove {x} {y} click 1 click 1")
    print(f"✓ Double-clicked at ({x}, {y})")


def move(x, y):
    run_cmd(f"xdotool mousemove {x} {y}")
    print(f"✓ Moved to ({x}, {y})")


def type_text(text):
    run_cmd(f'xdotool type --delay 50 "{text}"')
    print(f"✓ Typed: {text}")


def press_key(key):
    run_cmd(f"xdotool key {key}")
    print(f"✓ Pressed: {key}")


def execute_step(step):
    from .window import focus_window
    from .ocr import find_text_on_screen

    cmd = step["command"]
    args = step["args"]

    if cmd == "focus":
        if args:
            focus_window(args[0])
    elif cmd == "click":
        if args and args[0].startswith("@e"):
            click_element(args[0])
        elif len(args) >= 2:
            click(int(args[0]), int(args[1]))
    elif cmd == "type":
        if args:
            type_text(" ".join(args))
    elif cmd == "key":
        if args:
            press_key(args[0])
    elif cmd == "screenshot":
        screenshot(args[0] if args else None)
    elif cmd == "region":
        if len(args) >= 4:
            region_screenshot(*[int(a) for a in args[:4]])
    elif cmd == "move":
        if len(args) >= 2:
            move(int(args[0]), int(args[1]))
    elif cmd == "dblclick":
        if len(args) >= 2:
            dblclick(int(args[0]), int(args[1]))
    elif cmd == "find-text":
        if args:
            result = find_text_on_screen(" ".join(args))
            if result:
                click(result["x"], result["y"])
    else:
        raise ValueError(f"Unknown command: {cmd}")


def click_element(ref, force_confidence_threshold=0.5):
    global ELEMENT_CACHE, STABLE_ELEMENT_REGISTRY
    from .atspi import relink_pinned_elements

    if ref not in ELEMENT_CACHE:
        if STABLE_ELEMENT_REGISTRY:
            results = relink_pinned_elements()

        if ref not in ELEMENT_CACHE:
            print(f"Error: Element {ref} not found. Run snapshot -i first.")
            return False

    elem = ELEMENT_CACHE[ref]
    x, y = elem["x"], elem["y"]
    confidence = elem.get("confidence", 1.0)

    name_str = elem["name"][:30] if elem["name"] else "(unnamed)"
    role_str = elem["role"]

    if confidence < 1.0:
        conf_pct = int(confidence * 100)
        if confidence < force_confidence_threshold:
            print(f"⚠ Low confidence ({conf_pct}%) for {ref}: {name_str} [{role_str}]")
            print(f"   Position: ({x}, {y})")

            alternatives = elem.get("alternatives", [])
            if alternatives:
                print(f"   Alternatives:")
                for i, alt in enumerate(alternatives[:3], 1):
                    alt_name = alt["name"][:25] if alt["name"] else "(unnamed)"
                    alt_conf = int(alt["confidence"] * 100)
                    alt_x = alt["x"]
                    alt_y = alt["y"]
                    print(
                        f"     [{i}] {alt_name} @ ({alt_x}, {alt_y}) - {alt_conf}% confidence"
                    )
            return False
        else:
            print(
                f"? {ref}: {name_str} [{role_str}] at ({x}, {y}) - {conf_pct}% confidence (proceeding)"
            )

    print(f"Clicking {ref}: {name_str} [{role_str}] at ({x}, {y})")
    click(x, y)
    return True


def click(target, verify=None, verify_timeout=5):
    from .window import wait_for_text

    if isinstance(target, (tuple, list)) and len(target) == 2:
        x, y = int(target[0]), int(target[1])
        click_coords(x, y)
        success = True
    elif isinstance(target, str) and target.startswith("@e"):
        success = click_element(target)
    elif (
        isinstance(target, str)
        and "," in target
        and all(p.strip().isdigit() for p in target.split(","))
    ):
        x, y = map(int, target.split(","))
        click_coords(x, y)
        success = True
    elif isinstance(target, str):
        from .ocr import find_text_on_screen

        result = find_text_on_screen(target, return_all=False, silent=False)
        if result:
            x, y = result["x"], result["y"]
            click_coords(x, y)
            print(f"✓ Clicked text {target} at ({x}, {y})")
            success = True
        else:
            print(f"✗ Text {target} not found on screen")
            partial = find_text_on_screen(
                target, return_all=True, silent=True, min_confidence=60
            )
            if partial and len(partial) > 0:
                print("  Possible alternatives:")
                for i, match in enumerate(partial[:3], 1):
                    m_text = match["text"]
                    m_x = match["x"]
                    m_y = match["y"]
                    m_conf = match["confidence"]
                    print(f"    [{i}] {m_text} at ({m_x}, {m_y}) - {m_conf}%")
            success = False
    else:
        print(f"✗ Invalid click target: {target}")
        success = False

    if success and verify:
        print(f"  ⏳ Verifying: looking for {verify}...")
        result = wait_for_text(verify, timeout=verify_timeout, silent=True)
        if result:
            elapsed = result["time"]
            print(f"  ✓ Verified: Found {verify} after {elapsed:.1f}s")
        else:
            print(
                f"  ✗ Verification failed: {verify} not found after {verify_timeout}s"
            )
            return False

    return success


from pathlib import Path
