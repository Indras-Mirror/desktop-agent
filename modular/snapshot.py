from .config import (
    ELEMENT_CACHE,
    ATSPI_AVAILABLE,
    PIL_AVAILABLE,
    SCREENSHOT_DIR,
    PRIMARY_MONITOR,
)
from .window import get_active_window, get_mouse_position, get_screen_size, list_windows
from .input import screenshot
from .atspi import walk_tree
from PIL import Image, ImageDraw


def snapshot(interactive=False):
    global ELEMENT_CACHE

    print("=== Desktop UI Snapshot ===\n")

    active = get_active_window()
    print(f"Active Window:")
    print(f"  ID: {active['id']}")
    print(f"  Name: {active['name']}")
    print(f"  PID: {active['pid']}")

    mouse = get_mouse_position()
    print(f"\nMouse Position: x={mouse.get('x', '?')}, y={mouse.get('y', '?')}")

    ss_path = SCREENSHOT_DIR / "snapshot.png"
    screenshot(ss_path)

    if interactive:
        if not ATSPI_AVAILABLE:
            print(
                "\n⚠️  AT-SPI not available. Install with: sudo apt install python3-pyatspi"
            )
            print("Falling back to coordinate-based interaction.")
            return {"active_window": active, "mouse": mouse, "elements": []}

        print("\nScanning for interactive elements (AT-SPI)...")

        ELEMENT_CACHE.clear()

        import pyatspi

        desktop = pyatspi.Registry.getDesktop(0)
        all_elements = []

        for i in range(desktop.childCount):
            try:
                app = desktop.getChildAtIndex(i)
                if app.name:
                    elements = walk_tree(app, max_depth=12)
                    all_elements.extend(elements)
            except:
                pass

        # Filter elements to primary monitor only
        mon = PRIMARY_MONITOR

        visible_elements = []
        for elem in all_elements:
            if elem["width"] > 5 and elem["height"] > 5:
                # Check if element is within primary monitor bounds
                if (mon['x'] <= elem["x"] < mon['x'] + mon['width'] and
                    mon['y'] <= elem["y"] < mon['y'] + mon['height']):
                    # Adjust coordinates to be relative to primary monitor
                    elem["x"] -= mon['x']
                    elem["y"] -= mon['y']
                    elem["bounds"] = (elem["bounds"][0] - mon['x'], elem["bounds"][1] - mon['y'])
                    visible_elements.append(elem)

        visible_elements.sort(key=lambda e: (e["y"], e["x"]))

        MAX_ELEMENTS = 50
        if len(visible_elements) > MAX_ELEMENTS:
            print(f"Found {len(visible_elements)} elements, showing top {MAX_ELEMENTS}")
            visible_elements = visible_elements[:MAX_ELEMENTS]

        if visible_elements:
            print(f"\nInteractive Elements ({len(visible_elements)} found):")
            for i, elem in enumerate(visible_elements, 1):
                ref = f"@e{i}"
                ELEMENT_CACHE[ref] = elem

                name = elem["name"][:40] if elem["name"] else "(unnamed)"
                role = elem["role"]
                desc = f" - {elem['description'][:20]}" if elem["description"] else ""
                print(f"  {ref}: {name} [{role}]{desc} at ({elem['x']}, {elem['y']})")

            if PIL_AVAILABLE and ss_path.exists():
                try:
                    img = Image.open(ss_path)
                    draw = ImageDraw.Draw(img)

                    for i, elem in enumerate(visible_elements, 1):
                        x, y = elem["x"], elem["y"]
                        w, h = elem["width"], elem["height"]

                        x1, y1 = elem["bounds"][0], elem["bounds"][1]
                        x2, y2 = x1 + w, y1 + h
                        draw.rectangle([x1, y1, x2, y2], outline="cyan", width=2)

                        draw.ellipse([x - 5, y - 5, x + 5, y + 5], fill="red")

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


