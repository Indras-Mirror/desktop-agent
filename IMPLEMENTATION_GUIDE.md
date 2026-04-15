# Desktop Agent - Implementation Guide for Task-Caching Improvements

**Priority Implementation Order for Maximum Impact**

---

## Phase 1: Quick Wins (Implement This Week)

### 1A. Add Parameter Support to Tasks

**File:** `/home/mal/.local/bin/desktop-agent.py`

**Changes needed:**

```python
# Update save_task function (around line 156)
def save_task(name, description="", purpose="", context="", app_context="", parameters=None):
    """
    parameters: List of dicts like [{"name": "query", "type": "string", "default": ""}]
    """
    steps = stop_recording()
    if not steps:
        print("No steps recorded.")
        return False

    steps_json = json.dumps(steps)
    params_json = json.dumps(parameters) if parameters else None
    embed_text = f"{name}. {description}. {purpose}"
    embedding = get_embedding(embed_text)

    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    
    # Add parameters column if not exists
    try:
        c.execute("ALTER TABLE tasks ADD COLUMN parameters TEXT")
        conn.commit()
    except sqlite3.OperationalError:
        pass  # Column already exists
    
    try:
        c.execute(
            """
            INSERT INTO tasks (name, description, purpose, context, app_context, steps_json, parameters, embedding)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """,
            (name, description, purpose, context, app_context, steps_json, params_json, 
             json.dumps(embedding) if embedding else None),
        )
        conn.commit()
        print(f"Task saved: {name}")
        if parameters:
            print(f"  Parameters: {', '.join([p['name'] for p in parameters])}")
        return True
    except sqlite3.IntegrityError:
        print(f"Task '{name}' already exists.")
        return False
    finally:
        conn.close()


# Add parameter substitution function
def substitute_parameters(steps, param_values):
    """
    Replace ${var_name} in step args with actual values
    
    steps: List of step dicts
    param_values: Dict like {"query": "linux automation", "count": "5"}
    """
    substituted = []
    for step in steps:
        new_step = step.copy()
        new_args = []
        for arg in step["args"]:
            if isinstance(arg, str):
                # Replace all ${var} patterns
                for var_name, var_value in param_values.items():
                    arg = arg.replace(f"${{{var_name}}}", str(var_value))
            new_args.append(arg)
        new_step["args"] = new_args
        substituted.append(new_step)
    return substituted


# Update replay_task to accept parameters (around line 251)
def replay_task(query, param_values=None, dry_run=True):
    """
    param_values: Dict of parameter values like {"query": "test", "count": 5}
    """
    # ... existing code to find task ...
    
    steps = json.loads(steps_json)
    
    # Apply parameter substitution if provided
    if param_values:
        steps = substitute_parameters(steps, param_values)
    
    # Show steps
    print(f"\nTask steps ({len(steps)}):")
    for i, step in enumerate(steps, 1):
        print(f"  {i}. {step['description']}")
    
    if dry_run:
        print("\n(Dry run - use 'replay --run' to execute)")
        return steps
    
    # Execute steps
    print("\nExecuting task...")
    for i, step in enumerate(steps, 1):
        print(f"[{i}/{len(steps)}] {step['description']}")
        execute_step(step)
        time.sleep(0.5)  # Delay between steps
    
    # ... rest of existing code ...
```

**CLI Usage:**
```bash
# Save task with parameters
desktop-agent save-task web-search-generic \
  --description "Search web for any query" \
  --purpose "Generic web search" \
  --params '[{"name": "query", "type": "string"}]'

# Use task with parameters
desktop-agent replay --run "search web" --param query="linux automation"
```

---

### 1B. Activate Task Success Tracking

**Already have `task_runs` table - just need to USE it!**

