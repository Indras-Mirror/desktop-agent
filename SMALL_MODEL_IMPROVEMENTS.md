# Desktop Agent - Small Model Improvements (Implementation Plan)

**Priority implementations to make desktop-agent work well with less intelligent models**

---

## 🎯 Quick Wins (Implement First)

### 1. Better OCR Filtering

**Problem:** OCR returns 10+ noisy matches, confuses small models

**Solution:** Add filtering flags

```python
# In desktop-agent.py, update find_text() function

def find_text(text, show_all=False, min_confidence=0.70, max_results=5, fuzzy=True):
    """
    Find text using OCR with better filtering
    
    Args:
        text: Text to search for
        show_all: Return JSON with all matches
        min_confidence: Minimum confidence threshold (0.0-1.0)
        max_results: Maximum number of results to return
        fuzzy: Allow fuzzy matching (case-insensitive, partial matches)
    """
    path = screenshot()
    if not path or not OCR_AVAILABLE:
        return None
    
    img = Image.open(path)
    data = pytesseract.image_to_data(img, output_type=pytesseract.Output.DICT)
    
    matches = []
    for i, word in enumerate(data['text']):
        if not word.strip():
            continue
            
        conf = float(data['conf'][i])
        
        # Apply confidence filter
        if conf < min_confidence * 100:
            continue
        
        # Apply fuzzy matching
        if fuzzy:
            # Case-insensitive comparison
            if text.lower() in word.lower() or word.lower() in text.lower():
                x, y = data['left'][i], data['top'][i]
                w, h = data['width'][i], data['height'][i]
                matches.append({
                    'text': word,
                    'x': x + w//2,
                    'y': y + h//2,
                    'confidence': conf / 100,
                    'bounds': (x, y, w, h)
                })
        else:
            # Exact match
            if text == word:
                x, y = data['left'][i], data['top'][i]
                w, h = data['width'][i], data['height'][i]
                matches.append({
                    'text': word,
                    'x': x + w//2,
                    'y': y + h//2,
                    'confidence': conf / 100,
                    'bounds': (x, y, w, h)
                })
    
    # Deduplicate matches that are very close together
    filtered = []
    for match in matches:
        too_close = False
        for existing in filtered:
            dist = math.sqrt((match['x'] - existing['x'])**2 + 
                           (match['y'] - existing['y'])**2)
            if dist < 50:  # Within 50 pixels
                too_close = True
                break
        if not too_close:
            filtered.append(match)
    
    # Sort by confidence
    filtered.sort(key=lambda m: m['confidence'], reverse=True)
    
    # Limit results
    filtered = filtered[:max_results]
    
    if not filtered:
        print(f"No matches found for '{text}'")
        return None
    
    if show_all:
        print(json.dumps(filtered, indent=2))
        return filtered
    else:
        best = filtered[0]
        print(f"Found '{text}' at ({best['x']}, {best['y']}) - confidence: {int(best['confidence']*100)}%")
        if len(filtered) > 1:
            print(f"  ({len(filtered)-1} other matches found)")
        print(f"To click it: desktop-agent click {best['x']} {best['y']}")
        return best
```

**Usage:**
```bash
# Old way (noisy)
desktop-agent find-text "Download"
# Returns: 13 matches, many false positives

# New way (clean)
desktop-agent find-text "Download" --min-confidence 0.85 --max-results 3
# Returns: 3 high-quality matches

desktop-agent find-text "Download" --fuzzy
# Matches: "download", "Download", "DOWNLOAD"
```

---

### 2. Wait-For Commands

**Problem:** Models use `sleep` guessing instead of waiting for actual conditions

**Solution:** Add explicit wait commands

```python
import time

def wait_for_text(text, timeout=10, interval=0.5):
    """Wait for text to appear on screen"""
    print(f"Waiting for text '{text}' (timeout: {timeout}s)...")
    start = time.time()
    
    while time.time() - start < timeout:
        result = find_text(text, show_all=False, min_confidence=0.75)
        if result:
            print(f"✓ Text found after {int(time.time() - start)}s")
            return result
        time.sleep(interval)
    
    print(f"✗ Timeout: Text '{text}' not found after {timeout}s")
    return None

def wait_for_window(name, timeout=10, interval=0.5):
    """Wait for window to appear"""
    print(f"Waiting for window '{name}' (timeout: {timeout}s)...")
    start = time.time()
    
    while time.time() - start < timeout:
        stdout, _, _ = run_cmd(f'xdotool search --onlyvisible --name "{name}"')
        if stdout:
            print(f"✓ Window found after {int(time.time() - start)}s")
            return stdout.split()[0]  # Return window ID
        time.sleep(interval)
    
    print(f"✗ Timeout: Window '{name}' not found after {timeout}s")
    return None

def wait_for_file(pattern, timeout=30, interval=1.0):
    """Wait for file to appear"""
    print(f"Waiting for file matching '{pattern}' (timeout: {timeout}s)...")
    start = time.time()
    
    while time.time() - start < timeout:
        stdout, _, _ = run_cmd(f"ls {pattern} 2>/dev/null")
        if stdout:
            print(f"✓ File found: {stdout.split()[0]}")
            return stdout.split()[0]
        time.sleep(interval)
    
    print(f"✗ Timeout: File '{pattern}' not found after {timeout}s")
    return None
```

