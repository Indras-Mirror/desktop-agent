# Desktop Agent - Project Handoff Report

## Project Overview

**Project**: desktop-agent  
**Location**: `/home/mal/.local/bin/desktop-agent.py`  
**GitHub**: https://github.com/Indras-Mirror/desktop-agent  
**Status**: Experimental (feature/task-cache branch)

Linux desktop automation CLI for AI agents with AT-SPI element detection, OCR text finding, and AI-curated task recording with semantic search.

---

## GitHub Repository

### Credentials
- **User**: Indras-Mirror (Excidos)
- **Token**: `[REDACTED - use git credential store]`
- **Email**: malichcoory@gmail.com

### Branches
- **main** - Original working code (backup)
- **feature/task-cache** - Experimental with task recording + semantic search

### Push to GitHub
```bash
cd /tmp/desktop-agent-repo
git add .
git -c user.name="Excidos" -c user.email="malichcoory@gmail.com" commit -m "message"
git push origin feature/task-cache
```

---

## Project Structure

```
~/.cache/desktop-agent/
├── tasks.db           # SQLite with task data + embeddings
└── recording.json    # Current recording state (persists across CLI calls)

~/.local/bin/
├── desktop-agent.py   # Main Python implementation
└── desktop-agent      # Symlink to python script
```

---

## Database Schema

```sql
CREATE TABLE tasks (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT UNIQUE NOT NULL,           -- Task identifier (goal-based)
    description TEXT,                     -- What task does
    purpose TEXT,                         -- Why useful
    context TEXT,                         -- When to use
    app_context TEXT,                     -- Requirements
    steps_json TEXT,                      -- Action sequence (see below)
    embedding BLOB,                       -- 768-dim nomic embedding
    success_rate REAL DEFAULT 1.0,
    last_used TIMESTAMP,
    use_count INTEGER DEFAULT 0,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE task_runs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    task_id INTEGER,
    executed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    success INTEGER,
    notes TEXT,
    FOREIGN KEY (task_id) REFERENCES tasks(id)
);
```

### Steps JSON Structure
```json
[
    {"command": "focus", "args": ["Firefox"], "description": "Focus window: Firefox", "timestamp": 1234567890},
    {"command": "key", "args": ["Ctrl+l"], "description": "Press key: Ctrl+l", "timestamp": 1234567891},
    {"command": "type", "args": ["search query"], "description": "Type: search query", "timestamp": 1234567892},
    {"command": "key", "args": ["Return"], "description": "Press key: Return", "timestamp": 1234567893}
]
```

---

## Task Recording System

### Recording Flow (AI-Curated)

1. **Start recording**: `desktop-agent record`
2. **Execute steps**: Use normal commands (focus, click, type, key, etc.)
3. **Save task**: AI evaluates success, then saves with metadata

### Recording Persistence
- Recording state saved to `~/.cache/desktop-agent/recording.json`
- Survives CLI restarts - steps accumulate until saved

### Commands that Record
- `focus` - Focus window
- `click` - Click coordinates or @eN element
- `type` - Type text
- `key` - Press key
- `screenshot` - Take screenshot
- `region` - Take region screenshot

### Save Task Command
```bash
desktop-agent save-task <name> \
  --description "What the task does" \
  --purpose "Why it's useful" \
  --context "When to use it" \
  --app-context "Requirements"
```

### Task Commands
```bash
desktop-agent tasks              # List all tasks
desktop-agent tasks search <q>    # Semantic search
desktop-agent replay <query>      # Dry-run (show steps)
desktop-agent replay --run <query> # Execute with semantic match
desktop-agent forget <name>       # Delete task
```

---

## Semantic Search

### How It Works
1. **Embedding**: Uses `nomic-embed-text` via `http://localhost:9086/v1/embeddings`
2. **Text for embedding**: Combines name + description + purpose
3. **Similarity**: Cosine similarity in pure Python (no numpy dependency)
4. **Fallback**: First tries exact name match, then semantic search

### Embedding Server
- **URL**: `http://localhost:9086/v1/embeddings`
- **Model**: nomic-embed-text-v1.5
- **Dimension**: 768

### Example Searches
```bash
# "edit text" finds open-gedit-type-text (66%)
# "run terminal" finds open-terminal-run-command (79%)
# "capture screenshot" finds capture-screenshot (84%)
# "take notes while researching" finds research-web-take-notes (69%)
```

---

## Current Task Repository (14 Tasks)