```python
# Add this function
def record_task_execution(task_id, success, error_details=None):
    """Record task execution result"""
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("""
        INSERT INTO task_runs (task_id, success, notes)
        VALUES (?, ?, ?)
    """, (task_id, 1 if success else 0, error_details or ""))
    conn.commit()
    
    # Update success rate
    c.execute("""
        SELECT COUNT(*), SUM(success) FROM task_runs WHERE task_id = ?
    """, (task_id,))
    total, successes = c.fetchone()
    
    if total > 0:
        success_rate = successes / total
        c.execute("""
            UPDATE tasks SET success_rate = ? WHERE id = ?
        """, (success_rate, task_id))
        conn.commit()
    
    conn.close()
    return success_rate if total > 0 else 1.0


# Update replay_task to wrap execution in try/catch
def replay_task(query, param_values=None, dry_run=True):
    # ... find task code ...
    
    if not dry_run:
        print("\nExecuting task...")
        success = True
        error_msg = None
        
        try:
            for i, step in enumerate(steps, 1):
                print(f"[{i}/{len(steps)}] {step['description']}")
                execute_step(step)
                time.sleep(0.5)
            print("✓ Task completed successfully")
        except Exception as e:
            success = False
            error_msg = str(e)
            print(f"✗ Task failed at step {i}: {e}")
        
        # Record execution
        if task_id:
            new_rate = record_task_execution(task_id, success, error_msg)
            print(f"  Success rate: {int(new_rate * 100)}% ({successes}/{total} runs)")
    
    return steps


# Add function to execute a single step
def execute_step(step):
    """Execute a single recorded step"""
    cmd = step["command"]
    args = step["args"]
    
    if cmd == "focus":
        focus_window(args[0])
    elif cmd == "click":
        if args[0].startswith("@"):
            click_element(args[0])
        else:
            click(int(args[0]), int(args[1]))
    elif cmd == "type":
        type_text(args[0])
    elif cmd == "key":
        press_key(args[0])
    elif cmd == "screenshot":
        screenshot(args[0] if args else None)
    elif cmd == "region":
        region_screenshot(*[int(a) for a in args])
    else:
        raise ValueError(f"Unknown command: {cmd}")
```

**Benefits:**
- See which tasks actually work
- Sort by success rate in search results
- Auto-deprecate broken tasks

---

### 1C. Enhanced Task Search (Weight by Success Rate)

```python
def search_tasks(query, limit=5, min_success_rate=0.0):
    """Search tasks with success rate weighting"""
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("""
        SELECT name, description, purpose, steps_json, success_rate, use_count 
        FROM tasks 
        WHERE success_rate >= ?
    """, (min_success_rate,))
    rows = c.fetchall()
    conn.close()

    if not rows:
        print("No tasks to search.")
        return

    query_emb = get_embedding(query)
    if not query_emb:
        print("Search failed - could not embed query.")
        return

    results = []
    for name, desc, purpose, steps_json, success_rate, use_count in rows:
        if not desc:
            desc = ""
        stored_emb = get_embedding(f"{name}. {desc}. {purpose or ''}")
        if stored_emb:
            sim = cosine_similarity(query_emb, stored_emb)
            
            # Boost by success rate and use count
            weighted_score = sim * (0.7 + 0.2 * success_rate + 0.1 * min(use_count / 10, 1.0))
            
            results.append((weighted_score, sim, name, desc, purpose, success_rate, use_count))

    results.sort(reverse=True)

    print(f"\nSearch results for '{query}':")
    for score, sim, name, desc, purpose, success_rate, use_count in results[:limit]:
        confidence = "✓" if success_rate >= 0.8 else "?" if success_rate >= 0.5 else "✗"
        print(f"  {confidence} [{int(sim * 100)}%] {name} (success: {int(success_rate * 100)}%, used {use_count}x)")
        if desc:
            print(f"    {desc}")
```

---

## Phase 2: High-Value Repository Tasks

### Ready-to-Record Tasks

**Category: System Inspection**