**Usage:**
```bash
# Instead of: sleep 5
desktop-agent wait-for --text "Download complete" --timeout 30

# Instead of: sleep 3 && check window
desktop-agent wait-for --window "Firefox" --timeout 10

# Wait for download
desktop-agent wait-for --file "~/Downloads/code*.deb" --timeout 60
```

---

### 3. Ensure-App Command

**Problem:** Models open apps multiple times or can't find already-running apps

**Solution:** Smart app launcher

```python
def ensure_app(app_name, timeout=10):
    """
    Make sure app is running, start if needed
    
    Returns: (success, window_id, message)
    """
    print(f"Ensuring {app_name} is running...")
    
    # Check if window exists
    stdout, _, _ = run_cmd(f'xdotool search --onlyvisible --name "{app_name}"')
    if stdout:
        window_id = stdout.split()[0]
        # Focus the window
        run_cmd(f'xdotool windowactivate {window_id}')
        print(f"✓ {app_name} already running (focused window {window_id})")
        return True, window_id, "already_running"
    
    # App not running, start it
    print(f"  Starting {app_name}...")
    
    # Use open-app micro-task if available
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("SELECT steps_json FROM tasks WHERE name = 'open-app'")
    row = c.fetchone()
    conn.close()
    
    if row:
        # Use micro-task with parameter
        steps = json.loads(row[0])
        steps = substitute_parameters(steps, {"app_name": app_name})
        for step in steps:
            execute_step(step)
            time.sleep(0.3)
    else:
        # Fallback: manual open
        run_cmd(f"xdotool key Super")
        time.sleep(0.5)
        run_cmd(f'xdotool type "{app_name}"')
        time.sleep(0.3)
        run_cmd(f"xdotool key Return")
    
    # Wait for window to appear
    window_id = wait_for_window(app_name, timeout=timeout)
    if window_id:
        print(f"✓ {app_name} started (window {window_id})")
        return True, window_id, "started"
    else:
        print(f"✗ Failed to start {app_name}")
        return False, None, "failed"
```

**Usage:**
```bash
desktop-agent ensure-app firefox
# Returns: ✓ firefox already running (focused window 12345)

desktop-agent ensure-app "VS Code"
# Returns: ✓ VS Code started (window 67890)
```

---

## 🚀 Medium Priority (Week 2)

### 4. Browse Command (All-in-One Web Navigation)

```python
def browse(url, wait_for_text=None, timeout=10):
    """
    Open URL in browser and optionally wait for content
    
    Args:
        url: URL to navigate to
        wait_for_text: Optional text to wait for after page loads
        timeout: Timeout for page load / text search
    """
    print(f"Browsing to {url}...")
    
    # Ensure browser is running
    success, window_id, _ = ensure_app("Firefox")
    if not success:
        print("✗ Failed to open browser")
        return False
    
    time.sleep(1)
    
    # Focus URL bar
    run_cmd("xdotool key ctrl+l")
    time.sleep(0.5)
    
    # Type URL
    run_cmd(f'xdotool type "{url}"')
    time.sleep(0.3)
    
    # Press Return
    run_cmd("xdotool key Return")
    
    # Wait for page to load
    if wait_for_text:
        result = wait_for_text(wait_for_text, timeout=timeout)
        if result:
            print(f"✓ Page loaded (found '{wait_for_text}')")
            return True
        else:
            print(f"✗ Page load timeout (couldn't find '{wait_for_text}')")
            return False
    else:
        # Generic wait
        time.sleep(3)
        print(f"✓ Navigated to {url}")
        return True
```

**Usage:**
```bash
# Simple navigation
desktop-agent browse "https://code.visualstudio.com/Download"

# With validation
desktop-agent browse "https://code.visualstudio.com/Download" --wait-for ".deb"
```

---

### 5. Smart-Click Command (Multi-Strategy)

