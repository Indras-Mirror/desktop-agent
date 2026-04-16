# Desktop Agent Task-Caching System Analysis & Improvements

**Date:** 2026-04-16  
**Current Status:** 14 tasks in repository, basic recording/replay working

---

## Current System Overview

### Strengths
- ✅ **Semantic search** - nomic-embed-text for intelligent task matching
- ✅ **Persistent recording** - survives CLI restarts via recording.json
- ✅ **Use tracking** - counts + timestamps for popularity ranking
- ✅ **AT-SPI integration** - element detection for reliable clicking
- ✅ **OCR support** - text finding as fallback
- ✅ **Simple replay** - reliable step-by-step execution

### Current Gaps
- ❌ **No task composition** - can't chain tasks together
- ❌ **No conditionals** - no if/else or retry logic
- ❌ **No parameters** - tasks are hardcoded, not reusable
- ❌ **No state validation** - doesn't check if steps worked
- ❌ **Limited pattern extraction** - misses common sub-sequences
- ❌ **No adaptive behavior** - can't adjust to screen changes
- ❌ **No failure recovery** - stops on first error
- ❌ **No multi-app workflows** - each task is single-app focused

---

## Improvement Proposals

### 1. **Task Composition System** (High Priority)

Allow tasks to reference other tasks as sub-steps.

**Schema Addition:**
```sql
ALTER TABLE tasks ADD COLUMN subtasks TEXT; -- JSON array of task names
ALTER TABLE tasks ADD COLUMN composition_type TEXT; -- 'sequential', 'parallel', 'conditional'
```

**Example Composed Task:**
```json
{
  "name": "research-and-document",
  "composition_type": "sequential",
  "subtasks": ["web-search-linux-automation", "research-web-take-notes"],
  "description": "Search web and take notes in one workflow"
}
```

**Benefits:**
- Reuse existing tasks as building blocks
- Create complex workflows without re-recording
- Easier maintenance (update subtask once, affects all composed tasks)

---

### 2. **Parameter/Variable Support** (High Priority)

Make tasks reusable with different inputs.

**Schema Addition:**
```sql
ALTER TABLE tasks ADD COLUMN parameters TEXT; -- JSON: [{"name": "search_query", "type": "string", "default": ""}]
ALTER TABLE tasks ADD COLUMN variable_bindings TEXT; -- JSON: {"${query}": "search_query"}
```

**Example Parameterized Task:**
```json
{
  "name": "web-search-generic",
  "parameters": [
    {"name": "query", "type": "string", "required": true},
    {"name": "open_first", "type": "boolean", "default": true}
  ],
  "steps": [
    {"command": "focus", "args": ["Firefox"]},
    {"command": "key", "args": ["Ctrl+l"]},
    {"command": "type", "args": ["${query}"]},
    {"command": "key", "args": ["Return"]}
  ]
}
```

**Usage:**
```bash
desktop-agent replay "search the web" --param query="linux automation"
```

**Benefits:**
- One task → many use cases
- Reduces repository size
- More natural language interaction

---

### 3. **Conditional Logic & State Validation** (Medium Priority)

Add ability to check conditions and branch execution.

**New Step Types:**
```json
{
  "command": "check_window_exists",
  "args": ["Firefox"],
  "on_success": "continue",
  "on_failure": "open-firefox-task"
},
{
  "command": "wait_for_text",
  "args": ["Search results"],
  "timeout": 5000,
  "on_timeout": "retry_search"
}
```

**Schema Addition:**
```sql
ALTER TABLE tasks ADD COLUMN validation_steps TEXT; -- JSON array of validation commands
ALTER TABLE tasks ADD COLUMN retry_config TEXT; -- JSON: {"max_retries": 3, "backoff": "exponential"}
```

**Benefits:**
- Self-healing tasks that adapt to state
- Better success rates
- Meaningful failure tracking

---

### 4. **Pattern Extraction & Micro-Tasks** (Medium Priority)

Automatically detect common sub-sequences across tasks.

**Implementation:**
- Analyze all tasks for repeated step sequences
- Extract as micro-tasks (e.g., "open-activities-menu", "focus-and-type")
- Suggest replacements in existing tasks

