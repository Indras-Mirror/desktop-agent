import sys
import json
from pathlib import Path

from .config import RECORDING_ACTIVE
from .task_system import (
    start_recording,
    save_task,
    list_tasks,
    search_tasks,
    replay_task,
    delete_task,
)
from .input import (
    screenshot,
    region_screenshot,
    type_text,
    press_key,
    click,
    click_element,
    dblclick,
    move,
    execute_step,
)
from .window import (
    list_windows,
    wait_for_text,
    wait_for_window,
    wait_for_file,
    ensure_app,
    navigate,
    web_search,
)
from .input import (
    focus_window,
    screenshot,
    region_screenshot,
    type_text,
    press_key,
    click,
    click_element,
    dblclick,
    move,
    scroll,
    drag,
    execute_step,
)
from .atspi import pin_element, list_pinned, relink_pinned_elements
from .snapshot import snapshot
from .ocr import find_text_on_screen


def main():
    if len(sys.argv) < 2:
        print("Usage: desktop-agent <command> [args]")
        print("Run desktop-agent --help for full usage")
        sys.exit(1)

    cmd = sys.argv[1]
    args = sys.argv[2:]

    if cmd == "--help" or cmd == "-h":
        print("""
desktop-agent - Desktop automation CLI for AI agents

MULTI-MONITOR MODE:
    All coordinates are relative to PRIMARY MONITOR only.
    Use 'monitor' command to see monitor configuration.

COMMANDS:
    screenshot [path]              Take screenshot (primary monitor only)
    region <x,y,w,h> [path]      Screenshot of region
    windows                        List visible windows
    focus <name>                   Focus window by name
    click                         Click at current mouse position (no move)
    click <x> <y>                 Click at coordinates (primary monitor)
    click @eN                     Click element by ref (after snapshot -i)
    click "text"                  Click text via OCR search
    click <target> --verify "text" Click and verify expected result
    dblclick <x> <y>              Double click (primary monitor)
    scroll <x> <y> [dir] [n]    Scroll at coords (dir: up/down/left/right, n: clicks)
    drag <x1> <y1> <x2> <y2>    Drag from start to end coordinates
    move <x> <y>                 Move mouse (primary monitor)
    type "<text>"                 Type text
    key <keyname>                 Press key (Enter, Ctrl+c, etc.)
    active                         Get active window info
    mouse                          Get mouse position
    monitor                        Show primary monitor configuration
    snapshot                       Full UI snapshot (primary monitor)
    snapshot -i                   Interactive snapshot with AT-SPI elements
    find-text [options] "<text>"  Find text using OCR
                                  --all             Return all matches as JSON
                                  --min-confidence  Min confidence (default: 75)
                                  --max-results     Max results (default: 3)
                                  --exact-word      Match exact word only (no substrings)
    wait-for-text "<text>"        Wait for text to appear (timeout: 10s)
    wait-for-window "<name>"      Wait for window to appear and focus (timeout: 10s)
    wait-for-file "<pattern>"     Wait for file to exist (timeout: 30s)
    ensure-app "<name>"           Ensure app is running (focus or start, timeout: 10s)
    shortcut <app> <action>       Execute app-specific keyboard shortcut
    shortcut <app> list           List all shortcuts for an app
    navigate "<url>"              Navigate browser to URL (handles URL bar)
                                  --wait-for "text"  Wait for text after load
    web-search "<query>"          Search using browser search box (Ctrl+K)
                                  --no-verify  Skip result verification
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
    Run snapshot -i to scan for interactive UI elements
    Elements are assigned refs like @e1, @e2, @e3...
    Click elements with click @e1 instead of coordinates
    Similar to agent-browser mechanics!

STABLE ELEMENT REFS (PINNING):
    Elements become stale after UI changes. Use pin to make them stable.
    Pinned elements auto-relink when clicked - coordinates update automatically.
    Use pinned to see all pins, unpin to remove them.

OCR TEXT FINDING:
    Use find-text to locate text on screen using OCR
    Useful when AT-SPI doesn't expose elements
    Returns coordinates of the text for clicking
""")
        sys.exit(0)

    elif cmd in ["screenshot", "ss"]:
        path = args[0] if args else None
        screenshot(path)

    elif cmd == "region":
        if len(args) < 1:
            print("Usage: region <x,y,w,h> [path]")
            sys.exit(1)
        coords = args[0].split(",")
        x, y, w, h = map(int, coords)
        path = args[1] if len(args) > 1 else None
        region_screenshot(x, y, w, h, path)

    elif cmd in ["windows", "win"]:
        for win in list_windows():
            print(f"{win['id']} | {win['pid']} | {win['name']}")

    elif cmd == "focus":
        if not args:
            print("Usage: focus <window-name>")
            sys.exit(1)
        focus_window(args[0])

    elif cmd == "click":
        if len(args) == 0:
            success = click()
            sys.exit(0 if success else 1)

        verify = None
        verify_timeout = 5
        if "--verify" in args:
            verify_idx = args.index("--verify")
            if verify_idx + 1 < len(args):
                verify = args[verify_idx + 1]
                args = args[:verify_idx] + args[verify_idx + 2 :]
            else:
                print("Error: --verify requires a text argument")
                sys.exit(1)

        if args[0].startswith("@e"):
            target = args[0]
            success = click(target, verify=verify, verify_timeout=verify_timeout)
        elif len(args) >= 2 and args[0].isdigit() and args[1].isdigit():
            target = (int(args[0]), int(args[1]))
            success = click(target, verify=verify, verify_timeout=verify_timeout)
        else:
            target = " ".join(args)
            success = click(target, verify=verify, verify_timeout=verify_timeout)

        sys.exit(0 if success else 1)

    elif cmd == "dblclick":
        if len(args) == 0:
            dblclick()
        elif len(args) >= 2:
            dblclick(int(args[0]), int(args[1]))
        else:
            print("Usage: dblclick [<x> <y>]")
            sys.exit(1)

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

    elif cmd == "key":
        if not args:
            print("Usage: key <keyname>")
            sys.exit(1)
        press_key(args[0])

    elif cmd == "shortcut":
        from .shortcuts import get_shortcut, list_shortcuts
        if len(args) < 2:
            print("Usage: shortcut <app> <action>")
            print("       shortcut <app> list")
            sys.exit(1)

        app_name = args[0]
        action = args[1]

        if action == "list":
            shortcuts = list_shortcuts(app_name)
            if shortcuts:
                print(f"Shortcuts for {app_name}:")
                for act, key in shortcuts.items():
                    print(f"  {act}: {key}")
            else:
                print(f"No shortcuts found for {app_name}")
        else:
            shortcut = get_shortcut(app_name, action)
            if shortcut:
                print(f"Pressing {app_name} shortcut '{action}': {shortcut}")
                press_key(shortcut)
            else:
                print(f"Unknown shortcut: {action} for {app_name}")

    elif cmd == "active":
        from .window import get_active_window

        active = get_active_window()
        print(json.dumps(active, indent=2))

    elif cmd == "mouse":
        from .window import get_mouse_position

        print(json.dumps(get_mouse_position(), indent=2))

    elif cmd == "monitor":
        from .config import PRIMARY_MONITOR
        print("Primary Monitor:")
        print(json.dumps(PRIMARY_MONITOR, indent=2))
        print("\nAll coordinates are relative to the primary monitor.")
        print(f"Absolute position: ({PRIMARY_MONITOR['x']}, {PRIMARY_MONITOR['y']})")
        print(f"Size: {PRIMARY_MONITOR['width']}x{PRIMARY_MONITOR['height']}")

    elif cmd == "snapshot":
        interactive = "-i" in args or "--interactive" in args
        snapshot(interactive=interactive)

    elif cmd == "find-text":
        return_all = "--all" in args or "-a" in args
        exact_word = "--exact-word" in args
        min_confidence = 75
        max_results = 3

        if "--min-confidence" in args:
            idx = args.index("--min-confidence")
            if idx + 1 < len(args):
                min_confidence = int(args[idx + 1])
                args = args[:idx] + args[idx + 2 :]

        if "--max-results" in args:
            idx = args.index("--max-results")
            if idx + 1 < len(args):
                max_results = int(args[idx + 1])
                args = args[:idx] + args[idx + 2 :]

        if return_all:
            args = [a for a in args if a not in ("--all", "-a")]

        if exact_word:
            args = [a for a in args if a != "--exact-word"]

        if not args:
            print(
                "Usage: find-text [--all] [--min-confidence N] [--max-results N] [--exact-word] <text>"
            )
            sys.exit(1)

        text = " ".join(args)
        find_text_on_screen(
            text,
            return_all=return_all,
            min_confidence=min_confidence,
            max_results=max_results,
            exact_word=exact_word,
        )

    elif cmd == "wait-for-text":
        if not args:
            print('Usage: wait-for-text "<text>" [--timeout N]')
            sys.exit(1)

        timeout = 10
        if "--timeout" in args:
            idx = args.index("--timeout")
            if idx + 1 < len(args):
                timeout = int(args[idx + 1])
                args = args[:idx] + args[idx + 2 :]

        text = " ".join(args)
        result = wait_for_text(text, timeout=timeout)
        sys.exit(0 if result else 1)

    elif cmd == "wait-for-window":
        if not args:
            print('Usage: wait-for-window "<name>" [--timeout N]')
            sys.exit(1)

        timeout = 10
        if "--timeout" in args:
            idx = args.index("--timeout")
            if idx + 1 < len(args):
                timeout = int(args[idx + 1])
                args = args[:idx] + args[idx + 2 :]

        name = " ".join(args)
        result = wait_for_window(name, timeout=timeout)
        sys.exit(0 if result else 1)

    elif cmd == "wait-for-file":
        if not args:
            print('Usage: wait-for-file "<pattern>" [--timeout N]')
            sys.exit(1)

        timeout = 30
        if "--timeout" in args:
            idx = args.index("--timeout")
            if idx + 1 < len(args):
                timeout = int(args[idx + 1])
                args = args[:idx] + args[idx + 2 :]

        pattern = " ".join(args)
        result = wait_for_file(pattern, timeout=timeout)
        sys.exit(0 if result else 1)

    elif cmd == "ensure-app":
        if not args:
            print('Usage: ensure-app "<app-name>" [--timeout N]')
            sys.exit(1)

        timeout = 10
        if "--timeout" in args:
            idx = args.index("--timeout")
            if idx + 1 < len(args):
                timeout = int(args[idx + 1])
                args = args[:idx] + args[idx + 2 :]

        app_name = " ".join(args)
        success, window_id, status = ensure_app(app_name, timeout=timeout)
        sys.exit(0 if success else 1)

    elif cmd == "navigate":
        if not args:
            print('Usage: navigate "<url>" [--wait-for "text"] [--timeout N]')
            sys.exit(1)

        wait_for = None
        if "--wait-for" in args:
            idx = args.index("--wait-for")
            if idx + 1 < len(args):
                wait_for = args[idx + 1]
                args = args[:idx] + args[idx + 2 :]

        timeout = 15
        if "--timeout" in args:
            idx = args.index("--timeout")
            if idx + 1 < len(args):
                timeout = int(args[idx + 1])
                args = args[:idx] + args[idx + 2 :]

        url = " ".join(args)
        success = navigate(url, wait_for=wait_for, timeout=timeout)
        sys.exit(0 if success else 1)

    elif cmd == "web-search":
        if not args:
            print('Usage: web-search "<query>" [--no-verify] [--timeout N]')
            sys.exit(1)

        verify = True
        if "--no-verify" in args:
            verify = False
            args = [a for a in args if a != "--no-verify"]

        timeout = 10
        if "--timeout" in args:
            idx = args.index("--timeout")
            if idx + 1 < len(args):
                timeout = int(args[idx + 1])
                args = args[:idx] + args[idx + 2 :]

        query = " ".join(args)
        success = web_search(query, verify=verify, timeout=timeout)
        sys.exit(0 if success else 1)

    elif cmd == "pin":
        if not args:
            print("Usage: pin @eN")
            sys.exit(1)
        ref = args[0]
        stable_id = pin_element(ref)
        if stable_id:
            print(f"Use pinned to list all pinned elements")
            print(
                f"Note: Pinned elements are automatically relinked when you click them"
            )

    elif cmd == "unpin":
        from .config import STABLE_ELEMENT_REGISTRY

        if not args:
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
        print("Recording enabled. Execute your task steps, then use save-task to save.")

    elif cmd == "save-task":
        if not args:
            print(
                'Usage: save-task <name> [--description "..."] [--purpose "..."] [--context "..."] [--app-context "..."] [--params \'[...]\']'
            )
            sys.exit(1)
        name = args[0]
        description = ""
        purpose = ""
        context = ""
        app_context = ""
        parameters = None
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
            elif args[i] == "--params" and i + 1 < len(args):
                try:
                    parameters = json.loads(args[i + 1])
                except json.JSONDecodeError:
                    print(f"Error: Invalid JSON for --params: {args[i + 1]}")
                    sys.exit(1)
                i += 2
            else:
                i += 1
        save_task(name, description, purpose, context, app_context, parameters)

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
            print("Usage: replay [--run] [--param key=value ...] <task-name-or-query>")
            sys.exit(1)

        run_mode = False
        param_values = {}
        query_args = []

        i = 0
        while i < len(args):
            if args[i] == "--run":
                run_mode = True
                i += 1
            elif args[i] == "--param" and i + 1 < len(args):
                if "=" in args[i + 1]:
                    key, value = args[i + 1].split("=", 1)
                    param_values[key] = value
                i += 2
            else:
                query_args.append(args[i])
                i += 1

        query = " ".join(query_args)
        if not query:
            print("Error: No task name or query provided")
            sys.exit(1)

        steps = replay_task(
            query, param_values if param_values else None, dry_run=not run_mode
        )

        if not steps:
            print("Task not found. Use tasks search <query> to find similar tasks.")
            sys.exit(1)

    elif cmd == "forget":
        if not args:
            print("Usage: forget <task-name>")
            sys.exit(1)
        delete_task(args[0])

    elif cmd == "scroll":
        if len(args) < 2:
            print("Usage: scroll <x> <y> [direction] [clicks]")
            print("  direction: up, down (default), left, right")
            print("  clicks: number of scroll steps (default: 3)")
            sys.exit(1)
        x, y = int(args[0]), int(args[1])
        direction = args[2] if len(args) > 2 else "down"
        clicks = int(args[3]) if len(args) > 3 else 3
        scroll(x, y, direction=direction, clicks=clicks)

    elif cmd == "drag":
        if len(args) < 4:
            print("Usage: drag <x1> <y1> <x2> <y2>")
            sys.exit(1)
        drag(int(args[0]), int(args[1]), int(args[2]), int(args[3]))

    else:
        print(f"Unknown command: {cmd}")
        print("Run 'desktop-agent --help' for usage")
        sys.exit(1)


if __name__ == "__main__":
    main()
