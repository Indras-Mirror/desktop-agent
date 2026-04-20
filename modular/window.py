import subprocess
import time
import glob as glob_module
import os


def _xdotool(*args):
    result = subprocess.run(["xdotool"] + list(args), capture_output=True, text=True)
    return result.stdout.strip(), result.returncode


def list_windows():
    stdout, _ = _xdotool("search", "--onlyvisible", "--name", ".")
    windows = []
    for wid in stdout.split("\n"):
        wid = wid.strip()
        if not wid:
            continue
        name, _ = _xdotool("getwindowname", wid)
        pid, _ = _xdotool("getwindowpid", wid)
        windows.append({"id": wid, "name": name, "pid": pid})
    return windows


def get_active_window():
    wid, _ = _xdotool("getactivewindow")
    name, _ = _xdotool("getwindowname", wid)
    pid, _ = _xdotool("getwindowpid", wid)
    geom, _ = _xdotool("getwindowgeometry", wid)
    return {"id": wid, "name": name, "pid": pid, "geometry": geom}


def get_mouse_position():
    stdout, _ = _xdotool("getmouselocation")
    coords = {}
    for p in stdout.split():
        if ":" in p:
            k, v = p.split(":", 1)
            coords[k] = v
    return coords


def get_screen_size():
    stdout, _ = _xdotool("getdisplaygeometry")
    if stdout:
        parts = stdout.split()
        if len(parts) >= 2:
            return int(parts[0]), int(parts[1])

    result = subprocess.run(["xrandr"], capture_output=True, text=True)
    if result.returncode == 0:
        for line in result.stdout.split("\n"):
            if "*" in line:
                res = line.split()[0]
                if "x" in res:
                    w, h = res.split("x")
                    return int(w), int(h)

    return 1920, 1080


def wait_for_text(text, timeout=10, interval=0.5, silent=False):
    from .ocr import find_text_on_screen

    if not silent:
        print(f"Waiting for text {text} (timeout: {timeout}s)...")
    start = time.time()

    while time.time() - start < timeout:
        result = find_text_on_screen(text, return_all=False, silent=True)
        if result:
            elapsed = time.time() - start
            if not silent:
                print(f"Found {text} after {elapsed:.1f}s")
            result["time"] = elapsed
            return result
        time.sleep(interval)

    if not silent:
        print(f"Timeout: {text} not found after {timeout}s")
    return None


def wait_for_window(name, timeout=10, interval=0.5, auto_focus=True):
    print(f"Waiting for window {name} (timeout: {timeout}s)...")
    start = time.time()

    while time.time() - start < timeout:
        stdout, _ = _xdotool("search", "--onlyvisible", "--name", name)
        if stdout:
            window_id = stdout.split()[0]
            elapsed = time.time() - start
            print(f"Window {name} found after {elapsed:.1f}s (ID: {window_id})")

            if auto_focus:
                _xdotool("windowactivate", window_id)
                time.sleep(0.2)
                _xdotool("windowraise", window_id)
                time.sleep(0.3)
                _xdotool("windowfocus", window_id)
                time.sleep(0.2)
                print(f"Focused window {name}")

            return window_id
        time.sleep(interval)

    print(f"Timeout: Window {name} not found after {timeout}s")
    return None


def ensure_window_focused(name, timeout=5):
    active = get_active_window()
    if name.lower() in active['name'].lower():
        print(f"Window already focused: {active['name']}")
        return True

    return wait_for_window(name, timeout=timeout, auto_focus=True) is not None


def wait_for_file(pattern, timeout=30, interval=1.0):
    pattern = os.path.expanduser(pattern)
    print(f"Waiting for file matching {pattern} (timeout: {timeout}s)...")
    start = time.time()

    while time.time() - start < timeout:
        matches = sorted(glob_module.glob(pattern))
        if matches:
            file_path = matches[0]
            try:
                size = os.path.getsize(file_path)
                if size < 1024:
                    size_str = f"{size}B"
                elif size < 1024 * 1024:
                    size_str = f"{size / 1024:.1f}KB"
                else:
                    size_str = f"{size / (1024 * 1024):.1f}MB"
            except OSError:
                size_str = "?"
            elapsed = time.time() - start
            print(f"Found file after {elapsed:.1f}s: {file_path} ({size_str})")
            return file_path
        time.sleep(interval)

    print(f"Timeout: File matching {pattern} not found after {timeout}s")
    return None


def ensure_app(app_name, timeout=10):
    print(f"Ensuring {app_name} is running...")

    stdout, _ = _xdotool("search", "--onlyvisible", "--name", app_name)
    if stdout:
        window_id = stdout.split()[0]
        _xdotool("windowactivate", window_id)
        time.sleep(0.3)
        print(f"{app_name} already running (focused window {window_id})")
        return True, window_id, "already_running"

    print(f"  Starting {app_name}...")

    _xdotool("key", "Super")
    time.sleep(0.8)
    _xdotool("type", app_name)
    time.sleep(0.5)
    _xdotool("key", "Return")

    print(f"  Waiting for {app_name} to open...")
    window_id = wait_for_window(app_name, timeout=timeout, auto_focus=True)

    if window_id:
        print(f"{app_name} started successfully (window {window_id})")
        return True, window_id, "started"
    else:
        print(f"Failed to start {app_name}")
        return False, None, "failed"


def navigate(url, wait_for=None, timeout=15):
    print(f"Navigating to {url}...")

    subprocess.run(["xdotool", "key", "ctrl+l"], capture_output=True, text=True)
    time.sleep(0.5)

    subprocess.run(["xdotool", "type", "--clearmodifiers", url], capture_output=True, text=True)
    time.sleep(0.3)

    subprocess.run(["xdotool", "key", "Return"], capture_output=True, text=True)
    print(f"Navigated to {url}")

    if wait_for:
        print(f"  Waiting for page to load (looking for {wait_for})...")
        result = wait_for_text(wait_for, timeout=timeout, silent=True)
        if result:
            print(f"  Page loaded (found {wait_for} after {result['time']:.1f}s)")
            return True
        else:
            print(f"  Page load timeout: {wait_for} not found after {timeout}s")
            return False

    time.sleep(2)
    return True


def web_search(query, verify=True, timeout=10):
    print(f"Searching for: {query}")

    subprocess.run(["xdotool", "key", "ctrl+k"], capture_output=True, text=True)
    time.sleep(0.8)

    subprocess.run(["xdotool", "type", "--clearmodifiers", query], capture_output=True, text=True)
    time.sleep(0.5)
    print(f"Typed search query: {query}")

    subprocess.run(["xdotool", "key", "Return"], capture_output=True, text=True)
    print(f"Submitted search")

    if verify:
        print(f"  Verifying search results...")
        result = wait_for_text(query.split()[0], timeout=timeout, silent=True)
        if result:
            print(f"  Search results appeared")
            return True
        else:
            print(f"  Search verification failed - results not found")
            return False

    return True