```bash
# Task 1: check-running-apps
desktop-agent record
desktop-agent key Super
desktop-agent type "system monitor"
desktop-agent key Return
# Wait for System Monitor to open
desktop-agent save-task check-running-apps \
  --description "Open System Monitor to view running applications" \
  --purpose "Verify which applications are currently running" \
  --context "Before launching apps or debugging issues"

# Task 2: check-clipboard-content  
desktop-agent record
desktop-agent key Super
desktop-agent type "terminal"
desktop-agent key Return
desktop-agent type "xclip -o"
desktop-agent key Return
desktop-agent save-task check-clipboard-content \
  --description "Display current clipboard content in terminal" \
  --purpose "Verify clipboard before paste operations" \
  --context "Before pasting into important documents"
```

**Category: File Operations**

```bash
# Task 3: create-directory-structure
desktop-agent record
desktop-agent key Super
desktop-agent type "terminal"
desktop-agent key Return
desktop-agent type "mkdir -p ~/Projects/new-project/{src,docs,tests}"
desktop-agent key Return
desktop-agent type "ls -la ~/Projects/new-project/"
desktop-agent key Return
desktop-agent save-task create-directory-structure \
  --description "Create project directory structure with subdirectories" \
  --purpose "Scaffold new project with standard folders" \
  --context "Starting new development projects"

# Task 4: find-file-by-name
desktop-agent record
desktop-agent key Super
desktop-agent type "terminal"
desktop-agent key Return
desktop-agent type "find ~ -name '*.py' -type f | head -20"
desktop-agent key Return
desktop-agent save-task find-file-by-name \
  --description "Search filesystem for files matching pattern" \
  --purpose "Locate files when you don't know exact path" \
  --context "Finding configuration files or source code"
```

**Category: Development Workflows**

```bash
# Task 5: git-commit-workflow
desktop-agent record
desktop-agent key Super
desktop-agent type "terminal"
desktop-agent key Return
desktop-agent type "cd ~/Projects/desktop-agent"
desktop-agent key Return
desktop-agent type "git status"
desktop-agent key Return
desktop-agent type "git add ."
desktop-agent key Return
desktop-agent type 'git commit -m "Update task repository"'
desktop-agent key Return
desktop-agent save-task git-commit-workflow \
  --description "Stage all changes and create git commit" \
  --purpose "Quick commit during development" \
  --context "Saving work in progress" \
  --params '[{"name": "message", "type": "string", "default": "Update"}]'

# Task 6: run-tests-and-report
desktop-agent record
desktop-agent key Super
desktop-agent type "terminal"
desktop-agent key Return
desktop-agent type "cd ~/Projects/my-app"
desktop-agent key Return
desktop-agent type "npm test 2>&1 | tee test-results.txt"
desktop-agent key Return
desktop-agent save-task run-tests-and-report \
  --description "Run test suite and save output to file" \
  --purpose "Testing with result archival" \
  --context "Before commits or deployments"
```

**Category: Multi-App Workflows**

```bash
# Task 7: code-and-terminal-split
desktop-agent record
desktop-agent key Super
desktop-agent type "code"
desktop-agent key Return
# Wait for VS Code
desktop-agent key Super+Left  # Tile left
desktop-agent key Super
desktop-agent type "terminal"
desktop-agent key Return
# Wait for terminal
desktop-agent key Super+Right  # Tile right
desktop-agent save-task code-and-terminal-split \
  --description "Open VS Code and Terminal in split screen" \
  --purpose "Development environment setup" \
  --context "Starting coding session"

# Task 8: extract-text-to-file
desktop-agent record
# Assume you have some text selected
desktop-agent key Ctrl+c
desktop-agent key Super
desktop-agent type "gedit"
desktop-agent key Return
# Wait for gedit
desktop-agent key Ctrl+v
desktop-agent key Ctrl+s
desktop-agent type "extracted-text.txt"
desktop-agent key Return
desktop-agent save-task extract-text-to-file \
  --description "Copy selected text and save to new file" \
  --purpose "Extract content from any application to text file" \
  --context "Saving important content from web or apps"
```

---

## Phase 3: Task Composition (Future)

**Once parameters + validation are working, add composition:**

