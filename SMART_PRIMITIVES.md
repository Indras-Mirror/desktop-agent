# Desktop Agent - Smart Primitives (No Extra Layers)

**Philosophy:** Make existing commands intelligent, not add abstraction layers

---

## 🎯 Core Insight

The problem isn't that models are dumb or that primitives are too low-level. The problem is:

1. **Poor feedback** - Commands don't tell you what happened
2. **Noisy data** - OCR returns too much junk
3. **No validation** - Can't easily check if action worked
4. **Unclear state** - Did it succeed? Who knows!

**Solution:** Make the primitives themselves smarter, not add new commands.

---

## 🔧 Improved Primitives

### 1. Smart Click (Keep Same Command, Make It Smarter)

**Current behavior:**
```bash
desktop-agent click 532 144
# Output: Clicked at (532, 144)
# Problem: Did it work? What did it click? No idea!
```

**Improved behavior:**
```bash
# Auto-detect input type
desktop-agent click 532 144
# Output: ✓ Clicked at (532, 144)

desktop-agent click @e5
# Output: ✓ Clicked button "Download" at (532, 144)

desktop-agent click "Download .deb"
# Output: ✓ Found text "Download .deb" at (532, 144), clicked
#         (Also found: ".deb" at (580, 144) with 87% confidence)

# If click fails
desktop-agent click "Missing Button"
# Output: ✗ Text "Missing Button" not found
#         Similar matches:
#         - "Missing" at (400, 200) - 75% confidence
#         - "Button" at (500, 300) - 80% confidence
```

**Implementation changes:**
```python
def click(target, fallback_on_fail=True):
    """
    Smart click - auto-detect if target is:
    - Coordinates (x,y)
    - Element ref (@eN)
    - Text to search for (OCR)
    """
    # Detect type
    if isinstance(target, str) and target.startswith("@e"):
        # Element reference
        return click_element(target)
    
    elif isinstance(target, str) and "," in target:
        # Coordinates
        x, y = map(int, target.split(","))
        run_cmd(f"xdotool mousemove {x} {y} click 1")
        print(f"✓ Clicked at ({x}, {y})")
        return True
    
    elif isinstance(target, str):
        # Text search via OCR
        result = find_text(target, min_confidence=0.75, max_results=3)
        if result:
            x, y = result['x'], result['y']
            run_cmd(f"xdotool mousemove {x} {y} click 1")
            print(f"✓ Found text '{target}' at ({x}, {y}), clicked")
            
            # Show alternatives if multiple matches
            if len(result.get('alternatives', [])) > 0:
                print(f"  (Also found {len(result['alternatives'])} other matches)")
            return True
        else:
            print(f"✗ Text '{target}' not found")
            if fallback_on_fail:
                # Show what WAS found nearby
                print("  Trying partial matches...")
                partial = find_text(target, fuzzy=True, min_confidence=0.60)
                if partial:
                    print(f"  Found partial match: '{partial['text']}' at ({partial['x']}, {partial['y']})")
            return False
    
    # If we get here, invalid input
    print(f"✗ Invalid click target: {target}")
    return False
```

**Usage stays simple:**
```bash
# All of these work with ONE command
desktop-agent click 532 144
desktop-agent click @e5
desktop-agent click "Download"
```

---

### 2. Better OCR (Clean Output by Default)

**Current behavior:**
```bash
desktop-agent find-text "Download"
# Returns: 13 matches, lots of noise, hard to parse
```

**Improved behavior:**
```bash
desktop-agent find-text "Download"
# Default: Clean, top 3 matches only
# Output:
# ✓ Found "Download" (3 matches):
#   [1] "Download .deb" at (532, 144) - 96% confidence
#   [2] "Download" at (620, 144) - 92% confidence  
#   [3] "download" at (450, 200) - 85% confidence
#
# To click: desktop-agent click "Download"

# If you want ALL matches
desktop-agent find-text "Download" --all
# Returns: JSON with all 13 matches
```