| Task Name | Description | Purpose |
|-----------|-------------|---------|
| `open-gedit-type-text` | Open gedit via Activities, type text | Quick note taking |
| `capture-screenshot` | Full screen capture to file | Screen capture |
| `web-search-linux-automation` | Firefox search + open result | Research |
| `open-terminal-run-command` | Open terminal, run shell command | Command execution |
| `check-weather-website-cli` | Web search + CLI weather (curl wttr.in) | Multi-source weather |
| `navigate-folder-create-file` | File manager + terminal file creation | File management |
| `open-code-system-monitor` | Open VS Code + System Monitor | Dev environment setup |
| `research-web-take-notes` | Web search + open gedit for notes | Research & documentation |
| `copy-paste-between-apps` | Alt+Tab switch, Ctrl+c/v between apps | Clipboard workflow |
| `play-music-youtube` | YouTube Music via Firefox, search & play | Background music |
| `capture-region-screenshot` | Region screenshot (x,y,w,h) | Partial screen capture |
| `window-management-basics` | List windows, focus, Alt+Tab, maximize | Window navigation |
| `open-system-settings` | Open system settings via Activities | System configuration |
| `switch-workspace-open-app` | Switch workspaces (Ctrl+Right), open app | Virtual desktop org |

### Test Replays
```bash
# Works - semantic matching finds correct task
desktop-agent replay "capture screenshot"
desktop-agent replay --run "edit text"
desktop-agent tasks search "open developer tools"
```

---

## Technical Implementation Details

### Dependencies (Already Installed)
- python3
- pyatspi (AT-SPI element detection)
- pytesseract + tesseract (OCR)
- Pillow (image processing)
- xdotool (keyboard/mouse)
- scrot (screenshots)
- requests (embedding API)

### No External Dependencies
- Cosine similarity implemented in pure Python (math module)
- File-based recording persistence (JSON)

### Embedding API Integration
```python
def get_embedding(text):
    try:
        resp = requests.post(
            "http://localhost:9086/v1/embeddings",
            json={"input": [text], "model": "nomic"},
            timeout=10
        )
        return resp.json()["data"][0]["embedding"]
    except Exception as e:
        print(f"Warning: Embedding failed: {e}")
        return None
```

### Replay Execution
When `replay --run` executes:
- Parses each step's command + args
- Maps to desktop-agent functions (focus, click, type, key, etc.)
- Adds 0.5s delay between steps for reliability

---

## Known Limitations

1. **Spotify**: Spotify desktop app has GPU issues, use web (YouTube Music) instead
2. **File Manager**: Some operations complex; terminal `touch` more reliable
3. **Click by @eN**: Requires recent `snapshot -i` - element refs expire
4. **Recording**: Commands must be run via desktop-agent CLI to record steps

---

## Extending the Project

### Adding New Commands to Recording
Add `record_step()` call in main() command handler:
```python
elif cmd == "new-command":
    some_function(args)
    record_step("new-command", args, f"Description: {args}")
```

### Adding New Task Types
- Create new recording: `desktop-agent record`
- Execute steps naturally
- Save with rich metadata: `desktop-agent save-task <name> --description "..." --purpose "..."`

### Improving Semantic Search
- Could add more context fields to embedding text
- Could weight purpose/context differently
- Could add task success tracking for quality scoring

### Database Operations
```bash
# View all tasks
sqlite3 ~/.cache/desktop-agent/tasks.db "SELECT name, description, purpose FROM tasks"

# View task steps
sqlite3 ~/.cache/desktop-agent/tasks.db "SELECT steps_json FROM tasks WHERE name='task-name'"

# Check embeddings
sqlite3 ~/.cache/desktop-agent/tasks.db "SELECT name, length(embedding) FROM tasks"

# Delete task
desktop-agent forget <task-name>
```

---

## Revert to Original

If experimental breaks and you need to restore working version:
```bash
# Option 1: From GitHub main branch
cd /tmp
git clone https://github.com/Indras-Mirror/desktop-agent.git
cp desktop-agent/main/desktop-agent.py.original ~/.local/bin/desktop-agent.py

# Option 2: From local backup
cp ~/.local/bin/desktop-agent.py.original ~/.local/bin/desktop-agent.py
```

---

## Files to Commit for Full Sync

```
/home/mal/.local/bin/desktop-agent.py          # Main implementation
/home/mal/.claude/skills/desktop-agent/SKILL.md  # Documentation
~/.cache/desktop-agent/tasks.db                # Task repository (not committed - local only)
~/.cache/desktop-agent/recording.json          # Current recording state
```

---

## Quick Start for New AI

```bash
# Test existing tasks
desktop-agent tasks
desktop-agent tasks search "search the web"
desktop-agent replay "take a screenshot"

# Record new task
desktop-agent record
<execute steps>
desktop-agent save-task my-new-task --description "..." --purpose "..."

# Use semantic search
desktop-agent replay "I want to play music"
# → finds play-music-youtube
```

---

## Contact / Context

- **User**: mal (malichcoory@gmail.com)
- **System**: Linux (Cinnamon desktop)
- **Embedding Server**: Running at localhost:9086 (from Odin project)
- **Token used for GitHub**: [REDACTED - use git credential store]

---

**Last Updated**: 2026-04-15  
**Version**: 1.1 - Task Caching with Semantic Search
**Status**: Production Ready (feature branch)