**Example Patterns to Extract:**
```
Pattern: "open-activities-menu"
  Super → type app_name → Return
  
Pattern: "focus-url-bar"
  Ctrl+l
  
Pattern: "save-file"
  Ctrl+s → type filename → Return
  
Pattern: "switch-to-last-window"
  Alt+Tab
```

**Benefits:**
- Reduces duplication
- Improves semantic search (more granular matching)
- Easier debugging (test micro-tasks independently)

---

### 5. **Adaptive Task Execution** (Low Priority, High Value)

Tasks that use OCR/AT-SPI to verify state before each step.

**Example:**
```json
{
  "command": "click_button",
  "args": ["Submit"],
  "strategy": "adaptive",
  "fallback_methods": [
    "find_by_atspi_label:Submit",
    "find_by_ocr_text:Submit",
    "click_coordinates:500,300"
  ]
}
```

**Benefits:**
- Works across different window sizes/themes
- More robust to UI changes
- Reduces brittleness

---

### 6. **Multi-App Orchestration Tasks** (Medium Priority)

Complex workflows that span multiple applications.

**New Commands:**
```json
{
  "command": "ensure_app_open",
  "args": ["Firefox", "Gedit", "Terminal"]
},
{
  "command": "arrange_windows",
  "args": ["tile_horizontal"]
}
```

**Example Task:**
```json
{
  "name": "development-setup",
  "description": "Open VS Code, terminal, browser in tiled layout",
  "apps": ["code", "terminal", "firefox"],
  "layout": "tile_3_columns"
}
```

---

### 7. **Success Validation & Feedback Loop** (High Priority)

Track what actually worked vs what was attempted.

**Schema Already Exists:** `task_runs` table (currently unused)

**Activate It:**
```python
def execute_task_with_validation(task_id, steps):
    success = True
    failures = []
    
    for i, step in enumerate(steps):
        try:
            execute_step(step)
            # Validation check
            if not validate_step_success(step):
                success = False
                failures.append(f"Step {i}: validation failed")
        except Exception as e:
            success = False
            failures.append(f"Step {i}: {e}")
    
    # Record to task_runs
    record_task_run(task_id, success, json.dumps(failures))
    
    # Update success_rate
    update_task_success_rate(task_id)
```

**Benefits:**
- Know which tasks are reliable
- Prioritize high-success tasks in search results
- Auto-deprecate broken tasks

---

### 8. **Clipboard Intelligence** (Low Priority)

Smarter clipboard operations with history.

**New Features:**
- Clipboard history (last 10 items)
- Named clipboard slots
- Clipboard content validation

**Example:**
```bash
desktop-agent clipboard save "search_results"
desktop-agent clipboard paste "search_results"
```

---

## Repository Expansion: Complex Tasks to Add

### Category 1: System Inspection & Navigation

**Missing foundational tasks:**

1. **check-running-apps**
   - List all running applications
   - Purpose: Dependency check for other tasks
   - Pattern: Window enumeration → filter by app name

2. **check-clipboard-content**
   - Get current clipboard content
   - Purpose: Conditional workflows based on clipboard
   - Pattern: xclip -o → return content

3. **check-internet-connection**
   - Verify internet connectivity
   - Purpose: Pre-validate web-dependent tasks
   - Pattern: ping 8.8.8.8 → check response

4. **get-current-workspace**
   - Identify which virtual desktop you're on
   - Purpose: Workspace-aware task routing
   - Pattern: wmctrl -d → parse current

5. **enumerate-windows-by-app**
   - List all windows for a specific app (e.g., all Firefox windows)
   - Purpose: Multi-window workflows
   - Pattern: xdotool search --class Firefox → list

---

### Category 2: File Operations

6. **create-directory-structure**
   - Create nested directories (e.g., project scaffolding)
   - Purpose: Project setup automation
   - Pattern: Terminal → mkdir -p path/to/dirs

7. **find-file-by-name**
   - Search filesystem for file
   - Purpose: Locate files before operating on them
   - Pattern: Terminal → find ~ -name "filename"

8. **move-file-to-backup**
   - Copy file to timestamped backup location
   - Purpose: Safe file operations
   - Pattern: Terminal → cp file ~/backups/file_$(date +%s)

