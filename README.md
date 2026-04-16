# Desktop Agent - Task-Caching Desktop Automation

**Linux desktop automation CLI with AI-curated task recording and semantic search**

---

## 🚀 Quick Start

```bash
# View all tasks
desktop-agent tasks

# Search for a task
desktop-agent tasks search "check disk space"

# Run a task
desktop-agent replay --run "check-disk-space"

# Record new task
desktop-agent record
# ... do your steps ...
desktop-agent save-task my-task --description "What it does" --purpose "Why useful"
```

---

## 📚 Documentation

**START HERE:** Read [`COMPLETE_HANDOFF.md`](./COMPLETE_HANDOFF.md) for full details

**Quick Reference:**
- [`SESSION_SUMMARY.md`](./SESSION_SUMMARY.md) - What we built today
- [`IMPLEMENTATION_STATUS.md`](./IMPLEMENTATION_STATUS.md) - Current status
- [`TASK_REPOSITORY_ROADMAP.md`](./TASK_REPOSITORY_ROADMAP.md) - 38 tasks to add
- [`IMPLEMENTATION_GUIDE.md`](./IMPLEMENTATION_GUIDE.md) - Code examples
- [`ANALYSIS.md`](./ANALYSIS.md) - System architecture

---

## ✨ Features

- ✅ **Task Recording** - Record GUI actions as reusable tasks
- ✅ **Semantic Search** - Find tasks by description using embeddings
- ✅ **Parameters** - Reusable tasks with `${variable}` placeholders
- ✅ **Success Tracking** - Auto-track what works (✓ ? ✗ indicators)
- ✅ **Micro-Tasks** - Common patterns extracted as building blocks
- ✅ **OCR Support** - Extract text from screenshots
- ✅ **Multi-Drive** - Navigate across multiple hard drives

---

## 📊 Current Status

- **35 tasks** in repository
- **11 micro-tasks** extracted
- **100% success rate** on executed tasks
- **Parameters working** (3 parameterized tasks)
- **Success tracking active**

---

## 🔧 Technical Details

**Location:** `~/.local/bin/desktop-agent.py`  
**Database:** `~/.cache/desktop-agent/tasks.db` (SQLite)  
**Embeddings:** nomic-embed-text (768-dim vectors)  
**Dependencies:** pyatspi, pytesseract, pillow, requests, xdotool, scrot

---

## 💡 Examples

### Basic Usage
```bash
# Check disk space across all drives
desktop-agent replay --run check-disk-space

# Navigate to mounted drives
desktop-agent replay --run view-mounted-drives

# Find large files
desktop-agent replay --run find-large-files
```

### Parameterized Tasks
```bash
# Open different apps with same task
desktop-agent replay --run --param app_name="firefox" open-app
desktop-agent replay --run --param app_name="terminal" open-app

# Run different terminal commands
desktop-agent replay --run --param command="ls -la" run-command
desktop-agent replay --run --param command="df -h" run-command
```

### Recording New Tasks
```bash
desktop-agent record
# Do your steps in the GUI...
desktop-agent save-task my-workflow \
  --description "Opens Firefox and checks email" \
  --purpose "Morning routine" \
  --context "Start of day"
```

---

## 🎯 Next Steps

1. **Task Composition** - Chain tasks together
2. **Conditional Logic** - If/else execution
3. **Auto-Pattern Extraction** - Suggest micro-tasks automatically
4. **More Foundation Tasks** - Git, networking, process management

---

## 📖 Project Structure

```
/home/mal/AI/desktop-agent/
├── README.md                       ← You are here
├── COMPLETE_HANDOFF.md             ← START HERE (full details)
├── SESSION_SUMMARY.md              ← Today's work
├── IMPLEMENTATION_STATUS.md        ← Current status
├── TASK_REPOSITORY_ROADMAP.md     ← 38 tasks to add
├── IMPLEMENTATION_GUIDE.md         ← Code examples
├── ANALYSIS.md                     ← Architecture
├── extract-micro-tasks.py          ← Pattern analysis
├── analyze-reddit-feed.py          ← OCR for Reddit
└── browse-and-analyze-reddit.sh    ← Reddit workflow

~/.cache/desktop-agent/
├── tasks.db                        ← All tasks + embeddings
└── recording.json                  ← Current recording

~/.local/bin/
└── desktop-agent.py                ← Main implementation
```

---

## 🏆 Achievements

**Phase 1 Complete:**
- ✅ Parameter support
- ✅ Success tracking
- ✅ Enhanced search
- ✅ Test case (Reddit)

**Phase 2 Complete:**
- ✅ 9 foundation tasks
- ✅ 11 micro-tasks extracted
- ✅ Multi-drive navigation

**Phase 3 (Next):**
- ⏳ Task composition
- ⏳ Conditional logic
- ⏳ Auto-pattern extraction

---

**Version:** 2.1 - Parameters + Success Tracking + Micro-Tasks  
**Last Updated:** 2026-04-16  
**Status:** Production Ready