```python
def smart_click(target, fallback=None, verify_action=None, timeout=5):
    """
    Try multiple strategies to click a target
    
    Args:
        target: @eN ref, text label, or coordinates "x,y"
        fallback: Fallback text if first attempt fails
        verify_action: Text to look for after clicking (verification)
        timeout: Timeout for verification
    
    Returns: (success, method_used, details)
    """
    print(f"Smart-clicking '{target}'...")
    
    # Strategy 1: Element reference (@eN)
    if target.startswith("@e"):
        try:
            success = click_element(target)
            if success:
                print(f"✓ Clicked {target} (via element ref)")
                if verify_action:
                    return verify_smart_click(verify_action, timeout)
                return True, "element_ref", target
        except Exception as e:
            print(f"  Element ref failed: {e}")
    
    # Strategy 2: Coordinates (x,y)
    if "," in target and target.replace(",", "").replace(" ", "").isdigit():
        x, y = map(int, target.split(","))
        click(x, y)
        print(f"✓ Clicked coordinates ({x}, {y})")
        if verify_action:
            return verify_smart_click(verify_action, timeout)
        return True, "coordinates", f"{x},{y}"
    
    # Strategy 3: Text search (OCR)
    result = find_text(target, min_confidence=0.75, max_results=3)
    if result:
        x, y = result['x'], result['y']
        click(x, y)
        print(f"✓ Clicked text '{target}' at ({x}, {y})")
        if verify_action:
            return verify_smart_click(verify_action, timeout)
        return True, "ocr_text", f"{x},{y}"
    
    # Strategy 4: Fallback text search
    if fallback:
        print(f"  Primary target failed, trying fallback '{fallback}'...")
        result = find_text(fallback, min_confidence=0.70, max_results=3)
        if result:
            x, y = result['x'], result['y']
            click(x, y)
            print(f"✓ Clicked fallback text '{fallback}' at ({x}, {y})")
            if verify_action:
                return verify_smart_click(verify_action, timeout)
            return True, "ocr_fallback", f"{x},{y}"
    
    print(f"✗ All click strategies failed for '{target}'")
    return False, "failed", None

def verify_smart_click(expected_text, timeout=5):
    """Verify an action succeeded by looking for expected result"""
    result = wait_for_text(expected_text, timeout=timeout, interval=0.5)
    if result:
        return True, "verified", expected_text
    else:
        return False, "verification_failed", expected_text
```

**Usage:**
```bash
# Try element ref, fall back to OCR
desktop-agent smart-click @e5

# Try text search with fallback
desktop-agent smart-click "Download .deb" --fallback "deb"

# With verification
desktop-agent smart-click "Login" --verify "Welcome back"
```

---

## 🎨 High Priority (Week 3)

### 6. Task Templates

**Create a template system for common workflows**

```python
TASK_TEMPLATES = {
    "download-file": {
        "steps": [
            {"action": "browse", "args": {"url": "${url}"}},
            {"action": "smart-click", "args": {"target": "${click_text}"}},
            {"action": "wait-for-file", "args": {"pattern": "${verify_file}", "timeout": 60}},
        ],
        "params": ["url", "click_text", "verify_file"],
        "description": "Navigate to URL, click download link, wait for file"
    },
    "send-message": {
        "steps": [
            {"action": "browse", "args": {"url": "${platform_url}", "wait_for_text": "${platform_identifier}"}},
            {"action": "smart-click", "args": {"target": "${search_button}"}},
            {"action": "type", "args": {"text": "${recipient}"}},
            {"action": "wait-for-text", "args": {"text": "${recipient}", "timeout": 5}},
            {"action": "smart-click", "args": {"target": "${recipient}"}},
            {"action": "smart-click", "args": {"target": "${message_input}"}},
            {"action": "type", "args": {"text": "${message}"}},
            {"action": "smart-click", "args": {"target": "${send_button}", "verify_action": "${verify_text}"}},
        ],
        "params": ["platform_url", "platform_identifier", "search_button", "recipient", "message_input", "message", "send_button", "verify_text"],
        "description": "Send message on social platform"
    }
}

def task_from_template(template_name, **kwargs):
    """Execute a task from a template"""
    if template_name not in TASK_TEMPLATES:
        print(f"✗ Template '{template_name}' not found")
        return False
    
    template = TASK_TEMPLATES[template_name]
    print(f"Running template: {template_name}")
    print(f"  {template['description']}")
    
    # Validate parameters
    missing = [p for p in template['params'] if p not in kwargs]
    if missing:
        print(f"✗ Missing required parameters: {', '.join(missing)}")
        return False
    
    # Execute steps
    for i, step in enumerate(template['steps'], 1):
        action = step['action']
        args = step['args'].copy()
        
        # Substitute parameters
        for key, value in args.items():
            if isinstance(value, str) and value.startswith("${") and value.endswith("}"):
                param_name = value[2:-1]
                args[key] = kwargs[param_name]
        
        print(f"  [{i}/{len(template['steps'])}] {action} {args}")
        
        # Execute action
        if action == "browse":
            success = browse(**args)
        elif action == "smart-click":
            success, _, _ = smart_click(**args)
        elif action == "wait-for-file":
            success = wait_for_file(**args)
        elif action == "wait-for-text":
            success = wait_for_text(**args)
        elif action == "type":
            run_cmd(f'xdotool type "{args["text"]}"')
            success = True
        else:
            print(f"✗ Unknown action: {action}")
            return False
        
        if not success:
            print(f"✗ Template failed at step {i}")
            return False
        
        time.sleep(0.5)
    
    print(f"✓ Template completed successfully")
    return True
```