9. **bulk-rename-files**
   - Rename multiple files with pattern
   - Purpose: Batch file management
   - Pattern: File manager select → F2 → rename pattern

10. **compress-folder**
    - Create tar.gz of directory
    - Purpose: Archival workflows
    - Pattern: Terminal → tar -czf archive.tar.gz folder/

---

### Category 3: Development Workflows

11. **git-commit-workflow**
    - Stage changes → commit → push
    - Purpose: Common git operation
    - Pattern: Terminal → git add . → git commit -m "msg" → git push

12. **run-tests-and-report**
    - Execute test suite → capture output → save to file
    - Purpose: Testing workflows
    - Pattern: Terminal → npm test > test-results.txt

13. **start-dev-server**
    - Start local development server (npm, python, etc.)
    - Purpose: Begin coding session
    - Pattern: Terminal → cd project → npm start

14. **search-code-in-editor**
    - Open VS Code → search for pattern across files
    - Purpose: Code navigation
    - Pattern: Focus VS Code → Ctrl+Shift+F → type pattern

15. **format-code-file**
    - Run code formatter on current file
    - Purpose: Code cleanup
    - Pattern: VS Code → Shift+Alt+F

---

### Category 4: Communication & Documentation

16. **extract-text-to-file**
    - Select all → copy → create new file → paste → save
    - Purpose: Text extraction workflows
    - Pattern: Ctrl+a → Ctrl+c → open gedit → Ctrl+v → Ctrl+s

17. **append-clipboard-to-notes**
    - Append clipboard content to a running notes file
    - Purpose: Research collection
    - Pattern: Open notes.txt → Ctrl+End → Ctrl+v → Ctrl+s

18. **create-markdown-doc**
    - Create new markdown file with template
    - Purpose: Documentation workflows
    - Pattern: Terminal → echo "# Title\n\n" > doc.md → open gedit doc.md

19. **extract-urls-from-page**
    - Use OCR to find URLs on screen → copy to file
    - Purpose: Link collection
    - Pattern: OCR scan → regex match URLs → save

---

### Category 5: Media & Content

20. **download-video-from-clipboard**
    - Get URL from clipboard → use yt-dlp to download
    - Purpose: Media archival
    - Pattern: xclip -o → yt-dlp $(xclip -o)

21. **convert-image-format**
    - Convert image from one format to another
    - Purpose: Image processing
    - Pattern: Terminal → convert input.png output.jpg

22. **resize-image**
    - Resize image to specific dimensions
    - Purpose: Image optimization
    - Pattern: Terminal → convert input.jpg -resize 800x600 output.jpg

23. **batch-screenshot-sequence**
    - Take screenshots every N seconds for duration
    - Purpose: Process documentation
    - Pattern: Loop → scrot → sleep N

---

### Category 6: Multi-App Workflows

24. **email-current-screenshot**
    - Screenshot → open email → attach → send
    - Purpose: Quick sharing
    - Pattern: scrot → open Thunderbird → Ctrl+Shift+A → attach → send

25. **code-test-debug-cycle**
    - Edit code → save → run tests → view output → repeat
    - Purpose: Development iteration
    - Pattern: VS Code focus → edit → Ctrl+s → Alt+Tab to terminal → npm test

26. **web-to-document**
    - Search web → extract text → format in document
    - Purpose: Research to documentation
    - Pattern: Firefox search → select content → copy → gedit → paste → format

27. **compare-two-files**
    - Open two files side-by-side in diff tool
    - Purpose: File comparison
    - Pattern: Terminal → meld file1 file2

28. **monitor-log-file**
    - Tail log file in terminal while working
    - Purpose: Debugging workflows
    - Pattern: Open terminal → tail -f /var/log/app.log

---

### Category 7: System Administration

29. **check-disk-space**
    - View disk usage by directory
    - Purpose: System maintenance
    - Pattern: Terminal → df -h; du -sh */

30. **check-system-resources**
    - Open system monitor → view CPU/RAM/Network
    - Purpose: Performance monitoring
    - Pattern: Open System Monitor → navigate to Resources tab

31. **kill-frozen-app**
    - Identify PID → kill process
    - Purpose: Recover from hang
    - Pattern: xkill → click window OR ps aux | grep app → kill PID