**Changes:**
```python
def find_text(text, show_all=False, min_confidence=0.75, max_results=3):
    """
    IMPROVED: Filter by default, cleaner output
    """
    # ... OCR code ...
    
    # ALWAYS filter by min_confidence (default 0.75)
    matches = [m for m in matches if m['confidence'] >= min_confidence]
    
    # ALWAYS deduplicate nearby matches
    matches = deduplicate_by_proximity(matches, threshold=50)
    
    # ALWAYS sort by confidence
    matches.sort(key=lambda m: m['confidence'], reverse=True)
    
    # Limit results by default
    if not show_all:
        matches = matches[:max_results]
    
    # Clean output
    if not matches:
        print(f"✗ No matches found for '{text}' (tried min confidence {min_confidence})")
        print(f"  Try: desktop-agent find-text '{text}' --min-confidence 0.6")
        return None
    
    if show_all:
        print(json.dumps(matches, indent=2))
        return matches
    else:
        print(f"✓ Found '{text}' ({len(matches)} matches):")
        for i, match in enumerate(matches, 1):
            print(f"  [{i}] \"{match['text']}\" at ({match['x']}, {match['y']}) - {int(match['confidence']*100)}% confidence")
        print(f"\nTo click: desktop-agent click \"{text}\"")
        return matches[0]
```

**No new flags needed - smart defaults!**

---

### 3. Self-Validating Commands

**Add optional validation to existing commands:**

```bash
# Click with automatic validation
desktop-agent click "Login" --verify "Welcome"
# Output: ✓ Clicked "Login" at (500, 300)
#         ✓ Verified: Found "Welcome" after 0.8s

# Type with verification
desktop-agent type "search query" --verify "results"
# Output: ✓ Typed "search query"
#         ✓ Verified: Found "results" after 1.2s

# If verification fails
desktop-agent click "Login" --verify "Welcome"
# Output: ✓ Clicked "Login" at (500, 300)
#         ✗ Verification failed: "Welcome" not found after 5s
```

**Implementation:**
```python
def click(target, verify=None, verify_timeout=5):
    """Click with optional verification"""
    success = do_click(target)
    
    if success and verify:
        # Wait for expected result
        print(f"  Waiting for '{verify}'...")
        result = wait_for_text(verify, timeout=verify_timeout, silent=True)
        if result:
            print(f"  ✓ Verified: Found '{verify}' after {result['time']}s")
        else:
            print(f"  ✗ Verification failed: '{verify}' not found after {verify_timeout}s")
            return False
    
    return success
```

---

### 4. Wait Commands (Add to Existing Set)

**Just add 3 simple wait commands:**

```bash
desktop-agent wait-for-text "Download complete"
# Output: Waiting for "Download complete"...
#         ✓ Found after 3.2s

desktop-agent wait-for-window "Firefox"
# Output: Waiting for window "Firefox"...
#         ✓ Window appeared after 1.5s

desktop-agent wait-for-file "~/Downloads/*.deb"
# Output: Waiting for file matching ~/Downloads/*.deb...
#         ✓ Found: code_1.116.0.deb (44MB)
```

**These are just new primitives, not abstraction layers.**

---

### 5. Better Snapshot Output

**Current behavior:**
```bash
desktop-agent snapshot -i
# Returns: Huge list of elements, hard to parse
```

**Improved behavior:**
```bash
desktop-agent snapshot -i
# Output:
# ✓ Found 23 interactive elements:
#
# Buttons (8):
#   @e1  "Download" at (532, 144)
#   @e2  "Cancel" at (620, 144)
#   @e3  "Help" at (450, 50)
#   ...
#
# Text Inputs (3):
#   @e9  "Search" at (300, 50)
#   @e10 "Username" at (400, 200)
#   ...
#
# Links (12):
#   @e15 "Documentation" at (100, 100)
#   ...
#
# To click: desktop-agent click @e1

# For full JSON output
desktop-agent snapshot -i --json
```

**Group by type, cleaner presentation, still all the data.**

---

## 🎯 Key Improvements to Existing Commands

### `click` command
- ✅ Auto-detect input type (coords, @e, text)
- ✅ Try OCR fallback automatically
- ✅ Show what was clicked
- ✅ Optional `--verify` flag

### `find-text` command
- ✅ Smart defaults (min-confidence 0.75, max 3 results)
- ✅ Auto-deduplicate nearby matches
- ✅ Cleaner output by default
- ✅ Suggest alternatives if nothing found

### `snapshot` command
- ✅ Group elements by type
- ✅ Cleaner presentation
- ✅ Still show full data with --json

### Add 3 new primitives (not abstractions)
- ✅ `wait-for-text`
- ✅ `wait-for-window`
- ✅ `wait-for-file`

---

## 📊 Example: VSCode Download (Before vs After)

### Before (Complex, Poor Feedback)
```bash
desktop-agent key Super
desktop-agent type "firefox"
desktop-agent key Return
sleep 4  # Guess
desktop-agent key Ctrl+l
desktop-agent type "code.visualstudio.com"
desktop-agent key Return
sleep 5  # Guess
desktop-agent find-text ".deb"
# Returns: 13 noisy matches
desktop-agent click 532 144  # Might work?
# No feedback if it worked!
sleep 8  # Guess
ls ~/Downloads/  # Manual check
```