```python
# Schema migration
def add_composition_support():
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    try:
        c.execute("ALTER TABLE tasks ADD COLUMN subtasks TEXT")  # JSON array
        c.execute("ALTER TABLE tasks ADD COLUMN composition_type TEXT")  # sequential/parallel/conditional
        conn.commit()
    except sqlite3.OperationalError:
        pass
    conn.close()

# Create composed task
def create_composed_task(name, description, purpose, subtask_names, composition_type="sequential"):
    """
    Create task that chains other tasks together
    
    composition_type: 'sequential' | 'parallel' | 'conditional'
    """
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    
    # Verify all subtasks exist
    placeholders = ','.join(['?' for _ in subtask_names])
    c.execute(f"SELECT name FROM tasks WHERE name IN ({placeholders})", subtask_names)
    found = [row[0] for row in c.fetchall()]
    missing = set(subtask_names) - set(found)
    
    if missing:
        print(f"Error: Missing subtasks: {missing}")
        conn.close()
        return False
    
    subtasks_json = json.dumps(subtask_names)
    embed_text = f"{name}. {description}. {purpose}"
    embedding = get_embedding(embed_text)
    
    try:
        c.execute("""
            INSERT INTO tasks (name, description, purpose, subtasks, composition_type, embedding)
            VALUES (?, ?, ?, ?, ?, ?)
        """, (name, description, purpose, subtasks_json, composition_type,
              json.dumps(embedding) if embedding else None))
        conn.commit()
        print(f"Composed task created: {name}")
        print(f"  Subtasks: {' → '.join(subtask_names)}")
        return True
    except sqlite3.IntegrityError:
        print(f"Task '{name}' already exists.")
        return False
    finally:
        conn.close()

# Example usage
create_composed_task(
    "full-research-workflow",
    "Search web, extract results, and save to notes",
    "Complete research workflow from search to documentation",
    ["web-search-linux-automation", "extract-text-to-file", "append-clipboard-to-notes"],
    "sequential"
)
```

---

## Quick Start: Implement Today

**Step 1:** Backup current working version
```bash
cp ~/.local/bin/desktop-agent.py ~/.local/bin/desktop-agent.py.backup-$(date +%Y%m%d)
```

**Step 2:** Add parameter support (copy functions from 1A above)

**Step 3:** Add success tracking (copy functions from 1B above)

**Step 4:** Test with a parameterized task:
```bash
# Record a search task with ${query} placeholder
desktop-agent record
desktop-agent focus Firefox
desktop-agent key Ctrl+l
desktop-agent type '${query}'  # Literal string
desktop-agent key Return
desktop-agent save-task search-generic --description "Generic web search"

# Use it with parameter
desktop-agent replay --run "search-generic" --param query="linux automation"
```

**Step 5:** Add 5 new foundational tasks (from Phase 2 examples)

**Step 6:** Watch success rates build up:
```bash
desktop-agent tasks search "find files" --min-success 0.7
```

---

## Measuring Success

After 1 week of using enhanced system:

```bash
# Check stats
sqlite3 ~/.cache/desktop-agent/tasks.db "
  SELECT 
    COUNT(*) as total_tasks,
    AVG(success_rate) as avg_success,
    SUM(use_count) as total_uses
  FROM tasks
"

# View top performers
sqlite3 ~/.cache/desktop-agent/tasks.db "
  SELECT name, use_count, success_rate 
  FROM tasks 
  ORDER BY use_count DESC 
  LIMIT 10
"

# View failure patterns
sqlite3 ~/.cache/desktop-agent/tasks.db "
  SELECT t.name, COUNT(*) as failures
  FROM task_runs r
  JOIN tasks t ON r.task_id = t.id
  WHERE r.success = 0
  GROUP BY t.name
  ORDER BY failures DESC
"
```

---

## Next Steps After Phase 1

1. Pattern extraction (find common micro-tasks)
2. Conditional execution (if app is open, else open it)
3. Adaptive tasks (use OCR to verify state)
4. Complex compositions (chain 3+ tasks with conditionals)

But start with **parameters + success tracking** - those alone will 3x the value of your task repository.