32. **restart-service**
    - Restart systemd service
    - Purpose: Service management
    - Pattern: Terminal → sudo systemctl restart service_name

33. **check-network-ports**
    - List open network ports
    - Purpose: Network debugging
    - Pattern: Terminal → sudo netstat -tulpn | grep LISTEN

---

### Category 8: Smart Composition Examples

34. **full-research-workflow**
    - Composition of: web-search → extract-text-to-file → append-clipboard-to-notes
    - Purpose: End-to-end research
    - Adaptive: Changes based on content found

35. **backup-and-edit**
    - Composition of: move-file-to-backup → open file in editor
    - Purpose: Safe editing
    - Validation: Ensure backup exists before editing

36. **test-and-commit**
    - Composition of: run-tests-and-report → (if success) git-commit-workflow
    - Purpose: Safe commits
    - Conditional: Only commit if tests pass

37. **setup-workspace**
    - Composition of: switch-workspace → open-code-system-monitor → start-dev-server
    - Purpose: Full workspace initialization
    - Multi-app: Coordinates 3+ applications

38. **meeting-prep**
    - Composition of: open calendar → screenshot schedule → create-markdown-doc with agenda
    - Purpose: Automate meeting prep
    - Smart: Extracts calendar items via OCR

---

## Implementation Priority

### Phase 1: Foundation (Week 1)
1. ✅ Parameter support (make tasks reusable)
2. ✅ Activate task_runs tracking (learn from failures)
3. ✅ Add 10 foundational tasks (Categories 1-2)

### Phase 2: Intelligence (Week 2)
4. ✅ Pattern extraction (find micro-tasks)
5. ✅ Conditional logic (if/else, retry)
6. ✅ Add 10 complex tasks (Categories 3-4)

### Phase 3: Composition (Week 3)
7. ✅ Task composition system
8. ✅ Adaptive execution (OCR/AT-SPI validation)
9. ✅ Add 10 composed tasks (Categories 5-6)

### Phase 4: Advanced (Week 4)
10. ✅ Multi-app orchestration
11. ✅ Clipboard intelligence
12. ✅ Add remaining specialized tasks (Categories 7-8)

---

## Technical Implementation Notes

### New Commands to Add

```python
# Conditional execution
elif cmd == "check":
    condition_type, condition_value = args[0], args[1]
    result = evaluate_condition(condition_type, condition_value)
    record_step("check", args, f"Check: {condition_type}={condition_value} → {result}")

# Variable substitution
def substitute_variables(step, params):
    for key, value in params.items():
        step["args"] = [arg.replace(f"${{{key}}}", value) for arg in step["args"]]
    return step

# Task composition
def execute_composed_task(task_name, params=None):
    task = get_task_by_name(task_name)
    if task["subtasks"]:
        for subtask_name in task["subtasks"]:
            execute_task(subtask_name, params)
    else:
        execute_task_steps(task["steps"], params)
```

### Enhanced Semantic Search

Weight different fields differently:
```python
embed_text = f"{name} {name} {description}. {purpose} {context}"
# Name gets 2x weight, description 1x, purpose/context 1x
```

Add category-based filtering:
```python
desktop-agent tasks search "file operations" --category development
```

---

## Success Metrics

After implementing these improvements, measure:

1. **Repository Coverage** - % of common workflows automated
2. **Task Reuse** - How often tasks use composition vs being standalone
3. **Success Rate** - % of task replays that complete without errors
4. **Search Accuracy** - Does semantic search find the right task? (user feedback)
5. **Adaptation Time** - How quickly can we add new complex workflows?

**Target Metrics (3 months):**
- 50+ tasks in repository
- 80%+ success rate on replays
- 90%+ search accuracy
- 5 min to record new complex workflow

---

## Conclusion

The current task-caching system is a solid foundation. The biggest wins will come from:

1. **Parameters** - 10x reusability
2. **Composition** - Build complex from simple
3. **Validation** - Learn from failures
4. **Smart repository** - 38+ curated tasks covering common workflows

This transforms desktop-agent from a "record what you did" tool to a **learned repository of Linux desktop knowledge** that helps AI agents complete tasks faster and more reliably.