### After (Simple, Clear Feedback)
```bash
# Smart click opens app if needed
desktop-agent click "Firefox" --verify "Mozilla"
# ✓ Window "Firefox" found, focused
# ✓ Verified: Found "Mozilla" after 0.2s

# Type in URL bar (Ctrl+l automatic if text doesn't match)
desktop-agent type "code.visualstudio.com"
desktop-agent key Return

# Wait for page load (not sleep guessing)
desktop-agent wait-for-text ".deb"
# ✓ Found ".deb" after 2.3s

# Smart click auto-finds via OCR
desktop-agent click ".deb" --verify "download"
# ✓ Found text ".deb" at (532, 144), clicked
# ✓ Verified: Found "download" after 0.8s

# Wait for actual file (not sleep guessing)
desktop-agent wait-for-file "~/Downloads/code*.deb"
# ✓ Found: code_1.116.0.deb (44MB)
```

**Same primitives, just smarter!**

---

## 🔧 Implementation Changes

### 1. Update `click()` function
```python
def click(target, verify=None, verify_timeout=5, fallback=True):
    """Smart click with auto-detection and verification"""
    # Auto-detect target type and click
    # Add verification if requested
    # Return clear success/failure
```

### 2. Update `find_text()` function
```python
def find_text(text, show_all=False, min_confidence=0.75, max_results=3):
    """Better defaults, cleaner output"""
    # Filter by confidence by default
    # Deduplicate by default
    # Clean output format
    # Suggest alternatives on failure
```

### 3. Add wait functions
```python
def wait_for_text(text, timeout=10):
    """Wait for text to appear"""

def wait_for_window(name, timeout=10):
    """Wait for window to appear"""

def wait_for_file(pattern, timeout=30):
    """Wait for file to exist"""
```

### 4. Update `snapshot()` output
```python
def snapshot(interactive=False, json_output=False):
    """Better formatting of element list"""
    if interactive and not json_output:
        # Group by element type
        # Show counts
        # Cleaner presentation
```

---

## 💡 Philosophy

**Don't add layers, improve the primitives:**

❌ **Bad:** Create `browse`, `smart-click`, `task-from-template` wrapper commands
✅ **Good:** Make `click`, `find-text`, `type` smarter and self-validating

❌ **Bad:** Hide complexity behind abstractions
✅ **Good:** Make complexity manageable with better feedback

❌ **Bad:** Create new DSL/template system
✅ **Good:** Make existing commands intelligent enough to do the job

---

## 🎯 Benefits

### For Small Models
- **Less guessing** - Clear feedback at each step
- **Better data** - Clean OCR results by default
- **Self-validating** - `--verify` flag checks if action worked
- **Smarter primitives** - Commands do more with less input

### For Users
- **Same commands** - No new syntax to learn
- **Better feedback** - Always know what happened
- **Flexible** - Can still use low-level when needed
- **Backward compatible** - Old scripts still work

### For Code
- **Less abstraction** - No extra wrapper layer
- **Simpler** - Improve existing functions, don't add new ones
- **Maintainable** - One set of commands, not two

---

## 📋 Implementation Checklist

**Phase 1: Better Feedback (2 hours)**
- [ ] Update `click()` to auto-detect target type
- [ ] Update `click()` to show what was clicked
- [ ] Update `find_text()` with better defaults
- [ ] Update `find_text()` output format

**Phase 2: Validation (2 hours)**
- [ ] Add `--verify` flag to `click()`
- [ ] Add `--verify` flag to `type()`
- [ ] Add wait functions (3 new commands)

**Phase 3: Better Output (1 hour)**
- [ ] Update `snapshot()` formatting
- [ ] Add element grouping
- [ ] Add helpful suggestions on failures

**Total: ~5 hours to significantly improve UX without adding complexity**

---

## 🚀 Result

**Same simple commands, much smarter behavior:**

```bash
# Before: Complex, uncertain
desktop-agent key Super
desktop-agent type "firefox"
sleep 4
desktop-agent key Ctrl+l
...

# After: Simple, confident
desktop-agent click "Firefox" --verify "Mozilla"
desktop-agent type "code.visualstudio.com"
desktop-agent key Return
desktop-agent wait-for-text ".deb"
desktop-agent click ".deb" --verify "download"
desktop-agent wait-for-file "~/Downloads/code*.deb"
```

**No extra abstraction layer needed - just smarter primitives!**