**Usage:**
```bash
# Download VSCode
desktop-agent task-from-template download-file \
  --url "https://code.visualstudio.com/Download" \
  --click-text ".deb" \
  --verify-file "~/Downloads/code*.deb"

# Send Facebook message
desktop-agent task-from-template send-message \
  --platform-url "https://messenger.com" \
  --platform-identifier "Messenger" \
  --search-button "Search" \
  --recipient "Malich Coory" \
  --message-input "Message" \
  --message "Hi" \
  --send-button "Send" \
  --verify-text "Just now"
```

---

## 📊 Testing Plan

### Test with Small Model (MiniMax M2.5 Free)

**Test Case 1: Download VSCode**
```bash
# Old way (failed)
[Long sequence of low-level commands]

# New way (should succeed)
desktop-agent task-from-template download-file \
  --url "https://code.visualstudio.com/Download" \
  --click-text ".deb" \
  --verify-file "~/Downloads/code*.deb"
```

**Expected:** ✓ Success in ~30 seconds with clear validation at each step

**Test Case 2: Send Facebook Message**
```bash
desktop-agent task-from-template send-message \
  --platform-url "https://messenger.com" \
  --platform-identifier "Messenger" \
  --search-button "Search" \
  --recipient "Malich Coory" \
  --message-input "Message" \
  --message "Hi" \
  --send-button "Send" \
  --verify-text "Just now"
```

**Expected:** ✓ Success with authentication check at each step

---

## 🎯 Success Metrics

### Current State (Before Improvements)
- **Small model task completion:** 0/2 (0%)
- **Commands per task:** 20-30 low-level
- **Error recovery:** None
- **Feedback quality:** Poor (guess and hope)

### Target State (After Improvements)
- **Small model task completion:** 7/10 (70%)
- **Commands per task:** 3-5 high-level
- **Error recovery:** Built-in fallbacks
- **Feedback quality:** Clear success/failure at each step

---

## 📝 Implementation Order

1. ✅ **OCR filtering** (1 hour) - Immediate impact on accuracy
2. ✅ **wait-for commands** (2 hours) - Stop using `sleep` guessing
3. ✅ **ensure-app** (1 hour) - Smart app management
4. ✅ **browse command** (2 hours) - High-level web navigation
5. ✅ **smart-click** (3 hours) - Multi-strategy clicking
6. ✅ **task templates** (4 hours) - Common workflows bundled

**Total time:** ~13 hours for complete implementation

---

## 💡 Additional Quick Wins

### A. Dry-Run Flag for All Commands
```bash
desktop-agent smart-click "Download" --dry-run
# Returns: Would click button "Download .deb" at (532, 144)
```

### B. Command Aliases
```bash
# Short aliases for common patterns
desktop-agent goto <url>  # Alias for browse
desktop-agent tap <target>  # Alias for smart-click
desktop-agent wait <condition>  # Alias for wait-for-*
```

### C. Visual Feedback
```bash
desktop-agent snapshot -i --annotate
# Returns screenshot with colored boxes:
# - Green: High-confidence clickable elements
# - Yellow: Medium-confidence
# - Red: Failed matches
```

---

## 🚀 Next Steps

1. **Review this plan** - Confirm priorities
2. **Implement Week 1 (Quick Wins)** - OCR, wait-for, ensure-app
3. **Test with small model** - Validate improvements work
4. **Iterate** - Adjust based on results
5. **Implement Week 2-3** - Browse, smart-click, templates
6. **Full testing** - Complete task suite

**End goal:** Small models can successfully complete 70%+ of desktop automation tasks with high-level commands.
