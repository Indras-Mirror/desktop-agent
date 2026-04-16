from .config import run_cmd, ATSPI_AVAILABLE, ELEMENT_CACHE, STABLE_ELEMENT_REGISTRY
from difflib import SequenceMatcher
import math


def get_element_bounds(element):
    try:
        import pyatspi

        component = element.queryComponent()
        extents = component.getExtents(pyatspi.DESKTOP_COORDS)
        x, y, w, h = extents.x, extents.y, extents.width, extents.height

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
    try:
        import pyatspi

        selector = {
            "role": element.getRoleName(),
            "name": element.name if element.name else None,
            "description": element.description if element.description else None,
            "app_name": None,
            "index": None,
            "attrs": {},
        }

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
    if not selector_name:
        return 1.0

    elem_name = elem_name or ""
    selector_name_lower = selector_name.lower()
    elem_name_lower = elem_name.lower()

    if selector_name_lower == elem_name_lower:
        return 1.0

    if selector_name_lower in elem_name_lower:
        return 0.85 + (len(selector_name) / max(len(elem_name), 1)) * 0.1
    if elem_name_lower in selector_name_lower:
        return 0.80

    ratio = SequenceMatcher(None, selector_name_lower, elem_name_lower).ratio()
    return ratio


def selector_matches(element, selector):
    try:
        if selector.get("role") and element.getRoleName() != selector["role"]:
            return False
        return True
    except:
        return False


def calculate_match_confidence(element, selector):
    import pyatspi

    confidence = 1.0

    name_conf = calculate_name_confidence(
        element.name if element.name else "", selector.get("name")
    )
    confidence *= 0.5 + name_conf * 0.5

    if selector.get("description"):
        desc_conf = calculate_name_confidence(
            element.description if element.description else "", selector["description"]
        )
        confidence *= 0.7 + desc_conf * 0.3

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
                confidence *= 1.1
            else:
                confidence *= 0.7
        except:
            pass

    return min(confidence, 1.0)


def find_all_elements_by_selector(desktop, selector, max_depth=15, min_confidence=0.3):
    all_matches = []

    try:
        for i in range(desktop.childCount):
            try:
                app = desktop.getChildAtIndex(i)
                if app.name:
                    if selector.get("app_name") and app.name != selector["app_name"]:
                        continue

                    matches = _search_tree_for_all_matches(
                        app, selector, 0, max_depth, min_confidence
                    )
                    all_matches.extend(matches)
            except:
                pass
    except:
        pass

    all_matches.sort(key=lambda x: x["confidence"], reverse=True)
    return all_matches


def _search_tree_for_all_matches(element, selector, depth, max_depth, min_confidence):
    matches = []

    if depth > max_depth:
        return matches

    try:
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
    matches = find_all_elements_by_selector(
        desktop, selector, max_depth, min_confidence=0.5
    )
    return matches[0] if matches else None


def _search_tree_for_match(element, selector, depth, max_depth):
    if depth > max_depth:
        return None

    try:
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
    global ELEMENT_CACHE, STABLE_ELEMENT_REGISTRY

    if ref not in ELEMENT_CACHE:
        print(f"Error: Element {ref} not found. Run snapshot -i first.")
        return None

    elem = ELEMENT_CACHE[ref]
    selector = create_element_selector(elem["element"]) if "element" in elem else None

    if not selector:
        print(f"Error: Could not create selector for {ref}")
        return None

    stable_id = f"pin_{len(STABLE_ELEMENT_REGISTRY) + 1}"

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
    global STABLE_ELEMENT_REGISTRY, ELEMENT_CACHE

    if not STABLE_ELEMENT_REGISTRY:
        return []

    import pyatspi

    desktop = None
    try:
        desktop = pyatspi.Registry.getDesktop(0)
    except:
        print("Error: Could not access AT-SPI")
        return []

    results = []
    for stable_id, entry in list(STABLE_ELEMENT_REGISTRY.items()):
        selector = entry["selector"]
        matches = find_all_elements_by_selector(desktop, selector, min_confidence=0.3)

        if matches:
            best_match = matches[0]
            orig_ref = entry["ref"]

            ELEMENT_CACHE[orig_ref] = best_match

            STABLE_ELEMENT_REGISTRY[stable_id]["last_x"] = best_match["x"]
            STABLE_ELEMENT_REGISTRY[stable_id]["last_y"] = best_match["y"]
            STABLE_ELEMENT_REGISTRY[stable_id]["stale"] = False
            STABLE_ELEMENT_REGISTRY[stable_id]["confidence"] = best_match["confidence"]
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
                    f"  {status} {r['ref']}: {r['name']} @ ({r['x']}, {r['y']}) - {conf_pct}% confidence"
                )
    if stale > 0:
        print(f"  ⚠ {stale} element(s) could not be found")

    return results


def list_pinned():
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
    import pyatspi

    if elements is None:
        elements = []

    if depth > max_depth:
        return elements

    try:
        role = element.getRole()
        state_set = element.getState()

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
            pyatspi.ROLE_PAGE_TAB,
            pyatspi.ROLE_COMBO_BOX,
            pyatspi.ROLE_LABEL,
            pyatspi.ROLE_ICON,
            pyatspi.ROLE_MENU_BAR,
        ]

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

        for i in range(element.childCount):
            try:
                child = element.getChildAtIndex(i)
                walk_tree(child, depth + 1, max_depth, elements)
            except:
                pass

    except:
        pass

    return elements
